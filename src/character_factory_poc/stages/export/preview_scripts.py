"""미리보기 발행이 대상 저장소 가상환경 안에서 돌리는 DB 조각.

공장은 DB 드라이버 의존성을 갖지 않는다(pg_admin과 같은 원칙). 아래 문자열을 대상 저장소의
python으로 실행하고, 요청은 표준입력 JSON으로, 접속 정보는 자식 프로세스 환경변수로만 넘긴다.
결과는 표준출력 JSON 한 줄이다. 값(DSN·토큰)은 출력하지 않는다.
"""

from __future__ import annotations

#: api-svc 가상환경(psycopg)에서 돈다. 환경변수 CFP_PG_DSN.
API_DB_SCRIPT = r"""
import json, os, sys
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

req = json.loads(sys.stdin.read())
op = req["op"]
LOCK = "cfp-preview-publish"


def columns(cur, table):
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def existing(cur, uid, handle):
    cur.execute(
        "SELECT id FROM character WHERE character_uid::text = %s OR handle = %s LIMIT 1",
        (uid, handle),
    )
    row = cur.fetchone()
    return row[0] if row else None


with psycopg.connect(os.environ["CFP_PG_DSN"]) as conn:
    cur = conn.cursor()
    if op == "inspect":
        cur.execute("SELECT version_num FROM alembic_version")
        heads = sorted(r[0] for r in cur.fetchall())
        cols, seqs = {}, {}
        for table in req["tables"]:
            cols[table] = columns(cur, table)
            seq = None
            if cols[table]:
                cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
                seq = cur.fetchone()[0]
            seqs[table] = seq
        out = {
            "heads": heads,
            "columns": cols,
            "sequences": seqs,
            "existing": existing(cur, req["uid"], req["handle"]),
        }
    elif op == "reserve":
        out = {"ids": {}}
        for table, count in req["counts"].items():
            cur.execute("SELECT pg_get_serial_sequence(%s, 'id')", (table,))
            seq = cur.fetchone()[0]
            if not seq:
                raise SystemExit(f"{table}: id 시퀀스가 없다")
            cur.execute(
                "SELECT nextval(%s::regclass) FROM generate_series(1, %s)", (seq, int(count))
            )
            out["ids"][table] = [int(r[0]) for r in cur.fetchall()]
        conn.commit()
    elif op == "insert":
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (LOCK,))
        if existing(cur, req["uid"], req["handle"]) is not None:
            raise SystemExit("같은 character_uid 또는 handle이 이미 있다")
        dropped, inserted = {}, {}
        for table in req["order"]:
            spec = req["tables"].get(table)
            if not spec or not spec["rows"]:
                continue
            live = set(columns(cur, table))
            if not live:
                raise SystemExit(f"{table}: 대상 DB에 표가 없다")
            keep = [i for i, c in enumerate(spec["columns"]) if c in live]
            lost = [c for c in spec["columns"] if c not in live]
            if lost:
                dropped[table] = lost
            names = [spec["columns"][i] for i in keep]
            stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table),
                sql.SQL(", ").join(map(sql.Identifier, names)),
                sql.SQL(", ").join(sql.Placeholder() * len(names)),
            )
            for row in spec["rows"]:
                values = [
                    Jsonb(row[i]) if isinstance(row[i], (dict, list)) else row[i] for i in keep
                ]
                cur.execute(stmt, values)
            inserted[table] = len(spec["rows"])
        conn.commit()
        out = {"dropped": dropped, "inserted": inserted}
    elif op == "enable":
        cur.execute(
            "UPDATE character SET chat_enabled = %s, call_enabled = %s WHERE id = %s",
            (bool(req["chat"]), bool(req["call"]), int(req["id"])),
        )
        if cur.rowcount != 1:
            raise SystemExit("켤 캐릭터 행이 없다")
        conn.commit()
        out = {"updated": 1}
    else:
        raise SystemExit(f"모르는 작업: {op}")
sys.stdout.write(json.dumps(out, ensure_ascii=False))
"""

#: chat-svc 가상환경에서 돈다. 작업 디렉터리는 chat-svc 저장소다.
#: 환경변수 RQC_CONTENT_DATABASE_URL(+ RQC_ENV 등 대상 설정).
CHAT_DB_SCRIPT = r"""
import json, os, sys
from pathlib import Path
import sqlalchemy as sa
from relationship_quest_chat.adapters.storage.postgres.content_schema import content_release_head
from relationship_quest_chat.adapters.storage.postgres.engine import build_postgres_engine
from relationship_quest_chat.config import RuntimeSettings
from relationship_quest_chat.content_cli.publish import publish, verify
from relationship_quest_chat.domain.content.aggregates import GenerationModelConfigSelection

req = json.loads(sys.stdin.read())
settings = RuntimeSettings.from_env(dict(os.environ))
settings.validate_job("content")
engine = build_postgres_engine(settings, role="content")
policy = GenerationModelConfigSelection.application_policy()
try:
    with engine.connect() as conn:
        rows = conn.execute(sa.text("SELECT version_num FROM alembic_version"))
        heads = sorted(r[0] for r in rows)
        head = conn.execute(
            sa.select(content_release_head.c.release_id).where(
                content_release_head.c.singleton == 1
            )
        ).scalar_one_or_none()
    out = {"heads": heads, "releaseHead": None if head is None else str(head)}
    if req["op"] == "inspect":
        findings = verify(data_dir=Path(req["dataDir"]), engine=engine, model_configs=policy)
        out["drift"] = [
            {"aggregate": f.aggregate, "owner": f.owner, "reason": f.reason} for f in findings
        ]
    elif req["op"] == "publish":
        if out["releaseHead"] != req["expectedHead"]:
            raise SystemExit("chat-svc 발행본이 점검 뒤에 바뀌었다")
        report = publish(
            data_dir=Path(req["dataDir"]),
            engine=engine,
            expected_release_id=req["expectedHead"],
            model_configs=policy,
        )
        out["report"] = {
            "releaseId": report.release_id,
            "releaseCreated": report.release_created,
            "versionsCreated": report.versions_created,
            "characters": report.characters,
            "chapters": report.chapters,
        }
        findings = verify(data_dir=Path(req["dataDir"]), engine=engine, model_configs=policy)
        out["driftAfter"] = len(findings)
    else:
        raise SystemExit("모르는 작업")
finally:
    engine.dispose()
sys.stdout.write(json.dumps(out, ensure_ascii=False))
"""

__all__ = ["API_DB_SCRIPT", "CHAT_DB_SCRIPT"]
