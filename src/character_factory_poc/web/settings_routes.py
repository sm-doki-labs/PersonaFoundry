"""설정 화면의 Grok 계정 연결(D-0211). 서버 명령(cfp grok login --device)과 같은 공장 로그인을 쓴다.

화면 없는 서버라 기기 코드 로그인만 연다. 코드와 승인 주소를 화면에 보이고, 백그라운드에서 승인을
기다렸다가 공장 로그인 파일에 저장한다. 토큰 값은 응답·기록에 넣지 않는다.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from fastapi import APIRouter

from character_factory_poc.common.config import load_config
from character_factory_poc.common.errors import VideoGenerationError
from character_factory_poc.web.errors import WebError

#: 승인을 기다리는 최대 시간(초). xAI 기기 코드 만료와 같은 15분이다.
DEVICE_TIMEOUT_S = 900.0


def install_settings_routes(app, conf) -> None:
    router = APIRouter(prefix="/api/settings")
    lock = threading.Lock()
    flow: dict[str, Any] = {}

    def login():
        from character_factory_poc.providers.xai_login import XaiLogin

        video = load_config(conf.root, conf.config_path).providers.get("video")
        extra = video.extra if video else {}
        return XaiLogin(
            store=extra.get("login_file") or None,
            client_id=str(extra.get("oauth_client_id") or ""),
        )

    def video_route() -> dict[str, Any]:
        video = load_config(conf.root, conf.config_path).providers.get("video")
        if video is None:
            return {"adapter": None, "order": []}
        order = list(video.extra.get("order") or [])
        if video.adapter == "grok" and not order:
            order = ["grok_oauth", "xai_video"]
        return {"adapter": video.adapter, "order": order}

    def flow_view() -> dict[str, Any] | None:
        if not flow:
            return None
        view = {k: flow.get(k) for k in ("status", "url", "code", "expiresAt", "error")}
        if view["status"] == "pending" and time.time() > (flow.get("deadline") or 0):
            view["status"] = "expired"
        return view

    def view() -> dict[str, Any]:
        try:
            st = login().status()
            account = {
                "connected": bool(st.get("loggedIn")),
                "email": st.get("email") or None,
                "expiresInMin": st.get("expiresInMin"),
            }
        except VideoGenerationError as exc:
            account = {"connected": False, "email": None, "expiresInMin": None, "error": str(exc)}
        with lock:
            return {"grok": account, "flow": flow_view(), "video": video_route()}

    @router.get("/grok")
    def grok_status() -> dict[str, Any]:
        return view()

    @router.post("/grok/device")
    def grok_device() -> dict[str, Any]:
        with lock:
            current = flow_view()
            pending = bool(current and current["status"] == "pending")
            if not pending:
                flow.clear()
                flow.update(status="starting", url=None, code=None, expiresAt=None, error=None)
        if pending:
            # 이미 받은 코드가 살아 있으면 새로 받지 않는다(두 번 눌러도 코드 하나).
            return view()
        shown = threading.Event()

        def on_prompt(url: str, code: str) -> None:
            deadline = time.time() + DEVICE_TIMEOUT_S
            with lock:
                flow.update(
                    status="pending",
                    url=url,
                    code=code,
                    deadline=deadline,
                    expiresAt=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(deadline)),
                )
            shown.set()

        def worker() -> None:
            try:
                login().login_device(on_prompt=on_prompt, timeout_s=DEVICE_TIMEOUT_S)
                with lock:
                    flow.update(status="connected", url=None, code=None)
            except Exception as exc:  # noqa: BLE001 — 화면에 실패 이유만 보인다
                with lock:
                    flow.update(status="failed", error=str(exc)[:300])
            finally:
                shown.set()

        threading.Thread(target=worker, name="cfp-grok-device", daemon=True).start()
        if not shown.wait(timeout=20):
            raise WebError(504, "xAI 로그인 코드를 받지 못했어요. 잠시 뒤 다시 눌러 주세요.")
        with lock:
            if flow.get("status") == "failed":
                raise WebError(502, flow.get("error") or "xAI 로그인을 시작하지 못했어요.")
        return view()

    @router.delete("/grok")
    def grok_logout() -> dict[str, Any]:
        login().logout()
        with lock:
            flow.clear()
        return view()

    app.include_router(router)
