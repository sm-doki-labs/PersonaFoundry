"""OpenAI Images API(GPT Image 2.6) 직접 호출. 생성(generations)과 편집(edits)을 쓴다.

키 값은 환경변수에서만 읽고 오류 문구·기록에 넣지 않는다.
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE = "https://api.openai.com/v1"


class ImageApiError(RuntimeError):
    pass


@dataclass
class ImageResult:
    data: bytes
    elapsed_ms: int
    usage: dict[str, Any] = field(default_factory=dict)
    revised_prompt: str | None = None


class OpenAIImagesClient:
    def __init__(
        self,
        model: str = "gpt-image-2.6-sunburst",
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str = DEFAULT_BASE,
        timeout: float = 360.0,
        retries: int = 2,
    ):
        self.model = model
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def _key(self) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise ImageApiError(f"{self.api_key_env} 환경변수가 비었다")
        return key

    def _post(self, path: str, **kw: Any) -> tuple[dict[str, Any], int]:
        key = self._key()
        url = f"{self.base_url}{path}"
        last = ""
        for attempt in range(self.retries + 1):
            t0 = time.monotonic()
            try:
                with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=30.0)) as c:
                    r = c.post(url, headers={"Authorization": f"Bearer {key}"}, **kw)
            except httpx.HTTPError as e:
                last = f"전송 실패: {type(e).__name__}"
            else:
                ms = int((time.monotonic() - t0) * 1000)
                if r.status_code == 200:
                    return r.json(), ms
                body = r.text.replace(key, "***")[:800]
                last = f"HTTP {r.status_code}: {body}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    break
            if attempt < self.retries:
                time.sleep(5 * (attempt + 1))
        raise ImageApiError(last)

    @staticmethod
    def _result(data: dict[str, Any], ms: int) -> ImageResult:
        item = (data.get("data") or [{}])[0]
        b64 = item.get("b64_json")
        if not b64:
            raise ImageApiError("응답에 b64_json이 없다")
        try:
            raw = base64.b64decode(b64, validate=True)
        except (binascii.Error, TypeError, ValueError) as exc:
            raise ImageApiError("응답의 이미지 base64가 잘못됐다") from exc
        return ImageResult(
            data=raw,
            elapsed_ms=ms,
            usage=data.get("usage") or {},
            revised_prompt=item.get("revised_prompt"),
        )

    def generate(
        self, prompt: str, *, size: str, quality: str = "high", complexity: str | None = None
    ) -> ImageResult:
        body: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "n": 1,
            "output_format": "png",
        }
        if complexity:
            body["complexity"] = complexity
        data, ms = self._post("/images/generations", json=body)
        return self._result(data, ms)

    def edit(
        self,
        prompt: str,
        images: list[Path],
        *,
        size: str,
        quality: str = "high",
        complexity: str | None = None,
    ) -> ImageResult:
        form: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "quality": quality,
            "n": "1",
            "output_format": "png",
        }
        if complexity:
            form["complexity"] = complexity
        files = [
            (
                "image[]",
                (p.name, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/png"),
            )
            for p in images
        ]
        data, ms = self._post("/images/edits", data=form, files=files)
        return self._result(data, ms)
