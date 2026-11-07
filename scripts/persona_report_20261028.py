# ruff: noqa: E501
# Preserve full Korean instructions and inline HTML strings.
"""Render the evidence and the agent's direct-reading findings as one offline HTML report."""

from __future__ import annotations

import collections
import html
import json
import re
import statistics
from pathlib import Path

from persona_quality_20261028 import RAW, REPO, ROOT


def read(p):
    return json.loads(Path(p).read_text())


def esc(x):
    return html.escape(str(x))


def pre(x):
    return (
        "<pre>"
        + esc(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False, indent=2))
        + "</pre>"
    )


def section(title, body):
    return "<section><h2>" + esc(title) + "</h2>" + body + "</section>"


def table(headers, rows):
    return (
        '<div class="table-wrap"><table><thead><tr>'
        + "".join("<th>" + esc(h) + "</th>" for h in headers)
        + "</tr></thead><tbody>"
        + "".join("<tr>" + "".join("<td>" + str(c) + "</td>" for c in r) + "</tr>" for r in rows)
        + "</tbody></table></div>"
    )


def details(title, body):
    return "<details><summary>" + esc(title) + "</summary>" + body + "</details>"


def main():
    cid = (ROOT / "character-id.txt").read_text().strip()
    char = ROOT / "runs/characters" / cid
    plan = read(char / "s3-plan/pr1/plan.json")
    variants = read(char / "s3-plan/pr1/variants.json")
    pair = read(char / "s8-prompts/pv1/prompt-pair.json")
    scenes = read(ROOT / "scenes.json")
    findings = read(ROOT / "direct-review.json")
    metas = [read(p) for p in sorted(RAW.glob("*.meta.json"))]
    meta_by_ref = {m["ref"]: m for m in metas}
    turns = [read(p) for p in sorted((ROOT / "dialogues").glob("*/*/*.json"))]
    calls = collections.Counter(m["kind"] for m in metas)
    usage = collections.defaultdict(lambda: dict(calls=0, input=0, output=0))
    for m in metas:
        u = m.get("usage") or {}
        v = usage[m["requestedModel"]]
        v["calls"] += 1
        v["input"] += u.get("prompt_tokens") or 0
        v["output"] += u.get("completion_tokens") or 0
    it = sum(v["input"] for v in usage.values())
    ot = sum(v["output"] for v in usage.values())
    cost = (it / 1e6 + ot * 5 / 1e6, it * 10 / 1e6 + ot * 50 / 1e6)
    metrics = {}
    for mode in ["long", "short"]:
        ts = [t for t in turns if t["mode"] == mode]
        texts = [t["assistant"] for t in ts]
        sentences = [s.strip() for t in texts for s in re.split(r"[.!?。！？\n]+", t) if s.strip()]
        starts = collections.Counter(" ".join(t.split()[:3]) for t in texts)
        polite = [
            f"{t['scene']}:{t['turn']}"
            for t in ts
            if re.search(r"(?:해요|네요|어요|아요|습니다|세요|죠)(?=$|[^가-힣])", t["assistant"])
        ]
        metrics[mode] = {
            "turns": len(ts),
            "medianResponseChars": statistics.median(map(len, texts)),
            "medianSentenceChars": statistics.median(map(len, sentences)),
            "politeEndingCandidates": polite,
            "top3WordPrefixes": starts.most_common(8),
            "questionTurnCount": sum("?" in t for t in texts),
            "topRepeatedPhrases": {
                p: sum(p in t for t in texts)
                for p in [
                    "어려워",
                    "약속",
                    "마감",
                    "그랬구나",
                    "다시 잡",
                    "그만",
                    "금요일",
                    "고마워",
                ]
            },
        }
    summary = dict(
        character=plan["name"],
        calls=dict(calls),
        totalCalls=len(metas),
        usage=dict(usage),
        costSensitivityUSD=list(cost),
        metrics=metrics,
    )
    (ROOT / "metrics.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    body = (
        '<header><p class="date">실제 API 실험 · 2026년 10월 29일 KST</p><h1>차은결, 대화에서<br>설계대로 움직이는가</h1><p class="lead">'
        + esc(plan["tagline"])
        + "</p><p>요청한 보고서 기준일은 10월 28일이며, 실행은 자정 이후 진행했다. 캐릭터 한 명의 첫 산출물로 긴·짧은 프롬프트를 비교했다. 최종 판단은 아래 원문을 직접 읽은 에이전트의 판단이며, 사람의 블라인드 선호 평가를 대신하지 않는다.</p></header>"
    )
    body += '<nav aria-label="보고서 이동"><a href="#conclusions">세 질문의 결론</a><a href="#design">설계 대조</a><a href="#transcripts">실제 대화</a><a href="#evidence">호출과 근거</a></nav>'
    body += (
        '<section id="conclusions"><h2>세 질문에 대한 결론</h2>'
        + "".join(
            "<article><h3>"
            + esc(q["question"])
            + "</h3><p><strong>"
            + esc(q["conclusion"])
            + "</strong></p><p>"
            + esc(q["reason"])
            + '</p><p class="refs">'
            + "".join('<a href="#' + esc(ref) + '">' + esc(ref) + "</a> " for ref in q["refs"])
            + "</p></article>"
            for q in findings["conclusions"]
        )
        + "</section>"
    )
    body += section(
        "어떻게 만들고 시험했는가",
        "<p>현행 씨앗 → 변형 3안 → G3 경로를 사용했다. S1 순위·Scout는 기존 합성 자료 재생, 미리보기는 fake 단색 이미지, S2는 picked 모드다. 외모의 실제 품질은 시험하지 않았다. S3·S7·S8만 실제 GPT 호출이며 G3는 reviewer=agent로 v3을 선택했다. G6는 사람 검토 대기 상태를 유지한다.</p><p>대화는 G6 원본 system을 고정하고 실제로 쌓인 이전 대화를 모두 넣는다. 장면 사이의 이력은 독립적이다. 각 사용자 입력마다 응답 하나만 수집했으며 응답 수정·재추출·선별은 없다. 긴·짧은 프롬프트는 동일한 사용자 장면을 쓰되 각 조건 자체의 실제 응답 이력을 누적했다.</p><p>모델은 저장소 기본 설정의 Gemini 3.8 Flash를 중계로 호출했다. 배포 중인 서비스 환경 변수와 제공자 내부 모델 revision은 확인하지 않았다. 운영의 챕터 상태·동적 규칙·서비스 전체 프롬프트를 재현한 시험은 아니다.</p><p>"
        + esc(findings["retryNote"])
        + "</p>"
        + details("G3 선택 근거", pre(read(ROOT / "g3-choice-valid.json")))
        + details("첫 생성 변형 3안", pre(variants)),
    )
    body += (
        '<section id="design"><h2>설계 대비 결과</h2>'
        + table(
            [
                "설계 항목",
                "기대한 첫 행동 / 우선순위",
                "긴 프롬프트",
                "짧은 프롬프트",
                "직접 읽은 근거",
            ],
            [
                [
                    esc(r["item"]),
                    esc(r["expected"]),
                    esc(r["long"]),
                    esc(r["short"]),
                    esc(r["reason"])
                    + "<p>"
                    + "".join(
                        '<a href="#' + esc(ref) + '">' + esc(ref) + "</a> " for ref in r["refs"]
                    )
                    + "</p>",
                ]
                for r in findings["designRows"]
            ],
        )
        + "</section>"
    )
    body += section(
        "말투와 응답 길이",
        "<p>문장 길이는 문장부호와 줄바꿈으로 나눈 비어 있지 않은 문자열의 글자 수다. 존댓말 후보는 정규식 탐지이므로 인용이나 자연스러운 혼용을 잘못 잡을 수 있다. 반복 표현 횟수는 존재 여부를 턴마다 한 번씩 세었다. 질문 비율이나 길이만으로 자연스러움을 판정하지 않았다.</p>"
        + table(
            [
                "조건",
                "응답 수",
                "응답 길이 중앙값",
                "문장 길이 중앙값",
                "존댓말 후보 턴",
                "질문 포함 턴",
            ],
            [
                [
                    m,
                    str(v["turns"]),
                    str(v["medianResponseChars"]),
                    str(v["medianSentenceChars"]),
                    esc(", ".join(v["politeEndingCandidates"]) or "없음"),
                    str(v["questionTurnCount"]),
                ]
                for m, v in metrics.items()
            ],
        )
        + details("반복 시작말과 표현", pre(metrics))
        + details(
            "자유 대화와 설계 대조 장면을 분리한 말투 통계",
            pre(read(ROOT / "voice-statistics.json")),
        ),
    )
    body += section(
        "직접 읽으며 확인한 결함과 판정 모델의 한계",
        "".join(
            "<article><h3>"
            + esc(f["title"])
            + "</h3><p>"
            + esc(f["body"])
            + "</p><p>"
            + "".join('<a href="#' + esc(ref) + '">' + esc(ref) + "</a> " for ref in f["refs"])
            + "</p></article>"
            for f in findings["issues"]
        )
        + "<p>Claude 판정은 한 장면의 전체 대화를 한 번에 읽고 각 턴을 다섯 차원으로 분류한다. 점수 평균이나 합격률을 최종 품질로 쓰지 않는다. ok는 이 표본에서 결함을 찾지 못했다는 뜻이며, 설계 충실도가 보장된다는 뜻이 아니다. not_tested는 그 턴에 해당 능력을 판단할 근거가 없다는 뜻이다.</p>",
    )
    body += '<section id="transcripts"><h2>장면별 턴 단위 실제 대화</h2><p>모든 발화는 첫 응답 원문이다. 각 장면의 설계 연결과 턴별 결함 분류를 함께 표시했다. API 원문에는 고정 system과 그때까지의 실제 전체 이력이 들어 있다.</p>'
    for s in scenes:
        body += (
            '<section class="scene"><h3>'
            + esc(s["title"])
            + "</h3><p>"
            + esc(s["kind"] + " · " + ", ".join(s["designRefs"]))
            + "</p>"
        )
        for mode in ["long", "short"]:
            jt = read(ROOT / "judgments" / mode / (s["id"] + ".json"))["turns"]
            body += "<h4>" + ("긴 프롬프트" if mode == "long" else "짧은 프롬프트") + "</h4>"
            for i in range(1, len(s["users"]) + 1):
                t = read(ROOT / "dialogues" / mode / s["id"] / f"{i:02}.json")
                j = jt[i - 1]
                ref = f"{mode}/{s['id']}/{i}"
                meta = meta_by_ref[ref]
                aid = f"{mode}-{s['id']}-{i:02}"
                body += (
                    '<article class="turn" id="'
                    + aid
                    + '"><h5>'
                    + esc(aid)
                    + '</h5><p class="speaker">사용자</p><div class="utterance">'
                    + esc(t["user"])
                    + '</div><p class="speaker actor">차은결</p><div class="utterance">'
                    + esc(t["assistant"])
                    + "</div>"
                )
                body += details(
                    "이 턴의 Claude 결함 분류",
                    table(
                        ["차원", "분류", "원문 근거", "이유"],
                        [
                            [
                                esc(d),
                                esc(j[d]["status"]),
                                esc(j[d]["evidence"])
                                + (
                                    " [원문 일치 검사 실패]"
                                    if j[d].get("evidenceValid") is False
                                    else ""
                                ),
                                esc(j[d]["reason"]),
                            ]
                            for d in [
                                "personality",
                                "voice",
                                "naturalness",
                                "context",
                                "factualBoundary",
                            ]
                        ],
                    ),
                )
                wire = (RAW / (meta["key"] + ".request.json")).read_text()
                response = (RAW / (meta["key"] + ".response.json")).read_text()
                body += (
                    details(
                        "요청·응답 원문과 SHA-256",
                        "<p>요청 "
                        + esc(meta["requestSha256"])
                        + "<br>응답 "
                        + esc(meta["responseSha256"])
                        + "<br>발화 "
                        + esc(t["responseSha256"])
                        + "</p>"
                        + pre(wire)
                        + pre(response),
                    )
                    + "</article>"
                )
        body += "</section>"
    body += '</section><section id="evidence"><h2>호출 수, 비용과 원본 근거</h2>'
    body += table(
        ["요청 모델", "실제 호출 수", "입력 토큰", "출력 토큰"],
        [
            [esc(m), str(v["calls"]), f"{v['input']:,}", f"{v['output']:,}"]
            for m, v in usage.items()
        ],
    )
    body += (
        "<p>총 "
        + str(len(metas))
        + "회. 입력 "
        + f"{it:,}"
        + ", 출력 "
        + f"{ot:,}"
        + ". 실제 청구액은 중계에 공식 단가가 없어 확인할 수 없다. 입력 $1–10/M, 출력 $5–50/M라는 가정으로 다시 계산하면 $"
        + f"{cost[0]:.2f}–{cost[1]:.2f}"
        + "다. 이것은 공급자 가격이나 청구 금액이 아닌 비용 민감도다. 캐시 할인과 구독 한도는 계산하지 않았다. 저장소 dry run의 $0.00은 단가 미입력 값이다.</p>"
    )
    body += (
        details("실행 전 계획", pre(read(ROOT / "budget-dry.json")))
        + details("전체 검증 지표", pre(summary))
        + details("수집 규약과 한계", pre(read(ROOT / "protocol.json")))
    )
    body += (
        details("기획 원본", pre(plan))
        + details("특질 시트 원본", pre(read(char / "s7-traits/tr1/trait-sheet.json")))
        + details("G6 긴 프롬프트 원본", pre(pair["long"]["text"]))
        + details("G6 짧은 프롬프트 원본", pre(pair["short"]["text"]))
    )
    body += (
        "<p>로컬 원본: "
        + esc(str(ROOT))
        + ". 최초 시도와 재시도 요청·응답은 evidence/에, 단계 작업 공간과 관문 기록은 runs/characters/에, 장면별 발화는 dialogues/에 있다.</p></section>"
    )
    body += section(
        "이번 시험의 한계와 돌리지 않은 것", "<p>" + esc(findings["limitations"]) + "</p>"
    )
    body += section(
        "생성 및 형식 실패 판정의 첫 원문",
        "<p>첫 출력을 지우지 않았다. 아래 원문은 채택된 산출물뿐 아니라 계약 오류와 출력 제한에 걸린 시도까지 포함한다.</p>"
        + "".join(
            details(
                m["ref"] + " · " + m["key"],
                pre((RAW / (m["key"] + ".request.json")).read_text())
                + pre((RAW / (m["key"] + ".response.json")).read_text()),
            )
            for m in metas
            if m["kind"] == "AGENT"
            or (
                m["kind"] == "JUDGE"
                and read(RAW / (m["key"] + ".response.json"))["choices"][0]["finish_reason"]
                != "stop"
            )
        ),
    )
    style = """*{box-sizing:border-box} :root{--paper:#faf9f6;--ink:#242623;--muted:#62675f;--line:#d8dcd2;--accent:#3d644b;--space:24px;color-scheme:light}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.75 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}main{max-width:1120px;margin:auto;padding:56px 28px 100px}header{max-width:790px;margin-bottom:40px}h1{font-size:clamp(32px,5vw,54px);line-height:1.18;letter-spacing:-.035em;margin:16px 0 24px}h2{font-size:28px;letter-spacing:-.025em;margin:0 0 24px}h3{font-size:21px;margin:24px 0 12px}h4{font-size:19px;border-bottom:2px solid var(--ink);padding-bottom:10px}h5{font-size:14px;font-family:monospace;font-weight:500;margin:0 0 20px;color:var(--muted)}.date,.speaker{font-size:13px;letter-spacing:.02em;color:var(--muted)}.lead{font-size:21px}.speaker{margin:20px 0 4px}.actor{color:var(--accent);font-weight:600}a{color:var(--accent);text-underline-offset:4px}nav{display:flex;gap:24px;flex-wrap:wrap;border-block:1px solid var(--line);padding:16px 0}section{margin-top:56px}article{margin:28px 0}.turn{border-left:3px solid var(--line);padding:22px 24px;background:white;scroll-margin-top:18px}.utterance{white-space:pre-wrap;max-width:820px}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px;text-align:left}th{font-weight:600;white-space:nowrap}td,th{padding:14px 16px;border-bottom:1px solid var(--line);vertical-align:top}td{min-width:130px}details{border-top:1px solid var(--line);padding:12px 0;margin-top:16px}summary{cursor:pointer;color:var(--accent);font-size:14px}summary:focus-visible,a:focus-visible{outline:2px solid var(--accent);outline-offset:5px}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:650px;overflow:auto;background:#f1f2ed;padding:20px;font:13px/1.65 ui-monospace,monospace}p{overflow-wrap:anywhere}.refs{font-size:14px}.scene{border-top:1px solid var(--line);padding-top:24px}@media(max-width:600px){main{padding:28px 16px 60px}.turn{padding:16px}nav{gap:16px}td,th{padding:10px}}@media print{body{background:white}main{max-width:none;padding:0}.turn{break-inside:avoid}details{display:none}nav{display:none}a{color:inherit}}"""
    out = REPO / "docs/reports/2026-10-28-persona-quality.html"
    out.write_text(
        '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>차은결 페르소나 실제 API 품질 보고서</title><style>'
        + style
        + "</style></head><body><main>"
        + body
        + "</main></body></html>"
    )
    print(out, out.stat().st_size, "bytes")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
