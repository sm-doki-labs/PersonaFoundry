"""학습된 모델 연결(QA v5 B-F07). 화면이 올린 연결 파일 내용을 CLI 연결과 같은 길로 기록한다.

생성·학습 호출은 없다. Hugging Face 어댑터면 연결 전에 저장소 주인·커밋·기반 모델만 확인한다.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Body, FastAPI

from character_factory_poc.common.config import load_config
from character_factory_poc.common.errors import FactoryError
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import BIND_EXISTING, SOURCE
from character_factory_poc.pipeline.origin import read_model_mode, read_origin
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError


def install_binding_routes(app: FastAPI, root, conf, jobs) -> None:
    @app.post("/api/characters/{character_id}/model-binding", status_code=201)
    def connect(character_id: str, body: Annotated[Any, Body()]) -> dict[str, Any]:
        from character_factory_poc.stages.model_prep.bind import import_binding_data
        from character_factory_poc.web.model_path import binding_view

        char_dir = reads.character_dir(root, character_id)
        if read_origin(char_dir) != SOURCE or read_model_mode(char_dir) != BIND_EXISTING:
            raise WebError(
                409, "이 캐릭터는 '학습된 모델 연결' 방식이 아니라서 모델을 연결할 수 없어요."
            )
        # 작업은 도는 동안 캐릭터 잠금을 쥐고 있다. 기다리게 하지 않고 바로 알린다.
        if jobs.active_for(character_id):
            raise WebError(409, "지금 도는 작업이 끝난 뒤에 연결해 주세요.")
        with jobs.locks.hold(character_id):
            state, error = reads.read_state(char_dir)
            if error:
                raise WebError(409, "진행 상태를 읽지 못해 연결을 기록하지 못했어요.")
            gates = state.get("gates") if isinstance(state.get("gates"), dict) else {}
            if (gates.get("G8") or {}).get("status") in {"AWAITING_HUMAN", "APPROVED"}:
                # 열린 G8은 지금 연결 기록을 근거로 열렸다. 바꾸려면 G8을 반려해 새 판으로 연다.
                raise WebError(
                    409, "평가 검토가 이미 열렸거나 끝나서 연결한 모델을 바꿀 수 없어요."
                )
            ctx = Context(config=load_config(root, conf.config_path), execute=False)
            try:
                import_binding_data(ctx, character_id, body)
            except FactoryError as exc:
                raise WebError(400, str(exc)) from exc
        jobs.publish_state(character_id, force=True)
        return {"characterId": character_id, "binding": binding_view(char_dir)}
