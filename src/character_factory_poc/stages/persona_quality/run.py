"""정규 API로 첫 응답을 수집한다. 토큰 계수기는 호출 전에 명시적으로 결합한다."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.persona import load_prompt_pair
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message, TextModel
from character_factory_poc.stages.persona_quality.protocol import Cohort, canonical_hash, next_user


def plan_qualification(cohort: Cohort) -> dict:
    if getattr(cohort, "schemaVersion", None) == "persona-development-cohort-v2":
        from character_factory_poc.stages.persona_quality.development import plan_development

        return plan_development(cohort)
    n = len(cohort.slots)
    if cohort.profile.get("profileId") == "ko-text-choice-voice-long-v2":
        normal = n * 7 if cohort.formation else 0
        maximum = n * 21 if cohort.formation else 0
        return dict(
            dryRun=True,
            plannedArtifacts=n,
            formationCalls=normal,
            maxFormationCalls=maximum,
            dialogueCalls=n * 60,
            judgeCalls=n * 9,
            maxJudgeCalls=n * 18,
            nominalCompletionCalls=normal + n * 69,
            maxCompletionCalls=maximum + n * 78,
            maxOutputTokens=(cohort.profile.get("modelBinding") or {}).get("maxOutputTokens"),
            tokenCounterCallsAdditional=n * 60 + 1,
            billing="explicit upper prices and shared persistent caps required",
            tokenization="exact bound tokenizer required",
            scope="new recipe qualification; legacy comparison uses prepared development artifacts",
        )
    return dict(
        dryRun=True,
        plannedArtifacts=n,
        formationCalls=n * 3 if cohort.formation else 0,
        dialogueCalls=n * 60,
        judgeCalls=n * 9,
        nominalCompletionCalls=n * (72 if cohort.formation else 69),
        maxCompletionCalls=n * (87 if cohort.formation else 78),
        maxFormationCalls=n * 9 if cohort.formation else 0,
        maxJudgeCalls=n * 18,
        maxOutputTokens=(cohort.profile.get("modelBinding") or {}).get("maxOutputTokens"),
        tokenCounterCallsAdditional=n * 60 + 1,
        billing="UNKNOWN until provider rates are verified",
        tokenization="exact bound tokenizer required before each request",
    )


def form_slot(slot, cohort: Cohort, *, shared_run_budget=None) -> Path:
    """이미 준비된 씨앗/S2에서 새로 형성한다. legacy는 frozen 소스로 별도 형성 후 평가한다."""
    from character_factory_poc.pipeline.approve import approve_gate
    from character_factory_poc.stages.s3_plan.variants import run_s3_variants
    from character_factory_poc.stages.s7_traits.sheet import run_s7
    from character_factory_poc.stages.s8_prompts.build import run_s8

    ctx = Context.load(Path(slot.root), execute=True)
    if shared_run_budget is not None:
        ctx._run_budget = shared_run_budget
    choice_voice = cohort.profile.get("profileId") == "ko-text-choice-voice-long-v2"
    if choice_voice and slot.recipe == "old":
        raise ValueError(
            "legacy subprocess cannot use the shared v2 envelope; use frozen development comparison"
        )
    if ctx.config.agent.get("backend") == "codex_exec":
        raise ValueError("qualification requires bounded API generation, not nested agent retries")
    if not choice_voice and int(ctx.config.stage("s3").get("max_check_retries", 3)) != 0:
        raise ValueError("S3 semantic retries must be disabled for first-pass qualification")
    from character_factory_poc.providers.factory import make_text_model

    generation_model = make_text_model(ctx.config.provider("text"))
    if hasattr(generation_model, "max_retries"):
        generation_model.max_retries = 0
    ctx._text = generation_model
    if slot.recipe == "old":
        if any(
            int(ctx.config.stage(stage).get("max_check_retries", 3)) != 0 for stage in ("s7", "s8")
        ):
            raise ValueError("old semantic retries must be disabled for first-pass qualification")
        from character_factory_poc.stages.persona_quality.protocol import recipe_hash

        if not cohort.baselineSource or not cohort.baselineSourceSha256:
            raise ValueError("old recipe needs frozen source and hash")
        source = Path(cohort.baselineSource).resolve()
        if recipe_hash(source) != cohort.baselineSourceSha256:
            raise ValueError("frozen old source changed")

        program = """
import json,sys
sys.path.insert(0,sys.argv[1])
import character_factory_poc.contracts
from pathlib import Path
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.stages.s3_plan.variants import run_s3_variants
from character_factory_poc.stages.s7_traits.sheet import run_s7
from character_factory_poc.stages.s8_prompts.build import run_s8
c=Context.load(Path(sys.argv[2]),execute=True);cid=sys.argv[3]
from character_factory_poc.providers.factory import make_text_model
m=make_text_model(c.config.provider('text'))
if hasattr(m,'max_retries'):m.max_retries=0
c.use_models(m)
if c.state(cid).stage('s3').currentRev:raise ValueError('old slot already attempted')
run_s3_variants(c,cid)
approve_gate(c,cid,'G3',dict(decision='SELECT',selections=['v1'],reviewer='fixed-v1'))
run_s7(c,cid)
print(json.dumps(dict(path=str(run_s8(c,cid,[])/'prompt-pair.json'))))
"""
        result = subprocess.run(
            [sys.executable, "-c", program, str(source), slot.root, slot.characterId],
            capture_output=True,
            text=True,
            timeout=1800,
            env=dict(os.environ),
        )
        if result.returncode:
            raise ValueError("frozen old formation failed: " + result.stderr[-2000:])
        return Path(json.loads(result.stdout.splitlines()[-1])["path"])
    expected_profile = "ko-text-choice-voice-long-v2" if choice_voice else "ko-text-prompt-long-v1"
    if ctx.config.stage("s7").get("formation_profile") != expected_profile:
        raise ValueError("slot config does not bind new formation profile")
    if choice_voice:
        profile_path = (
            ctx.config.runs_dir / "quality-profiles" / f"{canonical_hash(cohort.profile)}.json"
        )
        write_once_json(profile_path, cohort.profile)
        ctx.config.stages["s7"]["quality_profile"] = str(profile_path)
    state = ctx.state(slot.characterId)
    if state.stage("s3").currentRev or state.stage("s7").currentRev:
        raise ValueError("first-pass slot already contains generated artifacts")
    run_s3_variants(ctx, slot.characterId)
    selected = "v1"
    if choice_voice:
        from character_factory_poc.stages.s3_plan.choice_design import select_by_content

        rev = ctx.state(slot.characterId).stage("s3").currentRev
        candidates = read_json(
            ctx.character_dir(slot.characterId) / "s3-plan" / rev / "variants.json"
        )["candidates"]
        selected = select_by_content(candidates)["variantId"]
    approve_gate(
        ctx,
        slot.characterId,
        "G3",
        dict(
            decision="SELECT",
            selections=[selected],
            reviewer="qualification-fixed-selection",
            reasons="preregistered content-only selection; no edits"
            if choice_voice
            else "preregistered v1; no edits",
        ),
    )
    run_s7(ctx, slot.characterId)
    return run_s8(ctx, slot.characterId, []) / "prompt-pair.json"


def run_qualification(
    ctx: Context,
    cohort: Cohort,
    run_dir: Path,
    *,
    dialogue_model: TextModel,
    token_counter: Callable[[tuple[Message, ...]], int] | None,
    formation_runner: Callable | None = None,
) -> Path:
    """형식 외 재시도·응답 재추출 없이 모든 실패를 슬롯 원장에 남긴다."""
    if getattr(cohort, "schemaVersion", None) == "persona-development-cohort-v2":
        from character_factory_poc.stages.persona_quality.development import run_development

        return run_development(
            ctx, cohort, run_dir, dialogue_model=dialogue_model, token_counter=token_counter
        )
    if not ctx.execute:
        raise ValueError("--execute is required")
    choice_voice = cohort.profile.get("profileId") == "ko-text-choice-voice-long-v2"
    if choice_voice:
        from character_factory_poc.stages.persona_quality.choice_voice_protocol import (
            validate_frozen_split,
        )

        manifest = validate_frozen_split(cohort)
        if any(slot.recipe == "old" for slot in cohort.slots):
            raise ValueError(
                "v2 qualification uses new slots; "
                "compare legacy with the frozen development protocol"
            )
    binding = cohort.profile.get("modelBinding") or {}
    if not binding or binding.get("model") != dialogue_model.model:
        raise ValueError("dialogue model binding mismatch")
    actual_reasoning = getattr(dialogue_model, "reasoning_effort", None)
    effective_binding = dict(
        provider=dialogue_model.name,
        providerPath=getattr(
            dialogue_model, "base_url", "fake" if dialogue_model.name == "fake" else None
        ),
        model=dialogue_model.model,
        reasoningSettings=(
            {"reasoning_effort": actual_reasoning} if actual_reasoning is not None else {}
        ),
    )
    for field, actual in effective_binding.items():
        if binding.get(field) != actual:
            raise ValueError(f"dialogue provider/settings binding mismatch: {field}")
    if token_counter is None:
        raise ValueError("exact model tokenizer must be bound; estimates are not measurements")
    if not (1 <= binding.get("maxOutputTokens", 0) <= 2400):
        raise ValueError("dialogue maxOutputTokens must be1..2400")
    probe_count = token_counter((Message("user", "토큰 계수 연결 확인"),))
    if type(probe_count) is not int or probe_count < 0:
        raise ValueError("exact tokenizer preflight returned an invalid count")
    from character_factory_poc.stages.persona_quality.protocol import recipe_hash

    observed_recipe = recipe_hash(Path(__file__).parents[3])
    if dialogue_model.name != "fake" and observed_recipe != cohort.recipeHash:
        raise ValueError("running recipe differs from the frozen cohort hash")
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    write_once_json(run_dir / "cohort.json", cohort.model_dump(mode="json"))
    cohort_hash = canonical_hash(cohort)
    registration = run_dir / "registration.json"
    if not registration.exists():
        write_once_json(
            registration,
            dict(
                startedAt=time.time(),
                cohortHash=cohort_hash,
                slotIds=[s.id for s in cohort.slots],
                synthetic=dialogue_model.name == "fake",
                effectiveBinding=effective_binding,
                observedRecipeHash=observed_recipe,
            ),
        )
    started = read_json(registration)["startedAt"]
    if choice_voice:
        from character_factory_poc.stages.persona_quality.development import shared_budget

        budget = shared_budget(
            ctx,
            run_dir / "run-budget.json",
            synthetic=dialogue_model.name == "fake"
            and all(ctx.config.provider(k).adapter == "fake" for k in ("text", "judge")),
        )
        ctx._run_budget = budget
        tracked_dialogue = __import__(
            "character_factory_poc.providers.tracked", fromlist=["TrackedTextModel"]
        ).TrackedTextModel
        dialogue_model = tracked_dialogue(dialogue_model, ctx.ledger("persona-quality"), budget)
    else:
        budget = ctx.budget()
    # Generation budgets are checked by each stage as well. Dialogue is a separate bounded command.
    from character_factory_poc.common.budget import CallPlan

    planned_calls = len(cohort.slots) * ((81 if choice_voice else 69) if cohort.formation else 60)
    if choice_voice:
        planned_calls = 0
        for slot in cohort.slots:
            if (run_dir / "failures" / f"{slot.id}.json").exists():
                continue
            artifact = run_dir / "artifacts" / f"{slot.id}.json"
            if cohort.formation and not artifact.exists():
                if not (run_dir / "formation-attempts" / f"{slot.id}.json").exists():
                    planned_calls += 21
                else:
                    continue
            planned_calls += sum(
                not (run_dir / "dialogues" / slot.id / scene.id / f"{n:02}.json").exists()
                for scene in slot.scenes
                for n in range(1, len(scene.turns) + 1)
            )
    budget.check_plan(
        [
            CallPlan(
                "quality-run",
                "formation and first replies",
                planned_calls,
                None,
            )
        ]
    )
    for slot in cohort.slots:
        failure = run_dir / "failures" / f"{slot.id}.json"
        if failure.exists():
            continue  # recovery never silently changes the first-pass result
        try:
            artifact = run_dir / "artifacts" / f"{slot.id}.json"
            if artifact.exists():
                frozen = read_json(artifact)
                pair_path = Path(frozen["path"])
                if sha256_file(pair_path) != frozen["sha256"]:
                    raise ValueError("frozen prompt changed")
            else:
                if cohort.formation:
                    if choice_voice:
                        attempt = run_dir / "formation-attempts" / f"{slot.id}.json"
                        if attempt.exists():
                            raise ValueError(
                                "prior formation outcome unknown; first-pass redraw forbidden"
                            )
                        write_once_json(attempt, dict(slotId=slot.id, cohortHash=cohort_hash))
                        if formation_runner is not None:
                            if dialogue_model.name != "fake":
                                raise ValueError(
                                    "external formation callback bypasses the shared envelope"
                                )
                            pair_path = formation_runner(slot, cohort)
                        else:
                            pair_path = form_slot(slot, cohort, shared_run_budget=budget)
                    else:
                        budget.consume(9)
                        pair_path = (formation_runner or form_slot)(slot, cohort)
                else:
                    state = Context.load(Path(slot.root), execute=False).state(slot.characterId)
                    rev = state.stage("s8").currentRev
                    pair_path = (
                        Path(slot.root)
                        / "runs/characters"
                        / slot.characterId
                        / "s8-prompts"
                        / str(rev)
                        / "prompt-pair.json"
                    )
                pair_path = Path(pair_path).resolve()
                write_once_json(artifact, dict(path=str(pair_path), sha256=sha256_file(pair_path)))
            pair = load_prompt_pair(pair_path)
            if choice_voice:
                from character_factory_poc.contracts.voice import VoiceBinding
                from character_factory_poc.stages.persona_quality.choice_voice_protocol import (
                    verify_voice_split,
                )
                from character_factory_poc.stages.s7_traits.voice import load_voice_pack
                from character_factory_poc.stages.s8_prompts.formation import verify_bundle

                slot_ctx = Context.load(Path(slot.root), execute=False)
                bound, _, trait_path = verify_bundle(slot_ctx, slot.characterId, pair_path.parent)
                voice = VoiceBinding.model_validate(
                    read_json(trait_path.parent / "voice-binding.json")
                )
                pack = load_voice_pack(
                    Path(voice.packPath), approval_index=Path(voice.approvalIndexPath)
                )
                verify_voice_split(pack, manifest)
            if slot.recipe == "new" and dialogue_model.name != "fake":
                from character_factory_poc.contracts.formation import QualityProfile
                from character_factory_poc.stages.s8_prompts.formation import verify_bundle

                slot_ctx = Context.load(Path(slot.root), execute=False)
                bundle, _, _ = verify_bundle(slot_ctx, slot.characterId, pair_path.parent)
                expected_profile = QualityProfile.model_validate(cohort.profile).model_dump(
                    mode="json"
                )
                encoded_profile = (
                    json.dumps(expected_profile, ensure_ascii=False, sort_keys=True, indent=2)
                    + "\n"
                )
                if bundle.profileSha256 != sha256_text(encoded_profile):
                    raise ValueError("formed bundle differs from the frozen consumer profile")
            for scene in slot.scenes:
                history = [Message("system", pair.long.text)]
                for n, turn in enumerate(scene.turns, 1):
                    dest = run_dir / "dialogues" / slot.id / scene.id / f"{n:02}.json"
                    user = next_user(
                        turn, history[-1].content if history[-1].role == "assistant" else ""
                    )
                    history.append(Message("user", user))
                    request_hash = canonical_hash([dataclasses.asdict(m) for m in history])
                    if dest.exists():
                        old = read_json(dest)
                        if (
                            old.get("requestSha256") != request_hash
                            or old.get("cohortHash") != cohort_hash
                            or old["status"] != "OK"
                            or old.get("responseSha256") != sha256_text(old.get("assistant", ""))
                            or old.get("systemSha256") != pair.long.sha256
                            or old.get("user") != user
                        ):
                            raise ValueError("checkpoint mismatch/failed first reply")
                        history.append(Message("assistant", old["assistant"]))
                        continue
                    attempt = dest.with_suffix(".attempt.json")
                    if attempt.exists():
                        raise ValueError("prior request outcome unknown; redraw forbidden")
                    if time.time() - started > 48 * 3600:
                        raise ValueError("elapsed48h cap reached")
                    count = token_counter(tuple(history))
                    context_limit = min(24000, binding.get("contextLimit", 24000))
                    if type(count) is not int or count + binding["maxOutputTokens"] > context_limit:
                        raise ValueError("input/context token limit exceeded")
                    if not choice_voice:
                        budget.consume()
                    req = ChatRequest(
                        "DIALOGUE",
                        "persona-quality",
                        tuple(history),
                        f"{slot.id}/{scene.id}/{n}",
                        max_output_tokens=binding["maxOutputTokens"],
                        temperature=binding.get("temperature", 0.7),
                        metadata={"modelBinding": effective_binding},
                    )
                    write_once_json(
                        attempt,
                        dict(
                            request=dataclasses.asdict(req),
                            requestSha256=request_hash,
                            inputTokens=count,
                        ),
                    )
                    resp = dialogue_model.complete(req)
                    status = "OK"
                    if (
                        not resp.text.strip()
                        or getattr(resp, "finish_reason", None) == "length"
                        or (
                            resp.output_tokens is not None
                            and resp.output_tokens >= binding["maxOutputTokens"]
                        )
                    ):
                        status = "FAILED"
                    write_once_json(
                        dest,
                        dict(
                            status=status,
                            user=user,
                            assistant=resp.text,
                            cohortHash=cohort_hash,
                            systemSha256=pair.long.sha256,
                            requestSha256=request_hash,
                            responseSha256=sha256_text(resp.text),
                            response=dataclasses.asdict(resp),
                            turn=n,
                        ),
                    )
                    if status != "OK":
                        raise ValueError("empty/truncated first response")
                    history.append(Message("assistant", resp.text))
        except Exception as exc:
            write_once_json(
                failure,
                dict(
                    slot=slot.id,
                    error=type(exc).__name__,
                    reason=str(exc),
                    firstPass=False,
                    cohortHash=cohort_hash,
                ),
            )
    return run_dir
