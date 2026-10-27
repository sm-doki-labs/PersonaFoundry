"""가짜 TextModel (NFR-08). (stage, ref) 또는 kind 키로 준비한 응답을 돌려준다."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from acf.providers.base import ChatRequest, ChatResponse

Responder = Callable[[ChatRequest], str]


class FakeTextModel:
    name = "fake"

    def __init__(self, model: str = "fake-text", responses: dict[str, Any] | None = None):
        self.model = model
        self.responses: dict[str, Any] = dict(responses or {})
        self.requests: list[ChatRequest] = []

    def add(self, key: str, response: Any) -> None:
        self.responses[key] = response

    def _lookup(self, req: ChatRequest) -> Any:
        for key in (f"{req.stage}:{req.ref}", req.ref, req.kind, "*"):
            if key in self.responses:
                return self.responses[key]
        raise KeyError(f"가짜 응답이 없다: stage={req.stage} ref={req.ref} kind={req.kind}")

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.requests.append(request)
        resp = self._lookup(request)
        if callable(resp):
            resp = resp(request)
        if isinstance(resp, list):
            # 순서대로 소비 (재시도 테스트용)
            if not resp:
                raise KeyError("가짜 응답 목록이 비었다")
            resp = resp.pop(0)
            if callable(resp):
                resp = resp(request)
        text = resp if isinstance(resp, str) else json.dumps(resp, ensure_ascii=False)
        return ChatResponse(
            text=text,
            input_tokens=sum(len(m.content) for m in request.messages) // 4,
            output_tokens=len(text) // 4,
            elapsed_ms=1,
            model=self.model,
            provider=self.name,
        )
