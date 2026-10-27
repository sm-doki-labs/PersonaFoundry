"""character-plan-v1 (LLD §5.9)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from acf.common.schema import register
from acf.contracts.common import Strict

EvidenceKind = Literal["BRIEF", "APPEARANCE", "USER", "PRESET"]


class Evidence(Strict):
    kind: EvidenceKind
    ref: str = ""
    quote: str = ""


class Chapter(Strict):
    chapterId: Literal["ch1", "ch2", "ch3"]
    scene: str = Field(min_length=1)
    relationStage: str = Field(min_length=1)
    lighting: str = ""
    composition: str = ""


PERSONALITY_FIELDS = ("coreTraits", "contrastTrait")


@register("character-plan-v1")
class CharacterPlan(Strict):
    schemaVersion: Literal["character-plan-v1"] = "character-plan-v1"
    characterId: str
    planRev: str
    briefId: str | None = None
    name: str = Field(min_length=1)
    age: int = Field(ge=18)
    job: str = Field(min_length=1)
    coreTraits: list[str] = Field(min_length=1, max_length=4)
    contrastTrait: str = Field(min_length=1)
    chapters: list[Chapter] = Field(min_length=3, max_length=3)
    evidence: dict[str, list[Evidence]] = Field(default_factory=dict)
    appearanceRev: str | None = None
    notes: str = ""

    @field_validator("chapters")
    @classmethod
    def _chapters_unique(cls, v: list[Chapter]) -> list[Chapter]:
        ids = [c.chapterId for c in v]
        if sorted(ids) != ["ch1", "ch2", "ch3"]:
            raise ValueError("chapters는 ch1, ch2, ch3 각각 하나씩이어야 한다")
        return v

    @model_validator(mode="after")
    def _personality_not_from_appearance(self):
        # D-0005: 성격 칸의 근거에 외모 명세가 들어가면 실패한다.
        for f in PERSONALITY_FIELDS:
            for ev in self.evidence.get(f, []):
                if ev.kind == "APPEARANCE":
                    raise ValueError(f"{f}의 근거로 APPEARANCE를 쓸 수 없다(D-0005)")
        return self
