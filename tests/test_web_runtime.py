"""Real runtime graph and creator API (plan 2026-10-30, backend A).

The tests use a temporary factory root and the real JobManager._run_default path. run_until is
replaced only to capture RunOptions; no provider, network, or model call happens here.
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from character_factory_poc.common.ids import character_id
from character_factory_poc.pipeline.graph import GATES, STAGES
from character_factory_poc.pipeline.orchestrator import RunLog
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.events import EventHub
from character_factory_poc.web.jobs import Job, JobManager
from character_factory_poc.web.runtime import install_runtime_routes
from character_factory_poc.web.settings import load_settings

TOML = """
[providers.text]
adapter = "fake"

[providers.judge]
adapter = "fake"

[providers.image]
adapter = "fake"

[providers.video]
adapter = "fake"

[web]
jobs_dir = "work/web-jobs"
default_until = "G6"
"""

BRIEF = "말수가 적고 도구를 고쳐 쓰는 성인 정비사."


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "factory"
    root.mkdir()
    (root / "factory.toml").write_text(TOML, encoding="utf-8")
    return root


def client_for(root: Path) -> tuple[TestClient, JobManager]:
    conf = load_settings(root)
    manager = JobManager(root, conf, EventHub())
    app = FastAPI()

    @app.exception_handler(WebError)
    async def _web_error(_request: Request, exc: WebError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    install_runtime_routes(app, root, conf, manager)
    return TestClient(app), manager


def create(client: TestClient, slug: str = "runtime-one", brief: str = BRIEF):
    return client.post("/api/runtime/characters", json={"slug": slug, "brief": brief})


def test_graph_is_stages_with_gates_and_both_late_gates(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    client, _ = client_for(root)
    with client:
        response = client.get("/api/runtime/graph")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "live"
    assert [stage["id"] for stage in body["stages"]] == list(STAGES)
    for row in body["stages"]:
        source = STAGES[row["id"]]
        assert row["name"] == source.name
        assert row["deps"] == sorted(source.deps)
        assert row["needs"] == sorted(source.needs)
        assert row["after"] == sorted(source.after)
        assert row["gate"] == source.gate
        assert row["implemented"] is source.implemented

    gates = {gate["id"]: gate for gate in body["gates"]}
    assert list(gates) == list(GATES)
    assert {"G7a", "G4b"} <= set(gates)
    assert gates["G4b"]["stage"] == "s4b"
    assert gates["G7a"]["stage"] == "s9s"
    assert gates["G7a"]["title"] == "데이터 샘플 검토"


def test_creator_request_writes_state_and_immutable_brief_without_a_job(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    cid = character_id("runtime-one")
    client, manager = client_for(root)
    with client:
        response = create(client)

    assert response.status_code == 201, response.text
    assert response.json() == {"characterId": cid}
    char = root / "runs" / "characters" / cid
    brief = char / "creator-input" / "brief-r1.md"
    assert brief.read_text(encoding="utf-8") == BRIEF
    state = json.loads((char / "state.json").read_text(encoding="utf-8"))
    assert state["schemaVersion"] == "state-v1"
    assert state["subjectId"] == cid
    assert manager.list() == []


def test_duplicate_slug_is_409_and_preserves_first_artifacts(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    client, _ = client_for(root)
    with client:
        first = create(client)
        cid = first.json()["characterId"]
        char = root / "runs" / "characters" / cid
        (char / "keep.txt").write_text("first", encoding="utf-8")
        original_state = (char / "state.json").read_bytes()

        second = create(client, brief="두 번째 브리프")

    assert first.status_code == 201
    assert second.status_code == 409
    assert (char / "keep.txt").read_text(encoding="utf-8") == "first"
    assert (char / "creator-input" / "brief-r1.md").read_text(encoding="utf-8") == BRIEF
    assert (char / "state.json").read_bytes() == original_state


def test_simultaneous_same_slug_requests_create_one_complete_character(tmp_path: Path) -> None:
    root = make_root(tmp_path)

    def post() -> int:
        client, _ = client_for(root)
        with client:
            return create(client, slug="runtime-race").status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: post(), range(2)))

    assert statuses == [201, 409]
    cid = character_id("runtime-race")
    char = root / "runs" / "characters" / cid
    assert (char / "creator-input" / "brief-r1.md").read_text(encoding="utf-8") == BRIEF
    state = json.loads((char / "state.json").read_text(encoding="utf-8"))
    assert state["subjectId"] == cid


@pytest.mark.parametrize("slug", ["../escape", "Upper", "", "has space", "-leading"])
def test_invalid_slug_is_rejected_before_creating_a_character(tmp_path: Path, slug: str) -> None:
    root = make_root(tmp_path)
    client, _ = client_for(root)
    with client:
        response = create(client, slug=slug)

    assert response.status_code == 400
    assert not (root / "runs" / "characters").exists()


@pytest.mark.parametrize("brief", ["", "x" * 20_001])
def test_empty_or_oversized_brief_is_rejected_without_a_visible_character(
    tmp_path: Path, brief: str
) -> None:
    root = make_root(tmp_path)
    client, _ = client_for(root)
    with client:
        response = create(client, brief=brief)

    assert response.status_code == 400
    assert not (root / "runs" / "characters").exists()


def test_exactly_20_000_character_brief_is_accepted(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    brief = "가" * 20_000
    client, _ = client_for(root)
    with client:
        response = create(client, slug="runtime-boundary", brief=brief)

    assert response.status_code == 201, response.text
    cid = response.json()["characterId"]
    assert (root / "runs" / "characters" / cid / "creator-input" / "brief-r1.md").read_text(
        encoding="utf-8"
    ) == brief


def test_character_directory_symlink_is_a_conflict_and_outside_stays_clean(
    tmp_path: Path,
) -> None:
    root = make_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    chars = root / "runs" / "characters"
    chars.mkdir(parents=True)
    os.symlink(outside, chars / character_id("runtime-link"))
    client, _ = client_for(root)
    with client:
        response = create(client, slug="runtime-link")

    assert response.status_code == 409
    assert list(outside.iterdir()) == []


def test_characters_root_symlink_escape_is_rejected(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    outside = tmp_path / "outside-root"
    outside.mkdir()
    (root / "runs").mkdir()
    os.symlink(outside, root / "runs" / "characters")
    client, _ = client_for(root)
    with client:
        response = create(client, slug="runtime-root-link")

    assert response.status_code == 400
    assert list(outside.iterdir()) == []


def _job(cid: str) -> Job:
    return Job(job_id="job-test", character_id=cid, until="G6")


def _capture_run_until(monkeypatch) -> dict:
    captured: dict = {}

    def fake(ctx, cid, opt):
        captured["characterId"] = cid
        captured["options"] = opt
        return RunLog(stopped_at="G6")

    monkeypatch.setattr("character_factory_poc.web.jobs.run_until", fake)
    return captured


def test_run_default_restores_persisted_brief_and_absent_file_stays_legacy(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_root(tmp_path)
    client, _ = client_for(root)
    with client:
        cid = create(client).json()["characterId"]
    conf = load_settings(root)
    manager = JobManager(root, conf, EventHub())
    captured = _capture_run_until(monkeypatch)

    manager._run_default(_job(cid), object())
    assert captured["characterId"] == cid
    assert captured["options"].brief_text == BRIEF
    assert captured["options"].until == "G6"

    legacy = root / "runs" / "characters" / "cf-20261030-legacy"
    legacy.mkdir(parents=True)
    (legacy / "state.json").write_text(
        json.dumps({"schemaVersion": "state-v1", "subjectId": legacy.name}), encoding="utf-8"
    )
    manager._run_default(_job(legacy.name), object())
    assert captured["options"].brief_text is None


def test_run_default_rejects_oversized_persisted_brief(tmp_path: Path, monkeypatch) -> None:
    root = make_root(tmp_path)
    cid = "cf-20261030-oversized"
    char = root / "runs" / "characters" / cid
    (char / "creator-input").mkdir(parents=True)
    (char / "state.json").write_text(
        json.dumps({"schemaVersion": "state-v1", "subjectId": cid}), encoding="utf-8"
    )
    (char / "creator-input" / "brief-r1.md").write_text("x" * 20_001, encoding="utf-8")
    manager = JobManager(root, load_settings(root), EventHub())
    captured = _capture_run_until(monkeypatch)

    with pytest.raises(ValueError, match="브리프"):
        manager._run_default(_job(cid), object())
    assert "options" not in captured


@pytest.mark.parametrize("symlink_parent", [False, True])
def test_run_default_rejects_symlinked_creator_input(
    tmp_path: Path, monkeypatch, symlink_parent: bool
) -> None:
    root = make_root(tmp_path)
    cid = "cf-20261030-link-input"
    char = root / "runs" / "characters" / cid
    char.mkdir(parents=True)
    outside = tmp_path / "outside-brief"
    outside.mkdir()
    (outside / "brief-r1.md").write_text(BRIEF, encoding="utf-8")
    if symlink_parent:
        os.symlink(outside, char / "creator-input")
    else:
        (char / "creator-input").mkdir()
        os.symlink(outside / "brief-r1.md", char / "creator-input" / "brief-r1.md")
    manager = JobManager(root, load_settings(root), EventHub())
    captured = _capture_run_until(monkeypatch)

    with pytest.raises(ValueError, match="심볼릭|링크"):
        manager._run_default(_job(cid), object())
    assert "options" not in captured


def test_malformed_state_is_not_submitted_for_execution(tmp_path: Path) -> None:
    root = make_root(tmp_path)
    cid = "cf-20261030-broken"
    char = root / "runs" / "characters" / cid
    char.mkdir(parents=True)
    (char / "state.json").write_text("{not json", encoding="utf-8")
    manager = JobManager(root, load_settings(root), EventHub())

    with pytest.raises(WebError) as error:
        manager.submit(cid, "run", "G6")

    assert error.value.status == 409
    assert manager.list() == []


def test_restart_keeps_the_same_immutable_brief_and_rejects_duplicate(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_root(tmp_path)
    client, _ = client_for(root)
    with client:
        cid = create(client).json()["characterId"]
    char = root / "runs" / "characters" / cid
    brief = char / "creator-input" / "brief-r1.md"
    before = brief.read_bytes()

    restarted, _ = client_for(root)
    with restarted:
        duplicate = create(restarted, brief="재시작 뒤 덮어쓰기 시도")

    assert duplicate.status_code == 409
    assert brief.read_bytes() == before
    manager = JobManager(root, load_settings(root), EventHub())
    captured = _capture_run_until(monkeypatch)
    manager._run_default(_job(cid), object())
    assert captured["options"].brief_text == BRIEF
    assert brief.read_bytes() == before


def test_create_refuses_whitespace_only_request(tmp_path):
    from character_factory_poc.web.app import create_app

    with TestClient(create_app(tmp_path)) as client:
        res = client.post("/api/runtime/characters", json={"slug": "blank", "brief": " \n\t"})
        assert res.status_code == 400
        assert not (tmp_path / "runs/characters").exists()


def test_creation_publishes_only_a_complete_character(tmp_path, monkeypatch):
    from character_factory_poc.pipeline.state import StateFile
    from character_factory_poc.web import reads

    root = make_root(tmp_path)
    original = StateFile.save
    observed = []

    def before_publish(state):
        observed.append(reads.list_projects(root)["characters"])
        return original(state)

    monkeypatch.setattr(StateFile, "save", before_publish)
    client, _ = client_for(root)
    with client:
        response = create(client)
    assert response.status_code == 201
    assert observed == [[]], "incomplete reservations must never appear in the real list"
    assert len(reads.list_projects(root)["characters"]) == 1


@pytest.mark.parametrize(
    "raw",
    [{}, {"subjectId": "wrong"}, {"subjectId": "cf-20261030-broken", "schemaVersion": "state-v99"}],
)
def test_schema_invalid_state_is_rejected_before_queueing(tmp_path, raw):
    root = make_root(tmp_path)
    cid = "cf-20261030-broken"
    char = root / "runs/characters" / cid
    char.mkdir(parents=True)
    (char / "state.json").write_text(json.dumps(raw), encoding="utf-8")
    manager = JobManager(root, load_settings(root), EventHub())
    with pytest.raises(WebError) as error:
        manager.submit(cid, "run", "G6")
    assert error.value.status == 409
    assert manager.list() == []
