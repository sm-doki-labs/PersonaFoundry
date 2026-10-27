"""S10t 학습 실행 기록 읽기·쓰기와 공급자 설정 해석 (LLD §5.15·§8.9)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from acf.common.config import ProviderConfig
from acf.common.errors import CheckFailed, GateNotApprovedError, NeedsInputError
from acf.common.schema import dump
from acf.common.store import read_json
from acf.contracts.dataset import DatasetRev
from acf.contracts.training import TrainingRun
from acf.pipeline.context import Context
from acf.providers.training.port import ALL_PROVIDERS, TrainRequest

_REV_RE = re.compile(r"^tr(\d+)$")


@dataclass(frozen=True)
class ResolvedProvider:
    adapter: str
    cfg: ProviderConfig
    budget_usd: float


def train_root(ctx: Context, cid: str) -> Path:
    return ctx.character_dir(cid) / "s10-train"


def latest_rev(ctx: Context, cid: str) -> Path | None:
    root = train_root(ctx, cid)
    if not root.is_dir():
        return None
    found: list[tuple[int, Path]] = []
    for path in root.iterdir():
        match = _REV_RE.match(path.name)
        if path.is_dir() and match:
            found.append((int(match.group(1)), path))
    return max(found)[1] if found else None


def run_path(rev_dir: Path, provider: str) -> Path:
    return rev_dir / provider / "training-run.json"


def read_run(path: Path) -> TrainingRun:
    if not path.is_file():
        raise NeedsInputError(f"학습 실행 기록이 없다: {path}")
    return TrainingRun.model_validate(read_json(path))


def write_run(path: Path, run: TrainingRun) -> None:
    """training-run.json만 상태를 바꾼다. versioned 자산은 건드리지 않는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(dump(run), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


def _config_for(ctx: Context, adapter: str) -> ProviderConfig:
    base = ctx.config.providers.get(f"training_{adapter}") or ctx.config.providers.get(adapter)
    if base is None:
        base = ProviderConfig(adapter=adapter)
    stage = ctx.config.stage("s10t").get(adapter)
    extra = dict(base.extra)
    model = base.model
    base_url = base.base_url
    api_key_env = base.api_key_env
    if isinstance(stage, dict):
        extra.update({k: v for k, v in stage.items() if k != "budget_usd"})
        model = str(stage.get("model", model))
        base_url = str(stage.get("base_url", base_url))
        api_key_env = str(stage.get("api_key_env", api_key_env))
    explicit = base.adapter if base.adapter not in {"", "fake"} else adapter
    return ProviderConfig(
        adapter=explicit,
        base_url=base_url,
        model=model,
        api_key_env=api_key_env,
        extra=extra,
    )


def resolve_providers(ctx: Context, requested: list[str] | None) -> list[ResolvedProvider]:
    stage = ctx.config.stage("s10t")
    keys = requested
    if keys is None:
        configured = stage.get("providers")
        if configured is None:
            keys = ["gemma_qlora", "vertex_gemini"]
        elif isinstance(configured, list) and all(isinstance(v, str) for v in configured):
            keys = list(configured)
        else:
            raise CheckFailed("s10t", ["[stages.s10t] providers는 문자열 목록이어야 한다"])
    if not keys:
        raise CheckFailed("s10t", ["학습 공급자를 하나 이상 골라야 한다"])
    default_budget = float(stage.get("budget_usd", ctx.config.budget.max_cost_usd_per_command))
    out: list[ResolvedProvider] = []
    seen: set[str] = set()
    for key in keys:
        if not isinstance(key, str) or not key:
            raise CheckFailed("s10t", ["공급자 이름은 비어 있지 않은 문자열이어야 한다"])
        if key in ALL_PROVIDERS:
            adapter = key
            cfg = _config_for(ctx, adapter)
        else:
            cfg = ctx.config.providers.get(key)
            if cfg is None:
                raise CheckFailed("s10t", [f"학습 공급자 설정이 없다: {key}"])
            adapter = cfg.adapter or key
        if adapter not in ALL_PROVIDERS:
            raise CheckFailed(
                "s10t", [f"알 수 없는 학습 공급자: {adapter}(gemma_qlora·vertex_gemini·fake)"]
            )
        if adapter in seen:
            continue
        seen.add(adapter)
        per = stage.get(adapter)
        budget = default_budget
        if isinstance(per, dict) and "budget_usd" in per:
            budget = float(per["budget_usd"])
        if budget < 0:
            raise CheckFailed("s10t", ["budget_usd는 0 이상이어야 한다"])
        out.append(ResolvedProvider(adapter=adapter, cfg=cfg, budget_usd=budget))
    return out


def load_approved_dataset(ctx: Context, cid: str) -> tuple[DatasetRev, Path]:
    state = ctx.state(cid)
    gate = state.gate("G7")
    if gate.status != "APPROVED":
        raise GateNotApprovedError(f"s10t는 G7 승인이 필요하다(현재 {gate.status})")
    root = ctx.character_dir(cid) / "s9-data"
    if not root.is_dir():
        raise NeedsInputError("S9 데이터셋 폴더가 없다. G7에서 고정한 dataset-rev-v2가 필요하다")
    candidates: list[tuple[int, Path]] = []
    for path in root.iterdir():
        match = re.match(r"^ds(\d+)$", path.name)
        if path.is_dir() and match:
            candidates.append((int(match.group(1)), path))
    if not candidates:
        raise NeedsInputError("dataset-rev-v2 폴더(s9-data/ds<k>)가 없다")
    chosen: Path | None = None
    if gate.rev:
        for _number, path in candidates:
            if path.name == gate.rev:
                chosen = path
                break
    if chosen is None:
        chosen = max(candidates)[1]
    dataset_file = chosen / "dataset.json"
    if not dataset_file.is_file():
        raise NeedsInputError(f"dataset.json이 없다: {dataset_file}")
    dataset = DatasetRev.model_validate(read_json(dataset_file))
    if dataset.characterId != cid:
        raise CheckFailed("s10t", ["dataset-rev-v2의 characterId가 캐릭터와 다르다"])
    if dataset.datasetRev != chosen.name:
        raise CheckFailed(
            "s10t", [f"datasetRev {dataset.datasetRev}와 폴더 {chosen.name}가 다르다"]
        )
    if dataset.blockingFailures:
        raise CheckFailed("s10t", ["차단 실패가 있는 데이터셋은 학습에 쓸 수 없다"])
    return dataset, chosen


def build_request(
    rev_dir: Path, rev: str, provider: str, dataset: DatasetRev, dataset_dir: Path, budget: float
) -> TrainRequest:
    folder = rev_dir / provider
    return TrainRequest(
        dataset=dataset,
        dataset_dir=dataset_dir,
        budget_usd=budget,
        plan_dir=folder,
        artifact_dir=folder / "artifacts",
        run_ref=rev,
    )


def ensure_approved(state, rev: str) -> None:
    """모든 공급자의 model_binding이 생기면 s10t를 APPROVED로 둔다(관문 없음)."""
    status = state.stage("s10t").status
    if status == "APPROVED":
        return
    if status != "AWAITING_HUMAN":
        state.transition("s10t", "RUNNING", rev=rev)
    state.transition("s10t", "APPROVED", rev=rev)


def ensure_failed(state, rev: str, error: str) -> None:
    status = state.stage("s10t").status
    if status == "RUNNING":
        state.transition("s10t", "CHECK_FAILED", rev=rev, error=error)
    elif status == "AWAITING_HUMAN":
        state.transition("s10t", "REJECTED", rev=rev, error=error)
    elif status == "APPROVED":
        state.transition("s10t", "RUNNING", rev=rev)
        state.transition("s10t", "CHECK_FAILED", rev=rev, error=error)
