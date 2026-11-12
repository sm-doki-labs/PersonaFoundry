"""Source-grounded candidates, deterministic compilation, and G6 source binding.

Structural eligibility is not semantic approval. Only G6 can approve these cards.
Holdout text is never retained in author/review packets.
"""

from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.store import read_json, verify_manifest, write_once_json
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.s0_source.run import load_approved_source
from character_factory_poc.stages.s8_prompts import source_shape
from character_factory_poc.stages.s8_prompts.evidence_compiler import (
    INTERVIEW_FORMAT,
    compile_prompt,
)
from character_factory_poc.stages.s8_prompts.evidence_compiler import SECTIONS as SECTIONS
from character_factory_poc.stages.s8_prompts.evidence_source import prepare_records, validate_card
from character_factory_poc.stages.s8_prompts.twin import approved_facts, motif_facts

VERSION = "evidence-pipeline-v3"
TENDENCY_VERSION = "evidence-pipeline-v4"
USAGE_VERSION = "evidence-pipeline-v5"
MEASURED_VERSION = "evidence-pipeline-v6"
COMPACT_VERSION = "evidence-pipeline-v7"
SEEDED_VERSION = "evidence-pipeline-v8"
LABELED_VERSION = "evidence-pipeline-v9"
SECTIONED_VERSION = "evidence-pipeline-v10"
FULL_VERSION = "evidence-pipeline-v2"
LEGACY_VERSION = "evidence-pipeline-v1"
FACT_BOUNDARY = (
    "사실표 또는 현재 대화에서 확인할 수 없는 개인사나 공동 기억은 긍정도 부정도 단정하지 않는다. "
    "다른 일화로 메우지 않고, 지금 고를 수 있는 것만 현재 판단으로 답한다."
)
# New packets record factPolicy in their binding; packets without it keep their old role bytes.
FACT_POLICY = "facts-first-v1"
FACT_PRIORITY = (
    " [FACTS]는 아래 모든 행동·말투 지침보다 우선한다. [FACTS]에 적힌 숫자·날짜·이름·관계와 "
    "어긋나게 말하지 않고, 그 값을 말할 때는 반올림하거나 흐리거나 추정하지 않고 적힌 그대로 쓴다. "
    "행동·말투 지침은 말하는 방식만 정한다."
)


def instructions(version=VERSION):
    return files("character_factory_poc.resources").joinpath(version + ".md").read_text("utf-8")


# New v10 packets render measured voice with named habit words (evidence_voice.HABITS_STYLE);
# saved bindings without voiceStyle keep the original wording they were reviewed with.
_NEW_VOICE = object()


def version_for(ctx, cid=None):
    return select_standard(ctx, cid)[0]


TEXT_STANDARDS = ("source_shape", "chapter_template")
# Text standard confirmed 2026-11-13 (D-0201, D-0202). v10 starts from the S3 scene analysis,
# so a character whose approved plan has none falls back to the previous standard. An
# explicit [stages.s8] motif_compiler always wins and is never replaced.
DEFAULT_COMPILER = "evidence-v10"
FALLBACK_COMPILER = "evidence-v4"
_SCENE_ANALYSIS = ("voice", "behavior", "facts-limits")


def has_scene_analysis(ctx, cid):
    gate = ctx.state(cid).gate("G3")
    if gate.status != "APPROVED" or not gate.rev:
        return False
    folder = ctx.character_dir(cid) / "s3-plan" / str(gate.rev) / "scene-analysis"
    return all((folder / f"{name}.json").is_file() for name in _SCENE_ANALYSIS)


def configured_compiler(ctx, cid=None):
    """(motif_compiler value, fallback note or None)."""
    cfg = ctx.config.stage("s8")
    if "motif_compiler" in cfg:
        return cfg["motif_compiler"], None
    if cid is not None and has_scene_analysis(ctx, cid):
        return DEFAULT_COMPILER, None
    if DEFAULT_COMPILER == FALLBACK_COMPILER:
        return FALLBACK_COMPILER, None
    return FALLBACK_COMPILER, "S3 장면 분석 결과가 없어 이전 표준(evidence-v4)을 쓴다"


def select_standard(ctx, cid=None):
    """Return the compiler and, when the text standard was chosen, why it was chosen.

    The text standard follows the approved source's shape by default. chapterTemplate keeps
    choosing scenes and video direction, and decides the text standard only when the shape
    cannot be judged or [stages.s8] text_standard = "chapter_template".
    """
    cfg = ctx.config.stage("s8")
    value, fallback = configured_compiler(ctx, cid)
    conversation = {
        "evidence-v4": TENDENCY_VERSION,
        "evidence-v7": COMPACT_VERSION,
        "evidence-v8": SEEDED_VERSION,
        "evidence-v9": LABELED_VERSION,
        "evidence-v10": SECTIONED_VERSION,
    }
    if cid is not None and value in conversation:
        interview = cfg.get("interview_compiler", INTERVIEW_FORMAT)
        if interview not in (INTERVIEW_FORMAT, "inherit"):
            raise ValueError("interview_compiler는 interview-editor-v2 또는 inherit여야 한다")
        mode = cfg.get("text_standard", "source_shape")
        if mode not in TEXT_STANDARDS:
            raise ValueError("text_standard는 source_shape 또는 chapter_template여야 한다")
        gate = ctx.state(cid).gate("G0")
        if interview == INTERVIEW_FORMAT and gate.status == "APPROVED" and gate.rev:
            folder = ctx.character_dir(cid) / "s0-source" / gate.rev
            template = read_json(folder / "source-pack.json").get("chapterTemplate")
            shape = source_shape.analyze_folder(folder) if mode == "source_shape" else None
            if shape and shape["shape"]:
                standard, basis = shape["shape"], "source_shape"
            else:
                interview_scene = template == "INTERVIEW"
                standard = source_shape.INTERVIEW if interview_scene else source_shape.CONVERSATION
                basis = "chapter_template"
            # v10 handles both shapes itself; earlier conversation versions hand interviews
            # to the interview editor.
            sectioned = value == "evidence-v10"
            interview_editor = standard == source_shape.INTERVIEW and not sectioned
            version = INTERVIEW_FORMAT if interview_editor else conversation[value]
            record = dict(
                mode=mode,
                basis=basis,
                standard=standard,
                compiler=version,
                chapterTemplate=template,
            )
            if shape:
                record.update(label=shape["label"], sourceShape=shape)
            if fallback:
                record["defaultFallback"] = fallback
            return version, record
    return {
        "evidence-v1": LEGACY_VERSION,
        "evidence-v2": FULL_VERSION,
        "evidence-v3": VERSION,
        "evidence-v4": TENDENCY_VERSION,
        "evidence-v5": USAGE_VERSION,
        "evidence-v6": MEASURED_VERSION,
        "evidence-v7": COMPACT_VERSION,
        "evidence-v8": SEEDED_VERSION,
        "evidence-v9": LABELED_VERSION,
        "evidence-v10": SECTIONED_VERSION,
    }[value], None


def selected(ctx):
    value = ctx.config.stage("s8").get("motif_compiler", DEFAULT_COMPILER)
    if value not in {
        "evidence-v1",
        "evidence-v2",
        "evidence-v3",
        "evidence-v4",
        "evidence-v5",
        "evidence-v6",
        "evidence-v7",
        "evidence-v8",
        "evidence-v9",
        "evidence-v10",
        "v3",
    }:
        raise ValueError(
            "motif_compiler는 evidence-v10, evidence-v9, evidence-v8, evidence-v7, evidence-v6, "
            "evidence-v5, "
            "evidence-v4, evidence-v3, evidence-v2, evidence-v1 또는 v3여야 한다"
        )
    return value in {
        "evidence-v1",
        "evidence-v2",
        "evidence-v3",
        "evidence-v4",
        "evidence-v5",
        "evidence-v6",
        "evidence-v7",
        "evidence-v8",
        "evidence-v9",
        "evidence-v10",
    }


def is_evidence(folder):
    folder = Path(folder)
    if any((folder / name).exists() for name in ("evidence-intent.json", "evidence-binding.json")):
        return True
    path = folder / "prompt-pair.json"
    return path.is_file() and read_json(path).get("systemRulesRef") in {
        "builtin:" + VERSION,
        "builtin:" + TENDENCY_VERSION,
        "builtin:" + USAGE_VERSION,
        "builtin:" + MEASURED_VERSION,
        "builtin:" + COMPACT_VERSION,
        "builtin:" + SEEDED_VERSION,
        "builtin:" + LABELED_VERSION,
        "builtin:" + SECTIONED_VERSION,
        "builtin:" + LEGACY_VERSION,
        "builtin:" + FULL_VERSION,
        "builtin:" + INTERVIEW_FORMAT,
    }


def _inputs(
    ctx,
    cid,
    plan,
    plan_path,
    sheet_path,
    *,
    version=None,
    fact_policy=FACT_POLICY,
    text_standard=None,
    voice_style=_NEW_VOICE,
):
    # A saved revision passes its own compiler and record; it is never routed again.
    if not version:
        version, text_standard = select_standard(ctx, cid)
    elif text_standard is not None and text_standard.get("compiler") != version:
        raise ValueError("저장된 텍스트 표준 기록과 컴파일러가 다르다")
    if voice_style is _NEW_VOICE:
        from character_factory_poc.stages.s8_prompts.evidence_voice import HABITS_STYLE

        voice_style = HABITS_STYLE if version == SECTIONED_VERSION else None
    pack, index, corpus = load_approved_source(ctx, cid)
    root = ctx.character_dir(cid)
    folder = root / "s0-source" / index.sourceRev
    state = ctx.state(cid)
    source_gate = state.gate("G0")
    if source_gate.rev != index.sourceRev or index.characterId != cid:
        raise ValueError("원문 revision과 캐릭터가 다르다")
    variants = read_json(plan_path.parent / "variants.json")
    if variants["seedSha256"] != sha256_file(folder / "source-pack.json"):
        raise ValueError("G3 기획과 G0 원문이 다르다. 기획을 다시 검토한다")
    if verify_manifest(folder):
        raise ValueError("승인 원문 파일이 변경되었다. 새 원문 revision이 필요하다")
    flags = {x["msgId"] for x in read_json(folder / "digest.json")["piiFlags"]}
    # Read local identifiers only, never pass held text into either model or review.
    held = []
    with (folder / "holdout.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                held.append({k: row[k] for k in ("msgId", "textId", "convId")})
    cfg = ctx.config.stage("s8")
    cap = cfg.get("evidence_max_records", 80)
    if version == LEGACY_VERSION and (type(cap) is not int or not 2 <= cap <= 160):
        raise ValueError("evidence_max_records는 2~160 정수여야 한다")
    scenes = cfg.get("evidence_scenes", {})
    if not isinstance(scenes, dict) or any(
        not isinstance(v, str) or not v.strip() for v in scenes.values()
    ):
        raise ValueError("evidence_scenes에는 캐릭터 ID별 장면 문자열을 넣는다")
    scene = scenes.get(cid, cfg.get("evidence_scene"))
    if scene is None:
        scene = {
            "FAN_CALL": "처음 만나는 팬과 통화한다. 해요체를 쓴다.",
            "FAMILY_CALL": "가족과 통화한다. 원문의 관계와 말높임을 따른다.",
            "FRIEND_CHAT": (
                "오래된 친구와 메신저로 대화한다. 원문에서 확인된 말높임을 따른다. "
                "친한 관계라는 이유로 확인되지 않은 공동 기억이나 개인사를 만들지 않는다."
            ),
            "INTERVIEW": (
                "상대는 질문자로서 인터뷰를 진행하고 인물은 질문에 답한다. "
                "주제와 진행 순서는 질문자가 정한다. 원문에서 확인된 말높임을 따른다."
            ),
        }[pack.chapterTemplate]
    info = [f"이 대화 상대는 {plan.name}에서 모티브를 얻은 AI 캐릭터다. 실제 본인은 아니다."]
    info += [
        v
        for k, v in pack.knownFacts.items()
        if k in {"age", "gender", "job", "background", "relation"}
    ]
    info += pack.factSheet  # User-provided lines, verbatim, before collected public facts.
    info += motif_facts(approved_facts(ctx, cid))
    if pack.subject.kind == "PUBLIC_FIGURE":
        info += [
            t
            for t, e in zip(plan.lifeAndTastes, plan.evidence.get("lifeAndTastes", []), strict=True)
            if e.kind == "SOURCE" and e.ref not in flags
        ]
    facts = "\n".join(dict.fromkeys(info))
    role = (
        "제공된 사실과 조건별 언어 행동에 따라 AI 모티브 캐릭터로 대화한다. "
        "캐릭터가 실제로 할 말만 쓰고 해설·라벨·행동 지문은 쓰지 않는다. " + FACT_BOUNDARY
    )
    if version in {
        VERSION,
        TENDENCY_VERSION,
        USAGE_VERSION,
        MEASURED_VERSION,
        COMPACT_VERSION,
        SEEDED_VERSION,
        LABELED_VERSION,
        SECTIONED_VERSION,
    }:
        role += (
            " 관찰된 특성은 해당 조건에서만 가능한 반응 경향이며 매번 실행할 과제가 아니다. "
            "답변 전에 개인 경험·보유 물건·최근 행동을 주장하는지 확인한다. "
            "사용자의 질문에 깔린 전제와 앞서 AI가 한 말은 개인 사실의 증거가 아니다. "
            "사실표나 사용자가 명시한 사실로 확인되지 않는 회상은 구체화하지 않는다. "
            "확인할 수 없다는 범위만 짧게 밝히고 현재 질문에 답한다. "
            "앞 답변에서 지어냈다면 그 내용을 철회하며 다른 일화를 만들지 않는다."
        )
    interview_v10 = (
        version == SECTIONED_VERSION
        and (text_standard or {}).get("standard") == source_shape.INTERVIEW
    )
    if version == INTERVIEW_FORMAT or interview_v10:
        tail = role[role.index(" 관찰된 특성은") :] if interview_v10 else ""
        role = (
            "인터뷰에서 진행자의 질문을 받는 AI 모티브 인물이다. 실제 본인이 아니다. "
            "진행자의 질문에는 인물의 발화만 답한다. 질문의 전제는 증거가 아니다. "
            "확인되지 않은 개인사나 비공개 대화를 사실로 만들지 않는다."
        ) + tail
    if fact_policy is not None:
        if fact_policy != FACT_POLICY:
            raise ValueError("알 수 없는 사실 우선 규칙이다")
        role += FACT_PRIORITY
    paths = [
        folder / n
        for n in (
            "source-pack.json",
            "source-index.json",
            "corpus.jsonl",
            "holdout.jsonl",
            "digest.json",
        )
    ]
    paths += [plan_path, plan_path.parent / "variants.json", sheet_path]
    for gate_name in ("G0", "G3"):
        gate = state.gate(gate_name)
        if gate.status != "APPROVED" or not gate.recordRef:
            raise ValueError(gate_name + " 원문 검토 승인이 필요하다")
        paths.append(root / gate.recordRef)
    for p in (folder / "facts.json", sheet_path.parent / "trait-ledger.json"):
        if p.exists():
            paths.append(p)
    binding = dict(
        compiler=version,
        instructionsSha256=sha256_text(instructions(version)),
        sourceRevision=index.sourceRev,
        planRevision=plan.planRev,
        traitRevision=sheet_path.parent.name,
        scene=scene,
        factsSha256=sha256_text(facts),
        maxRecords=cap,
        artifacts={p.relative_to(root).as_posix(): sha256_file(p) for p in paths},
    )
    if fact_policy is not None:
        binding["factPolicy"] = fact_policy
    if text_standard is not None:
        binding["textStandard"] = text_standard
    if voice_style is not None:
        binding["voiceStyle"] = voice_style
    if version in {
        VERSION,
        FULL_VERSION,
        TENDENCY_VERSION,
        USAGE_VERSION,
        MEASURED_VERSION,
        COMPACT_VERSION,
        SEEDED_VERSION,
        LABELED_VERSION,
        SECTIONED_VERSION,
        INTERVIEW_FORMAT,
    }:
        from character_factory_poc.stages.s8_prompts.evidence_full_source import (
            TRANSPORT,
            prepare_full_source,
        )

        chunk_chars = cfg.get("evidence_chunk_chars", 24000)
        if type(chunk_chars) is not int or not 6000 <= chunk_chars <= 60000:
            raise ValueError("evidence_chunk_chars는 6000~60000 정수여야 한다")
        binding.pop("maxRecords")
        binding["chunkChars"] = chunk_chars
        # v7 measures chunks on the one-line transport; older versions keep JSON-sized chunks.
        compact = version in {COMPACT_VERSION, SEEDED_VERSION, LABELED_VERSION, SECTIONED_VERSION}
        transport = TRANSPORT if compact else "json"
        if compact:
            binding["sourceTransport"] = TRANSPORT
        if version in {SEEDED_VERSION, LABELED_VERSION, SECTIONED_VERSION}:
            binding["seed"] = "s3-scene-analysis"
        records = prepare_full_source(
            corpus, held, flags, max_chunk_chars=chunk_chars, transport=transport
        )
    else:
        records = prepare_records(corpus, held, flags, max_records=cap)
        # Bound the total transport, not just the number of windows. Never cut a turn.
        chosen, used = [], 0
        for record in records["records"]:
            size = len(json.dumps(record, ensure_ascii=False))
            if used + size <= 60000:
                chosen.append(record)
                used += size
        records["stats"]["transport_discarded"] = len(records["records"]) - len(chosen)
        records["stats"]["transport_chars"] = used
        records["records"] = chosen
    packet = dict(
        role=role,
        scene=scene,
        facts=facts,
        sections=[],
        trainIds=[r["id"] for r in records["records"]],
        holdoutIds=records["holdoutIds"],
    )
    if version in {
        VERSION,
        FULL_VERSION,
        TENDENCY_VERSION,
        USAGE_VERSION,
        MEASURED_VERSION,
        COMPACT_VERSION,
        SEEDED_VERSION,
        LABELED_VERSION,
    }:
        packet["formatVersion"] = "evidence-conditions-v2"
    if version == INTERVIEW_FORMAT:
        packet["formatVersion"] = INTERVIEW_FORMAT
    if version in {MEASURED_VERSION, SECTIONED_VERSION}:
        from character_factory_poc.stages.s8_prompts.evidence_voice import measured_voice_lines
        from character_factory_poc.stages.s8_prompts.twin import approved_voice

        packet["formatVersion"] = "evidence-conditions-v3"
        voice = measured_voice_lines(
            approved_voice(ctx, cid, plan).get("speechProfile"), voice_style
        )
        if voice:
            packet["voice"] = voice
    compile_prompt(packet)  # Validate immutable literal fields before paying for extraction.
    return packet, records, binding


def full_plan(ctx, cid, probes=0):
    from character_factory_poc.common.budget import CallPlan
    from character_factory_poc.stages.s3_plan.importer import load_approved_plan
    from character_factory_poc.stages.s8_prompts.build import load_latest_trait_sheet

    plan, plan_path = load_approved_plan(ctx, cid)
    _, sheet_path = load_latest_trait_sheet(ctx, cid)
    _, source, binding = _inputs(ctx, cid, plan, plan_path, sheet_path)
    version = binding["compiler"]
    if version == INTERVIEW_FORMAT:
        from character_factory_poc.stages.s8_prompts.interview_authoring import plan_calls

        return plan_calls(source) + [CallPlan("s8", "요청한 추가 응답 표본", probes, None)]
    if version == SECTIONED_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES
        from character_factory_poc.stages.s8_prompts.evidence_sections import (
            plan_count,
            speed_settings,
        )
        from character_factory_poc.stages.s8_prompts.evidence_tendencies import _labeled_partition

        dev, check, _ = _labeled_partition(source)
        hedged = speed_settings(ctx.config.stage("s8"))["hedgeSeconds"] > 0
        return [
            CallPlan(
                "s8",
                f"섹션별 후보 2회(보충 포함)와 응답별 전수 표시 최대 2×{len(dev) + len(check)}회",
                plan_count(dev, check, hedged) + ATOMIC_RETRIES,
                None,
            ),
            CallPlan("s8", "요청한 추가 응답 표본", probes, None),
        ]
    if version == LABELED_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES
        from character_factory_poc.stages.s8_prompts.evidence_tendencies import _labeled_partition

        dev, check, _ = _labeled_partition(source)
        return [
            CallPlan(
                "s8",
                f"S3 관찰 통합 1회와 응답별 전수 표시 {len(dev)}+{len(check)}회",
                1 + len(dev) + len(check) + ATOMIC_RETRIES,
                None,
            ),
            CallPlan("s8", "요청한 추가 응답 표본", probes, None),
        ]
    if version == SEEDED_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES
        from character_factory_poc.stages.s8_prompts.evidence_tendencies import (
            SeededProfile,
            _seeded_partition,
        )

        dev, check, _ = _seeded_partition(source)
        batch = ctx.config.stage("s8").get("evidence_audit_batch", SeededProfile.AUDIT_BATCH)
        groups = -(-12 // batch)  # upper bound: consolidation is asked for at most 12
        return [
            CallPlan(
                "s8",
                f"S3 관찰 통합 1회와 원문 {len(dev)}+{len(check)}덩어리 대화별 대조",
                1 + (len(dev) + len(check)) * groups + ATOMIC_RETRIES,
                None,
            ),
            CallPlan("s8", "요청한 추가 응답 표본", probes, None),
        ]
    if version == COMPACT_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_atomic import partition_compact
        from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES
        from character_factory_poc.stages.s8_prompts.evidence_tendencies import (
            COMPACT_AUDIT_BATCH,
            MAX_CONSOLIDATED,
        )

        dev, check, _ = partition_compact(source)
        batch = ctx.config.stage("s8").get("evidence_audit_batch", COMPACT_AUDIT_BATCH)
        groups = -(-min(12, MAX_CONSOLIDATED) // batch)  # upper bound
        return [
            CallPlan(
                "s8",
                f"한 줄 원문 {len(dev)}+{len(check)}조각 기능·말투 분리와 대화별 대조",
                len(dev) + (len(dev) + len(check)) * groups + 1 + ATOMIC_RETRIES,
                None,
            ),
            CallPlan("s8", "요청한 추가 응답 표본", probes, None),
        ]
    if version in {TENDENCY_VERSION, USAGE_VERSION, MEASURED_VERSION}:
        from character_factory_poc.stages.s8_prompts.evidence_atomic import partition
        from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES

        dev, check, _ = partition(source)
        return [
            CallPlan(
                "s8",
                "기능·말투 분리와 전체 조건부 대조",
                2 * len(dev) + len(check) + 1 + ATOMIC_RETRIES,
                None,
            ),
            CallPlan("s8", "요청한 추가 응답 표본", probes, None),
        ]
    if version == VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_atomic import partition
        from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import ATOMIC_RETRIES

        dev, check, _ = partition(source)
        return [
            CallPlan(
                "s8",
                "원자 특징 발견·개발 대조·범위 축소·독립 확인(최대)",
                3 * len(dev) + len(check) + 2 + ATOMIC_RETRIES,
                None,
            ),
            CallPlan("s8", "요청한 추가 응답 표본", probes, None),
        ]
    return [
        CallPlan(
            "s8",
            f"전체 {len(source['chunks'])}구간 관찰·통합·특징별 전체 대조",
            2 * len(source["chunks"]) + 1,
            None,
        ),
        CallPlan("s8", "요청한 추가 응답 표본", probes, None),
    ]


def build(ctx, cid, plan, plan_path, sheet_path, folder, budget, rework=None):
    # A resumed run keeps the policy its interrupted binding was written with.
    prior = folder / "evidence-binding.json"
    policy = read_json(prior).get("factPolicy") if prior.is_file() else FACT_POLICY
    kept = read_json(prior) if prior.is_file() else {}  # Also keep its compiler and standard.
    packet, source, binding = _inputs(
        ctx,
        cid,
        plan,
        plan_path,
        sheet_path,
        fact_policy=policy,
        version=kept.get("compiler"),
        text_standard=kept.get("textStandard"),
        voice_style=kept.get("voiceStyle") if prior.is_file() else _NEW_VOICE,
    )
    if binding["compiler"] == INTERVIEW_FORMAT:
        from character_factory_poc.stages.s8_prompts import interview_authoring

        return interview_authoring.build(ctx, cid, packet, source, binding, folder, budget, rework)
    if binding["compiler"] == SECTIONED_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_sections import build_sections

        return build_sections(ctx, cid, packet, source, binding, folder, budget, rework)
    if binding["compiler"] == USAGE_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_usage import build_usage

        return build_usage(ctx, cid, packet, source, binding, folder, budget, rework)
    if binding["compiler"] == MEASURED_VERSION:
        from character_factory_poc.stages.s8_prompts import evidence_measured
        from character_factory_poc.stages.s8_prompts.evidence_tendencies import build_tendencies

        return build_tendencies(
            ctx, cid, packet, source, binding, folder, budget, rework, profile=evidence_measured
        )
    if binding["compiler"] == LABELED_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_tendencies import (
            LabeledProfile,
            build_tendencies,
        )

        return build_tendencies(
            ctx, cid, packet, source, binding, folder, budget, rework, profile=LabeledProfile
        )
    if binding["compiler"] == SEEDED_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_tendencies import (
            SeededProfile,
            build_tendencies,
        )

        return build_tendencies(
            ctx, cid, packet, source, binding, folder, budget, rework, profile=SeededProfile
        )
    if binding["compiler"] == COMPACT_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_tendencies import (
            CompactProfile,
            build_tendencies,
        )

        return build_tendencies(
            ctx, cid, packet, source, binding, folder, budget, rework, profile=CompactProfile
        )
    if binding["compiler"] == TENDENCY_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_tendencies import build_tendencies

        return build_tendencies(ctx, cid, packet, source, binding, folder, budget, rework)
    if binding["compiler"] == VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_atomic import build_atomic

        return build_atomic(ctx, cid, packet, source, binding, folder, budget, rework)
    if binding["compiler"] == FULL_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import build_full

        return build_full(ctx, cid, packet, source, binding, folder, budget, rework)
    records = source["records"]
    review = dict(
        schemaVersion="evidence-review-v1",
        status="AWAITING_HUMAN",
        records=records,
        cards=[],
        held=[],
        stats=source["stats"],
        binding=binding,
    )
    write_once_json(folder / "evidence-binding.json", binding)
    if len({tuple(r["unit"]) for r in records}) < 2:
        review.update(
            status="HELD",
            held=[dict(index=None, reason="서로 다른 대화 두 개 이상의 근거가 필요하다")],
        )
        write_once_json(folder / "evidence-review.json", review)
        raise ValueError("반복 경향을 추출할 독립 대화 근거가 부족하다")
    payload = dict(
        role=packet["role"], scene=packet["scene"], facts=packet["facts"], records=records
    )
    if rework:
        payload["editorRevision"] = rework
    candidates_path = folder / "evidence-candidates.json"
    if candidates_path.exists():
        cached = read_json(candidates_path)
        if cached["bindingSha256"] != sha256_file(folder / "evidence-binding.json"):
            raise ValueError("중단된 추출의 원천이 다르다")
        out, response_model = cached["output"], cached["responseModel"]
    else:
        response = ctx.text_model(cid, budget).complete(
            ChatRequest(
                kind="AGENT",
                stage="s8",
                ref=f"{cid}/{folder.name}/evidence",
                max_output_tokens=6000,
                response_json=True,
                messages=(
                    Message("system", instructions(LEGACY_VERSION)),
                    Message("user", json.dumps(payload, ensure_ascii=False)),
                ),
            )
        )
        out, response_model = extract_json_object(response.text), response.model
        write_once_json(
            candidates_path,
            dict(
                output=out,
                responseModel=response_model,
                bindingSha256=sha256_file(folder / "evidence-binding.json"),
            ),
        )
    if (
        set(out) != {"sections"}
        or not isinstance(out["sections"], list)
        or len(out["sections"]) > 12
    ):
        raise ValueError("근거 후보 응답 형식이 다르다")
    for n, card in enumerate(out["sections"]):
        try:
            compile_prompt(packet | {"sections": [card]})
            validate_card(card, records)
        except (TypeError, ValueError, KeyError):
            review["held"].append(dict(index=n, reason="형식·예시·원문 복사·독립 근거 검사 미충족"))
        else:
            review["cards"].append(card)
    packet["sections"] = review["cards"]
    review["responseModel"] = response_model
    if not review["cards"]:
        review["status"] = "HELD"
        if not review["held"]:
            review["held"] = [dict(index=None, reason="반복 근거를 갖춘 후보 없음")]
        write_once_json(folder / "evidence-review.json", review)
        raise ValueError("검사를 통과한 근거 후보가 없다. 원문·장면을 검토한다")
    text = compile_prompt(packet)
    write_once_json(folder / "evidence-packet.json", packet)
    review["packetSha256"] = sha256_file(folder / "evidence-packet.json")
    write_once_json(folder / "evidence-review.json", review)
    return text, dict(
        compiler=LEGACY_VERSION,
        responseModel=response_model,
        status="AWAITING_HUMAN",
        evidenceReviewSha256=sha256_file(folder / "evidence-review.json"),
    )


def verify_review(ctx, cid, folder, *, approved=False):
    from character_factory_poc.stages.s3_plan.importer import load_approved_plan
    from character_factory_poc.stages.s8_prompts.build import load_latest_trait_sheet

    root = ctx.character_dir(cid)
    plan, plan_path = load_approved_plan(ctx, cid)
    _, sheet_path = load_latest_trait_sheet(ctx, cid)
    saved = read_json(folder / "evidence-binding.json")
    current, source, binding = _inputs(
        ctx,
        cid,
        plan,
        plan_path,
        sheet_path,
        version=saved["compiler"],
        fact_policy=saved.get("factPolicy"),
        text_standard=saved.get("textStandard"),
        voice_style=saved.get("voiceStyle"),
    )
    review = read_json(folder / "evidence-review.json")
    packet = read_json(folder / "evidence-packet.json")
    assembly = read_json(folder / "assembly.json")
    if saved != binding or review["binding"] != binding:
        raise ValueError("원문·사실·장면·기획·특질이 달라졌다. 다시 생성하고 근거를 검토한다")
    if review.get("status") != "AWAITING_HUMAN" or not review.get("cards"):
        raise ValueError("검토 가능한 근거 후보가 없다")
    if review.get("packetSha256") != sha256_file(folder / "evidence-packet.json") or assembly.get(
        "evidenceReviewSha256"
    ) != sha256_file(folder / "evidence-review.json"):
        raise ValueError("검토 자료가 변경되었다")
    current["sections"] = review["cards"]
    if "statedFacts" in packet:
        current["statedFacts"] = review.get("statedFacts")
    if current != packet or source["records"] != review["records"]:
        raise ValueError("검토 카드나 원문 표본이 다르다")
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import verify_analysis_files

    verify_analysis_files(folder, review)
    if saved["compiler"] == INTERVIEW_FORMAT:
        from character_factory_poc.stages.s8_prompts.interview_authoring import verify_cards

        verify_cards(review["cards"], source, review)
    else:
        for card in review["cards"]:
            validate_card(
                card,
                source["records"],
                extra_speech=[
                    t["text"]
                    for ch in source.get("chunks", [])
                    for seg in ch["segments"]
                    for t in seg["turns"]
                ],
            )
    text = compile_prompt(packet)
    pair = read_json(folder / "prompt-pair.json")
    for key in ("long", "short"):
        if (
            pair[key] != dict(text=text, sha256=sha256_text(text), chars=len(text))
            or (folder / (key + ".md")).read_text("utf-8") != text
        ):
            raise ValueError("검토한 근거와 프롬프트가 다르다")
    if pair["systemRulesRef"] != "builtin:" + saved["compiler"] or pair[
        "systemRulesSha256"
    ] != sha256_text(instructions(saved["compiler"])):
        raise ValueError("조립 지시 버전이 다르다")
    if (folder / "example-turns.json").exists():
        raise ValueError("근거 표준은 예시 대화를 주입하지 않는다")
    if approved:
        gate = ctx.state(cid).gate("G6")
        if gate.status != "APPROVED" or gate.rev != folder.name or not gate.recordRef:
            raise ValueError("근거를 검토한 G6 승인이 필요하다")
        shown = read_json(root / gate.recordRef)["shownArtifacts"]
        for name in (
            "prompt-pair.json",
            "evidence-packet.json",
            "evidence-review.json",
            "evidence-binding.json",
            "assembly.json",
        ):
            p = folder / name
            if dict(ref=p.relative_to(root).as_posix(), sha256=sha256_file(p)) not in shown:
                raise ValueError("G6에서 검토한 자료와 현재 자료가 다르다")
        version = read_json(folder / "persona-version.json")
        if any(
            version[k] != pair[k] for k in ("long", "short", "systemRulesRef", "systemRulesSha256")
        ):
            raise ValueError("확정된 페르소나가 검토 본문과 다르다")
    return review


def verify_snapshot(root, folder, *, review_preview=False):
    """Verify pinned local bytes without loading corpus text on every demo turn."""
    root, folder = Path(root), Path(folder)
    binding = read_json(folder / "evidence-binding.json")
    state = read_json(root / "state.json")
    gate = state.get("gates", {}).get("G6", {})
    allowed = {"AWAITING_HUMAN", "APPROVED"} if review_preview else {"APPROVED"}
    if gate.get("status") not in allowed or gate.get("rev") != folder.name:
        raise ValueError("원문 근거 검토와 G6 승인을 먼저 완료해 주세요")
    for name, key in (("G0", "sourceRevision"), ("G3", "planRevision")):
        current = state.get("gates", {}).get(name, {})
        if current.get("status") != "APPROVED" or current.get("rev") != binding[key]:
            raise ValueError("검토한 원문 또는 기획 revision이 바뀌었다")
    if state.get("stages", {}).get("s7", {}).get("currentRev") != binding["traitRevision"]:
        raise ValueError("검토한 특질 revision이 바뀌었다")
    for ref, digest in binding["artifacts"].items():
        path = (root / ref).resolve()
        if not path.is_relative_to(root.resolve()) or sha256_file(path) != digest:
            raise ValueError("검토한 원천 파일이 바뀌었다")
    packet = read_json(folder / "evidence-packet.json")
    review = read_json(folder / "evidence-review.json")
    assembly = read_json(folder / "assembly.json")
    if (
        review.get("binding") != binding
        or review.get("packetSha256") != sha256_file(folder / "evidence-packet.json")
        or assembly.get("evidenceReviewSha256") != sha256_file(folder / "evidence-review.json")
    ):
        raise ValueError("근거 검토 자료가 바뀌었다")
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import verify_analysis_files

    verify_analysis_files(folder, review)
    text = compile_prompt(packet)
    pair = read_json(folder / "prompt-pair.json")
    if (
        pair["long"]["text"] != text
        or pair["long"]["sha256"] != sha256_text(text)
        or (folder / "long.md").read_text("utf-8") != text
    ):
        raise ValueError("검토한 본문과 시연 프롬프트가 다르다")
    if (folder / "example-turns.json").exists():
        raise ValueError("근거 표준에 예시 대화가 추가되었다")
    if gate["status"] == "APPROVED":
        record = read_json(root / gate["recordRef"])
        for name in (
            "prompt-pair.json",
            "evidence-binding.json",
            "evidence-packet.json",
            "evidence-review.json",
            "assembly.json",
        ):
            path = folder / name
            if (
                dict(ref=path.relative_to(root).as_posix(), sha256=sha256_file(path))
                not in record["shownArtifacts"]
            ):
                raise ValueError("G6 승인 이후 검토 자료가 바뀌었다")
