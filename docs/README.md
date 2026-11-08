# 문서 인덱스

프로젝트 개요는 [README](../README.md), 작업 규칙과 세션 절차는 [AGENTS.md](../AGENTS.md)에 있다.

## 읽는 순서

| 상황 | 먼저 읽을 것 |
|---|---|
| 처음 본다 | [README](../README.md) → [현재 상태](status/current-state.md) → [PRD](product/prd.md) |
| 작업을 이어받는다 | [현재 상태](status/current-state.md) → [알려진 문제](status/known-issues.md) → [인계 규칙](status/README.md)의 최신 인계 → [결정 기록](status/decisions.md) → [미결 질문](status/open-questions.md) |
| 기능을 바꾼다 | [PRD](product/prd.md) → [시스템 명세](architecture/spec.md) → [상세 설계](architecture/lld.md)(이 순서로 고친다) |
| 무엇이 안 되는지 본다 | [알려진 문제](status/known-issues.md) |
| 실제로 돌려 본 결과를 본다 | [검증 기록](status/verification.md), [보고서](#보고서와-안내) |

## 문서 목록

| 목적 | 문서 |
|---|---|
| 무엇을 왜 만드는지, 무엇이 성공인지 확인한다. | [PRD](product/prd.md) |
| 3일 PoC의 범위, 작업 갈래, 일정, 합격 기준을 확인한다. | [PoC 계획서 2026-10-27](product/2026-10-27-poc-plan.md) |
| 같은 공장 안의 실존 인물 갈래(손흥민·부모님 병렬 시연)의 구조, 모델 준비 방식, 영상 등급, 계획표를 확인한다. | [실존 인물 갈래 계획 2026-11-08](product/2026-11-08-real-person-track-plan.md) |
| 공정 단계, 에이전트 역할, 산출물 계약, 관문, ID 체계를 확인한다. | [시스템 명세](architecture/spec.md) |
| 패키지, 명령, 파일 형식, 알고리즘, 테스트, 구현 순서를 확인한다. | [상세 설계](architecture/lld.md) |
| 지금 공정이 실제로 어디까지 되는지, 사람이 처리할 일과 자료 위치를 확인한다. | [현재 상태](status/current-state.md) |
| 지금 안 되는 것(막힘·미검증·미구현·한계)을 확인한다. | [알려진 문제](status/known-issues.md) |
| 세션 간 인계 규칙과 최신 인계를 확인한다. 인계 문서는 `status/handoffs/`에 있다. | [인계 규칙](status/README.md) |
| 확정 결정과 제안을 구분해 확인한다. | [결정 기록](status/decisions.md) |
| 아직 정하지 않은 질문을 확인한다. | [미결 질문](status/open-questions.md) |
| 실제로 실행한 검증과 결과를 확인한다. | [검증 기록](status/verification.md) |
| 인계·결정·보고서 양식을 사용한다. | [양식 모음](templates/README.md) |

## 보고서와 안내

| 목적 | 문서 |
|---|---|
| 승인한 데이터셋으로 Gemma QLoRA를 실제 학습하고 체크포인트를 골라 평가·패키지까지 잇는 절차와 비용을 확인한다. | [QLoRA 실행 안내](guides/qlora-run.md) |
| 한소민처럼 실존하지 않는 새 인물의 데이터셋·클러스터 비율·평가·지속 개선 규격과 정책 파일을 확인한다. | [창작 인물 QLoRA 규격](guides/qlora-authored/README.md) |
| Gemini 개념 피드백과 새 츤데레 한지완 생성·실제40응답의 차이와 한계를 확인한다. | [새 캐릭터 실제 결과](reports/2026-10-30-tsundere-persona-live.md) |
| 서비스v6 기반 성향 프롬프트 구현과 실제96응답을 확인한다. | [구현·실제 비교](reports/2026-10-29-service-persona-runtime.md) · [제작 안내](guides/actor-persona.md) |
| 윤서진의 성격 전달 누락·예시 선정·말투 변환 경로를 프롬프트 관점에서 확인한다. | [프롬프트 감사](reports/2026-10-29-trait-persona-prompt-audit.md) |
| 형용사·추가 특질로 윤서진을 실제 생성하고 Gemini42응답의 품질을 확인한다. | [윤서진 제작·실제 Gemini 결과](reports/2026-10-29-trait-persona-gemini-live.md) |
| 기존 말투 자료 감사와 실제132응답의 개선 여부를 확인한다. | [실제 모델 검증](reports/2026-10-29-persona-choice-voice-live-validation.md) · [말투 자료 감사](reports/2026-10-29-voice-source-audit.md) |
| 선택·말투 분리 구현·검사·남은 실제 검증을 확인한다. | [구현 보고서](reports/2026-10-29-persona-choice-voice-implementation.md) · [코드 검토](reports/2026-10-29-persona-choice-voice-code-review.md) |
| 승인된 실제 말투 자료와 출처·정책을 연결한다. | [말투 자산 안내](guides/voice-assets.md) |
| 새 형성 프로필과 기본 품질 검증 명령을 사용한다. | [형성·품질 검증 안내](guides/persona-quality-runbook.md) |
| 구현된 페르소나 축(S3 import → S7 → S8 → G6)을 실제로 돌린다. | [페르소나 축 실행 안내](guides/persona-runbook.md) |
| 첫 실제 실행(P29 기반 윤도희)의 결과와 고친 것을 확인한다. | [실행 보고서 2026-10-14](reports/2026-10-14-dohee-p29-persona-run.md) |
| 도구를 가진 에이전트와 오케스트레이터로 명령 하나에 G6까지 간 실행을 확인한다. | [에이전틱 실행 보고서 2026-10-14](reports/2026-10-14-agentic-p29-run.md) |
| 선택 차이가 약해 보인 원인과 이전 판단의 범위 정정을 확인한다. | [기획·선택·관찰 원인 분석](reports/2026-10-29-persona-choice-cause-analysis.md) |
| 특질·선택 개선과 실제 말투 예시 적용의 새 계획·독립 검토를 확인한다. | [선택·말투 개선 계획](product/2026-10-29-persona-choice-voice-plan.md) · [서브에이전트 검토](reports/2026-10-29-persona-choice-voice-plan-review.md) |
| 새 공정 구현·실제4캐릭터·48응답 관찰과 한계를 확인한다. | [구현·개발 관찰](reports/2026-10-29-persona-quality-floor-implementation.md) · [대화 전체](http://127.0.0.1:8879/report.html) |
| 페르소나 형성 공정의 기본 품질 개선안과 독립 검토를 확인한다. | [개선 계획](product/2026-10-29-persona-quality-floor-plan.md) · [서브에이전트 검토](reports/2026-10-29-persona-quality-floor-plan-review.md) |
| 한소민 학습 근거를 분석하고 정본·프롬프트 공장 개선의107응답을 확인한다. | [분석·개선 HTML](reports/2026-10-29-somin-transfer.html) · [요약](reports/2026-10-29-somin-transfer.md) |
| 실제 기획·페르소나와 긴·짧은 134응답 품질을 확인한다. | [원문 HTML](reports/2026-10-28-persona-quality.html) · [요약](reports/2026-10-28-persona-quality.md) |

## 폴더 배치

| 폴더 | 내용 |
|---|---|
| `product/` | 요구사항(PRD) |
| `architecture/` | 시스템 명세, 상세 설계, 이후의 계약 문서 |
| `status/` | 현재 상태, 알려진 문제, 결정, 미결 질문, 검증 누적 기록 |
| `status/handoffs/` | 세션별 인계 문서(작성 뒤 고치지 않는다) |
| `guides/` | 실행 안내, 작업 지침 |
| `research/` | 조사 근거와 설계 논의(필요할 때 만든다. 지금은 없다) |
| `reports/` | 개별 실험·검토 보고서 |
| `templates/` | 재사용 양식 |

날짜가 있는 문서는 파일 이름에 `YYYY-MM-DD`를 넣는다.


- [추가 특질 추천 계획](product/2026-10-29-trait-recommendation-plan.md)과 [제작 안내](guides/trait-authoring.md)를 참고한다.

- [추가 특질 추천 구현·검증](reports/2026-10-29-trait-recommendation-implementation.md)은773개 검사와 실제 브라우저의 정상/장애 흐름을 기록한다.

- [텍스트 모델 덱·개발/테스트 경로 안내](guides/text-model-deck.md)와 [연결 계획](product/2026-10-30-text-model-deck-plan.md)을 참고한다.

- [글래스 시안·실제 텍스트 공정 연결 인계](status/handoffs/handoff-2026-10-30-text-studio-connection.md)는 DeepSeek 병렬 구현, 실제 설정·출처 API와 시연 각본의 구분을 기록한다.

- [실제 공장 화면 실행 안내](guides/agentic-studio.md): 기본 실제 모드, 요청·작업·검수·자동 재개와 시연 경계.

- [실제 에이전틱 공장 화면 연결 인계](status/handoffs/handoff-2026-10-30-agentic-studio-runtime.md): 시작·관문·자동 재개·실제 그래프·검증과 남은 경계.
