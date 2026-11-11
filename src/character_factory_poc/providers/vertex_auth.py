"""Vertex AI 접근 토큰(D-0149). gcloud 로그인으로 받은 토큰을 캐시하고 만료 전에 새로 받는다.

토큰 값은 기록하지 않는다. 받지 못하면 로그인 방법만 알린다.
"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable, Sequence

DEFAULT_COMMAND = ("gcloud", "auth", "application-default", "print-access-token")
#: gcloud 접근 토큰은 1시간 유효하다. 여유를 두고 45분마다 새로 받는다.
DEFAULT_TTL_S = 45 * 60


def _run(command: Sequence[str]) -> str:
    return subprocess.run(
        list(command), capture_output=True, text=True, timeout=30, check=True
    ).stdout


def vertex_openai_base_url(project: str, location: str = "global") -> str:
    """Vertex AI의 OpenAI 호환 chat/completions 주소(끝의 /chat/completions 앞까지)."""
    if not project:
        raise ValueError("vertex_openai에는 project가 필요하다")
    host = (
        "aiplatform.googleapis.com"
        if location == "global"
        else f"{location}-aiplatform.googleapis.com"
    )
    return f"https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi"


class GcloudToken:
    def __init__(
        self,
        command: Sequence[str] = DEFAULT_COMMAND,
        ttl_s: float = DEFAULT_TTL_S,
        runner: Callable[[Sequence[str]], str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.command = tuple(command)
        self.ttl_s = ttl_s
        self._runner = runner
        self._clock = clock
        self._lock = threading.Lock()
        self._token: str | None = None
        self._at = 0.0

    def get(self) -> str:
        with self._lock:
            if self._token is None or self._clock() - self._at >= self.ttl_s:
                self._fetch()
            return self._token  # type: ignore[return-value]

    def refresh(self) -> str:
        with self._lock:
            self._fetch()
            return self._token  # type: ignore[return-value]

    def _fetch(self) -> None:
        try:
            token = ((self._runner or _run)(self.command) or "").strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(
                "Vertex 접근 토큰을 받지 못했다. gcloud auth application-default login이 필요하다"
            ) from exc
        if not token:
            raise RuntimeError(
                "Vertex 접근 토큰이 비었다. gcloud auth application-default login이 필요하다"
            )
        self._token, self._at = token, self._clock()
