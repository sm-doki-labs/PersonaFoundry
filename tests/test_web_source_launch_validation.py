"""Reject unusable SOURCE judge settings before enqueueing any paid work."""

import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from character_factory_poc.web.app import create_app
from tests.test_source_intake import META, put, start

TEXT = '[providers.text]\nadapter="vertex_openai"\nmodel="google/synthetic"\n'
REAL_JUDGE = '[providers.judge]\nadapter="openai_compat"\nmodel="other/synthetic"\n'


@pytest.mark.parametrize(
    "judge", ["", '[providers.judge]\nadapter="fake"\n', '[providers.judge]\nmodel="synthetic"\n']
)
@pytest.mark.parametrize("auto", [True, False])
@pytest.mark.parametrize("adapter", ["vertex_openai", "openai_compat"])
def test_missing_or_fake_judge_blocks_source_before_submit(tmp_path, judge, auto, adapter):
    # The web launch must use its own config, not the default CLI config.
    (tmp_path / "factory.toml").write_text(TEXT + REAL_JUDGE)
    web_config = tmp_path / "factory-web.toml"
    text = TEXT.replace('adapter="vertex_openai"', f'adapter="{adapter}"')
    web_config.write_text(text + judge)
    app = create_app(tmp_path, config_path=web_config)
    submitted = Mock(return_value={"jobId": "should-not-start"})
    app.state.jobs.submit = submitted
    with TestClient(app) as client:
        draft = client.post(
            "/api/sources/drafts",
            json={"displayName": "합성인물", "subjectKind": "PRIVATE_PERSON", "autoReview": auto},
        )
        url = "/api/sources/" + draft.json()["characterId"]
        assert client.post(put(client, url) + "/complete", json=META).is_success
        folder = tmp_path / "runs/characters" / url.rsplit("/", 1)[-1]
        before = (folder / "s0-source/intake.json").read_bytes()
        result = client.post(url + "/finalize")
        assert result.status_code == 503, result.text
        assert result.json()["detail"] == (
            "생성 모델은 연결돼 있지만 검토 모델이 준비되지 않았어요. "
            "운영 설정에서 검토 모델을 연결한 뒤 다시 시작해 주세요. "
            "아직 제작을 시작하지 않았어요."
        )
        submitted.assert_not_called()
        assert not (folder / "source-pack.json").exists()
        assert not (folder / "s0-source/sp1").exists()
        assert (folder / "s0-source/intake.json").read_bytes() == before
        # Fixing configuration allows retry of the same draft, without reupload.
        web_config.write_text(text + REAL_JUDGE)
        assert client.post(url + "/finalize").status_code == 200
        submitted.assert_called_once()


@pytest.mark.parametrize("config", ["", '[providers.text]\nadapter="fake"\n', TEXT + REAL_JUDGE])
def test_synthetic_and_real_paired_providers_can_launch(tmp_path, config):
    (tmp_path / "factory.toml").write_text(config)
    app = create_app(tmp_path)
    submitted = Mock(return_value={"jobId": "synthetic-job"})
    app.state.jobs.submit = submitted
    with TestClient(app) as client:
        url = start(client)
        assert client.post(put(client, url) + "/complete", json=META).is_success
        assert client.post(url + "/finalize").status_code == 200
        submitted.assert_called_once()
        folder = tmp_path / "runs/characters" / url.rsplit("/", 1)[-1]
        assert (
            json.loads((folder / "s0-source/intake.json").read_text())["jobId"] == "synthetic-job"
        )
