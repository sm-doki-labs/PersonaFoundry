import os
import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """기본 테스트는 네트워크를 막는다 (NFR-08)."""

    def guard(*a, **k):
        raise RuntimeError("테스트에서 네트워크 연결은 금지된다")

    monkeypatch.setattr(socket.socket, "connect", guard)


@pytest.fixture(autouse=True)
def fake_tendency_tags(monkeypatch):
    """모티브 S3의 원문 경향 표시(D-0148)는 시험이 따로 정하지 않으면 한 칸으로 표시한다.

    시험이 "s3:<ref>"나 ref로 응답을 정했으면 그 응답을 쓴다.
    """
    from character_factory_poc.providers.fake import FakeTextModel
    from tests.support.tendency import fake_tags, is_tagging

    original = FakeTextModel._lookup

    def lookup(self, req):
        if is_tagging(req) and not {f"{req.stage}:{req.ref}", req.ref} & self.responses.keys():
            return fake_tags
        return original(self, req)

    monkeypatch.setattr(FakeTextModel, "_lookup", lookup)


@pytest.fixture(autouse=True)
def known_target_heads(monkeypatch):
    """실제 적재(CFP_PG_ADMIN_URL)가 없으면 대상 저장소 head를 로컬 체크아웃에서 읽지 않는다.

    파일만 만드는 내보내기 시험이 ~/projects/api-svc 같은 로컬 체크아웃의 상태에 따라
    깨지지 않게 한다. 실제 적재 시험은 CFP_API_SVC_REPO·CFP_CHAT_SVC_REPO가 가리키는
    저장소의 진짜 head를 읽고 검사한다.
    """
    if os.environ.get("CFP_PG_ADMIN_URL"):
        return
    from character_factory_poc.stages.export import export
    from character_factory_poc.stages.export.settings import API_SVC_HEAD, CHAT_SVC_HEAD

    monkeypatch.setattr(
        export,
        "read_heads",
        lambda settings, runner: export.TargetHeads(api_svc=API_SVC_HEAD, chat_svc=CHAT_SVC_HEAD),
    )
