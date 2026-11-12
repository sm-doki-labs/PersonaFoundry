"""설정으로 어댑터를 고른다."""

from __future__ import annotations

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.providers.base import ImageModel, TextModel, VideoModel
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.fake_image import FakeImageModel
from character_factory_poc.providers.fake_video import FakeVideoModel
from character_factory_poc.providers.openai_compat import OpenAICompatTextModel


def make_text_model(cfg: ProviderConfig) -> TextModel:
    if cfg.adapter == "fake":
        return FakeTextModel(model=cfg.model or "fake-text")
    if cfg.adapter == "openai_compat":
        if not cfg.base_url or not cfg.model:
            raise ValueError("openai_compat 어댑터에는 base_url과 model이 필요하다")
        return OpenAICompatTextModel(
            base_url=cfg.base_url,
            model=cfg.model,
            api_key_env=cfg.api_key_env,
            timeout=float(cfg.extra.get("timeout_s", 180)),
            max_retries=int(cfg.extra.get("max_retries", 3)),
            reasoning_effort=cfg.extra.get("reasoning_effort"),
            stream=bool(cfg.extra.get("stream", False)),
        )
    if cfg.adapter == "vertex_openai":
        # D-0149: Vertex AI OpenAI 호환 주소 + gcloud 접근 토큰 자동 갱신.
        from character_factory_poc.providers.vertex_auth import (
            DEFAULT_COMMAND,
            DEFAULT_TTL_S,
            GcloudToken,
            vertex_openai_base_url,
        )

        x = cfg.extra
        if not cfg.model:
            raise ValueError(
                'vertex_openai 어댑터에는 model이 필요하다(예: "google/gemini-3.8-flash")'
            )
        base = cfg.base_url or vertex_openai_base_url(
            str(x.get("project", "")), str(x.get("location", "global"))
        )
        return OpenAICompatTextModel(
            base_url=base,
            model=cfg.model,
            timeout=float(x.get("timeout_s", 180)),
            max_retries=int(x.get("max_retries", 3)),
            reasoning_effort=x.get("reasoning_effort"),
            token_provider=GcloudToken(
                command=tuple(x.get("token_command", DEFAULT_COMMAND)),
                ttl_s=float(x.get("token_ttl_s", DEFAULT_TTL_S)),
            ),
        )
    if cfg.adapter == "anthropic":
        from character_factory_poc.providers.anthropic_messages import AnthropicTextModel

        if not cfg.model:
            raise ValueError('anthropic 어댑터에는 model이 필요하다(예: "claude-opus-5-5")')
        x = cfg.extra
        return AnthropicTextModel(
            model=cfg.model,
            api_key_env=cfg.api_key_env or "ANTHROPIC_API_KEY",
            base_url=cfg.base_url or "https://api.anthropic.com/v1",
            timeout=float(x.get("timeout_s", 900)),
            max_retries=int(x.get("max_retries", 2)),
            effort=x.get("effort"),
            max_output_tokens=int(x.get("max_output_tokens", 64_000)),
        )
    raise ValueError(f"알 수 없는 텍스트 어댑터: {cfg.adapter}")


def make_vision_model(cfg: ProviderConfig):
    """[providers.vision] (D-0036). fake 또는 openai_compat."""
    if cfg.adapter == "fake":
        from character_factory_poc.providers.fake_vision import FakeVisionModel

        return FakeVisionModel(model=cfg.model or "fake-vision")
    if cfg.adapter == "openai_compat":
        from character_factory_poc.providers.openai_compat import OpenAICompatVisionModel

        if not cfg.base_url or not cfg.model:
            raise ValueError("openai_compat 비전 어댑터에는 base_url과 model이 필요하다")
        return OpenAICompatVisionModel(
            base_url=cfg.base_url,
            model=cfg.model,
            api_key_env=cfg.api_key_env,
            timeout=float(cfg.extra.get("timeout_s", 180)),
            max_retries=int(cfg.extra.get("max_retries", 3)),
        )
    raise ValueError(f"알 수 없는 비전 어댑터: '{cfg.adapter}'. openai_compat 또는 fake다")


def make_image_model(cfg: ProviderConfig) -> ImageModel:
    if cfg.adapter == "fake":
        return FakeImageModel(model=cfg.model or "fake-image")
    if cfg.adapter == "openai_images":
        from character_factory_poc.providers.openai_images import OpenAIImageModel

        x = cfg.extra
        return OpenAIImageModel(
            model=cfg.model or "gpt-image-2.6-sunburst",
            api_key_env=cfg.api_key_env or "OPENAI_API_KEY",
            base_url=cfg.base_url or "https://api.openai.com/v1",
            timeout=float(x.get("timeout_s", 360)),
            max_retries=int(x.get("max_retries", 0)),
            quality=str(x.get("quality", "high")),
            complexity=str(x.get("complexity", "medium")),
        )
    if cfg.adapter == "xai_images":
        from character_factory_poc.providers.xai_images import XAIImageModel

        x = cfg.extra
        return XAIImageModel(
            model=cfg.model or "grok-imagine-image-2.0",
            api_key_env=cfg.api_key_env or "XAI_API_KEY",
            base_url=cfg.base_url or "https://api.x.ai/v1",
            timeout=float(x.get("timeout_s", 180)),
            max_retries=int(x.get("max_retries", 0)),
        )
    if cfg.adapter == "codex_image":
        from character_factory_poc.providers.codex_image import DEFAULT_DISABLE, CodexImageModel

        x = cfg.extra
        return CodexImageModel(
            model=cfg.model or "gpt-6.1-sol",
            reasoning_effort=str(x.get("reasoning_effort", "low")),
            timeout_s=int(x.get("timeout_s", 600)),
            disable_features=tuple(x.get("disable_features", DEFAULT_DISABLE)),
            extra_config=tuple(x.get("extra_config", ())),
        )
    raise ValueError(
        f"알 수 없는 이미지 어댑터: '{cfg.adapter}'. "
        '[providers.image] adapter는 "openai_images"(공식 API), '
        '"xai_images"(Grok 이미지), "codex_image"(ChatGPT 구독), "fake" 중 하나다'
    )


def make_video_model(cfg: ProviderConfig) -> VideoModel:
    x = cfg.extra
    if cfg.adapter == "fake":
        return FakeVideoModel(model=cfg.model or "fake-video")
    if cfg.adapter == "xai_video":
        from character_factory_poc.providers.xai_video import XaiVideoModel

        return XaiVideoModel(
            model=cfg.model or "grok-imagine-video-1.5",
            api_key_env=cfg.api_key_env or "XAI_API_KEY",
            base_url=cfg.base_url or "https://api.x.ai/v1",
            poll_interval_s=float(x.get("poll_interval_s", 5)),
            timeout_s=float(x.get("timeout_s", 600)),
            prices=x.get("price_per_second"),
        )
    if cfg.adapter == "grok_oauth":
        from character_factory_poc.providers.grok_oauth import GrokOAuthVideoModel

        return GrokOAuthVideoModel(
            model=cfg.model or "grok-imagine-video-1.5",
            token_file=x.get("token_file") or None,
            token_env=str(x.get("token_env") or ""),
            login_file=x.get("login_file") or None,
            client_id=str(x.get("oauth_client_id") or ""),
            base_url=cfg.base_url or "https://api.x.ai/v1",
            poll_interval_s=float(x.get("poll_interval_s", 5)),
            timeout_s=float(x.get("timeout_s", 600)),
            prices=x.get("price_per_second"),
        )
    if cfg.adapter == "grok":
        # 사용자 2026-11-12: 시연·시험의 1순위 기본은 OAuth 로그인, 안 되면 API 키.
        from character_factory_poc.providers.grok_chain import GrokVideoChain

        order = list(x.get("order") or ["grok_oauth", "xai_video"])
        bad = [a for a in order if a not in {"grok_oauth", "xai_video"}]
        if bad or not order:
            raise ValueError(
                f"[providers.video] order는 grok_oauth·xai_video 가운데서 고른다: {bad or order}"
            )
        members = [
            make_video_model(
                ProviderConfig(
                    adapter=adapter,
                    model=cfg.model,
                    base_url=cfg.base_url,
                    api_key_env=cfg.api_key_env if adapter == "xai_video" else "",
                    extra=x,
                )
            )
            for adapter in order
        ]
        return GrokVideoChain(members)
    if cfg.adapter == "grok_web":
        # D-0029: xAI 이용 정책은 봇·스크립트 접근을 금지한다. 위험을 알고 켠다는 표시가 있어야 만든다.
        if x.get("accept_terms_risk") is not True:
            raise ValueError(
                "grok_web은 xAI 이용 정책(자동화 접근 금지) 위반 위험이 있어 기본으로 꺼져 있다. "
                "위험을 알고 쓰려면 [providers.video]에 accept_terms_risk = true를 넣는다(D-0029)"
            )
        from character_factory_poc.providers.grok_web import GrokWebVideoModel, selectors_from

        return GrokWebVideoModel(
            model=cfg.model or "grok-imagine-web",
            cdp_url=str(x.get("cdp_url", "http://127.0.0.1:9222")),
            imagine_url=str(x.get("imagine_url", "https://grok.com/imagine")),
            selectors=selectors_from(x),
            timeout_s=float(x.get("timeout_s", 600)),
        )
    raise ValueError(
        f"알 수 없는 영상 어댑터: '{cfg.adapter}'. grok(로그인 먼저, 안 되면 API 키), xai_video(공식 API), "
        "grok_oauth(OAuth 로그인 토큰), grok_web(웹, 기본 꺼짐), fake 중 하나다"
    )
