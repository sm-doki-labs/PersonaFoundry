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
        text_binding: dict | None = None,
        cached_input_tokens: int | None = None,
        cache_write_tokens: int | None = None,
        reasoning_tokens: int | None = None,
        finish_reason: str | None = None,
        usage_source: str | None = None,
        price: dict | None = None,
        billing: dict | None = None,
        error_status: int | None = None,
    ) -> str:
        """호출 한 건을 덧붙인다. 비용 기록 필드(명세 §24.5)는 값이 있을 때만 쓴다."""
        call_id = uuid.uuid4().hex[:12]
        extra = {
            "cachedInputTokens": cached_input_tokens,
            "cacheWriteTokens": cache_write_tokens,
            "reasoningTokens": reasoning_tokens,
            "finishReason": finish_reason,
            "usageSource": usage_source,
            "price": price,
            "billing": billing,
            "errorStatus": error_status,
        }
        _append(
            self.calls_path,
            {
                **({"textBinding": text_binding} if text_binding is not None else {}),
                **{k: v for k, v in extra.items() if v is not None},
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
        from character_factory_poc.common.cost_report import counts_as_unpriced

        calls = self.calls()
        by_stage: dict[str, dict[str, Any]] = {}
        for c in calls:
            s = by_stage.setdefault(
                c["stage"],
                {
                    "calls": 0,
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "estCostUsd": 0.0,
                    "unpricedCalls": 0,
                },
            )
            s["calls"] += 1
            s["inputTokens"] += c.get("inputTokens") or 0
            s["outputTokens"] += c.get("outputTokens") or 0
            cost = c.get("estCostUsd")
            if cost is not None:
                s["estCostUsd"] += cost
            elif counts_as_unpriced(c):
                # 비용 미확인 호출은 0으로 더하지 않고 따로 센다(FR-67).
                s["unpricedCalls"] += 1
        human = self.human()
        gates = sorted({h["gate"] for h in human})
        return {
            "totalCalls": len(calls),
            "unpricedCalls": sum(s["unpricedCalls"] for s in by_stage.values()),
            "byStage": by_stage,
            "humanMinutes": sum(h["minutes"] for h in human),
            "humanByGate": {g: sum(h["minutes"] for h in human if h["gate"] == g) for g in gates},
        }
