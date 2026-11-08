"""S9 기계 검사 (LLD §8.8 4단계, 가이드 §8·§9.2).

두 층이다. 한 대화 안의 차단 검사는 작성 응답을 받은 자리에서 돌리고, 실패하면 같은 입력으로
다시 쓴다. 데이터셋 전체 검사(중복·같은 말끝·같은 사과 문장)는 모든 대화를 모은 뒤 돌린다.
토큰화 도구가 없으므로 길이는 글자 수 근사로 재고, 근사임을 보고서에 남긴다.

클러스터에 턴 조건(`TurnRule`, 창작 인물 정책의 long)이 있으면 `turn_range`(assistant 턴 수
하한·상한)와 `long_structure`(작성자가 표시한 화제 전환·후반 계기 위치)를 차단 검사로 더한다.
`long_structure`는 작성자의 자기 표시를 기계로 확인할 뿐이고, 내용이 실제로 전환됐는지는 G7a·G7
사람 검토가 본다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from character_factory_poc.contracts.dataset import Conversation, Message, TurnRule

BLOCKING_NAMES: tuple[str, ...] = (
    "roles_alternate",
    "system_present",
    "no_empty",
    "source_flow_turns",
    "source_overlap",
    "flow_beats",
    "no_emoji",
    "turn_length",
    "close_formal_opener",
    "repeated_lines",
    "no_prefill",
    "source_facts_absent",
    "forbidden_phrases",
    "max_length",
    "turn_range",
    "long_structure",
)
DATASET_BLOCKING_NAMES: tuple[str, ...] = (
    "duplicate_messages",
    "ending_repetition",
    "phrase_repetition",
    "apology_repetition",
)
PREFILL_MARKERS: tuple[str, ...] = ("네 알겠습니다", "[HISTORY]", "HISTORY_STATUS")
APOLOGY_MARKERS: tuple[str, ...] = ("미안", "사과", "잘못했")
_STRIP = re.compile(r"[\s.,!?~;…ㅋㅎㅠㅜ]+")
# SNS 재작성은 원본을 흐름 뼈대로만 쓴다(학습 가이드 §7.1, D-0135). 공백·문장 부호·자모 웃음을 뺀 뒤
# 원본과 이어서 같은 글자가 OVERLAP_LIMIT 이상이면 막는다.
# 메시지 수는 원본과 FLOW_TURN_SLACK까지 다를 수 있다.
OVERLAP_LIMIT = 10
# 한소민 장기 대화 검사기(gen-r1 validate.py)에서 옮긴 말투 검사(D-0138).
CLOSE_RELATIONSHIPS = frozenset({"STRONGLY_FAVORABLE", "FAVORABLE"})
FORMAL_OPENER = re.compile(r"^네[,. ]")
_ACK_WORDS = "네|응|웅|그래|그렇구나|그랬구나|좋네|좋아|고마워|알겠어|오케이|ㅇㅋ"
GENERIC_ACK = re.compile(rf"^({_ACK_WORDS})[,.!~ ]*(ㅋ+|ㅎ+)?[.!~]*$")
BUBBLE_MEDIAN_MAX = 26
QUESTION_RATIO_MAX = 0.6
# 캐릭터 말에는 그림 이모지를 쓰지 않는다. ㅋㅋ·ㅠㅠ·^^·♥ 같은 글자 표현은 허용한다(D-0137).
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\uFE0F]")
FLOW_TURN_SLACK = 2
FLOW_BEATS = (3, 8)


@dataclass(frozen=True)
class ConvSpec:
    """한 대화를 검사할 때 필요한 문맥. system은 대화마다 다르고 나머지는 클러스터 공통이다."""

    cluster_id: str
    system: str
    material: str
    source: dict[str, Any] | None = None
    forbidden: tuple[str, ...] = ()
    source_facts: tuple[str, ...] = ()
    max_length_tokens: int = 4096
    chars_per_token: float = 1.5
    turn_rule: TurnRule | None = None
    relationship: str = ""
    turn_max_chars: int = 0


def normalize(text: str) -> str:
    return _STRIP.sub("", text)


def slot_beats(source: dict[str, Any] | None, item: dict[str, Any]) -> list[str]:
    """흐름 뼈대는 시드가 있으면 시드의 사건, 없으면 작성 응답의 flowBeats다."""
    seed = (source or {}).get("seed") or {}
    beats = seed.get("beats") if seed else item.get("flowBeats")
    return [str(b) for b in beats or []]


def style_warnings(conv: Conversation) -> list[str]:
    """한소민 검사기의 경고 항목: 말풍선 길이, 맞장구뿐인 줄, 인터뷰 같은 질문 비율."""
    said = [m.content for m in conv.messages if m.role == "assistant"]
    heard = [m.content for m in conv.messages if m.role == "user"]
    out: list[str] = []
    bubbles = sorted(len(b) for s in said for b in s.split("\n") if b.strip())
    texting = conv.provenance.channel in ("", "text")  # 말풍선은 문자 장면에만 있다
    if texting and bubbles and bubbles[len(bubbles) // 2] > BUBBLE_MEDIAN_MAX:
        out.append(f"캐릭터 말풍선 길이 중앙값이 {BUBBLE_MEDIAN_MAX}자를 넘는다")
    generic = sum(bool(GENERIC_ACK.match(s.strip())) for s in said)
    if generic > max(1, len(said) // 10):
        out.append(f"맞장구뿐인 캐릭터 말이 {generic}줄이다")
    if heard and sum("?" in u for u in heard) / len(heard) > QUESTION_RATIO_MAX:
        out.append("상대 말의 60% 넘게 질문이다(인터뷰처럼 읽힌다)")
    return out


def source_texts(source: dict[str, Any] | None) -> list[str]:
    return [str(t.get("content") or "") for t in (source or {}).get("turns", [])]


def overlaps(texts: list[str], sources: list[str], n: int = OVERLAP_LIMIT) -> bool:
    """texts 가운데 하나라도 원본과 정규화 뒤 n글자 이상 이어서 같으면 True."""
    grams: set[str] = set()
    for s in sources:
        norm = normalize(s)
        grams.update(norm[i : i + n] for i in range(len(norm) - n + 1))
    if not grams:
        return False
    for t in texts:
        norm = normalize(t)
        if any(norm[i : i + n] in grams for i in range(len(norm) - n + 1)):
            return True
    return False


def longest_overlap(texts: list[str], sources: list[str]) -> int:
    """texts와 원본 사이에서 정규화 뒤 이어서 같은 가장 긴 글자 수(보고용)."""
    best = 0
    norms = [normalize(s) for s in sources if s.strip()]
    for t in texts:
        a = normalize(t)
        for b in norms:
            prev = [0] * (len(b) + 1)
            for ch in a:
                cur = [0] * (len(b) + 1)
                for j, bj in enumerate(b, start=1):
                    if ch == bj:
                        cur[j] = prev[j - 1] + 1
                        if cur[j] > best:
                            best = cur[j]
                prev = cur
    return best


def approx_tokens(text: str, chars_per_token: float) -> int:
    """토큰화 도구가 없을 때 쓰는 글자 수 근사. 보고서에 근사임을 남긴다."""
    return math.ceil(len(text) / chars_per_token) if text else 0


def conversation_text(conv: Conversation) -> str:
    body = "\n".join(m.content for m in conv.messages)
    return f"{conv.system}\n{body}"


def assistant_text(conv: Conversation) -> str:
    return "\n".join(m.content for m in conv.messages if m.role == "assistant")


def assistant_turns(messages: list[Message] | list[dict[str, Any]]) -> int:
    return sum(
        1 for m in messages if (m.role if isinstance(m, Message) else m.get("role")) == "assistant"
    )


def turn_range_ok(conv: Conversation, rule: TurnRule) -> bool:
    turns = assistant_turns(list(conv.messages))
    return rule.minAssistantTurns <= turns <= rule.maxAssistantTurns


def structure_problems(item: dict[str, Any], rule: TurnRule | None) -> list[str]:
    """작성 응답의 topicShiftAt·lateTriggerAt 표시를 확인한다. 위치는 0부터 센 user 메시지다."""
    if rule is None or (rule.minTopicShifts == 0 and rule.minLateTriggers == 0):
        return []
    messages = list(item.get("messages") or [])
    total = len(messages)

    def user_positions(key: str) -> list[int] | None:
        raw = item.get(key) or []
        if not isinstance(raw, list) or any(type(x) is not int for x in raw):
            return None
        return sorted({x for x in raw if 0 < x < total and messages[x].get("role") == "user"})

    problems: list[str] = []
    shifts = user_positions("topicShiftAt")
    if shifts is None or len(shifts) < rule.minTopicShifts:
        problems.append(
            f"long_structure: topicShiftAt에 화제가 바뀌는 user 메시지 위치를 "
            f"{rule.minTopicShifts}개 이상 적는다(받은 값 {item.get('topicShiftAt')!r})"
        )
    late = user_positions("lateTriggerAt")
    start = rule.lateTriggerFrom * total
    late_ok = [x for x in late or [] if x >= start]
    if late is None or len(late_ok) < rule.minLateTriggers:
        problems.append(
            f"long_structure: lateTriggerAt에 대화 {round(rule.lateTriggerFrom * 100)}% 이후"
            f"(메시지 {int(start)}번 이후)의 계기 상황 user 메시지 위치를 "
            f"{rule.minLateTriggers}개 이상 적는다(받은 값 {item.get('lateTriggerAt')!r})"
        )
    return problems


def _alternates(messages: list[Message]) -> bool:
    if len(messages) < 2 or len(messages) % 2:
        return False
    return all(m.role == ("user" if i % 2 == 0 else "assistant") for i, m in enumerate(messages))


def _no_repeat(messages: list[Message]) -> bool:
    seen = [normalize(m.content) for m in messages if m.role == "assistant"]
    long = [s for s in seen if len(s) >= 6]
    return len(long) == len(set(long))


def evaluate(conv: Conversation, spec: ConvSpec) -> dict[str, bool]:
    messages = list(conv.messages)
    results: dict[str, bool] = {
        "roles_alternate": _alternates(messages),
        "system_present": bool(conv.system.strip()),
        "no_empty": all(m.content.strip() for m in messages),
        "no_prefill": (
            bool(messages)
            and messages[0].role == "user"
            and not any(p in conv.system for p in PREFILL_MARKERS)
            and not any(p in m.content for m in messages for p in PREFILL_MARKERS[:1])
        ),
        "source_flow_turns": True,
        "source_overlap": True,
        "flow_beats": True,
        "no_emoji": not EMOJI.search(assistant_text(conv)),
        "turn_length": not spec.turn_max_chars
        or all(len(m.content) <= spec.turn_max_chars for m in messages if m.role == "assistant"),
        "close_formal_opener": spec.relationship not in CLOSE_RELATIONSHIPS
        or not any(
            FORMAL_OPENER.match(m.content.strip()) for m in messages if m.role == "assistant"
        ),
        "repeated_lines": _no_repeat(messages),
        "source_facts_absent": True,
        "forbidden_phrases": True,
        "max_length": approx_tokens(conversation_text(conv), spec.chars_per_token)
        <= spec.max_length_tokens,
    }
    if spec.material == "SNS_REWRITE" and spec.source is not None:
        original = source_texts(spec.source)
        results["source_flow_turns"] = abs(len(messages) - len(original)) <= FLOW_TURN_SLACK
        beats = [b for b in conv.provenance.flowBeats if b.strip()]
        results["flow_beats"] = FLOW_BEATS[0] <= len(beats) <= FLOW_BEATS[1] and len(beats) == len(
            conv.provenance.flowBeats
        )
        written = [m.content for m in messages] + list(conv.provenance.flowBeats)
        results["source_overlap"] = not overlaps([*written, conv.system], original)
    joined = conversation_text(conv)
    if spec.source_facts:
        results["source_facts_absent"] = not any(f and f in joined for f in spec.source_facts)
    if spec.forbidden:
        speech = assistant_text(conv)
        results["forbidden_phrases"] = not any(f and f in speech for f in spec.forbidden)
    if spec.turn_rule is not None:
        results["turn_range"] = turn_range_ok(conv, spec.turn_rule)
    return results


_REASON: dict[str, str] = {
    "roles_alternate": "user·assistant가 번갈아 나오고 user로 시작해 assistant로 끝나야 한다",
    "system_present": "system(짧은 프롬프트 + 시작 장면)이 비어 있다",
    "no_empty": "빈 답이나 빈 메시지가 있다",
    "source_flow_turns": "SNS 재작성의 메시지 수가 원본과 2개 넘게 다르다",
    "source_overlap": "대사·장면·뼈대가 원본과 공백·문장 부호를 빼고 10글자 이상 이어서 같다",
    "flow_beats": "SNS 재작성에 흐름 뼈대(flowBeats) 3~8줄이 없다",
    "no_emoji": "캐릭터 말에 그림 이모지가 있다(ㅋㅋ·ㅠㅠ·^^는 써도 된다)",
    "turn_length": "캐릭터 한 턴이 길이 상한을 넘었다",
    "close_formal_opener": "가까운 관계인데 캐릭터 말이 '네,'로 시작한다",
    "repeated_lines": "같은 대화 안에서 캐릭터가 같은 말을 되풀이했다",
    "no_prefill": "첫 메시지가 user가 아니거나 system에 이력·프리필 표지가 있다",
    "source_facts_absent": "원본 화자의 사실이 캐릭터 설정·대사에 들어갔다",
    "forbidden_phrases": "인계안의 금지 표현이 캐릭터 대사에 있다",
    "max_length": "학습 길이(토큰 근사) 상한을 넘었다",
    "turn_range": "클러스터의 assistant 턴 수 범위(긴 대화 하한·상한)를 벗어났다",
    "long_structure": "긴 대화의 화제 전환·후반 계기 위치 표시가 조건에 못 미친다",
}


def problems_of(results: dict[str, bool]) -> list[str]:
    return [f"{name}: {_REASON[name]}" for name in BLOCKING_NAMES if not results.get(name, True)]


def conversation_problems(conv: Conversation, spec: ConvSpec) -> list[str]:
    problems = problems_of(evaluate(conv, spec))
    if spec.turn_rule is not None and not turn_range_ok(conv, spec.turn_rule):
        turns = assistant_turns(list(conv.messages))
        rule = spec.turn_rule
        problems = [p for p in problems if not p.startswith("turn_range:")]
        problems.append(
            f"turn_range: assistant 턴이 {turns}개다. {rule.minAssistantTurns}~"
            f"{rule.maxAssistantTurns}턴으로 쓴다(user·assistant 한 쌍이 한 턴)"
        )
    if spec.turn_max_chars and any(p.startswith("turn_length:") for p in problems):
        long = [
            str(i)
            for i, m in enumerate(conv.messages)
            if m.role == "assistant" and len(m.content) > spec.turn_max_chars
        ]
        problems = [p for p in problems if not p.startswith("turn_length:")]
        problems.append(
            f"turn_length: 캐릭터 말 {', '.join(long)}번 메시지가 "
            f"{spec.turn_max_chars}자를 넘는다. 짧게 끊어 쓴다"
        )
    return problems


def batch_problems(written: list[dict[str, Any]], specs: list[ConvSpec], system: str) -> list[str]:
    """작성 모델 응답(조립 전)을 검사한다. 실패하면 같은 입력으로 다시 쓴다."""
    problems: list[str] = []
    if len(written) != len(specs):
        problems.append(f"대화 수가 {len(specs)}개가 아니라 {len(written)}개다")
    for i, (item, spec) in enumerate(zip(written, specs, strict=False)):
        messages = [Message(role=m["role"], content=m["content"]) for m in item.get("messages", [])]
        if not _alternates(messages):
            problems.append(f"{i + 1}번째: user·assistant가 번갈아 나오지 않는다")
            continue
        conv = Conversation(
            conversationId=f"probe-{i}",
            clusterId=spec.cluster_id,  # type: ignore[arg-type]
            material=spec.material,  # type: ignore[arg-type]
            skeletonId="probe",
            system=spec.system or system,
            messages=messages,
            provenance={
                "writerModel": "probe",
                "requestRef": "probe",
                "flowBeats": (
                    slot_beats(spec.source, item) if spec.material == "SNS_REWRITE" else []
                ),
            },
        )
        problems.extend(f"{i + 1}번째: {p}" for p in conversation_problems(conv, spec))
        problems.extend(f"{i + 1}번째: {p}" for p in structure_problems(item, spec.turn_rule))
        scene = str(item.get("scene") or "").strip()
        if not 5 <= len(scene) <= 200:
            problems.append(f"{i + 1}번째: scene은 5~200자의 한 문장이어야 한다(받은 값 {scene!r})")
        elif "?" in scene:
            problems.append(f"{i + 1}번째: scene에 질문(?)을 넣지 않는다")
        if spec.material == "SNS_REWRITE" and overlaps([scene], source_texts(spec.source)):
            problems.append(f"{i + 1}번째: scene이 원본과 10글자 이상 이어서 같다")
        if spec.material == "SNS_REWRITE":
            want = (spec.source or {}).get("sourceId", "")
            if not item.get("sourceId") or item.get("sourceId") != want:
                problems.append(f"{i + 1}번째: SNS 재작성이면 sourceId={want!r}를 그대로 적는다")
    return problems


def _ngram_set(text: str, n: int) -> set[str]:
    norm = normalize(text)
    return {norm[i : i + n] for i in range(max(0, len(norm) - n + 1))}


def _cap(base: int, conversations: int, share: float) -> int:
    return max(base, math.ceil(conversations * share))


@dataclass
class DatasetReport:
    blocking: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def blocking_ids(self) -> list[str]:
        seen: list[str] = []
        for item in self.blocking:
            if item["conversationId"] not in seen:
                seen.append(item["conversationId"])
        return seen

    def problems(self) -> list[str]:
        return [f"{b['check']}: {b['conversationId']} ({b['detail']})" for b in self.blocking]


def dataset_report(
    conversations: list[Conversation],
    *,
    phrase_ngram: int,
    phrase_max_conversations: int,
    bubble_max_conversations: int,
    max_items: int = 60,
) -> DatasetReport:
    report = DatasetReport()
    total = len(conversations)
    report.metrics["conversations"] = total
    if not conversations:
        return report

    signature: dict[tuple[tuple[str, str], ...], list[str]] = {}
    endings: dict[str, set[str]] = {}
    phrases: dict[str, set[str]] = {}
    apologies: dict[str, set[str]] = {}
    for conv in conversations:
        key = tuple((m.role, normalize(m.content)) for m in conv.messages)
        signature.setdefault(key, []).append(conv.conversationId)
        assistant = [m.content for m in conv.messages if m.role == "assistant"]
        if assistant:
            last = normalize(assistant[-1])
            if len(last) >= 4:
                endings.setdefault(last, set()).add(conv.conversationId)
        for bubble in assistant:
            norm = normalize(bubble)
            if len(norm) >= 4 and any(m in bubble for m in APOLOGY_MARKERS):
                apologies.setdefault(norm, set()).add(conv.conversationId)
        for gram in _ngram_set(assistant_text(conv), phrase_ngram):
            phrases.setdefault(gram, set()).add(conv.conversationId)

    for _key, ids in signature.items():
        if len(ids) > 1:
            for cid in ids[:max_items]:
                report.blocking.append(
                    {
                        "check": "duplicate_messages",
                        "conversationId": cid,
                        "detail": f"같은 메시지 묶음이 {len(ids)}개 있다",
                    }
                )
    ending_cap = _cap(bubble_max_conversations, total, 0.02)
    for text, ids in endings.items():
        if len(ids) > ending_cap:
            for cid in sorted(ids)[:max_items]:
                report.blocking.append(
                    {
                        "check": "ending_repetition",
                        "conversationId": cid,
                        "detail": f"마지막 대사 {text[:20]!r}가 {len(ids)}개 대화에 반복된다",
                    }
                )
    apology_cap = _cap(bubble_max_conversations, total, 0.02)
    for text, ids in apologies.items():
        if len(ids) > apology_cap:
            for cid in sorted(ids)[:max_items]:
                report.blocking.append(
                    {
                        "check": "apology_repetition",
                        "conversationId": cid,
                        "detail": f"같은 사과 문장 {text[:20]!r}가 {len(ids)}개 대화에 반복된다",
                    }
                )
    phrase_cap = _cap(phrase_max_conversations, total, 0.02)
    reported: set[str] = set()
    for gram, ids in phrases.items():
        if len(ids) > phrase_cap:
            for cid in sorted(ids)[:max_items]:
                if cid in reported:
                    continue
                reported.add(cid)
                report.blocking.append(
                    {
                        "check": "phrase_repetition",
                        "conversationId": cid,
                        "detail": f"{phrase_ngram}자 조각 {gram!r}가 {len(ids)}개 대화에 반복된다",
                    }
                )

    for conv in conversations:
        user_chars = sum(len(m.content) for m in conv.messages if m.role == "user")
        reply_chars = sum(len(m.content) for m in conv.messages if m.role == "assistant")
        if user_chars and reply_chars / user_chars > 2.0:
            report.warnings.append(
                f"{conv.conversationId}: 답변/사용자 길이 비율이 {reply_chars / user_chars:.2f}다"
            )
        if reply_chars and not user_chars:
            report.warnings.append(f"{conv.conversationId}: 사용자 턴이 비어 있다")
    report.metrics["blocking"] = len(report.blocking)
    report.metrics["warnings"] = len(report.warnings)
    return report
