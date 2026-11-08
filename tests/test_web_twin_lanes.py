"""트윈 그래프의 팀 줄과 화면 시험 자료(studio/tests/fixtures)가 실제 응답과 같은지 확인한다."""

import json
from pathlib import Path

import pytest

from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import SOURCE, write_model_mode, write_origin
from character_factory_poc.web import reads
from tests.test_web_runtime import client_for, make_root

FIXTURES = Path(__file__).resolve().parents[1] / "studio" / "tests" / "fixtures"


@pytest.mark.parametrize("mode", ["TRAIN", "BIND_EXISTING", "PROMPT_ONLY"])
def test_twin_lanes_match_studio_fixture(tmp_path, mode):
    root = make_root(tmp_path)
    ctx = Context.load(root, False)
    ctx.state("twin").save()
    folder = ctx.character_dir("twin")
    write_origin(folder, SOURCE)
    write_model_mode(folder, mode)
    client, _ = client_for(root)
    body = client.get("/api/runtime/graph", params={"character_id": "twin"}).json()
    body.pop("orchestrator")
    fixture = json.loads((FIXTURES / f"twin-graph-{mode}.json").read_text("utf-8"))
    assert body == fixture
    lanes = {lane["id"]: lane for lane in body["lanes"]}
    assert body["lanes"][0] == {"id": "source", "label": "출처", "stages": ["s0"]}
    assert lanes["appearance"]["stages"] == ["s2"]
    assert "s9h" in lanes["training"]["stages"]
    assert ("data" in lanes) == (mode == "TRAIN")
    assert lanes["training"]["label"] == ("학습" if mode == "TRAIN" else "평가")
    placed = [sid for lane in body["lanes"] for sid in lane["stages"]]
    assert sorted(placed) == sorted(s["id"] for s in body["stages"])


def test_original_lanes_are_unchanged(tmp_path):
    root = make_root(tmp_path)
    client, _ = client_for(root)
    body = client.get("/api/runtime/graph").json()
    assert body["lanes"] == [
        {"id": lane["id"], "label": lane["label"], "stages": list(lane["stages"])}
        for lane in reads.LANES
    ]
