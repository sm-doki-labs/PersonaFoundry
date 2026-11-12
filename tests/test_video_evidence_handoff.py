"""Authorized videos overlap prompt preparation; G6 still requires real review."""

import json
import time
from threading import Event

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline import orchestrator
from character_factory_poc.pipeline.origin import VIDEO_STAGES, stage_def, write_video_tier
from character_factory_poc.web.app import create_app
from tests.support.web_gates import trait_sheet_for
from tests.test_chapter_start import _start
from tests.test_evidence_pipeline import candidate
from tests.test_twin_s3 import _answer, _ready


def setup(tmp_path, monkeypatch, *, auto_resume=False):
    (tmp_path / "factory.toml").write_text(
        '[providers.demo_chat]\nadapter="fake"\nmodel="synthetic"\n'
        f'[orchestrator]\nauto_resume={str(auto_resume).lower()}\nresume_until="sx"\n'
    )
    ctx, model, cid = _ready(tmp_path)
    root = ctx.character_dir(cid)
    origin = root / "origin.json"
    origin.write_text(json.dumps(read_json(origin) | {"autoReview": True}))
    write_video_tier(root, "light")

    def answer(req):
        return {
            "s3-twin": _answer,
            "s7": lambda req: trait_sheet_for(ctx, cid),
            "s8": candidate,
            "s8c": lambda req: _start().model_dump() | {"characterId": cid},
        }[req.stage](req)

    model.add("AGENT", answer)
    monkeypatch.setattr("character_factory_poc.web.jobs.Context", lambda **kw: ctx)
    video_runs = []

    original = orchestrator._stage_runners

    def runners(context, character, options):
        out = original(context, character, options)

        def video_stage(sid):
            def run():
                # Keep orchestration, evidence and review real; only asset generation is synthetic.
                if sid == "s6":
                    video_runs.append(options)
                state = context.state(character)
                state.transition(sid, "RUNNING", rev="synthetic")
                gate = stage_def(context.character_dir(character), sid).gate
                if gate:
                    state.transition(sid, "AWAITING_HUMAN", rev="synthetic")
                    state.set_gate(gate, "APPROVED", "synthetic", None)
                state.transition(sid, "APPROVED", rev="synthetic")
                return context.character_dir(character)

            return run

        out.update({sid: video_stage(sid) for sid in VIDEO_STAGES})
        return out

    monkeypatch.setattr(orchestrator, "_stage_runners", runners)
    # Synthetic assets belong to the selected tier; revision/tier authorization remains real.
    monkeypatch.setattr(orchestrator, "_matches_video_scope", lambda *args: True)
    return ctx, cid, video_runs


def wait_idle(jobs, cid):
    deadline = time.monotonic() + 10
    while jobs.active_for(cid) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert jobs.active_for(cid) is None, jobs.list(cid)


def start(jobs, cid, *, video=True):
    return jobs.submit(
        cid,
        until="G5b" if video else "s8c",
        trigger="videos-with-chat" if video else "manual",
        confirm=list(VIDEO_STAGES) if video else [],
    )["jobId"]


def approve(client, cid, **extra):
    return client.post(
        f"/api/characters/{cid}/gates/G6/decision",
        json=dict(decision="APPROVE", reviewer="synthetic human", **extra),
    )


@pytest.mark.parametrize("auto_resume", [False, True])
@pytest.mark.parametrize("restart", [False, True])
def test_video_completes_while_review_waits_then_resumes_without_regeneration(
    tmp_path,
    monkeypatch,
    auto_resume,
    restart,
):
    ctx, cid, videos = setup(tmp_path, monkeypatch, auto_resume=auto_resume)
    app = create_app(tmp_path)
    jobs = app.state.jobs
    first = start(jobs, cid)
    wait_idle(jobs, cid)
    paused = jobs.get(first)
    assert paused["status"] == "succeeded", paused["error"]
    assert paused["stoppedAt"] == "G6" and paused["waiting"] == ["G6"]
    assert paused["blocked"] == paused["held"] == []
    assert len(videos) == 1
    assert ctx.state(cid).stage("s8c").status == "APPROVED"
    assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
    root = ctx.character_dir(cid)
    assert (root / "s8-chapters/cs1/samples.json").is_file()
    assert not (root / "s8-prompts/pv1/persona-version.json").exists()
    assert read_json(root / "video-job.json")["status"] != "failed"
    if restart:
        app = create_app(tmp_path)
        jobs = app.state.jobs
        assert jobs.get(first)["waiting"] == ["G6"]
    with TestClient(app) as client:
        denied = approve(client, cid)
        assert denied.status_code == 400
        assert ctx.state(cid).gate("G6").status == "AWAITING_HUMAN"
        assert len(videos) == 1
        accepted = approve(client, cid, evidenceReviewed=True)
        assert accepted.status_code == 200, accepted.text
        continuation = accepted.json()["resumeJob"]
        assert continuation is not None
        assert continuation["trigger"] == "videos-with-chat"
        assert continuation["until"] == "G5b"
        assert continuation["confirm"] == list(VIDEO_STAGES)
        wait_idle(jobs, cid)
        assert jobs.get(continuation["jobId"])["status"] == "succeeded"
    assert len(videos) == 1
    assert videos[0].videos_with_chat and videos[0].confirmed == set(VIDEO_STAGES)
    assert ctx.state(cid).gate("G5b").status == "APPROVED"
    assert not (root / "s8-chapters/cs2").exists()


@pytest.mark.parametrize("decision", ["REJECT", "REQUEST_CHANGES"])
def test_rejected_evidence_never_resumes_video(tmp_path, monkeypatch, decision):
    ctx, cid, videos = setup(tmp_path, monkeypatch)
    app = create_app(tmp_path)
    jobs = app.state.jobs
    first = start(jobs, cid)
    wait_idle(jobs, cid)
    assert jobs.get(first)["status"] == "succeeded"
    with TestClient(app) as client:
        result = client.post(
            f"/api/characters/{cid}/gates/G6/decision",
            json=dict(
                decision=decision,
                reviewer="synthetic human",
                reasons="revise evidence",
                requestedChanges=[dict(field="long", note="revise evidence")],
            ),
        )
        assert result.status_code == 200, result.text
        assert result.json()["resumeJob"] is None
    assert len(videos) == 1
    assert ctx.state(cid).gate("G6").status == "REJECTED"


@pytest.mark.parametrize("change", ["tier", "revision"])
def test_changed_scope_does_not_reuse_old_video_authorization(tmp_path, monkeypatch, change):
    ctx, cid, videos = setup(tmp_path, monkeypatch)
    app = create_app(tmp_path)
    jobs = app.state.jobs
    first = start(jobs, cid)
    wait_idle(jobs, cid)
    assert jobs.get(first)["status"] == "succeeded"
    if change == "tier":
        write_video_tier(ctx.character_dir(cid), "max")
        with TestClient(app) as client:
            result = approve(client, cid, evidenceReviewed=True)
            assert result.status_code == 200, result.text
            assert result.json()["resumeJob"] is None
    else:
        # A different revision's approval must not satisfy the paused job.
        ctx.state(cid).set_gate("G6", "APPROVED", "pv999", None)
        assert jobs.request_resume(cid) is None
    assert len(videos) == 1


def test_sample_failure_is_still_a_failure_and_cannot_resume_video(tmp_path, monkeypatch):
    ctx, cid, videos = setup(tmp_path, monkeypatch)

    def fail(*args):
        raise RuntimeError("synthetic sample failure")

    monkeypatch.setattr("character_factory_poc.common.demo_chat.run_samples", fail)
    app = create_app(tmp_path)
    jobs = app.state.jobs
    first = start(jobs, cid)
    wait_idle(jobs, cid)
    assert jobs.get(first)["status"] == "failed"
    assert ctx.state(cid).stage("s8c").status == "CHECK_FAILED"
    with TestClient(app) as client:
        result = approve(client, cid, evidenceReviewed=True)
        assert result.status_code == 200, result.text
        assert result.json()["resumeJob"] is None
    assert len(videos) == 1


def test_no_video_run_keeps_existing_manual_review_flow(tmp_path, monkeypatch):
    ctx, cid, videos = setup(tmp_path, monkeypatch)
    write_video_tier(ctx.character_dir(cid), "none")
    app = create_app(tmp_path)
    jobs = app.state.jobs
    first = start(jobs, cid, video=False)
    wait_idle(jobs, cid)
    assert jobs.get(first)["status"] == "succeeded"
    assert jobs.get(first)["stoppedAt"] == "s8c"
    assert jobs.get(first)["waiting"] == ["G6"]
    with TestClient(app) as client:
        result = approve(client, cid, evidenceReviewed=True)
        assert result.status_code == 200, result.text
        assert result.json()["resumeJob"] is None
    assert videos == []


def test_repeated_resume_does_not_duplicate_authorized_video(tmp_path, monkeypatch):
    ctx, cid, videos = setup(tmp_path, monkeypatch)
    from character_factory_poc.web import jobs as jobs_module

    original = jobs_module.run_until
    entered, release = Event(), Event()

    def run(context, character, options):
        if options.videos_with_chat and context.state(character).gate("G6").status == "APPROVED":
            entered.set()
            assert release.wait(5)
        return original(context, character, options)

    monkeypatch.setattr(jobs_module, "run_until", run)
    app = create_app(tmp_path)
    jobs = app.state.jobs
    first = start(jobs, cid)
    wait_idle(jobs, cid)
    assert jobs.get(first)["status"] == "succeeded"
    try:
        with TestClient(app) as client:
            result = approve(client, cid, evidenceReviewed=True)
            assert result.status_code == 200, result.text
            assert entered.wait(5)
            assert jobs.request_resume(cid) is None
            assert jobs.request_resume(cid) is None
    finally:
        release.set()
    wait_idle(jobs, cid)
    assert len(videos) == 1
    assert len(jobs.list(cid)) == 2


def test_tier_change_during_handoff_cannot_expand_authorization(tmp_path, monkeypatch):
    ctx, cid, videos = setup(tmp_path, monkeypatch)
    app = create_app(tmp_path)
    jobs = app.state.jobs
    first = start(jobs, cid)
    wait_idle(jobs, cid)
    assert jobs.get(first)["status"] == "succeeded"
    submit = jobs.submit

    def change_then_submit(*args, **kwargs):
        if kwargs.get("_resume_from"):
            write_video_tier(ctx.character_dir(cid), "max")
        return submit(*args, **kwargs)

    monkeypatch.setattr(jobs, "submit", change_then_submit)
    with TestClient(app) as client:
        result = approve(client, cid, evidenceReviewed=True)
        assert result.status_code == 200, result.text
    wait_idle(jobs, cid)
    assert len(videos) == 1


def test_gate_status_without_an_approval_record_does_not_resume(tmp_path, monkeypatch):
    ctx, cid, videos = setup(tmp_path, monkeypatch)
    jobs = create_app(tmp_path).state.jobs
    first = start(jobs, cid)
    wait_idle(jobs, cid)
    assert jobs.get(first)["status"] == "succeeded"
    ctx.state(cid).set_gate("G6", "APPROVED", "pv1", None)
    assert jobs.request_resume(cid) is None
    assert len(videos) == 1
