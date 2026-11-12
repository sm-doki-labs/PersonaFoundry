"""Offline S8 compiler for reviewed evidence cards. Also runs as a standalone file."""

import argparse
import json
import re
import sys
from pathlib import Path

SECTIONS = (
    "FACTS",
    "LIFE_AND_TASTES",
    "DISPOSITION",
    "WANTS_AND_FEARS",
    "READING_AND_TENSION",
    "CHOICES",
    "VOICE",
    "KNOWS_AND_LIMITS",
)
INTERVIEW_FORMAT = "interview-editor-v2"
FACTS_GUARD_SCOPE = "FACTS_GUARD"
_INTERVIEW_SCOPES = ("LOCAL", "REPEATED", "REPORTED", "MEASURED", FACTS_GUARD_SCOPE)
# Compiler-owned card. Its presence marks an interview packet built with the facts guard;
# packets without it keep the original layout byte for byte.
FACTS_GUARD = (
    "사실표의 숫자·기록·날짜·이름은 적힌 그대로 말하고 어림하거나 흐리게 바꾸지 않는다. "
    "사실표에 없는 수치나 기록은 만들지 않는다."
)
FACTS_GUARD_CARD = dict(
    section="KNOWS_AND_LIMITS",
    scope=FACTS_GUARD_SCOPE,
    trigger="숫자·기록·날짜·이름 같은 사실을 물을 때",
    first=FACTS_GUARD,
    shift="",
    stop="",
    limit="사실표에 없는 사실의 답은 다른 항목을 따른다.",
    rule=FACTS_GUARD,
    evidence=[],
)
# Guarded interview packets fill an empty section with a plain instruction to the character.
_GUARDED_EMPTY = {
    "LIFE_AND_TASTES": "사실표에 없는 취향이나 생활 습관은 지어내지 않는다.",
    "WANTS_AND_FEARS": "사실표에 없는 목표나 걱정은 지어내지 않는다.",
}
_GUARDED_DEFAULT = "묻는 내용에 맞춰 답한다."
_INTERVIEW_BOUNDARY = (
    "경험을 묻는 질문에는 사실표와 본인이 직접 밝힌 범위까지만 개인사로 답한다. "
    "그때의 날짜·연락·인용·감정·지금도 계속하는 습관은 별개의 사실이다. "
    "확인되지 않은 전제는 있었다거나 없었다고 받지 않는다. "
    "기억이 흐리다는 말로 사건이 있었던 듯 처리하지 않는다. "
    "확인할 수 없는 경험은 짧게 유보하고, "
    "함께 물은 판단이나 이유에는 현재 의견이나 조건부 설명으로 답한다."
)
NEUTRAL = "자료가 부족하므로 이 영역의 인물 특성을 정하지 않는다."
# Card slots that no independent evidence confirmed. They stay in the review record but
# are not rendered, so the prompt does not repeat an instruction to do nothing (D-0196).
UNOBSERVED = "이 항목은 독립 근거로 확인하지 않아 별도 반응을 지시하지 않는다."
# Per-card caveats that v6 states once at the top instead of repeating on every card.
_CARD_CAVEATS = (
    " 이 특징은 매번 수행할 의무나 고정된 반응 순서가 아니다.",
    " 같은 적용 범위에서 다른 반응 또는 미판정 근거도 있어 단일한 방식으로 일반화하지 않는다.",
)
_SHARED_CAVEAT = (
    "아래 적용 상황별 특징은 매번 수행할 의무나 고정된 순서가 아니며, "
    "같은 상황에서 다른 반응이 관찰된 경우도 한 가지 방식으로 일반화하지 않는다."
)
_PACKET = {"role", "facts", "scene", "sections", "trainIds", "holdoutIds"}
_CARD = {"section", "trigger", "first", "shift", "stop", "limit", "evidence", "rule"}
# Reject explicit worked examples, speaker labels, and competing section headers.
_EXAMPLE = re.compile(
    r"(?<!\w)(?:user|assistant|model|system|human|bot|speaker\s*\d+|Q|A|"
    r"사용자|유저|모델|상대|질문|답변|예시|예문|예제|examples?|sample dialogue)\s*[:：]"
    r"|(?<!\w)(?:for example|e\.g\.|예를 들어|예를 들면)(?!\w)"
    r"|\[(?:CHARACTER_EXAMPLES|EXAMPLES?|SOURCE)(?:\]|\s)"
    r"|(?:→|=>)",
    re.IGNORECASE,
)
_HEADER = re.compile(r"^\s*\[(?:" + "|".join(SECTIONS) + r")\]\s*$", re.M | re.I)
# Only paired, single-line notation can qualify. Unpaired/nested quotes stay held.
_QUOTE = re.compile(
    r"“[^”\r\n]*”|‘[^’\r\n]*’|「[^」\r\n]*」|"
    r"(?<![A-Za-z0-9])'[^'\r\n]*'|\"[^\"\r\n]*\"|`[^`\r\n]*`"
)
_QUOTE_MARK = re.compile(r"[“‘「」\"`]|(?<![A-Za-z0-9])'|(?<![A-Za-z])’|’(?![A-Za-z])|”")
_META_LABEL = (
    r"(?:(?:종결|연결|선어말|어말|관형사형|명사형|전성)\s*)?어미"
    r"|형태소|조사|접사|접두사|접미사|구문|구성"
)
_META_AFTER = re.compile(r"\s*(?:라는\s*)?(?:" + _META_LABEL + r")")
_META_BEFORE = re.compile(r"(?<!\w)(?:" + _META_LABEL + r")\s*[:：]?\s*$")
# These are notation categories, not a character-specific inventory of endings.
_LETTER = r"[가-힣ㄱ-ㅎㅏ-ㅣA-Za-z]"
_MORPH_BODY = rf"(?:{_LETTER}|\({_LETTER}+\))+"
_BOUND_FORM = re.compile(rf"(?:[-~]{_MORPH_BODY}-?|{_MORPH_BODY}-)")
_SLOT = r"(?:NP|VP|AP|N|V|A|S|주어|목적어|서술어|명사구|동사구|명사|동사|형용사|어간|절)"
_SLOTTED_FORM = re.compile(rf"{_SLOT}[-~]{_MORPH_BODY}-?")
_SLOT_SEQUENCE = re.compile(rf"{_SLOT}(?:\s*\+\s*{_SLOT})+")
# Multiword notation must leave a predicate stem open and use grammatical words,
# not a concrete subject, time, or event. Unknown constructions remain held.
_BOUND_NOUNS = {"것", "수", "줄", "바", "적", "뿐", "데", "리", "듯", "만큼", "지"}
_AUXILIARIES = {"같다", "있다", "없다", "하다", "되다", "알다", "모르다", "싶다"}


def _grammatical_form(value):
    """Recognize a small notation grammar, never a quoted lexical utterance."""
    alternatives = value.split("/")
    if all(_BOUND_FORM.fullmatch(part.strip()) for part in alternatives):
        return True
    if _SLOT_SEQUENCE.fullmatch(value) or _SLOTTED_FORM.fullmatch(value):
        return True
    words = value.split()
    return (
        len(words) == 3
        and bool(_BOUND_FORM.fullmatch(words[0]) or _SLOTTED_FORM.fullmatch(words[0]))
        and words[0][-1] != "-"  # A prefix does not leave a predicate stem open.
        and words[1] in _BOUND_NOUNS
        and words[2] in _AUXILIARIES
    )


def _non_grammatical_quote(value):
    """Require both incomplete notation and an adjacent grammatical explanation.

    Mask only validated spans for inspection; the rendered text is never changed.
    A grammatical label alone cannot turn a full utterance into notation.
    """
    remainder = []
    end = 0
    for quote in _QUOTE.finditer(value):
        if not _grammatical_form(quote.group()[1:-1]):
            return True
        after = value[quote.end() :]
        label = _META_AFTER.match(after)
        if label:
            explanation = after[label.end() :]
        elif _META_BEFORE.search(value[: quote.start()]):
            explanation = after
        else:
            return True
        # A bare label or punctuation is not a functional/structural explanation.
        if len(re.findall(r"[가-힣A-Za-z]+", explanation)) < 2:
            return True
        remainder.append(value[end : quote.start()])
        remainder.append(" ")
        end = quote.end()
    remainder.append(value[end:])
    return bool(_QUOTE_MARK.search("".join(remainder)))


def _keys(value, expected, path):
    if not isinstance(value, dict) or set(value) != expected:
        missing = (
            sorted(expected.difference(value)) if isinstance(value, dict) else sorted(expected)
        )
        raise ValueError(f"{path}: expected exact schema (missing: {missing}; no extra fields)")


def _text(value, path, *, literal=False):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: expected nonblank text")
    # Quoted proper nouns can be part of approved facts; never rewrite their bytes.
    checked = re.sub(r"[“”‘’「」\"']", "", value) if literal else value
    if (
        _EXAMPLE.search(checked)
        or _HEADER.search(value)
        or (not literal and _non_grammatical_quote(value))
    ):
        raise ValueError(f"{path}: dialogue/example or reserved section heading")
    # JSON permits lone escaped surrogates; they cannot appear in UTF-8 output.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{path}: invalid Unicode") from exc
    return value


def _ids(value, path):
    if not isinstance(value, list) or any(
        not isinstance(i, str) or not i or i != i.strip() for i in value
    ):
        raise ValueError(f"{path}: expected a list of nonblank, unpadded string IDs")
    if len(set(value)) != len(value):
        raise ValueError(f"{path}: duplicate ID")
    return set(value)


def compile_prompt(packet: dict) -> str:
    """Render only the three literal inputs and the reviewed rule of each valid card."""
    conditions = isinstance(packet, dict) and "formatVersion" in packet
    interview = conditions and packet.get("formatVersion") == INTERVIEW_FORMAT
    voiced = isinstance(packet, dict) and "voice" in packet
    stated = isinstance(packet, dict) and "statedFacts" in packet
    measured = conditions and packet.get("formatVersion") == "evidence-conditions-v3"
    if voiced and not measured:
        raise ValueError("voice: measured lines need evidence-conditions-v3")
    if stated and not measured:
        raise ValueError("statedFacts: self-reported facts need evidence-conditions-v3")
    _keys(
        packet,
        _PACKET
        | ({"formatVersion"} if conditions else set())
        | ({"voice"} if voiced else set())
        | ({"statedFacts"} if stated else set()),
        "packet",
    )
    if conditions and packet["formatVersion"] not in {
        "evidence-conditions-v2",
        "evidence-conditions-v3",
        INTERVIEW_FORMAT,
    }:
        raise ValueError("unknown evidence formatVersion")
    role, scene, facts = (
        _text(packet[k], k, literal=k == "facts") for k in ("role", "scene", "facts")
    )
    train = _ids(packet["trainIds"], "trainIds")
    held = _ids(packet["holdoutIds"], "holdoutIds")
    if train & held:
        raise ValueError("trainIds and holdoutIds overlap")
    if stated:
        # evidence-v10: what the person said about themselves, moved out of behaviour cards so
        # it sits with the other facts. Each line cites the training turns it came from.
        if not isinstance(packet["statedFacts"], list):
            raise ValueError("statedFacts: expected a list")
        extra = []
        for n, item in enumerate(packet["statedFacts"]):
            _keys(item, {"text", "evidence"}, f"statedFacts[{n}]")
            refs = _ids(item["evidence"], f"statedFacts[{n}].evidence")
            if not refs or not refs <= train:
                raise ValueError(f"statedFacts[{n}].evidence: expected training IDs only")
            extra.append(_text(item["text"], f"statedFacts[{n}].text"))
        if extra:
            facts += "\n" + "\n".join(extra)
    if not isinstance(packet["sections"], list):
        raise ValueError("sections: expected an array of approved cards")

    rules = {heading: [] for heading in SECTIONS[1:]}
    guarded = False
    if voiced:
        if not isinstance(packet["voice"], list):
            raise ValueError("voice: expected measured lines")
        for n, line in enumerate(packet["voice"]):
            rules["VOICE"].append(_text(line, f"voice[{n}]"))
    for n, card in enumerate(packet["sections"]):
        path = f"sections[{n}]"
        _keys(card, _CARD | ({"scope"} if interview else set()), path)
        if interview and card["scope"] not in _INTERVIEW_SCOPES:
            raise ValueError(f"{path}.scope: unknown interview evidence scope")
        if interview and card["scope"] == FACTS_GUARD_SCOPE:
            if card != FACTS_GUARD_CARD or guarded:
                raise ValueError(f"{path}: facts guard must be the single fixed card")
            guarded = True
            continue
        heading = card["section"]
        if not isinstance(heading, str) or heading not in rules:
            raise ValueError(f"{path}.section: unknown section or reserved FACTS")
        for key in ("trigger", "first", "shift", "stop", "limit", "rule"):
            if interview and key in ("shift", "stop") and card[key] == "":
                continue
            _text(card[key], f"{path}.{key}")
        refs = _ids(card["evidence"], f"{path}.evidence")
        if not refs or not refs <= train:
            raise ValueError(f"{path}.evidence: expected one or more training IDs only")
        if interview:
            first = card["first"].strip()
            trigger = card["trigger"].strip()
            # Preserve the condition even if the writer didn't put it into the first sentence.
            lead = first if first.startswith(trigger) else f"{trigger}: {first}"
            line = " ".join(
                [lead] + [card[key].strip() for key in ("shift", "stop", "limit") if card[key]]
            )
            if line in rules[heading]:
                raise ValueError(f"{path}: duplicate interview rule")
            rules[heading].append(line)
        elif conditions:
            # Do not let an independently authored summary erase the scoped behavior.
            labels = (
                ("trigger", "적용 상황"),
                ("first", "첫 반응"),
                ("shift", "이어지는 반응"),
                ("stop", "마무리 조건"),
                ("limit", "적용 한계"),
            )
            shown = []
            for key, label in labels:
                value = card[key]
                if measured and value.strip() == UNOBSERVED:
                    continue
                if measured and key == "limit":
                    for caveat in _CARD_CAVEATS:
                        value = value.replace(caveat, "")
                    value = value.strip()
                    if not value:
                        continue
                shown.append(f"{label}: {value}")
            rules[heading].append("\n".join(shown))
        else:
            rules[heading].append(card["rule"])

    if interview:
        if guarded:
            rules["KNOWS_AND_LIMITS"].insert(0, FACTS_GUARD)
        rules["KNOWS_AND_LIMITS"].append(_INTERVIEW_BOUNDARY)
    parts = [role + (" " + _SHARED_CAVEAT if measured else ""), scene, "[FACTS]\n" + facts]
    for name, lines in rules.items():
        empty = _GUARDED_EMPTY.get(name, _GUARDED_DEFAULT) if guarded else NEUTRAL
        parts.append(f"[{name}]\n" + ("\n".join(lines) if lines else empty))
    return "\n\n".join(parts) + "\n"


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="reviewed JSON packet (UTF-8)")
    parser.add_argument("output", type=Path, help="compiled prompt (UTF-8)")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() and args.input.samefile(args.output):
            raise ValueError("input and output must be different files")
        packet = json.loads(
            args.input.read_bytes().decode("utf-8"), object_pairs_hook=_unique_object
        )
        prompt = compile_prompt(packet)
        args.output.write_bytes(prompt.encode("utf-8"))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
