"""D-0082: 영상통화 카메라 관찰 규칙과 부딪히는 외모 읽기를 저작 단계에서 막는다."""

from character_factory_poc.common.call_context import (
    CALL_OBSERVATION_RULE,
    appearance_reading_problems,
)
from character_factory_poc.common.schema import validate
from character_factory_poc.stages.s3_plan.check_v2 import check_plan_v2
from character_factory_poc.stages.s7_traits.check import check_trait_sheet
from character_factory_poc.stages.s8_prompts.actor_persona import compose_approved_sheet
from tests.support.flow import v2_plan
from tests.support.synthetic import trait_sheet


def test_plan_check_rejects_reading_the_users_appearance():
    plan = v2_plan("cf-20260101-x", coreTraits=["상대의 안색과 눈 밑을 먼저 살핀다"])
    problems = check_plan_v2(None, [])(validate("character-plan-v2", dict(plan, variantId="v1")))
    assert any(p.startswith("coreTraits:") and "안색" in p for p in problems)
    ok = v2_plan("cf-20260101-x", coreTraits=["상대가 고개를 숙이면 말을 줄이고 기다린다"])
    assert check_plan_v2(None, [])(validate("character-plan-v2", dict(ok, variantId="v1"))) == []


def test_trait_check_rejects_appearance_reading_in_attention():
    raw = trait_sheet("cf-20260101-x", "pr1")
    raw["choice"]["attention"] = "상대의 말보다 피로도와 다크서클 같은 몸 상태를 먼저 본다."
    problems = check_trait_sheet(validate("trait-sheet-v1", raw))
    assert any(p.startswith("choice.attention:") for p in problems)
    assert appearance_reading_problems("x", "한숨 소리에 말을 멈춘다") == []


def test_call_observation_rule_lives_in_the_shared_frame_only():
    """D-0089: 관찰 규칙은 공유 프레임이 소유하고 페르소나 칸에 중복하지 않는다(MD-1.4)."""
    from character_factory_poc.stages.s8_prompts.actor_persona import load_actor_rules

    rules, _ = load_actor_rules()
    plan = v2_plan("cf-20260101-x")
    sheet = validate("trait-sheet-v1", trait_sheet("cf-20260101-x", "pr1"))
    text, sections = compose_approved_sheet(plan, sheet, rules_text=rules)
    assert CALL_OBSERVATION_RULE in rules
    assert CALL_OBSERVATION_RULE not in sections["PERSONA / KNOWS_AND_LIMITS"]
    assert text.count(CALL_OBSERVATION_RULE) == 1


def test_plan_core_mention_survives_changed_sentence_ending():
    from character_factory_poc.stages.s7_traits.check import _mentions

    plan = "새벽 4시에 시작되는 제빵 루틴을 철저히 지키며 맡은 분량의 책임을 다한다."
    kept = (
        "새벽 4시에 시작되는 제빵 루틴을 철저히 지키며 맡은 분량의 책임을 다하고, 묵묵히 완수한다."
    )
    rewritten = "새벽부터 이어지는 자신의 제빵 루틴과 원칙을 지키며 맡은 몫을 완수한다."
    assert _mentions(plan, kept)
    assert not _mentions(plan, rewritten)


def test_plain_advice_word_is_allowed_and_null_evidence_is_empty():
    from character_factory_poc.contracts.planning import EvidenceV2

    assert appearance_reading_problems("voiceExamples", "빈속에 커피만 마시면 속 쓰려요") == []
    assert EvidenceV2(kind="AGENT", ref=None, quote=None).quote == ""
