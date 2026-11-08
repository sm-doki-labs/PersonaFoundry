"""실제 패키지 경로에서 승인 기획의 높임 등급이 챕터 프로필까지 전달된다."""

import pytest

from character_factory_poc.stages.export.doki_app.chat_svc import build_tree
from character_factory_poc.stages.s11_release.package import build_package, load_package
from tests.support import export_flow
from tests.support.flow import approve_plan_v2, sample_plan_v2


@pytest.mark.parametrize(
    "summary,expected", [("처음부터 해요체로 답한다.", "POLITE"), ("짧은 반말을 쓴다.", "CASUAL")]
)
def test_exported_profiles_follow_approved_voice(tmp_path, monkeypatch, summary, expected):
    def approve(ctx, cid):
        plan = sample_plan_v2(cid)
        plan["voiceSummary"] = summary
        plan["chapterArc"][1]["arc"] = "가까워져도 말을 놓지 않는다."
        plan["chapterArc"][2]["arc"] = "상대가 동의하면 서로 말을 놓는다."
        return approve_plan_v2(ctx, cid, plan)

    monkeypatch.setattr(export_flow, "approve_plan_v2", approve)
    ctx, cid = export_flow.full_flow(tmp_path)
    build_package(ctx, cid)
    profiles = [
        v
        for k, v in build_tree(*load_package(ctx, cid)).files.items()
        if k.startswith("relationship_profiles/")
    ]
    assert [p["speechLevel"] for p in profiles] == [
        expected,
        expected,
        "FLEXIBLE" if expected == "POLITE" else "CASUAL",
    ]
    for p in profiles[:2]:
        assert ("존댓말" if expected == "POLITE" else "반말") in p["addresseeStance"]
        assert ("반말" if expected == "POLITE" else "존댓말") not in p["addresseeStance"]
    if expected == "POLITE":
        assert "상대가 동의하면" in profiles[2]["addresseeStance"]


def test_sheet_fallback_and_explicit_chapter_switch():
    from character_factory_poc.stages.export.doki_app.chat_svc import (
        _chapter_speech,
        _persona_speech_level,
    )

    sheet = {"card": {"dialogueHabits": {"lexicon": "기본 말투는 반말이다."}}}
    prompt = "[PERSONA / VOICE]\n짧게 답한다.\n말투 예시: 존댓말로 할까요?\n\n[OUTPUT]\n"
    assert _persona_speech_level(prompt, sheet) == "CASUAL"
    assert _persona_speech_level("[PERSONA / VOICE]\n존댓말 대신 반말을 쓴다.", {}) == "CASUAL"
    assert _persona_speech_level("[PERSONA / VOICE]\n반말은 쓰지 않는다.", {}) == "POLITE"
    assert _chapter_speech("서로 말을 놓는다.", "POLITE")[0] == "CASUAL"
    assert _chapter_speech("말을 놓을지 물어본다.", "POLITE")[0] == "POLITE"
