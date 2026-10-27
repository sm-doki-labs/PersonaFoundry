"""일회용 PostgreSQL 관리 (LLD §8.11).

규칙:
- 관리자 접속 정보는 환경변수 이름으로만 받는다. 값은 로그·기록·오류에 남기지 않는다.
- 로컬 개발 컨테이너(`dokilabs-local-api-db-1:5432`, `dokilabs-local-chat-db-1:54329`)에는
  절대 연결하지 않는다.
- 만든 데이터베이스 이름은 `cfp_verify_*`만 쓰고, 그 이름만 지운다.

SQL은 이 프로젝트 코드가 문장으로 만들고, 실행만 대상 저장소의 가상환경 python(psycopg)에
맡긴다. 이 프로젝트는 DB 드라이버 의존성을 갖지 않는다(pyproject 고정).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlsplit

from character_factory_poc.common.errors import FactoryError

#: 로컬 개발용 컨테이너. 여기에는 절대 붙지 않는다.
DEV_PORTS = frozenset({5432, 54329})
DEV_HOSTS = frozenset(
    {"dokilabs-local-api-db-1", "dokilabs-local-chat-db-1", "host.docker.internal"}
)
_DATABASE_NAME = re.compile(r"^cfp_verify_[a-z0-9_]{1,40}$")
_SCHEMES = frozenset({"postgresql", "postgres", "postgresql+psycopg", "postgresql+psycopg2"})


class PostgresAdminError(FactoryError):
    """일회용 DB 전제가 깨졌다."""


@dataclass(frozen=True)
class PostgresAdmin:
    """관리자 DSN. repr·문자열 변환에 비밀번호를 싣지 않는다."""

    host: str
    port: int
    user: str
    password: str = field(repr=False)
    database: str = "postgres"

    @classmethod
    def parse(cls, raw: str) -> PostgresAdmin:
        text = (raw or "").strip()
        if not text:
            raise PostgresAdminError("관리자 DSN이 비어 있다")
        parts = urlsplit(text)
        if parts.scheme not in _SCHEMES:
            raise PostgresAdminError("관리자 DSN은 postgresql:// URL이어야 한다")
        if not parts.hostname or not parts.path.strip("/"):
            raise PostgresAdminError("관리자 DSN에 호스트와 데이터베이스 이름이 필요하다")
        try:
            port = parts.port or 5432
        except ValueError as exc:  # 포트 파싱 실패도 값 없이 알린다
            raise PostgresAdminError("관리자 DSN의 포트가 올바르지 않다") from exc
        if parts.query:
            raise PostgresAdminError("관리자 DSN에 쿼리 매개변수를 쓰지 않는다")
        admin = cls(
            host=parts.hostname,
            port=int(port),
            user=unquote(parts.username or ""),
            password=unquote(parts.password or ""),
            database=unquote(parts.path.strip("/")),
        )
        admin.require_disposable()
        return admin

    def require_disposable(self) -> None:
        """로컬 개발 컨테이너·기본 포트를 거절한다."""
        if self.port in DEV_PORTS or self.host in DEV_HOSTS:
            raise PostgresAdminError(
                "로컬 개발 컨테이너에는 연결하지 않는다. 일회용 PostgreSQL의 관리자 DSN을 쓴다"
            )
        if not self.user:
            raise PostgresAdminError("관리자 DSN에 사용자 이름이 필요하다")

    @property
    def redacted(self) -> str:
        return f"postgresql://{self.user}:***@{self.host}:{self.port}/{self.database}"

    def url(self, database: str, *, driver: str = "") -> str:
        scheme = "postgresql" + (f"+{driver}" if driver else "")
        auth = f"{self.user}:{self.password}@" if self.password else f"{self.user}@"
        return f"{scheme}://{auth}{self.host}:{self.port}/{database}"


@dataclass(frozen=True)
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class Runner(Protocol):
    """명령 실행기. 시험은 가짜 Runner로 순서·인자·실패 처리를 확인한다."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        stdin: str | None = None,
    ) -> CommandResult: ...


class SubprocessRunner:
    def __init__(self, timeout_s: float = 900.0):
        self.timeout_s = timeout_s

    def run(self, argv, *, cwd=None, env=None, stdin=None) -> CommandResult:
        merged = dict(os.environ)
        merged.update(env or {})
        try:
            completed = subprocess.run(
                list(argv),
                cwd=str(cwd) if cwd else None,
                env=merged,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                check=False,
            )
        except FileNotFoundError as exc:
            return CommandResult(list(argv), 127, "", f"명령을 찾을 수 없다: {exc}")
        except subprocess.TimeoutExpired:
            return CommandResult(list(argv), 124, "", "시간 초과")
        return CommandResult(list(argv), completed.returncode, completed.stdout, completed.stderr)


#: psycopg 실행 조각. DSN은 표준입력이 아니라 자식 프로세스 환경변수로만 넘긴다.
_SQL_SCRIPT = (
    "import json, os, sys\n"
    "import psycopg\n"
    "sql = sys.stdin.read()\n"
    "rows = []\n"
    "with psycopg.connect(os.environ['CFP_PG_DSN'], autocommit=True) as conn:\n"
    "    cur = conn.execute(sql)\n"
    "    if cur.description:\n"
    "        rows = [[None if value is None else str(value) for value in row]\n"
    "                for row in cur.fetchall()]\n"
    "sys.stdout.write(json.dumps(rows))\n"
)


class SqlClient:
    """관리자 SQL 실행기. 이름은 검증하고, 값은 자식 프로세스 환경으로만 넘긴다."""

    def __init__(
        self,
        admin: PostgresAdmin,
        runner: Runner,
        *,
        python: Path | None = None,
        timeout_s: float = 900.0,
    ):
        self.admin = admin
        self.runner = runner
        self.python = Path(python) if python else Path(sys.executable)
        self.timeout_s = timeout_s
        self.calls: list[list[str]] = []

    def execute(self, sql: str, *, database: str | None = None) -> list[list[str]]:
        target = database or self.admin.database
        result = self.runner.run(
            [str(self.python), "-c", _SQL_SCRIPT],
            env={"CFP_PG_DSN": self.admin.url(target)},
            stdin=sql,
        )
        self.calls.append(list(result.argv))
        if not result.ok:
            message = (result.stderr or result.stdout).strip().splitlines()
            detail = " / ".join(line.strip() for line in message[-4:] if line.strip())
            detail = detail[:400] or "이유 없음"
            raise PostgresAdminError(f"SQL 실패({target}): {detail}")
        try:
            payload = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise PostgresAdminError("SQL 결과를 읽지 못했다") from exc
        return payload


def new_database_name(kind: str) -> str:
    """`cfp_verify_<kind>_<8hex>` 이름 하나. 만든 이름만 지운다."""
    suffix = uuid.uuid4().hex[:8]
    name = f"cfp_verify_{kind}_{suffix}"
    if _DATABASE_NAME.match(name) is None:
        raise PostgresAdminError("일회용 DB 이름 형식이 아니다")
    return name


def assert_disposable_name(name: str) -> str:
    if _DATABASE_NAME.match(name) is None:
        raise PostgresAdminError(f"일회용 DB 이름이 아니다: {name!r}")
    return name


def create_database(sql: SqlClient, name: str) -> None:
    sql.execute(f'CREATE DATABASE "{assert_disposable_name(name)}"')


def drop_database(sql: SqlClient, name: str) -> None:
    """항상 지운다. 이미 없으면 넘어간다."""
    sql.execute(f'DROP DATABASE IF EXISTS "{assert_disposable_name(name)}" WITH (FORCE)')


def query(sql: SqlClient, database: str, sql_text: str) -> list[list[str]]:
    return sql.execute(sql_text, database=assert_disposable_name(database))


__all__ = [
    "DEV_HOSTS",
    "DEV_PORTS",
    "CommandResult",
    "PostgresAdmin",
    "PostgresAdminError",
    "Runner",
    "SqlClient",
    "SubprocessRunner",
    "assert_disposable_name",
    "create_database",
    "drop_database",
    "new_database_name",
    "query",
]
