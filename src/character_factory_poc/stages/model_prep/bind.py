"""이미 학습된 모델의 연결 기록. 생성·학습 없이 HF 메타데이터와 설정만 확인한다."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, read_json, write_manifest, write_once_json
from character_factory_poc.contracts.model_binding import ModelBindingImport
from character_factory_poc.contracts.training import CostEstimate, ModelBinding, TrainingRun
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import BIND_EXISTING, SOURCE
from character_factory_poc.pipeline.origin import read_model_mode, read_origin

TOKEN_ENV = "HF_TOKEN"


class BindingClient(Protocol):
    def whoami(self) -> dict: ...
    def revision_info(self, ref: str, revision: str) -> tuple[str, str, set[str]]: ...
    def adapter_config(self, ref: str, revision: str) -> dict: ...


class _HubClient:
    def __init__(self, api, download):
        self.api = api
        self.download = download

    def whoami(self) -> dict:
        return self.api.whoami()

    def revision_info(self, ref, revision):
        info = self.api.model_info(ref, revision=revision)
        return info.id, info.sha, {f.rfilename for f in info.siblings}

    def adapter_config(self, ref, revision):
        path = self.download(ref, "adapter_config.json", revision=revision, token=self.api.token)
        return read_json(Path(path))


def _default_client() -> BindingClient | None:
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ModuleNotFoundError as exc:
        if exc.name == "huggingface_hub":
            return None
        raise
    token = os.environ.get(TOKEN_ENV)
    if not token:
        raise FactoryError(f"{TOKEN_ENV}가 없어 HF 토큰 신원을 확인할 수 없다")
    return _HubClient(HfApi(token=token), hf_hub_download)


def _preflight(binding: ModelBindingImport, client: BindingClient | None) -> dict:
    if binding.provider != "HF_ADAPTER":
        return {"status": "SKIPPED", "reason": "원격 모델은 연결 정보만 기록했다(확인 안 됨)."}
    client = client if client is not None else _default_client()
    if client is None:
        return {
            "status": "SKIPPED",
            "tokenEnv": TOKEN_ENV,
            "reason": "huggingface_hub 미설치로 사전 확인을 건너뜀(확인 안 됨).",
        }
    owner = binding.ref.split("/")[0]
    try:
        identity = client.whoami()
        name = identity["name"]
        owners = {name, *(org["name"] for org in identity.get("orgs", []))}
    except Exception:
        raise FactoryError(f"{TOKEN_ENV} 토큰 신원·소속 확인 실패: 인증 권한을 확인한다") from None
    if not name or owner.casefold() not in {o.casefold() for o in owners}:
        raise FactoryError("HF 저장소 소유 확인 실패: 토큰 계정 또는 소속 조직의 저장소가 아니다")
    try:
        repo, sha, files = client.revision_info(binding.ref, binding.revision)
    except Exception:
        raise FactoryError(
            "HF 저장소·커밋에 접근할 수 없다. 비공개 저장소의 404는 "
            "저장소·커밋이 없음 또는 읽기 권한 없음일 수 있다"
        ) from None
    if repo.casefold() != binding.ref.casefold() or sha.lower() != binding.revision.lower():
        raise FactoryError("HF가 돌려준 저장소 소유자·이름 또는 커밋이 연결 기록과 다르다")
    weights = files & {"adapter_model.safetensors", "adapter_model.bin"}
    if "adapter_config.json" not in files or not weights:
        raise FactoryError("HF 커밋에 adapter_config.json 또는 어댑터 가중치 파일이 없다")
    try:
        config = client.adapter_config(binding.ref, binding.revision)
        base = config.get("base_model_name_or_path")
    except Exception:
        raise FactoryError("고정한 HF 커밋의 adapter_config.json을 읽을 수 없다") from None
    if base != binding.baseModel:
        raise FactoryError("adapter_config.json의 기반 모델이 baseModel과 다르다")
    return {
        "status": "PASSED",
        "tokenEnv": TOKEN_ENV,
        "account": name,
        "owner": owner,
        "commit": sha,
        "weights": sorted(weights),
        "baseModel": base,
    }


def _no_token(obj: dict) -> None:
    token = os.environ.get(TOKEN_ENV)
    if token and token in json.dumps(obj, ensure_ascii=False):
        raise FactoryError("연결 기록에는 토큰 값을 넣을 수 없다")


def import_binding(
    ctx: Context, cid: str, binding_path: Path, *, client: BindingClient | None = None
) -> Path:
    char_dir = ctx.character_dir(cid)
    if read_origin(char_dir) != SOURCE or read_model_mode(char_dir) != BIND_EXISTING:
        raise FactoryError("이미 학습된 모델은 트윈의 BIND_EXISTING 모드에서만 연결할 수 있다")
    try:
        raw = read_json(binding_path)
    except (OSError, ValueError):
        raise FactoryError("모델 연결 JSON 파일을 읽을 수 없다") from None
    _no_token(raw)
    binding: ModelBindingImport = validate("model-binding-import-v1", raw)  # type: ignore[assignment]
    check = _preflight(binding, client)
    _no_token(check)
    root = char_dir / "model-prep"
    rev = next_rev(root, "mb")
    folder = root / rev
    ref = (folder / "binding.json").relative_to(char_dir).as_posix()
    # s11 packages all revisions under training-<provider>.json. An import gets a unique
    # provider slot; the external provider and pinned remote ref travel with that record.
    slot = f"IMPORTED-{rev}"
    run = TrainingRun(
        characterId=cid,
        datasetRev="",
        datasetDigest="",
        provider=slot,
        baseModel=binding.baseModel,
        baseModelRevision=binding.baseModelRevision,
        requestedConfig={},
        appliedConfig={"source": "IMPORTED", "binding": dump(binding), "preflight": check},
        dryRun=False,
        estimate=CostEstimate(usd=0, basis="기존 모델 연결. 학습·생성 호출 없음"),
        budgetUsd=0,
        status="SUCCEEDED",
        modelBinding=ModelBinding(provider=slot, ref=ref, checkpointId=binding.revision),
    )
    folder.mkdir(parents=True, exist_ok=False)
    write_once_json(folder / "binding.json", dump(binding))
    write_once_json(folder / "preflight.json", check)
    write_manifest(folder)
    trains = char_dir / "s10-train"
    tr = trains / next_rev(trains, "tr")
    tr.mkdir(parents=True, exist_ok=False)
    write_once_json(tr / slot / "training-run.json", dump(run))
    write_manifest(tr)
    return folder
