"""S7 특질 장부의 '구체적인 행동' 검사(D-0223). 실제 실패 문장으로 본다."""

import pytest

from character_factory_poc.stages.s7_traits.ledger import _ACTION

# 2026-11-13 손흥민 S7 1·2차 시도에서 '말투만'으로 잘못 걸러진 문장.
CONCRETE = [
    "자신이 직접 해 본 경험이 없어 잘 모른다고 분명히 밝힌 뒤, 자신이 실제로 겪어 잘 알고 있는 "
    "축구나 운동 루틴 이야기로 범위를 좁혀 답을 맺는다.",
    "아는 체하지 않고 자신이 해 보지 않아 잘 모른다는 사실 한계를 먼저 밝힌 뒤 화제를 자신이 "
    "아는 일상으로 돌린다.",
    "현재 확정되지 않은 사안이라 지금 밝힐 수 있는 내용이 없다고 선을 긋고, 혼자 결정할 수 없는 "
    "일이니 때를 기다려 달라고 답을 미룬다.",
    "직전에 상대가 건넨 짓궂은 놀림을 그대로 짚어 맞받아치는 농담을 건넨 뒤 본래 대화로 돌아간다.",
]
VAGUE = [
    "차분한 말투로 짧게 말한다.",
    "밝은 목소리로 담백하게 대답한다.",
    "문장을 짧게 끊어 존댓말로 말한다.",
]


@pytest.mark.parametrize("text", CONCRETE)
def test_concrete_actions_pass_even_with_words_in_between(text):
    assert _ACTION.search(text)


@pytest.mark.parametrize("text", VAGUE)
def test_tone_only_lines_are_still_rejected(text):
    assert not _ACTION.search(text)


def test_tone_check_is_a_soft_warning():
    """D-0223: '말투만' 검사는 권장 표시가 붙어 마지막 시도에서 단계를 멈추지 않는다."""
    from character_factory_poc.stages.s7_traits.ledger import SOFT, soft_only

    assert soft_only([SOFT + "t4.behavior: 말투만 적지 말고"])
    assert not soft_only([SOFT + "a", "시연 상황 UNKNOWN: 선택이 하나 필요하다"])
    assert not soft_only([])


def test_ledger_with_only_soft_problems_is_accepted_with_warnings(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from character_factory_poc.pipeline.agent import AgentResult
    from character_factory_poc.stages.s7_traits import ledger

    raw = ledger._example("cf-x", "pr1")
    soft = [ledger.SOFT + "t1.behavior: 말투만 적지 말고 구체적으로 무엇을 하는지 쓴다"]
    monkeypatch.setattr(ledger, "motif_tendencies", lambda *a: None)
    plan = SimpleNamespace(planRev="pr1", name="손흥민", evidence={})
    monkeypatch.setattr(ledger, "dump", lambda obj: {"choice": {}, "card": {}, "planRev": "pr1"})
    ctx = SimpleNamespace(agent_backend=lambda *a: None)

    monkeypatch.setattr(ledger, "run_agent", lambda *a, **k: AgentResult(False, None, raw, soft, 2))
    out = ledger.run_ledger(ctx, "cf-x", plan, object(), tmp_path, None, None)
    assert out.planRev == "pr1"
    assert json.loads((tmp_path / "ledger-warnings.json").read_text("utf-8"))["warnings"] == soft

    hard = soft + ["시연 상황 UNKNOWN: 선택이 하나 필요하다"]
    monkeypatch.setattr(ledger, "run_agent", lambda *a, **k: AgentResult(False, None, raw, hard, 2))
    with pytest.raises(SystemExit):
        ledger.run_ledger(ctx, "cf-x", plan, object(), tmp_path / "b", None, None)
