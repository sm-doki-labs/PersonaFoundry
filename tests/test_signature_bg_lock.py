"""시그니처 영상 배경 고정(D-0222). 합성 영상과 가짜 사람 분리로만 검사한다."""

import threading
from pathlib import Path

import cv2
import numpy as np
import pytest

from character_factory_poc.stages.s6_actions import bg_lock, postprocess

W, H, FPS = 180, 320, 24


def _scene(shift: int) -> np.ndarray:
    """줄무늬 배경(shift 만큼 밀림) + 가운데 사람 상자."""
    img = np.zeros((H, W, 3), np.uint8)
    for x in range(0, W, 12):
        img[:, (x + shift) % W : (x + shift) % W + 6] = (40, 120, 220)
    img[100:300, 60:120] = (20, 20, 20)
    return img


def _video(path: Path, shifts: list[int]) -> None:
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    for s in shifts:
        out.write(_scene(s))
    out.release()


def _person(frame: np.ndarray) -> np.ndarray:
    mask = np.zeros(frame.shape[:2], np.float32)
    mask[100:300, 60:120] = 1.0
    return mask


def test_warped_background_is_replaced_by_the_reference(tmp_path):
    src, ref, dst = tmp_path / "in.mp4", tmp_path / "ref.png", tmp_path / "out.mp4"
    _video(src, [0] * 10 + [5] * 30 + [0] * 10)  # 가운데에서 배경이 밀린다(일그러짐 흉내)
    cv2.imwrite(str(ref), _scene(0))
    report = bg_lock.lock_background(
        src, ref, dst, slot=threading.BoundedSemaphore(1), segment=_person
    )
    assert report["applied"] and report["frames"] == 50
    assert report["backgroundDiffMaxAfter"] < report["backgroundDiffMaxBefore"] / 3
    cap = cv2.VideoCapture(str(dst))
    for _ in range(20):
        ok, frame = cap.read()
    cap.release()
    assert ok
    left = cv2.absdiff(frame[:, :40], _scene(0)[:, :40]).mean()
    assert left < 6, "the shifted stripes are back where the reference has them"


def test_without_the_segmenter_the_video_is_kept(tmp_path, monkeypatch):
    def broken():
        raise ImportError("no litert")

    monkeypatch.setattr(bg_lock, "load_segmenter", broken)
    report = bg_lock.lock_background(
        tmp_path / "a.mp4", tmp_path / "b.png", tmp_path / "c.mp4", slot=threading.Lock()
    )
    assert report == {
        "applied": False,
        "method": bg_lock.METHOD,
        "reason": "사람 분리 도구를 쓰지 못했다: no litert",
    }


def test_only_the_signature_clip_with_a_middle_frame_is_locked(tmp_path, monkeypatch):
    src, ref = tmp_path / "in.mp4", tmp_path / "ref.png"
    _video(src, [0] * 144)  # 6초: 복귀 검사 길이 범위
    cv2.imwrite(str(ref), _scene(0))
    calls = []

    def fake(src_, ref_, dst, **kw):
        calls.append(dst)
        dst.write_bytes(src_.read_bytes())
        return {"applied": True, "method": "fake"}

    monkeypatch.setattr(bg_lock, "lock_background", fake)
    _, plain = postprocess.process(src, ref, {"trimWindowS": [2.5, 3.5]})
    assert "backgroundLock" not in plain and not calls
    _, sig = postprocess.process(
        src, ref, {"trimWindowS": [4.0, 5.0], "middleFrame": {"sha256": "x"}}
    )
    assert sig["backgroundLock"] == {"applied": True, "method": "fake"} and len(calls) == 1


def test_bundled_model_runs_with_litert():
    pytest.importorskip("ai_edge_litert")
    assert bg_lock.MODEL.is_file()
    segment = bg_lock.load_segmenter()
    mask = segment(_scene(0))
    assert mask.shape == (H, W) and 0.0 <= float(mask.min()) <= float(mask.max()) <= 1.0
