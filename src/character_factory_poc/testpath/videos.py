"""시험 경로 5·6번: 영상용 시드 한 장으로 Grok 영상(idle, 애교 반응)을 만든다.

시작·끝 프레임을 같은 이미지로 고정해(xAI first & last frame) 영상이 같은 자세로 시작하고 끝난다.
그래서 idle은 이음매 없이 반복되고, 애교 영상은 idle과 자연스럽게 오간다.
동작 지시문은 공장 동작 노드(S6)의 앱 클립 문장을 그대로 쓴다.
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

PRICE_PER_SECOND = {"480p": 0.08, "720p": 0.14, "1080p": 0.25}  # grok-imagine-video-1.5


class VideoApiError(RuntimeError):
    pass


def _data_uri(path: Path) -> str:
    raw = path.read_bytes()
    mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


@dataclass
class XaiFramesClient:
    model: str = "grok-imagine-video-1.5"
    api_key_env: str = "XAI_API_KEY"
    base_url: str = "https://api.x.ai/v1"
    poll_s: float = 5.0
    timeout_s: float = 900.0

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise VideoApiError(f"{self.api_key_env} 환경변수가 비었다")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    def body(
        self, prompt: str, first: Path, last: Path | None, duration: int, resolution: str
    ) -> dict[str, Any]:
        b: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "image": {"url": _data_uri(first)},
            "duration": duration,
            "resolution": resolution,
        }
        if last is not None:
            b["last_frame"] = {"url": _data_uri(last)}
        return b

    def generate(
        self,
        prompt: str,
        first: Path,
        last: Path | None,
        *,
        duration: int = 6,
        resolution: str = "720p",
    ) -> tuple[bytes, dict[str, Any]]:
        h = self._headers()
        key = h["Authorization"][7:]
        with httpx.Client(timeout=120.0) as c:
            r = c.post(
                f"{self.base_url}/videos/generations",
                headers=h,
                json=self.body(prompt, first, last, duration, resolution),
            )
            if r.status_code >= 400:
                raise VideoApiError(
                    f"제출 실패 HTTP {r.status_code}: {r.text.replace(key, '***')[:500]}"
                )
            job = r.json().get("request_id") or r.json().get("id")
            t0 = time.monotonic()
            while True:
                g = c.get(
                    f"{self.base_url}/videos/{job}", headers={"Authorization": h["Authorization"]}
                )
                if g.status_code >= 400:
                    raise VideoApiError(f"조회 실패 HTTP {g.status_code}: {g.text[:300]}")
                obj = g.json()
                status = str(obj.get("status", "")).lower()
                if status == "done":
                    break
                if status in ("failed", "error", "expired"):
                    raise VideoApiError(
                        f"작업 {job} 실패: {json.dumps(obj, ensure_ascii=False)[:500]}"
                    )
                if time.monotonic() - t0 > self.timeout_s:
                    raise VideoApiError(f"작업 {job} 시간 초과")
                time.sleep(self.poll_s)
            url = (obj.get("video") or {}).get("url") or obj.get("url")
            d = c.get(url)
            if d.status_code >= 400:
                raise VideoApiError(f"다운로드 실패 HTTP {d.status_code}")
        seconds = float((obj.get("video") or {}).get("duration") or duration)
        meta = {
            "jobId": job,
            "model": obj.get("model") or self.model,
            "resolution": resolution,
            "seconds": seconds,
            "elapsedS": round(time.monotonic() - t0, 1),
            "estUsd": round(PRICE_PER_SECOND.get(resolution, 0) * seconds, 3),
            "lastFramePinned": last is not None,
        }
        return d.content, meta
