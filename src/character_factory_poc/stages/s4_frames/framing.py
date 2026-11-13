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


#: D-0218: 이만큼 이하로 어긋나면 그대로 둔다. 이보다 크게 어긋난 비율은 잘못 찾은 얼굴로 본다.
ALIGN_TOLERANCE = 0.02
ALIGN_LIMIT = (0.7, 1.4)


def _face_box(img) -> tuple[float, float, float, float] | None:
    """(가운데 x, 가운데 y, 너비, 높이). 원본 화소 기준. 화면 위쪽 2/3 안의 가장 큰 얼굴."""
    import cv2

    scale = _WIDTH / img.shape[1]
    height = int(img.shape[0] * scale)
    gray = cv2.equalizeHist(cv2.cvtColor(cv2.resize(img, (_WIDTH, height)), cv2.COLOR_BGR2GRAY))
    for name in ("haarcascade_frontalface_alt2.xml", "haarcascade_frontalface_default.xml"):
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.05, minNeighbors=5, minSize=(40, 40))
        faces = [f for f in faces if f[1] + f[3] / 2 < height * 2 / 3]
        if faces:
            x, y, w, h = max(faces, key=lambda f: f[2])
            return ((x + w / 2) / scale, (y + h / 2) / scale, w / scale, h / scale)
    return None


def align_boxes(base_img, frame_img, base_box, frame_box):
    """frame 을 키우거나 줄이고 옮겨 얼굴 크기·위치를 base 에 맞춘다. 빈 가장자리는 base 로 채운다.

    돌려주는 값: (맞춘 이미지, 기록). 맞출 필요가 없거나 비율이 이상하면 frame 을 그대로 준다."""
    import cv2
    import numpy as np

    h, w = base_img.shape[:2]
    if frame_img.shape[:2] != (h, w):
        sx, sy = w / frame_img.shape[1], h / frame_img.shape[0]
        frame_img = cv2.resize(frame_img, (w, h), interpolation=cv2.INTER_AREA)
        fx, fy, fw, fh = frame_box
        frame_box = (fx * sx, fy * sy, fw * sx, fh * sy)
    s = float(base_box[2] / frame_box[2])
    record = {"method": "face", "before": round(1 / s, 3)}
    shift = max(abs(base_box[0] - frame_box[0]), abs(base_box[1] - frame_box[1])) / w
    if abs(s - 1) <= ALIGN_TOLERANCE and shift <= ALIGN_TOLERANCE:
        return frame_img, record | {"applied": False}
    if not ALIGN_LIMIT[0] <= s <= ALIGN_LIMIT[1]:
        reason = "비율이 범위를 벗어나 얼굴 검출을 믿지 않는다"
        return frame_img, record | {"applied": False, "reason": reason}
    tx = float(base_box[0] - s * frame_box[0])
    ty = float(base_box[1] - s * frame_box[1])
    matrix = np.float32([[s, 0, tx], [0, s, ty]])
    warped = cv2.warpAffine(frame_img, matrix, (w, h), flags=cv2.INTER_LINEAR)
    mask = cv2.warpAffine(np.full((h, w), 255, np.uint8), matrix, (w, h), flags=cv2.INTER_NEAREST)
    out = np.where(mask[..., None] > 0, warped, base_img)
    shift_px = [int(round(tx)), int(round(ty))]
    return out, record | {"applied": True, "scaleApplied": round(s, 3), "shiftPx": shift_px}


def align_to_base(base: Path, data: bytes) -> tuple[bytes, dict]:
    """시그니처 중간 프레임(PNG 바이트)을 기준 사진의 얼굴 크기·위치에 맞춘다(D-0218)."""
    import cv2
    import numpy as np

    base_img = cv2.imread(str(base))
    frame_img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if base_img is None or frame_img is None:
        return data, {"method": "face", "applied": False, "reason": "이미지를 읽지 못했다"}
    a, b = _face_box(base_img), _face_box(frame_img)
    if not a or not b:
        return data, {"method": "face", "applied": False, "reason": "얼굴을 찾지 못했다"}
    out, record = align_boxes(base_img, frame_img, a, b)
    if not record.get("applied"):
        return data, record
    ok, buf = cv2.imencode(".png", out)
    return (buf.tobytes(), record) if ok else (data, record | {"applied": False})
