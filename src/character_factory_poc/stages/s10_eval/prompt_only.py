"""학습 없이 긴 프롬프트 경로로 가는 G8 결정 (K-0038, D-0048).

학습 결과(model_binding)가 없으면 평가 대신 이 결정을 G8에 연다. 사람이 긴 프롬프트(LONG_BASE)를
고르면 SFT 평가 없이 패키지(S11)로 간다. "학습을 기다린다"(REJECT)를 고르면 학습 결과가 생길 때까지
평가 단계가 기다린다. 데이터셋(G7)과 학습 계획(dry run)은 그대로 패키지에 남는다.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import dump, register, validate
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.contracts.common import ArtifactRef, Strict
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import now_iso, write_gate_record

PROMPT_ONLY_FILE = "prompt-only.json"
ADOPTED = "LONG_BASE"


class TrainingPlanRef(Strict):
    provider: str
    status: str
    dryRun: bool
    estimateUsd: float | None = None
    ref: ArtifactRef


@register("eval-prompt-only-v1")
class PromptOnlyDecision(Strict):
    """G8에 올리는 '학습 없이 진행' 결정 자료."""

    schemaVersion: Literal["eval-prompt-only-v1"] = "eval-prompt-only-v1"
    characterId: str
    reason: str
    datasetRev: str | None = None
    trainingRuns: list[TrainingPlanRef] = Field(default_factory=list)
    longPrompt: ArtifactRef
    adoptOptions: list[str] = Field(default_factory=lambda: [ADOPTED])
    createdAt: str


def is_prompt_only(rev_dir: Path) -> bool:
    return (rev_dir / PROMPT_ONLY_FILE).is_file()


def _training_runs(ctx: Context, cid: str) -> list[TrainingPlanRef]:
    from character_factory_poc.stages.s10_train.io import latest_rev

    char_dir = ctx.character_dir(cid)
    rev_dir = latest_rev(ctx, cid)
    if rev_dir is None:
        return []
    out = []
    for path in sorted(rev_dir.glob("*/training-run.json")):
        run = json.loads(path.read_text("utf-8"))
        out.append(
            TrainingPlanRef(
                provider=str(run.get("provider", path.parent.name)),
                status=str(run.get("status", "")),
                dryRun=bool(run.get("dryRun", True)),
                estimateUsd=(run.get("estimate") or {}).get("usd"),
                ref=ArtifactRef(
                    ref=path.relative_to(char_dir).as_posix(), sha256=sha256_file(path)
                ),
            )
        )
    return out


def _dataset_rev(ctx: Context, cid: str) -> str | None:
    gate = ctx.state(cid).gate("G7")
    return gate.rev if gate.status == "APPROVED" else None


def _page(cid: str, rev: str, doc: PromptOnlyDecision, final: str = "") -> str:
    e = html.escape

    def usd(value: float | None) -> str:
        return "" if value is None else "$" + format(value, ".2f")

    rows = "".join(
        f"<tr><td>{e(r.provider)}</td><td>{e(r.status)}</td>"
        f"<td>{'계획만(dry run)' if r.dryRun else '실행'}</td>"
        f"<td>{usd(r.estimateUsd)}</td></tr>"
        for r in doc.trainingRuns
    )
    done = f"<p><b>결정:</b> {e(final)}</p>" if final else ""
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        "<title>G8 학습 없이 진행</title><style>body{font-family:-apple-system,system-ui,"
        "sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;line-height:1.55}"
        "table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:.3rem .6rem}</style>"
        f"</head><body><h1>G8 학습 없이 진행</h1><p>{e(cid)} · {e(rev)}</p>"
        f"<p>{e(doc.reason)}</p><h2>학습 계획</h2><table><tr><th>공급자</th><th>상태</th>"
        f"<th>실행</th><th>추정 비용</th></tr>{rows}</table>"
        f"<p>데이터셋: {e(doc.datasetRev or '없음')} · 긴 프롬프트: "
        f"<code>{e(doc.longPrompt.ref)}</code></p>{done}"
        '<p>답 형식: {"decision": "SELECT", "adopted": "LONG_BASE"} 또는 '
        '{"decision": "REJECT"}(학습을 기다린다)</p></body></html>'
    )


def open_prompt_only(ctx: Context, cid: str) -> Path:
    """학습 결과가 없을 때 G8을 '학습 없이 진행' 결정으로 연다."""
    from character_factory_poc.stages.s10_eval.prereg import _prompt_pair

    state = ctx.state(cid)
    state.require_deps("s10")
    char_dir = ctx.character_dir(cid)
    st = state.stage("s10")
    if st.status == "AWAITING_HUMAN" and st.currentRev:
        rev_dir = char_dir / "s10-eval" / st.currentRev
        if is_prompt_only(rev_dir):
            return rev_dir
    _, _, long_path, _ = _prompt_pair(ctx, cid)
    rev = next_rev(char_dir / "s10-eval", "ev")
    rev_dir = char_dir / "s10-eval" / rev
    runs = _training_runs(ctx, cid)
    planned = ", ".join(f"{r.provider}({r.status})" for r in runs) or "학습 계획 없음"
    doc = PromptOnlyDecision(
        characterId=cid,
        reason=(
            "학습 결과(model_binding)가 없어 SFT 조건을 평가할 수 없다. "
            f"학습 상태: {planned}. 긴 프롬프트로 패키지까지 갈지, 학습을 기다릴지 정한다."
        ),
        datasetRev=_dataset_rev(ctx, cid),
        trainingRuns=runs,
        longPrompt=ArtifactRef(
            ref=long_path.relative_to(char_dir).as_posix(), sha256=sha256_file(long_path)
        ),
        createdAt=now_iso(),
    )
    state.transition("s10", "RUNNING", rev=rev)
    write_once_json(rev_dir / PROMPT_ONLY_FILE, dump(doc))
    (rev_dir / "gate-G8.html").write_text(_page(cid, rev, doc), encoding="utf-8")
    write_manifest(rev_dir)
    state.transition("s10", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G8", "AWAITING_HUMAN", rev, None)
    return rev_dir


def approve_prompt_only(ctx: Context, cid: str, rev_dir: Path, answer: dict[str, Any]) -> Path:
    """SELECT LONG_BASE면 긴 프롬프트로 진행, REJECT면 학습을 기다린다."""
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    rev = rev_dir.name
    doc: PromptOnlyDecision = validate(  # type: ignore[assignment]
        "eval-prompt-only-v1", json.loads((rev_dir / PROMPT_ONLY_FILE).read_text("utf-8"))
    )
    decision = str(answer.get("decision") or "")
    if decision == "SELECT":
        adopted = str(answer.get("adopted") or ADOPTED)
        if adopted not in doc.adoptOptions:
            raise FactoryError(f"G8(학습 없이 진행)에서 고를 수 있는 것은 {doc.adoptOptions}다")
        selections = [adopted]
        summary = f"긴 프롬프트({adopted})로 진행"
    elif decision == "REJECT":
        selections = []
        summary = "학습을 기다린다"
    else:
        raise FactoryError("G8(학습 없이 진행) 결정은 SELECT(긴 프롬프트) 또는 REJECT(학습 대기)다")
    (rev_dir / "gate-G8.html").write_text(_page(cid, rev, doc, summary), encoding="utf-8")
    rec = write_gate_record(
        char_dir,
        state,
        gate="G8",
        rev=rev,
        stage_id="s10",
        shown=[rev_dir / PROMPT_ONLY_FILE, rev_dir / "gate-G8.html"],
        decision=decision,
        reviewer=str(answer.get("reviewer", "user")),
        reasons=str(answer.get("reasons", "")) or summary,
        selections=selections,
        minutes=float(answer.get("minutes", 0) or 0),
    )
    ctx.ledger(cid).record_human(gate="G8", minutes=rec.minutes, ref=f"{cid}/{rev}")
    return rev_dir
