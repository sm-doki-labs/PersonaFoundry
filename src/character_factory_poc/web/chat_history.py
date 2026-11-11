"""Durable chat snapshots, independent of prompt/model requests (local POSIX store)."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import stat
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from character_factory_poc.web.errors import WebError
from character_factory_poc.web.reads import character_dir

MAX_BYTES = 2 * 1024 * 1024
SID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")


class SavedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Literal["user", "assistant"]
    # Archiving must retain legacy text that exceeds the model input limit.
    # The request and whole JSON record still have the strict 2 MiB bound.
    content: str = Field(max_length=1024 * 1024)
    ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    rejected: int | None = Field(default=None, ge=0, le=100000)
    reasons: list[Annotated[str, Field(max_length=1000)]] | None = Field(
        default=None, max_length=100
    )
    model: str | None = Field(default=None, max_length=256)
    error: str | None = Field(default=None, max_length=2000)
    stopped: bool | None = None


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    revision: int = Field(ge=0)
    messages: list[SavedMessage] = Field(max_length=2000)


def session_name(sid):
    if not SID.fullmatch(sid):
        raise WebError(400, "대화 주소를 확인해 주세요.")
    return sid + ".json"


@contextmanager
def history_dir(root, cid):
    folder = character_dir(root, cid)
    fd = None
    try:
        # Use directory descriptors and O_NOFOLLOW for every child; symlinks never
        # redirect snapshots, temporary files, or reads outside this character.
        parent = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                os.mkdir("chat-history", mode=0o700, dir_fd=parent)
            except FileExistsError:
                pass
            fd = os.open(
                "chat-history", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            os.fsync(parent)
        finally:
            os.close(parent)
        # flock covers separate requests, app instances and worker processes.
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise WebError(400, "대화 저장 경로를 확인해 주세요.") from exc
        raise WebError(503, "대화 기록을 저장하거나 읽지 못했어요. 다시 시도해 주세요.") from exc
    finally:
        if fd is not None:
            os.close(fd)


def read_session(fd, sid):
    name = session_name(sid)
    try:
        file = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    except FileNotFoundError:
        return None
    with os.fdopen(file, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise WebError(400, "대화 저장 파일을 확인해 주세요.")
        raw = stream.read(MAX_BYTES + 1)
    try:
        if len(raw) > MAX_BYTES:
            raise ValueError("large record")
        data = json.loads(raw)
        Snapshot.model_validate({"revision": data["revision"], "messages": data["messages"]})
        if (
            data["id"] != sid
            or data["messageCount"] != len(data["messages"])
            or not all(isinstance(data[k], str) for k in ("title", "createdAt", "updatedAt"))
        ):
            raise ValueError("invalid record")
        return data
    except (ValueError, KeyError, TypeError) as exc:
        raise WebError(503, "저장된 대화를 읽지 못했어요. 원본 파일은 보존했어요.") from exc


def summary(data):
    return {
        k: data[k] for k in ("id", "revision", "title", "createdAt", "updatedAt", "messageCount")
    }


def write_session(root, cid, sid, snapshot):
    name = session_name(sid)
    messages = [m.model_dump(exclude_none=True) for m in snapshot.messages]
    with history_dir(root, cid) as fd:
        previous = read_session(fd, sid)
        revision = previous["revision"] if previous else 0
        # Retry after a lost acknowledgement is safe, including creation.
        if previous and previous["messages"] == messages:
            return previous
        if revision != snapshot.revision:
            raise WebError(409, "다른 탭에서 대화가 바뀌었어요. 별도 대화로 저장해 주세요.")
        stamp = datetime.now(UTC).isoformat()
        data = dict(
            id=sid,
            revision=revision + 1,
            messages=messages,
            title=next((m["content"][:60] for m in messages if m["content"].strip()), "새 대화"),
            createdAt=previous["createdAt"] if previous else stamp,
            updatedAt=stamp,
            messageCount=len(messages),
        )
        raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise WebError(413, "대화 기록이 너무 커요. 새 대화로 나누어 주세요.")
        temp = "." + str(uuid4()) + ".tmp"
        try:
            file = os.open(
                temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
            )
            with os.fdopen(file, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
        finally:
            try:
                os.unlink(temp, dir_fd=fd)
            except FileNotFoundError:
                pass
        return data


def install_chat_history_routes(app, root):
    path = "/api/characters/{cid}/chat/sessions"

    @app.get(path)
    def sessions(cid: str):
        with history_dir(root, cid) as fd:
            items = [
                summary(read_session(fd, name[:-5]))
                for name in os.listdir(fd)
                if name.endswith(".json") and SID.fullmatch(name[:-5])
            ]
        return {"sessions": sorted(items, key=lambda x: (x["updatedAt"], x["id"]), reverse=True)}

    @app.get(path + "/{sid}")
    def session(cid: str, sid: str):
        session_name(sid)
        with history_dir(root, cid) as fd:
            data = read_session(fd, sid)
        if data is None:
            raise WebError(404, "저장된 대화를 찾을 수 없어요.")
        return data

    @app.put(path + "/{sid}")
    async def save(cid: str, sid: str, request: Request):
        session_name(sid)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise WebError(413, "대화 기록이 너무 커요. 새 대화로 나누어 주세요.")
        try:
            snapshot = Snapshot.model_validate_json(raw)
        except ValidationError as exc:
            raise WebError(422, "저장할 대화의 내용과 크기를 확인해 주세요.") from exc
        return await run_in_threadpool(write_session, root, cid, sid, snapshot)
