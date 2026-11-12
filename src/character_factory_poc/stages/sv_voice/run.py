"""SV: character voice. The user gives a Fish Audio voice (model) ID when creating a character;
the factory records it as-is and ships it in the character package. No model call (D-0205).

The ID is stored in voice-settings.json at intake. The stage writes an immutable voice/vo<n>/
voice.json record and is APPROVED right away, with or without an ID, so the package step never
waits on it. A missing ID is recorded as "not set" and the package carries no voice.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file
from character_factory_poc.common.store import next_rev, read_json, write_once_json
from character_factory_poc.pipeline.context import Context

PROVIDER = "fish_audio"
SETTINGS = "voice-settings.json"
# Fish Audio voice models are addressed by a 32-character hexadecimal ID.
FISH_ID = re.compile(r"^[0-9a-f]{32}$")


def normalize_reference_id(value) -> str | None:
    """Trim and lower-case; None for empty. Raises ValueError for anything else."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Fish Audio 음성 ID는 문자열이어야 해요.")
    text = value.strip().lower()
    if not text:
        return None
    if not FISH_ID.match(text):
        raise ValueError(
            "Fish Audio 음성 ID는 영문 소문자·숫자 32자예요(예: 802e3bc2b27e49c2995d23ef70e6ac89)."
        )
    return text


def write_voice(folder: Path, reference_id: str | None) -> None:
    ref = normalize_reference_id(reference_id)
    path = Path(folder) / SETTINGS
    path.write_text(
        json.dumps({"provider": PROVIDER, "referenceId": ref}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def read_voice(folder: Path) -> dict | None:
    path = Path(folder) / SETTINGS
    if not path.is_file():
        return None
    data = json.loads(path.read_text("utf-8"))
    if data.get("provider") != PROVIDER:
        raise ValueError("알 수 없는 음성 공급자다")
    return {"provider": PROVIDER, "referenceId": normalize_reference_id(data.get("referenceId"))}


def run_sv(ctx: Context, cid: str) -> Path:
    folder = ctx.character_dir(cid)
    state = ctx.state(cid)
    state.require_deps("sv")
    settings = read_voice(folder) or {"provider": PROVIDER, "referenceId": None}
    base = folder / "voice"
    rev = next_rev(base, "vo")
    state.transition("sv", "RUNNING", rev=rev)
    source = folder / SETTINGS
    record = dict(settings, settingsSha256=sha256_file(source) if source.is_file() else None)
    write_once_json(base / rev / "voice.json", record)
    state = ctx.state(cid)
    state.transition("sv", "APPROVED", rev=rev)
    return base / rev


def approved_voice(char_dir: Path, state) -> dict | None:
    """The approved voice record with its rev, or None when the stage has not run or no ID."""
    st = state.stage("sv")
    if st.status != "APPROVED" or not st.currentRev:
        return None
    path = Path(char_dir) / "voice" / st.currentRev / "voice.json"
    if not path.is_file():
        return None
    data = read_json(path)
    if not data.get("referenceId"):
        return None
    return {
        "provider": data["provider"],
        "referenceId": data["referenceId"],
        "voiceRev": st.currentRev,
        "record": f"voice/{st.currentRev}/voice.json",
    }
