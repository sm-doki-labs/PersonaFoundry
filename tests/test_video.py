"""S5 소개 영상·G5와 두 영상 어댑터(xai_video, grok_web) 오프라인 테스트 (D-0028~D-0030). 네트워크 없음."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

import acf.contracts  # noqa: F401
from acf.cli import main
from acf.common.config import ProviderConfig
from acf.common.errors import (
    BudgetExceeded,
    CheckFailed,
    FactoryError,
    GateNotApprovedError,
    VideoGenerationError,
    VideoTimeoutError,
)
from acf.pipeline.approve import approve_gate
from acf.pipeline.context import Context
from acf.pipeline.orchestrator import RunOptions, run_until
from acf.providers.base import VideoRequest
from acf.providers.factory import make_video_model
from acf.providers.fake import FakeTextModel
from acf.providers.fake_image import FakeImageModel, solid_png
from acf.providers.fake_video import FAKE_MP4, FakeVideoModel
from acf.providers.grok_web import GrokWebVideoModel
from acf.providers.xai_video import XaiVideoModel, estimate_cost
from acf.stages.s1_reference.run import run_s1
from acf.stages.s2_hero.approve import load_appearance_spec
from acf.stages.s2_hero.run import run_s2
from acf.stages.s3_plan.draft import new_character
from acf.stages.s5_intro.approve import load_approved_intro
from acf.stages.s5_intro.first_frame import crop_to_ratio, parse_ratio
from acf.stages.s5_intro.run import run_s5
from tests.support.synthetic import RANKING
from tests.test_agentic import BRIEF, CATALOG
from tests.test_frames import agent


def _ctx(root: Path, extra: str = "") -> Context:
    (root / "catalog.json").write_text(json.dumps(CATALOG, ensure_ascii=False), "utf-8")
    (root / "factory.toml").write_text(
        f'[resources]\nstanford_presets_json = "{root / "catalog.json"}"\n{extra}'
        '\n[stages.s2]\nbase_photo = "picked"\n',
        encoding="utf-8",
    )
    c = Context.load(root, execute=True)
    text = FakeTextModel()
    text.add("AGENT", agent)
    c.use_models(text)
    c.use_image(FakeImageModel())
    c.use_video(FakeVideoModel())
    return c


@pytest.fixture
def ctx(tmp_path: Path) -> Context:
    return _ctx(tmp_path)


def _through_s2(ctx: Context) -> str:
    cid = new_character(ctx, "intro")
    run_s1(ctx, cid, RANKING)
    approve_gate(
        ctx,
        cid,
        "G1",
        {
            "decision": "SELECT",
            "selections": ["c2"],
            "referencePreviews": ["c2-1"],
            "reviewer": "u",
        },
    )
    run_s2(ctx, cid)
    return cid


# ---------------------------------------------------------------- S5·G5


def test_s5_requires_s2(ctx):
    cid = new_character(ctx, "nog2")
    with pytest.raises(GateNotApprovedError, match="s2"):
        run_s5(ctx, cid)


def _png_size(path: Path) -> tuple[int, int]:
    raw = path.read_bytes()
    return int.from_bytes(raw[16:20], "big"), int.from_bytes(raw[20:24], "big")


def test_s5_offline_to_g5_human_select(ctx):
    video = FakeVideoModel()
    image = FakeImageModel()
    ctx.use_video(video)
    ctx.use_image(image)
    cid = _through_s2(ctx)
    out = run_s5(ctx, cid)
    st = ctx.state(cid)
    assert out.name == "vi1" and st.stage("s5").status == "AWAITING_HUMAN"
    assert st.gate("G5").status == "AWAITING_HUMAN"
    # 첫 프레임은 기준 이미지(S2 picked = G1 얼굴)를 참조로 새로 만든 9:16 세로 사진(D-0031)
    _, hero = load_appearance_spec(ctx, cid)
    assert (out / "hero.png").read_bytes() == hero.read_bytes()
    img_req = [r for r in image.requests if r.stage == "s5"]
    assert len(img_req) == 1 and img_req[0].size == "1024x1536"
    assert img_req[0].reference_images == (str(out / "hero.png"),)
    assert "Vertical 9:16" in img_req[0].prompt and "chin resting" in img_req[0].negative_prompt
    w, h = _png_size(out / "first-frame.png")
    assert abs(w / h - 9 / 16) < 0.03 and _png_size(out / "first-frame-raw.png") != (w, h)
    inputs = json.loads((out / "inputs.json").read_text("utf-8"))
    assert inputs["schemaVersion"] == "intro-inputs-v2"
    assert inputs["firstFrameSource"]["mode"] == "generated"
    assert inputs["firstFrameSource"]["croppedSize"] == [w, h]
    assert len(video.submits) == 2 and all(
        r.first_frame == str(out / "first-frame.png") for r in video.submits
    )
    req = video.submits[0]
    assert (req.duration, req.resolution, req.generate_audio) == (8, "720p", False)
    assert req.aspect_ratio == "9:16"
    assert "same person" in req.prompt and "No text" in req.prompt
    jobs = [json.loads((out / "jobs" / f"v{n}.json").read_text("utf-8")) for n in (1, 2)]
    assert [j["status"] for j in jobs] == ["DONE", "DONE"]
    assert jobs[0]["videoId"] == f"vd-{cid}-intro-vi1-1"
    assets = json.loads((out / "videos.json").read_text("utf-8"))
    assert [a["candidateId"] for a in assets] == ["v1", "v2"]
    assert (out / "videos" / "v1.mp4").read_bytes() == FAKE_MP4
    page = (out / "gate-G5.html").read_text("utf-8")
    assert '<video src="videos/v2.mp4"' in page and 'value="v2"' in page
    assert 'src="hero.png"' in page and 'src="first-frame.png"' in page and "9:16" in page
    calls = [c for c in ctx.ledger(cid).calls() if c["kind"] == "VIDEO"]
    assert len(calls) == 2 and calls[0]["seconds"] == 8.0

    with pytest.raises(FactoryError):
        approve_gate(ctx, cid, "G5", {"decision": "SELECT", "selections": ["v9"], "reviewer": "u"})
    approve_gate(
        ctx, cid, "G5", {"decision": "SELECT", "selections": ["v2"], "reviewer": "u", "minutes": 2}
    )
    approved, rev_dir = load_approved_intro(ctx, cid)
    assert approved.videoId == f"vd-{cid}-intro-vi1-2" and approved.appearanceRev == "ar1"
    assert (rev_dir / approved.video.path).exists()
    assert ctx.state(cid).stage("s5").status == "APPROVED"
    assert main(["--root", str(ctx.config.root), "verify", cid]) == 0


class Flaky(FakeVideoModel):
    """첫 수집에서 시간 초과를 내고, 그 뒤로는 정상."""

    def __init__(self):
        super().__init__()
        self.fail_next = True

    def collect(self, job_id, request):
        if self.fail_next:
            self.fail_next = False
            self.collects.append(job_id)
            raise VideoTimeoutError(job_id, "아직 생성 중")
        return super().collect(job_id, request)


def test_s5_resumes_same_job_after_timeout(ctx):
    cid = _through_s2(ctx)
    flaky = Flaky()
    ctx.use_video(flaky)
    with pytest.raises(VideoTimeoutError):
        run_s5(ctx, cid)
    assert ctx.state(cid).stage("s5").status == "CHECK_FAILED"
    job = json.loads((ctx.character_dir(cid) / "s5-intro" / "vi1" / "jobs" / "v1.json").read_text())
    assert job["status"] == "SUBMITTED" and job["jobId"] == "fake-job-1"
    image = FakeImageModel()
    ctx.use_image(image)
    out = run_s5(ctx, cid)
    assert out.name == "vi1"  # 같은 rev에서 이어 간다
    assert len(flaky.submits) == 2  # v1은 다시 제출하지 않았다(v1 1회 + v2 1회)
    assert flaky.collects == ["fake-job-1", "fake-job-1", "fake-job-2"]
    assert image.requests == []  # 첫 프레임도 다시 만들지 않았다


def test_s5_hero_mode_uses_picked_image_as_is(tmp_path):
    ctx = _ctx(tmp_path, '\n[stages.s5]\nfirst_frame = "hero"\naspect_ratio = ""\n')
    image = FakeImageModel()
    ctx.use_image(image)
    cid = _through_s2(ctx)
    image.requests.clear()
    out = run_s5(ctx, cid)
    _, hero = load_appearance_spec(ctx, cid)
    assert (out / "first-frame.png").read_bytes() == hero.read_bytes() and image.requests == []
    src = json.loads((out / "inputs.json").read_text("utf-8"))["firstFrameSource"]
    assert src["mode"] == "hero" and src["rawSize"] is None


def test_s5_square_first_frame_is_rejected_not_cropped(ctx):
    class Square(FakeImageModel):
        def generate(self, request):
            return super().generate(replace(request, size="1024x1024"))

    ctx.use_image(Square())
    video = FakeVideoModel()
    ctx.use_video(video)
    cid = _through_s2(ctx)
    with pytest.raises(CheckFailed, match="너무 벗어났다"):
        run_s5(ctx, cid)
    assert ctx.state(cid).stage("s5").status == "CHECK_FAILED" and video.submits == []


def test_crop_to_ratio_center_crops():
    png, raw, cropped = crop_to_ratio(solid_png(941, 1672, (9, 9, 9)), (9, 16))
    assert raw == (941, 1672) and cropped == (940, 1672) and png.startswith(b"\x89PNG")
    _, _, cropped = crop_to_ratio(solid_png(1024, 1536, (9, 9, 9)), (9, 16))
    assert cropped == (864, 1536)
    with pytest.raises(ValueError, match="비율"):
        parse_ratio("tall")


def test_s5_resumes_after_interrupted_process(ctx):
    cid = _through_s2(ctx)

    class Interrupted(FakeVideoModel):
        def submit(self, request):
            raise KeyboardInterrupt  # 사람이 프로세스를 끊음: 상태가 RUNNING으로 남는다

    ctx.use_video(Interrupted())
    with pytest.raises(KeyboardInterrupt):
        run_s5(ctx, cid)
    assert ctx.state(cid).stage("s5").status == "RUNNING"
    image = FakeImageModel()
    ctx.use_image(image)
    ctx.use_video(FakeVideoModel())
    assert run_s5(ctx, cid).name == "vi1" and image.requests == []


def test_s5_failed_job_is_recorded(ctx):
    cid = _through_s2(ctx)

    class Broken(FakeVideoModel):
        def collect(self, job_id, request):
            raise VideoGenerationError("moderation")

    ctx.use_video(Broken())
    with pytest.raises(VideoGenerationError):
        run_s5(ctx, cid)
    job = json.loads((ctx.character_dir(cid) / "s5-intro" / "vi1" / "jobs" / "v1.json").read_text())
    assert job["status"] == "FAILED" and "moderation" in job["error"]


def test_s5_cost_cap_rejects_before_submit(tmp_path):
    ctx = _ctx(
        tmp_path,
        '\n[providers.video]\nadapter = "xai_video"\nmodel = "grok-imagine-video-1.5"\n'
        '\n[stages.s5]\nresolution = "1080p"\n\n[budget]\nmax_cost_usd_per_command = 1.0\n',
    )
    video = FakeVideoModel()
    ctx.use_video(video)
    cid = _through_s2(ctx)
    with pytest.raises(BudgetExceeded, match="USD"):
        run_s5(ctx, cid)
    assert video.submits == []


def test_run_until_g5_with_auto_frames(ctx):
    cid = new_character(ctx, "orch5")
    opt = RunOptions(until="G6", ranking=RANKING, brief_text=BRIEF, auto_approve={"G1", "G3", "G4"})
    log = run_until(ctx, cid, opt)
    assert log.stopped_at == "G5" and ctx.state(cid).gate("G5").status == "AWAITING_HUMAN"


def test_video_dry_run_shows_cost(tmp_path, capsys):
    ctx = _ctx(
        tmp_path,
        '\n[providers.video]\nadapter = "xai_video"\nmodel = "grok-imagine-video-1.5-lite"\n',
    )
    cid = _through_s2(ctx)
    assert main(["--root", str(tmp_path), "video", "intro", cid]) == 0
    out = capsys.readouterr().out
    # 2편 × (8초 × $0.03 + 입력 이미지 $0.01) = $0.50, 첫 프레임은 구독·가짜라 0
    assert "소개 영상 후보 2편" in out and "0.50 USD" in out and "9:16 첫 프레임 1장" in out
    assert main(["--root", str(tmp_path), "video", "web-setup"]) == 0
    assert "--remote-debugging-port=9222" in capsys.readouterr().out


# ---------------------------------------------------------------- xai_video


def _req(tmp_path: Path) -> VideoRequest:
    frame = tmp_path / "frame.png"
    frame.write_bytes(solid_png(4, 4, (1, 2, 3)))
    return VideoRequest(stage="s5", prompt="smile", ref="x", first_frame=str(frame))


def _xai(handler, monkeypatch, **kw) -> XaiVideoModel:
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return XaiVideoModel(client=client, sleep=lambda s: None, **kw)


def test_xai_submit_poll_download(tmp_path, monkeypatch):
    seen: list[httpx.Request] = []
    polls = iter(["pending", "pending", "done"])

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, json={"request_id": "req-123"})
        if request.url.path == "/v1/videos/req-123":
            st = next(polls)
            body = {"status": st}
            if st == "done":
                body["video"] = {"url": "https://cdn.example/v.mp4", "duration": 8}
            return httpx.Response(200, json=body)
        if request.url.host == "cdn.example":
            return httpx.Response(200, content=FAKE_MP4)
        return httpx.Response(404)

    m = _xai(handler, monkeypatch)
    req = _req(tmp_path)
    job = m.submit(req)
    assert job == "req-123"
    post = seen[0]
    assert post.url.path == "/v1/videos/generations"
    assert post.headers["authorization"] == "Bearer test-key"
    body = json.loads(post.content)
    assert body["model"] == "grok-imagine-video-1.5-lite" and body["prompt"] == "smile"
    assert body["image"]["url"].startswith("data:image/png;base64,")
    assert (body["duration"], body["resolution"], body["generate_audio"]) == (8, "720p", False)
    assert "aspect_ratio" not in body
    res = m.collect(job, req)
    assert res.data == FAKE_MP4 and res.seconds == 8.0 and res.job_id == "req-123"
    assert res.est_cost_usd == pytest.approx(8 * 0.03 + 0.01)
    assert "authorization" not in {
        k.lower() for k in seen[-1].headers
    }  # CDN에는 키를 보내지 않는다


def test_xai_failed_timeout_missing_key_and_retry(tmp_path, monkeypatch):
    req = _req(tmp_path)

    def failed(request):
        return httpx.Response(200, json={"status": "failed", "error": "content policy"})

    with pytest.raises(VideoGenerationError, match="content policy"):
        _xai(failed, monkeypatch).collect("req-1", req)

    ticks = iter(range(0, 10_000, 100))
    pending = _xai(
        lambda r: httpx.Response(200, json={"status": "pending"}),
        monkeypatch,
        timeout_s=250,
        clock=lambda: next(ticks),
    )
    with pytest.raises(VideoTimeoutError) as e:
        pending.collect("req-9", req)
    assert e.value.job_id == "req-9"

    monkeypatch.delenv("XAI_API_KEY")
    m = XaiVideoModel(
        client=httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("네트워크 호출")))
    )
    with pytest.raises(VideoGenerationError, match="XAI_API_KEY"):
        m.submit(req)

    codes = iter([429, 503, 200])

    def flaky(request):
        c = next(codes)
        return httpx.Response(c, json={"request_id": "ok"} if c == 200 else {})

    assert _xai(flaky, monkeypatch).submit(req) == "ok"


def test_estimate_cost_table():
    assert estimate_cost("grok-imagine-video-1.5", "1080p", 8) == pytest.approx(2.01)
    assert estimate_cost("grok-imagine-video-1.5-lite", "720p", 8) == pytest.approx(0.25)
    assert estimate_cost("unknown", "720p", 8) is None


# ---------------------------------------------------------------- grok_web


class FakeDriver:
    """실제 화면 흐름(2026-10-21)을 흉내 낸다. paywall에 든 옵션을 누르면 주소에 #subscribe가 붙는다."""

    def __init__(
        self,
        tmp: Path,
        fail_at: str | None = None,
        payload: bytes = FAKE_MP4,
        paywall: tuple[str, ...] = (),
        audio_on: bool = True,
    ):
        self.tmp = tmp
        self.fail_at = fail_at
        self.payload = payload
        self.paywall = paywall
        self.audio_on = audio_on
        self.url = ""
        self.steps: list[tuple] = []
        self.closed = False

    def _step(self, *s):
        self.steps.append(s)
        if self.fail_at == s[0]:
            raise RuntimeError(f"{s[0]} 요소 없음")

    def open(self, url):
        self.url = url
        self._step("open", url)

    def upload(self, selector, path):
        self._step("upload", selector, path)

    def wait_visible(self, selector, timeout_s):
        self._step("uploaded", selector)

    def fill(self, selector, text):
        self._step("fill", selector, text)

    def click(self, selector):
        self._step("click", selector)
        if any(f'"{p}"' in selector for p in self.paywall):
            self.url += "#subscribe"
        if "오디오" in selector:
            self.audio_on = not self.audio_on

    def attribute(self, selector, name):
        return "true" if self.audio_on else "false"

    def current_url(self):
        return self.url

    def wait_result(self, timeout_s):
        self._step("wait")
        return "post-1", "https://assets.example/post-1/generated_video.mp4"

    def fetch(self, url, timeout_s):
        self._step("fetch", url)
        return self.payload

    def screenshot(self, path):
        Path(path).write_bytes(b"png")
        self.steps.append(("screenshot", str(path)))

    def close(self):
        self.closed = True


def test_grok_web_flow_with_fake_driver(tmp_path):
    driver = FakeDriver(tmp_path)
    m = GrokWebVideoModel(work_dir=tmp_path / "work", driver_factory=lambda url: driver)
    req = replace(_req(tmp_path), duration=6, resolution="480p")
    job = m.submit(req)
    names = [s[0] for s in driver.steps]
    # 비디오 모드 → 480p → 6s → 소리 끔(켜져 있었으므로 한 번 누름) → 업로드 → 프롬프트 → 제출 → 대기 → 받기
    assert names == [
        "open",
        "click",
        "click",
        "click",
        "click",
        "upload",
        "uploaded",
        "fill",
        "click",
        "wait",
        "fetch",
    ]
    clicks = [s[1] for s in driver.steps if s[0] == "click"]
    assert '"비디오"' in clicks[0] and '"480p"' in clicks[1] and '"6s"' in clicks[2]
    assert "오디오" in clicks[3] and "submit" in clicks[4] and not driver.audio_on
    assert driver.steps[5][2] == str(Path(req.first_frame).resolve())
    assert driver.steps[7][2] == "smile" and driver.closed
    res = m.collect(job, req)
    assert res.data == FAKE_MP4 and res.provider == "grok_web" and res.est_cost_usd == 0.0
    assert res.job_id.endswith(":post-1") and Path(res.source_path).read_bytes() == FAKE_MP4
    with pytest.raises(VideoGenerationError, match="이어 받을 수 없다"):
        m.collect(job, req)


def test_grok_web_rejects_unsupported_settings_and_paywall(tmp_path):
    m = GrokWebVideoModel(work_dir=tmp_path / "work", driver_factory=lambda url: 1 / 0)
    with pytest.raises(VideoGenerationError, match="길이 8초"):
        m.submit(_req(tmp_path))  # 기본 8초는 웹에 없다. 브라우저를 열기 전에 거절
    driver = FakeDriver(tmp_path, paywall=("720p",))
    m = GrokWebVideoModel(work_dir=tmp_path / "work", driver_factory=lambda url: driver)
    with pytest.raises(VideoGenerationError, match="결제 창"):
        m.submit(replace(_req(tmp_path), duration=6, resolution="720p"))
    assert "upload" not in [s[0] for s in driver.steps] and driver.closed


def test_s5_checks_web_settings_before_first_frame(ctx):
    cid = _through_s2(ctx)
    image = FakeImageModel()
    ctx.use_image(image)
    ctx.use_video(GrokWebVideoModel(driver_factory=lambda url: 1 / 0))
    with pytest.raises(VideoGenerationError, match="고를 수 없는 설정"):
        run_s5(ctx, cid)
    assert image.requests == [] and ctx.state(cid).stage("s5").status == "CHECK_FAILED"


@pytest.mark.parametrize(
    "fail_at, payload, match",
    [("wait", FAKE_MP4, "'wait' 단계"), (None, b"<html>", "MP4가 아니다")],
)
def test_grok_web_failure_leaves_screenshot(tmp_path, fail_at, payload, match):
    driver = FakeDriver(tmp_path, fail_at=fail_at, payload=payload)
    m = GrokWebVideoModel(work_dir=tmp_path / "work", driver_factory=lambda url: driver)
    with pytest.raises(VideoGenerationError, match=match) as e:
        m.submit(replace(_req(tmp_path), duration=6, resolution="480p"))
    assert "스크린샷" in str(e.value) and driver.steps[-1][0] == "screenshot" and driver.closed


def test_factory_video_adapters(monkeypatch):
    assert isinstance(make_video_model(ProviderConfig(adapter="fake")), FakeVideoModel)
    x = make_video_model(
        ProviderConfig(
            adapter="xai_video",
            model="grok-imagine-video-1.5",
            extra={"poll_interval_s": 2, "timeout_s": 300},
        )
    )
    assert isinstance(x, XaiVideoModel) and (x.poll_interval_s, x.timeout_s) == (2.0, 300.0)
    with pytest.raises(ValueError, match="accept_terms_risk"):
        make_video_model(ProviderConfig(adapter="grok_web"))
    w = make_video_model(
        ProviderConfig(
            adapter="grok_web",
            extra={
                "accept_terms_risk": True,
                "cdp_url": "http://127.0.0.1:9333",
                "selectors": {"submit": "#go"},
            },
        )
    )
    assert isinstance(w, GrokWebVideoModel) and w.cdp_url.endswith(":9333")
    assert w.selectors["submit"] == "#go" and w.selectors["upload"].endswith("input[type=file]")
    with pytest.raises(ValueError, match="알 수 없는 영상 어댑터"):
        make_video_model(ProviderConfig(adapter="sora"))
