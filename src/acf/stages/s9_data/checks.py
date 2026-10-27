"""S9 기계 검사 (LLD §8.8 4단계, 가이드 §8·§9.2).

두 층이다. 한 대화 안의 차단 검사는 작성 응답을 받은 자리에서 돌리고, 실패하면 같은 입력으로
다시 쓴다. 데이터셋 전체 검사(중복·같은 말끝·같은 사과 문장)는 모든 대화를 모은 뒤 돌린다.
토큰화 도구가 없으므로 길이는 글자 수 근사로 재고, 근사임을 보고서에 남긴다.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from acf.contracts.dataset import Conversation, Message

BLOCKING_NAMES: tuple[str, ...] = (
    "roles_alternate",
    "system_present",
    "no_empty",
    "sns_user_turns_verbatim",
    "no_prefill",
    "source_facts_absent",
    "forbidden_phrases",
    "max_length",
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


def normalize(text: str) -> str:
    return _STRIP.sub("", text)


def approx_tokens(text: str, chars_per_token: float) -> int:
    """토큰화 도구가 없을 때 쓰는 글자 수 근사. 보고서에 근사임을 남긴다."""
    return math.ceil(len(text) / chars_per_token) if text else 0


def conversation_text(conv: Conversation) -> str:
    body = "\n".join(m.content for m in conv.messages)
    return f"{conv.system}\n{body}"


def assistant_text(conv: Conversation) -> str:
    return "\n".join(m.content for m in conv.messages if m.role == "assistant")


def _alternates(messages: list[Message]) -> bool:
    if len(messages) < 2 or len(messages) % 2:
        return False
    return all(m.role == ("user" if i % 2 == 0 else "assistant") for i, m in enumerate(messages))


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
        "sns_user_turns_verbatim": True,
        "source_facts_absent": True,
        "forbidden_phrases": True,
        "max_length": approx_tokens(conversation_text(conv), spec.chars_per_token)
        <= spec.max_length_tokens,
    }
    if spec.material == "SNS_REWRITE" and spec.source is not None:
        source_turns = [t for t in spec.source.get("turns", []) if t.get("role") == "user"]
        user_turns = [m for m in messages if m.role == "user"]
        results["sns_user_turns_verbatim"] = [t["content"] for t in source_turns] == [
            m.content for m in user_turns
        ] and len(source_turns) == len(user_turns)
    joined = conversation_text(conv)
    if spec.source_facts:
        results["source_facts_absent"] = not any(f and f in joined for f in spec.source_facts)
    if spec.forbidden:
        speech = assistant_text(conv)
        results["forbidden_phrases"] = not any(f and f in speech for f in spec.forbidden)
    return results


_REASON: dict[str, str] = {
    "roles_alternate": "user·assistant가 번갈아 나오고 user로 시작해 assistant로 끝나야 한다",
    "system_present": "system(짧은 프롬프트 + 시작 장면)이 비어 있다",
    "no_empty": "빈 답이나 빈 메시지가 있다",
    "sns_user_turns_verbatim": "SNS 원문의 사용자 턴을 글자 그대로 유지하지 않았다",
    "no_prefill": "첫 메시지가 user가 아니거나 system에 이력·프리필 표지가 있다",
    "source_facts_absent": "원본 화자의 사실이 캐릭터 설정·대사에 들어갔다",
    "forbidden_phrases": "인계안의 금지 표현이 캐릭터 대사에 있다",
    "max_length": "학습 길이(토큰 근사) 상한을 넘었다",
}


def problems_of(results: dict[str, bool]) -> list[str]:
    return [f"{name}: {_REASON[name]}" for name in BLOCKING_NAMES if not results.get(name, True)]


def conversation_problems(conv: Conversation, spec: ConvSpec) -> list[str]:
    return problems_of(evaluate(conv, spec))


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
            system=system,
            messages=messages,
            provenance={"writerModel": "probe", "requestRef": "probe"},
        )
        problems.extend(f"{i + 1}번째: {p}" for p in conversation_problems(conv, spec))
        scene = str(item.get("scene") or "").strip()
        if not 5 <= len(scene) <= 200:
            problems.append(f"{i + 1}번째: scene은 5~200자의 한 문장이어야 한다(받은 값 {scene!r})")
        elif "?" in scene:
            problems.append(f"{i + 1}번째: scene에 질문(?)을 넣지 않는다")
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
