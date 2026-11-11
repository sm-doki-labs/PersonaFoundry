"""History endpoints use synthetic temporary folders only; no provider or live server."""

import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from character_factory_poc.web.demo_chat import install_demo_routes
from character_factory_poc.web.errors import WebError

CID = "cf-history-test"
URL = f"/api/characters/{CID}/chat/sessions"


def client_for(root):
    app = FastAPI()
    install_demo_routes(app, root, None)

    @app.exception_handler(WebError)
    async def errors(request, exc):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    return TestClient(app)


@pytest.fixture
def setup(tmp_path):
    folder = tmp_path / "runs/characters" / CID
    folder.mkdir(parents=True)
    return tmp_path, folder, client_for(tmp_path)


def snapshot(content="합성 메시지", revision=0):
    return {"revision": revision, "messages": [{"role": "user", "content": content}]}


def test_save_list_restore_after_app_restart_and_keep_other_sessions(setup):
    root, folder, client = setup
    sid = str(uuid4())
    result = client.put(f"{URL}/{sid}", json=snapshot("첫 대화"))
    assert result.status_code == 200
    assert result.json()["revision"] == 1
    other = str(uuid4())
    assert client.put(f"{URL}/{other}", json=snapshot("둘째 대화")).status_code == 200
    restarted = client_for(root)
    assert restarted.get(f"{URL}/{sid}").json()["messages"] == snapshot("첫 대화")["messages"]
    assert {s["id"] for s in restarted.get(URL).json()["sessions"]} == {sid, other}
    assert list((folder / "chat-history").glob("*.json"))


def test_lost_ack_is_idempotent_and_stale_snapshot_cannot_overwrite(setup):
    _, _, client = setup
    url = f"{URL}/{uuid4()}"
    assert client.put(url, json=snapshot()).status_code == 200
    assert client.put(url, json=snapshot()).json()["revision"] == 1
    assert client.put(url, json=snapshot("新", 1)).json()["revision"] == 2
    assert client.put(url, json=snapshot("다른 탭", 1)).status_code == 409
    assert client.get(url).json()["messages"][0]["content"] == "新"


def test_concurrent_writers_only_one_revision_wins(setup):
    root, _, client = setup
    url = f"{URL}/{uuid4()}"
    client.put(url, json=snapshot())

    def write(content):
        return client_for(root).put(url, json=snapshot(content, 1)).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ["왼쪽", "오른쪽"])) == [200, 409]


@pytest.mark.parametrize(
    "body",
    [
        {"revision": -1, "messages": []},
        {"revision": True, "messages": []},
        {"revision": 0, "messages": [{"role": "system", "content": "x"}]},
        {"revision": 0, "messages": [{"role": "user", "content": "x" * (1024 * 1024 + 1)}]},
        {"revision": 0, "messages": [{"role": "user", "content": "x"}] * 2001},
        {"revision": 0, "messages": [], "path": "../outside"},
    ],
)
def test_invalid_snapshot_is_rejected(setup, body):
    _, _, client = setup
    assert client.put(f"{URL}/{uuid4()}", json=body).status_code == 422


def test_body_limit_and_malformed_json(setup):
    _, _, client = setup
    url = f"{URL}/{uuid4()}"
    assert client.put(url, content=b"x" * (2 * 1024 * 1024 + 1)).status_code == 413
    assert client.put(url, content=b"{").status_code == 422


def test_path_escape_and_symlinks_are_rejected(setup, tmp_path):
    _, folder, client = setup
    assert client.put(f"{URL}/not-a-uuid", json=snapshot()).status_code == 400
    outside = tmp_path / "outside"
    outside.mkdir()
    (folder / "chat-history").symlink_to(outside, target_is_directory=True)
    assert client.put(f"{URL}/{uuid4()}", json=snapshot()).status_code == 400
    assert not list(outside.iterdir())


def test_session_symlink_cannot_be_read_or_overwritten(setup, tmp_path):
    _, folder, client = setup
    history = folder / "chat-history"
    history.mkdir()
    target = tmp_path / "private.json"
    target.write_text('{"private":"untouched"}')
    sid = str(uuid4())
    (history / f"{sid}.json").symlink_to(target)
    assert client.get(f"{URL}/{sid}").status_code == 400
    assert client.put(f"{URL}/{sid}", json=snapshot()).status_code == 400
    assert json.loads(target.read_text()) == {"private": "untouched"}


def test_atomic_save_failure_keeps_previous_snapshot_and_can_retry(setup, monkeypatch):
    import os

    _, _, client = setup
    url = f"{URL}/{uuid4()}"
    client.put(url, json=snapshot("이전"))
    original = os.replace

    def fail(*args, **kwargs):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(os, "replace", fail)
    assert client.put(url, json=snapshot("새 내용", 1)).status_code == 503
    assert client.get(url).json()["messages"][0]["content"] == "이전"
    monkeypatch.setattr(os, "replace", original)
    assert client.put(url, json=snapshot("새 내용", 1)).status_code == 200


def test_missing_character_and_session(setup):
    _, _, client = setup
    assert client.get(f"{URL}/{uuid4()}").status_code == 404
    assert client.get("/api/characters/cf-absent/chat/sessions").status_code == 404


def test_character_escape_is_rejected_and_characters_are_isolated(setup, tmp_path):
    _, folder, client = setup
    other = folder.parent / "cf-other"
    other.mkdir()
    sid = str(uuid4())
    client.put(f"{URL}/{sid}", json=snapshot("one character only"))
    other_url = f"/api/characters/cf-other/chat/sessions/{sid}"
    assert client.get(other_url).status_code == 404
    (folder.parent / "cf-escape").symlink_to(tmp_path, target_is_directory=True)
    assert client.get("/api/characters/cf-escape/chat/sessions").status_code == 400


def test_corrupt_record_is_preserved_and_reported(setup):
    _, folder, client = setup
    sid = str(uuid4())
    client.put(f"{URL}/{sid}", json=snapshot())
    file = folder / "chat-history" / f"{sid}.json"
    file.write_text("{broken")
    assert client.get(URL).status_code == 503
    assert client.put(f"{URL}/{sid}", json=snapshot("replacement", 1)).status_code == 503
    assert file.read_text() == "{broken"


def test_invalid_record_metadata_is_reported_instead_of_crashing_list(setup):
    _, folder, client = setup
    sid = str(uuid4())
    client.put(f"{URL}/{sid}", json=snapshot())
    file = folder / "chat-history" / f"{sid}.json"
    data = json.loads(file.read_text())
    del data["title"]
    file.write_text(json.dumps(data))
    assert client.get(URL).status_code == 503


def test_meta_uses_shared_configured_provider_without_model_request(setup, monkeypatch):
    from types import SimpleNamespace

    from character_factory_poc.common import demo_chat as demo

    root, _, _ = setup
    seen = []

    def configured(ctx):
        seen.append(ctx)
        return SimpleNamespace(model="synthetic-configured-model")

    monkeypatch.setattr(demo, "configured_provider", configured)

    def forbidden(*args, **kwargs):
        raise AssertionError("history and metadata must not invoke a model")

    monkeypatch.setattr(demo, "talk_model", forbidden)
    app = FastAPI()
    app.state.jobs = SimpleNamespace(active_for=lambda _: None)
    install_demo_routes(app, root, SimpleNamespace(config_path=None, server_mode=False))
    result = TestClient(app).get(f"/api/characters/{CID}/chat/meta")
    assert result.status_code == 200
    assert result.json()["model"]["model"] == "synthetic-configured-model"
    assert len(seen) == 1


def test_legacy_message_over_model_limit_is_archived_verbatim(setup):
    root, _, client = setup
    sid = str(uuid4())
    content = "보존할 합성 원문 " * 2000
    assert len(content) > 16000
    result = client.put(f"{URL}/{sid}", json=snapshot(content))
    assert result.status_code == 200
    restarted = client_for(root)
    assert restarted.get(f"{URL}/{sid}").json()["messages"][0]["content"] == content
    assert restarted.put(f"{URL}/{uuid4()}", json=snapshot("새 대화")).status_code == 200
    assert restarted.get(f"{URL}/{sid}").json()["messages"][0]["content"] == content
