"""넣기 서비스까지 실제로 넣고 지운다. CFP_PREVIEW_E2E_BASE_URL 이 있을 때만 돈다.

준비물: backoffice factory-import 를 그 주소에 띄우고(일회용 DB·S3 또는 dev), FACTORY_IMPORT_TOKEN,
dev 배포 판 chat-svc 체크아웃(CFP_PREVIEW_E2E_CHAT_REPO, 기본 ~/projects/_wt/chat-svc-live).
dev 를 가리키면 실제 dev 에 테스터 전용 캐릭터가 생겼다가 지워진다.
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from character_factory_poc.stages.export.preview import publish_preview, remove_preview
from tests.test_preview_publish import _ready, _with_fish

BASE = os.environ.get("CFP_PREVIEW_E2E_BASE_URL", "")
CHAT = Path(
    os.environ.get("CFP_PREVIEW_E2E_CHAT_REPO", "~/projects/_wt/chat-svc-live")
).expanduser()
pytestmark = pytest.mark.skipif(not BASE, reason="넣기 서비스 주소가 없다")


@pytest.fixture(autouse=True)
def no_network():
    """이 시험만 실제 넣기 서비스에 닿는다(기본 네트워크 차단을 이 파일에서 푼다)."""
    yield


def test_publish_then_remove(tmp_path, monkeypatch):
    token = os.environ["FACTORY_IMPORT_TOKEN"]
    ctx, settings = _ready(tmp_path, monkeypatch, "PROMPT_ONLY")
    monkeypatch.setenv("FACTORY_IMPORT_TOKEN", token)
    if os.environ.get("CFP_PREVIEW_E2E_FISH"):
        _with_fish(monkeypatch)
    settings = replace(settings, base_url=BASE.rstrip("/"), chat_svc_repo=CHAT)
    published = publish_preview(ctx, "cf-20261113-preview-unit", settings=settings)
    assert published.status == "PUBLISHED", published.failure
    removed = remove_preview(ctx, "cf-20261113-preview-unit", settings=settings)
    assert removed.status == "REMOVED", removed.failure
