# 인계: 2026-11-08 트윈 앞단과 영상 등급

이전 인계: [handoff-2026-11-08-twin-skeleton.md](handoff-2026-11-08-twin-skeleton.md)

## 1. 지금 상태 한눈에

- 실존 인물 갈래 계획 §12 순서 2·3·4·7을 구현했다. 커밋하지 않았다.
- 트윈 캐릭터는 출처 묶음 → G0 → 받은 사진 기준 사진(G1s)·원문 기반 기획(G3) → 뒤쪽 단계로 이어진다. 뒤쪽 단계(s4a~sx, s7·s8)는 오리지널 실행 함수를 그대로 쓴다.
- 영상 등급(light·standard·pro·max)이 S6에 들어갔다.
- 전체 테스트 1303개 통과, 1개 건너뜀.

## 2. 이번 세션에서 한 일

- 순서 2(메인): `contracts/source.py`(source-pack-v1, source-index-v1, source-digest-v1), `stages/s0_source/`(parse.py 결정적 정리, run.py 출처 정리 에이전트와 G0 페이지, approve.py G0), `prompts/source_curator.md`, `tests/test_source_s0.py`. `cfp run --source-pack`.
- 순서 7(서브에이전트 Heisenberg, gpt-6-astra): `stages/s6_actions/`(catalog.py VIDEO_TIERS·full37, run.py, light.py, approve.py), `stages/export/doki_app/api_svc.py` 챕터당 10편 미만 경고, `tests/test_video_tiers.py`, `tests/test_actions.py` 기대값.
- 순서 3(서브에이전트 Hilbert): `stages/s2_hero/twin.py`(run_s2_twin, approve_g1s), `tests/test_twin_s2.py`.
- 순서 4(서브에이전트 Linnaeus): `stages/s3_plan/twin.py`(run_s3_twin), `prompts/source_planner.md`, `contracts/planning.py`(EvidenceKindV2 SOURCE), `contracts/source.py`(knownFacts, chapterTemplate), `checks/registry.py`(s0, s3-twin), `tests/test_twin_s3.py`.
- 연결(메인): `pipeline/graph.py` 트윈 s0·s2·s3 구현됨, `pipeline/orchestrator.py` 트윈 실행 함수, `pipeline/approve.py` G0·G1s, `pipeline/scheduler.py` s0 공급자, `tests/test_twin_flow.py` 통합 흐름.
- 결정 D-0140, D-0141. 계획 문서 변경 이력.
- 실제 공급자 호출, 학습, 커밋은 하지 않았다.

## 3. 결정

- D-0140 트윈 s0 구현 방식(제안)
- D-0141 순서 3·4·7 구현 방식(제안)

## 4. 확인한 사실과 정정

- 다른 세션이 같은 날 D-0129를 먼저 썼다. 이 작업의 s0 결정은 D-0140이다(처음 D-0130으로 적었다가 main과 겹쳐 옮겼다).
- S4 장면 합성 프롬프트에는 아직 "가상 인물" 지시가 있다. 트윈 사진으로 실제 생성할 때 품질과 공급자 거절 여부를 확인해야 한다(계획 순서 11).
- 트윈 G3에서 칸을 직접 고치면(edits) 근거 검사가 다시 돌지 않는다. 근거를 지켜야 하는 수정은 REQUEST_CHANGES로 새 후보를 받는다.
- 트윈 기획의 내부 관계 단계 값은 연애 틀(FLIRT·DATING 등)을 유지한다. 제목·흐름만 팬·가족 틀로 바뀐다.
- 워크숍 화면·대기열은 아직 오리지널 그래프만 그린다(순서 9).

## 5. 미결

- 새 질문 없음.

## 6. 다음 할 일

1. 순서 5: S7·S8 연결(원문 말투 예시, 챕터별 말높임, chat-svc 내보내기의 CASUAL 고정 수정).
2. 순서 6: 모델 준비 방식(TRAIN·BIND_EXISTING·PROMPT_ONLY)과 s9h 비교 세트.
3. 순서 8·9·10: 비교 보고, 여러 캐릭터 병렬 실행·공급자별 상한·진행 화면, 앱 내보내기.

## 7. 떠 있는 것

- 서브에이전트 3명은 모두 끝났고 닫았다.
- 이 작업의 코드 변경은 커밋하지 않았다. 다른 세션의 변경과 같은 작업 트리에 있다.

