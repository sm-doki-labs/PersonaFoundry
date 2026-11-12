"""테스터 전용 미리보기 발행 — 넣기 API(backoffice factory-import) 호출 순서와 몸통.

가짜 서버로 돌고 네트워크를 쓰지 않는다.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import replace
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from character_factory_poc.contracts.release import CharacterVoice
from character_factory_poc.stages.export import preview
from character_factory_poc.stages.export.doki_app import chat_svc
from character_factory_poc.stages.export.doki_app.naming import character_uid
from character_factory_poc.stages.export.preview import (
    Ports,
    PreviewSettings,
    latest_published,
    publish_preview,
    remove_preview,
)
from character_factory_poc.stages.s11_release.package import build_package, load_package
from tests import test_twin_export as twin
from tests.support.export_flow import approve_package

CID = "cf-20261113-preview-unit"
FISH = "fb7cdd3886ae42c996842b9470693322"
REAL_CHAT = Path("~/projects/_wt/chat-svc-live").expanduser()


class FakeImport:
    """넣기 서비스를 흉내 내고 호출 순서를 적는다."""

    def __init__(self, *, testers=2, existing=None, voice_reachable=True, fail=None):
        self.testers, self.existing, self.voice_reachable, self.fail = (
            testers,
            existing,
            voice_reachable,
            fail,
        )
        self.log: list[str] = []
        self.next: dict[str, int] = {}
        self.body: dict | None = None
        self.upload_request: dict | None = None
        self.put: list[tuple[str, dict, Path]] = []

    def api(self, method, path, body):
        assert path.startswith("/api/v1/factory-import/")
        tail = path.removeprefix("/api/v1/factory-import")
        route = tail.split("?")[0]
        self.log.append(f"{method} {route}")
        if route == "/state":
            tables = parse_qs(urlsplit(tail).query)["tables"][0].split(",")
            return 200, {
                "api": {
                    "heads": ["194_character_ko_voices_f12_f14"],
                    "columns": {t: [] for t in tables},
                    "sequences": {t: f"{t}_id_seq" for t in tables},
                    "existing": self.existing,
                    "testers": self.testers,
                    "imported": [],
                },
                "chat": {"releaseHead": "release-a", "characters": 10, "chapters": 220},
                "voice": {"reachable": self.voice_reachable, "voices": 45},
            }
        if route == "/reservations":
            ids = {}
            for table, count in body["counts"].items():
                start = self.next.get(table, 500)
                ids[table] = list(range(start, start + count))
                self.next[table] = start + count
            return 200, {"ids": ids}
        if route == "/uploads":
            self.upload_request = body
            files = []
            for item in body["files"]:
                access = "public" if item["kind"] == "profile_photo" else "protected"
                folder = f"api-svc/{access}/characters/{body['characterId']}/{uuid.uuid4().hex}"
                key = f"{folder}/{item['variant']}.{item['ext']}"
                files.append(
                    {
                        "ref": item["ref"],
                        "key": key,
                        "url": f"https://s3.test/{key}?sig=1",
                        "method": "PUT",
                        "headers": {"Content-Type": item["contentType"]},
                    }
                )
            return 200, {"files": files}
        if route == "/characters" and method == "POST":
            self.body = body
            if self.fail:
                return 409, {"detail": {"code": "FACTORY_IMPORT_CONFLICT", "message": self.fail}}
            voice = body.get("voice")
            answer = None
            if voice and voice.get("fishReferenceId"):
                answer = {"voiceId": str(uuid.uuid4()), "name": "pf-x", "created": True}
            elif voice:
                answer = {"voiceId": voice["voiceId"], "name": "ko-M-2", "created": False}
            return 200, {
                "status": "PUBLISHED",
                "characterId": body["api"]["tables"]["character"]["rows"][0][0],
                "releaseId": "release-b",
                "voice": answer,
                "warnings": [],
                "steps": [
                    {
                        "name": "노출 확인",
                        "ok": True,
                        "detail": "로그인 없는 목록·검색 6곳에서 안 보임",
                    }
                ],
            }
        if method == "DELETE":
            return 200, {
                "deleted": {"character": 1, "media": 3},
                "filesDeleted": 3,
                "voice": {"voiceId": "v", "created": True, "removed": True},
            }
        raise AssertionError((method, path))

    def put_file(self, url, headers, path):
        self.log.append("PUT file")
        self.put.append((url, headers, path))
        return 200

    def compile_chat(self, data_dir, uid):
        self.log.append("compile")
        assert (data_dir / "pointers" / "content-pointers-v2.json").is_file()
        chapter = str(uuid.uuid4())
        return {
            "content": {
                "characterVersions": [
                    {"characterUid": uid, "revision": "r1", "payloadHash": "0" * 64}
                ],
                "chapterVersions": [
                    {"chapterUid": chapter, "revision": "c1", "payloadHash": "1" * 64}
                ],
                "generationProfiles": [{"revision": "g1", "payload": {}, "payloadHash": "2" * 64}],
                "releaseCharacters": [
                    {
                        "characterUid": uid,
                        "locale": "ko",
                        "characterRevision": "r1",
                        "displayOrder": 1,
                    }
                ],
                "releaseChapters": [
                    {
                        "characterUid": uid,
                        "chapterUid": chapter,
                        "locale": "ko",
                        "chapterRevision": "c1",
                        "generationProfileRevision": "g1",
                        "number": 1,
                    }
                ],
            },
            "problems": [],
        }

    def ports(self):
        return Ports(api=self.api, put_file=self.put_file, compile_chat=self.compile_chat)


def _ready(tmp_path, monkeypatch, mode):
    make = twin._twin
    monkeypatch.setattr(twin, "_twin", lambda ctx, unused: make(ctx, CID))
    ctx, _, _, _ = twin._approved(tmp_path, mode)
    build_package(ctx, CID)
    approve_package(ctx, CID)
    monkeypatch.setenv("FACTORY_IMPORT_TOKEN", "t" * 40)
    package, package_dir = load_package(ctx, CID)
    pointers = chat_svc.build_tree(package, package_dir).files["pointers/content-pointers-v2.json"]
    repo = tmp_path / "chat-svc"
    (repo / "data" / "pointers").mkdir(parents=True)
    (repo / "data" / "pointers" / "content-pointers-v2.json").write_text(
        json.dumps({"schemaVersion": pointers["schemaVersion"], "pointers": []})
    )
    settings = PreviewSettings(base_url="https://factory-import.test", chat_svc_repo=repo)
    return ctx, settings


@pytest.fixture
def approved(tmp_path, monkeypatch):
    return _ready(tmp_path, monkeypatch, "PROMPT_ONLY")


def _with_fish(monkeypatch):
    real = preview.load_package

    def load(ctx, cid):
        package, package_dir = real(ctx, cid)
        voice = CharacterVoice(referenceId=FISH, voiceRev="vo1", record="voice/voice.json")
        return package.model_copy(update={"voice": voice}), package_dir

    monkeypatch.setattr(preview, "load_package", load)


def test_one_call_carries_profile_persona_media_and_fish_voice(approved, monkeypatch):
    ctx, settings = approved
    _with_fish(monkeypatch)
    fake = FakeImport()
    result = publish_preview(ctx, CID, settings=settings, ports=fake.ports())
    assert result.status == "PUBLISHED", result.failure
    order = [e for e in fake.log if e != "PUT file"]
    assert order == [
        "GET /state",
        "POST /reservations",
        "compile",
        "POST /uploads",
        "POST /characters",
    ]
    assert fake.log.index("PUT file") < fake.log.index("POST /characters")

    body = fake.body
    assert body["characterUid"] == str(character_uid(CID)) and body["handle"] == CID
    assert body["voice"] == {
        "fishReferenceId": FISH,
        "displayName": result.name[:64],
        "language": "ko",
    }
    tables = body["api"]["tables"]
    assert "character_voice" not in tables and "character_voice_language" not in tables
    character = dict(
        zip(tables["character"]["columns"], tables["character"]["rows"][0], strict=True)
    )
    assert character["voice_id"] is None and character["character_uid"] == body["characterUid"]
    assert result.apiCharacterId == character["id"] == 500  # 넣기 서비스가 예약한 번호
    assert body["chat"]["releaseCharacters"][0]["characterUid"] == body["characterUid"]
    assert body["enable"]["chat"] is True and body["expiresAt"]

    # 파일 키는 넣기 서비스가 정한 api-svc 규칙 키로 바뀌고, 그 주소로 실제 파일을 올렸다.
    fs = tables["file_store"]
    keys = [row[fs["columns"].index("key")] for row in fs["rows"]]
    assert keys and all(
        re.match(
            rf"^api-svc/(public|protected)/characters/{result.apiCharacterId}/[0-9a-f]{{32}}/", k
        )
        for k in keys
    )
    assert sorted(
        url.split("?")[0].removeprefix("https://s3.test/") for url, _, _ in fake.put
    ) == sorted(keys)
    assert all(path.is_file() for _, _, path in fake.put)
    kinds = {item["kind"] for item in fake.upload_request["files"]}
    assert "profile_photo" in kinds
    assert result.voice["created"] is True
    assert latest_published(ctx, CID)["apiCharacterId"] == result.apiCharacterId


def test_existing_voice_uuid_is_sent_as_voice_id(approved, monkeypatch):
    ctx, settings = approved
    real = preview.load_package

    def load(ctx, cid):
        package, package_dir = real(ctx, cid)
        bound = package.twin.model_copy(update={"voiceId": uuid.UUID(twin.VOICE)})
        return package.model_copy(update={"twin": bound}), package_dir

    monkeypatch.setattr(preview, "load_package", load)
    fake = FakeImport()
    result = publish_preview(ctx, CID, settings=settings, ports=fake.ports())
    assert result.status == "PUBLISHED", result.failure
    assert fake.body["voice"] == {"voiceId": twin.VOICE, "language": "ko"}
    assert "character_voice" not in fake.body["api"]["tables"]


def test_without_voice_warns_and_default_voice_is_used(approved):
    ctx, settings = approved
    fake = FakeImport()
    result = publish_preview(ctx, CID, settings=settings, ports=fake.ports())
    assert result.status == "PUBLISHED" and fake.body["voice"] is None
    assert any("VOICE_LANGUAGE_NOT_AVAILABLE" in w for w in result.warnings)

    voice = "123317ec-b985-4f91-af39-47e493fa9333"
    fake = FakeImport()
    again = publish_preview(
        ctx, CID, settings=replace(settings, default_voice_id=voice), ports=fake.ports()
    )
    assert again.status == "PUBLISHED" and fake.body["voice"] == {
        "voiceId": voice,
        "language": "ko",
    }


@pytest.mark.parametrize(
    "fake,needle",
    [
        (FakeImport(testers=0), "테스터 명단"),
        (FakeImport(existing=12), "이미 발행된"),
    ],
)
def test_stops_before_any_write(approved, fake, needle):
    ctx, settings = approved
    result = publish_preview(ctx, CID, settings=settings, ports=fake.ports())
    assert result.status == "FAILED" and needle in result.failure
    assert fake.log == ["GET /state"]


def test_fish_voice_needs_voice_svc(approved, monkeypatch):
    ctx, settings = approved
    _with_fish(monkeypatch)
    fake = FakeImport(voice_reachable=False)
    result = publish_preview(ctx, CID, settings=settings, ports=fake.ports())
    assert "voice-svc" in result.failure and "POST /characters" not in fake.log


def test_server_message_is_shown_as_is(approved):
    ctx, settings = approved
    fake = FakeImport(fail="같은 character_uid 또는 handle 이 이미 있어요")
    result = publish_preview(ctx, CID, settings=settings, ports=fake.ports())
    assert result.status == "FAILED"
    assert (
        result.failure == "넣기: 넣기 실패(HTTP 409): 같은 character_uid 또는 handle 이 이미 있어요"
    )


def test_needs_address_token_and_chat_checkout(approved, monkeypatch):
    ctx, settings = approved
    fake = FakeImport()
    assert (
        "base_url"
        in publish_preview(
            ctx, CID, settings=replace(settings, base_url=""), ports=fake.ports()
        ).failure
    )
    missing = replace(settings, chat_svc_repo=Path("/nonexistent/chat"))
    assert (
        "chat-svc 체크아웃"
        in publish_preview(ctx, CID, settings=missing, ports=fake.ports()).failure
    )
    monkeypatch.delenv("FACTORY_IMPORT_TOKEN")
    assert (
        "FACTORY_IMPORT_TOKEN"
        in publish_preview(ctx, CID, settings=settings, ports=fake.ports()).failure
    )
    assert fake.log == []


def test_remove_deletes_last_published_and_allows_republish(approved):
    ctx, settings = approved
    fake = FakeImport()
    published = publish_preview(ctx, CID, settings=settings, ports=fake.ports())
    removed = remove_preview(ctx, CID, settings=settings, ports=fake.ports())
    assert removed.status == "REMOVED", removed.failure
    assert fake.log[-1] == f"DELETE /characters/{published.apiCharacterId}"
    assert latest_published(ctx, CID) is None
    assert remove_preview(ctx, CID, settings=settings, ports=fake.ports()).failure.endswith(
        "지울 발행 기록이 없어요"
    )


@pytest.mark.skipif(
    not (REAL_CHAT / ".venv/bin/python").is_file(), reason="dev 배포 판 chat-svc 체크아웃이 없다"
)
def test_real_chat_svc_compiler_output_fits_import_api(approved):
    """dev 배포 판 chat-svc 컴파일러로 컴파일해 넣기 API 가 받는 모양인지 본다(DB·네트워크 없음)."""
    ctx, settings = approved
    settings = replace(settings, chat_svc_repo=REAL_CHAT)
    fake = FakeImport()
    real = preview.default_ports(settings)
    ports = Ports(api=fake.api, put_file=fake.put_file, compile_chat=real.compile_chat)
    result = publish_preview(ctx, CID, settings=settings, ports=ports)
    assert result.status == "PUBLISHED", result.failure
    chat = fake.body["chat"]
    uid = fake.body["characterUid"]
    assert {c["characterUid"] for c in chat["characterVersions"]} == {uid}
    assert chat["releaseChapters"] and all(
        m["characterUid"] == uid for m in chat["releaseChapters"]
    )
    revisions = {(c["chapterUid"], c["revision"]) for c in chat["chapterVersions"]}
    assert {(m["chapterUid"], m["chapterRevision"]) for m in chat["releaseChapters"]} <= revisions
    assert {m["generationProfileRevision"] for m in chat["releaseChapters"]} <= {
        g["revision"] for g in chat["generationProfiles"]
    }
    for name in ("characterVersions", "chapterVersions", "generationProfiles"):
        assert all(re.fullmatch(r"[0-9a-f]{64}", item["payloadHash"]) for item in chat[name])
    stage_uids = {
        row[fake.body["api"]["tables"]["character_stage"]["columns"].index("stage_uid")]
        for row in fake.body["api"]["tables"]["character_stage"]["rows"]
    }
    assert {m["chapterUid"] for m in chat["releaseChapters"]} == {str(u) for u in stage_uids}
