"""evidence-v10: each section searches its own candidates, short sections get one top-up.

Synthetic data only; no paid calls and no real chat text.
"""

import json

import pytest

from character_factory_poc.stages.s8_prompts import evidence_pipeline as pipeline
from character_factory_poc.stages.s8_prompts import evidence_sections as v10
from tests.test_evidence_v7_compact import claim


def sectioned_fake(calls):
    def fake(req):
        data = json.loads(req.messages[1].content)
        if data.get("phase") in ("tendency-audit", "tendency-confirm"):
            codes = [c["n"] + "S" for c in data["claims"]]
            rows, prev = [], None
            for line in data["chunk"]["lines"].split("\n"):
                if line.startswith("## "):
                    prev = None
                    continue
                tid, role, _ = line.split(" ", 2)
                if role == "S" and prev == "U":
                    rows.append([tid, *codes])
                prev = role
            return {"labels": rows}
        calls.append(data)
        evidence = sorted(
            {r for o in data["observations"] for c in o["claims"] for r in c["evidence"]}
        )
        base = {k: v for k, v in claim().items() if k != "id"}
        round_no = len(calls)
        out = [
            dict(base, section=s, evidence=evidence, function=f"{s} 기능 {round_no}")
            for s in data["sectionQuota"]
        ]
        for c in out:
            if c["section"] == "LIFE_AND_TASTES":
                c["statedFacts"] = [f"쉬는 날에는 집에서 쉰다고 말했다 {round_no}"]
            if c["section"] == "READING_AND_TENSION":
                c["function"] = f"오해 바로잡기 {round_no}"
            if c["section"] == "CHOICES" and round_no == 2:
                c["trigger"] = "상대가 음식, 옷, 게임, 또는 여행을 말할 때"
        # One more than the quota allows for DISPOSITION in round 1: must be set aside.
        if round_no == 1:
            out += [
                dict(base, section="DISPOSITION", evidence=evidence, function=f"추가 {i}")
                for i in range(data["sectionQuota"]["DISPOSITION"])
            ]
        return {"claims": out}

    return fake


def test_sections_follow_quota_top_up_once_and_record_shortfalls(tmp_path, monkeypatch):
    from character_factory_poc.common.store import read_json
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES
    from tests.test_evidence_pipeline import ready

    ctx, model, cid = ready(tmp_path)
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v10"

    def seed(ctx, cid, dev):
        ids = dev[0]["recordIds"][:3]
        notes = [dict(description="짧게 되묻는다", dimension="behavior", evidence=ids)]
        return [dict(chunkId="s3-test", claims=notes, model=None, heldClaims=[])]

    monkeypatch.setattr(v10, "s3_observations", seed)
    calls = []
    model.add("AGENT", sectioned_fake(calls))
    planned = pipeline.full_plan(ctx, cid)[0].calls - ATOMIC_RETRIES
    before = len(model.requests)
    folder = run_s8(ctx, cid, [])
    sent = [r for r in model.requests[before:] if "/tendency-" in (r.ref or "")]
    assert len(sent) <= planned

    # Round 1 asks every section with its candidate quota; round 2 only the short ones.
    assert calls[0]["sectionQuota"] == {s: n for s, (_, n, _) in v10.SECTION_PLAN.items()}
    assert calls[0]["existingClaims"] == []
    short = calls[1]["sectionQuota"]
    # DISPOSITION reached its target of 4 in round 1, so it is not searched again.
    assert len(calls) == 2 and set(short) == set(v10.SECTION_PLAN) - {"DISPOSITION"}
    assert short["VOICE"] == 8 and short["KNOWS_AND_LIMITS"] == 3  # min(candidates, need + 2)
    assert len(calls[1]["existingClaims"]) == 12

    report = read_json(folder / "evidence-section-coverage.json")
    assert [x["claim"]["function"] for x in report["excluded"]] == ["추가 5"]
    cov = report["coverage"]
    assert cov["DISPOSITION"] == dict(
        target=4, measuredLines=0, retained=6, status="ok", lengthTrimmed=0
    )
    others = {"DISPOSITION", "CHOICES"}
    assert all(c["retained"] == 2 for s, c in cov.items() if s not in others)
    assert cov["READING_AND_TENSION"]["status"] == "ok"
    # The round-2 CHOICES candidate lists four topics as its condition: held, not used.
    assert cov["CHOICES"] == dict(
        target=3, measuredLines=0, retained=1, status="short", lengthTrimmed=0
    )

    review = pipeline.verify_review(ctx, cid, folder)
    assert review["schemaVersion"] == "evidence-review-v10"
    assert review["sectionCoverage"] == cov and len(review["cards"]) == 17
    topic = [h for h in review["held"] if h["claim"]["section"] == "CHOICES"]
    assert topic and topic[0]["reason"].startswith("적용 상황이 화제 나열이다(4개 항목)")
    # Self-reported facts leave the cards and join [FACTS]; correction cards get the fixed limit.
    stated = [f["text"] for f in review["statedFacts"]]
    assert stated == ["쉬는 날에는 집에서 쉰다고 말했다 1", "쉬는 날에는 집에서 쉰다고 말했다 2"]
    long_text = (folder / "long.md").read_text("utf-8")
    facts = long_text.split("\n[FACTS]\n")[1].split("\n[LIFE_AND_TASTES]\n")[0]
    assert all(s in facts for s in stated)
    reading = [c for c in review["cards"] if c["section"] == "READING_AND_TENSION"]
    assert reading and all(v10.CORRECTION_LIMIT in c["limit"] for c in reading)
    assert read_json(folder / "evidence-binding.json")["compiler"] == "evidence-pipeline-v10"
    assert read_json(folder / "evidence-binding.json")["voiceStyle"] == "named-habits-v1"


def test_section_rules_differ_by_source_shape():
    assert v10.section_rule("VOICE", "conversation")["minUnits"] == 8
    assert v10.section_rule("LIFE_AND_TASTES", "conversation")["kind"] == "self_report"
    assert v10.section_rule("CHOICES", "interview") == dict(
        section="CHOICES", kind="behavior", minUnits=3, minShare=0.2
    )
    assert v10.section_rule("WANTS_AND_FEARS", "interview")["minUnits"] == 2


def test_length_limit_keeps_targets_and_trims_extras_round_robin(monkeypatch):
    monkeypatch.setattr(v10, "compile_prompt", lambda p: "x" * (100 * len(p["sections"])))

    def cards(section, n):
        return [dict(card=f"{section}-{i}", claim=dict(section=section)) for i in range(n)]

    ranked = {s: [] for s in v10.SECTION_PLAN}
    ranked["VOICE"], ranked["DISPOSITION"] = cards("VOICE", 4), cards("DISPOSITION", 6)
    targets = {s: 0 for s in v10.SECTION_PLAN} | {"DISPOSITION": 4}
    chosen, trimmed = v10.fit_length({}, ranked, targets, limit=700)
    # 4 target cards (never trimmed) + 3 extras, alternating VOICE and DISPOSITION.
    assert [x["card"] for x in chosen["DISPOSITION"]] == [f"DISPOSITION-{i}" for i in range(5)]
    assert [x["card"] for x in chosen["VOICE"]] == ["VOICE-0", "VOICE-1"]
    assert [x["card"] for x in trimmed] == ["DISPOSITION-5", "VOICE-2", "VOICE-3"]


def test_named_habit_style_states_words_and_rates_without_upper_bounds():
    from character_factory_poc.stages.s8_prompts import evidence_compiler as compiler
    from character_factory_poc.stages.s8_prompts.evidence_voice import (
        HABITS_STYLE,
        measured_voice_lines,
    )
    from tests.test_evidence_voice_and_retention import profile

    p = profile()
    p["casual"]["markerCounts"] = {"진짜": 130, "좀": 111, "뭐": 100, "되게": 62, "또": 300}
    old, new = measured_voice_lines(p), measured_voice_lines(p, HABITS_STYLE)
    for n, line in enumerate(new):
        compiler._text(line, f"voice[{n}]")
    habit = next(line for line in new if line.startswith("말버릇:"))
    assert "자주 섞어" in habit and "진짜·좀·뭐·되게" in habit and "또" not in habit
    assert "40~150자 답에는 군말이 답당 약 1.1개" in habit
    text = "\n".join(new)
    assert "넘기지 않는다" not in text and "에만 나오고" not in text
    assert old == measured_voice_lines(p, None)  # reviewed packets keep their wording

    p["casual"].update(habitShare=0.02, fillerByLength={}, fillerPer100Chars=0.4)
    rare = next(line for line in measured_voice_lines(p, HABITS_STYLE) if "말버릇" in line)
    assert rare.startswith("말버릇: 정도부사와 군말은 드물다.")


def test_hedged_call_uses_the_faster_duplicate_and_keeps_the_slow_one_running():
    import threading
    import time

    from character_factory_poc.providers.base import ChatRequest, ChatResponse, Message
    from character_factory_poc.providers.hedged import HedgedTextModel

    finished = []

    class Slow:
        name, model = "fake", "fake"

        def complete(self, req):
            time.sleep(0.4 if not req.ref.endswith("-hedge") else 0)
            finished.append(req.ref)
            return ChatResponse(
                text=req.ref,
                input_tokens=1,
                output_tokens=1,
                elapsed_ms=1,
                model="fake",
                provider="fake",
            )

    notes = []
    req = ChatRequest(kind="AGENT", stage="s8", ref="r", messages=(Message("user", "x"),))
    out = HedgedTextModel(Slow(), 0.05, lambda ref, s: notes.append(ref)).complete(req)
    assert out.text == "r-hedge" and notes == ["r"]
    for t in threading.enumerate():
        if t is not threading.current_thread() and not t.daemon:
            t.join(2)
    assert finished == ["r-hedge", "r"]  # the slow call still completes (and is billed)
    assert HedgedTextModel(Slow(), 0, None).complete(req).text == "r"


def test_self_report_share_is_twenty_percent():
    assert v10.section_rule("LIFE_AND_TASTES", "conversation")["minShare"] == 0.2
    assert v10.section_rule("WANTS_AND_FEARS", "interview")["minShare"] == 0.2


@pytest.mark.text_default
def test_default_is_v10_when_s3_scene_analysis_exists_else_v4(tmp_path):
    import shutil

    from tests.test_evidence_pipeline import ready

    ctx, _, cid = ready(tmp_path)
    ctx.config.stages["s8"].pop("motif_compiler", None)
    rev = ctx.state(cid).gate("G3").rev
    folder = ctx.character_dir(cid) / "s3-plan" / str(rev) / "scene-analysis"
    shutil.rmtree(folder, ignore_errors=True)  # a plan made before S3 scene analysis
    value, note = pipeline.configured_compiler(ctx, cid)
    assert (value, bool(note)) == ("evidence-v4", True)
    assert pipeline.version_for(ctx, cid) != v10.SECTIONED_VERSION
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("voice", "behavior", "facts-limits"):
        (folder / f"{name}.json").write_text("{}", encoding="utf-8")
    assert pipeline.configured_compiler(ctx, cid) == ("evidence-v10", None)
    assert pipeline.version_for(ctx, cid) == v10.SECTIONED_VERSION
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v4"  # explicit setting always wins
    assert pipeline.configured_compiler(ctx, cid) == ("evidence-v4", None)
