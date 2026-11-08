"""G8 채택 기록 (LLD §6.5·§8.9).

사람 20쌍 판정과 LLM 합의 일치율을 최종 보고서에 반영하고, 채택한 조건(model_binding ref 또는
LONG_BASE)을 gate-record와 adoption.json에 남긴다.
보고서의 정책 결정값(decision)은 자동 초안이다. 사람 채택과 함께 기록할 뿐 채택을 막거나 바꾸지
않는다(D-0078).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import dump, register, validate
from character_factory_poc.common.store import write_manifest, write_once_json
from character_factory_poc.contracts.common import ArtifactRef, Strict
from character_factory_poc.contracts.training import EvalPrereg, EvalReport, HumanPick
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import now_iso, write_gate_record
from character_factory_poc.stages.s10_eval.judge import EvalPairsDoc, llm_human_agreement
from character_factory_poc.stages.s10_eval.page import render_g8_page
from character_factory_poc.stages.s10_eval.prereg import read_prereg


@register("eval-adoption-v1")
class EvalAdoption(Strict):
    schemaVersion: Literal["eval-adoption-v1"] = "eval-adoption-v1"
    characterId: str
    preregSha256: str
    decision: Literal["SELECT"]
    adopted: str
    armId: str
    humanPicks: list[HumanPick]
    llmHumanAgreement: float
    report: ArtifactRef
    recordedAt: str
    draftDecision: str | None = Field(
        default=None, description="보고서의 정책 결정값 초안. 사람 채택과 나란히 남긴다"
    )


def load_report(rev_dir: Path) -> EvalReport:
    path = rev_dir / "report.json"
    if not path.exists():
        raise FactoryError(f"평가 보고서가 없다: {path}. cfp eval report를 먼저 실행한다")
    return validate("eval-report-v2", json.loads(path.read_text("utf-8")))  # type: ignore[return-value]


def load_improvement_tasks(char_dir: Path, report: EvalReport) -> dict[str, Any] | None:
    """보고서가 가리키는 improvement-tasks.json. 없거나 해시가 다르면 None이다."""
    ref = report.improvementTasksRef
    if ref is None:
        return None
    path = char_dir / ref.ref
    if not path.is_file():
        return None
    obj = json.loads(path.read_text("utf-8"))
    if sha256_of(obj) != ref.sha256:
        raise FactoryError(f"개선 과제 장부가 보고서 뒤에 바뀌었다: {ref.ref}")
    return obj


def load_pairs(rev_dir: Path) -> tuple[EvalPairsDoc, dict[str, Any]]:
    path = rev_dir / "pairs.json"
    if not path.exists():
        raise FactoryError(f"짝 판정이 없다: {path}")
    raw = json.loads(path.read_text("utf-8"))
    return validate("eval-pairs-v1", raw), raw  # type: ignore[return-value]


def _adopted_arm(prereg: EvalPrereg, adopted: str) -> str:
    if adopted == "LONG_BASE":
        return "LONG_BASE"
    for arm in prereg.arms:
        if arm.armId == "LONG_BASE":
            continue
        if arm.model == adopted:
            if adopted.startswith("UNBOUND:"):
                raise FactoryError("model_binding이 없는 조건은 채택할 수 없다")
            return arm.armId
    raise FactoryError(
        "G8 adopted는 LONG_BASE 또는 사전 등록의 SFT model_binding ref여야 한다: " + adopted
    )


def _picks(answer: dict[str, Any], expected: set[str]) -> list[HumanPick]:
    raw = answer.get("humanPicks")
    if not isinstance(raw, list):
        raise FactoryError("G8 humanPicks는 [{pairId, pick}] 목록이다")
    picks: list[HumanPick] = []
    ids: set[str] = set()
    for row in raw:
        if not isinstance(row, dict):
            raise FactoryError("G8 humanPicks의 각 항목은 객체다")
        pick = HumanPick(pairId=str(row.get("pairId", "")), pick=row.get("pick"))
        if pick.pairId in ids:
            raise FactoryError(f"G8 humanPicks에 같은 pairId가 두 번 있다: {pick.pairId}")
        ids.add(pick.pairId)
        picks.append(pick)
    if ids != expected:
        missing = sorted(expected - ids)
        extra = sorted(ids - expected)
        raise FactoryError(
            f"G8 humanPicks는 블라인드 표본 전체를 골라야 한다(빠짐 {missing}, 모르는 쌍 {extra})"
        )
    return picks


def approve_g8(ctx: Context, cid: str, answer: dict[str, Any]) -> Path:
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    gate = state.gate("G8")
    if gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError(f"{cid}: G8이 대기 상태가 아니다({gate.status})")
    from character_factory_poc.stages.s10_eval.prompt_only import (
        PROMPT_ONLY_FILE,
        approve_prompt_only,
        is_prompt_only,
    )

    if is_prompt_only(char_dir / "s10-eval" / gate.rev):
        from character_factory_poc.stages.s10_eval.twin import SCHEMA, approve_twin

        folder = char_dir / "s10-eval" / gate.rev
        doc = json.loads((folder / PROMPT_ONLY_FILE).read_text("utf-8"))
        if doc.get("schemaVersion") == SCHEMA:
            return approve_twin(ctx, cid, folder, doc, answer)
        # K-0038: 학습 결과 없이 연 G8. 평가 보고서 대신 '긴 프롬프트로 진행' 결정을 받는다.
        return approve_prompt_only(ctx, cid, char_dir / "s10-eval" / gate.rev, answer)
    if answer.get("decision") != "SELECT":
        raise FactoryError("G8 결정은 SELECT다(채택 조건을 고른다)")
    rev_dir = char_dir / "s10-eval" / gate.rev
    from character_factory_poc.pipeline.graph import SOURCE
    from character_factory_poc.pipeline.origin import read_origin
    from character_factory_poc.stages.s10_eval import blind

    is_twin = read_origin(char_dir) == SOURCE
    if is_twin and not (rev_dir / blind.BASE).is_file():
        raise FactoryError("트윈 TRAIN G8에는 비교 실행 보고가 필요하다")
    if is_twin:
        blind.verify_evidence(rev_dir)
    prereg, digest = read_prereg(rev_dir)
    report = load_report(rev_dir)
    pairs, pairs_raw = load_pairs(rev_dir)
    if report.preregSha256 != digest or pairs.preregSha256 != digest:
        raise FactoryError("G8 보고서·판정이 사전 등록과 다른 revision을 가리킨다")

    adopted = str(answer.get("adopted", ""))
    arm_id = _adopted_arm(prereg, adopted)
    picks = _picks(answer, set(pairs.humanPairIds))
    agreement, matched, total = llm_human_agreement(picks, pairs_raw["pairs"])
    tasks = load_improvement_tasks(char_dir, report)
    recommendation = (
        report.recommendation
        + f" G8 사람 판정 {total}쌍 중 LLM 합의와 {matched}쌍 일치({agreement:.3f})."
    )
    if report.decision is not None:
        recommendation += f" 정책 결정 초안 {report.decision}, 사람 채택 {arm_id}."
    final = report.model_copy(
        update={
            "humanPicks": picks,
            "llmHumanAgreement": agreement,
            "recommendation": recommendation,
        }
    )
    final = validate("eval-report-v2", dump(final))  # type: ignore[assignment]
    write_once_json(rev_dir / "report-final.json", dump(final))
    page = render_g8_page(
        subject_id=cid,
        rev=gate.rev,
        prereg=prereg,
        report=final,
        pairs=pairs_raw,
        final=True,
        adopted=adopted,
        improvement_tasks=tasks,
    )
    if is_twin:
        page = blind.decorate(page, rev_dir)
    (rev_dir / "gate-G8.html").write_text(page, encoding="utf-8")
    report_ref = ArtifactRef(
        ref=(rev_dir / "report-final.json").relative_to(char_dir).as_posix(),
        sha256=sha256_of(dump(final)),
    )
    adoption = validate(
        "eval-adoption-v1",
        dump(
            EvalAdoption(
                characterId=cid,
                preregSha256=digest,
                decision="SELECT",
                adopted=adopted,
                armId=arm_id,
                humanPicks=picks,
                llmHumanAgreement=agreement,
                report=report_ref,
                recordedAt=now_iso(),
                draftDecision=report.decision,
            )
        ),
    )
    write_once_json(rev_dir / "adoption.json", dump(adoption))
    write_manifest(rev_dir)
    rec = write_gate_record(
        char_dir,
        state,
        gate="G8",
        rev=gate.rev,
        stage_id="s10",
        shown=[
            rev_dir / "prereg.json",
            rev_dir / "report-final.json",
            rev_dir / "gate-G8.html",
            *(blind.evidence(rev_dir) if is_twin else []),
        ],
        decision="SELECT",
        reviewer=str(answer.get("reviewer", "user")),
        reasons=str(answer.get("reasons", "")),
        selections=[adopted],
        minutes=float(answer.get("minutes", 0) or 0),
    )
    ctx.ledger(cid).record_human(gate="G8", minutes=rec.minutes, ref=f"{cid}/{gate.rev}")
    return rev_dir
