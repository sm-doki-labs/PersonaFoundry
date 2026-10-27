"""LLM 짝 판정과 사람 블라인드 표본 (LLD §8.9, D-0044 (2)).

두 조건의 같은 입력 응답을 정순·역순으로 보여 주고, 두 판정이 같은 쪽을 가리킬 때만 consensus로
센다. 사람 20쌍은 고정 시드로 고르고 페이지에는 어느 조건인지 숨긴다.
"""

from __future__ import annotations

import random
from importlib import resources
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import dump, register, validate
from character_factory_poc.common.store import write_manifest, write_once_json
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.training import ArmId, EvalPrereg, EvalRun, HumanPick, SetId
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import (
    ChatRequest,
    Message,
    TextModel,
    extract_json_object,
)
from character_factory_poc.stages.s10_eval.prereg import HUMAN_SAMPLE_SEED, load_prereg
from character_factory_poc.stages.s10_eval.run import load_runs, load_set_docs

ARM_PAIRS: tuple[tuple[ArmId, ArmId], ...] = (
    ("LONG_BASE", "SHORT_GEMMA_SFT"),
    ("LONG_BASE", "SHORT_GEMINI_SFT"),
    ("SHORT_GEMMA_SFT", "SHORT_GEMINI_SFT"),
)


@register("eval-pairs-v1")
class EvalPairsDoc(Strict):
    schemaVersion: Literal["eval-pairs-v1"] = "eval-pairs-v1"
    characterId: str
    preregSha256: str
    humanSampleSeed: int
    humanPairIds: list[str] = Field(default_factory=list)
    pairs: list[dict[str, Any]] = Field(default_factory=list)


def load_judge_prompt(name: str) -> str:
    return resources.files("character_factory_poc.prompts").joinpath(name).read_text("utf-8")


def ask_judge(
    judge: TextModel,
    *,
    prompt_name: str,
    user_text: str,
    ref: str,
    max_output_tokens: int = 600,
) -> dict[str, Any]:
    """판정 프롬프트를 system으로, 자료를 user로 보내 JSON 객체를 받는다."""
    role = load_judge_prompt(prompt_name)
    response = judge.complete(
        ChatRequest(
            kind="JUDGE",
            stage="s10",
            messages=(Message("system", role), Message("user", user_text)),
            ref=ref,
            max_output_tokens=max_output_tokens,
            temperature=0.0,
            response_json=True,
        )
    )
    try:
        obj = extract_json_object(response.text)
    except ValueError:
        return {"_error": "판정 응답이 JSON이 아니다"}
    return obj if isinstance(obj, dict) else {"_error": "판정 응답이 객체가 아니다"}


def _history_text(item: dict) -> str:
    lines = []
    for h in item.get("history", []):
        who = "사용자" if h["role"] == "user" else "캐릭터"
        lines.append(f"{who}: {h['content']}")
    return "\n".join(lines)


def _case_inputs(set_id: SetId, set_doc: dict, run: EvalRun) -> list[tuple[dict, int, str, str]]:
    """(set item, turn index, user text, reply) 목록. LONG200은 마지막 확인 질문만 쓴다."""
    by_item = {item.itemId: item for item in run.items}
    out: list[tuple[dict, int, str, str]] = []
    for item in set_doc["items"]:
        run_item = by_item.get(item["itemId"])
        if run_item is None or not run_item.turns:
            raise FactoryError(f"{set_id}: {item['itemId']} 응답이 없다")
        if set_id in {"OE", "SE"}:
            out.append((item, 0, item["question"], run_item.turns[0].reply))
            continue
        if set_id == "APOLOGY":
            turn_no = max(int(n) for n in item["recoveryTurns"])
        else:
            checks = [t for t in item["turns"] if t.get("kind") == "check"]
            turn_no = max(int(t["turn"]) for t in checks)
        idx = turn_no - 1
        if idx >= len(run_item.turns) or idx >= len(item["turns"]):
            raise FactoryError(f"{set_id}: {item['itemId']} {turn_no}턴 응답이 모자란다")
        out.append((item, idx, item["turns"][idx]["user"], run_item.turns[idx].reply))
    return out


def build_pair_cases(
    prereg: EvalPrereg, runs: dict[tuple[ArmId, SetId], EvalRun], set_docs: dict[SetId, dict]
) -> list[dict[str, Any]]:
    """조건 쌍 × 세트의 판정 사례를 고정 순서로 만든다. 아직 판정하지 않은 상태다."""
    cases: list[dict[str, Any]] = []
    n = 0
    for arm_a, arm_b in ARM_PAIRS:
        for spec in prereg.sets:
            run_a = runs[(arm_a, spec.setId)]
            run_b = runs[(arm_b, spec.setId)]
            doc = set_docs[spec.setId]
            a_by_item = {i.itemId: i for i in run_a.items}
            b_by_item = {i.itemId: i for i in run_b.items}
            for item, idx, user, reply_a in _case_inputs(spec.setId, doc, run_a):
                b_item = b_by_item.get(item["itemId"])
                if b_item is None or idx >= len(b_item.turns):
                    raise FactoryError(f"{spec.setId}: {item['itemId']} 반대 조건 응답이 없다")
                reply_b = b_item.turns[idx].reply
                n += 1
                cases.append(
                    {
                        "pairId": f"p{n:03d}",
                        "setId": spec.setId,
                        "itemId": item["itemId"],
                        "personaId": a_by_item[item["itemId"]].personaId,
                        "armA": arm_a,
                        "armB": arm_b,
                        "turn": idx + 1,
                        "user": user,
                        "history": _history_text(item) if spec.setId in {"OE", "SE"} else "",
                        "replyA": reply_a,
                        "replyB": reply_b,
                        "forward": "TIE",
                        "reverse": "TIE",
                        "consensus": "SPLIT",
                        "reasons": "",
                    }
                )
    return cases


def _pick(obj: dict[str, Any]) -> Literal["A", "B", "TIE"]:
    value = str(obj.get("pick", "TIE")).strip().upper()
    return value if value in {"A", "B", "TIE"} else "TIE"  # type: ignore[return-value]


def normalize_reverse(pick: str) -> str:
    """역순에서 A는 armB, B는 armA다. 정순 라벨(A=armA, B=armB)로 되돌린다."""
    return {"A": "B", "B": "A"}.get(pick, pick)


def consensus_of(forward: str, reverse: str) -> str:
    normalized = normalize_reverse(reverse)
    if forward == normalized:
        return forward
    return "SPLIT"


def judge_pair(judge: TextModel, case: dict[str, Any], *, cid: str, rev: str) -> dict[str, Any]:
    """한 사례를 정순·역순으로 판정해 consensus를 채운 사본을 돌려준다."""
    history = f"<history>\n{case['history']}\n</history>\n" if case.get("history") else ""
    base = f"{history}<user_turn>\n{case['user']}\n</user_turn>\n\n"
    forward = ask_judge(
        judge,
        prompt_name="eval_pair.md",
        user_text=(base + f"<A>\n{case['replyA']}\n</A>\n\n<B>\n{case['replyB']}\n</B>"),
        ref=f"{cid}/{rev}/pair/{case['pairId']}/forward",
    )
    reverse = ask_judge(
        judge,
        prompt_name="eval_pair.md",
        user_text=(base + f"<A>\n{case['replyB']}\n</A>\n\n<B>\n{case['replyA']}\n</B>"),
        ref=f"{cid}/{rev}/pair/{case['pairId']}/reverse",
    )
    f, r = _pick(forward), _pick(reverse)
    reasons = " | ".join(
        s
        for s in (
            str(forward.get("reasons", "")),
            str(reverse.get("reasons", "")),
            str(forward.get("_error", "")),
            str(reverse.get("_error", "")),
        )
        if s
    )
    return case | {
        "forward": f,
        "reverse": r,
        "consensus": consensus_of(f, r),
        "reasons": reasons[:600],
    }


def human_sample(pair_ids: list[str], count: int, seed: int = HUMAN_SAMPLE_SEED) -> list[str]:
    """고정 시드로 사람이 볼 쌍을 고른다. 같은 입력이면 언제나 같은 20쌍이다."""
    ids = sorted(pair_ids)
    if count >= len(ids):
        return ids
    return sorted(random.Random(seed).sample(ids, count))


def llm_human_agreement(
    picks: list[HumanPick], pairs: list[dict[str, Any]]
) -> tuple[float, int, int]:
    """(일치율, 일치 수, 비교 수). SPLIT은 LLM이 합의하지 못한 것으로 보고 불일치로 센다."""
    by_id = {p["pairId"]: p for p in pairs}
    matched = 0
    for pick in picks:
        case = by_id.get(pick.pairId)
        if case is None:
            raise FactoryError(f"사람 판정의 pairId가 표본에 없다: {pick.pairId}")
        if case["consensus"] != "SPLIT" and pick.pick == case["consensus"]:
            matched += 1
    total = len(picks)
    return (round(matched / total, 3) if total else 0.0), matched, total


def run_judge(ctx: Context, cid: str) -> Path:
    """judge만 따로 돌려 `pairs.json`을 쓴다. 보고서는 이 파일을 재사용할 수 있다."""
    prereg, digest, rev_dir = load_prereg(ctx, cid)
    runs = load_runs(prereg, rev_dir)
    set_docs = load_set_docs(prereg, ctx.character_dir(cid))
    cases = build_pair_cases(prereg, runs, set_docs)
    budget = ctx.budget()
    budget.check_plan([CallPlan("s10", f"LLM 짝 판정 {len(cases)}쌍 × 정순·역순", len(cases) * 2)])
    judge = ctx.judge_model(cid, budget)
    judged = [judge_pair(judge, c, cid=cid, rev=rev_dir.name) for c in cases]
    sample = human_sample([c["pairId"] for c in judged], prereg.humanPairs)
    doc = validate(
        "eval-pairs-v1",
        {
            "characterId": cid,
            "preregSha256": digest,
            "humanSampleSeed": HUMAN_SAMPLE_SEED,
            "humanPairIds": sample,
            "pairs": judged,
        },
    )
    write_once_json(rev_dir / "pairs.json", dump(doc))
    write_manifest(rev_dir)
    return rev_dir / "pairs.json"
