"""S10 평가 보고서 `eval-report-v2`와 G8 페이지 (LLD §5.15·§8.9).

지표·기준 결과·LLM 짝 판정·사람 블라인드 표본을 모아 보고서를 쓴다. 기준 미달이어도 보고서는
나오고 채택은 G8에서 사람이 정한다.
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
from character_factory_poc.stages.s10_eval.judge import EvalPairsDoc, run_judge
from character_factory_poc.stages.s10_eval.metrics import (
    arm_metrics,
    criteria_overall,
    evaluate_criteria,
)
from character_factory_poc.stages.s10_eval.page import render_g8_page
from character_factory_poc.stages.s10_eval.prereg import load_prereg
from character_factory_poc.stages.s10_eval.run import load_runs, load_set_docs

SFT_ARMS: tuple[ArmId, ...] = ("SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT")


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

    def row(arm: str) -> str:
        return (
            f"{arm}: 반복 {by_key[(arm, 'repeat_rate_101_200')]:.3f}, "
            f"기억 {by_key[(arm, 'memory_recall_200')]:.3f}, "
            f"사과 {by_key[(arm, 'apology_recovery')]:.3f}"
        )

    winners = [arm for arm in SFT_ARMS if all(overall.get(c.id, False) for c in prereg.criteria)]
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
    detail = "; ".join(row(a) for a in SFT_ARMS)
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
    prereg, digest, rev_dir = load_prereg(ctx, cid)
    char_dir = ctx.character_dir(cid)
    runs = load_runs(prereg, rev_dir)
    set_docs = load_set_docs(prereg, char_dir)
    pairs_doc, pairs_raw = _load_pairs(rev_dir, prereg, digest, char_dir)
    budget = ctx.budget()
    # 짝 판정은 pairs.json에 이미 있다. 여기서는 지표 판정만 부른다.
    judge_calls = 12 * len(prereg.arms) + 6 * len(prereg.arms)
    budget.check_plan([CallPlan("s10", "지표 판정과 보고서", judge_calls)])
    judge = _judge(ctx, cid, prereg, budget)

    metrics = arm_metrics(prereg, runs, set_docs, judge, cid=cid)
    criteria = evaluate_criteria(prereg, metrics)
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
