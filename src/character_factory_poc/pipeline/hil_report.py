"""사람 관문 보고서 (LLD §5.21·§6.10, 명세 §7.4, FR-47, D-0049).

관문 기록·상태 파일·관문 사건 기록만 읽어 관문별·revision별 열린 시각, 결정 시각, 대기 시간,
사람이 적은 검토 시간, 결정, 수정 반복, 추천 일치 여부를 모은다. 외부 호출이 없다.

대기 시간(waitMinutes)은 decided.at - opened.at(분), 검토 시간(reviewMinutes)은 관문 기록의
minutes다. G7a·G8은 사람 판정 자체가 관문의 내용이라 추천 일치 여부를 늘 비운다(spec §7.2).
"""

from __future__ import annotations

import json
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.contracts.report import HilGate, HilReport, HilRound, HilTotals
from character_factory_poc.pipeline.graph import GATES
from character_factory_poc.pipeline.state import gate_events_path

# 사람 판정 자체가 관문의 내용이라 추천을 붙이지 않는 관문(spec §7.2).
NO_REVIEW_GATES = frozenset({"G7a", "G8"})
DEFAULT_MAX_ROUNDS = 3
REPORTS_DIR = "reports"


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def read_events(char_dir: Path) -> list[dict[str, Any]]:
    """관문 사건 기록을 순서대로 읽는다. 깨진 줄은 건너뛴다."""
    path = gate_events_path(Path(char_dir))
    if not path.exists():
        return []
    try:
        lines = path.read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def read_records(char_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """gates/<gate>-<rev>.json을 gate → rev → 기록으로 모은다."""
    folder = Path(char_dir) / "gates"
    out: dict[str, dict[str, dict[str, Any]]] = {}
    if not folder.is_dir():
        return out
    for path in sorted(folder.glob("*.json")):
        stem = path.stem
        if "-" not in stem:
            continue
        gate, rev = stem.split("-", 1)
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        record_rev = data.get("rev")
        key = record_rev if isinstance(record_rev, str) and record_rev else rev
        out.setdefault(gate, {})[key] = data
    return out


def read_state(char_dir: Path) -> dict[str, Any]:
    path = Path(char_dir) / "state.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FactoryError(f"state.json을 읽지 못했다: {exc}") from None
    return data if isinstance(data, dict) else {}


def max_rework_rounds(char_dir: Path) -> int:
    """factory.toml의 [rework] max_rounds. 읽지 못하면 제안값 3을 쓴다."""
    parents = Path(char_dir).resolve().parents
    if len(parents) < 3:
        return DEFAULT_MAX_ROUNDS
    root = parents[2]
    path = root / "factory.toml"
    if not path.exists():
        return DEFAULT_MAX_ROUNDS
    try:
        data = tomllib.loads(path.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return DEFAULT_MAX_ROUNDS
    rework = data.get("rework")
    if not isinstance(rework, dict):
        return DEFAULT_MAX_ROUNDS
    value = rework.get("max_rounds", DEFAULT_MAX_ROUNDS)
    return value if isinstance(value, int) and value > 0 else DEFAULT_MAX_ROUNDS


def rework_cap_reached(char_dir: Path, gate: str, cap: int | None = None) -> bool:
    """rework/ 브리프의 반복 차수가 상한에 닿았는지. 브리프가 없으면 거짓이다.

    C 갈래(수정 요청 재작업)가 아직 브리프를 쓰지 않는 저장소에서는 늘 거짓이다.
    """
    limit = max_rework_rounds(char_dir) if cap is None else cap
    folder = Path(char_dir) / "rework"
    if limit <= 0 or not folder.is_dir():
        return False
    for path in sorted(folder.glob(f"{gate}-*.json")):
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("gate") not in (None, gate):
            continue
        try:
            round_no = int(data.get("round", 0))
        except (TypeError, ValueError):
            continue
        if round_no >= limit:
            return True
    return False


def _minutes_between(start: str | None, end: str | None) -> float | None:
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    try:
        delta = datetime.fromisoformat(end) - datetime.fromisoformat(start)
    except ValueError:
        return None
    return round(delta.total_seconds() / 60, 1)


def _gate_rounds(
    gate: str,
    records: dict[str, dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[HilRound]:
    opened: dict[str, str] = {}
    decided: dict[str, str] = {}
    order: list[str] = []

    def remember(rev: str) -> None:
        if rev not in order:
            order.append(rev)

    for rev in records:
        remember(rev)
    for event in events:
        if event.get("gate") != gate:
            continue
        rev, at = event.get("rev"), event.get("at")
        if not isinstance(rev, str):
            continue
        kind = event.get("event")
        if not isinstance(at, str):
            continue
        remember(rev)
        if kind == "opened" and (rev not in opened or at < opened[rev]):
            opened[rev] = at
        elif kind == "decided" and (rev not in decided or at > decided[rev]):
            decided[rev] = at

    rounds: list[HilRound] = []
    for rev in order:
        record = records.get(rev, {})
        opened_at = opened.get(rev)
        decided_at = decided.get(rev) or (
            record.get("decidedAt") if isinstance(record.get("decidedAt"), str) else None
        )
        decision = record.get("decision") if isinstance(record.get("decision"), str) else None
        try:
            review_minutes = float(record.get("minutes", 0.0) or 0.0)
        except (TypeError, ValueError):
            review_minutes = 0.0
        followed: bool | None = None
        if gate not in NO_REVIEW_GATES and isinstance(record.get("followedReview"), bool):
            followed = bool(record["followedReview"])
        review_ref = record.get("reviewRef") if isinstance(record.get("reviewRef"), str) else None
        rounds.append(
            HilRound(
                rev=rev,
                openedAt=opened_at,
                decidedAt=decided_at,
                waitMinutes=_minutes_between(opened_at, decided_at),
                reviewMinutes=review_minutes,
                decision=decision,
                followedReview=followed,
                reviewRef=review_ref,
            )
        )
    rounds.sort(key=lambda r: (r.openedAt or r.decidedAt or "", r.rev))
    return rounds


def build_hil_report(char_dir: Path) -> HilReport:
    """관문·revision별 사람 시간과 합계를 만든다. 외부 호출이 없다."""
    char_dir = Path(char_dir)
    if not char_dir.is_dir():
        raise FactoryError(f"캐릭터 폴더가 없다: {char_dir}")
    state = read_state(char_dir)
    subject = state.get("subjectId") if isinstance(state.get("subjectId"), str) else char_dir.name
    records = read_records(char_dir)
    events = read_events(char_dir)
    cap = max_rework_rounds(char_dir)

    gates: list[HilGate] = []
    decided_gates = 0
    request_changes = 0
    judged: list[bool] = []
    for gate in GATES:
        rounds = _gate_rounds(gate, records.get(gate, {}), events)
        changes = sum(1 for r in rounds if r.decision == "REQUEST_CHANGES")
        if any(r.decidedAt for r in rounds):
            decided_gates += 1
        request_changes += changes
        judged += [r.followedReview for r in rounds if r.followedReview is not None]
        gates.append(
            HilGate(
                gate=gate,
                rounds=rounds,
                requestChangesCount=changes,
                reworkCapReached=rework_cap_reached(char_dir, gate, cap),
            )
        )

    wait_total = sum(r.waitMinutes or 0.0 for g in gates for r in g.rounds)
    review_total = sum(r.reviewMinutes for g in gates for r in g.rounds)
    return HilReport(
        subjectId=subject,
        createdAt=_iso(_now()),
        gates=gates,
        totals=HilTotals(
            gatesDecided=decided_gates,
            waitMinutes=round(wait_total, 1),
            reviewMinutes=round(review_total, 1),
            requestChanges=request_changes,
            followedReviewRate=(
                round(sum(1 for x in judged if x) / len(judged), 3) if judged else None
            ),
        ),
    )


def reports_folder(char_dir: Path) -> Path:
    return Path(char_dir) / REPORTS_DIR


def hil_report_path(char_dir: Path, at: datetime | None = None) -> Path:
    stamp = (at or _now()).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    return reports_folder(char_dir) / f"hil-{stamp}.json"


def write_hil_report(char_dir: Path, at: datetime | None = None) -> tuple[HilReport, Path]:
    """보고서를 만들어 runs/characters/<id>/reports/hil-<UTC 시각>.json에 쓴다.

    보고서는 다시 만들 수 있는 파생 기록이라 한 번만 쓰기 규칙을 두지 않는다. 다만 같은 초에
    두 번 쓰면 파일 이름이 같아 나중 내용으로 덮어쓴다.
    """
    from character_factory_poc.common.schema import dump

    report = build_hil_report(char_dir)
    path = hil_report_path(char_dir, at)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dump(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report, path
