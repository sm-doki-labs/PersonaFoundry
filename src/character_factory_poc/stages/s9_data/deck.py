"""Opt-in S9 deck: grounded exhaustive review and one bounded Gemini correction.

Public Conversation stays unchanged; request audits and immutable batch receipts
carry role/route/profile provenance. A failed or interrupted batch needs an
explicit new revision, never an automatic redraw on resume.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

from pydantic import ConfigDict, Field

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.dataset import BehaviorRow, Conversation
from character_factory_poc.pipeline.agent import AGENT_MAX_OUTPUT_TOKENS, load_role_prompt
from character_factory_poc.providers.base import ChatRequest, Message

TASKS = ("scenarios", "sft_answers", "screening", "adjudication", "repair")
FORMAT_RETRIES = 2
# Writer + Terra + Sol, then repair + Terra + Sol. Sol confirms all Terra
# concerns; this is not a claim about calibrated pass/fail sampling rates.
BATCH_CALL_BOUND = 6 * (1 + FORMAT_RETRIES)


def enabled(ctx) -> bool:
    return bool(getattr(ctx.config, "text_pipeline", {}).get("enabled", False))


def writer_model(ctx) -> str:
    cfg = ctx.config.task_provider("sft_answers") if enabled(ctx) else ctx.config.provider("text")
    return cfg.model or cfg.adapter


def snapshot(ctx) -> dict[str, Any]:
    return {
        "bindings": {task: ctx.config.text_binding(task) for task in TASKS},
        "formatRetries": FORMAT_RETRIES,
        "semanticCorrectionRounds": 1,
    }


def pin(ctx, rev_dir: Path, *, create: bool = False) -> None:
    """Reject route/profile switches and legacy-to-deck resumes before any calls."""
    path = rev_dir / "model-deck.json"
    if not enabled(ctx):
        if path.exists():
            raise CheckFailed("s9", ["model deck disabled for a pinned deck revision"])
        return
    expected = snapshot(ctx)
    if not path.exists():
        if not create:
            raise CheckFailed("s9", ["revision has no model deck snapshot; use a new revision"])
        write_once_json(path, expected)
    elif read_json(path) != expected:
        raise CheckFailed("s9", ["model deck binding changed; use a new revision"])


def batch_plan(stage: str, batches: int) -> list[CallPlan]:
    return [
        CallPlan(
            stage,
            "모델 덱: 배치마다 작성·전수검사·이견검토, 수정 한 번과 재검사 "
            "(각 요청 형식 재시도 최대 2회 포함)",
            batches * BATCH_CALL_BOUND,
            est_cost_usd=None,
        )
    ]


class DeckOutput(Strict):
    model_config = ConfigDict(extra="forbid", strict=True)


class ScenarioOutput(DeckOutput):
    # These are factual scene/user-action descriptions, never assistant speech.
    behaviorTable: list[BehaviorRow] = Field(min_length=3, max_length=8)
    forbidden: list[str]
    notes: str


class SemanticError(DeckOutput):
    kind: Literal["canon", "speaker", "context"]
    messageIndex: int = Field(ge=0)
    quote: str = Field(min_length=1)
    evidenceSource: Literal["system", "message"]
    evidenceMessageIndex: int | None
    evidenceQuote: str = Field(min_length=1)
    explanation: str = Field(min_length=1)


class ConversationReview(DeckOutput):
    conversationId: str
    verdict: Literal["PASS", "ERROR"]
    errors: list[SemanticError]


class ReviewOutput(DeckOutput):
    reviews: list[ConversationReview]


def request(
    ctx, cid, *, budget, stage, rev_dir, task, role, contract, inputs, validate_output=None
):
    """One logical request, at most two format retries, no provider/path fallback.

    The task model is already tracked. This layer records the actual response
    model and full request/response for *each* attempt, including invalid JSON.
    Provider exceptions propagate immediately and get an audit record too.
    """
    binding = ctx.config.text_binding(task)
    model = ctx.task_model(cid, budget, task)
    history = [
        Message("system", load_role_prompt(role)),
        Message(
            "user",
            json.dumps(
                {"inputs": inputs, "outputSchema": contract.model_json_schema()}, ensure_ascii=False
            ),
        ),
    ]
    for attempt in range(1, FORMAT_RETRIES + 2):
        ref = f"requests/data-deck-{task}-{uuid.uuid4().hex}.json"
        req = ChatRequest(
            kind="JUDGE" if task in {"screening", "adjudication"} else "AGENT",
            stage=stage,
            messages=tuple(history),
            ref=f"{cid}/{rev_dir.name}/{ref}",
            max_output_tokens=AGENT_MAX_OUTPUT_TOKENS,
            temperature=0.0 if task in {"screening", "adjudication"} else 0.7,
            response_json=True,
            metadata={"textBinding": binding},
        )
        audit = {
            "binding": binding,
            "stage": stage,
            "ref": req.ref,
            "attempt": attempt,
            "requestedModel": model.model,
            "messages": [{"role": m.role, "content": m.content} for m in history],
        }
        try:
            response = model.complete(req)
        except Exception as exc:
            write_once_json(
                rev_dir / ref, {**audit, "ok": False, "failureType": type(exc).__name__}
            )
            raise
        audit.update(
            responseModel=response.model, responseProvider=response.provider, response=response.text
        )
        try:
            output = contract.model_validate_json(response.text, strict=True)
            if validate_output:
                problems = validate_output(output)
                if problems:
                    raise ValueError("; ".join(problems))
        except ValueError as exc:
            write_once_json(rev_dir / ref, {**audit, "ok": False, "problem": str(exc)})
            if attempt > FORMAT_RETRIES:
                raise CheckFailed(stage, [f"{task}: invalid structured response: {exc}"]) from exc
            history.extend(
                [
                    Message("assistant", response.text),
                    Message(
                        "user",
                        f"Correct only the output format/coverage/citations: {exc}. "
                        "Return the complete strict JSON object.",
                    ),
                ]
            )
            continue
        write_once_json(rev_dir / ref, {**audit, "ok": True})
        return output, ref, response.model
    raise AssertionError("unreachable")


def _review_problems(out: ReviewOutput, conversations: list[Conversation]) -> list[str]:
    by_id = {c.conversationId: c for c in conversations}
    got = [r.conversationId for r in out.reviews]
    problems = []
    if len(got) != len(by_id) or set(got) != set(by_id):
        return ["reviews must cover every conversationId exactly once"]
    for review in out.reviews:
        conv = by_id[review.conversationId]
        if (review.verdict == "ERROR") != bool(review.errors):
            problems.append("ERROR requires cited errors; PASS requires an empty errors list")
        for error in review.errors:
            idx = error.messageIndex
            if (
                idx >= len(conv.messages)
                or conv.messages[idx].role != "assistant"
                or error.quote.strip() == ""
                or error.quote not in conv.messages[idx].content
            ):
                problems.append("error quote must cite an existing assistant message (zero based)")
            if error.evidenceSource == "system":
                evidence = conv.system if error.evidenceMessageIndex is None else ""
            else:
                j = error.evidenceMessageIndex
                evidence = conv.messages[j].content if j is not None and 0 <= j < idx else ""
            if not error.evidenceQuote.strip() or error.evidenceQuote not in evidence:
                problems.append("error evidence must quote system or an earlier context message")
            if not error.explanation.strip():
                problems.append("error explanation must be nonempty")
    return problems


def _review(session, budget, conversations, round_no):
    inputs = {
        "conversations": [dump(c) for c in conversations],
        "round": round_no,
        "scope": "Explicit canon, speaker ownership and context errors only. "
        "Preserve jealousy, defensive apologies and abrasiveness.",
    }
    kwargs = dict(
        ctx=session.ctx,
        cid=session.cid,
        budget=budget,
        stage=session.stage,
        rev_dir=_rev_dir(session),
        contract=ReviewOutput,
        validate_output=lambda out: _review_problems(out, conversations),
    )
    terra, _, _ = request(**kwargs, task="screening", role="data_deck_screening", inputs=inputs)
    if not any(r.errors for r in terra.reviews):
        return terra
    # Systematically confirm concerns, including disagreement dismissal, before
    # Gemini sees a repair instruction. No automatic human approval is implied.
    sol, _, _ = request(
        **kwargs,
        task="adjudication",
        role="data_deck_adjudication",
        inputs={**inputs, "screening": dump(terra)},
    )
    return sol


def _rev_dir(session):
    from character_factory_poc.stages.s9_data.plan import data_dir

    return data_dir(session.ctx, session.cid) / session.rev


def _write_and_review(session, slots, ids, notes, budget):
    from character_factory_poc.stages.s9_data import checks, samples

    args = dict(
        ctx=session.ctx,
        cid=session.cid,
        budget=budget,
        stage=session.stage,
        rev_dir=_rev_dir(session),
        contract=samples.WriterOutput,
    )
    specs = samples._specs(session, slots)
    attempt_notes = list(notes)
    # D-0138: mechanical check failures get max_retries rewrites with the problems as
    # review notes (the legacy writer path also rewrites); then the batch fails.
    for attempt in range(1 + max(0, session.cfg.max_retries)):
        inputs = samples.batch_inputs(session, slots, ids, attempt_notes)
        output, ref, actual = request(
            **args, task="sft_answers", role="data_deck_writer", inputs=inputs
        )
        written = [dump(c) for c in output.conversations]
        problems = checks.batch_problems(written, specs, session.system)
        if not problems:
            conversations = samples.assemble(
                replace(session, writer_model=actual), slots, ids, written, ref
            )
            # Check assembled scene+system length as well as the pre-assembly checks.
            problems = [
                f"{i + 1}번째: {p}"
                for i, (c, spec) in enumerate(zip(conversations, specs, strict=True))
                for p in checks.conversation_problems(c, spec)
            ]
        if not problems:
            break
        if attempt == max(0, session.cfg.max_retries):
            raise CheckFailed(session.stage, problems)
        attempt_notes = [
            "; ".join(p.split(": ", 1)[1] for p in problems if p.startswith(f"{i + 1}번째:"))
            or notes[i]
            for i in range(len(slots))
        ]
    review = _review(session, budget, conversations, 0)
    flagged = {r.conversationId: r.errors for r in review.reviews if r.errors}
    if not flagged:
        return conversations
    positions = [i for i, cid in enumerate(ids) if cid in flagged]
    correction_inputs = {
        "system": samples.batch_inputs(session, slots, ids, notes)["system"],
        "handoff": dump(session.handoff),
        "conversations": [
            {
                "conversationId": ids[i],
                "original": written[i],
                "confirmedErrors": [dump(e) for e in flagged[ids[i]]],
            }
            for i in positions
        ],
        "instruction": "Only edit cited assistant message indices. Preserve all user text, "
        "uncited history, scene, sourceId and skeletonKey verbatim. Same order.",
    }
    repaired, ref, actual = request(
        **args, task="repair", role="data_deck_repair", inputs=correction_inputs
    )
    replacements = [dump(c) for c in repaired.conversations]
    if len(replacements) != len(positions):
        raise CheckFailed(session.stage, ["repair must return exactly the flagged conversations"])
    for pos, replacement in zip(positions, replacements, strict=True):
        # Repair cannot change turn count, so the writer's long-dialogue position
        # markers stay valid; carry them when the repair model leaves them empty.
        for key in ("topicShiftAt", "lateTriggerAt", "flowBeats"):
            if not replacement.get(key):
                replacement[key] = written[pos].get(key, [])
    for pos, replacement in zip(positions, replacements, strict=True):
        original = written[pos]
        mutable = {e.messageIndex for e in flagged[ids[pos]]}
        if any(original[k] != replacement[k] for k in ("scene", "skeletonKey", "sourceId")) or len(
            original["messages"]
        ) != len(replacement["messages"]):
            raise CheckFailed(session.stage, ["repair changed scene/source/skeleton/turn count"])
        for j, (old, new) in enumerate(
            zip(original["messages"], replacement["messages"], strict=True)
        ):
            if old["role"] != new["role"] or (j not in mutable and old != new):
                raise CheckFailed(session.stage, ["repair changed user text or uncited history"])
    repaired_slots = [slots[i] for i in positions]
    repaired_specs = [specs[i] for i in positions]
    problems = checks.batch_problems(replacements, repaired_specs, session.system)
    if problems:
        raise CheckFailed(session.stage, problems)
    fixed = samples.assemble(
        replace(session, writer_model=actual),
        repaired_slots,
        [ids[i] for i in positions],
        replacements,
        ref,
    )
    for pos, conv, spec in zip(positions, fixed, repaired_specs, strict=True):
        problems = checks.conversation_problems(conv, spec)
        if problems:
            raise CheckFailed(session.stage, problems)
        conversations[pos] = conv
    final = _review(session, budget, conversations, 1)
    unresolved = [f"{r.conversationId}: {e.explanation}" for r in final.reviews for e in r.errors]
    if unresolved:
        raise CheckFailed(
            session.stage, ["semantic errors unresolved after one correction", *unresolved]
        )
    return conversations


def write_batch(session, slots, ids, notes):
    """A persistent receipt prevents unlimited re-execution of a failed batch."""
    from character_factory_poc.stages.s9_data.samples import batch_inputs

    root = _rev_dir(session) / "deck-batches"
    key = sha256_of([session.cluster, ids])
    start, done = root / f"{key}-started.json", root / f"{key}-outcome.json"
    fingerprint = sha256_of(
        {"input": batch_inputs(session, slots, ids, notes), "deck": snapshot(session.ctx)}
    )
    if start.exists():
        if read_json(start)["fingerprint"] != fingerprint:
            raise CheckFailed(session.stage, ["batch inputs/binding changed; use a new revision"])
        if done.exists() and (outcome := read_json(done))["ok"]:
            return [Conversation.model_validate(c) for c in outcome["conversations"]]
        raise CheckFailed(
            session.stage, ["batch failed or interrupted; explicit new revision required"]
        )
    write_once_json(start, {"fingerprint": fingerprint, "conversationIds": ids})
    try:
        conversations = _write_and_review(session, slots, ids, notes, session.ctx.budget())
    except Exception as exc:
        write_once_json(
            done,
            {
                "ok": False,
                "failureType": type(exc).__name__,
                "problems": exc.problems if isinstance(exc, CheckFailed) else [],
            },
        )
        raise
    write_once_json(done, {"ok": True, "conversations": [dump(c) for c in conversations]})
    return conversations
