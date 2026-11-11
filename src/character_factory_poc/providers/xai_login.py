"""공장 소유 xAI(Grok) 로그인 — 영상 1순위 경로의 토큰을 공장이 받고, 저장하고, 갱신한다.

사용자 2026-11-12: "opencodex로 호출하는건 적절하지 않은 것 같은데, 공장 소유의 코드로 하는게
맞지 않아?" 그래서 opencodex의 auth.json을 읽지 않는다. 로그인·저장·갱신·로그아웃을 이 모듈이 한다.

- 로그인은 xAI 공식 로그인 화면(auth.x.ai)에서 사람이 한다. 공장은 비밀번호·쿠키를 받지 않는다.
  브라우저(PKCE 인가 코드, 127.0.0.1:56121/callback으로 돌아옴) 또는 기기 코드(화면 없는 서버).
- xAI는 외부 앱의 로그인 클라이언트 등록을 공개하지 않는다. 기본 client_id는 Grok CLI의 공개
  클라이언트(opencodex와 같다)이고 설정으로 바꾼다. 공식 문서가 보장하는 경로가 아니라 막힐 수 있다.
- 토큰은 공장 전용 파일(기본 ~/.character-factory/xai-oauth.json, 0600)에 둔다.
  CFP_XAI_OAUTH_FILE로 바꾼다. 갱신은 파일 잠금 안에서 하고, 잠금을 얻은 뒤 다시 읽어 다른 작업이
  이미 갱신했으면 그 값을 쓴다. 새로 고침 토큰이 바뀌어 돌아오면 바로 저장한다.
- 토큰·코드 값은 출력·기록·예외 메시지에 넣지 않는다.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx

from character_factory_poc.common.errors import VideoGenerationError

DISCOVERY_URL = "https://auth.x.ai/.well-known/openid-configuration"
#: Grok CLI 공개 클라이언트(xAI 공식 로그인 화면). [providers.video] oauth_client_id로 바꾼다.
DEFAULT_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
SCOPE = "openid profile email offline_access grok-cli:access api:access"
CALLBACK_PORT = 56121  # 클라이언트에 등록된 돌아올 주소의 포트
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://127.0.0.1:{CALLBACK_PORT}{CALLBACK_PATH}"
TRUSTED_HOSTS = frozenset({"auth.x.ai", "accounts.x.ai"})
REFRESH_SKEW_S = 300.0  # 남은 시간이 이보다 짧으면 쓰기 전에 갱신한다
LOGIN_HINT = "cfp grok login으로 공장에서 Grok 계정에 로그인한다"


class XaiLoginRequired(VideoGenerationError):
    """로그인이 없거나 갱신할 수 없다. 사람이 다시 로그인해야 한다."""


class XaiLoginError(VideoGenerationError):
    """로그인·갱신 요청이 실패했다(네트워크·서버). 메시지에 토큰을 넣지 않는다."""


def default_store() -> Path:
    raw = os.environ.get("CFP_XAI_OAUTH_FILE", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".character-factory" / "xai-oauth.json"


@dataclass
class Credentials:
    access: str
    refresh: str
    expires_at: float  # epoch 초
    email: str = ""
    account_id: str = ""
    obtained_at: float = 0.0
    client_id: str = DEFAULT_CLIENT_ID

    def __repr__(self) -> str:  # 토큰을 repr에 싣지 않는다
        return f"Credentials(email={self.email!r}, expires_at={self.expires_at:.0f})"


def _jwt_claims(token: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(pad))
    except (ValueError, json.JSONDecodeError):
        return {}


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    return verifier, challenge.decode()


class XaiLogin:
    def __init__(
        self,
        store: Path | None = None,
        *,
        client_id: str = "",
        http: httpx.Client | None = None,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.store = Path(store).expanduser() if store else default_store()
        self.client_id = client_id.strip() or DEFAULT_CLIENT_ID
        self.http = http or httpx.Client(timeout=30.0)
        self.now = now
        self.sleep = sleep
        self._endpoints: dict[str, str] | None = None

    def __repr__(self) -> str:
        return f"XaiLogin(store={self.store!s})"

    # ------------------------------------------------------------------ 저장

    @contextmanager
    def _locked(self):
        self.store.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = self.store.with_suffix(".lock")
        with lock.open("a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def load(self) -> Credentials | None:
        try:
            raw = json.loads(self.store.read_text("utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            raise XaiLoginRequired(
                f"공장 Grok 로그인 파일을 읽지 못했다: {self.store}. {LOGIN_HINT}"
            ) from exc
        try:
            return Credentials(**{k: raw[k] for k in raw if k in Credentials.__dataclass_fields__})
        except TypeError as exc:
            raise XaiLoginRequired(
                f"공장 Grok 로그인 파일 형식이 아니다: {self.store}. {LOGIN_HINT}"
            ) from exc

    def save(self, cred: Credentials) -> None:
        self.store.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.store.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(asdict(cred), fh)
        os.replace(tmp, self.store)
        os.chmod(self.store, 0o600)

    # ------------------------------------------------------------------ xAI 로그인 서버

    def endpoints(self) -> dict[str, str]:
        if self._endpoints is None:
            r = self.http.get(DISCOVERY_URL, headers={"Accept": "application/json"})
            if r.status_code != 200:
                raise XaiLoginError(f"xAI 로그인 설정을 읽지 못했다(HTTP {r.status_code})")
            doc = r.json()
            out = {}
            for key in (
                "authorization_endpoint",
                "token_endpoint",
                "device_authorization_endpoint",
                "revocation_endpoint",
            ):
                url = doc.get(key)
                if not isinstance(url, str):
                    continue
                parts = urllib.parse.urlsplit(url)
                if parts.scheme != "https" or parts.hostname not in TRUSTED_HOSTS or parts.port:
                    raise XaiLoginError(f"xAI 로그인 설정의 주소가 예상과 다르다({key})")
                out[key] = url
            if "authorization_endpoint" not in out or "token_endpoint" not in out:
                raise XaiLoginError("xAI 로그인 설정에 인가·토큰 주소가 없다")
            self._endpoints = out
        return self._endpoints

    def _token(self, form: dict[str, str]) -> dict:
        r = self.http.post(
            self.endpoints()["token_endpoint"],
            data=form,
            headers={"Accept": "application/json"},
        )
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code == 200 and isinstance(body, dict):
            return body
        err = body.get("error") if isinstance(body, dict) else None
        if err in {"invalid_grant", "invalid_client", "unauthorized_client"}:
            raise XaiLoginRequired(f"xAI가 로그인을 받아 주지 않았다({err}). {LOGIN_HINT}")
        detail = f", {err}" if err else ""
        raise XaiLoginError(f"xAI 토큰 요청 실패(HTTP {r.status_code}{detail})")

    def _credentials(self, payload: dict, refresh_fallback: str = "") -> Credentials:
        access = payload.get("access_token")
        if not isinstance(access, str) or not access:
            raise XaiLoginError("xAI 토큰 응답에 access_token이 없다")
        refresh = payload.get("refresh_token") or refresh_fallback
        if not refresh:
            raise XaiLoginError("xAI 토큰 응답에 refresh_token이 없다(offline_access)")
        expires_in = payload.get("expires_in")
        expires_in = float(expires_in) if isinstance(expires_in, int | float) else 3600.0
        claims = _jwt_claims(payload.get("id_token") or "") or _jwt_claims(access)
        now = self.now()
        return Credentials(
            access=access,
            refresh=str(refresh),
            expires_at=now + expires_in,
            email=str(claims.get("email") or "").lower(),
            account_id=str(claims.get("sub") or ""),
            obtained_at=now,
            client_id=self.client_id,
        )

    # ------------------------------------------------------------------ 로그인

    def authorize_url(self, *, state: str, challenge: str) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "nonce": secrets.token_urlsafe(16),
        }
        return self.endpoints()["authorization_endpoint"] + "?" + urllib.parse.urlencode(params)

    def exchange(self, code: str, verifier: str) -> Credentials:
        payload = self._token(
            {
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": verifier,
            }
        )
        cred = self._credentials(payload)
        with self._locked():
            self.save(cred)
        return cred

    def login_browser(
        self,
        *,
        open_browser: bool = True,
        timeout_s: float = 300.0,
        on_url: Callable[[str], None] = print,
    ) -> Credentials:
        """브라우저 로그인. 127.0.0.1:56121에서 돌아오는 인가 코드를 한 번 받는다."""
        verifier, challenge = _pkce()
        state = secrets.token_urlsafe(24)
        url = self.authorize_url(state=state, challenge=challenge)
        got: dict[str, str] = {}
        done = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # 요청 줄(코드 포함)을 남기지 않는다
                return

            def do_GET(self):  # noqa: N802
                parts = urllib.parse.urlsplit(self.path)
                if parts.path != CALLBACK_PATH:
                    self.send_response(404)
                    self.end_headers()
                    return
                query = dict(urllib.parse.parse_qsl(parts.query))
                ok = query.get("state") == state and "code" in query
                got.update(query if ok else {"error": query.get("error") or "state_mismatch"})
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                msg = (
                    "로그인됐어요. 이 창을 닫아도 돼요."
                    if ok
                    else "로그인하지 못했어요. 공장 화면을 확인해 주세요."
                )
                self.wfile.write(f"<p>{msg}</p>".encode())
                done.set()

        try:
            server = HTTPServer(("127.0.0.1", CALLBACK_PORT), Handler)
        except OSError as exc:
            raise XaiLoginError(
                f"로그인 응답을 받을 127.0.0.1:{CALLBACK_PORT}을 열지 못했다"
                "(다른 로그인 창이 쓰는 중일 수 있다)"
            ) from exc
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            on_url(url)
            if open_browser:
                webbrowser.open(url)
            if not done.wait(timeout_s):
                raise XaiLoginError(f"{timeout_s:.0f}초 안에 브라우저 로그인이 끝나지 않았다")
        finally:
            server.shutdown()
            server.server_close()
        if "code" not in got:
            raise XaiLoginError(f"브라우저 로그인이 거절됐다({got.get('error', 'unknown')})")
        return self.exchange(got["code"], verifier)

    def login_device(
        self,
        *,
        on_prompt: Callable[[str, str], None] = lambda url, code: print(url, code),
        timeout_s: float = 900.0,
    ) -> Credentials:
        """기기 코드 로그인(화면 없는 서버). 다른 기기 브라우저에서 코드를 넣는다."""
        endpoint = self.endpoints().get("device_authorization_endpoint")
        if not endpoint:
            raise XaiLoginError("xAI 로그인 설정에 기기 코드 주소가 없다")
        r = self.http.post(
            endpoint,
            data={"client_id": self.client_id, "scope": SCOPE},
            headers={"Accept": "application/json"},
        )
        if r.status_code != 200:
            raise XaiLoginError(f"기기 코드를 받지 못했다(HTTP {r.status_code})")
        dev = r.json()
        on_prompt(
            str(dev.get("verification_uri_complete") or dev.get("verification_uri")),
            str(dev.get("user_code", "")),
        )
        interval = float(dev.get("interval") or 5)
        deadline = self.now() + min(timeout_s, float(dev.get("expires_in") or timeout_s))
        while self.now() < deadline:
            self.sleep(interval)
            t = self.http.post(
                self.endpoints()["token_endpoint"],
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": str(dev.get("device_code")),
                    "client_id": self.client_id,
                },
                headers={"Accept": "application/json"},
            )
            body = t.json() if t.content else {}
            if t.status_code == 200:
                cred = self._credentials(body)
                with self._locked():
                    self.save(cred)
                return cred
            err = body.get("error")
            if err == "slow_down":
                interval += 5
            elif err != "authorization_pending":
                raise XaiLoginError(f"기기 코드 로그인 실패({err or t.status_code})")
        raise XaiLoginError("기기 코드가 만료됐다. 다시 로그인한다")

    # ------------------------------------------------------------------ 사용

    def access_token(self, *, min_valid_s: float = REFRESH_SKEW_S) -> str:
        """쓸 수 있는 access 토큰. 곧 만료되면 잠금 안에서 갱신한다."""
        cred = self.load()
        if cred is None:
            raise XaiLoginRequired(f"공장에 Grok 로그인이 없다. {LOGIN_HINT}")
        if cred.expires_at - self.now() > min_valid_s:
            return cred.access
        with self._locked():
            cred = self.load()  # 다른 작업이 이미 갱신했을 수 있다
            if cred is None:
                raise XaiLoginRequired(f"공장에 Grok 로그인이 없다. {LOGIN_HINT}")
            if cred.expires_at - self.now() > min_valid_s:
                return cred.access
            self.client_id = cred.client_id or self.client_id
            payload = self._token(
                {
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "refresh_token": cred.refresh,
                }
            )
            fresh = self._credentials(payload, refresh_fallback=cred.refresh)
            fresh.email = fresh.email or cred.email
            fresh.account_id = fresh.account_id or cred.account_id
            self.save(fresh)
            return fresh.access

    def status(self) -> dict:
        cred = self.load()
        if cred is None:
            return {"loggedIn": False, "store": str(self.store)}
        return {
            "loggedIn": True,
            "email": cred.email,
            "expiresInMin": round((cred.expires_at - self.now()) / 60, 1),
            "store": str(self.store),
        }

    def logout(self) -> bool:
        cred = self.load()
        if cred is None:
            return False
        revoke = None
        try:
            revoke = self.endpoints().get("revocation_endpoint")
        except XaiLoginError:
            pass
        if revoke:
            try:
                self.http.post(
                    revoke,
                    data={
                        "token": cred.refresh,
                        "client_id": cred.client_id,
                        "token_type_hint": "refresh_token",
                    },
                )
            except httpx.HTTPError:
                pass  # 지우는 것이 우선이다
        with self._locked():
            self.store.unlink(missing_ok=True)
        return True


__all__ = [
    "CALLBACK_PORT",
    "DEFAULT_CLIENT_ID",
    "REDIRECT_URI",
    "Credentials",
    "XaiLogin",
    "XaiLoginError",
    "XaiLoginRequired",
    "default_store",
]
