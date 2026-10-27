"""G8 정적 검토 페이지 (LLD §6.4·§8.9).

지표·기준·LLM 짝 판정과 사람 블라인드 20쌍을 한 장에 보여 주고, 답 JSON을 복사하게 한다.
사람 표본에는 어느 조건인지 쓰지 않는다.
"""

from __future__ import annotations

from html import escape
from typing import Any

from acf.contracts.training import EvalPrereg, EvalReport
from acf.stages.s10_eval.metrics import criteria_overall


def _e(value: Any) -> str:
    return escape(str(value), quote=True)


def _metric_value(report: EvalReport, arm: str, metric: str) -> float | None:
    for row in report.metrics:
        if row.armId == arm and row.metric == metric:
            return row.value
    return None


def _metric_detail(report: EvalReport, arm: str, metric: str) -> str:
    for row in report.metrics:
        if row.armId == arm and row.metric == metric:
            return row.detail
    return ""


def render_g8_page(
    *,
    subject_id: str,
    rev: str,
    prereg: EvalPrereg,
    report: EvalReport,
    pairs: dict[str, Any],
    final: bool = False,
    adopted: str | None = None,
) -> str:
    overall = criteria_overall(prereg, report.criteriaResults)
    picks = {p.pairId: p.pick for p in report.humanPicks}
    pair_by_id = {p["pairId"]: p for p in pairs.get("pairs", [])}
    arms = [a.armId for a in prereg.arms]
    parts = [
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>G8 평가 · {_e(subject_id)} · {_e(rev)}</title>",
        "<style>body{font-family:-apple-system,system-ui,sans-serif;max-width:1180px;"
        "margin:2rem auto;padding:0 1rem;line-height:1.6;color:#1d1d1f;background:#fff}"
        "*{box-sizing:border-box}h2{margin-top:2.4rem;border-bottom:1px solid #d8d8dc;"
        "padding-bottom:.35rem}table{border-collapse:collapse;width:100%;font-size:.92rem}"
        "th,td{border:1px solid #d8d8dc;padding:.45rem .55rem;text-align:left;vertical-align:top}"
        "th{background:#f5f5f7}.num{font-variant-numeric:tabular-nums;text-align:right}"
        ".pass{color:#0b6b3a;font-weight:600}.fail{color:#a3221a;font-weight:600}"
        ".hint{color:#555;font-size:.9rem}.badge{display:inline-block;border-radius:999px;"
        "padding:.1rem .55rem;font-size:.8rem;border:1px solid currentColor}"
        ".pair{border:1px solid #d8d8dc;border-radius:10px;padding:.8rem 1rem;margin:0 0 1rem}"
        ".cols{display:grid;grid-template-columns:1fr 1fr;gap:.8rem}.col{background:#fafafa;"
        "border-radius:8px;padding:.7rem;white-space:pre-wrap}"
        "label{display:inline-flex;gap:.35rem;align-items:center;margin-right:1rem;min-height:44px}"
        "select,input,button,textarea{font:inherit;min-height:44px}"
        "button{cursor:pointer;padding:.45rem 1rem}:focus-visible{outline:3px solid #176e63;"
        "outline-offset:3px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f5f7;"
        "padding:1rem;border-radius:8px}@media(max-width:700px){.cols{grid-template-columns:1fr}}"
        "</style></head><body><main>",
        f"<h1>G8 평가 보고서</h1><p class="
        "hint"
        ">{_e(subject_id)} · {_e(rev)} · "
        f"prereg {_e(report.preregSha256[:12])}… · 판정 {_e(prereg.judge.model)}"
        f"({_e(prereg.judge.family)})</p>",
    ]

    parts.append(
        "<h2>기준</h2><table><tr><th>기준</th><th>지표</th><th>비교</th>"
        "<th>적용</th><th>전체</th></tr>"
    )
    for criterion in prereg.criteria:
        ok = overall.get(criterion.id, False)
        cls = "pass" if ok else "fail"
        mark = "통과" if ok else "미달"
        parts.append(
            f"<tr><td>{_e(criterion.id)}</td><td>{_e(criterion.metric)}</td>"
            f"<td>{_e(criterion.comparator)} {_e(criterion.threshold)}</td>"
            f"<td>{_e(criterion.appliesTo)}</td>"
            f'<td class="{cls}">{mark}</td></tr>'
        )
    parts.append(
        '</table><p class="hint">SFT_ANY는 SFT 조건 가운데 하나라도 기준을 '
        "넘으면 통과로 본다. 미달이어도 보고서는 나오고 채택은 사람이 정한다.</p>"
    )

    parts.append(
        '<h2>지표</h2><table><tr><th>조건</th><th>지표</th><th class="num">값</th>'
        "<th>기준 결과</th><th>근거</th></tr>"
    )
    result_by = {(r.id, r.armId): r for r in report.criteriaResults}
    for arm in arms:
        for criterion in prereg.criteria:
            value = _metric_value(report, arm, criterion.metric)
            row = result_by.get((criterion.id, arm))
            verdict = "—"
            if row is not None:
                verdict = "통과" if row.passed else "미달"
            parts.append(
                f"<tr><td>{_e(arm)}</td><td>{_e(criterion.metric)}</td>"
                f'<td class="num">{_e(value if value is not None else "—")}</td>'
                f"<td>{_e(verdict)}</td>"
                f"<td>{_e(_metric_detail(report, arm, criterion.metric))}</td></tr>"
            )
    parts.append("</table>")

    parts.append(
        '<h2>LLM 짝 판정</h2><p class="hint">정순·역순이 같은 쪽을 가리킬 때만 '
        "합의로 센다. SPLIT은 합의 실패다.</p><table><tr><th>pair</th><th>세트</th>"
        "<th>항목</th><th>A</th><th>B</th><th>정순</th><th>역순</th>"
        "<th>합의</th></tr>"
    )
    for pair in pairs.get("pairs", []):
        parts.append(
            f"<tr><td>{_e(pair['pairId'])}</td><td>{_e(pair['setId'])}</td>"
            f"<td>{_e(pair['itemId'])}</td><td>{_e(pair['armA'])}</td>"
            f"<td>{_e(pair['armB'])}</td><td>{_e(pair['forward'])}</td>"
            f"<td>{_e(pair['reverse'])}</td><td>{_e(pair['consensus'])}</td></tr>"
        )
    parts.append("</table>")

    parts.append("<h2>사람 블라인드 20쌍</h2>")
    parts.append(
        '<p class="hint">어느 조건인지 표시하지 않는다. 더 자연스럽고 캐릭터에 맞는 답을 '
        "고른다. LLM이 정순·역순에서 합의하지 못한 쌍(SPLIT)은 일치율에서 불일치로 센다. "
        "판정은 참고용이며 G8 채택은 사람이 정한다.</p>"
    )
    for pid in pairs.get("humanPairIds", []):
        pair = pair_by_id.get(pid)
        if pair is None:
            continue
        chosen = picks.get(pid)
        parts.append(
            f'<section class="pair" data-pair="{_e(pid)}">'
            f'<p class="hint">{_e(pid)} · {_e(pair["setId"])} · {_e(pair["itemId"])}'
            f" · {_e(pair['turn'])}턴</p>"
        )
        if pair.get("history"):
            parts.append(
                f"<details><summary>고정 이력</summary><pre>{_e(pair['history'])}</pre></details>"
            )
        parts.append(
            f"<p><b>사용자</b></p><pre>{_e(pair['user'])}</pre>"
            f'<div class="cols"><div class="col"><b>A</b>\n{_e(pair["replyA"])}</div>'
            f'<div class="col"><b>B</b>\n{_e(pair["replyB"])}</div></div>'
        )
        for pick in ("A", "B", "TIE"):
            checked = " checked" if chosen == pick else ""
            parts.append(
                f'<label><input type="radio" name="pick-{_e(pid)}" value="{pick}"{checked}>'
                f" {pick}</label>"
            )
        parts.append("</section>")

    parts.append("<h2>채택</h2>")
    parts.append('<label>채택 조건 <select id="adopted">')
    for arm in prereg.arms:
        value = "LONG_BASE" if arm.armId == "LONG_BASE" else arm.model
        if arm.armId != "LONG_BASE" and value.startswith("UNBOUND:"):
            parts.append(
                f'<option value="{_e(value)}" disabled>{_e(arm.armId)} · '
                f"{_e(value)} (바인딩 없음)</option>"
            )
            continue
        selected = " selected" if adopted == value else ""
        parts.append(
            f'<option value="{_e(value)}"{selected}>{_e(arm.armId)} · {_e(value)}</option>'
        )
    parts.append("</select></label>")
    if report.llmHumanAgreement is not None:
        parts.append(
            f"<p><b>LLM·사람 일치율</b> {report.llmHumanAgreement:.3f} "
            f"({len(report.humanPicks)}쌍)</p>"
        )
    parts.extend(
        [
            '<label>검토자 <input id="reviewer" value="user"></label>',
            '<label>소요 분 <input id="minutes" type="number" min="0" '
            'step="any" value="0"></label>',
            '<label>사유·메모 <textarea id="reasons"></textarea></label>',
            '<button type="button" onclick="copyAnswer()">답 JSON 복사</button>',
            '<p class="hint">20쌍을 모두 고른 뒤 복사한다. answer.json으로 저장하고 '
            f"<code>acf gate import {_e(subject_id)} G8 --answer answer.json</code>"
            "을 실행한다.</p>",
            '<p id="status" role="status"></p>'
            '<pre id="out" tabindex="0" aria-label="답 JSON"></pre>',
            "<script>async function copyAnswer(){const picks=[];"
            "document.querySelectorAll('section[data-pair]').forEach(s=>{"
            "const c=s.querySelector('input:checked');"
            "if(c){picks.push({pairId:s.dataset.pair,pick:c.value});}});"
            "const answer={decision:'SELECT',adopted:document.getElementById('adopted').value,"
            "humanPicks:picks,reviewer:document.getElementById('reviewer').value,"
            "minutes:Number(document.getElementById('minutes').value),"
            "reasons:document.getElementById('reasons').value};"
            "const text=JSON.stringify(answer,null,2);"
            "document.getElementById('out').textContent=text;"
            "const status=document.getElementById('status');"
            "const expected=document.querySelectorAll('section[data-pair]').length;"
            "if(picks.length!==expected){status.textContent='아직 고르지 않은 쌍이 있습니다: '"
            "+(expected-picks.length)+'쌍';return;}"
            "try{await navigator.clipboard.writeText(text);"
            "status.textContent='답 JSON을 복사했습니다.';}"
            "catch{status.textContent='자동 복사가 안 되면 아래 JSON을 직접 복사해 주세요.';}}"
            "</script></main></body></html>",
        ]
    )
    if final:
        parts.insert(2, '<meta name="final" content="true">')
    return "".join(parts)
