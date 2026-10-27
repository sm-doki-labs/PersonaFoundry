"""G1 다시 만들기: 고칠 점 메모로 얼굴 미리보기만 새 rf<k>에 다시 만든다(D-0043 (2)).

직전 G1이 `REQUEST_CHANGES`일 때만 돈다. 순위·인물·특징·보고서는 직전 rf에서 바이트 그대로
가져오고(`carried-from.json`에 해시를 남긴다), Scout를 다시 부르지 않는다. 같은 특징·군집이므로
외모군 ID와 공통 특징은 그대로이고 얼굴만 새로 만든다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import (
    CheckFailed,
    FactoryError,
    ImageGenerationError,
    NameLeakError,
)
from character_factory_poc.common.names import find_name_leaks
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_bytes,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.reference import RankingPeople, ReferenceReport
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s1_reference.features import load_vocab
from character_factory_poc.stages.s1_reference.page import render_g1_page
from character_factory_poc.stages.s1_reference.preview import generate_previews
from character_factory_poc.stages.s1_reference.ranking import all_names, load_ranking
from character_factory_poc.stages.s1_reference.run import s1_config

CARRIED = ("ranking.json", "people.json", "features.json", "report.json")


def _last_request(ctx: Context, cid: str) -> tuple[str, str]:
    """직전 G1의 (rev, 고칠 점 메모). REQUEST_CHANGES가 아니면 거절한다."""
    g = ctx.state(cid).gate("G1")
    if g.status == "AWAITING_HUMAN":
        raise FactoryError(
            f"{cid}: G1 결정이 아직 없다. 얼굴을 고르거나 REQUEST_CHANGES와 고칠 점 메모를 "
            "기록한 뒤 cfp ref faces를 쓴다"
        )
    if not g.rev or not g.recordRef:
        raise FactoryError(f"{cid}: G1 기록이 없다. 먼저 cfp ref run으로 얼굴 후보를 만든다")
    rec = read_json(ctx.character_dir(cid) / g.recordRef)
    if rec.get("decision") != "REQUEST_CHANGES":
        raise FactoryError(
            f"{cid}: 얼굴 다시 만들기는 직전 G1이 REQUEST_CHANGES일 때만 돈다"
            f"(현재 {rec.get('decision')}). 범위·순위 목록을 바꾸려면 cfp ref run을 다시 돈다"
        )
    note = str(rec.get("reasons") or rec.get("note") or "").strip()
    if not note:
        raise FactoryError(f"{cid}: G1 REQUEST_CHANGES 기록에 고칠 점 메모가 없다")
    return g.rev, note


def _report(ctx: Context, cid: str, rev: str) -> tuple[Path, ReferenceReport]:
    rev_dir = ctx.character_dir(cid) / "s1-reference" / rev
    report = validate("reference-report-v2", read_json(rev_dir / "report.json"))
    return rev_dir, report  # type: ignore[return-value]


def plan_calls(ctx: Context, cid: str) -> list[CallPlan]:
    cfg = s1_config(ctx)
    prev, note = _last_request(ctx, cid)
    _, report = _report(ctx, cid, prev)
    per = int(cfg["previews_per_cluster"])
    n = len(report.candidates) * per
    return [
        CallPlan(
            "s1",
            f"같은 특징·군집으로 얼굴 미리보기 {n}장 다시 만들기(Scout 호출 없음, 메모: {note})",
            n,
        )
    ]


def run_faces(ctx: Context, cid: str) -> Path:
    cfg = s1_config(ctx)
    prev_rev, note = _last_request(ctx, cid)
    prev_dir, report = _report(ctx, cid, prev_rev)
    ctx.budget().check_plan(plan_calls(ctx, cid))
    char_dir = ctx.character_dir(cid)
    rev = next_rev(char_dir / "s1-reference", "rf")
    rev_dir = char_dir / "s1-reference" / rev
    state = ctx.state(cid)
    state.transition("s1", "RUNNING", rev=rev)
    try:
        _run(ctx, cid, rev, rev_dir, prev_dir, prev_rev, report, cfg, note)
    except (CheckFailed, NameLeakError, ImageGenerationError) as e:
        ctx.state(cid).transition("s1", "CHECK_FAILED", rev=rev, error=str(e))
        raise
    state = ctx.state(cid)
    state.transition("s1", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G1", "AWAITING_HUMAN", rev, None)
    return rev_dir


def _run(
    ctx: Context,
    cid: str,
    rev: str,
    rev_dir: Path,
    prev_dir: Path,
    prev_rev: str,
    report: ReferenceReport,
    cfg: dict[str, Any],
    note: str,
) -> None:
    names = all_names(load_ranking(read_json(prev_dir / "ranking.json")))
    people: RankingPeople = validate(  # type: ignore[assignment]
        "ranking-people-v1", read_json(prev_dir / "people.json")
    )
    vocab = load_vocab()

    carried: dict[str, str] = {}
    for name in CARRIED:
        data = (prev_dir / name).read_bytes()
        write_once_bytes(rev_dir / name, data)
        carried[name] = sha256_file(rev_dir / name)
    write_once_json(
        rev_dir / "carried-from.json",
        {"fromRev": prev_rev, "files": carried, "note": note},
    )

    previews = generate_previews(
        image_model=ctx.image_model(cid, ctx.budget()),
        subject_id=cid,
        rev=rev,
        rev_dir=rev_dir,
        report=report,
        vocab=vocab,
        names=names,
        per_cluster=int(cfg["previews_per_cluster"]),
        size=str(cfg["image_size"]),
        revision_note=note,
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
