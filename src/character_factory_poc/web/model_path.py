"""모델 만들기 화면의 읽기 모델(D-0130): 재료 → 데이터셋 → 학습 → 평가.

캐릭터 폴더의 기록(s9-data, s10-train, s10-eval, gates, state.json)만 읽는다. 쓰지 않는다.
학습 진행은 공급자가 training-run.json에 남긴 상태·진행(appliedConfig.progress)과 임대
기록(lease.json)·감시 기록(guard.json)·체크포인트 선택 기록으로 계산한다. 쓴 돈은 임대 시간 ×
시간당 단가로 낸 추정이다(청구액이 아니다).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REV = {
    "ds": re.compile(r"^ds(\d+)$"),
    "tr": re.compile(r"^tr(\d+)$"),
    "ev": re.compile(r"^ev(\d+)$"),
}
STOP_FILE = "stop-request.json"
SKIP_FILE = "skip-training.json"
FINAL = {"FAILED", "CANCELLED"}
MATERIAL_KO = {
    "SNS_REWRITE": "실제 대화(SNS·말뭉치) 다시 쓰기",
    "SYNTH": "합성",
    "NIKL": "국립국어원 말뭉치",
    # 모티브 학습 데이터는 G0에서 승인한 원문 대화를 그대로 쓴다(QA v5 B-F22).
    "SOURCE": "원문 대화",
}
SOURCE_KO = {"SNS": "SNS(문자)", "NIKL": "말뭉치(통화)"}
DROP_KO = {
    "not_alternating": "말한 사람이 번갈아 나오지 않음",
    "empty_turn": "빈 발화가 있음",
    "too_short": "4턴보다 짧음",
    "over_limit": "후보 상한을 넘음",
    "over_share": "말뭉치 비율 상한을 넘음",
}
DECISION_KO = {
    "DEVELOPMENT_RECOMMENDED": "개발 권장",
    "INCONCLUSIVE": "판단 보류",
    "KEEP_INCUMBENT": "기반 모델 유지",
    "BLOCKED_INTEGRITY": "선별 기록 문제",
    "BLOCKED_QUALITY": "품질 미달",
    "MODEL_ACCEPTED": "모델 채택",
    "RELEASE_ACCEPTED": "출시 채택",
    "PENDING": "고르는 중",
}
PHASES = (
    ("guard", "감시 시작", "GPU를 빌리기 전에 자동 반납 감시를 켜요"),
    ("lease", "GPU 빌림", "학습할 GPU를 한 대 빌려요"),
    ("upload", "데이터 올림", "파일 해시가 맞아야 시작해요"),
    ("train", "학습", "0.5회차마다 체크포인트를 남겨요"),
    ("screen", "선별 답 만들기", "체크포인트마다 같은 질문에 답해요"),
    ("collect", "결과 받기·GPU 반납", "받은 파일을 확인하고 바로 반납해요"),
    ("select", "체크포인트 고르기", "판정 모델이 짝으로 비교해요"),
)
# 연결한 모델 종류와 연결 전 확인 결과를 화면 말로(QA v5 B-F07).
BIND_KIND_KO = {
    "HF_ADAPTER": "Hugging Face 어댑터",
    "VERTEX_TUNED": "Vertex 튜닝 모델",
    "ENDPOINT": "서빙 주소",
}
CHECK_KO = {
    "PASSED": "저장소 주인·커밋·기반 모델을 확인했어요",
    "SKIPPED": "연결 정보만 기록했어요(미리 확인하지 않음)",
}
# 평가 조건 이름(QA v5 C-08). 화면은 관문 G8과 같은 조건 수를 센다.
ARM_KO = {
    "LONG_BASE": "긴 프롬프트",
    "SHORT_GEMMA_SFT": "Gemma 학습 모델",
    "SHORT_GEMINI_SFT": "Gemini 학습 모델",
}
# 옛 기록에 남은 내부 코드 문구를 화면 말로 바꾼다(QA v5 B-F22).
_PLAIN = (
    ("개로 50개 미만이다.", "개로 50개보다 적어요."),
    ("PROMPT_ONLY를 권장한다", "학습 대신 '프롬프트만' 방식을 권해요"),
    ("PROMPT_ONLY", "'프롬프트만' 방식"),
)


def plain_note(text: str) -> str:
    for old, new in _PLAIN:
        text = text.replace(old, new)
    return text


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8")) if path.is_file() else None
    except (OSError, json.JSONDecodeError):
        return None


def _jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        lines = path.read_text("utf-8").splitlines() if path.is_file() else []
    except OSError:
        return out
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _latest(folder: Path, kind: str, prefer: str | None = None) -> Path | None:
    if not folder.is_dir():
        return None
    if prefer and _REV[kind].match(prefer) and (folder / prefer).is_dir():
        return folder / prefer
    found = [
        (int(m.group(1)), p)
        for p in folder.iterdir()
        if p.is_dir() and (m := _REV[kind].match(p.name))
    ]
    return max(found)[1] if found else None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return at if at.tzinfo else at.replace(tzinfo=UTC)


def _hours(start: Any, end: Any, now: datetime) -> float | None:
    a = _time(start)
    if a is None:
        return None
    b = _time(end) or now
    return round(max(0.0, (b - a).total_seconds() / 3600.0), 4)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _gate_record(char_dir: Path, gates: dict[str, Any], gate: str) -> dict[str, Any]:
    g = _dict(gates.get(gate))
    out: dict[str, Any] = {"status": g.get("status", "PENDING"), "rev": g.get("rev")}
    ref = g.get("recordRef")
    rec = _dict(_json(char_dir / ref)) if isinstance(ref, str) else {}
    out["decidedAt"] = rec.get("decidedAt")
    out["decision"] = rec.get("decision")
    out["selections"] = [s for s in rec.get("selections") or [] if isinstance(s, str)]
    return out


# ---- 재료·데이터셋 ---------------------------------------------------------------------------


def dataset_view(char_dir: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    gates = _dict(state.get("gates"))
    stages = _dict(state.get("stages"))
    rev_dir = _latest(char_dir / "s9-data", "ds", _dict(gates.get("G7")).get("rev"))
    if rev_dir is None:
        return None
    plan = _dict(_json(rev_dir / "plan.json"))
    index = _jsonl(rev_dir / "index.jsonl")
    report = _dict(_json(rev_dir / "check-report.json"))
    warnings = [plain_note(w) for w in report.get("warnings") or [] if isinstance(w, str)]
    by_cluster: dict[str, Counter] = {}
    materials: dict[str, Counter] = {}
    for row in index:
        cid = str(row.get("clusterId") or "")
        by_cluster.setdefault(cid, Counter())[str(row.get("split") or "")] += 1
        materials.setdefault(cid, Counter())[str(row.get("material") or "")] += 1
    clusters = []
    for c in plan.get("clusters") or []:
        cid = str(c.get("clusterId"))
        splits = by_cluster.get(cid, Counter())
        verdicts = Counter(
            str(v)
            for v in _dict(
                _dict(_json(rev_dir / "qa" / f"G7a-{cid}.json")).get("verdicts")
            ).values()
        )
        clusters.append(
            {
                "id": cid,
                "label": c.get("label") or cid,
                "share": c.get("share"),
                "target": c.get("targetConversations"),
                "materialsPlanned": list(c.get("materials") or []),
                "materials": {k: n for k, n in materials.get(cid, Counter()).items() if k},
                "train": splits.get("train", 0),
                "validation": splits.get("validation_base", 0)
                + splits.get("validation_augmented", 0),
                "eval": splits.get("eval", 0),
                "sample": {"total": sum(verdicts.values()), **dict(verdicts)},
                "warnings": [w for w in warnings if w.startswith(cid + ":")],
            }
        )
    totals: Counter = Counter()
    for row in index:
        split = str(row.get("split") or "")
        totals["validation" if split.startswith("validation") else split] += 1
    mats = Counter(str(r.get("material") or "") for r in index)
    g7a = [_dict(_json(p)) for p in sorted((char_dir / "gates").glob(f"G7a-{rev_dir.name}-*.json"))]
    g7a_at = max((str(r.get("decidedAt") or "") for r in g7a), default="") or None
    return {
        "rev": rev_dir.name,
        "status": _dict(stages.get("s9")).get("status", "PENDING"),
        "sampleStatus": _dict(stages.get("s9s")).get("status", "PENDING"),
        "planned": plan.get("targetTrainConversations"),
        "counts": {
            "train": totals.get("train", 0),
            "validation": totals.get("validation", 0),
            "eval": totals.get("eval", 0),
            "total": len(index),
        },
        "clusters": clusters,
        "warnings": warnings,
        # 클러스터 이름으로 시작하지 않는 경고(재료 집계 등)는 데이터셋 전체 경고로 보인다.
        "notes": [w for w in warnings if not any(w.startswith(c + ":") for c in by_cluster)],
        "sources": _sources(report.get("sources")),
        "trainingPrompt": _training_prompt(rev_dir),
        "blocking": [w for w in report.get("blocking") or [] if isinstance(w, str)],
        "materials": {k: n for k, n in mats.items() if k},
        "gates": {
            "G7a": {
                **_gate_record(char_dir, gates, "G7a"),
                "decidedAt": g7a_at,
                "records": len(g7a),
            },
            "G7": _gate_record(char_dir, gates, "G7"),
        },
    }


def _training_prompt(rev_dir: Path) -> dict[str, Any] | None:
    """S9가 남긴 학습용 짧은 프롬프트 요약(D-0138). 옛 데이터셋이면 None."""
    body = _dict(_json(rev_dir / "training-prompt.json"))
    if not body.get("core"):
        return None
    return {
        "coreChars": body.get("coreChars"),
        "longestChars": body.get("longestSystemChars"),
        "relationships": len(_dict(body.get("relationships"))),
        "channels": len(_dict(body.get("channels"))),
        "origin": body.get("origin"),
    }


def _sources(raw: Any) -> dict[str, Any] | None:
    """S9가 남긴 실제 대화 재료 집계(D-0131·D-0134). 없으면(옛 데이터셋) None."""
    if not isinstance(raw, dict):
        return None
    dropped = _dict(raw.get("dropped"))
    return {
        "file": raw.get("path") or "",
        "missing": bool(raw.get("missing")),
        "sessions": raw.get("sessions", 0),
        "split": raw.get("split", 0),
        "windows": raw.get("windows", 0),
        "window": raw.get("window"),
        "offered": raw.get("offered", 0),
        "used": raw.get("used"),
        "limit": raw.get("limit"),
        # D-0134: 출처별(SNS 문자·말뭉치 통화) 구간 수와 말뭉치 목표 비율.
        "corpusShare": raw.get("corpusShare"),
        # D-0135: 다시 쓰는 방식, 원본 겹침, 흐름 뼈대 예시.
        "rewrite": raw.get("rewrite") or "TURN_ONLY",
        "overlap": raw.get("overlap") if isinstance(raw.get("overlap"), dict) else None,
        "example": raw.get("example") if isinstance(raw.get("example"), dict) else None,
        "bySource": [
            {
                "kind": k,
                "label": SOURCE_KO.get(k, k),
                "sessions": _dict(v).get("sessions", 0),
                "windows": _dict(v).get("windows", 0),
                "offered": _dict(v).get("offered", 0),
                "used": _dict(raw.get("usedBySource")).get(k),
            }
            for k, v in sorted(_dict(raw.get("bySource")).items(), key=lambda kv: kv[0] != "SNS")
        ],
        "dropped": [
            {"reason": k, "label": DROP_KO.get(k, k), "count": n}
            for k, n in sorted(dropped.items())
            if isinstance(n, int) and n
        ],
    }


def material_view(dataset: dict[str, Any] | None) -> dict[str, Any] | None:
    if dataset is None:
        return None
    used = dataset["materials"]
    planned = sorted({m for c in dataset["clusters"] for m in c["materialsPlanned"]})
    return {
        "used": [
            {"kind": k, "label": MATERIAL_KO.get(k, k), "conversations": n}
            for k, n in sorted(used.items())
        ],
        "planned": [{"kind": k, "label": MATERIAL_KO.get(k, k)} for k in planned],
        "total": sum(used.values()),
        "sources": dataset.get("sources"),
        # D-0135: 새 데이터셋은 흐름 뼈대만 쓰고 양쪽을 새로 쓴다.
        # 옛 데이터셋은 캐릭터 턴만 다시 썼다.
        "rewrite": (dataset.get("sources") or {}).get("rewrite") or "TURN_ONLY",
        # 대화 데이터 창고(색인)는 아직 연결 전이다(K-0098).
        "warehouse": False,
        "status": dataset["sampleStatus"],
    }


# ---- 학습 -----------------------------------------------------------------------------------


def _phase(key: str, status: str, detail: str = "", meter: float | None = None) -> dict[str, Any]:
    _, name, hint = next(p for p in PHASES if p[0] == key)
    return {"key": key, "name": name, "status": status, "detail": detail or hint, "meter": meter}


def _money(value: Any) -> str:
    return "$" + format(float(value), ".2f")


def _phases(
    run: dict[str, Any], lease: dict[str, Any], guard: dict[str, Any], sel: dict[str, Any]
) -> list[dict[str, Any]]:
    status = run.get("status")
    ac = _dict(run.get("appliedConfig"))
    provider = run.get("provider")
    progress = _dict(ac.get("progress"))
    leased = provider == "gemma_qlora"
    # 제출(GPU 빌림·데이터 올림) 중에는 실행 기록이 아직 PLANNED다.
    # 임대 기록이 살아 있으면 시작한 것으로 본다.
    renting = lease.get("status") in {"CREATING", "CREATED", "READY"} and status == "PLANNED"
    started = status not in {"PLANNED", None} or renting
    out: list[dict[str, Any]] = []
    if not leased:
        note = (
            "시험용 가짜 학습이라 GPU를 빌리지 않아요"
            if provider == "fake"
            else "튜닝 서비스가 맡아요"
        )
        out += [_phase("guard", "skip", note), _phase("lease", "skip", note)]
    else:
        if guard:
            deadline = guard.get("deadlineAt")
            out.append(
                _phase("guard", "ok", f"자동 반납 마감 {deadline}" if deadline else "켰어요")
            )
        else:
            out.append(_phase("guard", "ok" if started else "idle"))
        ls = lease.get("status")
        gpu = lease.get("gpu") or ac.get("gpu")
        rate = lease.get("dphTotal") or ac.get("dphTotal")
        tail = " · ".join(
            x
            for x in (
                str(gpu) if gpu else "",
                ("시간당 " + _money(rate)) if isinstance(rate, int | float) else "",
            )
            if x
        )
        if ls == "CREATING":
            out.append(_phase("lease", "run", "GPU를 찾는 중이에요"))
        elif ls in {"CREATED", "READY"}:
            out.append(_phase("lease", "ok", tail or "빌렸어요"))
        elif ls == "DESTROYED":
            out.append(_phase("lease", "ok", (tail + " · " if tail else "") + "반납했어요"))
        elif ls in {"UNRESOLVED", "AMBIGUOUS"}:
            out.append(
                _phase(
                    "lease", "fail", "빌린 결과가 확실하지 않아요. 남은 GPU가 없는지 확인해야 해요"
                )
            )
        else:
            out.append(
                _phase(
                    "lease", "ok" if started else "idle", "지정한 서버를 써요" if started else ""
                )
            )
    transfers = run.get("transfers") or []
    if not started:
        out.append(_phase("upload", "idle"))
    elif not leased:
        out.append(_phase("upload", "ok", f"{len(transfers)}파일"))
    elif transfers and all(t.get("remoteSha256") for t in transfers):
        out.append(_phase("upload", "ok", f"{len(transfers)}파일 · 해시 일치"))
    elif renting and lease.get("status") == "READY":
        out.append(_phase("upload", "run", "올리는 중이에요"))
    else:
        out.append(_phase("upload", "run" if status == "SUBMITTED" else "idle"))
    step, total = progress.get("step"), progress.get("maxSteps")
    meter = None
    if isinstance(step, int | float) and isinstance(total, int | float) and total:
        meter = round(min(1.0, float(step) / float(total)), 4)
    steps = f"{int(step)} / {int(total)}스텝" if meter is not None else ""
    phase = progress.get("phase")
    if not started:
        out.append(_phase("train", "idle"))
    elif status == "CANCELLED" and phase not in {"screen", "done"}:
        out.append(_phase("train", "fail", "중단했어요" + (f" · {steps}" if steps else "")))
    elif status == "FAILED" and not ac.get("completedAt"):
        out.append(_phase("train", "fail", str(ac.get("error") or "학습이 실패했어요")[:200]))
    elif renting:
        out.append(_phase("train", "idle", "GPU가 준비되면 시작해요"))
    elif status in {"SUBMITTED", "RUNNING"} and phase not in {"screen", "done"}:
        if status == "RUNNING":
            out.append(_phase("train", "run", steps or "학습 중이에요", meter))
        else:
            out.append(_phase("train", "idle", "곧 시작해요"))
    else:
        out.append(_phase("train", "ok", steps or "끝났어요"))
    screening = int(_dict(run.get("requestedConfig")).get("screenGenerations") or 0)
    if not leased or not screening:
        out.append(_phase("screen", "skip", "이 학습은 선별 답을 만들지 않아요"))
    elif phase == "screen" and status == "RUNNING":
        out.append(_phase("screen", "run", f"{screening}번 생성 중이에요"))
    elif ac.get("screen") == "done":
        out.append(_phase("screen", "ok", f"{screening}번 생성"))
    elif ac.get("screen") == "failed":
        out.append(_phase("screen", "warn", "선별 답을 다 만들지 못했어요 · 학습 결과는 남았어요"))
    else:
        out.append(
            _phase("screen", "idle", f"체크포인트마다 같은 질문에 답해요 · {screening}번 생성")
        )
    if ac.get("collectPending"):
        out.append(_phase("collect", "fail", "결과를 받아 오지 못했어요"))
    elif status == "SUCCEEDED" and (not leased or ac.get("remoteDeleted")):
        destroyed = lease.get("destroyedAt")
        out.append(
            _phase(
                "collect",
                "ok",
                "받은 파일 확인" + (f" · {destroyed} 반납 확인" if destroyed else ""),
            )
        )
    elif status == "SUCCEEDED":
        out.append(_phase("collect", "run", "받는 중이에요"))
    else:
        out.append(_phase("collect", "idle"))
    decision = _dict(ac.get("selection")).get("decision")
    binding = _dict(run.get("modelBinding"))
    if decision == "PENDING":
        out.append(_phase("select", "run", "고르는 중이에요"))
    elif decision:
        chosen = _dict(sel.get("chosen")).get("checkpointId")
        label = DECISION_KO.get(str(decision), str(decision))
        out.append(
            _phase(
                "select", "ok" if binding else "warn", (f"{chosen} · " if chosen else "") + label
            )
        )
    elif binding and status == "SUCCEEDED":
        out.append(_phase("select", "ok", f"{binding.get('checkpointId')} · 마지막 체크포인트"))
    else:
        out.append(_phase("select", "idle"))
    return out


def _selection(sel: dict[str, Any], run: dict[str, Any]) -> dict[str, Any] | None:
    if sel.get("arms"):
        wins = _dict(sel.get("wins"))
        chosen = _dict(sel.get("chosen")).get("checkpointId")
        rows = []
        for arm in sel.get("arms") or []:
            arm = _dict(arm)
            rows.append(
                {
                    "arm": arm.get("arm"),
                    "role": arm.get("role"),
                    "epoch": arm.get("epoch"),
                    "empty": _dict(arm.get("empty")).get("rate"),
                    "truncated": _dict(arm.get("truncated")).get("rate"),
                    "loop": _dict(arm.get("loop")).get("rate"),
                    "eligible": arm.get("eligible"),
                    "exclusion": arm.get("exclusion") or "",
                    "wins": wins.get(str(arm.get("arm"))),
                    "chosen": arm.get("arm") == chosen,
                }
            )
        return {
            "decision": sel.get("decision"),
            "decisionKo": DECISION_KO.get(str(sel.get("decision")), sel.get("decision")),
            "chosen": chosen,
            "reasons": [str(r) for r in sel.get("reasons") or []][:5],
            "rows": rows,
        }
    binding = _dict(run.get("modelBinding"))
    if run.get("status") == "SUCCEEDED" and binding:
        rows = [
            {
                "arm": c.get("checkpointId"),
                "role": "checkpoint",
                "epoch": c.get("epoch"),
                "chosen": c.get("checkpointId") == binding.get("checkpointId"),
            }
            for c in run.get("checkpoints") or []
            if isinstance(c, dict)
        ]
        return {
            "decision": None,
            "decisionKo": "선별 없이 마지막 체크포인트",
            "chosen": binding.get("checkpointId"),
            "reasons": [],
            "rows": rows,
        }
    return None


def _run_view(folder: Path, now: datetime) -> dict[str, Any]:
    run = _dict(_json(folder / "training-run.json"))
    lease = _dict(_json(folder / "lease.json"))
    guard = _dict(_json(folder / "guard.json"))
    sel = _dict(_json(folder / "checkpoint-selection.json"))
    ac = _dict(run.get("appliedConfig"))
    est = _dict(run.get("estimate"))
    req = _dict(run.get("requestedConfig"))
    alive = bool(lease) and lease.get("status") not in {None, "NONE", "DESTROYED"}
    rate = lease.get("dphTotal") or ac.get("dphTotal") or ac.get("hourlyRateUsd")
    hours = _hours(lease.get("createdAt"), lease.get("destroyedAt"), now) if lease else None
    spent = (
        round(hours * float(rate), 2)
        if hours is not None and isinstance(rate, int | float)
        else None
    )
    if run.get("provider") == "fake" and run.get("status") not in {"PLANNED", None}:
        spent = 0.0
    return {
        "provider": run.get("provider") or folder.name,
        "status": run.get("status"),
        "dryRun": run.get("dryRun"),
        "baseModel": run.get("baseModel"),
        "estimate": {
            "usd": est.get("usd"),
            "gpuHours": est.get("gpuHours"),
            "basis": est.get("basis") or "",
        },
        "budgetUsd": run.get("budgetUsd"),
        "config": {
            k: req.get(k)
            for k in ("epochs", "checkpointEpochs", "screenGenerations", "loraR", "maxSeqLength")
            if k in req
        },
        "transfers": len(run.get("transfers") or []),
        "progress": _dict(ac.get("progress")),
        "submittedAt": ac.get("submittedAt"),
        "completedAt": ac.get("completedAt"),
        "elapsedHours": _hours(
            ac.get("submittedAt"), ac.get("completedAt") or lease.get("destroyedAt"), now
        ),
        "spentUsd": spent,
        "hourlyUsd": rate if isinstance(rate, int | float) else None,
        "gpu": lease.get("gpu") or ac.get("gpu"),
        "gpuAlive": alive,
        "gpuSince": lease.get("createdAt") if alive else None,
        "deadlineAt": guard.get("deadlineAt"),
        "collectPending": bool(ac.get("collectPending")),
        "collectError": str(ac.get("collectError") or "")[:300],
        "error": str(ac.get("error") or "")[:300],
        "binding": run.get("modelBinding"),
        "selection": _selection(sel, run),
        "phases": _phases(run, lease, guard, sel),
    }


def _state_of(runs: list[dict[str, Any]], skip: bool) -> str:
    statuses = [r["status"] for r in runs]
    if any(
        r["collectPending"] or (r["gpuAlive"] and r["status"] in FINAL | {"SUCCEEDED"})
        for r in runs
    ):
        return "hold"
    if (
        any(s in {"SUBMITTED", "RUNNING"} for s in statuses)
        or any(r["status"] == "PLANNED" and r["gpuAlive"] for r in runs)
        or any(
            r["status"] == "SUCCEEDED" and r["phases"] and r["phases"][-1]["status"] == "run"
            for r in runs
        )
    ):
        return "run"
    if runs and all(s == "SUCCEEDED" for s in statuses):
        return "done"
    if "CANCELLED" in statuses:
        return "stopped"
    if "FAILED" in statuses:
        return "fail"
    return "skip" if skip else "plan"


def training_view(
    char_dir: Path, state: dict[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    stages = _dict(state.get("stages"))
    g7 = _dict(_dict(state.get("gates")).get("G7")).get("status", "PENDING")
    rev_dir = _latest(char_dir / "s10-train", "tr")
    base: dict[str, Any] = {
        "state": "pending" if g7 == "APPROVED" else "locked",
        "rev": None,
        "stageStatus": _dict(stages.get("s10t")).get("status", "PENDING"),
        "providers": [],
        "phases": [],
        "stopRequested": False,
        "skip": False,
    }
    if rev_dir is None:
        return base
    plan = _dict(_json(rev_dir / "plan.json"))
    runs = [
        _run_view(folder, now)
        for folder in sorted(p for p in rev_dir.iterdir() if (p / "training-run.json").is_file())
    ]
    skip = (rev_dir / SKIP_FILE).is_file()
    kind = _state_of(runs, skip)
    est = [r["estimate"]["usd"] for r in runs]
    spent = [r["spentUsd"] for r in runs if r["spentUsd"] is not None]
    return {
        **base,
        "state": kind,
        "rev": rev_dir.name,
        "datasetRev": plan.get("datasetRev"),
        "plannedAt": plan.get("createdAt"),
        "estimateUsd": round(sum(float(u) for u in est), 4) if est and None not in est else None,
        "budgetUsd": round(sum(float(r["budgetUsd"] or 0) for r in runs), 2) if runs else None,
        "gpuHours": round(sum(float(r["estimate"]["gpuHours"] or 0) for r in runs), 3)
        if runs
        else None,
        "spentUsd": round(sum(spent), 2) if spent else None,
        "adopted": any(r["binding"] for r in runs),
        "skip": skip,
        "stopRequested": (rev_dir / STOP_FILE).is_file() and kind == "run",
        "providers": runs,
        "phases": runs[0]["phases"] if runs else [],
    }


# ---- 평가 -----------------------------------------------------------------------------------


def eval_view(char_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    s10 = _dict(_dict(state.get("stages")).get("s10"))
    rev_dir = _latest(char_dir / "s10-eval", "ev", s10.get("currentRev"))
    report = _dict(_json(rev_dir / "report.json")) if rev_dir else {}
    gate = _gate_record(char_dir, _dict(state.get("gates")), "G8")
    arms = _arms(rev_dir)
    return {
        "status": s10.get("status", "PENDING"),
        "rev": rev_dir.name if rev_dir else None,
        "promptOnly": bool(rev_dir and (rev_dir / "prompt-only.json").is_file()),
        "gate": gate,
        "decision": report.get("decision"),
        "recommendation": report.get("recommendation"),
        "sftPrompt": _sft_prompt(char_dir, rev_dir),
        "arms": arms,
        "adopted": _adopted(gate, arms),
    }


def _arms(rev_dir: Path | None) -> list[dict[str, Any]]:
    """G8이 비교하는 조건(사전 등록 순서). 학습 결과가 없는 조건은 bound=False다."""
    prereg = _dict(_json(rev_dir / "prereg.json")) if rev_dir else {}
    out = []
    for a in prereg.get("arms") or []:
        arm = _dict(a)
        arm_id = str(arm.get("armId") or "")
        model = str(arm.get("model") or "")
        out.append(
            {
                "id": arm_id,
                "label": ARM_KO.get(arm_id, "학습 모델"),
                "model": model,
                "bound": not model.startswith("UNBOUND:"),
            }
        )
    return out


def _adopted(gate: dict[str, Any], arms: list[dict[str, Any]]) -> dict[str, Any] | None:
    """G8에서 채택한 조건. 승인 전이면 None이다."""
    if gate.get("status") != "APPROVED" or not gate.get("selections"):
        return None
    value = gate["selections"][0]
    if value == "LONG_BASE":
        return {"value": value, "label": ARM_KO["LONG_BASE"]}
    arm = next((a for a in arms if a["model"] == value), None)
    if arm:
        return {"value": value, "label": arm["label"]}
    if value.startswith("model-prep/"):
        return {"value": value, "label": "연결한 모델"}
    return {"value": value, "label": "학습 모델"}


def binding_view(char_dir: Path) -> dict[str, Any] | None:
    """학습된 모델 연결(BIND_EXISTING): 최신 학습 기록 폴더의 연결 기록. 없으면 None.

    s10 평가가 쓰는 규칙(stages.s10_eval.twin)과 같게, 최신 tr 폴더의 IMPORTED-mb* 하나만 본다.
    """
    rev_dir = _latest(char_dir / "s10-train", "tr")
    paths = sorted(rev_dir.glob("IMPORTED-mb*/training-run.json")) if rev_dir else []
    if len(paths) != 1:
        return None
    run = _dict(_json(paths[0]))
    applied = _dict(run.get("appliedConfig"))
    b = _dict(applied.get("binding"))
    check = _dict(applied.get("preflight"))
    prov = _dict(b.get("provenance"))
    status = str(check.get("status") or "")
    return {
        "rev": str(run.get("provider") or "").removeprefix("IMPORTED-"),
        "kind": b.get("provider"),
        "kindLabel": BIND_KIND_KO.get(str(b.get("provider")), "학습된 모델"),
        "ref": b.get("ref"),
        "revision": b.get("revision"),
        "baseModel": b.get("baseModel"),
        "baseModelRevision": b.get("baseModelRevision"),
        "servingRoute": b.get("servingRoute"),
        "trainedBy": prov.get("trainedBy"),
        "trainedAt": prov.get("trainedAt"),
        "dataNote": prov.get("dataNote"),
        "usageBasis": prov.get("usageBasis"),
        "check": status,
        "checkLabel": CHECK_KO.get(status, "확인 결과를 읽지 못했어요"),
    }


def _sft_prompt(char_dir: Path, rev_dir: Path | None) -> dict[str, Any] | None:
    """학습 모델 조건이 평가에 쓰는 system(D-0139). 사전 등록 전이면 None."""
    prereg = _dict(_json(rev_dir / "prereg.json")) if rev_dir else {}
    arm = next((a for a in prereg.get("arms") or [] if _dict(a).get("armId") != "LONG_BASE"), None)
    ref = _dict(_dict(arm).get("promptRef")).get("ref") if arm else None
    if not isinstance(ref, str):
        return None
    path = char_dir / ref
    text = path.read_text("utf-8") if path.is_file() else ""
    if "/prompts/sft-system-" in ref:
        rel = ref.rsplit("-", 1)[-1].removesuffix(".md").upper()
        return {"kind": "training", "chars": len(text), "relationship": rel}
    return {"kind": "legacy", "chars": len(text)}


def model_path(
    char_dir: Path, state: dict[str, Any], now: datetime | None = None
) -> dict[str, Any]:
    """GET /api/characters/{id}/model-path와 캐릭터 상세의 modelPath."""
    from character_factory_poc.pipeline.graph import BIND_EXISTING
    from character_factory_poc.pipeline.origin import read_model_mode

    try:
        mode = read_model_mode(char_dir)
    except Exception:
        mode = None
    dataset = dataset_view(char_dir, state)
    return {
        "mode": mode,
        "material": material_view(dataset),
        "dataset": dataset,
        "training": training_view(char_dir, state, now),
        "eval": eval_view(char_dir, state),
        "binding": binding_view(char_dir) if mode == BIND_EXISTING else None,
    }
