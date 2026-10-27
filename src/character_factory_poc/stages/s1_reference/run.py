"""S1 실행 (명세 §8, LLD §8.1). cfp ref run과 cfp run --ranking의 진입점."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.errors import CheckFailed, ImageGenerationError, NameLeakError
from character_factory_poc.common.names import find_name_leaks
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    write_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.reference import ReferenceReport, ReportSettings
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s1_reference.features import (
    check_features,
    contract_example,
    load_vocab,
    scout_people_input,
)
from character_factory_poc.stages.s1_reference.page import render_g1_page
from character_factory_poc.stages.s1_reference.preview import generate_previews
from character_factory_poc.stages.s1_reference.ranking import (
    all_names,
    build_people,
    load_ranking,
    ranking_sha,
)
from character_factory_poc.stages.s1_reference.report import build_report

# D-0018·D-0043 제안값. factory.toml [stages.s1]로 바꾼다. G1은 외모군마다 얼굴 한 장을 견준다.
DEFAULTS: dict[str, Any] = {
    "cluster_k": 4,
    "min_members_per_cluster": 3,
    "min_common_fields": 2,
    "previews_per_cluster": 1,
    "max_check_retries": 3,
    "image_size": "1024x1024",
    "min_list_size_for_percentile": 3,
}


def s1_config(ctx: Context) -> dict[str, Any]:
    return DEFAULTS | ctx.config.stage("s1")


def settings_from(cfg: dict[str, Any]) -> ReportSettings:
    return ReportSettings(
        clusterK=int(cfg["cluster_k"]),
        minMembers=int(cfg["min_members_per_cluster"]),
        minCommonFields=int(cfg["min_common_fields"]),
        previewsPerCluster=int(cfg["previews_per_cluster"]),
        minListSizeForPercentile=int(cfg["min_list_size_for_percentile"]),
    )


IMAGE_NOTES = {
    "codex_image": "ChatGPT 구독 한도 사용, API 과금 없음, 장당 약 30초(D-0019)",
    "fake": "가짜 단색 PNG, 호출 비용 없음",
}


def plan_calls(cfg: dict[str, Any], image_adapter: str = "fake") -> list[CallPlan]:
    retries = int(cfg["max_check_retries"])
    k, n = int(cfg["cluster_k"]), int(cfg["previews_per_cluster"])
    note = IMAGE_NOTES.get(image_adapter, image_adapter)
    return [
        CallPlan("s1", f"Scout 외모 특징 태깅 (재시도 포함 최대 {1 + retries}회)", 1 + retries),
        CallPlan("s1", f"외모군 미리보기 이미지 (후보 최대 {k}개 × {n}장, {note})", k * n),
    ]


def describe_ranking(obj: Any) -> str:
    """dry run용 요약. 순위 목록을 검증하고 인물 수를 센다. 이름은 출력하지 않는다."""
    ranking = load_ranking(obj)
    people = build_people(ranking, int(DEFAULTS["min_list_size_for_percentile"]))
    total = sum(len(x.entries) for x in ranking.lists)
    s = ranking.scope
    lines = [
        f"비교 범위: {s.characterGender} · {s.ageRange} · {s.artStyle} · "
        f"인물 인상 {s.appearanceOrigin}",
        f"순위 목록 {len(ranking.lists)}개, 항목 {total}개, 인물 {len(people.people)}명",
    ]
    for x in ranking.lists:
        lines.append(f"  {x.listId}: {x.category} · {x.period} · {len(x.entries)}명 ({x.source})")
    return "\n".join(lines)


REPORT_CONTRACT = "reference-report-v2"


def _previous(char_dir: Path, rev: str) -> tuple[str, ReferenceReport | None] | None:
    """가장 가까운 이전 rev의 보고서. 옛 계약이면 (rev, None)으로 비교만 건너뛴다(D-0021)."""
    for j in range(int(rev[2:]) - 1, 0, -1):
        p = char_dir / "s1-reference" / f"rf{j}" / "report.json"
        if p.exists():
            obj = json.loads(p.read_text("utf-8"))
            if obj.get("schemaVersion") != REPORT_CONTRACT:
                return f"rf{j}", None
            return f"rf{j}", validate(REPORT_CONTRACT, obj)  # type: ignore[return-value]
    return None


def run_s1(ctx: Context, cid: str, ranking_obj: Any) -> Path:
    cfg = s1_config(ctx)
    settings = settings_from(cfg)
    ranking = load_ranking(ranking_obj)  # 형식이 틀리면 아무것도 쓰지 않는다(LLD §10)
    budget = ctx.budget()
    budget.check_plan(plan_calls(cfg, ctx.config.provider("image").adapter))
    char_dir = ctx.character_dir(cid)
    rev = next_rev(char_dir / "s1-reference", "rf")
    rev_dir = char_dir / "s1-reference" / rev
    ctx.state(cid).transition("s1", "RUNNING", rev=rev)
    try:
        _run(ctx, cid, rev, rev_dir, ranking, cfg, settings, budget)
    except (CheckFailed, NameLeakError, ImageGenerationError) as e:
        ctx.state(cid).transition("s1", "CHECK_FAILED", rev=rev, error=str(e))
        raise
    state = ctx.state(cid)
    state.transition("s1", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G1", "AWAITING_HUMAN", rev, None)
    return rev_dir


def _run(ctx, cid, rev, rev_dir, ranking, cfg, settings, budget) -> None:
    names = all_names(ranking)
    people = build_people(ranking, settings.minListSizeForPercentile)
    write_once_json(rev_dir / "ranking.json", dump(ranking))
    write_once_json(rev_dir / "people.json", dump(people))

    vocab = load_vocab()
    people_in = scout_people_input(people)
    spec = AgentSpec(
        role="scout",
        output_contract="appearance-features-v1",
        stage="s1",
        max_check_retries=int(cfg["max_check_retries"]),
        temperature=0.2,
    )
    result = run_agent(
        spec,
        rev_dir / "workspace",
        {"people": people_in, "vocab": vocab, "scope": dump(ranking.scope)},
        [check_features(people_in, vocab)],
        ctx.text_model(cid, budget),
        ref=f"{cid}/{rev}",
        contract_example=contract_example(people_in, vocab),
        backend=ctx.agent_backend(cid, budget, "s1"),
    )
    if not result.ok:
        raise CheckFailed("s1", result.problems)
    features = result.output
    write_once_json(rev_dir / "features.json", dump(features))

    report = build_report(
        subject_id=cid,
        rev=rev,
        ranking_sha=ranking_sha(ranking),
        features_sha=sha256_of(dump(features)),
        vocab_version=vocab["schemaVersion"],
        scope=ranking.scope,
        settings=settings,
        people=people,
        features=features,
        previous=_previous(ctx.character_dir(cid), rev),
    )
    report_json = dump(report)
    if find_name_leaks(json.dumps(report_json, ensure_ascii=False), names):
        raise NameLeakError("보고서에 순위 목록의 이름이 있다(FR-35)")
    write_once_json(rev_dir / "report.json", report_json)

    previews = generate_previews(
        image_model=ctx.image_model(cid, budget),
        subject_id=cid,
        rev=rev,
        rev_dir=rev_dir,
        report=report,
        vocab=vocab,
        names=names,
        per_cluster=settings.previewsPerCluster,
        size=str(cfg["image_size"]),
    )
    previews_json = [dump(p) for p in previews]
    if find_name_leaks(json.dumps(previews_json, ensure_ascii=False), names):
        raise NameLeakError("미리보기 기록에 순위 목록의 이름이 있다(FR-35)")
    write_once_json(rev_dir / "previews.json", previews_json)
    write_once_text(
        rev_dir / "gate-G1.html",
        render_g1_page(
            subject_id=cid,
            rev=rev,
            report=report,
            previews=previews,
            people=people,
            vocab=vocab,
        ),
    )
    write_manifest(rev_dir)
