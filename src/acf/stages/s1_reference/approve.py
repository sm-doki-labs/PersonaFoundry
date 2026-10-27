"""G1 결정과 선택된 외모군·참조 사진 (명세 §7, LLD §8.1 approve, FR-09, D-0022).

G1 기록의 selections는 [외모군 ID, 참조 미리보기 ID...] 순서다. 참조 미리보기는 고른 외모군의
미리보기 가운데 0~2장이며, S2가 같은 얼굴을 유지하는 참조 이미지로 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path

from acf.common.errors import FactoryError, GateNotApprovedError
from acf.common.schema import validate
from acf.contracts.reference import AppearanceCluster, ReferencePreview, ReferenceReport
from acf.pipeline.context import Context
from acf.pipeline.gates import write_gate_record

MAX_REFERENCE_PREVIEWS = 2


def load_report(rev_dir: Path) -> ReferenceReport:
    obj = json.loads((rev_dir / "report.json").read_text("utf-8"))
    return validate("reference-report-v2", obj)  # type: ignore[return-value]


def load_previews(rev_dir: Path) -> list[ReferencePreview]:
    objs = json.loads((rev_dir / "previews.json").read_text("utf-8"))
    return [validate("reference-preview-v1", o) for o in objs]  # type: ignore[misc]


def approve_g1(ctx: Context, cid: str, answer: dict) -> Path:
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    g = state.gate("G1")
    if g.status != "AWAITING_HUMAN" or not g.rev:
        raise FactoryError(f"{cid}: G1이 대기 상태가 아니다({g.status})")
    rev_dir = char_dir / "s1-reference" / g.rev
    report = load_report(rev_dir)
    ids = [c.clusterId for c in report.candidates]
    previews = load_previews(rev_dir)
    decision = answer["decision"]
    selections = list(answer.get("selections") or [])
    refs = list(dict.fromkeys(answer.get("referencePreviews") or []))
    reasons = answer.get("reasons", "")
    if decision == "APPROVE":  # --auto-approve G1 (D-0015, D-0018)
        if not selections:
            selections = [report.ordering[0].clusterId]
            reasons = (
                reasons + " " if reasons else ""
            ) + f"정렬 1위 외모군 {selections[0]}을 골랐다."
        if not refs:
            first = next((p.previewId for p in previews if p.clusterId == selections[0]), None)
            refs = [first] if first else []
        decision = "SELECT"
    if decision == "SELECT":
        if len(selections) != 1 or selections[0] not in ids:
            raise FactoryError(
                f"G1 SELECT는 후보 하나를 selections에 담아야 한다({', '.join(ids)})"
            )
        allowed = [p.previewId for p in previews if p.clusterId == selections[0]]
        bad = [r for r in refs if r not in allowed]
        if bad:
            raise FactoryError(
                f"참조 사진 {', '.join(bad)}는 {selections[0]}의 미리보기가 아니다"
                f"({', '.join(allowed)})"
            )
        if len(refs) > MAX_REFERENCE_PREVIEWS:
            raise FactoryError(f"참조 사진은 {MAX_REFERENCE_PREVIEWS}장까지 고른다")
        selections = selections + refs
    elif decision in {"REJECT", "REQUEST_CHANGES"}:
        selections = []
    else:
        raise FactoryError(f"G1 결정은 SELECT·REQUEST_CHANGES·REJECT 중 하나다: {decision}")
    rec = write_gate_record(
        char_dir,
        state,
        gate="G1",
        rev=g.rev,
        stage_id="s1",
        shown=[rev_dir / "report.json", rev_dir / "previews.json", rev_dir / "gate-G1.html"],
        decision=decision,
        reviewer=answer["reviewer"],
        reasons=reasons,
        selections=selections,
        minutes=float(answer.get("minutes", 0)),
        requested_changes=answer.get("requestedChanges"),
    )
    ctx.ledger(cid).record_human(gate="G1", minutes=rec.minutes, ref=f"{cid}/{g.rev}")
    return rev_dir


def selected_cluster(ctx: Context, cid: str) -> AppearanceCluster:
    """G1에서 고른 외모군. 이름 없이 공통 특징·근거만 담는다(S2 입력, FR-35)."""
    char_dir = ctx.character_dir(cid)
    g = ctx.state(cid).gate("G1")
    if g.status != "APPROVED" or not g.rev or not g.recordRef:
        raise GateNotApprovedError(f"{cid}: G1 승인이 필요하다(현재 {g.status})")
    rec = json.loads((char_dir / g.recordRef).read_text("utf-8"))
    report = load_report(char_dir / "s1-reference" / g.rev)
    return next(c for c in report.candidates if c.clusterId == rec["selections"][0])


def selected_references(ctx: Context, cid: str) -> list[tuple[ReferencePreview, Path]]:
    """G1에서 고른 참조 미리보기와 파일 경로(S2 참조 이미지, D-0022). 고르지 않았으면 빈 목록."""
    char_dir = ctx.character_dir(cid)
    g = ctx.state(cid).gate("G1")
    if g.status != "APPROVED" or not g.rev or not g.recordRef:
        raise GateNotApprovedError(f"{cid}: G1 승인이 필요하다(현재 {g.status})")
    rec = json.loads((char_dir / g.recordRef).read_text("utf-8"))
    rev_dir = char_dir / "s1-reference" / g.rev
    by_id = {p.previewId: p for p in load_previews(rev_dir)}
    return [(by_id[i], rev_dir / by_id[i].filePath) for i in rec["selections"][1:]]
