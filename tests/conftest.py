import socket

import pytest


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """기본 테스트는 네트워크를 막는다 (NFR-08)."""

    def guard(*a, **k):
        raise RuntimeError("테스트에서 네트워크 연결은 금지된다")

    monkeypatch.setattr(socket.socket, "connect", guard)
