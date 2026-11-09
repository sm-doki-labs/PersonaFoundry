"""통화 직후의 감정 영상 선택. 대화와 재생 이력은 이 요청 안에서만 쓴다."""

from __future__ import annotations

import os
import re
from dataclasses import replace
from importlib.resources import files
from uuid import uuid4

import httpx

from character_factory_poc.common import demo_chat as demo
from character_factory_poc.providers.base import ChatRequest, Message

_RANK = re.compile(r"([1-3])위\s*[:.]?\s*([\w-]+)(?:[ :]+(\d+(?:\.\d+)?))?")
# api-svc clip_pick 설정과 같은 값: 가벼운 모델, 생각 끔, 2.5초 안에 못 고르면 대기 영상 유지.
PICK_MODEL = "gemini-3.5-flash"
PICK_TIMEOUT_S = 2.5

# jev(OpenCode /systemone). api-svc SystemOneChoiceClient와 같은 요청·같은 순위 규칙이다.
# 루트 .env에 OPENCODE_API_KEY가 있으면 jev로 고르고, 비어 있으면 위의 글 모델로 고른다.
JEV_KEY_ENV = "OPENCODE_API_KEY"
JEV_MODEL = "jev-1.13"
JEV_BASE_URL = "https://opencode.ai/zen/v1"
JEV_MIN_PROB = 0.05
_NONE_CRITERION = "딱 맞는 몸짓이 하나도 없는 평범한 말이면 몸짓 없이 가만히 있는다."
# 턴마다 부르므로 연결을 60초 이어 쓴다(api-svc #128과 같은 이유: 새 TLS 연결이 0.25~0.3초 더 든다).
_http = httpx.Client(timeout=PICK_TIMEOUT_S, limits=httpx.Limits(keepalive_expiry=60.0))


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


def _describe(c):
    mood = {"good": "밝음", "bad": "어두움"}.get(c["mood"], "")
    details = (c["title"], mood, c.get("description"), f"이럴 때: {c['useWhen']}")
    return " | ".join(part for part in details if part)


def jev_ready():
    return bool(os.environ.get(JEV_KEY_ENV))


def _jev_ranked(guide, candidates, state):
    """선택지마다 확률을 받아 상위 3개 키. 1위가 none이면 none 하나만."""
    criteria = {c["clipKey"]: _describe(c) for c in candidates}
    criteria["none"] = _NONE_CRITERION
    body = {
        "model": os.environ.get("OPENCODE_MODEL") or JEV_MODEL,
        "state": state,
        "questions": {
            "clip": {
                "type": "choice",
                # 출력 형식 문단은 뺀다. jev는 글을 쓰지 않는다.
                "instructions": guide.split("\n\n")[0].strip(),
                "criteria": criteria,
            }
        },
    }
    base = (os.environ.get("OPENCODE_BASE_URL") or JEV_BASE_URL).rstrip("/")
    response = _http.post(
        base + "/systemone",
        json=body,
        headers={"Authorization": f"Bearer {os.environ[JEV_KEY_ENV]}"},
        timeout=PICK_TIMEOUT_S,
    )
    response.raise_for_status()
    probabilities = response.json()["answers"]["clip"]["probabilities"]
    ordered = sorted(((str(k), float(v)) for k, v in probabilities.items()), key=lambda kv: -kv[1])
    if not ordered:
        return []
    ranked = [k for k, p in ordered if p >= JEV_MIN_PROB][:3] or [ordered[0][0]]
    if ranked[0] == "none":
        return ["none"]
    return [k for k in ranked if k == "none" or k in criteria]


def pick(ctx, cid, candidates, user, reply, recent):
    """recent is the client playback sequence, oldest first, including repeated keys."""
    if not candidates:
        return None
    by_key = {c["clipKey"]: c for c in candidates}
    guide = (
        files("character_factory_poc.resources")
        .joinpath("clip-pick-followup-v1.md")
        .read_text("utf-8")
    )
    state = f"유저: {user}\n캐릭터가 방금 한 말: {reply}"
    if jev_ready():
        try:
            ranked = _jev_ranked(guide, candidates, state)
        except Exception:
            # 시간 초과·키 오류여도 대화는 이어진다. 화면은 앱 규칙대로 옅은 반응을 쓴다.
            return None
        return _apply_rules(ranked, by_key, recent)
    lines = ["- " + " | ".join((c["clipKey"], _describe(c))) for c in candidates]
    request = ChatRequest(
        "PROBE",
        "demo",
        (
            Message("system", guide + "\n".join(lines)),
            Message("user", state),
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
    return _apply_rules(_ranked(raw or "", by_key), by_key, recent)


def _apply_rules(ranked, by_key, recent):
    banned = recent[-1] if len(recent) >= 3 and len(set(recent[-3:])) == 1 else None
    has_alternative = any(key != "none" for key in ranked[1:])
    for key in ranked:
        if key == "none":
            break
        if key != banned and (not has_alternative or key not in recent[-2:]):
            return by_key[key]
    return None
