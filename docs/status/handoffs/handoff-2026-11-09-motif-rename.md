# 인계: 2026-11-09 실존 인물 갈래 이름을 모티브로

이전 인계: [handoff-2026-11-08-twin-rehearsal-prep.md](handoff-2026-11-08-twin-rehearsal-prep.md)

## 1. 지금 상태 한눈에

- 실존 인물 갈래의 표시 이름을 "트윈"에서 "모티브"로 바꿨다(D-0144, D-0127의 갈래 이름 대체). 창작 갈래는 "오리지널" 그대로다.
- 브랜치 `codex/motif-rename`(main 0d8e219에서 시작, PR #4가 합쳐진 뒤). 전체 시험 1436 passed, 5 skipped(실제 적재 시험), studio 노드 시험 52 passed, ruff·format 깨끗.

## 2. 이번 세션에서 한 일

- 화면: 진행 화면 배지("모티브 · 학습" 등), 관문 화면 문구, 사용 안내, 시험 고정 자료의 `originLabel`.
- 패키지: 새 패키지의 `twin.originLabel`은 "모티브". 계약은 예전 패키지의 "트윈"도 읽는다(`contracts/release.py`).
- 명령: `cfp run --origin motif`, `cfp motif precheck`, 배치 명세 `"origin": "motif"`. 예전 이름 `twin`도 같은 뜻으로 받는다(`pipeline/origin.CLI_NAMES`, `contracts/batch.py`, `cli.py` 하위 명령 별칭). 시험 `tests/test_origin_track.py::test_cli_motif_name_and_old_twin_alias`.
- 문서: 리허설 안내서, 계획서 본문(변경 이력의 옛 줄은 당시 이름 그대로), 결정 D-0144와 D-0127 상태(폐기, D-0144로 대체).
- 코드 주석과 LLM 프롬프트 두 개(`source_curator.md`, `source_profiler.md`)의 "트윈 캐릭터"도 "모티브 캐릭터"로 바꿨다.

## 3. 결정

- D-0144 갈래 표시 이름 모티브(확정).

## 4. 확인한 사실과 정정

- 코드 값 `SOURCE`, 모듈·파일 이름(`*/twin.py`, `tests/test_twin_*.py`, `examples/twin/`, `docs/guides/twin-rehearsal.md`), 브랜치 이름은 바꾸지 않았다.
- 결정·미결 질문·인계 문서의 지난 기록은 규칙대로 고치지 않았다(D-0003).
- 2026-11-08 시연용으로 만든 엄마 패키지(`/tmp/twin-guide-1`, "트윈")는 새 코드에서도 그대로 읽힌다.

## 5. 미결

- 없음.

## 6. 다음 할 일

- PR 머지. 순서 11(실제 자료 리허설)은 사용자 자료·비용 승인 대기.

## 7. 떠 있는 것

- 시연 서버 두 개(8840 모티브 시연 공장, 8841 오리지널 긴 프롬프트 시연)가 켜져 있다.
