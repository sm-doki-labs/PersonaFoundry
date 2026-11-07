import pytest

from scripts.persona_choice_voice_live_20261029 import validate_collected_reply


def row():
    return dict(
        status="OK",
        assistant="응",
        response=dict(input_tokens=5000, output_tokens=100, finish_reason="stop"),
    )


@pytest.mark.parametrize("status", ["FAILED", "USAGE_UNVERIFIED"])
def test_failed_first_response_cannot_resume_as_history(status):
    value = row()
    value["status"] = status
    assert not validate_collected_reply(value)


@pytest.mark.parametrize(
    "change",
    [
        {"input_tokens": None},
        {"finish_reason": "length"},
        {"input_tokens": 23000},
        {"output_tokens": 2400},
    ],
)
def test_missing_usage_or_overflow_cannot_continue(change):
    value = row()
    value["response"].update(change)
    assert not validate_collected_reply(value)


def test_complete_bounded_first_response_can_resume():
    assert validate_collected_reply(row())
