"""사람 관문 보고서 계약 (LLD §5.21, 명세 §7.4, FR-47, D-0049).

관문 기록(gates/<gate>-<rev>.json), 상태 파일, 관문 사건 기록(ledger/gate-events.jsonl)만으로
다시 만드는 보고서다. 결정·검토 시간은 관문 기록에서, 열린 시각·결정 시각은 사건 기록에서 읽는다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from character_factory_poc.common.schema import register
from character_factory_poc.contracts.common import GateDecision, Strict


class HilRound(Strict):
    """관문 revision 하나의 사람 시간. 아직 결정되지 않았으면 decidedAt이 비어 있다."""

    rev: str
    openedAt: str | None = None
    decidedAt: str | None = None
    waitMinutes: float | None = None
    reviewMinutes: float = 0.0
    decision: GateDecision | None = None
    followedReview: bool | None = None
    reviewRef: str | None = None


class HilGate(Strict):
    gate: str
    rounds: list[HilRound] = Field(default_factory=list)
    requestChangesCount: int = 0
    reworkCapReached: bool = False


class HilTotals(Strict):
    gatesDecided: int = 0
    waitMinutes: float = 0.0
    reviewMinutes: float = 0.0
    requestChanges: int = 0
    followedReviewRate: float | None = None


@register("hil-report-v1")
class HilReport(Strict):
    schemaVersion: Literal["hil-report-v1"] = "hil-report-v1"
    subjectId: str
    createdAt: str
    gates: list[HilGate] = Field(default_factory=list)
    totals: HilTotals = Field(default_factory=HilTotals)
