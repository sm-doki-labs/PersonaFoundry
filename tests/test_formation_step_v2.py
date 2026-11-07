import pytest

from character_factory_poc.contracts.choice_design import SeedRequirementsDraft
from character_factory_poc.pipeline.formation_step import run_typed_step
from tests.support.flow import make_ctx


def test_step_resume_and_changed_fingerprint(tmp_path):
    ctx, agents = make_ctx(tmp_path)
    agents.set(
        "cv-requirements",
        lambda req: {
            "requirements": [
                dict(requirementId="r1", field="personality", quote="조용함", kind="fixed")
            ]
        },
    )
    folder = tmp_path / "step"
    kwargs = dict(
        ctx=ctx,
        cid="cf-x",
        folder=folder,
        role="seed_requirements",
        contract=SeedRequirementsDraft,
        stage="cv-requirements",
        inputs={"seed": "조용함"},
    )
    first = run_typed_step(**kwargs)
    assert run_typed_step(**kwargs) == first
    assert agents.calls == ["cv-requirements"]
    with pytest.raises(ValueError, match="fingerprint"):
        run_typed_step(**(kwargs | {"inputs": {"seed": "단호함"}}))
    assert len(agents.calls) == 1
