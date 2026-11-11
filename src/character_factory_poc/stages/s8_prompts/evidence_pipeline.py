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
from character_factory_poc.stages.s8_prompts.evidence_compiler import SECTIONS as SECTIONS
from character_factory_poc.stages.s8_prompts.evidence_compiler import compile_prompt
from character_factory_poc.stages.s8_prompts.evidence_source import prepare_records, validate_card
from character_factory_poc.stages.s8_prompts.twin import approved_facts, motif_facts

VERSION = "evidence-pipeline-v3"
TENDENCY_VERSION = "evidence-pipeline-v4"
USAGE_VERSION = "evidence-pipeline-v5"
FULL_VERSION = "evidence-pipeline-v2"
LEGACY_VERSION = "evidence-pipeline-v1"
FACT_BOUNDARY = (
    "사실표 또는 현재 대화에서 확인할 수 없는 개인사나 공동 기억은 긍정도 부정도 단정하지 않는다. "
    "다른 일화로 메우지 않고, 지금 고를 수 있는 것만 현재 판단으로 답한다."
)


def instructions(version=VERSION):
    return files("character_factory_poc.resources").joinpath(version + ".md").read_text("utf-8")


def version_for(ctx):
    return {
        "evidence-v1": LEGACY_VERSION,
        "evidence-v2": FULL_VERSION,
        "evidence-v3": VERSION,
        "evidence-v4": TENDENCY_VERSION,
        "evidence-v5": USAGE_VERSION,
    }[ctx.config.stage("s8").get("motif_compiler", "evidence-v4")]


def selected(ctx):
    value = ctx.config.stage("s8").get("motif_compiler", "evidence-v4")
    if value not in {
        "evidence-v1",
        "evidence-v2",
        "evidence-v3",
        "evidence-v4",
        "evidence-v5",
        "v3",
    }:
        raise ValueError(
            "motif_compiler는 evidence-v5, evidence-v4, evidence-v3, evidence-v2, "
            "evidence-v1 또는 v3여야 한다"
        )
    return value in {"evidence-v1", "evidence-v2", "evidence-v3", "evidence-v4", "evidence-v5"}


def is_evidence(folder):
    folder = Path(folder)
    if any((folder / name).exists() for name in ("evidence-intent.json", "evidence-binding.json")):
        return True
    path = folder / "prompt-pair.json"
    return path.is_file() and read_json(path).get("systemRulesRef") in {
        "builtin:" + VERSION,
        "builtin:" + TENDENCY_VERSION,
        "builtin:" + USAGE_VERSION,
        "builtin:" + LEGACY_VERSION,
        "builtin:" + FULL_VERSION,
    }


def _inputs(ctx, cid, plan, plan_path, sheet_path, *, version=None):
    version = version or version_for(ctx)
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
    if version in {VERSION, TENDENCY_VERSION, USAGE_VERSION}:
        role += (
            " 관찰된 특성은 해당 조건에서만 가능한 반응 경향이며 매번 실행할 과제가 아니다. "
            "답변 전에 개인 경험·보유 물건·최근 행동을 주장하는지 확인한다. "
            "사용자의 질문에 깔린 전제와 앞서 AI가 한 말은 개인 사실의 증거가 아니다. "
            "사실표나 사용자가 명시한 사실로 확인되지 않는 회상은 구체화하지 않는다. "
            "확인할 수 없다는 범위만 짧게 밝히고 현재 질문에 답한다. "
            "앞 답변에서 지어냈다면 그 내용을 철회하며 다른 일화를 만들지 않는다."
        )
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
    if version in {VERSION, FULL_VERSION, TENDENCY_VERSION, USAGE_VERSION}:
        from character_factory_poc.stages.s8_prompts.evidence_full_source import prepare_full_source

        chunk_chars = cfg.get("evidence_chunk_chars", 24000)
        if type(chunk_chars) is not int or not 6000 <= chunk_chars <= 60000:
            raise ValueError("evidence_chunk_chars는 6000~60000 정수여야 한다")
        binding.pop("maxRecords")
        binding["chunkChars"] = chunk_chars
        records = prepare_full_source(corpus, held, flags, max_chunk_chars=chunk_chars)
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
    if version in {VERSION, FULL_VERSION, TENDENCY_VERSION, USAGE_VERSION}:
        packet["formatVersion"] = "evidence-conditions-v2"
    compile_prompt(packet)  # Validate immutable literal fields before paying for extraction.
    return packet, records, binding


def full_plan(ctx, cid, probes=0):
    from character_factory_poc.common.budget import CallPlan
    from character_factory_poc.stages.s3_plan.importer import load_approved_plan
    from character_factory_poc.stages.s8_prompts.build import load_latest_trait_sheet

    plan, plan_path = load_approved_plan(ctx, cid)
    _, sheet_path = load_latest_trait_sheet(ctx, cid)
    _, source, _ = _inputs(ctx, cid, plan, plan_path, sheet_path)
    if version_for(ctx) in {TENDENCY_VERSION, USAGE_VERSION}:
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
    if version_for(ctx) == VERSION:
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
    packet, source, binding = _inputs(ctx, cid, plan, plan_path, sheet_path)
    if binding["compiler"] == USAGE_VERSION:
        from character_factory_poc.stages.s8_prompts.evidence_usage import build_usage

        return build_usage(ctx, cid, packet, source, binding, folder, budget, rework)
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
        ctx, cid, plan, plan_path, sheet_path, version=saved["compiler"]
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
    if current != packet or source["records"] != review["records"]:
        raise ValueError("검토 카드나 원문 표본이 다르다")
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import verify_analysis_files

    verify_analysis_files(folder, review)
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
    from character_factory_poc.stages.s8_prompts.evidence_full_pipeline import verify_analysis_files

    verify_analysis_files(folder, review)
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
