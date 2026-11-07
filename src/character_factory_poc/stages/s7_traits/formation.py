"""Opt-in S7a: one design draft, factory-bound sources, immutable resume."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, ValidationError

from character_factory_poc.common.budget import Budget, CallPlan
from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.errors import AgentFormatError, CheckFailed
from character_factory_poc.common.schema import dump, register
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.formation import (
    DecisionRule,
    FactPolicy,
    FormationContract,
    FormationDesign,
    Nonempty,
    OrdinaryModes,
    PersonaBlueprint,
    Sha256,
    SourceRef,
    VoiceProfile,
    load_quality_profile,
)
from character_factory_poc.contracts.persona import TraitSheet
from character_factory_poc.pipeline.agent import AGENT_MAX_OUTPUT_TOKENS, load_role_prompt
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s7_traits.check import check_matches_plan, check_trait_sheet

PROFILE_ID = "ko-text-prompt-long-v1"
_CANON_FIELDS = (
    "selectedTraits",
    "schemaVersion",
    "characterId",
    "planRev",
    "name",
    "age",
    "gender",
    "job",
    "background",
    "coreTraits",
    "contrastTrait",
    "choices",
    "lifeAndTastes",
    "wantsAndFears",
    "misreadings",
    "voiceSummary",
    "voiceExamples",
    "boundaries",
    "chapterArc",
    "chapters",
    "profileCard",
)


class SourceClaim(FormationContract):
    """Models cite visible fields; the factory supplies artifact identity and bytes."""

    kind: Literal["plan", "trait", "reference", "blueprint", "dialogue"]
    fieldPath: Nonempty
    quote: Nonempty
    ref: Nonempty | None = None
    version: Nonempty | None = None
    sha256: Sha256 | None = None


class BlueprintDraft(FormationContract):
    decisionRules: list[DecisionRule] = Field(min_length=1)
    voiceProfile: VoiceProfile
    ordinaryModes: OrdinaryModes
    factPolicy: FactPolicy
    sourceRefs: list[SourceClaim] = Field(default_factory=list)
    unresolved: list[Nonempty] = Field(default_factory=list)
    schemaVersion: Literal["persona-blueprint-v1"] = "persona-blueprint-v1"
    characterId: Nonempty | None = None
    planRev: Nonempty | None = None
    planSha256: Sha256 | None = None
    traitSheetSha256: Sha256 | None = None


@register("formation-design-draft-v1")
class FormationDraft(FormationContract):
    traitSheet: TraitSheet
    blueprint: BlueprintDraft


@dataclass(frozen=True)
class Artifact:
    kind: str
    path: Path
    ref: str
    version: str

    def source(self, field: str) -> SourceRef:
        value = field_text(read_json(self.path), field)
        return SourceRef(
            kind=self.kind,
            ref=self.ref,
            version=self.version,
            sha256=sha256_file(self.path),
            fieldPath=field,
            quote=value,
        )


def artifact(ctx: Context, cid: str, kind: str, path: Path, version: str) -> Artifact:
    return Artifact(kind, path, path.relative_to(ctx.character_dir(cid)).as_posix(), version)


def reference_inputs(references, reference_docs) -> list[dict]:
    """Only explicitly supplied standards; never fetch presets or dialogue corpora."""
    docs = reference_docs or {}
    records = []
    for ref in references or []:
        if (
            ref.get("kind") not in {"STANFORD", "OTHER"}
            or not all(isinstance(ref.get(k), str) and ref[k].strip() for k in ("id", "version"))
            or ref["id"] not in docs
        ):
            raise ValueError("reference requires an allowed standard and explicit body/version")
        records.append(
            {
                "kind": ref["kind"],
                "id": ref["id"],
                "version": ref["version"],
                "body": docs[ref["id"]],
            }
        )
    if len({r["id"] for r in records}) != len(records) or set(docs) != {r["id"] for r in records}:
        raise ValueError("reference bodies must match unique declared reference IDs")
    return sorted(records, key=lambda r: r["id"])


def store_references(ctx: Context, cid: str, root: Path, records: list[dict]) -> None:
    index = []
    for n, record in enumerate(records, 1):
        path = root / "references" / f"reference-{n:03}.json"
        write_once_json(path, {"body": record["body"]})
        index.append(
            {
                **{k: record[k] for k in ("id", "kind", "version")},
                "ref": path.relative_to(ctx.character_dir(cid)).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    write_once_json(root / "references/index.json", index)


def reference_sources(ctx: Context, cid: str, root: Path) -> list[Artifact]:
    sources = []
    for n, record in enumerate(read_json(root / "references/index.json"), 1):
        src = artifact(
            ctx, cid, "reference", root / "references" / f"reference-{n:03}.json", record["version"]
        )
        if src.ref != record["ref"] or sha256_file(src.path) != record["sha256"]:
            raise ValueError("stored reference source mismatch")
        sources.append(src)
    return sources


def reference_bodies(sources: list[Artifact]) -> list[dict]:
    return [
        {
            "ref": src.ref,
            "version": src.version,
            "sha256": sha256_file(src.path),
            "body": read_json(src.path),
        }
        for src in sources
    ]


def check_references(sheet: TraitSheet, root: Path) -> None:
    allowed = {
        (r["kind"], r["id"], r["version"]) for r in read_json(root / "references/index.json")
    }
    if any((r.kind, r.id, r.version) not in allowed for r in sheet.references):
        raise ValueError("trait reference is not an explicitly provided standard")


def field_text(body: Any, field: str) -> str:
    """Resolve an actual scalar JSON field; never evaluate a claimed path."""
    if field.startswith("/"):
        parts = [p.replace("~1", "/").replace("~0", "~") for p in field[1:].split("/")]
    elif re.fullmatch(r"[A-Za-z_]\w*(?:(?:\[\d+\])|(?:\.[A-Za-z_0-9]+))*", field):
        parts = re.findall(r"[^.\[\]]+", field)
    else:
        raise ValueError(f"invalid source fieldPath: {field}")
    try:
        for part in parts:
            body = body[int(part)] if isinstance(body, list) and part.isdecimal() else body[part]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ValueError(f"missing source fieldPath: {field}") from None
    if isinstance(body, str):
        return body
    if body is None or isinstance(body, dict | list):
        raise ValueError(f"source fieldPath must identify a scalar: {field}")
    return json.dumps(body, ensure_ascii=False)


def bind_claim(claim: SourceClaim, sources: list[Artifact]) -> SourceRef:
    candidates = [s for s in sources if s.kind == claim.kind]
    if claim.ref is not None:
        candidates = [s for s in candidates if s.ref == claim.ref]
    if len(candidates) != 1:
        raise ValueError(f"unprovided or ambiguous source: {claim.kind}/{claim.ref}")
    src = candidates[0]
    full = src.source(claim.fieldPath)
    if claim.quote not in full.quote:
        raise ValueError(f"source quote does not match {src.ref}:{claim.fieldPath}")
    if claim.version is not None and claim.version != src.version:
        raise ValueError(f"source version mismatch: {src.ref}")
    if claim.sha256 is not None and claim.sha256 != full.sha256:
        raise ValueError(f"source hash mismatch: {src.ref}")
    return full.model_copy(update={"quote": claim.quote})


def verify_sources(refs: list[SourceRef], sources: list[Artifact]) -> None:
    for ref in refs:
        bind_claim(SourceClaim.model_validate(dump(ref)), sources)


def canonical_plan(plan, plan_path: Path) -> dict[str, Any]:
    raw = dump(plan)
    return {
        "schemaVersion": "persona-source-v1",
        "sourceSha256": sha256_file(plan_path),
        "plan": {key: raw[key] for key in _CANON_FIELDS if key in raw},
    }


def approved_source(ctx: Context, cid: str, plan) -> Artifact:
    approved, path = load_approved_plan(ctx, cid)
    if dump(approved) != dump(plan) or plan.characterId != cid:
        raise ValueError("formation input differs from approved canonical plan")
    return artifact(ctx, cid, "plan", path, approved.planRev)


def revision_dir(ctx: Context, cid: str) -> Path:
    rev = ctx.state(cid).stage("s7").currentRev
    if not rev:
        raise ValueError("S7 formation requires a pinned revision")
    return ctx.character_dir(cid) / "s7-traits" / rev


def format_retries(ctx: Context) -> int:
    return min(2, max(0, int(ctx.config.stage("s7").get("max_format_retries", 2))))


def plan_calls(cfg_retries: int = 2) -> list[CallPlan]:
    calls = 1 + min(2, max(0, cfg_retries))
    return [
        CallPlan("s7", f"S7{letter} {label} (format retries only)", calls, est_cost_usd=None)
        for letter, label in (("a", "trait + blueprint"), ("b", "12 formation dialogues"))
    ]


def remaining_calls(folder: Path, limit: int) -> int:
    workspace = folder / "workspace"
    if (workspace / "output.json").exists() or (folder / "failure.json").exists():
        return 0
    used = sum(
        (workspace / f"attempt-{n}.txt").exists() or (workspace / f"error-{n}.json").exists()
        for n in range(1, limit + 1)
    )
    return limit - used


def previous_failure(folder: Path) -> None:
    if (folder / "failure.json").exists():
        raise CheckFailed("s7", read_json(folder / "failure.json")["problems"])


def fail_step(folder: Path, exc: Exception) -> None:
    problems = exc.problems if isinstance(exc, CheckFailed) else [str(exc)]
    write_once_json(folder / "failure.json", {"problems": problems})
    raise CheckFailed("s7", problems) from exc


def generate_draft(
    ctx: Context,
    cid: str,
    folder: Path,
    inputs: dict,
    contract,
    role: str,
    step: str,
    budget: Budget,
):
    """Replay saved attempts first. Only JSON/shape failures permit another output."""
    if not ctx.execute:
        raise ValueError("S7 formation requires execute=True")
    workspace = folder / "workspace"
    write_once_json(workspace / "inputs.json", inputs)
    if (workspace / "output.json").exists():
        return contract.model_validate(read_json(workspace / "output.json"))
    role_text = load_role_prompt(role)
    write_once_text(workspace / "role.md", role_text)
    user = json.dumps(
        {"inputs": inputs, "outputSchema": contract.model_json_schema()},
        ensure_ascii=False,
        indent=2,
    )
    user += "\nReturn one json object only."
    messages = [Message("system", role_text), Message("user", user)]
    failures = []
    for attempt in range(1, format_retries(ctx) + 2):
        raw_path = workspace / f"attempt-{attempt}.txt"
        error_path = workspace / f"error-{attempt}.json"
        if error_path.exists() and not raw_path.exists():
            failures = [read_json(error_path)["error"]]
            continue
        if raw_path.exists():
            text = raw_path.read_text(encoding="utf-8")
        else:
            request = ChatRequest(
                kind="AGENT",
                stage="s7",
                messages=tuple(messages),
                ref=f"{cid}/{folder.parent.name}/{step}#{attempt}",
                max_output_tokens=AGENT_MAX_OUTPUT_TOKENS,
                response_json=True,
                metadata={"formationStep": step},
            )
            write_once_json(
                workspace / f"request-{attempt}.json",
                {
                    "ref": request.ref,
                    "messages": [vars(m) for m in messages],
                    "outputContract": contract.__name__,
                },
            )
            try:
                text = ctx.role_model(cid, budget, role).complete(request).text
            except Exception as exc:
                write_once_json(error_path, {"error": str(exc)})
                raise
            write_once_text(raw_path, text)
        try:
            output = contract.model_validate(extract_json_object(text))
        except (ValueError, ValidationError) as exc:
            failures = [str(exc)]
            messages += [
                Message("assistant", text),
                Message(
                    "user",
                    (
                        "JSON 형식과 필수 필드만 고친다. "
                        "의미 품질을 이유로 새 예시를 선별하지 않는다.\n" + str(exc)
                    ),
                ),
            ]
            continue
        write_once_json(workspace / "output.json", dump(output))
        return output
    write_once_json(folder / "failure.json", {"problems": failures})
    raise AgentFormatError(f"{role}: format attempts exhausted: " + "; ".join(failures))


def _check_design(design: FormationDesign, cid: str, plan, sources: list[Artifact]) -> None:
    sheet, bp = design.traitSheet, design.blueprint
    if sheet.characterId != cid or sheet.planRev != plan.planRev:
        raise ValueError("trait sheet characterId/planRev differs from canonical plan")
    problems = check_trait_sheet(sheet) + check_matches_plan(plan.name, plan.coreTraits)(sheet)
    if problems:
        raise CheckFailed("s7", problems)
    plan_src, trait_src = sources[:2]
    if (bp.planSha256, bp.traitSheetSha256) != (
        sha256_file(plan_src.path),
        sha256_file(trait_src.path),
    ):
        raise ValueError("stored formation design source hash mismatch")
    verify_sources(bp.sourceRefs, sources)
    check_references(sheet, sources[1].path.parent)


def build_formation(
    ctx: Context, cid: str, plan, *, budget: Budget | None = None
) -> FormationDesign:
    """Form or reuse S7a in the state's exact S7 revision; no separate trait call."""
    if not ctx.execute:
        raise ValueError("S7 formation requires execute=True")
    root = revision_dir(ctx, cid)
    folder = root / "design"
    previous_failure(folder)
    try:
        plan_src = approved_source(ctx, cid, plan)
        trait_src = artifact(ctx, cid, "trait", root / "trait-sheet.json", root.name)
        standards = reference_sources(ctx, cid, root)
        sources = [plan_src, trait_src, *standards]
        if not (root / "blueprint.json").exists():
            draft = generate_draft(
                ctx,
                cid,
                folder,
                {
                    "canonical_plan": canonical_plan(plan, plan_src.path),
                    "reference_sources": reference_bodies(standards),
                },
                FormationDraft,
                "persona_formation",
                "design",
                budget or ctx.budget(),
            )
            sheet = draft.traitSheet
            if sheet.characterId != cid or sheet.planRev != plan.planRev:
                raise ValueError("trait sheet characterId/planRev differs from canonical plan")
            problems = check_trait_sheet(sheet) + check_matches_plan(plan.name, plan.coreTraits)(
                sheet
            )
            if problems:
                raise CheckFailed("s7", problems)
            check_references(sheet, root)
            write_once_json(trait_src.path, dump(sheet))
            body = BlueprintDraft.model_validate(draft.blueprint)
            meta = {
                "characterId": cid,
                "planRev": plan.planRev,
                "planSha256": sha256_file(plan_src.path),
                "traitSheetSha256": sha256_file(trait_src.path),
            }
            for key, value in meta.items():
                if getattr(body, key) is not None and getattr(body, key) != value:
                    raise ValueError(f"blueprint {key} mismatch")
            refs = [plan_src.source("coreTraits[0]"), trait_src.source("choice.attention")]
            refs.extend(bind_claim(claim, sources) for claim in body.sourceRefs)
            bp = PersonaBlueprint.model_validate(
                {
                    **dump(body),
                    **meta,
                    "sourceRefs": [dump(ref) for ref in refs],
                }
            )
            design = FormationDesign(traitSheet=sheet, blueprint=bp)
            _check_design(design, cid, plan, sources)
            write_once_json(root / "blueprint.json", dump(bp))
        design = FormationDesign.model_validate(
            {
                "traitSheet": read_json(trait_src.path),
                "blueprint": read_json(root / "blueprint.json"),
            }
        )
        _check_design(design, cid, plan, sources)
        return design
    except AgentFormatError:
        raise
    except (ValueError, CheckFailed) as exc:
        fail_step(folder, exc)


def formation_recipe_hash() -> str:
    from importlib.resources import files

    bodies = [
        Path(__file__).read_text("utf-8"),
        Path(__file__).with_name("dialogues.py").read_text("utf-8"),
    ]
    for role in ("persona_formation", "persona_dialogues"):
        bodies.append(
            files("character_factory_poc.prompts").joinpath(role + ".md").read_text("utf-8")
        )
    return sha256_text("\n".join(bodies))


def run_formation_s7(ctx: Context, cid: str, references=None, reference_docs=None) -> Path:
    """Opt-in lifecycle. S7 only becomes ready after both stored steps validate."""
    cfg = ctx.config.stage("s7")
    if cfg.get("formation_profile") != PROFILE_ID:
        raise ValueError(f"unknown formation profile: {cfg.get('formation_profile')!r}")
    if not ctx.execute:
        raise ValueError("S7 formation requires execute=True")
    standards = reference_inputs(references, reference_docs)
    profile_path = cfg.get("profile_path")
    profile = load_quality_profile(ctx.config.root / profile_path if profile_path else None)
    if profile.profileId != PROFILE_ID:
        raise ValueError("formation profile_path profileId mismatch")
    plan, plan_path = load_approved_plan(ctx, cid)
    state = ctx.state(cid)
    state.require_deps("s7")
    stage = state.stage("s7")
    parent = ctx.character_dir(cid) / "s7-traits"
    old = parent / stage.currentRev if stage.currentRev else None
    resume = (
        old is not None
        and (old / "profile.json").exists()
        and stage.status
        in {
            "RUNNING",
            "CHECK_FAILED",
            "AWAITING_HUMAN",
        }
    )
    recipe_sha = formation_recipe_hash()
    if ctx.text_deck_enabled:
        recipe_sha = sha256_text(
            recipe_sha
            + json.dumps(
                [ctx.config.text_binding(t) for t in ("voice", "scenarios")], sort_keys=True
            )
        )
    if resume and read_json(old / "inputs.json").get("formationRecipeSha256") != recipe_sha:
        if stage.status != "CHECK_FAILED":
            raise ValueError(
                "formation recipe changed; reject the pending revision before a new one"
            )
        resume = False
    root = old if resume else parent / next_rev(parent, "tr")
    budget = ctx.budget()
    pending = []
    for call, step, output in zip(
        plan_calls(format_retries(ctx)),
        ("design", "dialogues"),
        ("blueprint.json", "formation-dialogues.json"),
        strict=True,
    ):
        if not (root / output).exists():
            pending.append(
                CallPlan(
                    call.stage,
                    call.description,
                    remaining_calls(root / step, call.calls),
                    est_cost_usd=None,
                )
            )
    budget.check_plan(pending)
    if not resume or references is not None or reference_docs is not None:
        store_references(ctx, cid, root, standards)
    write_once_json(root / "profile.json", dump(profile))
    write_once_json(
        root / "inputs.json",
        {
            "plan": plan_path.relative_to(ctx.character_dir(cid)).as_posix(),
            "planSha256": sha256_file(plan_path),
            "profileSha256": sha256_file(root / "profile.json"),
            "formationProfile": PROFILE_ID,
            "formationRecipeSha256": recipe_sha,
            "referencesSha256": sha256_file(root / "references/index.json"),
        },
    )
    already_ready = resume and stage.status == "AWAITING_HUMAN"
    if not already_ready:
        state.transition("s7", "RUNNING", rev=root.name)
    try:
        design = build_formation(ctx, cid, plan, budget=budget)
        from character_factory_poc.stages.s7_traits.dialogues import build_formation_dialogues

        build_formation_dialogues(
            ctx,
            cid,
            canonical_plan(plan, plan_path),
            design.traitSheet,
            design.blueprint,
            budget=budget,
        )
    except Exception as exc:
        if not already_ready:
            state.transition("s7", "CHECK_FAILED", rev=root.name, error=str(exc))
        raise
    finally:
        write_manifest(root)
    if not already_ready:
        state.transition("s7", "AWAITING_HUMAN", rev=root.name)
    return root / "trait-sheet.json"
