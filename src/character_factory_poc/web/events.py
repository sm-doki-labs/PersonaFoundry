"""SSE 이벤트 허브 (PoC 계획서 §6).

작업 스레드에서 만든 사건을 asyncio 대기열로 넘겨 한 연결이 느려도 다른 연결을 막지 않는다.
대기열이 차면 그 연결의 사건만 버린다(화면은 다음 사건이나 새로고침으로 회복한다).
"""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

MAX_QUEUE = 512


@dataclass(eq=False)
class Subscriber:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop
    character_id: str | None = None


class EventHub:
    def __init__(self) -> None:
        self._subs: set[Subscriber] = set()
        self._lock = threading.Lock()

    def subscribe(self, character_id: str | None = None) -> Subscriber:
        """지금 도는 이벤트 루프에 붙는 구독자를 만든다. async 라우트 안에서 부른다."""
        sub = Subscriber(
            queue=asyncio.Queue(maxsize=MAX_QUEUE),
            loop=asyncio.get_running_loop(),
            character_id=character_id or None,
        )
        with self._lock:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        with self._lock:
            self._subs.discard(sub)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subs)

    def publish(self, event: str, data: dict[str, Any], character_id: str | None = None) -> None:
        """어느 스레드에서나 부를 수 있다. characterId를 지정한 구독자는 그 캐릭터 사건만 받는다."""
        payload = {"event": event, "data": data, "at": _now()}
        with self._lock:
            subs = list(self._subs)
        for sub in subs:
            if sub.character_id and character_id and sub.character_id != character_id:
                continue
            sub.loop.call_soon_threadsafe(_put_nowait, sub.queue, payload)


def _put_nowait(queue: asyncio.Queue, payload: dict[str, Any]) -> None:
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass


def format_sse(event: str, data: Any) -> str:
    """SSE 한 덩어리. data는 한 줄 JSON이어야 한다."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
