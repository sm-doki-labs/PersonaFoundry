"""통화 직후의 감정 영상 선택. 대화와 재생 이력은 이 요청 안에서만 쓴다."""

from __future__ import annotations

import re
from dataclasses import replace
from importlib.resources import files
from uuid import uuid4

from character_factory_poc.common import demo_chat as demo
from character_factory_poc.providers.base import ChatRequest, Message

_RANK = re.compile(r"([1-3])위\s*[:.]?\s*([\w-]+)(?:[ :]+(\d+(?:\.\d+)?))?")
# api-svc clip_pick 설정과 같은 값: 가벼운 모델, 생각 끔, 2.5초 안에 못 고르면 대기 영상 유지.
PICK_MODEL = "gemini-3.5-flash"
PICK_TIMEOUT_S = 2.5


def _ranked(text, candidates):
    ranks = {}
    for line in text.splitlines():
        match = _RANK.fullmatch(line.strip().strip("`"))
        if match:
            rank, key, score = match.groups()
            if key.lower() in {"none", "없음"}:
                key = "none"
            if (key == "none" or key in candidates) and (score is None or float(score) <= 100):
                ranks.setdefault(int(rank), key)
    # Some text models return just the winning key.
    if not ranks and text.strip() in candidates:
        return [text.strip()]
    return list(dict.fromkeys(ranks[i] for i in sorted(ranks)))


def pick(ctx, cid, candidates, user, reply, recent):
    """recent is the client playback sequence, oldest first, including repeated keys."""
    if not candidates:
        return None
    by_key = {c["clipKey"]: c for c in candidates}
    guide = files("character_factory_poc.resources").joinpath("clip-pick-followup-v1.md")
    lines = []
    for c in candidates:
        mood = {"good": "밝음", "bad": "어두움"}.get(c["mood"], "")
        details = (c["clipKey"], c["title"], mood, c.get("description"), f"이럴 때: {c['useWhen']}")
        lines.append("- " + " | ".join(part for part in details if part))
    request = ChatRequest(
        "PROBE",
        "demo",
        (
            Message("system", guide.read_text("utf-8") + "\n".join(lines)),
            Message("user", f"유저: {user}\n캐릭터가 방금 한 말: {reply}"),
        ),
        f"clip-{uuid4().hex}",
        temperature=0,
        max_output_tokens=160,
    )
    try:
        cfg = demo.provider(ctx, "studio")
        pick_cfg = ctx.config.providers.get("clip_pick")
        cfg = replace(
            cfg,
            model=(pick_cfg.model if pick_cfg else PICK_MODEL),
            extra={
                **cfg.extra,
                "reasoning_effort": "none",
                "timeout_s": PICK_TIMEOUT_S,
                "max_retries": 0,
            },
        )
        model = demo.talk_model(ctx, cid, cfg)
        raw = model.complete(request).text
    except Exception:
        # Optional playback must not interrupt a conversation on timeout/budget/provider failure.
        return None
    ranked = _ranked(raw or "", by_key)
    banned = recent[-1] if len(recent) >= 3 and len(set(recent[-3:])) == 1 else None
    has_alternative = any(key != "none" for key in ranked[1:])
    for key in ranked:
        if key == "none":
            break
        if key != banned and (not has_alternative or key not in recent[-2:]):
            return by_key[key]
    return None
