"""K-0073: S8 선택 경향의 상황 누락·'..', S7 말높임 충돌, 영상통화 말하기 규칙."""

from character_factory_poc.common.schema import validate
from character_factory_poc.stages.s7_traits.check import check_speech_level
from character_factory_poc.stages.s8_prompts.actor_persona import (
    compose_approved_sheet,
    load_actor_rules,
)
from tests.support.flow import v2_plan
from tests.support.synthetic import trait_sheet


def _sheet(**habits):
    raw = trait_sheet("cf-20260101-x", "pr1")
    raw["card"]["dialogueHabits"].update(habits)
    raw["card"]["judgmentPriorities"][0].update(
        dilemma="상대가 약속 시간에 늦는다고 연락할 때",
        choice="서두르지 말라고 하고 그동안 정리를 마친다.",
        switch="다급한 일이 생긴 단서가 있으면 안전부터 확인한다.",
    )
    return validate("trait-sheet-v1", raw)


def test_choices_keep_the_dilemma_and_have_no_double_period():
    text, sections = compose_approved_sheet(v2_plan("cf-20260101-x"), _sheet(), rules_text="")
    choices = sections["PERSONA / CHOICES"]
    assert ".." not in choices
    assert (
        "상대가 약속 시간에 늦는다고 연락할 때 → 서두르지 말라고 하고 그동안 정리를 마친다. "
        "다만 다급한 일이 생긴 단서가 있으면 안전부터 확인한다." in choices
    )


def test_formal_endings_conflict_with_a_haeyo_plan():
    check = check_speech_level("말끝을 정갈하게 맺는 해요체.")
    bad = _sheet(lexicon="'~합니다', '~해 두었습니다'처럼 맺음이 확실한 표현을 쓴다.")
    bare = _sheet(lexicon="천천히, 조심히, 괜찮습니다, 반죽처럼 같은 어휘를 자주 쓴다.")
    ok = _sheet(questions="'잠시 숨 좀 돌리고 이야기할까요?'처럼 드물게 묻는다.")
    assert any(p.startswith("card.dialogueHabits.lexicon:") for p in check(bad))
    assert any("괜찮습니다" in p for p in check(bare))
    assert check(ok) == []
    assert check_speech_level("")(bad) == []


def test_builtin_actor_rules_describe_speaking_in_a_video_call():
    rules, ref = load_actor_rules()
    assert ref == "builtin:actor-system-rules-v3"
    assert "문자 대화" not in rules and "영상통화" in rules


def test_voice_section_has_one_owner_and_summary_has_a_length_cap():
    """D-0090: 말투 칸은 기획 말투 요약 하나만 쓴다. 성격 시트 말버릇은 조립하지 않는다."""
    from character_factory_poc.stages.s3_plan.model_deck import voice_summary_length

    plan = dict(v2_plan("cf-20260101-x"), voiceSummary="정갈한 해요체로 짧게 말한다.")
    sheet = _sheet(lexicon="자주 쓰는 어휘장은 작업장 사물이다.")
    _, sections = compose_approved_sheet(plan, sheet, rules_text="")
    assert sections["PERSONA / VOICE"] == "정갈한 해요체로 짧게 말한다."

    class P:
        def __init__(self, n):
            self.variantId, self.voiceSummary = "v1", "가" * n

    class Out:
        variants = [P(701)]

    assert voice_summary_length(Out()) and not voice_summary_length(
        type("O", (), {"variants": [P(500)]})()
    )
