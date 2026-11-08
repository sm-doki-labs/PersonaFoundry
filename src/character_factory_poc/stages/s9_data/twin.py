"""모티브 TRAIN의 G7a·G7. 승인 원문에서 턴을 조립하며 모델을 호출하지 않는다."""

from __future__ import annotations

import re
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import replace
from itertools import groupby
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import (
    read_json,
    verify_manifest,
    write_manifest,
    write_once_json,
)
from character_factory_poc.contracts.common import ArtifactRef
from character_factory_poc.contracts.dataset import (
    ClusterPlan,
    Conversation,
    DataHandoff,
    DataPlan,
    DataSample,
    DatasetRev,
    Message,
    Provenance,
    ValidationPlan,
)
from character_factory_poc.contracts.persona import require_short
from character_factory_poc.contracts.source import SourceDigest
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import SOURCE, TRAIN
from character_factory_poc.pipeline.origin import read_model_mode, read_origin
from character_factory_poc.stages.s0_source.run import STAGE_DIR, load_approved_source, load_holdout
from character_factory_poc.stages.s9_data import build, checks, samples, split
from character_factory_poc.stages.s9_data import plan as plans

_OTHER_NOTE = (
    "제3자의 말을 사용자 질문이나 대상 인물의 답으로 오인하지 않도록 OTHER에서 문맥을 끊었다."
)


def _require(ctx: Context, cid: str, stage: str):
    char = ctx.character_dir(cid)
    if read_origin(char) != SOURCE or read_model_mode(char) != TRAIN:
        raise FactoryError(f"{stage}: TRAIN 방식의 모티브만 원문 학습 데이터를 만든다")
    state = ctx.state(cid)
    state.require_deps(stage)
    return state


@contextmanager
def _review_stage(state, stage: str, gate: str, folder: Path):
    rev = folder.name
    state.transition(stage, "RUNNING", rev=rev)
    try:
        yield
        write_manifest(folder)
    except (FactoryError, OSError, ValueError) as exc:
        state.transition(stage, "CHECK_FAILED", rev=rev, error=str(exc)[:500])
        raise
    state.transition(stage, "AWAITING_HUMAN", rev=rev)
    state.set_gate(gate, "AWAITING_HUMAN", rev, None)


def _exchanges(rows: list[dict]):
    for intact, block in groupby(rows, lambda r: r["speaker"] != "OTHER"):
        if not intact:
            continue
        turns = []
        spoken = (r for r in block if r["text"].strip())
        for speaker, run in groupby(spoken, lambda r: r["speaker"]):
            if speaker not in {"USER", "SUBJECT"}:
                raise FactoryError("원문에 알 수 없는 화자 구분이 있다")
            content = "\n".join(r["text"] for r in run)
            turns.append(
                Message(role="user" if speaker == "USER" else "assistant", content=content)
            )
        if turns and turns[0].role == "assistant":
            turns.pop(0)
        if turns and turns[-1].role == "user":
            turns.pop()
        if turns:
            yield turns


def _source_examples(ctx: Context, cid: str, system: str):
    _, index, rows = load_approved_source(ctx, cid)
    if index.sourceRev != ctx.state(cid).gate("G0").rev or index.characterId != cid:
        raise FactoryError("G0이 승인한 캐릭터·출처 판과 인덱스가 다르다")
    source = f"{STAGE_DIR}/{index.sourceRev}"
    folder = ctx.character_dir(cid) / source
    if verify_manifest(folder):
        raise FactoryError("G0 출처 판의 파일이 원래 해시와 다르다")
    digest = SourceDigest.model_validate(read_json(folder / "digest.json"))
    flagged = {flag.msgId for flag in digest.piiFlags}
    # 비교 세트는 유출 검사에서만 읽는다. 원문이나 일치한 문구는 보고서에 쓰지 않는다.
    held = load_holdout(ctx, cid)
    if index.holdoutMessages != len(held) or index.corpusMessages != len(rows):
        raise FactoryError("G0 인덱스와 비교 세트·원문 메시지 수가 다르다")
    held_ids = {r["convId"] for r in held}
    held_msgs = {r["msgId"] for r in held}
    phrases = {r["text"].strip() for r in held if r["text"].strip()}
    leak = re.compile("|".join(map(re.escape, sorted(phrases)))) if phrases else None
    if leak and leak.search(system):
        raise FactoryError("G6의 짧은 system에 비교 세트 원문이 있다")
    grouped = defaultdict(list)
    for row in rows:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", row["convId"]):
            raise FactoryError("원문 대화 ID 형식이 맞지 않는다")
        if row["convId"] in held_ids or row["msgId"] in held_msgs:
            raise FactoryError("비교 세트와 corpus의 원본 ID가 겹친다")
        if row["msgId"] in flagged and row["text"].strip() and row["text"].strip() in system:
            raise FactoryError("G6의 짧은 system에 G0에서 개인정보로 표시한 발화가 있다")
        grouped[row["convId"]].append(row)
    metrics = dict(
        otherMessages=sum(r["speaker"] == "OTHER" for r in rows),
        otherPolicy=_OTHER_NOTE,
        piiConversations=0,
        noExchangeConversations=0,
        holdoutTextConversations=0,
    )
    out = []
    for conv_id, group in grouped.items():
        if any(r["msgId"] in flagged for r in group):
            metrics["piiConversations"] += 1
            continue
        exchanges = list(_exchanges(group))
        if not exchanges:
            metrics["noExchangeConversations"] += 1
            continue
        if leak and any(leak.search(m.content) for turns in exchanges for m in turns):
            metrics["holdoutTextConversations"] += 1
            continue
        for i, turns in enumerate(exchanges, 1):
            out.append(
                Conversation(
                    conversationId=f"{conv_id}-{i}",
                    skeletonId=conv_id,
                    clusterId="base",
                    material="SOURCE",
                    system=system,
                    messages=turns,
                    provenance=Provenance(
                        writerModel="",
                        requestRef="",
                        sourceRef=f"{source}/corpus.jsonl#{conv_id}",
                        editedBy="none",
                    ),
                )
            )
    # G7a 뒤 원본 판, 개인정보 표시 또는 원문 정리가 바뀌었으면 샘플부터 다시 판정한다.
    pin = {
        "sourceRev": index.sourceRev,
        "manifestSha256": sha256_file(folder / "manifest.sha256"),
    }
    return out, metrics, pin


def _sized_config(cfg, convs):
    # split은 뼈대째 가져간다. 원문이 하나여도 train에 최소 한 묶음은 남긴다.
    groups = len({c.skeletonId for c in convs})
    if not groups:
        raise FactoryError(
            "학습할 원문 대화가 남지 않았다. 출처를 보완하거나 PROMPT_ONLY를 선택한다"
        )
    share = max(1, round(groups * 0.1))
    val = min(cfg.validation_base, share, groups - 1)
    ev = min(cfg.eval_per_cluster, share, groups - val - 1)
    return replace(cfg, validation_base=val, eval_per_cluster=ev, validation_augmented_share=0)


def _write_conv(folder: Path, conv: Conversation) -> ArtifactRef:
    rel = f"conversations/{conv.conversationId}.json"
    write_once_json(folder / rel, dump(conv))
    return ArtifactRef(ref=rel, sha256=sha256_file(folder / rel))


def run_s9s_twin(ctx: Context, cid: str) -> Path:
    """승인 원문 표본을 기존 G7a의 base(원문 대화) 한 묶음으로 올린다."""
    state = _require(ctx, cid, "s9s")
    root = plans.data_dir(ctx, cid)
    gate = state.gate("G7a")
    if gate.status in {"APPROVED", "AWAITING_HUMAN"} and gate.rev:
        return root / gate.rev
    folder = root / plans.new_rev(ctx, cid)
    with _review_stage(state, "s9s", "G7a", folder):
        pair, path = plans.load_prompt_pair(ctx, cid)
        convs, metrics, pin = _source_examples(ctx, cid, require_short(pair).text)
        excluded = set()
        if gate.status == "REJECTED" and gate.rev:
            old = root / gate.rev
            previous = read_json(old / "source-selection.json")
            if previous["source"] == pin:
                qa = samples.cluster_qa(old, "base")
                if qa is None:
                    raise FactoryError("거절된 G7a 판정 기록이 없다")
                excluded.update(previous["excluded"])
                excluded.update(k for k, v in qa.verdicts.items() if v != "ADOPT")
                excluded.update(qa.notes)
        convs = [c for c in convs if c.conversationId not in excluded]
        cfg = _sized_config(plans.s9_config(ctx), convs)
        target = len(convs) - cfg.validation_base - cfg.eval_per_cluster
        sample = sorted(convs, key=lambda c: sha256_text(c.conversationId))[: cfg.sample_size]
        cluster = ClusterPlan(
            clusterId="base",
            label="원문 대화",
            share=1,
            targetConversations=target,
            materials=["SOURCE"],
            sampleSize=len(sample),
        )
        plan = DataPlan(
            characterId=cid,
            personaVersion=plans.persona_version(ctx, cid, pair),
            promptPairSha256=sha256_file(path),
            targetTrainConversations=target,
            clusters=[cluster],
            validation=ValidationPlan(baseConversations=cfg.validation_base, augmentedShare=0),
            guideRef="모티브 갈래 계획 §7 · G0 승인 원문",
            writerModel="",
        )
        write_once_json(folder / "plan.json", dump(plan))
        plan_sha = sha256_file(folder / "plan.json")
        write_once_json(
            folder / "source-selection.json",
            {
                "source": pin,
                "excluded": sorted(excluded),
                "evalLimit": cfg.eval_per_cluster,
                "metrics": metrics,
            },
        )
        handoff = DataHandoff(
            characterId=cid,
            planSha256=plan_sha,
            clusterId="base",
            behaviorTable=[],
            notes=f"원문 대화만 사용한다. {_OTHER_NOTE} FIX·REJECT는 재작성 없이 제외한다.",
        )
        handoff_path = folder / "handoffs/base.json"
        write_once_json(handoff_path, dump(handoff))
        bundle = DataSample(
            characterId=cid,
            planSha256=plan_sha,
            clusterId="base",
            handoffSha256=sha256_file(handoff_path),
            conversations=[_write_conv(folder, c) for c in sample],
        )
        write_once_json(folder / "samples/base.json", dump(bundle))
        samples._write_pages(ctx, cid, folder.name, folder, plan)
    return folder


def run_s9_twin(ctx: Context, cid: str) -> Path:
    """G7a 판정을 적용하고 같은 원본 대화를 한 분할에 둔 뒤 G7을 연다."""
    state = _require(ctx, cid, "s9")
    root = plans.data_dir(ctx, cid)
    gate = state.gate("G7")
    if gate.status in {"APPROVED", "AWAITING_HUMAN"} and gate.rev:
        return root / gate.rev
    sample_dir = root / str(state.gate("G7a").rev)
    folder = root / plans.new_rev(ctx, cid) if gate.status == "REJECTED" else sample_dir
    with _review_stage(state, "s9", "G7", folder):
        plan = plans.load_plan(sample_dir / "plan.json")
        plan_sha = sha256_file(sample_dir / "plan.json")
        bundle_path = sample_dir / "samples/base.json"
        bundle = DataSample.model_validate(read_json(bundle_path))
        qa = samples.cluster_qa(sample_dir, "base")
        if (
            qa is None
            or qa.subjectSha256 != sha256_file(bundle_path)
            or bundle.planSha256 != plan_sha
        ):
            raise FactoryError("G7a에서 판정한 원문 샘플·계획이 아니다")
        pair, path = plans.load_prompt_pair(ctx, cid)
        selection = read_json(sample_dir / "source-selection.json")
        convs, metrics, pin = _source_examples(ctx, cid, require_short(pair).text)
        if pin != selection["source"] or sha256_file(path) != plan.promptPairSha256:
            raise FactoryError(
                "G7a 이후 G0 원문 또는 G6 프롬프트가 바뀌었다. 샘플부터 다시 판정한다"
            )
        excluded = set(selection["excluded"])
        excluded.update(k for k, v in qa.verdicts.items() if v != "ADOPT")
        if gate.status == "REJECTED" and gate.rev:
            old = root / gate.rev
            excluded.update(read_json(old / "check-report.json")["excluded"])
            excluded.update(read_json(old / "requests/g7-changes.json")["conversations"])
        convs = [c for c in convs if c.conversationId not in excluded]
        cfg = _sized_config(
            replace(
                plans.s9_config(ctx),
                validation_base=plan.validation.baseConversations,
                eval_per_cluster=selection["evalLimit"],
            ),
            convs,
        )
        approx = {
            c.conversationId: checks.approx_tokens(checks.conversation_text(c), cfg.chars_per_token)
            for c in convs
        }
        result = split.split(convs, plan, cfg, approx)
        train = len(result.splits["train"])
        warnings = list(result.warnings)
        if train < 50:
            warnings.insert(
                0,
                f"학습 예시가 {train}개로 50개 미만이다. "
                "원문을 외워 되풀이할 위험이 커서 PROMPT_ONLY를 권장한다.",
            )
        write_once_json(folder / "plan.json", dump(plan))
        for conv in convs:
            _write_conv(folder, conv)
        dataset = DatasetRev(
            characterId=cid,
            datasetRev=folder.name,
            personaVersion=plan.personaVersion,
            planSha256=plan_sha,
            sampleQaRefs=[f"s9-data/{sample_dir.name}/qa/G7a-base.json"],
            clusterCounts=split.cluster_counts(convs),
            files=split.write_splits(folder, result),
            blockingFailures=0,
            warnings=len(warnings),
            digest=result.digest,
        )
        write_once_json(folder / "dataset.json", dump(dataset))
        report = checks.DatasetReport(warnings=warnings, metrics=metrics)
        write_once_json(
            folder / "check-report.json",
            {
                "warnings": warnings,
                "blocking": [],
                "metrics": metrics,
                "sourceRev": pin["sourceRev"],
                "excluded": sorted(excluded),
            },
        )
        build._write_page(cid, folder.name, folder, dataset, report, convs)
    return folder
