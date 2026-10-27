"""S10t plan: 실제 설정으로 training-run-v2(dryRun=true, PLANNED)를 쓴다(LLD §8.9)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.contracts.training import TrainingRun
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.training import TrainRequest, make_training_provider
from character_factory_poc.stages.s10_train.io import (
    load_approved_dataset,
    resolve_providers,
    train_root,
    write_run,
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _replace_previous(state) -> None:
    """새 계획을 만들 때 이전 AWAITING_HUMAN 계획은 대체됐다고 남긴다."""
    current = state.stage("s10t").status
    if current == "AWAITING_HUMAN":
        state.transition("s10t", "REJECTED", error="새 학습 계획으로 대체")


def plan_s10t(ctx: Context, cid: str, providers: list[str] | None = None) -> Path:
    """데이터셋 파일·해시·스텝·비용을 고정한다. 원격 호출은 하지 않는다."""
    state = ctx.state(cid)
    state.require_deps("s10t")
    dataset, dataset_dir = load_approved_dataset(ctx, cid)
    resolved = resolve_providers(ctx, providers)
    rev = next_rev(train_root(ctx, cid), "tr")
    rev_dir = train_root(ctx, cid) / rev
    rev_dir.mkdir(parents=True, exist_ok=True)
    _replace_previous(state)
    state.transition("s10t", "RUNNING", rev=rev)
    summary: list[dict[str, Any]] = []
    try:
        for item in resolved:
            provider = make_training_provider(item.adapter, item.cfg)
            folder = rev_dir / provider.name
            folder.mkdir(parents=True, exist_ok=True)
            request = TrainRequest(
                dataset=dataset,
                dataset_dir=dataset_dir,
                budget_usd=item.budget_usd,
                plan_dir=folder,
                artifact_dir=folder / "artifacts",
                run_ref=rev,
            )
            run: TrainingRun = provider.plan(request)
            path = folder / "training-run.json"
            write_run(path, run)
            write_manifest(folder)
            summary.append(
                {
                    "provider": run.provider,
                    "path": path.relative_to(rev_dir).as_posix(),
                    "status": run.status,
                    "dryRun": run.dryRun,
                    "usd": run.estimate.usd,
                    "gpuHours": run.estimate.gpuHours,
                    "billableTokens": run.estimate.billableTokens,
                    "basis": run.estimate.basis,
                }
            )
        record = {
            "schemaVersion": "s10-train-plan-v1",
            "characterId": cid,
            "datasetRev": dataset.datasetRev,
            "datasetDigest": dataset.digest,
            "datasetPath": dataset_dir.relative_to(ctx.character_dir(cid)).as_posix(),
            "dryRun": True,
            "providers": summary,
            "createdAt": _now(),
        }
        write_once_json(rev_dir / "plan.json", record)
        write_manifest(rev_dir)
    except (FactoryError, ValueError, OSError) as exc:
        current = ctx.state(cid)
        if current.stage("s10t").status != "RUNNING":
            current.transition("s10t", "RUNNING", rev=rev)
        current.transition("s10t", "CHECK_FAILED", rev=rev, error=str(exc))
        if rev_dir.exists():
            write_manifest(rev_dir)
        raise
    state.transition("s10t", "AWAITING_HUMAN", rev=rev)
    return rev_dir
