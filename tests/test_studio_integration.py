"""The existing visual studio must share the actual factory API origin."""

from pathlib import Path

from fastapi.testclient import TestClient

from character_factory_poc.web.app import create_app


def configure(root: Path, studio: Path):
    (root / "factory.toml").write_text(
        "[text_pipeline]\nenabled=true\n"
        "[web]\nstudio_dir=" + repr(str(studio)).replace("'", '"') + "\n",
        encoding="utf-8",
    )


def test_configured_studio_and_real_model_deck_share_one_server(tmp_path):
    studio = tmp_path / "visual"
    studio.mkdir()
    (studio / "d-ops.html").write_text("<button data-text-pipeline-open>텍스트 공정</button>")
    configure(tmp_path, studio)
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/studio/d-ops.html")
        assert response.status_code == 200
        assert "data-text-pipeline-open" in response.text
        assert response.headers["cache-control"] == "no-store"
        data = client.get("/api/text-pipeline")
        assert data.status_code == 200
        assert data.json()["route"] == "opencodex"
        assert data.json()["tasks"][0]["model"] == "gpt-6.1-sol"


def test_studio_does_not_serve_worker_logs_or_arbitrary_project_files(tmp_path):
    studio = tmp_path / "visual"
    (studio / "plans").mkdir(parents=True)
    (studio / "plans" / "worker-log.json").write_text('{"private":"worker output"}')
    (studio / "shared").mkdir()
    (studio / "shared" / "text-pipeline.js").write_text("window.FactoryTextPipeline = {};")
    (studio / "previews").mkdir()
    (studio / "previews" / "thumb.png").write_bytes(b"preview")
    configure(tmp_path, studio)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/studio/previews/thumb.png").status_code == 200
        assert client.get("/studio/plans/worker-log.json").status_code == 404
        assert client.get("/studio/shared/text-pipeline.js").status_code == 200


def test_unconfigured_factory_opens_current_factory(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/").status_code == 200
        assert client.get("/studio/factory.html").status_code == 200


def test_runtime_queue_override_still_reads_updated_factory_settings(tmp_path):
    studio = tmp_path / "visual"
    studio.mkdir()
    configure(tmp_path, studio)
    queue = tmp_path / "preview-jobs"
    app = create_app(tmp_path, jobs_dir=queue)
    assert app.state.settings.jobs_path == queue
    with TestClient(app) as client:
        assert client.get("/api/text-pipeline").json()["profile"] == "basic_test"
        config = tmp_path / "factory.toml"
        config.write_text(
            config.read_text().replace("enabled=true", 'enabled=true\nprofile="demo"')
        )
        body = client.get("/api/text-pipeline").json()
        assert body["profile"] == "demo"
        assert (
            next(t for t in body["tasks"] if t["id"] == "voice")["model"]
            == "google-antigravity/gemini-4-argon"
        )


def test_text_panel_opens_the_real_studio_character_when_configured(tmp_path):
    from character_factory_poc.pipeline.context import Context
    from character_factory_poc.stages.s3_plan.common import new_character

    studio = tmp_path / "visual"
    studio.mkdir()
    configure(tmp_path, studio)
    cid = new_character(Context.load(tmp_path, execute=False), "real-panel")
    with TestClient(create_app(tmp_path)) as client:
        response = client.get(f"/api/text-pipeline/characters/{cid}")
        assert response.status_code == 200
        assert response.json()["workshopUrl"] == f"/studio/factory.html#c/{cid}"
