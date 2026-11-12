"""순서 8: 합성 장면, 오프라인 모델, 원문 경계와 가족 판정 왕복."""

import json
from dataclasses import replace
from html.parser import HTMLParser

import pytest

from character_factory_poc.common.config import BudgetConfig, ProviderConfig
from character_factory_poc.common.errors import BudgetExceeded, FactoryError
from character_factory_poc.common.schema import validate
from character_factory_poc.common.store import read_json, verify_manifest, write_once_json
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.origin import write_model_mode
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.model_prep.bind import import_binding
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from character_factory_poc.stages.s9h_holdout import run as holdout
from character_factory_poc.stages.s10_eval import blind, compare, judge, prereg, report
from character_factory_poc.stages.s10_eval.twin import run_s10_twin
from tests.test_model_prep import Hub, _path
from tests.test_s10_eval import (
    FakeChat,
    JudgeResponder,
    _g7_and_training,
    _prompt_pair,
    _synthetic_runs,
)
from tests.test_twin_s3 import CANARY, _ready

VOICE = "이 동그란 연필은 손으로 종이를 접을 때 쓰는 연필입니다."
TRAIN_LINE = "학습 전용인 줄무늬 주전자에 파란 종이를 넣어 두었어요."
ACTUAL = [CANARY, "종이별 하나면 돼요.", "여기 있어요.", "파란색으로 해요."]


def _setup(tmp, monkeypatch, mode):
    ctx, _, cid = _ready(tmp)
    char = ctx.character_dir(cid)
    write_model_mode(char, mode)
    if mode == "TRAIN":
        run_s3_twin(ctx, cid)
        approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "u"})
    _prompt_pair(ctx, cid)
    write_once_json(
        char / "s8-prompts/pv1/source-plan.json", {"sourceVoice": {"examples": [{"quote": VOICE}]}}
    )
    rows = []
    for i, a in enumerate(ACTUAL):
        for j, (role, text) in enumerate(
            [
                ("OTHER", "[참여자1] 메모"),
                ("SUBJECT", "앞서 한 말"),
                ("USER", f"합성 질문 {i} <script>bad()</script>"),
                ("SUBJECT", a),
            ]
        ):
            rows.append(
                dict(
                    convId=f"c{i}",
                    msgId=f"m{i}-{j}",
                    speaker=role,
                    text=text,
                    name="보이면 안 되는 이름",
                )
            )
    monkeypatch.setattr(holdout, "load_holdout", lambda *_: rows)
    holdout.run_s9h(ctx, cid)
    ctx.config.providers.update(
        text=ProviderConfig(model="base-model"), judge=ProviderConfig(model="anthropic/claude")
    )
    long = (char / "s8-prompts/pv1/long.md").read_text()
    text = FakeTextModel("base-model", {"EVAL": [ACTUAL[0], VOICE, long[:28], TRAIN_LINE]})
    voter = FakeTextModel("anthropic/claude", {"JUDGE": {"pick": "A"}})
    ctx.use_models(text, voter)
    if mode == "BIND_EXISTING":
        import_binding(ctx, cid, _path(tmp), client=Hub())
    return ctx, cid, text, voter


class Ballot(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.groups = {}
        self.ballot = ""
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "form":
            self.ballot = d["data-ballot"]
        if tag == "input":
            assert d["type"] == "radio" and "required" in d
            self.groups.setdefault(d["name"], []).append(d["value"])


def test_prompt_comparison_blind_round_trip_and_privacy(tmp_path, monkeypatch):
    ctx, cid, text, voter = _setup(tmp_path, monkeypatch, "PROMPT_ONLY")
    folder = run_s10_twin(ctx, cid)
    doc = validate("twin-comparison-v1", read_json(folder / blind.BASE))
    (c,) = doc.conditions
    assert doc.sceneCount == 4 and c.modelScore.rate == 0.5 and c.humanScore.rate is None
    assert c.trials[0].exact and not c.trials[0].overlap
    assert not c.trials[1].exact and c.trials[1].overlap == ["VOICE"]
    assert c.trials[2].overlap == ["PROMPT"] and not c.trials[3].overlap
    assert sorted(t.blindActual for t in c.trials) == list("AABB")
    for i, (gen, j, t) in enumerate(zip(text.requests, voter.requests, c.trials, strict=True)):
        assert [(m.role, m.content) for m in gen.messages[1:]] == [
            ("user", "[다른 참여자] [참여자1] 메모"),
            ("assistant", "앞서 한 말"),
            ("user", f"합성 질문 {i} <script>bad()</script>"),
        ]
        payload = json.loads(j.messages[1].content)
        assert set(payload) == {"context", "user", "A", "B"} and payload[t.modelActual] == ACTUAL[i]
    page = (folder / f"twin-blind-{c.ballot}.html").read_text()
    demo = (folder / f"twin-demo-{c.ballot}.html").read_text()
    assert all(
        v not in page
        for v in ("blindActual", "LONG_BASE", "twin-demo", "<script>bad()", "보이면 안 되는 이름")
    )
    assert all(
        v in demo for v in ("AI 생성 · 본인과 무관한 기술 시연", "정답과 같음: 예", "말투 예시")
    )
    form = Ballot(page)
    assert all(v == ["A", "B"] for v in form.groups.values())
    answers = dict(ballot=form.ballot, picks={t.pairId: t.blindActual for t in c.trials})
    assert set(form.groups) == set(answers["picks"])
    path = tmp_path / "answers.json"
    for invalid in [
        dict(answers, ballot="다른 판"),
        dict(answers, picks={}),
        dict(answers, picks=dict.fromkeys(form.groups, "TIE")),
    ]:
        path.write_text(json.dumps(invalid))
        with pytest.raises(FactoryError):
            blind.import_blind_answers(ctx, cid, path)
    path.write_text(json.dumps(answers))
    updated = read_json(blind.import_blind_answers(ctx, cid, path))["conditions"][0]
    assert updated["humanScore"]["rate"] == 1 and updated["modelScore"]["rate"] == 0.5
    assert run_s10_twin(ctx, cid) == folder and len(text.requests) == len(voter.requests) == 4
    gate = (folder / "gate-G8.html").read_text()
    assert (
        "모델 구별률: 2/4" in gate and "사람 구별률: 4/4" in gate and gate.count(blind.START) == 1
    )
    approve_gate(ctx, cid, "G8", {"decision": "SELECT", "adopted": "LONG_BASE"})
    char = ctx.character_dir(cid)
    refs = {r["ref"] for r in read_json(char / "gates/G8-ev1.json")["shownArtifacts"]}
    assert f"s10-eval/ev1/{blind.REVIEWED}" in refs
    with pytest.raises(FactoryError, match="열린"):
        blind.import_blind_answers(ctx, cid, path)
    assert verify_manifest(folder) == []
    for p in char.rglob("*"):
        if (
            p.is_file()
            and (p.parent != folder or p.suffix != ".html")
            and p.name not in ("holdout.jsonl", "scenes.jsonl")
        ):
            assert CANARY.encode() not in p.read_bytes(), p


@pytest.mark.parametrize("served", [True, False])
def test_binding_uses_named_route_or_reports_missing(tmp_path, monkeypatch, served):
    ctx, cid, text, voter = _setup(tmp_path, monkeypatch, "BIND_EXISTING")
    routed = FakeTextModel("bound-model", {"EVAL": "다른 답"})
    if served:
        ctx.config.providers["test-route"] = ProviderConfig(model=routed.model)

        def factory(cfg):
            assert cfg.model == routed.model
            return routed

        monkeypatch.setattr(compare, "make_text_model", factory)
    assert sum(p.calls for p in compare.plan_calls(ctx, cid)) == (16 if served else 8)
    folder = run_s10_twin(ctx, cid)
    base, sft = read_json(folder / blind.BASE)["conditions"]
    assert base["status"] == "COMPLETE" and sft["status"] == (
        "COMPLETE" if served else "NO_SERVING"
    )
    assert len(text.requests) == 4 and len(routed.requests) == (4 if served else 0)
    assert len(voter.requests) == len(text.requests) + len(routed.requests)
    for a, b in zip(text.requests, routed.requests, strict=False):
        assert a.messages[1:] == b.messages[1:] and a.messages[0] != b.messages[0]
    if not served:
        assert "서빙 없음" in (folder / "gate-G8.html").read_text()


def test_skip_setting_opens_g8_without_comparison_calls(tmp_path, monkeypatch):
    """[stages.s10] comparison = "skip": 호출 없이 G8을 열고 평가 생략을 남긴다(D-0187)."""
    ctx, cid, text, voter = _setup(tmp_path, monkeypatch, "PROMPT_ONLY")
    ctx.config.stages["s10"] = {"comparison": "skip"}
    assert compare.plan_calls(ctx, cid) == []
    folder = run_s10_twin(ctx, cid)
    (c,) = read_json(folder / blind.BASE)["conditions"]
    assert c["status"] == "SKIPPED" and not c["trials"]
    assert not text.requests and not voter.requests
    assert "평가 생략" in (folder / "gate-G8.html").read_text()
    assert ctx.state(cid).gate("G8").status == "AWAITING_HUMAN"
    ctx.config.stages["s10"] = {"comparison": "maybe"}
    with pytest.raises(FactoryError, match="comparison"):
        compare.build_comparison(ctx, cid, tmp_path / "other")


def test_dry_plan_budget_and_independent_judge_before_calls(tmp_path, monkeypatch):
    ctx, cid, text, voter = _setup(tmp_path, monkeypatch, "PROMPT_ONLY")
    ctx.execute = False
    folder = run_s10_twin(ctx, cid)
    assert not text.requests and not voter.requests and not (folder / blind.BASE).exists()
    assert read_json(folder / blind.PLAN)["plannedCalls"] == 8
    ctx.execute = True
    ctx.max_calls = 7
    with pytest.raises(BudgetExceeded):
        run_s10_twin(ctx, cid)
    ctx.max_calls = 8
    ctx.config.providers["judge"] = ProviderConfig(model="base-same-family")
    with pytest.raises((ValueError, FactoryError), match="계열"):
        run_s10_twin(ctx, cid)
    ctx.config.providers["judge"] = ProviderConfig(adapter="openai_compat", model=voter.model)
    with pytest.raises(FactoryError, match="comparison_call_usd_upper"):
        run_s10_twin(ctx, cid)
    ctx.config.stages["s10"] = {"comparison_call_usd_upper": 6}
    with pytest.raises(BudgetExceeded):
        run_s10_twin(ctx, cid)
    assert not text.requests and not voter.requests
    ctx.config.providers["judge"] = ProviderConfig(model=voter.model)
    assert run_s10_twin(ctx, cid) == folder and (folder / blind.BASE).is_file()


def test_provider_error_cannot_copy_holdout_into_stage_history(tmp_path, monkeypatch):
    ctx, cid, _, voter = _setup(tmp_path, monkeypatch, "PROMPT_ONLY")

    def echo_error(req):
        raise RuntimeError(req.messages[-1].content)

    voter.add("JUDGE", echo_error)
    with pytest.raises(FactoryError, match="모델 호출 실패") as error:
        run_s10_twin(ctx, cid)
    assert CANARY not in str(error.value)
    assert ctx.state(cid).stage("s10").status == "CHECK_FAILED"
    assert not list((ctx.character_dir(cid) / "s10-eval").rglob("*.html"))


def test_train_appends_without_replacing_existing_g8(tmp_path, monkeypatch):
    ctx, cid, text, voter = _setup(tmp_path, monkeypatch, "TRAIN")
    char = ctx.character_dir(cid)
    ctx.config = replace(ctx.config, budget=BudgetConfig(max_calls_per_command=20000))
    _g7_and_training(ctx, cid)
    data = char / "s9-data/ds1/train.jsonl"
    data.parent.mkdir(parents=True)
    data.write_text(json.dumps({"messages": [{"role": "assistant", "content": TRAIN_LINE}]}) + "\n")
    build = prereg.build_prereg(ctx, cid)
    _synthetic_runs(ctx, cid, build)
    voter.add("JUDGE", JudgeResponder())
    judge.run_judge(ctx, cid)
    folder = report.build_report(ctx, cid)
    before = (folder / "report.json").read_bytes()
    voter.add("JUDGE", {"pick": "A"})
    sft = FakeChat("gemma-r1", "모델 답")
    compare.append_twin_comparison(ctx, cid, models={"gemma-r1": sft})
    doc = read_json(folder / blind.BASE)
    assert [c["status"] for c in doc["conditions"]] == ["COMPLETE", "COMPLETE", "NO_SERVING"]
    assert doc["conditions"][0]["trials"][3]["overlap"] == ["TRAIN"] and len(sft.calls) == 4
    assert (folder / "report.json").read_bytes() == before
    pairs = read_json(folder / "pairs.json")
    approve_gate(
        ctx,
        cid,
        "G8",
        {
            "decision": "SELECT",
            "adopted": "gemma-r1",
            "humanPicks": [{"pairId": pid, "pick": "A"} for pid in pairs["humanPairIds"]],
        },
    )
    assert "모티브 비교 평가" in (folder / "gate-G8.html").read_text()
    assert (folder / "report-final.json").exists() and verify_manifest(folder) == []
    assert any(
        r["ref"].endswith(blind.BASE)
        for r in read_json(char / "gates/G8-ev1.json")["shownArtifacts"]
    )
