# 인계: 학습용 짧은 프롬프트를 평가·서빙에 연결(D-0139)

이전 인계: [handoff-2026-11-08-somin-recipe.md](handoff-2026-11-08-somin-recipe.md)

## 지금 상태

- 학습·평가·서빙이 같은 학습용 짧은 프롬프트를 쓴다. S10 평가의 학습 모델 조건은 학습한 데이터셋의 `training-prompt.json`으로 만든 system(핵심 + 관계 + 영상통화 + 평가 장면)을 사전 등록에 고정하고, S11 서빙 기록은 같은 파일과 조립 규칙을 싣는다.
- 작업 폴더 `character-factory-poc-wt/foundry-screens`, 커밋하지 않았다.

## 한 일

1. `s9_data/training_prompt.py`: `load·find·eval_system·relationship_for_stage`, 자원에 평가 장면·서비스 채널·관계 단계 대응·조립 규칙.
2. `s10_eval/prereg.py`: `eval_relationship`, `sft_prompt`, 학습 모델 조건 promptRef.
3. `contracts/release.py` `Sft.trainingPrompt`, `SftServing.systemPrompt·systemAssembly`, `s11_release/package.py`.
4. 화면: 평가 비교 카드 문구, 데이터셋 요약의 학습용 프롬프트.
5. 시험 3개 추가·1개 보강. 문서 D-0139, K-0108 갱신, LLD v1.30, 검증 기록.

## 확인

- 서버 1265 passed·1 skipped, 화면 노드 44 passed. 가짜 공급자 흐름 밝은·어두운 화면 `work/training-ui-20261108/shots/ev/`.

## 남은 것

- 실제 서비스의 어댑터 런타임이 서빙 기록의 `systemPrompt`를 쓰게 하기(K-0108).
- 관계 문장을 캐릭터 말투에서 만들지, 핵심을 더 줄일지, 시드-대사 겹침 경고.
- 실제 GPU 어댑터로 평가 한 번(K-0100).
