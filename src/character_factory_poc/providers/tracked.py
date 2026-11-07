"""호출마다 원장·예산을 거치는 래퍼."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from character_factory_poc.common.budget import Budget
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.providers.base import (
    ChatRequest,
    ChatResponse,
    ImageModel,
    ImageRequest,
    ImageResult,
    TextModel,
    VideoModel,
    VideoRequest,
    VideoResult,
    VisionRequest,
    VisionResult,
)


def _utc_now() -> datetime:
    """단가 조회 시각. 테스트가 시계를 고정할 때 바꾼다."""
    return datetime.now(UTC)


def _effective_billing(inner, billing: dict | None) -> dict | None:
    """과금 구분이 없고 가짜 공급자면 비용이 생기지 않는 호출로 표시한다(명세 §24.2)."""
    if billing is None and getattr(inner, "name", "") == "fake":
        return {"route": "fake", "family": None, "class": "none"}
    return billing


def _ledger_binding(binding: dict | None) -> dict | None:
    """원장에 남길 덱 해석 결과. 인증 환경변수 이름은 원장에 넣지 않는다(명세 §24.2)."""
    if not isinstance(binding, dict) or not isinstance(binding.get("provider"), dict):
        return binding
    provider = {k: v for k, v in binding["provider"].items() if k != "api_key_env"}
    return {**binding, "provider": provider}


def _usage_of(resp) -> dict:
    """응답의 usage-v1을 쓰고, 없으면 기존 토큰 필드로 만든다."""
    usage = getattr(resp, "usage", None)
    if usage:
        return dict(usage)
    return {
        "inputTokens": resp.input_tokens,
        "cachedInputTokens": None,
        "cacheWriteTokens": None,
        "outputTokens": resp.output_tokens,
        "reasoningTokens": None,
        "finishReason": getattr(resp, "finish_reason", None),
        "usageSource": "legacy_fields",
    }


def _price_call(model: str, usage: dict, billing: dict | None, overrides: dict | None):
    """요청 모델과 호출 시각의 단가로 비용을 계산한다. 미확인이면 (None, None)."""
    if (billing or {}).get("class") == "none":
        return None, None
    from character_factory_poc.common import pricing

    try:
        entry = pricing.lookup(model, _utc_now(), overrides or {})
    except ValueError:
        # 단가표 오류로 이미 끝난 호출의 기록을 잃지 않는다. 비용은 미확인으로 남긴다.
        return None, None
    if entry is None:
        return None, None
    est = pricing.estimate(usage, entry)
    ref = pricing.price_ref(entry)
    if ref is not None:
        ref = dict(ref)
        if est.get("upperBound"):
            ref["upperBound"] = True
        if est.get("reason"):
            ref["costReason"] = est["reason"]
    return est.get("usd"), ref


def _error_status(exc: BaseException) -> int | None:
    from character_factory_poc.common.errors import ProviderRequestError

    if isinstance(exc, ProviderRequestError):
        return exc.status
    return getattr(exc, "status", None) if type(exc).__name__ == "ProviderTransportError" else None


def _rejected_before_use(status: int | None) -> bool:
    """429를 뺀 4xx 거절은 생성 전에 멈춘 요청이므로 예약을 0 토큰으로 풀어 준다."""
    return status is not None and 400 <= status < 500 and status != 429


def _usage_fields(usage: dict, resp) -> dict:
    return dict(
        input_tokens=usage.get("inputTokens"),
        output_tokens=usage.get("outputTokens"),
        cached_input_tokens=usage.get("cachedInputTokens"),
        cache_write_tokens=usage.get("cacheWriteTokens"),
        reasoning_tokens=usage.get("reasoningTokens"),
        finish_reason=usage.get("finishReason") or getattr(resp, "finish_reason", None),
        usage_source=usage.get("usageSource"),
    )


class TrackedTextModel:
    def __init__(
        self,
        inner: TextModel,
        ledger: Ledger,
        budget: Budget,
        binding=None,
        billing: dict | None = None,
        price_overrides: dict | None = None,
        transport_retries: int = 0,
        sleep=None,
    ):
        self.binding = binding
        self.inner = inner
        self.ledger = ledger
        self.budget = budget
        self.billing = _effective_billing(inner, billing)
        self.price_overrides = dict(price_overrides or {})
        # D-0084: 전송 실패(ProviderTransportError)만 시도마다 예약·원장을 따로 두고 다시 보낸다.
        self.transport_retries = max(0, int(transport_retries))
        self._sleep = sleep

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    def complete(self, request: ChatRequest) -> ChatResponse:
        from dataclasses import replace

        from character_factory_poc.common.errors import ProviderTransportError

        attempt = 0
        while True:
            try:
                return self._complete_once(request)
            except ProviderTransportError:
                if attempt >= self.transport_retries:
                    raise
                attempt += 1
                # 끊긴 시도의 예약은 청구됐을 수 있어 그대로 두고, 새 ref로 새 예약을 잡는다.
                (self._sleep or time.sleep)(2.0 * attempt)
                request = replace(request, ref=f"{request.ref}~transport{attempt}")

    def _complete_once(self, request: ChatRequest) -> ChatResponse:
        from character_factory_poc.common.budget import RunBudget
        from character_factory_poc.common.canonical import sha256_text

        reservation = None
        if isinstance(self.budget, RunBudget):
            if self.budget.synthetic and self.inner.name != "fake":
                raise ValueError("synthetic budget cannot fund a real provider")
            if hasattr(self.inner, "max_retries"):
                self.inner.max_retries = 0
            reservation = sha256_text(
                str(self.ledger.calls_path)
                + request.ref
                + str(request.messages)
                + str(request.max_output_tokens)
            )
            upper = sum(len(m.content.encode("utf-8")) + 1024 for m in request.messages)
            self.budget.reserve(
                reservation, input_tokens=upper, output_tokens=request.max_output_tokens
            )
        else:
            self.budget.consume(1)
        try:
            resp = self.inner.complete(request)
        except Exception as exc:
            status = _error_status(exc)
            kind = getattr(exc, "kind", None)
            self.ledger.record_call(
                stage=request.stage,
                kind=request.kind,
                provider=self.inner.name,
                model=self.inner.model,
                input_tokens=None,
                output_tokens=None,
                ms=0,
                ok=False,
                ref=request.ref,
                text_binding=_ledger_binding(self.binding),
                billing=self.billing,
                error_status=status,
                usage_source=f"transport_failed:{kind}" if kind else None,
            )
            if reservation is not None and _rejected_before_use(status):
                # 같은 요청을 다시 보내는 것은 지금처럼 중복 예약으로 막는다(재추첨 금지).
                self.budget.settle(reservation, input_tokens=0, output_tokens=0)
            raise
        usage = _usage_of(resp)
        cost, price = _price_call(self.inner.model, usage, self.billing, self.price_overrides)
        # 끝난 호출은 예산 정산이 상한 초과로 멈추더라도 원장에 먼저 남긴다.
        self.ledger.record_call(
            stage=request.stage,
            kind=request.kind,
            provider=resp.provider,
            model=resp.model,
            ms=resp.elapsed_ms,
            ok=True,
            ref=request.ref,
            est_cost_usd=cost,
            text_binding=_ledger_binding(self.binding),
            price=price,
            billing=self.billing,
            **_usage_fields(usage, resp),
        )
        if reservation is not None:
            # usage-v1의 outputTokens는 생각 토큰까지 보정한 청구 출력이다(Q-0023).
            self.budget.settle(
                reservation,
                input_tokens=usage.get("inputTokens"),
                output_tokens=usage.get("outputTokens"),
            )
        return resp


class TrackedCodexAgent:
    """codex exec 실행마다 원장·예산을 거친다."""

    def __init__(self, inner, ledger: Ledger, budget: Budget, stage: str):
        self.inner = inner
        self.ledger = ledger
        self.budget = budget
        self.stage = stage

    @property
    def model(self) -> str:
        return self.inner.model

    def run(self, workspace, prompt: str, ref: str, allow_paths=None):
        from character_factory_poc.common.budget import RunBudget

        if isinstance(self.budget, RunBudget):
            if self.inner.name != "fake_codex":
                raise ValueError(
                    "bounded formation requires API execution; nested tool cost is unbounded"
                )
            self.budget.reserve(ref, input_tokens=10000, output_tokens=12000)
        else:
            self.budget.consume(1)
        try:
            run = self.inner.run(workspace, prompt, allow_paths)
        except Exception as e:
            self.ledger.record_call(
                stage=self.stage,
                kind="AGENT_TAINTED" if "TaintedOutput" in type(e).__name__ else "AGENT",
                provider=self.inner.name,
                model=self.inner.model,
                input_tokens=None,
                output_tokens=None,
                ms=0,
                ok=False,
                ref=ref,
            )
            raise
        self.ledger.record_call(
            stage=self.stage,
            kind="AGENT",
            provider=self.inner.name,
            model=self.inner.model,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            ms=run.elapsed_ms,
            ok=run.exit_code == 0,
            ref=ref,
        )
        return run


class TrackedImageModel:
    """이미지 생성 호출마다 원장(kind=IMAGE, images=1)·예산을 거친다."""

    def __init__(self, inner: ImageModel, ledger: Ledger, budget: Budget):
        self.inner = inner
        self.ledger = ledger
        self.budget = budget

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    def generate(self, request: ImageRequest) -> ImageResult:
        self.budget.consume(1)
        try:
            res = self.inner.generate(request)
        except Exception:
            self.ledger.record_call(
                stage=request.stage,
                kind="IMAGE",
                provider=self.inner.name,
                model=self.inner.model,
                input_tokens=None,
                output_tokens=None,
                ms=0,
                ok=False,
                ref=request.ref,
                images=0,
            )
            raise
        self.ledger.record_call(
            stage=request.stage,
            kind="IMAGE",
            provider=res.provider,
            model=res.model,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            ms=res.elapsed_ms,
            ok=True,
            ref=request.ref,
            est_cost_usd=res.est_cost_usd,
            images=1,
        )
        return res


class TrackedVisionModel:
    """비전 판정 호출마다 원장(kind=VISION)·예산을 거친다(D-0036)."""

    def __init__(
        self,
        inner,
        ledger: Ledger,
        budget: Budget,
        billing: dict | None = None,
        price_overrides: dict | None = None,
    ):
        self.inner = inner
        self.ledger = ledger
        self.budget = budget
        self.billing = _effective_billing(inner, billing)
        self.price_overrides = dict(price_overrides or {})

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    def judge(self, request: VisionRequest) -> VisionResult:
        self.budget.consume(1)
        try:
            res = self.inner.judge(request)
        except Exception as exc:
            self.ledger.record_call(
                stage=request.stage,
                kind="VISION",
                provider=self.inner.name,
                model=self.inner.model,
                input_tokens=None,
                output_tokens=None,
                ms=0,
                ok=False,
                ref=request.ref,
                billing=self.billing,
                error_status=_error_status(exc),
            )
            raise
        usage = _usage_of(res)
        cost, price = _price_call(self.inner.model, usage, self.billing, self.price_overrides)
        self.ledger.record_call(
            stage=request.stage,
            kind="VISION",
            provider=res.provider,
            model=res.model,
            ms=res.elapsed_ms,
            ok=True,
            ref=request.ref,
            est_cost_usd=cost,
            price=price,
            billing=self.billing,
            **_usage_fields(usage, res),
        )
        return res


class TrackedVideoModel:
    """제출마다 예산을 1회 쓰고, 수집 결과를 원장(kind=VIDEO, seconds, 비용 추정)에 남긴다."""

    def __init__(self, inner: VideoModel, ledger: Ledger, budget: Budget):
        self.inner = inner
        self.ledger = ledger
        self.budget = budget

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    @property
    def resumable(self) -> bool:
        return bool(getattr(self.inner, "resumable", False))

    def check_settings(self, duration: int, resolution: str) -> None:
        """공급자가 고를 수 없는 설정이면 생성 전에 거절한다(grok_web, D-0032)."""
        fn = getattr(self.inner, "check_settings", None)
        if fn is not None:
            fn(duration, resolution)

    def submit(self, request: VideoRequest) -> str:
        self.budget.consume(1)
        return self.inner.submit(request)

    def collect(self, job_id: str, request: VideoRequest) -> VideoResult:
        try:
            res = self.inner.collect(job_id, request)
        except Exception:
            self.ledger.record_call(
                stage=request.stage,
                kind="VIDEO",
                provider=self.inner.name,
                model=self.inner.model,
                input_tokens=None,
                output_tokens=None,
                ms=0,
                ok=False,
                ref=f"{request.ref}#{job_id}",
            )
            raise
        self.ledger.record_call(
            stage=request.stage,
            kind="VIDEO",
            provider=res.provider,
            model=res.model,
            input_tokens=None,
            output_tokens=None,
            ms=res.elapsed_ms,
            ok=True,
            ref=f"{request.ref}#{job_id}",
            est_cost_usd=res.est_cost_usd,
            seconds=res.seconds,
        )
        return res
