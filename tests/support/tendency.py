"""모티브 S3 경향 표시(D-0148)의 가짜 판정 응답. 모든 답을 같은 경향 칸 하나로 표시한다."""

from __future__ import annotations

import json

TAG_SITUATION = "TASTE"
TAG_MOVE = "OWN_EXPERIENCE"


def is_tagging(req) -> bool:
    return req.stage == "s3" and "/tendencies/" in req.ref


def fake_tags(req) -> dict:
    items = json.loads(req.messages[-1].content)
    return {
        "items": [
            {
                "id": it["id"],
                "situation": TAG_SITUATION,
                "moves": [TAG_MOVE],
                "evidence": it["answer"][:20],
            }
            for it in items
        ]
    }
