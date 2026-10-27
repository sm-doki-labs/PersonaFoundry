"""G7a·G7 정적 검토 페이지 (LLD §6.4·§8.8). 네트워크 요청 없이 HTML 한 장."""

from __future__ import annotations

import json
from html import escape
from typing import Any

from acf.contracts.dataset import ClusterPlan, Conversation, DataHandoff, DatasetRev

_STYLE = (
    "body{font-family:-apple-system,system-ui,sans-serif;max-width:1100px;margin:2rem auto;"
    "padding:0 1rem;line-height:1.6;color:#222;background:#fff}"
    "*{box-sizing:border-box}h2{margin-top:2rem;border-bottom:1px solid #ddd;padding-bottom:.25rem}"
    ".hint{color:#555;font-size:.9rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;"
    "background:#f6f6f6;padding:1rem;border-radius:6px}"
    ".conv{background:#fafafa;border:1px solid #e3e3e3;border-radius:6px;padding:.75rem 1rem;"
    "margin:0 0 1rem}.turn{margin:.25rem 0}.role{font-weight:600}.user{color:#14534d}"
    ".assistant{color:#7a3b00}label{display:block;margin:.5rem 0}"
    "select,textarea,input,button{font:inherit}textarea{width:100%;min-height:3.5rem}"
    "button{cursor:pointer;padding:.5rem 1rem;min-height:44px}"
    "table{border-collapse:collapse}"
    "td,th{border:1px solid #ddd;padding:.25rem .5rem;text-align:right}"
    "th:first-child,td:first-child{text-align:left}"
)


def _e(value: Any) -> str:
    return escape(str(value), quote=True)


def _head(title: str) -> list[str]:
    return [
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{_e(title)}</title><style>{_STYLE}</style></head><body>",
    ]


def _turns(conv: Conversation) -> list[str]:
    out = []
    for m in conv.messages:
        out.append(
            f'<p class="turn {_e(m.role)}"><span class="role">{_e(m.role)}</span> · '
            f'<span class="content">{_e(m.content).replace(chr(10), "<br>")}</span></p>'
        )
    return out


def render_g7a_index(
    *,
    subject_id: str,
    rev: str,
    plan_rows: list[dict[str, Any]],
    pages: dict[str, str],
) -> str:
    parts = _head(f"G7a 샘플 검토 · {subject_id} · {rev}")
    parts.append(f'<main><h1>G7a 샘플 검토</h1><p class="hint">{_e(subject_id)} · {_e(rev)}</p>')
    parts.append(
        "<p>클러스터마다 인계안과 샘플 전문을 봅니다. 대화마다 ADOPT·FIX·REJECT와 고칠 점을 "
        "적고, 클러스터 결정(SELECT 또는 REQUEST_CHANGES)을 답 JSON으로 복사해 "
        "<code>acf gate import &lt;id&gt; G7a --answer answer.json</code>으로 넣습니다.</p>"
    )
    parts.append("<table><tr><th>클러스터</th><th>목표 대화</th><th>샘플</th><th>페이지</th></tr>")
    for row in plan_rows:
        cid = str(row["clusterId"])
        href = pages.get(cid, "")
        link = f'<a href="{_e(href)}">열기</a>' if href else "없음"
        parts.append(
            f"<tr><td>{_e(cid)} · {_e(row['label'])}</td>"
            f"<td>{_e(row['targetConversations'])}</td><td>{_e(row['sampleSize'])}</td>"
            f"<td>{link}</td></tr>"
        )
    parts.append("</table></main></body></html>")
    return "".join(parts)


def render_g7a_cluster(
    *,
    subject_id: str,
    rev: str,
    cluster: ClusterPlan,
    handoff: DataHandoff,
    conversations: list[Conversation],
    sample_sha: str,
) -> str:
    cid = cluster.clusterId
    parts = _head(f"G7a {cid} · {subject_id} · {rev}")
    parts.append(
        f"<main><h1>{_e(cid)} 샘플 검토</h1>"
        f'<p class="hint">{_e(subject_id)} · {_e(rev)} · 목표 {cluster.targetConversations}대화 · '
        f"샘플 {len(conversations)}개 · 인계안 {_e(handoff.clusterId)}</p>"
    )
    parts.append("<h2>인계안</h2>")
    parts.append(
        "<table><tr><th>상황</th><th>먼저 보는 것</th><th>고르는 행동</th><th>말투</th></tr>"
    )
    for row in handoff.behaviorTable:
        parts.append(
            f"<tr><td>{_e(row.situation)}</td><td>{_e(row.attention)}</td>"
            f"<td>{_e(row.choice)}</td><td>{_e(row.voice)}</td></tr>"
        )
    parts.append("</table>")
    if handoff.voiceExamples:
        parts.append("<p><b>말투 예시</b></p><ul>")
        parts.extend(f"<li>{_e(v)}</li>" for v in handoff.voiceExamples)
        parts.append("</ul>")
    if handoff.forbidden:
        parts.append("<p><b>금지 패턴</b></p><ul>")
        parts.extend(f"<li>{_e(v)}</li>" for v in handoff.forbidden)
        parts.append("</ul>")
    if handoff.notes:
        parts.append(f"<p><b>메모</b> · {_e(handoff.notes)}</p>")
    parts.append("<h2>샘플 전문</h2>")
    for i, conv in enumerate(conversations, start=1):
        parts.append(
            f'<section class="conv" data-conv="{_e(conv.conversationId)}">'
            f"<p><b>{i}. {_e(conv.conversationId)}</b> · {_e(conv.material)} · "
            f"{_e(conv.skeletonId)}</p>"
            f'<p class="hint">system · {_e(conv.system).replace(chr(10), "<br>")}</p>'
        )
        parts.extend(_turns(conv))
        parts.append(
            "<label>판정 <select>"
            "<option>ADOPT</option><option>FIX</option><option>REJECT</option>"
            "</select></label>"
            '<label>고칠 점 <textarea placeholder="없으면 비워 둔다"></textarea></label>'
            "</section>"
        )
    parts.append(
        "<h2>결정</h2>"
        f'<p class="hint">샘플 묶음 {_e(sample_sha[:16])}…</p>'
        '<label>클러스터 결정 <select id="decision"><option>SELECT</option>'
        "<option>REQUEST_CHANGES</option></select></label>"
        '<label>검토자 <input id="reviewer" value="user"></label>'
        '<label>소요 분 <input id="minutes" type="number" value="0"></label>'
        '<button onclick="buildAnswer()">답 JSON 복사</button>'
        '<pre id="out"></pre>'
        "<script>const CLUSTER=" + json.dumps(cid) + ";"
        "function buildAnswer(){const verdicts={},notes={};"
        "document.querySelectorAll('[data-conv]').forEach(el=>{const id=el.dataset.conv;"
        "verdicts[id]=el.querySelector('select').value;"
        "const n=el.querySelector('textarea').value.trim();if(n){notes[id]=n;}});"
        "const o={decision:document.getElementById('decision').value,cluster:CLUSTER,"
        "verdicts:verdicts,notes:notes,"
        "reviewer:document.getElementById('reviewer').value,"
        "minutes:Number(document.getElementById('minutes').value)};"
        "const t=JSON.stringify(o,null,2);document.getElementById('out').textContent=t;"
        "if(navigator.clipboard){navigator.clipboard.writeText(t);}}</script></main>"
        "</body></html>"
    )
    return "".join(parts)


def render_g7_page(
    *,
    subject_id: str,
    dataset: DatasetRev,
    report: dict[str, Any],
    counts: list[dict[str, Any]],
    samples: list[Conversation],
) -> str:
    parts = _head(f"G7 데이터셋 승인 · {subject_id} · {dataset.datasetRev}")
    parts.append(
        f"<main><h1>G7 데이터셋 승인</h1>"
        f'<p class="hint">{_e(subject_id)} · {_e(dataset.datasetRev)} · '
        f"계획 {_e(dataset.planSha256[:12])}… · 데이터셋 digest {_e(dataset.digest[:12])}…</p>"
    )
    parts.append(
        f"<p>학습 {sum(1 for f in dataset.files if f.split == 'train')}파일 · "
        f"차단 실패 {dataset.blockingFailures} · 경고 {dataset.warnings} · "
        "승인하면 이 revision을 고정한다.</p>"
    )
    parts.append("<h2>분할 파일</h2><table><tr><th>split</th><th>경로</th><th>대화</th></tr>")
    for f in dataset.files:
        parts.append(
            f"<tr><td>{_e(f.split)}</td><td>{_e(f.path)}</td><td>{f.conversations}</td></tr>"
        )
    parts.append("</table>")
    parts.append(
        "<h2>클러스터별 수</h2><table><tr><th>클러스터</th><th>대화</th><th>답변</th>"
        "<th>토큰(근사)</th></tr>"
    )
    for row in counts:
        tokens = row.get("supervisedTokens")
        parts.append(
            f"<tr><td>{_e(row['clusterId'])}</td><td>{_e(row['conversations'])}</td>"
            f"<td>{_e(row['replies'])}</td><td>{'근사 없음' if tokens is None else tokens}</td>"
            "</tr>"
        )
    parts.append("</table>")
    parts.append("<h2>검사 보고서</h2>")
    parts.append(f"<pre>{_e(json.dumps(report, ensure_ascii=False, indent=2))}</pre>")
    parts.append("<h2>무작위 표본 20개</h2>")
    for i, conv in enumerate(samples, start=1):
        parts.append(
            f'<section class="conv" data-conv="{_e(conv.conversationId)}">'
            f"<p><b>{i}. {_e(conv.conversationId)}</b> · {_e(conv.clusterId)} · "
            f"{_e(conv.material)}</p>"
            f'<p class="hint">system · {_e(conv.system).replace(chr(10), "<br>")}</p>'
        )
        parts.extend(_turns(conv))
        parts.append(
            "<label>판정 <select><option>ADOPT</option><option>FIX</option>"
            "<option>REJECT</option></select></label></section>"
        )
    parts.append(
        "<h2>결정</h2>"
        '<label>결정 <select id="decision"><option>APPROVE</option>'
        "<option>REQUEST_CHANGES</option></select></label>"
        '<label>검토자 <input id="reviewer" value="user"></label>'
        '<label>소요 분 <input id="minutes" type="number" value="0"></label>'
        '<button onclick="buildAnswer()">답 JSON 복사</button><pre id="out"></pre>'
        "<script>function buildAnswer(){const verdicts={};"
        "document.querySelectorAll('[data-conv]').forEach(el=>{"
        "verdicts[el.dataset.conv]=el.querySelector('select').value;});"
        "const o={decision:document.getElementById('decision').value,verdicts:verdicts,"
        "reviewer:document.getElementById('reviewer').value,"
        "minutes:Number(document.getElementById('minutes').value)};"
        "const t=JSON.stringify(o,null,2);document.getElementById('out').textContent=t;"
        "if(navigator.clipboard){navigator.clipboard.writeText(t);}}</script></main>"
        "</body></html>"
    )
    return "".join(parts)
