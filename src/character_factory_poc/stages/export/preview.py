"""테스터 전용 미리보기 발행 — 공장 캐릭터를 실제 앱의 테스터에게만 보이게 올린다.

순서가 안전장치다(사용자 2026-11-12, 실서비스 = 개발 서버).

1. 읽기 점검: 대상 api-svc·chat-svc 스키마, 같은 캐릭터 유무, chat-svc 발행본이 저장소
   data/와 똑같은지(다르면 새 발행이 다른 캐릭터를 되돌리므로 멈춘다), 테스터 명단.
2. 대상 DB 시퀀스에서 id를 예약한다. 고정 200만 번대 id는 로컬 시연 DB 전용이다.
3. 그 id를 content.segments에 preview로 먼저 넣고, 다시 읽어 확인한 뒤 서버 설정 캐시
   (30초)보다 오래 기다린다. 그 전에는 캐릭터 행이 없다.
4. 사진·영상을 api-svc 키 규칙(public/protected·무작위 폴더)으로 올린다.
5. api-svc 행을 한 트랜잭션으로 넣는다. 대화·통화는 꺼진 채다.
6. chat-svc에 저장소 data/ + 우리 조각을, 점검한 발행본 위에서만(expected head) 발행한다.
7. 대화·통화를 켜고, 로그인하지 않은 요청의 목록·검색에 없는지 확인한다.

content.segments는 목록·탐색·검색·피드에서만 뺀다. id로 직접 부르는 상세·대화는 막지 않는다.
"""

from __future__ import annotations

import json
import mimetypes
import os
import shutil
import subprocess
import tempfile
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.export.doki_app import api_svc, chat_svc
from character_factory_poc.stages.export.doki_app.naming import character_uid, slug_for
from character_factory_poc.stages.export.preview_scripts import API_DB_SCRIPT, CHAT_DB_SCRIPT
from character_factory_poc.stages.export.verify import _overlay_tree
from character_factory_poc.stages.s11_release.package import (
    load_package,
    now_iso,
    verify_package_files,
)

SEGMENTS_KEY = "content.segments"
#: api-svc app_settings.CACHE_TTL_SECONDS(30) + 여유.
DEFAULT_WAIT_S = 35.0
_PUBLIC_KINDS = frozenset({"profile_photo"})
_SEGMENT_KEYS = frozenset(
    {"preview_member_ids", "new_member_ids", "new_member_since", "characters", "shorts"}
)


class PreviewError(FactoryError):
    """미리보기 발행을 멈춘다. 메시지는 사용자에게 그대로 보여도 되는 문장이다."""


# ------------------------------------------------------------------ 설정


@dataclass(frozen=True)
class PreviewSettings:
    target: str = "test"  # test | live
    api_svc_repo: Path = Path("~/projects/_wt/api-svc-live").expanduser()
    chat_svc_repo: Path = Path("~/projects/_wt/chat-svc-live").expanduser()
    api_base_url: str = ""  # 예: https://api.example.com (경로 /api/v1 앞)
    storage: str = "none"  # none | s3
    s3_bucket: str = ""
    aws_profile: str = ""
    wait_s: float = DEFAULT_WAIT_S
    allow_live: bool = False
    chat_env: dict[str, str] = field(default_factory=lambda: {"RQC_ENV": "local"})
    api_db_url_env: str = "CFP_PREVIEW_API_DB_URL"
    chat_db_url_env: str = "CFP_PREVIEW_CHAT_DB_URL"
    admin_token_env: str = "CFP_PREVIEW_ADMIN_TOKEN"
    live_confirm_env: str = "CFP_PREVIEW_LIVE_CONFIRM"

    def secret(self, name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise PreviewError(f"발행 설정이 비었어요: 환경변수 {name}")
        return value

    def require_ready(self) -> None:
        if self.target not in {"test", "live"}:
            raise PreviewError("발행 대상(target)은 test 또는 live여야 해요")
        if not self.api_base_url.strip():
            raise PreviewError("발행 설정이 비었어요: [publish.preview] api_base_url")
        for env in (self.api_db_url_env, self.chat_db_url_env, self.admin_token_env):
            self.secret(env)
        if self.target == "live":
            if not self.allow_live:
                raise PreviewError("실서비스 발행이 꺼져 있어요([publish.preview] allow_live)")
            if os.environ.get(self.live_confirm_env, "").strip() != "1":
                raise PreviewError(
                    f"실서비스 발행 확인값이 없어요(환경변수 {self.live_confirm_env}=1)"
                )
            if self.storage != "s3" or not self.s3_bucket:
                raise PreviewError(
                    "실서비스 발행에는 사진·영상 업로드(storage=s3, s3_bucket)가 필요해요"
                )
            if self.wait_s < DEFAULT_WAIT_S:
                raise PreviewError(f"실서비스 대기 시간은 {DEFAULT_WAIT_S:.0f}초 이상이어야 해요")


def load_preview_settings(ctx: Context) -> PreviewSettings:
    data: dict = {}
    source = ctx.config.source_path
    if source is not None and Path(source).is_file():
        data = tomllib.loads(Path(source).read_text(encoding="utf-8"))
    raw = (data.get("publish") or {}).get("preview") or {}
    base = PreviewSettings()

    def path(key: str, default: Path) -> Path:
        value = raw.get(key)
        return Path(value).expanduser() if isinstance(value, str) and value.strip() else default

    chat_env = raw.get("chat_env")
    return PreviewSettings(
        target=str(raw.get("target", base.target)),
        api_svc_repo=path("api_svc_repo", base.api_svc_repo),
        chat_svc_repo=path("chat_svc_repo", base.chat_svc_repo),
        api_base_url=str(raw.get("api_base_url", "")).rstrip("/"),
        storage=str(raw.get("storage", base.storage)),
        s3_bucket=str(raw.get("s3_bucket", "")),
        aws_profile=str(raw.get("aws_profile", "")),
        wait_s=float(raw.get("wait_seconds", base.wait_s)),
        allow_live=bool(raw.get("allow_live", False)),
        chat_env={str(k): str(v) for k, v in chat_env.items()}
        if isinstance(chat_env, dict)
        else base.chat_env,
    )


# ------------------------------------------------------------------ 바깥과 닿는 곳


def _venv_python(repo: Path) -> list[str]:
    venv = repo / ".venv" / "bin" / "python"
    return [str(venv)] if venv.is_file() else ["uv", "run", "python"]


def _run_script(argv: list[str], script: str, payload: dict, *, cwd: Path, env: dict) -> dict:
    merged = dict(os.environ)
    merged.update(env)
    done = subprocess.run(
        [*argv, "-c", script],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=merged,
        timeout=900,
        check=False,
    )
    if done.returncode != 0:
        lines = (done.stderr or done.stdout).strip().splitlines()
        detail = " / ".join(line.strip() for line in lines[-3:] if line.strip())[:400]
        raise PreviewError(detail or "DB 작업이 이유 없이 실패했어요")
    return json.loads(done.stdout or "{}")


@dataclass
class Ports:
    """발행이 바깥과 닿는 모든 곳. 시험은 가짜로 바꿔 순서를 확인한다."""

    api_db: Callable[[dict], dict]
    chat_db: Callable[[dict], dict]
    http: Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]
    upload: Callable[[Path, str], None]
    sleep: Callable[[float], None] = time.sleep


def _http(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            raw = res.read()
            return res.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PreviewError(
            f"api-svc에 닿지 못했어요: {exc.reason if hasattr(exc, 'reason') else exc}"
        ) from exc


def default_ports(settings: PreviewSettings) -> Ports:
    api_env = {"CFP_PG_DSN": settings.secret(settings.api_db_url_env)}
    chat_env = dict(settings.chat_env)
    chat_env["RQC_CONTENT_DATABASE_URL"] = settings.secret(settings.chat_db_url_env)
    if chat_env.get("RQC_ENV") == "local":
        chat_env.setdefault("RQC_DATABASE_URL", chat_env["RQC_CONTENT_DATABASE_URL"])

    def api_db(payload: dict) -> dict:
        return _run_script(
            _venv_python(settings.api_svc_repo),
            API_DB_SCRIPT,
            payload,
            cwd=settings.api_svc_repo,
            env=api_env,
        )

    def chat_db(payload: dict) -> dict:
        return _run_script(
            _venv_python(settings.chat_svc_repo),
            CHAT_DB_SCRIPT,
            payload,
            cwd=settings.chat_svc_repo,
            env=chat_env,
        )

    def upload(path: Path, key: str) -> None:
        if settings.storage == "none":
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        argv = [
            "aws",
            "s3",
            "cp",
            str(path),
            f"s3://{settings.s3_bucket}/{key}",
            "--content-type",
            content_type,
            "--only-show-errors",
        ]
        if settings.aws_profile:
            argv += ["--profile", settings.aws_profile]
        done = subprocess.run(argv, capture_output=True, text=True, timeout=600, check=False)
        if done.returncode != 0:
            raise PreviewError(f"사진·영상 업로드 실패: {(done.stderr or '').strip()[-300:]}")

    return Ports(api_db=api_db, chat_db=chat_db, http=_http, upload=upload)


# ------------------------------------------------------------------ 계획(순수 함수)


def merge_segments(raw: str | None, character_id: int) -> tuple[str, dict]:
    """기존 값을 지키고 캐릭터 하나만 preview로 더한다. 테스터가 없으면 멈춘다."""
    value = json.loads(raw) if raw and raw.strip() else {}
    if not isinstance(value, dict):
        raise PreviewError("content.segments 값이 JSON 객체가 아니에요")
    unknown = set(value) - _SEGMENT_KEYS
    if unknown:
        raise PreviewError(f"content.segments에 모르는 키가 있어요: {', '.join(sorted(unknown))}")
    testers = value.get("preview_member_ids") or []
    if not testers:
        raise PreviewError(
            "테스터 명단(content.segments의 preview_member_ids)이 비어 있어요. "
            "테스터 회원 id를 먼저 넣어 주세요"
        )
    characters = dict(value.get("characters") or {})
    current = characters.get(str(character_id))
    if current not in (None, "preview"):
        raise PreviewError(f"캐릭터 {character_id}가 이미 {current}로 지정돼 있어요")
    characters[str(character_id)] = "preview"
    value["characters"] = characters
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")), value


class _Recorder:
    """빌드가 쓰는 (표, 순번)을 모은다. 예약 수를 정하는 데만 쓴다."""

    def __init__(self) -> None:
        self.used: dict[str, set[int]] = {}
        self._table_no: dict[str, int] = {}

    def __call__(self, table: str, offset: int = 0) -> int:
        # 같은 (표, 순번)에는 늘 같은 값을 준다. 빌드가 id끼리 비교하는 곳이 있다.
        self.used.setdefault(table, set()).add(offset)
        number = self._table_no.setdefault(table, len(self._table_no) + 1)
        return 1_000_000_000 + number * 10_000 + offset


def _allocator(reserved: dict[str, list[int]], used: dict[str, set[int]]):
    mapping = {
        table: dict(zip(sorted(offsets), reserved[table], strict=True))
        for table, offsets in used.items()
    }

    def row_id(table: str, offset: int = 0) -> int:
        try:
            return mapping[table][offset]
        except KeyError as exc:
            raise PreviewError(f"예약하지 않은 id를 썼어요: {table}[{offset}]") from exc

    return row_id


def _canonical_keys(
    bundle: dict, character_id: int, files: dict[str, Path]
) -> list[tuple[Path, str]]:
    """file_store 키를 api-svc 규칙(ADR-0032)으로 바꾸고 (파일, 키) 목록을 돌려준다."""
    tables = bundle["tables"]
    usage: dict[int, str] = {}
    cm = tables.get("character_media")
    if cm:
        mi, ui = cm["columns"].index("media_id"), cm["columns"].index("usage_type")
        for row in cm["rows"]:
            usage.setdefault(row[mi], row[ui])
    fs = tables.get("file_store")
    if not fs:
        return []
    cols = fs["columns"]
    mi, ki = cols.index("media_id"), cols.index("key")
    si = cols.index("source_ref") if "source_ref" in cols else None
    uploads: list[tuple[Path, str]] = []
    for row in fs["rows"]:
        local = files.get(row[ki])
        if local is None or not local.is_file():
            raise PreviewError(f"올릴 파일을 찾지 못했어요: {row[ki]}")
        access = "public" if usage.get(row[mi]) in _PUBLIC_KINDS else "protected"
        ext = local.suffix.lstrip(".").lower() or "bin"
        key = f"api-svc/{access}/characters/{character_id}/{uuid.uuid4().hex}/original.{ext}"
        row[ki] = key
        if si is not None:
            row[si] = key
        uploads.append((local, key))
    return uploads


# ------------------------------------------------------------------ 결과


@dataclass
class PreviewStep:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class PreviewResult:
    characterId: str
    target: str
    status: str = "FAILED"  # PUBLISHED | FAILED
    apiCharacterId: int | None = None
    characterUid: str = ""
    name: str = ""
    visibleTo: str = "preview"
    steps: list[PreviewStep] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stoppedSafely: bool = True
    startedAt: str = ""
    finishedAt: str = ""

    def step(self, name: str, detail: str = "") -> None:
        self.steps.append(PreviewStep(name, True, detail[:600]))

    @property
    def failure(self) -> str:
        bad = [s for s in self.steps if not s.ok]
        return f"{bad[-1].name}: {bad[-1].detail}" if bad else ""


# ------------------------------------------------------------------ 본체


def publish_preview(
    ctx: Context,
    cid: str,
    *,
    settings: PreviewSettings | None = None,
    ports: Ports | None = None,
) -> PreviewResult:
    """G9 승인 패키지를 테스터 전용으로 발행한다. 실패해도 결과 파일을 남긴다."""
    settings = settings or load_preview_settings(ctx)
    result = PreviewResult(characterId=cid, target=settings.target, startedAt=now_iso())
    current = "준비"
    try:
        settings.require_ready()
        ports = ports or default_ports(settings)
        if ctx.state(cid).gate("G9").status != "APPROVED":
            raise PreviewError("패키지 승인(G9) 뒤에만 발행해요")
        package, package_dir = load_package(ctx, cid)
        problems = verify_package_files(package, package_dir)
        if problems:
            raise PreviewError("패키지 파일이 맞지 않아요: " + "; ".join(problems[:3]))
        if package.twin and package.twin.servingRoute:
            raise PreviewError(
                "전용 대화 모델을 쓰는 캐릭터예요. "
                "실서비스 chat-svc에는 캐릭터별 모델 경로가 없어요"
            )
        result.name = package.profile.name
        uid, handle = str(character_uid(cid)), slug_for(cid)
        result.characterUid = uid
        result.step("준비", f"{package.packageRev} · {package.profile.name}")

        current = "api-svc 점검"
        recorder = _Recorder()
        api_svc.build_seed(
            package, package_dir, exported_at=now_iso(), alembic_revision="", row_id=recorder
        )
        tables = sorted(recorder.used)
        api = ports.api_db({"op": "inspect", "tables": tables, "uid": uid, "handle": handle})
        if api.get("existing") is not None:
            raise PreviewError(f"이미 발행된 캐릭터예요(api-svc id {api['existing']})")
        missing = [t for t in tables if not api["sequences"].get(t)]
        if missing:
            raise PreviewError("id 시퀀스가 없는 표가 있어요: " + ", ".join(missing))
        result.step(current, "스키마 " + ",".join(api["heads"]))

        current = "chat-svc 점검"
        repo_data = settings.chat_svc_repo / "data"
        chat = ports.chat_db({"op": "inspect", "dataDir": str(repo_data)})
        if chat.get("drift"):
            sample = ", ".join(f"{d['owner']}({d['reason']})" for d in chat["drift"][:4])
            raise PreviewError(
                "실서비스 chat-svc 발행본이 저장소 data/와 달라요. 지금 발행하면 다른 캐릭터 "
                f"콘텐츠가 되돌아가요: {sample}"
            )
        expected_head = chat["releaseHead"]
        result.step(current, f"스키마 {','.join(chat['heads'])} · 발행본 {expected_head} · 차이 0")

        current = "테스터 명단"
        admin = settings.api_base_url + "/api/v1/admin/content/config"
        token = {"X-Admin-Token": settings.secret(settings.admin_token_env)}
        status, rows = ports.http("GET", admin, token, None)
        if status != 200 or not isinstance(rows, list):
            raise PreviewError(f"관리자 설정을 읽지 못했어요(HTTP {status})")
        before = next((r.get("value") for r in rows if r.get("key") == SEGMENTS_KEY), None)
        merge_segments(before, 1)  # 테스터 명단·형식을 예약 전에 확인한다
        result.step(
            current, f"테스터 {len(json.loads(before or '{}').get('preview_member_ids') or [])}명"
        )

        current = "id 예약"
        reserved = ports.api_db(
            {"op": "reserve", "counts": {t: len(o) for t, o in recorder.used.items()}}
        )["ids"]
        row_id = _allocator(reserved, recorder.used)
        seed = api_svc.build_seed(
            package,
            package_dir,
            exported_at=now_iso(),
            alembic_revision=",".join(api["heads"]),
            row_id=row_id,
        )
        bundle = seed.bundle
        character_id = row_id("character", 0)
        result.apiCharacterId = character_id
        ch = bundle["tables"]["character"]
        for col, value in (("chat_enabled", False), ("call_enabled", False), ("is_active", True)):
            ch["rows"][0][ch["columns"].index(col)] = value
        dropped = sorted(
            f"{t}.{c}"
            for t, spec in bundle["tables"].items()
            for c in spec["columns"]
            if c not in set(api["columns"].get(t) or [])
        )
        if dropped:
            result.warnings.append("실서비스 스키마에 없어 빼는 칸: " + ", ".join(dropped))
        problems = api_svc.validate_seed_bundle(bundle)
        tree = chat_svc.build_tree(package, package_dir)
        problems += chat_svc.validate_content_tree(tree.files)
        if problems:
            raise PreviewError("변환 결과 검사 실패: " + "; ".join(problems[:3]))
        uploads = _canonical_keys(bundle, character_id, seed.files)
        result.step(current, f"캐릭터 id {character_id} · 표 {len(reserved)}개")

        current = "사진·영상 업로드"
        for local, key in uploads:
            ports.upload(local, key)
        result.step(
            current,
            f"{len(uploads)}개"
            + (" (업로드 생략: 시험 대상)" if settings.storage == "none" else ""),
        )

        current = "테스터 전용 지정"
        status, rows = ports.http("GET", admin, token, None)
        latest = next((r.get("value") for r in (rows or []) if r.get("key") == SEGMENTS_KEY), None)
        merged, _ = merge_segments(latest, character_id)
        body = json.dumps({"value": merged}, ensure_ascii=False).encode()
        status, _ = ports.http(
            "PUT", f"{admin}/{SEGMENTS_KEY}", {**token, "Content-Type": "application/json"}, body
        )
        if status != 200:
            raise PreviewError(f"테스터 전용 지정을 저장하지 못했어요(HTTP {status})")
        status, rows = ports.http("GET", admin, token, None)
        saved = next((r.get("value") for r in (rows or []) if r.get("key") == SEGMENTS_KEY), "{}")
        if (json.loads(saved or "{}").get("characters") or {}).get(str(character_id)) != "preview":
            raise PreviewError("저장한 테스터 전용 지정을 다시 읽지 못했어요")
        ports.sleep(settings.wait_s)
        result.step(current, f"preview 확인 · {settings.wait_s:.0f}초 대기")

        current = "api-svc 등록"
        result.stoppedSafely = True
        inserted = ports.api_db(
            {
                "op": "insert",
                "uid": uid,
                "handle": handle,
                "order": bundle["table_order"],
                "tables": bundle["tables"],
            }
        )
        result.step(current, ", ".join(f"{t} {n}" for t, n in inserted["inserted"].items()))

        current = "chat-svc 발행"
        work = Path(tempfile.mkdtemp(prefix="cfp-preview-"))
        try:
            fragment = work / "fragment"
            chat_svc.write_tree(fragment, tree)
            note = _overlay_tree(repo_data, fragment, work / "data")
            published = ports.chat_db(
                {"op": "publish", "dataDir": str(work / "data"), "expectedHead": expected_head}
            )
        finally:
            shutil.rmtree(work, ignore_errors=True)
        if published.get("driftAfter"):
            raise PreviewError("발행 뒤 chat-svc 대조에서 차이가 남았어요")
        report = published["report"]
        result.step(
            current, f"{note} · 발행본 {report['releaseId']} · 캐릭터 {report['characters']}명"
        )

        current = "대화 켜기"
        call = any(v.kind == "ACTION" for v in package.videos)
        ports.api_db({"op": "enable", "id": character_id, "chat": True, "call": call})
        result.step(current, "대화 켬" + (" · 통화 켬" if call else ""))

        current = "노출 확인"
        result.step(current, _check_hidden(ports, settings.api_base_url, character_id, result.name))
        result.status = "PUBLISHED"
    except (PreviewError, FactoryError, KeyError, ValueError, OSError) as exc:
        result.steps.append(PreviewStep(current, False, str(exc)[:600]))
    finally:
        result.finishedAt = now_iso()
        _write_result(ctx, cid, result)
    return result


def _check_hidden(ports: Ports, base: str, character_id: int, name: str) -> str:
    """로그인하지 않은 요청(웹·안드로이드·iOS)의 목록·검색에 이 캐릭터가 없어야 한다."""
    checked = 0
    for platform in ("web", "android", "ios"):
        headers = {"X-Client-Platform": platform}
        for path in (
            "/api/v1/characters?sort=new&limit=50",
            "/api/v1/characters/search?" + urllib.parse.urlencode({"q": name, "limit": 50}),
        ):
            status, payload = ports.http("GET", base + path, headers, None)
            if status != 200 or not isinstance(payload, dict):
                raise PreviewError(
                    f"공개 목록을 읽지 못했어요({platform} {path.split('?')[0]}: HTTP {status})"
                )
            ids = {item.get("id") for item in payload.get("characters") or []}
            if character_id in ids:
                raise PreviewError(f"일반 사용자 목록에 보여요({platform} {path.split('?')[0]})")
            checked += 1
    return f"로그인 없는 목록·검색 {checked}곳에서 안 보임"


def _write_result(ctx: Context, cid: str, result: PreviewResult) -> Path:
    root = ctx.character_dir(cid) / "px-preview"
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = root / f"{stamp}-{result.target}.json"
    path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


__all__ = [
    "Ports",
    "PreviewError",
    "PreviewResult",
    "PreviewSettings",
    "default_ports",
    "load_preview_settings",
    "merge_segments",
    "publish_preview",
]
