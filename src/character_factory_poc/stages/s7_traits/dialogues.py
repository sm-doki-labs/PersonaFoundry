"""S7b: all twelve first-output dialogues, with separately hashed local facts."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from character_factory_poc.common.budget import Budget
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import AgentFormatError, CheckFailed
from character_factory_poc.common.schema import dump, register
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.contracts.formation import (
    DialoguePair,
    FactRef,
    FormationContract,
    FormationDialogue,
    FormationDialogues,
    Nonempty,
    PersonaBlueprint,
    Sha256,
)
from character_factory_poc.contracts.persona import TraitSheet
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s7_traits.formation import (
    SourceClaim,
    approved_source,
    artifact,
    bind_claim,
    fail_step,
    generate_draft,
    previous_failure,
    reference_bodies,
    reference_sources,
    revision_dir,
    verify_sources,
)
from character_factory_poc.stages.s7_traits.formation import (
    canonical_plan as project_canonical_plan,
)


class FactDraft(FormationContract):
    scope: Literal["canon", "example-local"]
    owner: Literal["character", "user", "shared", "external"]
    text: Nonempty
    source: SourceClaim
    dialogueId: Nonempty | None = None


class CanonFactDraft(FactDraft):
    scope: Literal["canon"]
    dialogueId: None = None


class LocalFactDraft(FactDraft):
    scope: Literal["example-local"]
    dialogueId: Nonempty


class DialogueDraft(FormationContract):
    dialogueId: Nonempty
    category: Literal["ordinary", "boundary", "change"]
    selectionSlot: Literal[
        "ordinary-self", "playful-affection", "listening-conflict", "condition-owner-change"
    ]
    pairs: list[DialoguePair] = Field(min_length=2, max_length=6)
    factRefs: list[Annotated[CanonFactDraft | LocalFactDraft, Field(discriminator="scope")]] = (
        Field(default_factory=list)
    )


@register("formation-dialogues-draft-v1")
class DialoguesDraft(FormationContract):
    dialogues: list[DialogueDraft] = Field(min_length=12, max_length=12)
    sourceRefs: list[SourceClaim] = Field(default_factory=list)
    characterId: Nonempty | None = None
    traitRevision: Nonempty | None = None
    planSha256: Sha256 | None = None
    traitSheetSha256: Sha256 | None = None
    blueprintSha256: Sha256 | None = None

    @model_validator(mode="after")
    def check_composition(self):
        rows = self.dialogues
        if len({d.dialogueId for d in rows}) != 12:
            raise ValueError("dialogue IDs must be unique")
        if Counter(d.category for d in rows) != {"ordinary": 8, "boundary": 2, "change": 2}:
            raise ValueError("dialogues require 8 ordinary / 2 boundary / 2 change")
        if sum(len(d.pairs) == 6 for d in rows) < 2:
            raise ValueError("at least two dialogues must have six pairs")
        if len({d.selectionSlot for d in rows}) != 4:
            raise ValueError("all four selection slots are required")
        for row in rows:
            # Check shape here; ownership/citation semantics never trigger a redraw.
            FormationDialogue.model_validate({**dump(row), "factRefs": []})
        return self


def _local_body(row) -> dict:
    return {key: dump(row)[key] for key in ("dialogueId", "category", "selectionSlot", "pairs")}


def _local_source(ctx: Context, cid: str, root: Path, row):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", row.dialogueId):
        raise ValueError("dialogueId must be a safe local identifier")
    return artifact(
        ctx,
        cid,
        "dialogue",
        root / "dialogues/sources" / f"{row.dialogueId}.json",
        root.name,
    )


def build_formation_dialogues(
    ctx: Context,
    cid: str,
    canonical_plan: dict,
    sheet: TraitSheet,
    blueprint: PersonaBlueprint,
    *,
    budget: Budget | None = None,
) -> FormationDialogues:
    """Write/reuse S7b in the pinned revision, giving the writer actual source bodies."""
    if not ctx.execute:
        raise ValueError("S7 formation requires execute=True")
    root = revision_dir(ctx, cid)
    folder = root / "dialogues"
    previous_failure(folder)
    try:
        plan, _ = load_approved_plan(ctx, cid)
        plan_src = approved_source(ctx, cid, plan)
        trait_src = artifact(ctx, cid, "trait", root / "trait-sheet.json", root.name)
        bp_src = artifact(ctx, cid, "blueprint", root / "blueprint.json", root.name)
        standards = reference_sources(ctx, cid, root)
        sources = [plan_src, trait_src, bp_src, *standards]
        if canonical_plan != project_canonical_plan(plan, plan_src.path):
            raise ValueError("writer canonical plan differs from approved projection")
        if dump(sheet) != read_json(trait_src.path) or dump(blueprint) != read_json(bp_src.path):
            raise ValueError("writer trait/blueprint differs from stored design")
        meta = {
            "characterId": cid,
            "traitRevision": root.name,
            "planSha256": sha256_file(plan_src.path),
            "traitSheetSha256": sha256_file(trait_src.path),
            "blueprintSha256": sha256_file(bp_src.path),
        }
        out = root / "formation-dialogues.json"
        if not out.exists():
            draft = generate_draft(
                ctx,
                cid,
                folder,
                {
                    "canonical_plan": canonical_plan,
                    "traitSheet": dump(sheet),
                    "blueprint": dump(blueprint),
                    "reference_sources": reference_bodies(standards),
                },
                DialoguesDraft,
                "persona_dialogues",
                "dialogues",
                budget or ctx.budget(),
            )
            for key, value in meta.items():
                if getattr(draft, key) is not None and getattr(draft, key) != value:
                    raise ValueError(f"dialogues {key} mismatch")
            refs = [
                plan_src.source("coreTraits[0]"),
                trait_src.source("choice.attention"),
                bp_src.source("ordinaryModes.selfStory"),
            ]
            refs.extend(bind_claim(claim, sources) for claim in draft.sourceRefs)
            rows = []
            for row in draft.dialogues:
                local = _local_source(ctx, cid, root, row)
                # Fact metadata is deliberately absent: the source cannot hash itself.
                write_once_json(local.path, _local_body(row))
                facts = []
                for fact in row.factRefs:
                    if fact.scope == "example-local" and fact.dialogueId != row.dialogueId:
                        raise ValueError("example-local fact belongs to another dialogue")
                    bound = bind_claim(
                        fact.source, [local] if fact.scope == "example-local" else sources
                    )
                    facts.append(FactRef.model_validate({**dump(fact), "source": dump(bound)}))
                rows.append(
                    FormationDialogue.model_validate(
                        {
                            **dump(row),
                            "factRefs": [dump(f) for f in facts],
                        }
                    )
                )
            result = FormationDialogues.model_validate(
                {
                    **meta,
                    "sourceRefs": [dump(ref) for ref in refs],
                    "dialogues": [dump(row) for row in rows],
                }
            )
            write_once_json(out, dump(result))
        result = FormationDialogues.model_validate(read_json(out))
        for key, value in meta.items():
            if getattr(result, key) != value:
                raise ValueError(f"stored dialogues {key} mismatch")
        verify_sources(result.sourceRefs, sources)
        for row in result.dialogues:
            local = _local_source(ctx, cid, root, row)
            if read_json(local.path) != _local_body(row):
                raise ValueError("stored local dialogue source differs from dialogue pairs")
            for fact in row.factRefs:
                verify_sources([fact.source], [local] if fact.scope == "example-local" else sources)
        return result
    except AgentFormatError:
        raise
    except (ValueError, CheckFailed) as exc:
        fail_step(folder, exc)
