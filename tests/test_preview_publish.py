"""테스터 전용 미리보기 발행의 순서와 멈춤 조건(가짜 연결, 네트워크·DB 없음)."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from character_factory_poc.stages.export.preview import (
    Ports,
    PreviewError,
    PreviewSettings,
    merge_segments,
    publish_preview,
)
from character_factory_poc.stages.s11_release.package import build_package
from tests import test_twin_export as twin
from tests.support.export_flow import approve_package

CID = "cf-20261112-preview-unit"


class FakeLive:
    """api-svc·chat-svc·관리자 API를 흉내 내고 호출 순서를 적는다."""

    def __init__(self, *, drift=(), testers=(7,), existing=None, listed_leak=False):
        self.log: list[str] = []
        self.segments = json.dumps({"preview_member_ids": list(testers)}) if testers else "{}"
        self.drift, self.existing, self.listed_leak = list(drift), existing, listed_leak
        self.next_id: dict[str, int] = {}
        self.inserted_id = None

    def api_db(self, req):
        self.log.append(f"api.{req['op']}")
        if req["op"] == "inspect":
            return {
                "heads": ["194_character_ko_voices_f12_f14"],
                "columns": {
                    t: ["id", "character_id", "media_id", "usage_type", "key"]
                    for t in req["tables"]
                },
                "sequences": {t: f"{t}_id_seq" for t in req["tables"]},
                "existing": self.existing,
            }
        if req["op"] == "reserve":
            ids = {}
            for table, count in req["counts"].items():
                start = self.next_id.get(table, 100)
                ids[table] = list(range(start, start + count))
                self.next_id[table] = start + count
            return {"ids": ids}
        if req["op"] == "insert":
            assert "preview" in self.segments  # 행보다 노출 설정이 먼저다
            self.inserted_id = req["tables"]["character"]["rows"][0][0]
            row = dict(
                zip(
                    req["tables"]["character"]["columns"],
                    req["tables"]["character"]["rows"][0],
                    strict=True,
                )
            )
            assert row["chat_enabled"] is False and row["call_enabled"] is False
            return {"inserted": {"character": 1}, "dropped": {}}
        if req["op"] == "enable":
            return {"updated": 1}
        raise AssertionError(req)

    def chat_db(self, req):
        self.log.append(f"chat.{req['op']}")
        if req["op"] == "inspect":
            return {"heads": ["0030"], "releaseHead": "release-a", "drift": self.drift}
        assert req["expectedHead"] == "release-a"
        return {
            "heads": ["0030"],
            "releaseHead": "release-a",
            "driftAfter": 0,
            "report": {"releaseId": "release-b", "characters": 26},
        }

    def http(self, method, url, headers, body):
        path = url.split("8899", 1)[1]
        self.log.append(f"http.{method} {path.split('?')[0]}")
        if "/admin/" in path:
            assert headers.get("X-Admin-Token") == "admin"
            if method == "PUT":
                self.segments = json.loads(body)["value"]
                return 200, {}
            return 200, [{"key": "content.segments", "value": self.segments}]
        ids = [{"id": self.inserted_id}] if self.listed_leak else [{"id": 1}]
        return 200, {"characters": ids}

    def ports(self):
        return Ports(
            api_db=self.api_db,
            chat_db=self.chat_db,
            http=self.http,
            upload=lambda path, key: self.log.append("upload"),
            sleep=lambda s: self.log.append(f"sleep {s:.0f}"),
        )


@pytest.fixture
def approved(tmp_path, monkeypatch):
    make = twin._twin
    monkeypatch.setattr(twin, "_twin", lambda ctx, unused: make(ctx, CID))
    ctx, _, _, _ = twin._approved(tmp_path, "PROMPT_ONLY")
    build_package(ctx, CID)
    approve_package(ctx, CID)
    for env in ("CFP_PREVIEW_API_DB_URL", "CFP_PREVIEW_CHAT_DB_URL"):
        monkeypatch.setenv(env, "postgresql://unused")
    monkeypatch.setenv("CFP_PREVIEW_ADMIN_TOKEN", "admin")
    return ctx


SETTINGS = PreviewSettings(target="test", api_base_url="http://127.0.0.1:8899", wait_s=35)


def test_order_segments_before_rows_and_hidden_check(approved):
    live = FakeLive()
    result = publish_preview(approved, CID, settings=SETTINGS, ports=live.ports())
    assert result.status == "PUBLISHED", result.failure
    order = [e for e in live.log if not e.startswith(("upload", "http.GET /api/v1/characters"))]
    put = order.index("http.PUT /api/v1/admin/content/config/content.segments")
    assert order.index("api.reserve") < put < order.index("sleep 35") < order.index("api.insert")
    assert order.index("api.insert") < order.index("chat.publish") < order.index("api.enable")
    saved = json.loads(live.segments)
    assert saved["characters"] == {str(result.apiCharacterId): "preview"}
    assert saved["preview_member_ids"] == [7]
    assert result.apiCharacterId == 100  # 대상 DB 시퀀스에서 예약한 번호
    files = list((approved.character_dir(CID) / "px-preview").glob("*.json"))
    assert len(files) == 1


@pytest.mark.parametrize(
    "fake,needle,forbidden",
    [
        (FakeLive(drift=[{"owner": "x", "reason": "hash_mismatch"}]), "되돌아가요", "api.reserve"),
        (FakeLive(testers=()), "테스터 명단", "api.reserve"),
        (FakeLive(existing=12), "이미 발행된", "api.reserve"),
    ],
)
def test_stops_before_any_write(approved, fake, needle, forbidden):
    result = publish_preview(approved, CID, settings=SETTINGS, ports=fake.ports())
    assert result.status == "FAILED" and needle in result.failure
    assert forbidden not in fake.log and "api.insert" not in fake.log
    assert not any(e.startswith("http.PUT") for e in fake.log)


def test_leak_is_reported_as_failure(approved):
    live = FakeLive(listed_leak=True)
    result = publish_preview(approved, CID, settings=SETTINGS, ports=live.ports())
    assert result.status == "FAILED" and "일반 사용자 목록에 보여요" in result.failure


def test_live_needs_explicit_switches(approved, monkeypatch):
    live = FakeLive()
    base = replace(SETTINGS, target="live")
    result = publish_preview(approved, CID, settings=base, ports=live.ports())
    assert "allow_live" in result.failure and live.log == []
    on = replace(base, allow_live=True, storage="s3", s3_bucket="b")
    assert (
        "CFP_PREVIEW_LIVE_CONFIRM"
        in publish_preview(approved, CID, settings=on, ports=live.ports()).failure
    )
    monkeypatch.setenv("CFP_PREVIEW_LIVE_CONFIRM", "1")
    short = replace(on, wait_s=5)
    assert "대기 시간" in publish_preview(approved, CID, settings=short, ports=live.ports()).failure
    assert live.log == []


def test_merge_keeps_other_entries():
    raw = json.dumps(
        {"preview_member_ids": [3], "characters": {"8": "new"}, "shorts": {"1": "existing"}}
    )
    merged, value = merge_segments(raw, 40)
    assert value == {
        "preview_member_ids": [3],
        "characters": {"8": "new", "40": "preview"},
        "shorts": {"1": "existing"},
    }
    with pytest.raises(PreviewError, match="이미 new"):
        merge_segments(raw, 8)
    with pytest.raises(PreviewError, match="모르는 키"):
        merge_segments(json.dumps({"preview_member_ids": [1], "typo": 1}), 9)


def test_keys_follow_api_svc_rule(approved):
    live = FakeLive()
    uploads = []
    ports = live.ports()
    ports.upload = lambda path, key: uploads.append((path, key))
    result = publish_preview(approved, CID, settings=SETTINGS, ports=ports)
    assert result.status == "PUBLISHED", result.failure
    assert uploads and all(path.is_file() for path, _ in uploads)
    for _, key in uploads:
        parts = key.split("/")
        assert parts[:3] == ["api-svc", parts[1], "characters"] and parts[1] in {
            "public",
            "protected",
        }
        assert parts[3] == str(result.apiCharacterId) and len(parts[4]) == 32
    assert any(k.split("/")[1] == "public" for _, k in uploads)  # 프로필 사진은 공개 키
