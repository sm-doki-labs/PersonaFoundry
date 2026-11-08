# 인계: 2026-11-08 트윈 페르소나와 모델 준비 방식

이전 인계: [handoff-2026-11-08-twin-front.md](handoff-2026-11-08-twin-front.md)

## 1. 지금 상태 한눈에

- 실존 인물 갈래 계획 §12 순서 1~7을 구현했다. 남은 것은 순서 8(비교 보고)·9(여러 캐릭터 병렬·진행 화면)·10(앱 내보내기)·11(실제 리허설)·12(발표 점검)다.
- 트윈은 출처 묶음 → G0 → 기준 사진(G1s)·기획(G3) → S7·S8(G6) → 모델 준비 방식에 따라 학습 데이터(G7a·G7)·학습 또는 비교 세트 → G8까지 합성 자료로 이어진다.
- 전체 테스트 1345개 통과, 1개 건너뜀. 실제 공급자 호출·학습·커밋은 하지 않았다.

## 2. 이번 세션에서 한 일

- 메인: 모델 준비 방식(`pipeline/graph.py` MODES·방식별 트윈 그래프, `pipeline/origin.py` read/write_model_mode·graph_for_dir), 스케줄러·오케스트레이터 연결, `cli.py`(`cfp run --model-mode`, `cfp model mode|bind`), `tests/test_model_mode.py`, 통합 흐름에 s9h 확인 추가.
- 서브에이전트 Schrodinger(gpt-6-astra): 순서 5. `stages/s7_traits/sheet.py`, `prompts/source_profiler.md`, `stages/s8_prompts/twin.py`·build.py·actor_persona.py, `stages/export/doki_app/chat_svc.py` 말높임, `tests/test_twin_persona.py`, `tests/test_chat_svc_speech_level.py`.
- 서브에이전트 James: 순서 6 연결·비교. `contracts/model_binding.py`, `stages/model_prep/bind.py`, `stages/s9h_holdout/run.py`, `stages/s10_eval/twin.py`, `stages/s10_eval/approve.py`, `contracts/training.py`, `tests/test_model_prep.py`.
- 서브에이전트 Maxwell: 순서 6 학습 데이터. `stages/s9_data/twin.py`, `contracts/dataset.py`(Material SOURCE), `tests/test_twin_dataset.py`.
- 결정 D-0132, 계획 문서 변경 이력.

## 3. 결정

- D-0132 순서 5·6 구현 방식(제안)

## 4. 확인한 사실과 정정

- 2026-11-07 시험 경로에서 서윤이 앱에서 반말을 쓴 원인(chat-svc 내보내기의 CASUAL 고정)을 고쳤다. 실제 앱 통화로는 다시 확인하지 않았다.
- 워크숍 G8 화면의 고정 문구 "긴 프롬프트로 진행"은 BIND_EXISTING에 맞지 않는다. 생성된 gate-G8.html에는 실제 채택 대상이 나온다(순서 9에서 화면 연결).
- 자연어로 적은 복잡한 말 놓기 조건은 자동 추정하지 않는다. 그런 챕터는 chapterStart.relationship에 명시한다.
- HF 사전 확인은 가짜 클라이언트로만 검증했다. 실제 접근은 하지 않았다.

## 5. 미결

- 새 질문 없음.

## 6. 다음 할 일

1. 순서 8: s9h 장면으로 실제 답 vs 생성 답 비교 보고, 외운 답 표시, 블라인드 판정 화면.
2. 순서 9: `cfp batch run`, 공급자별 동시 호출 상한, 진행 화면의 트윈 그래프.
3. 순서 10: 트윈 캐릭터의 앱 내보내기(캐릭터별 모델 연결, 챕터 틀 단계 이름, 음성 연결 칸).

## 7. 떠 있는 것

- 서브에이전트 3명은 모두 끝났고 닫았다.
- 코드 변경은 커밋하지 않았다. 다른 세션의 변경과 같은 작업 트리에 있다.

