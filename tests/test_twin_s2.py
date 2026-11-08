"""실제 사진 대신 단색 배열로 만든 JPEG/PNG와 가짜 비전 공급자만 사용한다."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import (
    CheckFailed,
    FactoryError,
    GateNotApprovedError,
    NeedsInputError,
)
from character_factory_poc.common.store import read_json, verify_manifest
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.fake_image import FakeImageModel
from character_factory_poc.providers.fake_video import FakeVideoModel
from character_factory_poc.providers.fake_vision import FakeVisionModel
from character_factory_poc.stages.s0_source.run import run_s0
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec, load_inputs
from character_factory_poc.stages.s2_hero.twin import approve_g1s, run_s2_twin
from character_factory_poc.stages.s3_plan.common import appearance_input
from character_factory_poc.stages.s5_intro.run import run_s5
from tests.test_source_s0 import _good_digest, _twin, _write_pack

CID = "cf-20261108-twin"
APPROVE = {"decision": "APPROVE", "reviewer": "u"}


@pytest.fixture
def ctx(tmp_path):
    (tmp_path / "factory.toml").write_text('[stages.s5]\nfirst_frame = "hero"\n')
    c = Context.load(tmp_path, execute=True)
    text = FakeTextModel()
    text.add("AGENT", _good_digest)
    c.use_models(text)
    c.use_video(FakeVideoModel())
    c.use_vision(FakeVisionModel(responder=lambda req: {"faceShape": "oval"}))
    _twin(c, CID)
    return c


def _source(ctx, tmp, count=2, approve=True):
    import json

    path = _write_pack(tmp)
    pack = read_json(path)
    pack["photos"] = []
    for i, suffix in enumerate([".jpg", ".png"][:count]):
        src = path.parent / f"private-name-{i}{suffix}"
        ok, encoded = cv2.imencode(suffix, np.full((24, 16, 3), 50 + 80 * i, np.uint8))
        assert ok
        src.write_bytes(encoded.tobytes())
        pack["photos"].append({"path": src.name})
    path.write_text(json.dumps(pack), encoding="utf-8")
    folder = run_s0(ctx, CID, path)
    if approve:
        approve_gate(ctx, CID, "G0", APPROVE)
    return folder


def test_requires_g0_before_any_photo_call(ctx, tmp_path):
    _source(ctx, tmp_path, approve=False)
    with pytest.raises(GateNotApprovedError, match="G0"):
        run_s2_twin(ctx, CID)
    assert not (ctx.character_dir(CID) / "s2-hero").exists()


def test_original_rejected(ctx):
    with pytest.raises(FactoryError, match="모티브"):
        run_s2_twin(ctx, "original")


def test_missing_photos(ctx, tmp_path):
    _source(ctx, tmp_path, count=0)
    with pytest.raises(NeedsInputError):
        run_s2_twin(ctx, CID)


@pytest.mark.parametrize("selected", [0, 1])
def test_gate_publishes_reviewed_photo_and_matching_spec(ctx, tmp_path, monkeypatch, selected):
    s0 = _source(ctx, tmp_path)
    # S0가 끝난 시점부터 비교 세트를 여는 즉시 실패한다.
    original_open = Path.open

    def guarded(path, *args, **kwargs):
        assert path != s0 / "holdout.jsonl"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    image = FakeImageModel()
    ctx.use_image(image)

    def describe(req):
        assert len(req.images) == 1
        label, path = req.images[0]
        assert all(s not in req.prompt + label + path for s in ["엄마", "private-name", "밥은"])
        pixels = cv2.imread(path)
        return {"faceShape": "oval" if pixels.mean() < 100 else "round"}

    vision = FakeVisionModel(responder=describe)
    ctx.use_vision(vision)
    folder = run_s2_twin(ctx, CID)
    assert (
        ctx.state(CID).gate("G1s").status == ctx.state(CID).stage("s2").status == "AWAITING_HUMAN"
    )
    assert appearance_input(ctx, CID) is None
    with pytest.raises(GateNotApprovedError):
        load_appearance_spec(ctx, CID)
    page = (folder / "gate-G1s.html").read_text()
    for i, desc in enumerate(["계란형", "둥근형"], 1):
        assert f'src="references/photo{i:03}.png"' in page and desc in page

    photo_id = f"photo{selected + 1:03}"
    answer = {"decision": "SELECT", "selections": [photo_id]} if selected else APPROVE
    assert approve_g1s(ctx, CID, answer) == folder
    assert len(vision.requests) == 2
    assert ctx.state(CID).gate("G1s").status == ctx.state(CID).stage("s2").status == "APPROVED"
    spec, hero = load_appearance_spec(ctx, CID)
    assert spec.referenceImage.id == photo_id
    assert spec.referenceImage.sha256 == sha256_file(hero)
    assert hero.read_bytes().startswith(b"\x89PNG")
    raw = Path(read_json(s0 / "source-index.json")["photos"][selected]["path"])
    assert (folder / "originals" / photo_id).read_bytes() == raw.read_bytes()
    assert np.array_equal(cv2.imread(str(raw)), cv2.imread(str(hero)))
    assert spec.descriptionEn == ["oval face", "round face"][selected]
    assert appearance_input(ctx, CID)["descriptionKo"] == ["계란형", "둥근형"][selected]
    assert load_inputs(folder).referencePreviews == [spec.referenceImage]
    assert verify_manifest(folder) == []
    record = read_json(ctx.character_dir(CID) / "gates" / f"G1s-{folder.name}.json")
    assert record["decision"] == answer["decision"] and record["selections"] == [photo_id]

    out = run_s5(ctx, CID)
    assert (out / "first-frame.png").read_bytes() == hero.read_bytes()
    assert image.requests == []


@pytest.mark.parametrize("decision", ["REQUEST_CHANGES", "REJECT"])
def test_negative_decisions_leave_no_approved_spec(ctx, tmp_path, decision):
    _source(ctx, tmp_path)
    folder = run_s2_twin(ctx, CID)
    for ids in [[], ["photo999"], ["photo001", "photo002"]]:
        with pytest.raises(FactoryError, match="후보 사진"):
            approve_g1s(ctx, CID, {"decision": "SELECT", "selections": ids})
    approve_g1s(ctx, CID, {"decision": decision, "reasons": "사진 다시 확인"})
    assert ctx.state(CID).stage("s2").status == "REJECTED"
    assert not (folder / "appearance-spec.json").exists()
    assert run_s2_twin(ctx, CID).name == "ar2"


def test_g0_hash_and_vision_output_enforced(ctx, tmp_path):
    _source(ctx, tmp_path)
    vision = FakeVisionModel(responder=lambda req: {"faceShape": "실명"})
    ctx.use_vision(vision)
    pic = tmp_path / "src" / "private-name-1.png"
    raw = pic.read_bytes()
    pic.write_bytes(raw + b"changed")
    with pytest.raises(CheckFailed, match="G0"):
        run_s2_twin(ctx, CID)
    assert vision.requests == []
    pic.write_bytes(raw)
    with pytest.raises(CheckFailed, match="외형 태그"):
        run_s2_twin(ctx, CID)
    assert ctx.state(CID).stage("s2").status == "CHECK_FAILED"
    assert ctx.state(CID).gate("G1s").status == "PENDING"


def test_review_cannot_approve_changed_photo_or_superseded_g0(ctx, tmp_path):
    _source(ctx, tmp_path)
    folder = run_s2_twin(ctx, CID)
    photo = folder / "references" / "photo001.png"
    original = photo.read_bytes()
    photo.write_bytes(original + b"changed")
    with pytest.raises(CheckFailed, match="해시 불일치"):
        approve_g1s(ctx, CID, APPROVE)
    photo.write_bytes(original)
    assert _source(ctx, tmp_path).name == "sp2"
    with pytest.raises(FactoryError, match="G0 출처 판"):
        approve_g1s(ctx, CID, APPROVE)
    assert ctx.state(CID).gate("G1s").status == "AWAITING_HUMAN"
    assert not (folder / "appearance-spec.json").exists()
