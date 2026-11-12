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

from character_factory_poc.common.config import load_config
from character_factory_poc.common.demo_chat import Scene
from character_factory_poc.common.ledger import Ledger
from character_factory_poc.pipeline.graph import CREATED, GATES, STAGES, gates_for
from character_factory_poc.pipeline.origin import (
    graph_for_dir,
    origin_label,
    read_archived,
    read_auto_review,
    read_model_mode,
    read_origin,
)
from character_factory_poc.pipeline.queue import gate_queue
from character_factory_poc.pipeline.review import load_review
from character_factory_poc.pipeline.rework import rework_status
from character_factory_poc.pipeline.state import gate_events_path, stage_events_path
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.gate_items import build_gate_items, file_url
from character_factory_poc.web.quality_status import derive_quality_status

CHARACTERS_DIR = "runs/characters"
BRIEFS_DIR = "runs/briefs"
MAX_FILES = 500
MAX_BRIEF_FILES = 100
DONE_STATUSES = {"APPROVED", "SKIPPED"}
# D-0101: 단계·관문 이력은 원장 끝부분만 읽는다. 회차 이력은 단계마다 최근 몇 번만 돌려준다.
MAX_TIMELINE_LINES = 20000
MAX_HISTORY = 10
_RUN_ENDS = {"AWAITING_HUMAN", "APPROVED", "CHECK_FAILED", "REJECTED", "SKIPPED"}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}
_TEXT_SUFFIXES = {".md", ".txt", ".log"}

# 단계 폴더 이름 (각 단계 run.py가 쓰는 값). S9~S11은 LLD §5.14·§5.15·§5.17의 저장 위치다.
STAGE_DIRS = {
    "s0": "s0-source",
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
    "s8c": "s8-chapters",
    "s9s": "s9-data",
    "s9": "s9-data",
    "s10t": "s10-train",
    "s10": "s10-eval",
    "s11": "s11-release",
    "sx": "sx-export",
    "px": "px-preview",
}

GATE_TITLES = {
    "G0": "출처 묶음 승인",
    "G1s": "기준 사진 선택",
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

# 모티브 갈래에만 있는 사람 전용 관문(D-0128). 오리지널 관문 목록(known_gates)에는 넣지 않는다.
TWIN_GATE_META: dict[str, dict[str, Any]] = {
    "G0": {
        "kind": "sourcePack",
        "stage": "s0",
        "connected": True,
        "decisions": ("APPROVE", "REQUEST_CHANGES", "REJECT"),
    },
    "G1s": {
        "kind": "sourcePhotos",
        "stage": "s2",
        "connected": True,
        "decisions": ("SELECT", "APPROVE", "REQUEST_CHANGES", "REJECT"),
    },
}

# 화면의 갈래(팀) 묶음. d-ops 시안의 병렬 작업 표시와 같은 나눔이다.
LANES = [
    {"id": "appearance", "label": "외모", "stages": ("s1", "s2")},
    {"id": "plan", "label": "기획", "stages": ("s3", "s3r")},
    {"id": "scene", "label": "장면", "stages": ("s4a", "s4b", "s4")},
    {"id": "video", "label": "영상", "stages": ("s5", "s6")},
    {"id": "persona", "label": "페르소나", "stages": ("s7", "s8")},
    {"id": "data", "label": "데이터", "stages": ("s9s", "s9")},
    {"id": "training", "label": "학습", "stages": ("s10t", "s10")},
    {"id": "voice", "label": "음성", "stages": ("sv",)},
    {"id": "release", "label": "패키지", "stages": ("s11", "sx", "px")},
]


def known_gates() -> list[str]:
    """화면이 아는 관문 순서. 그래프에 아직 없는 관문도 화면에는 보여 준다."""
    return [gate for gate in GATE_ORDER if gate in GATES or gate in GATE_META]


def decision_gates() -> list[str]:
    """결정을 받을 수 있는 관문 전체. 오리지널 관문 뒤에 모티브 전용 관문(G0·G1s)을 붙인다."""
    return [*TWIN_GATE_META, *known_gates()]


def gate_meta(gate: str) -> dict[str, Any]:
    meta = GATE_META.get(gate) or TWIN_GATE_META.get(gate)
    if meta is None:
        raise WebError(404, f"관문이 없다: {gate}({', '.join(known_gates())} 중 하나다)")
    return {"gate": gate, "title": GATE_TITLES.get(gate, gate), **meta}


# 비교 세트 원문과 정답 키가 든 파일. 화면 파일 목록·파일 열기 어디에도 내보내지 않는다(D-0120).
_TWIN_DEMO_RE = re.compile(r"^twin-demo-([a-f0-9]{32})\.html$")


def private_file(path: Path) -> bool:
    """비교 세트 원문(holdout.jsonl·s9h 장면), 가족 판정 전 시연 화면(실제 답이 드러난다)."""
    if path.name == "holdout.jsonl":
        return True
    if path.name == "scenes.jsonl" and "s9h-holdout" in path.parts:
        return True
    demo = _TWIN_DEMO_RE.match(path.name)
    return bool(demo) and not (path.parent / f"twin-votes-{demo.group(1)}.json").is_file()


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


def _read_jsonl(path: Path, limit: int = MAX_TIMELINE_LINES) -> list[dict[str, Any]]:
    """덧붙이기 기록의 끝부분. 읽지 못한 줄은 건너뛰고 파일이 없으면 빈 목록이다."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def stage_timeline(char_dir: Path) -> dict[str, dict[str, Any]]:
    """단계별 마지막 시작·종료·결정 시각과 회차 이력(D-0101). 기록이 없는 옛 캐릭터는 빈 dict다.

    RUNNING이 회차 하나를 연다. AWAITING_HUMAN·APPROVED·CHECK_FAILED·REJECTED·SKIPPED가 열린 회차를
    닫는다. 이미 닫힌 뒤 오는 APPROVED·REJECTED는 사람 결정으로 본다.
    """
    out: dict[str, dict[str, Any]] = {}
    for event in _read_jsonl(stage_events_path(char_dir)):
        sid, to, at = event.get("stage"), event.get("to"), event.get("at")
        if not isinstance(sid, str) or not isinstance(to, str):
            continue
        rec = out.setdefault(
            sid, {"startedAt": None, "endedAt": None, "decidedAt": None, "attempts": []}
        )
        attempts = rec["attempts"]
        open_attempt = attempts[-1] if attempts and attempts[-1]["endedAt"] is None else None
        if to == "RUNNING":
            if open_attempt is not None:
                open_attempt["endedAt"] = at
                open_attempt["result"] = "RESTARTED"
            attempts.append(
                {
                    "attempt": event.get("attempt"),
                    "rev": event.get("rev"),
                    "startedAt": at,
                    "endedAt": None,
                    "result": None,
                    "error": None,
                    "decision": None,
                }
            )
            rec.update(startedAt=at, endedAt=None, decidedAt=None)
        elif to in _RUN_ENDS:
            if open_attempt is not None:
                open_attempt.update(endedAt=at, result=to, error=event.get("error"))
                if event.get("rev"):
                    open_attempt["rev"] = event.get("rev")
                rec["endedAt"] = at
            else:
                rec["decidedAt"] = at
                if attempts:
                    attempts[-1]["decision"] = to
        del attempts[:-MAX_HISTORY]
    return out


def gate_timeline(char_dir: Path) -> dict[str, dict[str, Any]]:
    """관문별 마지막으로 열린 시각과 결정 시각(ledger/gate-events.jsonl, D-0101)."""
    out: dict[str, dict[str, Any]] = {}
    for event in _read_jsonl(gate_events_path(char_dir)):
        gate, at = event.get("gate"), event.get("at")
        if not isinstance(gate, str):
            continue
        if event.get("event") == "opened":
            out[gate] = {
                "openedAt": at,
                "openedRev": event.get("rev"),
                "decidedAt": None,
                "decision": None,
            }
        elif event.get("event") == "decided":
            rec = out.setdefault(gate, {"openedAt": None, "openedRev": event.get("rev")})
            rec["decidedAt"] = at
            rec["decision"] = event.get("status")
    return out


def cost_summary(char_dir: Path) -> dict[str, Any] | None:
    """원장 호출 기록의 추정 비용 합계. 비용 없는 호출은 0으로 더하지 않고 따로 센다(FR-67)."""
    folder = Path(char_dir) / "ledger"
    if not (folder / "calls.jsonl").exists():
        return {"estUsd": 0.0, "calls": 0, "unpricedCalls": 0}
    try:
        report = Ledger(folder).report()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    total = sum(float(s.get("estCostUsd") or 0) for s in report["byStage"].values())
    return {
        "estUsd": round(total, 4),
        "calls": report["totalCalls"],
        "unpricedCalls": report["unpricedCalls"],
    }


def _add_times(char_dir: Path, stages: list[dict[str, Any]], gates: list[dict[str, Any]]) -> None:
    timeline = stage_timeline(char_dir)
    for row in stages:
        times = timeline.get(row["id"], {})
        row["startedAt"] = times.get("startedAt")
        row["endedAt"] = times.get("endedAt")
        row["decidedAt"] = times.get("decidedAt")
    opened = gate_timeline(char_dir)
    for row in gates:
        times = opened.get(row["id"], {})
        row["openedAt"] = times.get("openedAt")
        row["decidedAt"] = times.get("decidedAt")


def graph_parts(char_dir):
    graph = graph_for_dir(char_dir)
    origin = read_origin(char_dir)
    attached = {stage.gate for stage in graph.values()}
    gates = [gid for gid in gates_for(origin) if gid in attached]
    metadata = {
        "origin": origin,
        "originLabel": origin_label(origin),
        "modelMode": read_model_mode(char_dir),
    }
    return graph, gates, metadata


SOURCE_LANE = {"id": "source", "label": "출처", "stages": ("s0",)}


def graph_lanes(graph):
    """팀 줄. 모티브는 맨 앞에 출처 팀(s0)을 두고 비교 세트(s9h)를 학습 팀에 넣는다.

    캐릭터 상세의 lanes와 /api/runtime/graph가 같은 배치를 쓰도록 여기서만 정한다.
    그 캐릭터 그래프에 없는 단계는 빼고, 단계가 다 빠진 팀도 뺀다. 학습하지 않는 방식이면
    학습 팀 이름은 '평가'다.
    """
    if "s0" not in graph:
        return LANES
    lanes = []
    for lane in [SOURCE_LANE, *LANES]:
        ids = ("s9h", *lane["stages"]) if lane["id"] == "training" else lane["stages"]
        if "s8" in ids:
            ids = (*ids, "s8c")
        kept = [sid for sid in ids if sid in graph]
        if kept:
            label = "평가" if lane["id"] == "training" and "s10t" not in graph else lane["label"]
            lanes.append({**lane, "label": label, "stages": kept})
    return lanes


def _twin_queue(graph, stages, pending):
    # 큐의 unblocks는 승인 한 번으로 바로 실행 가능한 수가 아니라 하류 미완료 단계 수다.
    done = {s["id"] for s in stages if s["status"] in DONE_STATUSES}
    queue = []
    for gate in pending:
        reached = {gate["id"]}
        while True:
            before = len(reached)
            for sid, stage in graph.items():
                if (stage.deps | stage.needs | stage.after) & reached:
                    reached.add(sid)
                    if stage.gate:
                        reached.add(stage.gate)
            if len(reached) == before:
                break
        downstream = [sid for sid in graph if sid in reached and sid not in done]
        queue.append(
            {
                "gate": gate["id"],
                "stage": next(s for s in graph if graph[s].gate == gate["id"]),
                "rev": gate["rev"],
                "openedAt": gate["openedAt"],
                "unblocks": len(downstream),
                "unblockedStages": downstream,
            }
        )
    return sorted(queue, key=lambda q: (-q["unblocks"], q["openedAt"] or "~"))


def _stage_rows(state: dict[str, Any], graph=STAGES) -> list[dict[str, Any]]:
    raw_stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
    raw_gates = state.get("gates") if isinstance(state.get("gates"), dict) else {}
    rows: list[dict[str, Any]] = []
    for stage_id, stage in graph.items():
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


def _gate_rows(state: dict[str, Any], gates=GATES) -> list[dict[str, Any]]:
    raw_gates = state.get("gates") if isinstance(state.get("gates"), dict) else {}
    rows: list[dict[str, Any]] = []
    for gate in gates:
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


QA_FIELDS = ("displayName", "status", "statusLabel", "chatReady", "goal", "createdAt", "archived")
STATUS_LABELS = dict(
    draft="시작 전",
    running="만드는 중",
    needs_review="확인 필요",
    chat_ready="대화 가능",
    failed="실패",
    stopped="멈춤",
)


def display_name(persona, intake):
    return (
        (persona or {}).get("name")
        or (intake or {}).get("subject", {}).get("displayName")
        or "이름 미정"
    )


def _demo_summary(char_dir: Path) -> dict | None:
    """시연 모드(자동 승인·테스터 발행) 상태. 꺼져 있으면 None."""
    from character_factory_poc.pipeline.demo import read_demo_mode

    try:
        mode = read_demo_mode(char_dir)
    except (OSError, ValueError):
        return None
    if mode is None:
        return None
    status = read_json_file(char_dir / "demo-status.json") or {}
    return {
        "enabled": True,
        "budgetUsd": mode.budgetUsd,
        "phase": status.get("phase", "ready"),
        "detail": status.get("detail", ""),
        "apiCharacterId": status.get("apiCharacterId"),
        "at": status.get("at"),
    }


def created_at(folder, intake):
    intake = intake or {}
    origin = read_json_file(folder / "origin.json") or {}
    stat = folder.stat()
    return (
        intake.get("createdAt")
        or origin.get("setAt")
        or datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_mtime), UTC).isoformat()
    )


def is_draft(intake, stages):
    return bool(
        intake
        and not intake.get("jobId")
        and all(s.get("status", "PENDING") == "PENDING" for s in stages if isinstance(s, dict))
    )


def visible_folders(root, *, include_archived=False):
    base = characters_root(root)
    if base.is_dir():
        for folder in sorted(base.iterdir()):
            if (
                _ID_RE.fullmatch(folder.name)
                and not folder.is_symlink()
                and folder.is_dir()
                and (include_archived or not read_archived(folder))
            ):
                yield folder


def chat_characters(root):
    items = []
    for folder in visible_folders(root):
        intake = read_json_file(folder / "s0-source/intake.json")
        name = display_name(_persona(folder), intake)
        if Scene.read(folder, name=name).readiness()["ready"]:
            items.append(
                dict(
                    characterId=folder.name,
                    displayName=name,
                    createdAt=created_at(folder, intake),
                    origin=read_origin(folder),
                )
            )
    return sorted(items, key=lambda r: r["createdAt"], reverse=True)


def job_status(row, job, last):
    status = row["status"]
    if (
        job
        and job["status"] == "running"
        and not (row.get("chatReady") and job.get("trigger") in {"videos", "videos-with-chat"})
    ):
        status = "running"
    elif status != "needs_review" and last and last["status"] == "failed":
        status = "failed"
    elif not job and last and last.get("status") == "succeeded" and status != "failed":
        gates = {g["id"]: g for g in row.get("gates", [])}
        if any(gates.get(g, {}).get("status") != "APPROVED" for g in last.get("waiting", [])):
            status = "needs_review"
    row.update(status=status, statusLabel=STATUS_LABELS[status])


def video_fields(folder, state):
    from character_factory_poc.pipeline.origin import is_twin, read_signature, read_video_tier
    from character_factory_poc.stages.s6_actions.catalog import signature_matches

    tier = read_video_tier(folder)
    signature = read_signature(folder)
    gate = state.get("gates", {}).get("G5b", {})
    approved = gate.get("rev") if gate.get("status") == "APPROVED" else None
    preset = ""
    inputs = {}
    if approved:
        inputs = read_json_file(folder / "s6-actions" / approved / "inputs.json") or {}
        preset = inputs.get("preset", "")
    # D-0165: 모티브는 시그니처 포즈를 바꾸면 영상을 다시 만들어야 한다.
    same_signature = not tier or not is_twin(folder) or signature_matches(inputs, signature, folder)
    job = read_json_file(folder / "video-job.json") or {}
    status = "none"
    if not tier and not preset.startswith("tier:"):
        # 영상 등급이 없는 캐릭터(오리지널 등)는 영상 칩을 띄우지 않는다(QA v5 E7).
        status = "none"
    elif tier != "none" and approved and (not tier or preset == f"tier:{tier}") and same_signature:
        status = "ready"
    elif tier and tier == job.get("tier"):
        if job.get("status") in ("queued", "running"):
            status = "making"
        elif job.get("status") == "failed":
            status = "failed"
    labels = {
        "none": "아직 영상이 없어요",
        "making": "영상을 만들고 있어요",
        "ready": "영상을 볼 수 있어요",
        "failed": "영상을 만들지 못했어요",
    }
    # 영상 작업이 실패했으면 까닭을 사람 말 한 줄로 싣는다(QA v5 E13). 예외 이름은 뗀다.
    error = ""
    if status == "failed":
        error = re.sub(r"^[A-Za-z_]*(Error|Exception): ", "", str(job.get("error") or "")).strip()
    return dict(
        videoTier=tier or (preset.removeprefix("tier:") if preset.startswith("tier:") else "none"),
        videoStatus=status,
        videoLabel=labels[status],
        videoError=error[:200],
        signaturePose=signature,
    )


def character_summary(char_dir: Path) -> dict[str, Any]:
    """캐릭터 한 명의 목록용 요약. 단계·관문 상태와 지금 기다리는 관문을 담는다."""
    char_dir = Path(char_dir)
    cid = char_dir.name
    state, error = read_state(char_dir)
    graph, gate_ids, meta = graph_parts(char_dir)
    stages = _stage_rows(state, graph)
    gates = _gate_rows(state, gate_ids)
    quality = derive_quality_status(char_dir, stages, gates)
    for stage in stages:
        review = next((g for g in quality["approvals"] if g["gate"] == stage["gate"]), None)
        if review:
            stage["qualityReview"] = dict(review)
            if stage["id"] == "s10":
                stage["qualityReview"]["label"] += " · " + quality["comparison"]["label"]
    _add_times(char_dir, stages, gates)
    persona = _persona(char_dir)
    pending = [g for g in gates if g["status"] == "AWAITING_HUMAN"]
    intake = read_json_file(char_dir / "s0-source/intake.json")
    display = display_name(persona, intake)
    chat = False if error else Scene.read(char_dir, name=display).readiness()["ready"]
    goal_stages = stages
    if meta["origin"] != CREATED:
        ids = {"s0", "s3", "s7", "s8", "s8c"}
        if meta["modelMode"] == "TRAIN":
            ids.update(("s9s", "s9", "s10t"))
        goal_stages = [s for s in stages if s["id"] in ids]
    goal = _progress(goal_stages)
    # 대화 가능 여부는 별도 기능이다. 실패·검토와 실제 완료 수를 덮지 않는다(D-0181).
    # 수정 요청(REJECTED)은 실패가 아니라 다시 확인할 일이다(QA 3차).
    if any(s["status"] == "CHECK_FAILED" for s in stages):
        status = "failed"
    elif pending or any(s["status"] == "REJECTED" for s in stages):
        status = "needs_review"
    elif chat:
        status = "chat_ready"
    elif is_draft(intake, stages):
        status = "draft"
    else:
        status = "stopped"
    return {
        "id": cid,
        "kind": "character",
        **meta,
        "name": (persona or {}).get("name") or cid,
        "displayName": display,
        "status": status,
        "statusLabel": STATUS_LABELS[status],
        "chatReady": chat,
        "qualityStatus": quality,
        "chapterTemplate": (read_json_file(char_dir / "source-pack.json") or {}).get(
            "chapterTemplate", ""
        ),
        **video_fields(char_dir, state),
        "createdAt": created_at(char_dir, intake),
        "archived": read_archived(char_dir),
        "goal": dict(
            label="전체 단계"
            if meta["origin"] == CREATED
            else "대화와 학습 준비"
            if meta["modelMode"] == "TRAIN"
            else "대화 제작 단계",
            done=goal["done"],
            total=goal["total"],
        ),
        "persona": persona,
        "dir": f"{CHARACTERS_DIR}/{cid}",
        "stateError": error,
        "stages": stages,
        "gates": gates,
        "lanes": _lanes(stages, graph_lanes(graph)),
        "pendingGates": pending,
        "queue": (
            [item.as_dict() for item in gate_queue(char_dir, state)]
            if meta["origin"] == CREATED
            else _twin_queue(graph, stages, pending)
        ),
        "progress": _progress(stages),
        "awaitingHuman": bool(pending),
        "updatedAt": _mtime_iso(char_dir / "state.json"),
    }


def _lane_status(items: list[dict[str, Any]]) -> str:
    # D-0101: 사람이 할 일과 실패를 실행 중보다 먼저 알린다(같은 갈래에서 겹쳐도 가려지지 않게).
    if any(s["status"] == "AWAITING_HUMAN" for s in items):
        return "gate"
    if any((s["gateStatus"] or "") == "AWAITING_HUMAN" for s in items):
        return "gate"
    if any(s["status"] == "CHECK_FAILED" for s in items):
        return "failed"
    if any(s["status"] == "RUNNING" for s in items):
        return "running"
    if items and all(s["status"] in DONE_STATUSES for s in items):
        return "done"
    return "pending"


def _lanes(stages: list[dict[str, Any]], lanes=LANES) -> list[dict[str, Any]]:
    by_id = {s["id"]: s for s in stages}
    out: list[dict[str, Any]] = []
    for lane in lanes:
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
    timeline = stage_timeline(char_dir)
    history = {sid: timeline[sid]["attempts"] for sid in graph_for_dir(char_dir) if sid in timeline}
    return {
        "id": character_id,
        "dir": f"{CHARACTERS_DIR}/{character_id}",
        "state": state,
        "stateError": error,
        "summary": summary,
        "qualityStatus": summary["qualityStatus"],
        **{
            k: summary[k]
            for k in (
                "origin",
                "originLabel",
                "modelMode",
                "chapterTemplate",
                "videoTier",
                "videoStatus",
                "videoLabel",
                "signaturePose",
                "videoError",
                *QA_FIELDS,
            )
        },
        "autoReview": read_auto_review(char_dir),
        "demo": _demo_summary(char_dir),
        "persona": summary["persona"],
        "stages": summary["stages"],
        "gates": summary["gates"],
        "lanes": summary["lanes"],
        "pendingGates": summary["pendingGates"],
        "queue": summary["queue"],
        "progress": summary["progress"],
        "updatedAt": summary["updatedAt"],
        "history": history,
        "cost": cost_summary(char_dir),
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
    graph, gates, metadata = graph_parts(char_dir)
    if gate not in gates:
        raise WebError(404, f"이 캐릭터에 없는 관문이다: {gate}")
    gate_row = next((g for g in _gate_rows(state, gates) if g["id"] == gate), None)
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
    stage_row = next((s for s in _stage_rows(state, graph) if s["id"] == stage_id), None)
    rev = gate_row["rev"]
    rev_dir: Path | None = None
    if rev:
        candidate = char_dir / stage_dir / rev
        if candidate.is_dir():
            rev_dir = candidate
    files = [
        _file_entry(char_dir, p) for p in _iter_files(rev_dir, MAX_FILES) if not private_file(p)
    ]
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
    if (
        gate == "G8"
        and metadata["modelMode"] == "BIND_EXISTING"
        and items.get("viewKind") == "promptOnly"
    ):
        # 값은 승인 기록의 실제 참조다. 화면용 문구와 분리해 결정 본문으로 그대로 보낸다.
        options = items.get("adoptOptions", [])
        if len(options) == 1:
            items.update(
                title="연결한 모델 채택", adoptLabel="연결한 모델로 진행", adoptTarget=options[0]
            )
    if gate == "G0" and "usageProblems" in items:
        # 이전 판에 남은 사용 근거 안내도 승인을 막지 않아요.
        items["usageProblems"] = []
    if (
        gate == "G8"
        and metadata["modelMode"] == "PROMPT_ONLY"
        and items.get("viewKind") == "promptOnly"
    ):
        items.update(title="프롬프트만", adoptLabel="프롬프트만 사용해요")
    missing = list(items.get("problems", []))
    if meta["connected"] and rev_dir is None:
        missing.append(
            f"{stage_dir}/{rev or '<rev>'}/ 폴더가 없다. 단계를 먼저 돌리거나 state.json의 "
            "revision을 확인한다"
        )
    # D-0049(LLD §6.8): 현재 관문 revision의 사전 검토만 보여 준다. 옛 revision 기록은 숨긴다.
    review = load_review(char_dir, gate, rev) if rev else None
    return {
        "characterId": character_id,
        **metadata,
        "gate": gate,
        "title": items.get("title") or meta["title"],
        "kind": items.get("viewKind") or meta["kind"],
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
        "review": review.model_dump(mode="json") if review is not None else None,
        "stage": stage_row,
        "stageDir": (f"{CHARACTERS_DIR}/{character_id}/{stage_dir}/{rev}" if rev_dir else None),
        "files": files,
        "previews": previews,
        "stateError": error,
        "generatedAt": now_iso(),
        "rework": rework_status(char_dir, gate, load_config(root).rework),
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
    if private_file(target):
        raise WebError(403, "비교 세트 원문이나 가족 판정 전 시연 화면은 화면에서 열 수 없다")
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


def list_projects(root: Path, *, include_archived=False) -> dict[str, Any]:
    """runs/characters/* 와 runs/briefs/* 목록 (GET /api/projects)."""
    root = Path(root)
    briefs_dir = briefs_root(root)
    characters: list[dict[str, Any]] = []
    for folder in visible_folders(root, include_archived=include_archived):
        try:
            characters.append(character_summary(folder))
        except OSError as exc:  # 권한 등으로 읽지 못한 폴더는 목록에 사유만 남긴다
            characters.append(
                {
                    "id": folder.name,
                    "kind": "character",
                    "name": folder.name,
                    "displayName": "이름 미정",
                    "status": "failed",
                    "statusLabel": STATUS_LABELS["failed"],
                    "chatReady": False,
                    "videoTier": "none",
                    "videoStatus": "none",
                    "videoLabel": "아직 영상이 없어요",
                    "goal": dict(label="전체 단계", done=0, total=0),
                    "createdAt": _mtime_iso(folder),
                    "archived": read_archived(folder),
                    "persona": None,
                    "dir": f"{CHARACTERS_DIR}/{folder.name}",
                    "stateError": f"폴더를 읽지 못했다: {exc}",
                    "stages": [],
                    "gates": [],
                    "pendingGates": [],
                    "queue": [],
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
            pending += sum(
                1
                for g in _gate_rows(state, graph_parts(folder)[1])
                if g["status"] == "AWAITING_HUMAN"
            )
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
    graph, gates, _ = graph_parts(char_dir)
    payload = {
        # D-0101: 같은 RUNNING으로 다시 들어간 재시도와 새 revision도 화면에 알린다.
        "stages": {
            sid: [
                _field(raw_stages.get(sid), "status"),
                _field(raw_stages.get(sid), "attempts"),
                _field(raw_stages.get(sid), "currentRev"),
            ]
            for sid in graph
        },
        "gates": {
            gid: [_field(raw_gates.get(gid), "status"), _field(raw_gates.get(gid), "rev")]
            for gid in gates
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else None
