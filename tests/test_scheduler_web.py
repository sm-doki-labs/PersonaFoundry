"""The videos-with-chat job shares scheduling without expanding its authorization."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Event

import pytest

from character_factory_poc.pipeline import orchestrator
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import VIDEO_STAGES, write_origin, write_video_tier
from character_factory_poc.web.events import EventHub
from character_factory_poc.web.jobs import Job, JobManager
from character_factory_poc.web.settings import load_settings
from tests.test_run_waves import _approved, _opens


def test_web_combined_job_runs_video_and_prompt_together(tmp_path, monkeypatch):
    ctx = Context.load(tmp_path, execute=True)
    cid = "combined"
    write_origin(ctx.character_dir(cid), "SOURCE", auto_review=True)
    write_video_tier(ctx.character_dir(cid), "light")
    for sid, gate in (
        ("s0", "G0"),
        ("s2", "G1s"),
        ("s3", "G3"),
        ("s4a", "G4a"),
        ("s4b", "G4b"),
        ("s4", "G4"),
    ):
        _approved(ctx, cid, sid, gate)
    video_started, release_video, prompt_started = Event(), Event(), Event()

    def video():
        video_started.set()
        assert release_video.wait(5)
        return _opens(ctx, cid, "s6")()

    def traits():
        assert video_started.wait(5)
        return _opens(ctx, cid, "s7")()

    def prompt():
        prompt_started.set()
        return _opens(ctx, cid, "s8")()

    def chapter():
        _approved(ctx, cid, "s8c", None)
        return ctx.character_dir(cid)

    def approve(c, i, gate, *args):
        sid = {"G5b": "s6", "G6": "s8"}[gate]
        st = c.state(i)
        st.set_gate(gate, "APPROVED", "r1", "synthetic.json")
        st.transition(sid, "APPROVED", rev="r1")

    monkeypatch.setattr(orchestrator, "approve_gate", approve)
    monkeypatch.setattr(orchestrator, "approve_text_gate", approve)
    monkeypatch.setattr(
        orchestrator,
        "_stage_runners",
        lambda *a: {
            "s6": video,
            "s7": traits,
            "s8": prompt,
            "s8c": chapter,
            "s5": lambda: pytest.fail("intro video was not authorized"),
            "s10": lambda: pytest.fail("evaluation was not authorized"),
        },
    )
    monkeypatch.setattr("character_factory_poc.web.jobs.Context", lambda **kw: ctx)
    jobs = JobManager(tmp_path, load_settings(tmp_path, None), EventHub())
    job = Job("test", cid, until="G5b", trigger="videos-with-chat", confirm=list(VIDEO_STAGES))
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(jobs._run_default, job, StringIO())
        try:
            assert video_started.wait(2), "video must not wait for the whole prompt pipeline"
            assert prompt_started.wait(2)
        finally:
            release_video.set()
        log = future.result(timeout=5)
    assert log.stopped_at == "G5b"
    assert ctx.state(cid).stage("s8c").status == "APPROVED"
    assert ctx.state(cid).gate("G5b").status == "APPROVED"


@pytest.mark.parametrize("blocked_stage", ["s4a", "s6"])
def test_source_finalize_reaches_g6_review_while_authorized_video_finishes(
    tmp_path, monkeypatch, blocked_stage
):
    import cv2
    import numpy as np
    from fastapi.testclient import TestClient

    from character_factory_poc.pipeline.origin import stage_def
    from character_factory_poc.providers.fake import FakeTextModel
    from character_factory_poc.web.app import create_app
    from tests.support.web_gates import trait_sheet_for
    from tests.test_chapter_start import _start
    from tests.test_evidence_pipeline import candidate
    from tests.test_source_intake import put
    from tests.test_source_s0 import _good_digest
    from tests.test_twin_flow import _pack
    from tests.test_twin_s3 import _answer
    from tests.test_video_evidence_handoff import wait_idle

    (tmp_path / "factory.toml").write_text(
        '[providers.demo_chat]\nadapter="fake"\nmodel="synthetic"\n'
    )
    app = create_app(tmp_path)
    client = TestClient(app)
    ctx = Context.load(tmp_path, execute=True)
    cid = client.post(
        "/api/sources/drafts",
        json={
            "displayName": "엄마",
            "subjectKind": "PRIVATE_PERSON",
            "videoTier": "light",
            "signaturePose": {"title": "인사", "motion": "손을 흔든다"},
            "knownFacts": {"age": "41", "gender": "female", "job": "제본사", "background": "가족"},
        },
    ).json()["characterId"]
    url = f"/api/sources/{cid}"
    text_path = _pack(tmp_path).parent / "mom.txt"
    target = put(client, url, text_path.read_bytes())
    assert client.post(
        target + "/complete",
        json={
            "textId": "a1",
            "kind": "KAKAO_EXPORT",
            "subjectSpeaker": "엄마",
            "userSpeaker": "나",
        },
    ).is_success
    _, png = cv2.imencode(".png", np.zeros((32, 32, 3), dtype=np.uint8))
    data = png.tobytes()
    photo = client.post(
        url + "/files",
        json={
            "filename": "synthetic.png",
            "size": len(data),
            "contentType": "image/png",
        },
    ).json()
    assert client.put(photo["upload"]["url"], content=data).is_success
    assert client.post(url + "/files/" + photo["fileId"] + "/complete", json={}).is_success

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
    original = orchestrator._stage_runners
    video_started, release_video, chapter_done = Event(), Event(), Event()

    def runners(context, character, options):
        out = original(context, character, options)
        chapter = out["s8c"]

        def chapters():
            result = chapter()
            chapter_done.set()
            return result

        def asset(sid):
            def generate():
                if sid == blocked_stage:
                    video_started.set()
                    assert release_video.wait(5)
                gate = stage_def(context.character_dir(character), sid).gate
                _approved(context, character, sid, gate)
                return context.character_dir(character)

            return generate

        out.update({sid: asset(sid) for sid in VIDEO_STAGES})
        out["s8c"] = chapters
        return out

    monkeypatch.setattr(orchestrator, "_stage_runners", runners)
    response = client.post(url + "/finalize")
    assert response.is_success, response.text
    job_id = response.json()["jobId"]
    try:
        assert video_started.wait(3)
        assert chapter_done.wait(3), "S8c must finish without waiting for video"
        assert app.state.jobs.get(job_id)["status"] == "running"
    finally:
        release_video.set()
    wait_idle(app.state.jobs, cid)
    job = app.state.jobs.get(job_id)
    assert job["status"] == "succeeded", job["error"]
    assert job["trigger"] == "videos-with-chat"
    assert job["waiting"] == ["G6"] and job["stoppedAt"] == "G6"
    assert ctx.state(cid).gate("G5b").status == "APPROVED"
    assert ctx.state(cid).stage("s8c").status == "APPROVED"
    assert all(ctx.state(cid).stage(sid).status == "PENDING" for sid in ("s9h", "s10", "s11", "sx"))
    assert not (ctx.character_dir(cid) / "s8-prompts/pv1/persona-version.json").exists()


def test_video_only_job_keeps_its_existing_scope(tmp_path, monkeypatch):
    from character_factory_poc.pipeline.orchestrator import RunLog

    ctx = Context.load(tmp_path, execute=True)
    cid = "video-only"
    write_origin(ctx.character_dir(cid), "SOURCE", auto_review=True)
    write_video_tier(ctx.character_dir(cid), "light")
    monkeypatch.setattr("character_factory_poc.web.jobs.Context", lambda **kw: ctx)
    options_seen = []

    def run(context, character, options):
        options_seen.append(options)
        context.state(character).set_gate("G5b", "APPROVED", "r1", None)
        return RunLog(stopped_at="G5b")

    monkeypatch.setattr("character_factory_poc.web.jobs.run_until", run)
    jobs = JobManager(tmp_path, load_settings(tmp_path, None), EventHub())
    log = jobs._run_default(Job("test", cid, until="G5b", trigger="videos"), StringIO())
    assert log.stopped_at == "G5b"
    assert len(options_seen) == 1
    assert options_seen[0].video_only and not options_seen[0].videos_with_chat
