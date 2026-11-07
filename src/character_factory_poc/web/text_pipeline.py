"""텍스트 공정 연결 API (계획표 A).

현재 모델 덱 선택을 바꾸고, 실제 캐릭터의 단계·관문·최근 호출·알려진 텍스트 자료를 읽는다.
모델 호출은 하지 않는다. 인증 값·경로·원시 설정은 응답에 넣지 않는다.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Body, FastAPI, Request
from fastapi.responses import JSONResponse

from character_factory_poc.common import text_deck
from character_factory_poc.common.config import FactoryConfig, load_config
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.settings import WebSettings

PROFILE_LABELS = {
    "basic_test": "개발 확인",
    "demo": "시연",
    "pre_demo_completion_check": "시연 전 최종 점검",
}
ROUTES = (("opencodex", "개발 연결"), ("test", "별도 테스트 서버"), ("api", "공식 API"))
TASK_LABELS = {
    "brief": "기본 설정 정리",
    "personality": "성격·행동 초안",
    "consistency": "설정 충돌 검토",
    "voice": "말투·대표 대사 완성",
    "scenarios": "SFT 상황·사용자 발화 설계",
    "sft_answers": "학습 답변·대화 이력 작성",
    "screening": "설정·화자·문맥 전수 검사",
    "adjudication": "검수 이견·표본 재검토",
    "repair": "확인된 오류 수정",
}
STAGES = {
    "s3": "기획",
    "s7": "특질",
    "s8": "프롬프트",
    "s9s": "데이터 샘플",
    "s9": "데이터",
}
GATES = ("G3", "G6", "G7a", "G7")
MAX_CALLS = 50
MAX_CALL_LINE = 16_384
MAX_LEDGER_BYTES = 262_144
_REV_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/#-]{0,199}$")

# (stage, 폴더, 파일, 화면 이름, 본문 상한, 출처 기록 방식)
ARTIFACTS = (
    ("s3", "s3-plan", "plan.json", "기획서", 4000, "none"),
    ("s7", "s7-traits", "trait-sheet.json", "특질 시트", 4000, "s7"),
    ("s8", "s8-prompts", "long.md", "페르소나 프롬프트", 6000, "s8"),
    ("s9s", "s9-data", "check-report.json", "데이터 샘플 보고서", 3000, "none"),
    ("s9", "s9-data", "check-report.json", "데이터 검수 보고서", 3000, "none"),
)


def install_text_pipeline_routes(app: FastAPI, root: Path, conf: WebSettings, jobs: Any) -> None:
    """create_app에서 한 번 설치한다. jobs는 active_jobs()를 제공하는 작업 큐다."""
    del root  # 설정 파일·루트는 실제 WebSettings 값을 쓴다.

    async def _web_error(_request: Request, exc: WebError) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    app.add_exception_handler(WebError, _web_error)

    def snapshot() -> dict[str, Any]:
        return _snapshot(conf, jobs)

    @app.get("/api/text-pipeline")
    def text_pipeline() -> dict[str, Any]:
        return snapshot()

    @app.post("/api/text-pipeline/selection")
    def text_pipeline_selection(body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        profile, route = _selection_body(body)
        if jobs.active_jobs():
            raise WebError(409, "실행 중인 작업이 있으면 텍스트 설정을 바꿀 수 없다")
        config = _factory_config(conf)
        try:
            text_deck.select(config, profile=profile, route=route)
        except ValueError as exc:
            raise WebError(400, str(exc)) from exc
        except OSError as exc:
            raise WebError(503, "텍스트 설정을 저장하지 못했다") from exc
        return snapshot()

    @app.get("/api/text-pipeline/characters")
    def text_pipeline_characters() -> dict[str, Any]:
        return {"characters": _characters(conf)}

    @app.get("/api/text-pipeline/characters/{character_id}")
    def text_pipeline_character(character_id: str) -> dict[str, Any]:
        return _character(conf, character_id)


def _selection_body(body: Any) -> tuple[str | None, str | None]:
    if not isinstance(body, dict):
        raise WebError(400, "선택 본문은 JSON 객체여야 한다")
    unknown = sorted(set(body) - {"profile", "route"})
    if unknown:
        raise WebError(400, f"알 수 없는 선택 필드다: {', '.join(unknown)}")
    values: dict[str, str | None] = {}
    for key in ("profile", "route"):
        value = body.get(key)
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise WebError(400, f"{key}는 비어 있지 않은 문자열이어야 한다")
        values[key] = value.strip() if isinstance(value, str) else None
    if values["profile"] is None and values["route"] is None:
        raise WebError(400, "profile이나 route 가운데 하나는 필요하다")
    return values["profile"], values["route"]


def _factory_config(conf: WebSettings) -> FactoryConfig:
    try:
        return load_config(Path(conf.root), conf.config_path)
    except (OSError, ValueError, TypeError) as exc:
        raise WebError(503, "텍스트 공정 설정을 읽지 못했다") from exc


def _snapshot(conf: WebSettings, jobs: Any) -> dict[str, Any]:
    config = _factory_config(conf)
    source = text_deck.deck()
    settings = config.text_pipeline if isinstance(config.text_pipeline, dict) else {}
    enabled = bool(settings.get("enabled", False))
    profiles = [
        {"id": pid, "label": PROFILE_LABELS.get(pid, pid)} for pid in source.get("profiles", {})
    ]
    routes = _route_rows(config, source)
    active = len(jobs.active_jobs())
    if not enabled:
        return {
            "enabled": False,
            "profile": None,
            "route": None,
            "completionCheck": "NOT_RUN",
            "profiles": profiles,
            "routes": routes,
            "tasks": [],
            "activeJobs": active,
        }
    try:
        bindings = [config.text_binding(stage["id"]) for stage in source["stages"]]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise WebError(503, "선택한 텍스트 공정 설정을 사용할 수 없다") from exc
    tasks = [
        {
            "id": stage["id"],
            "label": TASK_LABELS.get(stage["id"], stage.get("task") or stage["id"]),
            "model": binding["model"],
            "reasoningEffort": binding["reasoning_effort"],
        }
        for stage, binding in zip(source["stages"], bindings, strict=True)
    ]
    return {
        "enabled": True,
        "profile": bindings[0]["profile"],
        "route": bindings[0]["route"],
        "completionCheck": "NOT_RUN",
        "profiles": profiles,
        "routes": routes,
        "tasks": tasks,
        "activeJobs": active,
    }


def _route_rows(config: FactoryConfig, source: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for route_id, label in ROUTES:
        available, reason = _route_state(config, source, route_id)
        rows.append({"id": route_id, "label": label, "available": available, "reason": reason})
    return rows


def _route_state(config: FactoryConfig, source: dict[str, Any], route_id: str) -> tuple[bool, str]:
    settings = config.text_pipeline if isinstance(config.text_pipeline, dict) else {}
    routes = settings.get("routes") if isinstance(settings.get("routes"), dict) else {}
    route_config = routes.get(route_id) if isinstance(routes.get(route_id), dict) else {}
    if route_id == "test" and not route_config.get("base_url"):
        return False, "주소·인증 설정이 필요합니다"
    # api 경로는 모든 덱 task가 해석되면 고를 수 있다. 키가 비었는지는 호출 직전에 확인한다.
    candidate = replace(config, text_pipeline={**settings, "route": route_id})
    try:
        for stage in source["stages"]:
            text_deck.resolve(candidate, stage["id"])
    except (ValueError, KeyError, TypeError):
        return False, "경로 설정을 확인해야 합니다"
    return True, ""


def _characters(conf: WebSettings) -> list[dict[str, Any]]:
    root = Path(conf.root)
    folder = root / reads.CHARACTERS_DIR
    if not folder.is_dir():
        return []
    try:
        candidates = sorted(folder.iterdir(), key=lambda p: p.name)
    except OSError:
        return []
    out = []
    for candidate in candidates:
        if candidate.name.startswith(".") or not candidate.is_dir():
            continue
        try:
            char_dir = reads.character_dir(root, candidate.name)
        except (WebError, OSError):
            continue
        out.append({"id": char_dir.name, "name": _character_name(char_dir)})
    return out


def _character(conf: WebSettings, character_id: str) -> dict[str, Any]:
    char_dir = reads.character_dir(Path(conf.root), character_id)
    state, _error = reads.read_state(char_dir)
    return {
        "characterId": char_dir.name,
        "name": _character_name(char_dir, state),
        "stages": _stage_rows(state),
        "gates": _gate_rows(state),
        "calls": _recent_calls(char_dir),
        "artifacts": _artifact_rows(char_dir, state),
        "workshopUrl": (
            f"/studio/d-ops.html#char/{quote(char_dir.name, safe='')}"
            if conf.studio_path is not None
            else f"/c-glass.html?character={quote(char_dir.name, safe='')}"
        ),
    }


def _character_name(char_dir: Path, state: dict[str, Any] | None = None) -> str:
    if state is None:
        state, _error = reads.read_state(char_dir)
    rev = _stage_rev(state, "s3") or _gate_rev(state, "G3")
    if rev:
        path = _safe_file(char_dir, "s3-plan", rev, "plan.json")
        data = _read_json_object(path) if path else None
        name = _text(data.get("name")) if data else None
        if name:
            return name
    return char_dir.name


def _stage_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": sid,
            "label": label,
            "status": _status(_state_item(state, "stages", sid)),
            "revision": _stage_rev(state, sid),
        }
        for sid, label in STAGES.items()
    ]


def _gate_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": gid,
            "status": _status(_state_item(state, "gates", gid)),
            "revision": _gate_rev(state, gid),
        }
        for gid in GATES
    ]


def _state_item(state: dict[str, Any], table: str, key: str) -> dict[str, Any]:
    raw = state.get(table) if isinstance(state.get(table), dict) else {}
    item = raw.get(key) if isinstance(raw.get(key), dict) else {}
    return item


def _status(item: dict[str, Any]) -> str:
    value = item.get("status")
    return value if isinstance(value, str) and value else "PENDING"


def _stage_rev(state: dict[str, Any], stage_id: str) -> str | None:
    value = _state_item(state, "stages", stage_id).get("currentRev")
    return value if isinstance(value, str) and _REV_RE.fullmatch(value) else None


def _gate_rev(state: dict[str, Any], gate_id: str) -> str | None:
    value = _state_item(state, "gates", gate_id).get("rev")
    return value if isinstance(value, str) and _REV_RE.fullmatch(value) else None


def _recent_calls(char_dir: Path) -> list[dict[str, Any]]:
    path = _safe_file(char_dir, "ledger", "calls.jsonl")
    if path is None:
        return []
    rows = []
    for record in _tail_json_lines(path, MAX_CALLS * 4):
        binding = record.get("textBinding")
        binding = binding if isinstance(binding, dict) else {}
        stage = str(record.get("stage", "")).lower()
        if str(record.get("kind", "")).upper() in {"IMAGE", "VISION", "VIDEO", "TRAIN"}:
            continue
        if (
            not binding.get("task")
            and not stage.startswith(("s3", "s7", "s8", "s9", "cv-"))
            and stage not in {"g3", "g6", "g7a", "g7"}
        ):
            continue
        rows.append(
            {
                "task": _text(binding.get("task"))
                or _text(record.get("kind"))
                or _text(record.get("stage")),
                "stage": _text(record.get("stage")),
                "model": _text(record.get("model")),
                "profile": _text(binding.get("profile")),
                "route": _text(binding.get("route")),
                "ok": bool(record.get("ok")),
                "ref": _safe_ref(record.get("ref")),
            }
        )
    return rows[-MAX_CALLS:]


def _tail_json_lines(path: Path, limit: int) -> list[dict[str, Any]]:
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            end = handle.tell()
            start = max(0, end - MAX_LEDGER_BYTES)
            handle.seek(start)
            data = handle.read()
    except OSError:
        return []
    if start:
        cut = data.find(b"\n")
        data = data[cut + 1 :] if cut >= 0 else b""
    lines = [line for line in data.split(b"\n") if line.strip()][-limit:]
    out = []
    for line in lines:
        if len(line) > MAX_CALL_LINE:
            continue
        try:
            row = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _safe_ref(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not _REF_RE.fullmatch(value) or any(part == ".." for part in value.split("/")):
        return None
    return value


def _artifact_rows(char_dir: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for stage_id, folder, filename, label, limit, source_kind in ARTIFACTS:
        rev = _stage_rev(state, stage_id)
        if not rev:
            continue
        path = _safe_file(char_dir, folder, rev, filename)
        text = _read_limited(path, limit) if path else None
        if text is None:
            continue
        source_model, source_profile, completion = _source_of(
            char_dir, state, stage_id, rev, source_kind
        )
        rows.append(
            {
                "label": label,
                "revision": rev,
                "text": text,
                "textTruncated": len(text) > limit,
                "sourceModel": source_model,
                "sourceProfile": source_profile,
                "completionCheck": completion,
            }
        )
    return rows


def _source_of(
    char_dir: Path,
    state: dict[str, Any],
    stage_id: str,
    rev: str,
    source_kind: str,
) -> tuple[str | None, str | None, str]:
    if source_kind not in {"s7", "s8"}:
        return None, None, "NOT_RUN"
    path = _safe_file(char_dir, _folder(stage_id), rev, "text-deck-binding.json")
    data = _read_json_object(path) if path else None
    if not isinstance(data, dict):
        return None, None, "NOT_RUN"
    if source_kind == "s8":
        source = data.get("sourceGeneration")
        source = source if isinstance(source, dict) else {}
        binding = source.get("binding")
        binding = binding if isinstance(binding, dict) else {}
        completion = _text(data.get("completionCheck")) or "NOT_RUN"
        return (
            _text(source.get("responseModel")),
            _text(binding.get("profile")),
            completion,
        )
    binding = data.get("binding")
    binding = binding if isinstance(binding, dict) else {}
    return _text(data.get("responseModel")), _text(binding.get("profile")), "NOT_RUN"


def _folder(stage_id: str) -> str:
    folders = {
        "s3": "s3-plan",
        "s7": "s7-traits",
        "s8": "s8-prompts",
        "s9s": "s9-data",
        "s9": "s9-data",
    }
    return folders[stage_id]


def _safe_file(base: Path, *parts: str) -> Path | None:
    try:
        target = base.joinpath(*parts).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not target.is_relative_to(base) or not target.is_file():
        return None
    return target


def _read_limited(path: Path, limit: int) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            text = handle.read(limit + 1)
    except OSError:
        return None
    return text[:limit] + "…" if len(text) > limit else text


def _read_json_object(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read(200_001)
    except (OSError, UnicodeDecodeError):
        return None
    if len(text) > 200_000:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
