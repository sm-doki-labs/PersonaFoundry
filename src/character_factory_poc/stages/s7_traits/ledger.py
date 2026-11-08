"""S7 특질 장부(D-0091). 승인 기획 + 성격 시트 → trait-ledger-v1. 대화 프롬프트 조립의 원천이다."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from character_factory_poc.common.call_context import appearance_reading_problems
from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.trait_ledger import TraitLedger
from character_factory_poc.pipeline.agent import AgentSpec, run_agent

QUOTES = re.compile(r"[\"'“”‘’「」]")
#: 개념 겹침을 셀 때 빼는 흔한 낱말 앞 두 글자.
STOP = frozenset(
    (
        "상대 인물 자신 하는 하고 한다 있는 있다 않는 않고 않는다 때는 "
        "때도 경우 그리고 그러나 다만 먼저 이후 다시 조금 정도 대해 대한 "
        "위해 통해 그것 이것 모든 어떤 같은 된다 되는 하지 말을 말로 "
        "말이 대화 상황 행동 반응 마음 생각 무엇 지금 오늘 평소 기본 "
        "이야 이야기 "
    ).split()
)


def concept_tokens(text: str, exclude: tuple[str, ...] = ()) -> set[str]:
    """한글 낱말의 앞 두 글자를 어간 근사로 쓴다. 이름 같은 제외어와 흔한 낱말은 뺀다."""
    out = set()
    for word in re.findall(r"[가-힣]{2,}", text or ""):
        if any(word.startswith(e) for e in exclude if e):
            continue
        stem = word[:2]
        if stem not in STOP:
            out.add(stem)
    return out


def overlap(a: set[str], b: set[str]) -> float:
    """작은 쪽 기준 겹침 비율."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


#: D-0145: 기본 대응에 두면 거의 모든 턴에서 되풀이되는 평가·격려 시작과 감사·다짐 맺음.
DEFAULT_PRAISE = re.compile(r"잘하고 있|충분히 잘|편들|격려")
DEFAULT_THANKS_CLOSE = re.compile(r"(?:감사|다짐)[^.]{0,12}(?:맺|마무리)")

#: 같은 개념을 두 곳에 쓴 것으로 보는 겹침 비율(작은 쪽 기준).
DUP_THRESHOLD = 0.6


def check_ledger(name: str):
    exclude = (name[:2],) if name else ()

    def _check(ledger: TraitLedger) -> list[str]:
        problems: list[str] = []
        texts = _strings(dump(ledger))
        if any(QUOTES.search(t) for t in texts):
            problems.append("장부에 따옴표 대사나 인용을 넣지 않는다")
        problems += appearance_reading_problems("trait-ledger", " ".join(texts))
        if DEFAULT_PRAISE.search(ledger.defaultResponse) or DEFAULT_THANKS_CLOSE.search(
            ledger.defaultResponse
        ):
            problems.append(
                "defaultResponse: 상대 평가·격려로 시작하거나 감사·다짐으로 맺는 방식을 "
                "기본 대응에 두지 않는다. 그런 반응은 계기가 있는 trait에 둔다"
            )
        base = {
            **{f"disposition[{i}]": d for i, d in enumerate(ledger.disposition)},
            "coreTension": ledger.coreTension,
            "reading": ledger.reading,
            "defaultResponse": ledger.defaultResponse,
        }
        traits = {t.id: f"{t.trigger} {t.behavior}" for t in ledger.traits}
        for tid, ttext in traits.items():
            tt = concept_tokens(ttext, exclude)
            for key, btext in base.items():
                if overlap(tt, concept_tokens(btext, exclude)) >= DUP_THRESHOLD:
                    problems.append(
                        f"{key}: 조건부 특질 {tid}의 내용을 평소 모습 칸에 다시 썼다. "
                        "한 특질은 한 곳에만 쓴다"
                    )
        ids = list(traits)
        for i, a in enumerate(ids):
            for b in ids[i + 1 :]:
                ta = concept_tokens(traits[a], exclude)
                tb = concept_tokens(traits[b], exclude)
                if overlap(ta, tb) >= DUP_THRESHOLD:
                    problems.append(f"traits {a}·{b}: 계기와 행동이 겹친다. 하나로 합친다")
        for t in ledger.traits:
            if (
                overlap(concept_tokens(t.trigger, exclude), concept_tokens(t.nearMiss, exclude))
                >= 0.9
            ):
                problems.append(f"{t.id}.nearMiss: 계기와 거의 같다. 켜지지 않는 다른 상황을 쓴다")
        return problems

    return _check


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _example(cid: str, plan_rev: str) -> dict[str, Any]:
    return {
        "schemaVersion": "trait-ledger-v1",
        "characterId": cid,
        "planRev": plan_rev,
        "disposition": ["<대부분의 턴에서 드러나는 기본 성격>", "<기본 성격>"],
        "coreTension": "<핵심 긴장 한 문장>",
        "reading": "<평소 상대의 말을 받는 방식>",
        "defaultResponse": "<단서가 없을 때 하는 행동>",
        "traits": [
            {
                "id": f"t{i}",
                "kind": kind,
                "trigger": "<켜는 구체적 계기>",
                "nearMiss": "<비슷하지만 켜지지 않는 상황>",
                "behavior": "<관찰 가능한 행동 한 문장>",
                "rarity": "rare",
            }
            for i, kind in enumerate(("insult_reaction", "flaw", "misreading"), 1)
        ],
    }


def run_ledger(ctx, cid: str, plan, sheet, rev_dir: Path, budget, model) -> TraitLedger:
    raw_plan = {k: v for k, v in dump(plan).items() if k not in ("voiceExamples", "voiceSummary")}
    result = run_agent(
        AgentSpec("trait_ledger", "trait-ledger-v1", "s7", max_check_retries=1),
        rev_dir / "ledger-workspace",
        {
            "character-plan": raw_plan,
            "trait-sheet": {k: dump(sheet)[k] for k in ("choice", "card")},
        },
        [check_ledger(plan.name)],
        model,
        ref=f"{cid}/{rev_dir.name}/ledger",
        contract_example=_example(cid, plan.planRev),
        backend=ctx.agent_backend(cid, budget, "s7"),
    )
    if not result.ok:
        raise SystemExit("특질 장부 검사 실패:\n- " + "\n- ".join(result.problems))
    return result.output
