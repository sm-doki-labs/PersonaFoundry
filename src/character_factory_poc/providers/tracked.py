"""호출마다 원장·예산을 거치는 래퍼."""

from __future__ import annotations

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


class TrackedTextModel:
    def __init__(self, inner: TextModel, ledger: Ledger, budget: Budget):
        self.inner = inner
        self.ledger = ledger
        self.budget = budget

    @property
    def name(self) -> str:
        return self.inner.name

    @property
    def model(self) -> str:
        return self.inner.model

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.budget.consume(1)
        ok = True
        try:
            resp = self.inner.complete(request)
        except Exception:
            ok = False
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
            )
            raise
        if ok:
            self.ledger.record_call(
                stage=request.stage,
                kind=request.kind,
                provider=resp.provider,
                model=resp.model,
                input_tokens=resp.input_tokens,
                output_tokens=resp.output_tokens,
                ms=resp.elapsed_ms,
                ok=True,
                ref=request.ref,
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

    def __init__(self, inner, ledger: Ledger, budget: Budget):
        self.inner = inner
        self.ledger = ledger
        self.budget = budget

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
        except Exception:
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
            )
            raise
        self.ledger.record_call(
            stage=request.stage,
            kind="VISION",
            provider=res.provider,
            model=res.model,
            input_tokens=res.input_tokens,
            output_tokens=res.output_tokens,
            ms=res.elapsed_ms,
            ok=True,
            ref=request.ref,
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
