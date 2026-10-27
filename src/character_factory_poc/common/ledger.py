"""원장 (명세 §12, LLD §5.18). calls.jsonl, human-time.jsonl에 한 줄씩 덧붙인다."""

from __future__ import annotations

import fcntl
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _append(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(line)
        fcntl.flock(f, fcntl.LOCK_UN)


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    """원장과 같은 방식(파일 잠금 덧붙이기)으로 JSON 한 줄을 남긴다."""
    _append(Path(path), row)


class Ledger:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.calls_path = self.folder / "calls.jsonl"
        self.human_path = self.folder / "human-time.jsonl"

    def record_call(
        self,
        *,
        stage: str,
        kind: str,
        provider: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        ms: int,
        ok: bool,
        ref: str,
        est_cost_usd: float | None = None,
        images: int = 0,
        seconds: float = 0.0,
    ) -> str:
        call_id = uuid.uuid4().hex[:12]
        _append(
            self.calls_path,
            {
                "callId": call_id,
                "at": _now(),
                "stage": stage,
                "kind": kind,
                "provider": provider,
                "model": model,
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "images": images,
                "seconds": seconds,
                "ms": ms,
                "ok": ok,
                "estCostUsd": est_cost_usd,
                "ref": ref,
            },
        )
        return call_id

    def record_human(self, *, gate: str, minutes: float, ref: str) -> None:
        _append(self.human_path, {"at": _now(), "gate": gate, "minutes": minutes, "ref": ref})

    def calls(self) -> list[dict[str, Any]]:
        if not self.calls_path.exists():
            return []
        return [json.loads(ln) for ln in self.calls_path.read_text("utf-8").splitlines() if ln]

    def human(self) -> list[dict[str, Any]]:
        if not self.human_path.exists():
            return []
        return [json.loads(ln) for ln in self.human_path.read_text("utf-8").splitlines() if ln]

    def report(self) -> dict[str, Any]:
        calls = self.calls()
        by_stage: dict[str, dict[str, Any]] = {}
        for c in calls:
            s = by_stage.setdefault(
                c["stage"], {"calls": 0, "inputTokens": 0, "outputTokens": 0, "estCostUsd": 0.0}
            )
            s["calls"] += 1
            s["inputTokens"] += c.get("inputTokens") or 0
            s["outputTokens"] += c.get("outputTokens") or 0
            s["estCostUsd"] += c.get("estCostUsd") or 0.0
        human = self.human()
        gates = sorted({h["gate"] for h in human})
        return {
            "totalCalls": len(calls),
            "byStage": by_stage,
            "humanMinutes": sum(h["minutes"] for h in human),
            "humanByGate": {g: sum(h["minutes"] for h in human if h["gate"] == g) for g in gates},
        }
