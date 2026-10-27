"""G2 검토 페이지 (명세 §7, LLD §8.2). 정적 HTML 한 장, 네트워크 요청 없음."""

from __future__ import annotations

import html
from typing import Any

from acf.contracts.hero import HeroCandidate, HeroInputs
from acf.stages.s1_reference.page import ORIGIN_KO, summary, tag_label


def _e(s: Any) -> str:
    return html.escape(str(s), quote=True)


def render_g2_page(
    *,
    subject_id: str,
    rev: str,
    inputs: HeroInputs,
    candidates: list[HeroCandidate],
    vocab: dict[str, Any],
) -> str:
    s = inputs.scope
    refs = (
        "".join(
            f'<figure><img src="{_e(r.path)}" alt="{_e(r.id)}"><figcaption>{_e(r.id)}</figcaption></figure>'
            for r in inputs.referencePreviews
        )
        or '<p class="hint">참조 사진 없음(외모군 특징만으로 생성)</p>'
    )
    cards = "".join(
        f'<label class="card"><img src="{_e(c.filePath)}" alt="{_e(c.candidateId)}" title="{_e(c.prompt)}">'
        f'<br><input type="radio" name="pick" value="{_e(c.candidateId)}"> <b>{_e(c.candidateId)}</b> '
        f'<span class="hint">{_e(c.provider)} · {_e(c.model)}</span></label>'
        for c in candidates
    )
    tags = "".join(f"<li>{_e(tag_label(f, v, vocab))}</li>" for f, v in inputs.commonTags.items())
    return "".join(
        [
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            f"<title>G2 대표 이미지 선택 · {_e(subject_id)} · {_e(rev)}</title>",
            "<style>body{font-family:-apple-system,system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#222}"
            "h2{margin-top:2rem;border-bottom:1px solid #ddd}.grid{display:flex;gap:1rem;flex-wrap:wrap}"
            ".card{display:inline-block;border:1px solid #ddd;border-radius:8px;padding:.5rem}.card img{width:360px;height:360px;object-fit:cover;border-radius:6px;background:#eee}"
            "figure{display:inline-block;margin:0 1rem 0 0}figure img{width:200px;height:200px;object-fit:cover;border-radius:6px}"
            ".hint{color:#666;font-size:.9em}pre{white-space:pre-wrap;background:#f6f6f6;padding:1rem;border-radius:6px}"
            "label{margin:.5rem 0}textarea{width:100%;min-height:4rem}</style></head><body>",
            "<h1>G2 대표 이미지 선택</h1>",
            f'<p class="hint">{_e(subject_id)} · {_e(rev)} · 외모군 {_e(inputs.clusterId)}({_e(inputs.sourceReferenceRev)}) · '
            f"{_e(s.characterGender)}, {_e(s.ageRange)}, {_e(s.artStyle)}, 인물 인상 {_e(ORIGIN_KO[s.appearanceOrigin])}</p>",
            '<p class="hint">고른 한 장이 이 캐릭터의 기준 얼굴이 된다. 이후 챕터 프레임과 영상은 이 얼굴을 참조한다.</p>',
            f"<h2>외모군 특징</h2><p>{_e(summary(inputs.commonTags, vocab))}</p><ul>{tags}</ul>",
            f'<h2>G1에서 고른 참조 사진</h2><div class="grid">{refs}</div>',
            f'<h2>후보</h2><div class="grid">{cards}</div>',
            "<h2>결정</h2>"
            '<label>결정 <select id="decision"><option>SELECT</option><option>REQUEST_CHANGES</option><option>REJECT</option></select></label><br>'
            '<label>검토자 <input id="reviewer" value="user"></label><br>'
            '<label>소요 분 <input id="minutes" type="number" value="0"></label><br>'
            '<label>메모·수정 요청 <textarea id="reasons"></textarea></label><br>'
            '<button onclick="copyAnswer()">답 JSON 복사</button> '
            '<span class="hint">복사한 JSON을 answer.json으로 저장하고 '
            f"<code>acf gate import {_e(subject_id)} G2 --answer answer.json</code>을 실행한다.</span>"
            '<pre id="out"></pre>'
            "<script>function copyAnswer(){const d=document.getElementById('decision').value;"
            "const p=document.querySelector('input[name=pick]:checked');"
            "const o={decision:d,selections:(d==='SELECT'&&p)?[p.value]:[],reviewer:document.getElementById('reviewer').value,"
            "minutes:Number(document.getElementById('minutes').value),reasons:document.getElementById('reasons').value};"
            "const t=JSON.stringify(o,null,2);document.getElementById('out').textContent=t;"
            "if(navigator.clipboard){navigator.clipboard.writeText(t);}}</script></body></html>",
        ]
    )
