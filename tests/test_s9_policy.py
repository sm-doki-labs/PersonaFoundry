"""S9 창작 인물 정책(qlora-authored-v1, D-0078): 6클러스터, long 턴 조건, 턴 분포, 보호 클러스터.

가짜 작성 모델로 네트워크 없이 돈다. 공용 FakeWriterModel은 모든 대화를 2턴으로 쓰므로, long
클러스터 조건을 맞추는 하위 클래스를 이 파일에 둔다.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.schema import validate
from character_factory_poc.contracts.dataset import (
    ClusterPlan,
    Conversation,
    DataPlan,
    Message,
)
from character_factory_poc.stages.s9_data import build, checks, plan, samples
from character_factory_poc.stages.s9_data import policy as policy_mod
from character_factory_poc.stages.s9_data.approve import approve_g7a
from tests.support.data_fakes import (
    WORDS,
    FakeWriterModel,
    _block,
    make_s9_ctx,
    s9_toml,
    through_g6,
)

POLICY_LINE = 'policy = "qlora-authored-v1"\n'
POLICY_IDS = ["base", "situation", "history", "ownership", "conflict", "long"]


def policy_toml(root: Path, **kw) -> str:
    return s9_toml(root, **kw).replace("[stages.s9]\n", "[stages.s9]\n" + POLICY_LINE, 1)


class LongFakeWriter(FakeWriterModel):
    """batch.turnRule이 오면 그 하한 턴 수와 위치 표시를 지킨 긴 대화를 쓴다."""

    def __init__(self, *, one_skeleton: str = "", **kw):
        super().__init__(**kw)
        self.one_skeleton = one_skeleton

    def writer(self, req):
        batch = _block(req, "batch")
        rule = batch.get("turnRule")
        if not rule:
            out = super().writer(req)
            if batch["clusterId"] == self.one_skeleton:
                for item in out["conversations"]:
                    item["skeletonKey"] = "one-scene"
            return out
        items = []
        for _ in range(batch["count"]):
            self.n += 1
            items.append(self._long_item(self.n, rule))
        return {"conversations": items}

    def _long_item(self, n: int, rule: dict) -> dict:
        turns = rule["minAssistantTurns"]
        messages = []
        for t in range(turns):
            word = WORDS[(n + t) % 10]
            messages.append({"role": "user", "content": f"{n}-{t} 이번엔 {word} 얘기 해 볼래?"})
            messages.append(
                {"role": "assistant", "content": f"{word}라면 {n}번 대화 {t}턴째에 좋지."}
            )
        total = len(messages)
        start = math.ceil(total * rule["lateTriggerFromShare"])
        start += start % 2
        return {
            "skeletonKey": f"long-{n}",
            "scene": f"{WORDS[n % 10]} 근처에서 오래 문자를 주고받는 밤.",
            "sourceId": "",
            "messages": messages,
            "topicShiftAt": [4, 10],
            "lateTriggerAt": [start, start + 2],
        }


def setup(tmp_path: Path, toml: str, fake: FakeWriterModel | None = None):
    ctx, model = make_s9_ctx(tmp_path, toml, fake)
    cid = through_g6(ctx, tmp_path)
    model.cid = cid
    return ctx, cid, model


def all_select(ctx, cid, rev_dir: Path) -> None:
    for cluster in plan.plan_cluster_ids(rev_dir):
        sample = json.loads((rev_dir / "samples" / f"{cluster}.json").read_text("utf-8"))
        ids = [ref["ref"].split("/")[-1][: -len(".json")] for ref in sample["conversations"]]
        approve_g7a(
            ctx,
            cid,
            {
                "decision": "SELECT",
                "cluster": cluster,
                "verdicts": dict.fromkeys(ids, "ADOPT"),
                "reviewer": "user",
            },
        )


def plan_from_cfg(cfg: plan.S9Config) -> DataPlan:
    targets = plan.cluster_targets(cfg.target, cfg.shares)
    return DataPlan(
        characterId="cf-test",
        personaVersion="pv1",
        promptPairSha256="0" * 64,
        targetTrainConversations=cfg.target,
        clusters=[
            ClusterPlan(
                clusterId=c,
                label=cfg.labels[c],
                share=cfg.shares[c],
                targetConversations=targets[c],
                materials=list(cfg.materials[c]),
                sampleSize=cfg.sample_size,
                policy=cfg.cluster_policies.get(c),
            )
            for c in cfg.cluster_ids
        ],
        guideRef=cfg.guide_ref,
        writerModel="fake",
        policy=cfg.plan_policy,
    )


def conv(cid: str, cluster: str, turns: int, reply: str = "응 좋아") -> Conversation:
    messages = []
    for t in range(turns):
        messages += [
            Message(role="user", content=f"{cid} 질문 {t}"),
            Message(role="assistant", content=f"{reply} {t}"),
        ]
    return Conversation(
        conversationId=cid,
        clusterId=cluster,
        material="SYNTH",
        skeletonId=f"sk-{cid}",
        system="system",
        messages=messages,
        provenance={"writerModel": "fake", "requestRef": "ref"},
    )


def test_policy_plan_writes_six_clusters_with_sources(tmp_path):
    ctx, cid, _fake = setup(tmp_path, "[stages.s9]\n" + POLICY_LINE)
    rev_dir = plan.run_plan(ctx, cid)
    p = validate("data-plan-v1", json.loads((rev_dir / "plan.json").read_text("utf-8")))
    assert [c.clusterId for c in p.clusters] == POLICY_IDS
    shares = {c.clusterId: c.share for c in p.clusters}
    assert shares["base"] == 0.51 and shares["long"] == 0.05
    targets = {c.clusterId: c.targetConversations for c in p.clusters}
    assert targets == {
        "base": 326,
        "situation": 51,
        "history": 141,
        "ownership": 45,
        "conflict": 45,
        "long": 32,
    }
    by_id = {c.clusterId: c for c in p.clusters}
    assert by_id["long"].label.startswith("긴 대화")
    assert by_id["base"].materials == ["SNS_REWRITE", "SYNTH"]
    assert by_id["long"].materials == ["SYNTH"]
    assert any("stitch" in n for n in by_id["long"].policy.materialNotes)
    assert [c.clusterId for c in p.clusters if c.policy.protected] == POLICY_IDS[1:]
    base_pol = by_id["base"].policy
    assert base_pol.shareSource == "proposal" and "운영 시작값" in base_pol.shareNote
    assert "D-0045" in by_id["history"].policy.shareSource
    assert by_id["long"].policy.minShare == 0.05
    assert by_id["long"].policy.minShareSource.endswith("(15턴 이상 5% 이상)")
    rule = by_id["long"].policy.turnRule
    assert (rule.minAssistantTurns, rule.maxAssistantTurns) == (15, 30)
    assert rule.minTopicShifts == 2 and rule.minLateTriggers == 2
    assert "longDialogueMinTurns" in rule.sources["minAssistantTurns"]
    assert by_id["base"].policy.turnRule is None

    assert p.policy.name == "qlora-authored-v1"
    assert p.policy.status == "draft_proposal"
    assert len(p.policy.policySha256) == 64
    assert "clusters.base.targetShare" in p.policy.proposalValues
    assert "clusters.long.targetShare" in p.policy.proposalValues
    assert "dataset.protectedAnchors.minSurvivalRatio" in p.policy.proposalValues
    assert any("운영 시작값" in n for n in p.policy.notes)
    keys = [t.key for t in p.policy.turnTargets]
    assert keys[:5] == ["1-4", "5-9", "10-14", "15-19", "20-30"]
    assert {"maxTurns", "supervisedTokenShareTurnsGe10"} <= set(keys)
    assert "qlora-authored" in p.guideRef


def test_policy_share_override_records_config_source(tmp_path):
    toml = "[stages.s9]\n" + POLICY_LINE + "[stages.s9.shares]\nbase = 0.50\nlong = 0.06\n"
    ctx, cid, _fake = setup(tmp_path, toml)
    p = plan.build_plan(ctx, cid)
    long_pol = next(c for c in p.clusters if c.clusterId == "long").policy
    assert long_pol.shareSource.startswith("config:[stages.s9.shares].long")
    toml_bad = "[stages.s9]\n" + POLICY_LINE + "[stages.s9.shares]\nunknown = 0.1\n"
    (tmp_path / "factory.toml").write_text(toml_bad, encoding="utf-8")
    ctx2, _ = make_s9_ctx(tmp_path, toml_bad)
    with pytest.raises(CheckFailed):
        plan.s9_config(ctx2)


def test_without_policy_plan_keeps_five_clusters(tmp_path):
    ctx, cid, _fake = setup(tmp_path, '[stages.s2]\nbase_photo = "picked"\n')
    rev_dir = plan.run_plan(ctx, cid)
    p = validate("data-plan-v1", json.loads((rev_dir / "plan.json").read_text("utf-8")))
    assert [c.clusterId for c in p.clusters] == list(plan.CLUSTERS)
    assert {c.clusterId: c.share for c in p.clusters} == plan.DEFAULT_SHARES
    assert p.policy is None and all(c.policy is None for c in p.clusters)


def test_long_turn_floor_violation_is_detected(tmp_path):
    ctx, _ = make_s9_ctx(tmp_path, policy_toml(tmp_path))
    cfg = plan.s9_config(ctx)
    rule = cfg.turn_rule("long")
    spec = checks.ConvSpec(cluster_id="long", system="system", material="SYNTH", turn_rule=rule)
    short = conv("l1", "long", 3)
    assert checks.evaluate(short, spec)["turn_range"] is False
    assert any(p.startswith("turn_range") for p in checks.conversation_problems(short, spec))
    ok = conv("l2", "long", 15)
    assert checks.evaluate(ok, spec)["turn_range"] is True
    too_long = conv("l3", "long", 31)
    assert checks.evaluate(too_long, spec)["turn_range"] is False
    # Clusters without a turn rule keep the old blocking keys.
    base_spec = checks.ConvSpec(cluster_id="base", system="system", material="SYNTH")
    assert "turn_range" not in checks.evaluate(short, base_spec)

    written = {
        "scene": "긴 밤 문자를 주고받는 저녁.",
        "messages": [m.model_dump() for m in ok.messages],
    }
    problems = checks.batch_problems([written], [spec], "system")
    assert any("long_structure" in p for p in problems)
    marked = {**written, "topicShiftAt": [4, 10], "lateTriggerAt": [16, 20]}
    assert checks.batch_problems([marked], [spec], "system") == []
    early = {**written, "topicShiftAt": [4, 10], "lateTriggerAt": [2, 16]}
    assert any("lateTriggerAt" in p for p in checks.batch_problems([early], [spec], "system"))

    p = plan_from_cfg(cfg)
    items = policy_mod.conversation_items(p, [short, ok, conv("b1", "base", 2)])
    assert [(i["check"], i["conversationId"]) for i in items] == [("long_turn_range", "l1")]


def test_shared_fake_writer_satisfies_long_cluster_under_policy(tmp_path):
    ctx, cid, _fake = setup(tmp_path, policy_toml(tmp_path))
    rev_dir = samples.run_samples(ctx, cid)
    long_sample = json.loads((rev_dir / "samples" / "long.json").read_text("utf-8"))
    assert long_sample["conversations"]


def test_turn_distribution_verdicts_and_warnings(tmp_path):
    ctx, _ = make_s9_ctx(tmp_path, policy_toml(tmp_path))
    cfg = plan.s9_config(ctx)
    p = plan_from_cfg(cfg)
    train = (
        [conv(f"a{i}", "base", 2) for i in range(3)]
        + [conv(f"b{i}", "history", 6) for i in range(5)]
        + [conv("c0", "conflict", 12)]
        + [conv("d0", "long", 25)]
    )
    rep = policy_mod.evaluate(p, train, train, cfg)
    rows = {r["key"]: r for r in rep.turn_distribution["rows"]}
    assert rows["1-4"]["observed"] == 0.3 and rows["1-4"]["verdict"] == "PASS"
    assert rows["5-9"]["verdict"] == "PASS"
    assert rows["10-14"]["verdict"] == "PASS"
    assert rows["15-19"]["observed"] == 0 and rows["15-19"]["verdict"] == "OUT_OF_RANGE"
    assert rows["20-30"]["observed"] == 0.1 and rows["20-30"]["verdict"] == "OUT_OF_RANGE"
    assert rows["maxTurns"]["observed"] == 25 and rows["maxTurns"]["verdict"] == "PASS"
    share = rows["supervisedTokenShareTurnsGe10"]
    assert share["approximate"] is True and share["verdict"] in {"PASS", "OUT_OF_RANGE"}
    assert all(r["blocking"] is False for r in rows.values())
    assert any("15-19" in w for w in rep.warnings)
    assert not [b for b in rep.blocking if b["check"] != "protected_cluster_survival"]

    undecided = p.policy.model_copy(
        update={
            "turnTargets": [
                t.model_copy(update={"min": None, "max": None}) if t.key == "5-9" else t
                for t in p.policy.turnTargets
            ]
        }
    )
    rep2 = policy_mod.evaluate(p.model_copy(update={"policy": undecided}), train, train, cfg)
    rows2 = {r["key"]: r for r in rep2.turn_distribution["rows"]}
    assert rows2["5-9"]["verdict"] == "UNKNOWN"
    assert any("UNKNOWN" in w and "5-9" in w for w in rep2.warnings)

    shares = rep.cluster_shares
    assert shares["supervisedTokens"]["approximate"] is True
    assert shares["denominators"]["conversations"] == 10
    by_id = {r["clusterId"]: r for r in shares["rows"]}
    assert by_id["history"]["conversationShare"] == 0.5
    assert by_id["history"]["replies"] == 30
    assert by_id["long"]["verdict"] == "PASS"  # minShare 0.05, observed 0.1
    assert by_id["base"]["verdict"] == "UNKNOWN"
    assert by_id["base"]["targetShareSource"] == "proposal"
    assert any("허용 폭 미정" in w for w in rep.warnings)


def test_protected_cluster_loss_blocks(tmp_path):
    ctx, _ = make_s9_ctx(tmp_path, policy_toml(tmp_path, target=40))
    cfg = plan.s9_config(ctx)
    p = plan_from_cfg(cfg)
    targets = {c.clusterId: c.targetConversations for c in p.clusters}
    assert targets["history"] == 9
    convs = [conv(f"h{i}", "history", 6) for i in range(9)]
    rows, blocking, _w = policy_mod.protected_survival(p, convs, convs[:7], {"history": ["h0"]})
    hist = next(r for r in rows if r["clusterId"] == "history")
    assert hist["minimumTrain"] == 9 and hist["verdict"] == "BLOCKED"
    assert any(
        b["check"] == "protected_cluster_survival" and b["conversationId"] == "cluster:history"
        for b in blocking
    )
    rows_ok, blocking_ok, _ = policy_mod.protected_survival(p, convs, convs, {})
    assert next(r for r in rows_ok if r["clusterId"] == "history")["verdict"] == "PASS"
    assert not any(b["conversationId"] == "cluster:history" for b in blocking_ok)


def test_protected_cluster_dropped_by_split_blocks_build(tmp_path):
    fake = LongFakeWriter(one_skeleton="history")
    ctx, cid, _ = setup(tmp_path, policy_toml(tmp_path), fake)
    rev_dir = samples.run_samples(ctx, cid)
    all_select(ctx, cid, rev_dir)
    with pytest.raises(CheckFailed) as err:
        build.run_build(ctx, cid)
    assert "protected_cluster_survival" in str(err.value)
    assert ctx.state(cid).stage("s9").status == "CHECK_FAILED"
    report = json.loads((rev_dir / "check-report.json").read_text("utf-8"))
    assert any(b["check"] == "protected_cluster_survival" for b in report["blocking"])
    assert not (rev_dir / "dataset.json").exists()


def test_policy_flow_reports_turns_and_three_denominators(tmp_path):
    ctx, cid, fake = setup(tmp_path, policy_toml(tmp_path), LongFakeWriter())
    assert len(samples.plan_calls(ctx, cid)[0].description) > 0
    rev_dir = samples.run_samples(ctx, cid)
    assert set(plan.plan_cluster_ids(rev_dir)) == set(POLICY_IDS)
    long_handoff = [r for r in fake.requests if '"clusterId": "long"' in r.messages[-1].content]
    assert any('"turnRule"' in r.messages[-1].content for r in long_handoff)
    index = (rev_dir / "gate-G7a.html").read_text("utf-8")
    assert "운영 시작값(proposal)" in index
    assert "턴 조건" in (rev_dir / "gate-G7a-long.html").read_text("utf-8")
    all_select(ctx, cid, rev_dir)
    assert ctx.state(cid).gate("G7a").status == "APPROVED"

    out = build.run_build(ctx, cid)
    dataset = validate("dataset-rev-v2", json.loads((out / "dataset.json").read_text("utf-8")))
    assert dataset.blockingFailures == 0
    assert set(dataset.clusterCounts) == set(POLICY_IDS)
    rows = [json.loads(ln) for ln in (out / "index.jsonl").read_text("utf-8").splitlines()]
    long_rows = [r for r in rows if r["clusterId"] == "long"]
    assert long_rows and all(r["replies"] >= 15 for r in long_rows)
    one = validate("conversation-v1", json.loads((out / long_rows[0]["path"]).read_text("utf-8")))
    assert one.checks.blocking["turn_range"] and one.checks.blocking["long_structure"]

    report = json.loads((out / "check-report.json").read_text("utf-8"))
    pol = report["policy"]
    assert pol["name"] == "qlora-authored-v1"
    verdicts = {r["key"]: r["verdict"] for r in pol["turnDistribution"]["rows"]}
    assert set(verdicts.values()) <= {"PASS", "OUT_OF_RANGE", "UNKNOWN"}
    assert "1-4" in verdicts and "maxTurns" in verdicts
    assert {r["clusterId"] for r in pol["protectedClusters"]} == set(POLICY_IDS[1:])
    assert all(r["verdict"] == "PASS" for r in pol["protectedClusters"])
    shares = report["clusterShares"]
    assert shares["supervisedTokens"]["approximate"] is True
    first = shares["rows"][0]
    assert {"conversationShare", "replyShare", "supervisedTokenShareApprox"} <= set(first)
    assert dataset.warnings >= len(pol["warnings"])

    page = (out / "gate-G7.html").read_text("utf-8")
    for text in ("턴 분포 (학습 분할)", "세 분모", "보호 클러스터 생존", "운영 시작값(proposal)"):
        assert text in page
