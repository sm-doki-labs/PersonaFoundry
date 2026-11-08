import json

import pytest

from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import GATES, STAGES
from character_factory_poc.pipeline.origin import SOURCE, write_model_mode, write_origin
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError
from tests.test_web_runtime import client_for, make_root


@pytest.mark.parametrize("mode", ["TRAIN", "BIND_EXISTING", "PROMPT_ONLY"])
def test_graph_detail_and_job_validation_follow_character(tmp_path, mode):
    root = make_root(tmp_path)
    ctx = Context.load(root, False)
    cid = "twin"
    ctx.state(cid).save()
    folder = ctx.character_dir(cid)
    write_origin(folder, SOURCE)
    write_model_mode(folder, mode)
    state = ctx.state(cid)
    state.transition("s0", "RUNNING", rev="sp1")
    state.transition("s0", "AWAITING_HUMAN", rev="sp1")
    state.set_gate("G0", "AWAITING_HUMAN", "sp1", None)
    client, jobs = client_for(root)
    body = client.get("/api/runtime/graph", params={"character_id": cid}).json()
    detail = reads.character_detail(root, cid)
    for view in [body, detail, detail["summary"]]:
        stages = [r["id"] for r in view["stages"]]
        gates = [g["id"] for g in view["gates"]]
        assert {"s0", "s9h"} <= set(stages) and "s1" not in stages
        assert {"G0", "G1s"} <= set(gates) and "G1" not in gates
        assert ("s10t" in stages) == ("G7" in gates) == (mode == "TRAIN")
        assert (view["origin"], view["modelMode"]) == ("SOURCE", mode)
    assert detail["queue"][0]["gate"] == "G0" and detail["pendingGates"][0]["id"] == "G0"
    assert detail["history"]["s0"][0]["result"] == "AWAITING_HUMAN"
    assert reads.health_snapshot(root)["pendingGates"] == 1
    with pytest.raises(WebError):
        jobs.submit(cid, until="G1")
    with pytest.raises(WebError):
        jobs.submit(cid, until="G0", confirm=["s1"])


def test_original_default_and_scoped_graph_are_identical_except_metadata(tmp_path):
    root = make_root(tmp_path)
    ctx = Context.load(root, False)
    ctx.state("old").save()
    client, _ = client_for(root)
    graph = client.get("/api/runtime/graph").json()
    scoped = client.get("/api/runtime/graph?character_id=old").json()
    assert scoped == {**graph, "origin": "CREATED", "originLabel": "오리지널", "modelMode": "TRAIN"}
    detail = reads.character_detail(root, "old")
    assert [s["id"] for s in detail["stages"]] == list(STAGES)
    assert [g["id"] for g in detail["gates"]] == GATES


def test_bind_gate_carries_real_adoption_reference(tmp_path):
    root = make_root(tmp_path)
    ctx = Context.load(root, False)
    folder = ctx.character_dir("bound")
    write_origin(folder, SOURCE)
    write_model_mode(folder, "BIND_EXISTING")
    ctx.state("bound").set_gate("G8", "AWAITING_HUMAN", "ev1", None)
    rev = folder / "s10-eval/ev1"
    rev.mkdir(parents=True)
    ref = "model-prep/mb7/binding.json"
    (rev / "prompt-only.json").write_text(
        json.dumps({"mode": "BIND_EXISTING", "adoptOptions": [ref]})
    )
    gate = reads.gate_view(root, "bound", "G8")
    assert gate["modelMode"] == "BIND_EXISTING"
    assert gate["items"]["adoptTarget"] == ref == gate["items"]["adoptOptions"][0]
    assert gate["items"]["adoptLabel"] == "연결한 모델로 진행"
