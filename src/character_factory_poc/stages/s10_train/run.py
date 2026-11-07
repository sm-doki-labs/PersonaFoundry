"""S10t 진입점: 기본은 plan(dry run), --execute면 제출부터 회수·선택·GPU 반납까지 몬다(D-0077)."""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s10_train.drive import drive_s10t, needs_drive
from character_factory_poc.stages.s10_train.io import (
    latest_rev,
    read_run,
    resolve_providers,
    run_path,
)
from character_factory_poc.stages.s10_train.plan import plan_s10t


def _in_flight(ctx: Context, cid: str, providers: list[str] | None) -> bool:
    """최신 revision을 이어서 몰아야 하면 새 계획(=새 GPU)을 만들지 않는다.

    제출·학습·회수·선택이 남았거나, 실행 기록이 PLANNED여도 provider 폴더의 lease.json이 지우지
    않은 GPU(인스턴스 ID나 생성 라벨)를 가리키면 이어 간다. 업로드가 실패한 뒤 다시 실행해도
    두 번째 GPU를 빌리지 않기 위해서다.
    """
    rev_dir = latest_rev(ctx, cid)
    if rev_dir is None:
        return False
    for item in resolve_providers(ctx, providers):
        path = run_path(rev_dir, item.adapter)
        if path.exists() and needs_drive(read_run(path), rev_dir / item.adapter):
            return True
    return False


def run_s10t(ctx: Context, cid: str, providers: list[str] | None = None) -> Path:
    if ctx.execute and _in_flight(ctx, cid, providers):
        return drive_s10t(ctx, cid, providers)
    rev_dir = plan_s10t(ctx, cid, providers)
    if not ctx.execute:
        return rev_dir
    return drive_s10t(ctx, cid, providers)
