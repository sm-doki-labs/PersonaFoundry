# 인계: 2026-10-22 기획 씨앗 → 변형 → 배경 → 자세 → 완성 이미지 흐름(오프라인 골격)

이전 인계: [handoff-2026-10-21-shorts.md](handoff-2026-10-21-shorts.md).

## 1. 지금 상태 한눈에

- 외모 축 캐릭터의 기획·장면 흐름을 사용자 확정안대로 바꿨다(D-0033, D-0034). G2 뒤 사람이 씨앗을 쓰면 Planner가 변형 3안을 내고 G3에서 고른다. 그 뒤 참고 자료 선별(관문 없음), 배경 후보 → G4a → 장면 사실·자세 후보 → G4b → 챕터 완성 이미지 → G4 순서다.
- 오케스트레이터는 한 갈래가 관문·씨앗을 기다려도 다른 갈래를 계속 진행한다. 씨앗을 쓰는 동안 소개 영상(S5)이 만들어진다(D-0035).
- 전부 가짜 공급자로 오프라인 검증만 했다. 실제 모델·구독 이미지 호출은 하지 않았다. 테스트 182 passed.
- 참고 자료 색인은 오프라인 `hash-v1` 임베더 골격뿐이고 실제 임베딩 모델은 미정이다(Q-0019).

## 2. 이번 세션에서 한 일

- 조사: 앱 캐릭터 정보(api-svc `character`·`character_profile_card`·`character_stage`·`character_media`), chat-svc 페르소나 v6·챕터 정의·챕터 사실(`sceneFacts` 등)·관계 프로필(이서연 r14·v43 기준). 결과는 D-0033 근거와 `character-plan-v2`·`scene-plan-v1` 칸 이름에 반영했다.
- 문서: [PRD](../../product/prd.md)·[명세](../../architecture/spec.md)·[LLD](../../architecture/lld.md) v0.8, [결정 기록](../decisions.md) D-0033~D-0035, [미결 질문](../open-questions.md) Q-0019, [factory.example.toml](../../../factory.example.toml) `[stages.s3]`·`[stages.s3r]`·`[stages.s4a]`·`[stages.s4b]`·`[stages.s4]`.
- 주 에이전트가 만든 것: 계약 `contracts/planning.py`·`scene.py`·`refs.py`, `common/aspect.py`(S5 첫 프레임과 공용), 단계 그래프(s3r·s4a·s4b·G4a·G4b), 관문 연결, 기획서 v1·v2 로더, `NeedsInputError`, 갈래별 진행 오케스트레이터, 새 명령(`acf plan seed/variants/own`, `acf refs index/select`, `acf scene backgrounds/poses`, `acf run --seed`), 에이전트 검사 연결(registry), `tests/support/flow.py`, `tests/test_orchestrator_flow.py`.
- 하위 에이전트 3개(gpt-6.1-sol, 사용자 지시)가 쓰기 범위를 나눠 만든 것:
  - 기획: `stages/s3_plan/` seed·variants·own·approve·page·check_v2, 역할 프롬프트 plan_variants·plan_normalizer, `tests/test_plan_variants.py`. 순위 인물 이름은 원문 대신 해시로 작업 공간에 넘겨 유출을 검사한다.
  - 참고 자료: `providers/embed.py`(hash-v1), `stages/s3r_refs/` index·select, curator 프롬프트, `tests/test_refs.py`. 선별 결과에 원문을 남기지 않는다.
  - 장면: `stages/s4a_backgrounds/`, `stages/s4b_poses/`, `stages/s4_frames/` 재작성(얼굴 크롭 + 배경 사진 참조, 챕터별 부분 재생성), scene_scout·scene_writer·pose_director 프롬프트, `tests/test_scene_flow.py`, `tests/test_frames.py`에서 옛 한 단계 S4 테스트 제거.
- 실행하지 않았다: 실제 텍스트·이미지 모델 호출, 실제 색인 구축(기존 5명 저작 콘텐츠·Stanford·SNS 14유형).

## 3. 결정

D-0033(확정), D-0034(확정), D-0035(제안).

## 4. 확인한 사실과 정정

- 앱 코드 주석에 "단계가 오르면 의상·장소가 통째로 바뀐다"가 있어 의상을 자세 단계에서 챕터마다 정하게 했다.
- 영상통화 챕터는 세 챕터 장소를 다시 쓰는 구조(chat-svc `video-call-cafe/exhibition/yajang-context`)라 따로 배경을 정하지 않는다. chat-svc `current-state.md`의 "CLUB/HOTEL_CAFE/HOTEL_LOUNGE 3종" 서술과 데이터가 다르니 앱 연결 때 다시 확인한다.
- 공장에도 다른 저장소에도 임베딩 색인이 없었다. "임베딩된 자료"는 이번에 만든 골격으로 처음 생긴다.
- 기존 한 단계 S4(챕터당 2장 중 고르기)는 새 S4로 대체했다. D-0025(G4 사람 승인)는 유지되고, 생성 방식(D-0026의 챕터당 2장)은 D-0034의 챕터당 1장 + 부분 재생성으로 바뀌었다.
- 하위 에이전트가 남긴 제약: G3가 사람 검토 대기 중일 때 변형을 다시 만들려면 먼저 `REQUEST_CHANGES`나 `REJECT`를 기록해야 한다(기존 상태 규칙).

## 5. 미결

Q-0002, Q-0004, Q-0013, Q-0018, Q-0019.

## 6. 다음 할 일

1. 데모 캐릭터 한 명으로 실제 흐름 1회: `/tmp/acf-s2-demo-20261021/`의 G2 승인 캐릭터에 `acf plan seed` → `acf plan variants --execute` → G3 → `acf scene backgrounds --execute`(구독 이미지 9장, 약 5분) → G4a → `acf scene poses --execute` → G4b → `acf frames run --execute` → G4. 데모 폴더는 임시 폴더라 먼저 `runs/`로 옮긴다.
2. 참고 자료 색인 실제 구축: `acf refs index --personas <chat-svc data/personas> --stanford <카탈로그> --jsonl <SNS14>:SNS14`로 Git 밖 경로에 만들고, 실제 임베딩 모델을 정한다(Q-0019).
3. S7 특질 시트가 `reference-set`을 입력으로 읽게 연결한다(지금은 S3r 결과를 G6에서 근거로 보는 데까지만).
4. 승인 결과를 앱 칸(api-svc 프로필 카드·단계, chat-svc 페르소나·챕터 사실)으로 내보내는 변환을 설계한다.

## 7. 떠 있는 것

- 하위 에이전트 3개는 모두 종료했다.
- 실행 중인 프로세스 없음. Grok 전용 Chrome은 지난 세션에서 띄운 그대로일 수 있다.

