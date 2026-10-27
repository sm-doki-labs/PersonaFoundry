# 인계: 2026-10-21(프레임) S3 외모 연결과 S4 챕터 프레임·G4 사람 승인

이전 인계: [handoff-2026-10-21.md](handoff-2026-10-21.md)(같은 날 앞 세션).

## 1. 지금 상태 한눈에

- S3 Planner가 G2 외모 요약을 받아 기획서에 `appearanceRev`를 남기고, 챕터마다 조명·구도 한 줄을 채운다(D-0024).
- S4 챕터 프레임을 구현했다. 기준 얼굴을 참조로 붙여 챕터마다 후보 2장을 만들고, G4에서 사람이 세 챕터 각각 한 장을 골라 승인하면 `approved-frames.json`이 고정된다(D-0025, D-0026). 명령은 `acf frames run`, `acf gate import <id> G4`.
- 실제 구독으로 S4를 두 번 돌렸다(챕터당 1장). 세 챕터 모두 기준 얼굴과 장면·조명이 맞게 나왔고 G4 승인까지 확인했다. 기준 사진의 자세(턱 괴기)를 따라 하는 문제가 남았다(Q-0016).
- 테스트 66 passed.

## 2. 이번 세션에서 한 일

- 코드: `stages/s3_plan/draft.py`(`appearance_input`, 계약 예시), `stages/s3_plan/check.py`(외모 rev·조명·구도 검사), `checks/registry.py`, `prompts/planner.md`, `contracts/frames.py`(`frames-inputs-v1`, `chapter-frame-v1`, `chapter-frames-approved-v1`), `stages/s4_frames/`(prompt·run·page·approve), 그래프(s4 의존 G2·G3), 오케스트레이터, 관문 승인, CLI `frames run`.
- 테스트: `tests/test_frames.py` 11개.
- 문서: [결정 기록](../decisions.md) D-0024~D-0026, [미결 질문](../open-questions.md) Q-0016, [PRD](../../product/prd.md)·[명세](../../architecture/spec.md)·[LLD](../../architecture/lld.md) v0.5.
- 실제 호출: S4 fr1·fr2(각 3장). S3는 가짜 Planner로 채웠다(실제 Planner로 외모 연결 초안은 돌리지 않았다).

## 3. 결정

D-0024(제안), D-0025(확정), D-0026(제안).

## 4. 확인한 사실과 정정

- 프레임 한 장에 약 32~38초, 입력 토큰 약 5만~12.5만 개(구독 사용량).
- "참조는 얼굴에만, 자세는 장면을 따른다" 문장을 넣어도 3장 중 2장이 기준 사진의 자세를 따라 했다. 문장만으로는 부족하다.
- 오케스트레이터는 순차라서 G4 대기 중에는 S7·S8로 넘어가지 않는다. 명세의 "S4·S5·S7 병렬"은 아직 구현되지 않았다.

## 5. 미결

Q-0002, Q-0004, Q-0013, Q-0016.

## 6. 다음 할 일

1. Q-0016: 기준 이미지에서 얼굴 부분만 잘라 참조로 넣는 방식을 한 번 시험한다(얼굴 위치는 비전 모델 또는 얼굴 검출로 찾는다).
2. 실제 Planner(codex_exec)로 외모가 연결된 S3 초안을 한 번 돌려 조명·구도 문장 품질을 본다.
3. S5 소개 영상(Grok): xAI 영상 API 입력·사양·단가 확인 뒤 설계. 그다음 S6이 `load_approved_frames`를 입력으로 받는다.
4. 오케스트레이터가 사람 관문 대기 중에도 독립 단계(S7)를 진행하도록 바꿀지 정한다.

## 7. 떠 있는 것

없음. 데모 산출물: `/tmp/acf-s2-demo-20261021/runs/characters/cf-20261021-s2real/`(G1~G4 모두 승인 상태, s4-frames/fr2 승인).
