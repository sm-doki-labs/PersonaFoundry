"""S3r: 기획서로 용도별 검색을 하고 Curator의 선별 근거를 고정한다."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.errors import AgentFormatError, CheckFailed, ValidationFailed
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, write_manifest, write_once_json
from character_factory_poc.contracts.plan import CharacterPlan
from character_factory_poc.contracts.planning import CharacterPlanV2
from character_factory_poc.contracts.refs import (
    CurationOutput,
    ReferenceIndex,
    ReferenceSet,
    Retrieved,
    SelectedRef,
)
from character_factory_poc.pipeline.agent import AgentSpec, Check, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.embed import Embedder, HashEmbedder, cosine, make_embedder
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s3r_refs.index import load_index


def _settings(ctx: Context) -> dict[str, int]:
    values = {
        "top_k": 8,
        "max_selected": 8,
        "max_check_retries": 3,
        "max_format_retries": 2,
    }
    cfg = ctx.config.stage("s3r")
    for key, default in values.items():
        value = cfg.get(key, default)
        minimum = 0 if key.endswith("retries") else 1
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise CheckFailed("s3r", [f"{key}는 {minimum} 이상의 정수여야 한다"])
        values[key] = value
    return values


def plan_calls(ctx: Context) -> list[CallPlan]:
    if not ctx.config.resources.get("reference_index"):
        return []
    cfg = _settings(ctx)
    n = 1 + cfg["max_check_retries"] + cfg["max_format_retries"]
    return [CallPlan("s3r", f"Curator 참고 자료 선별 (재시도 포함 최대 {n}회)", n)]


def build_queries(plan: CharacterPlan | CharacterPlanV2) -> dict[str, str]:
    traits = [*plan.coreTraits, plan.contrastTrait]
    if isinstance(plan, CharacterPlanV2):
        traits += [f"{c.situation}: {c.firstMove}" for c in plan.choices]
        traits += plan.misreadings
        voice = [plan.voiceSummary, *plan.voiceExamples]
        data = [*plan.lifeAndTastes, plan.background]
    else:
        voice = plan.coreTraits
        data = [plan.job]
    return {"TRAITS": "\n".join(traits), "VOICE": "\n".join(voice), "DATA": "\n".join(data)}


def retrieve(
    index: ReferenceIndex,
    queries: dict[str, str],
    *,
    embedder: Embedder,
    top_k: int = 8,
) -> list[Retrieved]:
    """용도에 허용된 항목만 검색하고 동점은 itemId 순서로 고정한다."""
    if top_k < 1:
        raise ValueError("top_k는 1 이상이어야 한다")
    if (index.embedder, index.dim) != (embedder.name, embedder.dim):
        raise ValueError("인덱스와 검색 임베더의 이름 또는 dim이 다르다")
    vectors = embedder.embed(list(queries.values()))
    found = []
    for use, vector in zip(queries, vectors, strict=True):
        scored = [
            Retrieved(itemId=item.itemId, use=use, score=cosine(vector, item.vector))
            for item in index.items
            if use in item.uses
        ]
        found.extend(sorted(scored, key=lambda r: (-r.score, r.itemId))[:top_k])
    return found


def _selection_check(candidates: list[dict[str, Any]], max_selected: int) -> Check:
    allowed = {(row["itemId"], row["use"]) for row in candidates}

    def check(output: CurationOutput) -> list[str]:
        problems = []
        if len(output.selected) > max_selected:
            problems.append(f"selected 수가 max_selected={max_selected}를 넘었다")
        seen: set[str] = set()
        for item in output.selected:
            if (item.itemId, item.use) not in allowed:
                problems.append(f"검색 후보에 없는 선택이다: {item.itemId} ({item.use})")
            if item.itemId in seen:
                problems.append(f"selected itemId가 중복됐다: {item.itemId}")
            seen.add(item.itemId)
            if not item.why.strip():
                problems.append(f"why가 비었다: {item.itemId}")
        return problems

    return check


def codex_checks(stage: str, workspace: Path) -> tuple[str, list]:
    """registry가 연결할 진입점. API 백엔드와 같은 검색 후보·수량 검사를 쓴다."""
    if stage != "s3r":
        raise ValueError(f"참고 자료 검사가 정의되지 않은 단계: {stage}")
    inputs = Path(workspace) / "inputs"
    candidates = json.loads((inputs / "candidates.json").read_text("utf-8"))
    limits = json.loads((inputs / "limits.json").read_text("utf-8"))
    return "reference-curation-output-v1", [_selection_check(candidates, limits["max_selected"])]


def _embedder(index: ReferenceIndex) -> Embedder:
    # hash-v1의 차원은 인덱스에 고정되므로 기본값이 아닌 차원도 그대로 재현한다.
    if index.embedder == "hash-v1":
        return HashEmbedder(index.dim)
    return make_embedder(index.embedder)


def run_s3r(ctx: Context, cid: str) -> Path | None:
    state = ctx.state(cid)
    state.require_deps("s3r")
    budget = ctx.budget()
    budget.check_plan(plan_calls(ctx))
    index_path = ctx.config.resources.get("reference_index")
    if not index_path:
        status = state.stage("s3r").status
        if status == "PENDING":
            state.transition("s3r", "SKIPPED")
        elif status != "SKIPPED":
            raise CheckFailed("s3r", ["이미 실행한 단계의 reference_index 설정을 제거할 수 없다"])
        return None
    cfg = _settings(ctx)
    plan, _ = load_approved_plan(ctx, cid)
    rev = next_rev(ctx.character_dir(cid) / "s3r-refs", "rs")
    rev_dir = ctx.character_dir(cid) / "s3r-refs" / rev
    state.transition("s3r", "RUNNING", rev=rev)
    try:
        path = Path(index_path)
        if not path.is_absolute():
            path = ctx.config.root / path
        index, digest = load_index(path)
        queries = build_queries(plan)
        retrieved = retrieve(index, queries, embedder=_embedder(index), top_k=cfg["top_k"])
        items = {item.itemId: item for item in index.items}
        candidates = [
            {
                "itemId": r.itemId,
                "source": items[r.itemId].source,
                "label": items[r.itemId].label,
                "use": r.use,
                "score": r.score,
                "text": items[r.itemId].text[:400],
            }
            for r in retrieved
        ]
        if not candidates:
            raise CheckFailed("s3r", ["기획서 용도에 맞는 참고 자료 검색 후보가 없다"])
        summary = {"name": plan.name, "age": plan.age, "job": plan.job, **queries}
        inputs = {
            "plan-summary": summary,
            "queries": queries,
            "candidates": candidates,
            "limits": {"max_selected": cfg["max_selected"]},
        }
        first = candidates[0]
        example = {
            "schemaVersion": "reference-curation-output-v1",
            "selected": [
                {"itemId": first["itemId"], "use": first["use"], "why": "판단 우선순위 보강에 쓴다"}
            ],
        }
        spec = AgentSpec(
            role="curator",
            stage="s3r",
            output_contract="reference-curation-output-v1",
            max_check_retries=cfg["max_check_retries"],
            max_format_retries=cfg["max_format_retries"],
        )
        result = run_agent(
            spec,
            rev_dir / "workspace",
            inputs,
            [_selection_check(candidates, cfg["max_selected"])],
            ctx.text_model(cid, budget),
            ref=f"{cid}/{rev}",
            contract_example=example,
            backend=ctx.agent_backend(cid, budget, "s3r"),
        )
        if not result.ok:
            raise CheckFailed("s3r", result.problems)
        output: CurationOutput = result.output
        refs = ReferenceSet(
            characterId=cid,
            refRev=rev,
            planRev=plan.planRev,
            indexId=index.indexId,
            indexSha256=digest,
            embedder=index.embedder,
            queries=queries,
            retrieved=retrieved,
            selected=[
                SelectedRef(
                    itemId=s.itemId,
                    source=items[s.itemId].source,
                    version=items[s.itemId].version,
                    label=items[s.itemId].label,
                    use=s.use,
                    why=s.why,
                )
                for s in output.selected
            ],
        )
        write_once_json(rev_dir / "reference-set.json", dump(refs))
        write_manifest(rev_dir)
    except (CheckFailed, AgentFormatError, ValidationFailed, ValueError, OSError) as e:
        failure = e if isinstance(e, CheckFailed) else CheckFailed("s3r", [str(e)])
        ctx.state(cid).transition("s3r", "CHECK_FAILED", rev=rev, error=str(failure))
        if rev_dir.exists():
            write_manifest(rev_dir)
        if failure is e:
            raise
        raise failure from e
    ctx.state(cid).transition("s3r", "APPROVED", rev=rev)
    return rev_dir


def load_latest_reference_set(ctx: Context, cid: str) -> ReferenceSet | None:
    """현재 G3와 대응하는 승인 결과만 읽는다. 실패한 새 revision은 돌려주지 않는다."""
    state = ctx.state(cid)
    stage = state.stage("s3r")
    gate = state.gate("G3")
    if stage.status != "APPROVED" or not stage.currentRev or gate.status != "APPROVED":
        return None
    path = ctx.character_dir(cid) / "s3r-refs" / stage.currentRev / "reference-set.json"
    refs = validate("reference-set-v1", json.loads(path.read_text("utf-8")))
    if refs.characterId != cid or refs.refRev != stage.currentRev:
        raise CheckFailed("s3r", ["reference-set의 characterId 또는 refRev가 상태와 다르다"])
    return refs if refs.planRev == gate.rev else None
