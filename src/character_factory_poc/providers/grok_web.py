"""Grok 웹 영상 어댑터 (D-0028, D-0029, D-0032). 기본 꺼짐.

전용 Chrome 프로필로 띄운 브라우저에 Playwright가 CDP로 붙어(connect_over_cdp) grok.com Imagine에서
비디오 모드 → 해상도·길이·소리 → 첫 프레임 업로드 → 움직임 프롬프트 → 제출 → 결과 페이지의 영상 대기 →
로그인 세션으로 영상 파일 받기를 한다. 로그인은 사람이 그 프로필에서 한 번 한다. xAI 이용 정책은 봇·스크립트
접근을 금지하므로 계정 정지 위험이 있다. 그래서 설정에 accept_terms_risk = true가 있어야 만들어진다.

화면 구조는 2026-10-21 로그인 화면(한국어 UI)에서 맞췄다(D-0032). 업로드한 이미지의 비율을 영상이 따르므로
종횡비 버튼은 누르지 않는다. 계정 등급에서 막힌 옵션을 누르면 주소에 #subscribe가 붙고 결제 창이 뜬다.
"""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from character_factory_poc.common.errors import VideoGenerationError
from character_factory_poc.providers.base import VideoRequest, VideoResult

CHROME_COMMAND = (
    '"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" '
    "--remote-debugging-port={port} --user-data-dir={profile}"
)
DEFAULT_PROFILE = "~/.cfp/grok-chrome"
FORM = "form:has(button[type=submit])"
# 2026-10-21 실제 화면 기준. 영어 UI 이름은 추정이다. [providers.video.selectors]로 덮어쓴다.
DEFAULT_SELECTORS: dict[str, str] = {
    "video_mode": f'{FORM} button[aria-label="비디오"], {FORM} button[aria-label="Video"]',
    "option": f'{FORM} button[role=radio]:has-text("{{label}}")',
    "audio": f'{FORM} button[aria-label="비디오 오디오"], {FORM} button[aria-label="Video audio"]',
    "upload": f"{FORM} input[type=file]",
    # 업로드가 붙었다는 표시(첨부 이미지 제거 버튼)
    "uploaded": f'{FORM} button[aria-label="Remove image"]',
    "prompt": f"{FORM} [contenteditable=true]",
    "submit": f"{FORM} button[type=submit]",
}
# 웹 화면이 고를 수 있는 값(2026-10-21). 무료 등급은 480p·6s만 된다.
WEB_DURATIONS = (6, 10, 15)
WEB_RESOLUTIONS = ("480p", "720p")
PAYWALL = "#subscribe"
POST_URL = re.compile(r"/imagine/post/([0-9a-f-]{36})")


class WebDriver(Protocol):
    def open(self, url: str) -> None: ...
    def click(self, selector: str) -> None: ...
    def attribute(self, selector: str, name: str) -> str | None: ...
    def current_url(self) -> str: ...
    def upload(self, selector: str, path: str) -> None: ...
    def wait_visible(self, selector: str, timeout_s: float) -> None: ...
    def fill(self, selector: str, text: str) -> None: ...
    def wait_result(self, timeout_s: float) -> tuple[str, str]: ...
    def fetch(self, url: str, timeout_s: float) -> bytes: ...
    def screenshot(self, path: Path) -> None: ...
    def close(self) -> None: ...


class PlaywrightCdpDriver:
    """실제 드라이버. playwright는 선택 의존성이다(uv sync --extra web). 브라우저는 내려받지 않는다."""

    def __init__(self, cdp_url: str):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:  # pragma: no cover - 환경 의존
            raise VideoGenerationError(
                "playwright가 없다. 'uv sync --extra web'으로 설치한다(브라우저 다운로드는 필요 없다)"
            ) from e
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.connect_over_cdp(cdp_url, timeout=15000)
        except Exception as e:  # pragma: no cover - 환경 의존
            self._pw.stop()
            raise VideoGenerationError(
                f"{cdp_url}의 Chrome에 붙지 못했다. 'cfp video web-setup' 안내대로 전용 프로필 Chrome을 띄운다: {e}"
            ) from e
        ctx = self._browser.contexts[0] if self._browser.contexts else self._browser.new_context()
        self._page = ctx.new_page()
        self._page.set_default_timeout(15000)
        # 뒤에 숨은 탭은 브라우저가 화면 갱신을 늦출 수 있어 앞으로 가져온다.
        self._page.bring_to_front()

    def open(self, url: str) -> None:  # pragma: no cover - 실제 브라우저
        self._page.goto(url, wait_until="domcontentloaded")
        self._page.locator(DEFAULT_SELECTORS["submit"]).first.wait_for(state="visible")

    def click(self, selector: str) -> None:  # pragma: no cover
        self._page.locator(selector).first.click()
        self._page.wait_for_timeout(400)

    def attribute(self, selector: str, name: str) -> str | None:  # pragma: no cover
        return self._page.locator(selector).first.get_attribute(name)

    def current_url(self) -> str:  # pragma: no cover
        return self._page.url

    def upload(self, selector: str, path: str) -> None:  # pragma: no cover
        self._page.locator(selector).first.set_input_files(path)

    def wait_visible(self, selector: str, timeout_s: float) -> None:  # pragma: no cover
        self._page.locator(selector).first.wait_for(state="visible", timeout=timeout_s * 1000)

    def fill(self, selector: str, text: str) -> None:  # pragma: no cover
        box = self._page.locator(selector).first
        box.click()
        box.fill(text)
        if not box.inner_text().strip():  # 편집기가 fill을 받지 않으면 키 입력으로 넣는다
            self._page.keyboard.insert_text(text)
        if not box.inner_text().strip():
            raise VideoGenerationError("프롬프트가 입력되지 않았다")

    def wait_result(self, timeout_s: float) -> tuple[str, str]:  # pragma: no cover
        """결과 페이지(/imagine/post/<id>)로 넘어가고 그 id의 영상이 재생 가능해질 때까지 기다린다.

        제출이 받아지면 몇 초 안에 결과 페이지로 넘어간다. 90초 안에 넘어가지 않으면 제출이 안 된 것으로 본다."""
        deadline = time.monotonic() + timeout_s
        submit_deadline = time.monotonic() + min(90.0, timeout_s)
        while not POST_URL.search(self._page.url):
            if PAYWALL in self._page.url:
                raise VideoGenerationError(
                    "제출하자 결제 창이 떴다. 이 Grok 계정의 영상 생성 한도를 다 썼다"
                    "(무료 등급은 2026-10-21 실측 1편 뒤 막힘)"
                )
            if time.monotonic() > submit_deadline:
                raise VideoGenerationError("제출 뒤 결과 페이지로 넘어가지 않았다(제출 안 됨)")
            self._page.wait_for_timeout(1000)
        m = POST_URL.search(self._page.url)
        post = m.group(1) if m else ""
        js = (
            "(id)=>{const v=[...document.querySelectorAll('video')].find(v=>"
            "(v.currentSrc||v.src||'').includes(id)&&v.duration>0);return v?(v.currentSrc||v.src):null}"
        )
        while time.monotonic() < deadline:
            src = self._page.evaluate(js, post)
            if src:
                return post, src
            self._page.wait_for_timeout(3000)
        raise TimeoutError(f"{timeout_s}초 안에 결과 영상이 나오지 않았다")

    def fetch(self, url: str, timeout_s: float) -> bytes:  # pragma: no cover
        res = self._page.context.request.get(url, timeout=timeout_s * 1000)
        if not res.ok:
            raise VideoGenerationError(f"영상 받기 실패 HTTP {res.status}")
        return res.body()

    def screenshot(self, path: Path) -> None:  # pragma: no cover
        self._page.screenshot(path=str(path), full_page=True)

    def close(self) -> None:  # pragma: no cover
        try:
            self._page.close()
        finally:
            self._pw.stop()  # 사용자의 Chrome은 닫지 않는다


class GrokWebVideoModel:
    name = "grok_web"
    resumable = False  # 브라우저 작업은 중간에 끊기면 다시 이어 받을 수 없다

    def __init__(
        self,
        model: str = "grok-imagine-web",
        cdp_url: str = "http://127.0.0.1:9222",
        imagine_url: str = "https://grok.com/imagine",
        selectors: dict[str, str] | None = None,
        timeout_s: float = 600.0,
        work_dir: Path | None = None,
        driver_factory: Callable[[str], WebDriver] | None = None,
    ):
        self.model = model
        self.cdp_url = cdp_url
        self.imagine_url = imagine_url
        self.selectors = DEFAULT_SELECTORS | dict(selectors or {})
        self.timeout_s = timeout_s
        self.work_dir = Path(work_dir or Path.home() / ".cfp" / "grok-web-work")
        self.driver_factory = driver_factory or PlaywrightCdpDriver
        self._done: dict[str, VideoResult] = {}

    @staticmethod
    def check_settings(duration: int, resolution: str) -> None:
        """웹 화면에 없는 값이면 이미지·영상 생성 전에 거절한다."""
        bad = []
        if duration not in WEB_DURATIONS:
            bad.append(f"길이 {duration}초(웹은 {'/'.join(map(str, WEB_DURATIONS))}초)")
        if resolution not in WEB_RESOLUTIONS:
            bad.append(f"해상도 {resolution}(웹은 {'/'.join(WEB_RESOLUTIONS)})")
        if bad:
            raise VideoGenerationError(
                "grok_web이 고를 수 없는 설정: " + ", ".join(bad) + ". [stages.s5]를 바꾼다"
            )

    def _option(self, driver: WebDriver, label: str) -> None:
        driver.click(self.selectors["option"].replace("{label}", label))
        if PAYWALL in driver.current_url():
            raise VideoGenerationError(
                f"이 Grok 계정 등급에서는 '{label}'을 고를 수 없다(결제 창이 떴다). "
                "무료 등급은 480p·6초다. [stages.s5]를 바꾼다"
            )

    def submit(self, request: VideoRequest) -> str:
        self.check_settings(request.duration, request.resolution)
        job_id = f"web-{uuid.uuid4().hex[:12]}"
        job_dir = self.work_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        s = self.selectors
        t0 = time.monotonic()
        driver = self.driver_factory(self.cdp_url)
        step = "open"
        try:
            driver.open(self.imagine_url)
            step = "video_mode"
            driver.click(s["video_mode"])
            step = "resolution"
            self._option(driver, request.resolution)
            step = "duration"
            self._option(driver, f"{request.duration}s")
            step = "audio"
            on = driver.attribute(s["audio"], "aria-pressed") == "true"
            if on != bool(request.generate_audio):
                driver.click(s["audio"])
            step = "upload"
            driver.upload(s["upload"], str(Path(request.first_frame).resolve()))
            driver.wait_visible(s["uploaded"], 30.0)
            step = "prompt"
            driver.fill(s["prompt"], request.prompt)
            step = "submit"
            driver.click(s["submit"])
            step = "wait"
            post, src = driver.wait_result(self.timeout_s)
            step = "fetch"
            data = driver.fetch(src, 120.0)
            if data[4:8] != b"ftyp":
                raise VideoGenerationError("받은 파일이 MP4가 아니다")
            path = job_dir / "video.mp4"
            path.write_bytes(data)
        except Exception as e:
            shot = job_dir / f"error-{step}.png"
            try:
                driver.screenshot(shot)
            except Exception:  # noqa: BLE001 - 스크린샷 실패는 원래 오류를 가리지 않는다
                shot = None  # type: ignore[assignment]
            hint = f" 스크린샷: {shot}" if shot else ""
            raise VideoGenerationError(f"Grok 웹 '{step}' 단계 실패: {e}.{hint}") from e
        finally:
            driver.close()
        self._done[job_id] = VideoResult(
            data=data,
            mime="video/mp4",
            model=self.model,
            provider=self.name,
            elapsed_ms=int((time.monotonic() - t0) * 1000),
            job_id=f"{job_id}:{post}",
            seconds=float(request.duration),
            est_cost_usd=0.0,
            source_path=str(path),
        )
        return job_id

    def collect(self, job_id: str, request: VideoRequest) -> VideoResult:
        if job_id not in self._done:
            raise VideoGenerationError(f"웹 작업 {job_id}는 이어 받을 수 없다. 다시 제출한다")
        return self._done.pop(job_id)

    @staticmethod
    def chrome_command(port: int = 9222, profile: str = DEFAULT_PROFILE) -> str:
        return CHROME_COMMAND.format(port=port, profile=str(Path(profile).expanduser()))


def selectors_from(extra: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in dict(extra.get("selectors") or {}).items()}
