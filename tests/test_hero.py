"""S2 오프라인 흐름: G1(외모군+참조 사진) → 대표 이미지 후보 → G2 → 외모 명세 (D-0022, D-0023)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import acf.contracts  # noqa: F401
from acf.cli import main
from acf.common.errors import FactoryError, GateNotApprovedError, ImageGenerationError
from acf.common.names import find_name_leaks
from acf.pipeline.approve import approve_gate
from acf.pipeline.context import Context
from acf.pipeline.orchestrator import RunOptions, run_until
from acf.providers.fake import FakeTextModel
from acf.providers.fake_image import FakeImageModel
from acf.stages.s1_reference.approve import selected_references
from acf.stages.s1_reference.ranking import all_names, load_ranking
from acf.stages.s1_reference.run import run_s1
from acf.stages.s2_hero.approve import load_appearance_spec
from acf.stages.s2_hero.run import run_s2
from acf.stages.s3_plan.draft import new_character
from tests.support.synthetic import RANKING, scout_features

NAMES = all_names(load_ranking(RANKING))


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    c = Context.load(tmp_path, execute=True)
    text = FakeTextModel()
    text.add("AGENT", lambda req: scout_features(RANKING))
    c.use_models(text)
    c.use_image(FakeImageModel())
    return c


def _through_g1(ctx: Context, refs: list[str]) -> str:
    cid = new_character(ctx, "hero")
    run_s1(ctx, cid, RANKING)
    approve_gate(
        ctx,
        cid,
        "G1",
        {"decision": "SELECT", "selections": ["c2"], "referencePreviews": refs, "reviewer": "u"},
    )
    return cid


def test_g1_records_reference_previews_and_page_has_checkboxes(ctx):
    cid = _through_g1(ctx, ["c2-1", "c2-3"])
    rec = json.loads((ctx.character_dir(cid) / "gates" / "G1-rf1.json").read_text("utf-8"))
    assert rec["selections"] == ["c2", "c2-1", "c2-3"]
    refs = selected_references(ctx, cid)
    assert [p.previewId for p, _ in refs] == ["c2-1", "c2-3"] and all(f.exists() for _, f in refs)
    page = (ctx.character_dir(cid) / "s1-reference" / "rf1" / "gate-G1.html").read_text("utf-8")
    assert 'name="ref" value="c1-1"' in page and "referencePreviews" in page


@pytest.mark.parametrize(
    "refs, match",
    [(["c1-1"], "미리보기가 아니다"), (["c2-1", "c2-2", "c2-3"], "2장까지")],
)
def test_g1_rejects_bad_reference_previews(ctx, refs, match):
    cid = new_character(ctx, "bad")
    run_s1(ctx, cid, RANKING)
    with pytest.raises(FactoryError, match=match):
        approve_gate(
            ctx,
            cid,
            "G1",
            {
                "decision": "SELECT",
                "selections": ["c2"],
                "referencePreviews": refs,
                "reviewer": "u",
            },
        )
    assert ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"


def test_s2_requires_g1(ctx):
    cid = new_character(ctx, "nog1")
    with pytest.raises(GateNotApprovedError):
        run_s2(ctx, cid)


def test_s2_offline_to_g2_and_appearance_spec(ctx):
    image = FakeImageModel()
    ctx.use_image(image)
    cid = _through_g1(ctx, ["c2-2"])
    out = run_s2(ctx, cid)
    st = ctx.state(cid)
    assert out.name == "ar1" and st.stage("s2").status == "AWAITING_HUMAN"
    assert st.gate("G2").status == "AWAITING_HUMAN"

    hero_reqs = [r for r in image.requests if r.stage == "s2"]
    assert len(hero_reqs) == 4
    ref = str(out / "references" / "c2-2.png")
    assert all(r.reference_images == (ref,) for r in hero_reqs)
    assert "identity reference" in hero_reqs[0].prompt
    assert "fictional Korean woman" in hero_reqs[0].prompt
    # 참조 사진이 외형 기준이므로 외형 태그는 빼고 분위기만 준다
    assert "Appearance:" not in hero_reqs[0].prompt and "Mood: innocent" in hero_reqs[0].prompt
    assert (out / "references" / "c2-2.png").read_bytes() == (
        ctx.character_dir(cid) / "s1-reference" / "rf1" / "previews" / "c2-2.png"
    ).read_bytes()

    for name in ("candidates.json", "inputs.json"):
        assert find_name_leaks((out / name).read_text("utf-8"), NAMES) == []
    page = (out / "gate-G2.html").read_text("utf-8")
    assert 'value="h4"' in page and "references/c2-2.png" in page

    approve_gate(ctx, cid, "G2", {"decision": "SELECT", "selections": ["h3"], "reviewer": "u"})
    spec, img = load_appearance_spec(ctx, cid)
    assert spec.appearanceRev == "ar1" and spec.referenceImage.id == "h3"
    assert img == out / "candidates" / "h3.png" and img.exists()
    assert spec.scope.appearanceOrigin == "korean" and spec.tags["mood"] == ["innocent"]
    assert "청순" in spec.descriptionKo and "innocent" in spec.descriptionEn
    assert [r.id for r in spec.referencePreviews] == ["c2-2"]
    assert find_name_leaks(spec.model_dump_json(), NAMES) == []
    assert ctx.state(cid).stage("s2").status == "APPROVED"
    assert main(["--root", str(ctx.config.root), "verify", cid]) == 0


def test_s2_without_reference_photos(ctx):
    image = FakeImageModel()
    ctx.use_image(image)
    cid = _through_g1(ctx, [])
    run_s2(ctx, cid)
    hero = [r for r in image.requests if r.stage == "s2"]
    assert all(r.reference_images == () for r in hero)
    assert "identity reference" not in hero[0].prompt
    assert "Appearance: oval face" in hero[0].prompt


def test_g2_rejects_bad_selection_and_request_changes_reruns(ctx):
    cid = _through_g1(ctx, [])
    run_s2(ctx, cid)
    with pytest.raises(FactoryError):
        approve_gate(ctx, cid, "G2", {"decision": "SELECT", "selections": ["h9"], "reviewer": "u"})
    approve_gate(ctx, cid, "G2", {"decision": "REQUEST_CHANGES", "reviewer": "u"})
    with pytest.raises(GateNotApprovedError):
        load_appearance_spec(ctx, cid)
    assert run_s2(ctx, cid).name == "ar2"


def test_s2_image_failure_is_check_failed(ctx):
    cid = _through_g1(ctx, [])

    class Blocked:
        name, model = "blocked", "x"

        def generate(self, request):
            raise ImageGenerationError("blocked")

    ctx.use_image(Blocked())
    with pytest.raises(ImageGenerationError):
        run_s2(ctx, cid)
    assert ctx.state(cid).stage("s2").status == "CHECK_FAILED"


def test_run_until_g2_with_auto_approve(ctx):
    cid = new_character(ctx, "auto")
    log = run_until(ctx, cid, RunOptions(until="G2", ranking=RANKING, auto_approve={"G1", "G2"}))
    assert log.stopped_at == "G2"
    g1 = json.loads((ctx.character_dir(cid) / "gates" / "G1-rf1.json").read_text("utf-8"))
    assert g1["selections"] == ["c1", "c1-1"]
    spec, _ = load_appearance_spec(ctx, cid)
    assert spec.clusterId == "c1" and spec.referenceImage.id == "h1"


def test_run_stops_at_g2_for_human(ctx):
    cid = new_character(ctx, "human")
    log = run_until(ctx, cid, RunOptions(until="G6", ranking=RANKING, auto_approve={"G1"}))
    assert log.stopped_at == "G2" and ctx.state(cid).gate("G2").status == "AWAITING_HUMAN"


def test_hero_dry_run(ctx, capsys):
    cid = _through_g1(ctx, ["c2-1"])
    assert main(["--root", str(ctx.config.root), "hero", "run", cid]) == 0
    out = capsys.readouterr().out
    assert "대표 이미지 후보 4장 (참조 사진 1장" in out and "합계 4회" in out
