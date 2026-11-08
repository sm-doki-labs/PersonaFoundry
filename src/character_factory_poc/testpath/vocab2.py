"""외모 어휘 v2: 외모군을 나누는 cluster 칸과 프롬프트용 detail 칸."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

UNKNOWN = "unknown"
VOCAB_FILE = "appearance-tag-vocab-v2.json"


@cache
def load_vocab2() -> dict[str, Any]:
    text = (
        resources.files("character_factory_poc.resources").joinpath(VOCAB_FILE).read_text("utf-8")
    )
    return json.loads(text)


def cluster_single(vocab: dict[str, Any]) -> dict[str, Any]:
    return vocab["cluster"]["single"]


def cluster_multi(vocab: dict[str, Any]) -> dict[str, Any]:
    return vocab["cluster"]["multi"]


def detail_single(vocab: dict[str, Any]) -> dict[str, Any]:
    return vocab["detail"]["single"]


def single_fields(vocab: dict[str, Any]) -> dict[str, Any]:
    """값 하나를 고르는 칸 전체(cluster + detail). 순서는 파일 순서다."""
    return {**cluster_single(vocab), **detail_single(vocab)}


def all_field_names(vocab: dict[str, Any]) -> list[str]:
    return [*single_fields(vocab), *cluster_multi(vocab)]


def phrase(vocab: dict[str, Any], field: str, value: str, lang: str = "en") -> str:
    spec = {**single_fields(vocab), **cluster_multi(vocab)}[field]
    return spec["values"][value][lang]
