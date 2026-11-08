"""물결 실행과 유료 단계 판정 (LLD §6.6·§6.7, 명세 §7.1, D-0049).

실행 순서와 의존은 그래프(graph.py)가 정한다. 여기서는 지금 시작할 수 있는 단계를 결정적으로
계산하고(ready_stages), 그 단계를 동시에 돌린 뒤 다시 계산하기를 더 돌 단계가 없을 때까지
반복한다(run_waves). 한 번의 실행 안에서 같은 단계는 한 번만 시도한다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor

from character_factory_poc.common.errors import GateNotApprovedError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import CREATED, stages_for
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
    "sx": frozenset(),
    # 트윈 갈래(D-0128). s0은 출처 정리 에이전트가 텍스트 모델을 쓴다. s9h는 원문만 다룬다(제안).
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


def until_scope(until: str, origin: str = CREATED, mode: str = "TRAIN") -> list[str]:
    """--until까지의 단계(갈래 그래프 순서). 순차 훑기가 until에서 멈추는 것과 같은 범위다."""
    graph = stages_for(origin, mode)
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


def run_waves(ctx: Context, cid: str, opt) -> object:
    """의존이 풀린 단계를 opt.max_parallel개까지 동시에 돌린다(LLD §6.6)."""
    from character_factory_poc.pipeline.orchestrator import (
        RunLog,
        _appearance_axis,
        _finish,
        _skip_note,
        _stage_runners,
        _step,
    )
    from character_factory_poc.pipeline.origin import read_model_mode, read_origin

    log = RunLog()
    origin = read_origin(ctx.character_dir(cid))
    mode = read_model_mode(ctx.character_dir(cid))
    runners = _stage_runners(ctx, cid, opt)
    # 외모 축의 s3 ← s2 선행은 오리지널에만 있다. 트윈의 s3는 G0만 기다린다(D-0128).
    extra = extra_needs_for(origin == CREATED and _appearance_axis(ctx, cid, opt))
    scope: list[str] = []
    for sid in until_scope(opt.until, origin, mode):
        note = _skip_note(ctx, cid, sid, runners)
        if note is not None:
            if note:
                log.add(note)
            continue
        scope.append(sid)
    in_scope = {sid: runners[sid] for sid in scope}
    wrap = getattr(opt, "wrap_worker", None) or (lambda fn: fn)

    def one(sid: str):
        sub = RunLog()
        action = _step(ctx, cid, sid, opt, runners, sub)
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
    while not stopped:
        wave = ready_stages(ctx.state(cid), in_scope, attempted, extra)
        if not wave:
            break
        log.waves.append(list(wave))
        attempted.update(wave)
        workers = max(1, min(int(opt.max_parallel), len(wave)))
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"cfp-{cid}") as ex:
            futures = {sid: ex.submit(wrap(one), sid) for sid in wave}
            results = {sid: futures[sid].result() for sid in wave}
        for sid in wave:
            sub, action = results[sid]
            merge(sub)
            if action == "return":
                stopped = True
    # 이번 실행에서 돌지 않은 단계: 대기 관문·이미 끝남·시작 불가를 순차 훑기 문장으로 남긴다.
    for sid in scope:
        if sid in attempted:
            continue
        sub, action = one(sid)
        merge(sub)
        if action == "return":
            stopped = True
            break
    log.waiting = _sort(log.waiting, lambda g: _gate_stage(g, origin), origin)
    log.blocked = _sort(log.blocked, lambda s: s, origin)
    log.held = _sort(log.held, lambda s: s, origin)
    if stopped:
        return log
    return _finish(log)
