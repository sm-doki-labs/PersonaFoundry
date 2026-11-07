"""Frozen A/B/C/D first-response collection; never claims qualification."""

import dataclasses
from pathlib import Path
from typing import Literal

from pydantic import Field

from character_factory_poc.common.budget import CallPlan, RunBudget
from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.formation import FormationContract, Nonempty, Sha256
from character_factory_poc.contracts.persona import load_prompt_pair
from character_factory_poc.contracts.voice import VoiceBinding
from character_factory_poc.providers.base import ChatRequest, Message
from character_factory_poc.providers.tracked import TrackedTextModel
from character_factory_poc.stages.persona_quality.choice_voice_protocol import (
    DevelopmentCohortV2,
    next_neutral_user,
    validate_development,
)
from character_factory_poc.stages.s3_plan.choice_design import body_hash
from character_factory_poc.stages.s7_traits.voice import load_voice_pack


def plan_development(cohort):
    responses = sum(len(scene.turns) for s in cohort.slots for scene in s.scenes)
    return dict(
        dryRun=True,
        development=True,
        plannedArtifacts=len(cohort.slots),
        dialogueCalls=responses,
        formationCalls=0,
        judgeCalls=0,
        maxCompletionCalls=responses,
        maxOutputTokens=(cohort.profile.get("modelBinding") or {}).get("maxOutputTokens"),
        billing="explicit conservative price caps required for actual execution",
        note="frozen prepared artifacts; development cannot qualify the recipe",
    )


def shared_budget(ctx, path, *, synthetic):
    cfg = ctx.config.stage("s7")
    return RunBudget(
        path,
        max_calls=min(
            ctx.max_calls or ctx.config.budget.max_calls_per_command,
            ctx.config.budget.max_calls_per_command,
        ),
        max_tokens=int(cfg.get("max_run_tokens", 2_000_000)),
        max_cost_usd=ctx.config.budget.max_cost_usd_per_command,
        input_rate_per_million=cfg.get("input_rate_upper_per_million", 0 if synthetic else None),
        output_rate_per_million=cfg.get("output_rate_upper_per_million", 0 if synthetic else None),
        synthetic=synthetic,
    )


def check_consumer(binding, model, token_counter):
    if token_counter is None:
        raise ValueError("exact tokenizer is required")
    if binding.get("model") != model.model or binding.get("provider") != model.name:
        raise ValueError("consumer model binding mismatch")
    if binding.get("providerPath") != getattr(
        model, "base_url", "fake" if model.name == "fake" else None
    ):
        raise ValueError("consumer endpoint binding mismatch")
    reasoning = getattr(model, "reasoning_effort", None)
    if binding.get("reasoningSettings", {}) != (
        {"reasoning_effort": reasoning} if reasoning is not None else {}
    ):
        raise ValueError("consumer reasoning binding mismatch")
    if not 1 <= binding.get("maxOutputTokens", 0) <= 2400:
        raise ValueError("consumer total output budget must be 1..2400")
    probe = token_counter((Message("user", "토큰 계수 연결 확인"),))
    if type(probe) is not int or probe < 0:
        raise ValueError("exact tokenizer preflight is invalid")


def run_development(ctx, cohort, run_dir, *, dialogue_model, token_counter):
    if not ctx.execute:
        raise ValueError("--execute is required")
    validate_development(cohort)
    binding = cohort.profile.get("modelBinding") or {}
    check_consumer(binding, dialogue_model, token_counter)
    run = Path(run_dir)
    write_once_json(run / "cohort.json", cohort.model_dump(mode="json"))
    digest = body_hash(cohort.model_dump(mode="json"))
    write_once_json(
        run / "registration.json", dict(cohortHash=digest, synthetic=dialogue_model.name == "fake")
    )
    budget = shared_budget(ctx, run / "run-budget.json", synthetic=dialogue_model.name == "fake")
    remaining = sum(
        1
        for s in cohort.slots
        for scene in s.scenes
        for n in range(1, 7)
        if not (run / "dialogues" / s.id / scene.id / f"{n:02}.json").exists()
        and not (run / "failures" / f"{s.id}.json").exists()
    )
    budget.check_plan([CallPlan("development", "first replies only", remaining)])
    model = TrackedTextModel(dialogue_model, Ledger(run / "ledger"), budget)
    for slot in cohort.slots:
        failure = run / "failures" / f"{slot.id}.json"
        if failure.exists():
            continue
        try:
            pair = load_prompt_pair(slot.pair.verify())
            if pair.characterId != slot.characterId:
                raise ValueError("frozen pair identity mismatch")
            for scene in slot.scenes:
                history = [Message("system", pair.long.text)]
                for n, turn in enumerate(scene.turns, 1):
                    user = next_neutral_user(turn)
                    history.append(Message("user", user))
                    req_hash = body_hash([dataclasses.asdict(m) for m in history])
                    dest = run / "dialogues" / slot.id / scene.id / f"{n:02}.json"
                    if dest.exists():
                        old = read_json(dest)
                        if (
                            old.get("requestSha256") != req_hash
                            or old.get("cohortHash") != digest
                            or old.get("status") != "OK"
                            or old.get("responseSha256") != sha256_text(old.get("assistant", ""))
                        ):
                            raise ValueError("development checkpoint mismatch")
                        history.append(Message("assistant", old["assistant"]))
                        continue
                    attempt = dest.with_suffix(".attempt.json")
                    if attempt.exists():
                        raise ValueError("unknown first request outcome; redraw forbidden")
                    count = token_counter(tuple(history))
                    if (
                        type(count) is not int
                        or count < 0
                        or count + binding["maxOutputTokens"]
                        > min(24000, binding.get("contextLimit", 24000))
                    ):
                        raise ValueError("development input/context cap exceeded")
                    request = ChatRequest(
                        "DIALOGUE",
                        "persona-development",
                        tuple(history),
                        f"{slot.id}/{scene.id}/{n}",
                        max_output_tokens=binding["maxOutputTokens"],
                        temperature=binding.get("temperature", 0.7),
                    )
                    write_once_json(
                        attempt,
                        dict(
                            request=dataclasses.asdict(request),
                            inputTokens=count,
                            requestSha256=req_hash,
                        ),
                    )
                    response = model.complete(request)
                    ok = (
                        bool(response.text.strip())
                        and response.finish_reason != "length"
                        and (
                            response.output_tokens is None
                            or response.output_tokens < binding["maxOutputTokens"]
                        )
                    )
                    write_once_json(
                        dest,
                        dict(
                            status="OK" if ok else "FAILED",
                            user=user,
                            assistant=response.text,
                            cohortHash=digest,
                            requestSha256=req_hash,
                            responseSha256=sha256_text(response.text),
                            systemSha256=pair.long.sha256,
                            response=dataclasses.asdict(response),
                            turn=n,
                        ),
                    )
                    if not ok:
                        raise ValueError("empty/truncated first response")
                    history.append(Message("assistant", response.text))
        except Exception as exc:
            write_once_json(failure, dict(error=str(exc), slotId=slot.id, firstPassFailed=True))
    export_development_packet(run)
    return run


def export_development_packet(run):
    run = Path(run)
    cohort = DevelopmentCohortV2.model_validate(read_json(run / "cohort.json"))
    mapping = {}
    packet = []
    reference_by_character = {}
    for slot in cohort.slots:
        if slot.arm in {"D", "CURRENT", "COVERED"} and slot.voiceBinding:
            voice = VoiceBinding.model_validate(read_json(slot.voiceBinding.verify()))
            pack = load_voice_pack(
                Path(voice.packPath), approval_index=Path(voice.approvalIndexPath)
            )
            reference_by_character[slot.characterId] = [
                dict(text=e.styleView, sourceGroupId=e.sourceGroupId)
                for e in pack.validationExamples
            ]
    ordered = sorted(cohort.slots, key=lambda s: sha256_text(cohort.id + s.id))
    for i, slot in enumerate(ordered, 1):
        blind = f"P{i:03}"
        mapping[blind] = slot.id
        plan = read_json(slot.plan.verify())
        blueprint = read_json(slot.blueprint.verify())
        standard = {
            k: v
            for k, v in plan.items()
            if k
            not in {
                "schemaVersion",
                "characterId",
                "planRev",
                "seedRev",
                "variantId",
                "appearanceRev",
                "evidence",
                "notes",
            }
        }
        rules = [
            {k: v for k, v in r.items() if k != "choiceRuleId"}
            for r in blueprint.get("decisionRules", [])
        ]
        refs = reference_by_character.get(slot.characterId, [])
        for scene in slot.scenes:
            turns = []
            for n, turn in enumerate(scene.turns, 1):
                p = run / "dialogues" / slot.id / scene.id / f"{n:02}.json"
                row = (
                    read_json(p)
                    if p.exists()
                    else dict(user=turn.user, assistant=None, status="MISSING")
                )
                turns.append(
                    dict(
                        turn=n,
                        user=row["user"],
                        assistant=row.get("assistant"),
                        status=row["status"],
                    )
                )
            packet.append(
                dict(
                    id=f"{blind}/{scene.id}",
                    canonicalPlan=standard,
                    decisionRules=rules,
                    voiceReference=refs,
                    expectedChoices=scene.expectedChoices,
                    turns=turns,
                )
            )
    write_once_json(run / "blind-mapping.json", mapping)
    write_once_json(run / "review-packet.json", packet)
    write_once_json(
        run / "human-reviews-template.json",
        dict(
            cohortHash=body_hash(cohort.model_dump(mode="json")),
            scenes=[
                dict(
                    id=p["id"],
                    reviewer="",
                    sawLLMCandidatesFirst=False,
                    naturalness=None,
                    voiceFit=None,
                    choiceFaithful=None,
                    evidence=[],
                )
                for p in packet
            ],
        ),
    )
    return run / "review-packet.json"


def report_development(run, human_reviews=None):
    run = Path(run)
    cohort = DevelopmentCohortV2.model_validate(read_json(run / "cohort.json"))
    result = dict(
        status="METRICS_ONLY",
        qualityQualified=False,
        development=True,
        plannedArtifacts=len(cohort.slots),
        plannedReplies=sum(len(sc.turns) for s in cohort.slots for sc in s.scenes),
        completedArtifacts=0,
        completedReplies=0,
        failedSlots=[],
        humanReviewComplete=False,
        reasons=["development comparison is not independent qualification"],
    )
    try:
        validate_development(cohort)
    except ValueError as exc:
        result["reasons"].append(str(exc))
    digest = body_hash(cohort.model_dump(mode="json"))
    for slot in cohort.slots:
        complete = not (run / "failures" / f"{slot.id}.json").exists()
        pair = load_prompt_pair(slot.pair.verify())
        for scene in slot.scenes:
            history = [dict(role="system", content=pair.long.text)]
            for n, turn in enumerate(scene.turns, 1):
                path = run / "dialogues" / slot.id / scene.id / f"{n:02}.json"
                if not path.exists():
                    complete = False
                    continue
                row = read_json(path)
                history.append(dict(role="user", content=turn.user))
                valid = (
                    row.get("status") == "OK"
                    and row.get("cohortHash") == digest
                    and row.get("requestSha256") == body_hash(history)
                    and row.get("responseSha256") == sha256_text(row.get("assistant", ""))
                    and row.get("user") == turn.user
                    and row.get("systemSha256") == pair.long.sha256
                )
                if valid:
                    result["completedReplies"] += 1
                else:
                    complete = False
                history.append(dict(role="assistant", content=row.get("assistant", "")))
        if complete:
            result["completedArtifacts"] += 1
        else:
            result["failedSlots"].append(slot.id)
    if human_reviews is not None:
        try:
            reviews = DevelopmentHumanReviews.model_validate(read_json(Path(human_reviews)))
            packet = {p["id"]: p for p in read_json(run / "review-packet.json")}
            if (
                reviews.cohortHash != digest
                or {r.id for r in reviews.scenes} != packet.keys()
                or len(reviews.scenes) != len(packet)
            ):
                raise ValueError("development human review identity/coverage mismatch")
            for review in reviews.scenes:
                text = "\n".join(t["assistant"] or "" for t in packet[review.id]["turns"])
                if any(q not in text for q in review.evidence):
                    raise ValueError("development human review quote mismatch")
            result["humanReviewComplete"] = True
            result["humanSceneRatings"] = [r.model_dump() for r in reviews.scenes]
        except (ValueError, OSError) as exc:
            result["reasons"].append(str(exc))
    return result


class DevelopmentSceneReview(FormationContract):
    id: Nonempty
    reviewer: Nonempty
    sawLLMCandidatesFirst: Literal[False]
    naturalness: int = Field(ge=0, le=2)
    voiceFit: int = Field(ge=0, le=2)
    choiceFaithful: bool
    evidence: list[Nonempty] = Field(min_length=1)


class DevelopmentHumanReviews(FormationContract):
    cohortHash: Sha256
    scenes: list[DevelopmentSceneReview] = Field(min_length=1)


def qualification_standard(run, slot):
    artifact = Path(run) / "artifacts" / f"{slot.id}.json"
    if not artifact.exists():
        return dict(standardUnavailable="formation did not complete")
    pair = Path(read_json(artifact)["path"])
    bundle = read_json(pair.parent / "persona-bundle.json")
    if bundle.get("schemaVersion") != "persona-bundle-v2":
        return dict(standardUnavailable="choice-voice bundle missing")
    root = Path(slot.root) / "runs/characters" / slot.characterId

    def source(name):
        ref = bundle["sourceAssets"][name]
        path = Path(ref["path"]) if Path(ref["path"]).is_absolute() else root / ref["path"]
        if sha256_file(path) != ref["sha256"]:
            raise ValueError("qualification standard source hash mismatch")
        return read_json(path)

    plan = source("plan")
    bp = source("blueprint")
    voice = VoiceBinding.model_validate(source("voiceBinding"))
    pack = load_voice_pack(Path(voice.packPath), approval_index=Path(voice.approvalIndexPath))
    return dict(
        canonicalPlan={
            k: v
            for k, v in plan.items()
            if k
            not in {
                "schemaVersion",
                "characterId",
                "planRev",
                "seedRev",
                "variantId",
                "appearanceRev",
                "evidence",
                "notes",
            }
        },
        decisionRules=[
            {k: v for k, v in r.items() if k != "choiceRuleId"} for r in bp["decisionRules"]
        ],
        voiceReference=[
            dict(text=e.styleView, sourceGroupId=e.sourceGroupId) for e in pack.validationExamples
        ],
    )
