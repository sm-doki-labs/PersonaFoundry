"""S10t 진입점: 기본은 plan(dry run), --execute면 submit과 가능한 회수까지 한다."""

from __future__ import annotations

from pathlib import Path

from acf.pipeline.context import Context
from acf.stages.s10_train.collect import collect_s10t
from acf.stages.s10_train.io import latest_rev, read_run, resolve_providers, run_path
from acf.stages.s10_train.plan import plan_s10t
from acf.stages.s10_train.submit import submit_s10t


def run_s10t(ctx: Context, cid: str, providers: list[str] | None = None) -> Path:
    rev_dir = plan_s10t(ctx, cid, providers)
    if not ctx.execute:
        return rev_dir
    submit_s10t(ctx, cid, providers)
    latest = latest_rev(ctx, cid) or rev_dir
    resolved = resolve_providers(ctx, providers)
    runs = [read_run(run_path(latest, item.adapter)) for item in resolved]
    if all(run.status == "SUCCEEDED" for run in runs):
        collect_s10t(ctx, cid, providers)
    return latest
