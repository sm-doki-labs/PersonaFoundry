"""공통 계약: gate-record-v1, 상태 파일."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from character_factory_poc.common.schema import register


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactRef(Strict):
    ref: str
    sha256: str


class RequestedChange(Strict):
    field: str
    note: str


GateDecision = Literal["APPROVE", "REJECT", "REQUEST_CHANGES", "SELECT"]


@register("gate-record-v1")
class GateRecord(Strict):
    schemaVersion: Literal["gate-record-v1"] = "gate-record-v1"
    subjectId: str = Field(description="characterId 또는 briefId")
    gate: str
    rev: str
    shownArtifacts: list[ArtifactRef]
    decision: GateDecision
    selections: list[str] = Field(default_factory=list)
    reasons: str = ""
    requestedChanges: list[RequestedChange] = Field(default_factory=list)
    reviewer: str
    minutes: float = 0.0
    decidedAt: str


StageStatus = Literal[
    "PENDING", "RUNNING", "CHECK_FAILED", "AWAITING_HUMAN", "APPROVED", "REJECTED", "SKIPPED"
]
GateStatus = Literal["PENDING", "AWAITING_HUMAN", "APPROVED", "REJECTED"]


class StageState(Strict):
    status: StageStatus = "PENDING"
    currentRev: str | None = None
    attempts: int = 0
    lastError: str | None = None
    updatedAt: str | None = None


class GateState(Strict):
    status: GateStatus = "PENDING"
    rev: str | None = None
    recordRef: str | None = None


@register("state-v1")
class State(Strict):
    schemaVersion: Literal["state-v1"] = "state-v1"
    subjectId: str
    stages: dict[str, StageState] = Field(default_factory=dict)
    gates: dict[str, GateState] = Field(default_factory=dict)
