"""Opt-in SOURCE Lite reference masters, using synthetic photos and fake providers only."""

import json
from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from character_factory_poc.common.errors import BudgetExceeded, CheckFailed, GateNotApprovedError
from character_factory_poc.common.store import read_json, verify_manifest
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.origin import (
    graph_for_dir,
    read_reference_image,
    write_reference_image,
    write_video_tier,
)
from character_factory_poc.providers.fake_image import FakeImageModel
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s2_hero.twin import run_s2_twin
from character_factory_poc.stages.s4_frames.approve import load_approved_frames, load_frames
from character_factory_poc.stages.s4_frames.reference import matches_reference_inputs
from character_factory_poc.stages.s4_frames.run import run_s4
from tests.support.flow import approve_plan_v2
from tests.test_twin_s2 import APPROVE, CID, _source
from tests.test_twin_s2 import ctx as source_ctx  # noqa: F401


@pytest.fixture
def ready(request, tmp_path):
    ctx = request.getfixturevalue("source_ctx")
    _source(ctx, tmp_path)
    run_s2_twin(ctx, CID)
    approve_gate(ctx, CID, "G1s", APPROVE)
    approve_plan_v2(ctx, CID)
    folder = ctx.character_dir(CID)
    write_video_tier(folder, "light")
    write_reference_image(folder, {"wardrobe": "", "background": ""})
    image = FakeImageModel()
    ctx.use_image(image)
    return ctx, CID, image


def test_settings_preserve_other_video_fields_and_blank_opt_in(tmp_path):
    settings = {
        "videoTier": "light",
        "signature": {"title": "wave"},
        "videoScene": {"language": "Korean"},
    }
    (tmp_path / "video-settings.json").write_text(json.dumps(settings))
    assert read_reference_image(tmp_path) is None
    write_reference_image(tmp_path, {"wardrobe": "  ", "background": " green wall "})
    assert read_reference_image(tmp_path) == {"wardrobe": "", "background": "green wall"}
    assert read_json(tmp_path / "video-settings.json") == settings | {
        "referenceImage": {"wardrobe": "", "background": "green wall"}
    }
    write_reference_image(tmp_path, {})
    assert read_reference_image(tmp_path) == {"wardrobe": "", "background": ""}


def test_graph_is_opt_in_source_lite_and_does_not_mutate_legacy(ready):
    ctx, cid, _ = ready
    folder = ctx.character_dir(cid)
    graph = graph_for_dir(folder)
    assert "s4a" not in graph and "s4b" not in graph
    assert graph["s4"].deps == frozenset({"G3", "G1s"})
    assert graph["s6"].deps == frozenset({"G4"})
    for tier in ("none", "standard", "pro", "max"):
        write_video_tier(folder, tier)
        assert graph_for_dir(folder)["s4"].deps == frozenset({"G4b"})
    write_video_tier(folder, "light")
    data = read_json(folder / "video-settings.json")
    del data["referenceImage"]
    (folder / "video-settings.json").write_text(json.dumps(data))
    assert "s4a" in graph_for_dir(folder)
    original = folder.parent / "original"
    original.mkdir()
    write_video_tier(original, "light")
    write_reference_image(original, {})
    assert graph_for_dir(original)["s4"].deps == frozenset({"G4b"})


def test_one_full_photo_generation_frozen_inputs_and_human_gate(ready, monkeypatch):
    ctx, cid, image = ready
    # QA settings must not multiply calls or manufacture a visual-quality approval.
    ctx.config.stages["image_qa"] = {"enabled": True}
    monkeypatch.setattr(
        "character_factory_poc.stages.s4_frames.run.crop_face",
        lambda *a, **k: pytest.fail("reference master must use the full photo"),
    )
    appearance, source = load_appearance_spec(ctx, cid)
    folder = run_s4(ctx, cid)
    assert len(image.requests) == 1
    request = image.requests[0]
    assert len(request.reference_images) == 1
    assert Path(request.reference_images[0]).read_bytes() == source.read_bytes()
    inputs = read_json(folder / "inputs.json")
    assert inputs["schemaVersion"] == "reference-image-inputs-v1"
    assert inputs["appearanceRev"] == appearance.appearanceRev
    assert inputs["planRev"] == "pr1"
    assert inputs["sourceSha256"] == appearance.referenceImage.sha256
    assert inputs["wardrobe"] == inputs["background"] == ""
    assert inputs["prompt"] == request.prompt
    assert "hands clasped behind" in request.prompt
    assert "facing the camera" in request.prompt
    assert "slight closed-mouth smile" in request.prompt
    assert "Preserve the exact wardrobe" in request.prompt
    assert "Preserve the exact background" in request.prompt
    assert "책방" not in request.prompt  # Approved plan supplies lineage only.
    assert not (folder / "scene-plan.json").exists()
    assert not (folder / "plates").exists()
    frames = load_frames(folder)
    assert len(frames) == 1 and frames[0].frameId == "ch1-f1"
    assert frames[0].qa is None
    output = cv2.imread(str(folder / frames[0].filePath))
    assert output.shape[1] * 16 == output.shape[0] * 9
    assert (folder / "gate-G4.html").exists()
    assert verify_manifest(folder) == []
    assert matches_reference_inputs(ctx, cid, folder.name)
    assert ctx.state(cid).stage("s4").status == "AWAITING_HUMAN"
    assert ctx.state(cid).gate("G4").status == "AWAITING_HUMAN"
    with pytest.raises(GateNotApprovedError, match="G4"):
        ctx.state(cid).require_deps("s6")
    approve_gate(ctx, cid, "G4", APPROVE)
    approved, approved_dir = load_approved_frames(ctx, cid)
    assert approved_dir == folder and [f.frameId for f in approved.frames] == ["ch1-f1"]
    ctx.state(cid).require_deps("s6")


def test_settings_changes_create_immutable_revisions(ready):
    ctx, cid, image = ready
    first = run_s4(ctx, cid)
    before = {p.relative_to(first): p.read_bytes() for p in first.rglob("*") if p.is_file()}
    approve_gate(ctx, cid, "G4", {"decision": "REJECT", "reviewer": "test"})
    write_reference_image(
        ctx.character_dir(cid), {"wardrobe": "navy suit", "background": "green wall"}
    )
    assert not matches_reference_inputs(ctx, cid, first.name)
    second = run_s4(ctx, cid)
    assert first.name == "fr1" and second.name == "fr2"
    prompt = image.requests[-1].prompt
    assert "navy suit" in prompt and "green wall" in prompt
    # Rejecting G4 may refresh its manifest; generation must preserve the old assets.
    assert all(
        (first / path).read_bytes() == data
        for path, data in before.items()
        if path.name != "manifest.sha256"
    )
    assert matches_reference_inputs(ctx, cid, second.name)
    appearance, source = load_appearance_spec(ctx, cid)
    source.write_bytes(source.read_bytes() + b"tampered")
    assert not matches_reference_inputs(ctx, cid, second.name)


@pytest.mark.parametrize("gate", ["G1s", "G3"])
def test_both_source_photo_and_plan_approval_required(ready, gate):
    ctx, cid, image = ready
    ctx.state(cid).set_gate(gate, "AWAITING_HUMAN", "ar1" if gate == "G1s" else "pr1", None)
    with pytest.raises(GateNotApprovedError, match=gate):
        run_s4(ctx, cid)
    assert not image.requests
    assert not (ctx.character_dir(cid) / "s4-frames").exists()


def test_budget_preflight_prevents_revision_and_call(ready):
    ctx, cid, image = ready
    ctx.max_calls = 0
    with pytest.raises(BudgetExceeded):
        run_s4(ctx, cid)
    assert not image.requests
    assert not (ctx.character_dir(cid) / "s4-frames").exists()
    assert ctx.state(cid).stage("s4").status == "PENDING"


def test_invalid_generated_image_marks_check_failed(ready):
    ctx, cid, image = ready
    generate = image.generate
    image.generate = lambda req: replace(generate(req), data=b"not an image")
    with pytest.raises(CheckFailed):
        run_s4(ctx, cid)
    assert len(image.requests) == 1
    assert ctx.state(cid).stage("s4").status == "CHECK_FAILED"
    assert ctx.state(cid).gate("G4").status == "PENDING"


def test_source_hash_mismatch_fails_without_generation(ready):
    ctx, cid, image = ready
    _, source = load_appearance_spec(ctx, cid)
    source.write_bytes(source.read_bytes() + b"changed")
    with pytest.raises(CheckFailed, match="해시"):
        run_s4(ctx, cid)
    assert not image.requests
    assert ctx.state(cid).stage("s4").status == "CHECK_FAILED"
    assert ctx.state(cid).gate("G4").status == "PENDING"


def test_reuse_rejects_changed_plan_or_frozen_reference(ready):
    ctx, cid, _ = ready
    folder = run_s4(ctx, cid)
    assert not matches_reference_inputs(ctx, cid, None)
    assert not matches_reference_inputs(ctx, cid, "../fr1")
    assert not matches_reference_inputs(ctx, cid, "fr999")
    source = folder / "reference/source.png"
    original = source.read_bytes()
    source.write_bytes(original + b"changed")
    assert not matches_reference_inputs(ctx, cid, folder.name)
    source.write_bytes(original)
    assert matches_reference_inputs(ctx, cid, folder.name)
    approve_plan_v2(ctx, cid)
    assert not matches_reference_inputs(ctx, cid, folder.name)
