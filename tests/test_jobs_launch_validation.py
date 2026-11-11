"""Direct/resumed SOURCE jobs validate only upcoming S3 judge use, without providers."""

import json

import pytest

from character_factory_poc.pipeline.origin import write_origin
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.events import EventHub
from character_factory_poc.web.jobs import Job, JobManager
from character_factory_poc.web.settings import load_settings

TEXT = '[providers.text]\nadapter="vertex_openai"\nmodel="synthetic-text"\n'
JUDGE = '[providers.judge]\nadapter="openai_compat"\nmodel="other/synthetic"\n'


def manager(tmp_path, *, status="PENDING", origin="SOURCE", config=TEXT):
    config_path = tmp_path / "web-config.toml"
    config_path.write_text(config + '\n[orchestrator]\nauto_resume=true\nresume_until="sx"\n')
    # Verify the guard uses the selected web configuration, not the valid CLI default.
    (tmp_path / "factory.toml").write_text(TEXT + JUDGE)
    folder = tmp_path / "runs/characters/synthetic"
    folder.mkdir(parents=True)
    write_origin(folder, origin, auto_review=True)
    (folder / "state.json").write_text(
        json.dumps(
            dict(
                schemaVersion="state-v1",
                subjectId="synthetic",
                stages={"s3": {"status": status}},
                gates={"G3": {"status": "APPROVED" if status == "APPROVED" else "PENDING"}},
            )
        )
    )
    return JobManager(tmp_path, load_settings(tmp_path, config_path), EventHub())


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "CHECK_FAILED", "REJECTED"])
@pytest.mark.parametrize("target", ["G3", "s8c"])
def test_direct_submit_rejects_missing_judge_before_enqueuing(
    tmp_path, monkeypatch, status, target
):
    jobs = manager(tmp_path, status=status)
    started = []
    monkeypatch.setattr("threading.Thread.start", lambda thread: started.append(thread))
    with pytest.raises(WebError, match="검토 모델이 준비되지 않았어요") as error:
        jobs.submit("synthetic", until=target)
    assert error.value.status == 503
    assert started == [] and jobs.list() == []


@pytest.mark.parametrize("trigger", ["manual", "videos-with-chat"])
def test_worker_rechecks_config_before_any_pipeline_call(tmp_path, monkeypatch, trigger):
    jobs = manager(tmp_path)
    called = []

    def pipeline(*args):
        called.append(True)
        raise AssertionError("preflight must precede pipeline execution")

    monkeypatch.setattr("character_factory_poc.web.jobs.run_until", pipeline)
    job = Job(
        "job-test",
        "synthetic",
        until="G5b" if trigger == "videos-with-chat" else "G6",
        trigger=trigger,
    )
    with pytest.raises(WebError, match="검토 모델이 준비되지 않았어요"):
        jobs._run_default(job, object())
    assert called == []


def test_gate_resume_checks_judge_before_enqueuing(tmp_path, monkeypatch):
    jobs = manager(tmp_path)
    started = []
    monkeypatch.setattr("threading.Thread.start", lambda thread: started.append(thread))
    with pytest.raises(WebError, match="검토 모델이 준비되지 않았어요"):
        jobs.request_resume("synthetic")
    assert started == [] and jobs.list() == []


@pytest.mark.parametrize(
    "target,status,trigger,origin",
    [
        ("s0", "PENDING", "manual", "SOURCE"),
        ("G0", "PENDING", "manual", "SOURCE"),
        ("G5b", "PENDING", "videos", "SOURCE"),
        ("s8c", "APPROVED", "videos-with-chat", "SOURCE"),
        ("s8c", "AWAITING_HUMAN", "manual", "SOURCE"),
        ("s8c", "SKIPPED", "manual", "SOURCE"),
        ("G6", "PENDING", "manual", "CREATED"),
    ],
)
def test_jobs_without_upcoming_source_s3_do_not_require_judge(
    tmp_path,
    monkeypatch,
    target,
    status,
    trigger,
    origin,
):
    jobs = manager(tmp_path, status=status, origin=origin)
    started = []
    monkeypatch.setattr("threading.Thread.start", lambda thread: started.append(thread))
    result = jobs.submit("synthetic", until=target, trigger=trigger)
    assert result["status"] == "queued" and len(started) == 1


@pytest.mark.parametrize("config", ["", TEXT + JUDGE])
def test_fake_and_paired_real_configurations_are_allowed(tmp_path, monkeypatch, config):
    jobs = manager(tmp_path, config=config)
    monkeypatch.setattr("threading.Thread.start", lambda thread: None)
    assert jobs.submit("synthetic", until="s8c")["status"] == "queued"
