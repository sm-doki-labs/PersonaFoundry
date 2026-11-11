"""cfp run <id> --until <stage|gate> (LLD §6). 그래프를 따라 관문까지 자동 진행한다.

D-0035: 한 갈래가 사람 검토(관문)나 사람 입력(기획 씨앗)을 기다려도 멈추지 않고,
의존이 풀린 다른 갈래를 계속 진행한다. 예를 들어 S2가 자동으로 외모를 고정한 뒤(D-0042)
씨앗이 아직 없으면 S3는 기다리고 S5 소개 영상이 먼저 돈다.
더 진행할 단계가 없으면 멈추고, 기다리는 관문·입력을 모아 보고한다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.common.errors import (
    AgentFormatError,
    CheckFailed,
    FactoryError,
    GateNotApprovedError,
    NeedsInputError,
    StateTransitionError,
)
from character_factory_poc.pipeline.approve import approve_gate, approve_text_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import (
    ALL_GATES,
    ALL_STAGE_IDS,
    GATES,
    RETIRED_GATES,
    SOURCE,
    STAGES,
)

# 외모 축(S1·S2)을 탄 캐릭터만 도는 단계
APPEARANCE_STAGES = ("s2", "s4a", "s4b", "s4", "s5", "s6", "s11", "sx")
# 사람 판정 자체가 관문의 내용이라 자동 승인하지 않는다(G7a 클러스터별 판정, G8 블라인드 20쌍)
HUMAN_ONLY_GATES = {
    "G7a": "클러스터마다 샘플을 판정해야 한다",
    "G8": "블라인드 20쌍을 사람이 골라야 한다",
    # 모티브 갈래(D-0120, D-0128): 출처·사용 근거와 본인 닮음은 사람이 확인한다.
    "G0": "출처 묶음과 사용 근거를 사람이 확인해야 한다",
    "G1s": "받은 사진이 본인과 닮았는지 사람이 확인해야 한다",
}


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
    training_providers: list[str] | None = None  # s10t 학습 공급자. 없으면 [stages.s10t]
    submit_training: bool = False  # 학습 제출·회수까지 한다(유료). 기본은 계획(dry run)만
    verify_export: bool = False  # sx에서 일회용 DB 적재 확인까지 한다(LLD §8.11)
    # 모티브 s0 출처 묶음(source-pack-v1, D-0120). 없으면 지난 판을 쓴다
    source_pack: Path | None = None
    # D-0049(LLD §6.6·§6.7)
    video_only: bool = False  # 영상 요청은 지정한 다섯 단계만 돈다.
    max_parallel: int = 1  # 동시에 돌릴 단계 수. 1이면 순차 훑기
    web: bool = False  # 워크숍이 시작한 실행. 유료 공급자 단계는 확인을 받는다
    confirmed: set[str] = field(default_factory=set)  # 사람이 실행을 확인·허락한 단계
    # 물결 실행의 작업 스레드를 감싸는 함수(워크숍이 작업 로그를 스레드별로 모을 때 쓴다)
    wrap_worker: Callable[[Callable], Callable] | None = None


@dataclass
class RunLog:
    steps: list[str] = field(default_factory=list)
    stopped_at: str = ""
    waiting: list[str] = field(default_factory=list)  # 사람 검토를 기다리는 관문
    blocked: list[str] = field(default_factory=list)  # 의존·입력이 없어 시작하지 못한 단계
    held: list[str] = field(default_factory=list)  # 유료 공급자 단계: 실행 확인 대기(D-0049)
    waves: list[list[str]] = field(default_factory=list)  # 물결마다 동시에 시작한 단계
    timings: dict[str, dict[str, str]] = field(default_factory=dict)  # 단계별 start·end(UTC)

    def add(self, s: str) -> None:
        self.steps.append(s)
        print(s)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _appearance_axis(ctx: Context, cid: str, opt: RunOptions) -> bool:
    return opt.ranking is not None or ctx.state(cid).gate("G1").status != "PENDING"


def validate_until(until: str) -> None:
    """--until 값이 단계 또는 현행 관문인지 본다. G2는 결번이다(D-0042)."""
    if until in RETIRED_GATES:
        raise FactoryError(RETIRED_GATES[until] + ". --until로 받지 않는다")
    if until not in ALL_STAGE_IDS and until not in ALL_GATES:
        raise FactoryError(
            f"--until {until}: 없는 단계·관문이다({', '.join(STAGES)} / {', '.join(GATES)})"
        )


def validate_auto_approve(names: set[str]) -> None:
    """--auto-approve 값이 현행 관문인지 본다. G2는 결번이다(D-0042)."""
    for g in sorted(names):
        if g in RETIRED_GATES:
            raise FactoryError(RETIRED_GATES[g] + ". --auto-approve로 받지 않는다")
        if g in HUMAN_ONLY_GATES:
            raise FactoryError(f"--auto-approve {g}: {HUMAN_ONLY_GATES[g]}")
        if g not in GATES:
            raise FactoryError(f"--auto-approve {g}: 없는 관문이다({', '.join(GATES)})")


def _training_ready(ctx: Context, cid: str) -> bool:
    """최신 학습 revision에 성공한 model_binding이 하나라도 있는지 본다.

    s10t는 dry run(계획)만으로도 AWAITING_HUMAN이 되어 그래프상 s10의 after를 채운다.
    학습 결과 없이 평가를 시작하지 않도록 평가 진입점에서 따로 확인한다.
    """
    import json

    from character_factory_poc.stages.s10_train.io import latest_rev

    rev_dir = latest_rev(ctx, cid)
    if rev_dir is None:
        return False
    for path in sorted(rev_dir.glob("*/training-run.json")):
        run = json.loads(path.read_text("utf-8"))
        if run.get("status") == "SUCCEEDED" and run.get("modelBinding"):
            return True
    return False


def _training_undecided(ctx: Context, cid: str) -> bool:
    """학습 계획이 있고 '학습 없이 진행'을 고르지 않았다(학습 결과도 아직 없다)."""
    from character_factory_poc.stages.s10_train.io import latest_rev, skip_chosen

    rev_dir = latest_rev(ctx, cid)
    return rev_dir is not None and not skip_chosen(rev_dir)


def gpu_eval_held(ctx: Context, cid: str, sid: str) -> bool:
    """평가가 학습 어댑터로 GPU를 빌려야 하면 웹은 실행 확인을 받는다(D-0130)."""
    if sid != "s10":
        return False
    from character_factory_poc.stages.s10_eval.run import needs_gpu_eval

    return needs_gpu_eval(ctx, cid)


def _last_gate_decision(ctx: Context, cid: str, gate: str) -> str | None:
    """관문 상태가 가리키는 마지막 결정 기록의 decision. 없으면 None."""
    from character_factory_poc.common.store import read_json

    g = ctx.state(cid).gate(gate)
    if not g.recordRef:
        return None
    path = ctx.character_dir(cid) / g.recordRef
    if not path.exists():
        return None
    try:
        return read_json(path).get("decision")
    except (OSError, ValueError):
        return None


def _stage_runners(ctx: Context, cid: str, opt: RunOptions) -> dict[str, Callable[[], Path | None]]:
    from character_factory_poc.stages.s1_reference.run import run_s1
    from character_factory_poc.stages.s2_hero.run import run_s2
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
        # D-0033: 외모 축 캐릭터는 s2 승인 뒤 씨앗 → 변형. D-0080: 페르소나 우선 브리프도
        # 구형 초안(character-plan-v1) 대신 브리프를 씨앗으로 옮겨 같은 변형 경로를 쓴다.
        from character_factory_poc.stages.s3_plan.seed import load_latest_seed, write_seed
        from character_factory_poc.stages.s3_plan.variants import (
            run_s3_from_brief,
            run_s3_variants,
        )

        if load_latest_seed(ctx, cid) is None:
            if opt.seed:
                write_seed(ctx, cid, opt.seed)
            elif opt.brief_text and not appearance:
                return run_s3_from_brief(ctx, cid, opt.brief_text)
            elif not appearance:
                raise NeedsInputError(
                    "S3를 돌리려면 --brief 또는 --seed가 필요하다(또는 cfp plan import)"
                )
        # 씨앗은 다른 단계가 돌기 전에 먼저 고정한다. 외모 축은 그 뒤 s2 승인을 기다린다.
        if appearance and ctx.state(cid).stage("s2").status != "APPROVED":
            raise GateNotApprovedError(f"{cid}: 외모 축 캐릭터는 s2 승인 뒤 기획한다(D-0042)")
        return run_s3_variants(ctx, cid)

    def s10t():
        from character_factory_poc.stages.s10_train.plan import plan_s10t
        from character_factory_poc.stages.s10_train.run import run_s10t

        # 학습 제출은 유료라 --submit-training을 따로 줄 때만 한다(D-0048).
        if opt.submit_training:
            return run_s10t(ctx, cid, opt.training_providers)
        return plan_s10t(ctx, cid, opt.training_providers)

    def s10():
        from character_factory_poc.stages.s10_eval import prereg, prompt_only, report
        from character_factory_poc.stages.s10_eval import run as eval_run

        st = ctx.state(cid).stage("s10")
        last = ctx.character_dir(cid) / "s10-eval" / (st.currentRev or "-")
        if not _training_ready(ctx, cid):
            waiting = st.status == "REJECTED" and prompt_only.is_prompt_only(last)
            if opt.web and not waiting and _training_undecided(ctx, cid):
                # D-0130: 웹은 학습 계획을 세운 뒤 사람이 '학습 시작'이나 '학습 없이 진행'을
                # 고를 때까지 평가를 열지 않는다. 학습 화면이 비용 확인을 먼저 보인다.
                raise NeedsInputError("학습 비용 확인 대기(학습 시작 또는 학습 없이 진행)")
            mode = str(ctx.config.stage("s10").get("untrained", "ask"))
            if mode == "wait" or waiting:
                raise NeedsInputError(
                    "학습 결과(model_binding)가 없다. 학습은 계획(dry run)까지만 돌았다. "
                    "cfp train submit/collect --execute 뒤 다시 돌린다"
                )
            # K-0038: 학습 없이 긴 프롬프트로 갈지 사람이 G8에서 정한다.
            return prompt_only.open_prompt_only(ctx, cid)
        # 학습 대기를 골랐다가(REJECTED) 학습 결과가 생기면 새 ev revision으로 평가한다.
        if (
            st.status not in {"RUNNING", "CHECK_FAILED"}
            or not st.currentRev
            or prompt_only.is_prompt_only(last)
        ):
            prereg.build_prereg(ctx, cid)
        eval_run.run_eval(ctx, cid)
        return report.judge_and_report(ctx, cid)

    def sx():
        from character_factory_poc.stages.export.export import export_doki_app

        _, rev_dir = export_doki_app(ctx, cid, verify=opt.verify_export)
        return rev_dir

    from character_factory_poc.stages.s9_data.build import run_build
    from character_factory_poc.stages.s9_data.samples import run_samples
    from character_factory_poc.stages.s11_release.package import build_package

    runners: dict[str, Callable[[], Path | None]] = {
        "s3": s3,
        "s3r": lambda: run_s3r(ctx, cid),
        "s7": lambda: run_s7(ctx, cid),
        "s8": lambda: run_s8(ctx, cid, opt.voice_probes, opt.allow_same_family),
        "s9s": lambda: run_samples(ctx, cid),
        "s9": lambda: run_build(ctx, cid),
        "s10t": s10t,
        "s10": s10,
    }
    if opt.ranking is not None:
        runners["s1"] = lambda: run_s1(ctx, cid, opt.ranking)
    elif _last_gate_decision(ctx, cid, "G1") == "REQUEST_CHANGES":
        # D-0049(LLD §6.9): G1 수정 요청 뒤에는 같은 순위·특징으로 얼굴 미리보기만 다시 만든다
        # (cfp ref faces 경로). --ranking이 없어도 s1을 돈다.
        from character_factory_poc.stages.s1_reference.faces import run_faces

        runners["s1"] = lambda: run_faces(ctx, cid)
    if appearance:
        runners["s2"] = lambda: run_s2(ctx, cid)
        runners["s5"] = lambda: run_s5(ctx, cid)
        runners["s4a"] = lambda: run_s4a(ctx, cid)
        runners["s4b"] = lambda: run_s4b(ctx, cid)
        runners["s4"] = lambda: run_s4(ctx, cid)
        runners["s6"] = lambda: run_s6(ctx, cid)
        # 패키지는 외모·장면·영상 산출물이 있어야 만든다(LLD §8.10)
        runners["s11"] = lambda: build_package(ctx, cid)
        runners["sx"] = sx
    from character_factory_poc.pipeline.origin import read_origin

    if read_origin(ctx.character_dir(cid)) == SOURCE:
        # D-0128: 모티브는 s1이 없고, s0·s2·s3·s9h는 모티브 판 실행 함수가 생길 때까지 돌지 않는다.
        # 장면·영상·패키지는 s2(받은 사진 기준) 승인을 기다리는 같은 실행 함수를 쓴다.
        if opt.ranking is not None:
            raise FactoryError("모티브 캐릭터는 --ranking을 받지 않는다(얼굴은 받은 사진에서 온다)")
        for sid in ("s1", "s2", "s3"):
            runners.pop(sid, None)
        from character_factory_poc.pipeline.origin import read_video_tier
        from character_factory_poc.stages.s0_source.run import run_s0
        from character_factory_poc.stages.s2_hero.twin import run_s2_twin
        from character_factory_poc.stages.s3_plan.twin import run_s3_twin
        from character_factory_poc.stages.s6_actions.catalog import ALL_CHAPTERS, VIDEO_TIERS
        from character_factory_poc.stages.s8_prompts.chapter_start import run_s8c

        tier = VIDEO_TIERS.get(read_video_tier(ctx.character_dir(cid)))
        chapters = tier.chapters if tier else ALL_CHAPTERS
        runners.update(
            {
                "s8c": lambda: run_s8c(ctx, cid),
                "s0": lambda: run_s0(ctx, cid, opt.source_pack),
                "s2": lambda: run_s2_twin(ctx, cid),
                "s3": lambda: run_s3_twin(ctx, cid),
                "s5": lambda: run_s5(ctx, cid),
                "s4a": lambda: run_s4a(ctx, cid, chapters=chapters),
                "s4b": lambda: run_s4b(ctx, cid),
                "s4": lambda: run_s4(ctx, cid),
                "s6": lambda: run_s6(ctx, cid),
                "s11": lambda: build_package(ctx, cid),
                "sx": sx,
            }
        )
        from character_factory_poc.pipeline.graph import TRAIN
        from character_factory_poc.pipeline.origin import read_model_mode

        if read_model_mode(ctx.character_dir(cid)) == TRAIN:
            # D-0118: 모티브 학습 데이터는 실제 발화에서 만든다(모델 호출 없음).
            from character_factory_poc.stages.s9_data.twin import run_s9_twin, run_s9s_twin

            runners["s9s"] = lambda: run_s9s_twin(ctx, cid)
            runners["s9"] = lambda: run_s9_twin(ctx, cid)

            def s10_twin_train() -> Path | None:
                # 순서 8: 기존 평가 보고서가 G8을 연 뒤 실제 답 비교를 같은 G8에 붙인다.
                from character_factory_poc.stages.s10_eval import prompt_only
                from character_factory_poc.stages.s10_eval.compare import append_twin_comparison

                out = s10()
                if out is None or prompt_only.is_prompt_only(out):
                    return out
                if not (out / "report.json").is_file():
                    return out
                return append_twin_comparison(ctx, cid)

            runners["s10"] = s10_twin_train
        else:
            # D-0118: 학습하지 않는 방식은 G8에서 긴 프롬프트 또는 연결한 모델을 채택한다.
            from character_factory_poc.stages.s10_eval.twin import run_s10_twin

            runners["s10"] = lambda: run_s10_twin(ctx, cid)
        from character_factory_poc.stages.s9h_holdout.run import run_s9h

        runners["s9h"] = lambda: run_s9h(ctx, cid)
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


def _skip_note(ctx: Context, cid: str, sid: str, runners: dict) -> str | None:
    """실행 함수가 없는 단계의 건너뜀 문장. 기록할 것이 없으면 None."""
    from character_factory_poc.pipeline.origin import read_origin, stage_def

    stage = stage_def(ctx.character_dir(cid), sid)
    if stage.implemented and sid in runners:
        return None
    if ctx.state(cid).stage(sid).status == "PENDING":
        if read_origin(ctx.character_dir(cid)) == SOURCE:
            # D-0128: 모티브 앞단(s0·s2·s3·s9h)은 계획 §12 순서 2~6에서 구현한다.
            return f"{sid}: 모티브 {stage.name} — 아직 구현 전"
        if sid == "s1":
            return "s1: --ranking 없음 — 건너뜀(페르소나 우선 경로)"
        if sid in APPEARANCE_STAGES:
            return f"{sid}: 외모 축(S1·S2) 없음 — 건너뜀"
    return ""


def _mark_failed(ctx: Context, cid: str, sid: str, message: str) -> None:
    """실행 중으로 남은 단계를 CHECK_FAILED로 바꾼다. 이미 다른 상태면 그대로 둔다."""
    try:
        state = ctx.state(cid)
        st = state.stage(sid)
        if st.status == "RUNNING":
            state.transition(sid, "CHECK_FAILED", rev=st.currentRev, error=message[:2000])
    except (StateTransitionError, OSError):
        pass


def _matches_video_scope(ctx, cid, sid, rev):
    """등급이 바뀌면 범위가 같은 승인 결과만 재사용한다."""
    from character_factory_poc.common.store import read_json
    from character_factory_poc.pipeline.origin import read_video_tier
    from character_factory_poc.stages.s6_actions.catalog import VIDEO_TIERS

    folder = ctx.character_dir(cid)
    tier = read_video_tier(folder)
    if sid == "s2":
        return True
    state = ctx.state(cid)
    if sid == "s6":
        data = read_json(folder / "s6-actions" / rev / "inputs.json")
        return data["preset"] == f"tier:{tier}" and data["frameRev"] == state.gate("G4").rev
    locations = {
        "s4a": ("s4a-backgrounds", "background-candidates.json"),
        "s4b": ("s4b-poses", "scene-plan.json"),
        "s4": ("s4-frames", "scene-plan.json"),
    }
    dirname, filename = locations[sid]
    data = read_json(folder / dirname / rev / filename)
    upstream = {
        "s4a": ("planRev", "G3"),
        "s4b": ("backgroundRev", "G4a"),
        "s4": ("sceneRev", "G4b"),
    }
    field, gate = upstream[sid]
    if data[field] != state.gate(gate).rev:
        return False
    chapters = data["chapters"]
    return [ch["chapterId"] for ch in chapters] == list(VIDEO_TIERS[tier].chapters)


def _step(
    ctx: Context,
    cid: str,
    sid: str,
    opt: RunOptions,
    runners: dict,
    log: RunLog,
    *,
    auto_review: bool = False,
) -> str | None:
    """단계 하나를 처리한다(D-0035 규칙 그대로). 반환: None(다음 단계로), "break", "return".

    순차 훑기와 물결 실행(LLD §6.6)이 함께 쓴다.
    """
    from character_factory_poc.pipeline.origin import stage_def

    stage = stage_def(ctx.character_dir(cid), sid)  # D-0128: 모티브는 갈래 그래프의 관문을 쓴다
    state = ctx.state(cid)
    st = state.stage(sid)
    gate_ok = stage.gate is None or state.gate(stage.gate).status == "APPROVED"
    ran = False
    reusable = st.status in {"APPROVED", "SKIPPED"} or (st.status == "AWAITING_HUMAN" and gate_ok)
    if sid == "s8" and (reusable or st.status == "AWAITING_HUMAN"):
        from character_factory_poc.stages.s8_prompts.evidence_pipeline import (
            is_evidence,
            verify_review,
        )

        prompt_dir = ctx.character_dir(cid) / "s8-prompts" / str(st.currentRev)
        if is_evidence(prompt_dir):
            try:
                verify_review(ctx, cid, prompt_dir, approved=st.status == "APPROVED")
            except (OSError, ValueError, KeyError, TypeError):
                log.add(
                    "s8: 검토한 원천 또는 설정이 변경됐다. 해당 원천을 바로잡고 S8을 다시 생성한다"
                )
                log.blocked.append("s8")
                return "break"
    if reusable and sid == "s8c":
        from character_factory_poc.common.canonical import sha256_file
        from character_factory_poc.common.store import read_json
        from character_factory_poc.stages.s8_prompts.evidence_pipeline import is_evidence

        prompt_rev = state.stage("s8").currentRev
        prompt_dir = ctx.character_dir(cid) / "s8-prompts" / str(prompt_rev)
        if is_evidence(prompt_dir):
            pinned = ctx.character_dir(cid) / "s8-chapters" / str(st.currentRev) / "inputs.json"
            inputs = read_json(pinned) if pinned.is_file() else {}
            pair_path = prompt_dir / "prompt-pair.json"
            reusable = (
                pair_path.is_file()
                and inputs.get("promptRevision") == prompt_rev
                and inputs.get("promptPairSha256") == sha256_file(pair_path)
            )
    if reusable and (not opt.video_only or _matches_video_scope(ctx, cid, sid, st.currentRev)):
        log.add(f"{sid}: 이미 {st.status}({st.currentRev}) — 건너뜀")
    elif st.status == "AWAITING_HUMAN" and stage.gate:
        if opt.video_only and not _matches_video_scope(ctx, cid, sid, st.currentRev):
            raise NeedsInputError(
                "다른 등급으로 만들던 장면이 있어요. 먼저 기다리는 검토를 마쳐 주세요."
            )
        log.add(f"{sid}: {stage.gate} 대기 중({st.currentRev})")
    else:
        try:
            state.require_deps(sid)
        except GateNotApprovedError as e:
            log.add(f"{sid}: 시작 불가 — {e}")
            log.blocked.append(sid)
            return "break" if opt.until == sid else None
        # D-0049: 워크숍 실행은 유료 공급자 단계를 사람이 확인하기 전에는 돌리지 않는다.
        from character_factory_poc.pipeline.scheduler import paid_stage

        if (
            opt.web
            and sid not in opt.confirmed
            and (paid_stage(ctx, sid) or gpu_eval_held(ctx, cid, sid))
        ):
            log.add(f"{sid}: 유료 공급자 — 실행 확인 대기")
            log.held.append(sid)
            return None
        # D-0049: 수정 요청 뒤 다시 돌기 전에 재작업 브리프·반복 상한을 본다.
        if st.status == "REJECTED":
            from character_factory_poc.pipeline.rework import prepare_rework

            if not prepare_rework(ctx, cid, sid, opt):
                log.add(f"{sid}: {stage.gate} 반복 상한 — 사람 허락 대기")
                log.blocked.append(sid)
                return None
        log.add(f"{sid}: 실행")
        started = _now()
        try:
            out = runners[sid]()
        except NeedsInputError as e:
            log.add(f"{sid}: 사람 입력 대기 — {e}")
            log.blocked.append(sid)
            return None
        except GateNotApprovedError as e:
            log.add(f"{sid}: 시작 불가 — {e}")
            log.blocked.append(sid)
            return None
        except CheckFailed as e:
            # 검사 실패는 그 단계만 멈춘다. 다른 갈래는 계속 돈다(D-0035).
            _mark_failed(ctx, cid, sid, str(e))
            log.add(f"{sid}: 검사 실패 — {e}")
            log.blocked.append(sid)
            if opt.until == sid:
                log.stopped_at = sid
                return "return"
            return None
        except (AgentFormatError, SystemExit) as e:
            # 형식 재시도를 다 쓴 경우와, 단계가 검사 실패를 SystemExit(메시지)로 알리는
            # 경우도 검사 실패와 같이 그 단계만 멈춘다. 상태가 RUNNING으로 남지 않게
            # CHECK_FAILED로 바꾼다(K-0089).
            if isinstance(e, SystemExit) and not isinstance(e.code, str):
                raise
            message = e.code if isinstance(e, SystemExit) else str(e)
            _mark_failed(ctx, cid, sid, message)
            log.add(f"{sid}: 검사 실패 — {message}")
            log.blocked.append(sid)
            if opt.until == sid:
                log.stopped_at = sid
                return "return"
            return None
        except Exception as e:
            # 예상하지 못한 오류는 작업을 실패로 끝내되, 단계가 실행 중으로 남지 않게 한다(K-0089).
            _mark_failed(ctx, cid, sid, f"{type(e).__name__}: {e}")
            raise
        finally:
            log.timings[sid] = {"start": started, "end": _now()}
        ran = True
        if out is None:
            log.add(f"{sid}: 건너뜀({ctx.state(cid).stage(sid).status})")
        else:
            log.add(f"{sid}: 완료 → {out}")
    # 관문 처리: 자동 승인 플래그가 없으면 기다리는 관문으로 모으고 다른 갈래를 계속 진행한다
    state = ctx.state(cid)
    gate = stage.gate
    evidence_review = False
    if sid in {"s8", "s8c"} and state.gate("G6").rev:
        from character_factory_poc.stages.s8_prompts.evidence_pipeline import is_evidence

        evidence_review = is_evidence(ctx.character_dir(cid) / "s8-prompts" / state.gate("G6").rev)
    if auto_review and sid == "s8" and not evidence_review:
        gate = None  # 챕터 설정과 대화 표본까지 준비된 뒤 프롬프트를 승인한다.
    if auto_review and sid == "s8c" and state.stage(sid).status == "APPROVED":
        gate = "G6"
    if gate and state.gate(gate).status == "AWAITING_HUMAN":
        if gate == "G6" and evidence_review:
            log.add("G6: 원문 근거와 적용 조건 검토 대기")
            if gate not in log.waiting:
                log.waiting.append(gate)
        elif opt.video_only:
            approve_gate(
                ctx,
                cid,
                gate,
                {
                    "decision": "APPROVE",
                    "reviewer": "자동 진행",
                    "reasons": "고른 영상 등급에 맞춰 첫 후보를 선택했어요.",
                },
            )
            log.add(f"{gate}: 자동 진행")
        elif auto_review and gate in {"G0", "G3", "G6"}:
            approve_text_gate(ctx, cid, gate)
            log.add(f"{gate}: 자동 진행")
        elif gate in opt.auto_approve:
            _auto_approve(ctx, cid, gate)
            log.add(f"{gate}: 자동 승인(--auto-approve)")
        else:
            if ran:
                from character_factory_poc.pipeline.review import review_on_open

                review_on_open(ctx, cid, gate)
            log.add(f"{gate}: 사람 검토 대기")
            if gate not in log.waiting:
                log.waiting.append(gate)
    if opt.until in (sid, stage.gate):
        log.add(f"{opt.until}에 도달해 멈춘다")
        log.stopped_at = opt.until
        return "return"
    return None


def _finish(log: RunLog) -> RunLog:
    log.stopped_at = (log.waiting or log.blocked or ["end"])[0]
    if log.waiting or log.blocked:
        log.add(
            "더 진행할 단계가 없다. 기다리는 관문: "
            + (", ".join(log.waiting) or "없음")
            + " / 시작하지 못한 단계: "
            + (", ".join(log.blocked) or "없음")
        )
    return log


def run_until(ctx: Context, cid: str, opt: RunOptions) -> RunLog:
    validate_until(opt.until)
    validate_auto_approve(opt.auto_approve)
    from character_factory_poc.pipeline.origin import graph_for_dir, read_auto_review

    char_dir = ctx.character_dir(cid)
    graph = graph_for_dir(char_dir)
    if opt.until == "G6" and "s8c" in graph:
        # 모티브의 프롬프트 검토에는 첫 장면도 함께 준비한다.
        opt = replace(opt, until="s8c")
    auto_review = read_auto_review(char_dir)
    if not opt.video_only and not auto_review and opt.max_parallel > 1:
        # D-0049(LLD §6.6): 의존이 풀린 단계를 동시에 돌린다.
        from character_factory_poc.pipeline.scheduler import run_waves

        return run_waves(ctx, cid, opt)
    log = RunLog()
    runners = _stage_runners(ctx, cid, opt)
    # 자동 진행은 직렬 텍스트 경로만 탄다. 사진·영상·학습·평가는 별도 실행 확인이 필요하다.
    from character_factory_poc.pipeline.origin import VIDEO_STAGES

    for sid in VIDEO_STAGES if opt.video_only else graph:
        if auto_review and sid not in {"s0", "s3", "s7", "s8", "s8c"} and sid not in opt.confirmed:
            continue
        note = _skip_note(ctx, cid, sid, runners)
        if note is not None:
            if note:
                log.add(note)
            continue
        action = _step(ctx, cid, sid, opt, runners, log, auto_review=auto_review)
        if (auto_review or opt.video_only) and (log.blocked or log.held):
            break
        if action == "break":
            break
        if action == "return":
            return log
    return _finish(log)
