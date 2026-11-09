"""모티브 s0: 출처 묶음 정리 → 출처 정리 에이전트 → G0 대기 (계획 §4, D-0120, D-0128).

결정적 정리(읽기·화자·가리기·대화 나누기·비교 세트 분리·사용 근거)는 코드가 하고, 판단이 필요한 일
(화자 지정 확인, 놓친 개인정보 표시, 대표 메시지, 말투 관찰)은 에이전트가 한다. 에이전트 출력은
코드 검사(없는 메시지·대상 인물이 아닌 메시지·비교 세트 유출)를 통과해야 한다.

비교 세트(holdout.jsonl)는 에이전트 입력과 뒤쪽 단계 입력에 넣지 않는다. s9h만 읽는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import CheckFailed, FactoryError, NeedsInputError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import next_rev, read_json, write_manifest
from character_factory_poc.contracts.source import SourceDigest, SourceIndex, SourcePack, TextStats
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.gates import render_gate_page
from character_factory_poc.pipeline.graph import SOURCE
from character_factory_poc.stages.s0_source import facts, parse

STAGE_DIR = "s0-source"
SETTINGS = {
    "max_agent_messages": 600,
    "max_representative": 12,
    "max_check_retries": 3,
    "max_format_retries": 2,
}


def _settings(ctx: Context) -> dict[str, int]:
    cfg = ctx.config.stage("s0")
    return {k: int(cfg.get(k, v)) for k, v in SETTINGS.items()}


def plan_calls(ctx: Context, *, public: bool = True) -> list[CallPlan]:
    cfg = _settings(ctx)
    n = 1 + cfg["max_check_retries"] + cfg["max_format_retries"]
    return [CallPlan("s0", f"출처 정리 에이전트 (재시도 포함 최대 {n}회)", n)] + (
        [CallPlan("s0", "공인 공개 사실 검색·원문 대조 (최대 2회)", 2, None)] if public else []
    )


def _latest_rev_dir(ctx: Context, cid: str) -> Path | None:
    root = ctx.character_dir(cid) / STAGE_DIR
    revs = sorted(p for p in root.glob("sp*") if p.is_dir()) if root.exists() else []
    return revs[-1] if revs else None


def _load_pack(ctx: Context, cid: str, pack_path: Path | None) -> tuple[SourcePack, dict[str, Any]]:
    """출처 묶음을 읽고 상대 경로를 묶음 파일 기준 절대 경로로 바꾼다."""
    if pack_path is None:
        last = _latest_rev_dir(ctx, cid)
        if last is None or not (last / "source-pack.json").exists():
            raise NeedsInputError(
                "모티브 s0: 출처 묶음이 필요하다(cfp run ... --source-pack pack.json)"
            )
        raw = read_json(last / "source-pack.json")
        return validate("source-pack-v1", raw), raw  # type: ignore[return-value]
    pack_path = Path(pack_path).resolve()
    raw = json.loads(pack_path.read_text("utf-8"))
    base = pack_path.parent
    if isinstance(raw.get("factsPath"), str):
        raw["factsPath"] = str(facts.manual_path(raw["factsPath"], base, ctx.character_dir(cid)))
    for key in ("photos", "texts"):
        for item in raw.get(key, []):
            p = Path(item.get("path", ""))
            item["path"] = str(p if p.is_absolute() else (base / p).resolve())
    pack: SourcePack = validate("source-pack-v1", raw)  # type: ignore[assignment]
    ids = [t.textId for t in pack.texts]
    if len(ids) != len(set(ids)):
        raise CheckFailed("s0", ["texts의 textId가 겹친다"])
    missing = [x.path for x in [*pack.texts, *pack.photos] if not Path(x.path).exists()]
    if missing:
        raise CheckFailed("s0", [f"원문 파일이 없다: {p}" for p in missing])
    return pack, dump(pack)


def _read_all(pack: SourcePack) -> tuple[list[parse.Msg], list[TextStats], dict[str, int]]:
    msgs: list[parse.Msg] = []
    stats: list[TextStats] = []
    masked = {"phone": 0, "email": 0, "account": 0, "participant": 0, "otherParticipants": 0}
    subject_name = pack.subject.displayName
    for spec in pack.texts:
        raw = Path(spec.path).read_text("utf-8")
        try:
            if spec.kind == "KAKAO_EXPORT":
                part = parse.read_kakao(spec.textId, raw)
            elif spec.kind == "ARTICLE":
                part = parse.read_article(spec.textId, raw, spec.date, subject_name)
            else:
                part = parse.read_dialogue(spec.textId, raw, spec.date)
            if not part:
                raise parse.SourceError(f"{spec.textId}: 읽은 메시지가 없다(형식 확인)")
            parse.assign_speakers(part, spec, subject_name)
        except parse.SourceError as e:
            raise CheckFailed("s0", [str(e)]) from None
        for key, n in parse.mask(part).items():
            masked[key] = masked.get(key, 0) + n
        convs = parse.segment(part, spec, pack.holdout.gapHours)
        times = [m.at for m in part if m.at]
        stats.append(
            TextStats(
                textId=spec.textId,
                kind=spec.kind,
                sha256=sha256_file(Path(spec.path)),
                messages=len(part),
                subjectMessages=sum(m.speaker == "SUBJECT" for m in part),
                conversations=convs,
                first=min(times).isoformat(timespec="minutes") if times else None,
                last=max(times).isoformat(timespec="minutes") if times else None,
            )
        )
        msgs.extend(part)
    return msgs, stats, masked


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text("utf-8").splitlines() if line.strip()]


def _agent_sample(rows: list[dict], cap: int) -> list[dict]:
    """에이전트에 줄 표본. 대화를 통째로 고르게 뽑아 cap개를 넘지 않게 한다."""
    if len(rows) <= cap:
        return rows
    convs: dict[str, list[dict]] = {}
    for r in rows:
        convs.setdefault(r["convId"], []).append(r)
    keys = list(convs)
    out: list[dict] = []
    step = max(1, len(keys) // max(1, cap // 8))
    for key in keys[::step]:
        if len(out) + len(convs[key]) > cap:
            break
        out.extend(convs[key])
    return out or rows[:cap]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def digest_check(sample: list[dict], holdout_texts: list[str], max_rep: int):
    """에이전트 출력 검사. API·codex_exec 백엔드가 같은 함수를 쓴다."""
    ids = {r["msgId"] for r in sample}
    subject_ids = {r["msgId"] for r in sample if r["speaker"] == "SUBJECT"}
    leaks = [t for t in (_norm(x) for x in holdout_texts) if len(t) >= 12]
    need = min(3, len(subject_ids))

    def check(d: SourceDigest) -> list[str]:
        problems: list[str] = []
        if not d.speakerCheck.confirmed and not d.speakerCheck.note.strip():
            problems.append("speakerCheck.confirmed가 false면 note에 이유를 적는다")
        for f in d.piiFlags:
            if f.msgId not in ids:
                problems.append(f"piiFlags에 표본에 없는 msgId가 있다: {f.msgId}")
        seen: set[str] = set()
        for r in d.representative:
            if r.msgId not in subject_ids:
                problems.append(f"representative는 대상 인물(SUBJECT) 메시지만 고른다: {r.msgId}")
            if r.msgId in seen:
                problems.append(f"representative msgId가 겹친다: {r.msgId}")
            seen.add(r.msgId)
        if len(d.representative) < need:
            problems.append(f"representative를 {need}개 이상 고른다")
        if len(d.representative) > max_rep:
            problems.append(f"representative는 {max_rep}개 이하로 고른다")
        for o in d.observations:
            if len(o) > 300:
                problems.append("observations 한 줄은 300자 이하로 쓴다")
        written = _norm(
            " ".join(
                [
                    *d.observations,
                    *d.qualityNotes,
                    d.speakerCheck.note,
                    *(r.why for r in d.representative),
                ]
            )
        )
        if any(t in written for t in leaks):
            problems.append("비교 세트 원문이 출력에 들어갔다")
        return problems

    return check


def codex_checks(stage: str, workspace: Path) -> tuple[str, list]:
    """checks.registry가 연결할 진입점. 작업 공간의 입력과 같은 rev의 비교 세트로 검사한다."""
    if stage != "s0":
        raise ValueError(f"출처 정리 검사가 정의되지 않은 단계: {stage}")
    workspace = Path(workspace)
    sample = read_jsonl(workspace / "inputs" / "corpus-sample.jsonl")
    limits = json.loads((workspace / "inputs" / "limits.json").read_text("utf-8"))
    holdout_path = workspace.parent / "holdout.jsonl"
    holdout = [r["text"] for r in read_jsonl(holdout_path)] if holdout_path.exists() else []
    return "source-digest-v1", [digest_check(sample, holdout, limits["max_representative"])]


def _page(
    cid: str,
    rev: str,
    pack: SourcePack,
    index: SourceIndex,
    digest: SourceDigest,
    sample: list[dict],
    reviewed=None,
) -> str:
    by_id = {r["msgId"]: r for r in sample}
    lock = (
        "승인 잠김 — 다음을 채운 출처 묶음으로 다시 돌린다:\n- " + "\n- ".join(index.usageProblems)
        if index.usageProblems
        else "사용 근거가 채워져 있다."
    )
    basis = pack.usageBasis
    sections = [
        ("승인 조건", lock),
        (
            "대상과 사용 근거",
            f"대상: {pack.subject.displayName} ({pack.subject.kind})\n"
            f"사용 범위: {basis.scope or '-'}\n"
            f"동의: {basis.consentBy or '-'} / {basis.consentDate or '-'}\n"
            f"메모: {basis.notes or '-'}",
        ),
        (
            "원문",
            "\n".join(
                f"{t.textId} {t.kind}: 메시지 {t.messages}, 대상 인물 {t.subjectMessages}, "
                f"대화 {t.conversations}, 기간 {t.first or '-'} ~ {t.last or '-'}"
                for t in index.texts
            )
            + f"\n사진 {len(index.photos)}장",
        ),
        (
            "가린 항목과 비교 세트",
            f"가림: {json.dumps(index.masked, ensure_ascii=False)}\n"
            f"비교 세트(학습·프롬프트에 넣지 않음): 대화 {index.holdoutConversations}, "
            f"메시지 {index.holdoutMessages}",
        ),
        (
            "에이전트: 화자 확인",
            ("확인함" if digest.speakerCheck.confirmed else "확인 필요")
            + (f" — {digest.speakerCheck.note}" if digest.speakerCheck.note else ""),
        ),
        (
            "에이전트: 대표 메시지",
            "\n".join(
                f"[{r.category}] {by_id.get(r.msgId, {}).get('text', r.msgId)}  ← {r.why}"
                for r in digest.representative
            )
            or "-",
        ),
        ("에이전트: 말투 관찰", "\n".join(f"- {o}" for o in digest.observations) or "-"),
        (
            "에이전트: 더 가릴 것",
            "\n".join(
                f"{f.msgId}: {f.reason} — {by_id.get(f.msgId, {}).get('text', '')}"
                for f in digest.piiFlags
            )
            or "없음",
        ),
        ("에이전트: 자료 품질", "\n".join(f"- {n}" for n in digest.qualityNotes) or "-"),
    ]
    if reviewed is not None:
        for item in reviewed.items:
            lines = [item.line(), *(f"{s.title} {s.url}" for s in item.sources)]
            if item.selfView:
                q = item.selfView
                lines += [f"본인 시점: {q.paraphrase}", f"원문 {q.msgId}: {q.quote}"]
            if item.excluded:
                lines.append("입력에서 제외됨")
            sections.append((f"공개 사실 · {item.factId}", "\n".join(lines)))
        sections.append(
            (
                "사적인 질문을 넘기는 말",
                "\n".join(
                    [f"{q.msgId}: {q.quote}" for q in reviewed.deflections]
                    + [
                        f"기본 표현: {s}"
                        for s in reviewed.phrases()
                        if s not in {q.quote for q in reviewed.deflections}
                    ]
                ),
            )
        )
    return render_gate_page(
        exclude_ids=[f.factId for f in reviewed.items if not f.excluded] if reviewed else [],
        title=f"G0 출처 확인 · {pack.subject.displayName}",
        subject_id=cid,
        gate="G0",
        rev=rev,
        sections=sections,
    )


def run_s0(ctx: Context, cid: str, pack_path: Path | None = None) -> Path:
    from character_factory_poc.pipeline.origin import read_origin

    if read_origin(ctx.character_dir(cid)) != SOURCE:
        raise FactoryError(f"{cid}: s0은 모티브 캐릭터에만 있다")
    state = ctx.state(cid)
    state.require_deps("s0")
    cfg = _settings(ctx)
    budget = ctx.budget()
    pack, pack_raw = _load_pack(ctx, cid, pack_path)
    budget.check_plan(plan_calls(ctx, public=pack.subject.kind == "PUBLIC_FIGURE"))
    rev = next_rev(ctx.character_dir(cid) / STAGE_DIR, "sp")
    rev_dir = ctx.character_dir(cid) / STAGE_DIR / rev
    rev_dir.mkdir(parents=True, exist_ok=True)
    state.transition("s0", "RUNNING", rev=rev)

    msgs, stats, masked = _read_all(pack)
    corpus, held = parse.split_holdout(msgs, pack.holdout.fraction)
    other = masked.pop("otherParticipants", 0)
    index = SourceIndex(
        characterId=cid,
        sourceRev=rev,
        subjectKind=pack.subject.kind,
        texts=stats,
        photos=[{"path": p.path, "sha256": sha256_file(Path(p.path))} for p in pack.photos],
        corpusMessages=len(corpus),
        corpusSubjectMessages=sum(m.speaker == "SUBJECT" for m in corpus),
        holdoutConversations=len({m.convId for m in held}),
        holdoutMessages=len(held),
        masked=masked,
        otherParticipants=other,
        usageProblems=parse.usage_problems(pack),
    )
    if index.corpusSubjectMessages == 0:
        raise CheckFailed("s0", ["비교 세트를 빼고 나니 대상 인물 메시지가 없다"])
    (rev_dir / "source-pack.json").write_text(
        json.dumps(pack_raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    corpus_rows = [m.as_row() for m in corpus]
    _write_jsonl(rev_dir / "corpus.jsonl", corpus_rows)
    _write_jsonl(rev_dir / "holdout.jsonl", [m.as_row() for m in held])
    (rev_dir / "source-index.json").write_text(
        json.dumps(dump(index), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    sample = _agent_sample(corpus_rows, cfg["max_agent_messages"])
    agent_rows = [{k: r[k] for k in ("msgId", "convId", "at", "speaker", "text")} for r in sample]
    names = sorted({(r["textId"], r["speaker"], r["name"]) for r in corpus_rows})
    inputs = {
        "subject": {"displayName": pack.subject.displayName, "kind": pack.subject.kind},
        "speaker-map": [{"textId": t, "speaker": s, "name": n} for t, s, n in names],
        "corpus-sample.jsonl": "".join(
            json.dumps(r, ensure_ascii=False) + "\n" for r in agent_rows
        ),
        "limits": {"max_representative": cfg["max_representative"]},
    }
    first_subject = next((r["msgId"] for r in agent_rows if r["speaker"] == "SUBJECT"), "")
    example = {
        "schemaVersion": "source-digest-v1",
        "speakerCheck": {"confirmed": True, "note": ""},
        "piiFlags": [],
        "representative": [
            {"msgId": first_subject, "category": "DAILY", "why": "평소 안부를 묻는 방식"}
        ],
        "observations": ["짧은 질문으로 안부를 먼저 묻는다"],
        "qualityNotes": [],
    }
    spec = AgentSpec(
        role="source_curator",
        stage="s0",
        output_contract="source-digest-v1",
        max_check_retries=cfg["max_check_retries"],
        max_format_retries=cfg["max_format_retries"],
    )
    result = run_agent(
        spec,
        rev_dir / "workspace",
        inputs,
        [digest_check(sample, [m.text for m in held], cfg["max_representative"])],
        ctx.text_model(cid, budget),
        ref=f"{cid}/{rev}/s0",
        contract_example=example,
        backend=ctx.agent_backend(cid, budget, "s0"),
    )
    if not result.ok:
        raise CheckFailed("s0", result.problems)
    digest: SourceDigest = result.output
    (rev_dir / "digest.json").write_text(
        json.dumps(dump(digest), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    flagged = {f.msgId for f in digest.piiFlags}
    reviewed = facts.collect_for_gate(
        ctx,
        cid,
        pack,
        rev_dir,
        [r for r in sample if r["msgId"] not in flagged],
        {m.as_row()["msgId"] for m in held},
        budget,
    )
    (rev_dir / "gate-G0.html").write_text(
        _page(cid, rev, pack, index, digest, corpus_rows, reviewed), encoding="utf-8"
    )
    write_manifest(rev_dir)
    state.transition("s0", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G0", "AWAITING_HUMAN", rev, None)
    return rev_dir


def load_approved_source(ctx: Context, cid: str) -> tuple[SourcePack, SourceIndex, list[dict]]:
    """G0 승인된 출처 묶음·통계·정리된 원문(비교 세트 제외). 뒤쪽 단계(s2·s3)가 쓴다."""
    gate = ctx.state(cid).gate("G0")
    if gate.status != "APPROVED" or not gate.rev:
        raise FactoryError(f"{cid}: G0 승인이 필요하다(현재 {gate.status})")
    rev_dir = ctx.character_dir(cid) / STAGE_DIR / gate.rev
    pack = validate("source-pack-v1", read_json(rev_dir / "source-pack.json"))
    index = validate("source-index-v1", read_json(rev_dir / "source-index.json"))
    return pack, index, read_jsonl(rev_dir / "corpus.jsonl")  # type: ignore[return-value]


def load_holdout(ctx: Context, cid: str) -> list[dict]:
    """비교 세트. s9h·s10 비교 평가만 읽는다(D-0120)."""
    gate = ctx.state(cid).gate("G0")
    if gate.status != "APPROVED" or not gate.rev:
        raise FactoryError(f"{cid}: G0 승인이 필요하다(현재 {gate.status})")
    return read_jsonl(ctx.character_dir(cid) / STAGE_DIR / gate.rev / "holdout.jsonl")
