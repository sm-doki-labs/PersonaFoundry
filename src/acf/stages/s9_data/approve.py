"""G7a·G7 승인 (LLD §5.16·§8.8, D-0044).

G7a는 클러스터 단위로 판정을 받는다. 한 관문 rev에 여러 클러스터 기록이 쌓이므로
gate-record 파일 이름에 클러스터를 붙인다. 모든 클러스터가 SELECT면 관문이 승인되고,
하나라도 REQUEST_CHANGES면 그 클러스터만 메모를 붙여 다시 만든다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acf.common.canonical import sha256_file
from acf.common.errors import FactoryError
from acf.common.schema import dump, validate
from acf.common.store import read_json, write_manifest, write_once_json
from acf.contracts.common import GateRecord
from acf.contracts.dataset import DataQa
from acf.pipeline.context import Context
from acf.pipeline.gates import now_iso
from acf.stages.s9_data import plan as plan_mod
from acf.stages.s9_data import samples as writer
from acf.stages.s9_data.plan import CLUSTERS

_VERDICTS = {"ADOPT", "FIX", "REJECT"}


def _record(
    ctx: Context,
    cid: str,
    *,
    gate: str,
    rev: str,
    shown: list[Path],
    decision: str,
    reviewer: str,
    reasons: str,
    minutes: float,
    suffix: str = "",
) -> tuple[GateRecord, Path]:
    char_dir = ctx.character_dir(cid)
    rec = GateRecord(
        subjectId=cid,
        gate=gate,
        rev=rev,
        shownArtifacts=[
            {"ref": p.relative_to(char_dir).as_posix(), "sha256": sha256_file(p)} for p in shown
        ],
        decision=decision,  # type: ignore[arg-type]
        selections=[],
        reasons=reasons,
        reviewer=reviewer,
        minutes=minutes,
        decidedAt=now_iso(),
    )
    path = char_dir / "gates" / f"{gate}-{rev}{suffix}.json"
    write_once_json(path, dump(rec))
    return rec, path


def _verdicts(answer: dict[str, Any], ids: set[str]) -> dict[str, str]:
    raw = answer.get("verdicts") or {}
    if not isinstance(raw, dict):
        raise FactoryError("verdicts는 conversationId → ADOPT|FIX|REJECT 객체여야 한다")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if key not in ids:
            raise FactoryError(f"이 묶음에 없는 대화다: {key}")
        verdict = str(value).upper()
        if verdict not in _VERDICTS:
            raise FactoryError(f"{key}: 판정은 ADOPT·FIX·REJECT 중 하나다({value!r})")
        out[str(key)] = verdict
    return out


def _notes(answer: dict[str, Any], ids: set[str]) -> dict[str, str]:
    raw = answer.get("notes") or {}
    if not isinstance(raw, dict):
        raise FactoryError("notes는 conversationId → 고칠 점 객체여야 한다")
    out: dict[str, str] = {}
    for key, value in raw.items():
        if key not in ids:
            raise FactoryError(f"이 묶음에 없는 대화의 메모다: {key}")
        text = str(value).strip()
        if text:
            out[str(key)] = text
    return out


def approve_g7a(ctx: Context, cid: str, answer: dict) -> Path:
    state = ctx.state(cid)
    gate = state.gate("G7a")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G7a가 대기 상태가 아니다({gate.status})")
    rev = gate.rev
    rev_dir = plan_mod.data_dir(ctx, cid) / rev
    cluster = str(answer.get("cluster") or "")
    if cluster not in CLUSTERS:
        raise FactoryError(f"G7a: cluster는 {', '.join(CLUSTERS)} 중 하나다")
    if writer.cluster_qa(rev_dir, cluster) is not None:
        raise FactoryError(f"G7a: {cluster}는 이 revision에서 이미 판정했다")
    decision = str(answer.get("decision") or "")
    if decision not in {"SELECT", "REQUEST_CHANGES"}:
        raise FactoryError("G7a 결정은 SELECT 또는 REQUEST_CHANGES다")
    sample_path = rev_dir / "samples" / f"{cluster}.json"
    if not sample_path.exists():
        raise FactoryError(f"G7a: {cluster} 샘플 묶음이 없다({sample_path})")
    convs = writer.load_samples(rev_dir, cluster)
    ids = {c.conversationId for c in convs}
    verdicts = _verdicts(answer, ids)
    notes = _notes(answer, ids)
    for conv in convs:
        verdicts.setdefault(conv.conversationId, "ADOPT")
    memo = " / ".join(f"{k}: {v}" for k, v in notes.items())
    if decision == "REQUEST_CHANGES" and not notes:
        raise FactoryError("G7a REQUEST_CHANGES에는 고칠 점 메모가 필요하다")

    qa = DataQa(
        characterId=cid,
        gate="G7a",
        subjectSha256=sha256_file(sample_path),
        verdicts=verdicts,  # type: ignore[arg-type]
        notes=notes,
        reviewer=str(answer.get("reviewer") or "user"),
        minutes=float(answer.get("minutes") or 0),
    )
    write_once_json(rev_dir / "qa" / f"G7a-{cluster}.json", dump(qa))
    shown = [
        sample_path,
        rev_dir / "handoffs" / f"{cluster}.json",
        rev_dir / f"gate-G7a-{cluster}.html",
    ]
    rec, record_path = _record(
        ctx,
        cid,
        gate="G7a",
        rev=rev,
        shown=[p for p in shown if p.exists()],
        decision=decision,
        reviewer=qa.reviewer,
        reasons=str(answer.get("reasons") or memo),
        minutes=qa.minutes,
        suffix=f"-{cluster}",
    )
    ctx.ledger(cid).record_human(gate="G7a", minutes=rec.minutes, ref=f"{cid}/{rev}/{cluster}")
    if decision == "REQUEST_CHANGES":
        write_once_json(rev_dir / "requests" / "g7a-changes.json", {"clusters": {cluster: memo}})
        state.set_gate(
            "G7a", "REJECTED", rev, record_path.relative_to(ctx.character_dir(cid)).as_posix()
        )
        if state.stage("s9s").status == "AWAITING_HUMAN":
            state.transition("s9s", "REJECTED", rev=rev)
        write_manifest(rev_dir)
        return rev_dir

    decided = writer.reviews(rev_dir)
    all_selected = len(decided) == len(CLUSTERS)
    state.set_gate(
        "G7a",
        "APPROVED" if all_selected else "AWAITING_HUMAN",
        rev,
        record_path.relative_to(ctx.character_dir(cid)).as_posix(),
    )
    if all_selected and state.stage("s9s").status == "AWAITING_HUMAN":
        state.transition("s9s", "APPROVED", rev=rev)
    write_manifest(rev_dir)
    return rev_dir


def approve_g7(ctx: Context, cid: str, answer: dict) -> Path:
    state = ctx.state(cid)
    gate = state.gate("G7")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G7이 대기 상태가 아니다({gate.status})")
    rev = gate.rev
    rev_dir = plan_mod.data_dir(ctx, cid) / rev
    dataset_path = rev_dir / "dataset.json"
    if not dataset_path.exists():
        raise FactoryError(f"{cid}: G7 revision에 dataset.json이 없다({rev_dir})")
    rows = [
        json.loads(ln)
        for ln in (rev_dir / "index.jsonl").read_text("utf-8").splitlines()
        if ln.strip()
    ]
    ids = {str(row["conversationId"]) for row in rows}
    decision = str(answer.get("decision") or "")
    if decision not in {"APPROVE", "REQUEST_CHANGES"}:
        raise FactoryError("G7 결정은 APPROVE 또는 REQUEST_CHANGES다")
    verdicts = _verdicts(answer, ids)
    notes = _notes(answer, ids)
    flagged = {k: v for k, v in verdicts.items() if v in {"FIX", "REJECT"}}
    if decision == "REQUEST_CHANGES" and not flagged:
        raise FactoryError("G7 REQUEST_CHANGES에는 FIX·REJECT로 표시한 대화가 필요하다")
    if decision == "APPROVE" and int(read_json(dataset_path).get("blockingFailures", 0)) > 0:
        raise FactoryError("G7: 차단 검사 실패가 남아 있어 승인할 수 없다")
    qa = DataQa(
        characterId=cid,
        gate="G7",
        subjectSha256=sha256_file(dataset_path),
        verdicts=verdicts,  # type: ignore[arg-type]
        notes=notes,
        reviewer=str(answer.get("reviewer") or "user"),
        minutes=float(answer.get("minutes") or 0),
    )
    write_once_json(rev_dir / "qa" / f"G7-{rev}.json", dump(qa))
    rec, record_path = _record(
        ctx,
        cid,
        gate="G7",
        rev=rev,
        shown=[dataset_path, rev_dir / "gate-G7.html"],
        decision=decision,
        reviewer=qa.reviewer,
        reasons=str(answer.get("reasons") or ""),
        minutes=qa.minutes,
    )
    ctx.ledger(cid).record_human(gate="G7", minutes=rec.minutes, ref=f"{cid}/{rev}")
    record_ref = record_path.relative_to(ctx.character_dir(cid)).as_posix()
    if decision == "REQUEST_CHANGES":
        write_once_json(
            rev_dir / "requests" / "g7-changes.json",
            {"conversations": {k: notes.get(k, "검토자가 다시 쓰라고 했다") for k in flagged}},
        )
        state.set_gate("G7", "REJECTED", rev, record_ref)
        if state.stage("s9").status == "AWAITING_HUMAN":
            state.transition("s9", "REJECTED", rev=rev)
    else:
        dataset = validate("dataset-rev-v2", read_json(dataset_path))
        write_once_json(
            rev_dir / "frozen.json",
            {
                "datasetRev": dataset.datasetRev,  # type: ignore[union-attr]
                "digest": dataset.digest,  # type: ignore[union-attr]
                "recordRef": record_ref,
            },
        )
        state.set_gate("G7", "APPROVED", rev, record_ref)
        if state.stage("s9").status == "AWAITING_HUMAN":
            state.transition("s9", "APPROVED", rev=rev)
    write_manifest(rev_dir)
    return rev_dir
