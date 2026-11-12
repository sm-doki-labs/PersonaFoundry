"""Measured voice is rendered without examples; count caps give way to evidence thresholds."""

import re

import pytest

from character_factory_poc.stages.s8_prompts import evidence_compiler as compiler
from character_factory_poc.stages.s8_prompts import evidence_tendencies as m
from character_factory_poc.stages.s8_prompts.evidence_voice import measured_voice_lines
from tests.test_evidence_tendencies import claim


def profile():
    bucket = dict(
        answers=dict(
            count=200,
            medianChars=33,
            p90Chars=179,
            atMost80Chars=0.77,
            atMostTwoSentences=0.8,
            firstWords={"아": 40, "네": 30, "저는": 30, "제가": 10, "근데": 20},
        ),
        endings=dict(
            haeyo=300,
            jyo=80,
            janayo=40,
            geodeunyo=25,
            neyo=20,
            formal=120,
            hedgeFormal=20,
            hedgePolite=100,
            casual=10,
            plainDa=1,
            open=100,
            other=200,
        ),
        connectors={"는데": 59, "그래서": 34, "기 때문에": 27, "그러다 보니까": 2},
        hedgeByLength=dict(
            long=dict(count=79, share=0.68),
            medium=dict(count=197, share=0.26),
            short=dict(count=353, share=0.08),
        ),
        fillerByLength=dict(
            long=dict(count=79, avgPerAnswer=3.5),
            medium=dict(count=197, avgPerAnswer=1.1),
            short=dict(count=353, avgPerAnswer=0.24),
        ),
        fillerPer100Chars=1.26,
        habitWords=["진짜", "그냥", "너무", "정말"],
        habitShare=0.3,
        repeatShare=0.03,
        politeShare=0.98,
        sentences=1000,
        subjectMessages=600,
        longShare=0.1,
    )
    formal = dict(bucket, endings=dict(bucket["endings"], formal=300), longShare=0.42)
    return dict(bucket, casual=bucket, formal=formal, samples=["원문 견본 문장이에요."])


def test_measured_voice_has_numbers_but_no_example_utterances():
    lines = measured_voice_lines(profile())
    for n, line in enumerate(lines):
        compiler._text(line, f"voice[{n}]")  # passes the same example checker as cards
    text = "\n".join(lines)
    for number in ["33자", "77%", "80%", "68%", "1.3", "30%"]:
        assert number in text, number
    assert "'-잖아요'" in text and "'-거든요'" in text and "'-는 것 같다'" in text
    # No sample sentences, interjections or quoted openers become imitation targets.
    assert "원문 견본" not in text and "견본" not in text
    for opener in ["'아'", "'네'", "'저는'"]:
        assert opener not in text
    assert not re.search(r"[\"“][^\"”]{6,}[\"”]", text)


def test_small_profile_renders_nothing():
    p = profile()
    p["casual"]["answers"] = dict(p["casual"]["answers"], count=5)
    assert measured_voice_lines(p) == []


def test_voice_lines_lead_voice_section_and_unobserved_lines_are_dropped():
    card = m.to_card(claim(), ["s1", "s2"], "mixed")
    packet = dict(
        role="역할",
        scene="장면",
        facts="사실",
        trainIds=["s1", "s2"],
        holdoutIds=[],
        formatVersion="evidence-conditions-v3",
        sections=[card],
        voice=["답 길이: 중앙값 33자로 답한다."],
    )
    text = compiler.compile_prompt(packet)
    voice = text.split("[VOICE]\n", 1)[1]
    assert voice.startswith("답 길이: 중앙값 33자로 답한다.")
    assert "독립 근거로 확인하지 않아" not in text
    assert card["trigger"] in text


def test_consolidation_keeps_more_than_twelve_distinct_claims():
    c = {k: v for k, v in claim().items() if k != "id"}
    claims = [dict(c, function=f"기능 {i}") for i in range(20)]
    m.validate_phase("tendency-consolidate", {"claims": claims}, {"allowedIds": ["s1", "s2"]})


def test_confirmation_threshold_is_evidence_based():
    from character_factory_poc.stages.s8_prompts import evidence_measured as v6

    dev = dict(support=["s1", "s2"], supportUnits=3, variation=[], outside=[], unclear=[])
    need = v6.MIN_CONFIRMATION_SUPPORT
    assert need == 3
    assert m.state_for(dev, dict(dev, supportUnits=2), need) == "insufficient"
    assert m.state_for(dev, dict(dev, supportUnits=3), need) == "evidence_present"
    # v4 as approved for pv6 is unchanged.
    assert m.state_for(dev, dict(dev, supportUnits=1)) == "evidence_present"
    with pytest.raises(ValueError):
        m.state_for(dev, dev, min_confirm=0)


def test_v4_packets_render_exactly_as_before():
    card = m.to_card(claim(), ["s1", "s2"], "mixed")
    packet = dict(
        role="역할",
        scene="장면",
        facts="사실",
        trainIds=["s1", "s2"],
        holdoutIds=[],
        formatVersion="evidence-conditions-v2",
        sections=[card],
    )
    text = compiler.compile_prompt(packet)
    for key in ["trigger", "first", "shift", "stop", "limit"]:
        assert card[key] in text
    with pytest.raises(ValueError):
        compiler.compile_prompt(packet | {"voice": ["답 길이: 33자"]})


def test_native_v6_keeps_every_supported_claim_and_records_threshold(tmp_path, monkeypatch):
    from character_factory_poc.common.demo_chat import Scene
    from character_factory_poc.stages.s8_prompts import evidence_measured as v6
    from character_factory_poc.stages.s8_prompts import evidence_pipeline as pipeline
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from tests.test_evidence_pipeline import ready

    ctx, _, cid = ready(tmp_path)
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v6"
    # The synthetic corpus has few confirmation units; the configured override is recorded.
    ctx.config.stages["s8"]["min_confirmation_support"] = 1
    base = {k: v for k, v in claim().items() if k != "id"}

    def fake(ctx, cid, folder, budget, phase, key, p):
        assert phase != "tendency-consolidate"  # v6 merges in code, not with a model call
        if phase == "tendency-discover":
            claims = [
                dict(base, dimension="response", function=f"기능 {i}", evidence=p["allowedIds"][:2])
                for i in range(10)
            ]
            return {"claims": claims}, "f"
        audited.append((phase, key, len(p["claims"])))
        ts = {t["id"]: t for seg in p["chunk"]["segments"] for t in seg["turns"]}
        findings = []
        for c in p["claims"]:
            weak = c["function"] == "기능 0" and phase == "tendency-confirm"
            items = []
            for rid, t in p["targets"].items():
                uid = t["precedingUserIds"][-1]
                items.append(
                    dict(
                        responseTurnId=rid,
                        conditionTurnId=uid,
                        conditionQuote=ts[uid]["text"],
                        responseQuote=ts[rid]["text"],
                        applicability="no" if weak else "yes",
                        functionMatch="present",
                        formMatch="present",
                        reason="합성 검증",
                    )
                )
            findings.append(dict(claimId=c["id"], items=items, note="합성"))
        out = {"findings": findings}
        m.validate_phase(phase, out, p)
        return out, "f"

    audited = []
    monkeypatch.setattr(v6, "call", fake)
    monkeypatch.setattr(v6, "AUDIT_BATCH", 4)
    folder = run_s8(ctx, cid, [])
    # 10 claims are checked in groups of 4, 4 and 2 for every chunk.
    assert sorted({n for _, _, n in audited}) == [2, 4]
    assert any(key.endswith("-g03") for _, key, _ in audited)
    review = pipeline.verify_review(ctx, cid, folder)
    assert review["schemaVersion"] == "evidence-review-v6"
    decisions = __import__("json").loads((folder / "evidence-tendency-decisions.json").read_text())
    assert len(decisions) == 10
    supported = [d for d in decisions if d["retained"]]
    weak = [d for d in decisions if d["claim"]["function"] == "기능 0"]
    assert len(weak) == 1 and not weak[0]["retained"]
    assert any("확인용 원문" in h["reason"] for h in review["held"])
    assert review["retentionRule"]["minConfirmationSupport"] == 1
    assert v6.MIN_CONFIRMATION_SUPPORT == 3
    assert len(review["cards"]) == len(supported)
    text = (folder / "long.md").read_text()
    assert "독립 근거로 확인하지 않아" not in text
    assert Scene.read(ctx.character_dir(cid), review_preview=True).compose()


def test_dedupe_forms_keeps_best_supported_card_per_form():
    from character_factory_poc.stages.s8_prompts import evidence_measured as m

    def card(first, n):
        return dict(first=first, shift="", stop="", evidence=[f"e{i}" for i in range(n)])

    weak = card("'-ㄴ 것 같다' 구성으로 완곡하게 진술한다.", 2)
    strong = card("'-서' 연결 뒤 '-는 것 같다' 구성으로 결론을 맺는다.", 5)
    polite = card("'-어요/-아요' 종결어미로 맺는다.", 1)
    polite_again = card("강조 부사와 '-어요' 종결어미를 쓴다.", 1)
    plain = card("긍정 응답 표지로 시작한다.", 1)
    kept, dropped = m.dedupe_forms([weak, strong, polite, polite_again, plain])
    assert kept == [strong, polite, plain]
    assert [(c is weak, f) for c, f in dropped][0] == (True, ["-N 것 같다"])
    assert dropped[1] == (polite_again, ["-어요"])


def test_hedge_card_is_scoped_to_long_answers_and_still_compiles():
    from character_factory_poc.stages.s8_prompts import evidence_measured as m

    hedge = dict(
        trigger="상대가 의견을 물을 때",
        first="'-는 것 같다' 구성으로 완화한다.",
        shift="",
        stop="",
        limit="단순 인사",
        evidence=["e1"],
    )
    other = dict(
        trigger="확인 질문",
        first="긍정 응답 표지로 연다.",
        shift="",
        stop="",
        limit="",
        evidence=["e1"],
    )
    (scoped, same), n = m.scope_cards([hedge, other])
    assert n == 1 and same == other
    assert "두세 문장 이상" in scoped["trigger"] and "짧은 답" in scoped["limit"]


def test_voice_particle_and_filler_forms_have_no_words():
    from character_factory_poc.stages.s8_prompts import evidence_voice as v

    assert v._topic("진짜·정말") == "진짜·정말은" and v._topic("너무") == "너무는"
    forms = v._filler_forms({"어": 30, "이제": 20, "뭐": 10, "그냥": 40}, {"그냥"})
    labels = [label for label, _ in forms]
    assert labels[0].endswith("망설임 간투사") and len(labels) == 3
    for label in labels:
        assert not any(w in label.split() for w in ("어", "이제", "뭐", "그냥"))
