"""S2 오프라인 흐름: G1에서 고른 얼굴 → picked 기준 이미지·외모 명세 자동 고정 (D-0042, D-0043)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.cli import main
from character_factory_poc.common.errors import FactoryError, GateNotApprovedError
from character_factory_poc.common.names import find_name_leaks
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.fake_image import FakeImageModel
from character_factory_poc.stages.s1_reference.approve import selected_face, selected_references
from character_factory_poc.stages.s1_reference.ranking import all_names, load_ranking
from character_factory_poc.stages.s1_reference.run import run_s1
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s2_hero.run import run_s2
from character_factory_poc.stages.s3_plan.common import new_character
from tests.support.synthetic import RANKING, scout_features

NAMES = all_names(load_ranking(RANKING))
PICKED = '[stages.s2]\nbase_photo = "picked"\n'


def _ctx(root: Path, extra: str = PICKED) -> Context:
    if extra:
        (root / "factory.toml").write_text(extra, encoding="utf-8")
    c = Context.load(root, execute=True)
    text = FakeTextModel()
    text.add("AGENT", lambda req: scout_features(RANKING))
    c.use_models(text)
    c.use_image(FakeImageModel())
    return c


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return _ctx(tmp_path)


def _through_g1(ctx: Context, face: str = "c2-1", slug: str = "hero") -> str:
    cid = new_character(ctx, slug)
    run_s1(ctx, cid, RANKING)
    approve_gate(
        ctx,
        cid,
        "G1",
        {
            "decision": "SELECT",
            "selections": ["c2"],
            "referencePreviews": [face],
            "reviewer": "u",
        },
    )
    return cid


def test_picked_fixes_g1_face_without_image_calls(ctx):
    image = FakeImageModel()
    ctx.use_image(image)
    cid = _through_g1(ctx)
    image.requests.clear()  # S1 미리보기 호출은 세지 않는다
    out = run_s2(ctx, cid)
    st = ctx.state(cid)

    # 사람 관문 없이 APPROVED. G2 기록은 만들지 않는다.
    assert out.name == "ar1" and st.stage("s2").status == "APPROVED"
    assert st.gate("G2").status == "PENDING"
    assert image.requests == []
    assert not (out / "candidates.json").exists() and not (out / "gate-G2.html").exists()

    spec, img = load_appearance_spec(ctx, cid)
    assert spec.appearanceRev == "ar1" and spec.sourceReferenceRev == "rf1"
    assert spec.basePhoto == "picked" and spec.identityCheck.status == "SKIPPED"
    assert spec.identityCheck.attempts == 0 and spec.identityCheck.rubric == "identity-v1"
    assert spec.referenceImage.id == "c2-1" and img == out / "references" / "c2-1.png"
    assert [r.id for r in spec.referencePreviews] == ["c2-1"]
    preview = ctx.character_dir(cid) / "s1-reference" / "rf1" / "previews" / "c2-1.png"
    assert img.read_bytes() == preview.read_bytes()

    # 외형 태그는 빼고 스타일링·분위기만, 손은 얼굴에서 뗀다(D-0027, D-0043).
    assert "Appearance:" not in spec.heroPrompt and "Mood: innocent" in spec.heroPrompt
    assert "hands away from the face" in spec.heroPrompt
    assert spec.scope.appearanceOrigin == "korean" and spec.tags["mood"] == ["innocent"]
    assert "청순" in spec.descriptionKo and "innocent" in spec.descriptionEn
    assert find_name_leaks(spec.model_dump_json(), NAMES) == []

    inputs = json.loads((out / "inputs.json").read_text("utf-8"))
    assert inputs["basePhoto"] == "picked" and len(inputs["referencePreviews"]) == 1
    assert find_name_leaks((out / "inputs.json").read_text("utf-8"), NAMES) == []
    assert main(["--root", str(ctx.config.root), "verify", cid]) == 0


def test_s2_requires_g1(ctx):
    cid = new_character(ctx, "nog1")
    with pytest.raises(GateNotApprovedError):
        run_s2(ctx, cid)


def test_s2_requires_exactly_one_face(ctx):
    """옛 G1 기록(참조 사진 0~2장)을 그대로 읽을 수는 있지만 S2는 한 장만 받는다."""
    cid = _through_g1(ctx)
    assert len(selected_references(ctx, cid)) == 1
    assert selected_face(ctx, cid)[0].previewId == "c2-1"

    stale = _through_g1(ctx, face="c2-1", slug="stale")
    state = ctx.state(stale)
    rec = json.loads((ctx.character_dir(stale) / state.gate("G1").recordRef).read_text("utf-8"))
    rec["selections"] = ["c2", "c2-1", "c2-9"]
    (ctx.character_dir(stale) / state.gate("G1").recordRef).write_text(
        json.dumps(rec, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(FactoryError, match="미리보기에 없다"):
        run_s2(ctx, stale)
    rec["selections"] = ["c2", "c2-1", "c2-1"]
    (ctx.character_dir(stale) / state.gate("G1").recordRef).write_text(
        json.dumps(rec, ensure_ascii=False), encoding="utf-8"
    )
    with pytest.raises(FactoryError, match="정확히 한 장"):
        run_s2(ctx, stale)
    assert ctx.state(stale).stage("s2").status == "PENDING"


def test_s2_rerun_makes_new_appearance_rev(ctx):
    cid = _through_g1(ctx)
    assert run_s2(ctx, cid).name == "ar1"
    assert run_s2(ctx, cid).name == "ar2"
    spec, _ = load_appearance_spec(ctx, cid)
    assert spec.appearanceRev == "ar2"


def test_hero_dry_run_is_zero_calls(ctx, capsys):
    cid = _through_g1(ctx)
    assert main(["--root", str(ctx.config.root), "hero", "run", cid]) == 0
    out = capsys.readouterr().out
    assert "picked" in out and "합계 0회" in out
    assert not (ctx.character_dir(cid) / "s2-hero").exists()
