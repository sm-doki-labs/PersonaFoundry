"""테스터 전용 미리보기 발행을 실서비스와 같은 코드·스키마에서 끝까지 확인한다.

환경변수 CFP_PREVIEW_E2E=1일 때만 돈다. 준비물(사람이 띄운다):
- 일회용 PostgreSQL 두 DB(api·chat)를 실서비스 배포 판(api-svc 6bfba75, chat-svc 864e02b)으로
  migrate하고 기존 콘텐츠를 채운다(work/preview-e2e/setup.sh).
- 같은 api-svc 판을 그 DB로 띄운다(ADMIN_API_TOKEN 설정).
- CFP_PREVIEW_API_DB_URL·CFP_PREVIEW_CHAT_DB_URL·CFP_PREVIEW_ADMIN_TOKEN·
  CFP_PREVIEW_E2E_BASE_URL·CFP_PREVIEW_E2E_API_REPO·CFP_PREVIEW_E2E_CHAT_REPO.
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from dataclasses import replace
from pathlib import Path

import pytest

from character_factory_poc.stages.export.doki_app.naming import character_uid
from character_factory_poc.stages.export.preview import PreviewSettings, publish_preview
from character_factory_poc.stages.s11_release.package import build_package
from tests import test_twin_export as twin
from tests.support.export_flow import approve_package

pytestmark = pytest.mark.skipif(
    os.environ.get("CFP_PREVIEW_E2E") != "1", reason="실서비스 판 일회용 스택이 있을 때만"
)

BASE = os.environ.get("CFP_PREVIEW_E2E_BASE_URL", "http://127.0.0.1:8899")
API_REPO = Path(
    os.environ.get("CFP_PREVIEW_E2E_API_REPO", "~/projects/_wt/api-svc-live")
).expanduser()
CHAT_REPO = Path(
    os.environ.get("CFP_PREVIEW_E2E_CHAT_REPO", "~/projects/_wt/chat-svc-live")
).expanduser()


@pytest.fixture(autouse=True)
def no_network():
    """이 시험은 127.0.0.1의 일회용 스택만 부른다(기본 네트워크 차단을 이 파일에서만 푼다)."""
    assert BASE.startswith("http://127.0.0.1:")
    yield


def _api_py(code: str) -> str:
    done = subprocess.run(
        [str(API_REPO / ".venv/bin/python"), "-c", code],
        cwd=API_REPO,
        # 일회용 서버와 같은 DEBUG 설정(개발용 JWT 비밀값)으로 토큰을 만든다.
        env={**os.environ, "DEBUG": "true", "CFP_PG_DSN": os.environ["CFP_PREVIEW_API_DB_URL"]},
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _api_sql(sql: str) -> list:
    code = (
        "import json, os, psycopg\n"
        "with psycopg.connect(os.environ['CFP_PG_DSN'], autocommit=True) as c:\n"
        f"    cur = c.execute({sql!r})\n"
        "    print(json.dumps([list(r) for r in cur.fetchall()] if cur.description else [],"
        " default=str))\n"
    )
    return json.loads(_api_py(code))


def _chat_sql(sql: str) -> list:
    code = (
        "import json, os, sqlalchemy as sa\n"
        "e = sa.create_engine(os.environ['URL'])\n"
        "with e.connect() as c:\n"
        f"    print(json.dumps([list(r) for r in c.execute(sa.text({sql!r}))], default=str))\n"
    )
    done = subprocess.run(
        [str(CHAT_REPO / ".venv/bin/python"), "-c", code],
        env={**os.environ, "URL": os.environ["CFP_PREVIEW_CHAT_DB_URL"]},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def _token(member_id: int) -> str:
    return _api_py(
        "from app.services.auth.jwt_tokens import create_access_token\n"
        f"print(create_access_token({member_id}))"
    )


def _get(path: str, *, token: str | None = None, platform: str = "android") -> tuple[int, dict]:
    headers = {"X-Client-Platform": platform}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def _put_segments(value: dict) -> None:
    req = urllib.request.Request(
        BASE + "/api/v1/admin/content/config/content.segments",
        data=json.dumps({"value": json.dumps(value)}).encode(),
        method="PUT",
        headers={
            "X-Admin-Token": os.environ["CFP_PREVIEW_ADMIN_TOKEN"],
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        assert res.status == 200


def _listed(token: str | None, platform: str) -> set[int]:
    status, body = _get("/api/v1/characters?sort=new&limit=50", token=token, platform=platform)
    assert status == 200
    return {c["id"] for c in body["characters"]}


def test_preview_publish_on_live_schema(tmp_path, monkeypatch):
    cid = "cf-20261112-preview-e2e"
    make = twin._twin
    monkeypatch.setattr(twin, "_twin", lambda ctx, unused: make(ctx, cid))
    ctx, _, _, _ = twin._approved(tmp_path, "PROMPT_ONLY")
    build_package(ctx, cid)
    approve_package(ctx, cid)

    # member.id는 party에서 받는다.
    def member(name: str) -> int:
        return _api_sql(
            "WITH p AS (INSERT INTO party DEFAULT VALUES RETURNING id) "
            "INSERT INTO member (id, nickname, status, email) SELECT p.id, "
            f"'{name}', 'active', '{name}@e2e.invalid' FROM p RETURNING id"
        )[0][0]

    tester, regular = member("preview-tester"), member("regular")
    keep = {"preview_member_ids": [tester], "shorts": {"999": "existing"}}
    _put_segments(keep)
    uid = str(character_uid(cid))
    others_before = _chat_sql(
        "SELECT rc.character_uid::text, rc.character_version_id FROM content.release_characters rc "
        "JOIN content.content_release_head h ON h.release_id = rc.release_id ORDER BY 1, 2"
    )
    seq_before = _api_sql("SELECT last_value FROM character_id_seq")[0][0]

    settings = PreviewSettings(
        target="test",
        api_svc_repo=API_REPO,
        chat_svc_repo=CHAT_REPO,
        api_base_url=BASE,
        storage="none",
        wait_s=31,
    )
    result = publish_preview(ctx, cid, settings=settings)
    assert result.status == "PUBLISHED", result.failure
    cid_num = result.apiCharacterId
    assert cid_num == seq_before + 1  # 예약 번호를 썼다(200만 번대가 아니다)
    assert _api_sql("SELECT last_value FROM character_id_seq")[0][0] == cid_num
    row = _api_sql(
        f"SELECT chat_enabled, is_active, character_uid::text FROM character WHERE id = {cid_num}"
    )[0]
    assert row == [True, True, uid]
    keys = [
        r[0]
        for r in _api_sql(
            "SELECT f.key FROM file_store f JOIN character_media cm ON cm.media_id = f.media_id "
            f"WHERE cm.character_id = {cid_num}"
        )
    ]
    assert keys and all(k.startswith("api-svc/") and f"/characters/{cid_num}/" in k for k in keys)

    # 기존 노출 설정은 그대로, 이 캐릭터만 preview.
    _, rows = None, None
    req = urllib.request.Request(
        BASE + "/api/v1/admin/content/config",
        headers={"X-Admin-Token": os.environ["CFP_PREVIEW_ADMIN_TOKEN"]},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        rows = json.loads(res.read())
    saved = json.loads(next(r["value"] for r in rows if r["key"] == "content.segments"))
    assert saved == {**keep, "characters": {str(cid_num): "preview"}}

    tester_token, regular_token = _token(tester), _token(regular)
    for platform in ("android", "web", "ios"):
        assert cid_num in _listed(tester_token, platform)
        assert cid_num not in _listed(regular_token, platform)
        assert cid_num not in _listed(None, platform)
    assert _get(f"/api/v1/characters/{cid_num}", token=tester_token)[0] == 200

    # chat-svc: 새 캐릭터가 들어가고 다른 캐릭터의 발행 판은 그대로다.
    others_after = _chat_sql(
        "SELECT rc.character_uid::text, rc.character_version_id FROM content.release_characters rc "
        "JOIN content.content_release_head h ON h.release_id = rc.release_id ORDER BY 1, 2"
    )
    assert [r for r in others_after if r[0] != uid] == others_before
    assert any(r[0] == uid for r in others_after)

    again = publish_preview(ctx, cid, settings=replace(settings, wait_s=0))
    assert again.status == "FAILED" and "이미 발행된" in again.failure
