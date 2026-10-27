"""xAI Grok Imagine 영상 API 어댑터 (D-0028, D-0030). 이미지 → 영상, 비동기 제출·조회·다운로드.

공식 문서(2026-10-21 확인): POST {base}/videos/generations 로 제출하면 request_id가 돌아오고,
GET {base}/videos/{request_id} 를 status가 done(성공)·failed(실패)가 될 때까지 조회한다.
입력 이미지는 공개 URL·base64 data URI·file_id를 받고 영상의 첫 프레임이 된다. 출력 1초당 과금이다.
요청 본문의 이미지 필드 이름과 done·failed 외 상태 이름, 결과 URL 유효 기간은 첫 실제 호출에서
확인한다(LLD §13). 키는 환경변수 이름으로만 받는다.
"""

from __future__ import annotations

import base64
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from acf.common.errors import VideoGenerationError, VideoTimeoutError
from acf.providers.base import VideoRequest, VideoResult

# 출력 영상 1초당 USD (docs.x.ai/developers/pricing, 2026-10-21). 설정으로 덮어쓴다.
DEFAULT_PRICES: dict[str, dict[str, float]] = {
    "grok-imagine-video-1.5": {"480p": 0.08, "720p": 0.14, "1080p": 0.25},
    "grok-imagine-video-1.5-lite": {"480p": 0.02, "720p": 0.03, "1080p": 0.14},
}
IMAGE_INPUT_USD = 0.01  # 모델에 따라 입력 이미지 1장당 붙을 수 있는 값(보수적으로 더한다)
DONE = {"done", "completed", "succeeded"}
FAILED = {"failed", "error", "expired", "cancelled"}


def estimate_cost(
    model: str, resolution: str, seconds: float, prices: dict[str, dict[str, float]] | None = None
) -> float | None:
    table = (prices or DEFAULT_PRICES).get(model)
    if not table or resolution not in table:
        return None
    return round(table[resolution] * seconds + IMAGE_INPUT_USD, 4)


def data_uri(path: str) -> str:
    raw = Path(path).read_bytes()
    mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


class XaiVideoModel:
    name = "xai_video"
    resumable = True

    def __init__(
        self,
        model: str = "grok-imagine-video-1.5-lite",
        api_key_env: str = "XAI_API_KEY",
        base_url: str = "https://api.x.ai/v1",
        poll_interval_s: float = 5.0,
        timeout_s: float = 600.0,
        prices: dict[str, dict[str, float]] | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.model = model
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self.poll_interval_s = poll_interval_s
        self.timeout_s = timeout_s
        self.prices = prices
        self.client = client or httpx.Client(timeout=60.0)
        self.sleep = sleep
        self.clock = clock

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if not key:
            raise VideoGenerationError(
                f"환경변수 {self.api_key_env or '(없음)'}에 xAI API 키가 없다. 실행 전에 설정한다"
            )
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def _request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        """429·5xx는 지수 대기 3회(LLD §9)."""
        last: httpx.Response | None = None
        for attempt in range(4):
            last = self.client.request(method, url, **kw)
            if last.status_code != 429 and last.status_code < 500:
                return last
            if attempt < 3:
                self.sleep(2**attempt)
        assert last is not None
        return last

    def body(self, request: VideoRequest) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": request.prompt,
            "image": {"url": data_uri(request.first_frame)},
            "duration": request.duration,
            "resolution": request.resolution,
            "generate_audio": request.generate_audio,
        }
        if request.aspect_ratio:
            body["aspect_ratio"] = request.aspect_ratio
        return body

    def submit(self, request: VideoRequest) -> str:
        r = self._request(
            "POST",
            f"{self.base_url}/videos/generations",
            headers=self._headers(),
            json=self.body(request),
        )
        if r.status_code >= 400:
            raise VideoGenerationError(f"xAI 영상 제출 실패 HTTP {r.status_code}: {r.text[:300]}")
        job = r.json().get("request_id") or r.json().get("id")
        if not job:
            raise VideoGenerationError(f"xAI 응답에 request_id가 없다: {r.text[:300]}")
        return str(job)

    def collect(self, job_id: str, request: VideoRequest) -> VideoResult:
        t0 = self.clock()
        headers = self._headers()
        while True:
            r = self._request("GET", f"{self.base_url}/videos/{job_id}", headers=headers)
            if r.status_code >= 400:
                raise VideoGenerationError(
                    f"xAI 영상 조회 실패 HTTP {r.status_code}: {r.text[:300]}"
                )
            obj = r.json()
            status = str(obj.get("status", "")).lower()
            if status in DONE:
                break
            if status in FAILED:
                reason = obj.get("error") or obj.get("message") or status
                raise VideoGenerationError(f"xAI 영상 작업 {job_id} 실패: {reason}")
            if self.clock() - t0 > self.timeout_s:
                raise VideoTimeoutError(
                    job_id, f"xAI 영상 작업 {job_id}이 {self.timeout_s:.0f}초 안에 끝나지 않았다"
                )
            self.sleep(self.poll_interval_s)
        video = obj.get("video") or {}
        url = video.get("url") or obj.get("url")
        if not url:
            raise VideoGenerationError(f"xAI 응답에 영상 URL이 없다: {str(obj)[:300]}")
        d = self._request("GET", url)  # 결과 URL은 받는 즉시 내려받는다(유효 기간 미확인)
        if d.status_code >= 400:
            raise VideoGenerationError(f"영상 다운로드 실패 HTTP {d.status_code}")
        seconds = float(video.get("duration") or request.duration)
        return VideoResult(
            data=d.content,
            mime="video/mp4",
            model=str(obj.get("model") or self.model),
            provider=self.name,
            elapsed_ms=int((self.clock() - t0) * 1000),
            job_id=job_id,
            seconds=seconds,
            est_cost_usd=estimate_cost(self.model, request.resolution, seconds, self.prices),
        )
