"""G0에서 떼어 둔 비교 세트로만 평가 장면을 만든다(D-0120)."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from character_factory_poc.common.errors import CheckFailed, FactoryError
from character_factory_poc.common.store import (
    next_rev,
    write_manifest,
    write_once_json,
    write_once_text,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import SOURCE
from character_factory_poc.pipeline.origin import read_origin
from character_factory_poc.stages.s0_source.run import load_holdout


def _scenes(rows: list[dict], limit: int):
    conversations = defaultdict(list)
    for row in rows:
        conversations[row["convId"]].append({k: row[k] for k in ("msgId", "speaker", "text")})
    for conv, messages in conversations.items():
        for i, (user, reply) in enumerate(zip(messages, messages[1:], strict=False)):
            if user["speaker"] == "USER" and reply["speaker"] == "SUBJECT":
                yield {
                    "sceneId": reply["msgId"],
                    "convId": conv,
                    "context": messages[max(0, i - limit) : i],
                    "user": user,
                    "actualReply": reply,
                }


def run_s9h(ctx: Context, cid: str) -> Path:
    char_dir = ctx.character_dir(cid)
    if read_origin(char_dir) != SOURCE:
        raise FactoryError("s9h 비교 세트는 트윈에서만 만든다")
    state = ctx.state(cid)
    state.require_deps("s9h")
    root = char_dir / "s9h-holdout"
    rev = next_rev(root, "ho")
    folder = root / rev
    limit = ctx.config.stage("s9h").get("context_messages", 6)
    state.transition("s9h", "RUNNING", rev=rev)
    try:
        if type(limit) is not int or not 0 <= limit <= 6:
            raise CheckFailed("s9h", ["context_messages는 0~6 사이 정수여야 한다"])
        scenes = list(_scenes(load_holdout(ctx, cid), limit))
        if not scenes:
            raise CheckFailed("s9h", ["비교 세트에 USER 바로 뒤에 SUBJECT가 답한 장면이 없다"])
        write_once_text(
            folder / "scenes.jsonl",
            "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in scenes),
        )
        write_once_json(
            folder / "summary.json",
            {
                "sourceRev": state.gate("G0").rev,
                "sceneCount": len(scenes),
                "contextMessages": limit,
            },
        )
        write_manifest(folder)
    except (FactoryError, OSError, ValueError, KeyError):
        state.transition("s9h", "CHECK_FAILED", rev=rev, error="비교 세트 장면 준비 실패")
        raise
    state.transition("s9h", "APPROVED", rev=rev)
    return folder
