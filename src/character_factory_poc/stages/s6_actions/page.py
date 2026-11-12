"""G5b 정적 검토 페이지다. 첫 프레임과 동작 후보를 비교하고 답 JSON을 복사한다."""

from __future__ import annotations

from html import escape

from character_factory_poc.contracts.video import ActionClip, ActionInputs


def _e(value) -> str:
    return escape(str(value), quote=True)


def render_g5b_page(
    *, subject_id: str, rev: str, inputs: ActionInputs, clips: list[ActionClip]
) -> str:
    parts = [
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>G5b 동작 영상 선택 · {_e(subject_id)} · {_e(rev)}</title>",
        "<style>body{font-family:-apple-system,system-ui,sans-serif;max-width:1200px;"
        "margin:2rem auto;padding:0 1rem;line-height:1.6;color:#222;background:#fff}"
        "*{box-sizing:border-box}h2{margin-top:2rem;border-bottom:1px solid #ddd}"
        ".chapter{display:grid;grid-template-columns:1fr;gap:1rem}"
        ".references{display:flex;gap:1rem}.reference{flex:1;min-width:0;max-width:220px}"
        "img{width:100%;height:auto}.candidates{display:flex;flex-wrap:wrap;gap:1rem}"
        "figure{margin:0;max-width:100%;flex:0 1 260px}"
        "video{width:100%;max-height:460px;background:#000}"
        "fieldset{min-width:0;margin:0 0 1.5rem;padding:1rem;border:1px solid #ccc}"
        "legend{font-weight:600}.hint{color:#555;font-size:.9rem}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f6f6;padding:1rem}"
        "label{display:block;padding:.5rem 0;min-height:44px}"
        "textarea{display:block;width:100%;min-height:5rem}input,select,textarea,button{font:inherit}"
        "button,select,input:not([type=radio]){min-height:44px}"
        "button{cursor:pointer;padding:.5rem 1rem}"
        ":focus-visible{outline:3px solid #176e63;outline-offset:3px}"
        "@media(max-width:640px){.chapter{grid-template-columns:1fr}.reference{max-width:180px}}"
        "</style></head><body><main><h1>G5b 동작 영상 선택</h1>",
        f'<p class="hint">{_e(subject_id)} · {_e(rev)} · G4 {_e(inputs.frameRev)} · '
        f"{_e(inputs.model)} · {_e(inputs.preset)} · {_e(inputs.resolution)} · "
        f"{_e(inputs.aspectRatio or '입력 비율')}</p>",
        "<p>동작마다 후보 하나를 고르거나 제외합니다. 챕터마다 영상 하나 이상을 남겨 주세요. "
        "얼굴·손·루프를 재생해 확인하고, 수정할 동작에는 구체적인 메모를 적어 주세요.</p>",
    ]
    for chapter in inputs.chapters:
        parts.extend(
            [
                f'<section><h2>{_e(chapter.chapterId)}</h2><div class="chapter">',
                f'<p class="hint">{_e(chapter.stageNote)}</p><div class="references">',
                '<div class="reference"><b>G4 승인 · 미소 출발</b>'
                f'<img src="{_e(chapter.goodFrame.path)}" '
                f'alt="{_e(chapter.chapterId)} 미소 출발 첫 프레임"></div>',
            ]
        )
        if chapter.badFrame:
            parts.append(
                '<div class="reference"><b>표정 편집 · 무표정 출발</b>'
                f'<img src="{_e(chapter.badFrame.path)}" '
                f'alt="{_e(chapter.chapterId)} 무표정 출발 첫 프레임"></div>'
            )
        parts.append("</div><div>")
        for action in chapter.actions:
            aid = _e(action.actionId)
            parts.extend(
                [
                    f'<fieldset data-action="{aid}"><legend>{aid} · '
                    f"{_e(action.title or action.actionKey)}</legend>",
                    f'<p class="hint"><code>{_e(action.actionKey)}</code> · '
                    f"{'미소 출발' if action.mood == 'good' else '무표정 출발'} · "
                    f"{_e(action.duration)}초</p>",
                    "<details><summary>사용 조건</summary>"
                    f"<p>{_e(action.useWhen or '별도 조건 없음')}</p></details>",
                    "<details><summary>움직임 프롬프트</summary>"
                    f"<pre>{_e(action.prompt)}</pre></details>",
                    '<div class="candidates">',
                ]
            )
            for clip in (c for c in clips if c.actionId == action.actionId):
                asset = clip.asset
                marker = f" · {_e(clip.reusedFrom)} 재사용" if clip.reusedFrom else ""
                if asset.postprocess:
                    parts.append(
                        '<p class="hint">복귀 검사: '
                        f"{_e(asset.postprocess.get('status'))} · "
                        f"{_e(asset.postprocess.get('reason', '품질 미검증'))} · "
                        f"실제 {_e(asset.probe.durationS)}초. 자동 품질 승인이 아닙니다.</p>"
                    )
                parts.append(
                    f'<figure><video src="{_e(asset.filePath)}" controls loop muted playsinline '
                    f'preload="metadata" aria-label="{aid} {_e(asset.candidateId)}"></video>'
                    f'<figcaption><label><input type="radio" name="{aid}" '
                    f'value="{_e(asset.candidateId)}"> {_e(asset.candidateId)} 선택{marker}'
                    "</label></figcaption></figure>"
                )
            parts.extend(
                [
                    "</div>",
                    f'<label><input type="radio" name="{aid}" value="exclude"> 제외</label>',
                    f'<label for="note-{aid}">이 동작 수정 요청</label>'
                    f'<textarea id="note-{aid}" data-note="{aid}"></textarea></fieldset>',
                ]
            )
        parts.append("</div></div></section>")
    parts.extend(
        [
            '<section><h2>결정</h2><label>결정 <select id="decision"><option>SELECT</option>'
            "<option>REQUEST_CHANGES</option><option>REJECT</option></select></label>",
            '<label>검토자 <input id="reviewer" value="user"></label>',
            '<label>소요 분 <input id="minutes" type="number" '
            'min="0" step="any" value="0"></label>',
            '<label>사유·메모 <textarea id="reasons"></textarea></label>',
            '<button type="button" onclick="copyAnswer()">답 JSON 복사</button>',
            "<p>아래 JSON을 복사해 answer.json으로 저장하고 "
            f"<code>cfp gate import {_e(subject_id)} G5b --answer answer.json</code>"
            "을 실행합니다.</p>",
            '<p id="status" role="status"></p>'
            '<pre id="out" tabindex="0" aria-label="답 JSON"></pre>',
            "</section></main><script>async function copyAnswer(){"
            "const decision=document.getElementById('decision').value;"
            "const picks={},excluded=[],requestedChanges=[];"
            "document.querySelectorAll('fieldset[data-action]').forEach(group=>{"
            "const aid=group.dataset.action;const pick=group.querySelector('input:checked');"
            "if(decision==='SELECT'&&pick){if(pick.value==='exclude'){excluded.push(aid);}"
            "else{picks[aid]=pick.value;}}"
            "const note=group.querySelector('textarea').value.trim();"
            "if(decision==='REQUEST_CHANGES'&&note){requestedChanges.push({field:aid,note});}});"
            "const answer={decision,picks,excluded,requestedChanges,"
            "reviewer:document.getElementById('reviewer').value,"
            "minutes:Number(document.getElementById('minutes').value),"
            "reasons:document.getElementById('reasons').value};"
            "const text=JSON.stringify(answer,null,2);"
            "document.getElementById('out').textContent=text;"
            "const status=document.getElementById('status');"
            "try{await navigator.clipboard.writeText(text);"
            "status.textContent='답 JSON을 복사했습니다.';}"
            "catch{status.textContent='자동 복사가 안 되면 아래 JSON을 직접 복사해 주세요.';}"
            "}</script></body></html>",
        ]
    )
    return "".join(parts)
