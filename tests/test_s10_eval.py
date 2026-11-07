"""S10 평가(G8) 시험. 가짜 응답·판정 모델만 쓰고 네트워크를 쓰지 않는다(NFR-08)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

import character_factory_poc.contracts  # noqa: F401  계약 등록
from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import dump, known_contracts, validate
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts.training import EvalRun, HumanPick
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import write_gate_record
from character_factory_poc.providers.base import ChatRequest
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s10_eval import judge as eval_judge
from character_factory_poc.stages.s10_eval import metrics as eval_metrics
from character_factory_poc.stages.s10_eval import prereg as eval_prereg
from character_factory_poc.stages.s10_eval import report as eval_report
from character_factory_poc.stages.s10_eval import run as eval_run
from character_factory_poc.stages.s10_eval.approve import approve_g8
from tests.support.flow import approve_plan_v2, make_ctx, through_s2


def _context(root: Path, judge_model: str = "anthropic/claude-opus-5-5") -> tuple[Context, str]:
    extra = (
        "[providers.text]\n"
        'adapter = "fake"\n'
        'model = "base-model"\n'
        "[providers.judge]\n"
        'adapter = "fake"\n'
        f'model = "{judge_model}"\n'
        "[budget]\n"
        "max_calls_per_command = 20000\n"
    )
    ctx, _ = make_ctx(root, extra)
    cid = through_s2(ctx)
    approve_plan_v2(ctx, cid)
    _prompt_pair(ctx, cid)
    _g7_and_training(ctx, cid)
    return ctx, cid


def _prompt_pair(ctx: Context, cid: str) -> None:
    char_dir = ctx.character_dir(cid)
    long_text = "너는 윤하린이다. 하고 싶은 말을 짧게 한다. " * 4
    short_text = "너는 윤하린이다. 짧게 말한다."
    pair = validate(
        "prompt-pair-v1",
        {
            "characterId": cid,
            "personaVersion": "pv1",
            "traitSheetSha256": "0" * 64,
            "sections": ["ACTOR_IDENTITY"],
            "long": {
                "text": long_text,
                "sha256": sha256_text(long_text),
                "chars": len(long_text),
            },
            "short": {
                "text": short_text,
                "sha256": sha256_text(short_text),
                "chars": len(short_text),
            },
            "systemRulesRef": "builtin:test",
            "systemRulesSha256": "1" * 64,
        },
    )
    rev_dir = char_dir / "s8-prompts" / "pv1"
    write_once_json(rev_dir / "prompt-pair.json", dump(pair))
    (rev_dir / "long.md").write_text(long_text, encoding="utf-8")
    (rev_dir / "short.md").write_text(short_text, encoding="utf-8")
    state = ctx.state(cid)
    state.transition("s8", "RUNNING", rev="pv1")
    state.transition("s8", "AWAITING_HUMAN", rev="pv1")
    write_gate_record(
        char_dir,
        state,
        gate="G6",
        rev="pv1",
        stage_id="s8",
        shown=[rev_dir / "prompt-pair.json"],
        decision="APPROVE",
        reviewer="test",
        reasons="시험용 프롬프트 쌍",
    )


def _g7_and_training(ctx: Context, cid: str) -> None:
    state = ctx.state(cid)
    state.set_gate("G7", "APPROVED", "ds1", "gates/G7-ds1.json")
    state.transition("s10t", "RUNNING", rev="tr1")
    state.transition("s10t", "AWAITING_HUMAN", rev="tr1")
    for provider, base, ref in (
        ("gemma_qlora", "google/gemma-4-31B-it", "gemma-r1"),
        ("vertex_gemini", "google/gemini-3.1", "vertex-r1"),
    ):
        run = validate(
            "training-run-v2",
            {
                "characterId": cid,
                "datasetRev": "ds1",
                "datasetDigest": "2" * 64,
                "provider": provider,
                "baseModel": base,
                "requestedConfig": {"epochs": 1},
                "dryRun": False,
                "estimate": {"usd": 0.0, "basis": "시험 가짜"},
                "budgetUsd": 10.0,
                "status": "SUCCEEDED",
                "modelBinding": {"provider": provider, "ref": ref, "checkpointId": "ck-1"},
            },
        )
        write_once_json(
            ctx.character_dir(cid) / "s10-train" / "tr1" / provider / "training-run.json",
            dump(run),
        )


class JudgeResponder:
    """프롬프트 종류별 가짜 판정. 기억은 정답 키, 사과는 '회복' 표시, 짝은 긴 답을 고른다."""

    def __call__(self, req: ChatRequest) -> dict[str, Any]:
        system = req.messages[0].content
        user = req.messages[1].content
        if "기억 확인 판정자" in system:
            keys = re.search(r"<answer_keys>\n(.*?)\n</answer_keys>", user, re.S)
            reply = re.search(r"<reply>\n(.*?)\n</reply>", user, re.S)
            expected = [k.strip() for k in (keys.group(1) if keys else "").split("/")]
            body = reply.group(1) if reply else ""
            return {"correct": all(k and k in body for k in expected)}
        if "갈등 회복 판정자" in system:
            return {"recovered": "회복" in user}
        if "짝 비교 판정자" in system:
            a = re.search(r"<A>\n(.*?)\n</A>", user, re.S)
            b = re.search(r"<B>\n(.*?)\n</B>", user, re.S)
            left = a.group(1) if a else ""
            right = b.group(1) if b else ""
            pick = "TIE" if len(left) == len(right) else ("A" if len(left) > len(right) else "B")
            return {"pick": pick, "reasons": "긴 답"}
        return {"_error": "알 수 없는 판정 프롬프트"}


def _fake_models(ctx: Context) -> tuple[FakeTextModel, FakeTextModel]:
    text = FakeTextModel(model="base-model")
    judge = FakeTextModel(model="anthropic/claude-opus-5-5")
    judge.add("JUDGE", JudgeResponder())
    ctx.use_models(text, judge)
    return text, judge


class FakeChat:
    name = "fake-chat"

    def __init__(self, model: str, prefix: str, length: int = 0):
        self.model = model
        self.prefix = prefix
        self.length = length
        self.calls: list[tuple[list[tuple[str, str]], int, str]] = []

    def reply(self, messages, *, seed: int, ref: str) -> str:
        self.calls.append(([(m.role, m.content) for m in messages], seed, ref))
        text = f"{self.prefix} {len(messages)} {seed}"
        if self.length and len(text) < self.length:
            text += " " + "좋아" * ((self.length - len(text)) // 2 + 1)
        return text[: self.length] if self.length else text


def _prepared(root: Path, judge_model: str = "anthropic/claude-opus-5-5"):
    ctx, cid = _context(root, judge_model)
    _fake_models(ctx)
    build = eval_prereg.build_prereg(ctx, cid)
    return ctx, cid, build


def test_prereg_freezes_defaults_and_rejects_tampering(tmp_path: Path) -> None:
    ctx, cid, build = _prepared(tmp_path)
    p = build.prereg
    assert [a.armId for a in p.arms] == ["LONG_BASE", "SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT"]
    assert [s.setId for s in p.sets] == ["OE", "SE", "APOLOGY", "LONG200"]
    assert p.humanPairs == 20 and p.judge.orderSwap is True
    assert [(c.metric, c.comparator, c.threshold) for c in p.criteria] == [
        ("repeat_rate_101_200", "<=", 0.05),
        ("memory_recall_200", ">=", 0.9),
        ("apology_recovery", ">=", 0.667),
    ]
    assert all(c.appliesTo == "SFT_ANY" for c in p.criteria)
    assert (build.rev_dir / "sets" / "LONG200.json").exists()
    _, digest = eval_prereg.read_prereg(build.rev_dir)
    assert digest == build.sha256

    obj = json.loads((build.rev_dir / "prereg.json").read_text("utf-8"))
    obj["criteria"][0]["threshold"] = 0.5
    (build.rev_dir / "prereg.json").write_text(json.dumps(obj, ensure_ascii=False), "utf-8")
    with pytest.raises(eval_prereg.PreregMismatchError):
        eval_prereg.read_prereg(build.rev_dir)


def test_sets_have_expected_counts_and_fill_plan(tmp_path: Path) -> None:
    ctx, cid, build = _prepared(tmp_path)
    char_dir = ctx.character_dir(cid)
    docs = eval_run.load_set_docs(build.prereg, char_dir)
    assert len(docs["OE"]["items"]) == 12
    assert len(docs["SE"]["items"]) == 12
    assert len(docs["APOLOGY"]["items"]) == 6
    assert all(10 <= len(i["turns"]) <= 14 for i in docs["APOLOGY"]["items"])
    long = docs["LONG200"]
    assert len(long["items"]) == 4
    assert all(len(i["turns"]) == 200 for i in long["items"])
    assert all(len([t for t in i["turns"] if t["kind"] == "check"]) == 3 for i in long["items"])
    joined = json.dumps(long, ensure_ascii=False)
    assert "{name}" not in joined and "{relation}" not in joined
    assert "연애 중" in long["relation"] or "썸" in long["relation"]
    assert long["items"][0]["turns"][7]["kind"] == "plant"
    assert long["items"][0]["turns"][99]["kind"] == "change"


def test_prereg_rejects_same_family_judge(tmp_path: Path) -> None:
    ctx, cid = _context(tmp_path, judge_model="base-judge")
    _fake_models(ctx)
    with pytest.raises(FactoryError, match="계열이 같다"):
        eval_prereg.build_prereg(ctx, cid)


def test_run_feeds_reply_and_uses_distinct_turn_seed(tmp_path: Path) -> None:
    ctx, cid, build = _prepared(tmp_path)
    chat = FakeChat("base-model", "기준")
    rev_dir = eval_run.run_eval(
        ctx,
        cid,
        {"LONG_BASE": chat},
        only_sets=["APOLOGY"],
        only_arms=["LONG_BASE"],
    )
    obj = json.loads((rev_dir / "runs" / "LONG_BASE-APOLOGY.json").read_text("utf-8"))
    run = validate("eval-run-v1", obj)
    assert run.preregSha256 == build.sha256
    assert len(run.items) == 6
    assert all(len(i.turns) == 12 for i in run.items)
    seeds = [t.seed for i in run.items for t in i.turns]
    assert len(seeds) == len(set(seeds))
    spec = next(s for s in build.prereg.sets if s.setId == "APOLOGY")
    base = spec.seeds[0]
    assert run.items[0].turns[0].seed == eval_run.turn_seed(base, 1)
    assert run.items[0].turns[11].seed == eval_run.turn_seed(base, 12)
    # 두 번째 호출의 이력에 첫 응답이 assistant로 그대로 들어간다.
    second = chat.calls[1][0]
    assert ("assistant", run.items[0].turns[0].reply) in second


def test_run_rejects_changed_prereg(tmp_path: Path) -> None:
    ctx, cid, build = _prepared(tmp_path)
    obj = json.loads((build.rev_dir / "prereg.json").read_text("utf-8"))
    obj["humanPairs"] = 10
    (build.rev_dir / "prereg.json").write_text(json.dumps(obj, ensure_ascii=False), "utf-8")
    with pytest.raises(eval_prereg.PreregMismatchError):
        eval_run.run_eval(ctx, cid, {"LONG_BASE": FakeChat("base", "x")}, only_sets=["OE"])


def _long_run(cid: str, prereg_sha: str, arm: str, replies: list[str]) -> EvalRun:
    turns = [{"user": f"u{i}", "reply": r, "seed": i} for i, r in enumerate(replies, 1)]
    return validate(
        "eval-run-v1",
        {
            "characterId": cid,
            "preregSha256": prereg_sha,
            "armId": arm,
            "setId": "LONG200",
            "model": "m",
            "items": [{"itemId": "long-p1", "personaId": "p1", "turns": turns}],
        },
    )


def test_repeat_rate_handmade() -> None:
    replies = [f"답변 {i}" for i in range(1, 201)]
    replies[49] = "안녕하세요"  # 50턴
    replies[149] = "안녕 하세요!"  # 150턴: 정규화하면 같다
    replies[159] = "안녕하세요"  # 160턴
    run = _long_run("c", "0" * 64, "LONG_BASE", replies)
    out = eval_metrics.repeat_rate_101_200(run)
    assert out.value == 0.02
    assert "2/100" in out.detail


def test_memory_and_apology_metrics_with_fake_judge(tmp_path: Path) -> None:
    ctx, cid, build = _prepared(tmp_path)
    _, fake_judge = _fake_models(ctx)
    docs = eval_run.load_set_docs(build.prereg, ctx.character_dir(cid))
    # LONG200: 12 확인 질문 중 11개만 정답 키를 담는다.
    items = []
    for item in docs["LONG200"]["items"]:
        turns = []
        for idx, turn in enumerate(item["turns"], start=1):
            if turn["kind"] == "check":
                miss = item["personaId"] == "p4" and turn["checkId"] == "c3"
                body = "잘 기억 안 나" if miss else " ".join(turn["answerKeys"])
            else:
                body = f"답 {item['personaId']} {idx}"
            turns.append({"user": turn["user"], "reply": body, "seed": idx})
        items.append({"itemId": item["itemId"], "personaId": item["personaId"], "turns": turns})
    long_run = validate(
        "eval-run-v1",
        {
            "characterId": cid,
            "preregSha256": build.sha256,
            "armId": "SHORT_GEMMA_SFT",
            "setId": "LONG200",
            "model": "m",
            "items": items,
        },
    )
    memory = eval_metrics.memory_recall_200(long_run, docs["LONG200"], fake_judge, cid=cid)
    assert memory.value == 0.917

    # APOLOGY: 6개 중 4개만 진지한 사과에서 회복한다.
    apology_items = []
    for n, item in enumerate(docs["APOLOGY"]["items"]):
        turns = []
        for idx, turn in enumerate(item["turns"], start=1):
            body = "회복한 사과" if n < 4 and turn["phase"] == "sincere" else "그냥 미안해"
            turns.append({"user": turn["user"], "reply": body, "seed": idx})
        apology_items.append({"itemId": item["itemId"], "turns": turns})
    apology_run = validate(
        "eval-run-v1",
        {
            "characterId": cid,
            "preregSha256": build.sha256,
            "armId": "SHORT_GEMMA_SFT",
            "setId": "APOLOGY",
            "model": "m",
            "items": apology_items,
        },
    )
    apology = eval_metrics.apology_recovery(apology_run, docs["APOLOGY"], fake_judge, cid=cid)
    assert apology.value == 0.667


def _case() -> dict[str, Any]:
    return {
        "pairId": "p001",
        "setId": "OE",
        "itemId": "oe01",
        "personaId": "",
        "armA": "LONG_BASE",
        "armB": "SHORT_GEMMA_SFT",
        "turn": 1,
        "user": "몇 시였지?",
        "history": "",
        "replyA": "6시야",
        "replyB": "음...",
        "forward": "TIE",
        "reverse": "TIE",
        "consensus": "SPLIT",
        "reasons": "",
    }


def test_pair_judge_forward_reverse_consensus_and_split() -> None:
    agree = FakeTextModel(responses={"JUDGE": [{"pick": "A"}, {"pick": "B"}]})
    out = eval_judge.judge_pair(agree, _case(), cid="c", rev="ev1")
    assert (out["forward"], out["reverse"], out["consensus"]) == ("A", "B", "A")

    split = FakeTextModel(responses={"JUDGE": [{"pick": "A"}, {"pick": "A"}]})
    out = eval_judge.judge_pair(split, _case(), cid="c", rev="ev1")
    assert out["consensus"] == "SPLIT"


def test_human_sample_is_fixed_by_seed() -> None:
    ids = [f"p{i:03d}" for i in range(1, 31)]
    a = eval_judge.human_sample(ids, 20)
    b = eval_judge.human_sample(list(reversed(ids)), 20)
    assert a == b and len(a) == 20
    assert a != eval_judge.human_sample(ids, 20, seed=7)


def _synthetic_runs(ctx: Context, cid: str, build) -> dict[tuple[str, str], EvalRun]:
    docs = eval_run.load_set_docs(build.prereg, ctx.character_dir(cid))
    out: dict[tuple[str, str], EvalRun] = {}
    for arm in build.prereg.arms:
        for spec in build.prereg.sets:
            sid = spec.setId
            doc = docs[sid]
            items = []
            for item in doc["items"]:
                turns = []
                script = item.get("turns")
                if sid in {"OE", "SE"}:
                    pad = 60 if arm.armId == "SHORT_GEMMA_SFT" else 20
                    body = f"{arm.armId} {item['itemId']} " + "좋아" * pad
                    turns.append({"user": item["question"], "reply": body, "seed": 1})
                else:
                    for idx, turn in enumerate(script, start=1):
                        if sid == "APOLOGY" and turn["phase"] == "sincere":
                            recovered = arm.armId != "SHORT_GEMMA_SFT" or item["itemId"] < "ap05"
                            body = (
                                "내가 잘못했어. 다음엔 이렇게 할게. 회복"
                                if recovered
                                else "그냥 미안해"
                            )
                        elif sid == "LONG200" and turn["kind"] == "check":
                            miss = arm.armId == "SHORT_GEMMA_SFT" and (
                                item["personaId"] == "p4" and turn["checkId"] == "c3"
                            )
                            body = "잘 기억 안 나" if miss else " ".join(turn["answerKeys"])
                        else:
                            body = f"{arm.armId} {item['itemId']} {idx} " + "좋아" * (
                                30 if arm.armId == "SHORT_GEMMA_SFT" else 10
                            )
                        if sid == "LONG200" and 101 <= idx <= 200:
                            if arm.armId == "SHORT_GEMINI_SFT" and idx <= 150:
                                body = f"{arm.armId} {item['itemId']} 50 " + "좋아" * 10
                            elif arm.armId == "SHORT_GEMMA_SFT" and idx in {151, 152}:
                                body = f"{arm.armId} {item['itemId']} 50 " + "좋아" * 30
                        turns.append({"user": turn["user"], "reply": body, "seed": idx})
                items.append(
                    {
                        "itemId": item["itemId"],
                        "personaId": item.get("personaId", ""),
                        "turns": turns,
                    }
                )
            run = validate(
                "eval-run-v1",
                {
                    "characterId": cid,
                    "preregSha256": build.sha256,
                    "armId": arm.armId,
                    "setId": sid,
                    "model": arm.model,
                    "items": items,
                },
            )
            write_once_json(build.rev_dir / "runs" / f"{arm.armId}-{sid}.json", dump(run))
            out[(arm.armId, sid)] = run
    return out


def test_report_and_g8_approval(tmp_path: Path) -> None:
    ctx, cid, build = _prepared(tmp_path)
    _fake_models(ctx)
    _synthetic_runs(ctx, cid, build)
    eval_judge.run_judge(ctx, cid)
    pairs = json.loads((build.rev_dir / "pairs.json").read_text("utf-8"))
    rev_dir = eval_report.build_report(ctx, cid)
    report_obj = json.loads((rev_dir / "report.json").read_text("utf-8"))
    report = validate("eval-report-v2", report_obj)
    assert report.preregSha256 == build.sha256
    assert len(report.metrics) == 9
    assert len(report.criteriaResults) == 6
    assert len(report.llmPairs) == len(pairs["pairs"])
    assert "SHORT_GEMMA_SFT" in report.recommendation
    assert (rev_dir / "gate-G8.html").exists()
    assert ctx.state(cid).gate("G8").status == "AWAITING_HUMAN"

    by_id = {p["pairId"]: p for p in pairs["pairs"]}
    picks = []
    for pid in pairs["humanPairIds"]:
        consensus = by_id[pid]["consensus"]
        picks.append({"pairId": pid, "pick": consensus if consensus != "SPLIT" else "TIE"})
    expected, _, _ = eval_judge.llm_human_agreement(
        [HumanPick(pairId=p["pairId"], pick=p["pick"]) for p in picks], pairs["pairs"]
    )
    answer = {
        "decision": "SELECT",
        "adopted": "gemma-r1",
        "humanPicks": picks,
        "reviewer": "test",
        "minutes": 12,
        "reasons": "시험 채택",
    }
    approve_g8(ctx, cid, answer)
    final = validate(
        "eval-report-v2",
        json.loads((rev_dir / "report-final.json").read_text("utf-8")),
    )
    assert final.llmHumanAgreement == expected
    assert len(final.humanPicks) == 20
    adoption = json.loads((rev_dir / "adoption.json").read_text("utf-8"))
    assert adoption["armId"] == "SHORT_GEMMA_SFT" and adoption["adopted"] == "gemma-r1"
    record = json.loads((ctx.character_dir(cid) / "gates" / "G8-ev1.json").read_text("utf-8"))
    assert record["decision"] == "SELECT" and record["selections"] == ["gemma-r1"]
    assert ctx.state(cid).gate("G8").status == "APPROVED"
    assert ctx.state(cid).stage("s10").status == "APPROVED"
    page = (rev_dir / "gate-G8.html").read_text("utf-8")
    assert "사람 블라인드 20쌍" in page and 'data-pair="p' in page


def test_eval_contracts_registered() -> None:
    names = set(known_contracts())
    for name in (
        "eval-set-v1",
        "eval-prereg-v2",
        "eval-run-v1",
        "eval-pairs-v1",
        "eval-report-v2",
        "eval-adoption-v1",
    ):
        assert name in names


def test_gemma_only_prereg_judges_and_reports_two_arms(tmp_path: Path) -> None:
    """Gemma만 학습하면 사전 등록·짝 판정·보고서가 두 조건(LONG_BASE, SHORT_GEMMA_SFT)으로 돈다."""
    ctx, cid = _context(tmp_path)
    ctx.config.stages["s10t"] = {"providers": ["gemma_qlora"]}
    vertex = ctx.character_dir(cid) / "s10-train" / "tr1" / "vertex_gemini" / "training-run.json"
    vertex.unlink()
    _fake_models(ctx)
    build = eval_prereg.build_prereg(ctx, cid)
    assert [a.armId for a in build.prereg.arms] == ["LONG_BASE", "SHORT_GEMMA_SFT"]
    _synthetic_runs(ctx, cid, build)
    eval_judge.run_judge(ctx, cid)
    pairs = json.loads((build.rev_dir / "pairs.json").read_text("utf-8"))
    assert {(p["armA"], p["armB"]) for p in pairs["pairs"]} == {("LONG_BASE", "SHORT_GEMMA_SFT")}
    rev_dir = eval_report.build_report(ctx, cid)
    report = validate("eval-report-v2", json.loads((rev_dir / "report.json").read_text("utf-8")))
    assert {m.armId for m in report.metrics} == {"LONG_BASE", "SHORT_GEMMA_SFT"}
    assert "SHORT_GEMINI_SFT" not in report.recommendation
    assert ctx.state(cid).gate("G8").status == "AWAITING_HUMAN"
