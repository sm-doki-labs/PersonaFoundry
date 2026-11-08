"""학습용 짧은 프롬프트 조립(D-0138, 한소민 QLoRA 가이드 §3).

한소민은 성격 핵심(699자) + 관계 문장 + 채널 문장 + 시작 장면으로 학습했다. 공장의 짧은 프롬프트는
서비스 공통 규칙 전문이 들어 있어 학습 길이 상한을 넘었다(K-0106). 여기서는 승인된 프롬프트에서
페르소나 칸만 가져와 학습용 핵심을 만든다. 조건부 경향은 예외 문장('이 경향을 쓰지 않는다',
'드물게 나온다')을 빼고 남기며, 경향은 학습 데이터로 가르친다. 관계·채널 문장은 공장 공통 자원이다.
결정적 조립이라 같은 프롬프트에서 늘 같은 결과가 나온다. 페르소나 칸이 없는 옛 프롬프트는 짧은
프롬프트를 그대로 핵심으로 쓴다.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

from character_factory_poc.common.canonical import sha256_text
from character_factory_poc.common.errors import CheckFailed
from character_factory_poc.common.store import read_json, write_once_json

RESOURCE = "training-prompt-components-v1.json"
RELATIONSHIPS: tuple[str, ...] = ("STRONGLY_FAVORABLE", "FAVORABLE", "NEUTRAL", "UNFAVORABLE")
CHANNELS: tuple[str, ...] = ("text", "call", "video_call", "face_to_face")
CLOSE: frozenset[str] = frozenset({"STRONGLY_FAVORABLE", "FAVORABLE"})
CORE_SECTIONS: tuple[str, ...] = (
    "FACTS",
    "LIFE_AND_TASTES",
    "DISPOSITION",
    "WANTS_AND_FEARS",
    "READING_AND_TENSION",
    "CHOICES",
    "VOICE",
    "KNOWS_AND_LIMITS",
)
_HEAD = re.compile(r"(?m)^\[([A-Z_ /]+)\]\s*$")
_SENT = re.compile(r"(?<=[.!?])\s+")
_DROP = ("이 경향을 쓰지 않는다", "드물게 나온다")
FILE_NAME = "training-prompt.json"
SERVICE_CHANNEL = "video_call"


def components() -> dict[str, Any]:
    return json.loads(
        files("character_factory_poc.resources").joinpath(RESOURCE).read_text("utf-8")
    )


def sections(text: str) -> dict[str, str]:
    """'[NAME]' 줄로 나뉜 프롬프트를 칸 이름 → 본문으로."""
    out: dict[str, str] = {}
    marks = list(_HEAD.finditer(text))
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        out[m.group(1).strip()] = text[m.end() : end].strip()
    return out


def compress_choices(body: str) -> str:
    """조건부 경향에서 예외·빈도 문장을 뺀다. 경향 자체는 남긴다."""
    lines = []
    for line in body.splitlines():
        kept = [s for s in _SENT.split(line.strip()) if s and not any(d in s for d in _DROP)]
        if kept:
            lines.append(" ".join(kept))
    return "\n".join(lines)


@dataclass(frozen=True)
class TrainingPrompt:
    core: str
    relationships: dict[str, str] = field(default_factory=dict)
    channels: dict[str, str] = field(default_factory=dict)
    origin: str = "persona-sections"
    version: str = ""

    def system(self, relationship: str, channel: str) -> str:
        parts = [self.core.rstrip()]
        if relationship in self.relationships:
            parts.append("[RELATIONSHIP]\n" + self.relationships[relationship])
        if channel in self.channels:
            parts.append("[CHANNEL]\n" + self.channels[channel])
        return "\n\n".join(parts)

    def body(self) -> dict[str, Any]:
        longest = max(
            (len(self.system(r, c)) for r in self.relationships for c in self.channels),
            default=len(self.core),
        )
        return {
            "schemaVersion": "training-prompt-v1",
            "components": self.version,
            "origin": self.origin,
            "core": self.core,
            "coreChars": len(self.core),
            "coreSha256": sha256_text(self.core),
            "relationships": self.relationships,
            "channels": self.channels,
            "longestSystemChars": longest,
            "assembly": components().get("assembly", ""),
        }


def build(pair: Any) -> TrainingPrompt:
    comp = components()
    long = getattr(pair, "long", None)
    short = getattr(pair, "short", None)
    text = (long.text if long is not None else "") or (short.text if short is not None else "")
    secs = sections(text)
    persona = {k.split("/", 1)[1].strip(): v for k, v in secs.items() if k.startswith("PERSONA /")}
    if persona:
        parts = []
        if secs.get("ACTOR_IDENTITY"):
            parts.append("[ACTOR_IDENTITY]\n" + secs["ACTOR_IDENTITY"])
        for name in CORE_SECTIONS:
            if persona.get(name):
                body = compress_choices(persona[name]) if name == "CHOICES" else persona[name]
                parts.append(f"[PERSONA / {name}]\n{body.strip()}")
        parts.append("[TRAINING_RULES]\n" + comp["coreRules"].strip())
        core, origin = "\n\n".join(parts), "persona-sections"
    else:
        core = (short.text if short is not None else text).strip()
        origin = "legacy-short"
    return TrainingPrompt(
        core=core,
        relationships=dict(comp["relationships"]),
        channels=dict(comp["channels"]),
        origin=origin,
        version=str(comp.get("version", "")),
    )


def ensure(rev_dir: Path, pair: Any) -> TrainingPrompt:
    """revision 폴더에 학습용 짧은 프롬프트를 남긴다. 이미 있으면 같은지 확인한다."""
    tp = build(pair)
    path = rev_dir / FILE_NAME
    if path.exists():
        if read_json(path).get("coreSha256") != tp.body()["coreSha256"]:
            raise CheckFailed("s9", ["학습용 짧은 프롬프트가 이 revision의 기록과 다르다"])
        return tp
    write_once_json(path, tp.body())
    return tp


def load(path: Path) -> TrainingPrompt:
    """revision에 남긴 training-prompt.json을 다시 읽는다(평가·서빙이 같은 문장을 쓴다)."""
    body = read_json(path)
    if sha256_text(body["core"]) != body.get("coreSha256"):
        raise CheckFailed("s10", [f"{path.name}: 핵심 해시가 기록과 다르다"])
    return TrainingPrompt(
        core=body["core"],
        relationships=dict(body.get("relationships") or {}),
        channels=dict(body.get("channels") or {}),
        origin=str(body.get("origin") or ""),
        version=str(body.get("components") or ""),
    )


def find(char_dir: Path, dataset_rev: str | None) -> Path | None:
    if not dataset_rev:
        return None
    path = char_dir / "s9-data" / dataset_rev / FILE_NAME
    return path if path.is_file() else None


def relationship_for_stage(stage: str | None) -> str:
    """기획서 관계 단계(STRANGER·ACQUAINTANCE·FLIRTING·DATING)를 학습 관계 4종으로."""
    return str(components()["stageRelationships"].get(str(stage or ""), "FAVORABLE"))


def eval_system(tp: TrainingPrompt, relationship: str, channel: str = SERVICE_CHANNEL) -> str:
    """평가·서빙 system: 학습 때와 같은 순서(핵심 + 관계 + 채널 + 장면)."""
    return tp.system(relationship, channel) + "\n\n[SCENE]\n" + components()["evalScene"]


def assign_relationships(shares: dict[str, float], start: int, count: int) -> list[str]:
    """자리마다 가장 모자란 관계를 고른다. 같은 start면 늘 같은 순서다."""
    keys = [k for k in RELATIONSHIPS if shares.get(k, 0) > 0] or ["FAVORABLE"]
    have = dict.fromkeys(keys, 0)
    seq: list[str] = []
    for n in range(start + count):
        pick = max(keys, key=lambda k: ((n + 1) * shares.get(k, 0) - have[k], -keys.index(k)))
        have[pick] += 1
        seq.append(pick)
    return seq[start:]
