"""서버 프로세스의 영상 작업 상한과 xAI 제출 속도를 서로 분리해 제한한다."""

import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from threading import BoundedSemaphore, Event, Lock

MAX_VIDEO_JOBS = 6
_jobs = BoundedSemaphore(MAX_VIDEO_JOBS)
_browser_jobs = BoundedSemaphore(1)
_pacers_lock = Lock()
_pacers = {}


@contextmanager
def video_job_slot(*, browser=False):
    """S5·S6 및 캐릭터가 달라도 제출부터 수집·저장까지 합계 여섯 작업만 실행한다."""
    with _browser_jobs if browser else nullcontext():
        with _jobs:
            yield


class SubmissionPacer:
    def __init__(self, *, clock=time.monotonic, sleep=time.sleep):
        self.clock, self.sleep = clock, sleep
        self.lock = Lock()
        self.next_at = 0.0

    def wait(self):
        with self.lock:
            delay = self.next_at - self.clock()
            if delay > 0:
                self.sleep(delay)
            self.next_at = self.clock() + 1.0

    def defer(self, seconds):
        with self.lock:
            self.next_at = max(self.next_at, self.clock() + seconds)


def get_submission_pacer(base_url):
    with _pacers_lock:
        return _pacers.setdefault(base_url.rstrip("/"), SubmissionPacer())


def run_video_jobs(fn, items, *, workers=MAX_VIDEO_JOBS):
    """실패 후 대기 작업은 시작하지 않고 진행 중 결과를 저장한 뒤 실패를 돌려준다."""
    stopped = Event()
    failure_lock = Lock()
    failures = []

    def one(item):
        if stopped.is_set():
            return None
        try:
            return fn(item)
        except BaseException as exc:
            with failure_lock:
                if not failures:
                    failures.append(exc)
                stopped.set()
            return None

    with ThreadPoolExecutor(max_workers=max(1, min(workers, MAX_VIDEO_JOBS))) as pool:
        results = list(pool.map(one, items))
    if failures:
        raise failures[0]
    return results
