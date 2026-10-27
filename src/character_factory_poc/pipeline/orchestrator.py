"""cfp run <id> --until <stage|gate> (LLD §6). 그래프를 따라 관문까지 자동 진행한다.

D-0035: 한 갈래가 사람 검토(관문)나 사람 입력(기획 씨앗)을 기다려도 멈추지 않고,
의존이 풀린 다른 갈래를 계속 진행한다. 예를 들어 S2가 자동으로 외모를 고정한 뒤(D-0042)
씨앗이 아직 없으면 S3는 기다리고 S5 소개 영상이 먼저 돈다.
더 진행할 단계가 없으면 멈추고, 기다리는 관문·입력을 모아 보고한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from character_factory_poc.common.errors import (
    CheckFailed,
    FactoryError,
    GateNotApprovedError,
    NeedsInputError,
)
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import GATES, RETIRED_GATES, STAGES

# 외모 축(S1·S2)을 탄 캐릭터만 도는 단계
APPEARANCE_STAGES = ("s2", "s4a", "s4b", "s4", "s5", "s6")


@dataclass
class RunOptions:
    until: str = "G6"
    auto_approve: set[str] = field(default_factory=set)
    brief_text: str | None = None
    voice_probes: list[str] = field(default_factory=list)
    allow_same_family: bool = False
    ranking: Any = (
        None  # popularity-ranking-v2 객체. 없으면 s1을 건너뛴다(D-0013 페르소나 우선 경로).
    )
    seed: dict[str, Any] | None = None  # 기획 씨앗(D-0033). 저장된 씨앗이 없을 때만 쓴다.


@dataclass
class RunLog:
    steps: list[str] = field(default_factory=list)
    stopped_at: str = ""
    waiting: list[str] = field(default_factory=list)  # 사람 검토를 기다리는 관문
    blocked: list[str] = field(default_factory=list)  # 의존·입력이 없어 시작하지 못한 단계

    def add(self, s: str) -> None:
        self.steps.append(s)
        print(s)


def _appearance_axis(ctx: Context, cid: str, opt: RunOptions) -> bool:
    return opt.ranking is not None or ctx.state(cid).gate("G1").status != "PENDING"


def validate_until(until: str) -> None:
    """--until 값이 단계 또는 현행 관문인지 본다. G2는 결번이다(D-0042)."""
    if until in RETIRED_GATES:
        raise FactoryError(RETIRED_GATES[until] + ". --until로 받지 않는다")
    if until not in STAGES and until not in GATES:
        raise FactoryError(
            f"--until {until}: 없는 단계·관문이다({', '.join(STAGES)} / {', '.join(GATES)})"
        )


def validate_auto_approve(names: set[str]) -> None:
    """--auto-approve 값이 현행 관문인지 본다. G2는 결번이다(D-0042)."""
    for g in sorted(names):
        if g in RETIRED_GATES:
            raise FactoryError(RETIRED_GATES[g] + ". --auto-approve로 받지 않는다")
        if g not in GATES:
            raise FactoryError(f"--auto-approve {g}: 없는 관문이다({', '.join(GATES)})")


def _stage_runners(ctx: Context, cid: str, opt: RunOptions) -> dict[str, Callable[[], Path | None]]:
    from character_factory_poc.stages.s1_reference.run import run_s1
    from character_factory_poc.stages.s2_hero.run import run_s2
    from character_factory_poc.stages.s3_plan.draft import run_s3_draft
    from character_factory_poc.stages.s3r_refs.select import run_s3r
    from character_factory_poc.stages.s4_frames.run import run_s4
    from character_factory_poc.stages.s4a_backgrounds.run import run_s4a
    from character_factory_poc.stages.s4b_poses.run import run_s4b
    from character_factory_poc.stages.s5_intro.run import run_s5
    from character_factory_poc.stages.s6_actions.run import run_s6
    from character_factory_poc.stages.s7_traits.sheet import run_s7
    from character_factory_poc.stages.s8_prompts.build import run_s8

    appearance = _appearance_axis(ctx, cid, opt)

    def s3():
        if appearance:
            # D-0033: 외모 축 캐릭터는 s2 승인 뒤 씨앗 → 변형. 브리프 초안은 쓰지 않는다.
            from character_factory_poc.stages.s3_plan.seed import load_latest_seed, write_seed
            from character_factory_poc.stages.s3_plan.variants import run_s3_variants

            if opt.seed and load_latest_seed(ctx, cid) is None:
                write_seed(ctx, cid, opt.seed)
            return run_s3_variants(ctx, cid)
        if not opt.brief_text:
            raise NeedsInputError("S3를 돌리려면 --brief가 필요하다(또는 cfp plan import)")
        return run_s3_draft(ctx, cid, opt.brief_text)

    runners: dict[str, Callable[[], Path | None]] = {
        "s3": s3,
        "s3r": lambda: run_s3r(ctx, cid),
        "s7": lambda: run_s7(ctx, cid),
        "s8": lambda: run_s8(ctx, cid, opt.voice_probes, opt.allow_same_family),
    }
    if opt.ranking is not None:
        runners["s1"] = lambda: run_s1(ctx, cid, opt.ranking)
    if appearance:
        runners["s2"] = lambda: run_s2(ctx, cid)
        runners["s5"] = lambda: run_s5(ctx, cid)
        runners["s4a"] = lambda: run_s4a(ctx, cid)
        runners["s4b"] = lambda: run_s4b(ctx, cid)
        runners["s4"] = lambda: run_s4(ctx, cid)
        runners["s6"] = lambda: run_s6(ctx, cid)
    return runners


def _auto_approve(ctx: Context, cid: str, gate: str) -> None:
    approve_gate(
        ctx,
        cid,
        gate,
        {
            "decision": "APPROVE",
            "reviewer": "auto:--auto-approve",
            "reasons": "실험용 자동 승인 플래그. 사람 검토가 아니다.",
        },
    )


def run_until(ctx: Context, cid: str, opt: RunOptions) -> RunLog:
    validate_until(opt.until)
    validate_auto_approve(opt.auto_approve)
    log = RunLog()
    runners = _stage_runners(ctx, cid, opt)
    for sid, stage in STAGES.items():
        if not stage.implemented or sid not in runners:
            if ctx.state(cid).stage(sid).status == "PENDING":
                if sid == "s1":
                    log.add("s1: --ranking 없음 — 건너뜀(페르소나 우선 경로)")
                elif sid in APPEARANCE_STAGES:
                    log.add(f"{sid}: 외모 축(S1·S2) 없음 — 건너뜀")
            continue
        state = ctx.state(cid)
        st = state.stage(sid)
        gate_ok = stage.gate is None or state.gate(stage.gate).status == "APPROVED"
        if st.status in {"APPROVED", "SKIPPED"} or (st.status == "AWAITING_HUMAN" and gate_ok):
            log.add(f"{sid}: 이미 {st.status}({st.currentRev}) — 건너뜀")
        elif st.status == "AWAITING_HUMAN" and stage.gate:
            log.add(f"{sid}: {stage.gate} 대기 중({st.currentRev})")
        else:
            try:
                state.require_deps(sid)
            except GateNotApprovedError as e:
                log.add(f"{sid}: 시작 불가 — {e}")
                log.blocked.append(sid)
                if opt.until == sid:
                    break
                continue
            log.add(f"{sid}: 실행")
            try:
                out = runners[sid]()
            except NeedsInputError as e:
                log.add(f"{sid}: 사람 입력 대기 — {e}")
                log.blocked.append(sid)
                continue
            except GateNotApprovedError as e:
                log.add(f"{sid}: 시작 불가 — {e}")
                log.blocked.append(sid)
                continue
            except CheckFailed as e:
                # 검사 실패는 그 단계만 멈춘다. 다른 갈래는 계속 돈다(D-0035).
                log.add(f"{sid}: 검사 실패 — {e}")
                log.blocked.append(sid)
                if opt.until == sid:
                    log.stopped_at = sid
                    return log
                continue
            if out is None:
                log.add(f"{sid}: 건너뜀({ctx.state(cid).stage(sid).status})")
            else:
                log.add(f"{sid}: 완료 → {out}")
        # 관문 처리: 자동 승인 플래그가 없으면 기다리는 관문으로 모으고 다른 갈래를 계속 진행한다
        state = ctx.state(cid)
        if stage.gate and state.gate(stage.gate).status == "AWAITING_HUMAN":
            if stage.gate in opt.auto_approve:
                _auto_approve(ctx, cid, stage.gate)
                log.add(f"{stage.gate}: 자동 승인(--auto-approve)")
            else:
                log.add(f"{stage.gate}: 사람 검토 대기")
                if stage.gate not in log.waiting:
                    log.waiting.append(stage.gate)
        if opt.until in (sid, stage.gate):
            log.add(f"{opt.until}에 도달해 멈춘다")
            log.stopped_at = opt.until
            return log
    log.stopped_at = (log.waiting or log.blocked or ["end"])[0]
    if log.waiting or log.blocked:
        log.add(
            "더 진행할 단계가 없다. 기다리는 관문: "
            + (", ".join(log.waiting) or "없음")
            + " / 시작하지 못한 단계: "
            + (", ".join(log.blocked) or "없음")
        )
    return log
