"""물결 실행과 유료 단계 판정 (LLD §6.6·§6.7, 명세 §7.1, D-0049).

실행 순서와 의존은 그래프(graph.py)가 정한다. 여기서는 지금 시작할 수 있는 단계를 결정적으로
계산하고(ready_stages), 한 단계가 끝날 때마다 빈 실행 자리를 채운다(run_waves).
한 번의 실행 안에서 같은 단계는 한 번만 시도한다.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace

from character_factory_poc.common.errors import CheckFailed, GateNotApprovedError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import CREATED, Stage, stages_for
from character_factory_poc.pipeline.state import StateFile

RUNNABLE = frozenset({"PENDING", "RUNNING", "CHECK_FAILED", "REJECTED"})

# 단계가 쓰는 공급자 종류(LLD §6.7). 유료 표시(paid = true)를 볼 때만 쓴다.
STAGE_PROVIDERS: dict[str, frozenset[str]] = {
    "s1": frozenset({"text", "image"}),
    "s2": frozenset({"image", "vision"}),
    "s3": frozenset({"text"}),
    "s3r": frozenset({"text"}),
    "s5": frozenset({"video", "image"}),
    "s4a": frozenset({"text", "image"}),
    "s4b": frozenset({"text", "image"}),
    "s4": frozenset({"image"}),
    "s6": frozenset({"video", "image"}),
    "s7": frozenset({"text"}),
    "s8": frozenset({"text", "judge"}),
    "s9s": frozenset({"text"}),
    "s9": frozenset({"text"}),
    "s10t": frozenset({"tuning"}),
    "s10": frozenset({"text", "judge"}),
    "s11": frozenset(),
    "sv": frozenset(),
    "sx": frozenset(),
    "px": frozenset(),
    # 모티브 갈래(D-0128). s0은 출처 정리 에이전트가 텍스트 모델을 쓴다. s9h는 원문만 다룬다(제안).
    "s0": frozenset({"text"}),
    "s9h": frozenset(),
}


def paid_stage(ctx: Context, sid: str) -> bool:
    """그 단계가 가짜가 아닌 유료 표시 공급자를 쓰면 참이다."""
    return bool(paid_providers(ctx, sid))


def paid_providers(ctx: Context, sid: str) -> list[str]:
    """그 단계가 쓰는 유료 표시 공급자를 '종류: 어댑터/모델'로 돌려준다(실행 확인 화면용)."""
    out: list[str] = []
    for kind in sorted(STAGE_PROVIDERS.get(sid, frozenset())):
        p = ctx.config.provider(kind)
        if p.adapter != "fake" and bool(p.extra.get("paid", False)):
            out.append(f"{kind}: {p.adapter}/{p.model}" if p.model else f"{kind}: {p.adapter}")
    return out


def ready_stages(
    state: StateFile,
    runners: Mapping[str, Callable],
    attempted: set[str],
    extra_needs: Mapping[str, frozenset[str]] | None = None,
) -> list[str]:
    """지금 시작할 수 있는 단계(STAGES 순서). 순수 함수다.

    extra_needs는 그래프에 없지만 실행 함수가 직접 확인하는 선행 단계다. 외모 축 캐릭터의 s3는
    s2 승인을 실행 함수가 본다(graph.py 주석, D-0033). 순차 훑기는 STAGES 순서라 저절로 지켜진다.
    """
    extra = extra_needs or {}
    out: list[str] = []
    from character_factory_poc.pipeline.origin import graph_for_dir

    graph = graph_for_dir(state.path.parent)
    for sid, stage in graph.items():
        if sid in attempted or sid not in runners or not stage.implemented:
            continue
        if state.stage(sid).status not in RUNNABLE:
            continue
        if any(state.stage(n).status != "APPROVED" for n in extra.get(sid, ())):
            continue
        try:
            state.require_deps(sid)
        except GateNotApprovedError:
            continue
        out.append(sid)
    return out


def extra_needs_for(appearance_axis: bool) -> dict[str, frozenset[str]]:
    """외모 축이면 s3(씨앗 → 변형)는 s2 승인 뒤에 시작한다."""
    return {"s3": frozenset({"s2"})} if appearance_axis else {}


def until_scope(
    until: str,
    origin: str = CREATED,
    mode: str = "TRAIN",
    *,
    graph: Mapping[str, Stage] | None = None,
) -> list[str]:
    """--until까지의 단계(갈래 그래프 순서). 순차 훑기가 until에서 멈추는 것과 같은 범위다."""
    graph = stages_for(origin, mode) if graph is None else graph
    order = list(graph)
    if until in graph:
        return order[: order.index(until) + 1]
    for i, sid in enumerate(order):
        if graph[sid].gate == until:
            return order[: i + 1]
    return order


def _sort(ids: list[str], key_of: Callable[[str], str], origin: str = CREATED) -> list[str]:
    order = {sid: i for i, sid in enumerate(stages_for(origin))}
    seen: list[str] = []
    for x in ids:
        if x not in seen:
            seen.append(x)
    return sorted(seen, key=lambda x: order.get(key_of(x), len(order)))


def _gate_stage(gate: str, origin: str = CREATED) -> str:
    return next((sid for sid, s in stages_for(origin).items() if s.gate == gate), gate)


def _demo_stage_budget(ctx: Context, cid: str, sid: str) -> tuple[Context, float]:
    """예약과 worker의 계획 상한을 함께 정한다. 완료된 관문 처리는 예약하지 않는다."""
    from character_factory_poc.common.budget import Budget
    from character_factory_poc.pipeline.origin import stage_def

    state = ctx.state(cid)
    status = state.stage(sid).status
    if (status in {"APPROVED", "SKIPPED"} and sid != "s8c") or (
        status == "AWAITING_HUMAN" and stage_def(ctx.character_dir(cid), sid).gate
    ):
        return ctx, 0.0
    real = (
        any(p.adapter != "fake" for p in ctx.config.providers.values())
        or ctx.config.text_pipeline.get("enabled", False)
        or ctx.config.agent.get("backend") == "codex_exec"
    )
    if not real:
        return ctx, 0.0
    # 영상은 재개/부분 재생성을 포함한 실제 계획을 사용한다. 단가를 모르는 어댑터가
    # 돌려주는 0은 실제 비용 추정으로 쓰지 않고 아래의 unknown cap을 적용한다.
    if sid in {"s5", "s6"} and ctx.config.provider("video").adapter in {
        "xai_video",
        "grok_oauth",
        "grok",
    }:
        if sid == "s5":
            from character_factory_poc.stages.s5_intro.run import plan_calls, s5_config

            plans = plan_calls(ctx, s5_config(ctx))
        else:
            from character_factory_poc.stages.s6_actions.run import plan_calls, s6_config

            plans = plan_calls(ctx, s6_config(ctx, cid), cid)
        Budget(ctx.config.budget, max_calls_override=ctx.max_calls).check_plan(plans)
        if all(p.est_cost_usd is not None for p in plans):
            cost = sum(p.est_cost_usd for p in plans)
            if math.isfinite(cost) and cost >= 0:
                return ctx, cost
    cap = min(
        float(ctx.config.budget.max_cost_usd_per_command),
        float(ctx.config.orchestrator.get("parallel_stage_cost_cap_usd", 10.0)),
    )
    if not math.isfinite(cap) or cap <= 0:
        raise ValueError("시연 병렬 단계 비용 상한은 유한한 양수여야 한다")
    config = replace(ctx.config, budget=replace(ctx.config.budget, max_cost_usd_per_command=cap))
    worker = replace(ctx, config=config)
    if ctx._run_budget is not None:
        # 기존 공유 호출/토큰 예산을 버리거나 초기화하지 않고 계획 비용 검사만 더한다.
        worker._run_budget = _CappedStageBudget(ctx._run_budget, config.budget, ctx.max_calls)
    return worker, cap


class _CappedStageBudget:
    def __init__(self, shared, config, max_calls):
        from character_factory_poc.common.budget import Budget

        self.shared = shared
        self.local = Budget(config, max_calls_override=max_calls)

    def check_plan(self, plans):
        self.local.check_plan(plans)
        self.shared.check_plan(plans)

    def __getattr__(self, name):
        return getattr(self.shared, name)


def run_waves(
    ctx: Context, cid: str, opt, *, scope=None, auto_review=False, demo_budget=None
) -> object:
    """의존이 풀린 단계를 opt.max_parallel개까지 동시에 돌린다(LLD §6.6)."""
    from character_factory_poc.pipeline.orchestrator import (
        RunLog,
        _appearance_axis,
        _finish,
        _mark_failed,
        _skip_note,
        _stage_runners,
        _step,
    )
    from character_factory_poc.pipeline.origin import graph_for_dir, read_origin

    log = RunLog()
    origin = read_origin(ctx.character_dir(cid))
    graph = graph_for_dir(ctx.character_dir(cid))
    owners = {stage.gate: sid for sid, stage in graph.items() if stage.gate}
    runners = _stage_runners(ctx, cid, opt)
    # 외모 축의 s3 ← s2 선행은 오리지널에만 있다. 모티브의 s3는 G0만 기다린다(D-0128).
    extra = extra_needs_for(origin == CREATED and _appearance_axis(ctx, cid, opt))
    allowed = set(scope) if scope is not None else None
    scope: list[str] = []
    ordered = list(graph) if opt.videos_with_chat else until_scope(opt.until, graph=graph)
    for sid in ordered:
        if allowed is not None and sid not in allowed:
            continue
        note = _skip_note(ctx, cid, sid, runners)
        if note is not None:
            if note:
                log.add(note)
            continue
        scope.append(sid)
    in_scope = {sid: runners[sid] for sid in scope}
    wrap = getattr(opt, "wrap_worker", None) or (lambda fn: fn)

    def one(sid: str, worker: Context = ctx):
        sub = RunLog()
        stage_runners = runners if worker is ctx else _stage_runners(worker, cid, opt)
        from character_factory_poc.pipeline.origin import VIDEO_STAGES

        step_opt = opt
        if opt.videos_with_chat:
            step_opt = replace(
                opt,
                video_only=sid in VIDEO_STAGES,
                confirmed=opt.confirmed.intersection(VIDEO_STAGES),
            )
        action = _step(worker, cid, sid, step_opt, stage_runners, sub, auto_review=auto_review)
        return sub, action

    def merge(sub) -> None:
        log.steps.extend(sub.steps)
        log.waiting.extend(sub.waiting)
        log.blocked.extend(sub.blocked)
        log.held.extend(sub.held)
        log.timings.update(sub.timings)
        if sub.stopped_at:
            log.stopped_at = sub.stopped_at

    attempted: set[str] = set()
    stopped = False
    results = {}
    workers = max(1, int(opt.max_parallel))
    reserved: dict[str, float] = {}

    def budget_available(sid, amount=0.0, *, defer=False):
        if demo_budget is None:
            return True
        from character_factory_poc.pipeline.demo import spent_since

        limit, since = demo_budget
        spent = spent_since(ctx, cid, since)
        if spent >= limit:
            log.add(f"{sid}: 시연 예산 상한 도달 — 추정 ${spent:.2f} / ${limit:.2f}")
            log.held.append(sid)
            return False
        outstanding = sum(reserved.values())
        if spent + outstanding + amount > limit:
            if not defer:
                log.add(
                    f"{sid}: 시연 예산 상한 — 추정 ${spent:.2f} + 실행 중 예약 "
                    f"${outstanding:.2f} + 단계 예약 ${amount:.2f} > ${limit:.2f}"
                )
                log.held.append(sid)
            return False
        return True

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"cfp-{cid}") as ex:
        pending = {}
        while True:
            if not stopped:
                state = ctx.state(cid)
                active = set(pending.values())
                ready = {
                    sid
                    for sid in ready_stages(state, in_scope, attempted, extra)
                    if not active.intersection(
                        graph[sid].needs
                        | graph[sid].after
                        | extra.get(sid, frozenset())
                        | {owners[g] for g in graph[sid].deps}
                        | ({"s8c"} if auto_review and "G6" in graph[sid].deps else set())
                    )
                }
                # 이미 생성된 관문도 _step에서 처리해야 자동 승인이 후속 의존을 푼다.
                candidates = [sid for sid in scope if sid in ready]
                candidates.extend(
                    sid
                    for sid in scope
                    if sid not in attempted
                    and sid not in ready
                    and state.stage(sid).status not in RUNNABLE
                )
                batch = []
                for sid in candidates:
                    if len(pending) >= workers:
                        break
                    try:
                        worker, reservation = (
                            _demo_stage_budget(ctx, cid, sid)
                            if demo_budget is not None
                            else (ctx, 0.0)
                        )
                    except CheckFailed as exc:
                        _mark_failed(ctx, cid, sid, str(exc))
                        sub = RunLog()
                        sub.add(f"{sid}: 검사 실패 — {exc}")
                        sub.blocked.append(sid)
                        attempted.add(sid)
                        results[sid] = sub
                        if opt.until == sid and not opt.videos_with_chat:
                            sub.stopped_at = sid
                            stopped = True
                            break
                        continue
                    if not budget_available(sid, reservation, defer=bool(pending)):
                        if log.held:
                            stopped = True
                            break
                        continue  # 실행 중인 단계가 예약을 반납하면 다시 판단한다.
                    reserved[sid] = reservation
                    attempted.add(sid)
                    batch.append(sid)
                    pending[ex.submit(wrap(one), sid, worker)] = sid
                if batch:
                    log.waves.append(batch)
            if not pending:
                break
            # A reference photo can be confirmed from the UI while a long text
            # worker is still running. Notice that gate without waiting for the
            # text call to finish so the now-ready video branch can start.
            done, _ = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            for future in done:
                sid = pending.pop(future)
                # worker가 끝난 뒤에만 예약을 해제한다. 다음 admission은 spent_since를
                # 다시 읽으므로 확정 비용을 포함한다(미확인 비용의 기존 0 정책은 그대로).
                try:
                    sub, action = future.result()
                finally:
                    reserved.pop(sid, None)
                results[sid] = sub
                if action == "return" and not opt.videos_with_chat:
                    stopped = True
                # 실패/사람 대기는 해당 갈래만 막는다. 의존이 풀린 다른 갈래는 계속한다.
                # 유료 확인을 만난 자동검토의 실행 중단 규칙은 그대로 보존한다.
                if auto_review and sub.held:
                    stopped = True
    # 출력 순서는 완료 경합에 좌우되지 않게 그래프 순서로 합친다.
    for sid in scope:
        if sid in results:
            merge(results[sid])
    # 더 실행할 수 없을 때만 대기/의존 상태를 설명한다. 중단 뒤 새 단계는 실행하지 않는다.
    if not stopped:
        for sid in scope:
            if sid in attempted:
                continue
            if not budget_available(sid):
                break
            sub, action = one(sid)
            merge(sub)
            if action == "return":
                stopped = True
                break
    state = ctx.state(cid)
    log.waiting = _sort(
        [gate for gate in log.waiting if state.gate(gate).status != "APPROVED"],
        lambda g: _gate_stage(g, origin),
        origin,
    )
    log.blocked = _sort(log.blocked, lambda s: s, origin)
    log.held = _sort(log.held, lambda s: s, origin)
    if opt.videos_with_chat and not log.blocked and not log.held:
        state = ctx.state(cid)
        if state.stage("s8c").status == "APPROVED" and state.gate("G5b").status == "APPROVED":
            log.stopped_at = "G5b"
            return log
    if stopped and log.stopped_at:
        return log
    return _finish(log)
