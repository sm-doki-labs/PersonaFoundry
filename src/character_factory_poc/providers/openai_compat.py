"""OpenAI 호환 chat/completions 어댑터 (LLD §9, 명세 §24.3). 키는 환경변수 이름으로만 받는다.

요청 형식은 호출 주소의 호스트로 고른다. OpenAI 공식 주소는 `max_completion_tokens`를 쓰고
추론 강도가 `none`일 때만 `temperature`를 보낸다(지정하지 않으면 모델 기본 추론이 켜진다).
Gemini OpenAI 호환 주소와 그 밖의 주소(중계·테스트 서버)는 지금까지의 본문을 그대로 보낸다.
응답 사용량은 usage-v1로 정리한다.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from character_factory_poc.common.errors import ProviderRequestError, ProviderTransportError
from character_factory_poc.providers.base import (
    ChatRequest,
    ChatResponse,
    VisionRequest,
    VisionResult,
)
from character_factory_poc.providers.tracked import native_retry_sleep

OPENAI_HOST = "api.openai.com"
GEMINI_HOST = "generativelanguage.googleapis.com"
# 추론 강도 "none"을 받지 않는 OpenAI 모델. 스냅샷 ID(<모델>-<날짜>)도 같은 모델로 본다.
NO_REASONING_UNSUPPORTED = ("gpt-6.1-sol",)


def request_dialect(base_url: str) -> str:
    """호출 주소의 호스트로 요청 형식을 고른다: "openai" | "gemini" | "generic"."""
    host = (urlsplit(base_url).hostname or "").lower()
    if host == OPENAI_HOST:
        return "openai"
    if host == GEMINI_HOST:
        return "gemini"
    return "generic"


def _count(value) -> int | None:
    """토큰 수로 읽을 수 있는 값만 받는다. bool·문자열·음수는 모르는 값(None)이다."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _detail(usage: dict, group: str, name: str) -> int | None:
    details = usage.get(group)
    return _count(details.get(name)) if isinstance(details, dict) else None


def _rejects_no_reasoning(model: str) -> bool:
    base = model.removeprefix("openai/")
    return any(base == m or base.startswith(f"{m}-") for m in NO_REASONING_UNSUPPORTED)


def normalize_usage(data: dict) -> dict:
    """chat/completions 응답의 사용량을 usage-v1로 정리한다(명세 §24.3).

    `inputTokens`는 캐시 읽기(`cachedInputTokens`)·캐시 쓰기(`cacheWriteTokens`)를 포함한 전체
    입력이다. `outputTokens`는 청구되는 출력이다. Gemini 호환 응답은 completion_tokens에서 생각
    토큰을 뺀다는 보고가 있어(Q-0023), total_tokens − prompt_tokens가 더 크면 그 값을 쓰고
    usageSource에 `total_minus_prompt`를 남긴다. 캐시 읽기·쓰기·추론 토큰은 세부 항목에 있을 때만
    채운다. 모르는 값은 0이 아니라 None이다.
    """
    finish = None
    choices = data.get("choices") if isinstance(data, dict) else None
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        reason = choices[0].get("finish_reason")
        finish = reason if isinstance(reason, str) else None
    usage = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(usage, dict):
        return {
            "inputTokens": None,
            "cachedInputTokens": None,
            "cacheWriteTokens": None,
            "outputTokens": None,
            "reasoningTokens": None,
            "finishReason": finish,
            "usageSource": "missing",
        }
    prompt = _count(usage.get("prompt_tokens"))
    completion = _count(usage.get("completion_tokens"))
    total = _count(usage.get("total_tokens"))
    output, source = completion, "completion_tokens"
    if total is not None and prompt is not None and total >= prompt:
        if completion is None or total - prompt > completion:
            output, source = total - prompt, "total_minus_prompt"
    return {
        "inputTokens": prompt,
        "cachedInputTokens": _detail(usage, "prompt_tokens_details", "cached_tokens"),
        "cacheWriteTokens": _detail(usage, "prompt_tokens_details", "cache_write_tokens"),
        "outputTokens": output,
        "reasoningTokens": _detail(usage, "completion_tokens_details", "reasoning_tokens"),
        "finishReason": finish,
        "usageSource": source,
    }


def _provider_message(response: httpx.Response, secret: str | None) -> str:
    """거절 응답의 공급자 문구. error.message가 없으면 본문 앞부분을 쓰고 키 값을 가린다."""
    message = ""
    try:
        data = response.json()
    except ValueError:
        data = None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        data = data[0]  # Gemini 오류 본문은 배열로 올 때가 있다.
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            message = error["message"]
        elif isinstance(error, str):
            message = error
    if not message:
        message = response.text[:2000]
    if secret:
        message = message.replace(secret, "***")
    return message[:500]


def _send(
    post: Callable[..., httpx.Response],
    url: str,
    body: dict,
    headers: dict[str, str],
    *,
    max_retries: int,
    sleep: Callable[[float], object],
    secret: str | None,
    failure: str,
) -> tuple[dict, int]:
    """429·5xx·전송 오류만 지수 대기로 재시도한다.

    그 밖의 비정상 응답은 바로 ProviderRequestError다. 재시도를 다 쓰면 지금처럼
    `RuntimeError("<failure>: ...")`를 낸다. (응답 JSON, 걸린 ms)를 돌려준다.
    """
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        t0 = time.monotonic()
        try:
            r = post(url, json=body, headers=headers)
        except httpx.TransportError as e:
            last_exc = e
        else:
            if r.status_code == 429 or r.status_code >= 500:
                last_exc = httpx.HTTPStatusError(
                    f"status {r.status_code}", request=httpx.Request("POST", url), response=r
                )
            elif not r.is_success:
                raise ProviderRequestError(r.status_code, _provider_message(r, secret))
            else:
                data = r.json()
                return data, int((time.monotonic() - t0) * 1000)
        if attempt >= max_retries:
            break
        native_retry_sleep(
            sleep, delay, getattr(getattr(last_exc, "response", None), "status_code", None)
        )
        delay *= 2
    raise _transport_error(last_exc, failure) from last_exc


def _transport_error(exc: Exception | None, failure: str) -> ProviderTransportError:
    """재시도를 다 쓴 전송 실패를 종류별로 나눈다. RuntimeError도 상속한다."""
    status = None
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        kind = "rate_limit" if status == 429 else "server_error"
    elif isinstance(exc, httpx.TimeoutException):
        kind = "timeout"
    elif isinstance(exc, ValueError):
        kind = "malformed_stream"
    else:
        kind = "disconnect"
    return ProviderTransportError(kind, f"{failure}: {exc}", status)


THOUGHT_BLOCK = re.compile(r"<thought>.*?</thought>", re.S)


def strip_thoughts(text: str) -> str:
    """Gemini 생각 요약(include_thoughts)은 본문에 <thought> 태그로 섞인다. 저장하지 않는다."""
    if "<thought>" not in text:
        return text
    return THOUGHT_BLOCK.sub("", text).strip()


def collect_stream(lines) -> dict:
    """SSE 'data:' 조각을 비스트리밍 응답과 같은 모양으로 합친다.

    사용량은 마지막으로 받은 usage를 쓴다(Gemini는 조각마다, OpenAI는 마지막 조각에 준다).
    끝 표시([DONE]·finish_reason·usage)가 하나도 없이 끝나면 중간에 끊긴 것으로 본다.
    """
    parts: list[str] = []
    finish = model = usage = None
    done = False
    for raw in lines:
        line = raw.strip() if isinstance(raw, str) else raw.decode("utf-8").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            done = True
            break
        event = json.loads(payload)  # 깨진 조각은 ValueError(malformed_stream)
        model = event.get("model") or model
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                parts.append(delta["content"])
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]
    if not done and finish is None and usage is None:
        raise httpx.RemoteProtocolError("stream ended before completion")
    data: dict = {
        "choices": [
            {"message": {"content": strip_thoughts("".join(parts))}, "finish_reason": finish}
        ]
    }
    if model:
        data["model"] = model
    if usage is not None:
        data["usage"] = usage
    return data


def _send_stream(
    client_factory: Callable[[], httpx.Client],
    url: str,
    body: dict,
    headers: dict[str, str],
    *,
    max_retries: int,
    sleep: Callable[[float], object],
    secret: str | None,
    failure: str,
) -> tuple[dict, int]:
    """스트리밍 요청. 재시도·거절 규칙은 _send와 같다(D-0084)."""
    delay = 1.0
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        t0 = time.monotonic()
        try:
            with (
                client_factory() as client,
                client.stream("POST", url, json=body, headers=headers) as r,
            ):
                if r.status_code == 429 or r.status_code >= 500:
                    r.read()
                    last_exc = httpx.HTTPStatusError(
                        f"status {r.status_code}", request=httpx.Request("POST", url), response=r
                    )
                elif not r.is_success:
                    r.read()
                    raise ProviderRequestError(r.status_code, _provider_message(r, secret))
                else:
                    data = collect_stream(r.iter_lines())
                    return data, int((time.monotonic() - t0) * 1000)
        except (httpx.TransportError, ValueError) as e:
            last_exc = e
        if attempt >= max_retries:
            break
        native_retry_sleep(
            sleep, delay, getattr(getattr(last_exc, "response", None), "status_code", None)
        )
        delay *= 2
    raise _transport_error(last_exc, failure) from last_exc


def _secret(api_key_env: str) -> str | None:
    return (os.environ.get(api_key_env) or None) if api_key_env else None


class OpenAICompatTextModel:
    name = "openai_compat"

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key_env: str = "",
        timeout: float = 180.0,
        max_retries: int = 3,
        reasoning_effort: str | None = None,
        stream: bool = False,
        token_provider=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._api_key_env = api_key_env
        self.timeout = timeout
        self.max_retries = max_retries
        self.reasoning_effort = reasoning_effort
        self.stream = stream
        # D-0149: Vertex처럼 만료되는 접근 토큰을 쓰는 경로. get()·refresh()가 있는 객체다.
        self.token_provider = token_provider

    def streaming(self) -> bool:
        """스트리밍은 공식 API 형식에서만 켠다. 중계·테스트 서버 본문은 그대로 둔다(D-0084)."""
        return self.stream and request_dialect(self.base_url) in {"openai", "gemini"}

    def _secret(self) -> str | None:
        if self.token_provider is not None:
            return self.token_provider.get()
        return _secret(self._api_key_env)

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "User-Agent": "character-factory-poc/0.1"}
        key = self._secret()
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def body(self, request: ChatRequest) -> dict:
        """요청 형식(request_dialect)에 맞춘 chat/completions 본문.

        OpenAI 형식에서 추론 강도 "none"을 받지 않는 모델이면 호출 전에 ValueError를 낸다.
        """
        dialect = request_dialect(self.base_url)
        if (
            dialect == "openai"
            and self.reasoning_effort == "none"
            and _rejects_no_reasoning(self.model)
        ):
            raise ValueError(f"{self.model}은 추론 강도 none을 지원하지 않는다")
        messages = [{"role": m.role, "content": m.content} for m in request.messages]
        if request.response_json and not any("json" in m["content"] for m in messages):
            # OpenAI 계열은 json_object 형식을 쓸 때 메시지에 소문자 'json'이 있어야 한다.
            messages[-1]["content"] += "\n\n(응답 형식: json)"
        body: dict = {"model": self.model, "messages": messages}
        if dialect == "openai":
            body["max_completion_tokens"] = request.max_output_tokens
            # 추론이 켜지면 OpenAI는 temperature를 거절한다(FR-66). 추론 강도를 지정하지 않으면
            # 모델 기본 추론(medium)이 켜지므로 "none"일 때만 보낸다.
            if self.reasoning_effort == "none":
                body["temperature"] = request.temperature
        else:
            # gemini는 Q-0025 확인 전까지, generic(중계·테스트 서버)은 지금 본문을 그대로 쓴다.
            body["max_tokens"] = request.max_output_tokens
            body["temperature"] = request.temperature
        if self.reasoning_effort is not None:
            body["reasoning_effort"] = self.reasoning_effort
        if request.response_json:
            body["response_format"] = {"type": "json_object"}
        if self.streaming():
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
            if dialect == "gemini" and self.reasoning_effort not in (None, "none"):
                # 생각 요약을 받아야 생각하는 동안에도 조각이 와서 연결이 살아 있다. Gemini는
                # reasoning_effort와 thinking_config를 함께 받지 않으므로 같은 강도로 옮긴다.
                body.pop("reasoning_effort")
                body["extra_body"] = {
                    "google": {
                        "thinking_config": {
                            "thinking_level": self.reasoning_effort,
                            "include_thoughts": True,
                        }
                    }
                }
        return body

    def complete(self, request: ChatRequest) -> ChatResponse:
        try:
            return self._complete(request)
        except ProviderRequestError as exc:
            # 만료된 토큰이면 한 번만 새로 받아 다시 보낸다.
            if exc.status != 401 or self.token_provider is None:
                raise
            self.token_provider.refresh()
            return self._complete(request)

    def _complete(self, request: ChatRequest) -> ChatResponse:
        def post(url: str, **kw) -> httpx.Response:
            with httpx.Client(timeout=self.timeout) as client:
                return client.post(url, **kw)

        url = f"{self.base_url}/chat/completions"
        common = dict(
            max_retries=self.max_retries,
            sleep=time.sleep,
            secret=self._secret(),
            failure="공급자 호출 실패",
        )
        if self.streaming():
            data, elapsed_ms = _send_stream(
                lambda: httpx.Client(timeout=httpx.Timeout(self.timeout, connect=30.0)),
                url,
                self.body(request),
                self._headers(),
                **common,
            )
        else:
            data, elapsed_ms = _send(post, url, self.body(request), self._headers(), **common)
        usage = normalize_usage(data)
        return ChatResponse(
            text=data["choices"][0]["message"]["content"] or "",
            input_tokens=usage["inputTokens"],
            output_tokens=usage["outputTokens"],
            elapsed_ms=elapsed_ms,
            model=data.get("model", self.model),
            provider=self.name,
            finish_reason=data["choices"][0].get("finish_reason"),
            raw=data,
            usage=usage,
        )


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
        key = _secret(self._api_key_env)
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
        # 비전 요청은 추론 강도를 보내지 않는다. OpenAI 형식에서는 모델 기본 추론이 켜지므로
        # temperature를 빼고, 그 밖의 형식은 지금처럼 temperature 0을 보낸다.
        if request_dialect(self.base_url) == "openai":
            return {
                "model": self.model,
                "messages": messages,
                "max_completion_tokens": request.max_output_tokens,
                "response_format": {"type": "json_object"},
            }
        return {
            "model": self.model,
            "messages": messages,
            "max_tokens": request.max_output_tokens,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

    def judge(self, request: VisionRequest) -> VisionResult:
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            data, elapsed_ms = _send(
                client.post,
                f"{self.base_url}/chat/completions",
                self.body(request),
                self._headers(),
                max_retries=self.max_retries,
                sleep=self._sleep,
                secret=_secret(self._api_key_env),
                failure="비전 판정 호출 실패",
            )
        finally:
            if self._client is None:
                client.close()
        usage = normalize_usage(data)
        return VisionResult(
            text=data["choices"][0]["message"]["content"] or "",
            input_tokens=usage["inputTokens"],
            output_tokens=usage["outputTokens"],
            elapsed_ms=elapsed_ms,
            model=data.get("model", self.model),
            provider=self.name,
            usage=usage,
        )
