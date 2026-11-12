"""xAI Imagine image API (grok-imagine-image) on the factory ImageModel port.

With reference images the request goes to /v1/images/edits (up to five images, JSON body,
the output aspect follows the first image); without them to /v1/images/generations. The
response is re-encoded as PNG so callers keep writing PNG files.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from character_factory_poc.common.errors import ImageGenerationError
from character_factory_poc.providers.base import ImageRequest, ImageResult

DEFAULT_BASE = "https://api.x.ai/v1"
MAX_IMAGES = 5


def _data_uri(path: Path) -> str:
    raw = path.read_bytes()
    mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def _to_png(data: bytes) -> bytes:
    import cv2
    import numpy as np

    try:
        img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as exc:
        raise ImageGenerationError("xAI 이미지 응답을 읽을 수 없다") from exc
    if img is None or not img.size:
        raise ImageGenerationError("xAI 이미지 응답을 읽을 수 없다")
    ok, png = cv2.imencode(".png", img)
    if not ok:
        raise ImageGenerationError("xAI 이미지를 PNG로 바꾸지 못했다")
    return png.tobytes()


class XAIImageModel:
    name = "xai_images"

    def __init__(
        self,
        model: str = "grok-imagine-image-2.0",
        *,
        api_key_env: str = "XAI_API_KEY",
        base_url: str = DEFAULT_BASE,
        timeout: float = 180,
        max_retries: int = 0,
        opener=None,
    ):
        self.model = model
        self.api_key_env = api_key_env
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._open = opener or urllib.request.urlopen

    def body(self, request: ImageRequest) -> tuple[str, dict]:
        refs = [Path(p) for p in request.reference_images]
        if any(not p.is_file() for p in refs):
            raise ImageGenerationError("참조 이미지 파일이 없다")
        if len(refs) > MAX_IMAGES:
            raise ImageGenerationError(f"xAI 이미지 편집 참조는 {MAX_IMAGES}장까지다")
        prompt = request.prompt
        if request.negative_prompt:
            prompt += "\n\nAvoid: " + request.negative_prompt
        body: dict = {"model": self.model, "prompt": prompt, "response_format": "b64_json"}
        if not refs:
            return "/images/generations", body
        images = [{"type": "image_url", "url": _data_uri(p)} for p in refs]
        if len(images) == 1:
            body["image"] = images[0]
        else:
            body["images"] = images
        return "/images/edits", body

    def generate(self, request: ImageRequest) -> ImageResult:
        path, body = self.body(request)
        key = os.environ.get(self.api_key_env)
        if not key:
            raise ImageGenerationError(f"{self.api_key_env}가 없다")
        req = urllib.request.Request(
            self.base_url + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        )
        start = time.monotonic()
        last = None
        for attempt in range(self.max_retries + 1):
            try:
                with self._open(req, timeout=self.timeout) as resp:
                    data = json.loads(resp.read())
                break
            except urllib.error.HTTPError as exc:
                last = f"xAI 이미지 호출 실패 HTTP {exc.code}"
                if exc.code < 500 and exc.code != 429:
                    raise ImageGenerationError(last) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last = f"xAI 이미지 호출 실패: {type(exc).__name__}"
            if attempt == self.max_retries:
                raise ImageGenerationError(last)
            time.sleep(2 * (attempt + 1))
        items = data.get("data") or []
        if not items or not items[0].get("b64_json"):
            raise ImageGenerationError("xAI 이미지 응답에 이미지가 없다")
        png = _to_png(base64.b64decode(items[0]["b64_json"]))
        return ImageResult(
            data=png,
            mime="image/png",
            model=self.model,
            provider=self.name,
            elapsed_ms=int((time.monotonic() - start) * 1000),
        )
