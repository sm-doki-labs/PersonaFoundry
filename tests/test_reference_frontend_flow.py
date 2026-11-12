"""Reference-first intake, explicit consent and independent persona branch (fake only)."""

import time
from threading import Event

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline import orchestrator
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.fake_image import FakeImageModel, solid_png
from character_factory_poc.providers.fake_vision import FakeVisionModel
from character_factory_poc.web.app import create_app
from tests.support.web_gates import trait_sheet_for
from tests.test_chapter_start import _start
from tests.test_evidence_pipeline import candidate
from tests.test_source_intake import put
from tests.test_source_s0 import _good_digest
from tests.test_twin_flow import _pack
from tests.test_twin_s3 import _answer
from tests.test_video_evidence_handoff import wait_idle


def intake(tmp_path, monkeypatch):
    (tmp_path / "factory.toml").write_text(
        '[providers.demo_chat]\nadapter="fake"\nmodel="synthetic"\n'
        "[orchestrator]\nmax_parallel=3\nauto_resume=false\n"
    )
    app = create_app(tmp_path)
    client = TestClient(app)
    ctx = Context.load(tmp_path, execute=True)
    ctx.use_image(FakeImageModel())
    ctx.use_vision(FakeVisionModel(responder=lambda req: {"faceShape": "oval"}))
    response = client.post(
        "/api/sources/drafts",
        json={
            "displayName": "엄마",
            "subjectKind": "PRIVATE_PERSON",
            "videoTier": "light",
            "referenceImage": {"wardrobe": "푸른 셔츠", "background": "밝은 거실"},
            "signaturePose": {"title": "손인사", "motion": "오른손을 한 번 흔든다"},
            "knownFacts": {"age": "41", "gender": "female", "job": "제본사", "background": "가족"},
        },
    )
    assert response.is_success, response.text
    cid = response.json()["characterId"]
    url = "/api/sources/" + cid
    target = put(client, url, _pack(tmp_path).with_name("mom.txt").read_bytes())
    assert client.post(
        target + "/complete",
        json={
            "textId": "a1",
            "kind": "KAKAO_EXPORT",
            "subjectSpeaker": "엄마",
            "userSpeaker": "나",
        },
    ).is_success
    data = solid_png(90, 160, (100, 100, 100))
    upload = client.post(
        url + "/files",
        json={
            "filename": "photo.png",
            "size": len(data),
            "contentType": "image/png",
        },
    ).json()
    assert client.put(upload["upload"]["url"], content=data).is_success
    assert client.post(url + "/files/" + upload["fileId"] + "/complete", json={}).is_success

    def answer(req):
        return {
            "s0": _good_digest,
            "s3-twin": _answer,
            "s7": lambda req: trait_sheet_for(ctx, cid),
            "s8": candidate,
            "s8c": lambda req: _start().model_dump() | {"characterId": cid},
        }[req.stage](req)

    ctx.use_models(FakeTextModel(responses={"AGENT": answer}))
    monkeypatch.setattr("character_factory_poc.web.jobs.Context", lambda **kw: ctx)
    monkeypatch.setattr("character_factory_poc.web.reference_images.Context", lambda **kw: ctx)
    return ctx, cid, url, app.state.jobs, client


def test_intake_preview_confirm_six_and_idempotency(tmp_path, monkeypatch):
    ctx, cid, url, jobs, client = intake(tmp_path, monkeypatch)
    assert client.get(url).json()["referenceImage"]["wardrobe"] == "푸른 셔츠"
    launched = client.post(url + "/finalize")
    assert launched.is_success, launched.text
    wait_idle(jobs, cid)
    job = jobs.get(launched.json()["jobId"])
    assert job["status"] == "succeeded", job
    assert ctx.state(cid).gate("G4").status == "AWAITING_HUMAN", job
    assert ctx.state(cid).stage("s8c").status == "APPROVED", job
    assert ctx.state(cid).stage("s6").status == "PENDING"
    preview = client.get(url + "/reference")
    assert preview.is_success, preview.text
    info = preview.json()
    assert info["status"] == "awaiting_confirmation"
    assert client.get(info["imageUrl"]).is_success
    confirm = {"revision": info["revision"], "sha256": info["sha256"]}
    assert (
        client.post(url + "/reference/confirm", json=confirm | {"sha256": "0" * 64}).status_code
        == 409
    )
    approved = client.post(url + "/reference/confirm", json=confirm)
    assert approved.is_success, approved.text
    wait_idle(jobs, cid)
    assert ctx.state(cid).stage("s6").status == "APPROVED", jobs.list(cid)
    root = ctx.character_dir(cid)
    rev = ctx.state(cid).stage("s6").currentRev
    specs = read_json(root / "s6-actions" / rev / "clips.json")
    assert len(specs) == 6
    before = sorted(root.glob("s6-actions/va*"))
    assert client.post(url + "/reference/confirm", json=confirm).is_success
    wait_idle(jobs, cid)
    assert sorted(root.glob("s6-actions/va*")) == before
    assert ctx.state(cid).stage("s8").currentRev == "pv1"


def test_confirm_during_prompt_does_not_block_http(tmp_path, monkeypatch):
    ctx, cid, url, jobs, client = intake(tmp_path, monkeypatch)
    entered, release = Event(), Event()
    original = orchestrator._stage_runners

    def runners(context, character, options):
        out = original(context, character, options)
        s7 = out["s7"]

        def hold_prompt():
            entered.set()
            assert release.wait(15)
            return s7()

        out["s7"] = hold_prompt
        return out

    monkeypatch.setattr(orchestrator, "_stage_runners", runners)
    assert client.post(url + "/finalize").is_success
    assert entered.wait(5)
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            info = client.get(url + "/reference").json()
            if info["status"] == "awaiting_confirmation":
                break
            time.sleep(0.02)
        assert info["status"] == "awaiting_confirmation", jobs.list(cid)
        start = time.monotonic()
        accepted = client.post(
            url + "/reference/confirm",
            json={
                "revision": info["revision"],
                "sha256": info["sha256"],
            },
        )
        assert accepted.is_success, accepted.text
        assert time.monotonic() - start < 2
        assert ctx.state(cid).gate("G4").status == "APPROVED"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and ctx.state(cid).stage("s6").status != "APPROVED":
            time.sleep(0.02)
        assert ctx.state(cid).stage("s6").status == "APPROVED", jobs.list(cid)
        assert not release.is_set(), "videos must finish while the persona worker is still held"
    finally:
        release.set()
    wait_idle(jobs, cid)
    # Completion may enqueue one video-only continuation after the first job exits.
    time.sleep(0.1)
    wait_idle(jobs, cid)
    assert ctx.state(cid).stage("s6").status == "APPROVED", jobs.list(cid)


def test_retry_keeps_old_image_and_rejects_old_confirmation(tmp_path, monkeypatch):
    ctx, cid, url, jobs, client = intake(tmp_path, monkeypatch)
    client.post(url + "/finalize")
    wait_idle(jobs, cid)
    first = client.get(url + "/reference").json()
    old = client.get(first["imageUrl"]).content
    response = client.post(
        url + "/reference/retry",
        json={
            "revision": first["revision"],
            "wardrobe": "",
            "background": "",
        },
    )
    assert response.is_success, response.text
    wait_idle(jobs, cid)
    second = client.get(url + "/reference").json()
    assert second["status"] == "awaiting_confirmation", jobs.list(cid)
    assert first["revision"] != second["revision"]
    assert client.get(first["imageUrl"]).content == old
    assert second["wardrobe"] == second["background"] == ""
    assert (
        client.post(
            url + "/reference/confirm",
            json={
                "revision": first["revision"],
                "sha256": first["sha256"],
            },
        ).status_code
        == 409
    )
    assert ctx.state(cid).stage("s6").status == "PENDING"


def test_reference_flow_is_opt_in_and_lite_only(tmp_path):
    client = TestClient(create_app(tmp_path))
    data = {"displayName": "합성", "subjectKind": "PRIVATE_PERSON", "referenceImage": {}}
    assert client.post("/api/sources/drafts", json=data).status_code == 422
    assert (
        client.post("/api/sources/drafts", json=data | {"videoTier": "standard"}).status_code == 422
    )
    res = client.post(
        "/api/sources/drafts", json={k: v for k, v in data.items() if k != "referenceImage"}
    )
    cid = res.json()["characterId"]
    assert client.get(f"/api/sources/{cid}/reference").json()["enabled"] is False


def test_approved_bundle_exists_when_gate_is_published(tmp_path, monkeypatch):
    from character_factory_poc.stages.s4_frames import approve

    ctx, cid, url, jobs, client = intake(tmp_path, monkeypatch)
    client.post(url + "/finalize")
    wait_idle(jobs, cid)
    info = client.get(url + "/reference").json()
    original = approve.write_gate_record
    observed = []

    def publish(*args, **kwargs):
        result = original(*args, **kwargs)
        # At this point a different worker can already see G4=APPROVED.
        frames, _ = approve.load_approved_frames(ctx, cid)
        observed.append(frames.frameRev)
        return result

    monkeypatch.setattr(approve, "write_gate_record", publish)
    res = client.post(
        url + "/reference/confirm",
        json={
            "revision": info["revision"],
            "sha256": info["sha256"],
        },
    )
    assert res.is_success, res.text
    wait_idle(jobs, cid)
    assert observed == [info["revision"]]


# D-0212: 시연 모드는 기준 사진도 자동 승인하므로 여기서 뺀다(tests/test_publish_node.py).
@pytest.mark.parametrize("mode", ["video_only", "auto_approve", "stale"])
def test_automatic_paths_cannot_confirm_a_master(tmp_path, monkeypatch, mode):
    from character_factory_poc.pipeline.orchestrator import RunLog, RunOptions, _step
    from character_factory_poc.pipeline.origin import write_reference_image

    ctx, cid, url, jobs, client = intake(tmp_path, monkeypatch)
    assert client.post(url + "/finalize").is_success
    wait_idle(jobs, cid)
    opts = (
        {"video_only": True}
        if mode in {"video_only", "stale"}
        else ({"demo": True} if mode == "demo" else {"auto_approve": {"G4"}})
    )
    if mode == "stale":
        write_reference_image(ctx.character_dir(cid), {"wardrobe": "changed"})
    log = RunLog()
    _step(ctx, cid, "s4", RunOptions(**opts), {}, log, auto_review=True)
    assert ctx.state(cid).gate("G4").status == "AWAITING_HUMAN"
    assert ctx.state(cid).stage("s6").status == "PENDING"
    assert log.blocked == ["s4"] if mode == "stale" else log.waiting == ["G4"]
