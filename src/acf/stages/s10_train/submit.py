"""S10t submit: --execute와 비용 상한 안에서만 원격 학습을 시작한다(LLD §8.9)."""

from __future__ import annotations

from pathlib import Path

from acf.common.errors import NeedsInputError
from acf.common.store import write_manifest
from acf.pipeline.context import Context
from acf.providers.training import make_training_provider
from acf.providers.training.errors import TrainingError, TrainingLimitError
from acf.stages.s10_train.io import (
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


def submit_s10t(ctx: Context, cid: str, providers: list[str] | None = None) -> Path:
    if not ctx.execute:
        raise TrainingLimitError("학습 제출은 --execute가 있어야 한다(기본은 plan dry run)")
    rev_dir = latest_rev(ctx, cid)
    if rev_dir is None:
        raise NeedsInputError("s10t 계획이 없다. plan_s10t를 먼저 실행한다")
    rev = rev_dir.name
    dataset, dataset_dir = load_approved_dataset(ctx, cid)
    resolved = resolve_providers(ctx, providers)
    state = ctx.state(cid)
    try:
        for item in resolved:
            path = run_path(rev_dir, item.adapter)
            run = read_run(path)
            if run.status == "SUCCEEDED":
                continue
            if run.status in {"SUBMITTED", "RUNNING"} and run.jobId:
                continue
            if run.estimate.usd is not None and run.estimate.usd > run.budgetUsd + 1e-9:
                raise TrainingLimitError(
                    f"예상 비용 {run.estimate.usd:.4f} USD가 상한 {run.budgetUsd:.4f} USD를 넘는다"
                )
            provider = make_training_provider(item.adapter, item.cfg)
            request = build_request(rev_dir, rev, item.adapter, dataset, dataset_dir, run.budgetUsd)
            updated = provider.submit(run, request)
            write_run(path, updated)
            write_manifest(rev_dir / item.adapter)
    except TrainingError as exc:
        ensure_failed(state, rev, str(exc))
        raise
    write_manifest(rev_dir)
    runs = [read_run(run_path(rev_dir, item.adapter)) for item in resolved]
    failures = [
        f"{run.provider}: {run.status}" for run in runs if run.status in {"FAILED", "CANCELLED"}
    ]
    if failures:
        ensure_failed(state, rev, "; ".join(failures))
    elif all(run.status == "SUCCEEDED" and run.modelBinding is not None for run in runs):
        ensure_approved(state, rev)
    return rev_dir
