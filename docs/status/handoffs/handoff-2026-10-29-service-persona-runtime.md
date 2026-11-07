# 인계: 현행 서비스 기반 성향 프롬프트와 실제96응답

## 지금 상태 한눈에

- 사용자의 추가 지시대로 특질을 정규화된 성격 문장으로 통합하고, 실제 runtime을 서비스 v6의 여덟 persona 섹션에 맞췄다(D-0070·0071).
- runtime 예시·세 챕터·activeWhen 등 조건 필드·제작자/출처 표기는 제외했다. 단일 RuntimeContext만 받는다. 구형 조립/선정은 과거 재현과 내부 검토용이다.
- 윤서진 pr1 고정→새 실제 tr2/pv2, 최종3045자, G6 대기·정식 NOT_RUN / NOT_QUALIFIED다.
- 실제107요청/소비96응답, 소비 잘림0·재추첨0, 보존 판정 형식 재시도1. 최종785 passed/1 skipped·기존 경고1, lint/format·wheel 확인을 마쳤다.
- 자기 태도/짧은 장난은 더 관측됐지만 감정 대화·표현 강도는 혼합이다. 제품의 형성 품질 보장과 현행 서비스 대비 우열은 미입증이다.

## 이번 세션에서 한 일

[구현·실제 결과](../../reports/2026-10-29-service-persona-runtime.md), [제작 안내](../../guides/actor-persona.md), [정정된 실행 계획](../../product/2026-10-29-trait-persona-prompt-fix-plan.md)을 읽는다. 초기에 성격 누락 복원/예시 선정 개선을 계획했으나, 사용자 추가 지시에 따라 runtime 구조 교체로 범위를 정정했다. 예시 선정 알고리즘은 바꾸지 않았다.

새 계약/조립은 contracts/actor_persona.py와 stages/s8_prompts/actor_persona.py, 규칙은 resources/actor-system-rules-v1.md다. S7은 실제 styleEvidence를 받아 개인별 말투 문장을 쓰고, S8은 기본 성격·선택 특질을 같은 disposition에 합친다. compiler는 actor-tendencies-compiler-v3이며 bundle examplesUsage=review-only다. 출처와 검증 조건은 source assets에 남는다.

실험은 `runs/experiments/20261029-service-persona-runtime-r1/`다. A는 기존6683자, B는 같은 원천의 새2874자 조립, C는 새 실제 형성3045자다. 고정 이력36+독립 누적60=96첫응답을 기록했다. final-system-prompt.txt, actor-profile-C.json, dialogues.txt, summary.json, consumer-audit.json, final-observations.json을 보존했다. 스크립트는 `scripts/persona_service_runtime_live_20261029.py`, 작업/검토 로그는 `work/trait-persona-prompt-fix-20261029/`다.

## 결정

- D-0070: runtime은 서비스 기반 섹션/성향이며 내부 규칙표·예시·전체 챕터를 넣지 않는다는 사용자 확정이다.
- D-0071: 새 actor projection·버전 호환·실험 범위의 구현 제안이다.

## 확인한 사실과 정정

이전 v2의 기본 성격 누락은 새 actor 경로에서 본문 검증까지 연결했다(K-0054). 구형 v2 본문은 과거 재현용으로 남긴다. 내부 source hash만 확인하지 않고 실제 profile/body를 재현한다. 새 compiler를 구형으로 위장하는 경로는 recipe/compiler/자산 종류와 구형 본문 재현으로 막았다. 서브에이전트 지적3건은 재현 RED→GREEN/전체785검사로 확인했고 사후 독립 재검토는 하지 않았다.

Sonnet 첫 순위는 C3/A2/B0으로 assistant 원문 판단과 달랐다. 지각 때 필요를 먼저 묻지 않음/맞칭찬 생략을 major로 본 두 라벨은 현재 경향성 요구와 맞지 않아 배제했다. 판정은 보존했다. 단일 사례·새 누적최대6턴·사람 투표0으로 품질을 보장하지 않는다. C의 날선 자존심·과한 사과·사용자 경험 추정은 남는다.

입력409570+보수적출력87768=497338토큰, 가정환산USD18.72356/청구미확인, 마지막응답23.52분이다. 모든107요청/응답 해시와96이력·107예약 정산을 검증했다. 과거 실험516파일·실행 중 제품329파일 해시가 유지됐다. 다른 저장소는 읽기만 했다. commit/push/배포/학습은 없다.

## 미결

K-0053의 표현/개성 균형, K-0052의 의미/조합/효과 일반화는 미완료다. K-0055에 자동 검토가 경향을 필수 절차로 오판하는 문제를 남겼다. 기존 K-0047 및 K-0049~51의 정식/과거 미달은 유지한다. 새 사용자 질문(Q)은 없다.

## 다음 할 일

1. 후속 요청 시 현재3045자 actor와 동일 장면/모델을 기준으로, 성향의 강도와 표현의 균형을 여러 인물에서 확인한다. 답변 길이/반말/절차 실행을 품질로 대체하지 않는다.
2. 검토 기준은 사실·동의·상태의 필수 계약과 성향 구현을 분리한다. 과거 firstMove를 매번 실행해야 하는 정답으로 주지 않는다. 기존 자동판정을 수정했다고 과거 결과를 덮지 않는다.
3. 현재 관계를 모든 장면에서 명시한 별도 표본·긴 누적 대화·사람 블라인드를 준비한다. 운영 서비스가 더 좋아졌다는 주장은 실제 wire와의 대조 뒤에 한다.

## 떠 있는 것

없음. 생성·소비·판정과 독립 검토는 종료했다. 실험/작업 로그는 위 경로에 보존했다.
