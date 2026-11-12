"""모티브 출처 초안과 원본 업로드. 확정한 묶음만 S0 작업에 넘긴다."""

from __future__ import annotations

import fcntl
import hashlib
import json
import re
import shutil
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from fastapi.routing import APIRoute
from pydantic import Field, StringConstraints, ValidationError, model_validator

from character_factory_poc.common.config import load_config
from character_factory_poc.common.source_store import (
    MAX_BYTES,
    LocalSourceStore,
    S3SourceStore,
    SourcePathError,
    SourceStore,
    atomic_write,
    inside,
    local_copy,
)
from character_factory_poc.contracts.common import Strict
from character_factory_poc.contracts.source import (
    FactSheet,
    SourcePack,
    SourceSubject,
    SourceText,
    SubjectKind,
    UsageBasis,
    default_register,
)
from character_factory_poc.pipeline.context import Context
from character_factory_poc.pipeline.origin import (
    SOURCE,
    VIDEO_STAGES,
    VideoTier,
    read_auto_review,
    read_origin,
    read_signature,
    read_video_tier,
    write_model_mode,
    write_origin,
    write_signature,
    write_video_tier,
)
from character_factory_poc.stages.s0_source import parse
from character_factory_poc.stages.s3_plan.common import new_character
from character_factory_poc.stages.s6_actions.call_loop import VideoScene
from character_factory_poc.stages.sv_voice.run import (
    normalize_reference_id,
    read_voice,
    write_voice,
)
from character_factory_poc.web import reads
from character_factory_poc.web.errors import WebError
from character_factory_poc.web.launch_validation import validate_source_launch
from character_factory_poc.web.reference_images import (
    ReferenceImageSettings,
    install_reference_routes,
)

EXTENSIONS = {".txt", ".srt", ".vtt", ".csv", ".json"}
FIELDS = ("textId", "kind", "register", "subjectSpeaker", "userSpeaker", "date", "sourceUrl")


class KnownFacts(Strict):
    """S3 기획이 인물 소개 첫 줄로 쓰는 기본 정보(source-pack-v1 knownFacts)."""

    age: str = Field(default="", max_length=20)
    gender: str = Field(default="", max_length=20)
    job: str = Field(default="", max_length=60)
    background: str = Field(default="", max_length=400)


class SignaturePose(Strict):
    """유저가 정하는 시그니처 포즈(D-0165). 모든 영상 등급에 한 편씩 들어간다."""

    # 앞뒤 공백을 뗀 뒤 길이를 본다(공백만 적은 이름·동작은 받지 않는다).
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    motion: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=400)]
    useWhen: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = ""
    template: Literal["custom", "camera_click"] = "custom"
    middleFramePath: str | None = Field(default=None, max_length=500)
    middleFrameAtS: float = Field(default=2.0, gt=0, lt=4.5)


class Settings(Strict):
    videoTier: VideoTier
    videoScene: VideoScene | None = None
    signaturePose: SignaturePose | None = None


def _signature(pose: SignaturePose) -> dict:
    data = pose.model_dump(exclude_defaults=True)
    data.setdefault("useWhen", "")
    return {k: v.strip() if isinstance(v, str) else v for k, v in data.items()}


class Draft(Strict):
    referenceImage: ReferenceImageSettings | None = None
    videoScene: VideoScene | None = None
    videoTier: VideoTier = "none"
    signaturePose: SignaturePose | None = None
    displayName: str = Field(min_length=1)
    subjectKind: SubjectKind
    usageBasis: UsageBasis = Field(default_factory=UsageBasis)
    modelMode: Literal["PROMPT_ONLY", "BIND_EXISTING", "TRAIN"] = "PROMPT_ONLY"
    autoReview: bool = True
    chapterTemplate: Literal["FAN_CALL", "FAMILY_CALL", "FRIEND_CHAT", "INTERVIEW"] | None = None
    knownFacts: KnownFacts = Field(default_factory=KnownFacts)
    # 사용자가 준 사실(한 줄에 하나). S8 [FACTS]에 글자 그대로 들어간다.
    factSheet: FactSheet = Field(default_factory=list)
    # 시연 모드: 모든 관문 자동 승인 → 테스터 미리보기 발행 → 디스코드 알림(사용자 2026-11-12).
    demoMode: bool = False
    demoBudgetUsd: float = Field(default=15.0, gt=0, le=200)
    # D-0205: Fish Audio 음성 ID(선택). 적은 그대로 캐릭터 패키지에 싣는다.
    voiceReferenceId: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def reference_tier(self):
        if self.referenceImage is not None and self.videoTier != "light":
            raise ValueError("기준 사진 확인 흐름은 Lite 영상 6개에서 사용할 수 있어요.")
        self.voiceReferenceId = normalize_reference_id(self.voiceReferenceId)
        return self


class DemoSwitch(Strict):
    enabled: bool
    budgetUsd: float = Field(default=15.0, gt=0, le=200)
    start: bool = False
    publish: bool = True  # False면 패키지 승인(G9)까지만 하고 발행하지 않는다(로컬 시험)


class Upload(Strict):
    filename: str
    size: int = Field(gt=0, le=MAX_BYTES)
    contentType: str = Field(min_length=1)
    photoRole: Literal["identity", "signature"] = "identity"


class ImportPath(Strict):
    path: str


# 초안 칸 이름(오류가 난 칸을 쉬운 말로 알린다, QA v5 A-06).
DRAFT_LABELS = {
    "displayName": "표시 이름",
    "age": "나이",
    "gender": "성별",
    "job": "하는 일",
    "background": "한 줄 배경",
    "title": "시그니처 포즈 이름",
    "motion": "시그니처 동작",
    "useWhen": "나오는 때",
}


def _topic(word):
    code = ord(word[-1]) - 0xAC00
    return "은" if 0 <= code < 11172 and code % 28 else "는"


def draft_problem(errors):
    """초안 422를 칸 이름과 한도가 담긴 한 문장으로 바꾼다. 모르는 오류면 공통 문장."""
    for error in errors:
        if "factSheet" in error.get("loc", ()) and error.get("type") == "value_error":
            return str(error.get("msg", "")).removeprefix("Value error, ")
        field = next((str(x) for x in reversed(error.get("loc", ())) if x in DRAFT_LABELS), None)
        limit = (error.get("ctx") or {}).get("max_length")
        if field and limit:
            label = DRAFT_LABELS[field]
            return f"{label}{_topic(label)} {limit}자까지 적을 수 있어요."
    return "입력한 내용을 확인해 주세요."


class IntakeRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def checked(request):
            try:
                return await handler(request)
            except SourcePathError:
                raise WebError(403, "이 위치의 파일은 열 수 없어요.") from None
            except RequestValidationError as exc:
                path = request.url.path
                if path.endswith(("/settings", "/videos")):
                    raise WebError(
                        422,
                        "입력한 내용을 확인해 주세요. 시그니처 이름은 30자, 동작은 400자, "
                        "나오는 때는 200자까지 적을 수 있어요.",
                    ) from None
                if path.endswith("/drafts"):
                    raise WebError(422, draft_problem(exc.errors())) from None
                raise WebError(422, "입력한 내용과 파일 크기를 확인해 주세요.") from None

        return checked


def save(path: Path, data: dict) -> None:
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode())


PHOTO_FORMATS = {
    ".png": b"\x89PNG\r\n\x1a\n",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".webp": b"RIFF",
}
PHOTO_LIMIT = 15 * 1024 * 1024


def photo_ok(name, data):
    import cv2
    import numpy as np

    ext = Path(name).suffix.lower()
    if not data.startswith(PHOTO_FORMATS[ext]) or (ext == ".webp" and data[8:12] != b"WEBP"):
        return False
    try:
        return cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_REDUCED_COLOR_8) is not None
    except cv2.error:
        return False


def record(spec: Upload) -> dict:
    name = spec.filename
    photo = Path(name).suffix.lower() in PHOTO_FORMATS
    if spec.photoRole == "signature" and not photo:
        raise WebError(422, "시그니처 참고 사진은 jpg, png, webp로 올려 주세요.")
    if photo and spec.size > PHOTO_LIMIT:
        raise WebError(413, "사진은 15MB 이하로 올려 주세요.")
    if (
        Path(name).name != name
        or "\\" in name
        or len(name.encode()) > 255
        or any(ord(c) < 32 for c in name)
        or Path(name).suffix.lower() not in EXTENSIONS
        and not photo
    ):
        raise WebError(400, "원문 파일 이름과 형식을 확인해 주세요.")
    return dict(
        fileType="photo" if photo else "text",
        **({"photoRole": spec.photoRole} if photo else {}),
        fileId=uuid4().hex,
        filename=name,
        size=spec.size,
        sha256=None,
        status="pending",
        detectedSpeakers=[],
        suggested=dict(
            subjectSpeaker=None, userSpeaker=None, subjectChoices=[], kind=None, register=None
        ),
        problems=[],
        **dict.fromkeys(FIELDS),
    )


def find_file(draft, fid):
    for item in draft["files"]:
        if item["fileId"] == fid:
            return item
    raise WebError(404, "등록한 파일을 찾을 수 없어요.")


def summary(draft):
    problems = []
    files = draft["files"]
    if not any(f.get("fileType", "text") == "text" for f in files):
        problems.append("대화나 글이 담긴 원문을 하나 이상 올려 주세요.")
    if draft["videoTier"] != "none" and not any(
        f["fileType"] == "photo" and f.get("photoRole") != "signature" and f["status"] == "ready"
        for f in files
    ):
        problems.append("영상을 만들려면 인물 사진을 한 장 이상 올려 주세요.")
    if draft["videoTier"] != "none" and not draft.get("signaturePose"):
        problems.append("영상을 만들려면 시그니처 포즈를 정해 주세요.")
    if (
        draft.get("referenceImage") is not None
        and sum(f.get("fileType") == "photo" and f.get("photoRole") != "signature" for f in files)
        != 1
    ):
        problems.append("기준으로 쓸 인물 사진은 한 장만 올려 주세요.")
    ids = [f["textId"] for f in files if f["textId"]]
    if len(ids) != len(set(ids)):
        problems.append("원문 이름이 겹쳐요.")
    for f in files:
        problems.extend(f"{f['filename']}: {p}" for p in f["problems"])
    ready = bool(files) and all(f["status"] == "ready" for f in files)
    return problems, ready and not problems and not draft.get("jobId")


def source_text(folder, item):
    return SourceText(
        **{k: item[k] for k in FIELDS},
        path=str(local_copy(folder, item["fileId"], item["filename"]).relative_to(folder)),
    )


def photo_view(cid, item):
    """Transient preview URLs never become source provenance or immutable inputs."""
    if item.get("fileType") == "photo" and item["status"] == "ready":
        return item | {"previewUrl": f"/api/sources/{cid}/files/{item['fileId']}/preview"}
    return item


def kakao_layout(raw):
    """Recognize export structure, not mentions of Kakao inside an interview."""
    raw = raw.lstrip("\ufeff")
    if raw.startswith(('"', "[")):
        try:
            data = json.loads(raw)
            if isinstance(data, str):
                raw = data
            elif isinstance(data, list) and all(isinstance(x, str) for x in data):
                raw = "\n".join(data)
        except ValueError:
            pass
    for line in raw.splitlines():
        if (
            parse._PC_MSG.match(line)
            or parse._MOBILE_MSG.match(line)
            or re.match(r"^date,\s*user,\s*message(?:,|$)", line, re.I)
        ):
            return True
    return False


def suggested_kind(filename, raw):
    if Path(filename).suffix.lower() in {".vtt", ".srt"}:
        return "TRANSCRIPT"
    if kakao_layout(raw):
        return "KAKAO_EXPORT"
    name = filename.lower()
    if re.search(r"카카오톡|카톡|kakao", name) or Path(filename).suffix.lower() == ".csv":
        return "KAKAO_EXPORT"
    if re.search(r"브이로그|vlog|녹취|자막|일상|transcript|subtitle|casual", name):
        return "TRANSCRIPT"
    if re.search(r"기사|article|보도자료|news", name):
        return "ARTICLE"
    return "INTERVIEW"


def auto_text_id(item, files):
    stem = Path(item["filename"]).stem
    base = (
        re.sub(r"[^a-zA-Z0-9_-]+", "-", stem).strip("-")
        or "source-" + hashlib.sha256(stem.encode()).hexdigest()[:8]
    )
    taken = {f.get("textId") for f in files if f["fileId"] != item["fileId"]}
    result, n = base, 1
    while result in taken:
        n += 1
        result = f"{base}-{n}"
    return result


# 카톡을 내보낸 본인은 파일에 "나"로 적힌다. 대상 인물 후보에서는 맨 뒤로 미루고 권하지 않는다.
# 1:1 카톡에서는 내보낸 본인이 대화 상대라 상대 화자로 먼저 권한다(QA v5 A-03·A-23).
SELF_NAMES = {"나", "me"}


def is_self(name):
    return name.strip().lower() in SELF_NAMES


def speaker_suggestions(messages, display):
    """원문 화자 목록(본인은 뒤로), 표시 이름과 맞는 대상 화자, 고를 후보를 돌려준다.

    표시 이름과 맞는 화자가 없으면 줄 수로 아무나 고르지 않고 대상 화자를 비워 둔다.
    """
    counts = Counter(m.name for m in messages)
    ranked = [name for name, _ in counts.most_common()]
    ranked = [n for n in ranked if not is_self(n)] + [n for n in ranked if is_self(n)]

    def score(name):
        if name == display:
            return (1, 1, 1.0, counts[name])
        if is_self(name):
            return (0, 0, 0.0, 0)
        similarity = SequenceMatcher(None, display, name).ratio()
        return (0, int(name in display or display in name), similarity, counts[name])

    best = max(ranked, key=score, default=None)
    matched = best is not None and (score(best)[1] or score(best)[2] >= 0.5)
    choices = [n for n in ranked if not is_self(n)]
    return [dict(name=n, lines=counts[n]) for n in ranked], best if matched else None, choices


def user_suggestion(names, subject, kind):
    others = [n for n in names if n != subject]
    if kind == "KAKAO_EXPORT":
        me = next((n for n in others if is_self(n)), None)
        if me or not subject:
            return me
    return others[0] if subject and others else None


READ_HINT = {
    "KAKAO_EXPORT": (
        "카톡 대화로 읽지 못했어요. 카톡의 ‘대화 내보내기’로 받은 파일을 그대로 올려 주세요."
    ),
    "ARTICLE": "기사 문단을 찾지 못했어요. 본문이 담긴 글 파일인지 확인해 주세요.",
}


def read_problem(spec, exc):
    """원문을 읽지 못한 까닭을 쉬운 말 한 문장으로 알린다(QA v5 A-09)."""
    suffix = Path(spec.path).suffix.lower()
    if suffix in {".srt", ".vtt"} and spec.kind != "TRANSCRIPT":
        return "자막 파일(srt·vtt)은 종류를 ‘받아쓰기’로 골라 주세요."
    if suffix == ".json":
        return (
            "json 파일은 글줄을 담은 목록이어야 해요. "
            '예: ["기자: 오늘 어땠어요?", "손흥민: 재미있었어요."]'
        )
    if "CSV" in str(exc):
        return "카톡 csv의 날짜를 읽지 못했어요. 카톡에서 내보낸 파일을 그대로 올려 주세요."
    if spec.date and isinstance(exc, ValueError) and "isoformat" in str(exc):
        return "날짜를 읽지 못했어요. 날짜 칸을 다시 골라 주세요."
    if spec.kind in READ_HINT:
        return READ_HINT[spec.kind]
    return (
        "말한 사람이 적힌 줄을 찾지 못했어요. 줄마다 ‘이름: 한 말’처럼 적어 주세요. "
        "예: 기자: 오늘 어땠어요?"
    )


def install_source_routes(app, conf, jobs):
    router = APIRouter(prefix="/api/sources", route_class=IntakeRoute)
    store: SourceStore = (
        S3SourceStore(conf.source_bucket, conf.source_prefix)
        if conf.source_store == "s3"
        else LocalSourceStore()
    )
    if conf.source_store == "s3":
        from botocore.exceptions import BotoCoreError, ClientError
        from fastapi.responses import JSONResponse

        async def storage_error(request, exc):
            return JSONResponse({"detail": "원문 저장소에 연결하지 못했어요."}, status_code=502)

        for error in (BotoCoreError, ClientError):
            app.add_exception_handler(error, storage_error)
    allow_import = not conf.server_mode and conf.source_store == "local"

    @contextmanager
    def opened(cid, *, edit=False, purge=False, settings=False):
        try:
            folder = reads.character_dir(conf.root, cid)
        except WebError as exc:
            raise WebError(exc.status, "만들던 초안을 찾을 수 없어요.") from None
        try:
            state = inside(folder, "s0-source", "intake.json")
            lock = inside(folder, "s0-source", "intake.lock")
        except ValueError:
            raise WebError(403, "이 위치의 파일은 열 수 없어요.") from None
        legacy = (
            settings
            and not state.is_file()
            and lock.parent.is_dir()
            and read_origin(folder) == SOURCE
        )
        if not folder.is_relative_to(conf.root) or not (state.is_file() or legacy):
            raise WebError(404, "만들던 초안을 찾을 수 없어요.")
        with lock.open("a") as fp:
            fcntl.flock(fp, fcntl.LOCK_EX)
            if not (state.is_file() or legacy):
                raise WebError(404, "만들던 초안을 찾을 수 없어요.")  # 기다리는 사이 지운 초안
            draft = {} if legacy else json.loads(state.read_text("utf-8"))
            draft["videoTier"] = read_video_tier(folder) or "none"
            draft["signaturePose"] = read_signature(folder)
            from character_factory_poc.pipeline.origin import read_reference_image

            draft["referenceImage"] = read_reference_image(folder)
            for item in draft.get("files", []):
                item.setdefault("fileType", "text")
            if edit and (jobs.active_for(cid) or (draft.get("jobId") and not purge)):
                raise WebError(409, "이미 만들기를 시작해서 원문을 바꿀 수 없어요.")
            yield folder, draft
            if edit and not draft.get("_removed"):
                save(state, {k: v for k, v in draft.items() if k != "signaturePose"})

    @router.post("/drafts")
    def create(body: Draft):
        inside(conf.root, "runs", "characters")
        ctx = Context(config=load_config(conf.root, conf.config_path), execute=False)
        cid = new_character(ctx, f"motif-{uuid4().hex[:16]}")
        folder = ctx.character_dir(cid)
        write_origin(folder, SOURCE, auto_review=body.autoReview)
        write_video_tier(folder, body.videoTier)
        write_voice(folder, body.voiceReferenceId)
        if body.referenceImage is not None:
            from character_factory_poc.pipeline.origin import write_reference_image

            write_reference_image(folder, body.referenceImage.model_dump())
        if body.videoScene:
            from character_factory_poc.pipeline.origin import write_video_scene

            write_video_scene(folder, body.videoScene.model_dump(exclude_unset=True))
        if body.signaturePose:
            write_signature(folder, _signature(body.signaturePose))
        write_model_mode(folder, body.modelMode)
        if body.demoMode:
            from character_factory_poc.common.errors import FactoryError
            from character_factory_poc.pipeline.demo import write_demo_mode

            try:
                write_demo_mode(folder, enabled=True, budget_usd=body.demoBudgetUsd)
            except FactoryError as exc:
                raise WebError(422, str(exc)) from exc
        subject = SourceSubject(displayName=body.displayName, kind=body.subjectKind)
        intake = dict(
            characterId=cid,
            createdAt=datetime.now(UTC).isoformat(),
            subject=subject.model_dump(),
            usageBasis=body.usageBasis.model_dump(),
            chapterTemplate=body.chapterTemplate,
            knownFacts={k: v.strip() for k, v in body.knownFacts.model_dump().items() if v.strip()},
            files=[],
        )
        if body.factSheet:
            intake["factSheet"] = body.factSheet
        save(inside(folder, "s0-source", "intake.json"), intake)
        return {"characterId": cid}

    @router.get("/drafts")
    def drafts():
        result = []
        for folder in reads.visible_folders(conf.root):
            draft = reads.read_json_file(folder / "s0-source/intake.json")
            # Only resumable upload drafts belong here; old intake formats are
            # left untouched and remain visible through the character list.
            if (
                not isinstance(draft, dict)
                or not isinstance(draft.get("files"), list)
                or not isinstance(draft.get("subject"), dict)
                or not {"characterId", "usageBasis"}.issubset(draft)
                or draft.get("jobId")
                or jobs.active_for(folder.name)
            ):
                continue
            state, _ = reads.read_state(folder)
            if reads.is_draft(draft, state.get("stages", {}).values()):
                result.append(
                    dict(
                        characterId=folder.name,
                        displayName=reads.display_name(reads._persona(folder), draft),
                        createdAt=reads.created_at(folder, draft),
                        files=len(draft["files"]),
                    )
                )
        return sorted(result, key=lambda r: r["createdAt"], reverse=True)

    @router.get("/{cid}")
    def detail(cid: str):
        with opened(cid) as (folder, draft):
            problems, ready = summary(draft)
            return {k: draft[k] for k in ("characterId", "subject", "usageBasis", "files")} | {
                "files": [photo_view(cid, item) for item in draft["files"]],
                "videoTier": draft["videoTier"],
                "signaturePose": draft["signaturePose"],
                "referenceImage": draft["referenceImage"],
                "voiceReferenceId": (read_voice(folder) or {}).get("referenceId"),
                "knownFacts": draft.get("knownFacts", {}),
                "factSheet": draft.get("factSheet", []),
                "store": conf.source_store,
                "allowPathImport": allow_import,
                "problems": problems,
                "canFinalize": bool(ready),
                "jobId": draft.get("jobId"),
            }

    @router.post("/{cid}/files")
    def presign(cid: str, body: Upload):
        with opened(cid, edit=True) as (folder, draft):
            item = record(body)
            if body.photoRole == "signature":
                if draft["videoTier"] != "light" or not draft.get("signaturePose"):
                    raise WebError(409, "Lite를 고르고 시그니처 동작을 정한 뒤 사진을 올려 주세요.")
                if draft.get("referenceImage") is None:
                    # The gesture is redrawn onto the approved master photo, so the
                    # master-photo review flow is required.
                    raise WebError(
                        409, "시그니처 참고 사진은 기준 사진을 확인하는 Lite 흐름에서 쓸 수 있어요."
                    )
                if any(f.get("photoRole") == "signature" for f in draft["files"]):
                    raise WebError(
                        409,
                        "시그니처 참고 사진은 한 장만 올려 주세요. 기존 사진을 먼저 지워 주세요.",
                    )
            upload = store.upload(folder, item["fileId"], body.size, body.contentType)
            draft["files"].append(item)
            return {"fileId": item["fileId"], "upload": upload}

    @router.put("/{cid}/files/{fid}/content")
    async def content(cid: str, fid: str, request: Request):
        if conf.source_store != "local":
            raise WebError(403, "파일을 올릴 때 받은 주소를 이용해 주세요.")
        with opened(cid) as (_, draft):
            size = find_file(draft, fid)["size"]
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > size:
                raise WebError(413, "처음 고른 파일보다 크기가 커요.")
            data.extend(chunk)
        if len(data) != size:
            raise WebError(400, "처음 고른 파일과 크기가 달라요.")
        with opened(cid, edit=True) as (folder, draft):
            item = find_file(draft, fid)
            path = local_copy(folder, fid, item["filename"])
            if path.exists():
                raise WebError(409, "이미 올린 파일이에요.")
            atomic_write(path, data)
            item["sha256"] = hashlib.sha256(data).hexdigest()
        return {"fileId": fid}

    def check(folder, draft, item, body):
        if body.keys() - set(FIELDS):
            raise WebError(422, "바꿀 수 없는 항목이 있어요.")
        if item["fileType"] == "photo":
            if body:
                raise WebError(422, "사진에는 화자 정보를 넣지 않아도 돼요.")
            try:
                data = store.read(folder, item["fileId"], item["filename"], item["size"])
                digest = hashlib.sha256(data).hexdigest()
                if item["sha256"] not in (None, digest) or not photo_ok(item["filename"], data):
                    raise ValueError
            except (OSError, ValueError):
                item.update(
                    status="problem",
                    problems=["열 수 없는 사진이에요. 이 사진을 지우고 다른 사진을 올려 주세요."],
                )
            else:
                item.update(status="ready", sha256=digest, problems=[])
            return item
        candidate = item | body
        display = draft["subject"]["displayName"]
        problems = []
        raw = ""
        try:
            data = store.read(folder, item["fileId"], item["filename"], item["size"])
            digest = hashlib.sha256(data).hexdigest()
            if item["sha256"] and item["sha256"] != digest:
                raise ValueError
            raw = data.decode("utf-8-sig")
            candidate["sha256"] = digest
        except UnicodeError:
            problems.append("한글을 읽을 수 있도록 파일을 UTF-8로 저장해 주세요.")
        except (ValueError, OSError):
            problems.append("원문을 확인할 수 없어 파일을 다시 올려야 해요.")

        kind = suggested_kind(item["filename"], raw)
        candidate["kind"] = candidate["kind"] or kind

        if (
            not candidate["textId"]
            or isinstance(candidate["textId"], str)
            and not candidate["textId"].strip()
        ):
            candidate["textId"] = auto_text_id(item, draft["files"])
        try:
            spec = source_text(folder, candidate)
        except ValidationError:
            raise WebError(422, "원문 이름과 선택한 종류, 말한 자리를 확인해 주세요.") from None
        if spec.register is None:
            candidate["register"] = default_register(spec.kind)
        detected, subject, user, choices = [], None, None, []
        if (
            spec.kind != "KAKAO_EXPORT"
            and kakao_layout(raw)
            and Path(item["filename"]).suffix.lower() not in {".srt", ".vtt"}
        ):
            problems.append("카톡 내보내기 형식이에요. 파일 종류를 카톡으로 바꿔 주세요.")
        if not problems:
            try:
                messages = parse.source_messages(spec, raw, display)
                detected, subject, choices = speaker_suggestions(messages, display)
                if not (spec.subjectSpeaker or "").strip():
                    spec.subjectSpeaker = candidate["subjectSpeaker"] = subject
                names = [s["name"] for s in detected]
                chosen = spec.subjectSpeaker if spec.subjectSpeaker in names else subject
                user = user_suggestion(names, chosen, spec.kind)
                if not spec.subjectSpeaker and spec.kind != "ARTICLE":
                    problems.append(
                        f"원문에 ‘{display}’ 이름이 없어요. 누가 이 사람인지 골라 주세요. "
                        f"원문에 있는 이름: {', '.join(names)}"
                        if names
                        else "원문에 누가 말했는지 이름을 적어 주세요."
                    )
                for name in (spec.subjectSpeaker, spec.userSpeaker):
                    if spec.kind != "ARTICLE" and name and name not in names:
                        problems.append(
                            f"‘{name}’ 대신 원문에 있는 이름({', '.join(names)})을 골라 주세요."
                        )
                same = spec.subjectSpeaker and spec.subjectSpeaker == spec.userSpeaker
                if spec.kind != "ARTICLE" and same:
                    problems.append("대상 화자와 상대 화자를 다른 사람으로 골라 주세요.")
            except (ValueError, KeyError, TypeError) as exc:
                problems.append(read_problem(spec, exc))
        candidate.update(
            detectedSpeakers=detected,
            suggested=dict(
                subjectSpeaker=subject,
                userSpeaker=user,
                subjectChoices=choices,
                kind=kind,
                register=default_register(kind),
            ),
            warnings=[
                f"원문에 ‘{warning.split(': ', 1)[-1]}’ 안내가 있어요."
                for warning in parse.restriction_problems(raw)
            ],
        )
        item.update(candidate, status="problem" if problems else "ready", problems=problems)
        return item

    @router.post("/{cid}/files/{fid}/complete")
    @router.patch("/{cid}/files/{fid}")
    def complete(cid: str, fid: str, body: dict):
        with opened(cid, edit=True) as (folder, draft):
            item = check(folder, draft, find_file(draft, fid), body)
            if item.get("photoRole") == "signature":
                signature = dict(read_signature(folder) or {})
                # Raw upload is a gesture reference only. S4 redraws it onto the
                # approved master photo; G4 approval binds that seed as middle frame.
                if item["status"] == "ready":
                    signature["poseReferencePath"] = str(
                        local_copy(folder, fid, item["filename"]).relative_to(folder)
                    )
                else:
                    signature.pop("poseReferencePath", None)
                write_signature(folder, signature)
            return photo_view(cid, item)

    @router.get("/{cid}/files/{fid}/preview")
    def preview_photo(cid: str, fid: str):
        with opened(cid) as (folder, draft):
            item = find_file(draft, fid)
            if item.get("fileType") != "photo" or item["status"] != "ready":
                raise WebError(409, "확인이 끝난 사진만 볼 수 있어요.")
            try:
                data = store.read(folder, fid, item["filename"], item["size"])
                if hashlib.sha256(data).hexdigest() != item["sha256"]:
                    raise ValueError("image changed")
            except (OSError, ValueError):
                raise WebError(409, "확인한 사진과 달라서 다시 올려야 해요.") from None
            media = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
            }[Path(item["filename"]).suffix.lower()]
            return Response(
                data,
                media_type=media,
                headers={
                    "Cache-Control": "private, no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    @router.post("/{cid}/import-path")
    def import_path(cid: str, body: ImportPath):
        if not allow_import:
            raise WebError(403, "이 컴퓨터에 저장할 때만 파일 위치로 가져올 수 있어요.")
        path = Path(body.path).expanduser()
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
            raise WebError(400, "가져올 파일의 위치와 크기를 확인해 주세요.")
        item = record(
            Upload(filename=path.name, size=path.stat().st_size, contentType="text/plain")
        )
        with opened(cid, edit=True) as (folder, draft):
            with path.open("rb") as fp:
                data = fp.read(item["size"] + 1)
            if len(data) != item["size"]:
                raise WebError(409, "원문 파일의 크기가 바뀌었어요.")
            atomic_write(local_copy(folder, item["fileId"], path.name), data)
            item["sha256"] = hashlib.sha256(data).hexdigest()
            draft["files"].append(item)
            # 올린 파일과 같은 확인을 거쳐 준비됨·확인 필요로 바로 둔다(QA v5 A-05).
            return check(folder, draft, item, {})

    @router.delete("/{cid}/files/{fid}")
    def remove(cid: str, fid: str):
        with opened(cid, edit=True) as (folder, draft):
            item = find_file(draft, fid)
            store.delete(folder, fid)
            draft["files"].remove(item)
            if item.get("photoRole") == "signature":
                signature = dict(read_signature(folder) or {})
                signature.pop("poseReferencePath", None)
                write_signature(folder, signature)
        return {"fileId": fid}

    @router.delete("/{cid}")
    def purge(cid: str):
        """원본을 지운다. 시작하지 않은 초안이면 캐릭터 폴더까지 지운다(QA v5 A-04).

        그래야 목록에서 사라진다. 이미 시작한 캐릭터는 원본만 지우고 캐릭터는 남긴다.
        """
        with opened(cid, edit=True, purge=True) as (folder, draft):
            store.delete(folder)
            draft["files"].clear()
            state, _ = reads.read_state(folder)
            unstarted = reads.is_draft(draft, state.get("stages", {}).values())
            if unstarted:
                shutil.rmtree(folder)
                draft["_removed"] = True
        return {"characterId": cid, "removed": unstarted}

    @router.post("/{cid}/finalize")
    def finalize(cid: str):
        with opened(cid, edit=True) as (folder, draft):
            problems, ready = summary(draft)
            if not ready:
                raise WebError(409, "; ".join(problems) or "올린 원문을 모두 확인해 주세요.")
            validate_source_launch(load_config(conf.root, conf.config_path))
            texts, photos = [], []
            for item in draft["files"]:
                try:
                    data = store.read(folder, item["fileId"], item["filename"], item["size"])
                    if hashlib.sha256(data).hexdigest() != item["sha256"]:
                        raise ValueError("확인한 원본 해시와 다르다")
                except (ValueError, OSError):
                    message = "확인한 원문과 달라서 파일을 다시 올려야 해요."
                    item.update(status="problem", problems=[message])
                    save(inside(folder, "s0-source", "intake.json"), draft)
                    raise WebError(409, message) from None
                if conf.source_store == "s3":
                    atomic_write(local_copy(folder, item["fileId"], item["filename"]), data)
                if item.get("photoRole") == "signature":
                    # Kept as a gesture keyframe, never an identity/source portrait.
                    continue
                if item["fileType"] == "photo":
                    photos.append(
                        {
                            "path": str(
                                local_copy(folder, item["fileId"], item["filename"]).relative_to(
                                    folder
                                )
                            )
                        }
                    )
                else:
                    texts.append(source_text(folder, item))
            opts = {"chapterTemplate": draft["chapterTemplate"]} if draft["chapterTemplate"] else {}
            pack = SourcePack(
                subject=draft["subject"],
                knownFacts=draft.get("knownFacts", {}),
                factSheet=draft.get("factSheet", []),
                usageBasis=draft["usageBasis"],
                texts=texts,
                photos=photos,
                **opts,
            )
            save(inside(folder, "source-pack.json"), pack.model_dump(mode="json"))
            from character_factory_poc.pipeline.demo import read_demo_mode

            # D-0212: 시연 모드는 기준 사진 흐름이어도 사진 확인(G4)까지
            # 자동 승인하고 발행까지 간다.
            if read_demo_mode(folder):
                job = demo_job(cid, draft.get("subject", {}).get("displayName") or cid)
            elif draft.get("referenceImage") is not None:
                job = video_job(cid, prepare_chat=True)
            elif read_auto_review(folder) and draft["videoTier"] != "none":
                job = video_job(cid, prepare_chat=True)
            else:
                job = jobs.submit(cid, until="s8c" if read_auto_review(folder) else "G0")
            draft["jobId"] = job["jobId"]
            return {"jobId": draft["jobId"]}

    def demo_job(cid, name):
        """시연 모드 실행: 모든 관문을 자동 승인하고 테스터 발행 노드(px)까지 간다.

        D-0212: 알림은 발행이 끝났을 때(또는 멈췄을 때) 한 번만 보낸다. 시작 알림은 보내지 않는다.
        """
        return jobs.submit(cid, until="G9", trigger="demo")

    def video_job(cid, *, prepare_chat=False):
        from character_factory_poc.pipeline.origin import graph_for_dir

        graph = graph_for_dir(reads.character_dir(conf.root, cid))
        return jobs.submit(
            cid,
            until="G5b",
            confirm=[sid for sid in VIDEO_STAGES if sid in graph],
            trigger="videos-with-chat" if prepare_chat else "videos",
        )

    def change_settings(folder, draft, cid, tier, signature=None):
        from character_factory_poc.pipeline.origin import read_reference_image

        if read_reference_image(folder) is not None and tier != "light":
            raise WebError(409, "기준 사진 확인 흐름은 Lite 영상 6개로 유지해 주세요.")
        if tier != "light" and (
            (read_signature(folder) or {}).get("middleFramePath")
            or (read_signature(folder) or {}).get("poseReferencePath")
            or any(f.get("photoRole") == "signature" for f in draft.get("files", []))
        ):
            raise WebError(
                409, "시그니처 참고 사진은 Lite에서 지원해요. 사진을 지운 뒤 등급을 바꿔 주세요."
            )
        if jobs.active_for(cid):
            raise WebError(409, "만들기가 끝난 뒤에 바꿀 수 있어요.")
        if (draft.get("jobId") or "files" not in draft) and not reads.character_summary(folder)[
            "chatReady"
        ]:
            raise WebError(409, "대화 준비가 끝난 뒤에 바꿀 수 있어요.")
        write_video_tier(folder, tier)
        if signature:
            updated = _signature(signature)
            previous = read_signature(folder) or {}
            for key in ("template", "middleFramePath", "middleFrameAtS", "poseReferencePath"):
                if key not in signature.model_fields_set and key in previous:
                    updated[key] = previous[key]
            # An uploaded pose remains attached when editing its text description.
            uploaded = next(
                (
                    f
                    for f in draft.get("files", [])
                    if f.get("photoRole") == "signature" and f["status"] == "ready"
                ),
                None,
            )
            if uploaded:
                updated["poseReferencePath"] = str(
                    local_copy(folder, uploaded["fileId"], uploaded["filename"]).relative_to(folder)
                )
            write_signature(folder, updated)
            draft["signaturePose"] = read_signature(folder)

    @router.patch("/{cid}/settings")
    def settings(cid: str, body: Settings):
        with opened(cid, settings=True) as (folder, draft):
            change_settings(folder, draft, cid, body.videoTier, body.signaturePose)
            if body.videoScene:
                from character_factory_poc.pipeline.origin import write_video_scene

                write_video_scene(folder, body.videoScene.model_dump(exclude_unset=True))
            return {"videoTier": body.videoTier, "signaturePose": read_signature(folder)}

    @router.put("/{cid}/demo-mode")
    def demo_mode(cid: str, body: DemoSwitch):
        """만든 캐릭터에도 시연 모드를 켜고 끈다. start면 바로 자동 진행을 시작한다."""
        from character_factory_poc.common.errors import FactoryError
        from character_factory_poc.pipeline.demo import write_demo_mode

        folder = reads.character_dir(conf.root, cid)
        if not folder.is_dir() or not folder.is_relative_to(conf.root):
            raise WebError(404, "캐릭터를 찾을 수 없어요.")
        if jobs.active_for(cid):
            raise WebError(409, "진행 중인 작업이 끝난 뒤에 바꿀 수 있어요.")
        try:
            mode = write_demo_mode(
                folder, enabled=body.enabled, budget_usd=body.budgetUsd, publish=body.publish
            )
        except FactoryError as exc:
            raise WebError(422, str(exc)) from exc
        job_id = None
        if body.enabled and body.start:
            name = reads.display_name(reads._persona(folder), {}) or cid
            job_id = demo_job(cid, name)["jobId"]
        return {"enabled": mode.enabled, "budgetUsd": mode.budgetUsd, "jobId": job_id}

    videos = APIRouter(route_class=IntakeRoute)

    @videos.post("/api/characters/{cid}/videos")
    def start_videos(cid: str, body: Settings):
        with opened(cid, settings=True) as (folder, draft):
            row = reads.character_summary(folder)
            if not row["chatReady"]:
                raise WebError(409, "대화 준비가 끝나면 영상을 만들 수 있어요.")
            if body.videoTier == "none":
                raise WebError(422, "만들 영상의 등급을 골라 주세요.")
            if not body.signaturePose and not read_signature(folder):
                raise WebError(422, "영상을 만들려면 시그니처 포즈를 정해 주세요.")
            gate = next(
                (g for g in row["gates"] if g["id"] == "G0" and g["status"] == "APPROVED"), {}
            )
            if not gate.get("rev") or not (
                reads.read_json_file(inside(folder, "s0-source", gate["rev"], "source-pack.json"))
                or {}
            ).get("photos"):
                raise WebError(409, "영상을 만들려면 사진이 담긴 원문 묶음이 필요해요.")
            change_settings(folder, draft, cid, body.videoTier, body.signaturePose)
            if body.videoScene:
                from character_factory_poc.pipeline.origin import write_video_scene

                write_video_scene(folder, body.videoScene.model_dump(exclude_unset=True))
            return {"jobId": video_job(cid)["jobId"]}

    app.include_router(videos)
    app.include_router(router)
    install_reference_routes(app, conf, jobs)
