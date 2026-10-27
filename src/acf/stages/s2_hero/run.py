"""S2 실행 (명세 §3, LLD §8.2). acf hero run과 acf run의 s2 진입점."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from acf.common.budget import CallPlan
from acf.common.canonical import sha256_file
from acf.common.errors import CheckFailed, ImageGenerationError, NameLeakError
from acf.common.names import find_name_leaks
from acf.common.schema import dump, validate
from acf.common.store import (
    next_rev,
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from acf.contracts.hero import HeroCandidate
from acf.pipeline.context import Context
from acf.providers.base import ImageRequest
from acf.stages.s1_reference.approve import load_report, selected_cluster, selected_references
from acf.stages.s1_reference.features import load_vocab
from acf.stages.s1_reference.ranking import all_names, load_ranking
from acf.stages.s1_reference.run import IMAGE_NOTES
from acf.stages.s2_hero.page import render_g2_page
from acf.stages.s2_hero.prompt import NEGATIVE, build_hero_prompt

# D-0023 제안값. factory.toml [stages.s2]로 바꾼다.
DEFAULTS: dict[str, Any] = {"candidates": 4, "image_size": "1024x1024"}


def s2_config(ctx: Context) -> dict[str, Any]:
    return DEFAULTS | ctx.config.stage("s2")


def plan_calls(cfg: dict[str, Any], references: int, image_adapter: str = "fake") -> list[CallPlan]:
    n = int(cfg["candidates"])
    note = IMAGE_NOTES.get(image_adapter, image_adapter)
    return [CallPlan("s2", f"대표 이미지 후보 {n}장 (참조 사진 {references}장, {note})", n)]


def run_s2(ctx: Context, cid: str) -> Path:
    state = ctx.state(cid)
    state.require_deps("s2")  # G1 승인 필요
    cluster = selected_cluster(ctx, cid)
    refs = selected_references(ctx, cid)
    cfg = s2_config(ctx)
    budget = ctx.budget()
    budget.check_plan(plan_calls(cfg, len(refs), ctx.config.provider("image").adapter))
    char_dir = ctx.character_dir(cid)
    rf = state.gate("G1").rev or ""
    rev = next_rev(char_dir / "s2-hero", "ar")
    rev_dir = char_dir / "s2-hero" / rev
    state.transition("s2", "RUNNING", rev=rev)
    try:
        _run(ctx, cid, rev, rev_dir, rf, cluster, refs, cfg, budget)
    except (CheckFailed, NameLeakError, ImageGenerationError) as e:
        ctx.state(cid).transition("s2", "CHECK_FAILED", rev=rev, error=str(e))
        raise
    state = ctx.state(cid)
    state.transition("s2", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G2", "AWAITING_HUMAN", rev, None)
    return rev_dir


def _run(ctx, cid, rev, rev_dir, rf, cluster, refs, cfg, budget) -> None:
    s1_dir = ctx.character_dir(cid) / "s1-reference" / rf
    report = load_report(s1_dir)
    names = all_names(load_ranking(json.loads((s1_dir / "ranking.json").read_text("utf-8"))))
    vocab = load_vocab()

    # 참조 사진을 rev 폴더로 복사해 G2 페이지·manifest가 rev 폴더만으로 닫히게 한다.
    ref_items = []
    for preview, src in refs:
        rel = f"references/{preview.previewId}.png"
        write_once_bytes(rev_dir / rel, src.read_bytes())
        ref_items.append(
            {"id": preview.previewId, "path": rel, "sha256": sha256_file(rev_dir / rel)}
        )
    inputs = validate(
        "hero-inputs-v1",
        {
            "sourceReferenceRev": rf,
            "clusterId": cluster.clusterId,
            "commonTags": cluster.commonTags,
            "scope": dump(report.scope),
            "referencePreviews": ref_items,
        },
    )
    write_once_json(rev_dir / "inputs.json", dump(inputs))

    total = int(cfg["candidates"])
    size = str(cfg["image_size"])
    ref_paths = tuple(str(rev_dir / x["path"]) for x in ref_items)
    prompts = []
    for n in range(1, total + 1):
        prompt = build_hero_prompt(cluster, report.scope, vocab, n, total, bool(ref_paths))
        if find_name_leaks(prompt + " " + NEGATIVE, names):
            raise NameLeakError(
                f"대표 이미지 프롬프트(h{n})에 순위 목록의 이름이 있다. "
                "이미지 호출 전에 멈췄다(FR-35)"
            )
        prompts.append((n, prompt))

    image_model = ctx.image_model(cid, budget)
    candidates: list[HeroCandidate] = []
    for n, prompt in prompts:
        hid = f"h{n}"
        res = image_model.generate(
            ImageRequest(
                stage="s2",
                prompt=prompt,
                ref=f"{cid}/{rev}/{hid}",
                negative_prompt=NEGATIVE,
                size=size,
                reference_images=ref_paths,
            )
        )
        rel = f"candidates/{hid}.png"
        write_once_bytes(rev_dir / rel, res.data)
        candidates.append(
            validate(  # type: ignore[arg-type]
                "hero-candidate-v1",
                {
                    "candidateId": hid,
                    "clusterId": cluster.clusterId,
                    "sourceReferenceRev": rf,
                    "referencePreviews": [x["id"] for x in ref_items],
                    "prompt": prompt,
                    "negativePrompt": NEGATIVE,
                    "model": res.model,
                    "provider": res.provider,
                    "settings": {"size": size, "variation": n},
                    "fileSha256": sha256_file(rev_dir / rel),
                    "filePath": rel,
                },
            )
        )
    cand_json = [dump(c) for c in candidates]
    if find_name_leaks(json.dumps(cand_json, ensure_ascii=False), names):
        raise NameLeakError("대표 이미지 기록에 순위 목록의 이름이 있다(FR-35)")
    write_once_json(rev_dir / "candidates.json", cand_json)
    write_once_text(
        rev_dir / "gate-G2.html",
        render_g2_page(subject_id=cid, rev=rev, inputs=inputs, candidates=candidates, vocab=vocab),
    )
    write_manifest(rev_dir)
