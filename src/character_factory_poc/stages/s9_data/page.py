"""G7a·G7 정적 검토 페이지 (LLD §6.4·§8.8). 네트워크 요청 없이 HTML 한 장."""

from __future__ import annotations

import json
from html import escape
from typing import Any

from character_factory_poc.contracts.dataset import (
    ClusterPlan,
    Conversation,
    DataHandoff,
    DatasetRev,
)

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


def _src(source: str) -> str:
    """정책 출처 표시. proposal은 운영 시작값이라고 그대로 드러낸다."""
    if source == "proposal":
        return "운영 시작값(proposal)"
    if not source:
        return "미정"
    return f'<span class="hint">{_e(source)}</span>'


def _num(value: Any, digits: int = 4) -> str:
    if value is None:
        return "미정"
    if isinstance(value, float):
        return f"{round(value, digits):g}"
    return _e(value)


def _share_rows(shares: dict[str, Any]) -> list[str]:
    den = shares.get("denominators") or {}
    note = (shares.get("supervisedTokens") or {}).get("note", "")
    parts = [
        "<h2>클러스터 비율 (학습 분할, 세 분모)</h2>"
        f'<p class="hint">대화 {_e(den.get("conversations"))} · 답변 '
        f"{_e(den.get('replies'))} · 지도 토큰(근사) {_e(den.get('supervisedTokensApprox'))}. "
        f"{_e(note)}</p>"
        "<table><tr><th>클러스터</th><th>목표 비율</th><th>대화</th><th>답변</th>"
        "<th>지도 토큰(근사)</th><th>허용 범위</th><th>판정</th></tr>"
    ]
    for row in shares["rows"]:
        target = _num(row.get("targetShare"))
        if "targetShareSource" in row:
            target += " · " + _src(str(row.get("targetShareSource") or ""))
        guard = " · 보호" if row.get("protected") else ""
        parts.append(
            f"<tr><td>{_e(row['clusterId'])} · {_e(row.get('label', ''))}{guard}</td>"
            f"<td>{target}</td>"
            f"<td>{_e(row['conversations'])} ({_num(row.get('conversationShare'))})</td>"
            f"<td>{_e(row['replies'])} ({_num(row.get('replyShare'))})</td>"
            f"<td>{_e(row['supervisedTokensApprox'])} "
            f"({_num(row.get('supervisedTokenShareApprox'))})</td>"
            f"<td>{_num(row.get('minShare'))}~{_num(row.get('maxShare'))}</td>"
            f"<td>{_e(row.get('verdict', '판정 없음'))}</td></tr>"
        )
    parts.append("</table>")
    return parts


def _turn_rows(turns: dict[str, Any]) -> list[str]:
    parts = [
        "<h2>턴 분포 (학습 분할)</h2>"
        f'<p class="hint">단위 {_e(turns.get("unit"))} · 학습 대화 '
        f"{_e(turns.get('conversations'))} · 구간 밖 {_e(turns.get('outsideBands'))} · "
        f"{_e(turns.get('rule'))}</p>"
        "<table><tr><th>항목</th><th>관측</th><th>목표 범위</th><th>판정</th><th>출처</th></tr>"
    ]
    for row in turns["rows"]:
        observed = _num(row.get("observed"))
        if row.get("count") is not None:
            observed += f" ({_e(row['count'])}대화)"
        if row.get("approximate"):
            observed += " · 근사"
        sources = sorted({str(row.get("minSource") or ""), str(row.get("maxSource") or "")})
        parts.append(
            f"<tr><td>{_e(row['key'])}</td><td>{observed}</td>"
            f"<td>{_num(row.get('min'))}~{_num(row.get('max'))}</td>"
            f"<td>{_e(row['verdict'])}</td>"
            f"<td>{' · '.join(_src(s) for s in sources)}</td></tr>"
        )
    parts.append("</table>")
    return parts


def _protected_rows(rows: list[dict[str, Any]]) -> list[str]:
    parts = [
        "<h2>보호 클러스터 생존</h2><table><tr><th>클러스터</th><th>학습 목표</th>"
        "<th>분할 전</th><th>학습 분할</th><th>최소</th><th>판정</th></tr>"
    ]
    for row in rows:
        parts.append(
            f"<tr><td>{_e(row['clusterId'])}</td><td>{_e(row['targetTrain'])}</td>"
            f"<td>{_e(row['writtenBeforeSplit'])}</td><td>{_e(row['trainAfterSplit'])}</td>"
            f"<td>{_e(row['minimumTrain'])} ({_num(row.get('minRatio'))}배)</td>"
            f"<td>{_e(row['verdict'])}</td></tr>"
        )
    parts.append("</table>")
    parts.append(f'<p class="hint">최소 비율 출처 · {_src(str(rows[0]["minRatioSource"]))}</p>')
    return parts


def _policy_sections(view: dict[str, Any]) -> list[str]:
    """G7 페이지의 정책 절: 정책 기록, 세 분모 비율, 턴 분포, 보호 클러스터, 경고."""
    parts: list[str] = []
    pol = view.get("policy")
    if pol:
        parts.append(
            f"<h2>정책</h2><p>{_e(pol.get('name'))} · 상태 {_e(pol.get('status'))} · "
            f"정책 sha256 {_e(str(pol.get('policySha256', ''))[:12])}…</p>"
        )
        parts.extend(f'<p class="hint">{_e(n)}</p>' for n in pol.get("notes") or [])
        proposals = pol.get("proposalValues") or []
        if proposals:
            parts.append(
                "<p><b>운영 시작값(proposal)</b> · " + ", ".join(_e(p) for p in proposals) + "</p>"
            )
    shares = view.get("clusterShares") or {}
    if shares.get("rows"):
        parts.extend(_share_rows(shares))
    if not pol:
        return parts
    turns = pol.get("turnDistribution") or {}
    if turns.get("rows"):
        parts.extend(_turn_rows(turns))
    if pol.get("protectedClusters"):
        parts.extend(_protected_rows(pol["protectedClusters"]))
    warnings = pol.get("warnings") or []
    if warnings:
        parts.append("<h2>정책 경고</h2><ul>")
        parts.extend(f"<li>{_e(w)}</li>" for w in warnings)
        parts.append("</ul>")
    return parts


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
        "<code>cfp gate import &lt;id&gt; G7a --answer answer.json</code>으로 넣습니다.</p>"
    )
    with_policy = any(row.get("policy") for row in plan_rows)
    head = "<th>비율</th><th>보호</th>" if with_policy else ""
    parts.append(
        f"<table><tr><th>클러스터</th>{head}<th>목표 대화</th><th>샘플</th><th>페이지</th></tr>"
    )
    for row in plan_rows:
        cid = str(row["clusterId"])
        href = pages.get(cid, "")
        link = f'<a href="{_e(href)}">열기</a>' if href else "없음"
        extra = ""
        if with_policy:
            pol = row.get("policy") or {}
            extra = (
                f"<td>{_num(row.get('share'))} · {_src(str(pol.get('shareSource') or ''))}</td>"
                f"<td>{'보호' if pol.get('protected') else '-'}</td>"
            )
        parts.append(
            f"<tr><td>{_e(cid)} · {_e(row['label'])}</td>{extra}"
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
    if cluster.policy is not None:
        pol = cluster.policy
        parts.append(
            f"<p>{_e(cluster.label)} · 목표 비율 {_num(cluster.share)} · {_src(pol.shareSource)}"
            f"{' · 보호 클러스터' if pol.protected else ''}</p>"
        )
        if pol.description:
            parts.append(f'<p class="hint">정책 설명 · {_e(pol.description)}</p>')
        if pol.turnRule is not None:
            rule = pol.turnRule
            parts.append(
                f"<p><b>턴 조건</b> · assistant {rule.minAssistantTurns}~{rule.maxAssistantTurns}"
                f"턴 · 화제 전환 {rule.minTopicShifts}회 이상 · 대화 "
                f"{round(rule.lateTriggerFrom * 100)}% 이후 계기 상황 {rule.minLateTriggers}개 "
                "이상. 턴 수와 위치 표시는 기계 검사가 막고, 화제 전환·계기 상황이 내용에 실제로 "
                "있는지는 이 페이지에서 사람이 본다.</p>"
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
            f"{_e(conv.skeletonId)} · assistant "
            f"{sum(1 for m in conv.messages if m.role == 'assistant')}턴</p>"
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
    policy_view: dict[str, Any] | None = None,
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
    if policy_view:
        parts.extend(_policy_sections(policy_view))
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
