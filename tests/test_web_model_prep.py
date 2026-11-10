"""모델 만들기 탭의 서버 쪽(QA v5 B-F07·B-F22·C-08).

학습된 모델 연결은 화면에서 연결 파일 내용을 올려 기록한다. 생성·학습·네트워크 호출은 없다(서빙
주소 종류는 미리 확인하지 않는다). 모델 만들기 요약은 관문 G8과 같은 조건·채택 결과를 읽는다.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from character_factory_poc.common.store import write_once_json
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import BIND_EXISTING, TRAIN
from character_factory_poc.pipeline.orchestrator import _training_ready
from character_factory_poc.pipeline.origin import write_model_mode
from character_factory_poc.web import create_app
from character_factory_poc.web.model_path import eval_view, material_view, plain_note
from tests.test_source_s0 import _twin

CID = "cf-20261111-bind"
BINDING = {
    "schemaVersion": "model-binding-import-v1",
    "provider": "ENDPOINT",
    "ref": "https://serving.example/mom-v3",
    "revision": "v3",
    "baseModel": "synthetic/base",
    "baseModelRevision": "r1",
    "servingRoute": "mom-v3",
    "provenance": {
        "trainedBy": "테스트",
        "trainedAt": "2026-11-01",
        "dataNote": "합성 대화",
        "usageBasis": "테스트용",
    },
}


def _char(tmp_path, mode=BIND_EXISTING):
    ctx = Context.load(tmp_path, execute=False)
    cid = _twin(ctx, CID)
    write_model_mode(ctx.character_dir(cid), mode)
    return ctx, cid


def _post(client, cid, body):
    return client.post(f"/api/characters/{cid}/model-binding", json=body)


def test_screen_connects_a_trained_model_and_the_newest_one_is_used(tmp_path):
    ctx, cid = _char(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        assert client.get(f"/api/characters/{cid}").json()["modelPath"]["binding"] is None
        res = _post(client, cid, BINDING)
        assert res.status_code == 201, res.text
        first = res.json()["binding"]
        assert first["kindLabel"] == "서빙 주소" and first["ref"] == BINDING["ref"]
        assert first["check"] == "SKIPPED" and first["checkLabel"].endswith("(미리 확인하지 않음)")
        # 평가 전이면 다른 모델로 다시 연결할 수 있고, 화면과 평가는 새 연결을 본다.
        assert _post(client, cid, {**BINDING, "revision": "v4"}).status_code == 201
        path = client.get(f"/api/characters/{cid}").json()["modelPath"]
    assert path["mode"] == BIND_EXISTING
    assert path["binding"]["rev"] == "mb2" and path["binding"]["revision"] == "v4"
    assert _training_ready(ctx, cid)


def test_bad_connection_file_is_explained_in_plain_korean_and_writes_nothing(tmp_path):
    ctx, cid = _char(tmp_path)
    missing = {k: v for k, v in BINDING.items() if k != "servingRoute"}
    missing["provenance"] = {k: v for k, v in BINDING["provenance"].items() if k != "usageBasis"}
    hf = {**BINDING, "provider": "HF_ADAPTER", "ref": "lab/adapter", "revision": "main"}
    with TestClient(create_app(tmp_path)) as client:
        res = _post(client, cid, missing)
        assert res.status_code == 400
        detail = res.json()["detail"]
        assert "서빙 경로" in detail and "사용 근거" in detail
        assert "Field required" not in detail and "servingRoute" not in detail
        res = _post(client, cid, hf)
        assert res.status_code == 400 and "40자리 커밋" in res.json()["detail"]
        assert _post(client, cid, [BINDING]).status_code == 400
    assert not (ctx.character_dir(cid) / "model-prep").exists()
    assert not _training_ready(ctx, cid)


def test_connect_only_in_bind_mode_and_before_the_evaluation_review(tmp_path):
    ctx, cid = _char(tmp_path, TRAIN)
    with TestClient(create_app(tmp_path)) as client:
        res = _post(client, cid, BINDING)
        assert res.status_code == 409 and "학습된 모델 연결" in res.json()["detail"]
        write_model_mode(ctx.character_dir(cid), BIND_EXISTING)
        ctx.state(cid).set_gate("G8", "AWAITING_HUMAN", "ev1", None)
        res = _post(client, cid, BINDING)
        assert res.status_code == 409 and "평가 검토" in res.json()["detail"]
    assert not (ctx.character_dir(cid) / "model-prep").exists()


def _approved_g8(char, selection):
    write_once_json(
        char / "s10-eval/ev1/prereg.json",
        {
            "arms": [
                {"armId": "LONG_BASE", "model": "text-model"},
                {"armId": "SHORT_GEMMA_SFT", "model": "s10-train/tr1/gemma_qlora/run.json"},
                {"armId": "SHORT_GEMINI_SFT", "model": "UNBOUND:vertex_gemini"},
            ]
        },
    )
    write_once_json(char / "gates/G8-ev1.json", {"decision": "SELECT", "selections": [selection]})
    return {
        "stages": {"s10": {"status": "APPROVED", "currentRev": "ev1"}},
        "gates": {"G8": {"status": "APPROVED", "rev": "ev1", "recordRef": "gates/G8-ev1.json"}},
    }


def test_model_tab_counts_the_same_conditions_and_adoption_as_g8(tmp_path):
    view = eval_view(tmp_path, _approved_g8(tmp_path, "LONG_BASE"))
    assert [a["label"] for a in view["arms"]] == [
        "긴 프롬프트",
        "Gemma 학습 모델",
        "Gemini 학습 모델",
    ]
    assert [a["bound"] for a in view["arms"]] == [True, True, False]
    assert view["adopted"]["label"] == "긴 프롬프트"
    other = tmp_path / "b"
    view = eval_view(other, _approved_g8(other, "s10-train/tr1/gemma_qlora/run.json"))
    assert view["adopted"]["label"] == "Gemma 학습 모델"


def test_motif_material_and_old_warnings_read_without_internal_codes():
    dataset = {
        "materials": {"SOURCE": 3},
        "clusters": [{"materialsPlanned": ["SOURCE"]}],
        "sampleStatus": "APPROVED",
    }
    view = material_view(dataset)
    assert [u["label"] for u in view["used"]] == ["원문 대화"]
    old = (
        "학습 예시가 1개로 50개 미만이다. 원문을 외워 되풀이할 위험이 커서 PROMPT_ONLY를 권장한다."
    )
    assert "PROMPT_ONLY" not in plain_note(old) and plain_note(old).endswith("권해요.")
    assert (
        json.dumps(view, ensure_ascii=False).count("SOURCE") == 2
    )  # 값(kind)은 남고 이름만 바뀐다
