"""학습 공급자 (LLD §8.9). `make_training_provider(name, cfg)`로 고른다."""

from __future__ import annotations

import tomllib
from functools import wraps

from character_factory_poc.common.config import ProviderConfig
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.providers.tracked import ProviderLimits
from character_factory_poc.providers.training.fake import FakeTrainingProvider
from character_factory_poc.providers.training.gemma_qlora import GemmaQLoraProvider
from character_factory_poc.providers.training.hosts import RemoteHost, VastRemoteHost
from character_factory_poc.providers.training.port import (
    ALL_PROVIDERS,
    DatasetFile,
    TrainingProvider,
    TrainRequest,
)
from character_factory_poc.providers.training.vertex_gemini import VertexGeminiProvider


class _LimitedTraining:
    """학습 포트는 Context 대신 TrainRequest로 캐릭터별 작업 폴더를 전달한다."""

    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        method = getattr(self.inner, name)
        if name not in {"submit", "status", "collect", "abort", "release"}:
            return method

        @wraps(method)
        def call(*args, **kwargs):
            request = kwargs["request"] if "request" in kwargs else args[-1]
            # runs/characters/<cid>/s10-train/<rev>/<provider>
            folder = request.plan_dir.resolve()
            ledger = Ledger(folder / "ledger")
            settings = {}
            for train_dir in folder.parents:
                if train_dir.name != "s10-train" or train_dir.parent.parent.name != "characters":
                    continue
                char = train_dir.parent
                ledger = Ledger(char / "ledger")
                path = char.parent.parent.parent / "factory.toml"
                if path.is_file():
                    with path.open("rb") as config:
                        settings = tomllib.load(config).get("orchestrator", {})
                break
            limits = ProviderLimits(settings, "tuning", ledger)
            return limits.call("s10t", self.inner, lambda _: method(*args, **kwargs))

        return call


def make_training_provider(name: str, cfg: ProviderConfig) -> TrainingProvider:
    """어댑터 이름 또는 설정 키로 학습 공급자를 만든다(기존 factory.py는 쓰지 않는다)."""
    adapter = name if name in ALL_PROVIDERS else (cfg.adapter or name)
    if adapter not in ALL_PROVIDERS:
        raise ValueError(
            f"알 수 없는 학습 공급자: '{name}'(adapter={cfg.adapter}). "
            "gemma_qlora, vertex_gemini, fake 중 하나다"
        )
    if adapter == "fake":
        return _LimitedTraining(FakeTrainingProvider(cfg))
    if adapter == "gemma_qlora":
        return _LimitedTraining(GemmaQLoraProvider(cfg))
    return _LimitedTraining(VertexGeminiProvider(cfg))


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
