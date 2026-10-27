# 인계: 2026-10-28 학습 없이 패키지까지(K-0038)와 G7a~G9 브라우저 확인

이전 인계: [handoff-2026-10-27-poc-h.md](handoff-2026-10-27-poc-h.md)

## 1. 지금 상태 한눈에

- 학습 결과가 없으면 G8이 "학습 없이 진행" 결정을 연다. 긴 프롬프트를 고르면 SFT 평가 없이 패키지·내보내기까지 간다(D-0048). K-0038 해결.
- 기본 `cfp run`은 학습을 계획(dry run)만 한다. 제출은 `--submit-training`.
- 워크숍 G7a~G9를 브라우저로 눌러 확인했고, 찾은 화면 문제 7가지를 고쳤다.
- `scripts/check.sh` 464 passed(일회용 DB 실제 적재 포함). 실제 공급자 호출 없음.

## 2. 이번 세션에서 한 일

- `src/character_factory_poc/stages/s10_eval/prompt_only.py`(`eval-prompt-only-v1`, `open_prompt_only`, `approve_prompt_only`), `approve_g8` 분기, 오케스트레이터 s10·s10t, 패키지 `collect_sft`(채택은 G8 기록에서, 평가 보고서는 G8 승인 revision에서), `cfp run --submit-training`.
- 웹: G8 `promptOnly` 화면(`gate.js`), 화면별 제목(`items.title`), G7a 판정 완료 표시와 다음 클러스터 자동 선택, 전송 후 busy 해제와 성공 메시지 유지, G8 지표는 블라인드 20쌍을 다 고른 뒤 열림, G9 SFT 칸 "학습 없이 긴 프롬프트로 진행", 좁은 폭 상단바, "결정 완료" 표기.
- 테스트: 전체 흐름에 학습 없이 진행·학습을 기다린다 두 경로 추가. SFT 경로는 `submit_training=True`로 명시.
- 브라우저 확인용 `scripts/build_late_gates_demo.py`.

## 3. 결정

- D-0048(확정, 구현 기본값은 제안).

## 4. 확인한 사실과 정정

- G7a는 클러스터마다 따로 보내는데, 화면이 첫 전송 뒤 busy를 풀지 않아 두 번째부터 조용히 무시됐다. API 테스트로는 드러나지 않았다(브라우저에서만 발견).
- G8 지표 표가 블라인드 판정 전에 조건 이름과 값을 보여 줘 블라인드를 깨고 있었다.

## 5. 미결

- K-0039(프로필 카드 네 칸, 가짜 학습의 평가 조건 연결)는 남아 있다.
- Q-0022, P-24 실제 공급자 확인.

## 6. 다음 할 일

1. 사용자 지시가 있으면 실제 공급자로 한 캐릭터: 순위 수집(Q-0022 확인 뒤) → 이미지·LLM으로 S1~S9 → G8 "학습 없이 진행" → 패키지 → 적재 확인.
2. K-0039 계약 보강(새 revision).

## 7. 떠 있는 것

- 일회용 Docker DB `cfp-verify-pg-1`. `scripts/verify_db.sh down`으로 내린다.
- 워크숍 서버는 내렸다. 데모 공장 `work/late-gates-demo-1·2·3`(Git 제외)은 지워도 된다.
