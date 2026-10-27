"""워크숍 자동 재개와 유료 단계 실행 확인 (D-0049, LLD §6.7)."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from character_factory_poc.common.config import load_config
from character_factory_poc.pipeline.orchestrator import RunLog, RunOptions, run_until
from character_factory_poc.web import create_app
from character_factory_poc.web.events import EventHub
from character_factory_poc.web.jobs import JobManager
from character_factory_poc.web.settings import load_settings
from tests import test_offline_pipeline as flow
from tests.support.web_gates import answer_for

ORCH = '\n[orchestrator]\nmax_parallel = 3\nauto_resume = true\nresume_until = "sx"\n'


def _wait_idle(client: TestClient, cid: str, timeout: float = 30.0) -> list[dict]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        data = client.get(f"/api/characters/{cid}").json()
        if data["job"] is None:
            return data["jobs"]
        time.sleep(0.05)
    raise AssertionError("작업이 끝나지 않았다")


def _app_for(root: Path, ctx, opt_extra: dict):
    holder: dict = {}

    def runner(job, stream) -> RunLog:
        jobs = holder["app"].state.jobs
        return run_until(ctx, job.character_id, jobs.run_options(job, stream, **opt_extra))

    app = create_app(root, runner=runner)
    holder["app"] = app
    return app


def _start(root: Path, extra_toml: str = ORCH):
    ctx, cid = flow.setup(root, "female")
    with open(root / "factory.toml", "a", encoding="utf-8") as f:
        f.write(extra_toml)
    ctx.config = load_config(root)
    extra = {
        "ranking": flow.ranking_for("female"),
        "seed": flow.SEED,
        "voice_probes": list(flow.PROBES),
    }
    run_until(ctx, cid, RunOptions(until="sx", **extra))  # 사람이 처음 한 번 시작했다
    assert ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"
    return ctx, cid, extra


def _decide(client: TestClient, cid: str, gate: str) -> dict:
    items = client.get(f"/api/characters/{cid}/gates/{gate}").json()["items"]
    res = client.post(f"/api/characters/{cid}/gates/{gate}/decision", json=answer_for(gate, items))
    assert res.status_code == 200, res.text
    return res.json()


def test_gate_decision_resumes_the_next_wave(tmp_path: Path) -> None:
    tmp_path = tmp_path / "f"
    ctx, cid, extra = _start(tmp_path)
    with TestClient(_app_for(tmp_path, ctx, extra)) as client:
        body = _decide(client, cid, "G1")
        assert body["resumeJob"]["trigger"] == "gate"
        jobs = _wait_idle(client, cid)
    state = ctx.state(cid)
    assert state.stage("s2").status == "APPROVED"
    assert state.gate("G3").status == "AWAITING_HUMAN"
    assert state.gate("G5").status == "AWAITING_HUMAN"
    assert jobs[0]["status"] == "succeeded" and jobs[0]["until"] == "sx"


def test_no_resume_when_auto_resume_is_off(tmp_path: Path) -> None:
    tmp_path = tmp_path / "f"
    ctx, cid, extra = _start(tmp_path, extra_toml="\n[orchestrator]\nauto_resume = false\n")
    with TestClient(_app_for(tmp_path, ctx, extra)) as client:
        body = _decide(client, cid, "G1")
        assert body["resumeJob"] is None
    assert ctx.state(cid).stage("s2").status == "PENDING"


def test_paid_stage_waits_for_confirmation_then_runs(tmp_path: Path) -> None:
    tmp_path = tmp_path / "f"
    paid = (
        '\n[providers.video]\nadapter = "xai_video"\nmodel = "grok-video"\n'
        'paid = true\n[providers.video.price_per_second."grok-video"]\n"720p" = 0.05\n'
    )
    ctx, cid, extra = _start(tmp_path, ORCH + paid)
    video = ctx._video
    with TestClient(_app_for(tmp_path, ctx, extra)) as client:
        _decide(client, cid, "G1")
        _wait_idle(client, cid)
        detail = client.get(f"/api/characters/{cid}").json()
        assert detail["held"] == [{"stage": "s5", "providers": ["video: xai_video/grok-video"]}]
        assert ctx.state(cid).stage("s5").status == "PENDING"
        assert video.submits == []  # 확인 전 영상 호출 0회
        assert ctx.state(cid).gate("G3").status == "AWAITING_HUMAN"  # 다른 갈래는 진행
        job = {"characterId": cid, "action": "run", "confirm": ["s5"]}
        res = client.post("/api/jobs", json=job)
        assert res.status_code == 202, res.text
        jobs = _wait_idle(client, cid)
        assert jobs[0]["status"] == "succeeded", jobs[0]["error"]
        assert client.get(f"/api/characters/{cid}").json()["held"] == []
    assert ctx.state(cid).gate("G5").status == "AWAITING_HUMAN"
    assert video.submits


def test_decision_during_a_running_job_runs_once_more(tmp_path: Path) -> None:
    char = tmp_path / "runs" / "characters" / "c1"
    char.mkdir(parents=True)
    (char / "state.json").write_text(json.dumps({"schemaVersion": "state-v1", "subjectId": "c1"}))
    (tmp_path / "factory.toml").write_text(ORCH, encoding="utf-8")
    gate = threading.Event()
    calls: list[str] = []

    def runner(job, stream) -> RunLog:
        calls.append(job.trigger)
        if len(calls) == 1:
            assert gate.wait(timeout=5)
        return RunLog()

    jobs = JobManager(tmp_path, load_settings(tmp_path, None), EventHub(), runner=runner)
    first = jobs.request_resume("c1")
    assert first is not None and first["trigger"] == "gate"
    assert jobs.request_resume("c1") is None  # 돌고 있으면 표시만 남긴다
    gate.set()
    end = time.monotonic() + 10
    while time.monotonic() < end and (len(calls) < 2 or jobs.active_for("c1")):
        time.sleep(0.02)
    assert calls == ["gate", "gate"]
    assert jobs.active_for("c1") is None
