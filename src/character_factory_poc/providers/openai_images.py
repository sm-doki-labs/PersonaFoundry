"""공식 OpenAI Images API를 공장의 ImageModel 포트에 연결한다."""

import math
from pathlib import Path

from character_factory_poc.common.errors import ImageGenerationError
from character_factory_poc.providers.base import ImageRequest, ImageResult
from character_factory_poc.providers.openai_images_client import (
    DEFAULT_BASE,
    ImageApiError,
    OpenAIImagesClient,
)


def image_cost_estimate(cfg) -> float | None:
    """명시한 계획용 추정액. 실제 청구액이나 이미지 품질 판정이 아니다."""
    if cfg.adapter != "openai_images":
        return 0.0
    cost = cfg.extra.get("estimated_cost_usd")
    if cost is None:
        return None
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        raise ValueError("이미지 estimated_cost_usd는 양의 유한한 금액이어야 한다")
    if not math.isfinite(cost) or cost <= 0:
        raise ValueError("이미지 estimated_cost_usd는 양의 유한한 금액이어야 한다")
    return float(cost)


class OpenAIImageModel:
    name = "openai_images"

    def __init__(
        self,
        model: str = "gpt-image-2.6-sunburst",
        *,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str = DEFAULT_BASE,
        timeout: float = 360,
        max_retries: int = 0,
        quality: str = "high",
        complexity: str = "medium",
    ):
        if base_url.rstrip("/") != DEFAULT_BASE:
            raise ValueError("openai_images는 공식 OpenAI API 주소만 사용한다")
        if quality not in {"auto", "low", "medium", "high"}:
            raise ValueError("이미지 quality는 auto, low, medium, high 중 하나다")
        if complexity not in {"low", "medium", "high"}:
            raise ValueError("이미지 complexity는 low, medium, high 중 하나다")
        self.model = model
        self.max_retries = max_retries
        self.quality = quality
        self.complexity = complexity
        self.client = OpenAIImagesClient(
            model,
            api_key_env=api_key_env,
            base_url=base_url,
            timeout=timeout,
            retries=max_retries,
        )

    def generate(self, request: ImageRequest) -> ImageResult:
        refs = [Path(p) for p in request.reference_images]
        if any(not p.is_file() for p in refs):
            raise ImageGenerationError("참조 이미지 파일이 없다")
        prompt = request.prompt
        if request.negative_prompt:
            prompt += "\n\nAvoid: " + request.negative_prompt
        settings = dict(size=request.size, quality=self.quality, complexity=self.complexity)
        try:
            result = (
                self.client.edit(prompt, refs, **settings)
                if refs
                else self.client.generate(prompt, **settings)
            )
        except ImageApiError as exc:
            raise ImageGenerationError(str(exc)) from exc
        if not result.data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ImageGenerationError("OpenAI 이미지 응답이 PNG가 아니다")
        import cv2
        import numpy as np

        try:
            decoded = cv2.imdecode(np.frombuffer(result.data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        except cv2.error as exc:
            raise ImageGenerationError("OpenAI PNG 이미지가 손상됐다") from exc
        if decoded is None or not decoded.size:
            raise ImageGenerationError("OpenAI PNG 이미지가 손상됐다")
        return ImageResult(
            data=result.data,
            mime="image/png",
            model=self.model,
            provider=self.name,
            elapsed_ms=result.elapsed_ms,
            input_tokens=result.usage.get("input_tokens"),
            output_tokens=result.usage.get("output_tokens"),
            # 텍스트/이미지/캐시 단가를 구분하지 못한 비용은 0이 아닌 미확인이다.
            est_cost_usd=None,
        )
