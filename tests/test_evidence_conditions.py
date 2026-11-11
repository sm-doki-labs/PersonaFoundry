"""Conditions must survive compilation; legacy revisions remain reproducible."""

import pytest

from character_factory_poc.stages.s8_prompts.evidence_compiler import compile_prompt


def packet():
    return dict(
        role="모티브 AI로 답한다.",
        scene="친구끼리 대화한다.",
        facts="개발자",
        trainIds=["a", "b"],
        holdoutIds=[],
        formatVersion="evidence-conditions-v2",
        sections=[
            dict(
                section="VOICE",
                evidence=["a", "b"],
                trigger="친구가 이유를 요청했고 현재 판단에 필요한 조건이 있을 때",
                first="직접적인 판단 근거를 먼저 제시한다.",
                shift="상대가 조건을 더 물으면 필요한 차이를 설명한다.",
                stop="상대가 이해했으면 배경 설명을 반복하지 않는다.",
                limit="단순 확인 질문이나 아직 근거가 부족한 경우에는 적용하지 않는다.",
                rule="짧게 설명한다.",
            )
        ],
    )


def test_v2_keeps_every_condition_even_when_summary_omits_them():
    p = packet()
    text = compile_prompt(p)
    for field in ("trigger", "first", "shift", "stop", "limit"):
        assert p["sections"][0][field] in text
    assert p["sections"][0]["rule"] not in text
    changed = packet()
    changed["sections"][0]["limit"] = "과거 경험이 확인되지 않으면 만들거나 부정하지 않는다."
    assert compile_prompt(changed) != text


def test_old_packet_still_renders_legacy_rule_only():
    p = packet()
    p.pop("formatVersion")
    text = compile_prompt(p)
    assert p["sections"][0]["rule"] in text
    assert p["sections"][0]["limit"] not in text


def test_unknown_render_contract_rejected():
    p = packet()
    p["formatVersion"] = "unknown"
    with pytest.raises(ValueError):
        compile_prompt(p)
