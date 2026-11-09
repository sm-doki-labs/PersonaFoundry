"""S7 특질 장부(D-0091). 승인 기획 + 성격 시트 → trait-ledger-v1. 대화 프롬프트 조립의 원천이다."""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Any

from character_factory_poc.common.call_context import appearance_reading_problems
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.trait_ledger import TraitLedger
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.origin import SOURCE, read_origin
from character_factory_poc.stages.s3_plan import tendencies as T

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
#: D-0146: 말하는 방식은 말투 칸이 소유한다(MD-1.4, D-0090). 평소 칸에서 분명한 말투 낱말만 잡는다.
VOICE_TERMS = re.compile(
    r"단정을|단정하지|누그러뜨|어미|말투|말버릇|말끝|존댓말|반말|높임"
    r"|해요체|하십시오체|말을 맺|끝맺"
)

#: 같은 개념을 두 곳에 쓴 것으로 보는 겹침 비율(작은 쪽 기준).
DUP_THRESHOLD = 0.6


def demo_situations() -> dict[str, str]:
    path = resources.files("character_factory_poc").joinpath(
        "resources/motif-demo-situations-v1.json"
    )
    return json.loads(path.read_text("utf-8"))


# S3의 JOKE는 시연의 TEASE와 같다. 가족 이야기나 본인의 감정은 사생활 질문·상대 고민과 다르다.
def _situation(cell: str) -> str:
    key = cell.split("/")[0]
    return "TEASE" if key == "JOKE" else key


# 막연한 말투·길이와 구별할 수 있는 화행이나 구체적인 말의 내용이 있는지 본다.
_ACTION = re.compile(
    r"되묻|되물|맞받|받아치|받아친|바로잡|되짚|짚어|짚고|돌려주|돌려준|물어|묻는|"
    r"(?:인정|거절|사과|공감|제안|칭찬|반문|격려|응원|확인|정정|반박|수긍|권유)"
    r"(?:부터 |을 |를 )?(?:한|하|해)|"
    r"권한|권하|덧붙|보탠|보태|털어놓|들려[주준]|말을 아[끼낀]|"
    r"선을 (?:긋|그어)|화제를 (?:돌|바|닫)|[다냐자]고 (?:말|답|한|밝|알)|"
    r"(?:경험|사례|이유|사실|기억|질문|농담|감사|예시|일화)[을를] [가-힣]+"
)


def check_ledger(name: str, tendencies: dict | None = None, source_refs: set[str] | None = None):
    exclude = (name[:2],) if name else ()
    rows = (tendencies or {}).get("tendencies", [])
    shares = {t["cell"]: t.get("share", 0) for t in rows}
    cells = shares.keys()
    motif = tendencies is not None
    required = demo_situations() if motif else {}
    covered = {_situation(cell) for cell in cells}

    def _check(ledger: TraitLedger) -> list[str]:
        problems: list[str] = []
        if motif:
            # D-0148: 모티브의 조건부 특질은 원문의 주요 경향에서만 고르고, 한 상황에 하나만 둔다.
            seen: dict[str, str] = {}
            for t in ledger.traits:
                if not _ACTION.search(t.behavior):
                    problems.append(
                        f"{t.id}.behavior: 말투만 적지 말고 구체적으로 무엇을 하는지 쓴다"
                    )
                if t.basis == "INFERRED":
                    if t.sourceRef not in (source_refs or set()):
                        problems.append(f"{t.id}.sourceRef: 승인 기획 SOURCE 근거의 ref를 쓴다")
                    sit = t.demoSituation
                    if sit not in required or sit in covered:
                        problems.append(f"{t.id}: 추론은 주요 경향이 없는 시연 상황에서만 쓴다")
                        continue
                elif t.basis in cells:
                    sit = _situation(t.basis)
                    if any(_situation(c) == sit and shares[c] > shares[t.basis] for c in cells):
                        problems.append(f"{t.id}.basis: 그 상황에서 비중이 가장 큰 경향을 쓴다")
                    if t.demoSituation and sit != t.demoSituation:
                        problems.append(f"{t.id}: 시연 상황과 원문 경향의 상황이 다르다")
                else:
                    problems.append(
                        f"{t.id}.basis: tendencies.tendencies의 cell 가운데 하나를 쓴다. "
                        "원문에서 드물게 나온 반응(minor)은 조건부 특질로 만들지 않는다"
                    )
                    continue
                if sit in seen:
                    problems.append(
                        f"{seen[sit]}·{t.id}: 같은 상황({sit})의 경향은 trait 하나로 합치고 "
                        "behavior에 주요 반응을 비중 순서대로 함께 쓴다"
                    )
                seen.setdefault(sit, t.id)
            for missing in sorted(required.keys() - seen.keys()):
                problems.append(f"시연 상황 {missing}: 선택이 하나 필요하다")
        elif any(t.basis or t.demoSituation or t.sourceRef for t in ledger.traits):
            problems.append("traits.basis: 원문 경향이 없는 캐릭터는 basis를 쓰지 않는다")
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
        for key, btext in base.items():
            if found := VOICE_TERMS.search(btext):
                problems.append(
                    f"{key}: 말하는 방식('{found.group(0)}')은 말투 칸이 소유한다. "
                    "평소 칸에는 무엇을 하는지만 쓴다"
                )
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


def _example(cid: str, plan_rev: str, motif: bool = False) -> dict[str, Any]:
    situations = list(demo_situations()) if motif else []
    kinds = ["choice"] * len(situations) if motif else ["insult_reaction", "flaw", "misreading"]
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
                **(
                    {
                        "basis": "<주요 경향 cell 또는 INFERRED>",
                        "demoSituation": situations[i - 1],
                        "sourceRef": "<추론한 경우 승인 기획의 SOURCE ref>",
                    }
                    if motif
                    else {}
                ),
            }
            for i, kind in enumerate(kinds, 1)
        ],
    }


def motif_tendencies(ctx, cid: str, plan_rev: str) -> dict | None:
    """모티브 G3 revision의 원문 경향. 오리지널만 None이고, 모티브에는 빈 경향 목록도 전달한다."""
    if read_origin(ctx.character_dir(cid)) != SOURCE:
        return None
    path = ctx.character_dir(cid) / "s3-plan" / plan_rev / "tendencies.json"
    if not path.is_file():
        return {"tendencies": []}
    agg = read_json(path)
    return T.agent_view(agg)


def run_ledger(ctx, cid: str, plan, sheet, rev_dir: Path, budget, model) -> TraitLedger:
    raw_plan = {k: v for k, v in dump(plan).items() if k not in ("voiceExamples", "voiceSummary")}
    tendencies = motif_tendencies(ctx, cid, plan.planRev)
    inputs = {
        "character-plan": raw_plan,
        "trait-sheet": {k: dump(sheet)[k] for k in ("choice", "card")},
    }
    if tendencies is not None:
        inputs["tendencies"] = tendencies
        inputs["demo-situations"] = demo_situations()
    source_refs = {e.ref for refs in plan.evidence.values() for e in refs if e.kind == "SOURCE"}
    result = run_agent(
        AgentSpec("trait_ledger", "trait-ledger-v1", "s7", max_check_retries=1),
        rev_dir / "ledger-workspace",
        inputs,
        [check_ledger(plan.name, tendencies, source_refs)],
        model,
        ref=f"{cid}/{rev_dir.name}/ledger",
        contract_example=_example(cid, plan.planRev, tendencies is not None),
        backend=ctx.agent_backend(cid, budget, "s7"),
    )
    if not result.ok:
        raise SystemExit("특질 장부 검사 실패:\n- " + "\n- ".join(result.problems))
    return result.output
