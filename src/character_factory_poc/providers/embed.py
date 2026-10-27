"""로컬 참고 자료 검색용 임베딩 포트. 실제 임베더 연결은 미결이다."""

from __future__ import annotations

import hashlib
import math
import unicodedata
from typing import Protocol


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """한글 음절을 보존한 문자 1~3-gram을 안정적으로 해싱한다."""

    name = "hash-v1"

    def __init__(self, dim: int = 256):
        if isinstance(dim, bool) or not isinstance(dim, int) or dim < 8:
            raise ValueError("임베딩 dim은 8 이상의 정수여야 한다")
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            normalized = " ".join(unicodedata.normalize("NFC", text).casefold().split())
            vector = [0.0] * self.dim
            for n in (1, 2, 3):
                for start in range(len(normalized) - n + 1):
                    gram = normalized[start : start + n]
                    if not gram.strip():
                        continue
                    digest = hashlib.blake2b(gram.encode("utf-8"), digest_size=8).digest()
                    slot = int.from_bytes(digest[:4], "big") % self.dim
                    vector[slot] += 1.0 if digest[4] & 1 else -1.0
            norm = math.sqrt(sum(v * v for v in vector))
            result.append([v / norm for v in vector] if norm else vector)
        return result


def make_embedder(name: str) -> Embedder:
    if name == "hash-v1":
        return HashEmbedder()
    raise ValueError(f"알 수 없는 임베더: {name}. 실제 임베더는 아직 연결하지 않았다(미결 질문)")


def cosine(a: list[float], b: list[float]) -> float:
    """영벡터의 유사도는 0이며, 차원 불일치·비유한 값은 거절한다."""
    if len(a) != len(b):
        raise ValueError("cosine 벡터의 차원이 다르다")
    if not all(math.isfinite(v) for v in (*a, *b)):
        raise ValueError("cosine 벡터에 비유한 값이 있다")
    na = math.sqrt(sum(v * v for v in a))
    nb = math.sqrt(sum(v * v for v in b))
    if not na or not nb:
        return 0.0
    return max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)))
