# 인계: 2026-10-28 에이전틱 실행(D-0049·D-0050)

이전 인계: [handoff-2026-10-28-prompt-only.md](handoff-2026-10-28-prompt-only.md)

## 1. 지금 상태 한눈에

- 워크숍에서 관문을 결정하면 실행기가 이어서 돌고(자동 재개), 의존이 풀린 단계는 동시에 돈다(물결 실행, 기본 3개).
- 고르기·승인 관문이 열리면 검토 에이전트가 후보별 추천·근거·걸리는 점을 남긴다. G7a·G8에는 붙이지 않는다. 이미지·영상 관문 비전 검토는 코드만 있고 꺼져 있다(Q-0020).
- 수정 요청 메모로 요청한 부분만 새 revision으로 다시 만들고 같은 관문을 다시 연다. 반복 상한 3.
- 대기 관문은 뒤쪽을 많이 푸는 순서로 보이고, `cfp report hil`이 관문별 대기·검토 시간·수정 반복·추천 일치를 낸다.
- 유료 표시 공급자 단계는 워크숍 실행에서 "실행 확인 대기"로 멈추고 "실행"을 눌러야 돈다.
- `scripts/check.sh` 515 passed(일회용 DB 적재 포함). 실제 공급자 호출 없음.

## 2. 이번 세션에서 한 일

- 문서: PRD v1.4 §8.11(FR-44~FR-47), 명세 v1.4 §7.1~§7.4, LLD v1.5 §3·§4·§5.16·§5.19~§5.21·§6.6~§6.10·§11·§12 M9, 계획서 `docs/product/2026-10-28-agentic-orchestration-plan.md`.
- A 갈래(주 에이전트): state.json 잠금·관문 사건 기록(`ledger/gate-events.jsonl`), `pipeline/scheduler.py`(`ready_stages`·`run_waves`·유료 단계), `run_until`의 `_step` 분리, `cfp run --parallel`, 워크숍 `request_resume`·held·confirm.
- B 갈래(하위 에이전트): `gate-review-v1`, `pipeline/review.py`, 관문 기록 `reviewRef`·`followedReview`, 관문 화면 추천 표시, `cfp review`.
- C 갈래(하위 에이전트): `rework-brief-v1`, `pipeline/rework.py`, G4a·G4b 챕터 부분 재생성, G5·G6 메모 반영, G1 수정 요청 뒤 얼굴만 다시, 반복 상한.
- D 갈래(하위 에이전트): `pipeline/queue.py`, `hil-report-v1`·`cfp report hil`, 작업실·운영 화면의 대기열 순서와 실행 확인 칩.
- E(통합): `tests/test_agentic_flow.py`(여성·남성 브리프, 작업 시작 1회 + 관문 결정만으로 내보내기까지, G4a·G4 수정 요청 포함), 브라우저 확인용 `scripts/agentic_demo.py`.
- 하위 에이전트 세 개는 `opencode-go/deepseek-v4.1-flash`로 각자 worktree(`../character-factory-poc-wt/{b-review,c-rework,d-queue}`)에서 일했고 브랜치 `codex/agentic-*`를 합쳤다.

## 3. 결정

- D-0049(제안), D-0050(제안: 세 질문을 제안값으로 진행, 검토 기록 위치, 반복 상한, G4a·G4b 챕터별 메모).

## 4. 확인한 사실과 정정

- 검토 기록을 단계 rev 폴더에 쓰면 G9 검토가 패키지 폴더에 파일을 더해 내보내기 해시 검사가 깨졌다. `reviews/`로 옮겼다(통합 시험에서 발견).
- 워크숍 G4a·G4b 수정 요청이 챕터 없는 메모 하나만 보내 부분 재생성이 안 되고 있었다. 챕터별 메모 칸으로 바꿨다(브라우저에서 발견).
- G1의 "뒤쪽 n단계"가 기획 갈래(s3 ← s2, 그래프에 없는 선행)를 빠뜨려 8로 나왔다. 16으로 고쳤다.
- 가짜 이미지 공급자는 같은 지시에 같은 그림을 내서, 브라우저 데모에서는 다시 만든 ch2 배경 사진이 그대로 보인다. 부분 재생성 자체는 `tests/test_rework.py`가 해시로 확인한다.

## 5. 미결

- K-0040: 실제 LLM·비전 검토 경로, 검토 프롬프트 품질, 사람 선택과의 일치율은 재 보지 않았다.
- Q-0020(비전 판정 경로), Q-0022, P-24 실제 공급자 확인, K-0039는 그대로다.

## 6. 다음 할 일

1. 사용자가 D-0049·D-0050 기본값을 확정하거나 바꾼다.
2. 사용자 지시가 있으면 실제 텍스트 판정 모델로 G3·G6·G7 검토를 한 캐릭터에서 돌리고 사람 선택과 비교한다.
3. Q-0020 확인 뒤 `[review] vision = true`로 이미지 관문 검토.

## 7. 떠 있는 것

- 일회용 Docker DB `cfp-verify-pg-1`. `scripts/verify_db.sh down`으로 내린다.
- worktree 세 개(`../character-factory-poc-wt/`)는 합친 뒤에도 남아 있다. 필요 없으면 `git worktree remove`로 정리한다.
- 브라우저 데모 데이터 `work/agentic-demo-1`(Git 제외).

