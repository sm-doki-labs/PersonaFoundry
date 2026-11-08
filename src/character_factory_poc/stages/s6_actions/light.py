"""한 챕터만 만드는 light 등급의 S6 계약. 기존 v2 파일은 3챕터 계약으로 검증한다."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from character_factory_poc.common.schema import register, validate
from character_factory_poc.common.store import read_json
from character_factory_poc.contracts.video import (
    ActionChapter,
    ActionInputs,
    ApprovedActions,
    ApprovedClip,
)

LIGHT_INPUTS = "action-inputs-light-v1"
LIGHT_APPROVED = "action-videos-approved-light-v1"


class LightChapter(ActionChapter):
    chapterId: Literal["ch1"]


@register(LIGHT_INPUTS)
class LightInputs(ActionInputs):
    schemaVersion: Literal["action-inputs-light-v1"] = LIGHT_INPUTS
    preset: Literal["tier:light"] = "tier:light"
    chapters: list[LightChapter] = Field(min_length=1, max_length=1)


@register(LIGHT_APPROVED)
class LightApprovedActions(ApprovedActions):
    schemaVersion: Literal["action-videos-approved-light-v1"] = LIGHT_APPROVED
    clips: list[ApprovedClip] = Field(min_length=1)

    @field_validator("clips")
    @classmethod
    def _every_chapter(cls, clips: list[ApprovedClip]) -> list[ApprovedClip]:
        if any(c.chapterId != "ch1" for c in clips):
            raise ValueError("light는 ch1 영상만 승인할 수 있다")
        if len({c.actionId for c in clips}) != len(clips):
            raise ValueError("한 동작에서 영상은 하나만 고른다")
        return clips


def read_inputs(path: Path) -> ActionInputs:
    data = read_json(path)
    return validate(
        LIGHT_INPUTS if data.get("schemaVersion") == LIGHT_INPUTS else "action-inputs-v2", data
    )


def read_approved(path: Path) -> ApprovedActions:
    data = read_json(path)
    return validate(
        LIGHT_APPROVED
        if data.get("schemaVersion") == LIGHT_APPROVED
        else "action-videos-approved-v2",
        data,
    )
