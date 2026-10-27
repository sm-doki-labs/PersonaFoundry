"""S9 데이터셋 단계: 계획 → 샘플 → G7a → 대량 → 검사 → 분할 → G7 (가짜 작성 모델)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.cli import main
from character_factory_poc.common.canonical import sha256_of
from character_factory_poc.common.errors import CheckFailed, FactoryError, GateNotApprovedError
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.contracts.dataset import Conversation, Message
from character_factory_poc.stages.s9_data import build, checks, plan, samples, split
from character_factory_poc.stages.s9_data.approve import approve_g7, approve_g7a
from character_factory_poc.stages.s9_data.plan import CLUSTERS
from tests.support.data_fakes import (
    FakeWriterModel,
    make_s9_ctx,
    s9_toml,
    through_g6,
    write_sns,
)


def setup(tmp_path: Path, toml: str | None = None, fake: FakeWriterModel | None = None):
    ctx, model = make_s9_ctx(tmp_path, toml if toml is not None else s9_toml(tmp_path), fake)
    cid = through_g6(ctx, tmp_path)
    model.cid = cid
    return ctx, cid, model


def _all_select(ctx, cid, rev_dir: Path) -> None:
    for cluster in CLUSTERS:
        sample = json.loads((rev_dir / "samples" / f"{cluster}.json").read_text("utf-8"))
        ids = [ref["ref"].split("/")[-1][: -len(".json")] for ref in sample["conversations"]]
        approve_g7a(
            ctx,
            cid,
            {
                "decision": "SELECT",
                "cluster": cluster,
                "verdicts": dict.fromkeys(ids, "ADOPT"),
                "notes": {},
                "reviewer": "user",
            },
        )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text("utf-8").splitlines() if ln.strip()]


def test_plan_uses_guide_defaults(tmp_path):
    ctx, cid, _fake = setup(tmp_path, toml='[stages.s2]\nbase_photo = "picked"\n')
    rev_dir = plan.run_plan(ctx, cid)
    obj = json.loads((rev_dir / "plan.json").read_text("utf-8"))
    p = validate("data-plan-v1", obj)
    assert p.targetTrainConversations == 640
    targets = {c.clusterId: c.targetConversations for c in p.clusters}
    assert targets == {
        "base": 358,
        "situation": 51,
        "history": 141,
        "ownership": 45,
        "conflict": 45,
    }
    assert sum(targets.values()) == 640
    assert all(c.sampleSize == 12 for c in p.clusters)
    assert p.validation.baseConversations == 60
    assert p.validation.augmentedShare == 0.1
    assert "가이드" in p.guideRef
    assert p.personaVersion == "pv1"
    assert len(p.promptPairSha256) == 64
    assert ctx.state(cid).stage("s9s").status == "RUNNING"


def test_plan_rejects_bad_config(tmp_path):
    toml = s9_toml(tmp_path) + "\n[stages.s9.shares]\nbase = 0.9\n"
    ctx, cid, _fake = setup(tmp_path, toml=toml)
    with pytest.raises(CheckFailed):
        plan.run_plan(ctx, cid)
    assert not plan.data_dir(ctx, cid).exists()


def test_plan_rejects_nikl(tmp_path):
    toml = s9_toml(tmp_path, materials_base='["NIKL"]')
    ctx, cid, _fake = setup(tmp_path, toml=toml)
    with pytest.raises(CheckFailed) as err:
        plan.run_plan(ctx, cid)
    assert "NIKL" in str(err.value)


def test_samples_writes_g7a(tmp_path):
    ctx, cid, fake = setup(tmp_path)
    rev_dir = samples.run_samples(ctx, cid)
    assert rev_dir.name == "ds1"
    assert (rev_dir / "plan.json").exists()
    bundle = validate("data-sample-v1", json.loads((rev_dir / "samples/base.json").read_text()))
    assert len(bundle.conversations) == 2
    conv = validate(
        "conversation-v1", json.loads((rev_dir / bundle.conversations[0].ref).read_text())
    )
    assert "[SCENE]" in conv.system
    assert conv.messages[0].role == "user" and conv.messages[-1].role == "assistant"
    assert conv.provenance.writerModel == "fake"
    assert all(conv.checks.blocking.values())
    assert conv.skeletonId.startswith("synth-")
    for cluster in CLUSTERS:
        validate(
            "data-handoff-v1",
            json.loads((rev_dir / "handoffs" / f"{cluster}.json").read_text("utf-8")),
        )
    for name in ("gate-G7a.html", "gate-G7a-base.html", "gate-G7a-conflict.html"):
        assert (rev_dir / name).exists()
    state = ctx.state(cid)
    assert state.stage("s9s").status == "AWAITING_HUMAN"
    assert state.gate("G7a").status == "AWAITING_HUMAN"
    s9s_calls = [r for r in fake.requests if r.stage == "s9s"]
    assert len(s9s_calls) == 10  # 인계안 5 + 샘플 배치 5
    page = (rev_dir / "gate-G7a-base.html").read_text("utf-8")
    assert "data-conv=" in page and "REQUEST_CHANGES" in page


def test_samples_requires_g6(tmp_path):
    ctx, _model = make_s9_ctx(tmp_path)
    with pytest.raises(GateNotApprovedError):
        samples.run_samples(ctx, "cf-20260101-nope")


def test_g7a_partial_select_then_request_changes(tmp_path):
    ctx, cid, _fake = setup(tmp_path)
    rev1 = samples.run_samples(ctx, cid)
    for cluster in CLUSTERS[:-1]:
        approve_g7a(
            ctx, cid, {"decision": "SELECT", "cluster": cluster, "verdicts": {}, "reviewer": "u"}
        )
    state = ctx.state(cid)
    assert state.gate("G7a").status == "AWAITING_HUMAN"
    assert state.stage("s9s").status == "AWAITING_HUMAN"
    assert (ctx.character_dir(cid) / "gates" / "G7a-ds1-base.json").exists()
    with pytest.raises(FactoryError):
        samples.run_samples(ctx, cid)
    last = CLUSTERS[-1]
    bundle = json.loads((rev1 / "samples" / f"{last}.json").read_text("utf-8"))
    conv_id = bundle["conversations"][0]["ref"].split("/")[-1][: -len(".json")]
    with pytest.raises(FactoryError):
        approve_g7a(
            ctx,
            cid,
            {"decision": "REQUEST_CHANGES", "cluster": last, "verdicts": {}, "notes": {}},
        )
    approve_g7a(
        ctx,
        cid,
        {
            "decision": "REQUEST_CHANGES",
            "cluster": last,
            "verdicts": {conv_id: "FIX"},
            "notes": {conv_id: "말투가 너무 딱딱하다"},
            "reviewer": "u",
        },
    )
    assert ctx.state(cid).stage("s9s").status == "REJECTED"
    rev2 = samples.run_samples(ctx, cid)
    assert rev2.name == "ds2"
    for cluster in CLUSTERS[:-1]:
        name = f"samples/{cluster}.json"
        assert (rev2 / name).read_bytes() == (rev1 / name).read_bytes()
        assert (rev2 / "qa" / f"G7a-{cluster}.json").exists()
    handoff = json.loads((rev2 / "handoffs" / f"{last}.json").read_text("utf-8"))
    assert "말투가 너무 딱딱하다" in handoff["notes"]
    assert (rev2 / "samples" / f"{last}.json").read_bytes() != (
        rev1 / "samples" / f"{last}.json"
    ).read_bytes()
    assert ctx.state(cid).gate("G7a").rev == "ds2"
    assert ctx.state(cid).gate("G7a").status == "AWAITING_HUMAN"


def test_all_select_closes_gate_without_new_calls(tmp_path):
    ctx, cid, fake = setup(tmp_path)
    rev_dir = samples.run_samples(ctx, cid)
    _all_select(ctx, cid, rev_dir)
    state = ctx.state(cid)
    assert state.gate("G7a").status == "APPROVED"
    assert state.stage("s9s").status == "APPROVED"
    before = len(fake.requests)
    again = samples.run_samples(ctx, cid)
    assert again == rev_dir and len(fake.requests) == before


def test_build_requires_g7a(tmp_path):
    ctx, cid, _fake = setup(tmp_path)
    with pytest.raises(GateNotApprovedError):
        build.run_build(ctx, cid)


def test_build_sns_rewrite_keeps_user_turns_and_retries(tmp_path):
    write_sns(tmp_path / "sns.jsonl", count=4)
    toml = s9_toml(tmp_path, materials_base='["SNS_REWRITE"]')
    ctx, cid, fake = setup(tmp_path, toml=toml, fake=FakeWriterModel(sns_bad_first=True))
    rev_dir = samples.run_samples(ctx, cid)
    _all_select(ctx, cid, rev_dir)
    out = build.run_build(ctx, cid)
    rows = _read_jsonl(out / "index.jsonl")
    assert fake.sns_bad_served
    sns_rows = [r for r in rows if r["material"] == "SNS_REWRITE"]
    assert sns_rows
    for row in sns_rows:
        conv = validate("conversation-v1", json.loads((out / row["path"]).read_text("utf-8")))
        assert conv.checks.blocking["sns_user_turns_verbatim"] is True
        assert conv.skeletonId.startswith("sns-sns")
        assert conv.provenance.sourceRef.startswith("sns")


def test_build_blocks_repeated_ending(tmp_path):
    toml = s9_toml(tmp_path, bubble_cap=1)
    ctx, cid, _fake = setup(tmp_path, toml=toml, fake=FakeWriterModel(same_ending=True))
    rev_dir = samples.run_samples(ctx, cid)
    _all_select(ctx, cid, rev_dir)
    with pytest.raises(CheckFailed) as err:
        build.run_build(ctx, cid)
    assert "ending_repetition" in str(err.value)
    assert ctx.state(cid).stage("s9").status == "CHECK_FAILED"
    assert not (rev_dir / "dataset.json").exists()
    report = json.loads((rev_dir / "check-report.json").read_text("utf-8"))
    assert report["lengthCheck"]["approximate"] is True


def test_samples_retry_cap_with_long_reply(tmp_path):
    toml = s9_toml(tmp_path, max_retries=1, max_length_tokens=256)
    ctx, cid, fake = setup(tmp_path, toml=toml, fake=FakeWriterModel(long_reply=True))
    with pytest.raises(CheckFailed) as err:
        samples.run_samples(ctx, cid)
    assert "max_length" in str(err.value)
    batch_calls = [r for r in fake.requests if '<input name="batch">' in r.messages[-1].content]
    assert len(batch_calls) == 2  # 같은 입력으로 두 번(재시도 상한 1)


def test_full_build_split_and_g7(tmp_path):
    ctx, cid, _fake = setup(tmp_path)
    rev_dir = samples.run_samples(ctx, cid)
    _all_select(ctx, cid, rev_dir)
    out = build.run_build(ctx, cid)
    assert out == rev_dir
    dataset = validate("dataset-rev-v2", json.loads((out / "dataset.json").read_text("utf-8")))
    assert dataset.blockingFailures == 0
    assert dataset.datasetRev == "ds1"
    assert {f.split for f in dataset.files} == set(split.SPLITS)
    rows = _read_jsonl(out / "index.jsonl")
    assert sum(f.conversations for f in dataset.files) == len(rows)
    for name in split.FILE_NAME.values():
        lines = _read_jsonl(out / name)
        assert all(line["messages"][0]["role"] == "system" for line in lines)
    by_skeleton: dict[str, set[str]] = {}
    for row in rows:
        by_skeleton.setdefault(row["skeletonId"], set()).add(row["split"])
    assert all(len(v) == 1 for v in by_skeleton.values())
    train_base = sum(1 for r in rows if r["split"] == "train" and r["clusterId"] == "base")
    assert train_base == 6
    val_base = sum(1 for r in rows if r["split"] == "validation_base")
    assert val_base == 2
    convs = [
        validate("conversation-v1", json.loads((out / r["path"]).read_text("utf-8"))) for r in rows
    ]
    payload = [
        {
            "conversationId": c.conversationId,
            "messages": [{"role": "system", "content": c.system}]
            + [{"role": m.role, "content": m.content} for m in c.messages],
        }
        for c in sorted(convs, key=lambda c: c.conversationId)
    ]
    assert dataset.digest == sha256_of(payload)
    assert (out / "gate-G7.html").exists()
    state = ctx.state(cid)
    assert state.stage("s9").status == "AWAITING_HUMAN"
    assert state.gate("G7").status == "AWAITING_HUMAN"
    assert len(dataset.sampleQaRefs) == len(CLUSTERS)

    approve_g7(ctx, cid, {"decision": "APPROVE", "verdicts": {}, "reviewer": "u", "minutes": 2})
    frozen = json.loads((out / "frozen.json").read_text("utf-8"))
    assert frozen["digest"] == dataset.digest and frozen["datasetRev"] == "ds1"
    assert ctx.state(cid).gate("G7").status == "APPROVED"
    assert ctx.state(cid).stage("s9").status == "APPROVED"
    assert ctx.ledger(cid).report()["humanByGate"]["G7"] == 2
    assert main(["--root", str(tmp_path), "verify", cid]) == 0
    qa = validate("data-qa-v2", json.loads((out / "qa" / "G7-ds1.json").read_text("utf-8")))
    assert qa.gate == "G7" and qa.subjectSha256


def test_g7_request_changes_regenerates_only_flagged(tmp_path):
    ctx, cid, _fake = setup(tmp_path)
    rev1 = samples.run_samples(ctx, cid)
    _all_select(ctx, cid, rev1)
    build.run_build(ctx, cid)
    rows = _read_jsonl(rev1 / "index.jsonl")
    target = rows[0]
    approve_g7(
        ctx,
        cid,
        {
            "decision": "REQUEST_CHANGES",
            "verdicts": {target["conversationId"]: "FIX"},
            "notes": {target["conversationId"]: "말투가 딱딱하다"},
            "reviewer": "u",
        },
    )
    assert ctx.state(cid).stage("s9").status == "REJECTED"
    rev2 = build.run_build(ctx, cid)
    assert rev2.name == "ds2"
    rows2 = _read_jsonl(rev2 / "index.jsonl")
    ids2 = {r["conversationId"] for r in rows2}
    assert target["conversationId"] not in ids2
    others = [r for r in rows if r["conversationId"] != target["conversationId"]]
    for row in others:
        assert (rev2 / row["path"]).read_bytes() == (rev1 / row["path"]).read_bytes()
    dataset = validate("dataset-rev-v2", json.loads((rev2 / "dataset.json").read_text("utf-8")))
    assert dataset.datasetRev == "ds2" and dataset.blockingFailures == 0


def test_g7_request_changes_needs_flagged_conversation(tmp_path):
    ctx, cid, _fake = setup(tmp_path)
    rev_dir = samples.run_samples(ctx, cid)
    _all_select(ctx, cid, rev_dir)
    build.run_build(ctx, cid)
    with pytest.raises(FactoryError):
        approve_g7(ctx, cid, {"decision": "REQUEST_CHANGES", "verdicts": {}, "reviewer": "u"})


def test_dry_run_plan_has_no_model_calls(tmp_path):
    ctx, cid, fake = setup(tmp_path)
    assert plan.plan_calls()[0].calls == 0
    before = len(fake.requests)
    sample_plans = samples.plan_calls(ctx, cid)
    assert sum(p.calls for p in sample_plans) > 0
    assert len(fake.requests) == before
    rev_dir = samples.run_samples(ctx, cid)
    build_plans = build.plan_calls(ctx, cid)
    assert sum(p.calls for p in build_plans) > 0
    assert len(fake.requests) > before
    assert (rev_dir / "plan.json").exists()


def test_split_keeps_skeleton_bundles_together():
    convs = []
    for i in range(10):
        convs.append(
            Conversation(
                conversationId=f"c{i:02d}",
                clusterId="base",
                material="SYNTH",
                skeletonId=f"sk{i // 2}",
                system="system",
                messages=[
                    Message(role="user", content=f"질문 {i}"),
                    Message(role="assistant", content=f"답 {i}"),
                ],
                provenance={"writerModel": "fake", "requestRef": "ref"},
            )
        )
    cfg = _cfg_for_split()
    plan_obj = validate("data-plan-v1", _plan_for_split())
    result = split.split(convs, plan_obj, cfg, {})
    where: dict[str, str] = {}
    for name, group in result.splits.items():
        for conv in group:
            assert where.setdefault(conv.skeletonId, name) == name
    assert sum(len(v) for v in result.splits.values()) == 10
    assert len(result.splits["train"]) == 6
    assert len(result.splits["validation_base"]) == 2
    assert len(result.splits["eval"]) == 2
    assert result.digest == sha256_of(
        [
            {
                "conversationId": c.conversationId,
                "messages": [{"role": "system", "content": c.system}]
                + [{"role": m.role, "content": m.content} for m in c.messages],
            }
            for c in sorted(convs, key=lambda c: c.conversationId)
        ]
    )


def test_checks_flag_sns_and_forbidden():
    spec = checks.ConvSpec(
        cluster_id="base",
        system="system",
        material="SNS_REWRITE",
        source={
            "sourceId": "sns1",
            "turns": [
                {"role": "user", "content": "원문 질문"},
                {"role": "assistant", "content": "원문 답"},
            ],
        },
        forbidden=("연락하지 마",),
        source_facts=("대학생",),
    )
    good = Conversation(
        conversationId="c1",
        clusterId="base",
        material="SNS_REWRITE",
        skeletonId="sns-1",
        system="system",
        messages=[
            Message(role="user", content="원문 질문"),
            Message(role="assistant", content="다시 쓴 답"),
        ],
        provenance={"writerModel": "fake", "requestRef": "ref"},
    )
    assert all(checks.evaluate(good, spec).values())
    bad = good.model_copy(
        update={
            "messages": [
                Message(role="user", content="바꾼 질문"),
                Message(role="assistant", content="연락하지 마. 나는 대학생이야."),
            ]
        }
    )
    result = checks.evaluate(bad, spec)
    assert result["sns_user_turns_verbatim"] is False
    assert result["forbidden_phrases"] is False
    assert result["source_facts_absent"] is False
    assert len(checks.problems_of(result)) == 3
    sample = Conversation(
        conversationId="c2",
        clusterId="base",
        material="SYNTH",
        skeletonId="s-2",
        system="system",
        messages=[
            Message(role="assistant", content="먼저 말함"),
            Message(role="user", content="질문"),
        ],
        provenance={"writerModel": "fake", "requestRef": "ref"},
    )
    assert checks.evaluate(sample, spec)["roles_alternate"] is False


def _cfg_for_split():
    from character_factory_poc.stages.s9_data.plan import S9Config

    return S9Config(
        target=10,
        shares={"base": 1.0, "situation": 0, "history": 0, "ownership": 0, "conflict": 0},
        materials={c: ("SYNTH",) for c in CLUSTERS},
        sample_size=1,
        concurrency=1,
        batch_size=1,
        max_retries=0,
        validation_base=2,
        validation_augmented_share=0.0,
        eval_per_cluster=2,
        max_length_tokens=4096,
        chars_per_token=1.5,
        phrase_ngram=6,
        phrase_max_conversations=10,
        bubble_max_conversations=10,
        forbidden_phrases=(),
        source_facts=(),
        sns_path="",
        sns_limit=0,
        guide_ref="test",
    )


def _plan_for_split():
    from character_factory_poc.stages.s9_data import plan as plan_mod

    targets = plan_mod.cluster_targets(10, _cfg_for_split().shares)
    return dump(
        plan_mod.DataPlan(
            characterId="cf-test",
            personaVersion="pv1",
            promptPairSha256="0" * 64,
            targetTrainConversations=10,
            clusters=[
                plan_mod.ClusterPlan(
                    clusterId="base",
                    label="기반",
                    share=1.0,
                    targetConversations=targets["base"],
                    materials=["SYNTH"],
                )
            ],
            guideRef="test",
            writerModel="fake",
        )
    )
