# 시그니처 중간 사진 몸 폭 고정 (2026-11-13)

- 원인: S4 시그니처 중간 사진을 OpenAI 이미지 모델로 만들면 몸통이 기준 사진보다 1.08~1.14배 넓게 그려져, S6 영상이 그 사진을 지나며 옆으로 늘었다 줄었다.
- 변경(미커밋, S4·S6 기준 사진 흐름 코드와 같은 미커밋 상태):
  - providers/xai_images.py: Grok 이미지 편집(grok-imagine-image-2.0, /v1/images/edits, 참조 최대 5장, PNG 재인코딩). factory 어댑터 xai_images.
  - Context.signature_image_model: [providers.signature_image]가 있으면 그 모델, 없으면 이미지 모델.
  - s4_frames/reference.py: 모든 시그니처 공통 BODY_LOCK과 부정어(넓어진 어깨·확대·재구도). POSE_TEMPLATES camera_click: 손 위치·윙크 템플릿. 다른 포즈는 사용자 동작 설명을 그대로 쓴다.
  - s6_actions/call_loop.py: 모든 영상 공통 BODY_LOCK(Identity Preservation)과 Motion의 폭 유지 문장. CAMERA_CLICK을 같은 손 위치·윙크 묘사로 교체.
  - factory.example.toml: [providers.signature_image] Grok 블록. 테스트 tests/test_signature_seed_body.py. 전체 2,372 passed·6 skipped.
- 실측: work/signature-v2-20261113(dual-s3-hybrid 손흥민 사본, 실행본 work/signature-v2-runtime). S4 fr2 68.6초, G4는 사용자 요청 재실행으로 에이전트가 승인, S6 va2 6편 63.1초. 중간 사진 몸통 폭 1.00~1.02배, 영상 아랫몸통 폭 전 구간 1.00배(이전 영상 최대 1.32배).
- 남은 것: 윙크는 약하다. 다른 5편 육안 검토 전. 실서버(8776·8781~8783)에는 반영하지 않았다.

- 확정(2026-11-13): 사용자가 이 방식을 표준으로 확정했다. D-0203.
