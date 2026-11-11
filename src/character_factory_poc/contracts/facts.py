"""공인 모티브의 공개 사실과 원문 인용 계약."""

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, HttpUrl, StringConstraints

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r"^[^\r\n]+$")]


class FactSource(Strict):
    url: HttpUrl
    title: str
    publishedAt: date | None = None


class Quote(Strict):
    msgId: Line
    quote: Line


class SelfView(Quote):
    paraphrase: Line


class Fact(Strict):
    factId: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    text: Line
    category: Literal["BIO", "CAREER", "RESULT", "AWARD", "RECORD", "CURRENT_STATUS"]
    eventDate: date
    importance: int = Field(ge=1, le=3)
    sources: list[FactSource] = Field(min_length=1)
    selfView: SelfView | None = None
    excluded: bool = False

    def line(self) -> str:
        return f"{self.eventDate.isoformat()}: {self.text}"


@register("motif-facts-v1")
class MotifFacts(Strict):
    schemaVersion: Literal["motif-facts-v1"] = "motif-facts-v1"
    items: list[Fact]
    deflections: list[Quote] = Field(default_factory=list, max_length=3)

    def phrases(self) -> list[str]:
        """사생활 넘기는 말. 뜻이 분명한 기본 문장을 맨 앞에 두고 원문 표현을 뒤에 붙인다."""
        phrases = ["그런 얘기는 따로 안 하고 있어요"]
        for item in self.deflections:
            if item.quote not in phrases:
                phrases.append(item.quote)
        if len(phrases) < 2:
            phrases.append("그건 저만 알고 있을게요")
        return phrases[:3]
