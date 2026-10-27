"""영상 실측 (LLD §8.5). ffprobe가 있으면 길이·해상도를 잰다. 없거나 실패하면 이유만 남긴다."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from character_factory_poc.contracts.video import Probe


def probe_video(path: Path) -> Probe:
    tool = shutil.which("ffprobe")
    if not tool:
        return Probe(tool=None, note="ffprobe가 없어 길이·해상도를 재지 않았다")
    try:
        out = subprocess.run(
            [
                tool,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height:format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        obj = json.loads(out.stdout or "{}")
        stream = (obj.get("streams") or [{}])[0]
        dur = (obj.get("format") or {}).get("duration")
        if out.returncode != 0 or not stream:
            return Probe(tool="ffprobe", note=f"ffprobe가 읽지 못했다: {out.stderr.strip()[:200]}")
        return Probe(
            tool="ffprobe",
            durationS=round(float(dur), 2) if dur else None,
            width=int(stream["width"]) if stream.get("width") else None,
            height=int(stream["height"]) if stream.get("height") else None,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired) as e:
        return Probe(tool="ffprobe", note=f"ffprobe 실패: {e}")
