# 추가 특질 추천 구현·검증

2026-10-29. 사용자 요청은 내부 제작자가 형용사로 기본 성격을 쓰고 보유한 특질을 추천받아 편하게 추가하는 흐름이다. [계획](../product/2026-10-29-trait-recommendation-plan.md), [제작 안내](../guides/trait-authoring.md), D-0066·D-0067을 따른다.

## 구현 결과

- 48개 허구 저작 프리셋의 행동 표현144개를 출처 hash/presetId/field path와 함께 내장했다. 원본과144/144 literal 일치를 확인했다. 원래 파일은 바꾸지 않았으며 개인의 측정값·실제 과거·SNS 원문은 넣지 않았다.
- 형용사 자유 입력으로 한 화면 최대5개를 추천하고 직접 검색·둘러보기·제외·추가·제거를 제공한다. 추천은 로컬 어휘 매칭이고 선택은 optional이다. 같은 추천 분류/저작 domain이 반복해 목록을 채우지 않도록 분산한다. 이 domain은 저작 태그로만 사용한다.
- 추가 특질은 원래 성격과 신원에서 분리한 selectedTraits로 새 씨앗 revision에 저장한다. 실제 카탈로그에서 ID를 해석하고 원문/출처를 확인하므로 클라이언트가 보내는 임의 행동을 신뢰하지 않는다. 이전 revision은 보존한다.
- 웹과 CLI가 같은 상태/씨앗 잠금·기준 revision 검사를 사용한다. 진행/검토/승인 중인 기획과 다른 화면에서 바뀐 씨앗을 조용히 변경하지 않는다.
- S3가 후보마다 선택 원문을 결합하고 v2의 고정 요구에 추가한다. 연결된 행동 규칙과 실제 행동 근거가 없는 경우 의미 검토의 PASS만으로 승인되지 않는다. S7 입력과 v1/v2·구형 long/short 최종 disposition에도 선택 행동이 남는다.
- 워크숍 첫 화면에서 제작 화면으로 들어간다. 성격만 필수이고 직업/배경 등의 부가 정보는 접을 수 있다. 추천 조회가 실패해도 선택0개로 기본 성격을 저장할 수 있다. 저장은 유료 생성·관문 승인을 시작하지 않는다.

## 실행한 검증

| 검증 | 실제 결과 | 근거 |
|---|---|---|
| 작업 전 기준 | 742 passed,1 skipped,기존 경고1 | `work/trait-recommendations-20261029/baseline-check.log` |
| 최종 전체 검사 | **773 passed,1 skipped**,기존 Starlette 경고1,79.88초. lint/format 통과 | `work/trait-recommendations-20261029/final-check.log` |
| 새 기능 중심 | 31 passed,기존 경고1 | `work/trait-recommendations-20261029/final-targeted.log` |
| 독립 검토 | R1 CLI 보호, R2 metadata-only 증거, R3 optional 조회 장애, R4 탈락 후보의 프리셋 선점 모두 재현 후 수정·재확인 | `review.md`, `review-followup.md`, `review-final.md` |
| 실제 브라우저/API | 성격 입력→추천→2개 추가→검색 중 선택 유지→sd1 저장, 카탈로그 GET503→전부 해제→sd2 빈 선택 저장, 복구→2개 선택→sd3 저장. 성격 원문 유지, 생성 작업0 | `browser-verification.json`, `creator-selected.png`, `creator-saved.png` |
| 원천 일치 | 원본 hash와 144개 행동/ID/필드 일치 | `catalog-verification.json` |
| 최종 wheel | 내장 자료·화면·JS·CSS 포함 및 현재 자산 바이트 일치. 저장소 밖에서 추출 wheel만으로144개 로드·추천 통과 | `wheel-final-verification.json` |

위 상대 경로의 검증 파일은 저장소의 `work/trait-recommendations-20261029/`에 있다. 브라우저는 합성 캐릭터 시험 루트에 연결했고 실제 생성 모델을 호출하지 않았다. 스크린샷의 선택과 저장도 이 합성 시험 데이터다. 기존 실제 모델 실험 산출물은 수정하지 않았다.

최종 wheel SHA256: `87efc30e4d9c3093d426c483320999afb1901fce87ebdc3a2a4358e4686f7b07`.

## 판단 범위

추가 특질 추천·선택 저장·전달 기능을 검증했다. 추천은 모든 형용사의 의미나 부정/모순을 이해하는 판정기가 아니며 추가 행동의 조합 적합성도 보장하지 않는다(K-0052). 기존 의미 검토와 제작자 관문을 유지한다. 이번 작업에서 실제 모델의 캐릭터 생성·대화 품질은 다시 측정하지 않았고, 이전0/4 첫 형성과 선택/자연스러움 미달(K-0049~51)을 해결했다고 주장하지 않는다. 실제 모델 호출·학습·배포·commit/push는 하지 않았다.
