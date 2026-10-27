"""참고 자료 검색·선별을 합성 자료와 가짜 공급자로만 검증한다."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from pathlib import Path

import pytest

from acf.common.errors import BudgetExceeded, CheckFailed, GateNotApprovedError, ImmutableWriteError
from acf.common.schema import validate
from acf.common.store import verify_manifest
from acf.providers.embed import HashEmbedder, cosine, make_embedder
from acf.providers.fake_codex import FakeCodexAgent
from acf.stages.s3_plan.importer import import_plan, load_approved_plan
from acf.stages.s3r_refs.index import build_index, load_index, write_index
from acf.stages.s3r_refs.select import (
    build_queries,
    codex_checks,
    load_latest_reference_set,
    plan_calls,
    retrieve,
    run_s3r,
)
from tests.support.flow import approve_plan_v2, make_ctx, through_g2
from tests.support.synthetic import PLAN
from tests.test_agentic import CATALOG

PERSONA = {
    "schemaVersion": "character-persona-v6",
    "personaId": "synthetic",
    "revision": "synthetic-r1",
    "displayName": "합성 인물",
    "identity": {"age": 25, "occupation": "가상 직장 비공개 사실"},
    "facts": ["비공개 개인 사실은 인덱스에 옮기지 않는다"],
    "lifeAndTastes": ["원본만의 취향은 옮기지 않는다"],
    "disposition": ["처음 보는 사람 앞에서는 이유를 끝까지 듣는다"],
    "wantsAndFears": ["작은 약속을 지키는 관심을 원한다"],
    "readingAndTension": ["조심스러운 태도가 무관심으로 보일까 염려한다"],
    "choices": ["일정을 재촉받으면 지금 고를 수 있는 여지를 먼저 남긴다"],
    "voice": ["한두 문장으로 담백하게 말하고 감탄사를 아낀다"],
    "boundaries": ["원본 경계 문장도 선별 항목에는 섞지 않는다"],
}


def _index(tmp_path: Path, *, dim: int = 256) -> Path:
    personas = tmp_path / "personas"
    personas.mkdir(exist_ok=True)
    (personas / "fake.json").write_text(json.dumps(PERSONA, ensure_ascii=False), "utf-8")
    (personas / "not-persona.json").write_text('{"schemaVersion":"other"}', "utf-8")
    (personas / "array.json").write_text("[]", "utf-8")
    data = tmp_path / "data.jsonl"
    data.write_text(
        json.dumps(
            {"id": "walk", "text": "흐린 날 필름 카메라로 골목을 찍는다", "label": "산책"},
            ensure_ascii=False,
        )
        + "\n\n",
        "utf-8",
    )
    index = build_index(
        "synthetic-index-v1",
        stanford_catalog=CATALOG,
        personas_dir=personas,
        jsonl=[(data, "SNS14")],
        embedder=HashEmbedder(dim),
    )
    path = tmp_path / "references.json"
    write_index(path, index)
    return path


def _selected(item_id: str = "AUTHORED:synthetic-r1:traits", use: str = "TRAITS", why="선택 보강"):
    return {
        "schemaVersion": "reference-curation-output-v1",
        "selected": [{"itemId": item_id, "use": use, "why": why}],
    }


def _ready(tmp_path: Path, extra_toml: str = "", *, dim: int = 256):
    path = _index(tmp_path, dim=dim)
    ctx, agents = make_ctx(tmp_path, f'reference_index = "{path}"\n{extra_toml}')
    cid = through_g2(ctx)
    approve_plan_v2(ctx, cid)
    return ctx, agents, cid, path


def test_hash_embedding_is_deterministic_normalized_and_korean_friendly():
    text = "재촉받으면 선택할 여지를 남긴다"
    embedder = HashEmbedder()
    vectors = embedder.embed([text, text, "", "  ", unicodedata.normalize("NFD", text)])
    assert embedder.name == "hash-v1" and embedder.dim == 256
    assert vectors[0] == vectors[1] == vectors[4] == HashEmbedder().embed([text])[0]
    assert math.isclose(sum(v * v for v in vectors[0]), 1)
    assert vectors[2] == vectors[3] == [0.0] * 256
    assert cosine(vectors[0], vectors[1]) == pytest.approx(1)
    assert cosine(vectors[0], vectors[2]) == 0
    assert make_embedder("hash-v1").name == "hash-v1"
    with pytest.raises(ValueError, match="실제 임베더"):
        make_embedder("remote")
    with pytest.raises(ValueError, match="dim"):
        HashEmbedder(7)
    with pytest.raises(ValueError, match="차원"):
        cosine([1], [1, 0])
    with pytest.raises(ValueError, match="비유한"):
        cosine([float("nan")], [1])


def test_build_index_sources_and_immutable_roundtrip(tmp_path):
    path = _index(tmp_path)
    index, digest = load_index(path)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert index.sources == ["AUTHORED", "SNS14", "STANFORD"]
    items = {item.itemId: item for item in index.items}
    assert set(items) == {
        "STANFORD:P29",
        "AUTHORED:synthetic-r1:traits",
        "AUTHORED:synthetic-r1:voice",
        "SNS14:walk",
    }
    preset = items["STANFORD:P29"]
    assert preset.version == "3.0" and preset.uses == ["TRAITS", "VOICE"]
    assert "내가 이 부분부터 할게." in preset.text
    assert "core_system_prompt" not in preset.text
    traits = items["AUTHORED:synthetic-r1:traits"]
    assert traits.version == "synthetic-r1" and traits.uses == ["TRAITS"]
    for field in ("disposition", "wantsAndFears", "readingAndTension", "choices"):
        assert PERSONA[field][0] in traits.text
    assert PERSONA["voice"][0] not in traits.text
    assert all(PERSONA["facts"][0] not in item.text for item in items.values())
    assert all(PERSONA["lifeAndTastes"][0] not in item.text for item in items.values())
    assert items["AUTHORED:synthetic-r1:voice"].uses == ["VOICE"]
    assert items["SNS14:walk"].uses == ["DATA"]
    assert all(len(item.vector) == index.dim for item in index.items)
    before = path.read_bytes()
    assert write_index(path, index) == path and path.read_bytes() == before
    with pytest.raises(ImmutableWriteError):
        write_index(path, index.model_copy(update={"indexId": "changed"}))


def test_index_rejects_duplicate_ids_and_wrong_vector_dimensions(tmp_path):
    path = _index(tmp_path)
    raw = json.loads(path.read_text("utf-8"))
    raw["items"].append(raw["items"][0])
    path.write_text(json.dumps(raw), "utf-8")
    with pytest.raises(ValueError, match="중복"):
        load_index(path)
    raw["items"].pop()
    raw["items"][0]["vector"] = [1.0]
    path.write_text(json.dumps(raw), "utf-8")
    with pytest.raises(ValueError, match="차원"):
        load_index(path)


def test_jsonl_sources_uses_and_prefixes(tmp_path):
    path = tmp_path / "items.jsonl"
    rows = [
        {"id": "NIKL:one", "text": "합성 장면", "uses": ["DATA", "VOICE"]},
        {"id": "two", "text": "두 번째 합성 장면"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), "utf-8")
    index = build_index("idx", jsonl=[(path, "NIKL")], embedder=HashEmbedder())
    assert [item.itemId for item in index.items] == ["NIKL:one", "NIKL:two"]
    assert index.items[0].uses == ["DATA", "VOICE"]
    with pytest.raises(ValueError, match="JSONL 출처"):
        build_index("idx", jsonl=[(path, "AUTHORED")], embedder=HashEmbedder())
    with pytest.raises(ValueError, match="중복"):
        build_index("idx", jsonl=[(path, "NIKL"), (path, "NIKL")], embedder=HashEmbedder())
    path.write_text('{"id": "bad"}', "utf-8")
    with pytest.raises(ValueError, match="items.jsonl:1"):
        build_index("idx", jsonl=[(path, "OTHER")], embedder=HashEmbedder())


def test_retrieval_matches_first_and_filters_by_use(tmp_path):
    index, _ = load_index(_index(tmp_path))
    voice = next(item for item in index.items if item.itemId.endswith(":voice"))
    found = retrieve(
        index, {"VOICE": voice.text, "DATA": voice.text}, embedder=HashEmbedder(), top_k=1
    )
    assert found[0].itemId == voice.itemId and found[0].score == pytest.approx(1)
    assert found[1].itemId == "SNS14:walk"
    with pytest.raises(ValueError, match="dim"):
        retrieve(index, {"VOICE": voice.text}, embedder=HashEmbedder(128))


def test_run_curator_preserves_provenance_without_raw_text(tmp_path):
    ctx, agents, cid, index_path = _ready(tmp_path, dim=64)
    agents.set("s3r", lambda req: _selected())
    rev_dir = run_s3r(ctx, cid)
    assert rev_dir == ctx.character_dir(cid) / "s3r-refs" / "rs1"
    assert ctx.state(cid).stage("s3r").status == "APPROVED"
    assert "s3r" not in ctx.state(cid).state.gates
    refs = load_latest_reference_set(ctx, cid)
    assert refs.refRev == "rs1" and refs.planRev == "pr1"
    assert refs.indexSha256 == hashlib.sha256(index_path.read_bytes()).hexdigest()
    assert refs.selected[0].source == "AUTHORED" and refs.selected[0].version == "synthetic-r1"
    serialized = (rev_dir / "reference-set.json").read_text("utf-8")
    assert '"text"' not in serialized and '"vector"' not in serialized
    assert PERSONA["wantsAndFears"][0] not in serialized
    assert verify_manifest(rev_dir) == []
    workspace = rev_dir / "workspace"
    candidates = json.loads((workspace / "inputs/candidates.json").read_text("utf-8"))
    assert all(len(c["text"]) <= 400 for c in candidates)
    assert (workspace / "output.json").exists()
    assert agents.calls.count("s3r") == 1
    assert plan_calls(ctx)[0].calls == 6
    contract, checks = codex_checks("s3r", workspace)
    assert contract == "reference-curation-output-v1"
    assert checks[0](validate(contract, _selected())) == []
    first_bytes = (rev_dir / "reference-set.json").read_bytes()
    next_dir = run_s3r(ctx, cid)
    assert next_dir.name == "rs2" and load_latest_reference_set(ctx, cid).refRev == "rs2"
    assert (rev_dir / "reference-set.json").read_bytes() == first_bytes
    approve_plan_v2(ctx, cid)
    assert load_latest_reference_set(ctx, cid) is None


def test_long_excerpts_are_truncated(tmp_path):
    path = tmp_path / "long.jsonl"
    path.write_text(json.dumps({"id": "long", "text": "가" * 1000}), "utf-8")
    index_path = tmp_path / "idx.json"
    write_index(index_path, build_index("idx", jsonl=[(path, "OTHER")], embedder=HashEmbedder()))
    ctx, agents = make_ctx(tmp_path, f'reference_index = "{index_path}"\n')
    cid = through_g2(ctx)
    approve_plan_v2(ctx, cid)
    agents.set("s3r", lambda req: _selected("OTHER:long", "DATA"))
    rev_dir = run_s3r(ctx, cid)
    candidates = json.loads((rev_dir / "workspace/inputs/candidates.json").read_text("utf-8"))
    assert len(candidates[0]["text"]) == 400
    assert "가" * 400 not in (rev_dir / "reference-set.json").read_text("utf-8")


def test_skipped_without_index_and_g3_is_required(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    cid = through_g2(ctx)
    with pytest.raises(GateNotApprovedError):
        run_s3r(ctx, cid)
    assert ctx.state(cid).stage("s3r").status == "PENDING"
    approve_plan_v2(ctx, cid)
    for _ in range(2):
        assert run_s3r(ctx, cid) is None
    assert ctx.state(cid).stage("s3r").status == "SKIPPED"
    assert load_latest_reference_set(ctx, cid) is None and plan_calls(ctx) == []
    assert "s3r" not in agents.calls
    assert not (ctx.character_dir(cid) / "s3r-refs").exists()


@pytest.mark.parametrize(
    ("selected", "limit", "problem"),
    [
        (_selected("OTHER:missing"), 8, "검색 후보"),
        (_selected(use="DATA"), 8, "검색 후보"),
        (_selected(why="   "), 8, "why가 비었다"),
        ({"selected": _selected()["selected"] * 2}, 8, "중복"),
        (
            {
                "selected": _selected("STANFORD:P29")["selected"]
                + _selected("STANFORD:P29", "VOICE")["selected"]
            },
            8,
            "중복",
        ),
        (
            {
                "selected": _selected()["selected"]
                + _selected("AUTHORED:synthetic-r1:voice", "VOICE")["selected"]
            },
            1,
            "max_selected",
        ),
    ],
)
def test_invalid_selection_retries_then_check_failed(tmp_path, selected, limit, problem):
    ctx, agents, cid, _ = _ready(
        tmp_path, f"[stages.s3r]\nmax_selected = {limit}\nmax_check_retries = 1\n"
    )
    agents.set("s3r", lambda req: selected)
    with pytest.raises(CheckFailed, match=problem):
        run_s3r(ctx, cid)
    assert agents.calls.count("s3r") == 2
    assert ctx.state(cid).stage("s3r").status == "CHECK_FAILED"
    rev_dir = ctx.character_dir(cid) / "s3r-refs" / "rs1"
    assert (rev_dir / "workspace/last-failed.json").exists()
    assert not (rev_dir / "reference-set.json").exists()
    assert verify_manifest(rev_dir) == []
    assert load_latest_reference_set(ctx, cid) is None


def test_invalid_format_becomes_check_failed(tmp_path):
    ctx, agents, cid, _ = _ready(tmp_path, "[stages.s3r]\nmax_format_retries = 1\n")
    agents.set("s3r", lambda req: {"selected": []})
    with pytest.raises(CheckFailed, match="형식 실패"):
        run_s3r(ctx, cid)
    assert agents.calls.count("s3r") == 2
    assert ctx.state(cid).stage("s3r").status == "CHECK_FAILED"


def test_budget_checked_before_any_write(tmp_path):
    ctx, agents, cid, _ = _ready(tmp_path)
    ctx.max_calls = 0
    before = (ctx.character_dir(cid) / "state.json").read_bytes()
    with pytest.raises(BudgetExceeded):
        run_s3r(ctx, cid)
    assert before == (ctx.character_dir(cid) / "state.json").read_bytes()
    assert not (ctx.character_dir(cid) / "s3r-refs").exists()
    assert "s3r" not in agents.calls


def test_top_k_config_and_relative_index_path(tmp_path):
    ctx, agents, cid, _ = _ready(tmp_path, "[stages.s3r]\ntop_k = 1\n")
    ctx.config.resources["reference_index"] = "references.json"
    agents.set("s3r", lambda req: _selected("SNS14:walk", "DATA"))
    run_s3r(ctx, cid)
    refs = load_latest_reference_set(ctx, cid)
    assert all(sum(r.use == use for r in refs.retrieved) == 1 for use in refs.queries)


def test_legacy_plan_queries_and_curator(tmp_path):
    index_path = _index(tmp_path)
    ctx, agents = make_ctx(tmp_path, f'reference_index = "{index_path}"\n')
    source = tmp_path / "legacy.json"
    source.write_text(json.dumps(PLAN, ensure_ascii=False), "utf-8")
    plan = import_plan(ctx, "legacy", source)
    approved, _ = load_approved_plan(ctx, plan.characterId)
    queries = build_queries(approved)
    assert queries["VOICE"] == "\n".join(approved.coreTraits)
    assert queries["DATA"] == approved.job
    agents.set("s3r", lambda req: _selected("STANFORD:P29"))
    assert run_s3r(ctx, plan.characterId).name == "rs1"


def test_codex_checks_use_same_constraints(tmp_path, monkeypatch):
    ctx, _, cid, _ = _ready(tmp_path)
    from acf.checks import registry

    original = registry.stage_checks
    monkeypatch.setattr(
        registry,
        "stage_checks",
        lambda stage, workspace: (
            codex_checks(stage, workspace) if stage == "s3r" else original(stage, workspace)
        ),
    )

    def writer(workspace, prompt, attempt):
        if attempt == 1:
            return _selected("OTHER:missing")
        assert "검색 후보에 없는 선택" in prompt
        return _selected()

    backend = FakeCodexAgent(writer=writer)
    ctx.use_codex(backend)
    rev_dir = run_s3r(ctx, cid)
    assert len(backend.calls) == 2
    assert (rev_dir / "workspace/AGENTS.md").exists()
    assert (rev_dir / "workspace/check.sh").exists()
    assert load_latest_reference_set(ctx, cid).selected[0].itemId == "AUTHORED:synthetic-r1:traits"
