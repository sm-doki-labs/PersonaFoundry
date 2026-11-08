"""트윈 G8의 판정 근거. 원문과 생성문은 시연·블라인드 화면에만 둔다."""

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import Strict

Side = Literal["A", "B"]


class Trial(Strict):
    sceneId: str
    pairId: str = Field(pattern=r"^[a-f0-9]{32}$")
    modelActual: Side
    modelPick: Side
    blindActual: Side
    exact: bool
    overlap: list[Literal["TRAIN", "PROMPT", "VOICE"]]


class Score(Strict):
    correct: int = Field(ge=0)
    total: int = Field(ge=0)
    rate: float | None = Field(ge=0, le=1)


class Condition(Strict):
    armId: str
    model: str
    promptSha256: str
    servingModel: str | None
    status: Literal["COMPLETE", "NO_SERVING", "PLANNED", "NO_JUDGE"]
    ballot: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    trials: list[Trial] = Field(default_factory=list)
    modelScore: Score
    humanScore: Score


@register("twin-comparison-v1")
class TwinComparison(Strict):
    schemaVersion: Literal["twin-comparison-v1"] = "twin-comparison-v1"
    characterId: str
    revision: str
    mode: Literal["TRAIN", "PROMPT_ONLY", "BIND_EXISTING"]
    holdoutRev: str
    scenesSha256: str
    sceneCount: int = Field(gt=0)
    overlapChars: int = Field(gt=0)
    judgeModel: str
    plannedCalls: int = Field(ge=0)
    costUpperUsd: float | None = Field(ge=0)
    conditions: list[Condition] = Field(min_length=1)
