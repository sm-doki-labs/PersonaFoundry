"""가짜 비전 판정 모델 (NFR-08). 준비한 함수나 기본값(모든 항목 PASS)으로 판정 JSON을 돌려준다."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from acf.providers.base import VisionRequest, VisionResult

Responder = Callable[[VisionRequest], Any]


def rubric_ids(request: VisionRequest) -> list[str]:
    """판정 프롬프트의 <rubric> 블록에서 항목 ID를 읽는다(가짜 응답을 만들 때 쓴다)."""
    m = re.search(r"<rubric>(.*?)</rubric>", request.prompt, re.S)
    if not m:
        return []
    return re.findall(r"^- ([a-z_]+):", m.group(1), re.M)


def all_pass(request: VisionRequest) -> dict:
    return {
        "schemaVersion": "vision-verdict-v1",
        "items": [{"id": i, "verdict": "PASS", "reason": "가짜 판정"} for i in rubric_ids(request)],
        "fixHint": "",
    }


class FakeVisionModel:
    name = "fake_vision"

    def __init__(self, model: str = "fake-vision", responder: Responder | None = None):
        self.model = model
        self.responder = responder or all_pass
        self.requests: list[VisionRequest] = []

    def judge(self, request: VisionRequest) -> VisionResult:
        self.requests.append(request)
        out = self.responder(request)
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)
        return VisionResult(
            text=text,
            input_tokens=len(request.prompt) // 4,
            output_tokens=len(text) // 4,
            elapsed_ms=1,
            model=self.model,
            provider=self.name,
        )
