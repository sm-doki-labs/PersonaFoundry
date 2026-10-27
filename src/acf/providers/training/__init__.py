"""학습 공급자 (LLD §8.9). `make_training_provider(name, cfg)`로 고른다."""

from __future__ import annotations

from acf.common.config import ProviderConfig
from acf.providers.training.fake import FakeTrainingProvider
from acf.providers.training.gemma_qlora import GemmaQLoraProvider
from acf.providers.training.hosts import RemoteHost, VastRemoteHost
from acf.providers.training.port import (
    ALL_PROVIDERS,
    DatasetFile,
    TrainingProvider,
    TrainRequest,
)
from acf.providers.training.vertex_gemini import VertexGeminiProvider


def make_training_provider(name: str, cfg: ProviderConfig) -> TrainingProvider:
    """어댑터 이름 또는 설정 키로 학습 공급자를 만든다(기존 factory.py는 쓰지 않는다)."""
    adapter = name if name in ALL_PROVIDERS else (cfg.adapter or name)
    if adapter not in ALL_PROVIDERS:
        raise ValueError(
            f"알 수 없는 학습 공급자: '{name}'(adapter={cfg.adapter}). "
            "gemma_qlora, vertex_gemini, fake 중 하나다"
        )
    if adapter == "fake":
        return FakeTrainingProvider(cfg)
    if adapter == "gemma_qlora":
        return GemmaQLoraProvider(cfg)
    return VertexGeminiProvider(cfg)


__all__ = [
    "ALL_PROVIDERS",
    "DatasetFile",
    "FakeTrainingProvider",
    "GemmaQLoraProvider",
    "RemoteHost",
    "TrainRequest",
    "TrainingProvider",
    "VastRemoteHost",
    "VertexGeminiProvider",
    "make_training_provider",
]
