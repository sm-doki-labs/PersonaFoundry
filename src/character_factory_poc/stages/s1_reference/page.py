"""G1 검토 페이지 (LLD §8.1 page, FR-09, D-0042·D-0043). 정적 HTML 한 장, 네트워크 없음.

외모군마다 얼굴 한 장을 보여 주고, 정렬 1위 외모군에 추천 표시를 붙인다. 사람은 얼굴 하나를
고르고(외모군은 그 얼굴에서 정해진다) 고칠 점 메모를 쓴다. 구성원 이름은 이 페이지에만 있고
S2 입력·이미지 프롬프트로 넘어가지 않는다(FR-35).
"""

from __future__ import annotations

import html
from typing import Any

from character_factory_poc.contracts.reference import (
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
    recommended = report.ordering[0].clusterId if report.ordering else ""

    def person_line(pid: str) -> str:
        p = by_id[pid]
        ranks = ", ".join(f"{a.category} {a.rank}위" for a in p.appearances)
        return f"{_e(pid)} {_e(p.name)} — {_e(ranks)}"

    rationale = {o.clusterId: o.rationale for o in report.ordering}
    out = [
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
        f"<title>G1 얼굴 고르기 · {_e(subject_id)} · {_e(rev)}</title>",
        "<style>body{font-family:-apple-system,system-ui,sans-serif;max-width:1100px;margin:2rem auto;"
        "padding:0 1rem;line-height:1.5;color:#222}"
        "h2{margin-top:2rem;border-bottom:1px solid #ddd}.card{border:1px solid #ddd;"
        "border-radius:8px;padding:1rem;margin:1rem 0}"
        ".imgs{display:flex;gap:.5rem;flex-wrap:wrap}.imgs img{width:200px;height:200px;"
        "object-fit:cover;border-radius:6px;background:#eee}"
        ".face{display:inline-block;margin:0 1rem 1rem 0;cursor:pointer}"
        ".badge{display:inline-block;background:#e8f3ec;color:#1d6b3d;border-radius:999px;"
        "padding:0 .5rem;font-size:.85em;margin-left:.4rem}"
        ".hint{color:#666;font-size:.9em}ul{margin:.25rem 0}"
        "pre{white-space:pre-wrap;background:#f6f6f6;padding:1rem;border-radius:6px}"
        "label{display:block;margin:.5rem 0}textarea{width:100%;min-height:4rem}</style></head><body>",
        "<h1>G1 얼굴 고르기</h1>",
        f'<p class="hint">{_e(subject_id)} · {_e(rev)} · 비교 범위: '
        f"{_e(report.scope.characterGender)}, {_e(report.scope.ageRange)}, "
        f"{_e(report.scope.artStyle)}, 인물 인상 {_e(ORIGIN_KO[report.scope.appearanceOrigin])}</p>",
        '<p class="hint">외모군마다 얼굴 한 장이다. 고른 얼굴이 외모군을 정하고, S2 기준 이미지와 '
        "이후 모든 장면·영상의 얼굴 기준이 된다(D-0042). 구성원 이름은 검토용으로만 보여 준다.</p>",
        "<h2>얼굴 후보</h2>",
    ]
    for c in report.candidates:
        faces = [p for p in previews if p.clusterId == c.clusterId]
        imgs = (
            "".join(
                f'<label class="face"><img src="{_e(p.filePath)}" alt="{_e(p.previewId)}" '
                f'title="{_e(p.prompt)}"><br><input type="radio" name="face" '
                f'value="{_e(p.previewId)}" data-cluster="{_e(c.clusterId)}"> {_e(p.previewId)}</label>'
                for p in faces
            )
            or '<p class="hint">이 외모군의 얼굴 미리보기가 없다. cfp ref faces로 다시 만든다.</p>'
        )
        badge = '<span class="badge">추천</span>' if c.clusterId == recommended else ""
        tags = "".join(f"<li>{_e(tag_label(f, v, vocab))}</li>" for f, v in c.commonTags.items())
        lims = "".join(f"<li>{_e(x)}</li>" for x in c.limitations) or "<li>없음</li>"
        members = "".join(f"<li>{person_line(m)}</li>" for m in c.members)
        out.append(
            f'<div class="card"><p><b>{_e(c.clusterId)}</b>{badge} · '
            f"{_e(summary(c.commonTags, vocab))}</p>"
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
        '<p class="hint">얼굴 하나를 고른다(외모군은 그 얼굴에서 정해진다). 마음에 드는 얼굴이 '
        "없으면 REQUEST_CHANGES에 고칠 점을 적는다. 그러면 cfp ref faces가 같은 특징·군집으로 "
        "얼굴만 다시 만든다(D-0043).</p>"
        '<label>결정 <select id="decision"><option>SELECT</option><option>REQUEST_CHANGES</option>'
        "<option>REJECT</option></select></label>"
        '<label>검토자 <input id="reviewer" value="user"></label>'
        '<label>소요 분 <input id="minutes" type="number" value="0"></label>'
        '<label>고칠 점 메모(REQUEST_CHANGES) <textarea id="note"></textarea></label>'
        '<label>사유 <textarea id="reasons"></textarea></label>'
        '<button onclick="copyAnswer()">답 JSON 복사</button> '
        '<span class="hint">복사한 JSON을 answer.json으로 저장하고 '
        f"<code>cfp gate import {_e(subject_id)} G1 --answer answer.json</code>을 실행한다.</span>"
        '<pre id="out"></pre>'
        "<script>function copyAnswer(){const d=document.getElementById('decision').value;"
        "const p=document.querySelector('input[name=face]:checked');"
        "const o={decision:d,selections:(d==='SELECT'&&p)?[p.dataset.cluster]:[],"
        "referencePreviews:(d==='SELECT'&&p)?[p.value]:[],"
        "note:document.getElementById('note').value,"
        "reviewer:document.getElementById('reviewer').value,"
        "minutes:Number(document.getElementById('minutes').value),"
        "reasons:document.getElementById('reasons').value};"
        "const t=JSON.stringify(o,null,2);document.getElementById('out').textContent=t;"
        "if(navigator.clipboard){navigator.clipboard.writeText(t);}}</script></body></html>"
    )
    return "".join(out)
