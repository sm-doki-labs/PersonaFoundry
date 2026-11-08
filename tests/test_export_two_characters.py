"""두 합성 트윈을 한 앱에 넣고 다시 넣어도 각자의 콘텐츠를 읽을 수 있다."""

import os
from contextlib import ExitStack
from dataclasses import replace

import pytest

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import read_json
from character_factory_poc.stages.export import verify
from character_factory_poc.stages.export.doki_app import naming
from character_factory_poc.stages.export.export import TargetHeads, export_doki_app
from character_factory_poc.stages.export.pg_admin import (
    PostgresAdmin,
    SqlClient,
    SubprocessRunner,
    create_database,
    drop_database,
    new_database_name,
)
from character_factory_poc.stages.export.settings import (
    API_SVC_HEAD,
    CHAT_SVC_HEAD,
    load_export_settings,
)
from character_factory_poc.stages.s11_release.package import build_package
from tests import test_twin_export as twin
from tests.support.export_flow import approve_package


def test_legacy_original_numbers():
    row_id = naming.api_seed_ids("cf-20261107-cf-20261107-testpath-s07")
    assert row_id("character", 0) == 900001
    assert row_id("character_profile_card", 0) == 900002
    assert row_id("character_stage", 1) == 900102
    assert row_id("file_store", 0) == 1803002
    assert row_id("media", 0) == 901001
    assert row_id("character_media", 1) == 903002
    assert row_id("character_clip", 1) == 904002
    assert row_id("character_clip_slot", 1) == 906002
    assert row_id("character_video", 0) == 905001


def test_reject_overflow():
    row_id = naming.api_seed_ids("synthetic-a", ["synthetic-a"])
    with pytest.raises(FactoryError, match="구간을 벗어나요"):
        row_id("media", 1024)


@pytest.fixture
def exports(tmp_path, monkeypatch):
    make_twin = twin._twin
    exports = []
    for mode, cid in [
        ("TRAIN", "cf-20261108-test-train"),
        ("PROMPT_ONLY", "cf-20261108-test-prompt"),
    ]:
        with monkeypatch.context() as patch:
            patch.setattr(twin, "_twin", lambda ctx, unused, cid=cid: make_twin(ctx, cid))
            ctx, _, _, _ = twin._approved(tmp_path, mode)
        build_package(ctx, cid)
        approve_package(ctx, cid)
        settings = replace(load_export_settings(ctx), default_voice_id=twin.VOICE)
        _, folder = export_doki_app(
            ctx, cid, settings=settings, heads=TargetHeads(API_SVC_HEAD, CHAT_SVC_HEAD)
        )
        exports.append(folder / "doki-app")
    return ctx, settings, exports


def test_all_seed_ids_are_disjoint(exports):
    ctx, settings, folders = exports
    first, second = [read_json(f / "api-svc/seed.json")["tables"] for f in folders]
    cid = "cf-20261108-test-train"
    _, repeat = export_doki_app(
        ctx, cid, settings=settings, heads=TargetHeads(API_SVC_HEAD, CHAT_SVC_HEAD)
    )
    repeated = read_json(repeat / "doki-app/api-svc/seed.json")["tables"]
    assert first.keys() == second.keys() == repeated.keys()
    for table in first:
        a, b = ({r[0] for r in seed[table]["rows"]} for seed in (first, second))
        assert a == {r[0] for r in repeated[table]["rows"]}
        assert a and b and a.isdisjoint(b), table
        assert 2_000_000 <= min(a | b) <= max(a | b) < 2**31


def test_colliding_character_folders_stop_export(exports, monkeypatch):
    ctx, settings, _ = exports
    monkeypatch.setattr(naming, "_block", lambda cid: 2_000_000)
    cid = "cf-20261108-test-train"
    with pytest.raises(FactoryError, match="구간이 겹쳐요"):
        export_doki_app(ctx, cid, settings=settings, heads=TargetHeads(API_SVC_HEAD, CHAT_SVC_HEAD))
    assert not (ctx.character_dir(cid) / "sx-export/ex2").exists()


@pytest.mark.skipif(not os.environ.get("CFP_PG_ADMIN_URL"), reason="일회용 PostgreSQL 미설정")
def test_two_twins_share_each_service_database(exports, tmp_path):
    _, settings, folders = exports
    admin = PostgresAdmin.parse(os.environ["CFP_PG_ADMIN_URL"])
    runner = SubprocessRunner()
    sql = SqlClient(admin, runner, python=verify.sql_python(settings))
    api, chat = settings.api_svc_repo, settings.chat_svc_repo
    api_db, chat_db = new_database_name("api"), new_database_name("chat")

    def run(repo, *args):
        env = verify._api_env(admin, api_db) if repo == api else verify._chat_env(admin, chat_db)
        result = runner.run(verify._cmd(repo, "-m", *args), cwd=repo, env=env)
        assert result.ok, verify._tail(result)

    seeds = [read_json(folder / "api-svc/seed.json")["tables"] for folder in folders]
    with ExitStack() as cleanup:
        for db, repo in [(api_db, api), (chat_db, chat)]:
            create_database(sql, db)
            cleanup.callback(drop_database, sql, db)
            run(repo, "alembic", "upgrade", "head")
        for _ in range(2):
            for folder in folders:
                run(api, "scripts.seed", "--file", str(folder / "api-svc/seed.json"), "load")
            for seed in seeds:
                uid = seed["character"]["rows"][0][
                    seed["character"]["columns"].index("character_uid")
                ]
                verify._check_api(sql, api_db, uid, len(seed["character_clip"]["rows"]))
            # 모든 표의 PK와 연결 키를 그대로 대조한다(단계·클립·슬롯·음성·미디어 포함).
            for name, table in seeds[0].items():
                columns = [
                    c
                    for c in table["columns"]
                    if c == "id" or c.endswith(("_id", "_uid")) or c == "key"
                ]
                indices = [table["columns"].index(c) for c in columns]
                expected = sorted(
                    (
                        [None if r[i] is None else str(r[i]) for i in indices]
                        for seed in seeds
                        for r in seed[name]["rows"]
                    ),
                    key=lambda r: int(r[0]),
                )
                actual = sql.execute(
                    f"SELECT {','.join(columns)} FROM {name} WHERE id >= 2000000 ORDER BY id",
                    database=api_db,
                )
                assert actual == expected, name

        assert sql.execute(
            "SELECT nextval(pg_get_serial_sequence('character','id')) = max(id) + 1 FROM character",
            database=api_db,
        ) == [["True"]]

        data = chat / "data"
        for i, folder in enumerate(folders):
            merged = tmp_path / f"data-{i}"
            verify._overlay_tree(data, folder / "chat-svc", merged)
            data = merged
            run(chat, "scripts.db_ops.content_release", "publish", "--data-dir", str(data))
        run(chat, "scripts.db_ops.content_release", "verify", "--data-dir", str(data))
        for cid in ["cf-20261108-test-train", "cf-20261108-test-prompt"]:
            uid = naming.character_uid(cid)
            assert sql.execute(
                "SELECT k.chapter_uid FROM content.content_release_head h "
                "JOIN content.release_characters c USING (release_id) "
                "JOIN content.release_chapters k USING (release_id, character_uid, locale) "
                f"WHERE c.character_uid = '{uid}' AND c.locale = 'ko' ORDER BY k.number",
                database=chat_db,
            ) == [[str(naming.chapter_uid(cid, f"ch{i}"))] for i in range(1, 4)]
