"""evidence-v8: S3 whole-source observations seed consolidation; the analyzer audits each half.

Synthetic data only; no paid calls and no real chat text.
"""

import json
from types import SimpleNamespace

import pytest

from character_factory_poc.stages.s8_prompts import evidence_pipeline as pipeline
from character_factory_poc.stages.s8_prompts import evidence_tendencies as m
from tests.test_evidence_v7_compact import claim, compact_fake


def seeded_fake(req):
    data = json.loads(req.messages[1].content)
    if data.get("phase") == "tendency-consolidate":
        # v8 consolidation reads the S3 notes and the development text together.
        assert data["chunk"]["lines"] and data["observations"]
        evidence = sorted(
            {r for o in data["observations"] for c in o["claims"] for r in c["evidence"]}
        )
        c = {k: v for k, v in claim().items() if k != "id"}
        c["evidence"] = evidence
        return {"claims": [c]}
    return compact_fake(req)


def test_s3_observations_keep_only_development_evidence(tmp_path):
    folder = tmp_path / "cid" / "s3-plan" / "pr1" / "scene-analysis"
    folder.mkdir(parents=True)
    for dim in ("voice", "behavior", "facts-limits"):
        obs = [dict(description=f"{dim} 관찰", dimension=dim, evidence=["a", "z"])]
        (folder / f"{dim}.json").write_text(json.dumps(dict(observations=obs, ref="r")))
    ctx = SimpleNamespace(
        state=lambda cid: SimpleNamespace(gate=lambda g: SimpleNamespace(rev="pr1")),
        character_dir=lambda cid: tmp_path / cid,
    )
    out = m.s3_observations(ctx, "cid", [dict(recordIds=["a", "b"])])
    assert [o["chunkId"] for o in out] == ["s3-pr1-voice", "s3-pr1-behavior", "s3-pr1-facts-limits"]
    assert all(c["evidence"] == ["a"] for o in out for c in o["claims"])
    with pytest.raises(ValueError):
        m.s3_observations(ctx, "cid", [dict(recordIds=["q"])])
    (folder / "voice.json").unlink()
    with pytest.raises(ValueError, match="S3"):
        m.s3_observations(ctx, "cid", [dict(recordIds=["a"])])


def test_native_v8_skips_discovery_and_reverifies(tmp_path, monkeypatch):
    from character_factory_poc.common.store import read_json
    from character_factory_poc.stages.s8_prompts.build import run_s8
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES
    from tests.test_evidence_pipeline import ready

    ctx, model, cid = ready(tmp_path)
    ctx.config.stages["s8"]["motif_compiler"] = "evidence-v8"

    def seed(ctx, cid, dev):
        ids = dev[0]["recordIds"][:3]
        notes = [dict(description="짧게 되묻는다", dimension="behavior", evidence=ids)]
        return [dict(chunkId="s3-test", claims=notes, model=None, heldClaims=[])]

    monkeypatch.setattr(m.SeededProfile, "seed", staticmethod(seed))
    model.add("AGENT", seeded_fake)
    planned = pipeline.full_plan(ctx, cid)[0].calls - ATOMIC_RETRIES
    before = len(model.requests)
    folder = run_s8(ctx, cid, [])
    sent = [r for r in model.requests[before:] if "/tendency-" in (r.ref or "")]
    phases = sorted(r.ref.split("/")[2] for r in sent)
    assert phases == ["tendency-audit", "tendency-confirm", "tendency-consolidate"]
    assert 0 < len(sent) <= planned
    split = read_json(folder / "evidence-partition.json")
    assert len(split["developmentChunks"]) == len(split["confirmationChunks"]) == 1
    binding = read_json(folder / "evidence-binding.json")
    assert binding["compiler"] == "evidence-pipeline-v8" and binding["seed"] == "s3-scene-analysis"
    review = pipeline.verify_review(ctx, cid, folder)
    assert review["schemaVersion"] == "evidence-review-v8" and review["cards"]
    assert read_json(folder / "evidence-observations.json")[0]["chunkId"] == "s3-test"
