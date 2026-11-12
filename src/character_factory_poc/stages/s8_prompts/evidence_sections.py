"""evidence-v10: section-driven candidates with per-section targets, caps and one top-up.

Each of the seven persona sections searches for its own candidates (S3 whole-source notes plus
the development text), every responding turn is labelled once, and code counts support. A
section that ends below its target gets one supplementary search for that section only; what
is still missing is recorded as a shortfall, never invented (D-0179, K-0116). VOICE always
carries the measured speech distribution from S3 and its cards add to it (D-0202).
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.store import write_once_json
from character_factory_poc.stages.s8_prompts.evidence_compiler import compile_prompt
from character_factory_poc.stages.s8_prompts.evidence_source import validate_card
from character_factory_poc.stages.s8_prompts.evidence_tendencies import (
    _labeled_partition,
    aggregate,
    labeled_call,
    s3_observations,
    state_for,
    to_card,
)

SECTIONED_VERSION = "evidence-pipeline-v10"
# (target, candidates, cap). Targets follow the larger of the two reference prompts
# (Ikjun pv6, Son v2). VOICE counts measured lines toward its target of 8.
SECTION_PLAN = {
    "VOICE": (8, 8, 8),
    "DISPOSITION": (4, 6, 6),
    "CHOICES": (3, 6, 6),
    "LIFE_AND_TASTES": (3, 6, 6),
    "READING_AND_TENSION": (2, 5, 5),
    "WANTS_AND_FEARS": (2, 5, 5),
    "KNOWS_AND_LIMITS": (2, 3, 3),
}
SELF_REPORT = {"LIFE_AND_TASTES", "WANTS_AND_FEARS"}
# Support units: conversations for chat, distinct sources (interviews) for interview text.
# Self-report sections use the same 20% share as behaviour: "this can happen when the topic
# comes up". 50% dropped well-supported tastes (Ikjun: 9 conversations at 49%).
RULES = {
    "conversation": dict(behavior=(8, 0.2), self_report=(2, 0.2)),
    "interview": dict(behavior=(3, 0.2), self_report=(2, 0.2)),
}
# Labeler speed settings ([stages.s8]): a call still running after evidence_hedge_s seconds is
# sent once more and the first answer wins (0 turns it off; the first candidate call waits twice
# as long because it is the largest). Labelling and the top-up search use
# evidence_light_reasoning ("" keeps the provider default); the first candidate search keeps
# the provider default because it reads the whole development text and writes every card.
HEDGE_S = 240
LIGHT_REASONING = "low"
# Cards whose function corrects or denies what the other person said get a fixed limit so they
# are not used to deny unverified private events (Son: "그런 적 없다" to an invented dinner).
CORRECTION = re.compile(r"정정|바로잡|오해|와전|반박|부인|부정하|선을 긋")
CORRECTION_LIMIT = (
    " 사실표나 현재 대화로 확인되지 않는 개인 일정·만남·대화를 묻는 질문에는 적용하지 않고,"
    " 그런 질문은 부정도 인정도 하지 않는다."
)
# A trigger listing this many items (split on commas, 또는, 혹은) is a topic list.
TOPIC_LIST_LIMIT = 4


def topic_items(trigger):
    return len([p for p in re.split(r",|또는|혹은", trigger) if p.strip()])


def card_problem(claim):
    """Deterministic backstops for the v10 card rules; None when the claim is acceptable."""
    n = topic_items(claim["trigger"])
    if n >= TOPIC_LIST_LIMIT:
        return f"적용 상황이 화제 나열이다({n}개 항목). 일반 상황 하나로 써야 한다"
    for k in ("realization", "exclusion"):
        if re.search(r"\d", claim[k]):
            return f"{k}에 숫자가 있다. 개인 사실은 statedFacts로 옮긴다"
    return None


def speed_settings(cfg):
    hedge = cfg.get("evidence_hedge_s", HEDGE_S)
    light = cfg.get("evidence_light_reasoning", LIGHT_REASONING)
    if type(hedge) not in (int, float) or hedge < 0:
        raise ValueError("evidence_hedge_s는 0 이상의 초다")
    if not isinstance(light, str):
        raise ValueError("evidence_light_reasoning은 문자열이다")
    return dict(hedgeSeconds=hedge, lightReasoning=light or None)


def _standard(binding):
    record = binding.get("textStandard") or {}
    return "interview" if record.get("standard") == "interview" else "conversation"


def _unit_key(standard):
    return (lambda unit: unit[0]) if standard == "interview" else tuple


def section_rule(section, standard, available=None):
    """available caps the unit count at what the source has, as v9's support_rule does."""
    kind = "self_report" if section in SELF_REPORT else "behavior"
    n, share = RULES[standard][kind]
    if available is not None:
        n = max(1, min(n, available))
    return dict(section=section, kind=kind, minUnits=n, minShare=share)


def _stats(d, v, units, key):
    support = set(d["support"]) | set(v["support"])
    variation = (set(d["variation"]) | set(v["variation"])) - support
    applicable = len(support) + len(variation)
    return dict(
        responses=len(support),
        units=len({key(units[r]) for r in support}),
        developmentUnits=len({key(units[r]) for r in d["support"]}),
        confirmationUnits=len({key(units[r]) for r in v["support"]}),
        applicable=applicable,
        share=round(len(support) / applicable, 4) if applicable else 0.0,
    )


def _judge(claim, d, v, stats, rule, min_confirm):
    """Return (state, None) when the candidate is kept, else (state, reason)."""
    if claim["section"] not in SECTION_PLAN:
        return None, "알 수 없는 섹션"
    if claim["observability"] != "prior_context":
        return None, "응답 이전에 확인할 수 없는 적용 조건"
    if rule["kind"] == "behavior":
        state = state_for(d, v, min_confirm)
        if state == "insufficient":
            return state, (
                "기능과 언어 형식의 공동 반복 근거 부족"
                f"(발견 쪽 {d['supportUnits']}건·확인용 원문 {v['supportUnits']}건)"
            )
    else:
        state = "mixed" if (d["variation"] or v["variation"]) else "evidence_present"
    few = stats["units"] < rule["minUnits"]
    low = not stats["applicable"] or stats["share"] < rule["minShare"]
    if few or low:
        what = "·".join(x for x, bad in [("근거 단위 수", few), ("지지 비율", low)] if bad)
        return state, (
            f"지지 근거가 얇다({what} 미달): 지지 단위 {stats['units']}개"
            f"(기준 {rule['minUnits']}개), 지지 {stats['responses']}/{stats['applicable']}건"
            f"({stats['share']:.0%}, 기준 {rule['minShare']:.0%})"
        )
    return state, None


def _voice_lines(packet):
    """Measured lines that describe speech; the basis and priority notes are not habits."""
    meta = ("측정 기준:", "우선순위:")
    return sum(not line.startswith(meta) for line in packet.get("voice") or [])


def _targets(packet):
    out = {s: t for s, (t, _, _) in SECTION_PLAN.items()}
    out["VOICE"] = max(0, out["VOICE"] - _voice_lines(packet))
    return out


def build_sections(ctx, cid, packet, source, binding, folder, budget, rework=None):
    from character_factory_poc.common.budget import CallPlan
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import (
        atomic_retry_remaining,
    )

    folder = Path(folder)
    if not source.get("coverage", {}).get("complete"):
        raise ValueError("전체 원문 범위 미완료")
    standard = _standard(binding)
    key = _unit_key(standard)
    dev, confirm, split = _labeled_partition(source)
    if budget is not None:
        hedged = speed_settings(ctx.config.stage("s8"))["hedgeSeconds"] > 0
        budget.check_plan(
            [CallPlan("s8", "섹션별 후보와 응답별 표시", plan_count(dev, confirm, hedged), None)]
        )
        if atomic_retry_remaining(folder) <= 0:
            raise ValueError("분석 재시도 여유가 없다")
    workers = ctx.config.stage("s8").get("evidence_workers", 2)
    if type(workers) is not int or not 1 <= workers <= 4:
        raise ValueError("evidence_workers는 1~4다")
    common = {k: packet[k] for k in ["role", "scene", "facts"]}
    if rework:
        common["editorRevision"] = rework
    for name, value in [
        ("coverage", source["coverage"]),
        ("chunks", source["chunks"]),
        ("binding", binding),
        ("partition", split),
    ]:
        write_once_json(folder / f"evidence-{name}.json", value)
    observations = s3_observations(ctx, cid, dev)
    write_once_json(folder / "evidence-observations.json", observations)
    allowed = sorted({r for ch in dev for r in ch["recordIds"]})
    dev_all = dict(
        id="dev-all", segments=[s for ch in dev for s in ch["segments"]], recordIds=allowed
    )
    targets_by_section = _targets(packet)
    speed = speed_settings(ctx.config.stage("s8"))
    hedge_log = folder / "analysis" / "hedge-log.jsonl"

    def note_hedge(ref, after):
        import json
        import time

        hedge_log.parent.mkdir(parents=True, exist_ok=True)
        with hedge_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(ref=ref, afterSeconds=after, at=time.time())) + "\n")

    def run(ctx, cid, folder, budget, phase, key_name, payload):
        from character_factory_poc.providers.hedged import HedgedTextModel

        first = phase == "tendency-consolidate" and key_name == "all"
        reasoning = None if first else speed["lightReasoning"]
        after = speed["hedgeSeconds"] * (2 if first else 1)

        def model_for(c, b):
            return HedgedTextModel(ctx.labeler_model(c, b, reasoning), after, note_hedge)

        return labeled_call(
            ctx,
            cid,
            folder,
            budget,
            phase,
            key_name,
            payload,
            version=SECTIONED_VERSION,
            model_for=model_for,
        )

    def candidates(key_name, quota, existing):
        out, model = run(
            ctx,
            cid,
            folder,
            budget,
            "tendency-consolidate",
            key_name,
            dict(
                **common,
                observations=[
                    {k: v for k, v in o.items() if k != "heldClaims"} for o in observations
                ],
                allowedIds=allowed,
                chunk=dev_all,
                sectionQuota=quota,
                existingClaims=existing,
                measuredVoice=packet.get("voice") or [],
            ),
        )
        kept, extra = [], []
        used = {s: 0 for s in quota}
        for c in out["claims"]:
            if c["section"] in used and used[c["section"]] < quota[c["section"]]:
                used[c["section"]] += 1
                kept.append(c)
            else:
                extra.append(dict(claim=c, reason="섹션 후보 할당 초과 또는 요청하지 않은 섹션"))
        return kept, extra, model

    def label(claims, tag):
        jobs = [
            (phase, ch)
            for phase, chunks in (("tendency-audit", dev), ("tendency-confirm", confirm))
            for ch in chunks
        ]

        def one(job):
            phase, ch = job
            return run(
                ctx,
                cid,
                folder,
                budget,
                phase,
                ch["id"] + tag,
                dict(**common, chunk=ch, claims=claims),
            )

        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, jobs))
        rows = {"tendency-audit": [], "tendency-confirm": []}
        for (phase, ch), (found, _) in zip(jobs, results, strict=True):
            rows[phase].append(dict(chunkId=ch["id"] + tag, findings=found["findings"]))
        model = results[-1][1] if results else None
        return rows["tendency-audit"], rows["tendency-confirm"], model

    units = {r["id"]: tuple(r["unit"]) for r in source["records"]}
    available = len({key(u) for u in units.values()})
    speech = [t["text"] for ch in source["chunks"] for seg in ch["segments"] for t in seg["turns"]]
    min_confirm = ctx.config.stage("s8").get("min_confirmation_support", 1)

    def decide(claims, development, confirmation, round_no):
        ds = aggregate(development, claims, source["records"])
        cs = aggregate(confirmation, claims, source["records"])
        out = []
        for c in claims:
            d, v = ds[c["id"]], cs[c["id"]]
            rule = section_rule(c["section"], standard, available)
            stats = _stats(d, v, units, key)
            state, reason = _judge(c, d, v, stats, rule, min_confirm)
            decision = dict(
                claim=c,
                development=d,
                confirmation=v,
                state=state,
                support=stats,
                rule=rule,
                round=round_no,
            )
            if reason is None:
                reason = card_problem(c)
            if reason is None:
                try:
                    card = to_card(c, sorted(set(d["support"]) | set(v["support"])), state)
                    # Add the fixed limit unless the writer already scoped out private events.
                    if CORRECTION.search(c["function"]) and "개인 일정" not in c["exclusion"]:
                        card["limit"] += CORRECTION_LIMIT
                    validate_card(card, source["records"], extra_speech=speech)
                    compile_prompt(packet | {"sections": [card]})
                except (ValueError, TypeError, KeyError) as exc:
                    reason = str(exc)
                else:
                    decision["card"] = card
            decision["retained"] = reason is None
            if reason:
                decision["reason"] = reason
            out.append(decision)
        return out

    # Round 1: every section searches with its own quota.
    quota1 = {s: n for s, (_, n, _) in SECTION_PLAN.items()}
    claims1, extra1, model = candidates("all", quota1, [])
    claims1 = [dict(c, id=f"tendency-{i:02d}") for i, c in enumerate(claims1, 1)]
    write_once_json(folder / "evidence-locked-tendencies.json", claims1)
    dev1, conf1, model = label(claims1, "") if claims1 else ([], [], model)
    decisions = decide(claims1, dev1, conf1, 1) if claims1 else []
    development, confirmation = list(dev1), list(conf1)

    def kept_by_section(decs):
        out = {s: 0 for s in SECTION_PLAN}
        for x in decs:
            if x["retained"]:
                out[x["claim"]["section"]] += 1
        return out

    # Round 2: one supplementary search only for sections below target.
    have = kept_by_section(decisions)
    short = {
        s: targets_by_section[s] - have[s] for s in SECTION_PLAN if have[s] < targets_by_section[s]
    }
    extra2 = []
    supplement = {}
    if short:
        quota2 = {s: min(SECTION_PLAN[s][1], need + 2) for s, need in short.items()}
        existing = [
            {k: c[k] for k in ("section", "function", "trigger", "realization")} for c in claims1
        ]
        claims2, extra2, model = candidates("supplement-1", quota2, existing)
        start = len(claims1)
        claims2 = [dict(c, id=f"tendency-{start + i:02d}") for i, c in enumerate(claims2, 1)]
        write_once_json(folder / "evidence-supplement-tendencies.json", claims2)
        if claims2:
            dev2, conf2, model = label(claims2, "-s1")
            decisions += decide(claims2, dev2, conf2, 2)
            development += dev2
            confirmation += conf2
        supplement = dict(requested=short, quota=quota2, candidates=len(claims2))

    # Per-section cap, then the prompt length limit: strongest support first (units, share).
    held = []
    by_section = {s: [] for s in SECTION_PLAN}
    for x in decisions:
        (by_section[x["claim"]["section"]] if x["retained"] else held).append(x)
    for s, xs in by_section.items():
        xs.sort(key=lambda x: (-x["support"]["units"], -x["support"]["share"]))
        cap = SECTION_PLAN[s][2]
        for i, x in enumerate(xs[cap:], cap + 1):
            x["retained"] = False
            x["reason"] = f"섹션 상한 {cap}개 초과(근거 순위 {i})"
            held.append(x)
        del xs[cap:]
    limit = min(int(ctx.config.stage("s8").get("long_prompt_max_chars", 8000)), 8000)
    known = {line.strip() for line in packet["facts"].split("\n")}
    dropped_facts = []

    def stated(sel):
        out, seen = [], set(known)
        for s in sorted(SELF_REPORT):
            for x in sel.get(s, []):
                for text in (x["claim"].get("statedFacts") or [])[:2]:
                    item = dict(text=text, evidence=x["card"]["evidence"])
                    if text in seen:
                        continue
                    try:
                        compile_prompt(packet | {"statedFacts": [item]})
                    except (ValueError, TypeError, KeyError) as exc:
                        if item not in [d["item"] for d in dropped_facts]:
                            dropped_facts.append(dict(item=item, reason=str(exc)))
                        continue
                    seen.add(text)
                    out.append(item)
        return {"statedFacts": out} if out else {}

    chosen, trimmed = fit_length(packet, by_section, targets_by_section, limit, extra=stated)
    for x in trimmed:
        x["retained"] = False
        x["reason"] = f"프롬프트 길이 상한 {limit}자 때문에 제외(목표 수는 채운 뒤의 추가분)"
        held.append(x)
    accepted = [x["card"] for s in SECTION_PLAN for x in chosen[s]]
    stated_facts = stated(chosen).get("statedFacts", [])
    final = kept_by_section(decisions)
    coverage = {
        s: dict(
            target=targets_by_section[s],
            measuredLines=_voice_lines(packet) if s == "VOICE" else 0,
            retained=final[s],
            status="ok" if final[s] >= targets_by_section[s] else "short",
            lengthTrimmed=sum(x["claim"]["section"] == s for x in trimmed),
        )
        for s in SECTION_PLAN
    }
    for x in decisions:
        x.pop("card", None)
    write_once_json(folder / "evidence-tendency-decisions.json", decisions)
    write_once_json(
        folder / "evidence-section-coverage.json",
        dict(
            standard=standard,
            plan=SECTION_PLAN,
            coverage=coverage,
            supplement=supplement,
            excluded=extra1 + extra2,
            speed=speed,
            statedFacts=stated_facts,
            droppedStatedFacts=dropped_facts,
        ),
    )
    write_once_json(folder / "evidence-development-audits.json", development)
    write_once_json(folder / "evidence-confirmation-audits.json", confirmation)
    files = (
        list((folder / "analysis").glob("*.json"))
        + list((folder / "analysis/receipts").glob("*.json"))
        + list(folder.glob("evidence-*.json"))
    )
    files = [p for p in files if p.name not in {"evidence-review.json", "evidence-packet.json"}]
    rules = {s: section_rule(s, standard, available) for s in SECTION_PLAN}
    review = dict(
        schemaVersion="evidence-review-v10",
        status="AWAITING_HUMAN" if accepted else "HELD",
        supportRule=dict(standard=standard, sections=rules),
        sectionCoverage=coverage,
        records=source["records"],
        cards=accepted,
        statedFacts=stated_facts,
        held=[{k: v for k, v in x.items() if k != "card"} for x in held],
        stats=source["stats"],
        binding=binding,
        coverage=source["coverage"],
        partition=split,
        auditCoverage=dict(
            complete=bool(decisions),
            developmentChunks=len(dev),
            confirmationChunks=len(confirm),
            claims=len(decisions),
            rounds=2 if supplement else 1,
        ),
        responseModel=model,
        analysisArtifacts={p.relative_to(folder).as_posix(): sha256_file(p) for p in files},
    )
    if not accepted:
        write_once_json(folder / "evidence-review.json", review)
        raise ValueError("섹션 기준을 통과한 특징이 없다")
    packet = packet | {"sections": accepted}
    if stated_facts:
        packet["statedFacts"] = stated_facts
    text = compile_prompt(packet)
    write_once_json(folder / "evidence-packet.json", packet)
    review["packetSha256"] = sha256_file(folder / "evidence-packet.json")
    write_once_json(folder / "evidence-review.json", review)
    return text, dict(
        compiler=SECTIONED_VERSION,
        responseModel=model,
        status="AWAITING_HUMAN",
        evidenceReviewSha256=sha256_file(folder / "evidence-review.json"),
    )


def plan_count(dev, confirm, hedged=False):
    """Upper bound: two candidate calls and two labelling rounds over every chunk, doubled when
    every call might be sent a second time."""
    calls = 2 + 2 * (len(dev) + len(confirm))
    return calls * 2 if hedged else calls


def fit_length(packet, ranked, targets, limit, extra=None):
    """Keep each section's strongest cards up to its target, then add the remaining cards
    one per section per pass (VOICE first) while the compiled prompt stays within limit.

    Cards up to the target are never dropped for length; the S8 length check reports it.
    extra(selection) returns packet fields that depend on the chosen cards (statedFacts).
    Returns (chosen by section, trimmed decisions).
    """
    chosen = {s: list(xs[: targets[s]]) for s, xs in ranked.items()}
    rest = {s: list(xs[targets[s] :]) for s, xs in ranked.items()}

    def size(sel):
        cards = [x["card"] for s in SECTION_PLAN for x in sel[s]]
        more = extra(sel) if extra else {}
        return len(compile_prompt(packet | {"sections": cards} | more)) if cards else 0

    trimmed = []
    while any(rest.values()):
        for s in SECTION_PLAN:
            if not rest[s]:
                continue
            x = rest[s].pop(0)
            trial = dict(chosen, **{s: [*chosen[s], x]})
            if size(trial) <= limit:
                chosen = trial
            else:
                trimmed.append(x)
                trimmed.extend(rest[s])  # weaker cards of this section do not jump ahead
                rest[s] = []
    return chosen, trimmed
