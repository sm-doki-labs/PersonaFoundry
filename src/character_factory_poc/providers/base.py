"""공급자 포트 (명세 §11, LLD §9). TextModel과 ImageGen(S1 미리보기)을 둔다."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Message:
    role: str  # system | user | assistant
    content: str


@dataclass(frozen=True)
class ChatRequest:
    kind: str  # 원장 kind: AGENT | JUDGE | PROBE
    stage: str
    messages: tuple[Message, ...]
    ref: str
    max_output_tokens: int = 4000
    temperature: float = 0.7
    response_json: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ChatResponse:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    elapsed_ms: int
    model: str
    provider: str
    finish_reason: str | None = None
    raw: dict | None = None
    # usage-v1(명세 §24.3). 모르는 값은 None이다.
    usage: dict | None = None


class TextModel(Protocol):
    name: str
    model: str

    def complete(self, request: ChatRequest) -> ChatResponse: ...


@dataclass(frozen=True)
class VisionRequest:
    """이미지 판정 요청(D-0036). images는 (라벨, 파일 경로) 순서대로 모델에 붙는다."""

    stage: str
    ref: str
    prompt: str
    images: tuple[tuple[str, str], ...]
    system: str = ""
    max_output_tokens: int = 2000


@dataclass(frozen=True)
class VisionResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    elapsed_ms: int
    model: str
    provider: str
    # usage-v1(명세 §24.3). 모르는 값은 None이다.
    usage: dict | None = None


class VisionModel(Protocol):
    name: str
    model: str

    def judge(self, request: VisionRequest) -> VisionResult: ...


@dataclass(frozen=True)
class ImageRequest:
    stage: str
    prompt: str
    ref: str
    negative_prompt: str = ""
    size: str = "1024x1024"
    # 같은 인물을 유지할 참조 이미지 파일 경로(S2 대표 이미지, D-0022)
    reference_images: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImageResult:
    data: bytes
    mime: str
    model: str
    provider: str
    elapsed_ms: int
    est_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    source_path: str = ""


class ImageModel(Protocol):
    name: str
    model: str

    def generate(self, request: ImageRequest) -> ImageResult: ...


@dataclass(frozen=True)
class VideoRequest:
    """이미지 → 영상 요청(S5·S6, D-0028). first_frame이 영상의 첫 프레임이 된다."""

    stage: str
    prompt: str
    ref: str
    first_frame: str
    duration: int = 8
    resolution: str = "720p"
    aspect_ratio: str | None = None
    generate_audio: bool = False


@dataclass(frozen=True)
class VideoResult:
    data: bytes
    mime: str
    model: str
    provider: str
    elapsed_ms: int
    job_id: str
    seconds: float
    est_cost_usd: float | None = None
    source_path: str = ""


class VideoModel(Protocol):
    """제출과 수집을 나눈다. resumable이면 끊긴 뒤 같은 job_id로 다시 수집할 수 있다."""

    name: str
    model: str
    resumable: bool

    def submit(self, request: VideoRequest) -> str: ...

    def collect(self, job_id: str, request: VideoRequest) -> VideoResult: ...


_FENCE_RE = re.compile(r"^\s*\x60\x60\x60(?:json)?\s*|\s*\x60\x60\x60\s*$", re.MULTILINE)


def extract_json_object(text: str) -> dict:
    """코드 펜스를 벗기고 첫 JSON 객체만 파싱한다 (LLD §7)."""
    cleaned = _FENCE_RE.sub("", text).strip()
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("JSON 객체가 없다")
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(cleaned)):
        ch = cleaned[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : i + 1])
    raise ValueError("JSON 객체가 닫히지 않았다")
