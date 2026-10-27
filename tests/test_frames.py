"""기존 S3 외모 연결과 얼굴 크롭 검사. 새 장면 흐름은 test_scene_flow.py에서 검증한다."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import acf.contracts  # noqa: F401
from acf.common.names import find_name_leaks
from acf.common.schema import validate
from acf.pipeline.approve import approve_gate
from acf.pipeline.context import Context
from acf.providers.fake import FakeTextModel
from acf.providers.fake_image import FakeImageModel
from acf.stages.s1_reference.ranking import all_names, load_ranking
from acf.stages.s1_reference.run import run_s1
from acf.stages.s2_hero.run import run_s2
from acf.stages.s3_plan.check import check_plan_draft
from acf.stages.s3_plan.draft import new_character, run_s3_draft
from tests.support.synthetic import RANKING, scout_features
from tests.test_agentic import BRIEF, CATALOG, _plan_from_preset

NAMES = all_names(load_ranking(RANKING))
LIGHT = {
    "ch1": "비 오는 오후 창가의 흐린 자연광",
    "ch2": "노란 전구 아래 따뜻한 밤빛",
    "ch3": "푸른 새벽빛",
}
COMPO = {
    "ch1": "창가 테이블에 앉아 카메라 쪽을 보는 상반신",
    "ch2": "골목에 서서 뒤돌아보는 반신",
    "ch3": "정류장 벤치에 앉은 상반신",
}


def plan_for(req) -> dict:
    cid, rev = req.ref.split("#")[0].split("/")
    plan = _plan_from_preset(cid, rev)
    text = "\n".join(m.content for m in req.messages)
    m = re.search(r'"appearanceRev": "(ar\d+)"', text)
    plan["appearanceRev"] = m.group(1) if m else None
    plan["chapters"] = [
        dict(c, lighting=LIGHT[c["chapterId"]], composition=COMPO[c["chapterId"]])
        for c in plan["chapters"]
    ]
    return plan


def agent(req):
    return scout_features(RANKING) if req.stage == "s1" else plan_for(req)


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    (tmp_path / "catalog.json").write_text(json.dumps(CATALOG, ensure_ascii=False), "utf-8")
    (tmp_path / "factory.toml").write_text(
        f'[resources]\nstanford_presets_json = "{tmp_path / "catalog.json"}"\n', encoding="utf-8"
    )
    c = Context.load(tmp_path, execute=True)
    text = FakeTextModel()
    text.add("AGENT", agent)
    c.use_models(text)
    c.use_image(FakeImageModel())
    return c


def _through_g2(ctx: Context) -> str:
    cid = new_character(ctx, "frames")
    run_s1(ctx, cid, RANKING)
    approve_gate(
        ctx,
        cid,
        "G1",
        {
            "decision": "SELECT",
            "selections": ["c2"],
            "referencePreviews": ["c2-1"],
            "reviewer": "u",
        },
    )
    run_s2(ctx, cid)
    approve_gate(ctx, cid, "G2", {"decision": "SELECT", "selections": ["h2"], "reviewer": "u"})
    return cid


def _through_g3(ctx: Context) -> str:
    cid = _through_g2(ctx)
    run_s3_draft(ctx, cid, BRIEF)
    approve_gate(ctx, cid, "G3", {"decision": "APPROVE", "reviewer": "u"})
    return cid


def test_s3_draft_receives_appearance_and_records_rev(ctx):
    cid = _through_g2(ctx)
    out = run_s3_draft(ctx, cid, BRIEF)
    plan = json.loads((out / "plan.json").read_text("utf-8"))
    assert plan["appearanceRev"] == "ar1"
    app = json.loads((out / "workspace" / "inputs" / "appearance.json").read_text("utf-8"))
    assert app["appearanceRev"] == "ar1" and "청순" in app["descriptionKo"]
    assert "성격" in app["use"]
    assert find_name_leaks(json.dumps(app, ensure_ascii=False), NAMES) == []


def test_s3_without_g2_has_no_appearance(ctx):
    cid = new_character(ctx, "persona")
    out = run_s3_draft(ctx, cid, BRIEF)
    assert not (out / "workspace" / "inputs" / "appearance.json").exists()
    assert json.loads((out / "plan.json").read_text("utf-8"))["appearanceRev"] is None


def test_s3_check_with_appearance_requires_rev_and_frame_lines():
    p = _plan_from_preset("cf-20260101-x", "pr1")
    p["appearanceRev"] = "ar9"
    problems = check_plan_draft(BRIEF, "ar1")(validate("character-plan-v1", p))
    assert any("appearanceRev" in x for x in problems)
    assert any("ch1.lighting" in x for x in problems)
    assert any("ch3.composition" in x for x in problems)
    assert not any(
        "lighting" in x for x in check_plan_draft(BRIEF)(validate("character-plan-v1", p))
    )


def _png(w: int, h: int) -> bytes:
    import cv2
    import numpy as np

    ok, buf = cv2.imencode(".png", np.full((h, w, 3), 200, dtype=np.uint8))
    assert ok
    return buf.tobytes()


def test_face_crop_box_and_crop():
    from acf.common.face_crop import crop_box, crop_face

    # 얼굴 상자를 1.4배 정사각형으로 넓히고 위로 올리며, 이미지 밖으로 나가지 않는다
    assert crop_box((500, 200, 380, 380), 1254, 1254, 1.4, 0.12) == (424, 78, 532, 532)
    assert crop_box((0, 0, 400, 400), 500, 500, 2.0, 0.0) == (0, 0, 500, 500)
    data = _png(1000, 800)
    out = crop_face(data, detector=lambda d: [(100, 100, 50, 50), (400, 300, 200, 200)])
    assert out is not None and out[1][2] == 280 and out[0].startswith(b"\x89PNG")
    assert crop_face(data) is None  # 실제 검출기: 얼굴 없는 단색 이미지
