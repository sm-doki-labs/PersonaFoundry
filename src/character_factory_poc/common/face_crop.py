"""얼굴 크롭 (D-0027, Q-0016). 기준 이미지에서 얼굴 주변만 잘라 참조 이미지의 자세 신호를 줄인다.

OpenCV 4.x의 Haar 정면 얼굴 검출기를 쓴다(OpenCV 5에는 없다). 네트워크·모델 다운로드가 없다.
"""

from __future__ import annotations

from collections.abc import Callable

Box = tuple[int, int, int, int]  # x, y, w, h
Detector = Callable[[bytes], list[Box]]


def detect_faces(data: bytes) -> list[Box]:
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    h, w = img.shape[:2]
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    m = max(24, int(min(w, h) * 0.08))
    found = casc.detectMultiScale(
        cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), scaleFactor=1.1, minNeighbors=5, minSize=(m, m)
    )
    return [tuple(int(v) for v in f) for f in found]  # type: ignore[misc]


def crop_box(box: Box, width: int, height: int, scale: float, lift: float) -> Box:
    """얼굴 상자를 scale배 정사각형으로 넓히고 머리카락이 들어가게 lift만큼 위로 올린다."""
    x, y, fw, fh = box
    side = min(int(max(fw, fh) * scale), width, height)
    cx, cy = x + fw / 2, y + fh / 2 - fh * lift
    left = max(0, min(int(cx - side / 2), width - side))
    top = max(0, min(int(cy - side / 2), height - side))
    return left, top, side, side


def crop_face(
    data: bytes, scale: float = 1.4, lift: float = 0.12, detector: Detector | None = None
) -> tuple[bytes, Box] | None:
    """가장 큰 얼굴 주변을 잘라 PNG로 돌려준다. 얼굴이 없으면 None."""
    import cv2
    import numpy as np

    faces = (detector or detect_faces)(data)
    if not faces:
        return None
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    left, top, side, _ = crop_box(max(faces, key=lambda f: f[2] * f[3]), w, h, scale, lift)
    ok, buf = cv2.imencode(".png", img[top : top + side, left : left + side])
    if not ok:
        return None
    return buf.tobytes(), (left, top, side, side)
