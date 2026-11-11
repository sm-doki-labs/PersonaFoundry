"""Configuration-only checks before web launches; never construct or call models."""

from character_factory_poc.common.config import FactoryConfig
from character_factory_poc.web.errors import WebError


def validate_source_launch(config: FactoryConfig) -> None:
    # Native SOURCE S3 uses text_model/judge_model directly, even when the text
    # deck is enabled. Missing providers default to fake in FactoryConfig.
    if config.provider("text").adapter != "fake" and config.provider("judge").adapter == "fake":
        raise WebError(
            503,
            "생성 모델은 연결돼 있지만 검토 모델이 준비되지 않았어요. "
            "운영 설정에서 검토 모델을 연결한 뒤 다시 시작해 주세요. "
            "아직 제작을 시작하지 않았어요.",
        )
