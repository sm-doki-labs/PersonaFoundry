"""이미지 비율 도구 (D-0031, D-0034). S5 첫 프레임과 S4 배경·완성 이미지가 같이 쓴다."""

from __future__ import annotations

# 생성 결과 비율이 목표에서 이만큼 넘게 벗어나면 자르지 않고 실패로 둔다
# (정사각형을 잘라 인물을 잃지 않게).
MAX_RATIO_DRIFT = 0.25


def parse_ratio(text: str) -> tuple[int, int]:
    w, _, h = str(text).partition(":")
    if not (w.isdigit() and h.isdigit()) or int(w) <= 0 or int(h) <= 0:
        raise ValueError(f"비율은 '9:16' 형식이다: {text!r}")
    return int(w), int(h)


def request_size(ratio: tuple[int, int]) -> str:
    """이미지 모델에 줄 크기 힌트. 세로면 1024x1536, 가로면 1536x1024, 같으면 1024x1024."""
    w, h = ratio
    if h > w:
        return "1024x1536"
    if w > h:
        return "1536x1024"
    return "1024x1024"


def crop_to_ratio(
    data: bytes, ratio: tuple[int, int]
) -> tuple[bytes, tuple[int, int], tuple[int, int]]:
    """가운데 기준으로 목표 비율의 가장 큰 상자를 잘라 PNG로 돌려준다.

    돌려주는 값은 (PNG, 원본 크기, 자른 크기)다."""
    import cv2
    import numpy as np

    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("이미지를 읽지 못했다")
    h, w = img.shape[:2]
    rw, rh = ratio
    target = rw / rh
    actual = w / h
    if abs(actual / target - 1) > MAX_RATIO_DRIFT:
        raise ValueError(
            f"생성된 이미지가 {w}×{h}로 목표 비율 {rw}:{rh}에서 너무 벗어났다. 다시 만든다"
        )
    if actual > target:  # 너무 넓다: 좌우를 자른다
        cw, ch = max(1, round(h * target)), h
    else:  # 너무 길다: 위아래를 자른다
        cw, ch = w, max(1, round(w / target))
    x, y = (w - cw) // 2, (h - ch) // 2
    ok, buf = cv2.imencode(".png", img[y : y + ch, x : x + cw])
    if not ok:
        raise ValueError("PNG 인코딩 실패")
    return buf.tobytes(), (w, h), (cw, ch)
