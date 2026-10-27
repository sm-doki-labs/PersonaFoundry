"""S1 레퍼런스 계약 (LLD §5.2~§5.6, D-0017, D-0020)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

from acf.common.names import normalize_name
from acf.common.schema import register
from acf.contracts.common import Strict

SLUG = r"^[a-z0-9][a-z0-9-]{0,40}$"

# 인물 인상(D-0020). 미리보기 프롬프트에 그대로 들어가므로 자유 입력 대신 정해진 값만 받는다.
AppearanceOrigin = Literal["korean", "east-asian", "unspecified"]


class RankingScope(Strict):
    characterGender: Literal["female", "male", "any"]
    ageRange: str = Field(min_length=1)
    artStyle: str = Field(min_length=1)
    appearanceOrigin: AppearanceOrigin
    moodHints: list[str] = Field(default_factory=list)


class RankingEntry(Strict):
    rank: int = Field(ge=1)
    name: str = Field(min_length=1)
    score: float | None = None


class RankingList(Strict):
    listId: str = Field(pattern=SLUG)
    source: str = Field(min_length=1)
    category: str = Field(min_length=1)
    period: str = Field(min_length=1)
    retrievedAt: str = ""
    url: str = ""
    entries: list[RankingEntry] = Field(min_length=1)

    @field_validator("entries")
    @classmethod
    def _unique(cls, v: list[RankingEntry]) -> list[RankingEntry]:
        ranks = [e.rank for e in v]
        if len(set(ranks)) != len(ranks):
            raise ValueError("한 목록 안에서 rank가 겹친다")
        names = [normalize_name(e.name) for e in v]
        if "" in names:
            raise ValueError("글자나 숫자가 없는 이름이 있다")
        if len(set(names)) != len(names):
            raise ValueError("한 목록 안에서 이름이 겹친다(공백·대소문자 무시)")
        return v


@register("popularity-ranking-v2")
class PopularityRanking(Strict):
    schemaVersion: Literal["popularity-ranking-v2"] = "popularity-ranking-v2"
    scope: RankingScope
    lists: list[RankingList] = Field(min_length=1)
    notes: str = ""

    @field_validator("lists")
    @classmethod
    def _unique_lists(cls, v: list[RankingList]) -> list[RankingList]:
        ids = [x.listId for x in v]
        if len(set(ids)) != len(ids):
            raise ValueError("listId가 겹친다")
        return v


class PersonAppearance(Strict):
    listId: str
    category: str
    rank: int
    listSize: int
    percentile: float | None


class Person(Strict):
    personId: str = Field(pattern=r"^p\d{3,}$")
    name: str
    appearances: list[PersonAppearance] = Field(min_length=1)


@register("ranking-people-v1")
class RankingPeople(Strict):
    schemaVersion: Literal["ranking-people-v1"] = "ranking-people-v1"
    rankingSha256: str
    people: list[Person]


SINGLE_FIELDS = (
    "faceShape",
    "eyeShape",
    "hairLength",
    "hairColor",
    "hairStyle",
    "bangs",
    "skinTone",
)
MULTI_FIELDS = ("styling", "mood")
ALL_FIELDS = SINGLE_FIELDS + MULTI_FIELDS


class FeatureTags(Strict):
    faceShape: str
    eyeShape: str
    hairLength: str
    hairColor: str
    hairStyle: str
    bangs: str
    skinTone: str
    styling: list[str] = Field(default_factory=list)
    mood: list[str] = Field(default_factory=list)


class PersonFeatures(Strict):
    personId: str
    recognized: bool
    tags: FeatureTags
    confidence: dict[str, float] = Field(default_factory=dict)
    note: str = ""

    @field_validator("confidence")
    @classmethod
    def _range(cls, v: dict[str, float]) -> dict[str, float]:
        for k, x in v.items():
            if not 0.0 <= x <= 1.0:
                raise ValueError(f"confidence.{k}는 0~1이어야 한다")
        return v


@register("appearance-features-v1")
class AppearanceFeatures(Strict):
    schemaVersion: Literal["appearance-features-v1"] = "appearance-features-v1"
    vocabVersion: str
    features: list[PersonFeatures] = Field(min_length=1)
    notes: str = ""


class Popularity(Strict):
    medianPercentile: float | None
    iqr: float | None
    normalizedCount: int
    unnormalizedCount: int


@register("appearance-cluster-v1")
class AppearanceCluster(Strict):
    schemaVersion: Literal["appearance-cluster-v1"] = "appearance-cluster-v1"
    clusterId: str = Field(pattern=r"^c\d+$")
    members: list[str] = Field(min_length=1)
    memberCount: int
    commonTags: dict[str, str | list[str]] = Field(min_length=1)
    tagShares: dict[str, dict[str, float]]
    listCount: int = Field(ge=1)
    popularity: Popularity
    limitations: list[str] = Field(default_factory=list)


class Ordering(Strict):
    clusterId: str
    rationale: str = Field(min_length=1)


class Dropped(Strict):
    members: list[str]
    reason: str = Field(min_length=1)


class ExcludedPerson(Strict):
    personId: str
    reason: str = Field(min_length=1)


class Reproducibility(Strict):
    previousRev: str | None = None
    agreementWithPrevious: float | None = None
    comparedPeople: int = 0


class ReportSettings(Strict):
    clusterK: int
    minMembers: int
    minCommonFields: int
    previewsPerCluster: int
    minListSizeForPercentile: int
    linkage: Literal["average"] = "average"
    distance: Literal["cosine"] = "cosine"


@register("reference-report-v2")
class ReferenceReport(Strict):
    schemaVersion: Literal["reference-report-v2"] = "reference-report-v2"
    subjectId: str
    referenceRev: str = Field(pattern=r"^rf\d+$")
    rankingSha256: str
    featuresSha256: str
    vocabVersion: str
    scope: RankingScope
    settings: ReportSettings
    normalization: str = Field(min_length=1)
    candidates: list[AppearanceCluster] = Field(min_length=1)
    ordering: list[Ordering] = Field(min_length=1)
    dropped: list[Dropped] = Field(default_factory=list)
    excludedPeople: list[ExcludedPerson] = Field(default_factory=list)
    cautions: list[str] = Field(min_length=3)
    reproducibility: Reproducibility

    @model_validator(mode="after")
    def _ordering_matches(self):
        ids = [c.clusterId for c in self.candidates]
        if [o.clusterId for o in self.ordering] != ids:
            raise ValueError("ordering의 clusterId 순서가 candidates와 같아야 한다")
        for c in self.candidates:
            if c.memberCount != len(c.members) or c.memberCount < self.settings.minMembers:
                raise ValueError(f"{c.clusterId}: 구성원 수가 기준과 맞지 않다")
        return self


@register("reference-preview-v1")
class ReferencePreview(Strict):
    schemaVersion: Literal["reference-preview-v1"] = "reference-preview-v1"
    previewId: str = Field(pattern=r"^c\d+-\d+$")
    clusterId: str
    prompt: str = Field(min_length=1)
    negativePrompt: str = ""
    model: str
    provider: str
    settings: dict[str, str | int]
    fileSha256: str
    filePath: str
