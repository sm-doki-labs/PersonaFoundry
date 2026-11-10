"""완성한 캐릭터와 대화하는 화면의 읽기·발화 경로."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated, Literal

from fastapi import Body
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from character_factory_poc.common import clip_pick
from character_factory_poc.common import demo_chat as demo
from character_factory_poc.common.config import load_config
from character_factory_poc.common.errors import (
    BudgetExceeded,
    ProviderRequestError,
    ProviderTransportError,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.graph import SOURCE
from character_factory_poc.pipeline.origin import read_origin
from character_factory_poc.providers.base import Message
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.reads import character_dir


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16000)
    ]


class Conversation(BaseModel):
    messages: list[Turn] = Field(min_length=1, max_length=100)
    via: Literal["studio", "vertex"] = "studio"


class ClipTurn(BaseModel):
    userMessage: Annotated[str, StringConstraints(strip_whitespace=True, max_length=16000)]
    replyText: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=16000)
    ]
    recent: list[str] = Field(default_factory=list, max_length=100)
    chapter: str = "ch1"


def can_make_video(folder, origin: str) -> bool:
    """영상 만들기를 시작할 수 있는 캐릭터인가(QA v5 D-04).

    모티브 영상은 승인한 출처 묶음의 사진이 있어야 만든다(영상 시작 API와 같은 조건).
    오리지널은 이 조건이 없다.
    """
    if origin != SOURCE:
        return True
    gate = (reads.read_state(folder)[0].get("gates") or {}).get("G0") or {}
    if gate.get("status") != "APPROVED" or not gate.get("rev"):
        return False
    pack = reads.read_json_file(folder / "s0-source" / str(gate["rev"]) / "source-pack.json")
    return bool((pack or {}).get("photos"))


def install_demo_routes(app, root, conf):
    def folder_for(cid):
        try:
            return character_dir(root, cid)
        except WebError as exc:
            raise WebError(exc.status, "캐릭터를 찾을 수 없어요.") from exc

    def setup(cid):
        folder = folder_for(cid)
        intake = reads.read_json_file(folder / "s0-source/intake.json")
        name = reads.display_name(reads._persona(folder), intake)
        return demo.Scene.read(folder, name=name), Context(
            config=load_config(root, conf.config_path), execute=True
        )

    @app.get("/api/chat/characters")
    def chat_characters():
        return reads.chat_characters(root)

    @app.get("/api/characters/{cid}/chat/meta")
    def meta(cid: str):
        scene, ctx = setup(cid)
        active = app.state.jobs.active_for(cid) or {}
        intake = reads.read_json_file(scene.folder / "s0-source/intake.json")
        stages = reads.read_state(scene.folder)[0].get("stages", {}).values()
        draft = reads.is_draft(intake, stages)
        readiness = scene.readiness(running=active.get("status") == "running", draft=draft)
        cfg = ctx.config.providers.get("demo_chat", demo.DEFAULT)
        origin = read_origin(scene.folder)
        return dict(
            characterId=cid,
            name=scene.name,
            origin=origin,
            canMakeVideo=can_make_video(scene.folder, origin),
            **readiness,
            promptRev=scene.prompt.name if scene.prompt else None,
            chapterRev=scene.chapter.name if scene.chapter else None,
            model=dict(via="studio", model=cfg.model),
            temperature=ctx.config.demo_chat_temperature(True),
            scenarios=demo.scenarios(scene.folder),
            samples=scene.samples(),
        )

    def reply(cid, chat, deadline):
        scene, ctx = setup(cid)
        try:
            system = scene.compose()
            cfg = demo.provider(ctx, chat.via, conf.server_mode)
            model = demo.talk_model(ctx, cid, cfg)
            messages = [
                Message("system", system),
                *(Message(m.role, m.content) for m in chat.messages),
            ]
            return demo.respond(model, messages, ctx.config.demo_chat_temperature(True), deadline)
        except demo.NotReady as exc:
            raise WebError(409, str(exc)) from exc
        except PermissionError as exc:
            raise WebError(403, str(exc)) from exc
        except ValueError as exc:
            raise WebError(503, "대화 모델의 연결 설정과 인증 정보를 확인해 주세요.") from exc
        except BudgetExceeded as exc:
            raise WebError(429, "이번 대화에 쓸 수 있는 분량을 모두 사용했어요.") from exc
        except ProviderTransportError as exc:
            if exc.kind == "timeout":
                raise TimeoutError from exc
            raise WebError(
                503, "지금은 대화 모델에 연결하기 어려워요. 잠시 후 다시 시도해 주세요."
            ) from exc
        except ProviderRequestError as exc:
            raise WebError(502, "대화 요청을 보내지 못했어요. 모델 설정을 확인해 주세요.") from exc
        except RuntimeError as exc:
            raise WebError(502, "답변을 만들지 못했어요. 잠시 후 다시 시도해 주세요.") from exc

    @app.post("/api/characters/{cid}/chat")
    async def chat(cid: str, body: Annotated[object, Body()] = None):
        try:
            conversation = Conversation.model_validate(body)
        except ValidationError as exc:
            raise WebError(422, "보낼 메시지와 대화 방식을 확인해 주세요.") from exc
        if conversation.messages[-1].role != "user":
            raise WebError(422, "캐릭터에게 보낼 말을 마지막에 적어 주세요.")
        try:
            deadline = time.monotonic() + demo.TIMEOUT
            return await asyncio.wait_for(
                asyncio.to_thread(reply, cid, conversation, deadline), demo.TIMEOUT
            )
        except TimeoutError as exc:
            raise WebError(504, "답변이 늦어지고 있어요. 잠시 후 다시 시도해 주세요.") from exc

    @app.get("/api/characters/{cid}/chat/clips")
    def clips(cid: str, chapter: str = "ch1"):
        return demo.chat_clips(folder_for(cid), chapter)

    @app.post("/api/characters/{cid}/chat/clip")
    def clip(cid: str, body: Annotated[object, Body()] = None):
        try:
            turn = ClipTurn.model_validate(body)
        except ValidationError as exc:
            raise WebError(422, "방금 나눈 말과 재생한 영상을 확인해 주세요.") from exc
        pool = demo.chat_clips(folder_for(cid), turn.chapter, for_picker=True)["emotion"]
        ctx = Context(config=load_config(root, conf.config_path), execute=True)
        chosen = clip_pick.pick(ctx, cid, pool, turn.userMessage, turn.replyText, turn.recent)
        if not chosen:
            return dict(clip=None, kind="none", mood=None)
        return dict(
            clip={k: chosen[k] for k in ("clipKey", "url", "mood", "title")},
            kind="emotion",
            mood=chosen["mood"],
        )
