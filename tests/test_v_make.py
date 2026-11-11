"""원문과 합성 사진부터 대화·영상 승인까지. 실제 공급자는 사용하지 않는다."""

import time
from threading import Event

from fastapi.testclient import TestClient

from character_factory_poc.common.store import read_json
from character_factory_poc.providers.fake_vision import FakeVisionModel, all_pass
from character_factory_poc.stages.s6_actions.catalog import VIDEO_TIERS
from character_factory_poc.web.app import create_app
from tests.support.flow import make_ctx
from tests.support.synthetic import assembly_answer
from tests.support.web_gates import trait_sheet_for
from tests.test_chapter_start import _start
from tests.test_scene_flow import agent_input, backgrounds, poses, scenes
from tests.test_source_intake import put
from tests.test_source_s0 import _good_digest
from tests.test_twin_flow import _pack
from tests.test_twin_s3 import _answer


def wait(client, job, expected="succeeded"):
    for _ in range(800):
        result = client.get("/api/jobs/" + job).json()
        if result["status"] in ("succeeded", "failed"):
            assert result["status"] == expected, result["log"][-8:]
            return result
        time.sleep(0.025)
    raise AssertionError("작업 시간 초과")


def test_light(tmp_path, monkeypatch):
    # Historical V3 auto-approval flow; the default evidence gate is covered in test_oc2_flow.
    ctx, agents = make_ctx(
        tmp_path, '[stages.s6]\nvideo_tier="max"\n[stages.s8]\nmotif_compiler="v3"'
    )
    client = TestClient(create_app(tmp_path))
    files = _pack(tmp_path).parent
    cid = client.post(
        "/api/sources/drafts",
        json={
            "displayName": "엄마",
            "subjectKind": "PRIVATE_PERSON",
            "videoTier": "light",
            "knownFacts": {"age": "41", "gender": "female", "job": "제본사", "background": "가족"},
        },
    ).json()["characterId"]
    url = "/api/sources/" + cid
    detail = "/api/characters/" + cid
    target = put(client, url, (files / "mom.txt").read_bytes())
    assert (
        client.post(
            target + "/complete",
            json={
                "textId": "a1",
                "kind": "KAKAO_EXPORT",
                "subjectSpeaker": "엄마",
                "userSpeaker": "나",
            },
        ).json()["fileType"]
        == "text"
    )
    assert "사진" in client.post(url + "/finalize").json()["detail"]
    assert client.patch(url + "/settings", json={"videoTier": "none"}).is_success
    assert client.get(url).json()["canFinalize"]
    assert client.patch(url + "/settings", json={"videoTier": "light"}).is_success

    def upload(data):
        record = client.post(
            url + "/files",
            json={"filename": "사진.png", "contentType": "image/png", "size": len(data)},
        ).json()
        assert client.put(record["upload"]["url"], content=data).is_success
        return client.post(url + "/files/" + record["fileId"] + "/complete", json={}).json()

    assert (
        client.post(
            url + "/files",
            json={"filename": "사진.png", "contentType": "image/png", "size": 15 * 1024**2 + 1},
        ).status_code
        == 413
    )
    bad = upload(b"not a photo")
    assert bad["status"] == "problem" and bad["problems"]
    assert client.delete(url + "/files/" + bad["fileId"]).is_success
    assert upload((files / "mom.png").read_bytes())["fileType"] == "photo"

    entered, resume = Event(), Event()

    def vision(req):
        entered.set()
        assert resume.wait(5)
        return {"faceShape": "oval"} if req.stage == "s2" else all_pass(req)

    ctx.use_vision(FakeVisionModel(responder=vision))

    def scoped(fn):
        def respond(req):
            wanted = agent_input(req, "settings")["chapters"]
            return {"chapters": [ch for ch in fn(req)["chapters"] if ch["chapterId"] in wanted]}

        return respond

    for stage, fn in {
        "s0": _good_digest,
        "s3-twin": _answer,
        "s7": lambda req: trait_sheet_for(ctx, cid),
        "s8": assembly_answer,
        "s8c": lambda req: _start().model_dump() | {"characterId": cid},
        "s4a": scoped(backgrounds),
        "s4b-scene": scenes,
        "s4b-pose": scoped(poses),
    }.items():
        agents.set(stage, fn)
    monkeypatch.setattr("character_factory_poc.web.jobs.Context", lambda **kw: ctx)
    monkeypatch.setattr("character_factory_poc.common.demo_chat.run_samples", lambda *a: None)
    paid_stages = {"s2", "s4a", "s4b", "s4", "s6"}
    monkeypatch.setattr(
        "character_factory_poc.pipeline.scheduler.paid_stage", lambda ctx, sid: sid in paid_stages
    )
    job = client.post(url + "/finalize").json()["jobId"]
    try:
        assert entered.wait(5), client.get("/api/jobs/" + job).json()
        row = client.get(detail).json()
        assert row["chatReady"] and row["videoStatus"] == "making"
    finally:
        resume.set()
    assert set(wait(client, job)["confirm"]) == paid_stages
    row = client.get(detail).json()
    assert row["videoStatus"] == "ready" and row["videoTier"] == "light"
    folder = ctx.character_dir(cid)
    pack = read_json(folder / "source-pack.json")
    assert len(pack["photos"]) == len(pack["texts"]) == 1
    for filename in (
        "s4a-backgrounds/bg1/background-candidates.json",
        "s4b-poses/ps1/scene-plan.json",
        "s4b-poses/ps1/pose-plan.json",
    ):
        assert [ch["chapterId"] for ch in read_json(folder / filename)["chapters"]] == ["ch1"]
    inputs = read_json(folder / "s6-actions/va1/inputs.json")
    assert [ch["chapterId"] for ch in inputs["chapters"]] == ["ch1"]
    assert [a["actionKey"] for a in inputs["chapters"][0]["actions"]] == list(
        VIDEO_TIERS["light"].actions
    )
    state = ctx.state(cid)
    assert state.gate("G5b").status == "APPROVED"
    assert all(state.stage(s).status == "PENDING" for s in ("s5", "s10", "s10t"))
    wait(client, client.post(detail + "/videos", json={"videoTier": "light"}).json()["jobId"])
    assert not (folder / "s6-actions/va2").exists()

    # 대화 가능 뒤 등급을 올려도 이전 승인 판은 보존한다.
    assert client.patch(url + "/settings", json={"videoTier": "standard"}).is_success
    assert client.get(detail).json()["videoStatus"] == "none"
    with monkeypatch.context() as failure:

        def unavailable(*args, **kwargs):
            raise RuntimeError("가짜 영상 공급자가 응답하지 않았어요.")

        failure.setattr(ctx._video, "submit", unavailable)
        wait(
            client,
            client.post(detail + "/videos", json={"videoTier": "standard"}).json()["jobId"],
            "failed",
        )
    failed = client.get(detail).json()
    assert failed["chatReady"] and failed["videoStatus"] == "failed"
    wait(client, client.post(detail + "/videos", json={"videoTier": "standard"}).json()["jobId"])
    upgraded = read_json(folder / "s6-actions/va2/inputs.json")
    assert [ch["chapterId"] for ch in upgraded["chapters"]] == ["ch1", "ch2", "ch3"]
    assert ctx.state(cid).gate("G1s").rev == "ar1"
    assert ctx.state(cid).gate("G4").rev == "fr2"
    assert client.get(detail).json()["videoStatus"] == "ready"
