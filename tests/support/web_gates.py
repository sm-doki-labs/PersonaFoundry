"""워크숍 관문 화면 테스트용 합성 흐름 (K-0037).

가짜 공급자로 S1부터 필요한 관문까지 실제 단계를 돌린다. 네트워크·실제 공급자는 쓰지 않는다.
마지막 관문만 대기로 남기고 앞 관문은 기본 답으로 통과시켜, 결정 API를 그 관문에서 시험한다.
답 형식은 화면이 만드는 것과 같은 모양이다(`src/acf/stages/*/approve.py` 참고).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from acf.pipeline.approve import approve_gate
from acf.pipeline.context import Context
from acf.providers.fake import FakeTextModel
from acf.stages.s1_reference.run import run_s1
from acf.stages.s2_hero.run import run_s2
from acf.stages.s3_plan.draft import new_character
from acf.stages.s3_plan.own import run_s3_own
from acf.stages.s3_plan.seed import write_seed
from acf.stages.s3_plan.variants import run_s3_variants
from acf.stages.s4_frames.run import run_s4
from acf.stages.s4a_backgrounds.run import run_s4a
from acf.stages.s4b_poses.run import run_s4b
from acf.stages.s5_intro.run import run_s5
from acf.stages.s6_actions.run import run_s6
from acf.stages.s7_traits.sheet import run_s7
from acf.stages.s8_prompts.build import run_s8
from tests.support.flow import make_ctx, sample_plan_v2
from tests.support.synthetic import RANKING, prompter_output, trait_sheet
from tests.test_plan_variants import output as plan_variants
from tests.test_scene_flow import backgrounds, poses, scenes

SLUG = "webgate"
SEED = {"personality": "조용하지만 단단함", "job": "책방 직원", "age": 24}
PROBES = ["시험 망쳤어.", "너 발표 잘하더라."]
OWN_TEXT = "윤하린은 24세 여성 책방 직원이다. 말보다 먼저 상대를 기다린다."
CONNECTED = ("G1", "G3", "G4a", "G4b", "G4", "G5", "G5b", "G6")


def build(
    tmp_path: Path, until: str = "G1", slug: str = SLUG, own: bool = False
) -> tuple[Context, str]:
    """S1부터 until 관문이 대기할 때까지 돈다. 앞 관문은 기본 답으로 통과시킨다."""
    if until not in CONNECTED:
        raise ValueError(f"연결된 관문이 아니다: {until}")
    ctx, agents = make_ctx(tmp_path)
    cid = new_character(ctx, slug)
    agents.set("s3-variants", lambda req: plan_variants(cid))
    agents.set("s4a", backgrounds)
    agents.set("s4b-scene", scenes)
    agents.set("s4b-pose", poses)
    agents.set("s7", lambda req: trait_sheet_for(ctx, cid))
    agents.set("s8", lambda req: prompter_output())
    ctx._text.add("PROBE", lambda req: "그럼 이렇게 하자. 내일 아침에 같이 보자.")
    judge = FakeTextModel(model="fake-judge")
    judge.add("JUDGE", {"pick": "A", "reasons": "선택이 더 맞는다"})
    ctx.use_models(ctx._text, judge)

    run_s1(ctx, cid, RANKING)
    if until == "G1":
        return ctx, cid
    approve_gate(
        ctx,
        cid,
        "G1",
        {
            "decision": "SELECT",
            "selections": ["c2"],
            "referencePreviews": ["c2-1"],
            "reviewer": "tester",
        },
    )
    run_s2(ctx, cid)
    write_seed(ctx, cid, SEED)
    if own:
        agents.set("s3-own", lambda req: own_plan(cid))
        run_s3_own(ctx, cid, OWN_TEXT)
    else:
        run_s3_variants(ctx, cid)
    if until == "G3":
        return ctx, cid
    approve_gate(ctx, cid, "G3", {"decision": "APPROVE", "reviewer": "tester"})
    if until in {"G5", "G5b", "G6"}:
        run_s5(ctx, cid)
        if until == "G5":
            return ctx, cid
    run_s4a(ctx, cid)
    if until == "G4a":
        return ctx, cid
    approve_gate(ctx, cid, "G4a", {"decision": "APPROVE", "reviewer": "tester"})
    run_s4b(ctx, cid)
    if until == "G4b":
        return ctx, cid
    approve_gate(ctx, cid, "G4b", {"decision": "APPROVE", "reviewer": "tester"})
    run_s4(ctx, cid)
    if until == "G4":
        return ctx, cid
    approve_gate(ctx, cid, "G4", {"decision": "APPROVE", "reviewer": "tester"})
    if until == "G5b":
        run_s6(ctx, cid)
        return ctx, cid
    run_s7(ctx, cid)
    run_s8(ctx, cid, PROBES)
    return ctx, cid


def trait_sheet_for(ctx: Context, cid: str) -> dict:
    """승인된 기획서의 핵심 성격을 특질 시트에 그대로 넣어 S7 검사를 통과시킨다."""
    plan_path = ctx.character_dir(cid) / "s3-plan" / "pr1" / "plan.json"
    plan = json.loads(plan_path.read_text("utf-8"))
    sheet = trait_sheet(cid, "pr1")
    sheet["card"]["expressedTraits"]["core"] = list(plan["coreTraits"])
    return sheet


def own_plan(cid: str) -> dict:
    """사람이 쓴 글을 정리한 u1 후보. 이름 근거를 USER로 남긴다(run_s3_own 검사)."""
    raw = copy.deepcopy(sample_plan_v2(cid))
    raw["evidence"] = {
        "name": [{"kind": "USER", "ref": "user-text.md", "quote": "윤하린"}],
        "coreTraits": [{"kind": "AGENT", "ref": "보완", "quote": ""}],
    }
    return raw


def answer_for(gate: str, items: dict) -> dict:
    """화면이 만드는 답과 같은 모양. 항목에서 ID를 꺼내 쓴다."""
    if gate == "G1":
        cluster = items["clusters"][0]
        face = cluster["faces"][0]
        return {
            "decision": "SELECT",
            "selections": [cluster["clusterId"]],
            "referencePreviews": [face["previewId"]],
            "reviewer": "tester",
            "minutes": 1.5,
            "reasons": "추천 얼굴로 고정",
        }
    if gate == "G3":
        return {
            "decision": "SELECT",
            "selections": ["v2"],
            "edits": {"tagline": "고른 책은 끝까지 읽는다"},
            "reviewer": "tester",
            "minutes": 2,
            "reasons": "조율을 먼저 하는 쪽",
        }
    if gate == "G4a":
        return {
            "decision": "SELECT",
            "picks": {"ch1": "ch1-b2", "ch2": "ch2-b1"},
            "custom": {"ch3": "강변 산책길 끝의 조용한 쉼터. 노을이 보인다."},
            "reviewer": "tester",
        }
    if gate == "G4b":
        picks = {}
        for chapter in items["chapters"]:
            picks[chapter["chapterId"]] = chapter["candidates"][0]["poseId"]
        return {
            "decision": "SELECT",
            "picks": picks,
            "tweaks": {"ch1": {"hands": "두 손을 무릎에 편안하게 둔다"}},
            "reviewer": "tester",
        }
    if gate == "G4":
        return {"decision": "APPROVE", "reviewer": "tester", "reasons": "세 장 모두 확인"}
    if gate == "G5":
        return {
            "decision": "SELECT",
            "selections": [items["candidates"][0]["candidateId"]],
            "reviewer": "tester",
        }
    if gate == "G5b":
        picks = {}
        for chapter in items["chapters"]:
            for action in chapter["actions"]:
                picks[action["actionId"]] = action["candidates"][0]["candidateId"]
        return {"decision": "SELECT", "picks": picks, "reviewer": "tester"}
    if gate == "G6":
        return {"decision": "APPROVE", "reviewer": "tester", "minutes": 3}
    raise ValueError(f"연결된 관문이 아니다: {gate}")
