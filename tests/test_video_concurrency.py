from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock

import httpx
import pytest


def test_pacer_spaces_requests_and_honors_shared_cooldown():
    from character_factory_poc.providers.video_concurrency import SubmissionPacer

    now = [0.0]
    pacer = SubmissionPacer(clock=lambda: now[0], sleep=lambda dt: now.__setitem__(0, now[0] + dt))
    times = []
    for _ in range(6):
        pacer.wait()
        times.append(now[0])
    assert times == [0, 1, 2, 3, 4, 5]
    pacer.defer(4)
    pacer.wait()
    assert now[0] == 9


def test_video_slots_bound_overlapping_jobs_across_pools():
    from character_factory_poc.providers.video_concurrency import run_video_jobs, video_job_slot

    release, full = Event(), Event()
    lock = Lock()
    active = peak = 0

    def job(i):
        nonlocal active, peak
        with video_job_slot():
            with lock:
                active += 1
                peak = max(peak, active)
                if active == 6:
                    full.set()
            assert release.wait(3)
            with lock:
                active -= 1
        return i

    with ThreadPoolExecutor(2) as pool:
        a = pool.submit(run_video_jobs, job, list(range(6)))
        b = pool.submit(run_video_jobs, job, list(range(6, 12)))
        try:
            assert full.wait(3), "six jobs must overlap before any completes"
            assert peak == 6
        finally:
            release.set()
        assert a.result() == list(range(6))
        assert b.result() == list(range(6, 12))
    assert peak == 6


def test_first_failure_prevents_more_queued_jobs_and_drains_running():
    from character_factory_poc.providers.video_concurrency import run_video_jobs

    started = []

    def fail(i):
        started.append(i)
        raise ValueError("stop")

    with pytest.raises(ValueError, match="stop"):
        run_video_jobs(fail, range(20), workers=1)
    assert started == [0]


def test_video_http_retry_uses_same_pacer_and_retry_after(monkeypatch):
    from character_factory_poc.providers import xai_video
    from character_factory_poc.providers.video_concurrency import SubmissionPacer

    now, starts = [0.0], []

    def sleep(dt):
        now[0] += dt

    pacer = SubmissionPacer(clock=lambda: now[0], sleep=sleep)
    monkeypatch.setattr(xai_video, "get_submission_pacer", lambda base: pacer)

    def handle(req):
        starts.append(now[0])
        if len(starts) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json={"request_id": "ok"})

    model = xai_video.XaiVideoModel(
        client=httpx.Client(transport=httpx.MockTransport(handle)), sleep=sleep
    )
    model._request("POST", "https://api.x.ai/v1/videos/generations", json={})
    assert starts == [0, 3]
    model._request("POST", "https://api.x.ai/v1/videos/generations", json={})
    assert starts == [0, 3, 4]


def test_concurrent_oauth_fallback_keeps_provider_per_worker():
    from types import SimpleNamespace

    from character_factory_poc.common.errors import VideoGenerationError
    from character_factory_poc.providers.grok_chain import GrokVideoChain

    class Member:
        model = "test"

        def __init__(self, name):
            self.name = name

        def submit(self, request):
            if self.name == "grok_oauth" and request.ref == "api":
                raise VideoGenerationError("HTTP 401")
            return request.ref

    chain = GrokVideoChain([Member("grok_oauth"), Member("xai_video")])
    synced = Barrier(2)

    def submit(ref):
        chain.submit(SimpleNamespace(ref=ref))
        synced.wait(timeout=3)
        return chain.name

    with ThreadPoolExecutor(2) as pool:
        assert list(pool.map(submit, ["oauth", "api"])) == ["grok_oauth", "xai_video"]
