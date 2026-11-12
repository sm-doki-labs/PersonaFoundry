"""외부 자원이 없는 G8 시연·가족 블라인드 화면과 판정 가져오기."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path

from character_factory_poc.common.errors import FactoryError
from character_factory_poc.common.store import (
    read_json,
    verify_manifest,
    write_manifest,
    write_once_json,
)
from character_factory_poc.contracts.twin_comparison import Condition, Score, TwinComparison
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import SOURCE
from character_factory_poc.pipeline.origin import read_origin

BASE = "twin-comparison.json"
REVIEWED = "twin-comparison-reviewed.json"
PLAN = "twin-comparison-plan.json"
START = "<!-- twin-comparison start -->"
END = "<!-- twin-comparison end -->"
LABEL = {"USER": "사용자", "SUBJECT": "대상 인물", "OTHER": "다른 참여자"}
NOTE = "AI 생성 · 본인과 무관한 기술 시연"

STYLE = """
:root{font:100%/1.65 system-ui,sans-serif;color:#212523;background:#f8f9f7}
body{max-width:48rem;margin:2.5rem auto;padding:0 1rem 3rem;overflow-wrap:anywhere}
section,fieldset{min-width:0;border:0;border-top:1px solid #cdd3ce;margin:1.6rem 0;padding:1rem 0}
legend,h2{font-weight:650;font-size:1.2rem}p,blockquote,label{white-space:pre-wrap}
blockquote{border-inline-start:3px solid #ccd2cd;padding-inline-start:1rem;margin:.6rem 0}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
label,.reply{display:block;background:white;border:1px solid #ccd2cd;border-radius:.55rem;
padding:.8rem}
label{cursor:pointer}label:has(:checked){outline:2px solid #256347}button{background:#255c44;
color:white;border:0;font:inherit;padding:.7rem 1rem;border-radius:.4rem}button:focus-visible,
input:focus-visible{outline:3px solid #2c7654;outline-offset:2px}small{color:#535c55}
@media(max-width:36rem){.cols{grid-template-columns:1fr}body{margin-top:1rem}}
"""


def _page(title, body):
    return (
        '<!doctype html><html lang="ko"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title><style>{STYLE}</style><main><h1>{title}</h1>"
        f"<p><small>{NOTE}</small></p>{body}</main></html>"
    )


def _context(scene):
    lines = "".join(
        f"<p><small>{LABEL[m['speaker']]}</small><br>{escape(m['text'])}</p>"
        for m in scene["context"]
    )
    return (f"<details><summary>앞 대화 보기</summary>{lines}</details>" if lines else "") + (
        f"<blockquote>{escape(scene['user']['text'])}</blockquote>"
    )


def render_pages(condition: Condition, items: list[tuple[dict, str]]) -> tuple[str, str]:
    """블라인드에는 정답 키, 조건 이름, 원본 ID, 시연 화면 링크를 넣지 않는다."""
    ballot = condition.ballot
    questions = []
    demo = []
    for n, (trial, (scene, reply)) in enumerate(zip(condition.trials, items, strict=True), 1):
        actual = escape(scene["actualReply"]["text"])
        fake = escape(reply)
        ctx = _context(scene)
        options = (actual, fake) if trial.blindActual == "A" else (fake, actual)
        choices = "".join(
            f'<label><input required type="radio" name="{trial.pairId}" value="{side}"> '
            f"{side}<br>{content}</label>"
            for side, content in zip("AB", options, strict=True)
        )
        questions.append(
            f"<fieldset><legend>장면 {n}</legend>{ctx}<div class=cols>{choices}</div></fieldset>"
        )
        flags = overlap_label(trial.overlap)
        demo.append(
            f"<section><h2>장면 {n}</h2>{ctx}<div class=cols>"
            f"<div class=reply><b>실제 카톡</b><p>{actual}</p></div>"
            f"<div class=reply><b>생성 답</b><p>{fake}</p></div></div>"
            f"<small>정답과 같음: {'예' if trial.exact else '아니요'} · 자료 겹침: {flags}"
            "</small></section>"
        )
    script = """
<script>
const form=document.querySelector('form'), status=document.querySelector('[role=status]');
const total=form.querySelectorAll('fieldset').length;
function progress(){const count=Array.from(new FormData(form)).length;
  status.textContent='선택한 장면 '+count+' / '+total}
form.addEventListener('change',progress);
form.addEventListener('submit',event=>{
  event.preventDefault();
  const picks=Object.fromEntries(new FormData(form));
  const json=JSON.stringify({ballot:form.dataset.ballot,picks},null,2);
  const url=URL.createObjectURL(new Blob([json],{type:'application/json'}));
  const a=document.createElement('a');a.href=url;a.download='answers-'+form.dataset.ballot+'.json';
  a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  status.textContent='답 파일을 저장했어요. 이 파일을 평가 담당자에게 전달해 주세요.';
});
</script>"""
    blind = _page(
        "어느 쪽이 실제 답일까요?",
        "<p>장면마다 실제로 보낸 답을 하나 골라 주세요. 선택은 파일로만 저장돼요.</p>"
        f'<form data-ballot="{ballot}">'
        + "".join(questions)
        + '<p role="status" aria-live="polite">선택한 장면 0 / '
        + str(len(questions))
        + "</p><button>답 파일 저장</button></form>"
        + script,
    )
    return blind, _page("카톡과 생성 답 비교", "".join(demo))


def overlap_label(values):
    labels = {"TRAIN": "학습 대화", "PROMPT": "대화 프롬프트", "VOICE": "말투 예시"}
    return ", ".join(labels[v] for v in values) or "없음"


def score(correct: int, total: int) -> Score:
    return Score(correct=correct, total=total, rate=correct / total if total else None)


def latest(folder):
    return next((folder / n for n in (REVIEWED, BASE, PLAN) if (folder / n).is_file()), None)


def evidence(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("twin-*") if p.is_file())


def verify_evidence(folder):
    if verify_manifest(folder):
        raise FactoryError("G8 근거 파일이 비교 판의 해시와 다르다")


def _stat(s):
    return f"{s.correct}/{s.total} ({s.rate:.1%})" if s.total else "판정 없음"


def decorate(page: str, folder: Path) -> str:
    path = latest(folder)
    if not path:
        return page
    report = TwinComparison.model_validate(read_json(path))
    block = [
        START,
        "<section><h2>모티브 비교 평가</h2>",
        f"<p>비교 세트 {report.sceneCount}장면 · 예상 호출 {report.plannedCalls}회. "
        "구별률은 실제 답을 맞힌 비율이에요. 50%에 가까우면 우연히 고를 때와 비슷해요. "
        "장면 수가 적거나 같은 대화가 반복되면 차이를 일반화하기 어려워요.</p>",
        f"<p>심사 모델: {escape(report.judgeModel)} · 비용 상한: "
        + (f"${report.costUpperUsd:.2f}" if report.costUpperUsd is not None else "미설정")
        + "</p>",
        "<p>두 답이 같은 장면도 분모에 포함돼요. 이때는 문장만으로 어느 쪽이 실제인지 "
        "알 수 없어요.</p>",
        "<p>가족 한 사람에게는 블라인드 파일 하나만 전달해 주세요. "
        "시연 화면에는 정답이 나와요.</p>",
    ]
    for c in report.conditions:
        state = {
            "NO_SERVING": "서빙 없음",
            "PLANNED": "실행 전",
            "NO_JUDGE": "독립 심사 모델 미설정",
            "SKIPPED": "평가 생략(설정)",
            "COMPLETE": "판정 완료",
        }[c.status]
        block.append(
            f"<h3>{escape(c.armId)} · {state}</h3>"
            f"<p>모델 구별률: {_stat(c.modelScore)} · 사람 구별률: {_stat(c.humanScore)}</p>"
        )
        if c.ballot:
            block.append(
                f"<p>정답과 같음 {sum(t.exact for t in c.trials)}건 · "
                f"자료와 {report.overlapChars}자 이상 겹침 "
                f"{sum(bool(t.overlap) for t in c.trials)}건</p>"
                f'<a href="twin-blind-{c.ballot}.html">가족용 블라인드</a> · '
                f'<a href="twin-demo-{c.ballot}.html">카톡과 생성 답 시연</a>'
            )
    block.extend(["</section>", END])
    section = "".join(block)
    if START in page:
        before, rest = page.split(START, 1)
        return before + section + rest.split(END, 1)[1]
    i = next((page.index(s) for s in ("<h2>채택", "</main>", "</html>") if s in page), len(page))
    return page[:i] + section + page[i:]


def refresh_page(folder):
    path = folder / "gate-G8.html"
    path.write_text(decorate(path.read_text("utf-8"), folder), encoding="utf-8")
    write_manifest(folder)


def import_blind_answers(ctx: Context, cid: str, path: Path) -> Path:
    char = ctx.character_dir(cid)
    gate = ctx.state(cid).gate("G8")
    if read_origin(char) != SOURCE or gate.status != "AWAITING_HUMAN" or not gate.rev:
        raise FactoryError("열린 모티브 G8에만 가족 판정을 들여올 수 있다")
    folder = char / "s10-eval" / gate.rev
    if not (folder / BASE).exists():
        raise FactoryError("실행한 비교 보고가 없다")
    verify_evidence(folder)
    report = TwinComparison.model_validate(read_json(folder / BASE))
    obj = read_json(path)
    ballot = obj.get("ballot") if isinstance(obj, dict) else None
    condition = next((c for c in report.conditions if c.ballot and c.ballot == ballot), None)
    if not condition or set(obj) != {"ballot", "picks"} or not isinstance(obj["picks"], dict):
        raise FactoryError("이 비교 판의 블라인드 답 파일이 아니다")
    picks = obj["picks"]
    if set(picks) != {t.pairId for t in condition.trials} or any(
        v not in ("A", "B") for v in picks.values()
    ):
        raise FactoryError("모든 장면에 A 또는 B를 하나씩 골라야 한다")
    write_once_json(folder / f"twin-votes-{ballot}.json", obj)
    for c in report.conditions:
        vote_path = folder / f"twin-votes-{c.ballot}.json"
        if c.ballot and vote_path.exists():
            votes = read_json(vote_path)["picks"]
            c.humanScore = score(
                sum(votes[t.pairId] == t.blindActual for t in c.trials), len(votes)
            )
    result = folder / REVIEWED
    tmp = result.with_suffix(".tmp")
    tmp.write_text(json.dumps(report.model_dump(), ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(result)
    refresh_page(folder)
    return result
