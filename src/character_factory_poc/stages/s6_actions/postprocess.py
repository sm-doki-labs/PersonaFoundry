"""Silent exports and conservative return-pose cut proposals, never quality approval."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
import numpy as np

from character_factory_poc.common.errors import VideoGenerationError

# 영상 여러 편을 동시에 받아도 후처리(ffmpeg 재인코딩)는 한 번에 하나씩, 스레드 2개로 돌린다.
# 컨테이너는 실제 호스트 코어 수를 보므로 libx264 기본 스레드가 수십 개가 되어 한 편에 500MB를 넘고,
# 1GB 서버에서 동시에 돌면 운영체제가 ffmpeg를 강제 종료했다(Railway 손흥민, 종료 코드 -9).
_FFMPEG_SLOT = threading.BoundedSemaphore(1)
_FFMPEG_THREADS = "2"


def _run(args: list[str]) -> None:
    try:
        with _FFMPEG_SLOT:
            proc = subprocess.run(args, capture_output=True, timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VideoGenerationError(f"영상 후처리 실패: {exc}") from exc
    if proc.returncode:
        detail = proc.stderr.decode(errors="replace")[-400:].strip()
        if proc.returncode < 0:
            note = f"ffmpeg가 신호 {-proc.returncode}로 강제 종료됨(메모리 부족 가능)"
            detail = f"{note} {detail}".strip()
        raise VideoGenerationError(f"영상 후처리 실패(종료 코드 {proc.returncode}): {detail}")


def require_tools() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise VideoGenerationError("통화 영상 후처리에는 ffmpeg와 ffprobe가 필요하다")


def _small(frame):
    return cv2.resize(frame, (96, 96)).astype(np.float32) / 255.0


def _distance(a, b):
    # 중앙 몸통/얼굴 부분과 타일 최댓값을 사용하여 정적인 넓은 배경이 점수를 압도하지 않게 한다.
    diff = np.abs(a - b).mean(axis=2)
    return max(
        float(diff[8:88, 24:72].mean()),
        max(
            float(tile.mean())
            for row in np.array_split(diff, 4)
            for tile in np.array_split(row, 4, axis=1)
        ),
    )


def select_cut(raw: Path, reference: Path, window: list[float] | None) -> dict:
    cap = cv2.VideoCapture(str(raw))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        ok, first = cap.read()
        photo = cv2.imread(str(reference))
        if not ok or fps <= 0 or photo is None:
            raise VideoGenerationError("복귀 검사에 필요한 영상 또는 기준 사진을 읽지 못했다")
        base, photo = _small(first), _small(photo)
        frames = [base]
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frames.append(_small(frame))
        duration = len(frames) / fps
        report = {
            "algorithm": "reference-tiles-v1",
            "qualityApproved": False,
            "sourceDurationS": round(duration, 4),
            "cutAtS": None,
            "status": "needs_review",
            "reason": "",
            "threshold": 0.07,
        }
        if not 5.7 <= duration <= 6.3:
            report["reason"] = "생성 길이가 6초 허용 범위를 벗어남"
            return report
        if window is None:
            report.update(status="untrimmed", reason="대기·말하기는 전체 길이 보존")
            return report
        movement = [_distance(frame, base) for frame in frames]
        if max(movement[: int(window[0] * fps)]) < 0.025:
            report["reason"] = "동작이 관측되지 않아 복귀로 판정하지 않음"
            return report
        scores = [max(_distance(frame, base), _distance(frame, photo)) for frame in frames]
        stable = max(2, round(fps * 0.12))
        candidates = []
        for i in range(
            max(1, int(window[0] * fps)), min(len(frames) - stable, int(window[1] * fps))
        ):
            if max(scores[i : i + stable]) > 0.07:
                continue
            if max(_distance(frames[j], frames[j - 1]) for j in range(i + 1, i + stable)) > 0.025:
                continue
            candidates.append((max(scores[i : i + stable]), i))
        if not candidates:
            report["reason"] = "지정 구간에서 기준 자세에 가깝고 안정된 복귀 지점을 찾지 못함"
            return report
        score, index = min(candidates)
        report.update(
            status="cut_proposed",
            reason="사람의 동작·얼굴·이음매 검토 필요",
            cutAtS=round((index + 1) / fps, 4),
            similarityError=round(score, 5),
        )
        return report
    finally:
        cap.release()


def process(raw: Path, reference: Path, production: dict) -> tuple[bytes, dict]:
    require_tools()
    report = select_cut(raw, reference, production.get("trimWindowS"))
    with TemporaryDirectory(prefix="cfp-silent-") as tmp:
        target = Path(tmp) / "silent.mp4"
        args = ["ffmpeg", "-v", "error", "-y", "-threads", _FFMPEG_THREADS, "-i", str(raw)]
        args += ["-map", "0:v:0", "-an"]
        if report["cutAtS"] is not None:
            args += [
                "-t",
                str(report["cutAtS"]),
                "-c:v",
                "libx264",
                "-threads",
                _FFMPEG_THREADS,
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
            ]
        else:
            args += ["-c:v", "copy"]
        _run(args + ["-movflags", "+faststart", str(target)])
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(target)],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        streams = json.loads(probe.stdout)["streams"]
        if any(s["codec_type"] == "audio" for s in streams):
            raise VideoGenerationError("무음 처리 뒤 오디오 트랙이 남았다")
        report["audioRemoved"] = True
        return target.read_bytes(), report
