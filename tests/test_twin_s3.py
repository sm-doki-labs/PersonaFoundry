"""트윈 S3의 인용 검증과 기존 G3 선택 경로. 모든 발화는 합성 자료다."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from character_factory_poc.checks.registry import run_checks
from character_factory_poc.common.errors import CheckFailed, FactoryError, GateNotApprovedError
from character_factory_poc.common.store import read_json, verify_manifest
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.stages.s0_source.run import run_s0
from character_factory_poc.stages.s3_plan.check_v2 import name_guard
from character_factory_poc.stages.s3_plan.importer import load_approved_plan
from character_factory_poc.stages.s3_plan.twin import run_s3_twin
from tests.support.synthetic import RANKING
from tests.test_source_s0 import _good_digest, _twin, _write_pack

LINES = (
    ("오늘 점심은?", "밥부터 먹어요. 저는 매일 도시락을 싸요."),
    ("약속에 늦겠어요.", "시간부터 다시 정해요. 급하게 뛰는 건 싫어요."),
    ("혼자 있고 싶어요.", "그럼 기다릴게요. 재촉하는 사람으로 보일까 봐 걱정해요."),
)
CANARY = "비교 전용 마지막 날의 자주색 유리구슬"


def _ctx(tmp):
    ctx = Context.load(tmp, execute=True)
    model = FakeTextModel()
    model.add("AGENT", _good_digest)
    ctx.use_models(model)
    return ctx, model


def _ready(tmp, kind="PRIVATE_PERSON", template=None, *, facts=True, introduction=""):
    ctx, model = _ctx(tmp)
    cid = _twin(ctx)
    path = _write_pack(tmp, kind=kind)
    pack = read_json(path)
    if facts:
        pack["knownFacts"] = {"age": "41", "gender": "female", "job": "제본사", "relation": "가족"}
    if template:
        pack["chapterTemplate"] = template
    path.write_text(json.dumps(pack), encoding="utf-8")
    lines = []
    for i, (q, a) in enumerate((*LINES, ("내일 봐요.", CANARY)), 1):
        if i == 1 and introduction:
            a = f"{introduction} {a}"
        lines.extend(
            [
                f"--------------- 2026년 10월 {i}일 토요일 ---------------",
                f"[나] [오전 9:00] {q}",
                f"[엄마] [오전 9:05] {a}",
            ]
        )
    path.with_name("mom.txt").write_text("\n".join(lines), encoding="utf-8")
    run_s0(ctx, cid, path)
    approve_gate(ctx, cid, "G0", {"decision": "APPROVE", "reviewer": "u"})
    model.add("AGENT", _answer)
    return ctx, model, cid


def _input(req, key):
    return json.loads(
        req.messages[1].content.split(f'<input name="{key}">', 1)[1].split("</input>", 1)[0]
    )


def _answer(req):
    source = _input(req, "source")
    rows = _input(req, "corpus-sample")
    refs = [
        dict(kind="SOURCE", ref=r["msgId"], quote=r["text"])
        for r in rows
        if r["speaker"] == "SUBJECT"
    ]
    a, b, c = refs
    facts = source["knownFacts"]
    ev = {k: [dict(kind="USER", ref=f"knownFacts.{k}", quote=v)] for k, v in facts.items()}
    if "relation" in ev:
        ev["background"] = ev.pop("relation")
    ev.update(
        tagline=[a],
        coreTraits=[a],
        contrastTrait=[c],
        choices=refs,
        lifeAndTastes=refs,
        wantsAndFears=[c],
        misreadings=[c],
        voiceSummary=[b],
        voiceExamples=[a, c],
        boundaries=[c],
    )
    return {
        **source["ids"],
        "name": source["displayName"],
        "age": 41,
        "gender": "female",
        "job": "제본사",
        "background": "가족",
        "tagline": "밥부터 챙기는 사람",
        "coreTraits": ["끼니를 먼저 챙긴다."],
        "contrastTrait": "혼자 있고 싶다면 기다린다.",
        "choices": [
            dict(situation=q, firstMove=v["quote"]) for (q, _), v in zip(LINES, refs, strict=True)
        ],
        "lifeAndTastes": [
            "매일 도시락을 싼다.",
            "급하게 뛰는 걸 싫어한다.",
            "재촉하지 않고 기다린다.",
        ],
        "wantsAndFears": ["재촉하고 싶지 않다."],
        "misreadings": ["재촉한다고 오해받을까 걱정한다."],
        "voiceSummary": "해요체로 먼저 제안한다.",
        "voiceExamples": [a["quote"], c["quote"]],
        "boundaries": ["혼자 있고 싶다는 말을 존중한다."],
        "chapterArc": source["chapterArc"],
        "evidence": ev,
    }


def test_origin_and_g0_before_any_agent(tmp_path):
    ctx, model = _ctx(tmp_path)
    with pytest.raises(FactoryError, match="트윈"):
        run_s3_twin(ctx, "original")
    cid = _twin(ctx)
    with pytest.raises(GateNotApprovedError, match="G0"):
        run_s3_twin(ctx, cid)
    assert not model.requests
    assert not (ctx.character_dir(cid) / "s3-plan").exists()


@pytest.mark.parametrize(
    "kind,template,titles",
    [
        ("PRIVATE_PERSON", None, ["안부", "일상", "속마음"]),
        ("PUBLIC_FIGURE", None, ["첫 통화", "친해지기", "단골 팬"]),
        ("PUBLIC_FIGURE", "FAMILY_CALL", ["안부", "일상", "속마음"]),
    ],
)
def test_select_approved_twin_without_holdout(tmp_path, monkeypatch, kind, template, titles):
    ctx, model, cid = _ready(tmp_path, kind, template)
    # 원문은 열어 보지 않고 S0에서 실제 생성한 비교 세트의 읽기 경로를 막는다.
    held = ctx.character_dir(cid) / "s0-source/sp1/holdout.jsonl"
    assert held.is_file()
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path != held, "S3가 비교 세트를 열었다"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    ranking = copy.deepcopy(RANKING)
    ranking["lists"][0]["entries"] = [dict(rank=1, name="엄 마"), dict(rank=2, name="합성인명")]
    path = ctx.character_dir(cid) / "s1-reference/r1/ranking.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(ranking), encoding="utf-8")
    folder = run_s3_twin(ctx, cid)
    assert ctx.state(cid).stage("s3").status == ctx.state(cid).gate("G3").status == "AWAITING_HUMAN"
    variants = read_json(folder / "variants.json")
    assert variants["schemaVersion"] == "plan-variants-v1"
    assert [p["variantId"] for p in variants["candidates"]] == ["v1"]
    assert CANARY not in str([m.content for m in model.requests[-1].messages])
    assert "holdout" not in str(_input(model.requests[-1], "source"))
    assert _input(model.requests[-1], "source")["sharedSpeechEndings"] == {
        "politeEnding": 3,
        "casualEnding": 0,
        "unclassified": 0,
    }
    assert run_checks("s3-twin", folder / "workspace") == []
    guard = read_json(folder / "workspace/inputs/name-guard.json")
    assert name_guard(["엄마"])[0] not in guard and name_guard(["합성인명"])[0] in guard
    page = (folder / "gate-G3.html").read_text("utf-8")
    assert "원문 또는 출처" in page and "knownFacts.age" in page
    for choice, ref in zip(
        variants["candidates"][0]["choices"],
        variants["candidates"][0]["evidence"]["choices"],
        strict=True,
    ):
        assert any(
            choice["situation"] in tr and ref["quote"] in tr and ref["ref"] in tr
            for tr in page.split("</tr>")
        )
    approve_gate(ctx, cid, "G3", {"decision": "SELECT", "selections": ["v1"], "reviewer": "u"})
    plan, path = load_approved_plan(ctx, cid)
    assert path == folder / "plan.json" and plan.name == "엄마"
    assert [c.title for c in plan.chapters] == titles
    assert verify_manifest(folder) == []


@pytest.mark.parametrize(
    "bad,reason",
    [
        ("quote", "원문의 일부"),
        ("id", "없는 msgId"),
        ("speaker", "SUBJECT"),
        ("missing_choice", "choices"),
        ("known_fact", "knownFacts.age"),
        ("wrong_job", "knownFacts.job"),
        ("user_trait", "SOURCE"),
        ("name", "displayName"),
        ("missing_job", "job"),
        ("unquoted_age", "knownFacts.age"),
    ],
)
def test_bad_output_never_opens_g3(tmp_path, bad, reason):
    ctx, model, cid = _ready(tmp_path)
    ctx.config.stages["s3t"] = {"max_check_retries": 0, "max_format_retries": 0}

    def respond(req):
        out = _answer(req)
        ev = out["evidence"]
        # 원본 예시에서 공유하는 dict를 수정하지 않는다.
        if bad == "quote":
            ev["choices"][0] = ev["choices"][0] | {"quote": "없는 문장"}
        elif bad == "id":
            ev["choices"][0] = ev["choices"][0] | {"ref": "k1-m999999"}
        elif bad == "speaker":
            user = next(r for r in _input(req, "corpus-sample") if r["speaker"] == "USER")
            ev["choices"][0] = dict(kind="SOURCE", ref=user["msgId"], quote=user["text"])
        elif bad == "missing_choice":
            ev["choices"] = ev["choices"][:-1]
        elif bad == "known_fact":
            out["age"] = 42
        elif bad == "wrong_job":
            ev["job"][0]["quote"] = "조각가"
        elif bad == "user_trait":
            ev["coreTraits"] = ev["job"]
        elif bad == "name":
            out["name"] = "다른이"
        elif bad == "unquoted_age":
            ev["age"] = ev["coreTraits"]
        else:
            del out["job"]
        return out

    model.add("AGENT", respond)
    with pytest.raises(CheckFailed, match=reason):
        run_s3_twin(ctx, cid)
    assert ctx.state(cid).stage("s3").status == "CHECK_FAILED"
    assert ctx.state(cid).gate("G3").status == "PENDING"
    folder = ctx.character_dir(cid) / "s3-plan/pr1"
    assert not (folder / "variants.json").exists()
    if bad != "missing_job":
        assert reason in " ".join(
            run_checks("s3-twin", folder / "workspace", folder / "workspace/last-failed.json")
        )


def test_limited_sample_and_retry(tmp_path):
    ctx, model, cid = _ready(tmp_path)
    ctx.config.stages["s3t"] = {"max_agent_messages": 4, "max_format_retries": 0}

    def inspect(req):
        rows = _input(req, "corpus-sample")
        assert len(rows) == 4
        assert [r["speaker"] for r in rows] == ["USER", "SUBJECT", "USER", "SUBJECT"]
        assert rows[0]["convId"] == rows[1]["convId"] != rows[2]["convId"] == rows[3]["convId"]
        assert rows[-1]["text"] == LINES[-1][1]
        return {}

    model.add("AGENT", inspect)
    with pytest.raises(CheckFailed, match="Field required"):
        run_s3_twin(ctx, cid)
    del ctx.config.stages["s3t"]

    def invalid(req):
        out = _answer(req)
        del out["evidence"]["choices"]
        return out

    model.add("AGENT", [invalid, _answer])
    folder = run_s3_twin(ctx, cid)
    assert folder.name == "pr2" and (folder / "workspace/attempt-2.txt").exists()


@pytest.mark.parametrize("stated", [True, False])
def test_required_facts_without_known_facts(tmp_path, stated):
    intro = "저는 41세 여성이고 직업은 제본사예요. 가족과 살아요." if stated else ""
    ctx, model, cid = _ready(tmp_path, facts=False, introduction=intro)
    ctx.config.stages["s3t"] = {"max_check_retries": 0}

    def respond(req):
        out = _answer(req)
        ref = out["evidence"]["coreTraits"][0]
        for key in ("age", "job", "gender", "background"):
            out["evidence"][key] = [ref]
        out["background"] = "가족과 살아요."
        return out

    model.add("AGENT", respond)
    if stated:
        folder = run_s3_twin(ctx, cid)
        plan = read_json(folder / "variants.json")["candidates"][0]
        assert all(e["kind"] == "SOURCE" for refs in plan["evidence"].values() for e in refs)
    else:
        with pytest.raises(CheckFailed) as exc:
            run_s3_twin(ctx, cid)
        assert all(f"knownFacts.{key}" in str(exc.value) for key in ("age", "gender", "job"))
        assert ctx.state(cid).gate("G3").status == "PENDING"
