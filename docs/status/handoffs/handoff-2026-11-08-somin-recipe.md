# 인계: 한소민 구성 반영(D-0138)

이전 인계: [handoff-2026-11-08-emoji-only.md](handoff-2026-11-08-emoji-only.md)

## 지금 상태

- S9 학습 데이터는 학습용 짧은 프롬프트(페르소나 칸 + 사실 규칙 + 관계 + 채널 + 장면)로 만들고, 실제 대화 재료는 흐름 시드만 작가에게 준다. 한소민 검사 항목을 더했다.
- 실제 모델(시드 sol, 작가 Flash·Argon)로 같은 4구간을 다시 돌려 모두 흐름을 따랐고 길이 검사를 통과했다.
- 작업 폴더 `character-factory-poc-wt/foundry-screens`, 커밋하지 않았다.

## 한 일

1. `s9_data/training_prompt.py`, 자원 `training-prompt-components-v1.json`(사실 규칙·관계 4종·채널 4종).
2. `s9_data/seeds.py`, 역할 `prompts/data_seed.md`, 덱 작업 매핑 `data_seed → scenarios`.
3. `samples.py` 배정·시드·system 조립, `checks.py` 한소민 검사, `deck.py` 기계 검사 실패 때 다시 쓰기, `plan.py` 설정, 계약 `Provenance.relationship·channel`.
4. 작가 지침 `data_writer.md`·`data_deck_writer.md`.
5. 시험 4개 추가, 가짜 작성 모델 시드 응답. 문서 D-0138, K-0106·K-0107 해결, K-0108, LLD v1.29, PRD FR-24, 검증 기록.

## 확인

- 서버 1262 passed·1 skipped, 화면 노드 44 passed.
- 실제 모델 비교 `work/training-ui-20261108/real-writer-compare2.html`. 비용 추정 합계 약 $0.46(Argon은 공식 API).

## 남은 것

- S10 평가·서비스 내보내기에서 같은 학습용 프롬프트 쓰기(K-0108).
- 관계 문장을 캐릭터 말투에서 만들지, 핵심을 더 줄일지(한소민 699자 대비 3,295자).
- 시드 문장이 대사에 그대로 옮겨지는 경우 경고.
- OpenCodex Argon 사용량 소진(약 5.7일 뒤 풀림). 그 전에는 Argon을 공식 API로만 쓸 수 있다.
