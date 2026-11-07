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
            base_url=cfg.base_url, model=cfg.model, api_key_env=cfg.api_key_env
        )
    raise ValueError(f"알 수 없는 비전 어댑터: '{cfg.adapter}'. openai_compat 또는 fake다")


def make_image_model(cfg: ProviderConfig) -> ImageModel:
    if cfg.adapter == "fake":
        return FakeImageModel(model=cfg.model or "fake-image")
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
        '[providers.image] adapter는 "codex_image"(ChatGPT 구독) 또는 "fake"다'
    )


def make_video_model(cfg: ProviderConfig) -> VideoModel:
    x = cfg.extra
    if cfg.adapter == "fake":
        return FakeVideoModel(model=cfg.model or "fake-video")
    if cfg.adapter == "xai_video":
        from character_factory_poc.providers.xai_video import XaiVideoModel

        return XaiVideoModel(
            model=cfg.model or "grok-imagine-video-1.5-lite",
            api_key_env=cfg.api_key_env or "XAI_API_KEY",
            base_url=cfg.base_url or "https://api.x.ai/v1",
            poll_interval_s=float(x.get("poll_interval_s", 5)),
            timeout_s=float(x.get("timeout_s", 600)),
            prices=x.get("price_per_second"),
        )
    if cfg.adapter == "grok_oauth":
        from character_factory_poc.providers.grok_oauth import GrokOAuthVideoModel

        return GrokOAuthVideoModel(
            model=cfg.model or "grok-imagine-video-1.5-lite",
            token_file=x.get("token_file") or None,
            token_env=str(x.get("token_env") or ""),
            base_url=cfg.base_url or "https://api.x.ai/v1",
            poll_interval_s=float(x.get("poll_interval_s", 5)),
            timeout_s=float(x.get("timeout_s", 600)),
            prices=x.get("price_per_second"),
        )
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
        f"알 수 없는 영상 어댑터: '{cfg.adapter}'. xai_video(공식 API), "
        "grok_oauth(OAuth 로그인 토큰), grok_web(웹, 기본 꺼짐), fake 중 하나다"
    )
