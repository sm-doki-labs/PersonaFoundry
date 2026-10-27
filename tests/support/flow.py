"""새 기획·배경·자세 흐름(D-0033~D-0035) 테스트 공용 도우미. 네트워크 없음.

- make_ctx: 가짜 텍스트·이미지·영상 모델을 붙인 Context. 에이전트 응답은 stage별 함수로 등록한다.
- through_s2: S1 → G1(c2, 얼굴 c2-1) → S2(picked, 자동 APPROVED)까지 진행한 캐릭터(D-0042).
- sample_plan_v2 / approve_plan_v2: 변형 흐름 없이 v2 기획서를 G3 승인 상태로 바로 고정한다
  (S4a 이후를 시험할 때 쓴다).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import acf.contracts  # noqa: F401
from acf.common.schema import dump, validate
from acf.common.store import next_rev, write_manifest, write_once_json
from acf.pipeline.approve import approve_gate
from acf.pipeline.context import Context
from acf.pipeline.gates import write_gate_record
from acf.providers.fake import FakeTextModel
from acf.providers.fake_image import FakeImageModel
from acf.providers.fake_video import FakeVideoModel
from acf.stages.s1_reference.run import run_s1
from acf.stages.s2_hero.run import run_s2
from acf.stages.s3_plan.draft import new_character
from tests.support.synthetic import RANKING, scout_features
from tests.test_agentic import CATALOG

Responder = Callable[[Any], Any]


class StageAgents:
    """req.stage(AgentSpec.stage)별 가짜 에이전트 응답. s1은 합성 Scout가 기본이다."""

    def __init__(self) -> None:
        self.by_stage: dict[str, Responder] = {"s1": lambda req: scout_features(RANKING)}
        self.calls: list[str] = []

    def set(self, stage: str, fn: Responder) -> None:
        self.by_stage[stage] = fn

    def __call__(self, req) -> Any:
        self.calls.append(req.stage)
        if req.stage not in self.by_stage:
            raise KeyError(f"가짜 에이전트 응답이 없다: stage={req.stage}")
        return self.by_stage[req.stage](req)


def make_ctx(root: Path, extra_toml: str = "") -> tuple[Context, StageAgents]:
    (root / "catalog.json").write_text(json.dumps(CATALOG, ensure_ascii=False), "utf-8")
    # D-0043 (6): 이번 PoC는 G1 얼굴을 그대로 기준 이미지로 쓰는 picked만 구현했다.
    # 시험이 [stages.s2]를 직접 지정하면 그대로 쓴다.
    s2 = "" if "[stages.s2]" in extra_toml else '\n[stages.s2]\nbase_photo = "picked"\n'
    (root / "factory.toml").write_text(
        f'[resources]\nstanford_presets_json = "{root / "catalog.json"}"\n{extra_toml}{s2}',
        encoding="utf-8",
    )
    ctx = Context.load(root, execute=True)
    agents = StageAgents()
    text = FakeTextModel()
    text.add("AGENT", agents)
    ctx.use_models(text)
    ctx.use_image(FakeImageModel())
    ctx.use_video(FakeVideoModel())
    return ctx, agents


def through_s2(ctx: Context, slug: str = "flow") -> str:
    cid = new_character(ctx, slug)
    run_s1(ctx, cid, RANKING)
    approve_gate(
        ctx,
        cid,
        "G1",
        {
            "decision": "SELECT",
            "selections": ["c2"],
            "referencePreviews": ["c2-1"],
            "reviewer": "u",
        },
    )
    run_s2(ctx, cid)
    return cid


ARC = {
    "ch1": (
        "GET_TO_KNOW",
        "친해지기",
        "STRANGER",
        "ACQUAINTANCE",
        "처음 만나 대화 속도와 취향을 확인한다",
    ),
    "ch2": (
        "FLIRT",
        "썸타기",
        "ACQUAINTANCE",
        "FLIRTING",
        "첫 데이트에서 서로의 호감을 조심스럽게 확인한다",
    ),
    "ch3": (
        "CONFESS",
        "고백하기",
        "FLIRTING",
        "DATING",
        "정돈되지 않은 마음을 꺼내 관계에 이름을 붙인다",
    ),
}


def sample_plan_v2(
    cid: str, rev: str = "pr1", variant: str = "v1", seed_rev: str = "sd1", **over: Any
) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "schemaVersion": "character-plan-v2",
        "characterId": cid,
        "planRev": rev,
        "variantId": variant,
        "seedRev": seed_rev,
        "name": "윤하린",
        "age": 24,
        "gender": "female",
        "job": "동네 책방 직원",
        "tagline": "필름 카메라를 들고 동네를 걷는 책방 직원",
        "background": (
            "서울 망원동 작은 책방에서 일하며 혼자 산다. 쉬는 날에는 필름 카메라로 골목을 찍는다."
        ),
        "coreTraits": [
            "처음 보는 사람 앞에서는 말수를 줄이고 상대가 좋아하는 이유를 끝까지 듣는다"
        ],
        "contrastTrait": "마음이 정해지면 다음 약속을 먼저 구체적으로 제안한다",
        "choices": [
            {
                "situation": "상대가 늦는다고 연락했을 때",
                "firstMove": "괜찮다고 하고 근처 서가에서 책을 고른다",
            },
            {"situation": "칭찬을 들었을 때", "firstMove": "무엇을 보고 한 말인지 되묻는다"},
            {
                "situation": "관계를 서둘러 정하자고 할 때",
                "firstMove": "지금 마음과 속도를 나눠 말한다",
            },
        ],
        "lifeAndTastes": [
            "흐린 날 필름 카메라를 들고 골목을 걷는다",
            "책방 문을 닫은 뒤 창가 자리에서 시집을 읽는다",
            "야구장 직관을 좋아해 조명이 켜질 때 도착하려 한다",
        ],
        "wantsAndFears": ["자기가 한 말을 정확히 기억해 주는 관심을 원한다"],
        "misreadings": ["조심스럽게 거리를 두는 태도가 관심이 식은 것으로 읽힐 수 있다"],
        "voiceSummary": "한두 문장으로 담백하게 말하고 감탄사를 아낀다",
        "voiceExamples": ["그 책, 저도 끝까지 읽었어요.", "오늘은 조금 더 걸어도 될 것 같아요."],
        "boundaries": ["일정이 불분명하면 그 자리에서 날짜를 확정하지 않는다"],
        "profileCard": {
            "hobby": "필름 사진",
            "likes": "흐린 날, 시집, 야구장 조명",
            "dislikes": "재촉",
            "favoriteFoods": "",
            "favoriteDrink": "따뜻한 보리차",
            "idealDate": "말없이 오래 걸어도 편한 산책",
            "everydayHabit": "문 닫기 전 서가 정리",
            "mbti": "INFJ",
            "tags": ["필름사진", "책방"],
            "tmi": [{"text": "필름 통에 영화표를 모은다", "revealStage": 1}],
        },
        "chapterArc": [
            {
                "chapterId": ch,
                "slot": a[0],
                "title": a[1],
                "entryStage": a[2],
                "targetStage": a[3],
                "arc": a[4],
            }
            for ch, a in ARC.items()
        ],
        "evidence": {
            "job": [{"kind": "SEED", "ref": seed_rev, "quote": "책방 직원"}],
            "coreTraits": [{"kind": "SEED", "ref": seed_rev, "quote": "조용하지만 단단함"}],
        },
        "appearanceRev": "ar1",
        "notes": "시험용 v2 기획서",
    }
    plan.update(over)
    return plan


def approve_plan_v2(ctx: Context, cid: str, plan: dict[str, Any] | None = None) -> Path:
    """v2 기획서를 s3-plan/pr<k>/plan.json으로 쓰고 G3 승인 기록을 남긴다(변형 흐름 생략)."""
    char_dir = ctx.character_dir(cid)
    rev = next_rev(char_dir / "s3-plan", "pr")
    obj = validate("character-plan-v2", plan or sample_plan_v2(cid, rev))
    obj = obj.model_copy(update={"characterId": cid, "planRev": rev})
    rev_dir = char_dir / "s3-plan" / rev
    write_once_json(rev_dir / "plan.json", dump(obj))
    write_manifest(rev_dir)
    state = ctx.state(cid)
    state.transition("s3", "RUNNING", rev=rev)
    state.transition("s3", "AWAITING_HUMAN", rev=rev)
    write_gate_record(
        char_dir,
        state,
        gate="G3",
        rev=rev,
        stage_id="s3",
        shown=[rev_dir / "plan.json"],
        decision="APPROVE",
        reviewer="test",
        reasons="테스트 도우미가 v2 기획서를 바로 고정했다",
    )
    return rev_dir
