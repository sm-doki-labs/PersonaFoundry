# 인계: 2026-10-27 PoC H 갈래(통합)와 전체 흐름

이전 인계: [handoff-2026-10-27-poc-m8-2.md](handoff-2026-10-27-poc-m8-2.md)

## 1. 지금 상태 한눈에

- PoC(D-0044) 코드 범위가 끝났다. 여성·남성 합성 브리프가 가짜 공급자로 S1 → G9 → 패키지 → 우리 앱 일회용 DB 적재까지 간다. 모든 관문 결정은 워크숍 웹 API로 보냈다.
- `scripts/check.sh` 462 passed, 건너뜀 0(일회용 Docker DB 실제 적재 포함).
- 실제 설정은 학습이 dry run이라 s10에서 "학습 결과 대기"로 멈춘다(K-0038).
- 실제 공급자 호출은 아직 없다(P-24 범위는 사용자 지시 뒤).

## 2. 이번 세션에서 한 일

- 그래프: `s9s·s9·s10t·s10·s11·sx` `implemented=True`. 오케스트레이터 러너와 `RunOptions.training_providers`·`verify_export`, 평가 진입 조건(`_training_ready`), 사람 판정 관문 자동 승인 금지(`HUMAN_ONLY_GATES`).
- 관문: `approve_gate`에 G7a·G7·G8·G9.
- 명령: `cfp data plan|samples|build`, `cfp train plan|submit|collect`, `cfp eval prereg|run|judge|report`, `cfp release build`, `cfp export doki-app [--verify]`, `cfp web`, `cfp run --training-providers --verify-export`.
- 웹: G7a~G9 `connected=True`, `gate_items`에 실제 산출물 읽기(`data_samples`·`data_dataset`·`eval_report`·`release_package`).
- 테스트: `tests/test_offline_pipeline.py`(여성·남성), `tests/test_cli_poc.py`, "아직 연결 전"을 확인하던 웹 테스트 12개를 새 상태에 맞춤.

## 3. 결정

- D-0047(제안).

## 4. 확인한 사실과 정정

- 전체 흐름은 두 캐릭터 모두 오케스트레이터 8회 실행으로 끝까지 간다. 갈래가 동시에 진행된다(예: G4b와 G7a가 같은 차례에 대기).
- 가짜 학습 공급자는 평가 조건에 연결되지 않아 SFT 조건이 `UNBOUND`이고, G8 채택 후보는 긴 프롬프트뿐이다(K-0039).

## 5. 미결

- K-0011·K-0012·K-0037 해결. K-0038·K-0039 새로.
- Q-0022(순위 원자료 재사용 허락), P-24 실제 공급자 확인.

## 6. 다음 할 일

1. 사용자 지시가 있으면 실제 공급자 1회: `cfp ref collect --execute`(Q-0022 확인 뒤), 이미지(구독)·LLM(로컬 중계)로 S1~S8 한 캐릭터.
2. 워크숍 G7a~G9 화면을 브라우저로 확인(`cfp web` + 합성 루트).
3. K-0038 방향 결정: 학습 실행, 또는 G8 없이 긴 프롬프트 경로만으로 패키지를 만드는 경로.
4. 하위 에이전트 계약 보강 제안 반영(handoff-2026-10-27-poc-m8-2 §4, K-0039).

## 7. 떠 있는 것

- 일회용 Docker DB `cfp-verify-pg-1`(127.0.0.1:55439). `scripts/verify_db.sh down`으로 내린다.
- 저장소 밖: `/tmp/cfp-*.py`·`/tmp/cfp-*.json`·`/tmp/cfp-*.log`, `/tmp/cfp-rename-trial-*`. 지워도 된다.
