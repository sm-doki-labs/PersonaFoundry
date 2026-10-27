"""G4a 오프라인 검토 페이지와 장면 관문 공통 서식."""

from __future__ import annotations

import html

from acf.contracts.qa import QaSummary
from acf.stages.image_qa import RUBRICS, Rubric


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def fields(items: dict) -> str:
    return (
        "<dl>"
        + "".join(
            f"<dt>{esc(key)}</dt>"
            f"<dd>{esc(', '.join(value) if isinstance(value, list) else value)}</dd>"
            for key, value in items.items()
        )
        + "</dl>"
    )


def render_qa(qa: QaSummary | None, rubric: Rubric) -> str:
    """자동 검사 요약을 표시하되 최종 판단은 사람에게 남긴다."""
    if qa is None:
        return ""
    failed = qa.status == "FAIL"
    badge = "자동 검사 미통과 — 사람 확인 필요" if failed else f"자동 검사 통과 ({qa.attempts}회째)"
    items = []
    for ids, prefix in ((qa.failed, ""), (qa.unsure, "판단 보류 · ")):
        for item_id in ids:
            label = rubric.label(item_id)
            reason = next((r for r in qa.reasons if r.startswith(label + ":")), label)
            items.append(f"<li>{esc(prefix + reason)}</li>")
    reasons = "<ul>" + "".join(items) + "</ul>" if items else ""
    state = "fail" if failed else "pass"
    return (
        f'<aside class="qa qa-{state}" aria-label="자동 검사 결과">'
        f'<strong class="qa-badge">{esc(badge)}</strong>{reasons}'
        f'<p><a href="{esc(qa.report)}">자동 검사 보고서 JSON</a></p>'
        "<p>자동 검사는 참고 자료이며 최종 승인은 사람이 결정합니다.</p></aside>"
    )


def page_shell(
    title: str,
    cid: str,
    rev: str,
    sections: list[str],
    script: str,
    *,
    decisions: tuple[str, ...] = ("SELECT", "APPROVE", "REQUEST_CHANGES", "REJECT"),
) -> str:
    options = "".join(f"<option>{esc(d)}</option>" for d in decisions)
    return "".join(
        [
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{esc(title)}</title><style>",
            ":root{--ink:#242624;--muted:#555d57;--line:#b8c1bb;--accent:#245c46;",
            "--paper:#fafbf9;--danger:#a12222;--space:1rem}*{box-sizing:border-box}",
            ".qa{padding:12px;border:1px solid var(--line);overflow-wrap:anywhere}",
            ".qa-badge{display:inline-block}.qa-pass .qa-badge{color:var(--accent)}",
            ".qa-fail{border-color:var(--danger)}.qa-fail .qa-badge{color:var(--danger)}",
            ".qa p{margin:8px 0 0;font-size:.9rem}.qa ul{padding-left:1.3rem}",
            "body{margin:0;background:var(--paper);color:var(--ink);",
            "font:16px/1.6 system-ui,sans-serif}main{max-width:1200px;margin:auto;padding:24px}",
            "h1{letter-spacing:-.02em}h2{margin:0}fieldset{border:1px solid var(--line);",
            "padding:16px;margin:24px 0}legend{font-size:1.35rem;font-weight:650}",
            ".grid{display:grid;"
            "grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));",
            "gap:16px}.card{display:flex;flex-direction:column;border:1px solid var(--line);",
            "padding:16px;gap:8px;background:white}.card:has(input:checked){",
            "outline:2px solid var(--accent)}img.plate,img.frame{display:block;width:100%;",
            "aspect-ratio:9/16;object-fit:contain;background:#e8ece8}img.ref{max-width:180px;",
            "max-height:200px;object-fit:contain}.scene{max-width:360px}",
            "dt{font-size:.85rem;color:var(--muted)}dd{margin:0 0 8px;overflow-wrap:anywhere}",
            "label{display:block;min-height:44px;padding:8px 0}input,textarea,select,button{",
            "font:inherit}textarea,input:not([type=radio]){width:100%;min-height:44px}",
            "textarea{min-height:88px}button{min-height:44px;padding:10px 24px;",
            "background:var(--accent);color:white;border:0;border-radius:6px;cursor:pointer}",
            "button:hover{background:#174331}button:active{background:#102e23}",
            ":focus-visible{outline:3px solid var(--accent);outline-offset:3px}",
            "pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            "summary{cursor:pointer;min-height:44px}",
            "@media(max-width:600px){main{padding:16px}}",
            '</style></head><body><a href="#main">검토로 건너뛰기</a><main id="main">',
            f"<h1>{esc(title)}</h1><p>{esc(cid)} · {esc(rev)}</p>",
            '<form id="review">',
            *sections,
            "<fieldset><legend>결정</legend>",
            f'<label>결정 <select id="decision">{options}</select></label>',
            '<label>검토자 <input id="reviewer" value="user" required></label>',
            '<label>검토 시간(분) <input id="minutes" type="number" min="0" value="0"></label>',
            '<label>검토 사유 <textarea id="reasons"></textarea></label></fieldset>',
            '<button type="submit">답 JSON 만들고 복사</button>',
            "<p>JSON을 answer.json으로 저장한 뒤 관문 답으로 가져오면 선택이 반영됩니다.</p>",
            '<p id="error" role="alert" tabindex="-1"></p>',
            '<label>관문 답 JSON <textarea id="out" readonly></textarea></label>',
            '<p id="copy-status" role="status"></p></form></main><script>',
            "const CH=['ch1','ch2','ch3'];const $=id=>document.getElementById(id);",
            "function metadata(){return {decision:$('decision').value,"
            "reviewer:$('reviewer').value,",
            "minutes:Number($('minutes').value),reasons:$('reasons').value};}",
            "function choices(){const picks={},custom={};for(const ch of CH){",
            "const r=document.querySelector('input[name='+ch+']:checked');",
            "if(!r)throw Error(ch+'에서 후보 또는 직접 정의를 선택하세요.');",
            "if(r.value==='custom'){const text=$('custom-'+ch).value.trim();",
            "if(!text)throw Error(ch+'의 직접 정의를 적어 주세요.');custom[ch]=text;}",
            "else picks[ch]=r.value;}return {picks,custom};}",
            script,
            "$('review').addEventListener('submit',async event=>{event.preventDefault();",
            "$('error').textContent='';try{const answer=buildAnswer();",
            "const text=JSON.stringify(answer,null,2);$('out').value=text;",
            "try{await navigator.clipboard.writeText(text);"
            "$('copy-status').textContent='복사했습니다.';}",
            "catch{$('copy-status').textContent='아래 JSON을 직접 복사하세요.';}}",
            "catch(error){$('error').textContent=error.message;$('error').focus();}});",
            "</script></body></html>",
        ]
    )


def custom_control(ch: str, label: str) -> str:
    return (
        f'<label><input type="radio" name="{ch}" value="custom"> {esc(label)}</label>'
        f'<label for="custom-{ch}">원하는 내용을 한두 줄로 적어 주세요.</label>'
        f'<textarea id="custom-{ch}"></textarea>'
    )


def render_g4a_page(cid: str, rev: str, backgrounds) -> str:
    sections = ["<p>챕터마다 배경 하나를 고르거나 원하는 배경을 직접 적어 주세요.</p>"]
    for ch in backgrounds.chapters:
        cards = []
        for candidate in ch.candidates:
            image = (
                f'<img class="plate" src="{esc(candidate.plate.path)}" '
                f'alt="{esc(candidate.place)}의 인물 없는 배경">'
                if candidate.plate
                else "<p>배경 사진을 생략한 후보입니다.</p>"
            )
            cards.append(
                '<article class="card">'
                + image
                + render_qa(candidate.qa, RUBRICS["plate-v1"])
                + fields(
                    {
                        k: getattr(candidate, k)
                        for k in (
                            "place",
                            "timeOfDay",
                            "why",
                            "props",
                            "mood",
                            "sceneFactsDraft",
                            "boundariesDraft",
                            "plateBrief",
                        )
                    }
                )
                + f'<label><input type="radio" name="{ch.chapterId}" '
                f'value="{esc(candidate.candidateId)}"> 이 배경 선택</label></article>'
            )
        sections.append(
            f"<fieldset><legend>{esc(ch.title)} · {ch.chapterId}</legend>"
            f'<p>{esc(ch.arc)}</p><div class="grid">{"".join(cards)}</div>'
            + custom_control(ch.chapterId, "배경 직접 정의")
            + "</fieldset>"
        )
    script = (
        "function buildAnswer(){const o=metadata();"
        "return o.decision==='SELECT'?{...o,...choices()}:o;}"
    )
    return page_shell("G4a 챕터 배경 선택", cid, rev, sections, script)
