"""외부 학습 모델의 고정 참조와 사용 근거(D-0118)."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import StringConstraints, model_validator

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Provenance(Strict):
    trainedBy: Text
    trainedAt: Text
    dataNote: Text
    usageBasis: Text


@register("model-binding-import-v1")
class ModelBindingImport(Strict):
    schemaVersion: Literal["model-binding-import-v1"] = "model-binding-import-v1"
    provider: Literal["HF_ADAPTER", "VERTEX_TUNED", "ENDPOINT"]
    ref: Text
    revision: Text
    baseModel: Text
    baseModelRevision: Text
    servingRoute: Text
    provenance: Provenance

    @model_validator(mode="after")
    def pinned_hf_adapter(self) -> ModelBindingImport:
        if self.provider == "HF_ADAPTER":
            if not re.fullmatch(r"[0-9a-fA-F]{40}", self.revision):
                raise ValueError("Hugging Face 어댑터의 버전은 40자리 커밋 해시여야 해요.")
            if not re.fullmatch(r"[\w.-]+/[\w.-]+", self.ref, re.ASCII):
                raise ValueError("Hugging Face 어댑터의 모델 이름은 '소유자/저장소' 꼴이어야 해요.")
        return self
