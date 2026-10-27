"""가짜 ImageGen (NFR-08). 프롬프트 해시로 색을 정한 단색 PNG를 돌려준다. 네트워크를 쓰지 않는다."""

from __future__ import annotations

import hashlib
import re
import struct
import zlib

from character_factory_poc.providers.base import ImageRequest, ImageResult


def solid_png(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _shape(size: str) -> tuple[int, int]:
    """요청 크기의 비율을 지킨 작은 이미지 크기(긴 변 64). 읽지 못하면 64×64."""
    m = re.match(r"^(\d+)x(\d+)", size or "")
    if not m:
        return 64, 64
    w, h = int(m.group(1)), int(m.group(2))
    scale = 64 / max(w, h)
    return max(1, round(w * scale)), max(1, round(h * scale))


class FakeImageModel:
    name = "fake_image"

    def __init__(self, model: str = "fake-image"):
        self.model = model
        self.requests: list[ImageRequest] = []

    def generate(self, request: ImageRequest) -> ImageResult:
        self.requests.append(request)
        h = hashlib.sha256(request.prompt.encode("utf-8")).digest()
        w, ht = _shape(request.size)
        return ImageResult(
            data=solid_png(w, ht, (h[0], h[1], h[2])),
            mime="image/png",
            model=self.model,
            provider=self.name,
            elapsed_ms=1,
            est_cost_usd=0.0,
        )
