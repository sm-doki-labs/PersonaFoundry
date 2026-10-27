"""S8 프롬프트 조립·정렬·표본 (명세 §10.2, LLD §8.7)."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import Field

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.schema import dump, register, validate
from character_factory_poc.common.store import (
    next_rev,
    write_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.common.textstats import section_names
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.persona import PromptPair, PromptProbe, TraitSheet
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import render_gate_page
from character_factory_poc.pipeline.rework import load_rework
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.s3_plan.importer import load_approved_plan

FILLED_BY_FACTORY = ("SYSTEM_RULES", "OUTPUT")
OUTPUT_RULE = "캐릭터의 발화 텍스트만 출력한다. JSON, 따옴표, 라벨, 설명, 행동·장면 지문을 붙이지 않는다. 한 턴은 대개 짧은 1~2문장으로 끝내고 3문장을 넘기지 않는다."


@register("prompter-output-v1")
class PrompterOutput(Strict):
    long: dict[str, str] = Field(min_length=1)
    short: dict[str, str] = Field(min_length=1)


def load_sections() -> dict[str, Any]:
    return json.loads(
        resources.files("character_factory_poc.resources")
        .joinpath("prompt-sections-v1.json")
        .read_text("utf-8")
    )


def load_system_rules(ctx: Context) -> tuple[str, str]:
    path = (ctx.config.stage("s8").get("system_rules_path") or "").strip()
    if path:
        p = Path(path)
        return p.read_text("utf-8"), str(p)
    text = (
        resources.files("character_factory_poc.resources")
        .joinpath("system-rules-default-v1.md")
        .read_text("utf-8")
    )
    return text, "builtin:system-rules-default-v1"


def make_section_checks(sections: list[str], short_budget: dict[str, int]):
    def _check(out: PrompterOutput) -> list[str]:
        p = []
        for name, obj in (("long", out.long), ("short", out.short)):
            keys = set(obj)
            if keys != set(sections):
                p.append(
                    f"{name}: 섹션 집합이 다르다. 빠짐={sorted(set(sections) - keys)} 추가={sorted(keys - set(sections))}"
                )
            for s in FILLED_BY_FACTORY:
                if obj.get(s, "").strip():
                    p.append(f"{name}.{s}: 공장이 채우는 섹션이다. 비워 둔다")
            for s, body in obj.items():
                if s not in FILLED_BY_FACTORY and s in sections and not body.strip():
                    p.append(f"{name}.{s}: 비어 있다")
        for s, limit in short_budget.items():
            if s in out.short and len(out.short[s]) > limit:
                p.append(f"short.{s}: {len(out.short[s])}자가 예산 {limit}자를 넘는다")
        return p

    return _check


def assemble(sections: list[str], body: dict[str, str], name: str, system_rules: str) -> str:
    parts = []
    for s in sections:
        if s == "SYSTEM_RULES":
            text = system_rules.strip()
        elif s == "OUTPUT":
            text = OUTPUT_RULE
        elif s == "ACTOR_IDENTITY":
            text = f"캐릭터 이름: {name}\n" + body[s].strip()
        else:
            text = body[s].strip()
        parts.append(f"[{s}]\n{text}")
    return "\n\n".join(parts) + "\n"


def align_check(long_text: str, short_text: str, sections: list[str], short_max: int) -> list[str]:
    p = []
    ln, sn = section_names(long_text), section_names(short_text)
    if set(ln) != set(sn):
        p.append(f"섹션 집합 불일치: long={ln} short={sn}")
    if set(ln) != set(sections):
        p.append(f"섹션 목록과 다르다: {ln}")
    if len(short_text) > short_max:
        p.append(f"짧은 프롬프트 {len(short_text)}자가 상한 {short_max}자를 넘는다")
    if len(short_text) >= len(long_text):
        p.append("짧은 프롬프트가 긴 프롬프트보다 짧지 않다")
    return p


def plan_calls(retries: int, probes: int) -> list[CallPlan]:
    return [
        CallPlan("s8", f"Prompter 섹션 본문 생성 (재시도 포함 최대 {1 + retries}회)", 1 + retries),
        CallPlan("s8", f"말투 확인 문장 {probes}개 × (긴·짧은 응답 2 + 판정 1)", probes * 3),
    ]


def load_latest_trait_sheet(ctx: Context, cid: str) -> tuple[TraitSheet, Path]:
    state = ctx.state(cid)
    rev = state.stage("s7").currentRev
    if not rev or state.stage("s7").status not in {"AWAITING_HUMAN", "APPROVED"}:
        raise ValueError("S7 특질 시트가 없다. 먼저 cfp persona traits를 실행한다")
    p = ctx.character_dir(cid) / "s7-traits" / rev / "trait-sheet.json"
    return validate("trait-sheet-v1", json.loads(p.read_text("utf-8"))), p  # type: ignore[return-value]


def _resumable_rev(char_dir: Path, state) -> str | None:
    """직전 실행이 RUNNING으로 끊겼고 prompt-pair.json은 있는데 probe가 없으면 이어 간다(LLD §6.3)."""
    st = state.stage("s8")
    rev = st.currentRev
    if st.status != "RUNNING" or not rev:
        return None
    d = char_dir / "s8-prompts" / rev
    if (d / "prompt-pair.json").exists() and not (d / "prompt-probe.json").exists():
        return rev
    return None


def run_s8(
    ctx: Context, cid: str, voice_probes: list[str], allow_same_family: bool = False
) -> Path:
    plan, _ = load_approved_plan(ctx, cid)
    sheet, sheet_path = load_latest_trait_sheet(ctx, cid)
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    state.require_deps("s8")
    brief = load_rework(ctx, cid, "G6")
    s8cfg = ctx.config.stage("s8")
    retries = int(s8cfg.get("max_check_retries", 3))
    short_max = int(s8cfg.get("short_prompt_max_chars", 1500))
    sec = load_sections()
    sections: list[str] = sec["sections"]
    short_budget: dict[str, int] = sec.get("shortOnlyBudget", {})
    budget = ctx.budget()
    resume_rev = _resumable_rev(char_dir, state)
    if resume_rev:
        rev_dir = char_dir / "s8-prompts" / resume_rev
        pair = validate(
            "prompt-pair-v1", json.loads((rev_dir / "prompt-pair.json").read_text("utf-8"))
        )
        probe_doc = run_probes(ctx, cid, budget, pair, sheet, voice_probes, allow_same_family)
        _finish_s8(cid, state, rev_dir, resume_rev, plan, sheet, pair, probe_doc)
        return rev_dir
    budget.check_plan(plan_calls(retries, len(voice_probes)))
    rev = next_rev(char_dir / "s8-prompts", "pv")
    rev_dir = char_dir / "s8-prompts" / rev
    state.transition("s8", "RUNNING", rev=rev)

    model = ctx.text_model(cid, budget)
    spec = AgentSpec(
        role="prompter", output_contract="prompter-output-v1", stage="s8", max_check_retries=retries
    )
    inputs: dict[str, Any] = {
        "trait-sheet": dump(sheet),
        "sections": sections,
        "shortBudget": short_budget,
        "character-name.txt": plan.name,
    }
    if brief is not None:
        inputs["revision"] = {
            "gate": brief.gate,
            "round": brief.round,
            "targets": [t.field for t in brief.targets],
            "notes": {t.field: t.note for t in brief.targets},
            "instructions": brief.instructions,
            "keep": brief.keep,
        }
    result = run_agent(
        spec,
        rev_dir / "workspace",
        inputs,
        [make_section_checks(sections, short_budget)],
        model,
        ref=f"{cid}/{rev}",
        contract_example={"long": {s: "" for s in sections}, "short": {s: "" for s in sections}},
        backend=ctx.agent_backend(cid, budget, "s8"),
    )
    if not result.ok:
        state.transition("s8", "CHECK_FAILED", rev=rev, error="; ".join(result.problems))
        raise SystemExit(
            f"S8 자동 검사 실패({result.attempts}회):\n- " + "\n- ".join(result.problems)
        )
    out: PrompterOutput = result.output
    rules_text, rules_ref = load_system_rules(ctx)
    long_text = assemble(sections, out.long, plan.name, rules_text)
    short_text = assemble(sections, out.short, plan.name, rules_text)
    problems = align_check(long_text, short_text, sections, short_max)
    if problems:
        state.transition("s8", "CHECK_FAILED", rev=rev, error="; ".join(problems))
        raise SystemExit("S8 정렬 검사 실패:\n- " + "\n- ".join(problems))

    pair = PromptPair(
        characterId=cid,
        personaVersion=None,
        traitSheetSha256=sha256_text(sheet_path.read_text("utf-8")),
        sections=sections,
        long={"text": long_text, "sha256": sha256_text(long_text), "chars": len(long_text)},
        short={"text": short_text, "sha256": sha256_text(short_text), "chars": len(short_text)},
        systemRulesRef=rules_ref,
        systemRulesSha256=sha256_text(rules_text),
        shortAdopted=False,
    )
    write_once_json(rev_dir / "prompt-pair.json", dump(pair))
    write_once_text(rev_dir / "long.md", long_text)
    write_once_text(rev_dir / "short.md", short_text)

    probe_doc = run_probes(ctx, cid, budget, pair, sheet, voice_probes, allow_same_family)
    _finish_s8(cid, state, rev_dir, rev, plan, sheet, pair, probe_doc)
    return rev_dir


def _probe_path(rev_dir: Path) -> Path:
    """첫 표본은 prompt-probe.json, 재실행은 prompt-probe-r<k>.json (JSON은 불변, 페이지는 파생)."""
    p = rev_dir / "prompt-probe.json"
    if not p.exists():
        return p
    k = 2
    while (rev_dir / f"prompt-probe-r{k}.json").exists():
        k += 1
    return rev_dir / f"prompt-probe-r{k}.json"


def _finish_s8(cid, state, rev_dir: Path, rev: str, plan, sheet, pair, probe_doc) -> None:
    long_text, short_text = pair.long.text, pair.short.text
    write_once_json(_probe_path(rev_dir), dump(probe_doc))
    page = render_gate_page(
        title=f"G6 페르소나 검토 · {plan.name} · {rev}",
        subject_id=cid,
        gate="G6",
        rev=rev,
        sections=[
            ("특질 시트", json.dumps(dump(sheet), ensure_ascii=False, indent=2)),
            (f"긴 프롬프트 ({pair.long.chars}자)", long_text),
            (f"짧은 프롬프트 ({pair.short.chars}자) · 운영 미채택(D-0006)", short_text),
        ],
        side_by_side=[(p.sentence, p.longResponse, p.shortResponse) for p in probe_doc.probes],
    )
    (rev_dir / "gate-G6.html").write_text(page, encoding="utf-8")  # 파생 뷰라 덮어쓴다
    write_manifest(rev_dir)
    if state.stage("s8").status != "AWAITING_HUMAN":
        state.transition("s8", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G6", "AWAITING_HUMAN", rev, None)


def rerun_probes(
    ctx: Context, cid: str, voice_probes: list[str], allow_same_family: bool = False
) -> Path:
    """고정된 프롬프트 쌍은 두고 말투 확인 표본만 다시 돌린다 (cfp persona probe)."""
    plan, _ = load_approved_plan(ctx, cid)
    sheet, _ = load_latest_trait_sheet(ctx, cid)
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    st = state.stage("s8")
    if st.status not in {"AWAITING_HUMAN", "RUNNING"} or not st.currentRev:
        raise ValueError(f"S8 프롬프트 쌍이 없다(상태 {st.status})")
    rev_dir = char_dir / "s8-prompts" / st.currentRev
    pair = validate("prompt-pair-v1", json.loads((rev_dir / "prompt-pair.json").read_text("utf-8")))
    budget = ctx.budget()
    budget.check_plan([plan_calls(0, len(voice_probes))[1]])
    probe_doc = run_probes(ctx, cid, budget, pair, sheet, voice_probes, allow_same_family)
    _finish_s8(cid, state, rev_dir, st.currentRev, plan, sheet, pair, probe_doc)
    return rev_dir


def _char_summary(sheet: TraitSheet) -> str:
    c = sheet.choice
    return (
        f"주목: {c.attention}\n해석·우선점: {c.interpretationPriority}\n주된 대응: {c.primaryResponse}\n"
        f"표현 강도: {c.expressionIntensity}\n태세: {sheet.card.stance}"
    )


def run_probes(
    ctx,
    cid,
    budget,
    pair: PromptPair,
    sheet: TraitSheet,
    sentences: list[str],
    allow_same_family: bool,
) -> PromptProbe:
    if not sentences:
        return PromptProbe(
            characterId=cid,
            promptPairSha256=sha256_text(pair.long.text),
            probes=[],
            judgeModel="none",
        )
    text_model = ctx.text_model(cid, budget)
    judge = ctx.judge_model(cid, budget, allow_same_family)
    judge_role = (
        resources.files("character_factory_poc.prompts")
        .joinpath("probe_judge.md")
        .read_text("utf-8")
    )
    probes = []
    import secrets

    rng = secrets.SystemRandom()
    for i, s in enumerate(sentences):
        responses = {}
        for cond, system in (("LONG", pair.long.text), ("SHORT", pair.short.text)):
            r = text_model.complete(
                ChatRequest(
                    kind="PROBE",
                    stage="s8",
                    messages=(Message("system", system), Message("user", s)),
                    ref=f"{cid}/probe{i}/{cond}",
                    max_output_tokens=1500,
                    temperature=0.8,
                )
            )
            responses[cond] = r.text.strip()
        # 판정 입력 익명화: A/B 순서를 무작위로 (NFR-02)
        order = ["LONG", "SHORT"]
        if rng.random() < 0.5:
            order.reverse()
        a, b = responses[order[0]], responses[order[1]]
        jr = judge.complete(
            ChatRequest(
                kind="JUDGE",
                stage="s8",
                messages=(
                    Message("system", judge_role),
                    Message(
                        "user",
                        f"<character>\n{_char_summary(sheet)}\n</character>\n\n"
                        f"<user_turn>{s}</user_turn>\n\n<A>{a}</A>\n\n<B>{b}</B>",
                    ),
                ),
                ref=f"{cid}/probe{i}/judge",
                max_output_tokens=300,
                temperature=0.0,
                response_json=True,
            )
        )
        try:
            jo = extract_json_object(jr.text)
            pick = str(jo.get("pick", "NONE")).upper()
            reasons = str(jo.get("reasons", ""))
        except ValueError:
            pick, reasons = "NONE", "판정 응답 형식 오류"
        mapped = {"A": order[0], "B": order[1]}.get(
            pick, pick if pick in {"TIE", "BOTH_BAD"} else "NONE"
        )
        probes.append(
            {
                "sentence": s,
                "longResponse": responses["LONG"],
                "shortResponse": responses["SHORT"],
                "judge": {"pick": mapped, "reasons": reasons},
            }
        )
    return PromptProbe(
        characterId=cid,
        promptPairSha256=sha256_text(pair.long.text),
        probes=probes,
        judgeModel=judge.model,
    )
