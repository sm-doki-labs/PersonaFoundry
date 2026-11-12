"""가짜 VideoGen (NFR-08). 제출·수집을 흉내 내고 작은 MP4 모양 바이트를 돌려준다. 네트워크 없음."""

from __future__ import annotations

from threading import Lock

from character_factory_poc.providers.base import VideoRequest, VideoResult

# ISO BMFF 시그니처(4~8바이트 'ftyp')만 갖춘 더미. 재생 가능한 영상은 아니다.
FAKE_MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00" * 64
_submit_lock = Lock()


class FakeVideoModel:
    name = "fake_video"
    resumable = True

    def __init__(self, model: str = "fake-video"):
        self.model = model
        self.submits: list[VideoRequest] = []
        self.collects: list[str] = []

    def submit(self, request: VideoRequest) -> str:
        with _submit_lock:
            self.submits.append(request)
            return f"fake-job-{len(self.submits)}"

    def collect(self, job_id: str, request: VideoRequest) -> VideoResult:
        self.collects.append(job_id)
        return VideoResult(
            data=FAKE_MP4,
            mime="video/mp4",
            model=self.model,
            provider=self.name,
            elapsed_ms=1,
            job_id=job_id,
            seconds=float(request.duration),
            est_cost_usd=0.0,
        )
