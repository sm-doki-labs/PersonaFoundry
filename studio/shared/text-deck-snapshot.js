// 시연 각본의 모델 배정 스냅샷. 실제 실행 출처는 /api/text-pipeline에서 별도로 읽는다.
window.FACTORY_TEXT_DECK_SNAPSHOT = {
  "source": "model-deck-v2",
  "purpose": "simulation-config-snapshot-not-run-evidence",
  "profile": "basic_test",
  "route": "opencodex",
  "tasks": {
    "brief": {
      "label": "기본 프로필·배경·제약 정리",
      "model": "gpt-6.1-sol",
      "reasoningEffort": "high"
    },
    "personality": {
      "label": "성격·행동 원리·관계 변화 초안",
      "model": "google-antigravity/gemini-3.8-flash",
      "reasoningEffort": "high"
    },
    "consistency": {
      "label": "성격 초안의 명시적 설정 충돌 검토",
      "model": "gpt-6.1-sol",
      "reasoningEffort": "high"
    },
    "voice": {
      "label": "성격 확정·최종 말투·대표 대사",
      "model": "google-antigravity/gemini-3.8-flash",
      "reasoningEffort": "high"
    },
    "scenarios": {
      "label": "SFT 상황 분포·사용자 발화·사실 맥락 설계",
      "model": "gpt-6.1-sol",
      "reasoningEffort": "medium"
    },
    "sft_answers": {
      "label": "학습 대상 답변과 말투가 필요한 과거 assistant 발화 생성",
      "model": "google-antigravity/gemini-3.8-flash",
      "reasoningEffort": "high"
    },
    "screening": {
      "label": "설정 충돌·화자 혼동·문맥 오류 전수 검사",
      "model": "gpt-6.1-terra",
      "reasoningEffort": "high"
    },
    "adjudication": {
      "label": "검수 이견·통과 및 탈락 표본 재검토",
      "model": "gpt-6.1-sol",
      "reasoningEffort": "high"
    },
    "repair": {
      "label": "확인된 오류만 수정하고 캐릭터성 유지",
      "model": "google-antigravity/gemini-3.8-flash",
      "reasoningEffort": "high"
    }
  }
};
