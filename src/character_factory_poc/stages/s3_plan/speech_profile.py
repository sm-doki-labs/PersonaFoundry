"""승인 원문의 말한 자리와 답 길이에 따라 모티브 말투 칸을 만든다."""

from __future__ import annotations

import re
import statistics
from collections import Counter
from itertools import pairwise

SCHEMA = "speech-profile-v1"
CONVERSATION_KINDS = frozenset({"KAKAO_EXPORT", "TRANSCRIPT"})
#: 말버릇 후보. 여러 낱말 표지는 문자열로, 한 낱말 표지는 어절 단위로 센다.
MARKERS = (
    "뭐", "또", "좀", "진짜", "정말", "너무", "너무나도", "이제", "그냥", "항상", "되게",
    "사실", "어떻게 보면", "약간", "일단은", "근데", "막", "완전", "아무튼", "그러니까",
)  # fmt: skip
#: 말을 고르며 끼우는 군말. 강조어(진짜·너무·정말)는 담화 표지 쪽에서 센다.
FILLERS = ("뭐", "이제", "좀", "그냥", "막", "약간", "이렇게", "어떻게 보면", "어", "음")
SELF_POLITE = ("저", "저는", "저도", "제가", "저를", "저한테", "제")
SELF_PLAIN = ("나", "나는", "나도", "내가", "나를", "나한테", "내")
#: (이름, 프롬프트 표기, 정규식, 존대 여부). 위에서부터 먼저 맞는 것 하나로 센다.
ENDINGS = (
    ("hedgePolite", "'~것 같아요'", r"(?:것|거) 같아요$", True),
    ("hedgeFormal", "'~것 같습니다'", r"(?:것|거) 같습니다$", True),
    ("geodeunyo", "'~거든요'", r"거든요$", True),
    ("janayo", "'~잖아요'", r"잖아요$", True),
    ("jyo", "'~죠'", r"죠$", True),
    ("neyo", "'~네요'", r"네요$", True),
    ("formal", "'~습니다'", r"(?:습니다|니다|니까)$", True),
    ("haeyo", "'~어요/~아요'", r"요$", True),
    ("plainDa", "'~다'", r"다$", False),
    ("casual", "반말 어미", r"(?:야|어|아|지|해|돼|거든|잖아|냐|니|래|게|자|네|구나)$", False),
    ("open", "연결어미", r"(?:고|는데|은데|지만|서|면|니까|구요|는데요)$", None),
)  # fmt: skip
LAUGH = re.compile(r"ㅋ{2,}|ㅎ{2,}|[ㅠㅜ]{2,}|\^\^|[\U0001F300-\U0001FAFF]")
CONNECTORS = ("는데", "기 때문에", "고 또", "그래서", "그러다 보니까", "그럼에도 불구하고")
SUFFIX_CONNECTORS = frozenset({"는데", "기 때문에", "고 또"})
#: 이 수보다 적게 관측되면 해당 항목을 쓰지 않는다.
MIN_SENTENCES = 30
MIN_ANSWERS = 20
MIN_MARKER_COUNT = 5


def _text_id(msg_id: str) -> str:
    return msg_id.rsplit("-", 1)[0]


def _clean(text: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", text).strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.?!])\s+|\n+", text)
    return [p.strip() for p in parts if len(re.sub(r"[^가-힣]", "", p)) >= 2]


def _bare_end(sentence: str) -> str:
    s = LAUGH.sub("", sentence)
    return re.sub(r"[\s.?!~…,·\"'”’)]+$", "", s)


def _ending(sentence: str) -> str:
    end = _bare_end(sentence)
    for name, _, pattern, _ in ENDINGS:
        if re.search(pattern, end):
            return name
    return "other"


def _words(text: str) -> list[str]:
    return [re.sub(r"[,.?!~…]+$", "", w) for w in text.split()]


#: (이름, 이상, 미만) 글자 수 구간. '~것 같' 비율을 나눠 센다.
LENGTH_BANDS = (("short", 0, 40), ("medium", 40, 150), ("long", 150, 10**9))


def _hedged(text: str) -> bool:
    return bool(re.search(r"(?:것|거) 같", text))


def _fillers(text: str) -> int:
    words = _words(text)
    return sum(words.count(f) for f in FILLERS if " " not in f) + sum(
        text.count(f) for f in FILLERS if " " in f
    )


def _repeats(text: str) -> bool:
    return bool(re.search(r"(?:^|\s)(\S{1,6}) \1(?:\s|$)", text))


def _rate(count: int, total: int) -> float:
    return round(count / total, 3) if total else 0.0


def _answer_pairs(corpus, kinds):
    for prev, row in pairwise(corpus):
        tid = _text_id(row["msgId"])
        if (
            row["speaker"] == "SUBJECT"
            and prev["speaker"] == "USER"
            and prev.get("convId") == row.get("convId")
            and _text_id(prev["msgId"]) == tid
            and kinds.get(tid) != "ARTICLE"
            and _clean(row["text"])
        ):
            yield prev, row


def _aggregate(corpus: list[dict], kinds: dict[str, str], *, casual_only: bool = False) -> dict:
    """corpus: 승인 원문(비교 세트 제외). kinds: textId → TextKind."""
    rows = [
        r
        for r in corpus
        if r["speaker"] == "SUBJECT" and kinds.get(_text_id(r["msgId"])) != "ARTICLE"
    ]
    texts = [_clean(r["text"]) for r in rows if _clean(r["text"])]
    sentences = [s for t in texts for s in _sentences(t)]
    ending_counts = Counter(_ending(s) for s in sentences)
    polite = sum(ending_counts[n] for n, *_, p in ENDINGS if p is True)
    plain = sum(ending_counts[n] for n, *_, p in ENDINGS if p is False)
    words = [w for t in texts for w in _words(t)]
    joined = " ".join(texts)
    marker_counts = {
        m: (joined.count(m) if " " in m else sum(w == m for w in words)) for m in MARKERS
    }
    openers = Counter(_words(t)[0] for t in texts if _words(t))
    self_polite = sum(w in SELF_POLITE for w in words)
    self_plain = sum(w in SELF_PLAIN for w in words)
    # 답: 같은 대화에서 상대 말 바로 뒤에 온 대상 발화
    answers = [
        (kinds.get(_text_id(r["msgId"]), ""), _clean(r["text"]))
        for _, r in _answer_pairs(corpus, kinds)
    ]
    talk = [a for k, a in answers if casual_only or k in CONVERSATION_KINDS]
    scope = "CONVERSATION" if len(talk) >= MIN_ANSWERS else "ALL"
    pool = talk if scope == "CONVERSATION" else [a for _, a in answers]
    lengths = sorted(len(a) for a in pool)
    first_words = Counter(_words(a)[0] for a in pool if _words(a))
    guna_open = sum(bool(re.search(r"구나", (_sentences(a) or [""])[0])) for a in pool)
    long_texts = [t for t in texts if len(t) > 150]
    return {
        "schemaVersion": SCHEMA,
        "subjectMessages": len(texts),
        "sentences": len(sentences),
        "eojeol": len(words),
        "endings": {n: ending_counts[n] for n, *_ in ENDINGS} | {"other": ending_counts["other"]},
        "politeShare": _rate(polite, polite + plain),
        "hedgeShare": _rate(sum(map(_hedged, texts)), len(texts)),
        # '~것 같'은 답이 길수록 많아진다. 길이를 빼고 한 비율만 주면 짧은 답에도 붙는다.
        "hedgeByLength": {
            name: {"count": len(group), "share": _rate(sum(map(_hedged, group)), len(group))}
            for name, group in (
                (name, [t for t in texts if lo <= len(t) < hi]) for name, lo, hi in LENGTH_BANDS
            )
        },
        "markersPer1000": {
            m: round(c * 1000 / len(words), 1) if words else 0.0 for m, c in marker_counts.items()
        },
        "markerCounts": marker_counts,
        "openers": dict(openers.most_common(12)),
        "selfReference": {"polite": self_polite, "plain": self_plain},
        "answers": {
            "scope": scope,
            "count": len(pool),
            "medianChars": statistics.median(lengths) if lengths else 0,
            "p90Chars": lengths[int(0.9 * (len(lengths) - 1))] if lengths else 0,
            "atMostTwoSentences": _rate(sum(len(_sentences(a)) <= 2 for a in pool), len(pool)),
            "atMost80Chars": _rate(sum(len(a) <= 80 for a in pool), len(pool)),
            "firstWords": dict(first_words.most_common(12)),
            "gunaOpenings": guna_open,
        },
        # '~구나'로 끝난 문장. 첫마디 다음 문장에서 상대 말을 되풀이하는 경우까지 센다.
        "gunaSentenceEndings": sum(bool(re.search(r"구나$", _bare_end(x))) for x in sentences),
        # 군말 밀도와 되풀이는 길이에 따라 다르다. 구간별로 세어 말결 문장에 쓴다.
        "fillerPer100Chars": round(100 * sum(map(_fillers, texts)) / max(1, len(joined)), 2),
        "fillerByLength": {
            name: {
                "count": len(group),
                "avgPerAnswer": round(statistics.mean(map(_fillers, group)), 2) if group else 0.0,
                "repeatShare": _rate(sum(map(_repeats, group)), len(group)),
            }
            for name, group in (
                (name, [t for t in texts if lo <= len(t) < hi]) for name, lo, hi in LENGTH_BANDS
            )
        },
        "longShare": _rate(len(long_texts), len(texts)),
        "connectors": {c: sum(t.count(c) for t in long_texts) for c in CONNECTORS},
        "repeatShare": _rate(
            sum(bool(re.search(r"(?:^|\s)(\S{1,6}) \1(?:\s|$)", t)) for t in texts), len(texts)
        ),
        "laughShare": _rate(sum(bool(LAUGH.search(t)) for t in texts), len(texts)),
    }


def _count_words(avg: float) -> str:
    return "0~1번" if avg < 0.5 else f"{max(1, round(avg))}번 안팎"


def _texture_sentence(profile: dict) -> str:
    """D-0147: 군말 밀도와 되풀이를 답 길이 구간별로 쓴다. 구간 근거가 모자라면 쓰지 않는다."""
    bands = profile.get("fillerByLength") or {}
    if not bands or any(bands[name]["count"] < MIN_ANSWERS for name, *_ in LENGTH_BANDS):
        return ""
    fillers = [
        f
        for f, _ in sorted(
            ((f, profile["markerCounts"].get(f, 0)) for f in FILLERS), key=lambda x: -x[1]
        )
        if _ >= MIN_MARKER_COUNT
    ][:5] or list(FILLERS[:4])
    short, medium, long = (bands[name] for name, *_ in LENGTH_BANDS)
    line = (
        f"말결: 생각을 고르며 {_quote_list(fillers)} 같은 군말을 끼운다. 한 답의 군말 수는 "
        f"한두 마디 짧은 답이 {_count_words(short['avgPerAnswer'])}, "
        f"두세 문장 답이 {_count_words(medium['avgPerAnswer'])}, "
        f"길게 말하는 답이 {_count_words(long['avgPerAnswer'])}이다"
        f"(글자 100자에 {profile['fillerPer100Chars']:.1f}번 꼴). 말끔하게 정리된 문장보다 "
        "생각나는 대로 이어 가는 말에 가깝다."
    )
    if long["repeatShare"] >= 0.05:
        line += (
            f" 길게 말할 때는 같은 말을 한 번 더 되풀이하거나 고쳐 잇는 일이 "
            f"{_tenths(long['repeatShare'])} 정도 있다."
        )
    return line


def _hedge_sentence(profile: dict) -> str:
    """D-0145: '~것 같' 비율을 답 길이 구간별로 쓴다. 구간 근거가 모자라면 전체 비율 하나를 쓴다."""
    if profile["hedgeShare"] < 0.1:
        return ""
    bands = profile.get("hedgeByLength") or {}
    if bands and all(bands[name]["count"] >= MIN_ANSWERS for name, *_ in LENGTH_BANDS):
        return (
            " 자기 생각과 느낌을 '~것 같아요'로 누그러뜨려 맺는 정도는 길이에 따라 다르다."
            f" 한두 마디 짧은 답(40자 미만)에서는 {_tenths(bands['short']['share'])},"
            f" 두세 문장 답(40~150자)에서는 {_tenths(bands['medium']['share'])},"
            f" 길게 생각을 말하는 답(150자 이상)에서는 {_tenths(bands['long']['share'])} 정도다."
        )
    return (
        " 자기 생각과 느낌은 '~것 같아요'로 누그러뜨려 맺는다"
        f"(발화 {_tenths(profile['hedgeShare'])})."
    )


def _tenths(share: float) -> str:
    n = round(share * 10)
    if n >= 10:
        return "거의 모두"
    if n <= 0:
        return "열에 하나도 안 되게"
    return f"열에 {n}"


def _josa(word: str, with_final: str, without_final: str) -> str:
    """마지막 글자 받침에 맞는 조사. '으로/로'는 ㄹ 받침 뒤에도 '로'다."""
    ch = word[-1]
    if not "가" <= ch <= "힣":
        return without_final
    final = (ord(ch) - 0xAC00) % 28
    if final == 0 or (with_final == "으로" and final == 8):
        return without_final
    return with_final


def _quote_list(items: list[str]) -> str:
    return ", ".join(f"'{x}'" for x in items)


ACKS = ("네", "아", "어", "예", "그렇죠", "맞아요", "진짜요", "아니요", "아니", "응", "어어")


def _legacy_lines(profile: dict, summary: str = "") -> list[str]:
    """말투 칸 문장. 근거가 모자란 항목은 쓰지 않는다. 수치는 '열에 N'으로 풀어 쓴다."""
    lines: list[str] = []
    endings = profile["endings"]
    enough = profile["sentences"] >= MIN_SENTENCES
    polite = profile["politeShare"]
    if enough and polite >= 0.8:
        line = "말높임: 상대에게는 존댓말을 기본으로 쓴다."
        if endings["formal"] + endings["hedgeFormal"] >= 0.05 * profile["sentences"]:
            line = (
                "말높임: 상대에게는 존댓말을 기본으로 쓰고, "
                "생각을 정리해 말할 때는 '~습니다'를 섞는다."
            )
        if endings["plainDa"] < 0.02 * profile["sentences"]:
            line += " '~다'로 끝나는 글말 문장은 쓰지 않는다."
        elif endings["plainDa"] < 0.1 * profile["sentences"]:
            line += " '~다'로 끝나는 글말 문장은 거의 쓰지 않는다."
        lines.append(line)
    elif enough and polite <= 0.2:
        lines.append("말높임: 상대에게 반말을 기본으로 쓴다.")
    elif summary:
        # 존댓말·반말이 섞이면 G3에서 사람이 승인한 말투 요약이 말높임을 정한다.
        lines.append(summary.strip())
    if not enough:
        return [*lines, _closing()]
    ranked = sorted(
        ((n, label, endings[n]) for n, label, _, _ in ENDINGS if n not in {"open", "plainDa"}),
        key=lambda x: -x[2],
    )
    top = [(label, c) for _, label, c in ranked if c >= 0.03 * profile["sentences"]][:5]
    if top:
        lines.append(
            "문장 끝: "
            + ", ".join(label for label, _ in top)
            + " 순으로 많다."
            + _hedge_sentence(profile)
            + (
                " 생각이 이어지는 중에는 '~는데', '~고' 같은 연결어미로"
                " 끝을 열어 둔 채 말을 멈추기도 한다."
                if endings["open"] >= 0.08 * profile["sentences"]
                else ""
            )
        )
    markers = [
        m
        for m, _ in sorted(profile["markersPer1000"].items(), key=lambda x: -x[1])
        if profile["markerCounts"][m] >= MIN_MARKER_COUNT and profile["markersPer1000"][m] >= 2.0
    ]
    if markers:
        head, rest = markers[:2], markers[2:12]
        line = f"담화 표지: {_quote_list(head)}{_josa(head[-1], '이', '가')} 가장 잦고"
        if rest:
            line += f", {_quote_list(rest)}{_josa(rest[-1], '을', '를')} 말 사이에 끼운다."
        else:
            line += "."
        openers = [
            w
            for w, c in profile["openers"].items()
            if c >= 0.015 * profile["subjectMessages"] and re.fullmatch(r"[가-힣]{1,4}", w)
        ][:8]
        if openers:
            line += (
                f" 대답의 첫마디는 {_quote_list(openers)}{_josa(openers[-1], '으로', '로')} 연다."
            )
        line += (
            " 한 문장에 같은 표지를 몰아 쓰지 않는다."
            if _texture_sentence(profile)
            else " 한 문장에 같은 표지를 몰아 쓰지 않고,"
            " 바로 답할 수 있는 짧은 말에는 표지를 붙이지 않는다."
        )
        lines.append(line)
    sp, pl = profile["selfReference"]["polite"], profile["selfReference"]["plain"]
    if sp + pl >= 10:
        if sp >= 3 * pl:
            lines.append(
                "자기 지칭: '저', '제가'를 쓴다."
                + (" '내가', '나'는 드물게 나온다." if pl >= 0.05 * (sp + pl) else "")
            )
        elif pl >= 3 * sp:
            lines.append("자기 지칭: '나', '내가'를 쓴다.")
    conn = [c for c, n in sorted(profile["connectors"].items(), key=lambda x: -x[1]) if n >= 3][:4]
    if profile["longShare"] >= 0.1 and conn:
        shown = ["~" + c if c in SUFFIX_CONNECTORS else c for c in conn]
        lines.append(
            f"말의 흐름: 생각해서 답하는 질문에는 {_quote_list(shown)}"
            f"{_josa(conn[-1], '으로', '로')}"
            " 문장을 끊지 않고 이어 붙인다. "
            "가벼운 질문이나 장난에는 짧게 받는다."
        )
    if texture := _texture_sentence(profile):
        lines.append(texture)
    elif profile["repeatShare"] >= 0.03:
        lines.append(
            "고쳐 말하기: 말하다가 같은 말을 한 번 더 되풀이하거나 단어를 고쳐 잇는 일이 가끔 있다."
        )
    if profile["laughShare"] < 0.02:
        lines.append("표기: 웃음 표기(ㅋㅋ)나 이모티콘은 거의 쓰지 않는다.")
    else:
        lines.append(
            f"표기: 웃음 표기나 이모티콘을 메시지 {_tenths(profile['laughShare'])} 정도에 쓴다."
        )
    ans = profile["answers"]
    if ans["count"] >= MIN_ANSWERS:
        acks = [w for w in ans["firstWords"] if w in ACKS][:4]
        guna_rare = profile.get("gunaSentenceEndings", 0) <= 0.005 * profile["sentences"]
        if ans["gunaOpenings"] <= 0.01 * ans["count"] and guna_rare:
            lines.append(
                "받는 말: 상대 말을 '아, 그러셨구나', '~시구나'처럼 '~구나'로 받지 않는다. "
                "첫마디 다음 문장에서도 상대가 한 말을 '~셨구나', '~시구나'로 "
                "되풀이해 확인하지 않는다. "
                + (f"받을 때는 {_quote_list(acks)}처럼 짧게 받거나 " if acks else "")
                + "받는 말 없이 바로 답한다."
            )
        where = "일상 대화에서는" if ans["scope"] == "CONVERSATION" else "대화에서는"
        if ans["medianChars"] <= 80:
            lines.append(
                f"길이: {where} 대개 한두 문장으로 답하고, 한 마디로 끝나는 답도 많다"
                f"(두 문장 이하가 {_tenths(ans['atMostTwoSentences'])}, "
                f"80자 안쪽이 {_tenths(ans['atMost80Chars'])})."
                " 생각해서 답할 질문에만 길게 이어 말한다."
            )
    return [*lines, _closing()]


def _closing() -> str:
    return (
        "본인이 밝힌 사실과 말투를 따르고, "
        "원문에 없는 경험이나 사용자와의 공동 기억을 지어내지 않는다."
    )


def default_register_fallback(kind: str) -> str:
    return "CASUAL" if kind in CONVERSATION_KINDS else "FORMAL"


def source_registers(texts) -> dict[str, str]:
    return {
        t.textId: getattr(t, "register", None) or default_register_fallback(t.kind) for t in texts
    }


DEFAULT_HABIT_WORDS = ("진짜", "그냥", "너무", "정말")

# 고유명사를 모르는 상태에서 사람·장소·상품 이름을 놓치지 않도록,
# 견본에 한해서는 지시어·부사·일상 술어만으로 이루어진 온전한 답을 고른다.
_SAMPLE_WORDS = frozenset(
    (
        """
아 어 음 네 예 응 와 아니 아니요 그렇죠 맞아요 그러게요 그럼요 그래요 괜찮아요
저 저는 저도 제가 나 나는 나도 내가 그게 그건 그거 그거는 이게 이건 이거 이거는
요즘 요새 요새는 오늘 오늘은 지금 아까 원래 그냥 좀 또 너무 정말 진짜 되게 많이 더 덜
사실 이렇게 그렇게 저렇게 이 정도는 그래서 근데 그래도 그럼 혹시 안 못 잘 다 왜 뭐
거 것 거는 건 걸 게 수도 수 있는 없는 있어요 없어요 같아요 같죠 같은데요 같네요
좋아요 좋아해요 좋죠 좋네요 좋았어요 재밌어요 재밌네요 재밌었습니다 재미있었어요
감사해요 감사합니다 고마워요 반가워요 궁금해요 어렵죠 어렵네요 쉽죠 되죠 되나요
그랬어요 그랬는데 했어요 했죠 해요 하는 하고 하죠 하세요 해주세요 보세요 봐보세요
보셨어요 보지 않나 않나요 나와요 많죠 많아요 모르겠어요 알겠어요 아닐까요 아니에요
맞아 맞지 그래 그랬어 그랬지 좋아 괜찮아 했어 했지 몰라 모르겠어 알겠어 고마워
"""
    ).split()
)


def _samples(answers: list[str]) -> list[str]:
    pool = []
    for text in sorted(set(answers)):
        if not 10 <= len(text) <= 60 or not re.fullmatch(r"[가-힣 .,?!~…ㅋㅎ]+", text):
            continue
        words = re.findall(r"[가-힣]+", text)
        if words and all(w in _SAMPLE_WORDS for w in words):
            pool.append((text, words[0], _ending(text), words[-1]))
    chosen, starts, endings, last = [], set(), set(), set()
    while pool and len(chosen) < 8:
        item = max(
            pool,
            key=lambda x: (
                int(x[1] not in starts) + int(x[2] not in endings),
                x[3] not in last,
                x[0].endswith((".", "?", "!")),
                -abs(len(x[0]) - 25),
            ),
        )
        text, first, ending, tail = item
        chosen.append(text)
        starts.add(first)
        endings.add(ending)
        last.add(tail)
        pool.remove(item)
    return chosen if len(chosen) >= 6 else []


def build_speech_profile(
    corpus: list[dict],
    kinds: dict[str, str],
    registers: dict[str, str] | None = None,
    model_habit_words: list[str] | None = None,
) -> dict:
    """승인 원문만 받는다. 기사와 비교 세트는 어느 자리의 근거에도 넣지 않는다."""
    profile = _aggregate(corpus, kinds)
    by_id = {k: (registers or {}).get(k) or default_register_fallback(v) for k, v in kinds.items()}
    groups = {"FORMAL": [], "CASUAL": []}
    for row in corpus:
        tid = _text_id(row["msgId"])
        if kinds.get(tid) != "ARTICLE" and tid in by_id:
            groups[by_id[tid]].append(row)
    casual_rows = groups["CASUAL"]
    casual = _aggregate(casual_rows, kinds, casual_only=True)
    raw_answers = [row["text"] for _, row in _answer_pairs(casual_rows, kinds)]
    answers = [_clean(a) for a in raw_answers if _clean(a)]
    habits = list(
        dict.fromkeys(DEFAULT_HABIT_WORDS if model_habit_words is None else model_habit_words)
    )
    casual["habitWords"] = habits
    casual["habitShare"] = _rate(
        sum(bool(set(_words(a)).intersection(habits)) for a in answers), len(answers)
    )
    casual["gunaShare"] = _rate(
        sum(any(_bare_end(s).endswith("구나") for s in _sentences(a)) for a in answers),
        len(answers),
    )
    # 중앙값을 상한으로 오해하지 않도록 일상 답의 약 3분의 2가 들어오는 길이를 안내한다.
    casual["typicalChars"] = (
        sorted(map(len, answers))[2 * (len(answers) - 1) // 3] if answers else 0
    )
    profile.update(
        casual=casual,
        formal=_aggregate(groups["FORMAL"], kinds),
        samples=_samples(raw_answers),
    )
    return profile


def _frequency(share: float) -> str:
    if 0.25 <= share <= 1 / 3:
        return "서너 답에 한 번꼴로"
    return (
        "거의 매 답에서"
        if share >= 0.85
        else (
            f"답의 {share:.0%} 정도에서" if share > 0.5 else f"{round(1 / share)}개 답에 한 번꼴로"
        )
    )


def render_voice_definition(profile: dict, summary: str = "") -> list[str]:
    """일상 답이 충분하면 자리별 지침을 쓴다. 예전 통계와 작은 표본은 종전대로 읽는다."""
    c = profile.get("casual")
    if not c or c["answers"]["count"] < MIN_ANSWERS or c["sentences"] < MIN_SENTENCES:
        return _legacy_lines(profile, summary)
    f, ans = profile["formal"], c["answers"]
    lines = []
    ends = c["endings"]
    formal_rate = (ends["formal"] + ends["hedgeFormal"]) / c["sentences"]
    known = sum(ends[n] for n, _, _, p in ENDINGS if p is not None)
    if known >= MIN_ANSWERS:
        level = "존댓말" if c["politeShare"] >= 0.8 else "반말" if c["politeShare"] <= 0.2 else ""
        base = (
            f"{level}을 기본으로 쓴다." if level else summary.strip() or "존댓말과 반말을 섞는다."
        )
        if level == "존댓말" and ends["haeyo"] + ends["jyo"] > ends["formal"] + ends["hedgeFormal"]:
            base = "해요체로 말한다."
        if (
            f["sentences"] >= MIN_SENTENCES
            and f["endings"]["formal"] + f["endings"]["hedgeFormal"] >= MIN_MARKER_COUNT
        ):
            base += " 소감·각오를 맺을 때 하십시오체('-습니다/-ㅂ니다')를 쓴다."
        lines.append(
            f"상대높임 등급: {base} 일상 대화에서 하십시오체는 문장의 {formal_rate:.0%} 정도다."
        )
    elif summary:
        lines.append(summary)
    span = max(10, round(c["typicalChars"] / 10) * 10)
    brief = "대개 한두 문장, " if ans["atMostTwoSentences"] >= 0.6 else ""
    lines.append(
        f"발화 길이: 가벼운 질문에는 {brief}{span}자 안팎으로 답한다."
        + (
            " 소감·각오·회상은 생각을 풀어 길게 말한다."
            if f["longShare"] >= 0.1 and f["subjectMessages"] >= MIN_ANSWERS
            else ""
        )
    )
    reflective = f if f["hedgeByLength"]["long"]["count"] >= MIN_ANSWERS else c
    long = reflective["hedgeByLength"]["long"]
    if long["count"] >= MIN_ANSWERS:
        conn = [
            k
            for k, v in sorted(reflective["connectors"].items(), key=lambda x: -x[1])
            if v >= MIN_MARKER_COUNT
        ][:3]
        if conn:
            lines.append(f"절 연결: 생각을 길게 풀 때 {_quote_list(conn)} 같은 말로 절을 잇는다.")
        if long["share"] >= 0.1:
            lines.append(
                "완화 표현: 생각이나 느낌을 길게 풀 때 '~것 같아요/~것 같습니다'로 맺는다"
                f"(긴 발화의 {long['share']:.0%}). 가벼운 답은 바로 맺는다."
            )
    fillers = [
        w
        for w, n in sorted(c["markerCounts"].items(), key=lambda x: -x[1])
        if w in FILLERS and w not in c["habitWords"] and n >= MIN_MARKER_COUNT
    ][:3]
    short = c["fillerByLength"]["short"]
    if fillers and short["count"] >= MIN_ANSWERS:
        lines.append(
            f"담화 표지: 생각을 고를 때 {_quote_list(fillers)} 같은 말을 끼운다."
            f" 짧은 답의 군말은 {_count_words(short['avgPerAnswer'])}이다."
        )
        if long["count"] >= MIN_ANSWERS:
            avg = reflective["fillerByLength"]["long"]["avgPerAnswer"]
            lines[-1] += f" 150자 넘게 풀어 말할 때 군말은 {_count_words(avg)}이다."
    elif fillers:
        lines.append(f"담화 표지: 생각을 고를 때 {_quote_list(fillers)} 같은 말을 끼운다.")
    if c["habitWords"] and not c["habitShare"]:
        lines.append(f"강조 부사: {_quote_list(c['habitWords'])} 없이 담백하게 말한다.")
    elif c["habitWords"]:
        lines.append(
            f"강조 부사: {_quote_list(c['habitWords'])} 가운데 하나를 골라 "
            f"{_frequency(c['habitShare'])}, 한 답에 하나까지 쓴다."
        )
    lines.append(
        f"반복: 강조할 때 같은 말을 한 번 더 되풀이한다(일상 발화의 {c['repeatShare']:.0%})."
        if c["repeatShare"]
        else "반복: 같은 말은 한 번으로 맺는다."
    )
    starts = [
        (w, n)
        for w, n in ans["firstWords"].items()
        if n >= MIN_MARKER_COUNT and w in _SAMPLE_WORDS and w not in c["habitWords"]
    ][:4]
    if starts:
        lines.append(
            "발화 개시어: "
            + ", ".join(f"'{w}'({n / ans['count']:.0%})" for w, n in starts)
            + "처럼 열거나 바로 본론으로 들어간다."
        )
    guna = c["gunaShare"]
    lines.append(
        "응답 방식: 상대 말을 짧게 받거나 곧바로 답한다. "
        + (f"'-구나'로 받는 답은 {guna:.0%} 정도다." if guna else "'-구나'로 되받는 일은 드물다.")
    )
    lines.append(f"표기: 웃음 표기와 이모티콘은 일상 발화의 {c['laughShare']:.0%} 정도에 쓴다.")
    lines.append(_closing())
    if profile["samples"]:
        lines.extend(
            [
                "말의 결 견본: 내용과 소재는 따라 하지 말고 말의 길이와 맺는 방식만 참고한다.",
                *(f'- "{s}"' for s in profile["samples"]),
            ]
        )
    return lines
