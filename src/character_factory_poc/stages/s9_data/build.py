"""S9 대량 작성·검사·분할·G7 (LLD §8.8 3~6단계).

G7a에서 채택한 샘플은 그대로 두고, 나머지는 같은 인계안과 채택 샘플을 예시로 쓴다. 차단 검사에
걸린 대화는 같은 입력으로 다시 쓰고, 데이터셋 전체 반복 검사에서 걸린 대화는 메모를 붙여
한 번 더 쓴다. 끝까지 실패하면 G7을 열지 않고 CHECK_FAILED로 멈춘다.

창작 인물 정책(D-0078) 계획이면 long 턴 범위 위반도 재작성 대상이고, 분할 뒤 보호 클러스터
생존을 확인해 모자라면 CHECK_FAILED로 멈춘다. 턴 분포·클러스터 비율은 보고서와 G7 페이지에
관측값·목표·판정으로 남기고 경고로만 센다(`policy.py`).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import read_json, write_manifest, write_once_json
from character_factory_poc.contracts.dataset import Conversation, DataQa, DatasetRev
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s9_data import checks, deck, page, split
from character_factory_poc.stages.s9_data import plan as plan_mod
from character_factory_poc.stages.s9_data import policy as policy_mod
from character_factory_poc.stages.s9_data import samples as writer
from character_factory_poc.stages.s9_data import training_prompt as tp_mod
from character_factory_poc.stages.s9_data.plan import S9Config


def _load_index(rev_dir: Path) -> list[dict[str, Any]]:
    path = rev_dir / "index.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]


def _g7_changes(rev_dir: Path) -> dict[str, str]:
    path = rev_dir / "requests" / "g7-changes.json"
    if not path.exists():
        return {}
    obj = json.loads(path.read_text("utf-8"))
    return {str(k): str(v) for k, v in (obj.get("conversations") or {}).items()}


def _carried(ctx: Context, cid: str, rev_dir: Path) -> list[Conversation]:
    return [
        validate("conversation-v1", read_json(rev_dir / row["path"]))  # type: ignore[list-item]
        for row in _load_index(rev_dir)
    ]


def _examples(convs: list[Conversation], limit: int = 3) -> list[dict[str, Any]]:
    return [{"system": c.system, "messages": [dump(m) for m in c.messages]} for c in convs[:limit]]


def _generate(
    ctx: Context,
    cid: str,
    *,
    cfg: S9Config,
    rev: str,
    rev_dir: Path,
    pair,
    cluster: str,
    handoff,
    need: int,
    kept: list[Conversation],
    notes: list[str],
    sources: list[dict[str, Any]],
    round_no: int,
    turn_rule=None,
) -> list[Conversation]:
    to_make = need - len(kept)
    if to_make <= 0:
        return []
    handoff_model = validate("data-handoff-v1", dump(handoff))
    slots = writer.make_slots(cfg, cluster, to_make, sources)
    label = "r" if round_no else "b"
    ids = [f"{rev}-{cluster}-{label}{round_no}{i:03d}" for i in range(to_make)]
    session = writer.WriteSession(
        ctx=ctx,
        cid=cid,
        stage="s9",
        rev=rev,
        cluster=cluster,
        system=pair.short.text,
        handoff=handoff_model,  # type: ignore[arg-type]
        cfg=cfg,
        examples=_examples(kept),
        writer_model=deck.writer_model(ctx),
        turn_rule=turn_rule,
        training=tp_mod.ensure(rev_dir, pair),
    )
    batch_notes = (notes + [""] * to_make)[:to_make]
    return writer.write_conversations(
        session, ids=ids, slots=slots, notes=batch_notes, rev_dir=rev_dir
    )


def plan_calls(ctx: Context, cid: str, cfg: S9Config | None = None) -> list[CallPlan]:
    cfg = cfg or plan_mod.s9_config(ctx)
    plan = _plan_or_default(ctx, cid)
    need = split.needed(plan, cfg)
    total = sum(need.values())
    batches = sum(-(-need[c] // cfg.batch_size) for c in need)
    if deck.enabled(ctx):
        return deck.batch_plan("s9", batches)
    return [
        CallPlan(
            "s9",
            f"대량 작성 최대 {total}대화 (배치 {cfg.batch_size}, 재시도 포함 최대 "
            f"{1 + cfg.max_retries}회, 동시 {cfg.concurrency})",
            batches * (1 + cfg.max_retries),
        )
    ]


def _plan_or_default(ctx: Context, cid: str):
    rev_dir = plan_mod.latest_rev(ctx, cid)
    if rev_dir is not None and (rev_dir / "plan.json").exists():
        return plan_mod.load_plan(rev_dir / "plan.json")
    return plan_mod.build_plan(ctx, cid)


def run_build(ctx: Context, cid: str) -> Path:
    state = ctx.state(cid)
    state.require_deps("s9")
    cfg = plan_mod.s9_config(ctx)
    gate_a = state.gate("G7a")
    data_root = plan_mod.data_dir(ctx, cid)
    sample_dir = data_root / str(gate_a.rev)
    if not (sample_dir / "plan.json").exists():
        raise FactoryError(f"{cid}: G7a revision의 plan.json이 없다({sample_dir})")
    deck.pin(ctx, sample_dir)
    plan = plan_mod.load_plan(sample_dir / "plan.json")
    plan_sha = sha256_file(sample_dir / "plan.json")
    qa = writer.reviews(sample_dir)
    cluster_ids = [c.clusterId for c in plan.clusters]
    if len(qa) < len(cluster_ids):
        raise FactoryError(f"{cid}: G7a에서 모든 클러스터를 승인해야 한다(기록 {sorted(qa)})")
    st = state.stage("s9")
    if st.status == "AWAITING_HUMAN" and st.currentRev:
        return data_root / st.currentRev
    if st.status == "APPROVED" and st.currentRev:
        return data_root / st.currentRev
    if (
        st.status == "RUNNING"
        and st.currentRev
        and (data_root / st.currentRev / "dataset.json").exists()
    ):
        # dataset.json까지 쓴 뒤 상태 전이 전에 끊긴 경우: 다시 만들지 않고 그 revision을 쓴다.
        state.transition("s9", "AWAITING_HUMAN", rev=st.currentRev)
        state.set_gate("G7", "AWAITING_HUMAN", st.currentRev, f"gates/G7-{st.currentRev}")
        return data_root / st.currentRev

    carry_from = data_root / st.currentRev if st.status == "REJECTED" and st.currentRev else None
    if carry_from is not None and not (carry_from / "plan.json").exists():
        carry_from = None
    rev = plan_mod.new_rev(ctx, cid) if carry_from else str(gate_a.rev)
    rev_dir = data_root / rev
    if carry_from is not None and carry_from != rev_dir:
        writer.carry_forward(carry_from, rev_dir, set())
    state.transition("s9", "RUNNING", rev=rev)

    need = split.needed(plan, cfg)
    if carry_from is not None:
        flagged = _g7_changes(carry_from)
        carried = [c for c in _carried(ctx, cid, rev_dir) if c.conversationId not in flagged]
    else:
        carried = [c for c in _adopted(sample_dir, qa, cluster_ids) if c.clusterId in cluster_ids]
    anchors = {
        c.clusterId: sorted(x.conversationId for x in carried if x.clusterId == c.clusterId)
        for c in plan.clusters
        if c.policy is not None and c.policy.protected
    }

    sns, sns_stats = writer.read_sns_sources(
        cfg.sns_path, cfg.sns_limit, cfg.sns_window, cfg.corpus_share
    )
    pair = _pair(ctx, cid)
    convs: list[Conversation] = list(carried)
    try:
        for c in plan.clusters:
            cluster = c.clusterId
            kept = [x for x in carried if x.clusterId == cluster]
            handoff = validate(
                "data-handoff-v1", read_json(sample_dir / "handoffs" / f"{cluster}.json")
            )
            notes = _cluster_notes(qa.get(cluster), sample_dir, cluster)
            sources = sns if "SNS_REWRITE" in cfg.materials[cluster] else []
            convs.extend(
                _generate(
                    ctx,
                    cid,
                    cfg=cfg,
                    rev=rev,
                    rev_dir=rev_dir,
                    pair=pair,
                    cluster=cluster,
                    handoff=handoff,
                    need=need[cluster],
                    kept=kept,
                    notes=notes,
                    sources=sources,
                    round_no=0,
                    turn_rule=writer.plan_turn_rule(plan, cluster),
                )
            )
    except CheckFailed as e:
        state.transition("s9", "CHECK_FAILED", rev=rev, error=str(e)[:500])
        raise

    report = _check(ctx, convs, cfg, plan)
    round_no = 1
    try:
        while (
            not deck.enabled(ctx)
            and report.blocking
            and round_no <= min(2, max(1, cfg.max_retries))
        ):
            flagged = set(report.blocking_ids)
            by_id = {c.conversationId: c for c in convs}
            kept = [c for c in convs if c.conversationId not in flagged]
            convs = kept
            for c in plan.clusters:
                cluster = c.clusterId
                blocked = [
                    x for x in flagged if by_id.get(x) is not None and by_id[x].clusterId == cluster
                ]
                if not blocked:
                    continue
                handoff = validate(
                    "data-handoff-v1", read_json(sample_dir / "handoffs" / f"{cluster}.json")
                )
                notes = [
                    item["detail"] for item in report.blocking if item["conversationId"] in blocked
                ]
                convs.extend(
                    _generate(
                        ctx,
                        cid,
                        cfg=cfg,
                        rev=rev,
                        rev_dir=rev_dir,
                        pair=pair,
                        cluster=cluster,
                        handoff=handoff,
                        need=len(blocked) + len([x for x in kept if x.clusterId == cluster]),
                        kept=[x for x in kept if x.clusterId == cluster],
                        notes=notes,
                        sources=sns if "SNS_REWRITE" in cfg.materials[cluster] else [],
                        round_no=round_no,
                        turn_rule=writer.plan_turn_rule(plan, cluster),
                    )
                )
            report = _check(ctx, convs, cfg, plan)
            round_no += 1
    except CheckFailed as e:
        state.transition("s9", "CHECK_FAILED", rev=rev, error=str(e)[:500])
        raise

    if report.blocking:
        _write_report(rev_dir, report, cfg)
        state.transition("s9", "CHECK_FAILED", rev=rev, error="; ".join(report.problems())[:500])
        raise CheckFailed("s9", report.problems())

    approx = {
        c.conversationId: checks.approx_tokens(checks.conversation_text(c), cfg.chars_per_token)
        for c in convs
    }
    result = split.split(convs, plan, cfg, approx)
    preport = policy_mod.evaluate(plan, convs, result.splits["train"], cfg, anchors)
    if preport.blocking:
        report.blocking.extend(preport.blocking)
        report.metrics["blocking"] = len(report.blocking)
        _write_report(rev_dir, report, cfg, extra=preport.body())
        state.transition("s9", "CHECK_FAILED", rev=rev, error="; ".join(report.problems())[:500])
        raise CheckFailed("s9", report.problems())
    used = sum(1 for c in convs if c.material == "SNS_REWRITE")
    sns_stats["used"] = used
    kinds = {s["sourceId"]: s.get("source", "SNS") for s in sns}
    # D-0135: 흐름 뼈대 재작성. 원본과 이어서 같은 가장 긴 글자 수와 뼈대 예시를 남긴다.
    # 원문은 남기지 않는다.
    originals = {s["sourceId"]: checks.source_texts(s) for s in sns}
    rewritten = [c for c in convs if c.material == "SNS_REWRITE"]
    sns_stats["rewrite"] = "SKELETON"
    sns_stats["overlap"] = {
        "limit": checks.OVERLAP_LIMIT,
        "checked": len(rewritten),
        "max": max(
            (
                checks.longest_overlap(
                    [m.content for m in c.messages] + list(c.provenance.flowBeats),
                    originals.get(c.provenance.sourceRef, []),
                )
                for c in rewritten
            ),
            default=0,
        ),
    }
    sample = next((c for c in rewritten if c.provenance.flowBeats), None)
    if sample is not None:
        sns_stats["example"] = {
            "conversationId": sample.conversationId,
            "origin": kinds.get(sample.provenance.sourceRef, "SNS"),
            "beats": list(sample.provenance.flowBeats),
            "messages": len(sample.messages),
            "sourceTurns": len(originals.get(sample.provenance.sourceRef, [])),
        }
    sns_stats["usedBySource"] = dict(
        Counter(
            kinds.get(c.provenance.sourceRef or "", "SNS")
            for c in convs
            if c.material == "SNS_REWRITE"
        )
    )
    sns_warning = writer.source_warning(sns_stats, used)
    if sns_warning:
        result.warnings.append(sns_warning)
    files = split.write_splits(rev_dir, result)
    counts = split.cluster_counts(convs)
    dataset = DatasetRev(
        characterId=cid,
        datasetRev=rev,
        personaVersion=plan.personaVersion,
        planSha256=plan_sha,
        sampleQaRefs=[f"s9-data/{rev}/qa/G7a-{c}.json" for c in sorted(qa)],
        clusterCounts={k: v for k, v in counts.items()},
        files=files,
        blockingFailures=0,
        warnings=len(report.warnings) + len(result.warnings) + len(preport.warnings),
        digest=result.digest,
    )
    write_once_json(rev_dir / "dataset.json", dump(dataset))
    _write_report(
        rev_dir,
        report,
        cfg,
        extra={
            "warnings": result.warnings,
            "approx": approx,
            "sources": sns_stats,
            **preport.body(),
        },
    )
    _write_page(cid, rev, rev_dir, dataset, report, convs, preport)
    write_manifest(rev_dir)
    state.transition("s9", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G7", "AWAITING_HUMAN", rev, None)
    return rev_dir


def _pair(ctx: Context, cid: str):
    pair, _path = plan_mod.load_prompt_pair(ctx, cid)
    return pair


def _adopted(
    sample_dir: Path, qa: dict[str, DataQa], cluster_ids: list[str] | tuple[str, ...]
) -> list[Conversation]:
    out: list[Conversation] = []
    for cluster in cluster_ids:
        record = qa.get(cluster)
        if record is None:
            continue
        for conv in writer.load_samples(sample_dir, cluster):
            if record.verdicts.get(conv.conversationId, "ADOPT") == "ADOPT":
                out.append(conv)
    return out


def _cluster_notes(record: DataQa | None, sample_dir: Path, cluster: str) -> list[str]:
    if record is None:
        return []
    notes: list[str] = []
    for conv in writer.load_samples(sample_dir, cluster):
        verdict = record.verdicts.get(conv.conversationId)
        if verdict in {"FIX", "REJECT"}:
            notes.append(record.notes.get(conv.conversationId, "검토자가 다시 쓰라고 했다"))
    return notes


def _check(ctx: Context, convs: list[Conversation], cfg: S9Config, plan) -> checks.DatasetReport:
    report = checks.dataset_report(
        convs,
        phrase_ngram=cfg.phrase_ngram,
        phrase_max_conversations=cfg.phrase_max_conversations,
        bubble_max_conversations=cfg.bubble_max_conversations,
    )
    items = policy_mod.conversation_items(plan, convs)
    if items:
        report.blocking.extend(items)
        report.metrics["blocking"] = len(report.blocking)
    return report


def _write_report(
    rev_dir: Path,
    report: checks.DatasetReport,
    cfg: S9Config,
    extra: dict[str, Any] | None = None,
) -> None:
    body: dict[str, Any] = {
        "blocking": report.blocking,
        "warnings": report.warnings,
        "metrics": report.metrics,
        "lengthCheck": {
            "approximate": True,
            "charsPerToken": cfg.chars_per_token,
            "maxLengthTokens": cfg.max_length_tokens,
            "note": "토큰화 도구가 없어 글자 수로 근사했다. supervisedTokens는 None이다",
        },
    }
    if extra:
        body.update(extra)
    path = rev_dir / "check-report.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")


def _write_page(
    cid: str,
    rev: str,
    rev_dir: Path,
    dataset: DatasetRev,
    report: checks.DatasetReport,
    convs: list[Conversation],
    preport: policy_mod.PolicyReport | None = None,
) -> None:
    import secrets

    rng = secrets.SystemRandom()
    picked = convs[:] if len(convs) <= 20 else rng.sample(convs, 20)
    counts = [
        {
            "clusterId": k,
            "conversations": v.conversations,
            "replies": v.replies,
            "supervisedTokens": v.supervisedTokens,
        }
        for k, v in sorted(dataset.clusterCounts.items())
    ]
    body = {
        "blocking": report.blocking,
        "warnings": report.warnings,
        "metrics": report.metrics,
        "note": "토큰 수는 글자 수 근사다(supervisedTokens=None)",
    }
    html = page.render_g7_page(
        subject_id=cid,
        dataset=dataset,
        report=body,
        counts=counts,
        samples=picked,
        policy_view=preport.body() if preport is not None else None,
    )
    (rev_dir / "gate-G7.html").write_text(html, encoding="utf-8")
