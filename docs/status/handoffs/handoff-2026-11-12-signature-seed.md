# 2026-11-12 시그니처 중간 프레임 시드

## 1. 지금 상태 한눈에

8776 PID81089, `work/signature-seed-runtime/factory-web.toml`. 시그니처 참고 사진이 있으면 S4가 기준 사진과 중간 프레임 시드를 함께 만들고, 확인 화면에서 두 이미지를 같이 승인한다. 공식 API 설정·기존 채팅·pv6/pv2는 그대로다.

## 2. 이번 세션에서 한 일

web/sources.py(poseReferencePath, 기준 사진 흐름에서만 업로드), stages/s4_frames/reference.py(시드 생성·signature-frame.json·G4 페이지), stages/s4_frames/approve.py(승인 시 middleFramePath 연결), web/reference_images.py(시드 URL·해시, 확인 시 해시 요구), studio/shared/reference.js·css(두 이미지 카드), studio/sources.html 안내 문구, 테스트와 PRD v1.33·spec v1.45·LLD v1.50·안내서를 고쳤다. 실제 인물 이미지·영상은 만들지 않았다.

## 3. 결정

D-0195. D-0194의 원본 직접 전달을 대체한다.

## 4. 확인한 사실과 정정

Python 244·Node 72 통과, 실행본 8건 통과. 정적 미리보기로 두 이미지 카드 확인. 기존 2,420파일 해시 변경0. D-0194 인계의 "원본 전체를 중간 프레임으로 사용"은 더 이상 사실이 아니다.

## 5. 미결

K-0125 갱신: 실제 이미지 모델의 손 모양 재현, 시드↔기준 사진 영상 전환 품질은 미검증. 참고 사진이 있으면 이미지 호출이 2회다.

## 6. 다음 할 일

실제 인물로 시그니처 참고 사진을 넣어 한 번 돌리고, 시드 품질과 시그니처 영상을 검수한다. commit/push는 하지 않았다.

## 7. 떠 있는 것

8776 서버 PID81089(제어 전 재확인). 임시 미리보기 서버는 종료했다. 증거: `work/signature-seed-20261112/deployment.json`, `work/signature-photo-20261112/two-image-card.png`.
