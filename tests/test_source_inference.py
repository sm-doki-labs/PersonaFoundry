"""Source intake inference regressions: synthetic uploads, no models or network."""

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.web.app import create_app
from character_factory_poc.web.sources import suggested_kind

PC = (
    "--------------- 2026년 11월 11일 수요일 ---------------\n"
    "[나] [오전 9:12] 안녕\n[합성 인물] [오전 9:13] 반가워"
)
MOBILE = "2026년 11월 11일 오전 9:12, 나 : 안녕\n2026년 11월 11일 오전 9:13, 합성 인물 : 반가워"


@pytest.mark.parametrize(
    "raw", [PC, MOBILE, "설명입니다. " * 100 + "\n" + PC], ids=["pc", "mobile", "long-header"]
)
def test_structured_kakao_content_wins_over_interview_filename(raw):
    assert suggested_kind("synthetic-interview.txt", raw) == "KAKAO_EXPORT"


def test_casual_mentions_of_kakao_do_not_reclassify_interview():
    assert (
        suggested_kind("synthetic-interview.txt", "기자: 카카오톡 써요?\n합성 인물: 네.")
        == "INTERVIEW"
    )


def upload(client, raw):
    cid = client.post(
        "/api/sources/drafts",
        json={"displayName": "합성 인물", "subjectKind": "PRIVATE_PERSON", "videoTier": "none"},
    ).json()["characterId"]
    url = f"/api/sources/{cid}/files"
    payload = raw.encode()
    item = client.post(
        url,
        json={
            "filename": "synthetic-interview.txt",
            "size": len(payload),
            "contentType": "text/plain",
        },
    ).json()
    assert client.put(item["upload"]["url"], content=payload).status_code == 200
    return f"{url}/{item['fileId']}"


def test_auto_upload_parses_real_speaker_names_after_long_header(tmp_path):
    client = TestClient(create_app(tmp_path))
    url = upload(client, "합성 파일 설명 " * 100 + "\n" + PC)
    response = client.post(url + "/complete", json={"kind": None, "register": None})
    assert response.status_code == 200
    record = response.json()
    assert record["kind"] == "KAKAO_EXPORT"
    assert record["register"] == "CASUAL"
    assert record["subjectSpeaker"] == "합성 인물"
    assert {s["name"] for s in record["detectedSpeakers"]} == {"나", "합성 인물"}
    assert record["status"] == "ready"
    # Manually confirmed fields remain authoritative on later edits.
    edited = client.patch(
        url, json={"subjectSpeaker": "나", "userSpeaker": "합성 인물", "register": "FORMAL"}
    ).json()
    assert (edited["subjectSpeaker"], edited["userSpeaker"], edited["register"]) == (
        "나",
        "합성 인물",
        "FORMAL",
    )


def test_explicit_wrong_kind_reports_format_problem_not_timestamp_speakers(tmp_path):
    client = TestClient(create_app(tmp_path))
    url = upload(client, PC)
    record = client.post(url + "/complete", json={"kind": "INTERVIEW"}).json()
    assert record["kind"] == "INTERVIEW", "do not silently overwrite a manual selection"
    assert record["status"] == "problem"
    assert record["detectedSpeakers"] == []
    assert record["subjectSpeaker"] is None
    assert "카톡" in " ".join(record["problems"])


@pytest.mark.parametrize(
    "legacy",
    [
        {"subject": {"displayName": "이전 인물", "kind": "PRIVATE_PERSON"}},
        {"files": None},
        {"files": {}},
        {"files": "legacy"},
    ],
)
def test_drafts_list_skips_legacy_records_without_mutating_them(tmp_path, legacy):
    import json

    folder = tmp_path / "runs/characters/cf-legacy/s0-source"
    folder.mkdir(parents=True)
    path = folder / "intake.json"
    path.write_text(json.dumps(legacy, ensure_ascii=False))
    before = path.read_bytes()
    client = TestClient(create_app(tmp_path))
    current = client.post(
        "/api/sources/drafts",
        json={"displayName": "이어 쓸 새 초안", "subjectKind": "PRIVATE_PERSON"},
    ).json()["characterId"]
    result = client.get("/api/sources/drafts")
    assert result.status_code == 200
    assert [row["characterId"] for row in result.json()] == [current]
    assert path.read_bytes() == before
