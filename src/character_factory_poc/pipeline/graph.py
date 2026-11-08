"""단계 그래프 (명세 §3, LLD §6.1)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stage:
    id: str
    name: str
    deps: frozenset[str] = frozenset()  # 승인돼야 하는 관문
    needs: frozenset[str] = frozenset()  # APPROVED여야 하는 단계(D-0042)
    after: frozenset[str] = frozenset()  # 완료(AWAITING_HUMAN 이상)돼야 하는 단계
    gate: str | None = None
    implemented: bool = False
    extra: dict = field(default_factory=dict)


STAGES: dict[str, Stage] = {
    s.id: s
    for s in [
        # D-0017: 화제성 순위 → 외모 특징 프록시. --ranking이 없으면 오케스트레이터가 건너뛴다.
        Stage("s1", "레퍼런스 선별", gate="G1", implemented=True),
        # D-0042: G1에서 고른 얼굴 하나로 기준 사진·외모 명세를 자동으로 고정한다. 사람 관문이
        # 없으므로 gate=None이고, G2는 결번이다. 통과하면 s2가 APPROVED가 된다.
        Stage("s2", "기준 사진", deps=frozenset({"G1"}), implemented=True),
        # D-0013: 외모 명세 없이도 기획서를 쓴다(appearanceRev=None).
        # D-0033: 외모 축 캐릭터는 s2 뒤 씨앗 → 변형 → G3 선택. 그래프 의존을 비워 페르소나 우선
        # 경로(브리프 초안·import, D-0013)도 남긴다. 변형 실행 함수가 s2 승인을 직접 확인한다.
        Stage("s3", "캐릭터 기획", deps=frozenset(), gate="G3", implemented=True),
        # D-0028·D-0033·D-0042: 소개 영상은 외모 명세(s2 승인)만 있으면 돈다. 기획을 쓰는 동안
        # 함께 만들어진다.
        Stage("s5", "소개 영상", needs=frozenset({"s2"}), gate="G5", implemented=True),
        # D-0033: 참고 자료 선별. 사람을 기다리지 않는다(관문 없음, 근거는 G6에서 함께 본다).
        Stage("s3r", "참고 자료 선별", deps=frozenset({"G3"}), implemented=True),
        # D-0033·D-0034: 배경 후보 → G4a → 장면 사실·자세 후보 → G4b → 완성 이미지 → G4.
        Stage(
            "s4a",
            "챕터 배경 후보",
            deps=frozenset({"G3"}),
            needs=frozenset({"s2"}),
            gate="G4a",
            implemented=True,
        ),
        Stage("s4b", "장면 사실·자세 후보", deps=frozenset({"G4a"}), gate="G4b", implemented=True),
        Stage(
            "s4",
            "챕터 완성 이미지",
            deps=frozenset({"G4b"}),
            needs=frozenset({"s2"}),
            gate="G4",
            implemented=True,
        ),
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
        # D-0044·D-0045, LLD §6.1·§8.8~§8.11: 학습 가이드 절차대로 샘플(G7a) → 대량(G7),
        # 학습(관문 없음, PoC는 dry run) → 평가(G8) → 패키지(G9) → 우리 앱 내보내기.
        # s10t는 PoC 실제 설정에서 계획(dry run)까지만 돈다. s10은 학습 결과가 있어야 시작한다.
        Stage("s9s", "데이터 샘플", deps=frozenset({"G6"}), gate="G7a", implemented=True),
        Stage("s9", "학습 데이터", deps=frozenset({"G7a"}), gate="G7", implemented=True),
        Stage("s10t", "SFT 학습", deps=frozenset({"G7"}), implemented=True),
        Stage(
            "s10",
            "평가",
            deps=frozenset({"G7"}),
            after=frozenset({"s10t"}),
            gate="G8",
            implemented=True,
        ),
        Stage(
            "s11",
            "릴리즈 패키지",
            deps=frozenset({"G4", "G5", "G5b", "G6", "G8"}),
            gate="G9",
            implemented=True,
        ),
        Stage("sx", "우리 앱 내보내기", deps=frozenset({"G9"}), implemented=True),
    ]
}

# G2는 결번이다(D-0042). 옛 state.json의 G2 칸은 읽기만 하고 쓰지 않는다.
GATES = ["G1", "G3", "G4a", "G4b", "G4", "G5", "G5b", "G6", "G7a", "G7", "G8", "G9"]
RETIRED_GATES = {"G2": "G2는 결번이다(D-0042). 외모는 G1에서 한 번 고르고 S2가 자동으로 고정한다"}

# --- 갈래(D-0116, D-0127, D-0128) ---------------------------------------------------------
# 출신 코드 값. 표시 이름은 오리지널(CREATED)·모티브(SOURCE)이다.
CREATED = "CREATED"
SOURCE = "SOURCE"
ORIGINS = (CREATED, SOURCE)

# 모티브 갈래는 앞단만 다르다. s1은 없고, s0(출처 묶음)·s9h(비교 세트)가 더해지며, s2·s3는 같은
# 단계 ID의 모티브 판이다. 뒤쪽 단계는 오리지널과 같은 정의를 쓰므로 의존과 산출물 계약이 같다.
# 구현 전 단계는 implemented=False로 두어 실행 목록에 들지 않는다(계획 §12 순서 2~6).
_TWIN_FRONT = {
    "s0": Stage("s0", "출처 묶음", gate="G0", implemented=True),
    "s2": Stage("s2", "기준 사진", deps=frozenset({"G0"}), gate="G1s", implemented=True),
    "s3": Stage("s3", "캐릭터 기획", deps=frozenset({"G0"}), gate="G3", implemented=True),
    "s9h": Stage("s9h", "비교 세트", deps=frozenset({"G0"}), implemented=True),
}


def _twin_stages() -> dict[str, Stage]:
    out: dict[str, Stage] = {"s0": _TWIN_FRONT["s0"]}
    for sid, stage in STAGES.items():
        if sid == "s1":
            continue
        out[sid] = _TWIN_FRONT.get(sid, stage)
        if sid == "s9":
            out["s9h"] = _TWIN_FRONT["s9h"]
    return out


TWIN_STAGES: dict[str, Stage] = _twin_stages()
TWIN_GATES = ["G0", "G1s", *[g for g in GATES if g != "G1"]]

# 모델 준비 방식(D-0118). 모티브가 학습하지 않는 방식이면 학습 데이터·학습 단계를 빼고, 평가(s10)는
# 대화 프롬프트 승인(G6)과 비교 세트(s9h)를 기다린다. TRAIN이면 학습 뒤에 비교 세트도 기다린다.
TRAIN = "TRAIN"
BIND_EXISTING = "BIND_EXISTING"
PROMPT_ONLY = "PROMPT_ONLY"
MODES = (TRAIN, BIND_EXISTING, PROMPT_ONLY)
_NO_TRAIN_STAGES = frozenset({"s9s", "s9", "s10t"})


def _twin_mode_stages(mode: str) -> dict[str, Stage]:
    out: dict[str, Stage] = {}
    for sid, stage in TWIN_STAGES.items():
        if mode != TRAIN and sid in _NO_TRAIN_STAGES:
            continue
        if sid == "s10":
            if mode == TRAIN:
                stage = Stage(
                    "s10",
                    stage.name,
                    deps=stage.deps,
                    after=frozenset({"s10t", "s9h"}),
                    gate=stage.gate,
                    implemented=stage.implemented,
                )
            else:
                stage = Stage(
                    "s10",
                    stage.name,
                    deps=frozenset({"G6"}),
                    after=frozenset({"s9h"}),
                    gate=stage.gate,
                    implemented=stage.implemented,
                )
        out[sid] = stage
    return out


TWIN_MODE_STAGES: dict[str, dict[str, Stage]] = {m: _twin_mode_stages(m) for m in MODES}
# 어느 갈래에든 있는 단계·관문 이름(--until 검사용)
ALL_STAGE_IDS = frozenset(STAGES) | frozenset(TWIN_STAGES)
ALL_GATES = frozenset(GATES) | frozenset(TWIN_GATES)


def stages_for(origin: str, mode: str = TRAIN) -> dict[str, Stage]:
    """그 갈래·모델 준비 방식의 단계 그래프(STAGES 순서). 오리지널은 STAGES 그 자체다."""
    if mode not in MODES:
        raise ValueError(f"알 수 없는 모델 준비 방식: {mode}")
    if origin == SOURCE:
        return TWIN_MODE_STAGES[mode]
    if origin != CREATED:
        raise ValueError(f"알 수 없는 출신: {origin}")
    return STAGES


def gates_for(origin: str) -> list[str]:
    """그 갈래의 관문 순서. 오리지널은 GATES 그 자체다."""
    if origin == SOURCE:
        return TWIN_GATES
    if origin != CREATED:
        raise ValueError(f"알 수 없는 출신: {origin}")
    return GATES
