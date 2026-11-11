"""Grok 영상: OAuth 로그인 먼저, 안 되면 API 키 (사용자 2026-11-12, 시연·시험 1순위 기본).

같은 xAI 영상 API(POST /videos/generations, GET /videos/{id})를 두 가지 인증으로 부른다.

1. grok_oauth: opencodex에 로그인한 xAI 계정(~/.opencodex/auth.json의 활성 계정) 토큰.
   2026-11-12 실제 호출로 확인했다(grok-imagine-video-1.5-lite 480p 2초, 1.5 1080p 2초).
   공식 문서가 보장하는 방식은 아니라 막힐 수 있다.
2. xai_video: XAI_API_KEY(공식 API 키).

토큰이 없거나 만료됐으면 네트워크를 부르기 전에 다음 경로로 넘어간다. 제출이 인증·구독·크레딧 문제
(HTTP 401·402·403)로 거절돼도 다음 경로로 넘어간다. 거절된 제출은 과금되지 않는다. 그 밖의 오류
(안전 차단, 잘못된 요청, 서버 오류)는 다른 경로로 다시 보내지 않고 그대로 올린다. 같은 요청을
두 번 과금하지 않기 위해서다.

토큰 갱신은 opencodex가 맡는다(잠금·세대 번호로 auth.json을 고친다). 공장은 auth.json을 쓰지 않는다.
토큰 값은 출력·기록하지 않는다.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence

from character_factory_poc.common.errors import VideoGenerationError
from character_factory_poc.providers.base import VideoRequest, VideoResult

#: 다른 경로로 넘어가도 되는 제출 거절(과금 없음).
_HANDOFF = re.compile(r"HTTP (401|402|403)\b")
#: 이전 실행이 남긴 job을 찾을 때 다른 경로로 다시 조회해 볼 응답.
_LOOKUP_MISS = re.compile(r"HTTP (401|402|403|404)\b")


def unavailable_reason(member) -> str | None:
    """네트워크 없이 이 경로를 지금 쓸 수 없는 이유. 쓸 수 있으면 None."""
    source = getattr(member, "token_source", None)
    if source is not None:
        try:
            source.token()
        except VideoGenerationError as exc:
            return str(exc)
        return None
    env = getattr(member, "api_key_env", "")
    if env and not os.environ.get(env):
        return f"환경변수 {env}에 xAI API 키가 없다"
    return None


class GrokVideoChain:
    """VideoModel. 쓸 수 있는 첫 경로로 제출하고, 그 경로로 결과를 받는다."""

    resumable = True

    def __init__(self, members: Sequence):
        if not members:
            raise ValueError("Grok 영상 경로가 하나 이상 필요하다")
        self.members = list(members)
        self.model = self.members[0].model
        self._used = None
        self._jobs: dict[str, object] = {}
        self.skipped: list[str] = []  # 이번 제출에서 건너뛴 경로와 이유(기록용)

    def __repr__(self) -> str:
        return f"GrokVideoChain({[m.name for m in self.members]!r}, model={self.model!r})"

    @property
    def name(self) -> str:
        """지금 쓰는(또는 쓸) 경로 이름. 제출 기록의 provider로 남는다."""
        if self._used is not None:
            return self._used.name
        for member in self.members:
            if unavailable_reason(member) is None:
                return member.name
        return self.members[0].name

    def submit(self, request: VideoRequest) -> str:
        reasons: list[str] = []
        for member in self.members:
            why = unavailable_reason(member)
            if why:
                reasons.append(f"{member.name}: {why}")
                continue
            try:
                job = member.submit(request)
            except VideoGenerationError as exc:
                if _HANDOFF.search(str(exc)):
                    reasons.append(f"{member.name}: {str(exc)[:200]}")
                    continue
                raise
            self._used = member
            self._jobs[job] = member
            self.skipped = reasons
            return job
        raise VideoGenerationError(
            "Grok 영상을 만들 경로가 없다. opencodex에서 xAI 계정에 로그인하거나 "
            "XAI_API_KEY를 설정한다. " + " / ".join(reasons)
        )

    def collect(self, job_id: str, request: VideoRequest) -> VideoResult:
        member = self._jobs.get(job_id)
        if member is not None:
            return member.collect(job_id, request)
        # 이전 실행이 남긴 job: 어느 경로로 냈는지 모르므로 쓸 수 있는 경로로 차례로 조회한다.
        last: VideoGenerationError | None = None
        for candidate in self.members:
            if unavailable_reason(candidate) is not None:
                continue
            try:
                result = candidate.collect(job_id, request)
            except VideoGenerationError as exc:
                if hasattr(exc, "job_id") or not _LOOKUP_MISS.search(str(exc)):
                    raise
                last = exc
                continue
            self._used = candidate
            return result
        raise last or VideoGenerationError(
            "이전 영상 작업을 조회할 경로가 없다. opencodex 로그인이나 XAI_API_KEY를 확인한다"
        )


def route_summary(cfg) -> str:
    """사람이 읽는 영상 경로 한 줄(알림·화면용). 네트워크를 부르지 않는다."""
    if cfg.adapter == "fake":
        return "영상: 시험용 가짜 영상(비용 없음)"
    if cfg.adapter not in {"grok", "grok_oauth", "xai_video"}:
        return f"영상: {cfg.adapter}"
    from character_factory_poc.providers.factory import make_video_model

    model = make_video_model(cfg)
    members = model.members if isinstance(model, GrokVideoChain) else [model]
    labels = {"grok_oauth": "Grok 로그인(opencodex)", "xai_video": "xAI API 키"}
    for i, member in enumerate(members):
        why = unavailable_reason(member)
        if why is None:
            note = "" if i == 0 else " · 앞 경로를 쓸 수 없어 넘어감"
            return f"영상: {labels.get(member.name, member.name)} · {model.model}{note}"
    return "영상: 쓸 수 있는 경로 없음(opencodex 로그인 또는 XAI_API_KEY 필요)"


__all__ = ["GrokVideoChain", "route_summary", "unavailable_reason"]
