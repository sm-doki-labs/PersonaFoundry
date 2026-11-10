"""브라우저 확인용 에이전틱 워크숍 데모(D-0049). 가짜 공급자, 네트워크 없음.

uv run python scripts/agentic_demo.py work/<새 폴더> [--port 8766]

여성 합성 브리프를 G1까지 돌린 뒤 워크숍을 띄운다. 화면에서 관문을 결정하면 실행기가 이어서
돌고(자동 재개·물결 실행), G3·G6·G7·G9에는 가짜 검토자의 추천이 붙는다. 소개 영상 공급자를
유료로 표시해 s5가 "실행 확인 대기"로 멈추는 것도 볼 수 있다.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_REPO))

import uvicorn  # noqa: E402

from character_factory_poc.common.config import load_config  # noqa: E402
from character_factory_poc.pipeline.orchestrator import RunLog, RunOptions, run_until  # noqa: E402
from character_factory_poc.web import create_app  # noqa: E402
from tests import test_offline_pipeline as flow  # noqa: E402
from tests.test_agentic_flow import ORCH, review_answer  # noqa: E402

PAID_VIDEO = (
    '\n[providers.video]\nadapter = "xai_video"\nmodel = "grok-video"\npaid = true\n'
    '[providers.video.price_per_second."grok-video"]\n"720p" = 0.05\n'
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--port", type=int, default=8766)
    args = ap.parse_args()
    root = Path(args.root).resolve()
    ctx, cid = flow.setup(root, "female")
    with open(root / "factory.toml", "a", encoding="utf-8") as f:
        f.write(ORCH + PAID_VIDEO + '\n[providers.demo_chat]\nadapter = "fake"\n')
    ctx.config = load_config(root)
    ctx._judge.add("REVIEW", review_answer)  # noqa: SLF001
    extra = {
        "ranking": flow.ranking_for("female"),
        "seed": flow.SEED,
        "voice_probes": list(flow.PROBES),
        "submit_training": True,
    }
    run_until(ctx, cid, RunOptions(until="sx", **extra))
    holder: dict = {}

    def runner(job, stream) -> RunLog:
        jobs = holder["app"].state.jobs
        return run_until(ctx, job.character_id, jobs.run_options(job, stream, **extra))

    app = create_app(root, runner=runner)
    holder["app"] = app
    print(f"캐릭터 {cid}: http://127.0.0.1:{args.port}/")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
