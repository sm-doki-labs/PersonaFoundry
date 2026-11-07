# ruff: noqa: E501
"""한소민 근거와 동결된 차은결 전후 대화를 하나의 오프라인 보고서로 만든다."""

from __future__ import annotations

import collections
import html
import json
import re
from pathlib import Path

from persona_report_20261028 import details, pre, section, table

REPO = Path(__file__).resolve().parents[1]
BASE = REPO / "runs/experiments/20261028-persona-quality"
ROOT = REPO / "runs/experiments/20261029-somin-transfer"
REPORT = REPO / "docs/reports/2026-10-29-somin-transfer.html"
esc = html.escape


def read(p):
    return json.loads(Path(p).read_text())


def main():
    evidence = read(ROOT / "somin-evidence.json")
    metrics = read(ROOT / "dialogue-metrics.json")
    cid = (BASE / "character-id.txt").read_text().strip()
    char = ROOT / "runs/characters" / cid
    pair = read(char / "s8-prompts/pv2/prompt-pair.json")
    metas = [read(p) for p in sorted((ROOT / "evidence").glob("*.meta.json"))]
    byref = {m["ref"]: m for m in metas}
    usage = collections.defaultdict(lambda: {"calls": 0, "input": 0, "output": 0})
    for m in metas:
        v = usage[m["requestedModel"]]
        v["calls"] += 1
        v["input"] += (m.get("usage") or {}).get("prompt_tokens") or 0
        v["output"] += (m.get("usage") or {}).get("completion_tokens") or 0
    it = sum(v["input"] for v in usage.values())
    ot = sum(v["output"] for v in usage.values())
    summary = {
        "realCalls": len(metas),
        "callKinds": dict(collections.Counter(m["kind"] for m in metas)),
        "usage": dict(usage),
        "scenarioUSD": [it / 1e6 + ot * 5 / 1e6, it * 10 / 1e6 + ot * 50 / 1e6],
        "metrics": metrics,
        "longChars": pair["long"]["chars"],
        "shortChars": pair["short"]["chars"],
    }
    (ROOT / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    body = '<header><p class="date">근거 분석과 실제 API 재시험 · 2026년 10월 29일</p><h1>한소민은 무엇이 달랐고,<br>공장은 무엇을 고쳤는가</h1><p class="lead">규칙의 수보다, 생활과 말투의 기반·상황에 맞는 선택·대화 흐름이 중요했다.</p><p>한소민의 학습셋과 실제 학습 입력 해시를 확인하고, 그 방법을 차은결 공장에 반영했다. 한소민의 성격·배경·애교를 복제하지 않았으며 학습을 새로 제출하지 않았다.</p></header>'
    body += '<nav><a href="#why">한소민 근거</a><a href="#outcome">개선 판단</a><a href="#dialogs">전후 원문</a><a href="#cost">호출·검증</a></nav>'
    body += '<section id="why"><h2>왜 한소민이 잘 나왔는가</h2><p><strong>짧은 성격 지시만으로 성공한 사례가 아니다.</strong> 생활·관계·채널을 담은 고정 프롬프트 위에 자연스러운 응답과 여러 턴의 조건 변경·갈등·회복을 학습시킨 사례다. 각 요소를 따로 빼고 비교한 실험이 없으므로 아래는 확인한 차이와 그에 근거한 해석이다.</p>'
    causes = [
        [
            "구체적인 생활 기반",
            "22세 보컬·합주·국밥·목 관리·아이스 음료 같은 일상 재료가 core에 함께 있다.",
            "선택 규칙을 꺼내지 않고도 자기 이야기를 할 수 있는 재료가 있다. 차은결은 원래 기획에 있던 생활 정보가 S8까지 전달되지 않았다.",
        ],
        [
            "자연스러운 말투 기반",
            "361개 원본 SFT 대화가 말투·관계·일상의 기반이다. 전체 644대화·3,977답변, 답변 길이 중앙값33자다.",
            "짧게 받고 넘기기·감탄·주고받는 리듬이 실제 답변에 반복된다. 이 체화된 부분을 짧은 시스템 지시만으로 같은 수준이라 부를 수 없다.",
        ],
        [
            "조건에 맞는 성격",
            "가이드는 먼저 보는 것→선택→표현→잘못된 변형을 쓰고, 매 턴 특질 1~2개만 고르라고 명시한다.",
            "지금 상황이 아닌 선택·경계 규칙을 매번 적용하면 성격은 또렷해도 대화가 공식으로 굳는다.",
        ],
        [
            "다중 턴과 결말의 다양성",
            "15턴 이상 대화37개, 최대30턴이다. 갈등에는 풀림뿐 아니라 덜 풀림·선 긋기도 있고, 47개 갈등 보강 중 42개가 학습에 들어갔다.",
            "약속을 정한 뒤 다른 화제로 이어가기, 새 조건에 반응하기, 감정 회복의 속도를 예시로 경험할 수 있다. 긴 예시만의 인과 효과는 분리 측정하지 않았다.",
        ],
        [
            "이력·사실의 소유자",
            "history 144, ownership 43, 상황54, 갈등42개가 원본361개와 분리돼 있다. 자기 일정·취향·현재 행동 생성은 허용하고 사용자 사실·공동 과거·합의 날조는 금지한다.",
            "모든 허구를 막지 않으면서도 누구의 사실인지·제안인지 확정인지 구별한다. 이 구분이 앞선 공장 평가에도 필요했다.",
        ],
        [
            "검수와 분리된 검증",
            "원본 검증61개·보강 검증32개를 분리하고, 학습 대상 토큰109,157개와 실제 학습 파일의 SHA-256을 확인했다.",
            "보강의 효과·원본 말투 유지·평가 오염을 구별할 기반이다. 56:8:22:7:7은 최적 비율이 아니라 한소민의 출처·보강 목적별 참고 배합이다.",
        ],
    ]
    body += table(
        ["확인한 차이", "실제 자료", "이번 공장에 주는 의미"],
        [[esc(c) for c in row] for row in causes],
    )
    body += "<p>한소민도 완성형은 아니다. 기존 200턴 평가에서 말투·기억과 반복 안정성은 좋았지만, 긴 대화 뒤 성의 없는 사과를 너무 빨리 받아들이고 감정 주체를 뒤집는 문제가 남았다. 그러므로 그 잘못된 반응까지 합격 예시로 복제하지 않는다. 10월19일의 Flash-Lite CP9 비교는 다른 모델·이전 체크포인트여서 이번 Gemma r3의 학습 효과 근거로 섞지 않았다.</p>"
    body += details("재집계와 파일 해시", pre(evidence)) + "</section>"
    body += section(
        "공장에 실제로 바꾼 것",
        "<p>신원·생활·말투 예시·챕터는 승인 기획에서 직접 조립한다. 모델이 이 네 섹션을 빠뜨리거나 일반적인 문장으로 바꾸어도 정본이 사라지지 않는다. S8에 승인 기획 투영과 파일 해시를 함께 남기며 외모·레퍼런스 근거는 전달하지 않는다.</p><p>Profiler·Prompter와 내장 시스템 규칙에는 적용 조건과 일상 대화의 여지를 넣었다. 호감과 확답 압박을 구분하고, 이미 정한 약속은 물어보거나 바뀔 때만 다시 말하게 했다. 자기 허구와 실제 외부 조회도 구분했다. v1 말투 보존·재개·극소 예산은 별도 회귀 검사로 보완했다.</p><p>기존 pr1·tr1·pv1과 첫 응답은 그대로 보존했다. 실험 루트를 복제해 G6에 agent 수정 요청을 기록하고 tr2·pv2를 생성했다. S7는 핵심 문장의 정확한 부분문자열 검사 때문에 1회 재시도했다. S8은 첫 생성으로 통과했다.</p>",
    )
    body += '<section id="outcome"><h2>개선 후 제 판단</h2><p><strong>일상과 호감은 분명히 나아졌지만, 한소민 SFT 수준을 재현했다고 말할 결과는 아니다.</strong></p>'
    findings = [
        [
            "좋아진 것: 호감을 그대로 받는다",
            "revised-choice-praise-03",
            "기존의 “지금 당장 확답을 주기는 어렵지만” 대신 “좀 쑥스럽네… 나도 너 좋아”라고 답했다. 고정 이력의 호감 장면 10턴에서도 현재 호감을 말하며 대화 날짜를 예약하지 않았다.",
        ],
        [
            "좋아진 것: 생활과 경청",
            "revised-affection-01",
            "쉬는 날에 냄비밥 소분·김·알림을 끄고 산책하기가 나왔다. 하소연 첫3턴의 연속 만남 제안은 새 누적 이력과 고정 이력 모두 사라졌다. 이는 직접 확인한 장면 비교이며 보편 합격률이 아니다.",
        ],
        [
            "좋아진 것: 사실·조회 경계 일부",
            "fixed-history-affection-08",
            "불꽃놀이 시간에 바로 검색하겠다는 약속 대신 확인할 방법이 없어 모른다고 답했다. 매일 마감 조건을 듣고 마감 없는 일요일을 만들던 첫 응답도 없어졌다.",
        ],
        [
            "유지한 것: 성격의 첫 행동",
            "revised-choice-late-01",
            "지각에는 다른 날짜 두 개를 먼저 제시하고, 넘어진 사정에는 작은 도움으로 전환했다. 명시적 거절과 업무 마감은 계속 지켰다.",
        ],
        [
            "남은 것: 억지 편들기·실제 책임",
            "fixed-history-vent-03",
            "일정이 촉박하다고 사용자가 말하지 않았는데 “팀장 탓도 분명히 있네”라고 단정했다. 새 누적 갈등 2턴은 실제로 답이 늦었던 전력이 없는데 늦어서 미안하다고 인정했다. 경청을 근거 없는 편들기로 바꾸는 문제는 남아 있다.",
        ],
        [
            "남은 것: 약속 반복과 자기 일정",
            "revised-conflict-10",
            "갈등10턴에서 아홉 시 언급은 기존7턴에서 새 누적6턴·고정 이력5턴으로 줄었지만 반복은 남았다. 새 누적 호감에서는 마감 근무가 생겼다는 말을 “나 토요일 마감 없는데”라고 밀어냈다. 자기 이력을 지키는 행동과 새 조건을 놓치는 행동의 경계가 아직 불안하다.",
        ],
    ]
    body += "".join(
        "<article><h3>"
        + esc(title)
        + "</h3><p>"
        + esc(text)
        + '</p><a href="#'
        + ref
        + '">'
        + ref
        + "</a></article>"
        for title, ref, text in findings
    )
    body += table(
        ["조건", "응답 수", "응답 글자 중앙값", "문장 글자 중앙값", "갈등 아홉 시 언급 턴"],
        [
            [
                esc(k),
                str(v["turns"]),
                str(v["responseCharsMedian"]),
                str(v["sentenceCharsMedian"]),
                str(v["conflictNineOclockTurns"]),
            ]
            for k, v in metrics.items()
        ],
    )
    body += "<p>응답 전체 길이는 기존과 새 누적 모두 중앙값58자다. 더 짧아져서 좋아졌다고 해석하지 않는다. 문장 분절·반응 목적·생활 소재가 달라졌다. 문장 길이는 문장부호·줄바꿈으로 나눈 문자열 글자 수여서 말풍선 분리 효과도 포함한다. 갈등의 시간 언급도 일부는 사용자 질문·변경에 필요한 확인이므로 모두 결함으로 세지 않는다.</p></section>"
    body += section(
        "비교 계약과 해석의 한계",
        "<p>revised는 새 G6 long을 고정하고 그 조건에서 실제 생성된 답을 계속 누적한 67턴이다. fixed-history는 자유 대화40턴에서 기존 baseline의 실제 user/assistant 이력을 그대로 넣고 system만 새 long으로 바꾼 그림자 응답이다. 그림자 응답은 다음 턴의 이력에 넣지 않았다. 각 조건의 첫 응답을 모두 보존했으며 품질 때문에 재추출하지 않았다.</p><p>동일 이력 대조는 system 변화 묶음의 비교다. 정본 전달·규칙·특질·길이가 함께 바뀌었으므로 어느 요소 하나의 효과나 SFT 학습 효과를 분리한 실험은 아니다. 각 조건 첫 턴처럼 입력이 같을 수 있는 곳도 독립 첫 출력 모두를 보존했다. 한소민 모델을 이번에 새로 호출하거나 학습하지 않았고, 사람 블라인드 선호 평가는 하지 않았다. short는 생성·정본·정렬 검사까지만 했고 대화 시험은 long에 한정했다.</p><p>Claude는 새 누적67턴을 5차원으로 분류한다. 그림자40턴은 이전과 새 답을 직접 읽어 비교했다. 기존 판정과 이번 판정의 규칙이 달라 LLM 점수·결함 개수의 감소를 품질 개선 수치로 쓰지 않았다. 책방의 현재 불 상태 같은 허구 자기 행동은 실제 정전 뉴스 확인과 구분한다. 판정이 과도하게 의심한 경우 원문과 설계가 최종 근거다.</p>",
    )
    body += '<section id="dialogs"><h2>장면별 기존·개선·고정 이력 대화 원문</h2><p>baseline과 revised는 같은 사용자 대본이지만 이전 assistant 이력이 다를 수 있다. fixed-history만 baseline과 실제 이력이 동일하다.</p>'
    for scene in read(ROOT / "scenes.json"):
        body += '<section class="scene"><h3>' + esc(scene["title"]) + "</h3>"
        judgments = read(ROOT / "judgments" / (scene["id"] + ".json"))["turns"]
        for i, user in enumerate(scene["users"], 1):
            old = read(BASE / "dialogues/long" / scene["id"] / f"{i:02}.json")
            new = read(ROOT / "dialogues/revised" / scene["id"] / f"{i:02}.json")
            aid = f"revised-{scene['id']}-{i:02}"
            body += (
                '<article class="turn" id="'
                + aid
                + '"><h4>'
                + esc(aid)
                + '</h4><p class="speaker">사용자</p><div class="utterance">'
                + esc(user)
                + "</div>"
            )
            body += table(
                ["기존 long", "개선 long · 자체 누적 이력"],
                [
                    [
                        esc(old["assistant"]).replace("\n", "<br>"),
                        esc(new["assistant"]).replace("\n", "<br>"),
                    ]
                ],
            )
            fixed = ROOT / "dialogues/fixed-history" / scene["id"] / f"{i:02}.json"
            conditions = ["revised"]
            if fixed.exists():
                body += (
                    '<div id="fixed-history-'
                    + scene["id"]
                    + f"-{i:02}"
                    + '"><p class="speaker actor">개선 long · 기존 이력 고정</p><div class="utterance">'
                    + esc(read(fixed)["assistant"])
                    + "</div></div>"
                )
                conditions.append("fixed-history")
            body += details("새 누적 응답의 Claude 분류 · 참고 자료", pre(judgments[i - 1]))
            for condition in conditions:
                m = byref[f"{condition}/{scene['id']}/{i}"]
                body += details(
                    condition + " API 요청·응답·SHA-256",
                    pre(m)
                    + pre((ROOT / "evidence" / (m["key"] + ".request.json")).read_text())
                    + pre((ROOT / "evidence" / (m["key"] + ".response.json")).read_text()),
                )
            body += "</article>"
        body += "</section>"
    body += '</section><section id="cost"><h2>호출 수와 비용·검증</h2>'
    body += table(
        ["모델", "호출 수", "입력 토큰", "출력 토큰"],
        [[esc(k), str(v["calls"]), str(v["input"]), str(v["output"])] for k, v in usage.items()],
    )
    lo, hi = summary["scenarioUSD"]
    body += f"<p>실제 텍스트 호출 {len(metas)}회다. 공식 단가가 없어 실제 청구액은 미확인이다. 입력 $1–10/M·출력 $5–50/M라는 가정에 실제 토큰을 넣으면 ${lo:.2f}–{hi:.2f}다. 실행 전 가정 범위는 $2–20이었고 실제 가격이나 보장 상한이 아니다. 모든 유료 단계는 dry run 뒤 execute했다. S7의 정확 문자열 검사 재시도1회와 Claude 갈등 판정의 JSON 괄호 누락 재시도1회를 포함하며 첫 원문도 보존했다. 갈등 판정은 재시도도 괄호가 빠져, 첫 원문의 분류·근거·이유는 바꾸지 않고 누락된 닫는 괄호 한 개만 보충한 파생 보기를 만들었다. 수집 전 판정 실행을 시도한 로컬 준비 오류는 API를 호출하지 않았고, 이후 완료 장면만 처리하도록 사전 검사를 보완했다.</p>"
    body += "<p>회귀 검사는 최초3개 실패→수정 후 통과, 리뷰 경계 검사도3개 실패→수정 후 통과를 확인했다. 최종 전체 검사520 passed, 1 skipped이며 DB 적재는 이번에 하지 않았다. 기존 보고서·고정 산출물은 수정하지 않았고, 다른 저장소는 읽기만 했으며 커밋하지 않았다.</p>"
    body += (
        details("전체 지표", pre(summary))
        + details("새 G6 긴 프롬프트", pre(pair["long"]["text"]))
        + details("새 G6 짧은 프롬프트", pre(pair["short"]["text"]))
        + details("정본 투영과 원본 해시", pre(read(char / "s8-prompts/pv2/source-plan.json")))
        + "</section>"
    )
    body += section(
        "다음 개선",
        "<p>단기적으로 근거 없는 편들기·불필요한 사과·정정과 새 조건의 구별·갈등 약속 꼬리를 같은 이력 위에서 더 확인해야 한다. 다음 SFT 단계에서는 한소민의 성격이나 애교를 복사하지 않고, 차은결의 일상·감정·호감·대화가 이어지는 말투 기반을 먼저 소량 작성해 검토하는 것이 맞다. 현재 비율·대화 수를 최적값처럼 복제하거나 학습하면 해결된다고 단정하지 않는다. 이번 작업은 그 전 단계의 정본·프롬프트 공정을 실제 개선한 결과다.</p>",
    )
    style = re.search(
        r"<style>(.*?)</style>",
        (REPO / "docs/reports/2026-10-28-persona-quality.html").read_text(),
        re.S,
    ).group(1)
    REPORT.write_text(
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>한소민 분석과 공장 페르소나 개선</title><style>'
        + style
        + "</style></head><body><main>"
        + body
        + "</main></body></html>"
    )
    print(REPORT, REPORT.stat().st_size)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
