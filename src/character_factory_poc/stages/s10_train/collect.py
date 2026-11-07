"""S10t collect: 완료된 원격 학습 결과를 회수하고 model_binding을 남긴다(LLD §8.9).

gemma_qlora는 회수 뒤 체크포인트별 첫 답변(선별)으로 체크포인트를 고른다(D-0077). 선택 결과가
model_binding을 정한다. 쓸 체크포인트가 없다고 판단되면(BLOCKED_*) binding을 남기지 않아 평가가
학습 결과 없이 진행할지 사람이 정하게 둔다.
"""

from __future__ import annotations

from pathlib import Path

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.errors import NeedsInputError
from character_factory_poc.common.store import write_manifest
from character_factory_poc.contracts.training import ModelBinding, TrainingRun
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.training import make_training_provider
from character_factory_poc.providers.training.errors import (
    TrainingIntegrityError,
    TrainingLimitError,
    TrainingNotReadyError,
)
from character_factory_poc.providers.training.port import TrainRequest
from character_factory_poc.providers.training.screening import read_tasks
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

PENDING = "PENDING"
BINDING_DECISIONS = frozenset({"DEVELOPMENT_RECOMMENDED", "INCONCLUSIVE"})


def select_for_run(ctx: Context, cid: str, run: TrainingRun, request: TrainRequest) -> TrainingRun:
    """선별 응답으로 체크포인트를 고르고 binding과 선택 요약을 run에 반영한다."""
    from character_factory_poc.stages.s10_train.select import select_checkpoint

    tasks_path = request.plan_dir / "screen-requests.jsonl"
    tasks = read_tasks(tasks_path) if tasks_path.exists() else []
    persona = ""
    for task in tasks:
        system = [m for m in task.get("messages") or [] if m.get("role") == "system"]
        if system:
            persona = str(system[0].get("content") or "")
            break
    judge = None
    stage = ctx.config.stage("s10t")
    judge_items = int(stage.get("selection_judge_items", 8))
    if tasks and stage.get("selection_judge", True) and judge_items > 0:
        arms = len(run.checkpoints) + 1
        calls = judge_items * 2 * arms * (arms - 1) // 2
        budget = ctx.budget()
        budget.check_plan([CallPlan("s10t", f"체크포인트 짝 판정 최대 {calls}회", calls)])
        judge = ctx.judge_model(cid, budget)
    result = select_checkpoint(
        run=run,
        artifact_dir=request.artifact_dir,
        tasks=tasks,
        persona_text=persona,
        judge=judge,
        out_path=request.plan_dir / "checkpoint-selection.json",
        judge_items=judge_items,
        # 체크포인트 ref는 artifact_dir 기준 상대 경로라 접두어를 붙이지 않는다.
        ref_prefix="",
    )
    applied = {
        **run.appliedConfig,
        "selection": {
            "decision": result.decision,
            "checkpointId": result.checkpoint_id,
            "record": result.record_path.name,
        },
    }
    # binding은 선택이 체크포인트를 고른 경우에만 남긴다. 같은 짧은 프롬프트의 기반 모델이
    # 이겼거나(KEEP_INCUMBENT) 쓸 체크포인트가 없으면(BLOCKED_*) 어댑터를 채택하지 않는다.
    binding = None
    if result.checkpoint_ref and result.checkpoint_id and result.decision in BINDING_DECISIONS:
        binding = ModelBinding(
            provider=run.provider,
            ref=str((request.artifact_dir / result.checkpoint_ref).resolve()),
            checkpointId=result.checkpoint_id,
        )
    return run.model_copy(update={"modelBinding": binding, "appliedConfig": applied})


def selection_decision(run: TrainingRun) -> str | None:
    """run에 기록된 체크포인트 선택 결정. 선택 단계가 없는 공급자면 None."""
    selection = run.appliedConfig.get("selection")
    return str(selection.get("decision")) if isinstance(selection, dict) else None


def collection_done(run: TrainingRun) -> bool:
    """회수·선택까지 끝났는지. KEEP_INCUMBENT·BLOCKED는 binding 없이 끝난 상태다."""
    if run.status != "SUCCEEDED":
        return False
    decision = selection_decision(run)
    if decision is None:
        return run.modelBinding is not None
    return decision != PENDING


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
        if collection_done(run):
            continue
        if run.status == "SUCCEEDED" and selection_decision(run) == PENDING:
            # 회수는 끝났고(원격·GPU 삭제됨) 선택만 실패했다. 로컬 파일로 선택만 다시 한다.
            request = build_request(rev_dir, rev, item.adapter, dataset, dataset_dir, run.budgetUsd)
            write_run(path, select_for_run(ctx, cid, run, request))
            write_manifest(rev_dir / item.adapter)
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
        if (
            updated.provider == "gemma_qlora"
            and (request.plan_dir / "screen-requests.jsonl").exists()
        ):
            # 선택 전에는 binding을 비워 둔다. 선택이 실패해도 마지막 체크포인트가
            # 조용히 채택되지 않고, 다시 돌리면 선택만 다시 한다.
            pending = updated.model_copy(
                update={
                    "modelBinding": None,
                    "appliedConfig": {**updated.appliedConfig, "selection": {"decision": PENDING}},
                }
            )
            write_run(path, pending)
            updated = select_for_run(ctx, cid, pending, request)
        write_run(path, updated)
        write_manifest(rev_dir / item.adapter)
    write_manifest(rev_dir)
    runs = [read_run(run_path(rev_dir, item.adapter)) for item in resolved]
    if all(run.status == "SUCCEEDED" and run.modelBinding is not None for run in runs):
        ensure_approved(state, rev)
    return rev_dir
