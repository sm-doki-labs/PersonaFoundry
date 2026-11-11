"""워크숍 웹앱 API 테스트 (PoC 계획서 §6, LLD §6.5).

합성 runs 폴더와 가짜 공급자만 쓴다. 네트워크도 실제 공급자도 부르지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.pipeline.graph import STAGES
from character_factory_poc.pipeline.orchestrator import RunLog
from character_factory_poc.web import create_app
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.events import EventHub, format_sse
from character_factory_poc.web.jobs import JobManager
from character_factory_poc.web.settings import load_settings

CID = "cf-20261027-seoha"
BRIEF = "bf-20261027-seoha"

FACTORY_TOML = """
[providers.text]
adapter = "fake"

[providers.judge]
adapter = "fake"

[providers.image]
adapter = "fake"

[providers.video]
adapter = "fake"

[web]
port = 8765
jobs_dir = "work/web-jobs"
sse_heartbeat_s = 0.5
default_until = "G6"
"""


def _write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _state() -> dict:
    return {
        "schemaVersion": "state-v1",
        "subjectId": CID,
        "stages": {
            "s1": {"status": "AWAITING_HUMAN", "currentRev": "rf1", "attempts": 1},
            "s3": {"status": "AWAITING_HUMAN", "currentRev": "pr1", "attempts": 1},
        },
        "gates": {
            "G1": {"status": "AWAITING_HUMAN", "rev": "rf1", "recordRef": None},
            "G3": {"status": "AWAITING_HUMAN", "rev": "pr1", "recordRef": None},
        },
    }


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "factory"
    root.mkdir()
    _write_text(root / "factory.toml", FACTORY_TOML)
    char = root / "runs" / "characters" / CID
    _write_text(char / "state.json", json.dumps(_state(), ensure_ascii=False, indent=2))
    _write_text(
        char / "s1-reference" / "rf1" / "report.json",
        json.dumps({"schemaVersion": "reference-report-v2"}),
    )
    _write_text(char / "s1-reference" / "rf1" / "previews.json", "[]")
    _write_text(
        char / "s1-reference" / "rf1" / "gate-G1.html",
        "<!doctype html><title>G1</title>",
    )
    (char / "s1-reference" / "rf1" / "previews").mkdir(parents=True, exist_ok=True)
    (char / "s1-reference" / "rf1" / "previews" / "p1.png").write_bytes(b"PNG")
    _write_text(
        char / "s3-plan" / "pr1" / "plan.json",
        json.dumps({"name": "윤하린", "job": "책방 직원", "age": 24}, ensure_ascii=False),
    )
    brief = root / "runs" / "briefs" / BRIEF
    _write_text(brief / "brief.md", "# 브리프")
    _write_text(brief / "probes.txt", "안녕")
    _write_text(root / "outside.txt", "공장 밖 파일")
    return root


def test_health_and_projects_read_real_runs(tmp_path):
    root = make_root(tmp_path)
    with TestClient(create_app(root)) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        assert body["status"] == "ok"
        assert body["root"] == str(root.resolve())
        assert body["config"]["port"] == 8765
        assert body["counts"] == {"characters": 1, "briefs": 1, "pendingGates": 2}

        data = client.get("/api/projects").json()
        assert [c["id"] for c in data["characters"]] == [CID]
        char = data["characters"][0]
        assert char["name"] == "윤하린"
        assert char["persona"]["job"] == "책방 직원"
        assert char["progress"]["total"] == sum(1 for s in STAGES.values() if s.implemented)
        assert {g["id"] for g in char["pendingGates"]} == {"G1", "G3"}
        stages = {s["id"]: s for s in char["stages"]}
        assert stages["s1"]["status"] == "AWAITING_HUMAN"
        assert stages["s1"]["gateStatus"] == "AWAITING_HUMAN"
        assert stages["s9"]["implemented"] is True
        assert data["totals"]["pendingGates"] == 2

        brief = data["briefs"][0]
        assert brief["id"] == BRIEF
        assert brief["hasBrief"] is True
        assert brief["hasProbes"] is True
        assert {f["path"] for f in brief["files"]} == {"brief.md", "probes.txt"}


def test_character_detail_keeps_state_and_lanes(tmp_path):
    root = make_root(tmp_path)
    with TestClient(create_app(root)) as client:
        detail = client.get("/api/characters/" + CID).json()
        assert detail["state"]["subjectId"] == CID
        assert detail["state"]["gates"]["G1"]["rev"] == "rf1"
        lanes = {lane["id"]: lane for lane in detail["lanes"]}
        assert lanes["appearance"]["status"] == "gate"
        assert lanes["appearance"]["pendingGates"] == ["G1"]
        assert lanes["data"]["implemented"] is True
        assert [g["id"] for g in detail["pendingGates"]] == ["G1", "G3"]
        assert client.get("/api/characters/not-there").status_code == 404


def test_corrupt_state_does_not_break_listing(tmp_path):
    root = make_root(tmp_path)
    broken = root / "runs" / "characters" / "cf-20261027-broken"
    _write_text(broken / "state.json", "{깨진 JSON")
    with TestClient(create_app(root)) as client:
        data = client.get("/api/projects").json()
        assert [c["id"] for c in data["characters"]] == ["cf-20261027-broken", CID]
        errors = {c["id"]: c["stateError"] for c in data["characters"]}
        assert errors["cf-20261027-broken"]
        assert errors[CID] is None


def test_gate_view_lists_files_previews_and_records(tmp_path):
    root = make_root(tmp_path)
    with TestClient(create_app(root)) as client:
        view = client.get("/api/characters/" + CID + "/gates/G1").json()
        assert view["title"] == "얼굴 고르기"
        assert view["status"] == "AWAITING_HUMAN"
        assert view["rev"] == "rf1"
        paths = {f["path"] for f in view["files"]}
        assert "s1-reference/rf1/gate-G1.html" in paths
        assert "s1-reference/rf1/previews/p1.png" in paths
        page = next(f for f in view["previews"] if f["kind"] == "html")
        assert page["url"] == "/api/files/" + CID + "/s1-reference/rf1/gate-G1.html"
        assert view["records"] == []
        assert client.get("/api/characters/" + CID + "/gates/G99").status_code == 404


def test_file_api_serves_only_character_folder(tmp_path):
    root = make_root(tmp_path)
    with TestClient(create_app(root)) as client:
        ok = client.get("/api/files/" + CID + "/s1-reference/rf1/gate-G1.html")
        assert ok.status_code == 200
        assert ok.headers["content-type"].startswith("text/html")
        assert "G1" in ok.text

        escapes = [
            "/api/files/" + CID + "/../factory.toml",
            "/api/files/" + CID + "/%2e%2e/%2e%2e/factory.toml",
            "/api/files/" + CID + "/..%2f..%2ffactory.toml",
            "/api/files/" + CID + "/%2Fetc%2Fpasswd",
        ]
        for url in escapes:
            res = client.get(url)
            assert res.status_code in {400, 404}, url
            assert "secret" not in res.text
        assert client.get("/api/files/" + CID + "/missing.txt").status_code == 404


def test_file_api_blocks_symlink_escape(tmp_path):
    root = make_root(tmp_path)
    char = root / "runs" / "characters" / CID
    os.symlink(root / "outside.txt", char / "leak.txt")
    with TestClient(create_app(root)) as client:
        res = client.get("/api/files/" + CID + "/leak.txt")
        assert res.status_code == 400


def test_gate_decision_uses_cli_path_and_records(tmp_path):
    root = make_root(tmp_path)
    with TestClient(create_app(root)) as client:
        answer = {"decision": "APPROVE", "reviewer": "test", "reasons": "확인"}
        res = client.post("/api/characters/" + CID + "/gates/G3/decision", json=answer)
        assert res.status_code == 200, res.text
        data = res.json()
        assert data["recordRef"] == "gates/G3-pr1.json"
        assert data["state"]["gates"]["G3"]["status"] == "APPROVED"
        assert data["state"]["stages"]["s3"]["status"] == "APPROVED"

        record_path = root / "runs" / "characters" / CID / "gates" / "G3-pr1.json"
        record = json.loads(record_path.read_text("utf-8"))
        assert record["decision"] == "APPROVE"
        assert record["reviewer"] == "test"
        assert record["shownArtifacts"][0]["ref"] == "s3-plan/pr1/plan.json"

        view = client.get("/api/characters/" + CID + "/gates/G3").json()
        assert view["status"] == "APPROVED"
        assert len(view["records"]) == 1
        assert view["records"][0]["file"] == "gates/G3-pr1.json"

        again = client.post("/api/characters/" + CID + "/gates/G3/decision", json=answer)
        assert again.status_code == 409
        missing = client.post("/api/characters/" + CID + "/gates/G1/decision", json={})
        assert missing.status_code == 400
        bad = client.post(
            "/api/characters/" + CID + "/gates/G1/decision",
            json={"decision": "MAYBE", "reviewer": "test"},
        )
        assert bad.status_code == 400
        unknown = client.post("/api/characters/" + CID + "/gates/G99/decision", json=answer)
        assert unknown.status_code == 404
        # G7은 연결됐다(H 갈래). 대기 중이 아니면 관문 경로가 409로 거절한다
        not_waiting = client.post("/api/characters/" + CID + "/gates/G7/decision", json=answer)
        assert not_waiting.status_code == 409


def test_job_queue_runs_orchestrator_with_fake_providers(tmp_path):
    root = make_root(tmp_path)
    with TestClient(create_app(root)) as client:
        res = client.post("/api/jobs", json={"characterId": CID, "action": "run", "until": "G3"})
        assert res.status_code == 202, res.text
        started = res.json()
        assert started["status"] in {"queued", "running"}
        assert started["until"] == "G3"

        deadline = time.time() + 20
        job = started
        while time.time() < deadline:
            job = client.get("/api/jobs/" + started["jobId"]).json()
            if job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.05)
        assert job["status"] == "succeeded", job
        assert job["result"]["stoppedAt"] == "G3"
        assert "G3" in job["result"]["waiting"]
        assert job["ranStages"] == []  # 이미 검토 중인 결과를 다시 만들지 않는다
        assert job["log"], job
        assert any("s3" in line for line in job["log"])
        assert client.get("/api/jobs").json()["jobs"]
        assert client.get("/api/jobs/job-missing").status_code == 404
        assert client.post("/api/jobs", json={"characterId": "nope"}).status_code == 404
        assert (
            client.post("/api/jobs", json={"characterId": CID, "until": "G99"}).status_code == 400
        )


def test_one_job_per_character(tmp_path):
    root = make_root(tmp_path)
    conf = load_settings(root)
    manager = JobManager(root, conf, EventHub(), runner=_blocking_runner())

    first = manager.submit(CID, "run", "G3")
    assert _runner_state["started"].wait(5)
    with pytest.raises(WebError) as err:
        manager.submit(CID, "run", "G3")
    assert err.value.status == 409

    _runner_state["release"].set()
    deadline = time.time() + 5
    while time.time() < deadline:
        if manager.get(first["jobId"])["status"] == "succeeded":
            break
        time.sleep(0.02)
    assert manager.get(first["jobId"])["status"] == "succeeded"

    with pytest.raises(WebError) as err:
        manager.submit(CID, "learn", "G3")
    assert err.value.status == 400


_runner_state: dict = {}


def _blocking_runner():
    _runner_state["started"] = threading.Event()
    _runner_state["release"] = threading.Event()

    def runner(job, stream):
        stream.write("가짜 실행")
        _runner_state["started"].set()
        _runner_state["release"].wait(5)
        return RunLog(stopped_at="G3")

    return runner


def test_sse_starts_with_hello_event(tmp_path):
    root = make_root(tmp_path)
    with TestClient(create_app(root)) as client:
        with client.stream("GET", "/api/events?limit=1") as res:
            assert res.status_code == 200
            assert res.headers["content-type"].startswith("text/event-stream")
            lines = [line for line in res.iter_lines() if line]
        assert lines[0] == "event: hello"
        payload = json.loads(lines[1].removeprefix("data: "))
        assert payload["type"] == "hello"
        assert payload["counts"]["characters"] == 1


def test_event_hub_filters_by_character_and_keeps_one_line_frames():
    hub = EventHub()

    async def scenario():
        scoped = hub.subscribe("cf-a")
        everything = hub.subscribe()
        hub.publish("state", {"type": "state", "characterId": "cf-a"}, "cf-a")
        hub.publish("state", {"type": "state", "characterId": "cf-b"}, "cf-b")
        hub.publish("hello", {"type": "hello"})
        await asyncio.sleep(0.05)
        scoped_events = [scoped.queue.get_nowait() for _ in range(scoped.queue.qsize())]
        all_events = [everything.queue.get_nowait() for _ in range(everything.queue.qsize())]
        hub.unsubscribe(scoped)
        hub.unsubscribe(everything)
        return scoped_events, all_events

    scoped_events, all_events = asyncio.run(scenario())
    assert [event["event"] for event in scoped_events] == ["state", "hello"]
    assert scoped_events[0]["data"]["characterId"] == "cf-a"
    assert [event["event"] for event in all_events] == ["state", "state", "hello"]
    assert hub.subscriber_count() == 0

    frame = format_sse("state", {"text": "줄" + chr(10) + "바꿈"})
    assert frame.startswith("event: state" + chr(10))
    assert frame.count(chr(10) + chr(10)) == 1
