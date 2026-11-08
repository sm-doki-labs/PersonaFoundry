"""S9 샘플 작성과 G7a 대기 (LLD §8.8 2단계, D-0044·D-0045).

클러스터마다 인계안을 만들고 같은 인계안으로 샘플을 쓴다. 작성 호출은 예산·원장을 거치고,
차단 검사에 걸리면 같은 입력으로 다시 쓴다(첫 성공을 보존한다). `build`도 이 파일의 배치
작성기를 그대로 쓴다(재료·검사·재시도 규칙이 같아야 한다).
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import Field

from character_factory_poc.common.budget import CallPlan
from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.common.schema import dump, register, validate
from character_factory_poc.common.store import (
    read_json,
    write_manifest,
    write_once_bytes,
    write_once_json,
)
from character_factory_poc.contracts.common import ArtifactRef, Strict
from character_factory_poc.contracts.dataset import (
    Conversation,
    ConversationChecks,
    DataHandoff,
    DataPlan,
    DataQa,
    DataSample,
    Message,
    TurnRule,
)
from character_factory_poc.contracts.persona import PromptPair, TraitSheet
from character_factory_poc.pipeline.agent import AgentSpec, run_agent
from character_factory_poc.pipeline.context import Context
from character_factory_poc.stages.s9_data import checks, deck, page, seeds
from character_factory_poc.stages.s9_data import handoff as handoff_mod
from character_factory_poc.stages.s9_data import plan as plan_mod
from character_factory_poc.stages.s9_data import training_prompt as tp_mod
from character_factory_poc.stages.s9_data.plan import S9Config
from character_factory_poc.stages.s9_data.split import FILE_NAME as SPLIT_FILE_NAMES

WRITER_CONTRACT = "data-writer-output-v1"
_SAFE = re.compile(r"[^A-Za-z0-9_-]+")


class WrittenConversation(Strict):
    skeletonKey: str = ""
    scene: str
    sourceId: str = ""
    flowBeats: list[str] = Field(
        default_factory=list,
        description="SNS 재작성: 원본에서 먼저 뽑은 흐름 뼈대 3~8줄(원문 문장 없이). 합성은 빈 배열"
        "",
    )
    messages: list[Message] = Field(min_length=2)
    topicShiftAt: list[int] = Field(
        default_factory=list, description="긴 대화: 화제가 바뀌는 user 메시지 위치(0부터)"
    )
    lateTriggerAt: list[int] = Field(
        default_factory=list, description="긴 대화: 후반 계기 상황이 시작되는 user 메시지 위치"
    )


class WriterOutput(Strict):
    conversations: list[WrittenConversation] = Field(min_length=1)


register(WRITER_CONTRACT)(WriterOutput)

CONTRACT_EXAMPLE = {
    "conversations": [
        {
            "skeletonKey": "rainy-bookshop",
            "scene": "비가 그친 저녁, 책방을 닫고 창가에 남아 문자를 주고받는다.",
            "sourceId": "",
            "flowBeats": [],
            "messages": [
                {"role": "user", "content": "오늘 문 닫았어?"},
                {"role": "assistant", "content": "방금 닫았어.\n아직 창가에 앉아 있어."},
                {"role": "user", "content": "뭐 해?"},
                {"role": "assistant", "content": "시집 한 권 펴 놨는데 한 줄도 안 읽혀."},
            ],
        }
    ]
}

RULES: tuple[str, ...] = (
    "messages는 user와 assistant만 쓴다. user로 시작해 assistant로 끝나고 번갈아 쓴다.",
    "assistant 대사는 캐릭터 한 사람의 말만 쓴다. 상대의 말·행동·감정을 대신 쓰지 않는다.",
    "system은 입력의 system을 그대로 따르고, 새 프롬프트를 만들지 않는다.",
    "scene은 시작 상황 한 문장이다. 다음 전개나 정답을 드러내지 않고 물음표를 넣지 않는다.",
    "SNS 재작성은 원본을 흐름 뼈대로만 쓴다. flowBeats 3~8줄을 먼저 적고 양쪽 대사를 새로 쓴다.",
    "SNS 재작성의 메시지 수는 원본과 같게, 많아야 2개 차이로 쓴다.",
    "대사와 뼈대는 원본과 공백·문장 부호를 빼고 10글자 이상 이어서 같으면 안 된다.",
    "원본 화자의 직업·나이·관계 사실을 캐릭터 설정으로 옮기지 않는다.",
    "갈등은 회복·덜 풀림·선 긋기로 끝낸다. 관계 위협이나 감정 협박으로 끝내지 않는다.",
    "같은 말끝·같은 사과 문장·같은 시작말을 대화 사이에서 반복하지 않는다.",
)


@dataclass(frozen=True)
class Slot:
    material: str
    source: dict[str, Any] | None = None
    # D-0138: 학습용 짧은 프롬프트의 관계·채널 배정.
    relationship: str = "FAVORABLE"
    channel: str = "text"


@dataclass
class WriteSession:
    ctx: Context
    cid: str
    stage: str
    rev: str
    cluster: str
    system: str
    handoff: DataHandoff
    cfg: S9Config
    examples: list[dict[str, Any]] = field(default_factory=list)
    writer_model: str = ""
    turn_rule: TurnRule | None = None
    # D-0138: 학습용 짧은 프롬프트. 있으면 대화마다 핵심 + 관계 + 채널 + 장면으로 system을 만든다.
    training: tp_mod.TrainingPrompt | None = None


def slot_system(session: WriteSession, slot: Slot) -> str:
    if session.training is None:
        return session.system
    return session.training.system(slot.relationship, slot.channel)


def turn_rule_input(rule: TurnRule) -> dict[str, Any]:
    """작성 모델에 넘기는 턴 조건. 출처 문자열은 계획에만 두고 작성 입력에는 넣지 않는다."""
    return {
        "minAssistantTurns": rule.minAssistantTurns,
        "maxAssistantTurns": rule.maxAssistantTurns,
        "minTopicShifts": rule.minTopicShifts,
        "minLateTriggers": rule.minLateTriggers,
        "lateTriggerFromShare": rule.lateTriggerFrom,
        "description": rule.description,
        "markers": (
            "topicShiftAt에 화제가 바뀌는 user 메시지 위치를, lateTriggerAt에 후반 계기 상황이 "
            "시작되는 user 메시지 위치를 0부터 센 정수로 적는다"
        ),
    }


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp, path)


SOURCE_MIN_TURNS = 4
SOURCE_MAX_TURNS = 12
DROP_REASONS = {
    "not_alternating": "말한 사람이 번갈아 나오지 않음",
    "empty_turn": "빈 발화가 있음",
    "too_short": "4턴보다 짧음",
    "over_limit": "후보 상한을 넘음",
    "over_share": "말뭉치 비율 상한을 넘음",
}
# 실제 대화 재료의 출처(D-0134). 말뭉치(국립국어원 구어)는 통화 장면 재료로만 쓴다.
SOURCE_KINDS: dict[str, str] = {"SNS": "SNS", "NIKL": "말뭉치"}
VOICE_CHANNELS: frozenset[str] = frozenset({"call", "video_call", "face_to_face"})
CHANNELS: frozenset[str] = frozenset({"text", *VOICE_CHANNELS})


def source_kind(obj: dict[str, Any]) -> str:
    """후보 한 줄의 출처. source 표시에 NIKL이 있으면 말뭉치, 나머지(표시 없음 포함)는 SNS."""
    return "NIKL" if "NIKL" in str(obj.get("source") or "").upper() else "SNS"


def source_channel(obj: dict[str, Any], kind: str) -> str:
    """후보의 채널. 파일에 channel이 있으면 그것을, 없으면 말뭉치는 통화·SNS는 문자로 둔다."""
    raw = str(obj.get("channel") or "").strip()
    if raw in CHANNELS:
        return raw
    return "call" if kind == "NIKL" else "text"


def _mix(
    sns: list[dict[str, Any]], nikl: list[dict[str, Any]], limit: int, share: float
) -> tuple[list[dict[str, Any]], int, int]:
    """SNS 구간과 말뭉치 구간을 번갈아 놓는다(D-0134).

    앞에서 몇 개를 쓰든 말뭉치가 share 비율 안팎이 되게 자리마다 정한다(make_slots가 앞에서부터
    쓴다). 말뭉치만 있으면 비율을 적용하지 않는다. SNS가 바닥나면 말뭉치를 더 넣지 않는다.
    """
    if not sns:
        share = 1.0
    out: list[dict[str, Any]] = []
    i = j = 0
    while len(out) < limit:
        want = math.floor((len(out) + 1) * share + 0.5)
        if j < len(nikl) and j < want:
            out.append(nikl[j])
            j += 1
        elif i < len(sns):
            out.append(sns[i])
            i += 1
        else:
            break
    return out, i, j


def _usable_source(msgs: list[dict[str, str]]) -> bool:
    return _source_problem(msgs) is None and len(msgs) <= SOURCE_MAX_TURNS


def _source_problem(msgs: list[dict[str, str]]) -> str | None:
    if any(not m["content"].strip() for m in msgs):
        return "empty_turn"
    if not all(m["role"] == ("user" if i % 2 == 0 else "assistant") for i, m in enumerate(msgs)):
        return "not_alternating"
    if len(msgs) < SOURCE_MIN_TURNS:
        return "too_short"
    return None


def _trim(msgs: list[dict[str, str]]) -> list[dict[str, str]]:
    """사용자로 시작하고 캐릭터로 끝나게 앞뒤만 다듬는다(가운데는 건드리지 않는다)."""
    start = 0
    while start < len(msgs) and msgs[start]["role"] != "user":
        start += 1
    end = len(msgs)
    while end > start and msgs[end - 1]["role"] != "assistant":
        end -= 1
    return msgs[start:end]


def _windows(msgs: list[dict[str, str]], size: int) -> tuple[list[list[dict[str, str]]], int]:
    """긴 세션을 size턴 이하 구간으로 자른다(D-0131).

    끝 자투리가 4턴보다 짧으면 버리고 그 턴 수를 돌려준다.
    """
    size = max(SOURCE_MIN_TURNS, size - size % 2)
    parts = [msgs[k : k + size] for k in range(0, len(msgs), size)]
    left = 0
    if len(parts) > 1 and len(parts[-1]) < SOURCE_MIN_TURNS:
        left = len(parts[-1])
        parts = parts[:-1]
    return parts, left


def read_sns_sources(
    path: str, limit: int, window: int = SOURCE_MAX_TURNS, corpus_share: float = 0.2
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """설정 경로의 후보 대화를 읽기 전용으로 열고, 쓸 수 있는 4~window턴 구간과 집계를 돌려준다.

    S9 작성 요청은 후보 한 개를 4~12턴으로 받는다. 실제 말뭉치·SNS 세션은 20~150턴이라 그대로는
    모두 버려졌다(K-0103). 그래서 긴 세션은 window턴 이하 구간으로 자르고, 같은 세션의 구간은
    sessionId를 같게 둔다. skeleton_id가 sessionId를 쓰므로 분할이 한 세션을 학습·검증으로 나누지
    않는다. 버린 후보는 이유별로 센다(데이터셋 경고). 원문은 저장소에 쓰지 않는다(D-0007).

    출처(D-0134): source에 NIKL이 있는 후보는 말뭉치다. 말뭉치 구간은 통화 채널로 표시하고,
    SNS 구간 사이에 corpus_share 비율로 섞는다. 구간마다 source·channel이 붙는다.
    """
    stats: dict[str, Any] = {
        "path": Path(path).name if path else "",
        "sessions": 0,
        "split": 0,
        "windows": 0,
        "offered": 0,
        "dropped": {},
        "leftoverTurns": 0,
        "window": window,
        "limit": limit,
        "corpusShare": corpus_share,
        "bySource": {},
    }
    if not path or limit <= 0:
        return [], stats
    p = Path(path)
    if not p.exists():
        stats["missing"] = True
        return [], stats
    text = p.read_text("utf-8")
    if text.lstrip().startswith("["):
        rows: list[Any] = json.loads(text)
    else:
        rows = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    dropped: Counter = Counter()
    sessions: dict[str, list[list[dict[str, Any]]]] = {"SNS": [], "NIKL": []}
    by_source: dict[str, Counter] = {}
    for obj in rows:
        stats["sessions"] += 1
        kind = source_kind(obj)
        channel = source_channel(obj, kind)
        seen = by_source.setdefault(kind, Counter())
        seen["sessions"] += 1
        turns = obj.get("messages") or obj.get("turns") or []
        msgs = [
            {"role": str(t.get("role", "")), "content": str(t.get("content", ""))} for t in turns
        ]
        msgs = _trim(msgs)
        problem = _source_problem(msgs)
        if problem:
            dropped[problem] += 1
            continue
        sid = str(obj.get("conversationId") or obj.get("id") or f"sns-{stats['sessions']:04d}")
        if len(msgs) <= window:
            parts, left = [msgs], 0
        else:
            parts, left = _windows(msgs, window)
            stats["split"] += 1
            stats["leftoverTurns"] += left
        stats["windows"] += len(parts)
        seen["windows"] += len(parts)
        sessions[kind].append(
            [
                {
                    "sourceId": sid if len(parts) == 1 else f"{sid}~w{k + 1}",
                    "sessionId": sid,
                    "source": kind,
                    "channel": channel,
                    "turns": part,
                }
                for k, part in enumerate(parts)
            ]
        )

    # 출처마다 세션의 첫 구간부터 돌아가며 놓는다.
    # 앞 세션의 구간이 자리를 다 차지하면 쓰는 세션 수가 줄어든다.
    def _order(group: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
        depth = max((len(s) for s in group), default=0)
        return [s[k] for k in range(depth) for s in group if k < len(s)]

    sns, nikl = _order(sessions["SNS"]), _order(sessions["NIKL"])
    out, i, j = _mix(sns, nikl, limit, corpus_share)
    if len(sns) > i:
        dropped["over_limit"] += len(sns) - i
    if len(nikl) > j:
        dropped["over_share" if sns else "over_limit"] += len(nikl) - j
    for s in out:
        by_source[s["source"]]["offered"] += 1
    stats["offered"] = len(out)
    stats["dropped"] = dict(dropped)
    stats["bySource"] = {
        k: {"sessions": c["sessions"], "windows": c["windows"], "offered": c["offered"]}
        for k, c in by_source.items()
    }
    return out, stats


def load_sns_sources(
    path: str, limit: int, window: int = SOURCE_MAX_TURNS, corpus_share: float = 0.2
) -> list[dict[str, Any]]:
    """설정 경로의 후보 대화(4~window턴 구간). 집계가 필요하면 read_sns_sources를 쓴다."""
    return read_sns_sources(path, limit, window, corpus_share)[0]


def source_warning(stats: dict[str, Any], used: int) -> str | None:
    """실제 대화 재료(SNS·말뭉치) 집계를 데이터셋 경고 한 줄로.

    쓸 후보가 있었는데 바뀐 것이 없으면 None.
    """
    if not stats.get("path"):
        return None
    if stats.get("missing"):
        return f"실제 대화 재료: 후보 파일 {stats['path']}을 찾지 못해 모두 합성으로 채웠어요"
    dropped = stats.get("dropped") or {}
    lost = sum(n for k, n in dropped.items() if k not in ("over_limit", "over_share"))
    over = dropped.get("over_limit", 0)
    if (
        not (lost or over or dropped.get("over_share") or stats.get("split"))
        and used == stats.get("offered")
        and not (stats.get("usedBySource") or {}).get("NIKL")
    ):
        return None
    parts = [f"실제 대화 재료: 후보 대화 {stats['sessions']}개"]
    if stats.get("split"):
        parts.append(
            f"긴 대화 {stats['split']}개는 {stats['window']}턴 이하 구간으로 나눠 구간 "
            f"{stats['windows']}개가 됐어요"
        )
    if lost:
        why = ", ".join(
            f"{DROP_REASONS.get(k, k)} {n}"
            for k, n in sorted(dropped.items())
            if k not in ("over_limit", "over_share")
        )
        parts.append(f"{lost}개는 버렸어요({why})")
    if over:
        parts.append(f"상한 {stats['limit']}개를 넘은 구간 {over}개는 쓰지 않았어요")
    share_over = dropped.get("over_share", 0)
    if share_over:
        parts.append(
            f"말뭉치 비율 {round(stats.get('corpusShare', 0) * 100)}%를 넘은 말뭉치 구간 "
            f"{share_over}개는 쓰지 않았어요"
        )
    mix = stats.get("usedBySource") or {}
    if mix.get("NIKL"):
        parts.append(
            f"이번 데이터에 쓴 구간 {used}개(SNS {mix.get('SNS', 0)} · 말뭉치 {mix['NIKL']}, "
            "말뭉치는 통화 장면)"
        )
    else:
        parts.append(f"이번 데이터에 쓴 구간 {used}개")
    return " · ".join(parts)


def make_slots(
    cfg: S9Config, cluster: str, needed: int, sources: list[dict[str, Any]], start: int = 0
) -> list[Slot]:
    materials = cfg.materials[cluster]
    rels = tp_mod.assign_relationships(cfg.relationship_shares, start, needed)
    slots: list[Slot] = []
    source_i = 0
    for k in range(needed):
        material = materials[(start + k) % len(materials)]
        if material == "SNS_REWRITE" and source_i < len(sources):
            src = sources[source_i]
            slots.append(Slot("SNS_REWRITE", src, rels[k], str(src.get("channel") or "text")))
            source_i += 1
        else:
            slots.append(Slot("SYNTH", None, rels[k], cfg.synth_channel))
    return slots


def _source_input(i: int, s: Slot) -> dict[str, Any]:
    src = s.source or {}
    base = {
        "index": i,
        "sourceId": src["sourceId"],
        # D-0134: 말뭉치 구간은 통화 장면으로 쓴다.
        "origin": src.get("source", "SNS"),
        "channel": src.get("channel", "text"),
    }
    if "seed" in src:
        # D-0138: 작가는 원문을 보지 않고 시드만 본다.
        return {
            **base,
            "seed": src["seed"],
            "sourceTurns": len(src.get("turns") or []),
            "lengths": seeds.lengths(src.get("turns") or []),
        }
    return {**base, "turns": src["turns"]}


def batch_inputs(
    session: WriteSession, slots: list[Slot], ids: list[str], notes: list[str]
) -> dict[str, Any]:
    tp = session.training
    out: dict[str, Any] = {
        "system": tp.core if tp is not None else session.system,
        "handoff": dump(session.handoff),
        "batch": {
            "clusterId": session.cluster,
            "count": len(slots),
            "conversationIds": ids,
            "materials": [s.material for s in slots],
            "sources": [_source_input(i, s) for i, s in enumerate(slots) if s.source is not None],
            "skeletonRule": "같은 장면 뼈대에서 나온 대화는 같은 skeletonKey를 쓴다",
        },
        "examples": session.examples,
        "reviewNotes": [n for n in notes if n],
    }
    if session.turn_rule is not None:
        out["batch"]["turnRule"] = turn_rule_input(session.turn_rule)
    if tp is not None:
        out["batch"]["assignments"] = [
            {
                "index": i,
                "relationship": s.relationship,
                "relationshipText": tp.relationships.get(s.relationship, ""),
                "channel": s.channel,
                "channelText": tp.channels.get(s.channel, ""),
            }
            for i, s in enumerate(slots)
        ]
        out["batch"]["turnMaxChars"] = session.cfg.turn_max_chars
    return out


def _specs(session: WriteSession, slots: list[Slot]) -> list[checks.ConvSpec]:
    forbidden = tuple(session.handoff.forbidden) + session.cfg.forbidden_phrases
    return [
        checks.ConvSpec(
            cluster_id=session.cluster,
            system=slot_system(session, s),
            material=s.material,
            source=s.source,
            forbidden=forbidden,
            source_facts=session.cfg.source_facts,
            max_length_tokens=session.cfg.max_length_tokens,
            chars_per_token=session.cfg.chars_per_token,
            turn_rule=session.turn_rule,
            relationship=s.relationship if session.training is not None else "",
            turn_max_chars=session.cfg.turn_max_chars,
        )
        for s in slots
    ]


def skeleton_id(cluster: str, slot: Slot, written: dict[str, Any]) -> str:
    if slot.material == "SNS_REWRITE" and slot.source is not None:
        # 같은 세션에서 자른 구간은 같은 뼈대로 묶는다(D-0131).
        raw = slot.source.get("sessionId") or slot.source.get("sourceId")
        sid = _SAFE.sub("-", str(raw)).strip("-") or "unknown"
        return f"sns-{sid}"
    key = str(written.get("skeletonKey") or "").strip()
    return "synth-" + sha256_text(f"{cluster}|{key}")[:10]


def assemble(
    session: WriteSession,
    slots: list[Slot],
    ids: list[str],
    written: list[dict[str, Any]],
    request_ref: str,
) -> list[Conversation]:
    specs = _specs(session, slots)
    out: list[Conversation] = []
    for i, (slot, item) in enumerate(zip(slots, written, strict=True)):
        scene = str(item.get("scene") or "").strip()
        system = slot_system(session, slot).rstrip() + "\n\n[SCENE]\n" + scene
        messages = [Message(role=m["role"], content=m["content"]) for m in item["messages"]]
        conv = Conversation(
            conversationId=ids[i],
            clusterId=session.cluster,  # type: ignore[arg-type]
            material=slot.material,  # type: ignore[arg-type]
            skeletonId=skeleton_id(session.cluster, slot, item),
            system=system,
            messages=messages,
            provenance={
                "writerModel": session.writer_model,
                "requestRef": request_ref,
                "sourceRef": str((slot.source or {}).get("sourceId") or ""),
                "flowBeats": checks.slot_beats(slot.source, item)
                if slot.material == "SNS_REWRITE"
                else [],
                "relationship": slot.relationship if session.training is not None else "",
                "channel": slot.channel if session.training is not None else "",
                "editedBy": "model",
            },
        )
        blocking = checks.evaluate(conv, specs[i])
        if session.turn_rule is not None:
            blocking["long_structure"] = not checks.structure_problems(item, session.turn_rule)
        warnings = (["답변/사용자 길이 비율이 2를 넘는다"] if _ratio(conv) > 2.0 else []) + (
            checks.style_warnings(conv)
        )
        out.append(
            conv.model_copy(
                update={"checks": ConversationChecks(blocking=blocking, warnings=warnings)}
            )
        )
    return out


def _ratio(conv: Conversation) -> float:
    user = sum(len(m.content) for m in conv.messages if m.role == "user")
    reply = sum(len(m.content) for m in conv.messages if m.role == "assistant")
    return reply / user if user else 0.0


def write_batch(
    session: WriteSession, slots: list[Slot], ids: list[str], notes: list[str] | None = None
) -> list[Conversation]:
    """한 배치를 쓴다. 차단 검사 실패는 같은 입력으로 다시 쓰고, 첫 성공을 보존한다."""
    # D-0138: 실제 대화 재료는 먼저 흐름 시드를 붙이고, 작가에게는 시드만 넘긴다.
    slots = seeds.attach(session, slots)
    if deck.enabled(session.ctx):
        return deck.write_batch(session, slots, ids, notes or [""] * len(slots))
    budget = session.ctx.budget()
    model = session.ctx.text_model(session.cid, budget)
    inputs = batch_inputs(session, slots, ids, notes or [""] * len(slots))
    specs = _specs(session, slots)
    problems: list[str] = []
    for attempt in range(1, session.cfg.max_retries + 2):
        workspace = (
            session.ctx.config.root
            / "work"
            / "s9-data"
            / f"{session.rev}-{session.cluster}-{ids[0]}-a{attempt}"
        )
        check = lambda out: checks.batch_problems(  # noqa: E731
            [c.model_dump() for c in out.conversations], specs, session.system
        )
        spec = AgentSpec(
            role="data_writer",
            output_contract=WRITER_CONTRACT,
            stage=session.stage,
            max_check_retries=0,
        )
        result = run_agent(
            spec,
            workspace,
            inputs,
            [check],
            model,
            ref=f"{session.cid}/{session.rev}/{session.cluster}/{ids[0]}#{attempt}",
            contract_example=CONTRACT_EXAMPLE,
            backend=session.ctx.agent_backend(session.cid, budget, session.stage),
        )
        request_ref = f"requests/{session.cluster}-{ids[0]}-a{attempt}.json"
        _write_json(
            request_dir(session) / f"{session.cluster}-{ids[0]}-a{attempt}.json",
            {
                "stage": session.stage,
                "cluster": session.cluster,
                "conversationIds": ids,
                "model": model.model,
                "attempt": attempt,
                "input": inputs,
                "ok": result.ok,
                "problems": result.problems,
            },
        )
        if result.ok:
            written = [c.model_dump() for c in result.output.conversations]
            return assemble(session, slots, ids, written, request_ref)
        problems = result.problems
    stage = session.stage
    raise CheckFailed(stage, [f"{session.cluster}/{ids[0]}: {p}" for p in problems])


def request_dir(session: WriteSession) -> Path:
    return plan_mod.data_dir(session.ctx, session.cid) / session.rev / "requests"


def _run_batches(items: list[Any], fn, concurrency: int) -> list[Any]:
    if concurrency <= 1 or len(items) <= 1:
        return [fn(i, item) for i, item in enumerate(items)]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(fn, i, item) for i, item in enumerate(items)]
        return [f.result() for f in futures]


def chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def write_conversations(
    session: WriteSession,
    *,
    ids: list[str],
    slots: list[Slot],
    notes: list[str] | None = None,
    rev_dir: Path | None = None,
) -> list[Conversation]:
    """배치로 나눠 쓰고 대화 파일을 남긴다. 반환 순서는 입력 ids 순서와 같다."""
    notes = notes or [""] * len(ids)
    id_chunks = chunked(ids, session.cfg.batch_size)
    slot_chunks = chunked(slots, session.cfg.batch_size)
    pairs = list(zip(id_chunks, slot_chunks, strict=True))

    def one(_i: int, pair) -> list[Conversation]:
        batch_ids, batch_slots = pair
        start = ids.index(batch_ids[0])
        convs = write_batch(session, batch_slots, batch_ids, notes[start : start + len(batch_ids)])
        folder = rev_dir or plan_mod.data_dir(session.ctx, session.cid) / session.rev
        for conv in convs:
            write_once_json(folder / "conversations" / f"{conv.conversationId}.json", dump(conv))
        return convs

    out: list[Conversation] = []
    for convs in _run_batches(pairs, one, session.cfg.concurrency):
        out.extend(convs)
    order = {cid: i for i, cid in enumerate(ids)}
    return sorted(out, key=lambda c: order[c.conversationId])


def load_examples(rev_dir: Path, refs: list[ArtifactRef], limit: int = 3) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ref in refs[:limit]:
        conv = validate("conversation-v1", read_json(rev_dir / ref.ref))
        out.append({"system": conv.system, "messages": [dump(m) for m in conv.messages]})
    return out


def sample_refs(rev_dir: Path, cluster: str) -> list[ArtifactRef]:
    path = rev_dir / "samples" / f"{cluster}.json"
    if not path.exists():
        return []
    bundle = validate("data-sample-v1", read_json(path))
    return list(bundle.conversations)  # type: ignore[arg-type]


def load_samples(rev_dir: Path, cluster: str) -> list[Conversation]:
    return [
        validate("conversation-v1", read_json(rev_dir / ref.ref))
        for ref in sample_refs(rev_dir, cluster)
    ]


def cluster_qa(rev_dir: Path, cluster: str) -> DataQa | None:
    path = rev_dir / "qa" / f"G7a-{cluster}.json"
    if not path.exists():
        return None
    return validate("data-qa-v2", read_json(path))  # type: ignore[return-value]


def reviews(rev_dir: Path) -> dict[str, DataQa]:
    ids = plan_mod.plan_cluster_ids(rev_dir)
    return {c: qa for c in ids if (qa := cluster_qa(rev_dir, c)) is not None}


def plan_turn_rule(plan: DataPlan, cluster: str) -> TurnRule | None:
    for c in plan.clusters:
        if c.clusterId == cluster and c.policy is not None:
            return c.policy.turnRule
    return None


def requested_changes(rev_dir: Path) -> dict[str, str]:
    path = rev_dir / "requests" / "g7a-changes.json"
    if not path.exists():
        return {}
    obj = json.loads(path.read_text("utf-8"))
    return {str(k): str(v) for k, v in (obj.get("clusters") or {}).items()}


def carry_forward(prev: Path, new: Path, skip_clusters: set[str]) -> None:
    """이전 rev에서 이번 rev로 파일을 복사한다. 다시 쓰는 클러스터의 인계안·샘플은 뺀다."""
    derived = {
        "dataset.json",
        "index.jsonl",
        "frozen.json",
        "manifest.sha256",
        *SPLIT_FILE_NAMES.values(),
    }
    for path in sorted(prev.rglob("*")):
        if not path.is_file() or path.name in derived:
            continue
        rel = path.relative_to(prev)
        head = rel.parts[0]
        if head in {"handoffs", "samples"} and rel.stem in skip_clusters:
            continue
        if head == "qa" and rel.name.startswith("G7a-"):
            cluster = rel.name[len("G7a-") : -len(".json")]
            if cluster in skip_clusters:
                continue
        if head == "requests" and rel.name == "g7a-changes.json":
            continue
        if head == "conversations" and any(f"-{c}-" in rel.name for c in skip_clusters):
            continue
        write_once_bytes(new / rel, path.read_bytes())


def _sample_cluster(
    ctx: Context,
    cid: str,
    *,
    cfg: S9Config,
    rev: str,
    rev_dir: Path,
    plan: DataPlan,
    plan_sha: str,
    pair: PromptPair,
    sheet: TraitSheet,
    cluster: str,
    sources: list[dict[str, Any]],
    memo: str,
) -> None:
    sample_path = rev_dir / "samples" / f"{cluster}.json"
    if sample_path.exists() and not memo:
        return
    handoff_path = rev_dir / "handoffs" / f"{cluster}.json"
    if memo or not handoff_path.exists():
        workspace = ctx.config.root / "work" / "s9-data" / f"{rev}-{cluster}-handoff"
        handoff = handoff_mod.build_handoff(
            ctx,
            cid,
            plan=plan,
            plan_sha=plan_sha,
            cluster_id=cluster,
            pair=pair,
            sheet=sheet,
            workspace=workspace,
            stage="s9s",
            retries=cfg.max_retries,
            memo=memo,
        )
        write_once_json(handoff_path, dump(handoff))
    handoff = validate("data-handoff-v1", read_json(handoff_path))
    count = next(c.sampleSize for c in plan.clusters if c.clusterId == cluster)
    slots = make_slots(cfg, cluster, count, sources)
    ids = [f"{rev}-{cluster}-s{i:03d}" for i in range(count)]
    session = WriteSession(
        ctx=ctx,
        cid=cid,
        stage="s9s",
        rev=rev,
        cluster=cluster,
        system=pair.short.text,
        handoff=handoff,  # type: ignore[arg-type]
        cfg=cfg,
        examples=[],
        writer_model=deck.writer_model(ctx),
        turn_rule=plan_turn_rule(plan, cluster),
        training=tp_mod.ensure(rev_dir, pair),
    )
    convs = write_conversations(session, ids=ids, slots=slots, rev_dir=rev_dir)
    write_once_json(
        sample_path,
        dump(
            DataSample(
                characterId=cid,
                planSha256=plan_sha,
                clusterId=cluster,  # type: ignore[arg-type]
                handoffSha256=sha256_file(handoff_path),
                conversations=[
                    ArtifactRef(
                        ref=f"conversations/{c.conversationId}.json",
                        sha256=sha256_file(rev_dir / "conversations" / f"{c.conversationId}.json"),
                    )
                    for c in convs
                ],
            )
        ),
    )


def _write_pages(ctx: Context, cid: str, rev: str, rev_dir: Path, plan: DataPlan) -> None:
    rows = [dump(c) for c in plan.clusters]
    pages: dict[str, str] = {}
    for c in plan.clusters:
        convs = load_samples(rev_dir, c.clusterId)
        if not convs:
            continue
        handoff = validate(
            "data-handoff-v1", read_json(rev_dir / "handoffs" / f"{c.clusterId}.json")
        )
        html = page.render_g7a_cluster(
            subject_id=cid,
            rev=rev,
            cluster=c,
            handoff=handoff,  # type: ignore[arg-type]
            conversations=convs,
            sample_sha=sha256_file(rev_dir / "samples" / f"{c.clusterId}.json"),
        )
        name = f"gate-G7a-{c.clusterId}.html"
        (rev_dir / name).write_text(html, encoding="utf-8")
        pages[c.clusterId] = name
    index = page.render_g7a_index(subject_id=cid, rev=rev, plan_rows=rows, pages=pages)
    (rev_dir / "gate-G7a.html").write_text(index, encoding="utf-8")


def _close_gate(ctx: Context, cid: str, rev: str, rev_dir: Path, plan: DataPlan) -> Path:
    state = ctx.state(cid)
    state.set_gate("G7a", "APPROVED", rev, None)
    if state.stage("s9s").status == "AWAITING_HUMAN":
        state.transition("s9s", "APPROVED", rev=rev)
    write_manifest(rev_dir)
    return rev_dir


def plan_calls(ctx: Context, cid: str, cfg: S9Config | None = None) -> list[CallPlan]:
    cfg = cfg or plan_mod.s9_config(ctx)
    clusters = len(cfg.cluster_ids)
    if deck.enabled(ctx):
        batches = clusters * -(-cfg.sample_size // cfg.batch_size)
        return [
            CallPlan(
                "s9s",
                "모델 덱 상황 인계안 (형식 재시도 최대 2회 포함)",
                clusters * (1 + deck.FORMAT_RETRIES),
                est_cost_usd=None,
            ),
            *deck.batch_plan("s9s", batches),
        ]
    handoffs = handoff_mod.plan_calls(clusters, cfg.max_retries)
    batches = sum(-(-cfg.sample_size // cfg.batch_size) for _ in cfg.cluster_ids)
    writer = CallPlan(
        "s9s",
        f"클러스터별 샘플 {cfg.sample_size}개 × {clusters} (배치 {cfg.batch_size}, "
        f"재시도 포함 최대 {1 + cfg.max_retries}회)",
        batches * (1 + cfg.max_retries),
    )
    return handoffs + [writer]


def run_samples(ctx: Context, cid: str) -> Path:
    """`cfp data samples`: 인계안·샘플을 쓰고 G7a 대기로 둔다."""
    state = ctx.state(cid)
    state.require_deps("s9s")
    cfg = plan_mod.s9_config(ctx)
    pair, _pair_path = plan_mod.load_prompt_pair(ctx, cid)
    sheet, _sheet_path = plan_mod.load_trait_sheet(ctx, cid)
    st = state.stage("s9s")
    data_root = plan_mod.data_dir(ctx, cid)

    if state.gate("G7a").status == "APPROVED" and st.currentRev:
        deck.pin(ctx, data_root / st.currentRev)
        return data_root / st.currentRev
    if st.status == "AWAITING_HUMAN":
        rev = st.currentRev
        if not rev:
            raise FactoryError(f"{cid}: s9s가 대기 상태인데 revision이 없다")
        rev_dir = data_root / rev
        deck.pin(ctx, rev_dir)
        plan = plan_mod.load_plan(rev_dir / "plan.json")
        if len(reviews(rev_dir)) == len(plan.clusters):
            return _close_gate(ctx, cid, rev, rev_dir, plan)
        raise FactoryError(
            f"{cid}: G7a 검토가 진행 중이다. 남은 클러스터를 판정하거나 REQUEST_CHANGES를 기록한다"
        )

    carry_from = data_root / st.currentRev if st.status == "REJECTED" and st.currentRev else None
    if carry_from is not None and not (carry_from / "plan.json").exists():
        carry_from = None
    memo_by_cluster = requested_changes(carry_from) if carry_from else {}

    if carry_from is None and st.currentRev and (data_root / st.currentRev / "plan.json").exists():
        rev = st.currentRev
    else:
        rev = plan_mod.new_rev(ctx, cid)
    rev_dir = data_root / rev
    if carry_from is not None and carry_from != rev_dir:
        carry_forward(carry_from, rev_dir, set(memo_by_cluster))
    if not (rev_dir / "plan.json").exists():
        plan = plan_mod.build_plan(ctx, cid)
        write_once_json(rev_dir / "plan.json", dump(plan))
        deck.pin(ctx, rev_dir, create=True)
    else:
        deck.pin(ctx, rev_dir)
    plan = plan_mod.load_plan(rev_dir / "plan.json")
    plan_sha = sha256_file(rev_dir / "plan.json")

    state.transition("s9s", "RUNNING", rev=rev)

    sns = load_sns_sources(cfg.sns_path, cfg.sns_limit, cfg.sns_window, cfg.corpus_share)
    try:
        for c in plan.clusters:
            sources = sns if "SNS_REWRITE" in cfg.materials[c.clusterId] else []
            _sample_cluster(
                ctx,
                cid,
                cfg=cfg,
                rev=rev,
                rev_dir=rev_dir,
                plan=plan,
                plan_sha=plan_sha,
                pair=pair,
                sheet=sheet,
                cluster=c.clusterId,
                sources=sources,
                memo=memo_by_cluster.get(c.clusterId, ""),
            )
    except CheckFailed as e:
        state.transition("s9s", "CHECK_FAILED", rev=rev, error=str(e)[:500])
        raise
    _write_pages(ctx, cid, rev, rev_dir, plan)
    write_manifest(rev_dir)
    state.transition("s9s", "AWAITING_HUMAN", rev=rev)
    state.set_gate("G7a", "AWAITING_HUMAN", rev, None)
    return rev_dir
