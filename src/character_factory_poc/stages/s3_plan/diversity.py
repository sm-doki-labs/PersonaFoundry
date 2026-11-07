"""기획 다양성 단서(D-0100).

언어 모델은 같은 브리프에서 최빈값으로 수렴하므로 다양성을 바깥에서 넣는다.

후보마다 범주별 단서를 하나씩 뽑고(같은 실행 안에서는 겹치지 않게),
이미 만든 인물의 이름·취미·음식을 피할 목록으로 넘긴다.
뽑기는 characterId와 planRev로 정해지는 난수라 같은 rev를 다시 만들면 같은 단서가 나온다.
"""

from __future__ import annotations

import hashlib
import json
import random
from importlib.resources import files
from pathlib import Path
from typing import Any


def load_anchors() -> dict[str, list[str]]:
    raw = json.loads(
        files("character_factory_poc.resources").joinpath("diversity-anchors-v1.json").read_text()
    )
    return raw["categories"]


def recent_anchor_values(characters_dir: Path, cid: str, limit_runs: int = 6) -> set[str]:
    """최근 실행들이 이미 받은 단서 값. 실행 사이에 같은 단서가 반복되지 않게 뺀다."""
    paths = sorted(
        (
            p
            for p in characters_dir.glob("*/s3-plan/*/workspace/inputs/diversity-anchors.json")
            if p.parts[-6] != cid
        ),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit_runs]
    seen: set[str] = set()
    for p in paths:
        try:
            for row in json.loads(p.read_text("utf-8")):
                seen.update(v for k, v in row.items() if k != "variantId")
        except (OSError, ValueError):
            continue
    return seen


def draw_anchors(
    cid: str, rev: str, count: int, exclude: set[str] | None = None
) -> list[dict[str, str]]:
    seed = int(hashlib.sha256(f"{cid}/{rev}".encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    cats = load_anchors()
    exclude = exclude or set()
    picks = {}
    for k, v in cats.items():
        fresh = [x for x in v if x not in exclude]
        pool = fresh if len(fresh) >= count else v
        picks[k] = rng.sample(pool, min(count, len(pool)))
    return [
        {"variantId": f"v{i + 1}", **{k: picks[k][i % len(picks[k])] for k in cats}}
        for i in range(count)
    ]


def avoid_list(characters_dir: Path, cid: str, limit_runs: int = 12) -> dict[str, list[str]]:
    """이미 만든 기획 후보의 이름·취미·음식. 최근 실행부터 limit_runs개만 본다."""
    files_ = sorted(
        (p for p in characters_dir.glob("*/s3-plan/*/variants.json") if p.parts[-4] != cid),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit_runs]
    out: dict[str, list[str]] = {"names": [], "hobbies": [], "foods": []}
    for p in files_:
        try:
            raw = json.loads(p.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        for c in raw.get("candidates", []):
            card: dict[str, Any] = c.get("profileCard") or {}
            for key, val in (
                ("names", c.get("name")),
                ("hobbies", card.get("hobby")),
                ("foods", card.get("favoriteFoods")),
            ):
                if isinstance(val, str) and val and val not in out[key]:
                    out[key].append(val)
    return out
