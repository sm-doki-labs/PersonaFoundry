"""G1 검토 페이지 (LLD §8.1 page, FR-09). 정적 HTML 한 장, 네트워크 요청 없음.

구성원 이름은 사람 검토용으로만 이 페이지에 보여 준다. 이 페이지는 S2 입력이 아니다(FR-35).
"""

from __future__ import annotations

import html
from typing import Any

from acf.contracts.reference import (
    MULTI_FIELDS,
    SINGLE_FIELDS,
    RankingPeople,
    ReferencePreview,
    ReferenceReport,
)

ORIGIN_KO = {"korean": "한국인", "east-asian": "동아시아인", "unspecified": "지정 안 함"}


def _e(s: Any) -> str:
    return html.escape(str(s), quote=True)


def tag_label(field: str, value: str | list[str], vocab: dict[str, Any]) -> str:
    group = vocab["single"] if field in SINGLE_FIELDS else vocab["multi"]
    vals = value if isinstance(value, list) else [value]
    ko = [group[field]["values"].get(v, {}).get("ko", v) for v in vals]
    return f"{group[field]['label']}: {', '.join(ko)}"


def summary(common: dict[str, Any], vocab: dict[str, Any]) -> str:
    parts = []
    for field in (*SINGLE_FIELDS, *MULTI_FIELDS):
        if field in common:
            group = vocab["single"] if field in SINGLE_FIELDS else vocab["multi"]
            vals = common[field] if isinstance(common[field], list) else [common[field]]
            parts += [group[field]["values"].get(v, {}).get("ko", v) for v in vals]
    return " · ".join(parts)


def render_g1_page(
    *,
    subject_id: str,
    rev: str,
    report: ReferenceReport,
    previews: list[ReferencePreview],
    people: RankingPeople,
    vocab: dict[str, Any],
) -> str:
    by_id = {p.personId: p for p in people.people}

    def person_line(pid: str) -> str:
        p = by_id[pid]
        ranks = ", ".join(f"{a.category} {a.rank}위" for a in p.appearances)
        return f"{_e(pid)} {_e(p.name)} — {_e(ranks)}"

    rationale = {o.clusterId: o.rationale for o in report.ordering}
    out = [
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
        f"<title>G1 외모군 선택 · {_e(subject_id)} · {_e(rev)}</title>",
        "<style>body{font-family:-apple-system,system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#222}"
        "h2{margin-top:2rem;border-bottom:1px solid #ddd}.card{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}"
        ".imgs{display:flex;gap:.5rem;flex-wrap:wrap}.imgs img{width:160px;height:160px;object-fit:cover;border-radius:6px;background:#eee}"
        ".hint{color:#666;font-size:.9em}ul{margin:.25rem 0}pre{white-space:pre-wrap;background:#f6f6f6;padding:1rem;border-radius:6px}"
        "label{display:block;margin:.5rem 0}textarea{width:100%;min-height:4rem}</style></head><body>",
        "<h1>G1 외모군 선택</h1>",
        f'<p class="hint">{_e(subject_id)} · {_e(rev)} · 비교 범위: {_e(report.scope.characterGender)}, '
        f"{_e(report.scope.ageRange)}, {_e(report.scope.artStyle)}, "
        f"인물 인상 {_e(ORIGIN_KO[report.scope.appearanceOrigin])}</p>",
        '<p class="hint">구성원 이름은 검토용으로만 보여 준다. 다음 단계(S2)와 이미지 생성에는 아래 공통 특징만 넘어간다.</p>',
        "<h2>후보</h2>",
    ]
    for c in report.candidates:
        imgs = "".join(
            f'<label class="ref"><img src="{_e(p.filePath)}" alt="{_e(p.previewId)}" '
            f'title="{_e(p.prompt)}"><br><input type="checkbox" name="ref" '
            f'value="{_e(p.previewId)}"> {_e(p.previewId)} 참조로 쓰기</label>'
            for p in previews
            if p.clusterId == c.clusterId
        )
        tags = "".join(f"<li>{_e(tag_label(f, v, vocab))}</li>" for f, v in c.commonTags.items())
        lims = "".join(f"<li>{_e(x)}</li>" for x in c.limitations) or "<li>없음</li>"
        members = "".join(f"<li>{person_line(m)}</li>" for m in c.members)
        out.append(
            f'<div class="card"><label><input type="radio" name="pick" value="{_e(c.clusterId)}"> '
            f"<b>{_e(c.clusterId)}</b> · {_e(summary(c.commonTags, vocab))}</label>"
            f'<p>{_e(rationale[c.clusterId])}</p><div class="imgs">{imgs}</div>'
            f"<p><b>공통 특징</b></p><ul>{tags}</ul><p><b>한계</b></p><ul>{lims}</ul>"
            f"<details><summary>구성원 {c.memberCount}명 (검토용)</summary><ul>{members}</ul></details></div>"
        )
    if report.dropped or report.excludedPeople:
        out.append("<h2>제외</h2><ul>")
        for d in report.dropped:
            names = ", ".join(person_line(m) for m in d.members)
            out.append(f"<li>{_e(d.reason)} — {names}</li>")
        for x in report.excludedPeople:
            out.append(f"<li>{person_line(x.personId)}: {_e(x.reason)}</li>")
        out.append("</ul>")
    out.append(
        "<h2>주의점</h2><ul>" + "".join(f"<li>{_e(x)}</li>" for x in report.cautions) + "</ul>"
    )
    out.append(f'<p class="hint">{_e(report.normalization)}</p>')
    repro = report.reproducibility
    if repro.previousRev:
        out.append(
            f'<p class="hint">이전 실행 {_e(repro.previousRev)}과의 군집 일치도(ARI): '
            f"{_e(repro.agreementWithPrevious)} (비교 {repro.comparedPeople}명)</p>"
        )
    out.append(
        "<h2>결정</h2>"
        '<p class="hint">외모군 하나를 고르고, 그 외모군의 미리보기 가운데 마음에 드는 사진을 0~2장 체크한다. '
        "체크한 사진은 다음 단계(S2)에서 같은 얼굴을 유지하는 참조 이미지로 쓰인다.</p>"
        '<label>결정 <select id="decision"><option>SELECT</option><option>REQUEST_CHANGES</option><option>REJECT</option></select></label>'
        '<label>검토자 <input id="reviewer" value="user"></label>'
        '<label>소요 분 <input id="minutes" type="number" value="0"></label>'
        '<label>사유·수정 요청 <textarea id="reasons"></textarea></label>'
        '<button onclick="copyAnswer()">답 JSON 복사</button> '
        '<span class="hint">복사한 JSON을 answer.json으로 저장하고 '
        f"<code>acf gate import {_e(subject_id)} G1 --answer answer.json</code>을 실행한다.</span>"
        '<pre id="out"></pre>'
        "<script>function copyAnswer(){const d=document.getElementById('decision').value;"
        "const p=document.querySelector('input[name=pick]:checked');"
        "const r=[...document.querySelectorAll('input[name=ref]:checked')].map(x=>x.value).filter(v=>p&&v.startsWith(p.value+'-'));"
        "const o={decision:d,selections:(d==='SELECT'&&p)?[p.value]:[],referencePreviews:d==='SELECT'?r:[],reviewer:document.getElementById('reviewer').value,"
        "minutes:Number(document.getElementById('minutes').value),reasons:document.getElementById('reasons').value};"
        "const t=JSON.stringify(o,null,2);document.getElementById('out').textContent=t;"
        "if(navigator.clipboard){navigator.clipboard.writeText(t);}}</script></body></html>"
    )
    return "".join(out)
