"""S1 오프라인 흐름: 합성 순위 목록 → Scout(가짜) → 군집 → 미리보기 → G1 (D-0017, FR-35)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.cli import main
from character_factory_poc.common.errors import (
    BudgetExceeded,
    CheckFailed,
    FactoryError,
    NameLeakError,
    ValidationFailed,
)
from character_factory_poc.common.names import find_name_leaks
from character_factory_poc.common.schema import validate
from character_factory_poc.pipeline.approve import approve_gate
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.fake_image import FakeImageModel
from character_factory_poc.stages.s1_reference import preview as preview_mod
from character_factory_poc.stages.s1_reference.approve import selected_cluster
from character_factory_poc.stages.s1_reference.cluster import (
    adjusted_rand_index,
    agglomerate,
    vectorize,
)
from character_factory_poc.stages.s1_reference.features import (
    check_features,
    load_vocab,
    scout_people_input,
)
from character_factory_poc.stages.s1_reference.ranking import all_names, build_people, load_ranking
from character_factory_poc.stages.s1_reference.run import run_s1
from character_factory_poc.stages.s3_plan.draft import new_character
from tests.support.synthetic import RANKING, scout_features

NAMES = all_names(load_ranking(RANKING))


def _ctx(root: Path, toml: str = "") -> Context:
    if toml:
        (root / "factory.toml").write_text(toml, encoding="utf-8")
    c = Context.load(root, execute=True)
    text = FakeTextModel()
    text.add("AGENT", lambda req: scout_features(RANKING))
    c.use_models(text)
    c.use_image(FakeImageModel())
    return c


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return _ctx(tmp_path)


def test_s1_offline_to_g1_select(ctx):
    cid = new_character(ctx, "ref")
    out = run_s1(ctx, cid, RANKING)
    st = ctx.state(cid)
    assert st.stage("s1").status == "AWAITING_HUMAN"
    assert st.gate("G1").status == "AWAITING_HUMAN"

    report = json.loads((out / "report.json").read_text("utf-8"))
    assert [c["clusterId"] for c in report["candidates"]] == ["c1", "c2", "c3"]
    c1 = report["candidates"][0]
    # 두 목록에 걸친 건강미 계열이 1위, 3명 미만(동떨어진 1명)은 제외, 모르는 인물은 제외
    assert c1["listCount"] == 2 and c1["commonTags"]["mood"][0] == "healthy"
    assert [c["commonTags"]["mood"] for c in report["candidates"][1:]] == [["innocent"], ["chic"]]
    assert len(report["dropped"]) == 1 and "3명 미만" in report["dropped"][0]["reason"]
    assert [x["personId"] for x in report["excludedPeople"]] == ["p008"]
    assert len(report["cautions"]) == 3
    assert "목록 하나에서만" in report["candidates"][1]["limitations"][0]

    # 이름 분리(FR-35): 다음 단계로 넘어가는 산출물에는 이름이 없고, 검토 페이지에만 있다
    for name in ("report.json", "previews.json"):
        assert find_name_leaks((out / name).read_text("utf-8"), NAMES) == []
    assert "가상 하윤" in (out / "gate-G1.html").read_text("utf-8")

    previews = json.loads((out / "previews.json").read_text("utf-8"))
    assert len(previews) == 3  # 외모군마다 얼굴 1장(D-0043 (1))
    assert all((out / p["filePath"]).read_bytes().startswith(b"\x89PNG") for p in previews)
    assert "not based on any real individual" in previews[0]["prompt"]
    assert "a fictional Korean woman in their 20s" in previews[0]["prompt"]
    assert "Variation" not in previews[0]["prompt"]
    assert "인물 인상 한국인" in (out / "gate-G1.html").read_text("utf-8")
    kinds = [c["kind"] for c in ctx.ledger(cid).calls()]
    assert kinds.count("AGENT") == 1 and kinds.count("IMAGE") == 3

    approve_gate(
        ctx,
        cid,
        "G1",
        {
            "decision": "SELECT",
            "selections": ["c2"],
            "referencePreviews": ["c2-1"],
            "reviewer": "user",
            "minutes": 3,
        },
    )
    assert ctx.state(cid).gate("G1").status == "APPROVED"
    assert ctx.state(cid).stage("s1").status == "APPROVED"
    chosen = selected_cluster(ctx, cid)
    assert chosen.clusterId == "c2"
    assert find_name_leaks(chosen.model_dump_json(), NAMES) == []
    assert main(["--root", str(ctx.config.root), "verify", cid]) == 0


def test_g1_select_requires_one_candidate(ctx):
    cid = new_character(ctx, "ref")
    run_s1(ctx, cid, RANKING)
    with pytest.raises(FactoryError):
        approve_gate(ctx, cid, "G1", {"decision": "SELECT", "selections": ["c9"], "reviewer": "u"})
    with pytest.raises(FactoryError):
        approve_gate(ctx, cid, "G1", {"decision": "SELECT", "reviewer": "u"})
    # 얼굴은 정확히 한 장이다(D-0042, D-0043 (2))
    with pytest.raises(FactoryError, match="얼굴 정확히 한 장"):
        approve_gate(
            ctx,
            cid,
            "G1",
            {"decision": "SELECT", "selections": ["c2"], "referencePreviews": [], "reviewer": "u"},
        )
    with pytest.raises(FactoryError, match="얼굴 정확히 한 장"):
        approve_gate(
            ctx,
            cid,
            "G1",
            {
                "decision": "SELECT",
                "selections": ["c2"],
                "referencePreviews": ["c2-1", "c2-2"],
                "reviewer": "u",
            },
        )
    assert ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"


def test_scout_check_catches_vocab_missing_and_name_leak():
    people = scout_people_input(build_people(load_ranking(RANKING), 3))
    vocab = load_vocab()
    out = scout_features(RANKING)
    assert check_features(people, vocab)(validate("appearance-features-v1", out)) == []
    bad = copy.deepcopy(out)
    bad["features"][0]["tags"]["hairColor"] = "pink"
    bad["features"][1]["note"] = "가상서아 와 비슷하다"  # 띄어쓰기를 바꾼 이름도 잡는다
    bad["features"][2]["tags"]["styling"] = []
    bad["features"] = bad["features"][:-1]
    problems = check_features(people, vocab)(validate("appearance-features-v1", bad))
    assert any("'pink'는 어휘에 없다" in p for p in problems)
    assert any(p.startswith("p002.note") for p in problems)
    assert any("p003.tags.styling" in p for p in problems)
    assert any("빠진 personId" in p and "p014" in p for p in problems)


def test_scout_retries_with_check_feedback(tmp_path):
    ctx = _ctx(tmp_path)
    bad = scout_features(RANKING)
    bad["features"][0]["tags"]["faceShape"] = "egg"
    text = FakeTextModel()
    text.add("AGENT", [bad, scout_features(RANKING)])
    ctx.use_models(text)
    cid = new_character(ctx, "retry")
    run_s1(ctx, cid, RANKING)
    assert len(text.requests) == 2
    assert "'egg'는 어휘에 없다" in text.requests[1].messages[-1].content


def test_cluster_is_deterministic_and_ari():
    feats = validate("appearance-features-v1", scout_features(RANKING)).features
    vectors = {f.personId: vectorize(f) for f in feats if f.recognized}
    shuffled = dict(reversed(list(vectors.items())))
    a = agglomerate(vectors, 4)
    assert a == agglomerate(shuffled, 4)
    assert sorted(len(c) for c in a) == [1, 4, 4, 4]
    labels = {m: str(i) for i, c in enumerate(a) for m in c}
    renamed = {m: "x" + v for m, v in labels.items()}
    assert adjusted_rand_index(labels, renamed) == (1.0, 13)
    merged = {m: ("same" if v in {"0", "1"} else v) for m, v in labels.items()}
    ari, n = adjusted_rand_index(labels, merged)
    assert n == 13 and ari is not None and ari < 1.0


def test_too_few_members_is_check_failed(tmp_path):
    ctx = _ctx(tmp_path, "[stages.s1]\nmin_members_per_cluster = 5\n")
    cid = new_character(ctx, "few")
    with pytest.raises(CheckFailed) as e:
        run_s1(ctx, cid, RANKING)
    assert "외모군이 없다" in str(e.value)
    assert ctx.state(cid).stage("s1").status == "CHECK_FAILED"
    assert ctx.state(cid).gate("G1").status == "PENDING"


def test_name_in_preview_prompt_stops_before_image_call(ctx, monkeypatch):
    image = FakeImageModel()
    ctx.use_image(image)
    monkeypatch.setattr(
        preview_mod, "build_prompt", lambda c, s, v, n, t, **kw: "portrait inspired by 가상하윤"
    )
    cid = new_character(ctx, "leak")
    with pytest.raises(NameLeakError):
        run_s1(ctx, cid, RANKING)
    assert image.requests == []
    assert ctx.state(cid).stage("s1").status == "CHECK_FAILED"


def test_rerun_after_request_changes_reports_agreement(ctx):
    cid = new_character(ctx, "again")
    run_s1(ctx, cid, RANKING)
    approve_gate(
        ctx,
        cid,
        "G1",
        {"decision": "REQUEST_CHANGES", "reviewer": "user", "note": "얼굴이 너무 어려 보인다"},
    )
    assert ctx.state(cid).stage("s1").status == "REJECTED"
    out = run_s1(ctx, cid, RANKING)
    assert out.name == "rf2"
    repro = json.loads((out / "report.json").read_text("utf-8"))["reproducibility"]
    assert repro == {"previousRev": "rf1", "agreementWithPrevious": 1.0, "comparedPeople": 13}


def test_run_until_with_ranking_stops_or_auto_selects(ctx):
    cid = new_character(ctx, "orch")
    log = run_until(ctx, cid, RunOptions(until="G1", ranking=RANKING))
    assert log.stopped_at == "G1" and ctx.state(cid).gate("G1").status == "AWAITING_HUMAN"

    cid2 = new_character(ctx, "orch-auto")
    log = run_until(ctx, cid2, RunOptions(until="G1", ranking=RANKING, auto_approve={"G1"}))
    assert ctx.state(cid2).gate("G1").status == "APPROVED"
    rec = json.loads((ctx.character_dir(cid2) / "gates" / "G1-rf1.json").read_text("utf-8"))
    assert rec["reviewer"].startswith("auto:") and rec["selections"] == ["c1", "c1-1"]
    assert rec["decision"] == "SELECT"


def test_ranking_validation_and_dry_run(tmp_path, capsys):
    dup = copy.deepcopy(RANKING)
    dup["lists"][0]["entries"][1]["rank"] = 1
    with pytest.raises(ValidationFailed):
        load_ranking(dup)
    no_period = copy.deepcopy(RANKING)
    del no_period["lists"][0]["period"]
    with pytest.raises(ValidationFailed):
        load_ranking(no_period)

    path = tmp_path / "ranking.json"
    path.write_text(json.dumps(RANKING, ensure_ascii=False), encoding="utf-8")
    assert main(["--root", str(tmp_path), "ref", "run", "x", "--ranking", str(path)]) == 0
    printed = capsys.readouterr().out
    assert "인물 14명" in printed and "합계 8회" in printed
    assert find_name_leaks(printed, NAMES) == []
    assert not (tmp_path / "runs").exists()


def test_budget_rejects_before_writing(tmp_path):
    ctx = _ctx(tmp_path, "[budget]\nmax_calls_per_command = 5\n")
    cid = new_character(ctx, "budget")
    with pytest.raises(BudgetExceeded):
        run_s1(ctx, cid, RANKING)
    assert not (ctx.character_dir(cid) / "s1-reference").exists()
    assert ctx.state(cid).stage("s1").status == "PENDING"


def test_example_template_is_valid():
    root = Path(__file__).resolve().parents[1]
    obj = json.loads(
        (root / "docs" / "templates" / "popularity-ranking-example.json").read_text("utf-8")
    )
    assert load_ranking(obj).lists


def test_appearance_origin_is_required_and_drives_prompt():
    """D-0020: 인물 인상은 필수이고 정해진 값만 받으며 미리보기 프롬프트 주어에 들어간다."""
    missing = copy.deepcopy(RANKING)
    del missing["scope"]["appearanceOrigin"]
    with pytest.raises(ValidationFailed, match="appearanceOrigin"):
        load_ranking(missing)
    free_text = copy.deepcopy(RANKING)
    free_text["scope"]["appearanceOrigin"] = "Korean idol style"
    with pytest.raises(ValidationFailed):
        load_ranking(free_text)

    cluster = validate(
        "appearance-cluster-v1",
        {
            "clusterId": "c1",
            "members": ["p001", "p002", "p004"],
            "memberCount": 3,
            "commonTags": {"hairLength": "long", "mood": ["innocent"]},
            "tagShares": {},
            "listCount": 1,
            "popularity": {
                "medianPercentile": 0.9,
                "iqr": 0.1,
                "normalizedCount": 3,
                "unnormalizedCount": 0,
            },
        },
    )
    vocab = load_vocab()
    base = load_ranking(RANKING).scope
    prompts = {}
    for origin in ("korean", "east-asian", "unspecified"):
        scope = base.model_copy(update={"appearanceOrigin": origin})
        prompts[origin] = preview_mod.build_prompt(cluster, scope, vocab, 1, 3)
    assert "a fictional Korean woman in their 20s" in prompts["korean"]
    assert "a fictional East Asian woman in their 20s" in prompts["east-asian"]
    assert "a fictional woman in their 20s" in prompts["unspecified"]
    assert "Korean" not in prompts["unspecified"]


def test_v1_ranking_is_rejected_with_upgrade_hint():
    old = copy.deepcopy(RANKING)
    old["schemaVersion"] = "popularity-ranking-v1"
    del old["scope"]["appearanceOrigin"]
    with pytest.raises(ValidationFailed, match="appearanceOrigin") as e:
        load_ranking(old)
    assert "popularity-ranking-v2" in str(e.value)


def test_negative_prompt_avoids_celebrity_wording():
    """'celebrity'를 넣으면 인물 인상과 함께 안전 시스템에 막혔다(2026-10-20 검증 기록)."""
    assert "celebrity" not in preview_mod.NEGATIVE.casefold()


def test_blocked_image_marks_s1_check_failed(ctx):
    from character_factory_poc.common.errors import ImageGenerationError

    class Blocked:
        name, model = "blocked", "x"

        def generate(self, request):
            raise ImageGenerationError("blocked by the safety system")

    ctx.use_image(Blocked())
    cid = new_character(ctx, "blocked")
    with pytest.raises(ImageGenerationError):
        run_s1(ctx, cid, RANKING)
    assert ctx.state(cid).stage("s1").status == "CHECK_FAILED"


def test_previous_v1_report_skips_agreement(ctx):
    """D-0021: 이전 rev 보고서가 옛 계약이면 실행은 계속하고 일치도 비교만 건너뛴다."""
    cid = new_character(ctx, "oldrev")
    old = ctx.character_dir(cid) / "s1-reference" / "rf1"
    old.mkdir(parents=True)
    (old / "report.json").write_text(
        json.dumps({"schemaVersion": "reference-report-v1"}), encoding="utf-8"
    )
    out = run_s1(ctx, cid, RANKING)
    assert out.name == "rf2"
    repro = json.loads((out / "report.json").read_text("utf-8"))["reproducibility"]
    assert repro == {"previousRev": "rf1", "agreementWithPrevious": None, "comparedPeople": 0}
