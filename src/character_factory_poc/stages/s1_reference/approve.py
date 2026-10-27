"""G1 결정과 선택된 외모군·얼굴 (명세 §7, LLD §8.1 approve, FR-09, D-0042·D-0043).

G1 기록의 selections는 [외모군 ID, 고른 얼굴 ID] 순서다. 얼굴은 정확히 한 장이고, 외모군은 그
얼굴에서 정한다. 고른 얼굴이 S2 기준 이미지와 이후 모든 장면·영상의 얼굴 기준이 된다.
`REQUEST_CHANGES`는 고칠 점 메모(`note`)를 받고, 다음 `cfp ref faces`가 얼굴만 다시 만든다.
"""

from __future__ import annotations

import json
from pathlib import Path

from character_factory_poc.common.errors import FactoryError, GateNotApprovedError
from character_factory_poc.common.schema import validate
from character_factory_poc.contracts.reference import (
    AppearanceCluster,
    ReferencePreview,
    ReferenceReport,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record

REQUIRED_REFERENCE_PREVIEWS = 1


def load_report(rev_dir: Path) -> ReferenceReport:
    obj = json.loads((rev_dir / "report.json").read_text("utf-8"))
    return validate("reference-report-v2", obj)  # type: ignore[return-value]


def load_previews(rev_dir: Path) -> list[ReferencePreview]:
    objs = json.loads((rev_dir / "previews.json").read_text("utf-8"))
    return [validate("reference-preview-v1", o) for o in objs]  # type: ignore[misc]


def _select(
    report: ReferenceReport,
    previews: list[ReferencePreview],
    selections: list[str],
    refs: list[str],
) -> tuple[list[str], str]:
    """SELECT 답을 검사해 [외모군, 얼굴]을 돌려준다. 외모군은 고른 얼굴에서 정한다(D-0042)."""
    if len(refs) != REQUIRED_REFERENCE_PREVIEWS:
        raise FactoryError(
            "G1 SELECT는 얼굴 정확히 한 장을 referencePreviews에 담아야 한다"
            f"(현재 {len(refs)}장). 외모군은 고른 얼굴에서 정한다(D-0042)"
        )
    by_id = {p.previewId: p for p in previews}
    face = by_id.get(refs[0])
    if face is None:
        raise FactoryError(
            f"얼굴 {refs[0]}는 이 실행의 미리보기가 아니다({', '.join(sorted(by_id))})"
        )
    ids = [c.clusterId for c in report.candidates]
    if len(selections) > REQUIRED_REFERENCE_PREVIEWS:
        raise FactoryError(f"G1 SELECT의 selections에는 외모군 하나만 담는다({', '.join(ids)})")
    if selections and selections[0] != face.clusterId:
        raise FactoryError(
            f"G1 SELECT의 외모군 {selections[0]}은 고른 얼굴 {face.previewId}"
            f"({face.clusterId})과 다르다. selections를 비우면 얼굴에서 정한다(D-0042)"
        )
    if face.clusterId not in ids:
        raise FactoryError(f"얼굴 {face.previewId}의 외모군 {face.clusterId}가 보고서에 없다")
    return [face.clusterId, face.previewId], f"고른 얼굴 {face.previewId}의 외모군 {face.clusterId}"


def approve_g1(ctx: Context, cid: str, answer: dict) -> Path:
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    g = state.gate("G1")
    if g.status != "AWAITING_HUMAN" or not g.rev:
        raise FactoryError(f"{cid}: G1이 대기 상태가 아니다({g.status})")
    if state.stage("s2").status == "APPROVED":
        raise FactoryError(
            f"{cid}: s2가 이미 승인돼 외모가 고정됐다. 얼굴을 바꾸려면 새 rf로 S1을 다시 돌린다"
            f"(cfp ref run {cid} --ranking ranking.json, D-0042)"
        )
    rev_dir = char_dir / "s1-reference" / g.rev
    report = load_report(rev_dir)
    previews = load_previews(rev_dir)
    decision = answer["decision"]
    selections = list(answer.get("selections") or [])
    refs = list(dict.fromkeys(answer.get("referencePreviews") or []))
    reasons = str(answer.get("reasons", ""))
    note = str(answer.get("note") or "").strip()
    if decision == "APPROVE":  # --auto-approve G1 (D-0015): 정렬 1위 외모군의 첫 얼굴
        if not selections:
            selections = [report.ordering[0].clusterId]
        if not refs:
            first = next((p.previewId for p in previews if p.clusterId == selections[0]), None)
            refs = [first] if first else []
        reasons = (reasons + " " if reasons else "") + (
            f"정렬 1위 외모군 {selections[0]}의 첫 얼굴을 골랐다."
        )
        decision = "SELECT"
    if decision == "SELECT":
        selections, why = _select(report, previews, selections, refs)
        reasons = (reasons + " " if reasons else "") + why
    elif decision == "REQUEST_CHANGES":
        if not note:
            raise FactoryError(
                "G1 REQUEST_CHANGES는 고칠 점 note가 필요하다. cfp ref faces가 이 메모로 얼굴만 "
                "다시 만든다(D-0043)"
            )
        reasons = reasons or note
        selections = []
    elif decision == "REJECT":
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


def _approved_record(ctx: Context, cid: str) -> dict:
    char_dir = ctx.character_dir(cid)
    g = ctx.state(cid).gate("G1")
    if g.status != "APPROVED" or not g.rev or not g.recordRef:
        raise GateNotApprovedError(f"{cid}: G1 승인이 필요하다(현재 {g.status})")
    return json.loads((char_dir / g.recordRef).read_text("utf-8"))


def selected_cluster(ctx: Context, cid: str) -> AppearanceCluster:
    """G1에서 고른 외모군. 이름 없이 공통 특징·근거만 담는다(S2 입력, FR-35)."""
    rec = _approved_record(ctx, cid)
    rev = ctx.state(cid).gate("G1").rev or ""
    report = load_report(ctx.character_dir(cid) / "s1-reference" / rev)
    return next(c for c in report.candidates if c.clusterId == rec["selections"][0])


def selected_references(ctx: Context, cid: str) -> list[tuple[ReferencePreview, Path]]:
    """G1에서 고른 얼굴과 파일 경로(S2 기준 이미지, D-0042). 얼굴은 정확히 한 장이다."""
    rec = _approved_record(ctx, cid)
    rev_dir = ctx.character_dir(cid) / "s1-reference" / (ctx.state(cid).gate("G1").rev or "")
    by_id = {p.previewId: p for p in load_previews(rev_dir)}
    out: list[tuple[ReferencePreview, Path]] = []
    for pid in rec["selections"][1:]:
        if pid not in by_id:  # 옛 rf의 기록을 새 rf에 옮겨 읽은 경우
            raise FactoryError(f"{cid}: G1 기록의 얼굴 {pid}가 이 실행 미리보기에 없다")
        out.append((by_id[pid], rev_dir / by_id[pid].filePath))
    return out


def selected_face(ctx: Context, cid: str) -> tuple[ReferencePreview, Path]:
    """S2가 쓰는 얼굴 정확히 한 장. 옛 기록이 0장·2장이면 이유를 붙여 거절한다."""
    refs = selected_references(ctx, cid)
    if len(refs) != REQUIRED_REFERENCE_PREVIEWS:
        raise FactoryError(
            f"{cid}: G1 기록에 고른 얼굴이 {len(refs)}장이다. 얼굴 정확히 한 장이 필요하다(D-0042)"
        )
    return refs[0]
