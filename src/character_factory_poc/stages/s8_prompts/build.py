"""S8 프롬프트 조립·정렬·표본 (명세 §10.2, LLD §8.7)."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from pydantic import Field

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.schema import dump, register, validate
from character_factory_poc.common.store import (
    next_rev,
    read_json,
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
from character_factory_poc.pipeline.origin import SOURCE, read_origin
from character_factory_poc.pipeline.rework import load_rework
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s8_prompts.source import (
    canonical_sections,
    project_plan,
    with_creator_traits,
)
from character_factory_poc.stages.s8_prompts.twin import approved_voice, motif_limits, voice_lines

FILLED_BY_FACTORY = ("SYSTEM_RULES", "OUTPUT")
OUTPUT_RULE = "캐릭터가 실제로 할 말만 출력한다. JSON·라벨·해설·행동 지문은 쓰지 않는다. 보통 짧은 1~3문장으로 답하고 필요하면 말풍선처럼 줄을 나눈다. 답변 틀을 채우려고 이유·대안·질문을 덧붙이지 않는다."


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


def assemble(
    sections: list[str],
    body: dict[str, str],
    name: str,
    system_rules: str,
    canonical: dict[str, str] | None = None,
    *,
    creator_plan=None,
) -> str:
    body = body | (canonical or {})
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
        if s == "PERSONA / DISPOSITION" and creator_plan is not None:
            text = with_creator_traits(text, creator_plan)
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
    twin = read_origin(ctx.character_dir(cid)) == SOURCE
    if not twin and ctx.config.stage("s7").get("formation_profile"):
        from character_factory_poc.stages.s8_prompts.formation import run_formation_s8

        return run_formation_s8(ctx, cid, voice_probes)
    if ctx.text_deck_enabled:
        return run_deck_s8(ctx, cid, voice_probes)
    plan, plan_path = load_approved_plan(ctx, cid)
    sheet, sheet_path = load_latest_trait_sheet(ctx, cid)
    char_dir = ctx.character_dir(cid)
    state = ctx.state(cid)
    state.require_deps("s8")
    brief = load_rework(ctx, cid, "G6")
    s8cfg = ctx.config.stage("s8")
    retries = int(s8cfg.get("max_check_retries", 3))
    short_max = int(s8cfg.get("short_prompt_max_chars", 2400))
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
    rules_text, rules_ref = load_system_rules(ctx)
    source = project_plan(plan, sha256_file(plan_path))
    canonical = canonical_sections(source, sheet)
    if twin:
        source["sourceVoice"] = approved_voice(ctx, cid, plan)
        canonical["PERSONA / VOICE"] = "\n".join(
            voice_lines(plan.voiceSummary, source["sourceVoice"])
        )
    empty_body = {s: "" for s in sections}
    base_chars = len(
        assemble(sections, empty_body, plan.name, rules_text, canonical, creator_plan=plan)
    )
    if base_chars > short_max:
        raise ValueError(f"정본 {base_chars}자가 짧은 프롬프트 상한 {short_max}자를 넘는다")
    generated = [s for s in sections if s not in canonical and s not in FILLED_BY_FACTORY]
    available = short_max - base_chars
    total_budget = sum(short_budget.get(s, 0) for s in generated)
    minimum = 24
    if available < minimum * len(generated):
        raise ValueError("정본 보존 뒤 생성 본문 예산이 부족하다. short 상한을 늘려야 한다")
    short_budget = dict(short_budget)
    if total_budget > available:
        for s in generated:
            short_budget[s] = minimum + int(
                short_budget.get(s, 0) * (available - minimum * len(generated)) / total_budget
            )
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
        "character-plan": source,
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
    long_text = assemble(sections, out.long, plan.name, rules_text, canonical, creator_plan=plan)
    short_text = assemble(sections, out.short, plan.name, rules_text, canonical, creator_plan=plan)
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
    write_once_json(rev_dir / "source-plan.json", source)
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


def run_deck_s8(ctx: Context, cid: str, voice_probes: list[str]) -> Path:
    """Preserve approved prose; the compatibility short slot is an uncompressed copy."""
    from character_factory_poc.stages.s8_prompts.actor_persona import (
        compose_approved_sheet,
        load_actor_rules,
    )

    if not ctx.execute:
        raise ValueError("--execute is required")
    if voice_probes:
        raise ValueError(
            "모델 덱 제작은 대화 시험을 자동 수행하지 않는다. 개발 평가는 별도로 실행한다"
        )
    state = ctx.state(cid)
    state.require_deps("s8")
    plan, plan_path = load_approved_plan(ctx, cid)
    sheet, sheet_path = load_latest_trait_sheet(ctx, cid)
    rules, rules_ref = load_actor_rules(ctx)
    source = project_plan(plan, sha256_file(plan_path))
    voice = None
    limits = None
    if read_origin(ctx.character_dir(cid)) == SOURCE:
        source["sourceVoice"] = approved_voice(ctx, cid, plan)
        voice = voice_lines(plan.voiceSummary, source["sourceVoice"])
        limits = motif_limits()
    ledger_path = sheet_path.parent / "trait-ledger.json"
    if ledger_path.exists():
        from character_factory_poc.stages.s8_prompts.actor_persona import compose_from_ledger

        ledger = validate("trait-ledger-v1", json.loads(ledger_path.read_text("utf-8")))
        text, sections = compose_from_ledger(
            plan, ledger, rules_text=rules, voice=voice, limits=limits
        )
        compiler = "actor-trait-ledger-v1"
    else:
        text, sections = compose_approved_sheet(
            plan, sheet, rules_text=rules, voice=voice, limits=limits
        )
        compiler = "actor-approved-sheet-v1"
    from character_factory_poc.common.errors import NeedsInputError

    gate = state.gate("G6")
    previous = ctx.character_dir(cid) / "s8-prompts" / str(gate.rev)
    record = read_json(ctx.character_dir(cid) / gate.recordRef) if gate.recordRef else {}
    rework = load_rework(ctx, cid, "G6")
    if rework is not None or record.get("decision") == "REQUEST_CHANGES":
        old_pair = previous / "prompt-pair.json"
        if old_pair.exists() and read_json(old_pair)["long"]["sha256"] == sha256_text(text):
            raise NeedsInputError(
                "G6 수정 요청이 남아 있다. S3/S7 원천이나 시스템 규칙을 먼저 수정한 뒤 조립한다"
            )
    source_binding_path = sheet_path.parent / "text-deck-binding.json"
    source_generation = (
        read_json(source_binding_path)
        if source_binding_path.exists()
        else dict(status="legacy_or_unknown", responseModel=None, binding=None)
    )
    if source_generation.get("traitSheetSha256", sha256_file(sheet_path)) != sha256_file(
        sheet_path
    ):
        raise ValueError("trait source generation binding hash mismatch")
    limit = int(ctx.config.stage("s8").get("long_prompt_max_chars", 8000))
    if len(text) > limit:
        raise ValueError(f"정본 {len(text)}자가 S8 상한 {limit}자를 넘는다. 내용을 자르지 않는다")
    folder = ctx.character_dir(cid) / "s8-prompts"
    rev = next_rev(folder, "pv")
    folder = folder / rev
    state.transition("s8", "RUNNING", rev=rev)
    content = dict(text=text, sha256=sha256_text(text), chars=len(text))
    pair = PromptPair(
        characterId=cid,
        traitSheetSha256=sha256_file(sheet_path),
        sections=list(sections),
        long=content,
        short=content,
        systemRulesRef=rules_ref,
        systemRulesSha256=sha256_text(rules),
        shortAdopted=False,
    )
    write_once_json(folder / "source-plan.json", source)
    write_once_json(
        folder / "text-deck-binding.json",
        dict(
            selectedConfiguration=ctx.config.text_binding("voice"),
            sourceGeneration=source_generation,
            completionCheck="NOT_RUN",
            compiler=compiler,
            planSha256=sha256_file(plan_path),
            traitSheetSha256=sha256_file(sheet_path),
            shortPolicy="uncompressed-identical-copy; not a qualified short prompt",
        ),
    )
    write_once_json(folder / "prompt-pair.json", dump(pair))
    write_once_text(folder / "long.md", text)
    write_once_text(folder / "short.md", text)
    probe = PromptProbe(
        characterId=cid,
        promptPairSha256=sha256_file(folder / "prompt-pair.json"),
        probes=[],
        judgeModel="",
        note="제작 중 대화 시험 미실행; short는 압축하지 않은 동일 본문",
    )
    _finish_s8(cid, state, folder, rev, plan, sheet, pair, probe)
    return folder
