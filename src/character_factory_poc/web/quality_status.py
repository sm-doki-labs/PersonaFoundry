"""현재 판의 승인·비교 기록에서 읽기 전용 검토 상태를 만든다.

공정 승인, 비교 수행, 품질 합격은 별개다. 기존 기록에는 통합 품질 합격 계약이
없으므로 여기서는 verified를 True로 추정하지 않는다. 원문·정답·대사는 반환하지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path

_AUTO_REVIEWERS = {"시연 자동 승인", "자동 진행", "auto:--auto-approve"}
_COMPARISON_LABELS = {
    "SKIPPED": "평가 생략",
    "COMPLETE": "비교 수행 기록 있음",
    "PARTIAL": "비교 일부 수행",
    "PLANNED": "비교 실행 전",
    "NO_JUDGE": "판정 모델 미준비",
    "NO_SERVING": "비교 모델 미준비",
    "MISSING": "비교 기록 없음",
    "UNREADABLE": "비교 기록 확인 필요",
}


def _path(folder: Path, ref: str) -> Path | None:
    path = (folder / ref).resolve()
    return path if path.is_relative_to(folder.resolve()) else None


def _read(path: Path | None) -> dict | None:
    try:
        data = json.loads(path.read_text("utf-8")) if path else None
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _approval(folder, gate, stage):
    rev = gate.get("rev")
    result = dict(
        gate=gate["id"],
        rev=rev,
        status="unverified",
        reviewer=None,
        recordRef=None,
        label="승인 근거 미확인",
    )
    if gate.get("status") == "AWAITING_HUMAN":
        return dict(result, status="pending", label="검토 대기")
    if gate.get("status") != "APPROVED" or not rev or stage.get("rev") != rev:
        return result
    ref = gate.get("recordRef") or f"gates/{gate['id']}-{rev}.json"
    if not isinstance(ref, str):
        return result
    record = _read(_path(folder, ref))
    if not record or record.get("gate") != gate["id"] or record.get("rev") != rev:
        return result
    reviewer = record.get("reviewer")
    if record.get("decision") not in {"APPROVE", "SELECT"} or not isinstance(reviewer, str):
        return result
    if not reviewer.strip():
        return result
    auto = reviewer.strip() in _AUTO_REVIEWERS
    return dict(
        result,
        status="auto_approved" if auto else "approval_recorded",
        reviewer=reviewer,
        recordRef=ref,
        label="자동 승인 · 사람 검토 미확인" if auto else "승인 기록 있음 · 품질 합격 미판정",
    )


def _comparison(folder, stages):
    rev = next((s.get("rev") for s in stages if s["id"] == "s10"), None)
    result = dict(status="MISSING", reportRef=None, conditions=[])
    if not isinstance(rev, str) or not rev:
        return result
    for name in (
        "twin-comparison-reviewed.json",
        "twin-comparison.json",
        "twin-comparison-plan.json",
    ):
        ref = f"s10-eval/{rev}/{name}"
        path = _path(folder, ref)
        if path is None or not path.is_file():
            continue
        report = _read(path)
        conditions = report.get("conditions") if report else None
        valid = (
            report
            and report.get("revision") == rev
            and report.get("characterId") == folder.name
            and isinstance(conditions, list)
            and conditions
            and all(
                isinstance(c, dict)
                and c.get("status")
                in {
                    "SKIPPED",
                    "COMPLETE",
                    "PLANNED",
                    "NO_JUDGE",
                    "NO_SERVING",
                }
                for c in conditions
            )
        )
        if not valid:
            return dict(result, status="UNREADABLE", reportRef=ref)
        statuses = {c["status"] for c in conditions}
        status = (
            "SKIPPED"
            if "SKIPPED" in statuses
            else "COMPLETE"
            if statuses == {"COMPLETE"}
            else "PARTIAL"
            if "COMPLETE" in statuses
            else "PLANNED"
            if "PLANNED" in statuses
            else "NO_JUDGE"
            if "NO_JUDGE" in statuses
            else "NO_SERVING"
        )
        return dict(
            status=status,
            reportRef=ref,
            conditions=[dict(armId=c.get("armId"), status=c["status"]) for c in conditions],
        )
    return result


def derive_quality_status(folder: Path, stages: list[dict], gates: list[dict]) -> dict:
    by_gate = {s["gate"]: s for s in stages if s.get("gate")}
    approvals = [_approval(folder, g, by_gate.get(g["id"], {})) for g in gates]
    comparison = _comparison(folder, stages)
    comparison["label"] = _COMPARISON_LABELS[comparison["status"]]
    automatic = [a["gate"] for a in approvals if a["status"] == "auto_approved"]
    recorded = [a["gate"] for a in approvals if a["status"] == "approval_recorded"]
    skipped = comparison["status"] == "SKIPPED"
    label = (
        "평가 생략 · 품질 검증 미확인"
        if skipped
        else "자동 승인 · 품질 검증 미확인"
        if automatic
        else "승인 기록 있음 · 품질 합격 미판정"
        if recorded
        else "품질 검증 미확인"
    )
    notes = []
    if automatic:
        notes.append(f"{'·'.join(automatic)} 자동 승인 기록이 있어요. 사람 검토로 보지 않아요.")
    for gate in ("G6", "G8"):
        approval = next((a for a in approvals if a["gate"] == gate), None)
        if approval and approval["status"] != "auto_approved":
            notes.append(f"{gate}: {approval['label']}.")
    notes.append(f"{comparison['label']}. 승인·비교 기록만으로 품질 합격을 판정하지 않아요.")
    return dict(
        status="evaluation_skipped" if skipped else "review_recorded" if recorded else "unverified",
        verified=False,
        label=label,
        detail=" ".join(notes),
        approvals=approvals,
        comparison=comparison,
    )
