# 인계: 흐름 뼈대 재작성과 10글자 겹침 검사(D-0135)

이전 인계: [handoff-2026-11-08-source-mix.md](handoff-2026-11-08-source-mix.md)

## 지금 상태

- S9 `SNS_REWRITE`는 원본을 흐름 뼈대로만 쓴다. 작성 모델이 뼈대 3~8줄을 먼저 적고 장면과 양쪽 대사를 새로 쓴다. 원본과 10글자 이상 이어서 같으면 막는다(K-0099 구현).
- 작업 폴더 `character-factory-poc-wt/foundry-screens`(브랜치 `codex/foundry-screens`), 커밋하지 않았다.
- 사용자 질문 대기: 통화 장면의 ㅋㅋ·ㅠㅠ·^^·이모지를 막을지(D-0134 `voice_channel_spoken`). 서비스는 통화 중 캐릭터 말을 그대로 음성 합성으로 보낸다(`relationship-quest-chat` `voice_dispatch.py`, 걸러 내는 곳 없음). 답에 따라 검사·지시문을 바꾼다.

## 한 일

1. 계약: `Provenance.flowBeats`, 작성 출력 `flowBeats`.
2. `checks.py`: `overlaps`·`longest_overlap`, 차단 검사 `source_overlap`·`flow_beats`·`source_flow_turns`(옛 `sns_user_turns_verbatim` 제거), 장면 겹침.
3. 지시문: `data_writer.md`·`data_deck_writer.md` 흐름 뼈대 재작성 절차. 덱 수리는 뼈대를 잇는다.
4. `build.py`: 보고에 `rewrite=SKELETON`·`overlap`·`example`. 화면 재료 칸 '다시 쓰는 방식'에 겹침과 뼈대 예시.
5. 가짜 작성 모델: 양쪽 새로 쓰기·뼈대 3줄, `sns_bad_first`는 원문 베끼기.
6. 문서: D-0135, PRD FR-24, 명세, LLD v1.28, K-0103·K-0104, 원래 폴더 K-0099 메모, 검증 기록.

## 확인

- 서버 1258 passed·1 skipped, 화면 노드 44 passed.
- 실제 SNS·말뭉치 같은 조건: 36구간 모두 새로 씀, 원본과 가장 길게 겹친 곳 3글자, 막힘 0. 원문 상대 말을 그대로 두면 225구간 중 220구간이 막힌다.
- 밝은·어두운·휴대폰 폭 화면 `work/training-ui-20261108/shots/*-skel*.png`.

## 남은 것

- 실제 작성 모델로 소량(예: 4대화) 돌려 뼈대와 새 대사의 맥락 정합성을 본다. 가짜 모델 뼈대는 고정 문구다.
- 10글자 미만 말은 베껴도 못 잡는다. 작성 요청 기록에는 원문이 남는다.
- 20~36턴 장기 대화 재료, 검증에 통화 장면 넣기(K-0104).
