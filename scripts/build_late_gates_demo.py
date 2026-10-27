"""브라우저 확인용 데모 공장: G7a·G7·G8(평가)·G8(학습 없이)·G9에서 각각 멈춘 캐릭터 다섯.

uv run python scripts/build_late_gates_demo.py work/<새 폴더>   (가짜 공급자, 네트워크 없음)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_REPO))

from fastapi.testclient import TestClient  # noqa: E402

from character_factory_poc.pipeline.orchestrator import RunOptions, run_until  # noqa: E402
from character_factory_poc.providers.fake import FakeTextModel  # noqa: E402
from character_factory_poc.stages.s3_plan.draft import new_character  # noqa: E402
from character_factory_poc.web import create_app  # noqa: E402
from tests.support.data_fakes import FakeWriterModel, write_sns  # noqa: E402
from tests.support.flow import make_ctx  # noqa: E402
from tests.support.synthetic import prompter_output  # noqa: E402
from tests.support.web_gates import PROBES, SEED, trait_sheet_for  # noqa: E402
from tests.test_offline_pipeline import (  # noqa: E402
    Judge,
    decide,
    eval_replies,
    factory_toml,
    gendered_variants,
    ranking_for,
)
from tests.test_scene_flow import backgrounds, poses, scenes  # noqa: E402

TARGETS = [
    ("g7a", "G7a", "female", False),
    ("g7", "G7", "male", False),
    ("g8-eval", "G8", "female", True),
    ("g8-prompt", "G8", "male", False),
    ("g9", "G9", "female", False),
]


def main(root: Path) -> None:
    root.mkdir(parents=True)
    write_sns(root / "sns.jsonl")
    ctx, agents = make_ctx(root, factory_toml(root))
    text = ctx._text
    text.add("PROBE", lambda req: "그럼 이렇게 하자. 내일 아침에 같이 보자.")
    text.add("EVAL", eval_replies())
    judge = FakeTextModel(model="anthropic/claude-opus-5-5")
    judge.add("JUDGE", Judge())
    ctx.use_models(text, judge)
    with TestClient(create_app(root)) as client:
        for slug, stop, gender, submit in TARGETS:
            cid = new_character(ctx, slug)
            agents.set("s3-variants", lambda req, c=cid, g=gender: gendered_variants(c, g))
            agents.set("s4a", backgrounds)
            agents.set("s4b-scene", scenes)
            agents.set("s4b-pose", poses)
            agents.set("s7", lambda req, c=cid: trait_sheet_for(ctx, c))
            agents.set("s8", lambda req: prompter_output())
            writer = FakeWriterModel()
            agents.set("s9s", writer.respond)
            agents.set("s9", writer.respond)
            opt = RunOptions(
                until="sx",
                ranking=ranking_for(gender),
                seed=SEED,
                voice_probes=list(PROBES),
                submit_training=submit,
            )
            for _ in range(30):
                log = run_until(ctx, cid, opt)
                if stop in log.waiting and all(g == stop for g in log.waiting):
                    break
                for gate in log.waiting:
                    if gate != stop:
                        decide(client, cid, gate, {})
            print(f"READY {stop} {cid}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
