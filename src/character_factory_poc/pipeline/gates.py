"""관문 기록과 검토 페이지 (명세 §7, LLD §6.4)."""

from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.schema import dump, validate
from character_factory_poc.common.store import write_once_json
from character_factory_poc.contracts.common import GateRecord
from character_factory_poc.pipeline.state import StateFile


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def record_path(char_dir: Path, gate: str, rev: str) -> Path:
    return char_dir / "gates" / f"{gate}-{rev}.json"


def write_gate_record(
    char_dir: Path,
    state: StateFile,
    *,
    gate: str,
    rev: str,
    stage_id: str,
    shown: list[Path],
    decision: str,
    reviewer: str,
    reasons: str = "",
    selections: list[str] | None = None,
    requested_changes: list[dict[str, str]] | None = None,
    minutes: float = 0.0,
) -> GateRecord:
    rec = GateRecord(
        subjectId=state.state.subjectId,
        gate=gate,
        rev=rev,
        shownArtifacts=[
            {"ref": p.relative_to(char_dir).as_posix(), "sha256": sha256_file(p)} for p in shown
        ],
        decision=decision,  # type: ignore[arg-type]
        selections=selections or [],
        reasons=reasons,
        requestedChanges=requested_changes or [],
        reviewer=reviewer,
        minutes=minutes,
        decidedAt=now_iso(),
    )
    p = record_path(char_dir, gate, rev)
    write_once_json(p, dump(rec))
    approved = decision in {"APPROVE", "SELECT"}
    state.set_gate(
        gate, "APPROVED" if approved else "REJECTED", rev, p.relative_to(char_dir).as_posix()
    )
    if state.stage(stage_id).status == "AWAITING_HUMAN":
        state.transition(stage_id, "APPROVED" if approved else "REJECTED", rev=rev)
    return rec


def parse_answer(path: Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text("utf-8"))
    # 최소 필드만 요구한다. 나머지는 write_gate_record가 채운다.
    for k in ("decision", "reviewer"):
        if k not in obj:
            raise ValueError(f"답 파일에 {k}가 없다")
    return obj


def _esc(s: str) -> str:
    return html.escape(s, quote=False)


def render_gate_page(
    *,
    title: str,
    subject_id: str,
    gate: str,
    rev: str,
    sections: list[tuple[str, str]],
    side_by_side: list[tuple[str, str, str]] | None = None,
) -> str:
    """정적 HTML 한 장. 결정을 gate-record 답 JSON으로 복사하게 한다. 네트워크 요청 없음."""
    parts = [
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
        f"<title>{_esc(title)}</title>",
        "<style>body{font-family:-apple-system,system-ui,sans-serif;max-width:1100px;margin:2rem auto;"
        "padding:0 1rem;line-height:1.5;color:#222}pre{white-space:pre-wrap;background:#f6f6f6;"
        "padding:1rem;border-radius:6px}h2{margin-top:2rem;border-bottom:1px solid #ddd}"
        ".cols{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.col{background:#fafafa;"
        "padding:.75rem;border-radius:6px}textarea{width:100%;min-height:5rem}"
        "label{display:block;margin:.5rem 0}.hint{color:#666;font-size:.9em}</style></head><body>",
        f"<h1>{_esc(title)}</h1>",
        f'<p class="hint">subject {_esc(subject_id)} · {_esc(gate)} · {_esc(rev)}</p>',
    ]
    for name, body in sections:
        parts.append(f"<h2>{_esc(name)}</h2><pre>{_esc(body)}</pre>")
    if side_by_side:
        parts.append("<h2>말투 확인 문장 (긴 프롬프트 / 짧은 프롬프트)</h2>")
        for sentence, left, right in side_by_side:
            parts.append(
                f'<p><b>{_esc(sentence)}</b></p><div class="cols"><div class="col">'
                f'<pre>{_esc(left)}</pre></div><div class="col"><pre>{_esc(right)}</pre></div></div>'
            )
    parts.append(
        "<h2>결정</h2>"
        '<label>결정 <select id="decision"><option>APPROVE</option><option>REQUEST_CHANGES</option>'
        "<option>REJECT</option></select></label>"
        '<label>검토자 <input id="reviewer" value="user"></label>'
        '<label>소요 분 <input id="minutes" type="number" value="0"></label>'
        '<label>사유·수정 요청 <textarea id="reasons"></textarea></label>'
        '<button onclick="copyAnswer()">답 JSON 복사</button> '
        '<span class="hint">복사한 JSON을 answer.json으로 저장하고 '
        f"<code>cfp gate import {_esc(subject_id)} {_esc(gate)} --answer answer.json</code>을 실행한다.</span>"
        '<pre id="out"></pre>'
        "<script>function copyAnswer(){const o={decision:document.getElementById('decision').value,"
        "reviewer:document.getElementById('reviewer').value,minutes:Number(document.getElementById('minutes').value),"
        "reasons:document.getElementById('reasons').value};const t=JSON.stringify(o,null,2);"
        "document.getElementById('out').textContent=t;if(navigator.clipboard){navigator.clipboard.writeText(t);}}"
        "</script></body></html>"
    )
    return "".join(parts)


def validate_record(obj: dict[str, Any]) -> GateRecord:
    return validate("gate-record-v1", obj)  # type: ignore[return-value]
