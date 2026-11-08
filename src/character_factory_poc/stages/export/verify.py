"""일회용 PostgreSQL 적재 확인 (LLD §8.11).

두 개의 빈 데이터베이스를 만들어 대상 저장소의 마이그레이션으로 스키마를 올리고, 그 저장소의
공식 적재 명령으로 우리 묶음만 넣은 뒤 우리 캐릭터로 좁혀 조회하고, 항상 지운다.
dev/stage·로컬 개발 컨테이너에는 연결하지 않는다(`pg_admin`이 거절한다).
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from character_factory_poc.contracts.release import CharacterPackage, Verification, VerifyStep
from character_factory_poc.stages.export.doki_app.naming import character_uid, revision_prefix
from character_factory_poc.stages.export.pg_admin import (
    CommandResult,
    PostgresAdmin,
    PostgresAdminError,
    Runner,
    SqlClient,
    create_database,
    drop_database,
    new_database_name,
)
from character_factory_poc.stages.export.settings import ExportSettings

T = TypeVar("T")


class StepFailed(RuntimeError):
    """한 단계가 실패해 다음 단계를 멈춘다. DB 정리는 finally가 맡는다."""


@dataclass
class _Recorder:
    steps: list[VerifyStep] = field(default_factory=list)

    def run(self, name: str, fn: Callable[[], Any]) -> Any:
        try:
            value = fn()
        except (StepFailed, PostgresAdminError, OSError) as exc:
            self.steps.append(VerifyStep(name=name, ok=False, detail=str(exc)[:900]))
            raise StepFailed(name) from exc
        detail = value if isinstance(value, str) else ""
        self.steps.append(VerifyStep(name=name, ok=True, detail=detail[:900]))
        return value

    def note(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(VerifyStep(name=name, ok=ok, detail=detail[:400]))


def _tail(result: CommandResult) -> str:
    lines = (result.stderr or result.stdout).strip().splitlines()
    if not lines:
        return "이유 없음"
    return " / ".join(line.strip() for line in lines[-6:] if line.strip())[:700]


def _must(result: CommandResult, label: str) -> str:
    if not result.ok:
        raise StepFailed(f"{label}: {_tail(result)}")
    return ""


def _cmd(repo: Path, *args: str) -> list[str]:
    """저장소 가상환경이 있으면 그 python으로, 없으면 `uv run python`으로 부른다."""
    venv = repo / ".venv" / "bin" / "python"
    prefix = [str(venv)] if venv.is_file() else ["uv", "run", "python"]
    return [*prefix, *args]


def _chat_env(admin: PostgresAdmin, database: str) -> dict[str, str]:
    url = admin.url(database, driver="psycopg")
    return {
        "RQC_ENV": "local",
        "RQC_DATABASE_URL": url,
        "RQC_MIGRATION_DATABASE_URL": url,
        "RQC_CONTENT_DATABASE_URL": url,
    }


def _api_env(admin: PostgresAdmin, database: str) -> dict[str, str]:
    return {
        "DEBUG": "true",
        "POSTGRES_HOST": admin.host,
        "POSTGRES_PORT": str(admin.port),
        "POSTGRES_USER": admin.user,
        "POSTGRES_PASSWORD": admin.password,
        "POSTGRES_DB": database,
    }


def sql_python(settings: ExportSettings) -> Path | None:
    """psycopg가 있는 interpreter. 이 프로젝트는 DB 드라이버 의존성을 갖지 않는다."""
    if settings.sql_python:
        path = Path(settings.sql_python).expanduser()
        return path if path.is_file() else None
    for repo in (settings.chat_svc_repo, settings.api_svc_repo):
        candidate = repo / ".venv" / "bin" / "python"
        if candidate.is_file():
            return candidate
    return None


def _overlay_tree(repo_data: Path, fragment: Path, dest: Path) -> str:
    """저장소 `data/` 복사본 위에 우리 조각을 덮고 포인터를 합친다."""
    shutil.copytree(repo_data, dest)
    merged = 0
    for path in sorted(fragment.rglob("*.json")):
        rel = path.relative_to(fragment)
        target = dest / rel
        if rel.as_posix() == "pointers/content-pointers-v2.json":
            merged = _merge_pointers(target, path)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    return f"정의 {len(list(fragment.rglob('*.json')))}개, 포인터 {merged}개 합침"


def _merge_pointers(target: Path, addition: Path) -> int:
    base = json.loads(target.read_text(encoding="utf-8"))
    extra = json.loads(addition.read_text(encoding="utf-8"))
    if base.get("schemaVersion") != extra.get("schemaVersion"):
        raise StepFailed("포인터 매니페스트 schemaVersion이 다르다")
    entries = list(base.get("pointers") or [])
    seen = {(item.get("kind"), item.get("key"), item.get("locale")) for item in entries}
    merged = 0
    for item in extra.get("pointers") or []:
        identity = (item.get("kind"), item.get("key"), item.get("locale"))
        if identity in seen:
            continue
        entries.append(item)
        seen.add(identity)
        merged += 1
    target.write_text(
        json.dumps(
            {"schemaVersion": base["schemaVersion"], "pointers": entries},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return merged


def _count(client: SqlClient, database: str, sql: str) -> int:
    rows = client.execute(sql, database=database)
    return int(rows[0][0]) if rows and rows[0] and rows[0][0] is not None else 0


def verify_databases(
    *,
    settings: ExportSettings,
    heads,
    package: CharacterPackage,
    seed_path: Path,
    tree_dir: Path,
    runner: Runner,
    sql: SqlClient | None = None,
) -> Verification:
    """일회용 DB 두 개에 적재하고 우리 캐릭터로 좁혀 확인한다. 항상 지운다."""
    rec = _Recorder()
    raw = os.environ.get(settings.admin_url_env, "").strip()
    if not raw:
        rec.note("admin-url", False, f"환경변수 {settings.admin_url_env}가 비었다")
        return Verification(status="FAILED", disposableDb=True, steps=rec.steps)
    try:
        admin = PostgresAdmin.parse(raw)
    except PostgresAdminError as exc:
        rec.note("admin-url", False, str(exc))
        return Verification(status="FAILED", disposableDb=True, steps=rec.steps)
    interpreter = sql_python(settings)
    if sql is None and interpreter is None:
        rec.note(
            "sql-python", False, "psycopg가 있는 python을 찾지 못했다([export.verify] sql_python)"
        )
        return Verification(status="FAILED", disposableDb=True, steps=rec.steps)
    client = sql or SqlClient(admin, runner, python=interpreter, timeout_s=settings.timeout_s)
    rec.note(
        "target-heads",
        True,
        f"api-svc {heads.api_svc} · chat-svc {heads.chat_svc} (변환기가 아는 값과 같다)",
    )

    chat_repo, api_repo = settings.chat_svc_repo, settings.api_svc_repo
    chat_db, api_db = new_database_name("chat"), new_database_name("api")
    created: list[str] = []
    work = Path(tempfile.mkdtemp(prefix="cfp-verify-"))
    uid = str(character_uid(package.characterId))
    prefix = revision_prefix(package.characterId, package.packageRev, twin=bool(package.twin))
    persona_rev = f"{prefix}-r1"
    clips = sum(1 for video in package.videos if video.kind == "ACTION")
    try:
        rec.run("chat-svc.create-db", lambda: _create(client, chat_db, created))
        rec.run(
            "chat-svc.tree",
            lambda: _overlay_tree(chat_repo / "data", tree_dir, work / "data"),
        )
        rec.run(
            "chat-svc.alembic",
            lambda: _must(
                runner.run(
                    _cmd(chat_repo, "-m", "alembic", "upgrade", "head"),
                    cwd=chat_repo,
                    env=_chat_env(admin, chat_db),
                ),
                "alembic upgrade head",
            ),
        )
        rec.run(
            "chat-svc.publish",
            lambda: _must(
                runner.run(
                    _cmd(
                        chat_repo,
                        "-m",
                        "scripts.db_ops.content_release",
                        "publish",
                        "--data-dir",
                        str(work / "data"),
                    ),
                    cwd=chat_repo,
                    env=_chat_env(admin, chat_db),
                ),
                "content_release publish",
            ),
        )
        rec.run(
            "chat-svc.verify",
            lambda: _must(
                runner.run(
                    _cmd(
                        chat_repo,
                        "-m",
                        "scripts.db_ops.content_release",
                        "verify",
                        "--data-dir",
                        str(work / "data"),
                    ),
                    cwd=chat_repo,
                    env=_chat_env(admin, chat_db),
                ),
                "content_release verify",
            ),
        )
        rec.run("chat-svc.query", lambda: _check_chat(client, chat_db, uid, persona_rev))

        rec.run("api-svc.create-db", lambda: _create(client, api_db, created))
        rec.run(
            "api-svc.alembic",
            lambda: _must(
                runner.run(
                    _cmd(api_repo, "-m", "alembic", "upgrade", "head"),
                    cwd=api_repo,
                    env=_api_env(admin, api_db),
                ),
                "alembic upgrade head",
            ),
        )
        rec.run(
            "api-svc.seed-load",
            lambda: _must(
                runner.run(
                    _cmd(
                        api_repo,
                        "-m",
                        "scripts.seed",
                        "--file",
                        str(seed_path),
                        "load",
                    ),
                    cwd=api_repo,
                    env=_api_env(admin, api_db),
                ),
                "scripts.seed load",
            ),
        )
        rec.run("api-svc.query", lambda: _check_api(client, api_db, uid, clips))
    except StepFailed:
        pass
    finally:
        for name in reversed(created):
            try:
                drop_database(client, name)
                rec.note(f"drop {name.split('_')[-2]}", True, "일회용 DB를 지웠다")
            except (PostgresAdminError, OSError) as exc:
                rec.note("drop-db", False, str(exc)[:300])
        shutil.rmtree(work, ignore_errors=True)
    ok = bool(rec.steps) and all(step.ok for step in rec.steps)
    return Verification(status="PASSED" if ok else "FAILED", disposableDb=True, steps=rec.steps)


def _create(client: SqlClient, name: str, created: list[str]) -> str:
    create_database(client, name)
    created.append(name)
    return "일회용 DB를 만들었다"


def _check_chat(client: SqlClient, database: str, uid: str, persona_rev: str) -> str:
    characters = _count(
        client, database, f"SELECT count(*) FROM content.characters WHERE character_uid = '{uid}'"
    )
    if characters != 1:
        raise StepFailed(f"chat-svc characters 조회 {characters}건")
    chapters = _count(
        client, database, f"SELECT count(*) FROM content.chapters WHERE character_uid = '{uid}'"
    )
    if chapters != 3:
        raise StepFailed(f"chat-svc chapters 조회 {chapters}건(3이어야 한다)")
    versions = _count(
        client,
        database,
        "SELECT count(*) FROM content.character_versions "
        f"WHERE character_uid = '{uid}' AND persona->>'revision' = '{persona_rev}'",
    )
    if versions != 1:
        raise StepFailed(f"chat-svc persona revision 조회 {versions}건({persona_rev})")
    released = _count(
        client,
        database,
        f"SELECT count(*) FROM content.release_characters WHERE character_uid = '{uid}'",
    )
    return f"캐릭터 1 · 챕터 {chapters} · persona {persona_rev} · 릴리스 membership {released}"


def _check_api(client: SqlClient, database: str, uid: str, clips: int) -> str:
    characters = _count(
        client, database, f"SELECT count(*) FROM character WHERE character_uid = '{uid}'"
    )
    if characters != 1:
        raise StepFailed(f"api-svc character 조회 {characters}건")
    stages = _count(
        client,
        database,
        "SELECT count(*) FROM character_stage s JOIN character c ON c.id = s.character_id "
        f"WHERE c.character_uid = '{uid}'",
    )
    if stages != 3:
        raise StepFailed(f"api-svc character_stage 조회 {stages}건(3이어야 한다)")
    stored = _count(
        client,
        database,
        "SELECT count(*) FROM character_clip k "
        "JOIN character_stage s ON s.id = k.character_stage_id "
        "JOIN character c ON c.id = s.character_id "
        f"WHERE c.character_uid = '{uid}'",
    )
    if stored != clips:
        raise StepFailed(f"api-svc character_clip 조회 {stored}건(패키지 {clips}편)")
    media = _count(
        client,
        database,
        "SELECT count(*) FROM file_store f JOIN media m ON m.id = f.media_id "
        "JOIN character_media cm ON cm.media_id = m.id "
        f"JOIN character c ON c.id = cm.character_id WHERE c.character_uid = '{uid}'",
    )
    if media <= 0:
        raise StepFailed("api-svc file_store 조회 0건")
    return f"캐릭터 1 · 단계 {stages} · 클립 {stored} · 미디어 {media}"


__all__ = ["StepFailed", "sql_python", "verify_databases"]
