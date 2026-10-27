"""trait-sheet-v1, prompt-pair-v1, prompt-probe-v1 (LLD §5.12·§5.13)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

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
