from pathlib import Path

import pytest

from character_factory_poc.common.store import read_json
from character_factory_poc.stages.export.doki_app.chat_svc import build_tree
from character_factory_poc.stages.export.export import load_package
from character_factory_poc.stages.s11_release.package import build_package
from tests.support.export_flow import write_json
from tests.test_twin_export import _approved


@pytest.mark.parametrize("mode", ["BIND_EXISTING", "TRAIN"])
def test_each_bundle_pins_the_approved_named_route(tmp_path: Path, mode: str):
    ctx, cid, folder, _ = _approved(tmp_path, mode)
    if mode == "TRAIN":
        run = read_json(folder / "training-run.json")
        run["appliedConfig"]["servingRoute"] = "fake-trained"
        write_json(folder / "training-run.json", run)
    build_package(ctx, cid)
    package, directory = load_package(ctx, cid)
    tree = build_tree(package, directory)
    configs = [value for path, value in tree.files.items() if path.startswith("models/")]
    (config,) = configs
    assert config["servingRoute"] == ("test-route" if mode == "BIND_EXISTING" else "fake-trained")
    assert config["model"] == ("synthetic-adapter" if mode == "BIND_EXISTING" else "fake-trained")
    assert config["baseUrl"] is None
    assert config["apiKeyEnv"] == (
        "SYNTHETIC_PROXY_KEY" if mode == "BIND_EXISTING" else "TWIN_SERVING_API_KEY"
    )
    bundles = [v for path, v in tree.files.items() if path.startswith("split_prompt_bundles/")]
    assert bundles and all(
        b["dialogue"]["modelConfigRevision"] == config["configVersion"] for b in bundles
    )
