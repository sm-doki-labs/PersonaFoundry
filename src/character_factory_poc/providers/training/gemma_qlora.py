"""Gemma 4 31B QLoRA 임대 GPU 학습 (LLD §8.9, 학습 가이드 §11, D-0044).

기본 설정은 학습 가이드 §11과 D-0045 (3)을 따른다: unsloth/gemma-4-31B-it-unsloth-bnb-4bit
revision 8e256fc6, QLoRA r16/α32, dropout 0, LR 5e-5 linear, warmup 5%, 배치 1×누적 4,
최대 4,096토큰, seed 3407, 3 epoch, 1·2·3 epoch 저장, assistant 답변만 손실.

plan은 데이터셋 파일의 바이트·sha256과 스텝 수·GPU 시간·비용만 낸다. submit은 조각 전송 →
원격 sha256 확인 → 학습 시작 순서이고, 완료는 계획 파일이 아니라 원격 complete.json으로만
판정한다. collect는 회수한 파일의 해시를 확인한 뒤에만 원격 폴더를 지운다.
"""

from __future__ import annotations

import hashlib
import json
import math
import shlex
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.contracts.training import (
    Checkpoint,
    CostEstimate,
    ModelBinding,
    TrainingRun,
    Transfer,
)
from character_factory_poc.providers.training.errors import (
    RemoteHostError,
    TrainingIntegrityError,
    TrainingLimitError,
    TrainingNotReadyError,
)
from character_factory_poc.providers.training.hosts import RemoteHost, VastRemoteHost
from character_factory_poc.providers.training.port import TrainRequest, resolve_dataset_files
from character_factory_poc.providers.training.settings import as_float, as_int, as_int_list, as_str


@dataclass(frozen=True)
class GemmaSettings:
    base_model: str = "unsloth/gemma-4-31B-it-unsloth-bnb-4bit"
    revision: str = "8e256fc6"
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.0
    learning_rate: float = 5e-5
    lr_scheduler: str = "linear"
    warmup_ratio: float = 0.05
    batch_size: int = 1
    grad_accum: int = 4
    max_seq_length: int = 4096
    seed: int = 3407
    epochs: int = 3
    save_epochs: tuple[int, ...] = (1, 2, 3)
    step_seconds: float = 6.0
    hourly_rate_usd: float = 0.80
    prep_overhead_seconds: float = 300.0
    max_gpu_hours: float = 8.0
    max_cost_usd: float = 20.0
    chunk_bytes: int = 8 * 1024 * 1024
    remote_root: str = "/workspace/cfp"

    @classmethod
    def from_extra(cls, extra: dict[str, Any], model: str = "") -> GemmaSettings:
        save_epochs = as_int_list(extra, ("save_epochs", "saveEpochs"), [1, 2, 3])
        return cls(
            base_model=model or as_str(extra, ("base_model", "baseModel"), cls.base_model),
            revision=as_str(extra, ("revision",), cls.revision),
            lora_r=as_int(extra, ("lora_r", "loraR"), 16, minimum=1),
            lora_alpha=as_int(extra, ("lora_alpha", "loraAlpha"), 32, minimum=1),
            lora_dropout=as_float(extra, ("lora_dropout", "loraDropout"), 0.0, minimum=0.0),
            learning_rate=as_float(extra, ("learning_rate", "lr"), 5e-5, minimum=0.0),
            lr_scheduler=as_str(extra, ("lr_scheduler",), "linear"),
            warmup_ratio=as_float(extra, ("warmup_ratio",), 0.05, minimum=0.0),
            batch_size=as_int(extra, ("batch_size",), 1, minimum=1),
            grad_accum=as_int(extra, ("grad_accum",), 4, minimum=1),
            max_seq_length=as_int(extra, ("max_seq_length",), 4096, minimum=1),
            seed=as_int(extra, ("seed",), 3407),
            epochs=as_int(extra, ("epochs", "epoch_count"), 3, minimum=1),
            save_epochs=tuple(save_epochs),
            step_seconds=as_float(extra, ("step_seconds",), 6.0, minimum=0.0),
            hourly_rate_usd=as_float(extra, ("hourly_rate_usd",), 0.80, minimum=0.0),
            prep_overhead_seconds=as_float(extra, ("prep_overhead_seconds",), 300.0, minimum=0.0),
            max_gpu_hours=as_float(extra, ("max_gpu_hours",), 8.0, minimum=0.0),
            max_cost_usd=as_float(extra, ("max_cost_usd",), 20.0, minimum=0.0),
            chunk_bytes=as_int(extra, ("chunk_bytes",), 8 * 1024 * 1024, minimum=1),
            remote_root=as_str(extra, ("remote_root",), "/workspace/cfp"),
        )

    @property
    def effective_batch(self) -> int:
        return self.batch_size * self.grad_accum

    def requested_config(self) -> dict[str, Any]:
        return {
            "baseModel": self.base_model,
            "baseModelRevision": self.revision,
            "loraR": self.lora_r,
            "loraAlpha": self.lora_alpha,
            "loraDropout": self.lora_dropout,
            "learningRate": self.learning_rate,
            "lrScheduler": self.lr_scheduler,
            "warmupRatio": self.warmup_ratio,
            "batchSize": self.batch_size,
            "gradAccum": self.grad_accum,
            "maxSeqLength": self.max_seq_length,
            "seed": self.seed,
            "epochs": self.epochs,
            "saveEpochs": list(self.save_epochs),
            "lossOn": "assistant",
        }


def _safe_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)
    return cleaned or "run"


def _safe_rel(value: str) -> str:
    rel = PurePosixPath(value)
    if rel.is_absolute() or not rel.parts or ".." in rel.parts:
        raise TrainingIntegrityError(f"원격 완료 기록의 경로가 안전하지 않다: {value}")
    return rel.as_posix()


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sync_file(
    host: RemoteHost,
    local: Path,
    remote: str,
    chunk_bytes: int,
    transfer: Transfer,
) -> Transfer:
    """맞는 조각은 건너뛰고, 모든 조각과 합친 파일의 원격 해시를 확인한다."""
    digest = sha256_file(local)
    if digest != transfer.sha256:
        raise TrainingIntegrityError(
            f"전송할 파일의 sha256이 데이터셋 기록과 다르다: {transfer.path}"
        )
    if host.sha256(remote) == digest:
        return transfer.model_copy(update={"remoteSha256": digest})
    parts: list[str] = []
    with local.open("rb") as handle:
        index = 0
        while True:
            chunk = handle.read(chunk_bytes)
            if not chunk:
                break
            part = f"{remote}.part{index:06d}"
            want = hashlib.sha256(chunk).hexdigest()
            if host.sha256(part) != want:
                host.put_chunk(part, chunk)
            if host.sha256(part) != want:
                raise TrainingIntegrityError(f"조각의 원격 sha256이 다르다: {part}")
            parts.append(part)
            index += 1
    if not parts:
        host.put_chunk(remote, b"")
    else:
        host.concat(parts, remote)
    if host.sha256(remote) != digest:
        raise TrainingIntegrityError(f"합친 파일의 원격 sha256이 다르다: {remote}")
    return transfer.model_copy(update={"remoteSha256": digest})


class GemmaQLoraProvider:
    name = "gemma_qlora"

    def __init__(self, cfg: ProviderConfig | None = None):
        self.cfg = cfg or ProviderConfig(adapter="gemma_qlora")
        self.settings = GemmaSettings.from_extra(self.cfg.extra, self.cfg.model)

    def _job_dir(self, request: TrainRequest) -> str:
        root = self.settings.remote_root.rstrip("/")
        run = request.run_ref or "run"
        parts = [request.dataset.characterId, request.dataset.datasetRev, run]
        return "/".join([root, *(_safe_segment(p) for p in parts)])

    def _host(self) -> RemoteHost:
        host = self.cfg.extra.get("remote_host")
        if host is not None:
            return host
        return VastRemoteHost.from_config(self.cfg.extra)

    def _check_budget(self, run: TrainingRun) -> None:
        if run.estimate.usd is None:
            raise TrainingLimitError("예상 비용이 없어 제출할 수 없다")
        limit = min(run.budgetUsd, self.settings.max_cost_usd)
        if run.estimate.usd > limit + 1e-9:
            raise TrainingLimitError(
                f"예상 비용 {run.estimate.usd:.4f} USD가 상한 {limit:.4f} USD를 넘는다"
            )
        hours = run.estimate.gpuHours or 0.0
        if hours > self.settings.max_gpu_hours + 1e-9:
            raise TrainingLimitError(
                f"예상 GPU {hours:.2f}시간이 상한 {self.settings.max_gpu_hours:.2f}시간을 넘는다"
            )

    def _wall_hours(self, run: TrainingRun) -> float:
        """GPU 시간 상한과 비용 상한 가운데 더 빨리 닿는 쪽을 벽시계 상한으로 쓴다."""
        cap = self.settings.max_gpu_hours
        rate = self.settings.hourly_rate_usd
        if rate > 0:
            cap = min(cap, min(run.budgetUsd, self.settings.max_cost_usd) / rate)
        return max(cap, 1.0 / 3600.0)

    def plan(self, request: TrainRequest) -> TrainingRun:
        files = resolve_dataset_files(request)
        train_conversations = sum(f.conversations for f in files if f.split == "train")
        steps = math.ceil(
            train_conversations * self.settings.epochs / self.settings.effective_batch
        )
        seconds = steps * self.settings.step_seconds + self.settings.prep_overhead_seconds
        gpu_hours = seconds / 3600.0
        usd = round(gpu_hours * self.settings.hourly_rate_usd, 4)
        basis = (
            f"L40S ${self.settings.hourly_rate_usd:.2f}/h(기본값, 설정으로 바꾼다), "
            f"스텝당 {self.settings.step_seconds:g}초(소민 r3 실측 기본값), "
            f"준비 {self.settings.prep_overhead_seconds:g}초; "
            f"스텝 {steps} = ceil(대화 {train_conversations} × epoch {self.settings.epochs} / "
            f"유효 배치 {self.settings.effective_batch}); 2026-10-27 확인"
        )
        return TrainingRun(
            characterId=request.dataset.characterId,
            datasetRev=request.dataset.datasetRev,
            datasetDigest=request.dataset.digest,
            provider="gemma_qlora",
            baseModel=self.settings.base_model,
            baseModelRevision=self.settings.revision,
            requestedConfig=self.settings.requested_config(),
            dryRun=True,
            estimate=CostEstimate(
                usd=usd,
                gpuHours=round(gpu_hours, 4),
                basis=basis,
            ),
            budgetUsd=request.budget_usd,
            status="PLANNED",
            transfers=[Transfer(path=f.relative, bytes=f.bytes, sha256=f.sha256) for f in files],
        )

    def _ensure_script(self, host: RemoteHost, job_dir: str) -> None:
        source = Path(__file__).parent / "remote" / "train_qlora.py"
        text = source.read_text("utf-8")
        remote = f"{job_dir}/train_qlora.py"
        if host.sha256(remote) != sha256_text(text):
            host.write_text(remote, text)
        if host.sha256(remote) != sha256_text(text):
            raise TrainingIntegrityError("원격 학습 스크립트의 sha256이 다르다")

    def submit(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        self._check_budget(run)
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        if run.status in {"SUBMITTED", "RUNNING"} and run.jobId:
            return run
        host = self._host()
        job_dir = run.jobId or self._job_dir(request)
        files = resolve_dataset_files(request)
        old = {t.path: t for t in run.transfers}
        transfers: list[Transfer] = []
        for item in files:
            transfer = old.get(item.relative)
            if transfer is None:
                transfer = Transfer(path=item.relative, bytes=item.bytes, sha256=item.sha256)
            transfers.append(
                _sync_file(
                    host,
                    item.path,
                    f"{job_dir}/{item.relative}",
                    self.settings.chunk_bytes,
                    transfer,
                )
            )
        self._ensure_script(host, job_dir)
        for transfer in transfers:
            if host.sha256(f"{job_dir}/{transfer.path}") != transfer.sha256:
                raise TrainingIntegrityError(f"원격 파일의 sha256이 다르다: {transfer.path}")
        started = {
            "startedAt": _now(),
            "maxWallHours": self._wall_hours(run),
            "maxCostUsd": min(run.budgetUsd, self.settings.max_cost_usd),
            "hourlyRateUsd": self.settings.hourly_rate_usd,
            "datasetRev": run.datasetRev,
            "datasetDigest": run.datasetDigest,
        }
        host.write_text(f"{job_dir}/started.json", json.dumps(started, ensure_ascii=False))
        args = ["python", "train_qlora.py", "--output", "adapter"]
        for item in files:
            flag = "--train" if item.split == "train" else "--validation"
            args += [flag, item.relative]
        s = self.settings
        args += [
            "--base-model",
            s.base_model,
            "--revision",
            s.revision,
            "--epochs",
            str(s.epochs),
            "--max-seq-length",
            str(s.max_seq_length),
            "--seed",
            str(s.seed),
            "--lora-r",
            str(s.lora_r),
            "--lora-alpha",
            str(s.lora_alpha),
            "--lora-dropout",
            str(s.lora_dropout),
            "--learning-rate",
            str(s.learning_rate),
            "--lr-scheduler",
            s.lr_scheduler,
            "--warmup-ratio",
            str(s.warmup_ratio),
            "--batch-size",
            str(s.batch_size),
            "--grad-accum",
            str(s.grad_accum),
            "--save-epochs",
            ",".join(str(e) for e in s.save_epochs),
        ]
        wall_seconds = max(1, int(self._wall_hours(run) * 3600))
        command = (
            f"cd {shlex.quote(job_dir)} && nohup timeout {wall_seconds}s "
            f"{shlex.join(args)} > train.log 2>&1 & echo $!"
        )
        pid = host.run(["bash", "-lc", command])
        host.write_text(f"{job_dir}/pid.txt", pid.strip() + "\n")
        return run.model_copy(
            update={
                "dryRun": False,
                "status": "SUBMITTED",
                "jobId": job_dir,
                "transfers": transfers,
                "appliedConfig": dict(run.requestedConfig),
            }
        )

    def _checkpoints(self, data: dict[str, Any]) -> list[Checkpoint]:
        out: list[Checkpoint] = []
        for raw in data.get("checkpoints") or []:
            checkpoint_id = str(raw.get("checkpointId") or raw.get("id") or "")
            if not checkpoint_id:
                raise TrainingIntegrityError("원격 complete.json의 체크포인트에 ID가 없다")
            ref = str(raw.get("ref") or checkpoint_id)
            out.append(
                Checkpoint(
                    checkpointId=checkpoint_id,
                    epoch=_int_or_none(raw.get("epoch")),
                    step=_int_or_none(raw.get("step")),
                    ref=ref,
                )
            )
        return out

    def _limit_reason(self, started: dict[str, Any]) -> str | None:
        raw = started.get("startedAt")
        if not isinstance(raw, str):
            return None
        try:
            at = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if at.tzinfo is None:
            at = at.replace(tzinfo=UTC)
        hours = (datetime.now(UTC) - at).total_seconds() / 3600.0
        max_wall = float(started.get("maxWallHours", self.settings.max_gpu_hours))
        if hours > max_wall:
            return f"시간 상한 {max_wall:.2f}시간을 넘었다(경과 {hours:.2f}시간)"
        rate = float(started.get("hourlyRateUsd", self.settings.hourly_rate_usd))
        max_cost = float(started.get("maxCostUsd", self.settings.max_cost_usd))
        if hours * rate > max_cost:
            return f"비용 상한 {max_cost:.2f} USD를 넘었다(추정 {hours * rate:.2f} USD)"
        return None

    def status(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        if not run.jobId:
            raise TrainingNotReadyError("학습 작업이 아직 제출되지 않았다")
        if run.status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return run
        host = self._host()
        job = run.jobId
        complete = host.read_text(f"{job}/complete.json")
        if complete is not None:
            try:
                data = json.loads(complete)
            except json.JSONDecodeError as exc:
                raise TrainingIntegrityError("원격 complete.json을 읽을 수 없다") from exc
            if data.get("ok") is False:
                reason = str(data.get("error") or "원격 학습이 실패했다")
                return run.model_copy(
                    update={
                        "status": "FAILED",
                        "appliedConfig": {**run.appliedConfig, "error": reason},
                    }
                )
            checkpoints = self._checkpoints(data)
            applied = dict(run.appliedConfig)
            if isinstance(data.get("appliedConfig"), dict):
                applied.update(data["appliedConfig"])
            applied["completedAt"] = data.get("finishedAt", "")
            return run.model_copy(
                update={"status": "SUCCEEDED", "checkpoints": checkpoints, "appliedConfig": applied}
            )
        started = host.read_text(f"{job}/started.json")
        if started is not None:
            try:
                started_data = json.loads(started)
            except json.JSONDecodeError:
                started_data = {}
            reason = self._limit_reason(started_data)
            if reason:
                try:
                    host.run(["bash", "-lc", f"pkill -f {shlex.quote(job)} || true"])
                except RemoteHostError:
                    pass
                return run.model_copy(
                    update={
                        "status": "FAILED",
                        "appliedConfig": {**run.appliedConfig, "error": reason},
                    }
                )
        log = host.read_text(f"{job}/train.log")
        return run.model_copy(update={"status": "RUNNING" if log is not None else "SUBMITTED"})

    def collect(self, run: TrainingRun, request: TrainRequest) -> TrainingRun:
        current = self.status(run, request)
        if current.status != "SUCCEEDED":
            raise TrainingNotReadyError(f"학습 작업이 아직 끝나지 않았다: {current.status}")
        host = self._host()
        job = current.jobId
        if not job:
            raise TrainingNotReadyError("학습 작업 ID가 없다")
        raw = host.read_text(f"{job}/complete.json")
        if raw is None:
            raise TrainingNotReadyError("원격 complete.json이 없다")
        data = json.loads(raw)
        files = data.get("files") or []
        if not files:
            raise TrainingIntegrityError("원격 complete.json에 회수할 파일이 없다")
        artifact_dir = request.artifact_dir.resolve()
        artifact_dir.mkdir(parents=True, exist_ok=True)
        for item in files:
            rel = _safe_rel(str(item.get("path") or ""))
            dest = (artifact_dir / rel).resolve()
            if not dest.is_relative_to(artifact_dir):
                raise TrainingIntegrityError(f"회수 경로가 폴더 밖을 가리킨다: {rel}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            host.fetch(f"{job}/{rel}", dest)
            if sha256_file(dest) != str(item.get("sha256") or ""):
                raise TrainingIntegrityError(f"회수한 파일의 sha256이 다르다: {rel}")
            expected_bytes = item.get("bytes")
            if isinstance(expected_bytes, int) and dest.stat().st_size != expected_bytes:
                raise TrainingIntegrityError(f"회수한 파일의 바이트 수가 다르다: {rel}")
        host.delete(job)
        checkpoints = self._checkpoints(data)
        binding_ref = _safe_rel(str(data.get("modelBindingRef") or "adapter"))
        checkpoint_id = checkpoints[-1].checkpointId if checkpoints else "final"
        applied = dict(current.appliedConfig)
        if isinstance(data.get("appliedConfig"), dict):
            applied.update(data["appliedConfig"])
        applied["remoteDeleted"] = True
        return current.model_copy(
            update={
                "checkpoints": checkpoints,
                "appliedConfig": applied,
                "modelBinding": ModelBinding(
                    provider="gemma_qlora",
                    ref=str((artifact_dir / binding_ref).resolve()),
                    checkpointId=checkpoint_id,
                ),
            }
        )
