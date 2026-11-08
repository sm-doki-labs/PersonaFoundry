# 인계: 2026-11-08 트윈 갈래 뼈대

이전 인계: [handoff-2026-11-08-real-person-track.md](handoff-2026-11-08-real-person-track.md)

## 1. 지금 상태 한눈에

- 실존 인물 갈래 계획 §12 순서 1(갈래 뼈대)을 구현했다. 커밋하지 않았다.
- 트윈 캐릭터는 만들 수 있고 그래프를 따라 돌지만, 앞단(s0·s2·s3·s9h)은 "아직 구현 전"으로 건너뛴다. 뒤쪽 단계는 G0·s2·G3 승인을 기다린다.
- 오리지널 갈래는 바뀌지 않았다(전체 테스트 통과).

## 2. 이번 세션에서 한 일

- `pipeline/graph.py`: 출신 값(CREATED·SOURCE), 트윈 그래프 `TWIN_STAGES`·`TWIN_GATES`, `stages_for`·`gates_for`. `STAGES`·`GATES`는 그대로다.
- `pipeline/origin.py`(새 파일): `origin.json`(`character-origin-v1`) 읽기·한 번 쓰기, 표시 이름(오리지널·트윈), 갈래별 단계 정의 `stage_def`.
- `pipeline/state.py`: `require_deps`가 갈래 그래프의 의존을 본다. 쓰지 않게 된 `STAGES` import를 지웠다.
- `pipeline/scheduler.py`: `ready_stages`·`until_scope`·정렬이 갈래 그래프를 따른다. 트윈에는 외모 축의 s3 ← s2 선행을 넣지 않는다.
- `pipeline/orchestrator.py`: G0·G1s는 사람만 결정, `--until`에 트윈 단계·관문 허용, 트윈은 `--ranking` 거절·s1·s2·s3 실행 함수 제외·장면·영상·패키지 실행 함수 등록, 트윈 건너뜀 문장, 순차 실행이 갈래 그래프 순서를 따른다.
- `cli.py`: `cfp run --new-slug <slug> --origin twin`. 기존 캐릭터의 출신은 바꿀 수 없다.
- `tests/test_origin_track.py`(새 파일, 9개).
- 결정 D-0127·D-0128, Q-0030 해결, 계획 문서 §3·변경 이력.

## 3. 결정

- D-0127 갈래 표시 이름 오리지널·트윈(확정)
- D-0128 트윈 그래프 계산 방식, s2·s3 트윈 판, origin.json(제안)

## 4. 확인한 사실과 정정

- 계획 문서의 s2s·s3s는 별도 단계가 아니라 s2·s3의 트윈 판으로 구현했다(D-0128).
- 워크숍 화면(`web/reads.py`, `web/runtime.py`, `web/jobs.py`)과 대기열(`pipeline/queue.py`)은 아직 오리지널 그래프만 본다. 트윈 캐릭터를 화면에 그리는 일은 계획 순서 9에서 한다.

## 5. 미결

- 새 질문 없음.

## 6. 다음 할 일

1. 계획 순서 2: 출처 묶음 s0·G0(`source-pack-v1`, 카톡 두 형식 읽기, 가림, 비교 세트 분리, G0 화면). 합성 fixture로만 테스트한다.
2. 순서 3·4: s2·s3 트윈 판 실행 함수.

## 7. 떠 있는 것

- 이전 인계의 로컬 시험 스택·에뮬레이터는 그대로일 수 있다.
- 이 작업의 코드 변경은 커밋하지 않았다. 다른 세션의 변경과 같은 작업 트리에 있다.

