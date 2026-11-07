"""trait-sheet-v1, prompt-pair-v1, prompt-probe-v1 (LLD §5.12·§5.13)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, StringConstraints, field_validator, model_validator

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict


class Choice(Strict):
    """선택 학습 기준 5항목 (gemini-sft-poc character-factory-choice-learning §1)."""

    attention: str = Field(description="먼저 주목하는 대상")
    interpretationPriority: str = Field(description="해석과 우선점")
    primaryResponse: str = Field(description="주된 대응")
    expressionIntensity: str = Field(description="표현의 강도")
    switchConditions: list[str] = Field(description="전환 조건")


class JudgmentPriority(Strict):
    value: str
    dilemma: str
    choice: str
    reason: str
    switch: str


class DialogueHabits(Strict):
    order: str
    directness: str
    questions: str
    evidence: str
    lexicon: str


class Situational(Strict):
    condition: str
    reaction: str
    returnOrSwitch: str


class Experience(Strict):
    event: str
    interpretation: str
    habitLink: str


class ExpressedTraits(Strict):
    core: list[str]
    contrast: str


class Card(Strict):
    """Stanford 프리셋 카드 7요소."""

    stance: str
    bigFiveNotes: str = ""
    expressedTraits: ExpressedTraits
    judgmentPriorities: list[JudgmentPriority]
    dialogueHabits: DialogueHabits
    situational: list[Situational]
    experiences: list[Experience]


class Reference(Strict):
    kind: Literal["SNS14", "STANFORD", "OTHER"]
    id: str
    version: str


@register("trait-sheet-v1")
class TraitSheet(Strict):
    schemaVersion: Literal["trait-sheet-v1"] = "trait-sheet-v1"
    characterId: str
    planRev: str
    choice: Choice
    card: Card
    references: list[Reference] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list, description="'미정'으로 남긴 칸")
    typeMappingAssumed: bool = Field(
        default=False, description="14유형과 프리셋 사이 대응을 가정했는지 (Q-0005; 항상 false)"
    )


class PromptText(Strict):
    text: str
    sha256: str
    chars: int


@register("prompt-pair-v1")
class PromptPair(Strict):
    schemaVersion: Literal["prompt-pair-v1"] = "prompt-pair-v1"
    characterId: str
    personaVersion: str | None = None
    traitSheetSha256: str
    sections: list[str]
    long: PromptText
    short: PromptText
    systemRulesRef: str
    systemRulesSha256: str
    shortAdopted: bool = False


class ProbeJudge(Strict):
    pick: Literal["LONG", "SHORT", "TIE", "BOTH_BAD", "NONE"]
    reasons: str = ""


class Probe(Strict):
    sentence: str
    longResponse: str
    shortResponse: str
    judge: ProbeJudge


@register("prompt-probe-v1")
class PromptProbe(Strict):
    schemaVersion: Literal["prompt-probe-v1"] = "prompt-probe-v1"
    characterId: str
    promptPairSha256: str
    probes: list[Probe]
    judgeModel: str
    note: str = "판정은 참고용이다. G6 승인에 자동으로 쓰지 않는다."


# New contracts deliberately do not change validation of historical v1 artifacts.
_Text = Annotated[str, StringConstraints(strip_whitespace=False, min_length=1, pattern=r"\S")]
_Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class PromptTextV2(PromptText):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    text: _Text
    sha256: _Sha256
    chars: int = Field(gt=0)

    @model_validator(mode="after")
    def verify_text(self) -> PromptTextV2:
        if self.chars != len(self.text) or self.sha256 != sha256_text(self.text):
            raise ValueError("prompt text chars/sha256 do not match actual text")
        return self


@register("prompt-pair-v2")
class PromptPairV2(Strict):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    schemaVersion: Literal["prompt-pair-v2"] = "prompt-pair-v2"
    characterId: _Text
    personaVersion: _Text | None = None
    traitSheetSha256: _Sha256
    sections: list[_Text] = Field(min_length=1)
    long: PromptTextV2
    longStatus: Literal["READY"] = "READY"
    short: PromptTextV2 | None = None
    shortStatus: Literal["UNAVAILABLE", "UNQUALIFIED", "READY"]
    systemRulesRef: _Text
    systemRulesSha256: _Sha256
    shortAdopted: Literal[False] = False

    @field_validator("shortAdopted", mode="before")
    @classmethod
    def require_false(cls, value: Any) -> bool:
        if value is not False:
            raise ValueError("shortAdopted must be false")
        return value

    @model_validator(mode="after")
    def verify_short_state(self) -> PromptPairV2:
        if (self.shortStatus == "UNAVAILABLE") != (self.short is None):
            raise ValueError("short data must agree with shortStatus")
        if len(set(self.sections)) != len(self.sections):
            raise ValueError("sections must be unique")
        return self


def load_prompt_pair(data_or_path: Mapping[str, Any] | str | Path) -> PromptPair | PromptPairV2:
    """Read only explicit v1/v2 artifacts; never invent a missing short or version."""
    data = (
        json.loads(Path(data_or_path).read_text(encoding="utf-8"))
        if isinstance(data_or_path, str | Path)
        else dict(data_or_path)
    )
    if not isinstance(data, dict):
        raise ValueError("prompt pair must be a JSON object")
    match data.get("schemaVersion"):
        case "prompt-pair-v1":
            return PromptPair.model_validate(data)
        case "prompt-pair-v2":
            return PromptPairV2.model_validate(data)
        case _:
            raise ValueError("unsupported or missing prompt-pair schemaVersion")


def require_long(pair: PromptPair | PromptPairV2) -> PromptText:
    """Both versions carry a required long prompt."""
    return pair.long


def require_short(pair: PromptPair | PromptPairV2) -> PromptText:
    """Legacy short stays readable; v2 consumers must explicitly support its state."""
    if isinstance(pair, PromptPairV2) and (pair.shortStatus != "READY" or pair.short is None):
        raise ValueError(f"short prompt unsupported: {pair.shortStatus}")
    assert pair.short is not None
    return pair.short
