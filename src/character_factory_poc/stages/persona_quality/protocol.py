"""독립 슬롯과 누적 대화 규약. 실제 자료는 runs/에만 둔다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.contracts.common import Strict


class Branch(Strict):
    contains: str = Field(min_length=1)
    user: str = Field(min_length=1)


class UserTurn(Strict):
    user: str = Field(min_length=1)
    branches: list[Branch] = Field(default_factory=list)


class Scene(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    turns: list[UserTurn]
    expectedChoices: dict[int, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def size(self):
        if len(self.turns) not in (6, 24):
            raise ValueError("장면은6턴 또는24턴이다")
        if any(k < 1 or k > len(self.turns) for k in self.expectedChoices):
            raise ValueError("행동 문항 위치가 장면 범위를 벗어난다")
        return self


class Slot(Strict):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    characterId: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    recipe: Literal["old", "new"]
    root: str
    scenes: list[Scene]

    @model_validator(mode="after")
    def complete(self):
        if len(self.scenes) != 7 or sorted(len(s.turns) for s in self.scenes) != [6] * 6 + [24]:
            raise ValueError("슬롯은6장면×6턴과1장면×24턴이다")
        if len({s.id for s in self.scenes}) != 7:
            raise ValueError("장면 ID가 중복됐다")
        if sum(len(s.expectedChoices) for s in self.scenes) != 5:
            raise ValueError("행동 문항5개를 S7 전에 고정한다")
        return self


class Cohort(Strict):
    schemaVersion: Literal["persona-quality-cohort-v1"] = "persona-quality-cohort-v1"
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    split: Literal["development", "holdout"]
    profile: dict
    baselineSource: str | None = None
    baselineSourceSha256: str | None = None
    recipeHash: str = Field(min_length=64, max_length=64)
    rubricHash: str = Field(min_length=64, max_length=64)
    independent: bool = False
    overlapAudit: str = ""
    expectedBeforeFormation: bool = False
    slots: list[Slot] = Field(min_length=1)
    # 형성은 같은 슬롯 root의 씨앗/S2 준비 뒤 실행한다. 이미 만들어진 산출물은 재사용하지 않는다.
    formation: bool = True

    @model_validator(mode="after")
    def unique(self):
        if len({s.id for s in self.slots}) != len(self.slots):
            raise ValueError("슬롯 ID가 중복됐다")
        identities = [(str(Path(s.root).resolve()), s.characterId) for s in self.slots]
        if len(set(identities)) != len(identities):
            raise ValueError("독립 run은 같은 캐릭터 폴더를 공유하지 않는다")
        if self.split == "holdout":
            from collections import Counter

            counts = Counter(s.characterId for s in self.slots if s.recipe == "new")
            if len(counts) != 8 or set(counts.values()) != {2}:
                raise ValueError("holdout requires exactly two runs for each of eight characters")
        return self


def canonical_hash(obj) -> str:
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump(mode="json")
    return sha256_text(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def next_user(turn: UserTurn, last_assistant: str) -> str:
    """의미를 추정해 대사를 고치지 않는다. 사전에 승인한 문자열 분기만 적용한다."""
    matched = [b.user for b in turn.branches if b.contains in last_assistant]
    if len(set(matched)) > 1:
        raise ValueError("서로 다른 후속 대사가 동시에 활성화됐다")
    return matched[0] if matched else turn.user


def load_cohort(path: Path) -> Cohort:
    raw = json.loads(Path(path).read_text("utf-8"))
    if raw.get("schemaVersion") == "persona-development-cohort-v2":
        from character_factory_poc.stages.persona_quality.choice_voice_protocol import (
            DevelopmentCohortV2,
        )

        return DevelopmentCohortV2.model_validate(raw)
    return Cohort.model_validate(raw)


class HumanTurn(Strict):
    turn: int = Field(ge=1, strict=True)
    voiceOK: bool = Field(strict=True)
    majorTypes: list[str]
    evidence: str = ""
    choiceOK: bool | None = None


class ReviewBody(Strict):
    reviewer: str = Field(min_length=1)
    sawLLMCandidatesFirst: Literal[False]
    naturalness: int = Field(ge=0, le=2, strict=True)
    collapse: bool = Field(strict=True)
    turns: list[HumanTurn]


class AdjudicatedReview(ReviewBody):
    reason: str = Field(min_length=1)


class SceneReview(ReviewBody):
    second: ReviewBody | None = None
    adjudication: AdjudicatedReview | None = None


class HumanReviews(Strict):
    cohortHash: str = Field(pattern=r"^[0-9a-f]{64}$")
    scenes: dict[str, SceneReview]
    blueprintFaithful: dict[str, bool]


def recipe_hash(source: Path) -> str:
    source = Path(source)
    return canonical_hash(
        {
            p.relative_to(source).as_posix(): p.read_text("utf-8")
            for p in sorted(source.rglob("*"))
            if p.suffix in (".py", ".md", ".json") and "__pycache__" not in p.parts
        }
    )
