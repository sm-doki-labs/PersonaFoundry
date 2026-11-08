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


def test_build_sns_rewrite_uses_flow_only_and_retries(tmp_path):
    """흐름 시드만 보고 양쪽을 새로 쓴다(D-0135, D-0138).

    작가 입력에는 원문이 없고, 캐릭터 말이 길이 상한을 넘은 첫 응답은 다시 쓴다.
    """
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
        assert conv.checks.blocking["source_overlap"] is True
        assert conv.checks.blocking["flow_beats"] is True
        assert conv.checks.blocking["turn_length"] is True
        assert conv.provenance.flowBeats[0] == "상대가 만날 시간을 묻는다"  # 시드의 사건
        assert conv.provenance.relationship and conv.provenance.channel == "text"
        assert "[RELATIONSHIP]" in conv.system and "[CHANNEL]" in conv.system
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
            Message(role="user", content="새로 쓴 질문"),
            Message(role="assistant", content="다시 쓴 답"),
        ],
        provenance={
            "writerModel": "fake",
            "requestRef": "ref",
            "flowBeats": ["상대가 묻는다", "캐릭터가 답한다", "둘이 정리한다"],
        },
    )
    assert all(checks.evaluate(good, spec).values())
    bad = good.model_copy(
        update={
            "messages": [
                Message(role="user", content="바꾼 질문"),
                Message(role="assistant", content="연락하지 마. 나는 대학생이야."),
            ],
            "provenance": good.provenance.model_copy(update={"flowBeats": []}),
        }
    )
    result = checks.evaluate(bad, spec)
    assert result["flow_beats"] is False  # 뼈대 없이 썼다
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


def _long_sns(path, sessions: int, turns: int) -> None:
    rows = []
    for s in range(1, sessions + 1):
        msgs = []
        for t in range(turns):
            role = "user" if t % 2 == 0 else "assistant"
            msgs.append({"role": role, "content": f"{s}번 대화 {t}번째 말"})
        rows.append({"conversationId": f"long{s:02d}", "messages": msgs})
    rows.append({"conversationId": "short", "messages": msgs[:2]})
    rows.append(
        {"conversationId": "gap", "messages": [msgs[0], {"role": "assistant", "content": " "}] * 3}
    )
    rows.append({"conversationId": "same", "messages": [msgs[0], msgs[0], msgs[1], msgs[1]]})
    rows.append({"conversationId": "lead", "messages": [msgs[1]] + msgs[:6] + [msgs[0]]})
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", "utf-8")


def test_long_sessions_are_cut_into_windows_with_one_session_id(tmp_path):
    """긴 세션은 12턴 이하 구간으로 자르고 같은 세션 ID로 묶는다.

    버린 후보는 이유별로 센다(D-0131).
    """
    path = tmp_path / "sns.jsonl"
    _long_sns(path, sessions=2, turns=30)
    sources, stats = samples.read_sns_sources(str(path), limit=5)
    # 세션마다 첫 구간부터 돌아가며 놓는다(앞 세션이 자리를 다 차지하지 않게).
    assert [s["sourceId"] for s in sources] == [
        "long01~w1",
        "long02~w1",
        "lead",
        "long01~w2",
        "long02~w2",
    ]
    every = samples.read_sns_sources(str(path), limit=50)[0]
    first = [s for s in every if s["sessionId"] == "long01"]
    assert [s["sourceId"] for s in first] == ["long01~w1", "long01~w2", "long01~w3"]
    assert [len(s["turns"]) for s in first] == [12, 12, 6]
    assert all(
        s["turns"][0]["role"] == "user" and s["turns"][-1]["role"] == "assistant" for s in sources
    )
    lead = next(s for s in every if s["sourceId"] == "lead")
    assert len(lead["turns"]) == 6  # 앞의 캐릭터 말과 끝의 사용자 말만 다듬었다
    assert stats["sessions"] == 6 and stats["split"] == 2 and stats["windows"] == 7
    assert stats["dropped"] == {
        "too_short": 1,
        "empty_turn": 1,
        "not_alternating": 1,
        "over_limit": 2,
    }
    line = samples.source_warning(stats, used=4)
    assert (
        line.startswith("실제 대화 재료: 후보 대화 6개")
        and "구간 7개" in line
        and "4턴보다 짧음 1" in line
    )
    assert "상한 5개를 넘은 구간 2개" in line and "쓴 구간 4개" in line


def test_build_keeps_session_windows_in_one_split_and_warns(tmp_path):
    _long_sns(tmp_path / "sns.jsonl", sessions=4, turns=40)
    toml = s9_toml(tmp_path, materials_base='["SNS_REWRITE"]')
    ctx, cid, _fake = setup(tmp_path, toml=toml)
    rev_dir = samples.run_samples(ctx, cid)
    _all_select(ctx, cid, rev_dir)
    out = build.run_build(ctx, cid)
    rows = [r for r in _read_jsonl(out / "index.jsonl") if r["material"] == "SNS_REWRITE"]
    assert rows
    splits: dict[str, set] = {}
    for row in rows:
        splits.setdefault(row["skeletonId"], set()).add(row["split"])
    assert all(len(v) == 1 for v in splits.values()), splits
    assert all(k.startswith("sns-") and "~w" not in k for k in splits)
    report = json.loads((out / "check-report.json").read_text("utf-8"))
    assert report["sources"]["split"] == 4 and report["sources"]["used"] == len(rows)
    assert any(w.startswith("실제 대화 재료: 후보 대화 8개") for w in report["warnings"])


def _mixed_sources(path: Path, sns: int, nikl: int, turns: int = 8) -> None:
    rows = []
    for kind, count in (("AIHUB_SNS", sns), ("NIKL", nikl)):
        for s in range(count):
            msgs = [
                {"role": "user" if t % 2 == 0 else "assistant", "content": f"{kind} {s}-{t}"}
                for t in range(turns)
            ]
            rows.append({"conversationId": f"{kind.lower()}-{s}", "source": kind, "messages": msgs})
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", "utf-8")


def test_corpus_windows_mix_in_as_call_scenes(tmp_path):
    """말뭉치 구간은 앞에서 몇 개를 쓰든 약 20%가 되게 SNS 사이에 놓고 통화로 표시한다(D-0134)."""
    path = tmp_path / "sns.jsonl"
    _mixed_sources(path, sns=6, nikl=4)
    sources, stats = samples.read_sns_sources(str(path), limit=5, corpus_share=0.2)
    assert [s["source"] for s in sources] == ["SNS", "SNS", "NIKL", "SNS", "SNS"]
    assert {s["channel"] for s in sources if s["source"] == "NIKL"} == {"call"}
    assert {s["channel"] for s in sources if s["source"] == "SNS"} == {"text"}
    assert stats["bySource"]["NIKL"] == {"sessions": 4, "windows": 4, "offered": 1}
    assert stats["dropped"] == {"over_limit": 2, "over_share": 3}
    every = samples.read_sns_sources(str(path), limit=50, corpus_share=0.2)[0]
    for n in (5, 10):
        assert sum(s["source"] == "NIKL" for s in every[:n]) == round(n * 0.2)
    # SNS가 바닥나면 말뭉치를 더 넣지 않는다(6 SNS + 말뭉치 2 = 8).
    assert len(every) == 8
    stats["usedBySource"] = {"SNS": 4, "NIKL": 1}
    line = samples.source_warning(stats, used=5)
    assert "말뭉치 비율 20%를 넘은 말뭉치 구간 3개" in line
    assert "쓴 구간 5개(SNS 4 · 말뭉치 1, 말뭉치는 통화 장면)" in line
    only = tmp_path / "nikl.jsonl"
    _mixed_sources(only, sns=0, nikl=3)
    alone = samples.read_sns_sources(str(only), limit=10)[0]
    assert [s["source"] for s in alone] == ["NIKL"] * 3  # 말뭉치만 있으면 비율을 적용하지 않는다


def test_call_scenes_allow_jamo_marks_but_not_emoji():
    """ㅋㅋ·ㅠㅠ·^^는 문자·통화 구분 없이 쓰고 그림 이모지만 막는다(D-0136, D-0137)."""
    turns = [{"role": "user", "content": "여보세요"}, {"role": "assistant", "content": "원문"}]

    def run(reply: str, material: str = "SNS_REWRITE") -> dict:
        source = {"sourceId": "nikl-1", "channel": "call", "turns": turns}
        spec = checks.ConvSpec(
            cluster_id="base",
            system="system",
            material=material,
            source=source if material == "SNS_REWRITE" else None,
        )
        conv = Conversation(
            conversationId="c1",
            clusterId="base",
            material=material,
            skeletonId="sns-nikl-1",
            system="system",
            messages=[
                Message(role="user", content="여보세요 나야"),
                Message(role="assistant", content=reply),
            ],
            provenance={
                "writerModel": "fake",
                "requestRef": "ref",
                "flowBeats": ["상대가 전화를 건다", "캐릭터가 받는다", "근황을 나눈다"]
                if material == "SNS_REWRITE"
                else [],
            },
        )
        return checks.evaluate(conv, spec)

    for reply in ("ㅋㅋ 진짜?", "알겠어ㅠㅠ", "좋아^^", "보고 싶었어♥", "아 진짜? 하하"):
        result = run(reply)
        assert all(result.values()), (reply, result)
    for reply in ("좋아 😊", "고마워 ❤️", "헐 🎉"):
        for material in ("SNS_REWRITE", "SYNTH"):
            result = run(reply, material)
            assert result["no_emoji"] is False, (reply, material)
            assert checks.problems_of(result) == [
                "no_emoji: 캐릭터 말에 그림 이모지가 있다(ㅋㅋ·ㅠㅠ·^^는 써도 된다)"
            ]


def test_build_reports_mix_and_sends_channel_to_writer(tmp_path):
    _mixed_sources(tmp_path / "sns.jsonl", sns=12, nikl=6)
    toml = s9_toml(tmp_path, materials_base='["SNS_REWRITE"]')
    from tests.support.data_fakes import _block

    class Recorder(FakeWriterModel):
        sent: list = []

        def writer(self, req):
            self.sent.extend(_block(req, "batch").get("sources", []))
            return super().writer(req)

    ctx, cid, fake = setup(tmp_path, toml=toml, fake=Recorder())
    rev_dir = samples.run_samples(ctx, cid)
    _all_select(ctx, cid, rev_dir)
    out = build.run_build(ctx, cid)
    report = json.loads((out / "check-report.json").read_text("utf-8"))
    mix = report["sources"]["usedBySource"]
    assert mix.get("NIKL") and mix["SNS"] > mix["NIKL"]
    assert sum(mix.values()) == report["sources"]["used"]
    assert any("말뭉치는 통화 장면" in w for w in report["warnings"])
    pairs = {(s["origin"], s["channel"]) for s in fake.sent}
    assert pairs == {("SNS", "text"), ("NIKL", "call")}


def test_rewrite_blocks_ten_char_overlap_with_source():
    """대사·뼈대가 원본과 공백·문장 부호를 빼고 10글자 이상 이어서 같으면 막는다.

    학습 가이드 §7.1, D-0135.
    """
    turns = [
        {"role": "user", "content": "내일 아침에 같이 등산 가기로 한 거 기억나?"},
        {"role": "assistant", "content": "응 당연하지 몇 시에 만나"},
        {"role": "user", "content": "일곱 시 반에 역 앞에서 보자"},
        {"role": "assistant", "content": "알겠어 늦지 마"},
    ]
    spec = checks.ConvSpec(
        cluster_id="base",
        system="system",
        material="SNS_REWRITE",
        source={"sourceId": "s1", "channel": "text", "turns": turns},
    )
    beats = ["상대가 약속을 확인한다", "캐릭터가 시간을 묻는다", "만날 곳을 정한다"]

    def conv(user: str, beats_: list[str] = beats, extra: int = 0) -> Conversation:
        msgs = [
            Message(role="user", content=user),
            Message(role="assistant", content="그럼 몇 시에 볼까?"),
            Message(role="user", content="여덟 시 어때"),
            Message(role="assistant", content="좋아, 정문에서 봐."),
        ] + [
            Message(role="user" if k % 2 == 0 else "assistant", content=f"덧붙인 말 {k}")
            for k in range(extra)
        ]
        return Conversation(
            conversationId="c1",
            clusterId="base",
            material="SNS_REWRITE",
            skeletonId="sns-s1",
            system="system",
            messages=msgs,
            provenance={"writerModel": "fake", "requestRef": "ref", "flowBeats": beats_},
        )

    assert all(checks.evaluate(conv("주말에 산에 가자던 거 아직 유효해?"), spec).values())
    # 띄어쓰기·문장 부호를 바꿔도 10글자 이상 이어서 같으면 막는다.
    copied = checks.evaluate(conv("내일 아침에, 같이 등산 가기로 했잖아"), spec)
    assert copied["source_overlap"] is False
    assert checks.problems_of(copied)[0].startswith("source_overlap:")
    # 뼈대에 원문 문장을 넣어도 막는다.
    leak = beats[:2] + ["일곱 시 반에 역 앞에서 보자"]
    leaked = checks.evaluate(conv("주말 산행 유효해?", leak), spec)
    assert leaked["source_overlap"] is False
    # 메시지 수는 원본과 2개까지 다를 수 있다.
    assert checks.evaluate(conv("주말 산행 유효해?", extra=2), spec)["source_flow_turns"] is True
    assert checks.evaluate(conv("주말 산행 유효해?", extra=4), spec)["source_flow_turns"] is False
    said = [t["content"] for t in turns]
    assert checks.longest_overlap(["내일 아침에, 같이 등산 가기로"], said) == 12


def test_training_prompt_keeps_persona_and_drops_service_rules():
    """학습용 짧은 프롬프트: 페르소나 칸 + 사실 규칙 + 관계·채널(D-0138, 한소민 가이드 §3)."""
    from types import SimpleNamespace

    from character_factory_poc.stages.s9_data import training_prompt as tp

    text = "\n".join(
        [
            "[ACTOR_IDENTITY]",
            "캐릭터 이름: 가온",
            "",
            "[INPUT_AND_BOUNDARIES]",
            "서비스 공통 규칙 전문이다. " * 50,
            "",
            "[PERSONA / FACTS]",
            "가온은 29세 꽃집 사장이다.",
            "",
            "[PERSONA / CHOICES]",
            "상대가 놀릴 때 → 가온은 더 크게 받아친다. 상대가 진지하면 이 경향을 쓰지 않는다. "
            "대화 전체에서 드물게 나온다.",
            "",
            "[PERSONA / VOICE]",
            "해요체를 기본으로 쓴다.",
            "",
            "[OUTPUT]",
            "말만 쓴다.",
        ]
    )
    pair = SimpleNamespace(long=SimpleNamespace(text=text), short=SimpleNamespace(text=text))
    built = tp.build(pair)
    assert built.origin == "persona-sections"
    assert "서비스 공통 규칙" not in built.core and "[OUTPUT]" not in built.core
    assert "가온은 더 크게 받아친다." in built.core
    assert "이 경향을 쓰지 않는다" not in built.core and "드물게" not in built.core
    assert "[TRAINING_RULES]" in built.core
    system = built.system("NEUTRAL", "call")
    assert "[RELATIONSHIP]\n아직 가깝지 않은 상대다" in system
    assert "[CHANNEL]\n음성 통화다" in system
    legacy = tp.build(SimpleNamespace(long=SimpleNamespace(text="## 성격\n밝다"), short=None))
    assert legacy.origin == "legacy-short" and legacy.core == "## 성격\n밝다"
    shares = {"FAVORABLE": 0.45, "STRONGLY_FAVORABLE": 0.3, "NEUTRAL": 0.15, "UNFAVORABLE": 0.1}
    seq = tp.assign_relationships(shares, 0, 20)
    assert [seq.count(k) for k in shares] == [9, 6, 3, 2]
    assert tp.assign_relationships(shares, 5, 3) == seq[5:8]  # 배치가 나뉘어도 같은 순서


def test_writer_sees_seed_not_source_and_seeds_are_reused(tmp_path):
    """작가 입력에는 원문이 없고 시드만 있다. 시드는 한 번 뽑아 다시 쓴다(D-0138)."""
    from tests.support.data_fakes import _block

    write_sns(tmp_path / "sns.jsonl", count=4)
    toml = s9_toml(tmp_path, materials_base='["SNS_REWRITE"]')

    class Recorder(FakeWriterModel):
        batches: list = []

        def writer(self, req):
            self.batches.append(_block(req, "batch"))
            return super().writer(req)

    ctx, cid, fake = setup(tmp_path, toml=toml, fake=Recorder())
    rev_dir = samples.run_samples(ctx, cid)
    sent = [s for b in fake.batches for s in b.get("sources", [])]
    assert sent and all("turns" not in s and s["seed"]["beats"] for s in sent)
    assert all(b["assignments"] and b["turnMaxChars"] == 60 for b in fake.batches)
    saved = sorted((rev_dir / "seeds").glob("*.json"))
    assert saved and all("turns" not in json.loads(p.read_text("utf-8"))["seed"] for p in saved)
    assert json.loads((rev_dir / "training-prompt.json").read_text("utf-8"))["coreChars"] > 0
    calls = fake.seed_calls
    _all_select(ctx, cid, rev_dir)
    build.run_build(ctx, cid)
    sources = {s["sourceId"] for b in fake.batches for s in b.get("sources", [])}
    assert fake.seed_calls - calls <= len(sources)  # 이미 뽑은 시드는 다시 뽑지 않는다
    assert len(list((rev_dir / "seeds").glob("*.json"))) == len(sources)


def test_seed_check_rejects_copied_source_text():
    from character_factory_poc.stages.s9_data import seeds

    src = {
        "sourceId": "s1",
        "turns": [
            {"role": "user", "content": "내일 아침에 같이 등산 가기로 한 거 기억나?"},
            {"role": "assistant", "content": "응 당연하지"},
        ],
    }
    seed = {
        "sourceId": "s1",
        "scene": "퇴근길에 문자를 주고받는 저녁.",
        "counterpart": "상대: 같은 동네 친구.",
        "beats": ["상대가 약속을 확인한다", "캐릭터가 답한다", "시간을 정한다", "마무리한다"],
        "rhythm": "짧게 주고받는다.",
    }
    assert seeds.seed_problems(seeds.SeedOutput(seeds=[seed]), [src]) == []
    copied = {**seed, "beats": [*seed["beats"][:3], "내일 아침에 같이 등산 가기로 한다"]}
    assert seeds.seed_problems(seeds.SeedOutput(seeds=[copied]), [src])
    wrong = {**seed, "sourceId": "other"}
    assert seeds.seed_problems(seeds.SeedOutput(seeds=[wrong]), [src])


def test_somin_style_checks():
    """한소민 검사기에서 옮긴 항목: 한 턴 60자, 가까운 관계 '네,' 시작, 같은 말 반복, 경고 3종."""
    spec = checks.ConvSpec(
        cluster_id="base",
        system="system",
        material="SYNTH",
        relationship="FAVORABLE",
        turn_max_chars=60,
    )

    def conv(*replies: str, user: str = "오늘 뭐 해") -> Conversation:
        msgs = []
        for r in replies:
            msgs += [Message(role="user", content=user), Message(role="assistant", content=r)]
        return Conversation(
            conversationId="c1",
            clusterId="base",
            material="SYNTH",
            skeletonId="synth-1",
            system="system",
            messages=msgs,
            provenance={"writerModel": "fake", "requestRef": "ref"},
        )

    assert all(checks.evaluate(conv("가게 정리 중이야", "너는?"), spec).values())
    assert checks.evaluate(conv("가" * 61), spec)["turn_length"] is False
    assert checks.evaluate(conv("네, 정리 중이에요"), spec)["close_formal_opener"] is False
    neutral = checks.ConvSpec(**{**spec.__dict__, "relationship": "NEUTRAL"})
    assert checks.evaluate(conv("네, 정리 중이에요"), neutral)["close_formal_opener"] is True
    assert (
        checks.evaluate(conv("오늘 반죽 망했어", "오늘 반죽 망했어ㅋㅋ"), spec)["repeated_lines"]
        is False
    )
    busy = "오늘은 손님이 정말 많아서 하루 종일 정신이 하나도 없었어"
    warns = checks.style_warnings(conv(busy, busy + "!", busy + "?", "응", "좋아", user="뭐?"))
    assert len(warns) == 3
