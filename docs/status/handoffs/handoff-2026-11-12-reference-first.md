# 기준 사진 확인 흐름 인계 — 2026-11-12

## 지금 상태 한눈에

D-0192 적용. 현재8776의 sources/factory에서 원문·사진·복장·배경→기준 사진 확인→영상6편. 프롬프트 분기 병렬, 확인 전 영상0. 기존2,101파일 변경0·pv6/pv2 유지. 미커밋.

## 이번 세션에서 한 일

- sources Draft referenceImage opt-in 및 단일 사진 검증, 프런트 복장/배경·기준 사진 카드·확인/재생성/영상 이어하기.
- SOURCE Lite 동적 그래프의 s4a/s4b 생략 및 단일9:16 사진. frozen inputs·원본 해시·기존 G4 계약.
- 자동 승인/등급 변경 정리에서도 G4 확인을 생략하지 않음. 확인은 revision/hash/입력 검사. 입력 변경·구버전 버튼 거절.
- 프롬프트 진행 중 확인 및 영상 시작. scheduler는 외부 확인을0.25초마다 확인한다. 승인 파일을 먼저 쓰고 G4를 공개하여 상태 경합 방지. 영상 실패 자동 재시도 금지.
- 실행본 work/reference-first-runtime/build.py는 이전 paused 제외 목록을 유지. 기존 채팅 wrapper와 config·데이터 root 유지.

## 결정

D-0192, PRD v1.30 → spec v1.42 → LLD v1.47. [제작 규칙](../../guides/call-loop-video.md).

## 확인한 사실과 정정

전체2238 passed·6 skipped·46 subtests, 활성 Node191 passed, 실행본34 passed. 독립 검토의 승인 파일 공개 순서 경합1건을 수정하고 회귀 검사 추가; 최종 high/medium 잔여없음(코드검토). CUA는 합성 자료/fake 공급자만 사용, 실제 Python 서버의 시작/사진표시/확인/6편완료를 확인. 최초 임시서버는 pytest 자동fixture 누락으로 S3 synthetic JUDGE 응답이 없어 실패했고 fixture 추가 후 새 합성 캐릭터로 완료했다. 실패 기록도 임시폴더에 남긴다. 기존 quality-status4실패는 중단 작업이며 활성검사에서 제외했다.

## 미결

K-0123: 실인물 기준 사진의 동일성·복장·배경·구도와 실제 영상6편의 손/표정/연결 품질은 미검증. K-0122 장기부하 미검증 유지. 서버 중단 시 확인된 사진의 이어 하기 버튼으로 명시 재개 가능.

## 다음 할 일

사용자가 실제 자료 생성을 요청하면 새 초안을 만들어 기준 사진을 먼저 확인받는다. 영상6편의 G5b 품질은 별도 직접 확인한다. 기존 pv6를 교체하지 않는다. 이전 인계의 실영상 생성 대신 이번 승인된 프론트 흐름을 먼저 구현했다.

## 떠 있는 것

8776 PID48322. work/reference-first-runtime/serve.py·factory-web.toml. 임시8787/8788 종료. 사용자 결과 `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/reference-first-20261112`. 기존루트 `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-tendency-live/factory`.
