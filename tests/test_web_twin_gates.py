"""모티브 관문 화면 API 테스트: G0 출처 확인, G1s 기준 사진, 모티브 G8 비교 요약.

합성 출처(테스트가 만든 카톡 형식 문장·단색 사진)와 가짜 공급자만 쓴다. 실존 인물·실제 대화는 없다.
비교 세트 원문은 관문 화면 응답·파일 목록·파일 열기 어디에도 나오지 않아야 한다(D-0120).

결정 경로: 지금 app.py의 결정 API는 reads.known_gates()(오리지널 관문)만 받는다. 모티브 관문 결정은
reads.decision_gates()로 바꿔야 열리므로, 여기서는 그 연결을 monkeypatch로 붙여 화면이 만드는 답
모양이 기존 approve 경로를 그대로 통과하는지 확인한다.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.common.config import BudgetConfig
from character_factory_poc.common.store import read_json
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.fake_vision import FakeVisionModel
from character_factory_poc.stages.s0_source.run import read_jsonl, run_s0
from character_factory_poc.stages.s2_hero.twin import run_s2_twin
from character_factory_poc.stages.s10_eval import blind, compare, judge, prereg, report
from character_factory_poc.stages.s10_eval.twin import run_s10_twin
from character_factory_poc.web import create_app, reads
from tests.test_s10_eval import FakeChat, JudgeResponder, _g7_and_training, _synthetic_runs
from tests.test_source_s0 import _good_digest, _twin, _write_pack
from tests.test_twin_comparison import ACTUAL, TRAIN_LINE, _setup
from tests.test_twin_s2 import _source

CID = "cf-20261108-twin"
# 합성 카톡에서 날짜가 가장 늦은 대화(비교 세트로 떼는 대화)에만 있는 문구.
HOLDOUT_ONLY = ("5번째 이야기", "뭐해 5")


@pytest.fixture
def twin_decisions(monkeypatch):
    """app.py가 reads.decision_gates()를 쓰게 되면 이 연결은 그대로 둬도 같다."""
    gates = reads.decision_gates()
    monkeypatch.setattr(reads, "known_gates", lambda: gates)


def _client(root: Path) -> TestClient:
    return TestClient(create_app(root))


def _view(client: TestClient, cid: str, gate: str) -> dict:
    res = client.get(f"/api/characters/{cid}/gates/{gate}")
    assert res.status_code == 200, res.text
    return res.json()


def _s0(tmp_path: Path, *, consent: bool = True) -> tuple[Context, str, Path]:
    ctx = Context.load(tmp_path, execute=True)
    text = FakeTextModel()
    text.add("AGENT", _good_digest)
    ctx.use_models(text)
    cid = _twin(ctx, CID)
    folder = run_s0(ctx, cid, _write_pack(tmp_path, consent=consent))
    return ctx, cid, folder


def test_g0_view_shows_source_summary_without_holdout_text(tmp_path, twin_decisions):
    ctx, cid, folder = _s0(tmp_path)
    held = read_jsonl(folder / "holdout.jsonl")
    subject = [r["text"] for r in held if r["speaker"] != "OTHER"]
    assert subject and all(any(s in t for s in HOLDOUT_ONLY) for t in subject)
    with _client(tmp_path) as client:
        view = _view(client, cid, "G0")
        raw = json.dumps(view, ensure_ascii=False)
        assert all(s not in raw for s in HOLDOUT_ONLY)
        assert "holdout.jsonl" not in raw
        hidden = client.get(f"/api/files/{cid}/s0-source/{view['rev']}/holdout.jsonl")
        assert hidden.status_code == 403
        assert all(s not in hidden.text for s in HOLDOUT_ONLY)
        items = view["items"]
        assert view["kind"] == "sourcePack" and view["origin"] == "SOURCE"
        assert view["decisions"] == ["APPROVE", "REQUEST_CHANGES", "REJECT"]
        assert view["missing"] == [] and view["status"] == "AWAITING_HUMAN"
        assert items["counts"]["holdoutConversations"] == 1
        assert items["counts"]["conversations"] == 6
        assert items["masked"]["phone"] == 1 and items["masked"]["email"] == 1
        assert items["usageProblems"] == [] and items["usage"]["consentBy"]
        assert items["texts"][0]["subjectSpeaker"] == "엄마"
        assert items["texts"][0]["userSpeaker"] == "나"
        assert items["agent"]["speakerCheck"]["confirmed"] is True
        reps = items["agent"]["representative"]
        assert reps and all(r["text"] for r in reps)
        assert items["photos"] == {"count": 1, "origins": ["가족 사진"]}
        answer = {
            "decision": "APPROVE",
            "reviewer": "u",
            "minutes": 1,
            "reasons": "",
            "expectedRev": view["rev"],
        }
        res = client.post(f"/api/characters/{cid}/gates/G0/decision", json=answer)
        assert res.status_code == 200, res.text
    assert ctx.state(cid).gate("G0").status == "APPROVED"


def test_g0_usage_lock_and_change_request(tmp_path, twin_decisions):
    ctx, cid, _ = _s0(tmp_path, consent=False)
    with _client(tmp_path) as client:
        view = _view(client, cid, "G0")
        assert len(view["items"]["usageProblems"]) == 2
        url = f"/api/characters/{cid}/gates/G0/decision"
        res = client.post(url, json={"decision": "APPROVE", "reviewer": "u"})
        assert res.status_code == 409 and "사용 근거" in res.text
        res = client.post(
            url,
            json={
                "decision": "REQUEST_CHANGES",
                "reviewer": "u",
                "reasons": "동의 날짜를 채워 주세요",
                "requestedChanges": [{"field": "source", "note": "동의 날짜를 채워 주세요"}],
            },
        )
        assert res.status_code == 200, res.text
    record = read_json(ctx.character_dir(cid) / ctx.state(cid).gate("G0").recordRef)
    assert record["requestedChanges"] == [{"field": "source", "note": "동의 날짜를 채워 주세요"}]


def test_g1s_view_lists_source_photos_and_select(tmp_path, twin_decisions):
    (tmp_path / "factory.toml").write_text('[stages.s5]\nfirst_frame = "hero"\n')
    ctx = Context.load(tmp_path, execute=True)
    text = FakeTextModel()
    text.add("AGENT", _good_digest)
    ctx.use_models(text)
    ctx.use_vision(FakeVisionModel(responder=lambda req: {"faceShape": "oval"}))
    _twin(ctx, CID)
    _source(ctx, tmp_path)
    run_s2_twin(ctx, CID)
    with _client(tmp_path) as client:
        view = _view(client, CID, "G1s")
        raw = json.dumps(view, ensure_ascii=False)
        # 원본 사진 파일 이름(개인정보가 들어갈 수 있다)은 화면 자료에 나오지 않는다.
        assert "private-name" not in raw
        items = view["items"]
        assert view["kind"] == "sourcePhotos" and view["missing"] == []
        photos = items["photos"]
        assert [p["default"] for p in photos] == [True, False]
        assert photos[0]["tags"] and photos[0]["descriptionKo"]
        assert client.get(photos[1]["file"]["url"]).status_code == 200
        res = client.post(
            f"/api/characters/{CID}/gates/G1s/decision",
            json={
                "decision": "SELECT",
                "selections": [photos[1]["photoId"]],
                "reviewer": "u",
                "expectedRev": view["rev"],
            },
        )
        assert res.status_code == 200, res.text
    spec = read_json(ctx.character_dir(CID) / "s2-hero" / view["rev"] / "appearance-spec.json")
    assert spec["referenceImage"]["id"] == photos[1]["photoId"]
    assert ctx.state(CID).gate("G1s").status == "APPROVED"


def _no_answer_key(raw: str) -> None:
    for word in ("blindActual", "modelActual", "modelPick", "pairId", "sceneId", ACTUAL[1]):
        assert word not in raw


@pytest.mark.parametrize(
    "mode,label", [("PROMPT_ONLY", "긴 프롬프트로 진행"), ("BIND_EXISTING", "연결한 모델로 진행")]
)
def test_twin_g8_adopt_label_and_comparison_summary(
    tmp_path, monkeypatch, twin_decisions, mode, label
):
    ctx, cid, _text, _voter = _setup(tmp_path, monkeypatch, mode)
    folder = run_s10_twin(ctx, cid)
    rev = folder.name
    with _client(tmp_path) as client:
        view = _view(client, cid, "G8")
        raw = json.dumps(view, ensure_ascii=False)
        _no_answer_key(raw)
        items = view["items"]
        assert view["kind"] == "promptOnly" and view["modelMode"] == mode
        assert items["adoptLabel"] == label
        assert items["adoptTarget"] == items["adoptOptions"][0]
        twin = items["twin"]
        assert twin["phase"] == "RUN" and twin["sceneCount"] == 4
        cond = twin["conditions"][0]
        assert cond["armId"] == "LONG_BASE" and cond["status"] == "COMPLETE"
        assert cond["modelScore"]["rate"] == 0.5 and cond["exact"] == 1 and cond["overlap"] == 2
        assert cond["voted"] is False and cond["demo"] is None
        doc = read_json(folder / blind.BASE)
        ballots = {c["ballot"] for c in doc["conditions"] if c["ballot"]}
        assert {b["ballot"] for b in twin["ballots"]} == ballots
        assert all(not f["name"].startswith("twin-demo-") for f in view["files"])
        for b in twin["ballots"]:
            demo = f"twin-demo-{b['ballot']}.html"
            assert client.get(f"/api/files/{cid}/s10-eval/{rev}/{demo}").status_code == 403
            assert client.get(b["file"]["url"]).status_code == 200
        # 가족 판정을 가져오면 사람 구별률이 채워지고 시연 화면이 열린다.
        first = doc["conditions"][0]
        picks = {t["pairId"]: t["blindActual"] for t in first["trials"]}
        answers = tmp_path / "answers.json"
        answers.write_text(json.dumps({"ballot": first["ballot"], "picks": picks}))
        blind.import_blind_answers(ctx, cid, answers)
        after = _view(client, cid, "G8")["items"]["twin"]
        assert after["phase"] == "REVIEWED"
        cond = after["conditions"][0]
        assert cond["voted"] and cond["humanScore"]["rate"] == 1
        assert client.get(cond["demo"]["url"]).status_code == 200
        assert all(c["demo"] is None for c in after["conditions"][1:])
        res = client.post(
            f"/api/characters/{cid}/gates/G8/decision",
            json={
                "decision": "SELECT",
                "adopted": items["adoptTarget"],
                "reviewer": "u",
                "expectedRev": rev,
            },
        )
        assert res.status_code == 200, res.text
    assert ctx.state(cid).gate("G8").status == "APPROVED"


def test_twin_train_g8_keeps_blind_pairs_and_adds_summary(tmp_path, monkeypatch):
    ctx, cid, _text, voter = _setup(tmp_path, monkeypatch, "TRAIN")
    char = ctx.character_dir(cid)
    ctx.config = replace(ctx.config, budget=BudgetConfig(max_calls_per_command=20000))
    _g7_and_training(ctx, cid)
    data = char / "s9-data/ds1/train.jsonl"
    data.parent.mkdir(parents=True)
    data.write_text(json.dumps({"messages": [{"role": "assistant", "content": TRAIN_LINE}]}) + "\n")
    _synthetic_runs(ctx, cid, prereg.build_prereg(ctx, cid))
    voter.add("JUDGE", JudgeResponder())
    judge.run_judge(ctx, cid)
    report.build_report(ctx, cid)
    voter.add("JUDGE", {"pick": "A"})
    compare.append_twin_comparison(ctx, cid, models={"gemma-r1": FakeChat("gemma-r1", "모델 답")})
    with _client(tmp_path) as client:
        view = _view(client, cid, "G8")
    items = view["items"]
    assert view["kind"] == "eval" and items["pairs"]
    assert all(set(p) == {"pairId", "prompt", "a", "b"} for p in items["pairs"])
    twin = items["twin"]
    assert [c["status"] for c in twin["conditions"]] == ["COMPLETE", "COMPLETE", "NO_SERVING"]
    assert twin["conditions"][0]["overlapKinds"].get("TRAIN") == 1
    assert len(twin["ballots"]) == 2 and all("armId" not in b for b in twin["ballots"])
    assert all(c not in json.dumps(twin, ensure_ascii=False) for c in ("blindActual", ACTUAL[1]))


def test_original_character_has_no_twin_gates_and_keeps_g8_label(tmp_path):
    ctx = Context.load(tmp_path, execute=True)
    ctx.character_dir("orig").mkdir(parents=True)
    ctx.state("orig").save()
    assert "G0" not in reads.known_gates() and "G1s" not in reads.known_gates()
    with _client(tmp_path) as client:
        for gate in ("G0", "G1s"):
            res = client.get(f"/api/characters/orig/gates/{gate}")
            assert res.status_code == 404
    rev_dir = ctx.character_dir("orig") / "s10-eval" / "ev1"
    rev_dir.mkdir(parents=True)
    (rev_dir / "prompt-only.json").write_text(json.dumps({"adoptOptions": ["LONG_BASE"]}))
    from character_factory_poc.web.gate_items import eval_report

    items = eval_report(ctx.character_dir("orig"), "orig", "s10-eval", "ev1")
    assert items["adoptLabel"] == "긴 프롬프트로 진행" and items["adoptTarget"] == "LONG_BASE"
    assert items["twin"] is None
