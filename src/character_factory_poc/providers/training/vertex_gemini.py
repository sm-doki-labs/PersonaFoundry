"""Vertex Gemini 감독 튜닝 (LLD §8.9·§5.15, D-0044).

공식 문서 확인(2026-10-27): `tuningJobs.create`는
`POST https://{location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{location}/tuningJobs`,
`tuningJobs.get`는 `GET .../v1/{name}`이고, 응답 `TuningJob`은 `name`, `state`
(`JOB_STATE_*`), `baseModel`, `tunedModel.model`, `tunedModel.checkpoints[]`
(`checkpointId`, `epoch`, `step`, `endpoint`)를 담는다. 근거는 aiplatform v1 REST discovery
문서와 googleapis의 `google/cloud/aiplatform/v1/tuning_job.proto`다.

plan은 학습 JSONL을 Vertex 형식(`systemInstruction` + `contents[{role, parts}]`)으로 바꾸고
글자 수를 토큰으로 근사해 비용을 낸다(근사 비율은 basis에 남긴다). 체크포인트의 epoch·step은
공급자가 준 원값만 기록하고 중간 epoch를 추정하지 않는다. 토큰은 주입 함수나 `gcloud auth
print-access-token`으로 받고 값은 출력·기록하지 않는다.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.store import write_once_text
from character_factory_poc.contracts.training import (
    Checkpoint,
    CostEstimate,
    ModelBinding,
    TrainingRun,
    Transfer,
)
from character_factory_poc.providers.training.errors import (
    TrainingError,
    TrainingIntegrityError,
    TrainingLimitError,
    TrainingNotReadyError,
)
from character_factory_poc.providers.training.port import TrainRequest, resolve_dataset_files
from character_factory_poc.providers.training.settings import as_float, as_int, as_str

DEFAULT_BASE_MODEL = "gemini-3.1-flash-lite"
DEFAULT_PRICE_PER_MILLION = 3.0
PRICE_SOURCE = (
    "Google Cloud Vertex AI 생성 AI 가격(2026-10-27 웹 검색 확인; 공식 페이지 직접 확인 필요)"
)


class VertexGeminiProvider:
    name = "vertex_gemini"

    def __init__(self, cfg: ProviderConfig | None = None):
        self.cfg = cfg or ProviderConfig(adapter="vertex_gemini")
        x = self.cfg.extra
        self.base_model = self.cfg.model or as_str(
            x, ("base_model", "baseModel"), DEFAULT_BASE_MODEL
        )
        self.location = as_str(x, ("location",), "us-central1")
        self.project = as_str(x, ("project",), "")
        if not self.project:
            env_name = as_str(x, ("project_env",), "GOOGLE_CLOUD_PROJECT")
            self.project = os.environ.get(env_name, "") if env_name else ""
        self.base_url = as_str(x, ("base_url",), "").rstrip("/")
        if not self.base_url:
            self.base_url = f"https://{self.location}-aiplatform.googleapis.com"
        self.epochs = as_int(x, ("epochs", "epoch_count"), 3, minimum=1)
        self.chars_per_token = as_float(x, ("chars_per_token",), 1.5, minimum=0.1)
        self.price_per_million = as_float(
            x,
            ("price_per_million_tokens_usd", "price_per_million"),
            DEFAULT_PRICE_PER_MILLION,
            minimum=0.0,
        )
        self.adapter_size = as_str(x, ("adapter_size",), "")
        self.training_uri = as_str(
            x, ("training_dataset_uri", "gcs_train_uri", "trainingDatasetUri"), ""
        )
        self.validation_uri = as_str(
            x, ("validation_dataset_uri", "gcs_validation_uri", "validationDatasetUri"), ""
        )
        self.display_name = as_str(x, ("tuned_model_display_name",), "")
        self.token_env = as_str(x, ("token_env",), "")
        self.token_file = as_str(x, ("token_file",), "")
        self.gcloud_timeout_s = as_float(x, ("gcloud_timeout_s",), 30.0, minimum=1.0)
        self.max_cost_usd = as_float(x, ("max_cost_usd",), 20.0, minimum=0.0)
        self.client = x.get("client") or httpx.Client(timeout=60.0)
        self._token_provider: Callable[[], str] | None = x.get("token_provider")
        self._access_token = as_str(x, ("access_token",), "")

    def _token(self) -> str:
        if self._token_provider is not None:
            return self._token_provider()
        if self._access_token:
            return self._access_token
        if self.token_env:
            value = os.environ.get(self.token_env)
            if not value:
                raise TrainingError(f"환경변수 {self.token_env}에 Vertex 접근 토큰이 없다")
            return value
        if self.token_file:
            value = Path(self.token_file).read_text("utf-8").strip()
            if not value:
                raise TrainingError(f"토큰 파일이 비었다: {self.token_file}")
            return value
        try:
            proc = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True,
                timeout=self.gcloud_timeout_s,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TrainingError(
                f"gcloud 접근 토큰을 얻지 못했다({type(exc).__name__}). token_provider를 주입한다"
            ) from None
        if proc.returncode != 0:
            raise TrainingError(f"gcloud auth print-access-token 실패(rc={proc.returncode})")
        value = (proc.stdout or b"").decode("utf-8", "replace").strip()
        if not value:
            raise TrainingError("gcloud auth print-access-token이 빈 값을 돌려줬다")
        return value

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}

    def _check_budget(self, run: TrainingRun) -> None:
        if run.estimate.usd is None:
            raise TrainingLimitError("예상 비용이 없어 제출할 수 없다")
        limit = min(run.budgetUsd, self.max_cost_usd)
        if run.estimate.usd > limit + 1e-9:
            raise TrainingLimitError(
                f"예상 비용 {run.estimate.usd:.4f} USD가 상한 {limit:.4f} USD를 넘는다"
            )

    def _convert(self, source: Path, dest: Path) -> tuple[int, str]:
        lines: list[str] = []
        chars = 0
        for number, line in enumerate(source.read_text("utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise TrainingIntegrityError(f"{source.name}:{number} JSONL이 아니다") from exc
            messages = row.get("messages")
            if not isinstance(messages, list) or not messages:
                raise TrainingIntegrityError(f"{source.name}:{number} messages가 없다")
            system: list[str] = []
            contents: list[dict[str, Any]] = []
            for message in messages:
                if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                    raise TrainingIntegrityError(f"{source.name}:{number} 메시지 형식이 다르다")
                role = message.get("role")
                text = message["content"]
                chars += len(text)
                if role == "system":
                    system.append(text)
                elif role in {"user", "assistant"}:
                    contents.append(
                        {
                            "role": "user" if role == "user" else "model",
                            "parts": [{"text": text}],
                        }
                    )
                else:
                    raise TrainingIntegrityError(
                        f"{source.name}:{number} role={role}은 옮길 수 없다"
                    )
            if not contents:
                raise TrainingIntegrityError(f"{source.name}:{number} user/assistant 메시지가 없다")
            out: dict[str, Any] = {}
            if system:
                out["systemInstruction"] = {"parts": [{"text": "\n".join(system)}]}
            out["contents"] = contents
            lines.append(json.dumps(out, ensure_ascii=False, sort_keys=True))
        write_once_text(dest, "\n".join(lines) + ("\n" if lines else ""))
        return chars, sha256_file(dest)

    def plan(self, request: TrainRequest) -> TrainingRun:
        files = resolve_dataset_files(request)
        out_dir = request.plan_dir / "vertex"
        out_dir.mkdir(parents=True, exist_ok=True)
        total_chars = 0
        transfers: list[Transfer] = []
        for item in files:
            name = "train" if item.split == "train" else item.split.replace("_", "-")
            dest = out_dir / f"{name}.jsonl"
            chars, digest = self._convert(item.path, dest)
            total_chars += chars
            transfers.append(
                Transfer(
                    path=f"vertex/{dest.name}",
                    bytes=dest.stat().st_size,
                    sha256=digest,
                )
            )
        dataset_tokens = math.ceil(total_chars / self.chars_per_token)
        billable = dataset_tokens * self.epochs
        usd = round(billable / 1_000_000 * self.price_per_million, 4)
        basis = (
            f"글자 {total_chars} ÷ {self.chars_per_token:g} ≈ {dataset_tokens} 토큰"
            "(글자 기반 근사) "
            f"× epoch {self.epochs} = {billable} 과금 토큰; 단가 ${self.price_per_million:g}/1M "
            f"학습 토큰({PRICE_SOURCE}); 기반 모델 기본값 {self.base_model} — "
            "착수 때 지원 목록 확인 필요"
        )
        requested: dict[str, Any] = {
            "baseModel": self.base_model,
            "epochs": self.epochs,
            "charsPerToken": self.chars_per_token,
            "pricePerMillionTokensUsd": self.price_per_million,
            "vertexFormat": "systemInstruction+contents",
        }
        if self.adapter_size:
            requested["adapterSize"] = self.adapter_size
        if self.training_uri:
            requested["trainingDatasetUri"] = self.training_uri
        if self.validation_uri:
            requested["validationDatasetUri"] = self.validation_uri
        return TrainingRun(
            characterId=request.dataset.characterId,
            datasetRev=request.dataset.datasetRev,
            datasetDigest=request.dataset.digest,
            provider="vertex_gemini",
            baseModel=self.base_model,
            baseModelRevision="",
            requestedConfig=requested,
            dryRun=True,
            estimate=CostEstimate(usd=usd, billableTokens=billable, basis=basis),
            budgetUsd=request.budget_usd,
            status="PLANNED",
            transfers=transfers,
        )

    def _resource(self, value: str) -> str:
        if value.startswith("projects/"):
            return value
        if not self.project:
            raise TrainingError("project가 없어 tuningJob 이름을 만들 수 없다")
        return f"projects/{self.project}/locations/{self.location}/tuningJobs/{value}"

    def _error(self, response: httpx.Response, what: str) -> TrainingError:
        body = response.text[:300] if response.text else ""
        return TrainingError(f"Vertex {what} 실패: HTTP {response.status_code} {body}".strip())

    def submit(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        self._check_budget(run)
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        if run.status in {"SUBMITTED", "RUNNING"} and run.jobId:
            return run
        if not self.project:
            raise TrainingError(
                "Vertex 제출에는 project가 필요하다([providers.*] project 또는 환경변수)"
            )
        if not self.training_uri:
            raise TrainingError(
                "Vertex 제출에는 gs:// 학습 데이터 URI가 필요하다. 이번 PoC는 업로드를 하지 않는다"
            )
        spec: dict[str, Any] = {
            "trainingDatasetUri": self.training_uri,
            "hyperParameters": {"epochCount": str(self.epochs)},
        }
        if self.validation_uri:
            spec["validationDatasetUri"] = self.validation_uri
        if self.adapter_size:
            spec["hyperParameters"]["adapterSize"] = self.adapter_size
        display = self.display_name or f"cfp-{run.characterId}-{run.datasetRev}"
        body = {
            "baseModel": run.baseModel,
            "tunedModelDisplayName": display[:128],
            "supervisedTuningSpec": spec,
        }
        url = f"{self.base_url}/v1/projects/{self.project}/locations/{self.location}/tuningJobs"
        response = self.client.post(url, json=body, headers=self._headers())
        if response.status_code >= 400:
            raise self._error(response, "튜닝 제출")
        job = response.json()
        name = job.get("name")
        if not isinstance(name, str) or not name:
            raise TrainingIntegrityError("Vertex 제출 응답에 tuningJob 이름이 없다")
        applied = dict(run.requestedConfig)
        applied.update(
            {
                "baseModel": job.get("baseModel", run.baseModel),
                "tuningJobResource": name,
                "submittedState": job.get("state", ""),
            }
        )
        return run.model_copy(
            update={
                "dryRun": False,
                "status": self._map_state(str(job.get("state") or ""), "SUBMITTED"),
                "jobId": name,
                "appliedConfig": applied,
            }
        )

    @staticmethod
    def _map_state(state: str, default: str) -> str:
        if state == "JOB_STATE_SUCCEEDED":
            return "SUCCEEDED"
        if state in {"JOB_STATE_FAILED", "JOB_STATE_EXPIRED", "JOB_STATE_PARTIALLY_SUCCEEDED"}:
            return "FAILED"
        if state in {"JOB_STATE_CANCELLED", "JOB_STATE_CANCELLING"}:
            return "CANCELLED"
        if state in {"JOB_STATE_QUEUED", "JOB_STATE_PENDING"}:
            return "SUBMITTED"
        if state in {"JOB_STATE_RUNNING", "JOB_STATE_UPDATING", "JOB_STATE_PAUSED"}:
            return "RUNNING"
        return default

    def _checkpoints(self, job: dict[str, Any]) -> list[Checkpoint]:
        tuned = job.get("tunedModel") or {}
        model = str(tuned.get("model") or "")
        out: list[Checkpoint] = []
        for raw in tuned.get("checkpoints") or []:
            checkpoint_id = str(raw.get("checkpointId") or "")
            if not checkpoint_id:
                raise TrainingIntegrityError("Vertex 체크포인트에 checkpointId가 없다")
            epoch = raw.get("epoch")
            step = raw.get("step")
            epoch_value = (
                int(epoch)
                if isinstance(epoch, str) and epoch.isdigit()
                else epoch
                if isinstance(epoch, int) and not isinstance(epoch, bool)
                else None
            )
            step_value = (
                int(step)
                if isinstance(step, str) and step.isdigit()
                else step
                if isinstance(step, int) and not isinstance(step, bool)
                else None
            )
            out.append(
                Checkpoint(
                    checkpointId=checkpoint_id,
                    epoch=epoch_value,
                    step=step_value,
                    ref=str(raw.get("endpoint") or model or checkpoint_id),
                )
            )
        return out

    def _get(self, name: str) -> dict[str, Any]:
        response = self.client.get(
            f"{self.base_url}/v1/{self._resource(name)}", headers=self._headers()
        )
        if response.status_code >= 400:
            raise self._error(response, "상태 조회")
        return response.json()

    def status(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        if not run.jobId:
            raise TrainingNotReadyError("Vertex 튜닝 작업이 아직 제출되지 않았다")
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        job = self._get(run.jobId)
        state = str(job.get("state") or "")
        applied = dict(run.appliedConfig)
        applied["providerState"] = state
        if isinstance(job.get("tunedModel"), dict):
            applied["tunedModel"] = job["tunedModel"]
        stats = job.get("tuningDataStats")
        if isinstance(stats, dict) and isinstance(stats.get("supervisedTuningDataStats"), dict):
            applied["tuningDataStats"] = stats["supervisedTuningDataStats"]
        return run.model_copy(
            update={
                "status": self._map_state(state, "RUNNING"),
                "checkpoints": self._checkpoints(job) or run.checkpoints,
                "appliedConfig": applied,
            }
        )

    def collect(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        current = self.status(run, request)
        if current.status != "SUCCEEDED":
            raise TrainingNotReadyError(f"Vertex 튜닝이 아직 끝나지 않았다: {current.status}")
        if not current.jobId:
            raise TrainingNotReadyError("Vertex 튜닝 작업 ID가 없다")
        job = self._get(current.jobId)
        tuned = job.get("tunedModel") or {}
        model = str(tuned.get("model") or "")
        if not model:
            raise TrainingIntegrityError("성공한 Vertex 튜닝 응답에 tunedModel.model이 없다")
        checkpoints = self._checkpoints(job)
        checkpoint_id = checkpoints[-1].checkpointId if checkpoints else model
        applied = dict(current.appliedConfig)
        applied["tunedModelModel"] = model
        applied["providerState"] = str(job.get("state") or "")
        return current.model_copy(
            update={
                "checkpoints": checkpoints,
                "appliedConfig": applied,
                "modelBinding": ModelBinding(
                    provider="vertex_gemini", ref=model, checkpointId=checkpoint_id
                ),
            }
        )
