"""Anthropic Messages API 어댑터. 키는 환경변수 이름으로만 받는다.

긴 원문 분석이 끊기지 않도록 스트리밍으로 받는다. 이 모델 계열은 temperature를 받지 않으므로
요청의 temperature는 보내지 않고, 사고 강도는 output_config.effort로 정한다.
"""

from __future__ import annotations

import json
import time

import httpx

from character_factory_poc.common.errors import ProviderRequestError
from character_factory_poc.providers.base import ChatRequest, ChatResponse
from character_factory_poc.providers.openai_compat import (
    _provider_message,
    _secret,
    _transport_error,
)
from character_factory_poc.providers.tracked import native_retry_sleep

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"
_FINISH = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length"}
_CACHE_MIN_CHARS = 4000


class _StreamError(ValueError):
    """스트림 안에서 공급자가 보낸 오류(과부하 등)."""


def _count(value) -> int | None:
    ok = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    return value if ok else None


def normalize_usage(usage: dict | None, stop_reason: str | None) -> dict:
    """Messages API 사용량을 usage-v1로 정리한다. inputTokens는 캐시 읽기·쓰기를 포함한다."""
    finish = _FINISH.get(stop_reason, stop_reason)
    if not isinstance(usage, dict):
        return dict(
            inputTokens=None,
            cachedInputTokens=None,
            cacheWriteTokens=None,
            outputTokens=None,
            reasoningTokens=None,
            finishReason=finish,
            usageSource="missing",
        )
    plain = _count(usage.get("input_tokens"))
    read = _count(usage.get("cache_read_input_tokens"))
    write = _count(usage.get("cache_creation_input_tokens"))
    details = usage.get("output_tokens_details")
    thinking = _count(details.get("thinking_tokens")) if isinstance(details, dict) else None
    total = None if plain is None else plain + (read or 0) + (write or 0)
    return dict(
        inputTokens=total,
        cachedInputTokens=read,
        cacheWriteTokens=write,
        outputTokens=_count(usage.get("output_tokens")),
        reasoningTokens=thinking,
        finishReason=finish,
        usageSource="anthropic_usage",
    )


def collect_stream(lines) -> dict:
    """SSE 줄에서 텍스트·종료 사유·사용량을 모은다. 끝 표시가 없으면 끊긴 응답이다."""
    text, usage, stop, model, done = [], {}, None, None, False
    for line in lines:
        if not line or not line.startswith("data:"):
            continue
        event = json.loads(line[5:].strip())
        kind = event.get("type")
        if kind == "message_start":
            message = event.get("message") or {}
            model = message.get("model")
            usage.update(message.get("usage") or {})
        elif kind == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "text_delta":
                text.append(delta.get("text", ""))
        elif kind == "message_delta":
            stop = (event.get("delta") or {}).get("stop_reason") or stop
            usage.update({k: v for k, v in (event.get("usage") or {}).items() if v is not None})
        elif kind == "message_stop":
            done = True
        elif kind == "error":
            raise _StreamError(str((event.get("error") or {}).get("type") or "stream error"))
    if not done:
        raise ValueError("스트림이 message_stop 없이 끝났다")
    return dict(text="".join(text), usage=usage, stop_reason=stop, model=model)


class AnthropicTextModel:
    name = "anthropic"

    def __init__(
        self,
        model: str,
        api_key_env: str = "ANTHROPIC_API_KEY",
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 900.0,
        max_retries: int = 2,
        effort: str | None = None,
        max_output_tokens: int = 64_000,
    ):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model
        self._api_key_env = api_key_env or "ANTHROPIC_API_KEY"
        self.timeout = timeout
        self.max_retries = max_retries
        self.effort = effort
        self.max_output_tokens = max_output_tokens

    def _headers(self, secret: str | None) -> dict[str, str]:
        headers = {
            "content-type": "application/json",
            "anthropic-version": API_VERSION,
            "user-agent": "character-factory-poc/0.1",
        }
        if secret:
            headers["x-api-key"] = secret
        return headers

    def body(self, request: ChatRequest) -> dict:
        system = "\n\n".join(m.content for m in request.messages if m.role == "system")
        messages: list[dict] = []
        for m in request.messages:
            if m.role == "system":
                continue
            role = "assistant" if m.role == "assistant" else "user"
            if messages and messages[-1]["role"] == role:
                messages[-1]["content"][0]["text"] += "\n\n" + m.content
            else:
                messages.append({"role": role, "content": [{"type": "text", "text": m.content}]})
        if not messages or messages[0]["role"] != "user":
            raise ValueError("Anthropic 요청은 사용자 메시지로 시작해야 한다")
        if request.response_json:
            # 시스템에 붙여야 재시도 때 첫 사용자 블록(긴 원문)이 그대로 남아 캐시가 맞는다.
            system = (system + "\n\n" if system else "") + "설명 없이 JSON 객체 하나만 반환한다."
        # 재시도 대화는 같은 긴 원문을 다시 보내므로 첫 사용자 블록을 캐시한다.
        first = messages[0]["content"][0]
        if len(first["text"]) >= _CACHE_MIN_CHARS:
            first["cache_control"] = {"type": "ephemeral"}
        body = {
            "model": self.model,
            "max_tokens": max(1, min(int(request.max_output_tokens), self.max_output_tokens)),
            "messages": messages,
            "stream": True,
        }
        if system:
            body["system"] = system
        if self.effort:
            body["output_config"] = {"effort": self.effort}
        return body

    def complete(self, request: ChatRequest) -> ChatResponse:
        url = f"{self.base_url}/messages"
        secret = _secret(self._api_key_env)
        body = self.body(request)
        headers = self._headers(secret)
        delay = 2.0
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.monotonic()
            try:
                timeout = httpx.Timeout(self.timeout, connect=30.0)
                with (
                    httpx.Client(timeout=timeout) as client,
                    client.stream("POST", url, json=body, headers=headers) as r,
                ):
                    if r.status_code in (429, 529) or r.status_code >= 500:
                        r.read()
                        last_exc = httpx.HTTPStatusError(
                            f"status {r.status_code}", request=r.request, response=r
                        )
                    elif not r.is_success:
                        r.read()
                        raise ProviderRequestError(r.status_code, _provider_message(r, secret))
                    else:
                        data = collect_stream(r.iter_lines())
                        usage = normalize_usage(data["usage"], data["stop_reason"])
                        return ChatResponse(
                            text=data["text"],
                            input_tokens=usage["inputTokens"],
                            output_tokens=usage["outputTokens"],
                            elapsed_ms=int((time.monotonic() - t0) * 1000),
                            model=data.get("model") or self.model,
                            provider=self.name,
                            finish_reason=usage["finishReason"],
                            raw={"stop_reason": data["stop_reason"], "usage": data["usage"]},
                            usage=usage,
                        )
            except (httpx.TransportError, ValueError) as exc:
                last_exc = exc
            if attempt >= self.max_retries:
                break
            status = getattr(getattr(last_exc, "response", None), "status_code", None)
            native_retry_sleep(time.sleep, delay, 429 if status == 529 else status)
            delay *= 2
        raise _transport_error(last_exc, "Anthropic 호출 실패") from last_exc
