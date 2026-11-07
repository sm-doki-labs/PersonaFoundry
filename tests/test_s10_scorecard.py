"""S10 정책 점수표·결정 초안·개선 과제 시험 (D-0078). 가짜 자료만 쓰고 네트워크를 쓰지 않는다."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

import character_factory_poc.contracts  # noqa: F401  계약 등록
from character_factory_poc.common import qlora_policy as qp
from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts.training import EvalPrereg, EvalRun, MetricValue
from character_factory_poc.stages.s10_eval import judge as eval_judge
from character_factory_poc.stages.s10_eval import prereg as eval_prereg
from character_factory_poc.stages.s10_eval import report as eval_report
from character_factory_poc.stages.s10_eval import scorecard as sc
from character_factory_poc.stages.s10_eval.approve import approve_g8
from character_factory_poc.stages.s10_eval.page import render_g8_page
from tests.test_s10_eval import _fake_models, _prepared, _synthetic_runs

GEMMA = "SHORT_GEMMA_SFT"
BASE = "LONG_BASE"
NOT_MEASURED_SUITES = {"canon_fact", "self_schedule", "register_voice", "distinctiveness"}


def _prereg() -> EvalPrereg:
    ref = {"ref": "s8-prompts/pv1/short.md", "sha256": "a" * 64}
    return validate(  # type: ignore[return-value]
        "eval-prereg-v2",
        {
            "characterId": "c1",
            "personaVersion": "pv1",
            "arms": [
                {"armId": BASE, "promptRef": ref, "model": "base-model"},
                {"armId": GEMMA, "promptRef": ref, "model": "/runs/adapter/epoch-2"},
            ],
            "sets": [
                {
                    "setId": sid,
                    "ref": {"ref": f"s10-eval/ev1/sets/{sid}.json", "sha256": "b" * 64},
                    "seeds": [1],
                    "perTurnSeed": True,
                }
                for sid in ("OE", "SE", "APOLOGY", "LONG200")
            ],
            "judge": {"model": "anthropic/claude-opus-5-5", "family": "anthropic"},
            "criteria": [dump(c) for c in eval_prereg.default_criteria()],
            "frozenAt": "2026-11-02T00:00:00Z",
        },
    )


def _metrics(repeat=(0, 400), memory=(12, 12), apology=(6, 6)) -> list[MetricValue]:
    out = []
    for arm in (BASE, GEMMA):
        for name, (num, den), word in (
            ("repeat_rate_101_200", repeat, "말풍선 중복"),
            ("memory_recall_200", memory, "정답"),
            ("apology_recovery", apology, "회복"),
        ):
            n, d = (num, den) if arm == GEMMA else ((0, den) if "repeat" in name else (den, den))
            out.append(
                MetricValue(armId=arm, metric=name, value=round(n / d, 3), detail=f"{n}/{d} {word}")
            )
    return out


def _pairs(consensus: list[str], set_id: str = "SE", item: str = "se01") -> list[dict[str, Any]]:
    return [
        {
            "pairId": f"p{i:03d}",
            "setId": set_id,
            "itemId": item,
            "armA": BASE,
            "armB": GEMMA,
            "consensus": c,
        }
        for i, c in enumerate(consensus, 1)
    ]


def _runs(reply: str = "평범한 답이야") -> dict[tuple[str, str], EvalRun]:
    out = {}
    for arm in (BASE, GEMMA):
        out[(arm, "SE")] = validate(
            "eval-run-v1",
            {
                "characterId": "c1",
                "preregSha256": "d" * 64,
                "armId": arm,
                "setId": "SE",
                "model": "m",
                "items": [
                    {
                        "itemId": "se01",
                        "turns": [{"user": "u", "reply": reply if arm == GEMMA else "답"}],
                    }
                ],
            },
        )
    return out  # type: ignore[return-value]


_SET_DOCS = {"OE": {"items": [{"itemId": "oe07", "topic": "ownership"}]}}


def _card(
    *,
    metrics: list[MetricValue] | None = None,
    pairs: list[dict[str, Any]] | None = None,
    runs: dict | None = None,
    integrity: list[str] | None = None,
    char_dir: Path | None = None,
    policy: dict[str, Any] | None = None,
) -> sc.Scorecard:
    return sc.build_scorecard(
        cid="c1",
        rev="ev1",
        prereg=_prereg(),
        digest="d" * 64,
        metrics=metrics if metrics is not None else _metrics(),
        runs=runs if runs is not None else _runs(),
        pairs=pairs if pairs is not None else _pairs(["B"] * 6 + ["A"] * 2),
        set_docs=_SET_DOCS,
        char_dir=char_dir,
        integrity=integrity,
        policy=policy,
    )


# ---- 결정값 경로 ------------------------------------------------------------------------------


def test_integrity_problem_blocks_before_quality() -> None:
    card = _card(
        integrity=["응답 누락: SHORT_GEMMA_SFT-SE.json이 없다"], metrics=_metrics((90, 100))
    )
    assert card.draft.decision == "BLOCKED_INTEGRITY"
    assert any("응답 누락" in r for r in card.draft.reasons)
    assert card.tasks_doc.draftDecision == "BLOCKED_INTEGRITY"


def test_gate_failure_blocks_quality_and_maps_repetition() -> None:
    assert _card(metrics=_metrics(repeat=(20, 400))).draft.decision != "BLOCKED_QUALITY"  # 5% 경계
    card = _card(metrics=_metrics(repeat=(40, 400)))
    assert card.draft.decision == "BLOCKED_QUALITY"
    assert any("101~200턴 말풍선 반복 40/400" in r for r in card.draft.reasons)
    task = next(t for t in card.tasks_doc.tasks if t.trigger == "gate:repeat_rate_101_200")
    assert task.failureType == "long_recap_repetition"
    assert task.mapping.confidence == "exact" and task.mapping.matchedTerms
    entry = next(
        e for e in qp.failure_types(qp.load_policy()) if e["id"] == "long_recap_repetition"
    )
    assert task.firstIntervention.text == entry["firstIntervention"]
    assert task.firstIntervention.kind == "data"
    ev = task.evidence[0]
    assert (ev.armId, ev.numerator, ev.denominator, ev.comparator) == (GEMMA, 40, 400, "<=")
    assert ev.threshold is not None and ev.threshold.value == 0.05


def test_empty_reply_is_critical_error_and_maps_to_policy_type() -> None:
    card = _card(runs=_runs(reply="  "))
    assert card.draft.decision == "BLOCKED_QUALITY"
    check = next(c for c in card.critical if c.errorId.startswith("repetition_loop"))
    gemma = next(m for m in check.measures if m.armId == GEMMA)
    assert (gemma.numerator, gemma.denominator, gemma.passed) == (1, 1, False)
    assert gemma.threshold is not None and gemma.threshold.startingValue is True
    task = next(t for t in card.tasks_doc.tasks if t.trigger.startswith("critical:"))
    assert task.failureType == "empty_or_loop_output" and task.mapping.confidence == "exact"
    assert task.firstIntervention.kind == "eval"


def test_inconclusive_when_consensus_below_half() -> None:
    card = _card(pairs=_pairs(["SPLIT"] * 6 + ["B"] * 4))
    assert card.draft.decision == "INCONCLUSIVE"
    tally = card.draft.versus_base[GEMMA]
    assert (tally.winsB, tally.split, tally.total) == (4, 6, 10)


def test_split_is_not_counted_as_win() -> None:
    # SPLIT 3개를 SFT 승으로 셌다면 SFT 4 : 2로 앞섰을 것이다. 빼면 LONG_BASE 2 : 1이다.
    card = _card(pairs=_pairs(["SPLIT"] * 3 + ["A", "A", "B"]))
    assert card.draft.decision == "KEEP_INCUMBENT"
    tally = card.draft.versus_base[GEMMA]
    assert (tally.winsA, tally.winsB, tally.split, tally.consensus) == (2, 1, 3, 3)


def test_reverse_orientation_pairs_are_flipped() -> None:
    pairs = _pairs(["A"] * 4)
    for p in pairs:
        p["armA"], p["armB"] = GEMMA, BASE
    card = _card(pairs=pairs)
    assert card.draft.decision == "DEVELOPMENT_RECOMMENDED"
    assert card.draft.versus_base[GEMMA].winsB == 4


def test_development_recommended_never_auto_accepts() -> None:
    card = _card()
    assert card.draft.decision == "DEVELOPMENT_RECOMMENDED"
    assert card.draft.candidate == GEMMA
    assert card.draft.decision not in sc.AUTO_FORBIDDEN
    assert sc.DRAFT_NOTE in card.draft.reasons
    assert card.tasks_doc.tasks == []


def test_equal_wins_are_inconclusive() -> None:
    assert _card(pairs=_pairs(["A", "B", "TIE", "TIE"])).draft.decision == "INCONCLUSIVE"


# ---- 축별 커버리지 ------------------------------------------------------------------------------


def test_coverage_shows_unmeasured_suites_and_starting_values() -> None:
    pairs = _pairs(["B"] * 4) + _pairs(["B", "B"], set_id="OE", item="oe07")
    card = _card(pairs=pairs)
    by_id = {s.suiteId: s for s in card.coverage}
    policy_ids = [s["id"] for s in qp.suites(qp.load_policy())]
    assert list(by_id) == policy_ids and len(policy_ids) == 8
    for sid in NOT_MEASURED_SUITES | {"history_accuracy"}:
        suite = by_id[sid]
        if sid in NOT_MEASURED_SUITES:
            assert suite.coverage == "NOT_MEASURED"
            assert all(c.state == "not_measured" and c.by for c in suite.components)
            assert suite.measures == [] and suite.pairs == []
    # OE 주인 문항만 짝 판정이 있으므로 history_accuracy는 아무것도 재지 못했다.
    assert by_id["history_accuracy"].coverage == "NOT_MEASURED"
    owner = by_id["owner_separation"]
    assert owner.coverage == "PARTIAL"
    assert owner.pairs[0].winsB == 2 and owner.pairs[0].setIds == ["OE"]
    assert {c.state for c in owner.components} == {"relative", "not_measured"}
    long = by_id["long_repetition"]
    assert long.coverage == "PARTIAL"
    assert {(m.armId, m.metric) for m in long.measures} == {
        (arm, metric)
        for arm in (BASE, GEMMA)
        for metric in ("repeat_rate_101_200", "memory_recall_200")
    }
    memory = next(m for m in long.measures if m.armId == GEMMA and m.metric == "memory_recall_200")
    assert (memory.numerator, memory.denominator, memory.passed) == (12, 12, True)
    assert "84" in long.note  # 정책 계획 40+16+28과 비교한다
    hurt = by_id["hurt_recovery"]
    assert hurt.coverage == "PARTIAL"
    apology = next(m for m in hurt.measures if m.armId == GEMMA)
    assert apology.threshold is not None and apology.threshold.value == 4
    assert "6" in apology.threshold.note
    assert by_id["canon_fact"].plan["items"].startingValue is True  # source=proposal
    assert by_id["owner_separation"].plan["items"].startingValue is False


def test_apology_gate_uses_policy_count() -> None:
    card = _card(metrics=_metrics(apology=(3, 6)))
    assert card.draft.decision == "BLOCKED_QUALITY"
    task = next(t for t in card.tasks_doc.tasks if t.trigger == "gate:apology_recovery")
    assert task.failureType == "own_apology_without_repair"
    assert task.mapping.confidence == "exact"
    assert _card(metrics=_metrics(apology=(4, 6))).draft.decision == "DEVELOPMENT_RECOMMENDED"


# ---- 개선 과제 매핑 ----------------------------------------------------------------------------


def test_improvement_tasks_mapping_and_ledger() -> None:
    pairs = _pairs(["B"] * 4) + _pairs(["A", "A", "A"], set_id="OE", item="oe07")
    card = _card(metrics=_metrics(memory=(9, 12)), pairs=pairs)
    doc = validate("improvement-tasks-v1", dump(card.tasks_doc))
    by_trigger = {t.trigger: t for t in doc.tasks}  # type: ignore[attr-defined]
    memory = by_trigger["gate:memory_recall_200"]
    assert memory.failureType == "user_fact_fabrication"
    assert memory.mapping.confidence == "approximate"
    assert "refused_fact_hedging" in memory.mapping.alternatives
    assert memory.evidence[0].numerator == 9 and memory.evidence[0].denominator == 12
    owner = by_trigger[f"pairs:owner_separation@{GEMMA}"]
    assert owner.failureType == "owner_confusion"
    assert "llm_only" in owner.evidence[0].detail
    assert doc.reviewMode == "llm_only"  # type: ignore[attr-defined]
    assert doc.oneInterventionPerRound is True  # type: ignore[attr-defined]
    demotions = doc.setDemotions  # type: ignore[attr-defined]
    assert [d.setId for d in demotions] == ["OE", "SE", "APOLOGY", "LONG200"]
    assert all(d.nextConfirmationRole == "development" for d in demotions)
    assert "opened once" in demotions[0].rule
    held = {h.item: h.value for h in doc.holdBeforeNextEval}  # type: ignore[attr-defined]
    assert held["사전 등록"] == "d" * 64
    assert "memory_recall_200=12" in held["집계 분모"]
    assert "개발 세트로 강등" in doc.note  # type: ignore[attr-defined]


def test_match_failure_type_falls_back_to_policy_text() -> None:
    policy = copy.deepcopy(qp.load_policy())
    policy["improvement"]["failureTypes"] = [
        e for e in policy["improvement"]["failureTypes"] if e["id"] != "owner_confusion"
    ]
    rule = sc.FAILURE_RULES["pairs:owner_separation"]
    failure_id, mapping = sc.match_failure_type(policy, rule)
    assert failure_id not in {None, "owner_confusion"}
    assert mapping.confidence == "approximate" and mapping.matchedTerms
    none_rule = sc.FailureRule("missing_type", ("zzz-no-match",), "exact", (), "시험")
    failure_id, mapping = sc.match_failure_type(policy, none_rule)
    assert failure_id is None and mapping.confidence == "unmapped"


# ---- checkpoint-selection 연동 ---------------------------------------------------------------


def _selection(char_dir: Path, decision: str, chosen: str | None, binding_ck: str) -> None:
    folder = char_dir / "s10-train" / "tr1" / "gemma_qlora"
    write_once_json(
        folder / "training-run.json",
        {
            "provider": "gemma_qlora",
            "baseModel": "google/gemma-4-31B-it",
            "datasetRev": "ds1",
            "requestedConfig": {"epochs": 2},
            "modelBinding": {
                "provider": "gemma_qlora",
                "ref": "/runs/adapter/epoch-2",
                "checkpointId": binding_ck,
            },
        },
    )
    doc: dict[str, Any] = {
        "characterId": "c1",
        "datasetRev": "ds1",
        "datasetDigest": "2" * 64,
        "rule": "시험 규칙",
        "screenFile": "screen/responses.jsonl",
        "plannedTasks": 8,
        "plannedArms": ["epoch-1", "epoch-2"],
        "judgeItems": 8,
        "bestCheckpoint": "epoch-2",
        "decision": decision,
        "reasons": ["base가 epoch-2와의 직접 비교에서 5:2로 앞선다"],
    }
    if chosen:
        doc["chosen"] = {"checkpointId": chosen, "ref": f"checkpoints/{chosen}", "epoch": 2}
    write_once_json(folder / "checkpoint-selection.json", validate_selection(doc))


def validate_selection(doc: dict[str, Any]) -> dict[str, Any]:
    from character_factory_poc.stages.s10_train import select  # noqa: F401  계약 등록

    return dump(validate("checkpoint-selection-v1", doc))


def test_checkpoint_selection_keep_incumbent_is_reported(tmp_path: Path) -> None:
    _selection(tmp_path, "KEEP_INCUMBENT", None, "epoch-2")
    card = _card(char_dir=tmp_path)
    sel = card.selection
    assert sel is not None and sel.decision == "KEEP_INCUMBENT"
    assert sel.ref == "s10-train/tr1/gemma_qlora/checkpoint-selection.json"
    assert "같은 짧은 프롬프트의 기반 모델" in sel.meaning
    assert any("KEEP_INCUMBENT" in r and "기반 모델" in r for r in card.draft.reasons)
    task = next(t for t in card.tasks_doc.tasks if t.trigger == "selection:KEEP_INCUMBENT")
    assert task.failureType == "loss_generation_divergence"
    assert task.firstIntervention.kind == "checkpoint"
    held = {h.item: h.value for h in card.tasks_doc.holdBeforeNextEval}
    assert "datasetRev=ds1" in held["기반 모델 revision·학습 설정·저장 에폭"]


def test_checkpoint_selection_binding_match(tmp_path: Path) -> None:
    _selection(tmp_path / "a", "DEVELOPMENT_RECOMMENDED", "epoch-2", "epoch-2")
    sel = _card(char_dir=tmp_path / "a").selection
    assert sel is not None and sel.matchesBinding is True and sel.chosen is not None
    _selection(tmp_path / "b", "DEVELOPMENT_RECOMMENDED", "epoch-1", "epoch-2")
    card = _card(char_dir=tmp_path / "b")
    assert card.selection is not None and card.selection.matchesBinding is False
    assert any("binding이 다르다" in r for r in card.draft.reasons)


def test_no_selection_file_is_fine(tmp_path: Path) -> None:
    assert _card(char_dir=tmp_path).selection is None


# ---- 보고서·페이지·G8 연동 ---------------------------------------------------------------------


def test_report_writes_decision_coverage_and_tasks(tmp_path: Path) -> None:
    ctx, cid, build = _prepared(tmp_path)
    _fake_models(ctx)
    _synthetic_runs(ctx, cid, build)
    eval_judge.run_judge(ctx, cid)
    rev_dir = eval_report.build_report(ctx, cid)
    report = validate("eval-report-v2", json.loads((rev_dir / "report.json").read_text("utf-8")))
    assert report.decision == "DEVELOPMENT_RECOMMENDED"  # type: ignore[attr-defined]
    coverage = {s["suiteId"]: s["coverage"] for s in report.suiteCoverage}  # type: ignore[attr-defined]
    assert all(coverage[s] == "NOT_MEASURED" for s in NOT_MEASURED_SUITES)
    ref = report.improvementTasksRef  # type: ignore[attr-defined]
    tasks = json.loads((ctx.character_dir(cid) / ref.ref).read_text("utf-8"))
    assert ref.ref == "s10-eval/ev1/improvement-tasks.json"
    assert sha256_of(tasks) == ref.sha256
    assert tasks["schemaVersion"] == "improvement-tasks-v1"
    # 합성 응답에서 Gemini는 101~150턴을 같은 말로 채웠다(200/400).
    repeat = next(t for t in tasks["tasks"] if t["trigger"] == "gate:repeat_rate_101_200")
    assert repeat["evidence"][0]["armId"] == "SHORT_GEMINI_SFT"
    page = (rev_dir / "gate-G8.html").read_text("utf-8")
    for text in (
        "결정 초안",
        "사람 결정을",
        "대신하지 않는다",
        "축별 커버리지",
        "미측정",
        "개선 과제",
    ):
        assert text in page
    assert "운영 시작값" in page

    pairs = json.loads((rev_dir / "pairs.json").read_text("utf-8"))
    picks = [{"pairId": pid, "pick": "A"} for pid in pairs["humanPairIds"]]
    approve_g8(
        ctx,
        cid,
        {"decision": "SELECT", "adopted": "LONG_BASE", "humanPicks": picks, "reviewer": "t"},
    )
    final = validate(
        "eval-report-v2", json.loads((rev_dir / "report-final.json").read_text("utf-8"))
    )
    assert final.decision == "DEVELOPMENT_RECOMMENDED"  # type: ignore[attr-defined]
    assert "사람 채택 LONG_BASE" in final.recommendation  # type: ignore[attr-defined]
    adoption = json.loads((rev_dir / "adoption.json").read_text("utf-8"))
    assert adoption["armId"] == "LONG_BASE"  # 초안과 달라도 사람 채택이 그대로 남는다
    assert adoption["draftDecision"] == "DEVELOPMENT_RECOMMENDED"
    assert "개선 과제" in (rev_dir / "gate-G8.html").read_text("utf-8")


def test_missing_response_blocks_report_with_integrity_record(tmp_path: Path) -> None:
    ctx, cid, build = _prepared(tmp_path)
    _fake_models(ctx)
    _synthetic_runs(ctx, cid, build)
    eval_judge.run_judge(ctx, cid)
    path = build.rev_dir / "runs" / "SHORT_GEMMA_SFT-APOLOGY.json"
    obj = json.loads(path.read_text("utf-8"))
    obj["items"] = obj["items"][:-1]
    path.write_text(json.dumps(obj, ensure_ascii=False), "utf-8")
    with pytest.raises(eval_report.IntegrityBlockedError, match="BLOCKED_INTEGRITY"):
        eval_report.build_report(ctx, cid)
    record = json.loads((build.rev_dir / "integrity-blocked.json").read_text("utf-8"))
    assert record["decision"] == "BLOCKED_INTEGRITY"
    assert any("응답 누락" in r and "ap06" in r for r in record["decisionReasons"])
    assert not (build.rev_dir / "report.json").exists()
    assert ctx.state(cid).gate("G8").status != "AWAITING_HUMAN"


def test_prereg_hash_mismatch_records_integrity_block(tmp_path: Path) -> None:
    ctx, cid, build = _prepared(tmp_path)
    _fake_models(ctx)
    _synthetic_runs(ctx, cid, build)
    eval_judge.run_judge(ctx, cid)
    obj = json.loads((build.rev_dir / "prereg.json").read_text("utf-8"))
    obj["humanPairs"] = 5
    (build.rev_dir / "prereg.json").write_text(json.dumps(obj, ensure_ascii=False), "utf-8")
    with pytest.raises(eval_prereg.PreregMismatchError):
        eval_report.build_report(ctx, cid)
    record = json.loads((build.rev_dir / "integrity-blocked.json").read_text("utf-8"))
    assert record["decision"] == "BLOCKED_INTEGRITY"
    assert "사전 등록 해시" in record["decisionReasons"][0]


def test_old_report_without_policy_fields_still_loads_and_renders() -> None:
    old = {
        "schemaVersion": "eval-report-v2",
        "characterId": "c1",
        "preregSha256": "d" * 64,
        "runRefs": [],
        "metrics": [{"armId": BASE, "metric": "memory_recall_200", "value": 0.9}],
        "criteriaResults": [],
        "llmPairs": [],
        "recommendation": "이전 보고서",
    }
    report = validate("eval-report-v2", old)
    assert report.decision is None and report.suiteCoverage == []  # type: ignore[attr-defined]
    assert report.improvementTasksRef is None  # type: ignore[attr-defined]
    page = render_g8_page(subject_id="c1", rev="ev1", prereg=_prereg(), report=report, pairs={})
    assert "결정 초안" not in page and "기준" in page
