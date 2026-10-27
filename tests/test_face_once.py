"""외모 한 번 고르기(M2b, D-0042·D-0043)를 가짜 공급자로 검증한다. 네트워크 없음."""

from __future__ import annotations

import json

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.cli import main
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import FactoryError, GateNotApprovedError, NameLeakError
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import GATES, STAGES
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.providers.fake_image import FakeImageModel
from character_factory_poc.stages.s1_reference.approve import selected_cluster
from character_factory_poc.stages.s1_reference.faces import run_faces
from character_factory_poc.stages.s1_reference.run import run_s1
from character_factory_poc.stages.s2_hero.approve import load_appearance_spec
from character_factory_poc.stages.s2_hero.run import run_s2
from character_factory_poc.stages.s3_plan.draft import new_character
from tests.support.flow import make_ctx
from tests.support.synthetic import RANKING


def _g1(ctx: Context, cid: str, **answer) -> None:
    base = {"decision": "SELECT", "reviewer": "u"}
    approve_gate(ctx, cid, "G1", base | answer)


def test_graph_has_no_g2_and_uses_s2_needs():
    assert "G2" not in GATES and "G2" not in STAGES
    assert STAGES["s2"].gate is None and STAGES["s2"].deps == frozenset({"G1"})
    assert STAGES["s5"].needs == frozenset({"s2"})
    assert STAGES["s4a"].needs == frozenset({"s2"})
    assert STAGES["s4"].needs == frozenset({"s2"})


def test_require_deps_speaks_about_s2(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cid = new_character(ctx, "needs")
    state = ctx.state(cid)
    state.set_gate("G3", "APPROVED", "pr1", None)
    with pytest.raises(GateNotApprovedError, match="s4a는 s2 승인이 필요하다"):
        state.require_deps("s4a")
    state.set_gate("G4b", "APPROVED", "ps1", None)
    with pytest.raises(GateNotApprovedError, match="s4는 s2 승인이 필요하다"):
        state.require_deps("s4")
    with pytest.raises(GateNotApprovedError, match="s5는 s2 승인이 필요하다"):
        state.require_deps("s5")


def test_g1_select_derives_cluster_from_face(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cid = new_character(ctx, "derive")
    run_s1(ctx, cid, RANKING)
    _g1(ctx, cid, selections=[], referencePreviews=["c2-1"])
    rec = json.loads((ctx.character_dir(cid) / ctx.state(cid).gate("G1").recordRef).read_text())
    assert rec["selections"] == ["c2", "c2-1"]
    assert selected_cluster(ctx, cid).clusterId == "c2"


def test_g1_select_rejects_mismatched_cluster(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cid = new_character(ctx, "mismatch")
    run_s1(ctx, cid, RANKING)
    with pytest.raises(FactoryError, match="다르다"):
        _g1(ctx, cid, selections=["c1"], referencePreviews=["c2-1"])
    assert ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"


def test_g1_request_changes_needs_note(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cid = new_character(ctx, "note")
    run_s1(ctx, cid, RANKING)
    with pytest.raises(FactoryError, match="note가 필요하다"):
        approve_gate(ctx, cid, "G1", {"decision": "REQUEST_CHANGES", "reviewer": "u"})
    assert ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"
    approve_gate(
        ctx,
        cid,
        "G1",
        {"decision": "REQUEST_CHANGES", "reviewer": "u", "note": "얼굴이 너무 어려 보인다"},
    )
    assert ctx.state(cid).gate("G1").status == "REJECTED"
    page = (ctx.character_dir(cid) / "s1-reference" / "rf1" / "gate-G1.html").read_text()
    assert 'name="face"' in page and "추천" in page and 'id="note"' in page


def test_ref_faces_remakes_only_faces_and_carries_the_rest(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    image = FakeImageModel()
    ctx.use_image(image)
    cid = new_character(ctx, "faces")
    run_s1(ctx, cid, RANKING)
    with pytest.raises(FactoryError, match="G1 결정이 아직 없다"):
        run_faces(ctx, cid)
    approve_gate(
        ctx,
        cid,
        "G1",
        {"decision": "REQUEST_CHANGES", "reviewer": "u", "note": "눈매가 더 차분했으면"},
    )
    rf1 = ctx.character_dir(cid) / "s1-reference" / "rf1"
    before = {n: (rf1 / n).read_bytes() for n in ("ranking.json", "people.json")}
    scouts = agents.calls.count("s1")
    image.requests.clear()

    out = run_faces(ctx, cid)
    assert out.name == "rf2" and agents.calls.count("s1") == scouts  # Scout 재호출 없음
    for name in ("ranking.json", "people.json", "features.json", "report.json"):
        assert (out / name).read_bytes() == (rf1 / name).read_bytes()
    assert before["ranking.json"] == (out / "ranking.json").read_bytes()
    carry = json.loads((out / "carried-from.json").read_text())
    assert carry["fromRev"] == "rf1" and carry["note"] == "눈매가 더 차분했으면"
    assert carry["files"]["report.json"] == sha256_file(out / "report.json")

    previews = json.loads((out / "previews.json").read_text())
    assert [p["previewId"] for p in previews] == ["c1-1", "c2-1", "c3-1"]
    assert all("Revision note: 눈매가 더 차분했으면" in p["prompt"] for p in previews)
    assert len(image.requests) == 3 and all(r.stage == "s1" for r in image.requests)
    assert all(
        (out / p["filePath"]).read_bytes() != (rf1 / p["filePath"]).read_bytes() for p in previews
    )
    assert ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"
    assert ctx.state(cid).gate("G1").rev == "rf2"

    _g1(ctx, cid, referencePreviews=["c2-1"])
    assert ctx.state(cid).gate("G1").status == "APPROVED"
    assert run_s2(ctx, cid).name == "ar1"
    assert main(["--root", str(ctx.config.root), "verify", cid]) == 0


def test_ref_faces_stops_on_name_in_note(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    image = FakeImageModel()
    ctx.use_image(image)
    cid = new_character(ctx, "leak")
    run_s1(ctx, cid, RANKING)
    approve_gate(
        ctx,
        cid,
        "G1",
        {"decision": "REQUEST_CHANGES", "reviewer": "u", "note": "가상하윤 느낌으로"},
    )
    image.requests.clear()
    with pytest.raises(NameLeakError):
        run_faces(ctx, cid)
    assert image.requests == []
    assert ctx.state(cid).stage("s1").status == "CHECK_FAILED"


def test_generate_is_rejected_before_any_write(tmp_path):
    ctx, _ = make_ctx(tmp_path, '[stages.s2]\nbase_photo = "generate"\n')
    image = FakeImageModel()
    ctx.use_image(image)
    cid = new_character(ctx, "gen")
    run_s1(ctx, cid, RANKING)
    _g1(ctx, cid, referencePreviews=["c2-1"])
    image.requests.clear()
    with pytest.raises(FactoryError, match="범위 밖") as e:
        run_s2(ctx, cid)
    assert "picked" in str(e.value) and "K-0034" in str(e.value)
    assert image.requests == []
    assert ctx.state(cid).stage("s2").status == "PENDING"
    assert not (ctx.character_dir(cid) / "s2-hero").exists()


def _old_char(ctx: Context, *, s2_marked: bool) -> str:
    """옛 G2 승인 기록(ar2, 후보 h2)을 손으로 만든다. s2 표시는 옵션이다."""
    cid = new_character(ctx, "old")
    char_dir = ctx.character_dir(cid)
    rev_dir = char_dir / "s2-hero" / "ar2"
    (rev_dir / "candidates").mkdir(parents=True)
    png = rev_dir / "candidates" / "h2.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"old")
    ref = {"id": "h2", "path": "candidates/h2.png", "sha256": sha256_file(png)}
    from character_factory_poc.common.schema import dump, validate

    spec = validate(
        "appearance-spec-v1",
        {
            "characterId": cid,
            "appearanceRev": "ar2",
            "sourceReferenceRev": "rf1",
            "clusterId": "c2",
            "scope": RANKING["scope"],
            "tags": {"mood": ["innocent"]},
            "descriptionKo": "청순",
            "descriptionEn": "innocent",
            "referenceImage": ref,
            "referencePreviews": [ref],
            "heroPrompt": "old prompt",
        },
    )
    (rev_dir / "appearance-spec.json").write_text(
        json.dumps(dump(spec), ensure_ascii=False), encoding="utf-8"
    )
    gates = {"G2": {"status": "APPROVED", "rev": "ar2", "recordRef": "gates/G2-ar2.json"}}
    stages = {"s2": {"status": "APPROVED", "currentRev": "ar2"}} if s2_marked else {}
    char_dir.mkdir(parents=True, exist_ok=True)
    (char_dir / "state.json").write_text(
        json.dumps(
            {"schemaVersion": "state-v1", "subjectId": cid, "stages": stages, "gates": gates},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return cid


@pytest.mark.parametrize("marked", [True, False])
def test_old_state_with_g2_still_reads(tmp_path, marked):
    ctx, _ = make_ctx(tmp_path)
    cid = _old_char(ctx, s2_marked=marked)
    assert ctx.state(cid).gate("G2").status == "APPROVED"
    spec, img = load_appearance_spec(ctx, cid)
    assert spec.appearanceRev == "ar2" and spec.basePhoto is None
    assert (
        spec.identityCheck is None
        and img == ctx.character_dir(cid) / "s2-hero/ar2/candidates/h2.png"
    )


def test_status_marks_legacy_g2(tmp_path, capsys):
    ctx, _ = make_ctx(tmp_path)
    cid = _old_char(ctx, s2_marked=True)
    assert main(["--root", str(ctx.config.root), "status", cid]) == 0
    out = capsys.readouterr().out
    assert "G2: APPROVED" in out and "결번·옛 기록" in out


def test_gate_import_g2_is_rejected(tmp_path, capsys):
    ctx, _ = make_ctx(tmp_path)
    cid = new_character(ctx, "gate2")
    answer = tmp_path / "answer.json"
    answer.write_text(json.dumps({"decision": "SELECT", "reviewer": "u"}), "utf-8")
    assert (
        main(["--root", str(ctx.config.root), "gate", "import", cid, "G2", "--answer", str(answer)])
        == 1
    )
    err = capsys.readouterr().err
    assert "G2는 결번" in err and "picked" in err


def test_auto_approve_and_until_reject_g2(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    cid = new_character(ctx, "retired")
    with pytest.raises(FactoryError, match="G2는 결번"):
        run_until(ctx, cid, RunOptions(until="G6", auto_approve={"G2"}))
    with pytest.raises(FactoryError, match="G2는 결번"):
        run_until(ctx, cid, RunOptions(until="G2"))


def test_orchestrator_runs_g1_then_s2_then_next_lane(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    image = FakeImageModel()
    ctx.use_image(image)
    cid = new_character(ctx, "lane")

    log = run_until(ctx, cid, RunOptions(until="s5", ranking=RANKING, auto_approve={"G1"}))
    st = ctx.state(cid)
    assert st.stage("s1").status == "APPROVED"
    assert st.stage("s2").status == "APPROVED" and st.stage("s2").currentRev == "ar1"
    assert "G2" not in log.waiting  # 결번은 대기 목록에 나오지 않는다
    assert st.stage("s5").status == "AWAITING_HUMAN" and log.waiting == ["G5"]
    assert "s3" in log.blocked  # 씨앗이 없어 그 갈래만 멈춘다
    spec, _ = load_appearance_spec(ctx, cid)
    assert spec.basePhoto == "picked" and spec.referenceImage.id == "c1-1"
    assert agents.calls.count("s1") == 1
