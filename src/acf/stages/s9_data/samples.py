"""S9 샘플 작성과 G7a 대기 (LLD §8.8 2단계, D-0044·D-0045).

클러스터마다 인계안을 만들고 같은 인계안으로 샘플을 쓴다. 작성 호출은 예산·원장을 거치고,
차단 검사에 걸리면 같은 입력으로 다시 쓴다(첫 성공을 보존한다). `build`도 이 파일의 배치
작성기를 그대로 쓴다(재료·검사·재시도 규칙이 같아야 한다).
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import Field

from acf.common.budget import CallPlan
from acf.common.canonical import sha256_file, sha256_text
from acf.common.errors import CheckFailed, FactoryError
from acf.common.schema import dump, register, validate
from acf.common.store import (
    read_json,
    write_manifest,
    write_once_bytes,
    write_once_json,
)
from acf.contracts.common import ArtifactRef, Strict
from acf.contracts.dataset import (
    Conversation,
    ConversationChecks,
    DataHandoff,
    DataPlan,
    DataQa,
    DataSample,
    Message,
)
from acf.contracts.persona import PromptPair, TraitSheet
from acf.pipeline.agent import AgentSpec, run_agent
from acf.pipeline.context import Context
from acf.stages.s9_data import checks, page
from acf.stages.s9_data import handoff as handoff_mod
from acf.stages.s9_data import plan as plan_mod
from acf.stages.s9_data.plan import CLUSTERS, S9Config
from acf.stages.s9_data.split import FILE_NAME as SPLIT_FILE_NAMES

WRITER_CONTRACT = "data-writer-output-v1"
_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


class WrittenConversation(Strict):
    skeletonKey: str = ""
    scene: str
    sourceId: str = ""
    messages: list[Message] = Field(min_length=2)


class WriterOutput(Strict):
    conversations: list[WrittenConversation] = Field(min_length=1)


register(WRITER_CONTRACT)(WriterOutput)

CONTRACT_EXAMPLE = {
    "conversations": [
        {
            "skeletonKey": "rainy-bookshop",
            "scene": "비가 그친 저녁, 책방을 닫고 창가에 남아 문자를 주고받는다.",
            "sourceId": "",
            "messages": [
                {"role": "user", "content": "오늘 문 닫았어?"},
                {"role": "assistant", "content": "방금 닫았어.\n아직 창가에 앉아 있어."},
                {"role": "user", "content": "뭐 해?"},
                {"role": "assistant", "content": "시집 한 권 펴 놨는데 한 줄도 안 읽혀."},
            ],
        }
    ]
}

RULES: tuple[str, ...] = (
    "messages는 user와 assistant만 쓴다. user로 시작해 assistant로 끝나고 번갈아 쓴다.",
    "assistant 대사는 캐릭터 한 사람의 말만 쓴다. 상대의 말·행동·감정을 대신 쓰지 않는다.",
    "system은 입력의 system을 그대로 따르고, 새 프롬프트를 만들지 않는다.",
    "scene은 시작 상황 한 문장이다. 다음 전개나 정답을 드러내지 않고 물음표를 넣지 않는다.",
    "SNS 재작성은 원본의 사용자 턴을 글자 그대로 두고 캐릭터 턴만 다시 쓴다. 턴 수는 그대로다.",
    "원본 화자의 직업·나이·관계 사실을 캐릭터 설정으로 옮기지 않는다.",
    "갈등은 회복·덜 풀림·선 긋기로 끝낸다. 관계 위협이나 감정 협박으로 끝내지 않는다.",
    "같은 말끝·같은 사과 문장·같은 시작말을 대화 사이에서 반복하지 않는다.",
)


@dataclass(frozen=True)
class Slot:
    material: str
    source: dict[str, Any] | None = None


@dataclass
class WriteSession:
    ctx: Context
    cid: str
    stage: str
    rev: str
    cluster: str
    system: str
    handoff: DataHandoff
    cfg: S9Config
    examples: list[dict[str, Any]] = field(default_factory=list)
    writer_model: str = ""


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


def _usable_source(msgs: list[dict[str, str]]) -> bool:
    if not 4 <= len(msgs) <= 12 or len(msgs) % 2:
        return False
    if any(not m["content"].strip() for m in msgs):
        return False
    return all(m["role"] == ("user" if i % 2 == 0 else "assistant") for i, m in enumerate(msgs))


def load_sns_sources(path: str, limit: int) -> list[dict[str, Any]]:
    """설정 경로의 후보 대화를 읽기 전용으로 연다. 원문은 저장소에 쓰지 않는다(D-0007)."""
    if not path or limit <= 0:
        return []
    p = Path(path)
    if not p.exists():
        return []
    text = p.read_text("utf-8")
    if text.lstrip().startswith("["):
        rows: list[Any] = json.loads(text)
    else:
        rows = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    out: list[dict[str, Any]] = []
    for obj in rows:
        turns = obj.get("messages") or obj.get("turns") or []
        msgs = [
            {"role": str(t.get("role", "")), "content": str(t.get("content", ""))} for t in turns
        ]
        if not _usable_source(msgs):
            continue
        sid = str(obj.get("conversationId") or obj.get("id") or f"sns-{len(out) + 1:04d}")
        out.append({"sourceId": sid, "turns": msgs})
        if len(out) >= limit:
            break
    return out


def make_slots(
    cfg: S9Config, cluster: str, needed: int, sources: list[dict[str, Any]], start: int = 0
) -> list[Slot]:
    materials = cfg.materials[cluster]
    slots: list[Slot] = []
    source_i = 0
    for k in range(needed):
        material = materials[(start + k) % len(materials)]
        if material == "SNS_REWRITE" and source_i < len(sources):
            slots.append(Slot("SNS_REWRITE", sources[source_i]))
            source_i += 1
        else:
            slots.append(Slot("SYNTH", None))
    return slots


def batch_inputs(
    session: WriteSession, slots: list[Slot], ids: list[str], notes: list[str]
) -> dict[str, Any]:
    return {
        "system": session.system,
        "handoff": dump(session.handoff),
        "batch": {
            "clusterId": session.cluster,
            "count": len(slots),
            "conversationIds": ids,
            "materials": [s.material for s in slots],
            "sources": [
                {"index": i, "sourceId": s.source["sourceId"], "turns": s.source["turns"]}
                for i, s in enumerate(slots)
                if s.source is not None
            ],
            "skeletonRule": "같은 장면 뼈대에서 나온 대화는 같은 skeletonKey를 쓴다",
        },
        "examples": session.examples,
        "reviewNotes": [n for n in notes if n],
    }


def _specs(session: WriteSession, slots: list[Slot]) -> list[checks.ConvSpec]:
    forbidden = tuple(session.handoff.forbidden) + session.cfg.forbidden_phrases
    return [
        checks.ConvSpec(
            cluster_id=session.cluster,
            system=session.system,
            material=s.material,
            source=s.source,
            forbidden=forbidden,
            source_facts=session.cfg.source_facts,
            max_length_tokens=session.cfg.max_length_tokens,
            chars_per_token=session.cfg.chars_per_token,
        )
        for s in slots
    ]


def skeleton_id(cluster: str, slot: Slot, written: dict[str, Any]) -> str:
    if slot.material == "SNS_REWRITE" and slot.source is not None:
        sid = _SAFE.sub("-", str(slot.source.get("sourceId"))).strip("-") or "unknown"
        return f"sns-{sid}"
    key = str(written.get("skeletonKey") or "").strip()
    return "synth-" + sha256_text(f"{cluster}|{key}")[:10]


def assemble(
    session: WriteSession,
    slots: list[Slot],
    ids: list[str],
    written: list[dict[str, Any]],
    request_ref: str,
) -> list[Conversation]:
    specs = _specs(session, slots)
    out: list[Conversation] = []
    for i, (slot, item) in enumerate(zip(slots, written, strict=True)):
        scene = str(item.get("scene") or "").strip()
        system = session.system.rstrip() + "\n\n[SCENE]\n" + scene
        messages = [Message(role=m["role"], content=m["content"]) for m in item["messages"]]
        conv = Conversation(
            conversationId=ids[i],
            clusterId=session.cluster,  # type: ignore[arg-type]
            material=slot.material,  # type: ignore[arg-type]
            skeletonId=skeleton_id(session.cluster, slot, item),
            system=system,
            messages=messages,
            provenance={
                "writerModel": session.writer_model,
                "requestRef": request_ref,
                "sourceRef": str((slot.source or {}).get("sourceId") or ""),
                "editedBy": "model",
            },
        )
        blocking = checks.evaluate(conv, specs[i])
        warnings = (
            [
                "답변/사용자 길이 비율이 2를 넘는다",
            ]
            if _ratio(conv) > 2.0
            else []
        )
        out.append(
            conv.model_copy(
                update={"checks": ConversationChecks(blocking=blocking, warnings=warnings)}
            )
        )
    return out


def _ratio(conv: Conversation) -> float:
    user = sum(len(m.content) for m in conv.messages if m.role == "user")
    reply = sum(len(m.content) for m in conv.messages if m.role == "assistant")
    return reply / user if user else 0.0


def write_batch(
    session: WriteSession, slots: list[Slot], ids: list[str], notes: list[str] | None = None
) -> list[Conversation]:
    """한 배치를 쓴다. 차단 검사 실패는 같은 입력으로 다시 쓰고, 첫 성공을 보존한다."""
    budget = session.ctx.budget()
    model = session.ctx.text_model(session.cid, budget)
    inputs = batch_inputs(session, slots, ids, notes or [""] * len(slots))
    specs = _specs(session, slots)
    problems: list[str] = []
    for attempt in range(1, session.cfg.max_retries + 2):
        workspace = (
            session.ctx.config.root
            / "work"
            / "s9-data"
            / f"{session.rev}-{session.cluster}-{ids[0]}-a{attempt}"
        )
        check = lambda out: checks.batch_problems(  # noqa: E731
            [c.model_dump() for c in out.conversations], specs, session.system
        )
        spec = AgentSpec(
            role="data_writer",
            output_contract=WRITER_CONTRACT,
            stage=session.stage,
            max_check_retries=0,
        )
        result = run_agent(
            spec,
            workspace,
            inputs,
            [check],
            model,
            ref=f"{session.cid}/{session.rev}/{session.cluster}/{ids[0]}#{attempt}",
            contract_example=CONTRACT_EXAMPLE,
            backend=session.ctx.agent_backend(session.cid, budget, session.stage),
        )
        request_ref = f"requests/{session.cluster}-{ids[0]}-a{attempt}.json"
        _write_json(
            request_dir(session) / f"{session.cluster}-{ids[0]}-a{attempt}.json",
            {
                "stage": session.stage,
                "cluster": session.cluster,
                "conversationIds": ids,
                "model": model.model,
                "attempt": attempt,
                "input": inputs,
                "ok": result.ok,
                "problems": result.problems,
            },
        )
        if result.ok:
            written = [c.model_dump() for c in result.output.conversations]
            return assemble(session, slots, ids, written, request_ref)
        problems = result.problems
    stage = session.stage
    raise CheckFailed(stage, [f"{session.cluster}/{ids[0]}: {p}" for p in problems])


def request_dir(session: WriteSession) -> Path:
    return plan_mod.data_dir(session.ctx, session.cid) / session.rev / "requests"


def _run_batches(items: list[Any], fn, concurrency: int) -> list[Any]:
    if concurrency <= 1 or len(items) <= 1:
        return [fn(i, item) for i, item in enumerate(items)]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(fn, i, item) for i, item in enumerate(items)]
        return [f.result() for f in futures]


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def write_conversations(
    session: WriteSession,
    *,
    ids: list[str],
    slots: list[Slot],
    notes: list[str] | None = None,
    rev_dir: Path | None = None,
) -> list[Conversation]:
    """배치로 나눠 쓰고 대화 파일을 남긴다. 반환 순서는 입력 ids 순서와 같다."""
    notes = notes or [""] * len(ids)
    id_chunks = chunked(ids, session.cfg.batch_size)
    slot_chunks = chunked(slots, session.cfg.batch_size)
    pairs = list(zip(id_chunks, slot_chunks, strict=True))

    def one(_i: int, pair) -> list[Conversation]:
        batch_ids, batch_slots = pair
        start = ids.index(batch_ids[0])
        convs = write_batch(session, batch_slots, batch_ids, notes[start : start + len(batch_ids)])
        folder = rev_dir or plan_mod.data_dir(session.ctx, session.cid) / session.rev
        for conv in convs:
            write_once_json(folder / "conversations" / f"{conv.conversationId}.json", dump(conv))
        return convs

    out: list[Conversation] = []
    for convs in _run_batches(pairs, one, session.cfg.concurrency):
        out.extend(convs)
    order = {cid: i for i, cid in enumerate(ids)}
    return sorted(out, key=lambda c: order[c.conversationId])


def load_examples(rev_dir: Path, refs: list[ArtifactRef], limit: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ref in refs[:limit]:
        conv = validate("conversation-v1", read_json(rev_dir / ref.ref))
        out.append({"system": conv.system, "messages": [dump(m) for m in conv.messages]})
    return out


def sample_refs(rev_dir: Path, cluster: str) -> list[ArtifactRef]:
    path = rev_dir / "samples" / f"{cluster}.json"
    if not path.exists():
        return []
    bundle = validate("data-sample-v1", read_json(path))
    return list(bundle.conversations)  # type: ignore[arg-type]


def load_samples(rev_dir: Path, cluster: str) -> list[Conversation]:
    return [
        validate("conversation-v1", read_json(rev_dir / ref.ref))
        for ref in sample_refs(rev_dir, cluster)
    ]


def cluster_qa(rev_dir: Path, cluster: str) -> DataQa | None:
    path = rev_dir / "qa" / f"G7a-{cluster}.json"
    if not path.exists():
        return None
    return validate("data-qa-v2", read_json(path))  # type: ignore[return-value]


def reviews(rev_dir: Path) -> dict[str, DataQa]:
    return {c: qa for c in CLUSTERS if (qa := cluster_qa(rev_dir, c)) is not None}


def requested_changes(rev_dir: Path) -> dict[str, str]:
    path = rev_dir / "requests" / "g7a-changes.json"
    if not path.exists():
        return {}
    obj = json.loads(path.read_text("utf-8"))
    return {str(k): str(v) for k, v in (obj.get("clusters") or {}).items()}


def carry_forward(prev: Path, new: Path, skip_clusters: set[str]) -> None:
    """이전 rev에서 이번 rev로 파일을 복사한다. 다시 쓰는 클러스터의 인계안·샘플은 뺀다."""
    derived = {
        "dataset.json",
        "index.jsonl",
        "frozen.json",
        "manifest.sha256",
        *SPLIT_FILE_NAMES.values(),
    }
    for path in sorted(prev.rglob("*")):
        if not path.is_file() or path.name in derived:
            continue
        rel = path.relative_to(prev)
        head = rel.parts[0]
        if head in {"handoffs", "samples"} and rel.stem in skip_clusters:
            continue
        if head == "qa" and rel.name.startswith("G7a-"):
            cluster = rel.name[len("G7a-") : -len(".json")]
            if cluster in skip_clusters:
                continue
        if head == "requests" and rel.name == "g7a-changes.json":
            continue
        if head == "conversations" and any(f"-{c}-" in rel.name for c in skip_clusters):
            continue
        write_once_bytes(new / rel, path.read_bytes())


def _sample_cluster(
    ctx: Context,
    cid: str,
    *,
    cfg: S9Config,
    rev: str,
    rev_dir: Path,
    plan: DataPlan,
    plan_sha: str,
    pair: PromptPair,
    sheet: TraitSheet,
    cluster: str,
    sources: list[dict[str, Any]],
    memo: str,
) -> None:
    sample_path = rev_dir / "samples" / f"{cluster}.json"
    if sample_path.exists() and not memo:
        return
    handoff_path = rev_dir / "handoffs" / f"{cluster}.json"
    if memo or not handoff_path.exists():
        workspace = ctx.config.root / "work" / "s9-data" / f"{rev}-{cluster}-handoff"
        handoff = handoff_mod.build_handoff(
            ctx,
            cid,
            plan=plan,
            plan_sha=plan_sha,
            cluster_id=cluster,
            pair=pair,
            sheet=sheet,
            workspace=workspace,
            stage="s9s",
            retries=cfg.max_retries,
            memo=memo,
        )
        write_once_json(handoff_path, dump(handoff))
    handoff = validate("data-handoff-v1", read_json(handoff_path))
    count = next(c.sampleSize for c in plan.clusters if c.clusterId == cluster)
    slots = make_slots(cfg, cluster, count, sources)
    ids = [f"{rev}-{cluster}-s{i:03d}" for i in range(count)]
    session = WriteSession(
        ctx=ctx,
        cid=cid,
        stage="s9s",
        rev=rev,
        cluster=cluster,
        system=pair.short.text,
        handoff=handoff,  # type: ignore[arg-type]
        cfg=cfg,
        examples=[],
        writer_model=ctx.config.provider("text").model or ctx.config.provider("text").adapter,
    )
    convs = write_conversations(session, ids=ids, slots=slots, rev_dir=rev_dir)
    write_once_json(
        sample_path,
        dump(
            DataSample(
                characterId=cid,
                planSha256=plan_sha,
                clusterId=cluster,  # type: ignore[arg-type]
                handoffSha256=sha256_file(handoff_path),
                conversations=[
                    ArtifactRef(
                        ref=f"conversations/{c.conversationId}.json",
                        sha256=sha256_file(rev_dir / "conversations" / f"{c.conversationId}.json"),
                    )
                    for c in convs
                ],
            )
        ),
    )


def _write_pages(ctx: Context, cid: str, rev: str, rev_dir: Path, plan: DataPlan) -> None:
    rows = [dump(c) for c in plan.clusters]
    pages: dict[str, str] = {}
    for c in plan.clusters:
        convs = load_samples(rev_dir, c.clusterId)
        if not convs:
            continue
        handoff = validate(
            "data-handoff-v1", read_json(rev_dir / "handoffs" / f"{c.clusterId}.json")
        )
        html = page.render_g7a_cluster(
            subject_id=cid,
            rev=rev,
            cluster=c,
            handoff=handoff,  # type: ignore[arg-type]
            conversations=convs,
            sample_sha=sha256_file(rev_dir / "samples" / f"{c.clusterId}.json"),
        )
        name = f"gate-G7a-{c.clusterId}.html"
        (rev_dir / name).write_text(html, encoding="utf-8")
        pages[c.clusterId] = name
    index = page.render_g7a_index(subject_id=cid, rev=rev, plan_rows=rows, pages=pages)
    (rev_dir / "gate-G7a.html").write_text(index, encoding="utf-8")


def _close_gate(ctx: Context, cid: str, rev: str, rev_dir: Path, plan: DataPlan) -> Path:
    state = ctx.state(cid)
    state.set_gate("G7a", "APPROVED", rev, None)
    if state.stage("s9s").status == "AWAITING_HUMAN":
        state.transition("s9s", "APPROVED", rev=rev)
    write_manifest(rev_dir)
    return rev_dir


def plan_calls(ctx: Context, cid: str, cfg: S9Config | None = None) -> list[CallPlan]:
    cfg = cfg or plan_mod.s9_config(ctx)
    clusters = len(CLUSTERS)
    handoffs = handoff_mod.plan_calls(clusters, cfg.max_retries)
    batches = sum(-(-cfg.sample_size // cfg.batch_size) for _ in CLUSTERS)
    writer = CallPlan(
        "s9s",
        f"클러스터별 샘플 {cfg.sample_size}개 × {clusters} (배치 {cfg.batch_size}, "
        f"재시도 포함 최대 {1 + cfg.max_retries}회)",
        batches * (1 + cfg.max_retries),
    )
    return handoffs + [writer]


def run_samples(ctx: Context, cid: str) -> Path:
    """`acf data samples`: 인계안·샘플을 쓰고 G7a 대기로 둔다."""
    state = ctx.state(cid)
    state.require_deps("s9s")
    cfg = plan_mod.s9_config(ctx)
    pair, _pair_path = plan_mod.load_prompt_pair(ctx, cid)
    sheet, _sheet_path = plan_mod.load_trait_sheet(ctx, cid)
    st = state.stage("s9s")
    data_root = plan_mod.data_dir(ctx, cid)

    if state.gate("G7a").status == "APPROVED" and st.currentRev:
        return data_root / st.currentRev
    if st.status == "AWAITING_HUMAN":
        rev = st.currentRev
        if not rev:
            raise FactoryError(f"{cid}: s9s가 대기 상태인데 revision이 없다")
        rev_dir = data_root / rev
        plan = plan_mod.load_plan(rev_dir / "plan.json")
        if len(reviews(rev_dir)) == len(CLUSTERS):
            return _close_gate(ctx, cid, rev, rev_dir, plan)
        raise FactoryError(
            f"{cid}: G7a 검토가 진행 중이다. 남은 클러스터를 판정하거나 REQUEST_CHANGES를 기록한다"
        )

    carry_from = data_root / st.currentRev if st.status == "REJECTED" and st.currentRev else None
    if carry_from is not None and not (carry_from / "plan.json").exists():
        carry_from = None
    memo_by_cluster = requested_changes(carry_from) if carry_from else {}

    if carry_from is None and st.currentRev and (data_root / st.currentRev / "plan.json").exists():
        rev = st.currentRev
    else:
        rev = plan_mod.new_rev(ctx, cid)
    rev_dir = data_root / rev
    if carry_from is not None and carry_from != rev_dir:
        carry_forward(carry_from, rev_dir, set(memo_by_cluster))
    if not (rev_dir / "plan.json").exists():
        plan = plan_mod.build_plan(ctx, cid)
        write_once_json(rev_dir / "plan.json", dump(plan))
    plan = plan_mod.load_plan(rev_dir / "plan.json")
    plan_sha = sha256_file(rev_dir / "plan.json")

    state.transition("s9s", "RUNNING", rev=rev)

    sns = load_sns_sources(cfg.sns_path, cfg.sns_limit)
    try:
        for c in plan.clusters:
            sources = sns if "SNS_REWRITE" in cfg.materials[c.clusterId] else []
            _sample_cluster(
                ctx,
                cid,
                cfg=cfg,
                rev=rev,
                rev_dir=rev_dir,
                plan=plan,
                plan_sha=plan_sha,
                pair=pair,
                sheet=sheet,
                cluster=c.clusterId,
                sources=sources,
                memo=memo_by_cluster.get(c.clusterId, ""),
            )
    except CheckFailed as e:
        state.transition("s9s", "CHECK_FAILED", rev=rev, error=str(e)[:500])
        raise
    _write_pages(ctx, cid, rev, rev_dir, plan)
    write_manifest(rev_dir)
    state.transition("s9s", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G7a", "AWAITING_HUMAN", rev, None)
    return rev_dir
