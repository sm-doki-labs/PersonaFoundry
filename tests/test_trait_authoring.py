import json

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.web import create_app
from tests.test_web_api import CID, make_root


@pytest.fixture
def authoring(tmp_path):
    root = make_root(tmp_path)
    state = root / "runs" / "characters" / CID / "state.json"
    body = json.loads(state.read_text())
    body["stages"]["s3"]["status"] = "PENDING"
    state.write_text(json.dumps(body))
    with TestClient(create_app(root)) as client:
        yield client, root


def save_body(client, selected=None, expected=None):
    catalog = client.get("/api/traits/catalog").json()
    return {
        "fields": {
            "personality": "다정하지만 말수가 적다",
            "age": 26,
            "gender": "female",
            "job": "책방 직원",
            "background": "혼자 산다",
            "notes": "제작자 원문",
        },
        "selectedIds": selected or [],
        "expectedSeedRev": expected,
        "catalogSha256": catalog["catalogSha256"],
    }


def test_recommendation_api_is_read_only_and_selection_is_optional(authoring):
    client, root = authoring
    result = client.post("/api/traits/recommend", json={"personality": "다정하고 무뚝뚝"})
    assert result.status_code == 200
    assert 1 <= len(result.json()["items"]) <= 5
    assert not list(root.rglob("sd*.json"))
    saved = client.post(f"/api/characters/{CID}/seed", json=save_body(client))
    assert saved.status_code == 200
    assert saved.json()["seed"]["selectedTraits"] == []
    assert saved.json()["seed"]["personality"] == "다정하지만 말수가 적다"
    assert client.get("/api/jobs").json()["jobs"] == []


def test_save_selected_traits_preserves_original_fields_and_new_revisions(authoring):
    client, root = authoring
    item = client.get("/api/traits/catalog").json()["items"][0]
    first = client.post(f"/api/characters/{CID}/seed", json=save_body(client, [item["traitId"]]))
    assert first.status_code == 200
    seed = first.json()["seed"]
    assert seed["selectedTraits"] == [item]
    assert seed["notes"] == "제작자 원문"
    assert seed["job"] == "책방 직원" and seed["age"] == 26
    path = root / "runs" / "characters" / CID / "s3-plan/seeds/sd1.json"
    original = path.read_bytes()
    second = client.post(f"/api/characters/{CID}/seed", json=save_body(client, expected="sd1"))
    assert second.status_code == 200
    assert second.json()["seed"]["seedRev"] == "sd2"
    assert path.read_bytes() == original
    assert client.get(f"/api/characters/{CID}/seed").json()["seed"]["seedRev"] == "sd2"


def test_stale_seed_and_catalog_are_rejected_without_writing(authoring):
    client, root = authoring
    body = save_body(client)
    assert client.post(f"/api/characters/{CID}/seed", json=body).status_code == 200
    assert client.post(f"/api/characters/{CID}/seed", json=body).status_code == 409
    body["expectedSeedRev"] = "sd1"
    body["catalogSha256"] = "b" * 64
    body["selectedIds"] = ["P01-T1"]
    assert client.post(f"/api/characters/{CID}/seed", json=body).status_code == 409
    assert len(list(root.rglob("sd*.json"))) == 1


@pytest.mark.parametrize("status", ["RUNNING", "APPROVED", "AWAITING_HUMAN"])
def test_pending_or_approved_plan_cannot_be_silently_invalidated(authoring, status):
    client, root = authoring
    path = root / "runs" / "characters" / CID / "state.json"
    body = json.loads(path.read_text())
    body["stages"]["s3"]["status"] = status
    path.write_text(json.dumps(body))
    assert client.get(f"/api/characters/{CID}/seed").json()["editable"] is False
    saved = client.post(f"/api/characters/{CID}/seed", json=save_body(client))
    assert saved.status_code == 409
    assert not list(root.rglob("sd*.json"))


@pytest.mark.parametrize("ids", [["unknown"], ["P01-T1", "P01-T1"]])
def test_invalid_selected_ids_do_not_write_a_seed(authoring, ids):
    client, root = authoring
    response = client.post(f"/api/characters/{CID}/seed", json=save_body(client, ids))
    assert response.status_code == 400
    assert not list(root.rglob("sd*.json"))


def test_client_cannot_supply_a_forged_behavior(authoring):
    client, _ = authoring
    body = save_body(client)
    body["fields"]["selectedTraits"] = [{"behavior": "위조"}]
    assert client.post(f"/api/characters/{CID}/seed", json=body).status_code == 422


def test_corrupt_state_blocks_seed_writes(authoring):
    client, root = authoring
    state = root / "runs" / "characters" / CID / "state.json"
    state.write_text("not-json")
    response = client.post(f"/api/characters/{CID}/seed", json=save_body(client))
    assert response.status_code == 409
    assert not list(root.rglob("sd*.json"))


def test_concurrent_seed_writers_only_accept_one_expected_revision(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from character_factory_poc.stages.s3_plan.seed import SeedConflict, write_seed
    from tests.support.flow import make_ctx, through_s2

    ctx, _ = make_ctx(tmp_path)
    cid = through_s2(ctx)

    def save():
        try:
            return write_seed(
                ctx, cid, dict(personality="다정함", gender="female"), expected_seed_rev=None
            ).seedRev
        except SeedConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save(), range(2)))
    assert sorted(results) == ["conflict", "sd1"]


@pytest.mark.parametrize("status", ["RUNNING", "AWAITING_HUMAN", "APPROVED"])
def test_cli_uses_the_same_protection_for_started_plans(tmp_path, status):
    from types import SimpleNamespace

    from character_factory_poc.cli import cmd_plan_seed
    from character_factory_poc.stages.s3_plan.seed import SeedConflict, load_latest_seed
    from tests.test_choice_design_flow import setup_choices

    ctx, _, cid = setup_choices(tmp_path)
    state = ctx.state(cid)
    state.transition("s3", "RUNNING", rev="pr1")
    if status != "RUNNING":
        state.transition("s3", status, rev="pr1")
    with pytest.raises(SeedConflict):
        cmd_plan_seed(
            SimpleNamespace(
                root=str(tmp_path),
                character_id=cid,
                file=None,
                personality="새 설정",
                trait=["P01-T1"],
            )
        )
    assert load_latest_seed(ctx, cid).seedRev == "sd1"


def test_no_selection_save_does_not_require_the_recommendation_catalog(authoring, monkeypatch):
    import character_factory_poc.stages.s3_plan.trait_recommendations as traits

    client, _ = authoring

    def unavailable(*args, **kwargs):
        raise OSError("catalog temporarily unavailable")

    monkeypatch.setattr(traits, "load_catalog", unavailable)
    response = client.post(
        f"/api/characters/{CID}/seed",
        json={
            "fields": {"personality": "다정하다", "gender": "female"},
            "selectedIds": [],
            "catalogSha256": None,
        },
    )
    assert response.status_code == 200
    assert response.json()["seed"]["selectedTraits"] == []
