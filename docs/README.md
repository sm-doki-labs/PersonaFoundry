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
| 구현된 페르소나 축(S3 import → S7 → S8 → G6)을 실제로 돌린다. | [페르소나 축 실행 안내](guides/persona-runbook.md) |
| 첫 실제 실행(P29 기반 윤도희)의 결과와 고친 것을 확인한다. | [실행 보고서 2026-10-14](reports/2026-10-14-dohee-p29-persona-run.md) |
| 도구를 가진 에이전트와 오케스트레이터로 명령 하나에 G6까지 간 실행을 확인한다. | [에이전틱 실행 보고서 2026-10-14](reports/2026-10-14-agentic-p29-run.md) |

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

