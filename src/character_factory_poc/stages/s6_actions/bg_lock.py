"""시그니처 영상의 배경을 기준 사진 배경으로 고정한다(D-0222).

시그니처 영상은 중간 프레임(편집 사진)을 2초에 지나는데, 이미지 편집이 배경 광고판을 다시 그려
영상이 기준 배경과 다른 배경 사이를 오가며 일그러졌다(2026-11-13 손흥민: 배경 차이 4→52).
카메라는 고정이라 배경은 처음부터 끝까지 기준 사진과 같아야 한다. 프레임마다 사람을 분리해
사람은 영상 그대로, 나머지는 기준 사진으로 덮는다. 기준 사진에서 사람이 있던 자리는 영상 쪽을
남겨 팔이 움직여 드러난 부분이 비지 않게 한다.

사람 분리는 MediaPipe Selfie Segmentation 모델(resources/selfie_segmentation.tflite)을
LiteRT(ai-edge-litert)로 돌린다. 둘 중 하나라도 없으면 원래 영상을 그대로 두고 이유를 남긴다.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

METHOD = "selfie-segmentation-v1"
MODEL = Path(__file__).resolve().parents[2] / "resources" / "selfie_segmentation.tflite"
#: 사람 마스크를 경계 밖으로 넓히는 비율(화면 너비 대비)과 경계를 부드럽게 하는 폭.
GROW = 0.012
FEATHER = 0.02

Segment = Callable[[np.ndarray], np.ndarray]


def load_segmenter() -> Segment:
    """BGR 프레임 → 사람일 확률(0~1, 프레임과 같은 크기)."""
    from ai_edge_litert.interpreter import Interpreter

    interpreter = Interpreter(model_path=str(MODEL))
    interpreter.allocate_tensors()
    src = interpreter.get_input_details()[0]
    dst = interpreter.get_output_details()[0]
    height, width = int(src["shape"][1]), int(src["shape"][2])

    def segment(frame: np.ndarray) -> np.ndarray:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        x = cv2.resize(rgb, (width, height)).astype(np.float32) / 255.0
        interpreter.set_tensor(src["index"], x[None])
        interpreter.invoke()
        mask = interpreter.get_tensor(dst["index"])[0, ..., 0]
        return cv2.resize(mask, (frame.shape[1], frame.shape[0]))

    return segment


def _soft(mask: np.ndarray) -> np.ndarray:
    width = mask.shape[1]
    grow = max(3, int(width * GROW) | 1)
    feather = max(3, int(width * FEATHER) | 1)
    hard = (mask > 0.5).astype(np.uint8)
    hard = cv2.dilate(hard, np.ones((grow, grow), np.uint8))
    return cv2.GaussianBlur(hard.astype(np.float32), (feather, feather), 0)


def _skip(reason: str) -> dict:
    return {"applied": False, "method": METHOD, "reason": reason}


def lock_background(
    src: Path,
    reference: Path,
    dst: Path,
    *,
    slot,
    segment: Segment | None = None,
    threads: str = "2",
    timeout: int = 180,
) -> dict:
    """src 영상의 배경을 reference 사진으로 덮어 dst 에 쓴다. 기록용 dict 를 돌려준다.

    프레임을 모아 두지 않고 한 장씩 ffmpeg 표준입력으로 흘린다(1GB 서버, 영상 한 편 약 400MB).
    slot 은 다른 후처리와 같이 쓰는 동시 실행 제한이다.
    """
    from character_factory_poc.common.errors import VideoGenerationError

    try:
        segment = segment or load_segmenter()
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        return _skip(f"사람 분리 도구를 쓰지 못했다: {exc}")
    cap = cv2.VideoCapture(str(src))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        photo = cv2.imread(str(reference))
        ok, frame = cap.read()
        if not ok or fps <= 0 or photo is None:
            return _skip("영상 또는 기준 사진을 읽지 못했다")
        h, w = frame.shape[:2]
        ref = cv2.resize(photo, (w, h), interpolation=cv2.INTER_AREA)
        ref_person = _soft(segment(ref))
        # 기록용: 사람이 거의 오지 않는 화면 양옆·위쪽 띠에서 기준 사진과의 차이를 잰다.
        strip = np.zeros((h, w), bool)
        strip[:, : int(w * 0.18)] = strip[:, int(w * 0.82) :] = strip[: int(h * 0.12), :] = True
        args = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24"]
        args += ["-s", f"{w}x{h}", "-r", f"{fps:.6f}", "-i", "-", "-an", "-c:v", "libx264"]
        args += ["-threads", threads, "-crf", "18", "-pix_fmt", "yuv420p"]
        args += ["-movflags", "+faststart", str(dst)]
        before = after = 0.0
        count = 0
        with slot:
            try:
                proc = subprocess.Popen(
                    args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                )
            except OSError as exc:
                raise VideoGenerationError(f"배경 고정 인코딩 실패: {exc}") from exc
            try:
                while ok:
                    keep = np.maximum(_soft(segment(frame)), ref_person)[..., None]
                    out = (frame * keep + ref * (1.0 - keep)).astype(np.uint8)
                    before = max(before, float(cv2.absdiff(frame, ref).mean(axis=2)[strip].mean()))
                    after = max(after, float(cv2.absdiff(out, ref).mean(axis=2)[strip].mean()))
                    proc.stdin.write(out.tobytes())
                    count += 1
                    ok, frame = cap.read()
                proc.stdin.close()
                err = proc.stderr.read()
                code = proc.wait(timeout=timeout)
            except (OSError, subprocess.TimeoutExpired) as exc:
                proc.kill()
                raise VideoGenerationError(f"배경 고정 인코딩 실패: {exc}") from exc
        if code:
            detail = err.decode(errors="replace")[-300:].strip()
            raise VideoGenerationError(f"배경 고정 인코딩 실패(종료 코드 {code}): {detail}")
    finally:
        cap.release()
    return {
        "applied": True,
        "method": METHOD,
        "frames": count,
        "backgroundDiffMaxBefore": round(before, 1),
        "backgroundDiffMaxAfter": round(after, 1),
    }
