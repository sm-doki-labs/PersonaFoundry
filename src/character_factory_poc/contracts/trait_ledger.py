"""trait-ledger-v1: 특질 장부(D-0091).

기획과 성격 시트에 흩어진 특질을 한 번씩만 모은다. 대화 프롬프트는 이 장부에서 조립 코드가 만든다.
평소 모습(대부분의 턴)과 조건부 특질(계기가 있을 때만)을 나누고, 칸 길이로 분량을 묶는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict

TraitKind = Literal["insult_reaction", "flaw", "misreading", "choice", "warmth"]


class LedgerTrait(Strict):
    id: str = Field(pattern=r"^t\d+$")
    kind: TraitKind
    trigger: str = Field(min_length=4, max_length=90, description="켜는 구체적 계기")
    nearMiss: str = Field(min_length=4, max_length=90, description="비슷하지만 켜지지 않는 상황")
    behavior: str = Field(min_length=4, max_length=150, description="관찰 가능한 행동 한 문장")
    rarity: Literal["rare", "sometimes"]
    #: D-0148: 모티브만 쓴다. 이 특질이 나온 원문 경향 칸(상황/반응). 대화 프롬프트에는 넣지 않는다.
    basis: str | None = Field(
        default=None, pattern=r"^(INFERRED|[A-Z_]+/[A-Z_]+)$", exclude_if=lambda v: v is None
    )

    sourceRef: str | None = Field(default=None, min_length=1, exclude_if=lambda v: v is None)
    demoSituation: Literal["TEASE", "WORRY", "CRITICISM", "UNKNOWN", "PRIVATE"] | None = Field(
        default=None, exclude_if=lambda v: v is None
    )


@register("trait-ledger-v1")
class TraitLedger(Strict):
    schemaVersion: Literal["trait-ledger-v1"] = "trait-ledger-v1"
    characterId: str
    planRev: str
    disposition: list[str] = Field(min_length=2, max_length=4)
    coreTension: str = Field(min_length=4, max_length=220)
    reading: str = Field(min_length=4, max_length=180)
    defaultResponse: str = Field(min_length=4, max_length=150)
    traits: list[LedgerTrait] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def _shape(self):
        if any(len(d) > 140 for d in self.disposition):
            raise ValueError("disposition 항목은 140자 이내다")
        kinds = [t.kind for t in self.traits]
        if any(t.basis for t in self.traits):
            # D-0148: 모티브는 원문 경향에서 고른다. 원문에 없는 시비 반응·결점을 지어내지 않는다.
            if not all(t.basis for t in self.traits):
                raise ValueError("모티브 장부는 모든 특질에 basis(원문 경향 칸)가 필요하다")
            if kinds.count("insult_reaction") > 1:
                raise ValueError("insult_reaction 특질은 하나까지다")
        else:
            if kinds.count("insult_reaction") != 1:
                raise ValueError("insult_reaction 특질은 정확히 하나다")
            if "flaw" not in kinds:
                raise ValueError("flaw 특질이 하나 이상 필요하다")
        if len({t.id for t in self.traits}) != len(self.traits):
            raise ValueError("특질 id가 겹친다")
        return self
