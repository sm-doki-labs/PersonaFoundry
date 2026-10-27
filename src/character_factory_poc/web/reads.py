"""워크숍 API의 읽기 모델 (PoC 계획서 §6).

runs/characters와 runs/briefs를 읽어 화면이 바로 쓸 수 있는 모양으로 바꾼다. 쓰기는 하지 않는다.
state.json이 손상돼도 목록 전체를 죽이지 않고 stateError로 알린다.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.pipeline.graph import GATES, STAGES
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.gate_items import build_gate_items, file_url

CHARACTERS_DIR = "runs/characters"
BRIEFS_DIR = "runs/briefs"
MAX_FILES = 500
MAX_BRIEF_FILES = 100
DONE_STATUSES = {"APPROVED", "SKIPPED"}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}
_TEXT_SUFFIXES = {".md", ".txt", ".log"}

# 단계 폴더 이름 (각 단계 run.py가 쓰는 값). S9~S11은 LLD §5.14·§5.15·§5.17의 저장 위치다.
STAGE_DIRS = {
    "s1": "s1-reference",
    "s2": "s2-hero",
    "s3": "s3-plan",
    "s3r": "s3r-refs",
    "s4a": "s4a-backgrounds",
    "s4b": "s4b-poses",
    "s4": "s4-frames",
    "s5": "s5-intro",
    "s6": "s6-actions",
    "s7": "s7-traits",
    "s8": "s8-prompts",
    "s9s": "s9-data",
    "s9": "s9-data",
    "s10t": "s10-train",
    "s10": "s10-eval",
    "s11": "s11-release",
    "sx": "sx-export",
}

GATE_TITLES = {
    "G1": "얼굴 고르기",
    "G2": "대표 이미지 선택(결번)",
    "G3": "기획안 고르기",
    "G4a": "챕터 배경 고르기",
    "G4b": "장면·자세 고르기",
    "G4": "완성 이미지 승인",
    "G5": "소개 영상 고르기",
    "G5b": "동작 영상 고르기",
    "G6": "프롬프트 승인",
    "G7a": "데이터 샘플 검토",
    "G7": "데이터셋 승인",
    "G8": "평가·블라인드 20쌍",
    "G9": "패키지 승인",
}

# 관문 화면의 종류·단계·허용 결정. connected=False는 단계 코드가 아직 없어 501로 답하는 관문이다.
GATE_META: dict[str, dict[str, Any]] = {
    "G1": {
        "kind": "faces",
        "stage": "s1",
        "connected": True,
        "decisions": ("SELECT", "APPROVE", "REQUEST_CHANGES", "REJECT"),
    },
    "G3": {
        "kind": "planVariants",
        "stage": "s3",
        "connected": True,
        "decisions": ("SELECT", "APPROVE", "REQUEST_CHANGES", "REJECT"),
    },
    "G4a": {
        "kind": "backgrounds",
        "stage": "s4a",
        "connected": True,
        "decisions": ("SELECT", "APPROVE", "REQUEST_CHANGES", "REJECT"),
    },
    "G4b": {
        "kind": "poses",
        "stage": "s4b",
        "connected": True,
        "decisions": ("SELECT", "APPROVE", "REQUEST_CHANGES", "REJECT"),
    },
    "G4": {
        "kind": "frames",
        "stage": "s4",
        "connected": True,
        "decisions": ("APPROVE", "SELECT", "REQUEST_CHANGES", "REJECT"),
    },
    "G5": {
        "kind": "intro",
        "stage": "s5",
        "connected": True,
        "decisions": ("SELECT", "REQUEST_CHANGES", "REJECT"),
    },
    "G5b": {
        "kind": "actions",
        "stage": "s6",
        "connected": True,
        "decisions": ("SELECT", "APPROVE", "REQUEST_CHANGES", "REJECT"),
    },
    "G6": {
        "kind": "prompts",
        "stage": "s8",
        "connected": True,
        "decisions": ("APPROVE", "REQUEST_CHANGES", "REJECT"),
    },
    "G7a": {
        "kind": "samples",
        "stage": "s9s",
        "connected": True,
        "decisions": ("SELECT", "REQUEST_CHANGES", "REJECT"),
    },
    "G7": {
        "kind": "dataset",
        "stage": "s9",
        "connected": True,
        "decisions": ("APPROVE", "REQUEST_CHANGES", "REJECT"),
    },
    "G8": {
        "kind": "eval",
        "stage": "s10",
        "connected": True,
        "decisions": ("SELECT", "REQUEST_CHANGES", "REJECT"),
    },
    "G9": {
        "kind": "package",
        "stage": "s11",
        "connected": True,
        "decisions": ("APPROVE", "REJECT"),
    },
}
# 화면에 보이는 관문 순서. 그래프에 아직 없는 관문도 이 순서 안에서 보여 준다.
GATE_ORDER = tuple(GATE_META)

# 화면의 갈래(팀) 묶음. d-ops 시안의 병렬 작업 표시와 같은 나눔이다.
LANES = [
    {"id": "appearance", "label": "외모", "stages": ("s1", "s2")},
    {"id": "plan", "label": "기획", "stages": ("s3", "s3r")},
    {"id": "scene", "label": "장면", "stages": ("s4a", "s4b", "s4")},
    {"id": "video", "label": "영상", "stages": ("s5", "s6")},
    {"id": "persona", "label": "페르소나", "stages": ("s7", "s8")},
    {"id": "data", "label": "데이터", "stages": ("s9s", "s9")},
    {"id": "training", "label": "학습", "stages": ("s10t", "s10")},
    {"id": "release", "label": "패키지", "stages": ("s11", "sx")},
]


def known_gates() -> list[str]:
    """화면이 아는 관문 순서. 그래프에 아직 없는 관문도 화면에는 보여 준다."""
    return [gate for gate in GATE_ORDER if gate in GATES or gate in GATE_META]


def gate_meta(gate: str) -> dict[str, Any]:
    meta = GATE_META.get(gate)
    if meta is None:
        raise WebError(404, f"관문이 없다: {gate}({', '.join(known_gates())} 중 하나다)")
    return {"gate": gate, "title": GATE_TITLES.get(gate, gate), **meta}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")
    except OSError:
        return None


def _sort_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def characters_root(root: Path) -> Path:
    return Path(root) / CHARACTERS_DIR


def briefs_root(root: Path) -> Path:
    return Path(root) / BRIEFS_DIR


def character_dir(root: Path, character_id: str) -> Path:
    """캐릭터 폴더를 푼다. id 형식과 runs/characters 밖 경로를 막는다."""
    if not _ID_RE.match(character_id or "") or ".." in character_id:
        raise WebError(400, f"캐릭터 id 형식이 아니다: {character_id!r}")
    base = characters_root(root).resolve()
    target = (base / character_id).resolve()
    if not target.is_relative_to(base):
        raise WebError(400, f"캐릭터 폴더 밖을 가리킨다: {character_id!r}")
    if not target.is_dir():
        raise WebError(404, f"캐릭터가 없다: {character_id}")
    return target


def read_state(char_dir: Path) -> tuple[dict[str, Any], str | None]:
    """state.json을 읽는다. 없거나 깨졌으면 빈 상태와 사유를 돌려준다."""
    path = Path(char_dir) / "state.json"
    if not path.exists():
        return {}, "state.json이 없다"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {}, f"state.json을 읽지 못했다: {exc}"
    if not isinstance(data, dict):
        return {}, "state.json이 객체가 아니다"
    return data, None


def read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _stage_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    raw_stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
    raw_gates = state.get("gates") if isinstance(state.get("gates"), dict) else {}
    rows: list[dict[str, Any]] = []
    for stage_id, stage in STAGES.items():
        raw = raw_stages.get(stage_id) if isinstance(raw_stages.get(stage_id), dict) else {}
        gate_raw = raw_gates.get(stage.gate) if isinstance(raw_gates.get(stage.gate), dict) else {}
        rows.append(
            {
                "id": stage_id,
                "name": stage.name,
                "implemented": stage.implemented,
                "status": raw.get("status", "PENDING"),
                "rev": raw.get("currentRev"),
                "attempts": raw.get("attempts", 0),
                "lastError": raw.get("lastError"),
                "updatedAt": raw.get("updatedAt"),
                "gate": stage.gate,
                "gateStatus": gate_raw.get("status", "PENDING"),
                "gateRev": gate_raw.get("rev"),
                "gateTitle": GATE_TITLES.get(stage.gate or "", ""),
            }
        )
    return rows


def _gate_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    raw_gates = state.get("gates") if isinstance(state.get("gates"), dict) else {}
    rows: list[dict[str, Any]] = []
    for gate in GATES:
        raw = raw_gates.get(gate) if isinstance(raw_gates.get(gate), dict) else {}
        rows.append(
            {
                "id": gate,
                "title": GATE_TITLES.get(gate, gate),
                "status": raw.get("status", "PENDING"),
                "rev": raw.get("rev"),
                "recordRef": raw.get("recordRef"),
            }
        )
    return rows


def _progress(stages: list[dict[str, Any]]) -> dict[str, Any]:
    implemented = [s for s in stages if s["implemented"]]
    done = [s for s in implemented if s["status"] in DONE_STATUSES]
    current = next((s for s in implemented if s["status"] not in DONE_STATUSES), None)
    total = len(implemented)
    return {
        "done": len(done),
        "total": total,
        "percent": round(len(done) / total * 100) if total else 0,
        "currentStage": current["id"] if current else None,
    }


def _persona(char_dir: Path) -> dict[str, Any] | None:
    """가장 최근 기획서에서 화면에 보일 이름·직업만 꺼낸다."""
    plan_dir = Path(char_dir) / "s3-plan"
    if not plan_dir.is_dir():
        return None
    plans = sorted(plan_dir.glob("*/plan.json"), key=_sort_mtime, reverse=True)
    for plan in plans:
        data = read_json_file(plan)
        if not data:
            continue
        name = data.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        out: dict[str, Any] = {
            "name": name,
            "job": data.get("job") or "",
            "age": data.get("age"),
            "tagline": data.get("tagline") or "",
            "planRev": data.get("planRev") or plan.parent.name,
            "variantId": data.get("variantId"),
        }
        return out
    return None


def character_summary(char_dir: Path) -> dict[str, Any]:
    """캐릭터 한 명의 목록용 요약. 단계·관문 상태와 지금 기다리는 관문을 담는다."""
    char_dir = Path(char_dir)
    cid = char_dir.name
    state, error = read_state(char_dir)
    stages = _stage_rows(state)
    gates = _gate_rows(state)
    persona = _persona(char_dir)
    pending = [g for g in gates if g["status"] == "AWAITING_HUMAN"]
    return {
        "id": cid,
        "kind": "character",
        "name": (persona or {}).get("name") or cid,
        "persona": persona,
        "dir": f"{CHARACTERS_DIR}/{cid}",
        "stateError": error,
        "stages": stages,
        "gates": gates,
        "lanes": _lanes(stages),
        "pendingGates": pending,
        "progress": _progress(stages),
        "awaitingHuman": bool(pending),
        "updatedAt": _mtime_iso(char_dir / "state.json"),
    }


def _lane_status(items: list[dict[str, Any]]) -> str:
    if any(s["status"] == "RUNNING" for s in items):
        return "running"
    if any(s["status"] == "CHECK_FAILED" for s in items):
        return "failed"
    if any(s["status"] == "AWAITING_HUMAN" for s in items):
        return "gate"
    if any((s["gateStatus"] or "") == "AWAITING_HUMAN" for s in items):
        return "gate"
    if items and all(s["status"] in DONE_STATUSES for s in items):
        return "done"
    return "pending"


def _lanes(stages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {s["id"]: s for s in stages}
    out: list[dict[str, Any]] = []
    for lane in LANES:
        items = [by_id[sid] for sid in lane["stages"] if sid in by_id]
        done = [s for s in items if s["status"] in DONE_STATUSES]
        out.append(
            {
                "id": lane["id"],
                "label": lane["label"],
                "status": _lane_status(items),
                "implemented": any(s["implemented"] for s in items),
                "done": len(done),
                "total": len(items),
                "percent": round(len(done) / len(items) * 100) if items else 0,
                "stages": [
                    {
                        "id": s["id"],
                        "name": s["name"],
                        "status": s["status"],
                        "rev": s["rev"],
                        "gate": s["gate"],
                        "gateStatus": s["gateStatus"],
                        "implemented": s["implemented"],
                    }
                    for s in items
                ],
                "pendingGates": [
                    s["gate"] for s in items if s["gate"] and s["gateStatus"] == "AWAITING_HUMAN"
                ],
            }
        )
    return out


def character_detail(root: Path, character_id: str) -> dict[str, Any]:
    """state.json 전체 + 갈래별 진행 + 대기 중인 관문 (GET /api/characters/{id})."""
    char_dir = character_dir(root, character_id)
    state, error = read_state(char_dir)
    summary = character_summary(char_dir)
    return {
        "id": character_id,
        "dir": f"{CHARACTERS_DIR}/{character_id}",
        "state": state,
        "stateError": error,
        "summary": summary,
        "persona": summary["persona"],
        "stages": summary["stages"],
        "gates": summary["gates"],
        "lanes": summary["lanes"],
        "pendingGates": summary["pendingGates"],
        "progress": summary["progress"],
        "updatedAt": summary["updatedAt"],
    }


def _kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return "image"
    if suffix in _VIDEO_SUFFIXES:
        return "video"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".json":
        return "json"
    if suffix in _TEXT_SUFFIXES:
        return "text"
    return "file"


def _iter_files(folder: Path | None, limit: int) -> list[Path]:
    if folder is None or not folder.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if path.name.endswith(".tmp") or path.name.startswith("."):
            continue
        out.append(path)
        if len(out) >= limit:
            break
    return out


def _file_entry(char_dir: Path, path: Path) -> dict[str, Any]:
    rel = path.relative_to(char_dir).as_posix()
    try:
        size = path.stat().st_size
    except OSError:
        size = 0
    return {
        "path": rel,
        "name": path.name,
        "size": size,
        "mtime": _mtime_iso(path),
        "kind": _kind(path),
        "url": file_url(char_dir.name, rel),
    }


def gate_records(char_dir: Path, gate: str) -> list[dict[str, Any]]:
    """gates/<gate>-<rev>.json 기록을 모두 모은다(오래된 것부터)."""
    folder = Path(char_dir) / "gates"
    if not folder.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(folder.glob(f"{gate}-*.json")):
        out.append({"file": path.relative_to(char_dir).as_posix(), "record": read_json_file(path)})
    return out


def gate_view(root: Path, character_id: str, gate: str) -> dict[str, Any]:
    """관문 상세 화면의 자료: 고를 항목·파일·미리보기 URL·기존 관문 기록.

    단계 코드가 없는 관문(G7a·G7·G8·G9)은 계약 모양의 합성 예시를 돌려주고 synthetic=true로
    표시한다. 결정은 이 경로가 아니라 POST .../decision이 기존 approve 경로로 보낸다.
    """
    meta = gate_meta(gate)
    char_dir = character_dir(root, character_id)
    state, error = read_state(char_dir)
    raw_gates = state.get("gates") if isinstance(state.get("gates"), dict) else {}
    raw_gate = raw_gates.get(gate) if isinstance(raw_gates.get(gate), dict) else {}
    gate_row = next((g for g in _gate_rows(state) if g["id"] == gate), None)
    if gate_row is None:
        gate_row = {
            "id": gate,
            "title": meta["title"],
            "status": raw_gate.get("status", "PENDING"),
            "rev": raw_gate.get("rev"),
            "recordRef": raw_gate.get("recordRef"),
        }
    stage_id = meta["stage"]
    stage_dir = STAGE_DIRS.get(stage_id, stage_id)
    stage_row = next((s for s in _stage_rows(state) if s["id"] == stage_id), None)
    rev = gate_row["rev"]
    rev_dir: Path | None = None
    if rev:
        candidate = char_dir / stage_dir / rev
        if candidate.is_dir():
            rev_dir = candidate
    files = [_file_entry(char_dir, p) for p in _iter_files(rev_dir, MAX_FILES)]
    records = gate_records(char_dir, gate)
    record_ref = gate_row["recordRef"] or raw_gate.get("recordRef")
    current = read_json_file(char_dir / str(record_ref)) if record_ref else None
    previews = [f for f in files if f["kind"] in {"html", "image", "video"}]
    items = build_gate_items(
        gate=gate,
        kind=meta["kind"],
        connected=meta["connected"],
        char_dir=char_dir,
        character_id=character_id,
        stage_dir=stage_dir,
        rev=rev,
    )
    missing = list(items.get("problems", []))
    if meta["connected"] and rev_dir is None:
        missing.append(
            f"{stage_dir}/{rev or '<rev>'}/ 폴더가 없다. 단계를 먼저 돌리거나 state.json의 "
            "revision을 확인한다"
        )
    return {
        "characterId": character_id,
        "gate": gate,
        "title": meta["title"],
        "kind": meta["kind"],
        "connected": meta["connected"],
        "decisions": list(meta["decisions"]),
        "synthetic": items.get("source") == "fixture",
        "items": items,
        "missing": missing,
        "status": gate_row["status"],
        "rev": rev,
        "recordRef": record_ref,
        "record": current,
        "records": records,
        "stage": stage_row,
        "stageDir": (f"{CHARACTERS_DIR}/{character_id}/{stage_dir}/{rev}" if rev_dir else None),
        "files": files,
        "previews": previews,
        "stateError": error,
        "generatedAt": now_iso(),
    }


def resolve_file(root: Path, character_id: str, rel: str) -> Path:
    """캐릭터 폴더 안의 파일만 연다. ..·절대 경로·심볼릭 링크로 폴더를 벗어나면 거절한다."""
    char_dir = character_dir(root, character_id)
    if not rel or "\x00" in rel:
        raise WebError(400, "파일 경로가 비었거나 잘못됐다")
    try:
        target = (char_dir / rel).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise WebError(400, f"파일 경로를 풀 수 없다: {rel}") from exc
    if not target.is_relative_to(char_dir):
        raise WebError(400, "캐릭터 폴더 밖의 파일은 열 수 없다")
    if not target.is_file():
        raise WebError(404, f"파일이 없다: {rel}")
    return target


def _brief_summary(folder: Path) -> dict[str, Any]:
    files = [
        {
            "path": p.relative_to(folder).as_posix(),
            "name": p.name,
            "size": p.stat().st_size,
            "mtime": _mtime_iso(p),
        }
        for p in _iter_files(folder, MAX_BRIEF_FILES)
    ]
    return {
        "id": folder.name,
        "kind": "brief",
        "dir": f"{BRIEFS_DIR}/{folder.name}",
        "files": files,
        "hasBrief": (folder / "brief.md").exists(),
        "hasPlan": (folder / "plan.json").exists(),
        "hasProbes": (folder / "probes.txt").exists(),
        "updatedAt": _mtime_iso(folder),
    }


def list_projects(root: Path) -> dict[str, Any]:
    """runs/characters/* 와 runs/briefs/* 목록 (GET /api/projects)."""
    root = Path(root)
    chars_dir = characters_root(root)
    briefs_dir = briefs_root(root)
    characters: list[dict[str, Any]] = []
    if chars_dir.is_dir():
        for folder in sorted(chars_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            try:
                characters.append(character_summary(folder))
            except OSError as exc:  # 권한 등으로 읽지 못한 폴더는 목록에 사유만 남긴다
                characters.append(
                    {
                        "id": folder.name,
                        "kind": "character",
                        "name": folder.name,
                        "persona": None,
                        "dir": f"{CHARACTERS_DIR}/{folder.name}",
                        "stateError": f"폴더를 읽지 못했다: {exc}",
                        "stages": [],
                        "gates": [],
                        "pendingGates": [],
                        "progress": {"done": 0, "total": 0, "percent": 0, "currentStage": None},
                        "awaitingHuman": False,
                        "updatedAt": None,
                    }
                )
    briefs: list[dict[str, Any]] = []
    if briefs_dir.is_dir():
        for folder in sorted(briefs_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            try:
                briefs.append(_brief_summary(folder))
            except OSError:
                continue
    pending = sum(len(c["pendingGates"]) for c in characters)
    return {
        "generatedAt": now_iso(),
        "root": str(root),
        "characters": characters,
        "briefs": briefs,
        "totals": {
            "characters": len(characters),
            "briefs": len(briefs),
            "pendingGates": pending,
        },
    }


def health_snapshot(root: Path) -> dict[str, Any]:
    """SSE hello에 실을 가벼운 집계. 캐릭터 폴더만 훑는다."""
    root = Path(root)
    chars_dir = characters_root(root)
    briefs_dir = briefs_root(root)
    characters = 0
    pending = 0
    if chars_dir.is_dir():
        for folder in sorted(chars_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith("."):
                continue
            characters += 1
            state, _ = read_state(folder)
            pending += sum(1 for g in _gate_rows(state) if g["status"] == "AWAITING_HUMAN")
    briefs = (
        sum(1 for p in briefs_dir.iterdir() if p.is_dir() and not p.name.startswith("."))
        if briefs_dir.is_dir()
        else 0
    )
    return {"characters": characters, "briefs": briefs, "pendingGates": pending}


def state_signature(root: Path, character_id: str) -> str:
    """단계·관문 상태가 바뀌었는지 비교할 서명. 작업 중 SSE push에 쓴다."""
    char_dir = character_dir(root, character_id)
    state, _ = read_state(char_dir)
    raw_stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
    raw_gates = state.get("gates") if isinstance(state.get("gates"), dict) else {}
    payload = {
        "stages": {sid: _field(raw_stages.get(sid), "status") for sid in STAGES},
        "gates": {
            gid: [_field(raw_gates.get(gid), "status"), _field(raw_gates.get(gid), "rev")]
            for gid in GATES
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else None
