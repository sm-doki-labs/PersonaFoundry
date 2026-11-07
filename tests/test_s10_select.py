"""S10t 체크포인트 선택 (D-0077). 가짜 판정 모델과 합성 선별 파일로 오프라인에서 돈다."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from character_factory_poc.common.schema import validate
from character_factory_poc.contracts.training import Checkpoint, CostEstimate, TrainingRun
from character_factory_poc.providers.base import ChatRequest, ChatResponse
from character_factory_poc.stages.s10_train.select import has_ngram_loop, select_checkpoint

PERSONA = "너는 서윤이다. 친구에게 반말로 짧게 말한다."
CKPTS = (("ckpt-e0.5", 0.5), ("ckpt-e1", 1.0), ("ckpt-e1.5", 1.5), ("ckpt-e2", 2.0))


def _run(epochs=CKPTS) -> TrainingRun:
    return TrainingRun(
        characterId="c001",
        datasetRev="d001",
        datasetDigest="0" * 64,
        provider="fake",
        baseModel="gemma-4-31b",
        requestedConfig={},
        dryRun=False,
        estimate=CostEstimate(),
        budgetUsd=10.0,
        status="SUCCEEDED",
        checkpoints=[
            Checkpoint(
                checkpointId=cid, epoch=ep, ref=f"checkpoints/{cid}", validationLoss=1.0 / ep
            )
            for cid, ep in reversed(epochs)  # 순서가 뒤섞여도 epoch 순으로 걷는다
        ],
    )


def _tasks(single: int = 4) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = [
        {
            "taskId": f"s-{n}",
            "kind": "single",
            "messages": [
                {"role": "system", "content": "짧은 system"},
                {"role": "user", "content": f"어제 {n}번 영화 봤어?"},
                {"role": "assistant", "content": "응 봤지"},
                {"role": "user", "content": f"{n}번 결말 어땠어?"},
            ],
            "reference": "좋았어",
            "seed": n,
        }
        for n in range(single)
    ]
    tasks.append(
        {
            "taskId": "m-0",
            "kind": "multi",
            "messages": [{"role": "system", "content": "짧은 system"}],
            "userTurns": ["뭐해", "밥은", "내일 봐"],
            "seed": 1000,
        }
    )
    return tasks


def _good(arm: str, task: str, turn: int) -> str:
    return f"{arm} 쪽 {task} {turn}번째 답이야 오늘은 산책하고 왔어 너는 뭐 했어"


def _write_screen(
    root: Path,
    tasks: list[dict[str, Any]],
    arms: list[str],
    text_for=_good,
    finish_for=lambda arm, task, turn: "stop",
) -> None:
    lines = []
    for arm in arms:
        for task in tasks:
            users = task.get("userTurns") or [task["messages"][-1]["content"]]
            turns = []
            for n, user in enumerate(users, start=1):
                text = text_for(arm, task["taskId"], n)
                finish = finish_for(arm, task["taskId"], n)
                turns.append(
                    {
                        "turn": n,
                        "user": user,
                        "text": text,
                        "finish": finish,
                        "inputTokens": 10,
                        "outputTokens": 5,
                    }
                )
                if not text or finish != "stop":
                    break
            lines.append(
                json.dumps(
                    {"arm": arm, "taskId": task["taskId"], "kind": task["kind"], "turns": turns},
                    ensure_ascii=False,
                )
            )
    path = root / "screen" / "responses.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", "utf-8")


class ScriptedJudge:
    """'선호' 표시가 있는 답을 고른다. 둘 다 없으면 위치 편향으로 A를 고른다."""

    name = "fake-judge"
    model = "fake/judge-model"

    def __init__(self, broken_task: str | None = None):
        self.broken_task = broken_task
        self.calls: list[ChatRequest] = []

    def complete(self, request: ChatRequest) -> ChatResponse:
        self.calls.append(request)
        user = request.messages[1].content
        a = re.search(r"<A>\n(.*?)\n</A>", user, re.S).group(1)
        b = re.search(r"<B>\n(.*?)\n</B>", user, re.S).group(1)
        if self.broken_task and f"/{self.broken_task}/" in request.ref:
            text = "판정 못 함"
        elif "선호" in a and "선호" not in b:
            text = '{"winner": "A", "reason": "말투가 맞다"}'
        elif "선호" in b and "선호" not in a:
            text = '{"winner": "B", "reason": "말투가 맞다"}'
        else:
            text = '{"winner": "A", "reason": "앞 답"}'
        return ChatResponse(
            text=text,
            input_tokens=1,
            output_tokens=1,
            elapsed_ms=0,
            model=self.model,
            provider="fake",
        )


def _doc(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text("utf-8"))
    validate("checkpoint-selection-v1", data)
    return data


def _arm(doc: dict[str, Any], arm: str) -> dict[str, Any]:
    return next(a for a in doc["arms"] if a["arm"] == arm)


def test_loop_detector() -> None:
    assert has_ngram_loop("좋아 진짜 너무 좋아 " * 3)
    assert not has_ngram_loop("오늘 산책하고 왔어 너는 뭐 했어")


def test_e2_loop_regression_is_excluded_and_judged_best_is_chosen(tmp_path: Path) -> None:
    tasks = _tasks()
    arms = ["base"] + [c for c, _ in CKPTS]

    def text_for(arm: str, task: str, turn: int) -> str:
        if arm == "ckpt-e2" and task == "s-0":
            return "응 그래 맞아 진짜 " * 6  # 7회 중 1회 루프: 0.2 이하지만 0.05 넘게 오른다
        if arm == "ckpt-e1.5":
            return "선호 " + _good(arm, task, turn)
        return _good(arm, task, turn)

    _write_screen(tmp_path, tasks, arms, text_for)
    judge = ScriptedJudge()
    out = tmp_path / "selection.json"
    result = select_checkpoint(
        run=_run(),
        artifact_dir=tmp_path,
        tasks=tasks,
        persona_text=PERSONA,
        judge=judge,
        out_path=out,
        judge_items=3,
        ref_prefix="vast:job/",
    )

    assert result.decision == "DEVELOPMENT_RECOMMENDED"
    assert result.checkpoint_id == "ckpt-e1.5"
    assert result.checkpoint_ref == "vast:job/checkpoints/ckpt-e1.5"
    doc = _doc(out)
    assert doc["eligibleCheckpoints"] == ["ckpt-e0.5", "ckpt-e1", "ckpt-e1.5"]
    e2 = _arm(doc, "ckpt-e2")
    assert e2["eligible"] is False and "결함 악화" in e2["exclusion"]
    assert e2["loop"] == {"numerator": 1, "denominator": 7, "rate": 0.1429}
    assert all("ckpt-e2" not in c.messages[1].content for c in judge.calls)
    assert all(c.kind == "JUDGE" and c.stage == "s10t" and c.response_json for c in judge.calls)
    assert PERSONA in judge.calls[0].messages[1].content
    assert doc["splitUse"] == "development_shared_context"
    assert {loss["lossUse"] for loss in doc["checkpointLosses"]} == {"recorded_only"}
    # base + 적격 3 = 4팔, 6쌍 × 3과제 × 정순·역순
    assert doc["plannedJudgments"] == doc["validJudgments"] == 36
    assert doc["chosen"]["checkpointId"] == "ckpt-e1.5"


def test_order_unstable_and_format_errors_are_not_counted(tmp_path: Path) -> None:
    epochs = (("ckpt-e1", 1.0), ("ckpt-e2", 2.0))
    tasks = _tasks()

    def text_for(arm: str, task: str, turn: int) -> str:
        return ("선호 " if arm == "ckpt-e2" else "") + _good(arm, task, turn)

    _write_screen(tmp_path, tasks, ["base", "ckpt-e1", "ckpt-e2"], text_for)
    out = tmp_path / "selection.json"
    result = select_checkpoint(
        run=_run(epochs),
        artifact_dir=tmp_path,
        tasks=tasks,
        persona_text=PERSONA,
        judge=ScriptedJudge(broken_task="s-0"),
        out_path=out,
        judge_items=4,
    )

    doc = _doc(out)
    base_e1 = [p for p in doc["pairs"] if (p["armA"], p["armB"]) == ("base", "ckpt-e1")]
    assert [p["consensus"] for p in base_e1] == [
        "MISSING",
        "ORDER_UNSTABLE",
        "ORDER_UNSTABLE",
        "ORDER_UNSTABLE",
    ]
    assert doc["orderUnstable"] == 3
    assert doc["wins"] == {"base": 0, "ckpt-e1": 0, "ckpt-e2": 6}
    assert doc["plannedJudgments"] == 24 and doc["validJudgments"] == 18
    assert doc["consensusComparisons"] == 6
    assert result.decision == "DEVELOPMENT_RECOMMENDED" and result.checkpoint_id == "ckpt-e2"


def test_base_winning_keeps_incumbent(tmp_path: Path) -> None:
    tasks = _tasks()

    def text_for(arm: str, task: str, turn: int) -> str:
        return ("선호 " if arm == "base" else "") + _good(arm, task, turn)

    _write_screen(tmp_path, tasks, ["base"] + [c for c, _ in CKPTS], text_for)
    out = tmp_path / "selection.json"
    result = select_checkpoint(
        run=_run(),
        artifact_dir=tmp_path,
        tasks=tasks,
        persona_text=PERSONA,
        judge=ScriptedJudge(),
        out_path=out,
    )

    assert result.decision == "KEEP_INCUMBENT"
    assert result.checkpoint_id is None and result.checkpoint_ref is None
    doc = _doc(out)
    assert doc["chosen"] is None
    assert doc["bestCheckpoint"] == "ckpt-e2"  # 체크포인트끼리는 모두 불안정 → 동률, 마지막 적격
    assert doc["wins"]["base"] == 16


def test_without_judge_last_eligible_is_inconclusive(tmp_path: Path) -> None:
    tasks = _tasks()
    _write_screen(tmp_path, tasks, [c for c, _ in CKPTS])
    out = tmp_path / "selection.json"
    result = select_checkpoint(
        run=_run(),
        artifact_dir=tmp_path,
        tasks=tasks,
        persona_text=PERSONA,
        judge=None,
        out_path=out,
        ref_prefix="c001/tr1",
    )

    assert result.decision == "INCONCLUSIVE"
    assert result.checkpoint_id == "ckpt-e2"
    assert result.checkpoint_ref == "c001/tr1/checkpoints/ckpt-e2"
    doc = _doc(out)
    assert doc["judgeModel"] is None and doc["pairs"] == []
    assert _arm(doc, "ckpt-e1")["coverage"] == {"numerator": 5, "denominator": 5, "rate": 1.0}


def test_missing_screen_blocks_integrity(tmp_path: Path) -> None:
    out = tmp_path / "selection.json"
    result = select_checkpoint(
        run=_run(),
        artifact_dir=tmp_path,
        tasks=_tasks(),
        persona_text=PERSONA,
        judge=ScriptedJudge(),
        out_path=out,
    )

    assert result.decision == "BLOCKED_INTEGRITY" and result.checkpoint_id is None
    assert _doc(out)["decision"] == "BLOCKED_INTEGRITY"


def test_checkpoint_rows_absent_blocks_integrity(tmp_path: Path) -> None:
    tasks = _tasks()
    _write_screen(tmp_path, tasks, ["base"])
    result = select_checkpoint(
        run=_run(),
        artifact_dir=tmp_path,
        tasks=tasks,
        persona_text=PERSONA,
        judge=None,
        out_path=tmp_path / "s.json",
    )
    assert result.decision == "BLOCKED_INTEGRITY"


def test_first_checkpoint_defects_block_quality(tmp_path: Path) -> None:
    tasks = _tasks()

    def text_for(arm: str, task: str, turn: int) -> str:
        return "" if task in {"s-0", "s-1"} else _good(arm, task, turn)

    _write_screen(tmp_path, tasks, [c for c, _ in CKPTS], text_for)
    judge = ScriptedJudge()
    out = tmp_path / "selection.json"
    result = select_checkpoint(
        run=_run(),
        artifact_dir=tmp_path,
        tasks=tasks,
        persona_text=PERSONA,
        judge=judge,
        out_path=out,
    )

    assert result.decision == "BLOCKED_QUALITY" and result.checkpoint_id is None
    assert judge.calls == []
    doc = _doc(out)
    first = _arm(doc, "ckpt-e0.5")
    assert first["empty"] == {"numerator": 2, "denominator": 7, "rate": 0.2857}
    assert "0.2 초과" in first["exclusion"]
    assert doc["eligibleCheckpoints"] == []
