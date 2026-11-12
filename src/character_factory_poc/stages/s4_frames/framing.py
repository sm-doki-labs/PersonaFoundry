"""시그니처 중간 프레임이 기준 사진과 같은 크기로 찍혔는지 잰다(D-0210).

Grok 이미지 편집은 동작 참고 사진의 구도를 따라 인물을 키우는 일이 있다(2026-11-13 손흥민:
배경은 그대로인데 얼굴이 1.18배). 영상은 2초에 이 프레임을 지나도록 고정되므로 화면이 확대됐다
돌아온다. 배경은 맞물려 크기가 같으므로 얼굴 크기 비율을 본다. 얼굴을 못 찾으면 판단하지 않는다.
"""

from __future__ import annotations

from pathlib import Path

#: 중간 프레임 얼굴 크기 / 기준 사진 얼굴 크기의 허용 범위.
SCALE_RANGE = (0.9, 1.1)
_WIDTH = 720


def _face_width(path: Path) -> float | None:
    import cv2

    img = cv2.imread(str(path))
    if img is None:
        return None
    height = int(img.shape[0] * _WIDTH / img.shape[1])
    gray = cv2.equalizeHist(cv2.cvtColor(cv2.resize(img, (_WIDTH, height)), cv2.COLOR_BGR2GRAY))
    for name in ("haarcascade_frontalface_alt2.xml", "haarcascade_frontalface_default.xml"):
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=5, minSize=(40, 40))
        # 광고판 글자 같은 작은 오검출을 피하려고 화면 위쪽 2/3 안의 가장 큰 얼굴만 본다.
        faces = [f for f in faces if f[1] + f[3] / 2 < height * 2 / 3]
        if faces:
            return float(max(f[2] for f in faces))
    return None


def face_scale(base: Path, frame: Path) -> dict:
    """{"scale": 비율|None, "ok": bool|None}. ok=None 은 얼굴을 못 찾아 판단하지 않았다는 뜻이다."""
    a, b = _face_width(base), _face_width(frame)
    if not a or not b:
        return {"scale": None, "ok": None, "range": list(SCALE_RANGE)}
    scale = round(b / a, 3)
    ok = SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]
    return {"scale": scale, "ok": ok, "range": list(SCALE_RANGE)}


def distance(check: dict) -> float:
    """고를 때 쓰는 값. 판단하지 못한 프레임은 맨 뒤로 보낸다."""
    return abs(check["scale"] - 1.0) if check.get("scale") else 9.0
