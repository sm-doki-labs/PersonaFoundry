"""Versioned shape-only generation, with immutable resume identities."""

import inspect
from dataclasses import asdict
from pathlib import Path

from character_factory_poc.common.canonical import sha256_file, sha256_text
from character_factory_poc.common.schema import dump
from character_factory_poc.common.store import read_json, write_once_json
from character_factory_poc.pipeline.agent import AgentSpec, load_role_prompt, run_agent
from character_factory_poc.stages.s3_plan.choice_design import body_hash


def step_fingerprint(ctx, *, role, contract, inputs, judge=False):
    from character_factory_poc.common.text_deck import task_for_role

    binding = (
        ctx.config.task_provider(task_for_role(role))
        if ctx.text_deck_enabled
        else ctx.config.provider("judge" if judge else "text")
    )
    # ProviderConfig stores environment variable names, never resolved key values.
    return body_hash(
        dict(
            inputs=inputs,
            role=load_role_prompt(role),
            schema=contract.model_json_schema(),
            contractCode=sha256_text(inspect.getsource(inspect.getmodule(contract))),
            runnerCode=sha256_file(Path(__file__)),
            provider=asdict(binding),
            agent=ctx.config.agent if not judge and not ctx.text_deck_enabled else {},
            textBinding=ctx.config.text_binding(task_for_role(role))
            if ctx.text_deck_enabled
            else None,
        )
    )


def run_typed_step(*, ctx, cid, folder, role, contract, stage, inputs, judge=False, budget=None):
    if not ctx.execute:
        raise ValueError("formation requires execute=True")
    folder = Path(folder)
    identity = step_fingerprint(ctx, role=role, contract=contract, inputs=inputs, judge=judge)
    marker = folder / "step.json"
    if marker.exists() and read_json(marker)["fingerprint"] != identity:
        raise ValueError("stage fingerprint changed; create a new revision")
    write_once_json(marker, {"fingerprint": identity})
    if (folder / "failure.json").exists():
        raise ValueError("previous step failure; create a new revision")
    output = folder / "result.json"
    if output.exists():
        saved = read_json(folder / "result-meta.json")
        if saved["sha256"] != sha256_file(output):
            raise ValueError("saved result hash mismatch")
        return contract.model_validate(read_json(output))
    budget = budget or ctx.budget()
    try:
        if ctx.text_deck_enabled:
            model = ctx.role_model(cid, budget, role)
        else:
            model = ctx.judge_model(cid, budget) if judge else ctx.text_model(cid, budget)
        backend = None if judge else ctx.agent_backend(cid, budget, stage)
        actual = backend or model
        write_once_json(
            folder / "model-binding.json",
            dict(
                model=actual.model,
                provider=getattr(getattr(actual, "inner", actual), "name", "unknown"),
                configuredProvider="judge" if judge else "text",
                stage=stage,
                textBinding=getattr(model, "binding", None),
            ),
        )
        result = run_agent(
            AgentSpec(
                role,
                contract.model_fields.get("schemaVersion").default
                if "schemaVersion" in contract.model_fields
                else _contract_name(contract),
                stage,
                max_format_retries=2,
                max_check_retries=0,
            ),
            folder / "workspace",
            {"payload": inputs, "outputSchema": contract.model_json_schema()},
            [],
            model,
            ref=f"{cid}/{folder.parent.name}/{stage}",
            backend=backend,
        )
        if not result.ok:
            raise ValueError("format failure: " + "; ".join(result.problems))
        write_once_json(output, dump(result.output))
        write_once_json(folder / "result-meta.json", {"sha256": sha256_file(output)})
        return result.output
    except Exception as exc:
        write_once_json(folder / "failure.json", {"error": str(exc)})
        raise


def _contract_name(cls):
    from character_factory_poc.common.schema import contract, known_contracts

    return next(name for name in known_contracts() if contract(name) is cls)
