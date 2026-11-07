"""S10 평가 보고서 `eval-report-v2`와 G8 페이지 (LLD §5.15·§8.9, D-0078).

지표·기준 결과·LLM 짝 판정·사람 블라인드 표본을 모아 보고서를 쓴다. 기준 미달이어도 보고서는
나오고 채택은 G8에서 사람이 정한다. 정책(qlora-authored-v1) 축별 커버리지, 결정값 초안, 개선 과제
장부(improvement-tasks.json)를 함께 쓴다(scorecard.py). 응답 누락·사전 등록 해시 불일치면
보고서 대신 integrity-blocked.json에 BLOCKED_INTEGRITY를 남기고 멈춘다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import write_manifest, write_once_json
from character_factory_poc.contracts.common import ArtifactRef
from character_factory_poc.contracts.training import (
    ArmId,
    CriterionResult,
    EvalPrereg,
    EvalReport,
    MetricValue,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s10_eval import scorecard as sc
from character_factory_poc.stages.s10_eval.judge import EvalPairsDoc, run_judge
from character_factory_poc.stages.s10_eval.metrics import (
    arm_metrics,
    criteria_overall,
    evaluate_criteria,
)
from character_factory_poc.stages.s10_eval.page import render_g8_page
from character_factory_poc.stages.s10_eval.prereg import (
    PreregMismatchError,
    current_rev,
    load_prereg,
)
from character_factory_poc.stages.s10_eval.run import load_runs, load_set_docs

SFT_ARMS: tuple[ArmId, ...] = ("SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT")
INTEGRITY_FILE = "integrity-blocked.json"


class IntegrityBlockedError(FactoryError):
    """응답 누락·사전 등록 해시 불일치. 보고서를 만들지 않는다(BLOCKED_INTEGRITY)."""


def _write_integrity_block(rev_dir: Path, cid: str, problems: list[str]) -> Path:
    """무결성 차단 기록. 진단용 파생 파일이라 같은 revision에서 다시 쓸 수 있다."""
    path = rev_dir / INTEGRITY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "characterId": cid,
        "evalRev": rev_dir.name,
        "decision": "BLOCKED_INTEGRITY",
        "decisionReasons": [f"무결성: {p}" for p in problems] + [sc.DRAFT_NOTE],
    }
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _block(rev_dir: Path, cid: str, problems: list[str]) -> IntegrityBlockedError:
    path = _write_integrity_block(rev_dir, cid, problems)
    shown = "; ".join(problems[:5]) + (f" 외 {len(problems) - 5}건" if len(problems) > 5 else "")
    return IntegrityBlockedError(f"BLOCKED_INTEGRITY: {shown}. 보고서를 만들지 않았다. 기록 {path}")


def _load_pairs(
    rev_dir: Path, prereg: EvalPrereg, digest: str, char_dir: Path
) -> tuple[EvalPairsDoc, dict[str, Any]]:
    path = rev_dir / "pairs.json"
    if path.exists():
        obj = json.loads(path.read_text("utf-8"))
        doc = validate("eval-pairs-v1", obj)
        if doc.preregSha256 != digest:
            raise FactoryError(
                "pairs.json의 사전 등록 해시가 다르다. 새 ev revision에서 다시 판정한다"
            )
        return doc, obj  # type: ignore[return-value]
    raise FactoryError(f"짝 판정이 없다: {path}. cfp eval judge를 먼저 실행한다")


def _judge(ctx: Context, cid: str, prereg: EvalPrereg, budget):
    judge_cfg = ctx.config.provider("judge")
    if judge_cfg.family() != prereg.judge.family:
        raise FactoryError(
            "사전 등록한 판정 모델 계열과 설정이 다르다: "
            f"등록 {prereg.judge.family}, 설정 {judge_cfg.family()}"
        )
    if prereg.judge.model and judge_cfg.model and prereg.judge.model != judge_cfg.model:
        raise FactoryError(
            "사전 등록한 판정 모델과 설정이 다르다: "
            f"등록 {prereg.judge.model}, 설정 {judge_cfg.model}"
        )
    return ctx.judge_model(cid, budget)


def _recommend(
    prereg: EvalPrereg,
    metrics: list[MetricValue],
    results: list[CriterionResult],
) -> str:
    overall = criteria_overall(prereg, results)
    by_key = {(m.armId, m.metric): m.value for m in metrics}
    sft_arms = [a.armId for a in prereg.arms if a.armId in SFT_ARMS]

    def row(arm: str) -> str:
        return (
            f"{arm}: 반복 {by_key[(arm, 'repeat_rate_101_200')]:.3f}, "
            f"기억 {by_key[(arm, 'memory_recall_200')]:.3f}, "
            f"사과 {by_key[(arm, 'apology_recovery')]:.3f}"
        )

    winners = [arm for arm in sft_arms if all(overall.get(c.id, False) for c in prereg.criteria)]
    if winners:
        best = sorted(
            winners,
            key=lambda a: (
                by_key[(a, "repeat_rate_101_200")],
                -by_key[(a, "memory_recall_200")],
                -by_key[(a, "apology_recovery")],
            ),
        )[0]
        return f"{best}가 G8 기본 기준을 모두 넘었다({row(best)}). 채택은 G8에서 사람이 정한다."
    failed = [c.id for c in prereg.criteria if not overall.get(c.id, False)]
    detail = "; ".join(row(a) for a in sft_arms)
    return (
        "SFT 조건 가운데 G8 기본 기준을 모두 넘은 조건이 없다. 미달 기준: "
        f"{', '.join(failed)}. {detail}. 기준 미달이어도 보고서는 유효하며 채택은 사람이 정한다."
    )


def _run_refs(char_dir: Path, rev_dir: Path) -> list[ArtifactRef]:
    refs: list[ArtifactRef] = []
    for path in sorted((rev_dir / "runs").glob("*.json")):
        run = validate("eval-run-v1", json.loads(path.read_text("utf-8")))
        refs.append(
            ArtifactRef(
                ref=path.relative_to(char_dir).as_posix(),
                sha256=sha256_of(dump(run)),
            )
        )
    return refs


def build_report(ctx: Context, cid: str) -> Path:
    """응답·판정을 읽어 보고서와 G8 페이지를 쓰고 s10을 사람 대기로 둔다."""
    if ctx.state(cid).gate("G8").status == "APPROVED":
        raise FactoryError("G8이 이미 승인됐다. 다시 평가하려면 새 ev revision을 등록한다")
    char_dir = ctx.character_dir(cid)
    try:
        prereg, digest, rev_dir = load_prereg(ctx, cid)
    except PreregMismatchError as exc:
        _write_integrity_block(
            char_dir / "s10-eval" / current_rev(ctx, cid), cid, [str(exc).splitlines()[0]]
        )
        raise
    if not (rev_dir / "pairs.json").exists():
        raise FactoryError(
            f"짝 판정이 없다: {rev_dir / 'pairs.json'}. cfp eval judge를 먼저 실행한다"
        )
    try:
        set_docs = load_set_docs(prereg, char_dir)
    except FactoryError as exc:
        raise _block(rev_dir, cid, [str(exc).splitlines()[0]]) from exc
    problems = sc.integrity_problems(prereg, digest, rev_dir, set_docs)
    if problems:
        raise _block(rev_dir, cid, problems)
    runs = load_runs(prereg, rev_dir)
    pairs_doc, pairs_raw = _load_pairs(rev_dir, prereg, digest, char_dir)
    budget = ctx.budget()
    # 짝 판정은 pairs.json에 이미 있다. 여기서는 지표 판정만 부른다.
    judge_calls = 12 * len(prereg.arms) + 6 * len(prereg.arms)
    budget.check_plan([CallPlan("s10", "지표 판정과 보고서", judge_calls)])
    judge = _judge(ctx, cid, prereg, budget)

    metrics = arm_metrics(prereg, runs, set_docs, judge, cid=cid)
    criteria = evaluate_criteria(prereg, metrics)
    card = sc.build_scorecard(
        cid=cid,
        rev=rev_dir.name,
        prereg=prereg,
        digest=digest,
        metrics=metrics,
        runs=runs,
        pairs=pairs_raw["pairs"],
        set_docs=set_docs,
        char_dir=char_dir,
    )
    tasks_obj = dump(validate("improvement-tasks-v1", dump(card.tasks_doc)))
    tasks_path = rev_dir / "improvement-tasks.json"
    write_once_json(tasks_path, tasks_obj)
    report = validate(
        "eval-report-v2",
        dump(
            EvalReport(
                characterId=cid,
                preregSha256=digest,
                runRefs=_run_refs(char_dir, rev_dir),
                metrics=metrics,
                criteriaResults=criteria,
                llmPairs=[
                    {
                        "pairId": p["pairId"],
                        "armA": p["armA"],
                        "armB": p["armB"],
                        "forward": p["forward"],
                        "reverse": p["reverse"],
                        "consensus": p["consensus"],
                    }
                    for p in pairs_raw["pairs"]
                ],
                recommendation=_recommend(prereg, metrics, criteria),
                decision=card.draft.decision,  # type: ignore[arg-type]
                decisionReasons=card.draft.reasons,
                suiteCoverage=[dump(s) for s in card.coverage],
                criticalErrorChecks=[dump(c) for c in card.critical],
                checkpointSelection=dump(card.selection) if card.selection else None,
                improvementTasksRef=ArtifactRef(
                    ref=tasks_path.relative_to(char_dir).as_posix(),
                    sha256=sha256_of(tasks_obj),
                ),
            )
        ),
    )
    write_once_json(rev_dir / "report.json", dump(report))
    page = render_g8_page(
        subject_id=cid,
        rev=rev_dir.name,
        prereg=prereg,
        report=report,
        pairs=pairs_raw,
        improvement_tasks=tasks_obj,
    )
    # 페이지는 파생 뷰다. 판정 뒤 최종 보고서로 다시 그릴 수 있게 덮어쓴다.
    (rev_dir / "gate-G8.html").write_text(page, encoding="utf-8")
    write_manifest(rev_dir)
    state = ctx.state(cid)
    if state.stage("s10").status == "RUNNING":
        state.transition("s10", "AWAITING_HUMAN", rev=rev_dir.name)
    state.set_gate("G8", "AWAITING_HUMAN", rev_dir.name, None)
    return rev_dir


def judge_and_report(ctx: Context, cid: str) -> Path:
    """짝 판정이 없으면 만들고 보고서까지 쓴다(명령 하나로 끝내는 경로)."""
    _, _, rev_dir = load_prereg(ctx, cid)
    if not (rev_dir / "pairs.json").exists():
        run_judge(ctx, cid)
    return build_report(ctx, cid)
