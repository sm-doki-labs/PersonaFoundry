"""Grok 영상 기본 경로(D-0183): 로그인 먼저, 안 되면 API 키.

실제 인증 파일·네트워크를 쓰지 않는다.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import VideoGenerationError
from character_factory_poc.providers.factory import make_video_model
from character_factory_poc.providers.fake_video import FAKE_MP4
from character_factory_poc.providers.grok_chain import GrokVideoChain
from character_factory_poc.providers.grok_oauth import GrokOAuthVideoModel
from character_factory_poc.providers.xai_video import XaiVideoModel
from tests.test_grok_oauth import TOKEN, _account, _auth, _req

KEY = "api-key-for-tests-abcdef"


class Fake:
    """xAI 영상 API 흉내. 인증 헤더별 응답을 정하고 호출을 적는다."""

    def __init__(self, submit=None, lookup=None):
        self.calls: list[tuple[str, str, str]] = []
        self.submit = submit or {}
        self.lookup = lookup or {}

    def who(self, request: httpx.Request) -> str:
        auth = request.headers.get("authorization", "")
        return "oauth" if auth == f"Bearer {TOKEN}" else "key" if auth == f"Bearer {KEY}" else "?"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        who = self.who(request)
        path = request.url.path
        self.calls.append((request.method, path, who))
        if request.method == "POST":
            status = self.submit.get(who, 200)
            if status != 200:
                return httpx.Response(status, json={"error": "refused"})
            return httpx.Response(200, json={"request_id": f"job-{who}"})
        if path.startswith("/v1/videos/"):
            status = self.lookup.get(who, 200)
            if status != 200:
                return httpx.Response(status, json={"error": "nope"})
            return httpx.Response(
                200,
                json={
                    "status": "done",
                    "video": {"url": "https://files.invalid/v.mp4", "duration": 2},
                },
            )
        return httpx.Response(200, content=FAKE_MP4)


def _chain(tmp_path: Path, fake: Fake, *, login=True, key=True, monkeypatch=None):
    auth = (
        _auth(tmp_path / "auth.json", [_account("a1")], "a1") if login else tmp_path / "none.json"
    )
    if monkeypatch is not None:
        if key:
            monkeypatch.setenv("XAI_API_KEY", KEY)
        else:
            monkeypatch.delenv("XAI_API_KEY", raising=False)
    client = httpx.Client(transport=httpx.MockTransport(fake))
    oauth = GrokOAuthVideoModel(token_file=auth, client=client, sleep=lambda s: None)
    api = XaiVideoModel(client=client, sleep=lambda s: None)
    return GrokVideoChain([oauth, api])


def test_login_is_first(tmp_path, monkeypatch):
    fake = Fake()
    chain = _chain(tmp_path, fake, monkeypatch=monkeypatch)
    assert chain.name == "grok_oauth"
    req = _req(tmp_path, duration=2, resolution="480p")
    result = chain.collect(chain.submit(req), req)
    assert result.provider == "grok_oauth" and result.data == FAKE_MP4
    assert {who for _, _, who in fake.calls if who != "?"} == {"oauth"}


def test_no_login_uses_api_key_without_calling_login(tmp_path, monkeypatch):
    fake = Fake()
    chain = _chain(tmp_path, fake, login=False, monkeypatch=monkeypatch)
    assert chain.name == "xai_video"
    req = _req(tmp_path)
    result = chain.collect(chain.submit(req), req)
    assert result.provider == "xai_video"
    assert "oauth" not in {who for _, _, who in fake.calls}
    assert chain.skipped and chain.skipped[0].startswith("grok_oauth:")


@pytest.mark.parametrize("status", [401, 402, 403])
def test_refused_login_hands_off_to_api_key(tmp_path, monkeypatch, status):
    fake = Fake(submit={"oauth": status})
    chain = _chain(tmp_path, fake, monkeypatch=monkeypatch)
    req = _req(tmp_path)
    job = chain.submit(req)
    assert job == "job-key" and chain.name == "xai_video"
    posts = [who for method, _, who in fake.calls if method == "POST"]
    assert posts == ["oauth", "key"]


def test_other_errors_are_not_retried_on_another_path(tmp_path, monkeypatch):
    fake = Fake(submit={"oauth": 400})
    chain = _chain(tmp_path, fake, monkeypatch=monkeypatch)
    with pytest.raises(VideoGenerationError, match="HTTP 400"):
        chain.submit(_req(tmp_path))
    assert [who for method, _, who in fake.calls if method == "POST"] == ["oauth"]


def test_nothing_available_stops_before_network(tmp_path, monkeypatch):
    fake = Fake()
    chain = _chain(tmp_path, fake, login=False, key=False, monkeypatch=monkeypatch)
    with pytest.raises(
        VideoGenerationError, match="opencodex에서 xAI 계정에 로그인하거나 XAI_API_KEY"
    ):
        chain.submit(_req(tmp_path))
    assert fake.calls == []


def test_resumed_job_is_looked_up_on_each_path(tmp_path, monkeypatch):
    fake = Fake(lookup={"oauth": 404})
    chain = _chain(tmp_path, fake, monkeypatch=monkeypatch)
    req = _req(tmp_path)
    result = chain.collect("job-from-earlier-run", req)
    assert result.provider == "xai_video"
    looked = [who for method, path, who in fake.calls if method == "GET" and "/videos/" in path]
    assert looked == ["oauth", "key"]


def test_factory_builds_login_first_chain(tmp_path, monkeypatch):
    auth = _auth(tmp_path / "auth.json", [_account("a1")], "a1")
    monkeypatch.setenv("XAI_API_KEY", KEY)
    model = make_video_model(
        ProviderConfig(
            adapter="grok", model="grok-imagine-video-1.5", extra={"token_file": str(auth)}
        )
    )
    assert isinstance(model, GrokVideoChain)
    assert [m.name for m in model.members] == ["grok_oauth", "xai_video"]
    assert model.model == "grok-imagine-video-1.5" and model.name == "grok_oauth"
    keyed = make_video_model(ProviderConfig(adapter="grok", extra={"order": ["xai_video"]}))
    assert [m.name for m in keyed.members] == ["xai_video"]
    with pytest.raises(ValueError, match="order"):
        make_video_model(ProviderConfig(adapter="grok", extra={"order": ["grok_web"]}))


def test_example_config_defaults_to_login_first():
    import tomllib

    root = Path(__file__).resolve().parents[1]
    video = tomllib.loads((root / "factory.example.toml").read_text("utf-8"))["providers"]["video"]
    assert video["adapter"] == "grok" and video["order"] == ["grok_oauth", "xai_video"]


def test_testpath_client_prefers_login(tmp_path, monkeypatch):
    from character_factory_poc.testpath.videos import VideoApiError, XaiFramesClient

    auth = _auth(tmp_path / "auth.json", [_account("a1")], "a1")
    monkeypatch.setenv("XAI_API_KEY", KEY)
    client = XaiFramesClient(token_file=str(auth))
    assert [name for name, _ in client._auth_options()] == ["grok_oauth", "xai_video"]
    assert client._headers()["Authorization"] == f"Bearer {TOKEN}"
    monkeypatch.delenv("XAI_API_KEY")
    missing = XaiFramesClient(token_file=str(tmp_path / "none.json"))
    with pytest.raises(VideoApiError, match="인증이 없다"):
        missing._auth_options()


def test_route_summary_names_the_path(tmp_path, monkeypatch):
    from character_factory_poc.providers.grok_chain import route_summary

    auth = _auth(tmp_path / "auth.json", [_account("a1")], "a1")
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    login = ProviderConfig(
        adapter="grok", model="grok-imagine-video-1.5-lite", extra={"token_file": str(auth)}
    )
    assert route_summary(login) == "영상: Grok 로그인(opencodex) · grok-imagine-video-1.5-lite"
    monkeypatch.setenv("XAI_API_KEY", KEY)
    none = ProviderConfig(adapter="grok", extra={"token_file": str(tmp_path / "none.json")})
    assert "xAI API 키" in route_summary(none) and "넘어감" in route_summary(none)
    assert route_summary(ProviderConfig()) == "영상: 시험용 가짜 영상(비용 없음)"
