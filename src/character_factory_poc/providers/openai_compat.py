"""OpenAI 호환 chat/completions 어댑터 (LLD §9). 키는 환경변수 이름으로만 받는다."""

from __future__ import annotations

import os
import time

import httpx

from character_factory_poc.providers.base import (
    ChatRequest,
    ChatResponse,
    VisionRequest,
    VisionResult,
)


class OpenAICompatTextModel:
    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str = "",
        timeout: float = 180.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key_env = api_key_env
        self.timeout = timeout
        self.max_retries = max_retries

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "User-Agent": "character-factory-poc/0.1"}
        key = os.environ.get(self._api_key_env) if self._api_key_env else None
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def complete(self, request: ChatRequest) -> ChatResponse:
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        if request.response_json and not any("json" in m["content"] for m in messages):
            # OpenAI 계열은 json_object 형식을 쓸 때 메시지에 소문자 'json'이 있어야 한다.
            messages[-1]["content"] += "\n\n(응답 형식: json)"
        body: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.response_json:
            body["response_format"] = {"type": "json_object"}
        url = f"{self.base_url}/chat/completions"
        delay = 1.0
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.monotonic()
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    r = client.post(url, json=body, headers=self._headers())
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"status {r.status_code}", request=r.request, response=r
                    )
                r.raise_for_status()
                data = r.json()
                text = data["choices"][0]["message"]["content"] or ""
                usage = data.get("usage") or {}
                return ChatResponse(
                    text=text,
                    input_tokens=usage.get("prompt_tokens"),
                    output_tokens=usage.get("completion_tokens"),
                    elapsed_ms=int((time.monotonic() - t0) * 1000),
                    model=data.get("model", self.model),
                    provider=self.name,
                )
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                last_exc = e
                if attempt >= self.max_retries:
                    break
                time.sleep(delay)
                delay *= 2
        raise RuntimeError(f"공급자 호출 실패: {last_exc}") from last_exc


def _data_uri(path: str) -> str:
    import base64
    from pathlib import Path

    raw = Path(path).read_bytes()
    mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


class OpenAICompatVisionModel:
    """OpenAI 호환 chat/completions에 이미지(data URI)를 붙여 판정 JSON을 받는다(D-0036).

    중계(opencodex)가 이미지 입력을 넘기는지는 실제 호출 전에 확인해야 한다(Q-0020)."""

    name = "openai_compat_vision"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str = "",
        timeout: float = 180.0,
        max_retries: int = 3,
        client: httpx.Client | None = None,
        sleep=time.sleep,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key_env = api_key_env
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = client
        self._sleep = sleep

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "User-Agent": "character-factory-poc/0.1"}
        key = os.environ.get(self._api_key_env) if self._api_key_env else None
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def body(self, request: VisionRequest) -> dict:
        parts: list[dict] = [{"type": "text", "text": request.prompt + "\n\n(응답 형식: json)"}]
        for label, path in request.images:
            parts.append({"type": "text", "text": f"[{label}]"})
            parts.append({"type": "image_url", "image_url": {"url": _data_uri(path)}})
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": parts})
        return {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

    def judge(self, request: VisionRequest) -> VisionResult:
        body = self.body(request)
        url = f"{self.base_url}/chat/completions"
        delay = 1.0
        last_exc: Exception | None = None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            for attempt in range(self.max_retries + 1):
                t0 = time.monotonic()
                try:
                    r = client.post(url, json=body, headers=self._headers())
                    if r.status_code == 429 or r.status_code >= 500:
                        raise httpx.HTTPStatusError(
                            f"status {r.status_code}", request=r.request, response=r
                        )
                    r.raise_for_status()
                    data = r.json()
                    usage = data.get("usage") or {}
                    return VisionResult(
                        text=data["choices"][0]["message"]["content"] or "",
                        input_tokens=usage.get("prompt_tokens"),
                        output_tokens=usage.get("completion_tokens"),
                        elapsed_ms=int((time.monotonic() - t0) * 1000),
                        model=data.get("model", self.model),
                        provider=self.name,
                    )
                except (httpx.HTTPStatusError, httpx.TransportError) as e:
                    last_exc = e
                    if attempt >= self.max_retries:
                        break
                    self._sleep(delay)
                    delay *= 2
        finally:
            if self._client is None:
                client.close()
        raise RuntimeError(f"비전 판정 호출 실패: {last_exc}") from last_exc
