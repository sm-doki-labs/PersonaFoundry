"""합성 원문 업로드부터 첫 장면과 승인 기록까지 확인한다."""

import time

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import MODES, stages_for
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.web.app import create_app
from tests.support.web_gates import trait_sheet_for
from tests.test_chapter_start import _start
from tests.test_evidence_pipeline import candidate
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
            "s8": lambda: candidate(req),
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

    monkeypatch.setattr("character_factory_poc.common.demo_chat.run_samples", sample)
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
        from tests.test_v_make import wait

        attempt = client.post("/api/jobs", json={"characterId": cid, "until": "s8c"}).json()
        stopped = wait(client, attempt["jobId"])
        assert "G0" in stopped["waiting"] and stopped["error"] is None
        return
    assert sampled == [cid], info
    assert state.stage("s8c").status == "APPROVED"
    for gate, decision in [("G0", "APPROVE"), ("G3", "SELECT")]:
        rec = read_json(root / state.gate(gate).recordRef)
        assert (rec["reviewer"], rec["decision"]) == ("자동 진행", decision)
        if gate == "G3":
            first = read_json(root / "s3-plan/pr1/variants.json")["candidates"][0]
            assert rec["selections"] == [first["variantId"]]
    assert "G6" in info["waiting"]
    assert state.gate("G6").status == "AWAITING_HUMAN"
    folder = root / "s8-prompts" / state.gate("G6").rev
    pair = read_json(folder / "prompt-pair.json")
    assert pair["systemRulesRef"] == "builtin:evidence-pipeline-v4"
    assert not (folder / "persona-version.json").exists()
    unreviewed = client.post(
        f"/api/characters/{cid}/gates/G6/decision",
        json={"decision": "APPROVE", "reviewer": "근거 검토자"},
    )
    assert unreviewed.status_code == 400, unreviewed.text
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    assert not (folder / "persona-version.json").exists()
    approval = client.post(
        f"/api/characters/{cid}/gates/G6/decision",
        json={
            "decision": "APPROVE",
            "reviewer": "근거 검토자",
            "evidenceReviewed": True,
            "expectedRev": state.gate("G6").rev,
        },
    )
    assert approval.status_code == 200, approval.text
    state = ctx.state(cid)
    assert state.gate("G6").status == "APPROVED"
    rec = read_json(root / state.gate("G6").recordRef)
    assert (rec["reviewer"], rec["decision"]) == ("근거 검토자", "APPROVE")
    version = read_json(folder / "persona-version.json")
    assert version["long"] == pair["long"]
    assert version["long"]["sha256"] == sha256_text((folder / "long.md").read_text("utf-8"))
    assert state.gate("G1s").status == state.gate("G8").status == "PENDING"
    assert all(state.stage(s).status == "PENDING" for s in ("s2", "s4", "s5", "s10t", "s10"))


def test_extra_target_holds_paid_work_without_running_unrelated_stages(tmp_path, monkeypatch):
    from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
    from character_factory_poc.pipeline.origin import write_origin

    ctx = Context.load(tmp_path, execute=True)
    cid = "cf-extra"
    folder = ctx.character_dir(cid)
    write_origin(folder, "SOURCE", auto_review=True)
    ctx.use_models(FakeTextModel(responses={"AGENT": _good_digest}))
    first = run_until(ctx, cid, RunOptions(until="G0", web=True, source_pack=_pack(tmp_path)))
    assert first.stopped_at == "G0"
    monkeypatch.setattr(
        "character_factory_poc.pipeline.scheduler.paid_stage", lambda ctx, sid: sid == "s2"
    )
    held = run_until(ctx, cid, RunOptions(until="s2", web=True))
    assert held.held == ["s2"] and not held.timings
    more = run_until(ctx, cid, RunOptions(until="s9h", web=True))
    assert list(more.timings) == ["s9h"] and ctx.state(cid).stage("s9h").status == "APPROVED"
