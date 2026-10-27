"""G5 검토 페이지 (명세 §7, LLD §8.5). 소개 영상 후보를 재생하고 하나를 고른다. 네트워크 요청 없음."""

from __future__ import annotations

import html
from typing import Any

from character_factory_poc.contracts.video import IntroInputs, VideoAsset


def _e(s: Any) -> str:
    return html.escape(str(s), quote=True)


def _probe(a: VideoAsset) -> str:
    p = a.probe
    if p.durationS is None and p.width is None:
        return p.note or "실측 없음"
    return f"실측 {p.durationS}초 · {p.width}×{p.height}"


def _refs(inputs: IntroInputs) -> str:
    src = inputs.firstFrameSource
    first = f'<div class="ref"><b>첫 프레임</b><br><img src="{_e(inputs.firstFrame.path)}" alt="first frame">'
    if src.mode == "generated":
        size = "×".join(str(v) for v in src.croppedSize or [])
        first += f'<br><span class="hint">대표 이미지 참조로 새로 만듦 · {_e(src.model)} · {_e(size)}</span>'
    first += "</div>"
    hero = (
        f'<div class="ref"><b>G2 대표 이미지</b><br><img src="{_e(src.hero.path)}" alt="hero"></div>'
        if src.mode == "generated"
        else ""
    )
    return f'<div class="refs">{hero}{first}</div>'


def render_g5_page(
    *, subject_id: str, rev: str, inputs: IntroInputs, assets: list[VideoAsset]
) -> str:
    s = inputs.settings
    cards = "".join(
        f'<label class="card"><video src="{_e(a.filePath)}" controls loop muted playsinline></video>'
        f'<br><input type="radio" name="pick" value="{_e(a.candidateId)}"> <b>{_e(a.candidateId)}</b> '
        f'<span class="hint">{_e(a.provider)} · {_e(a.model)} · {_e(_probe(a))}'
        f"{' · 예상 $' + format(a.estCostUsd, '.2f') if a.estCostUsd else ''}</span></label>"
        for a in assets
    )
    return "".join(
        [
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            f"<title>G5 소개 영상 선택 · {_e(subject_id)} · {_e(rev)}</title>",
            "<style>body{font-family:-apple-system,system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;line-height:1.5;color:#222}"
            "h2{margin-top:2rem;border-bottom:1px solid #ddd}.grid{display:flex;gap:1rem;flex-wrap:wrap}"
            ".card{display:inline-block;border:1px solid #ddd;border-radius:8px;padding:.5rem}.card video{max-width:420px;max-height:640px;border-radius:6px;background:#000}"
            ".refs{display:flex;gap:1rem}.ref img{max-width:300px;max-height:420px;border-radius:6px}.hint{color:#666;font-size:.9em}"
            "pre{white-space:pre-wrap;background:#f6f6f6;padding:1rem;border-radius:6px}textarea{width:100%;min-height:4rem}</style></head><body>",
            "<h1>G5 소개 영상 선택</h1>",
            f'<p class="hint">{_e(subject_id)} · {_e(rev)} · 외모 {_e(inputs.appearanceRev)} · 기획 {_e(inputs.planRev or "-")} · '
            f"{_e(inputs.provider)} {_e(inputs.model)} · {_e(s.resolution)} · {_e(s.duration)}초 · {_e(s.aspectRatio or '입력 비율')}</p>",
            '<p class="hint">G2 대표 이미지와 같은 사람으로 자연스럽게 움직이는 영상을 고른다. 얼굴이 바뀌거나 손·몸이 어색하면 REQUEST_CHANGES로 다시 만든다(첫 프레임도 새로 만든다).</p>',
            _refs(inputs),
            f"<h2>움직임 프롬프트</h2><pre>{_e(s.prompt)}</pre>",
            f'<h2>후보</h2><div class="grid">{cards}</div>',
            "<h2>결정</h2>"
            '<label>결정 <select id="decision"><option>SELECT</option><option>REQUEST_CHANGES</option><option>REJECT</option></select></label><br>'
            '<label>검토자 <input id="reviewer" value="user"></label><br>'
            '<label>소요 분 <input id="minutes" type="number" value="0"></label><br>'
            '<label>메모·수정 요청 <textarea id="reasons"></textarea></label><br>'
            '<button onclick="copyAnswer()">답 JSON 복사</button> '
            '<span class="hint">복사한 JSON을 answer.json으로 저장하고 '
            f"<code>cfp gate import {_e(subject_id)} G5 --answer answer.json</code>을 실행한다.</span>"
            '<pre id="out"></pre>'
            "<script>function copyAnswer(){const d=document.getElementById('decision').value;"
            "const p=document.querySelector('input[name=pick]:checked');"
            "const o={decision:d,selections:(d==='SELECT'&&p)?[p.value]:[],reviewer:document.getElementById('reviewer').value,"
            "minutes:Number(document.getElementById('minutes').value),reasons:document.getElementById('reasons').value};"
            "const t=JSON.stringify(o,null,2);document.getElementById('out').textContent=t;"
            "if(navigator.clipboard){navigator.clipboard.writeText(t);}}</script></body></html>",
        ]
    )
