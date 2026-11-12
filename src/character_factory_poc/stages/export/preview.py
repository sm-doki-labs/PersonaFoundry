"""테스터 전용 미리보기 발행 — 공장 캐릭터를 dev 앱의 테스터에게만 보이게 한 번에 올린다.

dev VPC 안의 넣기 서비스(backoffice factory-import, api-svc/docs/factory-import.md)를 부른다. 공장은 형식을
만들고, 쓰기·되돌리기는 넣기 서비스가 한다. 사람 승인 단계는 없다(사용자 2026-11-13).

1. 상태(GET /state): 같은 캐릭터 유무, 표·id 시퀀스, 테스터 명단, chat 발행본, voice-svc 도달.
2. id 예약(POST /reservations) → api-svc 시드 묶음(doki_app.api_svc)을 그 번호로 만든다.
3. chat 콘텐츠: dev 배포 판 chat-svc 체크아웃의 data/ 위에 우리 조각을 얹어 그 저장소 컴파일러로
   컴파일하고 이 캐릭터의 버전·소속만 뽑는다(preview_scripts).
4. 사진·영상: 업로드 주소(POST /uploads)를 받아 바로 PUT 한다. 키(api-svc ADR-0032)는 넣기 서비스가 정한다.
5. 넣기(POST /characters): 프로필·단계·미디어·통화 클립(api) + 페르소나·챕터(chat) + 음성을 한 번에.
   음성은 패키지의 Fish Audio 음성 ID(D-0205)면 새 Voice 로 발행, 없으면 twin.voiceId·default_voice_id 의
   voice-svc UUID 를 잇는다. 넣기 서비스가 preview 지정 → 행 → chat 발행본 → 대화·통화 켜기 순으로 올리고
   중간에 실패하면 되돌린다.

지우기는 remove_preview(DELETE /characters/{id}).
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
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.export.doki_app import api_svc, chat_svc
from character_factory_poc.stages.export.doki_app.naming import character_uid, slug_for
from character_factory_poc.stages.export.preview_scripts import CHAT_COMPILE_SCRIPT
from character_factory_poc.stages.export.verify import _overlay_tree
from character_factory_poc.stages.s11_release.package import (
    load_package,
    now_iso,
    verify_package_files,
)

API = "/api/v1/factory-import"
DEFAULT_CHAT_REPO = Path("~/projects/_wt/chat-svc-live")
_VOICE_TABLES = ("character_voice", "character_voice_language")


class PreviewError(FactoryError):
    """미리보기 발행을 멈춘다. 메시지는 사용자에게 그대로 보여도 되는 문장이다."""


# ------------------------------------------------------------------ 설정


@dataclass(frozen=True)
class PreviewSettings:
    target: str = "dev"
    base_url: str = ""  # 예: https://factory-import.dev.dokilabs.com
    token_env: str = "FACTORY_IMPORT_TOKEN"
    # dev 에 배포된 판의 chat-svc 체크아웃(.venv 포함). 컴파일만 하고 DB 에는 붙지 않는다.
    chat_svc_repo: Path = DEFAULT_CHAT_REPO
    expires_minutes: int = 60
    # 패키지에 Fish 음성 ID 가 없을 때 이을 voice-svc Voice UUID(twin.voiceId 가 먼저다).
    default_voice_id: str | None = None
    timeout_s: float = 240.0

    def token(self) -> str:
        value = os.environ.get(self.token_env, "").strip()
        if not value:
            raise PreviewError(f"발행 설정이 비었어요: 환경변수 {self.token_env}")
        return value

    def require_ready(self) -> None:
        if not self.base_url.startswith(("https://", "http://")):
            raise PreviewError(
                "발행 설정이 비었어요: [publish.preview] base_url(또는 FACTORY_IMPORT_BASE_URL)"
            )
        self.token()
        repo = self.chat_svc_repo.expanduser()
        if not (repo / "data").is_dir():
            raise PreviewError(
                f"chat-svc 체크아웃이 없어요: {repo} (dev 배포 판, [publish.preview] chat_svc_repo)"
            )


def load_preview_settings(ctx: Context) -> PreviewSettings:
    data: dict = {}
    source = ctx.config.source_path
    if source is not None and Path(source).is_file():
        data = tomllib.loads(Path(source).read_text(encoding="utf-8"))
    raw = (data.get("publish") or {}).get("preview") or {}
    doki = ((data.get("export") or {}).get("doki_app")) or {}
    base = PreviewSettings()
    repo = raw.get("chat_svc_repo")
    return PreviewSettings(
        target=str(raw.get("target", base.target)),
        base_url=str(raw.get("base_url") or os.environ.get("FACTORY_IMPORT_BASE_URL", "")).rstrip(
            "/"
        ),
        token_env=str(raw.get("token_env", base.token_env)),
        chat_svc_repo=Path(repo).expanduser()
        if isinstance(repo, str) and repo.strip()
        else base.chat_svc_repo,
        expires_minutes=int(raw.get("expires_minutes", base.expires_minutes)),
        default_voice_id=raw.get("default_voice_id")
        or doki.get("default_voice_id")
        or os.environ.get("CFP_DEFAULT_VOICE_ID")
        or None,
        timeout_s=float(raw.get("timeout_seconds", base.timeout_s)),
    )


# ------------------------------------------------------------------ 바깥과 닿는 곳


@dataclass
class Ports:
    """발행이 바깥과 닿는 모든 곳. 시험은 가짜로 바꿔 순서와 몸통을 확인한다."""

    api: Callable[[str, str, dict | None], tuple[int, Any]]  # (method, path, json) → (status, json)
    put_file: Callable[[str, dict[str, str], Path], int]
    compile_chat: Callable[[Path, str], dict]  # (data_dir, characterUid) → {content, problems}


def _venv_python(repo: Path) -> list[str]:
    venv = repo / ".venv" / "bin" / "python"
    return [str(venv)] if venv.is_file() else ["uv", "run", "python"]


def default_ports(settings: PreviewSettings) -> Ports:
    base = settings.base_url.rstrip("/")
    token = settings.token()

    def api(method: str, path: str, body: dict | None) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        headers = {"X-Factory-Import-Token": token, "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=settings.timeout_s) as res:
                raw = res.read()
                return res.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                return exc.code, json.loads(raw) if raw else None
            except ValueError:
                return exc.code, None
        except (urllib.error.URLError, TimeoutError) as exc:
            reason = getattr(exc, "reason", exc)
            raise PreviewError(f"넣기 서비스에 닿지 못했어요: {reason}") from exc

    def put_file(url: str, headers: dict[str, str], path: Path) -> int:
        size = path.stat().st_size
        with path.open("rb") as handle:
            req = urllib.request.Request(
                url, data=handle, method="PUT", headers={**headers, "Content-Length": str(size)}
            )
            try:
                with urllib.request.urlopen(req, timeout=600) as res:
                    return res.status
            except urllib.error.HTTPError as exc:
                return exc.code
            except (urllib.error.URLError, TimeoutError) as exc:
                raise PreviewError(
                    f"파일을 올리지 못했어요({path.name}): {getattr(exc, 'reason', exc)}"
                ) from exc

    def compile_chat(data_dir: Path, uid: str) -> dict:
        repo = settings.chat_svc_repo.expanduser()
        done = subprocess.run(
            [*_venv_python(repo), "-c", CHAT_COMPILE_SCRIPT],
            input=json.dumps({"dataDir": str(data_dir), "characterUid": uid}),
            capture_output=True,
            text=True,
            cwd=str(repo),
            env={**os.environ, "RQC_ENV": "local"},
            timeout=900,
            check=False,
        )
        if done.returncode != 0:
            lines = (done.stderr or done.stdout).strip().splitlines()
            detail = " / ".join(line.strip() for line in lines[-3:] if line.strip())[:400]
            raise PreviewError(f"chat-svc 컴파일 실패: {detail or '이유 없음'}")
        return json.loads(done.stdout or "{}")

    return Ports(api=api, put_file=put_file, compile_chat=compile_chat)


def _call(ports: Ports, method: str, path: str, body: dict | None, what: str) -> Any:
    status, payload = ports.api(method, API + path, body)
    if 200 <= status < 300:
        return payload or {}
    detail = (payload or {}).get("detail") if isinstance(payload, dict) else None
    message = detail.get("message") if isinstance(detail, dict) else detail
    raise PreviewError(f"{what} 실패(HTTP {status}){': ' + str(message) if message else ''}")


# ------------------------------------------------------------------ 계획(순수 함수)


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


def split_voice(package, bundle: dict) -> tuple[dict | None, str]:
    """음성 묶음 행을 빼고 넣기 API 의 voice 칸으로 바꾼다. 묶음은 넣기 서비스가 만든다."""
    tables = bundle["tables"]
    language_rows = tables.pop("character_voice_language", None)
    tables.pop("character_voice", None)
    bundle["table_order"] = [t for t in bundle["table_order"] if t not in _VOICE_TABLES]
    character = tables["character"]
    if "voice_id" in character["columns"]:
        character["rows"][0][character["columns"].index("voice_id")] = None
    if package.voice is not None:
        voice = {
            "fishReferenceId": package.voice.referenceId,
            "displayName": package.profile.name[:64],
            "language": package.locale,
        }
        return voice, f"Fish {package.voice.referenceId} → 새 Voice 발행"
    if language_rows and language_rows["rows"]:
        row = dict(zip(language_rows["columns"], language_rows["rows"][0], strict=True))
        return {
            "voiceId": str(row["voice_id"]),
            "language": str(row["language"]),
        }, f"voice-svc {row['voice_id']}"
    return None, "없음"


def upload_plan(bundle: dict, files: dict[str, Path]) -> list[tuple[str, Path, dict]]:
    """file_store 행마다 (지금 키, 파일, 업로드 요청 한 줄). 같은 media 는 같은 자산 폴더다."""
    tables = bundle["tables"]
    kind: dict[int, str] = {}
    for table, column, label in (
        ("character_media", "usage_type", None),
        ("character_clip", None, "call_clip"),
        ("character_video", None, "call_video"),
    ):
        spec = tables.get(table)
        if not spec:
            continue
        mi = spec["columns"].index("media_id")
        ui = spec["columns"].index(column) if column else None
        for row in spec["rows"]:
            kind.setdefault(row[mi], row[ui] if ui is not None else label)
    fs = tables.get("file_store")
    if not fs:
        return []
    cols = fs["columns"]
    mi, ki, vi = cols.index("media_id"), cols.index("key"), cols.index("variant_type")
    plan = []
    for row in fs["rows"]:
        local = files.get(row[ki])
        if local is None or not local.is_file():
            raise PreviewError(f"올릴 파일을 찾지 못했어요: {row[ki]}")
        plan.append(
            (
                row[ki],
                local,
                {
                    "ref": row[ki],
                    "asset": f"media-{row[mi]}",
                    "kind": kind.get(row[mi], "media"),
                    "variant": row[vi] or "original",
                    "ext": local.suffix.lstrip(".").lower() or "bin",
                    "contentType": mimetypes.guess_type(local.name)[0]
                    or "application/octet-stream",
                },
            )
        )
    return plan


def _rekey(bundle: dict, keys: dict[str, str]) -> None:
    fs = bundle["tables"]["file_store"]
    ki = fs["columns"].index("key")
    si = fs["columns"].index("source_ref") if "source_ref" in fs["columns"] else None
    for row in fs["rows"]:
        row[ki] = keys[row[ki]]
        if si is not None:
            row[si] = row[ki]


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
    status: str = "FAILED"  # PUBLISHED | FAILED | REMOVED
    apiCharacterId: int | None = None
    characterUid: str = ""
    name: str = ""
    visibleTo: str = "preview"
    voice: dict | None = None
    chatReleaseId: str | None = None
    expiresAt: str | None = None
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


#: chat-svc 활성 퀘스트는 관문 있는 메인 챕터가 정확히 3개다(content_cli/loader.py). 슬롯별 진입 단계.
_SPREAD_STAGES = {2: ("ACQUAINTANCE", "두 번째 통화"), 3: ("FLIRTING", "세 번째 통화")}


def spread_single_chapter(package):
    """챕터 1개짜리 모티브를 같은 장면으로 1~3단계에 펼친다(D-0210). 패키지 파일은 그대로다.

    2·3단계는 1단계와 같은 사실·프레임·통화 영상을 쓰고, 관계 진입 단계만 chat-svc 슬롯에 맞춘다.
    """
    if len(package.chapters) != 1:
        return package, ""
    first = package.chapters[0]
    if first.chapterNo != 1:
        return package, ""
    chapters = [first]
    for no, (stage, title) in _SPREAD_STAGES.items():
        chapters.append(
            first.model_copy(
                update={
                    "chapterNo": no,
                    "chapterId": f"ch{no}",
                    "relationshipStage": stage,
                    "title": title,
                }
            )
        )
    videos = list(package.videos)
    for video in package.videos:
        if video.kind == "ACTION" and (video.chapterNo or 1) == 1:
            for no in _SPREAD_STAGES:
                videos.append(
                    video.model_copy(update={"chapterNo": no, "videoId": f"{video.videoId}-ch{no}"})
                )
    note = "챕터가 1개라 같은 장면·통화 영상을 1~3단계에 펼쳤어요(chat-svc 는 관문 챕터 3개가 필요해요)"
    return package.model_copy(update={"chapters": chapters, "videos": videos}), note


def publish_preview(
    ctx: Context,
    cid: str,
    *,
    settings: PreviewSettings | None = None,
    ports: Ports | None = None,
) -> PreviewResult:
    """G9 승인 패키지를 테스터 전용으로 dev 에 올린다. 실패해도 결과 파일을 남긴다."""
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
                "전용 대화 모델을 쓰는 캐릭터예요. dev chat-svc 에는 캐릭터별 모델 경로가 없어요"
            )
        package, spread = spread_single_chapter(package)
        if spread:
            result.warnings.append(spread)
        result.name = package.profile.name
        uid, handle = str(character_uid(cid)), slug_for(cid)
        result.characterUid = uid
        result.step("준비", f"{package.packageRev} · {package.profile.name}")

        current = "넣기 서비스 점검"
        recorder = _Recorder()
        api_svc.build_seed(
            package,
            package_dir,
            exported_at=now_iso(),
            alembic_revision="",
            default_voice_id=settings.default_voice_id,
            row_id=recorder,
        )
        tables = sorted(recorder.used)
        query = urllib.parse.urlencode(
            {"characterUid": uid, "handle": handle, "tables": ",".join(tables)}
        )
        state = _call(ports, "GET", f"/state?{query}", None, "상태 조회")
        api, chat, voice_svc = (
            state.get("api") or {},
            state.get("chat") or {},
            state.get("voice") or {},
        )
        if api.get("existing") is not None:
            raise PreviewError(
                f"이미 발행된 캐릭터예요(앱 캐릭터 {api['existing']}). 먼저 지워 주세요"
            )
        missing = [t for t in tables if not (api.get("sequences") or {}).get(t)]
        if missing:
            raise PreviewError("id 시퀀스가 없는 표가 있어요: " + ", ".join(missing))
        if not api.get("testers"):
            raise PreviewError(
                "테스터 명단(content.segments 의 preview_member_ids)이 비어 있어요. 테스터 회원 id 를 먼저 넣어 주세요"
            )
        result.step(
            current,
            f"스키마 {','.join(api.get('heads') or [])} · 테스터 {api['testers']}명 · "
            f"chat 발행본 {chat.get('releaseHead')} · voice-svc {'닿음' if voice_svc.get('reachable') else '안 닿음'}",
        )

        current = "id 예약"
        counts = {t: len(o) for t, o in recorder.used.items()}
        reserved = _call(ports, "POST", "/reservations", {"counts": counts}, "id 예약")["ids"]
        row_id = _allocator(reserved, recorder.used)
        seed = api_svc.build_seed(
            package,
            package_dir,
            exported_at=now_iso(),
            alembic_revision=",".join(api.get("heads") or []),
            default_voice_id=settings.default_voice_id,
            row_id=row_id,
        )
        bundle = seed.bundle
        character_id = row_id("character", 0)
        result.apiCharacterId = character_id
        voice, voice_note = split_voice(package, bundle)
        if voice is None:
            result.warnings.append(
                "음성이 없어요 — 통화를 열면 409(VOICE_LANGUAGE_NOT_AVAILABLE). Fish 음성 ID 나 default_voice_id 를 주세요"
            )
        elif voice.get("fishReferenceId") and not voice_svc.get("reachable"):
            raise PreviewError("넣기 서비스가 voice-svc 에 닿지 못해 Fish 음성을 발행할 수 없어요")
        # dev 스키마에 없는 칸은 넣기 서비스가 빼고 warnings 로 돌려준다.
        problems = api_svc.validate_seed_bundle(bundle)
        tree = chat_svc.build_tree(package, package_dir)
        problems += chat_svc.validate_content_tree(tree.files)
        if problems:
            raise PreviewError("변환 결과 검사 실패: " + "; ".join(problems[:3]))
        result.step(current, f"앱 캐릭터 {character_id} · 표 {len(reserved)}개 · 음성 {voice_note}")

        current = "chat 콘텐츠 컴파일"
        repo_data = settings.chat_svc_repo.expanduser() / "data"
        work = Path(tempfile.mkdtemp(prefix="cfp-preview-"))
        try:
            fragment = work / "fragment"
            chat_svc.write_tree(fragment, tree)
            note = _overlay_tree(repo_data, fragment, work / "data")
            compiled = ports.compile_chat(work / "data", uid)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        content = compiled.get("content") or {}
        if not content.get("releaseCharacters") or not content.get("releaseChapters"):
            raise PreviewError("chat-svc 컴파일 결과에 이 캐릭터가 없어요")
        for problem in compiled.get("problems") or []:
            result.warnings.append(f"chat-svc 전체 트리 검사: {problem}")
        result.step(
            current,
            f"{note} · 캐릭터 버전 {len(content['characterVersions'])} · "
            f"챕터 {len(content['releaseChapters'])} · 생성 프로필 {len(content.get('generationProfiles') or [])}",
        )

        current = "사진·영상 업로드"
        plan = upload_plan(bundle, seed.files)
        if plan:
            answer = _call(
                ports,
                "POST",
                "/uploads",
                {"characterId": character_id, "files": [spec for _, _, spec in plan]},
                "업로드 주소 받기",
            )
            by_ref = {item["ref"]: item for item in answer.get("files") or []}
            keys: dict[str, str] = {}
            for ref, local, _spec in plan:
                target = by_ref.get(ref)
                if target is None:
                    raise PreviewError(f"업로드 주소를 받지 못했어요: {local.name}")
                status = ports.put_file(target["url"], target.get("headers") or {}, local)
                if not 200 <= status < 300:
                    raise PreviewError(f"파일을 올리지 못했어요({local.name}: HTTP {status})")
                keys[ref] = target["key"]
            _rekey(bundle, keys)
        result.step(current, f"{len(plan)}개")

        current = "넣기"
        expires = datetime.now(UTC) + timedelta(minutes=settings.expires_minutes)
        result.expiresAt = expires.replace(microsecond=0).isoformat()
        call = any(v.kind == "ACTION" for v in package.videos)
        payload = {
            "characterUid": uid,
            "handle": handle,
            "api": {"tables": bundle["tables"]},
            "chat": content,
            "voice": voice,
            "enable": {"chat": True, "call": call},
            "expiresAt": result.expiresAt,
            "source": f"PersonaFoundry {cid} {package.packageRev}",
        }
        done = _call(ports, "POST", "/characters", payload, "넣기")
        result.voice = done.get("voice")
        result.chatReleaseId = done.get("releaseId")
        for item in done.get("steps") or []:
            result.step(f"넣기 · {item.get('name')}", str(item.get("detail") or ""))
            if str(item.get("detail") or "").startswith("경고"):
                result.warnings.insert(0, f"{item.get('name')}: {item.get('detail')}")
        result.warnings += list(done.get("warnings") or [])
        result.status = "PUBLISHED"
    except (PreviewError, FactoryError, KeyError, ValueError, OSError) as exc:
        result.steps.append(PreviewStep(current, False, str(exc)[:600]))
    finally:
        result.finishedAt = now_iso()
        _write_result(ctx, cid, result)
    return result


def latest_published(ctx: Context, cid: str) -> dict | None:
    root = Path(ctx.character_dir(cid)) / "px-preview"
    for path in sorted(root.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("status") in {"PUBLISHED", "REMOVED"}:
            return data if data["status"] == "PUBLISHED" else None
    return None


def remove_preview(
    ctx: Context,
    cid: str,
    *,
    settings: PreviewSettings | None = None,
    ports: Ports | None = None,
) -> PreviewResult:
    """마지막으로 발행한 테스터 전용 캐릭터를 dev 에서 지운다(넣기 서비스가 넣은 것만)."""
    settings = settings or load_preview_settings(ctx)
    result = PreviewResult(characterId=cid, target=settings.target, startedAt=now_iso())
    current = "지우기"
    try:
        settings.require_ready()
        ports = ports or default_ports(settings)
        published = latest_published(ctx, cid)
        if not published or not published.get("apiCharacterId"):
            raise PreviewError("지울 발행 기록이 없어요")
        result.apiCharacterId = int(published["apiCharacterId"])
        result.characterUid = published.get("characterUid") or ""
        result.name = published.get("name") or ""
        done = _call(ports, "DELETE", f"/characters/{result.apiCharacterId}", None, "지우기")
        deleted = done.get("deleted") or {}
        voice = done.get("voice") or {}
        result.voice = voice or None
        result.step(
            current,
            f"앱 캐릭터 {result.apiCharacterId} · 행 {sum(deleted.values())}개 · 파일 {done.get('filesDeleted', 0)}개"
            + (f" · 음성 {voice.get('removed')}" if voice else ""),
        )
        if isinstance(voice.get("removed"), str):
            result.warnings.append(voice["removed"])
        result.status = "REMOVED"
    except (PreviewError, FactoryError, KeyError, ValueError, OSError) as exc:
        result.steps.append(PreviewStep(current, False, str(exc)[:600]))
    finally:
        result.finishedAt = now_iso()
        _write_result(ctx, cid, result)
    return result


def _write_result(ctx: Context, cid: str, result: PreviewResult) -> Path:
    root = ctx.character_dir(cid) / "px-preview"
    root.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suffix = "removed" if result.status == "REMOVED" else result.target
    path = root / f"{stamp}-{suffix}.json"
    n = 1
    while path.exists():
        n += 1
        path = root / f"{stamp}-{n}-{suffix}.json"
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
    "latest_published",
    "load_preview_settings",
    "publish_preview",
    "remove_preview",
    "split_voice",
    "upload_plan",
]
