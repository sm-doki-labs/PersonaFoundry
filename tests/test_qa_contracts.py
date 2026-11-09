"""J: 사용자가 보는 목록·상세·대화 화면의 계약. 임시 폴더만 사용한다."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.pipeline.origin import write_model_mode
from character_factory_poc.web.app import create_app
from tests.test_demo_chat import put, ready
from tests.test_source_intake import start


@pytest.fixture
def case(tmp_path):
    client = TestClient(create_app(tmp_path))
    cid = start(client).split("/")[-1]
    return client, tmp_path / "runs/characters" / cid, "/api/characters/" + cid


def status(client, url):
    (row,) = client.get("/api/projects").json()["characters"]
    detail = client.get(url).json()
    for key in (
        "displayName",
        "status",
        "statusLabel",
        "chatReady",
        "goal",
        "createdAt",
        "archived",
    ):
        assert row[key] == detail[key] == detail["summary"][key]
    assert datetime.fromisoformat(row["createdAt"]).tzinfo
    meta = client.get(url + "/chat/meta").json()
    assert meta["ready"] == row["chatReady"]
    assert meta["name"] == row["displayName"]
    return row, meta


def test_readiness_requires_both_usable_artifacts(case):
    client, folder, url = case
    row, meta = status(client, url)
    assert (row["status"], row["statusLabel"], row["displayName"]) == ("draft", "시작 전", "선수")
    assert meta["missing"] == ["prompt", "scene"] and meta["nextHref"].startswith("sources.html")
    assert client.get("/api/chat/characters").json() == []
    put(folder / "s3-plan/pr1/plan.json", {"name": "새 이름"})
    ready(folder)
    put(
        folder / "state.json",
        {"stages": {key: {"status": "APPROVED"} for key in ("s0", "s3", "s7", "s8", "s8c")}},
    )
    row, meta = status(client, url)
    assert (row["status"], row["statusLabel"], row["displayName"]) == (
        "chat_ready",
        "대화 가능",
        "새 이름",
    )
    assert row["goal"]["done"] == row["goal"]["total"] == 5 and not meta["missing"]
    assert client.get("/api/chat/characters").json() == [
        dict(
            characterId=folder.name,
            displayName="새 이름",
            createdAt=row["createdAt"],
            origin="SOURCE",
        )
    ]
    write_model_mode(folder, "TRAIN")
    assert status(client, url)[0]["goal"]["total"] == 8
    put(folder / "s8-chapters/cs2/chapter-start.json", {"chapters": []})
    row, meta = status(client, url)
    assert not row["chatReady"] and meta["missing"] == ["scene"] and "장면" in meta["reason"]
    assert (
        meta["nextHref"].startswith("factory.html")
        and client.get("/api/chat/characters").json() == []
    )
    (folder / "s8-prompts/pv10/long.md").write_text("  ")
    assert status(client, url)[1]["missing"] == ["prompt", "scene"]


def test_job_and_review_states(case, monkeypatch):
    client, folder, url = case
    put(folder / "state.json", {"stages": {"s0": {"status": "RUNNING"}}})
    row, meta = status(client, url)
    assert row["status"] == "stopped" and "만드는 중" not in meta["reason"]
    with monkeypatch.context() as m:
        m.setattr(client.app.state.jobs, "active_for", lambda cid: {"status": "running"})
        row, meta = status(client, url)
        assert (row["statusLabel"], meta["reason"]) == ("만드는 중", "만드는 중이에요")
    put(folder / "state.json", {"gates": {"G0": {"status": "AWAITING_HUMAN"}}})
    assert status(client, url)[0]["statusLabel"] == "확인 필요"
    put(folder / "state.json", {"stages": {"s0": {"status": "CHECK_FAILED"}}})
    assert status(client, url)[0]["statusLabel"] == "실패"


def test_archive_and_restore(case):
    client, folder, url = case
    ready(folder)
    assert client.post(url + "/archive", json={"archived": "false"}).status_code == 422
    assert client.post(url + "/archive", json={"archived": True}).is_success
    assert (
        client.get("/api/projects").json()["characters"]
        == client.get("/api/chat/characters").json()
        == []
    )
    assert client.get("/api/projects?includeArchived=true").json()["characters"][0]["archived"]
    assert client.get(url).json()["archived"]
    assert client.post(url + "/archive", json={"archived": False}).is_success
    assert status(client, url)[0]["chatReady"]


def test_suggestions_and_drafts(case):
    client, folder, _ = case
    draft_url = "/api/sources/" + folder.name
    raw = "진행: 하나\n진행: 둘\n진행: 셋\n선수(본인): 넷".encode()

    def upload():
        rec = client.post(
            draft_url + "/files",
            json=dict(filename="casual_vlog.txt", size=len(raw), contentType="text/plain"),
        ).json()
        client.put(rec["upload"]["url"], content=raw).raise_for_status()
        return draft_url + "/files/" + rec["fileId"]

    file = upload()
    item = client.post(file + "/complete", json={"subjectSpeaker": "", "textId": ""}).json()
    assert item["status"] == "ready" and item["textId"] == "casual_vlog"
    assert item["detectedSpeakers"] == [
        dict(name="진행", lines=3),
        dict(name="선수(본인)", lines=1),
    ]
    assert item["suggested"] == dict(
        kind="TRANSCRIPT", register="CASUAL", subjectSpeaker="선수(본인)", userSpeaker="진행"
    )
    assert item["subjectSpeaker"] == "선수(본인)"
    problem = client.patch(file, json={"subjectSpeaker": "다른 이름"}).json()
    assert problem["status"] == "problem" and "다른 이름" in problem["problems"][0]
    assert "진행" in problem["problems"][0] and "subjectSpeaker" not in problem["problems"][0]
    fixed = client.patch(file, json={"subjectSpeaker": None}).json()
    assert fixed["status"] == "ready" and fixed["detectedSpeakers"] == item["detectedSpeakers"]
    assert client.post(upload() + "/complete", json={}).json()["textId"] == "casual_vlog-2"
    new = start(client).split("/")[-1]
    newest, previous = client.get("/api/sources/drafts").json()
    assert newest["characterId"] == new and previous["files"] == 2
    assert previous["displayName"] == "선수" and previous["characterId"] == folder.name
    put(folder / "state.json", {"stages": {"s0": {"status": "APPROVED"}}})
    assert client.get("/api/sources/drafts").json() == [newest]
