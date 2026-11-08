# 인계: SNS·말뭉치 출처 섞기(D-0134)

이전 인계: [handoff-2026-11-08-training-ui.md](handoff-2026-11-08-training-ui.md)

## 지금 상태

- S9 실제 대화 재료를 출처별로 나눠, 말뭉치(NIKL) 구간은 통화 장면으로 20%만 SNS 사이에 섞는다. 작업 폴더는 `character-factory-poc-wt/foundry-screens`(브랜치 `codex/foundry-screens`)이고 커밋하지 않았다.

## 한 일

1. `s9_data/samples.py`: `source_kind`·`source_channel`·`_mix`, `read_sns_sources(..., corpus_share)`가 구간마다 `source`·`channel`을 붙이고 `bySource`·`over_share`를 센다. 경고 한 줄에 출처별 쓴 수. 작성 요청 `sources`에 `origin`·`channel`.
2. `plan.py`: `corpus_share`(기본 0.2, 0~1). `build.py`: `usedBySource`.
3. `checks.py`: 차단 검사 `voice_channel_spoken`(통화 원본의 캐릭터 말에 자모·^^·이모지 금지).
4. 지시문: `data_writer.md`(채널 규칙이 메신저 말투보다 우선, 통화 장면 쓰는 법), `data_deck_writer.md` 같은 규칙.
5. 화면: 재료 칸 '실제 대화 후보'·'출처별' 줄, 범례·요약 이름을 '실제 대화'로. `web/model_path.py` `sources.bySource`·`corpusShare`.
6. 시험 3개, 문서: D-0134, Q-0007 첫 값, K-0103 갱신, K-0104, LLD v1.27, 검증 기록.

## 참고한 기준

- 학습 가이드(`/Users/johnhuh619/Documents/Codex/2026-10-14/gem/somin-qlora-project/docs/데이터셋-프롬프트-구축-가이드.md`) §3.3 채널, §7.1 SNS 사용 규칙, §8 말투.
- 한소민 장기 대화 생성 지침(`~/projects/gemini-sft-poc/.work/somin-sft-diagnosis-2026-10-17/gen/BRIEF.md`).
- 공장 마스터 지시서 MD-1.6(`docs/guides/character-prompt-master-directive.md`).

## 확인

- 서버 1257 passed·1 skipped, 화면 노드 44 passed.
- 실제 AI Hub SNS 40세션 + NIKL 30구간, 목표 120대화: 쓴 36구간 = SNS 29 + 말뭉치 7. 밝은·어두운 화면 `work/training-ui-20261108/shots/*-mix*.png`.

## 남은 것

- 가이드 §7.1과 어긋남: 상대 원문을 글자 그대로 둔다. 흐름 뼈대만 쓰고 양쪽 대사를 새로 쓰는 재작성과 10글자 겹침 검사(K-0099, K-0104).
- 20~36턴 장기 대화 재료가 없다(구간 4~12턴). 검증에 통화 장면이 들어가게 분할 맞추기(K-0104).
- 실제 작성 모델로 통화 장면 소량 확인, 자료 이용 조건(Q-0019), 창고 색인·클러스터별 검색(K-0098, K-0103).
