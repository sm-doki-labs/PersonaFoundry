"""공장 소유 Grok 로그인(D-0184).

가짜 xAI 로그인 서버만 쓰고 실제 네트워크·opencodex 파일은 쓰지 않는다.
"""

from __future__ import annotations

import base64
import json
import stat
import urllib.parse
from pathlib import Path

import httpx
import pytest

from character_factory_poc.providers.xai_login import (
    DEFAULT_CLIENT_ID,
    REDIRECT_URI,
    XaiLogin,
    XaiLoginError,
    XaiLoginRequired,
)

DISCOVERY = {
    "authorization_endpoint": "https://auth.x.ai/oauth2/authorize",
    "token_endpoint": "https://auth.x.ai/oauth2/token",
    "device_authorization_endpoint": "https://auth.x.ai/oauth2/device/code",
    "revocation_endpoint": "https://auth.x.ai/oauth2/revoke",
}


def _jwt(claims: dict) -> str:
    seg = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"h.{seg}.s"


class Server:
    def __init__(self, discovery=None):
        self.discovery = discovery or DISCOVERY
        self.forms: list[dict] = []
        self.token_replies: list[httpx.Response] = []
        self.device_reply = httpx.Response(
            200,
            json={
                "device_code": "dev-1",
                "user_code": "ABCD",
                "verification_uri": "https://accounts.x.ai/device",
                "interval": 1,
                "expires_in": 60,
            },
        )
        self.revoked: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json=self.discovery)
        form = dict(urllib.parse.parse_qsl(request.content.decode()))
        if url == DISCOVERY["token_endpoint"]:
            self.forms.append(form)
            return self.token_replies.pop(0)
        if url == DISCOVERY["device_authorization_endpoint"]:
            self.forms.append(form)
            return self.device_reply
        if url == DISCOVERY["revocation_endpoint"]:
            self.revoked.append(form)
            return httpx.Response(200)
        raise AssertionError(url)


def token(access="acc-1", refresh="ref-1", expires_in=21600, email="Tester@Example.com"):
    return httpx.Response(
        200,
        json={
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": expires_in,
            "id_token": _jwt({"sub": "u-1", "email": email}),
        },
    )


def _login(tmp_path: Path, server: Server, now=1000.0) -> XaiLogin:
    clock = {"t": now}
    login = XaiLogin(
        store=tmp_path / "xai-oauth.json",
        http=httpx.Client(transport=httpx.MockTransport(server)),
        now=lambda: clock["t"],
        sleep=lambda s: clock.__setitem__("t", clock["t"] + s),
    )
    login.clock = clock
    return login


def test_authorize_url_uses_pkce_and_registered_redirect(tmp_path):
    login = _login(tmp_path, Server())
    url = login.authorize_url(state="st-1", challenge="ch-1")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    assert url.startswith("https://auth.x.ai/oauth2/authorize?")
    assert q["client_id"] == DEFAULT_CLIENT_ID and q["redirect_uri"] == REDIRECT_URI
    assert q["code_challenge_method"] == "S256" and q["state"] == "st-1"
    assert "offline_access" in q["scope"] and "api:access" in q["scope"]


def test_untrusted_discovery_host_is_refused(tmp_path):
    bad = dict(DISCOVERY, token_endpoint="https://evil.example/token")
    with pytest.raises(XaiLoginError, match="예상과 다르다"):
        _login(tmp_path, Server(bad)).endpoints()


def test_exchange_saves_private_file_without_leaking_token(tmp_path):
    server = Server()
    server.token_replies.append(token())
    login = _login(tmp_path, server)
    cred = login.exchange("code-1", "verifier-1")
    assert server.forms[0]["grant_type"] == "authorization_code"
    assert server.forms[0]["code_verifier"] == "verifier-1"
    assert cred.email == "tester@example.com" and "acc-1" not in repr(cred)
    mode = stat.S_IMODE(login.store.stat().st_mode)
    assert mode == 0o600
    assert login.status() == {
        "loggedIn": True,
        "email": "tester@example.com",
        "expiresInMin": 360.0,
        "store": str(login.store),
    }


def test_valid_token_needs_no_network_and_near_expiry_refreshes_with_rotation(tmp_path):
    server = Server()
    server.token_replies.append(token(expires_in=600))
    login = _login(tmp_path, server)
    login.exchange("c", "v")
    assert login.access_token() == "acc-1" and len(server.forms) == 1  # 10분 남음: 그대로
    login.clock["t"] += 400  # 3분 남음: 갱신
    server.token_replies.append(token(access="acc-2", refresh="ref-2"))
    assert login.access_token() == "acc-2"
    assert server.forms[-1] == {
        "grant_type": "refresh_token",
        "client_id": DEFAULT_CLIENT_ID,
        "refresh_token": "ref-1",
    }
    saved = json.loads(login.store.read_text())
    assert saved["refresh"] == "ref-2" and saved["email"] == "tester@example.com"


def test_refresh_done_by_another_job_is_reused(tmp_path):
    server = Server()
    server.token_replies.append(token(expires_in=100))
    a = _login(tmp_path, server)
    a.exchange("c", "v")
    b = _login(tmp_path, server)
    server.token_replies.append(token(access="acc-2", refresh="ref-2"))
    assert a.access_token() == "acc-2"
    calls = len(server.forms)
    assert b.access_token() == "acc-2" and len(server.forms) == calls  # b는 다시 갱신하지 않는다


def test_rejected_refresh_asks_for_login_again(tmp_path):
    server = Server()
    server.token_replies.append(token(expires_in=10))
    login = _login(tmp_path, server)
    login.exchange("c", "v")
    server.token_replies.append(httpx.Response(400, json={"error": "invalid_grant"}))
    with pytest.raises(XaiLoginRequired, match="cfp grok login"):
        login.access_token()


def test_missing_login_is_reported_before_any_request(tmp_path):
    server = Server()
    login = _login(tmp_path, server)
    with pytest.raises(XaiLoginRequired, match="공장에 Grok 로그인이 없다"):
        login.access_token()
    assert server.forms == [] and login.status()["loggedIn"] is False


def test_device_login_polls_until_approved(tmp_path):
    server = Server()
    server.token_replies += [
        httpx.Response(400, json={"error": "authorization_pending"}),
        httpx.Response(400, json={"error": "slow_down"}),
        token(),
    ]
    login = _login(tmp_path, server)
    shown = []
    cred = login.login_device(on_prompt=lambda url, code: shown.append((url, code)))
    assert shown == [("https://accounts.x.ai/device", "ABCD")]
    assert cred.email == "tester@example.com" and login.store.is_file()
    assert server.forms[-1]["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"


def test_logout_revokes_and_deletes(tmp_path):
    server = Server()
    server.token_replies.append(token())
    login = _login(tmp_path, server)
    login.exchange("c", "v")
    assert login.logout() is True and not login.store.exists()
    assert server.revoked[0]["token"] == "ref-1"
    assert login.logout() is False


def test_video_model_sends_factory_token(tmp_path, monkeypatch):
    """영상 기본 경로는 공장 로그인 토큰을 Bearer로 보낸다."""
    from character_factory_poc.common.config import ProviderConfig
    from character_factory_poc.providers.factory import make_video_model
    from tests.test_grok_oauth import _req

    server = Server()
    server.token_replies.append(token(access="factory-access"))
    import time

    _login(tmp_path, server, now=time.time()).exchange("c", "v")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    seen = []

    def api(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"request_id": "job-1"})

    model = make_video_model(
        ProviderConfig(adapter="grok", extra={"login_file": str(tmp_path / "xai-oauth.json")})
    )
    oauth = model.members[0]
    oauth.client = httpx.Client(transport=httpx.MockTransport(api))
    assert model.name == "grok_oauth"
    assert model.submit(_req(tmp_path)) == "job-1"
    assert seen == ["Bearer factory-access"]
