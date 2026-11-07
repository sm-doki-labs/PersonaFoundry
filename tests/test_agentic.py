"""codex_exec 백엔드(가짜)·오케스트레이터·검사 CLI·오염 탐지 테스트."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import character_factory_poc.contracts  # noqa: F401
from character_factory_poc.checks.cli import main as check_main
from character_factory_poc.cli import main
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.orchestrator import RunOptions, run_until
from character_factory_poc.providers.codex_exec import find_tainted_paths
from character_factory_poc.providers.fake import FakeTextModel
from character_factory_poc.providers.fake_codex import FakeCodexAgent
from tests.support.synthetic import PLAN, prompter_output, trait_sheet

CATALOG = {
    "schema_version": "3.0",
    "presets": [
        {
            "preset_id": "P29",
            "name": "먼저 움직이는 실용가",
            "summary": "먼저 제안하고 움직인다.",
            "stance": "주도형",
            "expression_focus": [
                {
                    "role": "핵심",
                    "domain": "외향성",
                    "behavior": "누군가 먼저 정하기를 기다리기보다 행동을 제안한다.",
                },
                {
                    "role": "핵심",
                    "domain": "신경성",
                    "behavior": "작은 실패나 변경에도 다른 방법을 찾아 움직인다.",
                },
                {
                    "role": "대비",
                    "domain": "성실성",
                    "behavior": "빠르게 시작하더라도 맡은 부분의 완료는 확인한다.",
                },
            ],
            "values": {"names": ["성취"]},
            "speech": {"primary": "핵심전달형", "secondary": "유머활용형"},
            "utterance_examples": ["내가 이 부분부터 할게."],
            "personality_data": {"x": 1},
            "core_system_prompt": "...",
        }
    ],
}

BRIEF = "타깃: 20대. 분위기: 밝고 실용적. 프리셋: P29를 쓴다. 챕터 1은 동네 러닝 크루 모임 뒤다."


def _plan_from_preset(cid: str, rev: str) -> dict:
    p = dict(PLAN)
    p.update(
        {
            "schemaVersion": "character-plan-v1",
            "characterId": cid,
            "planRev": rev,
            "evidence": {
                "name": [{"kind": "USER", "ref": "planner", "quote": ""}],
                "age": [{"kind": "USER", "ref": "planner", "quote": ""}],
                "job": [{"kind": "USER", "ref": "planner", "quote": ""}],
                "coreTraits": [
                    {
                        "kind": "PRESET",
                        "ref": "STANFORD:P29:3.0",
                        "quote": "누군가 먼저 정하기를 기다리기보다 행동을 제안한다.",
                    }
                ],
                "contrastTrait": [
                    {
                        "kind": "PRESET",
                        "ref": "STANFORD:P29:3.0",
                        "quote": "빠르게 시작하더라도 맡은 부분의 완료는 확인한다.",
                    }
                ],
                "chapters": [
                    {"kind": "BRIEF", "ref": "brief.md", "quote": "동네 러닝 크루 모임 뒤"}
                ],
            },
            "notes": "브리프가 P29를 지정했다. 이름·직업·챕터 2·3은 창작 설정이다.",
        }
    )
    return p


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    (tmp_path / "catalog.json").write_text(
        json.dumps(CATALOG, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "factory.toml").write_text(
        f'[agent]\nbackend = "codex_exec"\nmodel = "fake"\n\n[resources]\n'
        f'stanford_presets_json = "{tmp_path / "catalog.json"}"\n',
        encoding="utf-8",
    )
    c = Context.load(tmp_path, execute=True)
    return c


def _writer(ws: Path, prompt: str, attempt: int):
    """단계별 가짜 에이전트: 작업 공간 inputs를 읽어 output.json을 만든다."""
    from tests.support.flow import variants_from_workspace

    variants = variants_from_workspace(ws)
    if variants is not None:  # s3: D-0080 브리프 → 씨앗 → 변형
        return variants
    ids = ws / "inputs" / "ids.json"
    if ids.exists():  # s3
        d = json.loads(ids.read_text("utf-8"))
        return _plan_from_preset(d["characterId"], d["planRev"])
    if (ws / "inputs" / "character-plan.json").exists() and not (
        ws / "inputs" / "trait-sheet.json"
    ).exists():  # s7: S8도 이제 승인 기획을 받는다
        plan = json.loads((ws / "inputs" / "character-plan.json").read_text("utf-8"))
        # 구형 기획서(프리셋 기반)일 때만 프리셋 카드가 자동으로 들어온다.
        if plan.get("schemaVersion") == "character-plan-v1":
            assert (ws / "inputs" / "reference-doc-P29.json").exists()
        return trait_sheet(plan["characterId"], plan["planRev"])
    if (ws / "inputs" / "sections.json").exists():  # s8
        return prompter_output()
    return None


def test_run_until_g6_with_codex_backend(ctx, tmp_path):
    codex = FakeCodexAgent(writer=_writer)
    ctx.use_codex(codex)
    text = FakeTextModel()
    text.add("PROBE", lambda req: "그럼 이렇게 하자.")
    judge = FakeTextModel(model="fake-judge")
    judge.add("JUDGE", {"pick": "B", "reasons": "x"})
    ctx.use_models(text, judge)

    from character_factory_poc.stages.s3_plan.common import new_character

    cid = new_character(ctx, "codexrun")
    opt = RunOptions(until="G6", auto_approve={"G3"}, brief_text=BRIEF, voice_probes=["안녕"])
    log = run_until(ctx, cid, opt)
    assert log.stopped_at == "G6"
    st = ctx.state(cid)
    assert st.gate("G3").status == "APPROVED"
    rec = json.loads((ctx.character_dir(cid) / "gates" / "G3-pr1.json").read_text("utf-8"))
    assert rec["reviewer"].startswith("auto:")
    assert st.stage("s7").status == "AWAITING_HUMAN"
    assert st.gate("G6").status == "AWAITING_HUMAN"
    # 작업 공간에 AGENTS.md·check.sh·inputs가 있었고 codex가 세 단계에서 각각 한 번 호출됐다
    assert len(codex.calls) == 3
    ws3 = ctx.character_dir(cid) / "s3-plan" / "pr1" / "workspace"
    assert (ws3 / "AGENTS.md").exists() and (ws3 / "check.sh").exists()
    assert "plan_variants" in (ws3 / "AGENTS.md").read_text("utf-8")  # D-0080 브리프 → 변형
    # 원장에 codex 호출이 AGENT로 기록됐다
    kinds = [c["kind"] for c in ctx.ledger(cid).calls()]
    assert kinds.count("AGENT") == 3
    # 두 번째 실행은 전부 건너뛰고 G6에서 멈춘다
    log2 = run_until(ctx, cid, opt)
    assert log2.stopped_at == "G6" and len(codex.calls) == 3


def test_taint_detection(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    ok = ["/bin/zsh -lc 'cat inputs/plan.json'", "./check.sh", f"/bin/zsh -lc 'ls {ws}/inputs'"]
    assert find_tainted_paths(ok, ws, []) == []
    bad = ["/bin/zsh -lc 'cat /Users/x/secret.txt'", "cat ../other/file", "cat ~/.zshrc"]
    found = find_tainted_paths(bad, ws, [])
    assert len(found) == 3
    # 한국어 말투 표기의 물결표는 경로가 아니다(2026-10-22 실제 실행 오탐)
    speech = [
        "/bin/zsh -lc \"cat > scratch/gen.py <<'EOF'\nv = \\\"'~요', '~죠'로 끝맺는다\\\"\nEOF\""
    ]
    assert find_tainted_paths(speech, ws, []) == []
    assert find_tainted_paths(["cd ~ && ls", "ls ~", "cat > /tmp/gen.py"], ws, []) == [
        "/tmp/gen.py",
        "~",
    ]


def test_codex_backend_retries_with_feedback(ctx, tmp_path):
    """D-0080: 변형 경로에서도 검사 실패 사유를 붙여 codex를 다시 부른다."""
    from character_factory_poc.stages.s3_plan.common import new_character
    from character_factory_poc.stages.s3_plan.seed import write_seed
    from character_factory_poc.stages.s3_plan.variants import run_s3_variants
    from tests.support.flow import variants_from_workspace

    def writer(ws: Path, prompt: str, attempt: int):
        out = variants_from_workspace(ws)
        if attempt == 1:
            out["variants"][0]["coreTraits"] = ["밝음, 솔직함"]
        return out

    codex = FakeCodexAgent(writer=writer)
    ctx.use_codex(codex)
    cid = new_character(ctx, "retry")
    write_seed(ctx, cid, {"personality": "조용하지만 단단함"})
    run_s3_variants(ctx, cid)
    assert len(codex.calls) == 2
    assert "행동을 서술" in codex.calls[1][1]


def test_check_cli(ctx, tmp_path):
    from tests.support.flow import variants_for_seed

    ws = tmp_path / "ws"
    (ws / "inputs").mkdir(parents=True)
    seed = {
        "schemaVersion": "plan-seed-v1",
        "characterId": "cf-20260101-x",
        "seedRev": "sd1",
        "personality": "조용하지만 단단함",
    }
    ids = {"characterId": "cf-20260101-x", "planRev": "pr1", "seedRev": "sd1"}
    for name, value in (("seed", seed), ("ids", ids), ("variant-count", 3), ("name-guard", [])):
        (ws / "inputs" / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False), "utf-8")
    assert check_main(["s3-variants", str(ws)]) == 1  # output.json 없음
    (ws / "output.json").write_text(
        json.dumps(variants_for_seed(seed, ids), ensure_ascii=False), encoding="utf-8"
    )
    assert check_main(["s3-variants", str(ws)]) == 0
    assert main(["--root", str(tmp_path), "check", "s3-variants", str(ws)]) == 0
