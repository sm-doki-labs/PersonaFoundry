"""S5/S6의 동시 작업, 순서, 개별 저장과 실패 후 재개를 실제 tracked 경로로 검증한다."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError, Event, Lock

import pytest

from character_factory_poc.common.errors import VideoGenerationError, VideoTimeoutError
from character_factory_poc.common.store import read_json, verify_manifest
from character_factory_poc.providers.fake_video import FakeVideoModel
from character_factory_poc.stages.s5_intro.run import run_s5
from character_factory_poc.stages.s6_actions.run import run_s6
from tests import test_actions
from tests.test_video import _ctx, _through_s2

flow = test_actions.flow


class OverlappingVideo(FakeVideoModel):
    """첫 여섯 작업이 수집에 도착해야 완료한다. 실제 시간 지연 대신 장벽을 쓴다."""

    def __init__(self, folders, *, fail_ref=None, timeout=False):
        super().__init__()
        self.folders = folders
        self.fail_ref, self.timeout = fail_ref, timeout
        self.lock = Lock()
        self.barrier = Barrier(6)
        self.failure = Event()
        self.peer_finished = Event()
        self.active = self.peak = self.started = 0
        self.ordinals = {}

    def submit(self, request):
        with self.lock:
            job_id = super().submit(request)
            self.started += 1
            self.ordinals[job_id] = self.started
            self.active += 1
            self.peak = max(self.peak, self.active)
            assert self.active <= 6, "S5+S6 활성 영상 작업이 6개를 초과했다"
            return job_id

    def collect(self, job_id, request):
        folder = self.folders[request.stage]
        name = request.ref.rsplit("/", 1)[-1]
        job = read_json(folder / "jobs" / f"{name}.json")
        assert (job["jobId"], job["status"]) == (job_id, "SUBMITTED")
        try:
            if self.ordinals[job_id] <= 6:
                try:
                    self.barrier.wait(timeout=5)
                except BrokenBarrierError:
                    pytest.fail("여섯 영상이 완료 전에 함께 진행되지 않았다")
                if name == self.fail_ref:
                    self.failure.set()
                    if self.timeout:
                        raise VideoTimeoutError(job_id, "parallel timeout")
                    raise VideoGenerationError("parallel failure")
                if self.fail_ref:
                    assert self.failure.wait(5)
                # 첫 작업보다 다른 작업이 먼저 수집되도록 순서를 뒤집는다.
                if self.ordinals[job_id] == 1:
                    assert self.peer_finished.wait(5)
            result = super().collect(job_id, request)
            self.peer_finished.set()
            return result
        finally:
            with self.lock:
                self.active -= 1


def prepare(ctx, cid, stage, *, six=False):
    if stage == "s5":
        ctx.config.stages["s5"] = {"candidates": 6 if six else 8, "first_frame": "hero"}
        return run_s5, ctx.character_dir(cid) / "s5-intro/vi1"
    if six:
        ctx.config.stages["s6"] = {"preset": "custom", "actions": ["idle_good", "glad_good"]}
    return run_s6, ctx.character_dir(cid) / "s6-actions/va1"


def assets(folder, stage):
    rows = read_json(folder / ("videos.json" if stage == "s5" else "clips.json"))
    return rows if stage == "s5" else [row["asset"] for row in rows]


@pytest.mark.parametrize("stage", ["s5", "s6"])
def test_stage_runs_six_videos_and_preserves_input_order(flow, stage):
    ctx, cid, _ = flow
    run, folder = prepare(ctx, cid, stage)
    video = OverlappingVideo({stage: folder})
    ctx.use_video(video)
    assert run(ctx, cid) == folder
    assert video.peak == 6 and video.active == 0
    if stage == "s5":
        expected = [f"videos/v{n}.mp4" for n in range(1, 9)]
        gate = "G5"
    else:
        expected = [
            f"videos/ch{ch}-{key}-v1.mp4"
            for ch in range(1, 4)
            for key in (
                "idle_good",
                "idle_bad",
                "glad_good",
                "amused_good",
                "shy_good",
                "sorry_good",
            )
        ]
        gate = "G5b"
    rows = assets(folder, stage)
    assert [row["filePath"] for row in rows] == expected
    assert len({row["jobId"] for row in rows}) == len(expected)
    assert video.collects[0] != "fake-job-1"
    assert all(read_json(p)["status"] == "DONE" for p in (folder / "jobs").glob("*.json"))
    assert ctx.state(cid).stage(stage).status == "AWAITING_HUMAN"
    assert ctx.state(cid).gate(gate).status == "AWAITING_HUMAN"
    assert (folder / f"gate-{gate}.html").exists()
    assert verify_manifest(folder) == []


@pytest.mark.parametrize("stage", ["s5", "s6"])
@pytest.mark.parametrize("timeout", [False, True])
def test_failure_drains_successes_and_resume_does_not_resubmit_them(flow, stage, timeout):
    ctx, cid, _ = flow
    run, folder = prepare(ctx, cid, stage, six=True)
    failed_name = "v1" if stage == "s5" else "ch1-idle_good-v1"
    video = OverlappingVideo({stage: folder}, fail_ref=failed_name, timeout=timeout)
    ctx.use_video(video)
    with pytest.raises(VideoGenerationError, match="parallel"):
        run(ctx, cid)
    assert video.active == 0 and video.peak == 6
    assert ctx.state(cid).stage(stage).status == "CHECK_FAILED"
    assert not (folder / ("videos.json" if stage == "s5" else "clips.json")).exists()
    assert not (folder / "manifest.sha256").exists()
    assert len(list((folder / "assets").glob("*.json"))) == 5
    assert len(list((folder / "videos").glob("*.mp4"))) == 5
    job = read_json(folder / "jobs" / f"{failed_name}.json")
    assert job["status"] == ("SUBMITTED" if timeout else "FAILED")
    snapshots = {
        p: p.read_bytes() for p in folder.rglob("*") if p.is_file() and "jobs" not in p.parts
    }
    before_images = len(ctx._image.requests)
    ctx.config.stages[stage].update({"resolution": "480p", "candidates": 2})
    if stage == "s6":
        ctx.config.stages[stage]["pin_last_frame"] = False
    working = FakeVideoModel()
    ctx.use_video(working)
    assert run(ctx, cid) == folder
    assert len(working.submits) == (0 if timeout else 1)
    assert len(working.collects) == 1
    if timeout:
        assert working.collects == [job["jobId"]]
    else:
        assert working.submits[0].ref.endswith("/" + failed_name)
        assert working.submits[0].resolution == "720p"
        if stage == "s6":
            assert working.submits[0].last_frame == working.submits[0].first_frame
    assert len(ctx._image.requests) == before_images
    assert all(p.read_bytes() == content for p, content in snapshots.items())
    assert len(assets(folder, stage)) == 6
    assert verify_manifest(folder) == []


def test_s5_and_s6_share_six_active_video_slots(flow, tmp_path):
    actions_ctx, actions_cid, _ = flow
    intro_root = tmp_path / "intro"
    intro_root.mkdir()
    intro_ctx = _ctx(intro_root)
    intro_cid = _through_s2(intro_ctx)
    intro_run, intro_dir = prepare(intro_ctx, intro_cid, "s5")
    actions_run, actions_dir = prepare(actions_ctx, actions_cid, "s6")
    video = OverlappingVideo({"s5": intro_dir, "s6": actions_dir})
    intro_ctx.use_video(video)
    actions_ctx.use_video(video)
    with ThreadPoolExecutor(max_workers=2) as pool:
        intro = pool.submit(intro_run, intro_ctx, intro_cid)
        actions = pool.submit(actions_run, actions_ctx, actions_cid)
        assert intro.result(timeout=20) == intro_dir
        assert actions.result(timeout=20) == actions_dir
    assert video.peak == 6 and video.active == 0
    assert {r.stage for r in video.submits} == {"s5", "s6"}
    assert len(video.submits) == 26
    assert verify_manifest(intro_dir) == verify_manifest(actions_dir) == []


@pytest.mark.parametrize("stage", ["s5", "s6"])
def test_shared_browser_waits_for_previous_video(flow, stage):
    ctx, cid, _ = flow
    run, _ = prepare(ctx, cid, stage)
    entered, second_started, release = Event(), Event(), Event()

    class BrowserVideo(FakeVideoModel):
        name = "grok_web"

        def submit(self, request):
            job_id = super().submit(request)
            if job_id == "fake-job-2":
                second_started.set()
            return job_id

        def collect(self, job_id, request):
            if job_id == "fake-job-1":
                entered.set()
                assert release.wait(5)
            return super().collect(job_id, request)

    ctx.use_video(BrowserVideo())
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(run, ctx, cid)
        try:
            assert entered.wait(5)
            overlapped = second_started.wait(0.1)
        finally:
            release.set()
        future.result(timeout=10)
    assert not overlapped, "공유 브라우저에서 첫 영상 완료 전에 다음 작업을 시작했다"
