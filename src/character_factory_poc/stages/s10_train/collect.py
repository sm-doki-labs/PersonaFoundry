"""S10t collect: 완료된 원격 학습 결과를 회수하고 model_binding을 남긴다(LLD §8.9)."""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.common.errors import NeedsInputError
from character_factory_poc.common.store import write_manifest
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.training import make_training_provider
from character_factory_poc.providers.training.errors import (
    TrainingIntegrityError,
    TrainingLimitError,
    TrainingNotReadyError,
)
from character_factory_poc.stages.s10_train.io import (
    build_request,
    ensure_approved,
    ensure_failed,
    latest_rev,
    load_approved_dataset,
    read_run,
    resolve_providers,
    run_path,
    write_run,
)


def collect_s10t(ctx: Context, cid: str, providers: list[str] | None = None) -> Path:
    if not ctx.execute:
        raise TrainingLimitError("학습 회수는 --execute가 있어야 한다")
    rev_dir = latest_rev(ctx, cid)
    if rev_dir is None:
        raise NeedsInputError("s10t 계획이 없다. plan_s10t를 먼저 실행한다")
    rev = rev_dir.name
    dataset, dataset_dir = load_approved_dataset(ctx, cid)
    resolved = resolve_providers(ctx, providers)
    state = ctx.state(cid)
    for item in resolved:
        path = run_path(rev_dir, item.adapter)
        run = read_run(path)
        if run.status == "SUCCEEDED" and run.modelBinding is not None:
            continue
        if not run.jobId:
            raise TrainingNotReadyError(f"{item.adapter}: 먼저 submit_s10t로 제출한다")
        if run.estimate.usd is not None and run.estimate.usd > run.budgetUsd + 1e-9:
            raise TrainingLimitError(
                f"예상 비용 {run.estimate.usd:.4f} USD가 상한 {run.budgetUsd:.4f} USD를 넘는다"
            )
        provider = make_training_provider(item.adapter, item.cfg)
        request = build_request(rev_dir, rev, item.adapter, dataset, dataset_dir, run.budgetUsd)
        try:
            updated = provider.collect(run, request)
        except TrainingIntegrityError as exc:
            ensure_failed(state, rev, str(exc))
            raise
        write_run(path, updated)
        write_manifest(rev_dir / item.adapter)
    write_manifest(rev_dir)
    runs = [read_run(run_path(rev_dir, item.adapter)) for item in resolved]
    if all(run.status == "SUCCEEDED" and run.modelBinding is not None for run in runs):
        ensure_approved(state, rev)
    return rev_dir
