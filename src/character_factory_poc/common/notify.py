"""공장 알림 — 디스코드 웹후크로 보낸다(사용자 2026-11-12, 시연용 발행 알림).

- 주소는 환경변수 CFP_DISCORD_WEBHOOK_URL(.env)에서만 읽는다. 비어 있으면 아무것도 하지 않는다.
- 알림 실패는 공장 작업을 멈추지 않는다. 결과만 돌려준다.
- 메시지에는 원문·프롬프트·토큰·접속 정보를 싣지 않는다. 캐릭터 이름, 단계, 짧은 이유,
  비용 추정, 공장 화면 주소만 싣는다.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

WEBHOOK_ENV = "CFP_DISCORD_WEBHOOK_URL"
STUDIO_URL_ENV = "CFP_STUDIO_PUBLIC_URL"
_ALLOWED_HOSTS = ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")

#: event → (색, 제목 앞머리)
_STYLE = {
    "published": (0x2E9E5B, "✅ 테스터 미리보기 발행"),
    "failed": (0xD64545, "❌ 시연 자동 진행 멈춤"),
    "budget": (0xE0A100, "⚠️ 예산 상한 도달"),
    "waiting": (0xE0A100, "⏸️ 사람 확인 필요"),
    "started": (0x4A6CF7, "▶️ 시연 자동 진행 시작"),
    "test": (0x4A6CF7, "🔔 시험 알림"),
}

Sender = Callable[[str, bytes], int]


@dataclass(frozen=True)
class NotifyResult:
    sent: bool
    reason: str = ""


def _post(url: str, body: bytes) -> int:
    req = urllib.request.Request(
        url + ("&" if "?" in url else "?") + "wait=true",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "character-factory/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status
    except urllib.error.HTTPError as exc:
        return exc.code


def build_message(event: str, title: str, lines: list[str], link: str = "") -> dict:
    color, head = _STYLE.get(event, (0x888888, "공장 알림"))
    description = "\n".join(line for line in lines if line)[:1800]
    embed: dict = {"title": f"{head} · {title}"[:240], "description": description, "color": color}
    if link:
        embed["url"] = link
    return {"username": "캐릭터 공장", "embeds": [embed], "allowed_mentions": {"parse": []}}


def notify(
    event: str,
    title: str,
    lines: list[str],
    *,
    character_id: str | None = None,
    sender: Sender | None = None,
) -> NotifyResult:
    """알림 한 건. 웹후크가 없거나 보내지 못해도 예외를 던지지 않는다."""
    url = os.environ.get(WEBHOOK_ENV, "").strip()
    if not url:
        return NotifyResult(False, "웹후크 없음")
    if not url.startswith(_ALLOWED_HOSTS):
        return NotifyResult(False, "디스코드 웹후크 주소가 아님")
    base = os.environ.get(STUDIO_URL_ENV, "").strip().rstrip("/")
    link = f"{base}/studio/flow.html?c={character_id}" if base and character_id else ""
    body = json.dumps(build_message(event, title, lines, link), ensure_ascii=False).encode()
    try:
        status = (sender or _post)(url, body)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return NotifyResult(False, f"전송 실패: {type(exc).__name__}")
    return NotifyResult(200 <= status < 300, f"HTTP {status}")


__all__ = ["STUDIO_URL_ENV", "WEBHOOK_ENV", "NotifyResult", "build_message", "notify"]
