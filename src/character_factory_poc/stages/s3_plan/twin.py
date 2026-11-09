"""G0가 승인한 원문에서 한 사람의 기획을 정리하고 G3에서 인용과 대조한다.

D-0148: 원문 전체의 답을 상황·반응으로 표시해 되풀이된 경향을 센다.
평소 행동과 상황별 첫 행동은 경향에만 묶는다.
"""

from __future__ import annotations

import json
import re
from html import escape
from pathlib import Path

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.errors import AgentFormatError, CheckFailed, FactoryError
from character_factory_poc.common.names import normalize_name
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import (
    next_rev,
    read_json,
    write_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.contracts.planning import CHAPTER_SLOTS, CharacterPlanV2, PlanVariants
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import SOURCE, read_origin
from character_factory_poc.providers.base import ChatRequest, Message, extract_json_object
from character_factory_poc.stages.s0_source.run import STAGE_DIR, load_approved_source
from character_factory_poc.stages.s1_reference.ranking import all_names, load_ranking
from character_factory_poc.stages.s3_plan import tendencies as T
from character_factory_poc.stages.s3_plan.check_v2 import check_plan_v2, name_guard
from character_factory_poc.stages.s3_plan.speech_profile import (
    MIN_SENTENCES,
    build_speech_profile,
    render_voice_definition,
)

_ARCS = {
    "FAN_CALL": (
        ("첫 통화", "팬과 처음 인사를 나눈다."),
        ("친해지기", "서로 익숙한 주제로 이야기를 이어 간다."),
        ("단골 팬", "다시 전화한 팬과 반갑게 안부를 나눈다."),
    ),
    "FAMILY_CALL": (
        ("안부", "가족끼리 안부를 묻는다."),
        ("일상", "오늘 있었던 일을 함께 이야기한다."),
        ("속마음", "나누고 싶은 마음을 편하게 이야기한다."),
    ),
}
_LABELS = {
    "age": "나이",
    "gender": "성별",
    "job": "직업",
    "tagline": "한 줄 소개",
    "background": "배경",
    "coreTraits": "평소 행동",
    "contrastTrait": "평소와 다른 반응",
    "choices": "상황과 첫 행동",
    "lifeAndTastes": "생활과 취향",
    "wantsAndFears": "바라는 것과 걱정",
    "misreadings": "오해받는 지점",
    "voiceSummary": "말투",
    "voiceExamples": "말투 예시",
    "boundaries": "관계의 경계",
    "notes": "메모",
}
_FACT_FIELDS = {"age", "gender", "job", "background", "tagline"}
#: D-0148: 한 번 나온 말이 아니라 되풀이된 경향에서만 쓰는 칸.
TENDENCY_FIELDS = ("coreTraits", "choices")


def _sample(rows: list[dict], cap: int, must: list[str] = ()) -> list[dict]:
    """원문 전체에 걸쳐 대상 발화와 같은 대화의 바로 앞 줄을 짝지어 뽑는다.

    D-0148: must(경향 예시, 앞쪽이 먼저)를 상한의 3분의 1까지 먼저 넣고 나머지를 고르게 뽑는다.
    """
    subjects = [i for i, r in enumerate(rows) if r["speaker"] == "SUBJECT"]
    if not subjects:
        raise CheckFailed("s3", ["SUBJECT 발화가 필요하다"])
    selected: set[int] = set()
    where = {rows[i]["msgId"]: i for i in subjects}
    reserve = cap // 3
    for i in (where[m] for m in must if m in where):
        if len(selected) >= reserve:
            break
        selected.add(i)
        if len(selected) < cap and i and rows[i - 1]["convId"] == rows[i]["convId"]:
            selected.add(i - 1)
    n = min(len(subjects), max(1, cap // 2))
    anchors = [subjects[k * (len(subjects) - 1) // max(1, n - 1)] for k in range(n)]
    for i in (*anchors, *subjects):
        if i in selected:
            continue
        if len(selected) >= cap:
            break
        selected.add(i)
        if len(selected) < cap and i and rows[i - 1]["convId"] == rows[i]["convId"]:
            selected.add(i - 1)
    return [
        {k: rows[i][k] for k in ("msgId", "convId", "speaker", "text")} for i in sorted(selected)
    ]


def _chapters(template: str) -> list[dict]:
    return [
        dict(
            chapterId=ch,
            slot=s["slot"],
            entryStage=s["entry"],
            targetStage=s["target"],
            title=title,
            arc=arc,
        )
        for (ch, s), (title, arc) in zip(CHAPTER_SLOTS.items(), _ARCS[template], strict=True)
    ]


def _speech_endings(rows: list[dict]) -> dict[str, int]:
    """메시지 끝에서 식별되는 일부 한국어 종결형만 센다. 미분류를 반말로 보지 않는다."""
    counts = {"politeEnding": 0, "casualEnding": 0, "unclassified": 0}
    for row in rows:
        if row["speaker"] != "SUBJECT":
            continue
        text = row["text"].rstrip(" .!?…~\n\t")
        if re.search(r"(?:[가-힣]요|니다|니까)$", text):
            counts["politeEnding"] += 1
        elif re.search(r"(?:했어|할게|거야|잖아|먹었니|했니|할래)$", text):
            counts["casualEnding"] += 1
        else:
            counts["unclassified"] += 1
    return counts


def _guard(char_dir: Path, rows: list[dict], display: str) -> list[dict]:
    # 모티브는 S1이 없어도 실행한다. 다른 캐릭터의 순위·원문은 열지 않는다.
    role_names = {"user", "other", "나", "기자", "질문자", "사용자"}
    names = {
        r["name"]
        for r in rows
        if r["speaker"] != "SUBJECT"
        and normalize_name(r["name"]) not in role_names
        and not re.fullmatch(r"참여자\d+", r["name"])
    }
    for path in (char_dir / "s1-reference").glob("*/ranking.json"):
        names.update(all_names(load_ranking(read_json(path))))
    return name_guard(sorted(n for n in names if normalize_name(n) != normalize_name(display)))


def _claims(plan: CharacterPlanV2) -> dict[str, list]:
    fields = {key: getattr(plan, key) for key in _LABELS}
    fields.update({f"profileCard.{k}": v for k, v in dump(plan.profileCard).items()})
    return {key: v if isinstance(v, list) else [v] for key, v in fields.items() if v}


def _fact_in_quote(field: str, value, quote: str) -> bool:
    if field == "age":
        return re.search(rf"(?<!\d){value}\s*(?:세|살)", quote) is not None
    if field == "gender":
        labels = {
            "male": ("남성", "남자", "male"),
            "female": ("여성", "여자", "female"),
            "other": ("기타", "other"),
        }
        return any(
            re.search(rf"(?<![a-z]){label}(?![a-z])", quote.lower()) for label in labels[value]
        )
    if field == "job":
        return value in quote
    return True


def _check(source: dict, sample: list[dict], guard: list[dict], tendencies: dict | None = None):
    messages = {r["msgId"]: r for r in sample}
    cells = (tendencies or {}).get("answerCells", {})
    enforced = bool((tendencies or {}).get("enforced"))

    def check(plan: CharacterPlanV2) -> list[str]:
        problems = check_plan_v2(None, guard)(plan)
        if plan.name != source["displayName"]:
            problems.append("name: 대상 인물의 displayName과 달라서는 안 된다")
        if any(getattr(plan, k) != v for k, v in source["ids"].items()):
            problems.append("ids: 승인한 출처의 캐릭터·revision·후보 ID를 그대로 쓴다")
        if [dump(ch) for ch in plan.chapterArc] != source["chapterArc"]:
            problems.append("chapterArc: 선택한 통화 틀의 제목과 흐름을 그대로 쓴다")
        if plan.selectedTraits or plan.appearanceRev is not None:
            problems.append("selectedTraits·appearanceRev: 브리프나 외모로 인물을 정리하지 않는다")
        situations = [c.situation.strip() for c in plan.choices]
        if len(set(situations)) != len(situations):
            problems.append("choices: 같은 상황을 여러 선택으로 중복해 쓰지 않는다")
        claims = _claims(plan)
        for key in plan.evidence.keys() - claims.keys():
            problems.append(f"evidence.{key}: 대응하는 기획 칸이 없다")
        for key, values in claims.items():
            refs = plan.evidence.get(key, [])
            if len(values) != len(refs):
                hint = f" 또는 knownFacts.{key}" if key in _FACT_FIELDS else ""
                problems.append(
                    f"{key}: {len(values)}개 항목 각각에 SUBJECT 원문{hint} 근거가 필요하다"
                )
            for i, (value, ev) in enumerate(zip(values, refs, strict=False)):
                loc = f"{key}[{i}]"
                if isinstance(value, str) and not value.strip():
                    problems.append(f"{loc}: 공백만으로는 칸을 채울 수 없다")
                if ev.kind == "SOURCE":
                    row = messages.get(ev.ref)
                    if row is None:
                        problems.append(f"{loc}: 승인 원문 표본에 없는 msgId: {ev.ref}")
                    elif row["speaker"] != "SUBJECT":
                        problems.append(f"{loc}: SUBJECT의 발화만 인용할 수 있다")
                    elif not ev.quote.strip() or ev.quote not in row["text"]:
                        problems.append(f"{loc}: quote가 해당 메시지 원문의 일부가 아니다")
                    elif key == "voiceExamples" and value != ev.quote:
                        problems.append(f"{loc}: 말투 예시는 실제 인용과 같아야 한다")
                    elif not _fact_in_quote(key, value, ev.quote):
                        problems.append(
                            f"{loc}: 인용에 값이 명시되어 있지 않다. knownFacts.{key}가 필요하다"
                        )
                    elif enforced and key in TENDENCY_FIELDS and not cells.get(ev.ref):
                        problems.append(
                            f"{loc}: 주요 경향(자리 {T.MIN_OCCASIONS}곳 이상, 그 상황 답의 "
                            f"{T.MAIN_SHARE:.0%} 이상)의 답을 근거로 쓴다(tendencies.answerCells에 "
                            "있는 msgId). 드물게 나온 말은 lifeAndTastes 같은 생활 칸에 둔다"
                        )
                elif ev.kind == "USER" and key in _FACT_FIELDS:
                    fact = ev.ref.removeprefix("knownFacts.")
                    allowed = {key, "relation"} if key == "background" else {key}
                    matches = str(value) == ev.quote or (
                        key in {"age", "gender"} and _fact_in_quote(key, value, ev.quote)
                    )
                    if (
                        ev.ref != f"knownFacts.{fact}"
                        or fact not in allowed
                        or not ev.quote.strip()
                        or source["knownFacts"].get(fact) != ev.quote
                        or not matches
                    ):
                        problems.append(f"{loc}: 값과 일치하는 knownFacts.{key}가 필요하다")
                else:
                    problems.append(f"{loc}: SUBJECT의 SOURCE 근거가 필요하다")
        return problems

    return check


def codex_checks(stage: str, workspace: Path) -> tuple[str, list]:
    if stage != "s3-twin":
        raise ValueError(f"모티브 기획 검사가 없는 단계: {stage}")
    root = workspace / "inputs"
    return "character-plan-v2", [
        _check(
            *(
                read_json(root / f"{k}.json")
                for k in ("source", "corpus-sample", "name-guard", "tendencies")
            )
        )
    ]


def _tendency_section(agg: dict | None) -> str:
    """D-0148: G3에서 기획의 특질이 원문 전체의 어떤 경향에서 왔는지 본다."""
    if agg is None:
        return ""
    head = (
        f"대상 답 {agg['answers']}개 가운데 {agg['tagged']}개를 상황·반응으로 표시했다. "
        f"서로 다른 자리(영상·글과 날짜) {agg['minOccasions']}곳 이상에서, 그 상황 답의 "
        f"{agg.get('mainShare', T.MAIN_SHARE):.0%} 이상에서 나온 반응만 "
        "특질로 쓰는 주요 경향으로 본다. "
        "표시는 모델이 했으므로 인용이 반응과 맞는지 함께 본다."
    )
    if not agg["enforced"]:
        head += " 경향 칸이 적어 이번 기획은 경향 묶음 검사를 하지 않았다."
    body = []
    for sit, total in agg["situations"].items():
        rows = [r for r in agg["rows"] if r["situation"] == sit and T.is_main(r)][:4]
        if not rows:
            continue
        moves = "\n".join(
            f"{T.MOVES[r['move']]} {r['share']:.0%} · 자리 {r['occasions']}곳"
            + (f" · {r['years'][0]}~{r['years'][1]}" if r["years"] else "")
            for r in rows
        )
        quotes = "\n".join(f"“{r['examples'][0]['quote']}”" for r in rows if r["examples"])
        body.append(
            f"<tr><th scope='row'>{escape(T.SITUATIONS[sit])}<br>답 {total}개</th>"
            f"<td>{escape(moves)}</td><td>{escape(quotes)}</td></tr>"
        )
    thin = ", ".join(T.SITUATIONS[s] for s in agg["thinSituations"])
    note = (
        f"<p>원문 근거가 적은 상황: {escape(thin)}. 이 상황의 반응은 지어내지 않는다. "
        "필요하면 사람이 정하거나 원문을 보탠다.</p>"
        if thin
        else ""
    )
    return (
        f"<h2>원문 경향</h2><p>{escape(head)}</p><table><thead><tr><th>상황</th>"
        f"<th>되풀이된 반응</th><th>대표 인용</th></tr></thead><tbody>{''.join(body)}</tbody>"
        f"</table>{note}"
    )


def _profile_section(profile: dict | None, summary: str) -> str:
    """D-0145: G3에서 말투 칸이 어떤 원문 통계로 만들어지는지 함께 본다."""
    if profile is None:
        return ""
    ans = profile["answers"]
    stats = [
        ("대상 발화(기사 제외)", f"{profile['subjectMessages']}개, 문장 {profile['sentences']}개"),
        ("존댓말 어미 비율", f"{profile['politeShare']:.0%}"),
        (
            "'~것 같' 비율",
            f"{profile['hedgeShare']:.0%}"
            + "".join(
                f" · {label} {b['share']:.0%}({b['count']})"
                for label, b in zip(
                    ("40자 미만", "40~150자", "150자 이상"),
                    (profile.get("hedgeByLength") or {}).values(),
                    strict=False,
                )
            ),
        ),
        (
            "답 길이",
            f"{ans['count']}개, 중앙값 {ans['medianChars']}자, "
            f"두 문장 이하 {ans['atMostTwoSentences']:.0%}, 80자 이하 {ans['atMost80Chars']:.0%}",
        ),
        (
            "'~구나'로 받은 답 · 끝난 문장",
            f"{ans['gunaOpenings']} · {profile.get('gunaSentenceEndings', 0)}",
        ),
        ("웃음 표기·이모티콘", f"{profile['laughShare']:.0%}"),
    ]
    top = sorted(profile["markersPer1000"].items(), key=lambda x: -x[1])[:8]
    stats.append(("담화 표지(어절 천 개당)", ", ".join(f"{m} {v}" for m, v in top)))
    rows = "".join(
        f"<tr><th scope='row'>{escape(k)}</th><td colspan='2'>{escape(v)}</td></tr>"
        for k, v in stats
    )
    note = (
        "원문 문장이 적어 말투 칸은 아래 말투 요약을 쓴다."
        if profile["sentences"] < MIN_SENTENCES
        else "말투 칸은 아래 문장으로 들어간다. 말투 예시 문장은 대화 프롬프트에 넣지 않는다."
    )
    preview = "\n".join(render_voice_definition(profile, summary))
    return (
        "<h2>원문 말버릇 통계</h2>"
        f"<table><tbody>{rows}</tbody></table><p>{escape(note)}</p>"
        f"<pre>{escape(preview)}</pre>"
    )


def _page(
    plan: CharacterPlanV2, source: dict, profile: dict | None = None, agg: dict | None = None
) -> str:
    rows = []
    cells = T.tendency_cells(agg) if agg else {}

    def row(label, value, evidence):
        rows.append(
            f"<tr><th scope='row'>{escape(label)}</th><td>{escape(value)}</td>"
            f"<td>{escape(evidence)}</td></tr>"
        )

    row("이름", plan.name, "출처 묶음 · 대상 인물 표시 이름")
    for field, values in _claims(plan).items():
        for val, ev in zip(values, plan.evidence[field], strict=True):
            if field == "choices":
                val = f"{val.situation}\n→ {val.firstMove}"
            elif isinstance(val, dict):
                val = json.dumps(val, ensure_ascii=False)
            who = "대상 발화" if ev.kind == "SOURCE" else "사람이 적은 사실"
            basis = ""
            if field in TENDENCY_FIELDS and ev.kind == "SOURCE" and agg:
                found = cells.get(ev.ref, [])
                basis = "\n경향: " + (
                    ", ".join(
                        T.MOVES[c.split("/")[1]] + f"({T.SITUATIONS[c.split('/')[0]]})"
                        for c in found
                    )
                    or "없음(한 번 나온 말)"
                )
            row(_LABELS.get(field, field), str(val), f"“{ev.quote}”\n{who} · {ev.ref}{basis}")
    counts = source["sharedSpeechEndings"]
    endings = (
        f"공통 원문 종결형: 존대 표지 {counts['politeEnding']}건, "
        f"반말 표지 {counts['casualEnding']}건, 미분류 {counts['unclassified']}건"
    )
    for arc in plan.chapterArc:
        row(arc.title, arc.arc, f"통화 틀 · {source['chapterTemplate']}\n{endings}")
    return f"""<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>G3 인물 정리 대조</title>
<style>body{{font:1rem/1.6 system-ui,sans-serif;max-width:68rem;margin:2rem auto;
padding:0 1rem;color:#252525}}
table{{width:100%;border-collapse:collapse}}
td,th{{text-align:left;padding:.65rem;vertical-align:top;
white-space:pre-line;overflow-wrap:anywhere;border-bottom:1px solid #ddd}}
thead,code{{background:#f6f6f6}} th:first-child{{width:16%}} td{{width:42%}}
pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style>
<main><h1>{escape(plan.name)} · 인물 정리 대조</h1>
<p>G3 / {escape(plan.planRev)} / 후보 v1 · 출처 {escape(source["sourceRev"])}</p>
<p>각 설명을 오른쪽 인용과 비교하세요. 인용이 실제로 그 판단을 뒷받침하는지도 확인하세요.</p>
<table><thead><tr><th>항목</th><th>기획 내용</th><th>원문 또는 출처</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table>
{_tendency_section(agg)}
{_profile_section(profile, plan.voiceSummary)}
<h2>검토 결과 기록</h2>
<p>이 후보를 선택하려면 다음 내용을 answer.json에 저장하고 검토자 이름을 적으세요.
수정이 필요하면 decision을 REQUEST_CHANGES로 바꾸고 reasons에 이유를 적으세요.</p>
<pre>{{"decision":"SELECT","selections":["v1"],"reviewer":"검토자"}}</pre>
<code>cfp gate import {escape(plan.characterId)} G3 --answer answer.json</code></main></html>"""


def _settings(ctx: Context) -> dict:
    cfg = ctx.config.stage("s3t")
    settings = {"max_agent_messages": 600, "max_check_retries": 3, "max_format_retries": 2}
    for key in settings:
        value = cfg.get(key, settings[key])
        if type(value) is not int or value < int(key == "max_agent_messages"):
            raise FactoryError(f"[stages.s3t] {key} 값이 올바르지 않다")
        settings[key] = value
    return settings


def plan_calls(ctx: Context, answers: int = 0) -> list[CallPlan]:
    cfg = _settings(ctx)
    return [
        CallPlan("s3-twin", f"원문 답 경향 표시 (답 {T.BATCH}개당 1회)", T.n_calls(answers), None),
        CallPlan(
            "s3-twin",
            "원문 기반 인물 정리 (재시도 포함)",
            1 + cfg["max_format_retries"] + cfg["max_check_retries"],
            None,
        ),
    ]


def _tags(ctx: Context, cid: str, base: Path, rev: str, source_rev: str, pairs, budget) -> list:
    """같은 승인 원문·같은 표시 지시로 앞 revision이 표시해 둔 결과가 있으면 다시 부르지 않는다."""
    for prev in sorted(base.glob("pr*/tendency-tags.json"), reverse=True):
        saved = read_json(prev)
        if saved.get("sourceRev") == source_rev and saved.get("promptSha") == T.prompt_sha():
            return saved["tags"]
    model = ctx.judge_model(cid, budget)
    system = T.tagging_prompt()

    def call(i: int, payload: str) -> dict:
        resp = model.complete(
            ChatRequest(
                kind="JUDGE",
                stage="s3",
                messages=(Message("system", system), Message("user", payload)),
                ref=f"{cid}/{rev}/tendencies/{i}",
                max_output_tokens=6000,
                temperature=0.0,
                response_json=True,
            )
        )
        try:
            return extract_json_object(resp.text)
        except ValueError:
            return {}

    return T.tag_all(pairs, call)


def run_s3_twin(ctx: Context, cid: str) -> Path:
    char_dir = ctx.character_dir(cid)
    if read_origin(char_dir) != SOURCE:
        raise FactoryError(f"{cid}: 원문 기반 기획은 모티브 캐릭터에만 있다")
    state = ctx.state(cid)
    state.require_deps("s3")
    if state.stage("s3").status == "AWAITING_HUMAN":
        raise FactoryError(f"{cid}: G3 검토 대기 중이다")
    pack, index, corpus = load_approved_source(ctx, cid)
    cfg = _settings(ctx)
    budget = ctx.budget()
    kinds = {t.textId: t.kind for t in index.texts}
    pairs = T.pair_answers(corpus, kinds)
    budget.check_plan(plan_calls(ctx, len(pairs)))
    base = char_dir / "s3-plan"
    rev = next_rev(base, "pr")
    folder = base / rev
    state.transition("s3", "RUNNING", rev=rev)
    try:
        tags = _tags(ctx, cid, base, rev, index.sourceRev, pairs, budget)
        agg = T.aggregate(pairs, tags)
        # 기획이 검사에 걸려도 다음 revision이 표시를 다시 부르지 않도록 먼저 남긴다.
        write_once_json(
            folder / "tendency-tags.json",
            {"sourceRev": index.sourceRev, "promptSha": T.prompt_sha(), "tags": tags},
        )
        write_once_json(folder / "tendencies.json", agg)
        sample = _sample(corpus, cfg["max_agent_messages"], T.example_ids(agg))
        sample_ids = {r["msgId"] for r in sample if r["speaker"] == "SUBJECT"}
        member = T.tendency_cells(agg)
        tendencies = {
            **T.agent_view(agg),
            "answerCells": {m: c for m, c in member.items() if m in sample_ids},
        }
        # v2의 필수 seedRev 자리에 G0 revision 번호를 대응시키고 원래 spN도 보존한다.
        seed = "sd" + index.sourceRev.removeprefix("sp")
        ids = dict(characterId=cid, planRev=rev, seedRev=seed, variantId="v1")
        source = dict(
            ids=ids,
            sourceRev=index.sourceRev,
            displayName=pack.subject.displayName,
            knownFacts=pack.knownFacts,
            chapterTemplate=pack.chapterTemplate,
            chapterArc=_chapters(pack.chapterTemplate),
            # 원문에는 챕터 표지가 없으므로 챕터 사이 말높임 변화를 추정하지 않는다.
            sharedSpeechEndings=_speech_endings(corpus),
        )
        guard = _guard(char_dir, corpus, pack.subject.displayName)
        check = _check(source, sample, guard, tendencies)
        spec = AgentSpec(
            role="source_planner",
            output_contract="character-plan-v2",
            stage="s3-twin",
            max_format_retries=cfg["max_format_retries"],
            max_check_retries=cfg["max_check_retries"],
        )
        inputs = {
            "source": source,
            "corpus-sample": sample,
            "name-guard": guard,
            "tendencies": tendencies,
            "output-schema": CharacterPlanV2.model_json_schema(),
        }
        result = run_agent(
            spec,
            folder / "workspace",
            inputs,
            [check],
            ctx.text_model(cid, budget),
            ref=f"{cid}/{rev}/s3-twin",
            backend=ctx.agent_backend(cid, budget, "s3-twin"),
        )
        if not result.ok:
            raise CheckFailed("s3", result.problems)
        plan = result.output
        # codex_exec의 작업 파일이 아닌 처음 승인 원문에서 만든 검사로 출판 직전 다시 확인한다.
        for key, expected in inputs.items():
            path = folder / "workspace/inputs" / f"{key}.json"
            if not path.exists() or read_json(path) != expected:
                raise CheckFailed("s3", [f"작업 중 입력이 바뀌었다: {key}"])
        if problems := check(plan):
            raise CheckFailed("s3", problems)
        variants = PlanVariants(
            characterId=cid,
            planRev=rev,
            seedRev=seed,
            seedSha256=sha256_file(char_dir / STAGE_DIR / index.sourceRev / "source-pack.json"),
            mode="variants",
            candidates=[plan],
        )
        write_once_json(folder / "variants.json", dump(variants))
        # D-0145: S8 말투 칸과 같은 함수로 계산한다. 비교 세트는 corpus에 없다.
        profile = build_speech_profile(corpus, kinds)
        write_once_json(folder / "speech-profile.json", profile)
        write_once_text(folder / "gate-G3.html", _page(plan, source, profile, agg))
        write_manifest(folder)
    except (AgentFormatError, CheckFailed) as exc:
        failure = (
            exc
            if isinstance(exc, CheckFailed)
            else CheckFailed(
                "s3", [str(exc), "필수 사실이 없다면 해당 knownFacts 칸 또는 대상 발화를 보강한다"]
            )
        )
        state.transition("s3", "CHECK_FAILED", rev=rev, error=str(failure))
        if failure is exc:
            raise
        raise failure from exc
    state.transition("s3", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G3", "AWAITING_HUMAN", rev, None)
    return folder
