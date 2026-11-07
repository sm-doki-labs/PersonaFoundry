"""G3 후보를 나란히 비교하고 선택·수정 답 JSON을 만드는 오프라인 페이지."""

from __future__ import annotations

import html
import json

from character_factory_poc.common.schema import dump
from character_factory_poc.contracts.planning import EDITABLE_FIELDS, PlanVariants


def _e(value) -> str:
    return html.escape(str(value), quote=True)


def render_g3_page(*, variants: PlanVariants, choice_evidence=None) -> str:
    explicit = getattr(variants, "schemaVersion", "") == "plan-variants-v2"
    cards = []
    for plan in variants.candidates:
        fields = []
        for field, value in dump(plan).items():
            text = (
                json.dumps(value, ensure_ascii=False, indent=2)
                if not isinstance(value, str)
                else value
            )
            fields.append(f"<dt>{_e(field)}</dt><dd><pre>{_e(text)}</pre></dd>")
        if choice_evidence:
            for rule in choice_evidence[plan.variantId].rules:
                explanation = (
                    f"먼저 지키는 것: {rule.priority}\n"
                    f"감수하는 것: {rule.acceptedCost}\n"
                    f"생각을 바꾸는 조건: {rule.switchWhen}"
                )
                fields.append(
                    f"<dt>{_e(rule.situation)} · 선택 근거</dt>"
                    f"<dd><pre>{_e(explanation)}</pre></dd>"
                )
        cards.append(
            '<article class="card">'
            f'<h2><label><input type="radio" name="pick" value="{_e(plan.variantId)}"> '
            f"{_e(plan.variantId)} · {_e(plan.name)}</label></h2>"
            f"<p>{_e(plan.tagline)}</p><dl>{''.join(fields)}</dl></article>"
        )
    return "".join(
        [
            '<!doctype html><html lang="ko"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>G3 기획 선택 · {_e(variants.characterId)} · {_e(variants.planRev)}</title>",
            """<style>
        :root{--space:1rem;--ink:#222;--muted:#595959;--line:#d8d8d8;--paper:#fafafa}
        *{box-sizing:border-box}body{font-family:-apple-system,system-ui,sans-serif;
        max-width:1440px;margin:2rem auto;padding:0 var(--space);line-height:1.6;
        color:var(--ink)}h1{letter-spacing:-.02em}h2{font-size:1.15rem}
        .hint{color:var(--muted)}.cards{display:grid;
        grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));gap:var(--space)}
        .card{min-width:0;border:1px solid var(--line);border-radius:10px;padding:var(--space)}
        .card:has(input:checked){outline:2px solid var(--ink)}dt{font-weight:600}
        dd{margin:0 0 var(--space)}pre{white-space:pre-wrap;overflow-wrap:anywhere;
        font:inherit;margin:.25rem 0;background:var(--paper);padding:.5rem;border-radius:6px}
        label{display:block}input,select,textarea,button{font:inherit;max-width:100%}
        input:not([type=radio]),select,button{min-height:44px}
        input[type=radio]{width:20px;height:20px;vertical-align:middle}
        .card label{padding:.5rem 0;cursor:pointer}textarea{width:100%;min-height:7rem;
        padding:.5rem;border:1px solid var(--line);border-radius:6px}
        form>label{margin:var(--space) 0}fieldset{border:1px solid var(--line);margin:0;
        padding:var(--space)}button{cursor:pointer;padding:.5rem 1rem;background:var(--ink);
        color:white;border:0;border-radius:6px}:focus-visible{outline:3px solid #555;
        outline-offset:3px}#status{min-height:1.6em}
        </style></head><body>""",
            "<h1>G3 캐릭터 기획 선택</h1>",
            f'<p class="hint">{_e(variants.characterId)} · {_e(variants.planRev)} · '
            f"{_e(variants.mode)} · 씨앗 {_e(variants.seedRev)}</p>",
            "<p>같은 상황에서 무엇을 먼저 선택하는지 비교한 뒤 한 안을 고릅니다.</p>",
            f"<p>{_e(variants.axisNote)}</p>",
            '<form id="answer"><fieldset><legend>기획 후보</legend><div class="cards">',
            "".join(cards),
            "</div></fieldset><h2>선택과 수정</h2>",
            '<label for="decision">결정</label><select id="decision">'
            "<option>SELECT</option>"
            + ("" if explicit else "<option>APPROVE</option>")
            + "<option>REQUEST_CHANGES</option><option>REJECT</option></select>",
            (
                '<p class="hint">후보 하나를 직접 고릅니다. '
                "수정한 내용은 새 버전에서 다시 검토합니다.</p>"
                if explicit
                else '<p class="hint">APPROVE는 첫 후보를 고릅니다. '
                "수정 내용은 선택한 후보에 적용합니다.</p>"
            ),
            '<label for="edits">수정할 칸 · edits JSON 객체</label>',
            '<textarea id="edits" spellcheck="false" aria-describedby="edit-help">{}</textarea>',
            '<p id="edit-help" class="hint">예: {&quot;tagline&quot;: &quot;새 소개 문장&quot;}. '
            f"수정 가능: {_e(', '.join(EDITABLE_FIELDS))}</p>",
            '<label>검토자 <input id="reviewer" value="user" required></label>',
            '<label>소요 분 <input id="minutes" type="number" min="0" step="any" value="0" '
            "required></label>",
            '<label>선택 사유·수정 요청 <textarea id="reasons"></textarea></label>',
            '<button type="submit">답 JSON 복사</button>',
            '<p id="status" role="status" aria-live="polite"></p><pre id="out" tabindex="0"></pre>',
            '<p class="hint">답 JSON을 answer.json으로 저장한 뒤 ',
            f"<code>cfp gate import {_e(variants.characterId)} G3 --answer answer.json</code>",
            "을 실행합니다.</p></form><script>",
            f"const editable={json.dumps(EDITABLE_FIELDS)};",
            f"const first={json.dumps(variants.candidates[0].variantId)};",
            """
        const el=id=>document.getElementById(id);
        el('answer').addEventListener('submit',async event=>{
          event.preventDefault();el('out').textContent='';el('status').textContent='';
          try{
            const decision=el('decision').value;
            const active=decision==='SELECT'||decision==='APPROVE';
            const pick=document.querySelector('input[name=pick]:checked');
            if(decision==='SELECT'&&!pick)throw Error('기획 후보 한 개를 선택해 주세요.');
            const edits=active?JSON.parse(el('edits').value):{};
            if(!edits||Array.isArray(edits)||typeof edits!=='object')
              throw Error('edits에는 JSON 객체를 입력해 주세요.');
            if(Object.keys(edits).some(key=>!editable.includes(key)))
              throw Error('수정할 수 없는 칸이 있습니다. 수정 가능 목록을 확인해 주세요.');
            const answer={decision,selections:active?[decision==='APPROVE'?first:pick.value]:[],
              edits,reviewer:el('reviewer').value,minutes:Number(el('minutes').value),
              reasons:el('reasons').value};
            const text=JSON.stringify(answer,null,2);el('out').textContent=text;
            try{await navigator.clipboard.writeText(text);
              el('status').textContent='답 JSON을 복사했습니다.';}
            catch{el('status').textContent='아래 답 JSON을 직접 선택해 복사해 주세요.';}
          }catch(error){el('status').textContent=error.message;}
        });
        </script></body></html>
        """,
        ]
    )
