"""브라우저 사용성 확인용 모티브 데모. 가짜 공급자, 유료 호출 없음(D-0159 QA, 2026-11-10).

uv run python scripts/motif_demo.py work/<새 폴더> [--port 8770] [--sample-mp4 <재생되는 mp4>]

원문 화면(sources.html)에서 실존 인물 캐릭터를 처음부터 만들고, 대화 가능 → 영상 등급·시그니처 →
장면·영상 → 대화해 보기까지 화면으로 따라갈 수 있다. 모든 모델 답은 tests의 합성 응답이라
내용은 고정 견본이다(말투·사실 품질을 보지 않는다). 가짜 영상은 --sample-mp4 파일을 그대로 쓴다.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_REPO))

import uvicorn  # noqa: E402

from character_factory_poc.providers.base import VideoResult  # noqa: E402
from character_factory_poc.providers.fake_video import FakeVideoModel  # noqa: E402
from character_factory_poc.providers.fake_vision import FakeVisionModel, all_pass  # noqa: E402
from character_factory_poc.web import create_app  # noqa: E402
from tests.support.flow import make_ctx  # noqa: E402
from tests.support.synthetic import prompter_output  # noqa: E402
from tests.support.web_gates import trait_sheet_for  # noqa: E402
from tests.test_chapter_start import _start  # noqa: E402
from tests.test_scene_flow import agent_input, backgrounds, poses, scenes  # noqa: E402
from tests.test_source_s0 import _good_digest  # noqa: E402
from tests.test_twin_flow import _pack  # noqa: E402
from tests.test_twin_s3 import _answer  # noqa: E402

CID = re.compile(r"cf-[0-9]{8}-[A-Za-z0-9-]+?(?=/|#|$)")


def _cid(req) -> str:
    found = CID.search(req.ref or "")
    if not found:
        raise ValueError(f"요청에서 캐릭터를 찾지 못했다: {req.ref}")
    return found[0]


class PlayableVideo(FakeVideoModel):
    def __init__(self, sample: bytes):
        super().__init__()
        self.sample = sample

    def collect(self, job_id, request) -> VideoResult:
        result = super().collect(job_id, request)
        return VideoResult(**{**result.__dict__, "data": self.sample})


def _fake_tendency_tags() -> None:
    """tests/conftest.py와 같은 가짜 경향 표시(D-0148). 모티브 S3의 판정 호출에 답한다."""
    from character_factory_poc.providers.fake import FakeTextModel
    from tests.support.tendency import fake_tags, is_tagging

    original = FakeTextModel._lookup

    def lookup(self, req):
        if is_tagging(req) and not {f"{req.stage}:{req.ref}", req.ref} & self.responses.keys():
            return fake_tags
        return original(self, req)

    FakeTextModel._lookup = lookup


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--sample-mp4", default="")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # 대화해 보기·반응 고르기도 가짜 모델로 둔다(유료 호출 없음).
    ctx, agents = make_ctx(root, '[providers.demo_chat]\nadapter = "fake"\n')
    _fake_tendency_tags()
    if args.sample_mp4:
        ctx.use_video(PlayableVideo(Path(args.sample_mp4).read_bytes()))
    ctx.use_vision(
        FakeVisionModel(
            responder=lambda req: {"faceShape": "oval"} if req.stage == "s2" else all_pass(req)
        )
    )

    def scoped(fn):
        def respond(req):
            wanted = agent_input(req, "settings")["chapters"]
            return {"chapters": [ch for ch in fn(req)["chapters"] if ch["chapterId"] in wanted]}

        return respond

    for stage, fn in {
        "s0": _good_digest,
        "s3-twin": _answer,
        "s7": lambda req: trait_sheet_for(ctx, _cid(req)),
        "s8": lambda req: prompter_output(),
        "s8c": lambda req: _start().model_dump() | {"characterId": _cid(req)},
        "s4a": scoped(backgrounds),
        "s4b-scene": scenes,
        "s4b-pose": scoped(poses),
    }.items():
        agents.set(stage, fn)

    import character_factory_poc.common.demo_chat as demo_chat
    import character_factory_poc.web.jobs as jobs

    jobs.Context = lambda **kw: ctx
    demo_chat.run_samples = lambda *a: None
    samples = root / "samples"
    samples.mkdir(exist_ok=True)
    pack = _pack(samples)
    print(
        f"견본 원문: {pack.with_name('mom.txt')}  견본 사진: {pack.with_name('mom.png')}",
        flush=True,
    )
    app = create_app(root)
    print(f"원문 화면: http://127.0.0.1:{args.port}/studio/sources.html", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
