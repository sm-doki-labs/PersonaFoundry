"""Measured speech distribution for the evidence-v4 VOICE section.

Only counts, ratios and open grammatical notation are rendered. Sample sentences,
interjections and quoted openers are never emitted, so the prompt carries no example
utterances (D-0196). Small profiles render nothing and leave VOICE to the cards.
"""

from __future__ import annotations

import re

from character_factory_poc.stages.s3_plan.speech_profile import MIN_ANSWERS, MIN_MARKER_COUNT

# Ending buckets measured by speech_profile, rendered as open grammatical notation.
# Every quoted form is immediately labelled so the example checker accepts it as notation.
_ENDINGS = (
    ("haeyo", "'-어요/-아요' 종결어미"),
    ("jyo", "'-죠' 종결어미"),
    ("janayo", "'-잖아요' 종결어미"),
    ("geodeunyo", "'-거든요' 종결어미"),
    ("neyo", "'-네요' 종결어미"),
)
_FORMAL = ("formal", "hedgeFormal")
_CONNECTORS = {
    "는데": "'-는데' 연결어미",
    "기 때문에": "'-기' 명사형 어미에 인과 의존 표현을 붙인 구성",
    "그래서": "인과 접속부사",
    "그러다 보니까": "경과를 잇는 '-다' 연결어미 구성",
    "고 또": "'-고' 연결어미 뒤 첨가 부사",
}
_RESPONSE_OPENERS = {"아", "어", "네", "예", "음", "그렇죠", "맞아요"}
_SELF_OPENERS = {"저는", "제가", "저도", "나는", "내가", "나도"}
# Counted fillers described by word class and discourse function only; the words
# themselves are never rendered (no example utterances, D-0196).
_FILLER_CLASSES = (
    ("hesitation", ("어", "음"), "문두나 절 사이에 홀로 끼는 망설임 간투사"),
    ("vague", ("뭐",), "부정칭 대명사에서 굳어져 단정을 흐리는 담화 표지"),
    ("temporal", ("이제",), "시간 부사에서 굳어져 다음 말을 예고하는 담화 표지"),
    (
        "degree",
        ("좀", "약간", "막", "그냥"),
        "서술어 앞에 붙어 정도를 누그러뜨리는 부사형 담화 표지",
    ),
    ("deictic", ("이렇게", "어떻게 보면"), "말을 고르며 시간을 버는 지시·관점 부사구"),
)


def _topic(word: str) -> str:
    """Attach the topic particle with the right allomorph (받침 -> 은, otherwise 는)."""
    last = word[-1] if word else ""
    if "가" <= last <= "힣":
        return word + ("은" if (ord(last) - 0xAC00) % 28 else "는")
    return word + "는"


_CASUAL_SHARE = 0.2
_JAMO = re.compile(r"[ㄱ-ㅎㅏ-ㅣ]+")


def _casual_endings_line(c: dict, ends: dict) -> str | None:
    """Endings for a speaker who mostly uses 반말 (politeShare <= 0.2).

    The polite-ending line counts only 존댓말 buckets, so for a 반말 speaker it described the
    few polite endings as the whole distribution. This line counts the 반말 buckets as well.
    Polite speakers keep the existing line unchanged.
    """
    if c.get("politeShare", 1) > _CASUAL_SHARE:
        return None
    polite = sum(ends.get(k, 0) for k, _ in _ENDINGS) + sum(ends.get(k, 0) for k in _FORMAL)
    parts = [
        ("반말 종결어미", ends.get("casual", 0)),
        ("평서형 종결어미", ends.get("plainDa", 0)),
        ("연결어미로 끊어 맺는 문장", ends.get("open", 0)),
        ("존댓말 종결어미", polite),
    ]
    known = sum(n for _, n in parts)
    if known < MIN_ANSWERS:
        return None
    line = (
        "상대높임과 종결어미: 반말이 기본이고 존댓말은 드물다. 어미가 분류된 문장 가운데 "
        + ", ".join(f"{label} {_pct(n / known)}" for label, n in parts)
        + "다."
    )
    other = ends.get("other", 0)
    if other:
        line += (
            f" 전체 문장의 {_pct(other / (other + known))}는 어미 없이 명사·감탄·웃음 표기 등으로"
            " 끝나 분류되지 않았다."
        )
    return line


def _pct(x: float) -> str:
    return f"{x:.0%}"


def _filler_forms(counts: dict, habit: set) -> list[tuple[str, float]]:
    """Share of counted fillers per word class, largest first; classes under 5% are dropped."""
    sizes = [
        (label, sum(counts.get(w, 0) for w in words if w not in habit))
        for _, words, label in _FILLER_CLASSES
    ]
    total = sum(n for _, n in sizes)
    if total < MIN_MARKER_COUNT:
        return []
    return [
        (label, n / total) for label, n in sorted(sizes, key=lambda x: -x[1]) if n / total >= 0.05
    ]


# Voice line styles. None keeps the original wording, which existing reviewed packets were
# compiled with. HABITS_STYLE states habit words by name and as a usage rate instead of an
# upper bound: the bound wording made the chat model drop them entirely (Son: 0 of 18 answers
# with a filler versus 55% in the source at the same length; named wording gave 11 of 18).
HABITS_STYLE = "named-habits-v1"
_HABIT_EXTRA = ("되게", "완전")


def _habit_line(c: dict) -> str | None:
    from character_factory_poc.stages.s3_plan.speech_profile import FILLERS, LENGTH_BANDS

    habit = list(c.get("habitWords") or ())
    share = c.get("habitShare") or 0
    bands = c.get("fillerByLength") or {}
    counts = c.get("markerCounts") or {}
    pool = dict.fromkeys([*habit, *_HABIT_EXTRA, *(f for f in FILLERS if " " not in f)])
    words = [
        w
        for w, n in sorted(((w, counts.get(w, 0)) for w in pool), key=lambda x: -x[1])
        if n >= MIN_MARKER_COUNT
    ][:6]
    if not habit and not words:
        return None
    (s_name, _, s_hi), (m_name, _, m_hi), (l_name, _, _) = LENGTH_BANDS
    enough = {k: bands.get(k, {}).get("count", 0) >= MIN_ANSWERS for k in (s_name, m_name, l_name)}
    medium = bands.get(m_name, {}).get("avgPerAnswer", 0) if enough[m_name] else 0
    if share >= 0.1 or medium >= 0.3:
        line = "말버릇: 정도부사와 군말을 자주 섞어 말한다."
        if words:
            line += f" 많이 쓰는 말은 {'·'.join(words)} 순이다."
        parts = []
        if enough[m_name]:
            parts.append(f"{s_hi}~{m_hi}자 답에는 군말이 답당 약 {medium:.1f}개")
        if enough[l_name]:
            parts.append(f"{m_hi}자가 넘는 답에는 약 {bands[l_name]['avgPerAnswer']:.1f}개")
        if parts:
            line += " " + ", ".join(parts) + " 섞이고"
            if enough[s_name]:
                line += (
                    f", {s_hi}자 미만 단답에는 답당 {bands[s_name]['avgPerAnswer']:.1f}개로 드물다."
                )
            else:
                line += "다."
        if habit and share:
            line += f" 정도부사 {_topic('·'.join(habit))} 일상 답의 약 {_pct(share)}에 나온다."
        return line + " 다듬은 문어체로 바꾸지 않고 생각을 고르며 이어 가는 구어로 말한다."
    line = "말버릇: 정도부사와 군말은 드물다."
    if habit:
        line += f" 정도부사 {_topic('·'.join(habit))} 일상 답의 약 {_pct(share)}에만 나온다."
    if c.get("fillerPer100Chars"):
        line += f" 군말은 글자 100자당 {c['fillerPer100Chars']:.1f}개다."
    return line


def measured_voice_lines(profile: dict | None, style: str | None = None) -> list[str]:
    if style not in (None, HABITS_STYLE):
        raise ValueError("알 수 없는 말투 측정 문장 형식이다")
    named = style == HABITS_STYLE
    if not profile:
        return []
    c = profile.get("casual") or profile
    ans = c.get("answers") or {}
    if ans.get("count", 0) < MIN_ANSWERS:
        return []
    lines = [
        f"측정 기준: 원문에서 대상 인물의 답 {ans['count']}개를 센 분포다. "
        "매 답을 맞추는 목표가 아니라 전체 대화의 분포로 따른다."
    ]
    ends = c.get("endings") or {}
    known = sum(ends.get(k, 0) for k, _ in _ENDINGS) + sum(ends.get(k, 0) for k in _FORMAL)
    casual = _casual_endings_line(c, ends)
    if casual:
        lines.append(casual)
    elif known >= MIN_ANSWERS:
        parts = [
            f"{label} {_pct(ends.get(k, 0) / known)}"
            for k, label in _ENDINGS
            if ends.get(k, 0) >= MIN_MARKER_COUNT
        ]
        formal = sum(ends.get(k, 0) for k in _FORMAL)
        parts.append(f"하십시오체 '-습니다/-ㅂ니다' 종결어미 {_pct(formal / known)}")
        level = "해요체가 기본이다" if c.get("politeShare", 0) >= 0.8 else "말높임이 섞인다"
        line = f"상대높임과 종결어미: {level}. 분류된 종결어미 분포는 " + ", ".join(parts) + "."
        f = profile.get("formal") or {}
        fe = f.get("endings") or {}
        fknown = sum(fe.get(k, 0) for k, _ in _ENDINGS) + sum(fe.get(k, 0) for k in _FORMAL)
        if fknown >= MIN_ANSWERS:
            share = sum(fe.get(k, 0) for k in _FORMAL) / fknown
            line += f" 공식 소감·각오를 말하는 자리에서는 하십시오체가 {_pct(share)}로 늘어난다."
        lines.append(line)
    lines.append(
        f"답 길이: 일상 질의응답의 답은 중앙값 {ans['medianChars']}자이고 "
        f"{_pct(ans['atMost80Chars'])}가 80자 이하, {_pct(ans['atMostTwoSentences'])}가 "
        f"두 문장 이하다. 길게 풀어도 90%가 {ans['p90Chars']}자 안에서 맺는다."
    )
    hedge = c.get("hedgeByLength") or {}
    if hedge.get("long", {}).get("count", 0) >= MIN_ANSWERS:
        lines.append(
            "단정 완화: '-는 것 같다' 구성은 짧은 답의 "
            f"{_pct(hedge['short']['share'])}, 두세 문장 답의 {_pct(hedge['medium']['share'])}, "
            f"긴 답의 {_pct(hedge['long']['share'])}에만 나온다. 짧은 답과 사실 확인 답은 "
            "대개 단정형 종결어미로 맺는다."
        )
        if named:
            lines[-1] = lines[-1].replace("에만 나온다.", "에 나온다.")
    conn = [
        (_CONNECTORS[k], n)
        for k, n in sorted((c.get("connectors") or {}).items(), key=lambda x: -x[1])
        if k in _CONNECTORS and n >= MIN_MARKER_COUNT
    ][:3]
    if conn:
        lines.append(
            "절 연결: 이유와 배경을 풀 때 "
            + ", ".join(f"{label}({n}회)" for label, n in conn)
            + "로 절을 잇는다."
        )
    if named:
        habit_line = _habit_line(c)
        if habit_line:
            lines.append(habit_line)
    if not named and c.get("habitWords") and c.get("habitShare"):
        lines.append(
            "강조 부사: 정도부사 어휘 "
            + _topic("·".join(c["habitWords"]))
            + f" 일상 답의 약 {_pct(c['habitShare'])}에만 나오고 한 답에 하나를 넘지 않는다."
        )
    filler = c.get("fillerByLength") or {}
    if (
        not named
        and filler.get("short", {}).get("count", 0) >= MIN_ANSWERS
        and c.get("fillerPer100Chars")
    ):
        line = (
            f"담화 표지: 말을 고르는 군말은 글자 100자당 {c['fillerPer100Chars']:.1f}개다. "
            f"짧은 답에는 답당 {filler['short']['avgPerAnswer']:.1f}개로 거의 없고"
        )
        if filler.get("long", {}).get("count", 0) >= MIN_ANSWERS:
            line += f", 긴 답에서는 답당 {filler['long']['avgPerAnswer']:.1f}개로 늘어난다."
        else:
            line = line[: -len("없고")] + "없다."
        lines.append(line)
        forms = _filler_forms(c.get("markerCounts") or {}, set(c.get("habitWords") or ()))
        if forms:
            lines.append(
                "군말의 형태: "
                + ", ".join(f"{label}({_pct(share)})" for label, share in forms)
                + " 순으로 쓴다. 군말은 문장 성분이 아니라 절 경계나 서술어 앞에 끼우고, "
                "답이 길어질수록 더 자주 섞인다. 말끔하게 다듬은 "
                "문어체보다 생각을 고르며 이어 가는 구어 구성에 가깝다."
            )
    first = ans.get("firstWords") or {}
    response = sum(n for w, n in first.items() if w in _RESPONSE_OPENERS) / ans["count"]
    self_start = sum(n for w, n in first.items() if w in _SELF_OPENERS) / ans["count"]
    # Openers written only in 자모 (consonant abbreviations, laughter) are a separate class.
    # firstWords keeps only the most frequent openers, so this share is a lower bound.
    jamo = sum(n for w, n in first.items() if w and _JAMO.fullmatch(w)) / ans["count"]
    if response or self_start or jamo:
        line = f"발화 개시: 답의 {_pct(response)}는 짧은 응답 표지나 감탄사로 열고, "
        if jamo >= 0.05:
            line += f"적어도 {_pct(jamo)}는 자음 약어나 웃음 표기로 열며, "
        line += f"{_pct(self_start)}는 1인칭 주어로 바로 연다. 나머지는 본론으로 곧장 들어간다."
        lines.append(line)
    if "repeatShare" in c:
        lines.append(f"반복: 같은 말을 되풀이하는 발화는 {_pct(c['repeatShare'])}로 드물다.")
    if named:
        lines.append(
            "우선순위: 이 분포는 아래 적용 상황별 특징보다 우선한다. 어미·완화·말버릇은 "
            "대화 전체에서 위 비율에 가깝게 맞추고, 지나치게 많이 쓰지도 빼 버리지도 않는다."
        )
    else:
        lines.append(
            "우선순위: 이 분포는 아래 적용 상황별 특징보다 우선한다. 특징에 같은 어미·완화·강조 "
            "형식이 나와도 대화 전체의 빈도는 위 비율을 넘기지 않는다."
        )
    return lines
