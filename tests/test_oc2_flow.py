"""합성 원문 업로드부터 첫 장면과 승인 기록까지 확인한다."""

import sys
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import MODES, stages_for
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.web.app import create_app
from tests.support.synthetic import prompter_output
from tests.support.web_gates import trait_sheet_for
from tests.test_chapter_start import _start
from tests.test_source_intake import put
from tests.test_source_s0 import _good_digest
from tests.test_twin_flow import _pack
from tests.test_twin_s3 import _answer


@pytest.mark.parametrize("mode", MODES)
def test_motif_graph(mode):
    stage = stages_for("SOURCE", mode)["s8c"]
    assert stage.gate is None and stage.implemented
    assert stage.deps == {"G3"} and stage.after == {"s8"}
    assert "s8c" not in stages_for("CREATED", mode)


@pytest.mark.parametrize("manual,sample_failure", [(False, False), (True, False), (False, True)])
def test_finalize(tmp_path, monkeypatch, manual, sample_failure):
    client = TestClient(create_app(tmp_path))
    ctx = Context.load(tmp_path, execute=True)
    folder = _pack(tmp_path).parent
    options = {"autoReview": False, "modelMode": "TRAIN"} if manual else {}
    cid = client.post(
        "/api/sources/drafts",
        json=dict(
            displayName="엄마",
            subjectKind="PRIVATE_PERSON",
            **options,
            knownFacts=dict(age="41", gender="female", job="제본사", background="가족"),
        ),
    ).json()["characterId"]
    root = ctx.character_dir(cid)
    url = "/api/sources/" + cid
    assert client.get(url).json()["usageBasis"]["scope"] == "팀 내부 사용"
    target = put(client, url, (folder / "mom.txt").read_bytes())
    record = client.post(
        target + "/complete",
        json=dict(textId="a1", kind="KAKAO_EXPORT", subjectSpeaker="엄마", userSpeaker="나"),
    ).json()
    assert record["status"] == "ready"

    def reply(req):
        return {
            "s0": lambda: _good_digest(req),
            "s3-twin": lambda: _answer(req),
            "s7": lambda: trait_sheet_for(ctx, cid),
            "s8": prompter_output,
            "s8c": lambda: _start().model_dump() | {"characterId": cid},
        }[req.stage]()

    ctx.use_models(FakeTextModel(responses={"AGENT": reply}))
    monkeypatch.setattr("character_factory_poc.web.jobs.Context", lambda **kw: ctx)
    sampled = []

    def sample(context, character):
        assert (root / "s8-chapters/cs1/chapter-start.json").is_file()
        assert context.state(cid).gate("G6").status == "AWAITING_HUMAN"
        if sample_failure:
            raise RuntimeError("표본 생성 실패")
        sampled.append(character)

    monkeypatch.setitem(
        sys.modules, "character_factory_poc.common.demo_chat", SimpleNamespace(run_samples=sample)
    )
    job = client.post(url + "/finalize").json()["jobId"]
    for _ in range(500):
        info = client.get("/api/jobs/" + job).json()
        if info["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    if sample_failure:
        assert info["status"] == "failed"
        assert ctx.state(cid).stage("s8c").status == "CHECK_FAILED"
        assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
        return
    assert info["status"] == "succeeded", info["error"]
    state = ctx.state(cid)
    detail = client.get("/api/characters/" + cid).json()
    assert detail["autoReview"] is (not manual)
    assert detail["modelMode"] == ("TRAIN" if manual else "PROMPT_ONLY")
    assert any(s["id"] == "s8c" for lane in detail["lanes"] for s in lane["stages"])
    if manual:
        assert state.gate("G0").status == "AWAITING_HUMAN" and not sampled
        return
    assert sampled == [cid], info
    assert state.stage("s8c").status == "APPROVED"
    for gate, decision in [("G0", "APPROVE"), ("G3", "SELECT"), ("G6", "APPROVE")]:
        rec = read_json(root / state.gate(gate).recordRef)
        assert (rec["reviewer"], rec["decision"]) == ("자동 진행", decision)
        if gate == "G3":
            first = read_json(root / "s3-plan/pr1/variants.json")["candidates"][0]
            assert rec["selections"] == [first["variantId"]]
    assert state.gate("G1s").status == state.gate("G8").status == "PENDING"
    assert all(state.stage(s).status == "PENDING" for s in ("s2", "s4", "s5", "s10t", "s10"))
