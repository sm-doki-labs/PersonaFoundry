"""S11 릴리즈 패키지와 우리 앱(doki-app) 변환기 (LLD §5.17·§8.10·§8.11).

가짜 공급자·합성 자료로 패키지 생성·해시 검사·G9·변환 규칙·head 거절·적재 순서를 확인하고,
`ACF_PG_ADMIN_URL`이 있을 때만 일회용 PostgreSQL 실제 적재를 한 번 돌린다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from acf.common.errors import CheckFailed, FactoryError
from acf.common.store import read_json, verify_manifest
from acf.stages.export.doki_app import api_svc, chat_svc
from acf.stages.export.export import TargetHeads, ensure_heads, export_doki_app
from acf.stages.export.pg_admin import CommandResult, PostgresAdmin
from acf.stages.export.settings import API_SVC_HEAD, CHAT_SVC_HEAD, ExportSettings
from acf.stages.s11_release.approve import approve_g9
from acf.stages.s11_release.package import (
    build_package,
    load_package,
    verify_package_files,
)
from tests.support.export_flow import approve_package, fix_sft, full_flow

HEADS = TargetHeads(api_svc=API_SVC_HEAD, chat_svc=CHAT_SVC_HEAD, api_svc_commit="abc1234")


class FakeRunner:
    """명령 실행을 기록만 한다. fail_on에 든 조각이 argv에 있으면 실패한다."""

    def __init__(self, fail_on: str | None = None):
        self.fail_on = fail_on
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []

    def run(self, argv, *, cwd=None, env=None, stdin=None):
        argv = [str(arg) for arg in argv]
        self.calls.append(argv)
        self.envs.append(dict(env or {}))
        if self.fail_on and any(self.fail_on in arg for arg in argv):
            return CommandResult(argv, 1, "", f"{self.fail_on} 실패")
        return CommandResult(argv, 0, "", "")


class FakeSql:
    """CREATE/DROP과 조회를 흉내 낸다. 적재 결과 건수는 고정값이다."""

    def __init__(self, clips: int = 3):
        self.clips = clips
        self.calls: list[tuple[str, str | None]] = []

    def execute(self, sql: str, *, database: str | None = None) -> list[list[str]]:
        self.calls.append((sql, database))
        if sql.startswith("SELECT"):
            if "content.characters" in sql:
                return [["1"]]
            if "content.chapters" in sql:
                return [["3"]]
            if "content.character_versions" in sql:
                return [["1"]]
            if "content.release_characters" in sql:
                return [["1"]]
            if "FROM character_stage" in sql:
                return [["3"]]
            if "FROM character_clip" in sql:
                return [[str(self.clips)]]
            if "FROM character WHERE" in sql:
                return [["1"]]
            if "FROM file_store" in sql:
                return [["7"]]
        return []


def _settings(tmp_path: Path) -> ExportSettings:
    api, chat = tmp_path / "api-svc", tmp_path / "chat-svc"
    for repo in (api, chat):
        (repo / "data" / "pointers").mkdir(parents=True)
        (repo / "data" / "pointers" / "content-pointers-v2.json").write_text(
            json.dumps(
                {
                    "schemaVersion": "content-pointer-manifest-v2",
                    "pointers": [
                        {
                            "kind": "quest",
                            "key": "00000000-0000-0000-0000-000000000001",
                            "state": "ACTIVE",
                            "revision": "other-quest-v1",
                            "locale": "ko",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return ExportSettings(api_svc_repo=api, chat_svc_repo=chat, admin_url_env="ACF_TEST_ADMIN_URL")


@pytest.fixture
def flow(tmp_path):
    ctx, cid = full_flow(tmp_path)
    return ctx, cid


def test_package_build_and_g9(flow):
    ctx, cid = flow
    rev_dir = build_package(ctx, cid)
    assert rev_dir.name == "pk1"
    package = read_json(rev_dir / "package.json")
    assert package["schemaVersion"] == "character-package-v1"
    assert package["packageRev"] == "pk1"
    assert [chapter["chapterNo"] for chapter in package["chapters"]] == [1, 2, 3]
    assert package["sft"]["datasetRev"] is None
    assert package["persona"]["longPrompt"] == "persona/long-prompt.txt"
    assert package["videos"][0]["kind"] == "INTRO"
    assert any(video["kind"] == "ACTION" for video in package["videos"])
    assert all(video["synthetic"] for video in package["videos"])
    assert {gate["gate"] for gate in package["gates"]} >= {"G1", "G3", "G4", "G5", "G5b", "G6"}
    assert verify_manifest(rev_dir) == []
    loaded, _ = load_package(ctx, cid)
    assert verify_package_files(loaded, rev_dir) == []
    assert (rev_dir / "gate-G9.html").is_file()
    page = (rev_dir / "gate-G9.html").read_text("utf-8")
    assert package["profile"]["name"] in page
    assert "가짜 공급자로 만든 영상" in page and "SFT" in page
    assert ctx.state(cid).gate("G9").status == "AWAITING_HUMAN"

    with pytest.raises(FactoryError):
        approve_g9(ctx, cid, {"decision": "SELECT", "reviewer": "u"})

    approve_g9(ctx, cid, {"decision": "APPROVE", "reasons": "좋다", "reviewer": "u"})
    assert ctx.state(cid).gate("G9").status == "APPROVED"
    assert ctx.state(cid).stage("s11").status == "APPROVED"
    record = read_json(ctx.character_dir(cid) / "gates" / "G9-pk1.json")
    assert record["decision"] == "APPROVE"


def test_package_hash_mismatch_stops(flow):
    ctx, cid = flow
    frame = ctx.character_dir(cid) / "s4-frames" / "fr1" / "ch1" / "f1.png"
    frame.write_bytes(frame.read_bytes() + b"tamper")
    with pytest.raises(CheckFailed):
        build_package(ctx, cid)
    assert ctx.state(cid).stage("s11").status == "CHECK_FAILED"
    assert not (ctx.character_dir(cid) / "s11-release" / "pk1" / "package.json").exists()


def test_package_sft_null_then_filled(flow):
    ctx, cid = flow
    first = build_package(ctx, cid)
    assert read_json(first / "package.json")["sft"]["datasetRev"] is None
    approve_g9(ctx, cid, {"decision": "APPROVE", "reasons": "", "reviewer": "u"})
    fix_sft(ctx, cid, adopted="gemma-binding")
    second = build_package(ctx, cid)
    assert second.name == "pk2"
    sft = read_json(second / "package.json")["sft"]
    assert sft["datasetRev"] == "ds1"
    assert sft["trainingRuns"] == ["sft/training-gemma_qlora.json"]
    assert sft["evalReport"] == "sft/eval-report.json"
    assert sft["adoptedBinding"] == "gemma-binding"
    assert (second / "sft" / "dataset.json").is_file()


def test_export_seed_bundle_rules(flow, tmp_path):
    ctx, cid = flow
    build_package(ctx, cid)
    approve_package(ctx, cid)
    settings = _settings(tmp_path)
    result, rev_dir = export_doki_app(ctx, cid, settings=settings, heads=HEADS)
    seed_path = rev_dir / "doki-app" / "api-svc" / "seed.json"
    seed = json.loads(seed_path.read_text("utf-8"))
    assert seed["format"] == "dokilabs-seed/1"
    assert seed["alembic_revision"] == API_SVC_HEAD
    assert api_svc.validate_seed_bundle(seed) == []
    assert "character" in seed["tables"] and "character_clip" in seed["tables"]
    stages = seed["tables"]["character_stage"]
    assert [row[2] for row in stages["rows"]] == [1, 2, 3]
    assert all(row[9] == "MISSION" and row[13] == 20 for row in stages["rows"])
    keys = [row[3] for row in seed["tables"]["file_store"]["rows"]]
    assert keys and all(key.startswith("api-svc/protected/characters/") for key in keys)
    clips = seed["tables"]["character_clip"]
    assert clips["rows"] and all(row[7] == "live" for row in clips["rows"])
    package, _ = load_package(ctx, cid)
    expected = {video.clipKey for video in package.videos if video.kind == "ACTION"}
    assert {row[2] for row in clips["rows"]} == expected
    assert result.verification.status == "NOT_RUN"


def test_export_chat_tree_rules(flow, tmp_path):
    ctx, cid = flow
    build_package(ctx, cid)
    approve_package(ctx, cid)
    settings = _settings(tmp_path)
    result, rev_dir = export_doki_app(ctx, cid, settings=settings, heads=HEADS)
    tree_dir = rev_dir / "doki-app" / "chat-svc"
    files = {
        path.relative_to(tree_dir).as_posix(): json.loads(path.read_text("utf-8"))
        for path in tree_dir.rglob("*.json")
    }
    assert chat_svc.validate_content_tree(files) == []
    personas = [payload for rel, payload in files.items() if rel.startswith("personas/")]
    assert len(personas) == 1
    assert personas[0]["schemaVersion"] == "character-persona-v6"
    assert all(personas[0][section] for section in chat_svc.PERSONA_SECTIONS)
    quests = [payload for rel, payload in files.items() if rel.startswith("quests/")]
    assert quests[0]["schemaVersion"] == "character-quest-v4"
    assert len(quests[0]["chapters"]) == 3
    pointer = files[f"pointers/{chat_svc.POINTER_MANIFEST}"]
    assert pointer["pointers"][0]["revision"] == quests[0]["questRevision"]
    bundles = [payload for rel, payload in files.items() if rel.startswith("split_prompt_bundles/")]
    assert len(bundles) == 3
    assert all(bundle["frameRevision"] == chat_svc.PROMPT_FRAME_REVISION for bundle in bundles)
    outputs = {output.system: output for output in result.outputs}
    assert outputs["chat-svc"].path == "doki-app/chat-svc"
    assert outputs["api-svc"].kind == "seed-bundle"


def test_export_result_mapping_and_heads(flow, tmp_path):
    ctx, cid = flow
    build_package(ctx, cid)
    approve_package(ctx, cid)
    settings = _settings(tmp_path)
    result, rev_dir = export_doki_app(ctx, cid, settings=settings, heads=HEADS)
    assert result.target == "doki-app"
    assert result.targetVersions["api-svc"] == f"{API_SVC_HEAD}@abc1234"
    sources = {row.source for row in result.mapping}
    assert "profile.name" in sources and "characterId" in sources
    assert any("favoriteFoods" in item for item in result.unmapped)
    assert any("persona.shortPrompt" in item for item in result.unmapped)
    written = read_json(rev_dir / "export-result.json")
    assert written["schemaVersion"] == "export-result-v1"

    with pytest.raises(FactoryError):
        ensure_heads(TargetHeads(api_svc="0001_old", chat_svc=CHAT_SVC_HEAD))
    with pytest.raises(FactoryError):
        export_doki_app(
            ctx,
            cid,
            settings=settings,
            heads=TargetHeads(api_svc=API_SVC_HEAD, chat_svc="0001_old"),
        )


def test_rule_validators_catch_violations(flow, tmp_path):
    """재현한 규칙이 실제로 위반을 잡는지 확인한다(통과만 하는 검사가 아니다)."""
    ctx, cid = flow
    build_package(ctx, cid)
    approve_package(ctx, cid)
    result, rev_dir = export_doki_app(ctx, cid, settings=_settings(tmp_path), heads=HEADS)
    tree_dir = rev_dir / "doki-app" / "chat-svc"
    files = {
        path.relative_to(tree_dir).as_posix(): json.loads(path.read_text("utf-8"))
        for path in tree_dir.rglob("*.json")
    }
    persona_rel = next(rel for rel in files if rel.startswith("personas/"))
    broken = json.loads(json.dumps(files))
    broken[persona_rel].pop("voice")
    assert any("voice" in problem for problem in chat_svc.validate_content_tree(broken))

    seed = json.loads((rev_dir / "doki-app" / "api-svc" / "seed.json").read_text("utf-8"))
    legacy = json.loads(json.dumps(seed))
    legacy["tables"]["character_chapter"] = {"columns": ["id"], "rows": [[1]]}
    assert any("옛 표" in problem for problem in api_svc.validate_seed_bundle(legacy))
    no_uid = json.loads(json.dumps(seed))
    no_uid["tables"]["character_stage"]["columns"].remove("stage_uid")
    assert any("stage_uid" in problem for problem in api_svc.validate_seed_bundle(no_uid))
    assert result.verification.status == "NOT_RUN"


def test_verify_order_and_drop(flow, tmp_path):
    ctx, cid = flow
    build_package(ctx, cid)
    approve_package(ctx, cid)
    settings = _settings(tmp_path)
    runner = FakeRunner()
    sql = FakeSql(clips=_action_clips(ctx, cid))
    os.environ[settings.admin_url_env] = (
        "postgresql://acf_admin:acf-verify-local@127.0.0.1:55439/postgres"
    )
    try:
        result, _ = export_doki_app(
            ctx, cid, verify=True, settings=settings, runner=runner, heads=HEADS, sql=sql
        )
    finally:
        os.environ.pop(settings.admin_url_env, None)
    assert result.verification.status == "PASSED"
    joined = [" ".join(call) for call in runner.calls]
    assert "alembic upgrade head" in joined[0]
    assert any("content_release publish" in call for call in joined)
    assert any("content_release verify" in call for call in joined)
    assert any("scripts.seed" in call and " load" in call for call in joined)
    statements = [sql_text for sql_text, _ in sql.calls]
    assert statements[0].startswith("CREATE DATABASE")
    assert statements[-1].startswith("DROP DATABASE")
    assert sum(1 for text in statements if text.startswith("CREATE DATABASE")) == 2
    assert sum(1 for text in statements if text.startswith("DROP DATABASE")) == 2
    assert not any("5432" in env.get("RQC_DATABASE_URL", "") for env in runner.envs)


def test_verify_drops_database_when_load_fails(flow, tmp_path):
    ctx, cid = flow
    build_package(ctx, cid)
    approve_package(ctx, cid)
    settings = _settings(tmp_path)
    runner = FakeRunner(fail_on="content_release")
    sql = FakeSql()
    os.environ[settings.admin_url_env] = (
        "postgresql://acf_admin:acf-verify-local@127.0.0.1:55439/postgres"
    )
    try:
        with pytest.raises(CheckFailed):
            export_doki_app(
                ctx, cid, verify=True, settings=settings, runner=runner, heads=HEADS, sql=sql
            )
    finally:
        os.environ.pop(settings.admin_url_env, None)
    statements = [text for text, _ in sql.calls]
    assert statements[0].startswith("CREATE DATABASE")
    assert any(text.startswith("DROP DATABASE") for text in statements)
    assert ctx.state(cid).stage("sx").status == "CHECK_FAILED"


def test_verify_without_admin_env(flow, tmp_path):
    ctx, cid = flow
    build_package(ctx, cid)
    approve_package(ctx, cid)
    settings = _settings(tmp_path)
    os.environ.pop(settings.admin_url_env, None)
    with pytest.raises(CheckFailed):
        export_doki_app(
            ctx,
            cid,
            verify=True,
            settings=settings,
            runner=FakeRunner(),
            heads=HEADS,
            sql=FakeSql(),
        )


def test_admin_url_rejects_dev_containers():
    from acf.stages.export.pg_admin import PostgresAdminError

    with pytest.raises(PostgresAdminError):
        PostgresAdmin.parse("postgresql://dokilabs:dokilabs-local@localhost:5432/api_svc")
    with pytest.raises(PostgresAdminError):
        PostgresAdmin.parse("postgresql://dokilabs:dokilabs-local@localhost:54329/chat_svc")
    admin = PostgresAdmin.parse("postgresql://acf_admin:acf-verify-local@127.0.0.1:55439/postgres")
    assert "acf-verify-local" not in admin.redacted


def _action_clips(ctx, cid) -> int:
    package, _ = load_package(ctx, cid)
    return sum(1 for video in package.videos if video.kind == "ACTION")


@pytest.mark.skipif(
    not os.environ.get("ACF_PG_ADMIN_URL"),
    reason="ACF_PG_ADMIN_URL이 없어 실제 적재를 건너뛴다",
)
def test_real_load_into_disposable_postgres(flow, tmp_path):
    """일회용 PostgreSQL 두 개에 실제로 적재하고 우리 캐릭터로 좁혀 확인한다."""
    from acf.stages.export.settings import load_export_settings

    ctx, cid = flow
    build_package(ctx, cid)
    approve_package(ctx, cid)
    result, rev_dir = export_doki_app(ctx, cid, verify=True, settings=load_export_settings(ctx))
    assert result.verification.status == "PASSED", [
        (step.name, step.detail) for step in result.verification.steps
    ]
    steps = [step.name for step in result.verification.steps]
    assert steps[0] == "target-heads"
    assert steps.index("chat-svc.create-db") < steps.index("api-svc.create-db")
    assert any(name.startswith("api-svc") for name in steps)
    assert sum(1 for name in steps if name.startswith("drop")) == 2
    assert (rev_dir / "export-result.json").is_file()
