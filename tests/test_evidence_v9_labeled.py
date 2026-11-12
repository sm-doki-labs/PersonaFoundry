"""evidence-v9: S3-seeded candidates, every response labelled once, counted in code.

Synthetic data only; no paid calls and no real chat text.
"""

import json

import pytest

from character_factory_poc.stages.s8_prompts import evidence_pipeline as pipeline
from character_factory_poc.stages.s8_prompts import evidence_tendencies as m
from tests.test_evidence_v7_compact import claim, compact_fake


def labeled_fake(req):
    data = json.loads(req.messages[1].content)
    phase = data.get("phase", "")
    if phase == "tendency-consolidate":
        assert data["chunk"]["lines"] and data["observations"]
        evidence = sorted(
            {r for o in data["observations"] for c in o["claims"] for r in c["evidence"]}
        )
        c = {k: v for k, v in claim().items() if k != "id"}
        c["evidence"] = evidence
        return {"claims": [c]}
    if phase in ("tendency-audit", "tendency-confirm"):
        assert "targets" not in data and data["claims"][0]["n"] == "01"
        rows, prev = [], None
        for line in data["chunk"]["lines"].split("\n"):
            if line.startswith("## "):
                prev = None
                continue
            tid, role, _ = line.split(" ", 2)
            if role == "S" and prev == "U":
                rows.append([tid, "01S"])
            prev = role
        return {"labels": rows}
    return compact_fake(req)


def payload(n=4):
    turns = []
    for i in range(n):
        turns += [
            dict(id=f"u{i}", speaker="USER", text=f"질문 {i}"),
            dict(id=f"s{i}", speaker="SUBJECT", text=f"대답 {i}"),
        ]
    ch = dict(id="dev-0001", segments=[dict(unit=["t", "c1"], turns=turns)], recordIds=[])
    c = dict(claim(), id="tendency-01")
    return dict(chunk=ch, claims=[c], targets=m.targets(ch), role="r", scene="s", facts="f")


def test_labels_become_v4_items_and_bad_rows_are_kept_aside():
    p = payload()
    out = {"labels": [["s1", "01S"], ["s2", "01V"], ["s3", "01U", "01U"], ["nope", "01S"]]}
    found = m.labels_to_findings(out, p)["findings"][0]
    kinds = [(it["responseTurnId"], it["applicability"], it["formMatch"]) for it in found["items"]]
    assert kinds == [
        ("s1", "yes", "present"),
        ("s2", "yes", "absent"),
        ("s3", "unclear", "unclear"),
    ]
    assert all(it["conditionQuote"] and it["responseQuote"] for it in found["items"])
    assert found["invalidItems"][0]["item"] == ["nope", "01S"]
    with pytest.raises(ValueError):
        m.validate_labels({"labels": [["x", "99S"]] * 10}, p)
    with pytest.raises(ValueError):
        m.validate_labels({"rows": []}, p)


def test_support_rule_is_eight_conversations_and_twenty_percent():
    assert m.LabeledProfile.MIN_SUPPORT == dict(conversations=8, share=0.2)
    rule = m.support_rule({}, 100, m.LabeledProfile.MIN_SUPPORT)
    stats = dict(conversations=8, responses=20, applicable=100, share=0.2)
    assert m.thin_support(stats, rule) is None
    assert m.thin_support(dict(stats, responses=19, share=0.19), rule)
    assert m.thin_support(dict(stats, conversations=7), rule)


def test_native_v9_labels_every_response_and_reverifies(tmp_path, monkeypatch):
    from character_factory_poc.common.store import read_json
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES
    from tests.test_evidence_pipeline import ready

    ctx, model, cid = ready(tmp_path)
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v9"

    def seed(ctx, cid, dev):
        ids = dev[0]["recordIds"][:3]
        notes = [dict(description="짧게 되묻는다", dimension="behavior", evidence=ids)]
        return [dict(chunkId="s3-test", claims=notes, model=None, heldClaims=[])]

    monkeypatch.setattr(m.LabeledProfile, "seed", staticmethod(seed))
    model.add("AGENT", labeled_fake)
    planned = pipeline.full_plan(ctx, cid)[0].calls - ATOMIC_RETRIES
    before = len(model.requests)
    folder = run_s8(ctx, cid, [])
    sent = [r for r in model.requests[before:] if "/tendency-" in (r.ref or "")]
    assert sorted(r.ref.split("/")[2] for r in sent) == [
        "tendency-audit",
        "tendency-confirm",
        "tendency-consolidate",
    ]
    assert len(sent) == planned
    binding = read_json(folder / "evidence-binding.json")
    assert binding["compiler"] == "evidence-pipeline-v9"
    review = pipeline.verify_review(ctx, cid, folder)
    assert review["schemaVersion"] == "evidence-review-v9" and review["cards"]
    decision = read_json(folder / "evidence-tendency-decisions.json")[0]
    assert decision["retained"] and decision["support"]["share"] == 1.0
    saved = read_json(folder / "analysis" / "tendency-audit-dev-0001.json")["output"]
    assert set(saved) == {"labels"}
