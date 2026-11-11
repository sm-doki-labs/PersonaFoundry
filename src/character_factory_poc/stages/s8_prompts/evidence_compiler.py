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
NEUTRAL = "자료가 부족하므로 이 영역의 인물 특성을 정하지 않는다."
_PACKET = {"role", "facts", "scene", "sections", "trainIds", "holdoutIds"}
_CARD = {"section", "trigger", "first", "shift", "stop", "limit", "evidence", "rule"}
# Reject explicit worked examples, speaker labels, and competing section headers.
_EXAMPLE = re.compile(
    r"(?<!\w)(?:user|assistant|model|system|human|bot|speaker\s*\d+|Q|A|"
    r"사용자|유저|모델|상대|질문|답변|예시|예문|예제|examples?|sample dialogue)\s*[:：]"
    r"|(?<!\w)(?:for example|e\.g\.|예를 들어|예를 들면)(?!\w)"
    r"|\[(?:CHARACTER_EXAMPLES|EXAMPLES?|SOURCE)(?:\]|\s)"
    r"|(?:→|=>|“[^”]+”|‘[^’]+’|「[^」]+」|(?<![A-Za-z0-9])'[^'\n]+'|\"[^\"\n]+\")",
    re.IGNORECASE,
)
_HEADER = re.compile(r"^\s*\[(?:" + "|".join(SECTIONS) + r")\]\s*$", re.M | re.I)


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
    if _EXAMPLE.search(checked) or _HEADER.search(value):
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
    _keys(packet, _PACKET | ({"formatVersion"} if conditions else set()), "packet")
    if conditions and packet["formatVersion"] != "evidence-conditions-v2":
        raise ValueError("unknown evidence formatVersion")
    role, scene, facts = (
        _text(packet[k], k, literal=k == "facts") for k in ("role", "scene", "facts")
    )
    train = _ids(packet["trainIds"], "trainIds")
    held = _ids(packet["holdoutIds"], "holdoutIds")
    if train & held:
        raise ValueError("trainIds and holdoutIds overlap")
    if not isinstance(packet["sections"], list):
        raise ValueError("sections: expected an array of approved cards")

    rules = {heading: [] for heading in SECTIONS[1:]}
    for n, card in enumerate(packet["sections"]):
        path = f"sections[{n}]"
        _keys(card, _CARD, path)
        heading = card["section"]
        if not isinstance(heading, str) or heading not in rules:
            raise ValueError(f"{path}.section: unknown section or reserved FACTS")
        for key in ("trigger", "first", "shift", "stop", "limit", "rule"):
            _text(card[key], f"{path}.{key}")
        refs = _ids(card["evidence"], f"{path}.evidence")
        if not refs or not refs <= train:
            raise ValueError(f"{path}.evidence: expected one or more training IDs only")
        if conditions:
            # Do not let an independently authored summary erase the scoped behavior.
            labels = (
                ("trigger", "적용 상황"),
                ("first", "첫 반응"),
                ("shift", "이어지는 반응"),
                ("stop", "마무리 조건"),
                ("limit", "적용 한계"),
            )
            rules[heading].append("\n".join(f"{label}: {card[key]}" for key, label in labels))
        else:
            rules[heading].append(card["rule"])

    parts = [role, scene, "[FACTS]\n" + facts]
    for name, lines in rules.items():
        parts.append(f"[{name}]\n" + ("\n".join(lines) if lines else NEUTRAL))
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
