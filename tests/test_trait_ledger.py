"""D-0091: 특질 장부, 장부 기반 조립, 챕터 시작 특질 재서술 검사, 자동 특질 시험 지표."""

import pytest

from character_factory_poc.common.schema import validate
from character_factory_poc.stages.s7_traits.ledger import SOFT, check_ledger
from character_factory_poc.stages.s8_prompts.actor_persona import (
    BASE_RATE_LINE,
    compose_from_ledger,
)
from character_factory_poc.stages.s8_prompts.trait_check import metrics
from tests.support.flow import v2_plan


def _ledger(**over):
    raw = {
        "schemaVersion": "trait-ledger-v1",
        "characterId": "cf-20260101-x",
        "planRev": "pr1",
        "disposition": ["인물은 차분하게 사실부터 말한다.", "인물은 생활 이야기를 짧게 곁들인다."],
        "coreTension": "인물은 질서를 지키고 싶어 물러서며 안도와 씁쓸함을 함께 느낀다.",
        "reading": "인물은 상대가 한 말의 구체적인 사실을 먼저 받는다.",
        "defaultResponse": "인물은 짧게 답하고 자기 하루를 덧붙인다.",
        "traits": [
            {
                "id": "t1",
                "kind": "insult_reaction",
                "trigger": "상대가 근거 없이 빵 맛을 깎아내릴 때",
                "nearMiss": "상대가 구체적인 맛의 이유를 들어 물을 때",
                "behavior": "인물은 대꾸를 멈추고 하던 정리를 마친다.",
                "rarity": "sometimes",
            },
            {
                "id": "t2",
                "kind": "flaw",
                "trigger": "오븐 타이머가 울리는 순간 상대가 긴 이야기를 이어갈 때",
                "nearMiss": "타이머가 없는 마감 뒤에 상대가 이야기할 때",
                "behavior": "인물은 작업을 이유로 대화를 먼저 끊는다.",
                "rarity": "rare",
            },
            {
                "id": "t3",
                "kind": "misreading",
                "trigger": "상대가 입맛이 없다고 흘릴 때",
                "nearMiss": "상대가 일이 바쁘다고만 말할 때",
                "behavior": "인물은 끼니를 걱정해 담백한 빵을 권한다.",
                "rarity": "rare",
            },
        ],
    }
    raw.update(over)
    return validate("trait-ledger-v1", raw)


def test_ledger_contract_requires_one_insult_reaction_and_a_flaw():
    from character_factory_poc.common.errors import ValidationFailed

    with pytest.raises(ValidationFailed, match="insult_reaction"):
        _ledger(traits=[t | {"kind": "choice"} for t in _ledger().model_dump()["traits"]])


def test_ledger_check_rejects_restating_a_trait_in_the_baseline():
    assert check_ledger("윤서진")(_ledger()) == []
    dup = _ledger(defaultResponse="인물은 오븐 타이머가 울리면 작업을 이유로 대화를 먼저 끊는다.")
    assert any("t2" in p for p in check_ledger("윤서진")(dup))


def test_ledger_check_rejects_praise_first_or_thanks_closing_default():
    for text in (
        "인물은 상대가 이미 충분히 잘하고 있다며 편들기부터 한 뒤 짧게 답한다.",
        "인물은 상대 말을 바로 받아 주고 다정한 감사나 다짐으로 말을 맺는다.",
    ):
        problems = check_ledger("윤서진")(_ledger(defaultResponse=text))
        assert any(p.startswith(SOFT + "defaultResponse: 상대 평가") for p in problems)


def test_ledger_check_keeps_speaking_style_out_of_the_baseline():
    over = {
        "defaultResponse": (
            "인물은 화제를 따라가며 경험을 근거로 설명한 뒤 단정을 누그러뜨려 말을 맺는다."
        ),
        "reading": "인물은 상대 말을 존댓말로 정중하게 받는다.",
    }
    problems = check_ledger("윤서진")(_ledger(**over))
    assert any(p.startswith(SOFT + "defaultResponse: 말하는 방식") for p in problems)
    assert any(p.startswith(SOFT + "reading: 말하는 방식") for p in problems)
    # 계기가 있는 특질의 말 행동(말끝 흐리기 등)은 막지 않는다.
    ok = _ledger()
    ok.traits[1].behavior = "인물은 대답을 한두 마디로 끊고 말끝을 흐린다."
    assert not any("말하는 방식" in p for p in check_ledger("윤서진")(ok))


def test_compose_from_ledger_puts_each_trait_once_with_the_base_rate_line():
    plan = dict(v2_plan("cf-20260101-x"), voiceSummary="정갈한 해요체로 짧게 말한다.")
    text, sections = compose_from_ledger(plan, _ledger(), rules_text="")
    choices = sections["PERSONA / CHOICES"]
    assert BASE_RATE_LINE in choices
    assert text.count("작업을 이유로 대화를 먼저 끊는다") == 1
    assert "대화 전체에서 드물게 나온다." in choices
    assert sections["PERSONA / VOICE"] == "정갈한 해요체로 짧게 말한다."


def test_chapter_start_check_rejects_restating_a_ledger_trait():
    from character_factory_poc.common.schema import dump
    from character_factory_poc.stages.s8_prompts.chapter_start import check_chapter_start
    from tests.test_chapter_start import _start

    ledger = dump(_ledger())
    ok = _start()
    assert check_chapter_start("해요체", ledger, "윤서진")(ok) == []
    raw = dump(_start())
    raw["chapters"][1]["relationship"]["sceneWant"] = (
        "인물은 상대가 입맛이 없다고 흘리면 끼니를 걱정해 담백한 빵을 권하고 싶다."
    )
    bad = validate("chapter-start-v1", raw)
    assert any("t3" in p for p in check_chapter_start("해요체", ledger, "윤서진")(bad))


def test_trait_check_metrics_separate_trigger_hits_from_off_trigger_fires():
    rows = [
        {"kind": "trigger", "traitId": "t3", "reply": "빵 드세요.", "fired": ["t3"]},
        {"kind": "nearMiss", "traitId": "t3", "reply": "바쁘시군요.", "fired": []},
        {"kind": "generic", "traitId": None, "reply": "끼니는요? 빵 드세요.", "fired": ["t3"]},
        {"kind": "generic", "traitId": None, "reply": "좋네요.", "fired": []},
    ]
    m = metrics(_ledger(), rows, polite=True)
    assert m["traits"]["t3"]["triggerHit"] == 1 and m["traits"]["t3"]["offFire"] == 1
    assert m["genericAnyFire"] == 1 and m["formalReplies"] == 0
