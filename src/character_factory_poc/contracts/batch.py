"""여러 캐릭터를 독립 실행하는 입력 계약."""

from typing import Literal, Self

from pydantic import Field, model_validator

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict


class BatchCharacter(Strict):
    character_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,40}$")
    # twin은 D-0144 이전 이름이라 motif와 같은 뜻으로 받는다.
    origin: Literal["original", "motif", "twin"] | None = None
    model_mode: Literal["train", "bind", "prompt"] | None = None
    source_pack: str | None = Field(default=None, min_length=1)
    until: str = "G6"
    max_parallel: int = Field(default=1, ge=1, strict=True)

    @model_validator(mode="after")
    def one_target(self) -> Self:
        if (self.character_id is None) == (self.slug is None):
            raise ValueError("character_id와 slug 중 하나만 지정한다")
        return self


@register("batch-spec-v1")
class BatchSpec(Strict):
    schemaVersion: Literal["batch-spec-v1"] = "batch-spec-v1"
    characters: list[BatchCharacter] = Field(min_length=1)
    max_parallel: int = Field(default=2, ge=1, strict=True)  # 동시에 돌릴 캐릭터 수
