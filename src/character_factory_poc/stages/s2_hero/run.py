"""S2 기준 사진 (명세 §3, LLD §8.2, D-0042·D-0043). cfp hero run과 cfp run의 s2 진입점.

사람 관문이 없다. `base_photo = "picked"`면 G1에서 고른 얼굴을 그대로 기준 이미지로 고정하고
이미지·판정 호출 없이 `s2`를 `APPROVED`로 둔다. `generate`(기준 사진 생성 + identity-v1
동일인 검사)는 이번 PoC 범위 밖이므로 실행 전에 거절한다(K-0034).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import CheckFailed, FactoryError, NameLeakError
from character_factory_poc.common.names import find_name_leaks
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    write_manifest,
    write_once_bytes,
    write_once_json,
)
from character_factory_poc.contracts.reference import ReferencePreview, ReferenceReport
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s1_reference.approve import (
    load_report,
    selected_cluster,
    selected_references,
)
from character_factory_poc.stages.s1_reference.features import load_vocab
from character_factory_poc.stages.s1_reference.page import summary
from character_factory_poc.stages.s1_reference.ranking import all_names, load_ranking
from character_factory_poc.stages.s2_hero.approve import FORBIDDEN, description_en
from character_factory_poc.stages.s2_hero.prompt import build_hero_prompt

# D-0043 (6): generate가 문서상 기본값이지만 이번 PoC는 picked만 구현했다. factory.example.toml은
# picked를 쓴다. [stages.s2]로 바꾼다.
DEFAULTS: dict[str, Any] = {"base_photo": "generate", "image_size": "1024x1024"}
BASE_PHOTOS = {"generate", "picked"}
PICKED_NOTE = (
    "picked: G1에서 고른 얼굴을 기준 이미지로 그대로 쓴다(이미지·판정 호출 없음, D-0043 (6))"
)


def s2_config(ctx: Context) -> dict[str, Any]:
    cfg = DEFAULTS | ctx.config.stage("s2")
    mode = str(cfg["base_photo"])
    if mode not in BASE_PHOTOS:
        raise FactoryError(f'[stages.s2] base_photo는 "picked" 또는 "generate"다: {mode!r}')
    cfg["base_photo"] = mode
    return cfg


def plan_calls(cfg: dict[str, Any], faces: int = 1) -> list[CallPlan]:
    """dry run용 호출 계획. picked는 호출이 0회다(D-0043 (6))."""
    if str(cfg["base_photo"]) == "picked":
        return [
            CallPlan(
                "s2",
                f"G1 얼굴 {faces}장을 기준 이미지로 고정(picked): 이미지·판정 호출 없음",
                0,
            )
        ]
    return [
        CallPlan(
            "s2",
            'base_photo = "generate"는 이번 PoC 범위 밖이다(K-0034). '
            '실행하면 아무것도 쓰기 전에 거절하고 [stages.s2] base_photo = "picked"를 안내한다',
            0,
        )
    ]


def _require_picked(cfg: dict[str, Any]) -> None:
    if str(cfg["base_photo"]) == "picked":
        return
    raise FactoryError(
        'S2 [stages.s2] base_photo = "generate"(기준 사진 생성 + identity-v1 동일인 검사)는 '
        "이번 PoC 범위 밖이다(K-0034). 아무것도 쓰지 않고 멈춘다. "
        'factory.toml에 [stages.s2] base_photo = "picked"를 넣어 G1에서 고른 얼굴을 '
        "기준 이미지로 그대로 쓴다."
    )


def run_s2(ctx: Context, cid: str) -> Path:
    cfg = s2_config(ctx)
    _require_picked(cfg)
    state = ctx.state(cid)
    state.require_deps("s2")  # G1 승인 필요
    cluster = selected_cluster(ctx, cid)
    refs = selected_references(ctx, cid)
    if len(refs) != 1:
        raise FactoryError(
            f"{cid}: S2는 G1에서 고른 얼굴 정확히 한 장이 필요하다(현재 {len(refs)}장). "
            f"cfp gate import {cid} G1 --answer answer.json으로 얼굴 한 장을 고른다(D-0042)"
        )
    ctx.budget().check_plan(plan_calls(cfg, len(refs)))
    char_dir = ctx.character_dir(cid)
    rf = state.gate("G1").rev or ""
    rev = next_rev(char_dir / "s2-hero", "ar")
    rev_dir = char_dir / "s2-hero" / rev
    state.transition("s2", "RUNNING", rev=rev)
    try:
        _picked(ctx, cid, rev, rev_dir, rf, cluster, refs[0])
    except (CheckFailed, NameLeakError) as e:
        ctx.state(cid).transition("s2", "CHECK_FAILED", rev=rev, error=str(e))
        raise
    # 사람 관문 없이 고정한다(D-0042). 관문 기록은 만들지 않는다.
    ctx.state(cid).transition("s2", "APPROVED", rev=rev)
    return rev_dir


def _picked(
    ctx: Context,
    cid: str,
    rev: str,
    rev_dir: Path,
    rf: str,
    cluster,
    face: tuple[ReferencePreview, Path],
) -> None:
    """G1 얼굴을 그대로 기준 이미지로 고정하고 외모 명세를 쓴다."""
    preview, src = face
    s1_dir = ctx.character_dir(cid) / "s1-reference" / rf
    report: ReferenceReport = load_report(s1_dir)
    names = all_names(load_ranking(json.loads((s1_dir / "ranking.json").read_text("utf-8"))))
    vocab = load_vocab()

    rel = f"references/{preview.previewId}.png"
    prompt = build_hero_prompt(cluster, report.scope, vocab, has_references=True)
    if find_name_leaks(prompt, names):
        raise NameLeakError("S2 프롬프트에 순위 목록의 이름이 있다. 쓰기 전에 멈췄다(FR-35)")
    write_once_bytes(rev_dir / rel, src.read_bytes())
    ref_item = {"id": preview.previewId, "path": rel, "sha256": sha256_file(rev_dir / rel)}
    inputs = validate(
        "hero-inputs-v1",
        {
            "sourceReferenceRev": rf,
            "clusterId": cluster.clusterId,
            "commonTags": cluster.commonTags,
            "scope": dump(report.scope),
            "referencePreviews": [ref_item],
            "basePhoto": "picked",
        },
    )
    write_once_json(rev_dir / "inputs.json", dump(inputs))

    spec = validate(
        "appearance-spec-v1",
        {
            "characterId": cid,
            "appearanceRev": rev,
            "sourceReferenceRev": rf,
            "clusterId": cluster.clusterId,
            "scope": dump(report.scope),
            "tags": cluster.commonTags,
            "descriptionKo": summary(cluster.commonTags, vocab),
            "descriptionEn": description_en(cluster.commonTags, vocab),
            "referenceImage": ref_item,
            "referencePreviews": [ref_item],
            "heroPrompt": prompt,
            "forbidden": FORBIDDEN,
            "notes": PICKED_NOTE,
            "basePhoto": "picked",
            "identityCheck": {
                "rubric": "identity-v1",
                "status": "SKIPPED",
                "attempts": 0,
                "report": "",
            },
        },
    )
    if find_name_leaks(json.dumps(dump(spec), ensure_ascii=False), names):
        raise NameLeakError("외모 명세에 순위 목록의 이름이 있다(FR-35)")
    write_once_json(rev_dir / "appearance-spec.json", dump(spec))
    write_manifest(rev_dir)
