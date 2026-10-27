"""단계 그래프 (명세 §3, LLD §6.1)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stage:
    id: str
    name: str
    deps: frozenset[str] = frozenset()  # 승인돼야 하는 관문
    after: frozenset[str] = frozenset()  # 완료(AWAITING_HUMAN 이상)돼야 하는 단계
    gate: str | None = None
    implemented: bool = False
    extra: dict = field(default_factory=dict)


STAGES: dict[str, Stage] = {
    s.id: s
    for s in [
        # D-0017: 화제성 순위 → 외모 특징 프록시. --ranking이 없으면 오케스트레이터가 건너뛴다.
        Stage("s1", "레퍼런스 선별", gate="G1", implemented=True),
        # D-0023: G1에서 고른 외모군·참조 사진으로 후보를 만들고 G2에서 사람이 고른다.
        Stage("s2", "대표 이미지", deps=frozenset({"G1"}), gate="G2", implemented=True),
        # D-0013: 외모 명세 없이도 기획서를 쓴다(appearanceRev=None). G2가 있으면 참조한다.
        # D-0033: 외모 축 캐릭터는 G2 뒤 씨앗 → 변형 → G3 선택. 그래프 의존을 비워 페르소나 우선
        # 경로(브리프 초안·import, D-0013)도 남긴다. 변형 실행 함수가 G2 승인을 직접 확인한다.
        Stage("s3", "캐릭터 기획", deps=frozenset(), gate="G3", implemented=True),
        # D-0028·D-0033: 소개 영상은 G2만 있으면 돈다. 기획을 쓰는 동안 함께 만들어진다.
        Stage("s5", "소개 영상", deps=frozenset({"G2"}), gate="G5", implemented=True),
        # D-0033: 참고 자료 선별. 사람을 기다리지 않는다(관문 없음, 근거는 G6에서 함께 본다).
        Stage("s3r", "참고 자료 선별", deps=frozenset({"G3"}), implemented=True),
        # D-0033·D-0034: 배경 후보 → G4a → 장면 사실·자세 후보 → G4b → 완성 이미지 → G4.
        Stage("s4a", "챕터 배경 후보", deps=frozenset({"G2", "G3"}), gate="G4a", implemented=True),
        Stage("s4b", "장면 사실·자세 후보", deps=frozenset({"G4a"}), gate="G4b", implemented=True),
        Stage("s4", "챕터 완성 이미지", deps=frozenset({"G2", "G4b"}), gate="G4", implemented=True),
        # D-0038: 동작 영상은 G4 승인 이미지를 첫 프레임으로 쓰고 자기 관문 G5b를 갖는다.
        Stage("s6", "동작 영상", deps=frozenset({"G4"}), gate="G5b", implemented=True),
        Stage("s7", "상세 특질", deps=frozenset({"G3"}), implemented=True),
        Stage(
            "s8",
            "프롬프트",
            deps=frozenset({"G3"}),
            after=frozenset({"s7"}),
            gate="G6",
            implemented=True,
        ),
        Stage("s9", "학습 데이터", deps=frozenset({"G6"}), gate="G7"),
        Stage("s10", "SFT·평가", deps=frozenset({"G7"}), gate="G8"),
        Stage("s11", "릴리즈", deps=frozenset({"G5", "G8"}), gate="G9"),
    ]
}

GATES = ["G1", "G2", "G3", "G4a", "G4b", "G4", "G5", "G5b", "G6", "G7", "G8", "G9"]
