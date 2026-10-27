"""Grok OAuth 영상 어댑터 (D-0044, P-11). API 키 대신 로그인 토큰을 Bearer로 보낸다.

공식 문서로 확인한 것(2026-10-27, docs.x.ai/developers/model-capabilities/video/generation.md):
POST {base}/videos/generations에 model·prompt·image·duration·aspect_ratio·resolution·
generate_audio를 보내면 request_id가 돌아오고, GET {base}/videos/{request_id}를 status가
pending·done·failed 가운데 하나가 될 때까지 조회한다. done이면 video.url·video.duration·model,
failed면 error.code·error.message가 온다. 결과 URL은 임시 주소라 바로 내려받아야 한다. 입력 이미지는
url·file_id를 받고 첫 프레임이 되며, 길이는 1~15초(기본 8초), 해상도는 480p·720p·1080p다.
가격표(2026-10-27)는 영상 1초당 과금이다. 같은 문서의 모든 호출 예시는
`Authorization: Bearer $XAI_API_KEY`를 쓰고, API 키는 Management API에서 팀에 발급한다.

확인하지 못한 것(2026-10-27): xAI OAuth 로그인 접근 토큰을 api.x.ai의 영상 엔드포인트에 Bearer로
보냈을 때 받아 주는지 공식 문서에서 확인하지 못했다. 공식 문서의 OAuth 언급은 Grok CLI의
`grok login`, auth.x.ai, cli-chat-proxy.grok.com 경로에 한정된다. 로컬 opencodex 설정이 xai를
api.x.ai/v1 + authMode=oauth로 두고 있는 것은 확인했지만 공식 근거가 아니다. 영상 호출은 P-03·P-24에
따라 실제로 부르지 않는다. 따라서 실제 성공과 xAI 이용 조건 준수는 미확인이고, 토큰 갱신도 하지
않는다.

토큰은 opencodex auth.json의 xai.accounts 가운데 xai.activeAccountId와 id가 같은 계정의
credential.access에서 읽고, credential.expires는 epoch 밀리초로 가정해 검증한다(2026-10-27 로컬
파일에서 13자리 값 확인). 토큰 값은 repr·예외 메시지·원장에 넣지 않는다. 만료됐으면 새로 고침 없이
opencodex에서 다시 로그인하라는 오류를 낸다. 요청 본문·상태 처리·비용 추정은 xai_video와 같은 코드를
상속해 쓴다. 다만 2026-10-27 문서의 가격표는 해상도 구분 없는 초당 단가라 xai_video의
2026-10-21 표와 다르다. 비용은 비교용 추정치다.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from character_factory_poc.common.errors import VideoGenerationError, VideoTimeoutError
from character_factory_poc.providers.base import VideoRequest, VideoResult
from character_factory_poc.providers.xai_video import XaiVideoModel

DEFAULT_MODEL = "grok-imagine-video-1.5-lite"
DEFAULT_BASE_URL = "https://api.x.ai/v1"
LOGIN_HINT = "opencodex에서 xAI 계정에 다시 로그인한다"


def default_token_file() -> Path:
    """기본 인증 파일. 테스트가 HOME을 바꿀 수 있게 호출할 때 계산한다."""
    return Path.home() / ".opencodex" / "auth.json"


class TokenSource:
    """opencodex auth.json 또는 환경변수에서 xAI OAuth access 토큰을 읽는다.

    token_env가 있으면 파일보다 먼저 쓴다. 토큰 값은 필드에 저장하지 않고, repr에도 넣지 않는다.
    파일 경로는 기본 ~/.opencodex/auth.json이다. 계정은 xai.accounts 가운데 id가
    xai.activeAccountId와 같은 것을 고르고 credential.access를 읽는다.
    """

    def __init__(
        self,
        token_file: str | Path | None = None,
        token_env: str = "",
        now_ms: Callable[[], int] | None = None,
    ):
        self.token_file = Path(token_file).expanduser() if token_file else default_token_file()
        self.token_env = token_env.strip()
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))

    @classmethod
    def from_file(cls, path: str | Path) -> TokenSource:
        return cls(token_file=path)

    @classmethod
    def from_env(cls, name: str) -> TokenSource:
        return cls(token_env=name)

    def __repr__(self) -> str:
        return f"TokenSource(token_file={self.token_file!s}, token_env={self.token_env!r})"

    def token(self) -> str:
        if self.token_env:
            return self._from_env()
        return self._from_file(self.token_file)

    def _from_env(self) -> str:
        value = os.environ.get(self.token_env)
        if not value:
            raise VideoGenerationError(
                f"환경변수 {self.token_env}에 xAI OAuth 토큰이 없다. {LOGIN_HINT}"
            )
        return value

    def _from_file(self, path: Path) -> str:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            raise VideoGenerationError(
                f"opencodex 인증 파일을 읽지 못했다: {path}. {LOGIN_HINT}"
            ) from None
        try:
            data = json.loads(raw)
        except ValueError:
            raise VideoGenerationError(
                f"opencodex 인증 파일이 JSON이 아니다: {path}. {LOGIN_HINT}"
            ) from None

        xai = data.get("xai") if isinstance(data, dict) else None
        if not isinstance(xai, dict):
            raise VideoGenerationError(
                f"opencodex 인증 파일에 xai 설정이 없다: {path}. {LOGIN_HINT}"
            )
        accounts = xai.get("accounts")
        active = xai.get("activeAccountId")
        account = None
        if isinstance(accounts, list):
            account = next(
                (a for a in accounts if isinstance(a, dict) and a.get("id") == active),
                None,
            )
        if account is None:
            raise VideoGenerationError(
                f"opencodex 인증 파일에서 활성 xAI 계정을 찾지 못했다: {path}. {LOGIN_HINT}"
            )

        credential = account.get("credential")
        if not isinstance(credential, dict):
            raise VideoGenerationError(f"활성 xAI 계정에 credential이 없다: {path}. {LOGIN_HINT}")
        token = credential.get("access")
        if not isinstance(token, str) or not token:
            raise VideoGenerationError(f"활성 xAI 계정에 access 토큰이 없다: {path}. {LOGIN_HINT}")
        expires = credential.get("expires")
        if expires is None:
            raise VideoGenerationError(
                f"활성 xAI 계정에 만료 시각(credential.expires)이 없다: {path}. {LOGIN_HINT}"
            )
        try:
            expires_ms = float(expires)
        except (TypeError, ValueError):
            raise VideoGenerationError(
                f"활성 xAI 계정의 credential.expires가 숫자가 아니다: {path}. {LOGIN_HINT}"
            ) from None
        if expires_ms <= self._now_ms():
            raise VideoGenerationError(
                f"xAI OAuth 토큰이 만료됐다(credential.expires는 epoch 밀리초로 본다). {LOGIN_HINT}"
            )
        return token


class GrokOAuthVideoModel(XaiVideoModel):
    """xAI 영상 API를 OAuth 로그인 토큰으로 부르는 VideoModel. 실제 호출은 아직 검증하지 않았다.

    요청 본문·조회·다운로드·비용 추정은 XaiVideoModel을 그대로 상속한다. 다른 점은 인증 헤더와
    provider 이름뿐이다. 토큰이 없거나 만료됐으면 네트워크를 부르기 전에 다시 로그인하라는
    오류를 낸다.
    """

    name = "grok_oauth"
    resumable = True

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        token_file: str | Path | None = None,
        token_env: str = "",
        base_url: str = DEFAULT_BASE_URL,
        poll_interval_s: float = 5.0,
        timeout_s: float = 600.0,
        prices: dict[str, dict[str, float]] | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        token_source: TokenSource | None = None,
        now_ms: Callable[[], int] | None = None,
    ):
        self.token_source = token_source or TokenSource(
            token_file=token_file, token_env=token_env, now_ms=now_ms
        )
        super().__init__(
            model=model,
            api_key_env="",
            base_url=base_url,
            poll_interval_s=poll_interval_s,
            timeout_s=timeout_s,
            prices=prices,
            client=client,
            sleep=sleep,
            clock=clock,
        )

    def __repr__(self) -> str:
        return (
            f"GrokOAuthVideoModel(model={self.model!r}, base_url={self.base_url!r}, "
            f"token_source={self.token_source!r})"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token_source.token()}",
            "Content-Type": "application/json",
        }

    def _scrub(self, message: str) -> str:
        """공급자 응답이 토큰을 되돌려 줘도 오류 메시지에 남기지 않는다."""
        try:
            token = self.token_source.token()
        except VideoGenerationError:
            return message
        if len(token) >= 8 and token in message:
            return message.replace(token, "***")
        return message

    def submit(self, request: VideoRequest) -> str:
        try:
            return super().submit(request)
        except VideoGenerationError as e:
            raise VideoGenerationError(self._scrub(str(e))) from None

    def collect(self, job_id: str, request: VideoRequest) -> VideoResult:
        try:
            return super().collect(job_id, request)
        except VideoTimeoutError as e:
            # job_id를 잃으면 이어 받을 수 없으므로 시간 초과 유형을 유지한다.
            raise VideoTimeoutError(e.job_id, self._scrub(str(e))) from None
        except VideoGenerationError as e:
            raise VideoGenerationError(self._scrub(str(e))) from None
