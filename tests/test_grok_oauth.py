"""Grok OAuth 영상 어댑터 오프라인 테스트 (D-0044, P-11). 실제 인증 파일·네트워크를 쓰지 않는다."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.errors import VideoGenerationError, VideoTimeoutError
from character_factory_poc.providers.base import VideoRequest
from character_factory_poc.providers.factory import make_video_model
from character_factory_poc.providers.fake_image import solid_png
from character_factory_poc.providers.fake_video import FAKE_MP4
from character_factory_poc.providers.grok_oauth import GrokOAuthVideoModel, TokenSource

TOKEN = "oauth-access-token-for-tests-123456"
FUTURE_MS = 4_000_000_000_000  # 2096년쯤. epoch 밀리초로 해석되는지 확인하는 값
NOW_MS = 1_700_000_000_000  # 2023-11-14 UTC


def _auth(
    path: Path,
    accounts: list[dict],
    active: str | None,
) -> Path:
    path.write_text(
        json.dumps({"xai": {"activeAccountId": active, "accounts": accounts}}),
        encoding="utf-8",
    )
    return path


def _account(account_id: str, token: str = TOKEN, expires: int = FUTURE_MS) -> dict:
    return {
        "id": account_id,
        "credential": {"access": token, "expires": expires},
    }


def _req(tmp_path: Path, **kw) -> VideoRequest:
    frame = tmp_path / "frame.png"
    frame.write_bytes(solid_png(4, 4, (1, 2, 3)))
    return VideoRequest(
        stage="s5",
        prompt="smile",
        ref="x",
        first_frame=str(frame),
        **kw,
    )


def _no_network(request: httpx.Request) -> httpx.Response:
    pytest.fail("네트워크를 부르면 안 된다")


def _model(
    *,
    token_file: str | Path | None = None,
    token_env: str = "",
    handler=None,
    **kw,
) -> GrokOAuthVideoModel:
    if handler is None:
        handler = _no_network
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GrokOAuthVideoModel(
        token_file=token_file,
        token_env=token_env,
        client=client,
        sleep=lambda s: None,
        **kw,
    )


def test_submit_poll_download(tmp_path: Path):
    auth = _auth(tmp_path / "auth.json", [_account("acc-1")], "acc-1")
    seen: list[httpx.Request] = []
    polls = iter(["pending", "pending", "done"])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "req-1"})
        if request.url.path == "/v1/videos/req-1":
            status = next(polls)
            body: dict = {"status": status}
            if status == "done":
                body["video"] = {"url": "https://cdn.example/v.mp4", "duration": 8}
            return httpx.Response(200, json=body)
        if request.url.host == "cdn.example":
            return httpx.Response(200, content=FAKE_MP4)
        return httpx.Response(404)

    m = _model(
        token_file=auth,
        handler=handler,
        model="grok-imagine-video-1.5-lite",
        base_url="https://api.x.ai/v1",
        now_ms=lambda: NOW_MS,
    )
    req = _req(tmp_path, aspect_ratio="9:16")
    job = m.submit(req)
    assert job == "req-1"

    post = seen[0]
    assert post.url.path == "/v1/videos/generations"
    assert post.headers["authorization"] == f"Bearer {TOKEN}"
    body = json.loads(post.content)
    assert body["model"] == "grok-imagine-video-1.5-lite"
    assert body["prompt"] == "smile"
    assert body["image"]["url"].startswith("data:image/png;base64,")
    assert (body["duration"], body["resolution"], body["generate_audio"]) == (8, "720p", False)
    assert body["aspect_ratio"] == "9:16"

    res = m.collect(job, req)
    assert res.data == FAKE_MP4 and res.seconds == 8.0
    assert res.job_id == "req-1" and res.provider == "grok_oauth"
    assert res.est_cost_usd == pytest.approx(8 * 0.03 + 0.01)
    assert seen[-1].url.host == "cdn.example"
    assert "authorization" not in {k.lower() for k in seen[-1].headers}


def test_expired_token_is_rejected_before_network(tmp_path: Path):
    auth = _auth(
        tmp_path / "auth.json",
        [_account("acc-1", expires=NOW_MS - 1)],
        "acc-1",
    )
    m = _model(token_file=auth, now_ms=lambda: NOW_MS)
    with pytest.raises(VideoGenerationError, match="opencodex에서 xAI 계정에 다시 로그인한다"):
        m.submit(_req(tmp_path))


def test_expires_is_milliseconds_not_seconds(tmp_path: Path):
    auth = _auth(
        tmp_path / "auth.json",
        [_account("acc-1", expires=1_800_000_000)],
        "acc-1",
    )
    m = _model(token_file=auth, now_ms=lambda: NOW_MS)
    with pytest.raises(VideoGenerationError, match="만료"):
        m.submit(_req(tmp_path))


def test_missing_active_account_asks_to_login(tmp_path: Path):
    auth = _auth(tmp_path / "auth.json", [_account("acc-1")], "acc-2")
    m = _model(token_file=auth)
    with pytest.raises(VideoGenerationError, match="활성 xAI 계정을 찾지 못했다"):
        m.submit(_req(tmp_path))


def test_token_does_not_leak_into_error_or_repr(tmp_path: Path):
    auth = _auth(tmp_path / "auth.json", [_account("acc-1")], "acc-1")

    def handler(request: httpx.Request) -> httpx.Response:
        # 공급자가 실수로 토큰을 되돌려 줘도 메시지에 남기지 않는지 확인한다.
        return httpx.Response(401, text=f"invalid credential: {TOKEN}")

    m = _model(token_file=auth, handler=handler)
    with pytest.raises(VideoGenerationError) as e:
        m.submit(_req(tmp_path))
    assert TOKEN not in str(e.value)
    assert TOKEN not in repr(m)
    assert TOKEN not in repr(m.token_source)


def test_selects_active_account(tmp_path: Path):
    auth = _auth(
        tmp_path / "auth.json",
        [
            _account("acc-1", token="first-account-token-0001"),
            _account("acc-2", token="second-account-token-0002"),
        ],
        "acc-2",
    )
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"request_id": "req-2"})

    m = _model(token_file=auth, handler=handler)
    assert m.submit(_req(tmp_path)) == "req-2"
    assert seen[0].headers["authorization"] == "Bearer second-account-token-0002"


def test_token_env_takes_precedence_over_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"request_id": "req-env"})

    monkeypatch.setenv("CFP_TEST_XAI_OAUTH", "env-token-value-123456")
    m = _model(
        token_env="CFP_TEST_XAI_OAUTH",
        token_file=tmp_path / "missing.json",
        handler=handler,
    )
    assert m.submit(_req(tmp_path)) == "req-env"
    assert seen[0].headers["authorization"] == "Bearer env-token-value-123456"


def test_timeout_keeps_job_id_for_resume(tmp_path: Path):
    auth = _auth(tmp_path / "auth.json", [_account("acc-1")], "acc-1")
    ticks = iter(range(0, 10_000, 100))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "pending"})

    m = _model(
        token_file=auth,
        handler=handler,
        timeout_s=250,
        clock=lambda: next(ticks),
    )
    with pytest.raises(VideoTimeoutError) as e:
        m.collect("req-timeout", _req(tmp_path))
    assert e.value.job_id == "req-timeout"


def test_factory_registers_grok_oauth_and_lists_it_in_error(tmp_path: Path):
    auth = _auth(tmp_path / "auth.json", [_account("acc-1")], "acc-1")
    m = make_video_model(
        ProviderConfig(
            adapter="grok_oauth",
            model="grok-imagine-video-1.5",
            base_url="https://api.x.ai/v1",
            extra={
                "token_file": str(auth),
                "poll_interval_s": 2,
                "timeout_s": 300,
            },
        )
    )
    assert isinstance(m, GrokOAuthVideoModel)
    assert m.name == "grok_oauth" and m.resumable is True
    assert m.model == "grok-imagine-video-1.5"
    assert (m.poll_interval_s, m.timeout_s) == (2.0, 300.0)
    assert m.token_source.token_file == auth

    with pytest.raises(ValueError, match="grok_oauth"):
        make_video_model(ProviderConfig(adapter="sora"))


def test_token_source_from_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    auth = _auth(tmp_path / "auth.json", [_account("acc-1")], "acc-1")
    assert TokenSource.from_file(auth).token() == TOKEN
    monkeypatch.setenv("CFP_TEST_XAI_HELPER", "helper-token-123456")
    assert TokenSource.from_env("CFP_TEST_XAI_HELPER").token() == "helper-token-123456"


def test_default_token_path_is_lazy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """모델을 만들 때 실제 ~/.opencodex/auth.json을 읽지 않는다."""
    missing = tmp_path / "missing-auth.json"
    target = "character_factory_poc.providers.grok_oauth.default_token_file"
    monkeypatch.setattr(target, lambda: missing)
    m = _model()
    assert m.token_source.token_file == missing
    with pytest.raises(VideoGenerationError, match="인증 파일을 읽지 못했다"):
        m.submit(_req(tmp_path))
