"""참고 자료 색인과 선별 계약 (LLD §5.12a, D-0033, D-0035).

색인은 기존 저작 페르소나·Stanford 프리셋·SNS 14유형 등에서 만든 항목과 벡터다. 원문은 Git 밖에 둔다
(NFR-06). 선별 결과에는 항목 ID·출처·버전·선별 이유만 남기고 원문을 옮기지 않는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict

Source = Literal["AUTHORED", "STANFORD", "SNS14", "NIKL", "OTHER"]
Use = Literal["TRAITS", "VOICE", "DATA"]


class IndexItem(Strict):
    itemId: str = Field(min_length=1)
    source: Source
    version: str = ""
    label: str = ""
    uses: list[Use] = Field(min_length=1)
    text: str = Field(min_length=1)
    vector: list[float] = Field(min_length=1)


@register("reference-index-v1")
class ReferenceIndex(Strict):
    schemaVersion: Literal["reference-index-v1"] = "reference-index-v1"
    indexId: str = Field(min_length=1)
    embedder: str = Field(min_length=1)
    dim: int = Field(ge=8)
    sources: list[str] = Field(default_factory=list)
    items: list[IndexItem] = Field(default_factory=list)


class CuratedItem(Strict):
    itemId: str
    use: Use
    why: str = Field(min_length=1)


@register("reference-curation-output-v1")
class CurationOutput(Strict):
    """Curator 에이전트 출력: 검색 후보에서 고른 항목과 이유."""

    schemaVersion: Literal["reference-curation-output-v1"] = "reference-curation-output-v1"
    selected: list[CuratedItem] = Field(min_length=1)


class Retrieved(Strict):
    itemId: str
    use: Use
    score: float


class SelectedRef(Strict):
    itemId: str
    source: Source
    version: str
    label: str
    use: Use
    why: str


@register("reference-set-v1")
class ReferenceSet(Strict):
    schemaVersion: Literal["reference-set-v1"] = "reference-set-v1"
    characterId: str
    refRev: str = Field(pattern=r"^rs\d+$")
    planRev: str
    indexId: str
    indexSha256: str
    embedder: str
    queries: dict[str, str]
    retrieved: list[Retrieved]
    selected: list[SelectedRef]
