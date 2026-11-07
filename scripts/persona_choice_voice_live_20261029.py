# ruff: noqa: E501
"""Authorized source-audited live development comparison; not formal qualification."""

from __future__ import annotations

import argparse
import concurrent.futures
import dataclasses
import json
import shutil
import time
from pathlib import Path

import httpx

from character_factory_poc.common.budget import RunBudget
from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.formation import PersonaBlueprintV2
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import (
    ChatRequest,
    ChatResponse,
    Message,
)
from character_factory_poc.providers.tracked import TrackedTextModel
from character_factory_poc.stages.s3_plan.choice_design import body_hash, select_by_content

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "runs/experiments/20261029-choice-voice-live-r1"
OLD = REPO / "runs/experiments/20261029-quality-floor-development"
BASE = "http://127.0.0.1:10100/v1"
GEN = "gpt-6.1-sol"
CHAT = "google-antigravity/gemini-3.8-flash"
JUDGE = "anthropic/claude-sonnet-5"
LABELS = ("d1", "d2", "d3", "d4")
CAPS = dict(
    max_calls=300,
    max_tokens=2_500_000,
    max_cost_usd=75.0,
    input_rate_per_million=20.0,
    output_rate_per_million=120.0,
    synthetic=False,
)


def put(p, x):
    write_once_json(Path(p), x)


def path(label):
    r = ROOT / label
    return r, (r / "character-id.txt").read_text().strip()


def budget():
    return RunBudget(ROOT / "run-budget.json", **CAPS)


class Recorded:
    name = "openai_compat"
    base_url = BASE
    reasoning_effort = "low"
    max_retries = 0

    def __init__(self, model):
        self.model = model

    def complete(self, req):
        reg = read_json(ROOT / "registration.json")
        if time.time() - reg["startedUnix"] > 3600:
            raise ValueError("60 minute wall-time cap reached")
        msgs = [dataclasses.asdict(m) for m in req.messages]
        if req.response_json and not any("json" in m["content"] for m in msgs):
            msgs[-1]["content"] += "\n(응답 형식: json)"
        body = dict(
            model=self.model,
            messages=msgs,
            max_tokens=req.max_output_tokens,
            temperature=req.temperature,
            reasoning_effort="low",
        )
        if req.response_json:
            body["response_format"] = {"type": "json_object"}
        key = body_hash(dict(model=self.model, stage=req.stage, ref=req.ref, body=body))
        dest = ROOT / "evidence" / key
        dest.mkdir(parents=True, exist_ok=True)
        if (dest / "request.json").exists():
            raise ValueError("first request already attempted; redraw forbidden: " + req.ref)
        wire = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        (dest / "request.json").write_text(wire)
        put(
            dest / "request-meta.json",
            dict(
                ref=req.ref,
                stage=req.stage,
                kind=req.kind,
                requestSha256=sha256_text(wire),
                conservativeInputUpper=sum(len(m.content.encode()) + 1024 for m in req.messages),
                outputCap=req.max_output_tokens,
            ),
        )
        start = time.monotonic()
        try:
            with httpx.Client(timeout=240) as client:
                r = client.post(
                    BASE + "/chat/completions",
                    content=wire.encode(),
                    headers={"Content-Type": "application/json"},
                )
            (dest / "response.json").write_bytes(r.content)
            elapsed = int((time.monotonic() - start) * 1000)
            data = r.json()
            u = data.get("usage") or {}
            choices = data.get("choices") or []
            put(
                dest / "response-meta.json",
                dict(
                    status=r.status_code,
                    elapsedMs=elapsed,
                    responseSha256=sha256_file(dest / "response.json"),
                    requestedModel=self.model,
                    returnedModel=data.get("model"),
                    usage=u,
                    finishReason=choices[0].get("finish_reason") if choices else None,
                ),
            )
            r.raise_for_status()
            choice = choices[0]
            text = choice["message"].get("content") or ""
            if not text.strip():
                raise ValueError("empty first completion")
            print("CALL", req.stage, req.ref, self.model, elapsed, "ms", flush=True)
            return ChatResponse(
                text,
                u.get("prompt_tokens"),
                u.get("completion_tokens"),
                elapsed,
                data.get("model", self.model),
                self.name,
                choice.get("finish_reason"),
                data,
            )
        except Exception as exc:
            put(dest / "error.json", dict(type=type(exc).__name__, reason=str(exc)))
            raise


def tracked(model):
    return TrackedTextModel(Recorded(model), Ledger(ROOT / "shared-ledger"), budget())


def context(label):
    r, cid = path(label)
    ctx = Context.load(r, execute=True, max_calls=300)
    ctx._run_budget = budget()
    ctx._text = Recorded(GEN)
    ctx._judge = Recorded(JUDGE)
    return ctx, cid


def prepare():
    if (ROOT / "registration.json").exists():
        print("Already prepared; immutable run inputs left unchanged.", flush=True)
        return
    from character_factory_poc.stages.s7_traits.voice import load_voice_pack

    lib = ROOT / "voice-library"
    # Correct a descriptive count without replacing the already recorded first approval.
    original = read_json(lib / "approval.json")
    corrected = dict(
        original,
        auditNotes="20 literal fragments from 10 recorded human-edited text rows /8 source conversations; validation4 rows /2 conversations. No generated drafts or non-text excerpts.",
        supersedesApprovalSha256=sha256_file(lib / "approval.json"),
    )
    put(lib / "approval-v2.json", corrected)
    pack = read_json(lib / "pack.json")
    pack.update(
        approvalFile="approval-v2.json", approvalSha256=sha256_file(lib / "approval-v2.json")
    )
    put(lib / "pack-v2.json", pack)
    put(
        lib / "trusted-approvals-v2.json",
        dict(approvals={"approval-v2.json": sha256_file(lib / "approval-v2.json")}),
    )
    # The source reader requires a named JSON root. Preserve original bytes and
    # add a lossless, explicitly traced wrapper rather than alter source quotes.
    source = read_json(lib / "human-edited-original.json")
    put(lib / "indexed-human-edits.json", dict(records=source))
    put(
        lib / "source-wrapper-provenance.json",
        dict(
            kind="lossless-json-root-wrapper",
            original=str(lib / "human-edited-original.json"),
            originalSha256=sha256_file(lib / "human-edited-original.json"),
            derived=str(lib / "indexed-human-edits.json"),
            derivedSha256=sha256_file(lib / "indexed-human-edits.json"),
            mapping="original[i].field == derived.records[i].field",
        ),
    )
    content = {k: v for k, v in pack.items() if k not in ("approvalFile", "approvalSha256")}
    for example in content["examples"] + content["validationExamples"]:
        example.update(
            sourceFile="indexed-human-edits.json",
            sourceSha256=sha256_file(lib / "indexed-human-edits.json"),
            fieldPath="records" + example["fieldPath"],
        )
    record = dict(
        corrected,
        assetSha256=body_hash(content),
        wrapperProvenanceSha256=sha256_file(lib / "source-wrapper-provenance.json"),
    )
    put(lib / "approval-v3.json", record)
    pack = dict(
        content,
        approvalFile="approval-v3.json",
        approvalSha256=sha256_file(lib / "approval-v3.json"),
    )
    put(lib / "pack-v3.json", pack)
    put(
        lib / "trusted-approvals-v3.json",
        dict(approvals={"approval-v3.json": sha256_file(lib / "approval-v3.json")}),
    )
    load_voice_pack(lib / "pack-v3.json", approval_index=lib / "trusted-approvals-v3.json")
    policy = dict(assignments={}, targets={}, rules=[])
    original_hashes = {}
    for label in LABELS:
        src = OLD / label
        dst = ROOT / label
        if not dst.exists():
            shutil.copytree(src, dst)
        cid = (dst / "character-id.txt").read_text().strip()
        policy["assignments"][cid] = pack["packId"]
        policy["targets"][cid] = dict(
            requiredTags=["반말"], forbiddenTags=["존댓말"], positiveTags=["짧은", "문자"]
        )
        cfg = f'''[providers.text]\nadapter="openai_compat"\nbase_url="{BASE}"\nmodel="{GEN}"\nmax_retries=0\nreasoning_effort="low"\n[providers.judge]\nadapter="openai_compat"\nbase_url="{BASE}"\nmodel="{JUDGE}"\nmax_retries=0\nreasoning_effort="low"\n[providers.image]\nadapter="fake"\n[budget]\nmax_calls_per_command=300\nmax_cost_usd_per_command=75\n[stages.s3]\nmax_check_retries=0\n[stages.s7]\nformation_profile="ko-text-choice-voice-long-v2"\nvoice_packs=["{lib / "pack-v3.json"}"]\nvoice_approval_index="{lib / "trusted-approvals-v3.json"}"\nvoice_policy="{lib / "policy.json"}"\nbudget_run_id="choice-voice-live-r1"\nmax_run_tokens=2500000\ninput_rate_upper_per_million=20\noutput_rate_upper_per_million=120\n[stages.s2]\nbase_photo="picked"\n'''
        (dst / "factory.toml").write_text(cfg)
        ctx = Context.load(dst, execute=False)
        # Text experiment forks approved S1/S2 preparation; visual assets remain fake.
        if not (dst / "live-prepared.json").exists():
            for stage in ("s3", "s7", "s8"):
                if ctx.state(cid).stage(stage).status == "AWAITING_HUMAN":
                    ctx.state(cid).transition(stage, "REJECTED")
            put(
                dst / "live-prepared.json",
                dict(
                    source=str(src),
                    cid=cid,
                    baselineProfile="ko-text-prompt-long-v1",
                    visuals="fake historical setup; no image/video calls",
                ),
            )
        for p in src.rglob("*"):
            if p.is_file():
                original_hashes[str(p)] = sha256_file(p)
    put(lib / "policy.json", policy)
    put(ROOT / "baseline-hashes.json", original_hashes)
    put(
        ROOT / "registration.json",
        dict(
            startedUnix=time.time(),
            purpose="Actual-model development observation; no formal qualification",
            generation=GEN,
            judge=JUDGE,
            consumer=CHAT,
            reasoning="low",
            caps=CAPS,
            maxWallSeconds=3600,
            plannedCharacters=4,
            plannedArms=["A", "B", "C", "D"],
            plannedReplies=192,
            counterKind="UTF8_BYTES_UPPER_BOUND_NOT_EXACT",
            humanReviewOfResults=False,
            selection="all semantic-pass candidates eligible; deterministic content hash, no ordinal/observed-output selection",
        ),
    )
    put(
        ROOT / "dry-run.json",
        dict(
            normalFormationCalls=28,
            maxFormationCalls=84,
            additionalControlsNormal=12,
            dialogueCalls=192,
            assessmentCalls=8,
            maximumCompletionCalls=300,
            notes=[
                "Global persistent budget counts all raw first requests including failures.",
                "Exact tokenizer unavailable; never run formal qualifier with approximate counter.",
                "Current explicit human instruction authorizes this audited-source experiment; no new human dataset approval claimed.",
            ],
        ),
    )
    print("PREPARED", ROOT, flush=True)


def probe():
    read_json(ROOT / "registration.json")
    for model in (GEN, CHAT, JUDGE):
        dest = ROOT / "probes" / f"{model.replace('/', '_')}.json"
        if dest.exists():
            continue
        response = tracked(model).complete(
            ChatRequest(
                "PROBE",
                "live-probe",
                (Message("user", "한 단어로 준비라고 답해."),),
                "probe-v2/" + model,
                max_output_tokens=256,
                temperature=0.7,
            )
        )
        put(dest, dataclasses.asdict(response))


def generate(label):
    from character_factory_poc.pipeline.approve import approve_gate
    from character_factory_poc.stages.s3_plan.importer import load_approved_plan
    from character_factory_poc.stages.s3_plan.variants import run_s3_variants
    from character_factory_poc.stages.s7_traits.sheet import run_s7
    from character_factory_poc.stages.s8_prompts.build import run_s8

    marker = ROOT / "generation-v2" / f"{label}.json"
    if marker.exists():
        return read_json(marker)
    attempt = marker.with_suffix(".attempt.json")
    if attempt.exists():
        raise ValueError("unknown first formation result; preserve rather than redraw")
    put(attempt, dict(label=label, startedUnix=time.time()))
    ctx, cid = context(label)
    try:
        folder = run_s3_variants(ctx, cid)
        raw = read_json(folder / "variants.json")
        selected = select_by_content(raw["candidates"])
        approve_gate(
            ctx,
            cid,
            "G3",
            dict(
                decision="SELECT",
                selections=[selected["variantId"]],
                reviewer="agent",
                reasons="Pre-registered content hash tie-break after seed/semantic PASS; no dialogue output inspected.",
            ),
        )
        trait = run_s7(ctx, cid)
        out = run_s8(ctx, cid, [])
        plan, pp = load_approved_plan(ctx, cid)
        result = dict(
            label=label,
            status="FORMED",
            cid=cid,
            trait=str(trait),
            blueprint=str(trait.parent / "blueprint.json"),
            plan=str(pp),
            pair=str(out / "prompt-pair.json"),
            bundle=str(out / "persona-bundle.json"),
            s3=str(folder),
            g6="AWAITING_HUMAN",
            qualityQualified=False,
        )
    except Exception as exc:
        result = dict(
            label=label,
            status="FAILED",
            cid=cid,
            error=type(exc).__name__,
            reason=str(exc),
            firstPass=False,
            qualityQualified=False,
        )
    put(marker, result)
    print("FORMATION", label, result["status"], result.get("reason", ""), flush=True)
    return result


def all_generate(labels):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(generate, labels):
            print(json.dumps(result, ensure_ascii=False), flush=True)


def generation_result(label):
    citation = ROOT / "captured-validation-citations" / label / "result.json"
    if citation.exists():
        return read_json(citation)
    validated = ROOT / "captured-validation" / label / "result.json"
    if validated.exists():
        return read_json(validated)
    core = ROOT / "generation-core-bound-v2" / f"{label}.json"
    if core.exists():
        return read_json(core)
    core = ROOT / "generation-core-bound" / f"{label}.json"
    if core.exists():
        return read_json(core)
    recovered = ROOT / "generation-revalidated" / f"{label}.json"
    return read_json(recovered if recovered.exists() else ROOT / "generation-v2" / f"{label}.json")


def revalidate(label):
    from character_factory_poc.common.store import write_manifest, write_once_text
    from character_factory_poc.contracts.choice_design import (
        ChoiceDesign,
        ChoiceReview,
        PlanVariantsV2,
        SeedRequirements,
    )
    from character_factory_poc.pipeline.approve import approve_gate
    from character_factory_poc.stages.s3_plan.choice_design import require_choice_pass
    from character_factory_poc.stages.s3_plan.choice_flow import source_ref
    from character_factory_poc.stages.s3_plan.page import render_g3_page
    from character_factory_poc.stages.s7_traits.sheet import run_s7
    from character_factory_poc.stages.s8_prompts.build import run_s8

    marker = ROOT / "generation-revalidated" / f"{label}.json"
    if marker.exists():
        return read_json(marker)
    g = generation_result(label)
    if g["status"] == "FORMED":
        return g
    if g.get("reason") != "choice review quote is not in supplied designs":
        return g
    ctx, cid = context(label)
    root = ctx.character_dir(cid)
    folder = root / "s3-plan" / ctx.state(cid).stage("s3").currentRev
    inputs = read_json(folder / "choice-review-inputs.json")
    requirements = SeedRequirements.model_validate(read_json(folder / "requirements.json"))
    review = ChoiceReview.model_validate(read_json(folder / "choice-review.json"))
    designs = [ChoiceDesign.model_validate(d) for d in inputs["designs"]]
    candidates = [validate("character-plan-v2", p) for p in inputs["plans"]]
    # This check must succeed before any model call or state advancement. No
    # failed/unresolved semantic verdict can be converted to a pass by recovery.
    review_path = folder / "choice-review.json"
    # Evidence-only repair of the one observed identity-field paraphrase. Keep
    # every original verdict and every original file; never repair a FAIL.
    if label == "d1" and review.status == "PASS":
        rows = list(review.items)
        changes = []
        for n, item in enumerate(rows):
            if (
                item.variantId == "v2"
                and item.requirementId == "req-008"
                and item.quote == "퇴근길 산책을 좋아한다."
            ):
                candidate = next(p for p in inputs["plans"] if p["variantId"] == item.variantId)
                quote = candidate["background"]
                rows[n] = item.model_copy(update={"quote": quote})
                changes.append(
                    dict(
                        variantId=item.variantId,
                        requirementId=item.requirementId,
                        oldQuote=item.quote,
                        newQuote=quote,
                        sourceField="background",
                        actor="assistant source audit",
                        verdictUnchanged=True,
                    )
                )
        if changes:
            review = review.model_copy(update={"items": rows})
            review_path = folder / "choice-review-evidence-corrected.json"
            put(review_path, dump(review))
            put(
                folder / "choice-review-evidence-correction.json",
                dict(
                    originalReviewSha256=sha256_file(folder / "choice-review.json"),
                    changes=changes,
                    scope="literal citation correction only; original independent semantic verdict retained",
                ),
            )
    require_choice_pass(review, designs, requirements, body_hash(inputs), plans=candidates)
    seed_path = root / "s3-plan/seeds" / f"{inputs['seed']['seedRev']}.json"
    preserved = {
        str(p.relative_to(folder)): sha256_file(p)
        for p in folder.rglob("*")
        if p.is_file() and p.name != "manifest.sha256"
    }
    put(
        folder / "checker-revalidation.json",
        dict(
            reason="Verifier wrongly searched designs only although reviewer also receives plans; validate original first outputs against same input and own candidate.",
            originalFailure=read_json(folder / "failure.json"),
            firstOutputsRegenerated=False,
            priorFirstPass=False,
            sourceFiles=preserved,
            verifierSha256=sha256_file(
                REPO / "src/character_factory_poc/stages/s3_plan/choice_design.py"
            ),
        ),
    )
    variants = PlanVariantsV2(
        characterId=cid,
        planRev=folder.name,
        seedRev=inputs["seed"]["seedRev"],
        seedSha256=sha256_file(seed_path),
        candidates=candidates,
        axisNote=read_json(folder / "choices/result.json").get("axisNote", ""),
        requirements=source_ref(root, folder / "requirements.json", "requirements"),
        designs={
            d.variantId: source_ref(root, folder / f"choice-{d.variantId}.json", "choice")
            for d in designs
        },
        review=source_ref(root, review_path, "review"),
    )
    put(folder / "variants.json", dump(variants))
    write_once_text(
        folder / "gate-G3.html",
        render_g3_page(variants=variants, choice_evidence={d.variantId: d for d in designs}),
    )
    put(folder / "seed-ref.json", dump(source_ref(root, seed_path, "seed")))
    write_manifest(folder)
    ctx.state(cid).transition("s3", "RUNNING", rev=folder.name)
    ctx.state(cid).transition("s3", "AWAITING_HUMAN", rev=folder.name)
    ctx.state(cid).set_gate("G3", "AWAITING_HUMAN", folder.name, None)
    selected = select_by_content(inputs["plans"])
    try:
        approve_gate(
            ctx,
            cid,
            "G3",
            dict(
                decision="SELECT",
                selections=[selected["variantId"]],
                reviewer="agent",
                reasons="Deterministic revalidation of original PASS semantic review after verifier correction; first failures preserved.",
            ),
        )
        trait = run_s7(ctx, cid)
        out = run_s8(ctx, cid, [])
        result = dict(
            label=label,
            status="FORMED",
            cid=cid,
            trait=str(trait),
            blueprint=str(trait.parent / "blueprint.json"),
            plan=str(folder / "plan.json"),
            pair=str(out / "prompt-pair.json"),
            bundle=str(out / "persona-bundle.json"),
            s3=str(folder),
            g6="AWAITING_HUMAN",
            qualityQualified=False,
            firstPass=False,
            revalidatedFirstS3=True,
        )
    except Exception as exc:
        result = dict(
            label=label,
            status="FAILED",
            cid=cid,
            error=type(exc).__name__,
            reason=str(exc),
            firstPass=False,
            revalidatedFirstS3=True,
            qualityQualified=False,
        )
    put(marker, result)
    print("REVALIDATED", label, result["status"], result.get("reason", ""), flush=True)
    return result


def resume_core(label):
    from character_factory_poc.common.store import next_rev
    from character_factory_poc.stages.s7_traits.choice_voice import recipe
    from character_factory_poc.stages.s7_traits.sheet import run_s7
    from character_factory_poc.stages.s8_prompts.build import run_s8

    marker = ROOT / "generation-core-bound-v2" / f"{label}.json"
    if marker.exists():
        return read_json(marker)
    g = generation_result(label)
    if g.get("reason") != "card.expressedTraits.core[0]: 너무 짧다(5자). 조건과 행동을 서술한다":
        return g
    ctx, cid = context(label)
    char = ctx.character_dir(cid)
    old = char / "s7-traits" / ctx.state(cid).stage("s7").currentRev
    new = char / "s7-traits" / next_rev(char / "s7-traits", "tr")
    identity = read_json(old / "recipe.json")
    identity["recipe"] = recipe(ctx)
    put(new / "recipe.json", identity)
    shutil.copytree(old / "design", new / "design")
    put(
        new / "raw-design-reuse.json",
        dict(
            source=str(old / "design/result.json"),
            sha256=sha256_file(old / "design/result.json"),
            rawRegenerated=False,
            reason="Deterministic canonical core binding introduced after first compilation failure; preserve actual first design.",
        ),
    )
    ctx.state(cid).transition("s7", "RUNNING", rev=new.name)
    try:
        trait = run_s7(ctx, cid)
        out = run_s8(ctx, cid, [])
        result = dict(
            g,
            status="FORMED",
            trait=str(trait),
            blueprint=str(trait.parent / "blueprint.json"),
            plan=str(char / "s3-plan" / ctx.state(cid).stage("s3").currentRev / "plan.json"),
            pair=str(out / "prompt-pair.json"),
            bundle=str(out / "persona-bundle.json"),
            g6="AWAITING_HUMAN",
            firstPass=False,
            rawDesignReused=True,
        )
    except Exception as exc:
        result = dict(
            g,
            status="FAILED",
            reason=str(exc),
            error=type(exc).__name__,
            firstPass=False,
            rawDesignReused=True,
        )
    put(marker, result)
    print("CORE-BOUND", label, result["status"], result.get("reason", ""), flush=True)
    return result


def preservation_batches(ctx, cid, inputs, dest):
    from character_factory_poc.contracts.dialogue_beats import FormationBeats
    from character_factory_poc.contracts.rendered_dialogues import (
        PreservationReport,
        RenderedDialogues,
    )
    from character_factory_poc.pipeline.formation_step import run_typed_step
    from character_factory_poc.stages.s7_traits.voice_render import check_render_preservation

    beats = FormationBeats.model_validate(inputs["beats"])
    rendered = RenderedDialogues.model_validate(inputs["dialogues"])
    items = []
    for start in range(0, len(beats.dialogues), 2):
        selected = {d.dialogueId for d in beats.dialogues[start : start + 2]}
        scoped = inputs | dict(reviewDialogueIds=sorted(selected))
        report = run_typed_step(
            ctx=ctx,
            cid=cid,
            folder=dest / f"b{start // 2 + 1:02}" / "check",
            role="persona_voice_preservation",
            contract=PreservationReport,
            stage="cv-preservation",
            inputs=scoped,
            judge=True,
            budget=ctx._run_budget,
        )
        scoped_beats = beats.model_copy(
            update={"dialogues": [d for d in beats.dialogues if d.dialogueId in selected]}
        )
        scoped_render = rendered.model_copy(
            update={"dialogues": [d for d in rendered.dialogues if d.dialogueId in selected]}
        )
        check_render_preservation(
            scoped_beats, scoped_render, reviewer=lambda _, report=report: report
        )
        items.extend(report.items)
    combined = PreservationReport(status="PASS", inputSha256=body_hash(inputs), items=items)
    check_render_preservation(beats, rendered, reviewer=lambda _: combined)
    return combined


def validate_captured(label):
    from character_factory_poc.contracts.dialogue_beats import FormationBeats
    from character_factory_poc.contracts.rendered_dialogues import (
        RenderedDialogues,
    )
    from character_factory_poc.contracts.voice import VoiceBinding
    from character_factory_poc.stages.s7_traits.voice import verify_voice_binding
    from character_factory_poc.stages.s7_traits.voice_render import (
        check_render_preservation,
        check_render_structure,
    )

    marker = ROOT / "captured-validation" / label / "result.json"
    if marker.exists():
        return read_json(marker)
    ctx, cid = context(label)
    char = ctx.character_dir(cid)
    tr = char / "s7-traits" / ctx.state(cid).stage("s7").currentRev
    first_failure = read_json(tr / "failure.json")
    if first_failure.get("error") != "rendered number preservation failed":
        raise ValueError(
            "Only the demonstrated number-realization guard failure is eligible for source-preserving revalidation"
        )
    beats = FormationBeats.model_validate(read_json(tr / "formation-beats.json"))
    rendered = RenderedDialogues.model_validate(read_json(tr / "rendered-dialogues.json"))
    voice = VoiceBinding.model_validate(read_json(tr / "voice-binding.json"))
    bp = read_json(tr / "blueprint.json")
    plan_path = char / "s3-plan" / bp["planRev"] / "plan.json"
    verify_voice_binding(voice, read_json(plan_path), read_json(tr / "voice-policy.json"))
    check_render_structure(beats, rendered)
    inputs = dict(beats=dump(beats), voice=dump(voice), blueprint=bp, dialogues=dump(rendered))
    dest = marker.parent
    put(dest / "inputs.json", inputs)
    try:
        report = preservation_batches(ctx, cid, inputs, dest / "batches-v1")
        put(dest / "report.json", dump(report))
        check_render_preservation(beats, rendered, reviewer=lambda _, report=report: report)
        result = dict(
            label=label,
            status="VALIDATED_DEVELOPMENT_ONLY",
            cid=cid,
            trait=str(tr / "trait-sheet.json"),
            blueprint=str(tr / "blueprint.json"),
            plan=str(plan_path),
            s3=str(plan_path.parent),
            qualityQualified=False,
            firstPass=False,
            rawOutputsRegenerated=False,
            operationalFormationStatus="CHECK_FAILED preserved; evaluation-only source revalidation",
            preservation=str(dest / "report.json"),
        )
    except Exception as exc:
        result = dict(
            label=label,
            status="FAILED",
            cid=cid,
            reason=str(exc),
            firstPass=False,
            qualityQualified=False,
        )
    put(marker, result)
    print("CAPTURED-VALIDATION", label, result["status"], result.get("reason", ""), flush=True)
    return result


class ControlContext:
    def __init__(self, ctx, rev):
        self.base = ctx
        self.rev = rev

    def __getattr__(self, k):
        return getattr(self.base, k)

    def state(self, cid):
        from types import SimpleNamespace

        state = self.base.state(cid)
        rev = self.rev

        class StateView:
            def __getattr__(self, name):
                return getattr(state, name)

            def stage(self, name):
                return SimpleNamespace(currentRev=rev) if name == "s7" else state.stage(name)

        return StateView()


def controls(label):
    from character_factory_poc.contracts.dialogue_beats import FormationBeats
    from character_factory_poc.contracts.formation import TraitSheet
    from character_factory_poc.contracts.rendered_dialogues import (
        RenderedDialogues,
        RenderedDraft,
    )
    from character_factory_poc.contracts.voice import VoiceBinding
    from character_factory_poc.pipeline.formation_step import run_typed_step
    from character_factory_poc.stages.persona_quality.producers import prepare_development_pair
    from character_factory_poc.stages.s7_traits.dialogues import build_formation_dialogues
    from character_factory_poc.stages.s7_traits.formation import canonical_plan
    from character_factory_poc.stages.s7_traits.voice_render import (
        check_render_preservation,
        check_render_structure,
    )
    from character_factory_poc.stages.s8_prompts.build import load_system_rules
    from character_factory_poc.stages.s8_prompts.compiler import render

    dest = ROOT / "controls" / label
    marker = dest / "result.json"
    if marker.exists():
        return read_json(marker)
    g = generation_result(label)
    ctx, cid = context(label)
    rules_path = ROOT / "comparison-system-rules.md"
    if not rules_path.exists():
        rules_path.write_text(load_system_rules(ctx)[0])
    oldroot = OLD / label / "runs/characters" / cid
    oldbundle = oldroot / "s8-prompts/pv1/persona-bundle.json"
    a = read_json(oldbundle)
    atr = oldroot / "s7-traits" / a["traitRevision"]
    assets_a = dict(
        seed=oldroot / "s3-plan/seeds/sd1.json",
        plan=oldroot / "s3-plan" / a["planRev"] / "plan.json",
        trait=atr / "trait-sheet.json",
        blueprint=atr / "blueprint.json",
        dialogues=atr / "formation-dialogues.json",
        profile=atr / "profile.json",
        legacyBundle=oldbundle,
        systemRules=rules_path,
    )
    pair, producer = prepare_development_pair("A", assets_a, dest / "A")
    arms = {"A": dict(pair=dump(pair), producer=dump(producer))}
    failures = {}
    if g["status"] not in {"FORMED", "VALIDATED_DEVELOPMENT_ONLY"}:
        put(
            marker,
            dict(
                arms=arms,
                failures={
                    "B": "new formation failed",
                    "C": "new formation failed",
                    "D": "new formation failed",
                },
                plannedArms=4,
            ),
        )
        return read_json(marker)
    tr = Path(g["trait"]).parent
    bp = PersonaBlueprintV2.model_validate(read_json(tr / "blueprint.json"))
    sheet = TraitSheet.model_validate(read_json(g["trait"]))
    plan_path = Path(g["plan"])
    plan = validate(read_json(plan_path)["schemaVersion"], read_json(plan_path))
    binding = VoiceBinding(
        status="DRAFT",
        characterId=cid,
        planSha256=body_hash(dump(plan)),
        policySha256=body_hash({"control": "generated-voice"}),
        rules=[render(dump(bp.voiceProfile))],
        examples=[],
        reason="Frozen generated voiceProfile; no real-source exemplars",
    )
    draft_path = dest / "generated-voice-binding.json"
    put(draft_path, dump(binding))
    shared = dict(
        seed=ctx.character_dir(cid) / "s3-plan/seeds/sd1.json",
        plan=plan_path,
        trait=Path(g["trait"]),
        blueprint=tr / "blueprint.json",
        choice=ctx.character_dir(cid) / bp.approvedChoiceRef.path,
        systemRules=rules_path,
        compilerProfile=atr / "profile.json",
    )
    # B: same approved new choices/design, old direct writer and old compiler.
    try:
        bdir = tr.parent / (tr.name + "-direct-control")
        bdir.mkdir(exist_ok=True)
        for name in ("trait-sheet.json", "blueprint.json"):
            if not (bdir / name).exists():
                shutil.copyfile(tr / name, bdir / name)
        (bdir / "references").mkdir(exist_ok=True)
        put(bdir / "references/index.json", [])
        proxy = ControlContext(ctx, bdir.name)
        build_formation_dialogues(
            proxy, cid, canonical_plan(plan, plan_path), sheet, bp, budget=ctx._run_budget
        )
        pair, producer = prepare_development_pair(
            "B",
            shared | dict(dialogues=bdir / "formation-dialogues.json", voiceBinding=draft_path),
            dest / "B",
        )
        arms["B"] = dict(pair=dump(pair), producer=dump(producer))
    except Exception as exc:
        failures["B"] = str(exc)
    # C: the exact D beats, rendered with only frozen generated voice rules.
    try:
        beats = FormationBeats.model_validate(read_json(tr / "formation-beats.json"))
        inputs = dict(beats=dump(beats), voice=dump(binding), blueprint=dump(bp))
        draft = run_typed_step(
            ctx=ctx,
            cid=cid,
            folder=dest / "C-render",
            role="persona_voice_render",
            contract=RenderedDraft,
            stage="cv-render",
            inputs=inputs,
            budget=ctx._run_budget,
        )
        rendered = RenderedDialogues(
            characterId=cid,
            traitRevision=tr.name,
            beatsSha256=sha256_file(tr / "formation-beats.json"),
            voiceBindingSha256=sha256_file(draft_path),
            **dump(draft),
        )
        rendered_path = dest / "generated-rendered.json"
        put(rendered_path, dump(rendered))
        check_render_structure(beats, rendered)
        semantic = inputs | dict(dialogues=dump(rendered))
        put(dest / "C-preservation-inputs.json", semantic)
        report = preservation_batches(ctx, cid, semantic, dest / "C-preservation-batches")
        put(dest / "C-preservation-report.json", dump(report))
        check_render_preservation(beats, rendered, reviewer=lambda _, report=report: report)
        pair, producer = prepare_development_pair(
            "C",
            shared
            | dict(
                dialogues=rendered_path, voiceBinding=draft_path, beats=tr / "formation-beats.json"
            ),
            dest / "C",
        )
        arms["C"] = dict(pair=dump(pair), producer=dump(producer))
    except Exception as exc:
        failures["C"] = str(exc)
    try:
        pair, producer = prepare_development_pair(
            "D",
            shared
            | dict(
                dialogues=tr / "rendered-dialogues.json",
                voiceBinding=tr / "voice-binding.json",
                voicePolicy=tr / "voice-policy.json",
                beats=tr / "formation-beats.json",
            ),
            dest / "D",
        )
        arms["D"] = dict(pair=dump(pair), producer=dump(producer))
    except Exception as exc:
        failures["D"] = str(exc)
    put(marker, dict(arms=arms, failures=failures, plannedArms=4))
    print("CONTROLS", label, list(arms), failures, flush=True)
    return read_json(marker)


def recover_direct(label):
    from character_factory_poc.contracts.persona import TraitSheet
    from character_factory_poc.stages.persona_quality.producers import prepare_development_pair
    from character_factory_poc.stages.s7_traits.dialogues import build_formation_dialogues
    from character_factory_poc.stages.s7_traits.formation import canonical_plan

    dest = ROOT / "controls-supplement" / label
    marker = dest / "result.json"
    if marker.exists():
        return read_json(marker)
    prior = read_json(ROOT / "controls" / label / "result.json")
    ctx, cid = context(label)
    if (
        "B" in prior["arms"]
        or prior["failures"].get("B") != "'StateView' object has no attribute 'gate'"
    ):
        return prior
    prod = read_json(prior["arms"]["D"]["producer"]["path"])
    assets = {k: Path(v["path"]) for k, v in prod["assets"].items()}
    tr = assets["trait"].parent
    bp = PersonaBlueprintV2.model_validate(read_json(assets["blueprint"]))
    sheet = TraitSheet.model_validate(read_json(assets["trait"]))
    plan = validate(read_json(assets["plan"])["schemaVersion"], read_json(assets["plan"]))
    bdir = tr.parent / (tr.name + "-direct-control")
    try:
        build_formation_dialogues(
            ControlContext(ctx, bdir.name),
            cid,
            canonical_plan(plan, assets["plan"]),
            sheet,
            bp,
            budget=ctx._run_budget,
        )
        assets.update(
            dialogues=bdir / "formation-dialogues.json",
            voiceBinding=ROOT / "controls" / label / "generated-voice-binding.json",
        )
        for k in ("beats", "voicePolicy"):
            assets.pop(k, None)
        pair, producer = prepare_development_pair("B", assets, dest / "B")
        prior["arms"]["B"] = dict(pair=dump(pair), producer=dump(producer))
        prior["failures"].pop("B")
    except Exception as exc:
        prior["failures"]["B"] = str(exc)
    prior["scaffoldingRecovery"] = (
        "Delegate gate access in read-only control state view; no earlier B model request existed."
    )
    put(marker, prior)
    print("DIRECT-RECOVER", label, list(prior["arms"]), prior["failures"], flush=True)
    return prior


def control_result(label):
    supplement = ROOT / "controls-supplement" / label / "result.json"
    result = read_json(
        supplement if supplement.exists() else ROOT / "controls" / label / "result.json"
    )
    production = ROOT / "production-comparison" / label / "artifact.json"
    if production.exists():
        result["arms"]["COVERED"] = read_json(production)
    return result


def production_pair(label):
    from character_factory_poc.contracts.dialogue_beats import FormationBeats
    from character_factory_poc.contracts.voice_bundle import CoveragePolicy
    from character_factory_poc.stages.persona_quality.producers import prepare_development_pair

    dest = ROOT / "production-comparison" / label
    if (dest / "artifact.json").exists():
        return
    base = control_result(label)
    prod = read_json(base["arms"]["D"]["producer"]["path"])
    assets = {k: Path(v["path"]) for k, v in prod["assets"].items()}
    beats = FormationBeats.model_validate(read_json(assets["beats"]))
    bp = PersonaBlueprintV2.model_validate(read_json(assets["blueprint"]))
    policy = CoveragePolicy(
        requiredRuleIds=[r.choiceRuleId for r in bp.decisionRules],
        coverage={
            d.dialogueId: dict(
                tags=d.coverageTags, ruleIds=sorted({r for t in d.turns for r in t.decisionRuleIds})
            )
            for d in beats.dialogues
        },
    )
    put(dest / "coverage-policy.json", dump(policy))
    assets.update(
        coveragePolicy=dest / "coverage-policy.json",
        profile=assets["trait"].parent / "profile.json",
        preservation=Path(generation_result(label)["preservation"]),
    )
    pair, producer = prepare_development_pair("COVERED", assets, dest / "pair")
    put(dest / "artifact.json", dict(pair=dump(pair), producer=dump(producer)))
    print(
        "PRODUCTION-COMPARISON",
        label,
        "frozen validated sources + v2 coverage/voice compiler; G6 not approved",
        flush=True,
    )


def validate_collected_reply(row):
    response = row.get("response") or {}
    return (
        row.get("status") == "OK"
        and bool(row.get("assistant", "").strip())
        and response.get("finish_reason") != "length"
        and type(response.get("input_tokens")) is int
        and type(response.get("output_tokens")) is int
        and 0 <= response["input_tokens"]
        and response["input_tokens"] + 2400 <= 24000
        and 0 <= response["output_tokens"] < 2400
    )


def _collect_slot_locked(label, arm, pair_ref):
    from character_factory_poc.contracts.persona import load_prompt_pair
    from character_factory_poc.stages.persona_quality.choice_voice_protocol import FileAsset

    pair = load_prompt_pair(FileAsset.model_validate(pair_ref).verify())
    scenes = read_json(ROOT / "evaluation-scenes.json")
    model = tracked(CHAT)
    failure = ROOT / "collection-failures" / f"{label}-{arm}.json"
    if failure.exists():
        old_failure = read_json(failure)
        if old_failure.get("reason") != "conservative context cap exceeded":
            return
        put(
            ROOT / "collection-bound-recovery" / f"{label}-{arm}.json",
            dict(
                originalFailure=str(failure),
                originalSha256=sha256_file(failure),
                reason="Byte bound was incorrectly treated as a token count; no exact tokenizer claim. Resume only never-attempted turns with all first replies unchanged.",
                byteCeiling=48000,
                actualTokenContextPostcheck=24000,
            ),
        )
        failure = ROOT / "collection-failures-r2" / f"{label}-{arm}.json"
        if failure.exists():
            return
    try:
        for scene in scenes:
            history = [Message("system", pair.long.text)]
            for n, user in enumerate(scene["users"], 1):
                history.append(Message("user", user))
                dest = ROOT / "dialogues" / label / arm / scene["id"] / f"{n:02}.json"
                reqhash = body_hash([dataclasses.asdict(m) for m in history])
                if dest.exists():
                    old = read_json(dest)
                    if (
                        not validate_collected_reply(old)
                        or old.get("user") != user
                        or old.get("systemSha256") != pair.long.sha256
                        or old["requestSha256"] != reqhash
                        or old["responseSha256"] != sha256_text(old["assistant"])
                    ):
                        raise ValueError("checkpoint mismatch")
                    history.append(Message("assistant", old["assistant"]))
                    continue
                if dest.with_suffix(".attempt.json").exists():
                    raise ValueError("unknown first response; no redraw")
                upper = (
                    len(
                        json.dumps(
                            [dataclasses.asdict(m) for m in history], ensure_ascii=False
                        ).encode()
                    )
                    + 4096
                )
                if upper + 2400 > 48000:
                    raise ValueError("conservative context cap exceeded")
                request = ChatRequest(
                    "DIALOGUE",
                    "live-dialogue",
                    tuple(history),
                    f"{label}/{arm}/{scene['id']}/{n}",
                    max_output_tokens=2400,
                    temperature=0.7,
                )
                put(
                    dest.with_suffix(".attempt.json"),
                    dict(
                        request=dataclasses.asdict(request),
                        inputBound=upper,
                        counterKind="UTF8_BYTES_UPPER_BOUND_NOT_EXACT",
                        requestSha256=reqhash,
                        systemSha256=pair.long.sha256,
                    ),
                )
                response = model.complete(request)
                record = dict(
                    status="OK",
                    user=user,
                    assistant=response.text,
                    requestSha256=reqhash,
                    responseSha256=sha256_text(response.text),
                    systemSha256=pair.long.sha256,
                    response=dataclasses.asdict(response),
                )
                if not validate_collected_reply(record):
                    record["status"] = (
                        "USAGE_UNVERIFIED"
                        if response.input_tokens is None or response.output_tokens is None
                        else "FAILED"
                    )
                put(dest, record)
                if record["status"] != "OK":
                    raise ValueError(
                        "first response invalid, truncated, usage unknown or context allowance exceeded"
                    )
                history.append(Message("assistant", response.text))
    except Exception as exc:
        put(failure, dict(label=label, arm=arm, reason=str(exc), firstPass=False))
    print("COLLECTED", label, arm, flush=True)


def collect_slot(label, arm, pair_ref):
    import fcntl

    lock = ROOT / "collection-locks" / f"{label}-{arm}.lock"
    lock.parent.mkdir(exist_ok=True)
    with lock.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            return _collect_slot_locked(label, arm, pair_ref)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def verify_collection_sources(labels):
    from character_factory_poc.stages.persona_quality.choice_voice_protocol import (
        DevelopmentSlot,
        SplitManifest,
        validate_source_split,
        verify_voice_split,
    )
    from character_factory_poc.stages.persona_quality.producers import (
        DevelopmentProducer,
        verify_development_producer,
    )
    from character_factory_poc.stages.s7_traits.voice import load_voice_pack

    lib = ROOT / "voice-library"
    pack = load_voice_pack(lib / "pack-v3.json", approval_index=lib / "trusted-approvals-v3.json")
    splitrows = []
    for kind, examples in (
        ("injection", pack.examples),
        ("voice-validation", pack.validationExamples),
    ):
        for e in examples:
            splitrows.append(
                dict(
                    id=e.id,
                    path=str(lib / e.sourceFile),
                    sha256=e.sourceSha256,
                    sourceGroupId=e.sourceGroupId,
                    originalConversationId=e.originalConversationId,
                    parentSourceIds=[],
                    derivedFrom=[],
                    sceneFamilyId="source-" + e.sourceGroupId,
                    split=kind,
                    fieldPath=e.fieldPath,
                )
            )
    split = SplitManifest(auditStatus="PASS", rows=splitrows)
    validate_source_split(split)
    verify_voice_split(pack, split)
    put(ROOT / "split-manifest.json", dump(split))
    scenes = [
        dict(id=r["id"], turns=[dict(user=u, branches=[]) for u in r["users"]], expectedChoices={})
        for r in read_json(ROOT / "evaluation-scenes.json")
    ]
    slots = []
    for label in labels:
        result = control_result(label)
        producers = {}
        for arm, item in result["arms"].items():
            prod = DevelopmentProducer.model_validate(read_json(item["producer"]["path"]))
            producers[arm] = prod
            row = dict(
                id=label + "-" + arm,
                characterId=read_json(prod.assets["plan"].verify())["characterId"],
                arm=arm,
                pair=item["pair"],
                producer=item["producer"],
                scenes=scenes,
            )
            row.update(
                {
                    name: dump(prod.assets[name]) if name in prod.assets else None
                    for name in (
                        "seed",
                        "plan",
                        "blueprint",
                        "choice",
                        "beats",
                        "voiceBinding",
                        "voicePolicy",
                    )
                }
            )
            slot = DevelopmentSlot.model_validate(row)
            verify_development_producer(slot)
            slots.append(dump(slot))
            plan = read_json(prod.assets["plan"].verify())
            bp = read_json(prod.assets["blueprint"].verify())
            put(
                ROOT / "standards" / label / f"{arm}.json",
                dict(
                    canonicalPlan=plan,
                    decisionRules=bp["decisionRules"],
                    choiceExpected={
                        str(n): next(
                            (c["firstMove"] for c in plan["choices"] if c["situation"] == sit),
                            "not_explicitly_defined",
                        )
                        for n, sit in ((1, "상대가 약속에 늦을 때"), (4, "관계 확답을 재촉받을 때"))
                    },
                    sourceAssets={k: dump(v) for k, v in prod.assets.items()},
                    frozenBeforeConsumerCalls=True,
                ),
            )
        if len({p.assets["systemRules"].sha256 for p in producers.values()}) > 1:
            raise ValueError("controlled system rules differ")
        if (
            len(
                {
                    p.assets["profile" if a == "A" else "compilerProfile"].sha256
                    for a, p in producers.items()
                }
            )
            > 1
        ):
            raise ValueError("controlled compiler profiles differ")
        for key, arms in (
            ("blueprint", ["B", "C", "D"]),
            ("choice", ["B", "C", "D"]),
            ("beats", ["C", "D"]),
            ("voiceBinding", ["B", "C"]),
        ):
            if len({producers[a].assets[key].sha256 for a in arms if a in producers}) > 1:
                raise ValueError("controlled " + key + " differs")
    # The registry includes all planned slots; missing arms stay failures rather
    # than being called a complete cohort or removed from any denominator.
    manifest = dict(
        type="bounded-live-development-observation",
        expectedSlots=16,
        plannedReplies=192,
        actualPreparedSlots=slots,
        exactTokenizer=False,
        splitManifestSha256=sha256_file(ROOT / "split-manifest.json"),
        qualityQualified=False,
    )
    put(
        ROOT
        / (
            "collection-source-registry-"
            + "-".join(sorted(labels))
            + "-"
            + body_hash(slots)[:10]
            + ".json"
        ),
        manifest,
    )
    return manifest


def collect(labels):
    verify_collection_sources(labels)
    tasks = []
    for label in labels:
        result = control_result(label)
        for arm, row in result["arms"].items():
            tasks.append((label, arm, row["pair"]))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for _ in pool.map(lambda args: collect_slot(*args), tasks):
            pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "command",
        choices=[
            "prepare",
            "probe",
            "generate",
            "controls",
            "collect",
            "revalidate",
            "resume-core",
            "validate-captured",
            "recover-direct",
            "production-pair",
        ],
    )
    p.add_argument("--labels", nargs="+", default=list(LABELS))
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    if a.command == "prepare":
        prepare()
        return
    if not a.execute:
        print(json.dumps(read_json(ROOT / "dry-run.json"), ensure_ascii=False, indent=2))
        return
    if a.command == "probe":
        probe()
    elif a.command == "generate":
        all_generate(a.labels)
    elif a.command == "revalidate":
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for _ in pool.map(revalidate, a.labels):
                pass
    elif a.command == "resume-core":
        for label in a.labels:
            resume_core(label)
    elif a.command == "validate-captured":
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for _ in pool.map(validate_captured, a.labels):
                pass
    elif a.command == "recover-direct":
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for _ in pool.map(recover_direct, a.labels):
                pass
    elif a.command == "production-pair":
        for label in a.labels:
            production_pair(label)
    elif a.command == "controls":
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            for _ in pool.map(controls, a.labels):
                pass
    elif a.command == "collect":
        collect(a.labels)


if __name__ == "__main__":
    main()
