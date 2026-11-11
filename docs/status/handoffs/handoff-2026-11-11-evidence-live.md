# 2026-11-11 원문 근거 공정 실제 실행 검증

## 지금 상태 한눈에

오익준 승인 sp1·pr4·tr1 사본에서 공장 S8을 실제 실행해 pv2를 생성했다. n8n은 사용하지 않았다.
80개 표본→카드 5개→8섹션 982자이며 G6는 AWAITING_HUMAN이다.
실제 원문 대조에서 과잉 해석과 적용 한계 누락을 확인했고 새 판은 승인하지 않았다.
Gemini 4장면×2판, 8답변을 직접 읽었다. 추출 포함 성공 9회·시간 초과 1회, 총 10회다.
기존 승인 원본·기존 표준판·원문은 변경하지 않았다. 배포·내보내기·commit/push는 하지 않았다.

## 이번 세션에서 한 일

- 실행: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-live/run.py --execute`가 실제 `run_s8`과 Vertex Gemini를 호출했다. 공장의 전체 앞 단계를 다시 생성한 것은 아니다.
- 검증: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-live/verify.py`로 원본 해시·새 manifest·현재 원천 결속·사실 보존·예시 없음·일반 시연 차단을 확인했다.
- 응답: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-live/evaluate.py --execute`, 시간 초과 뒤 `--retry-suffix '~manual-timeout1'`로 미저장 한 건만 다시 불렀다. 기존 결과는 재생성하지 않았다.
- 직접 평가: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/work/evidence-live/extraction-direct-review.json`, `evaluation/direct-blind-review.json`. 평가 기준과 생성 조건을 먼저 고정했고 A/B를 읽어 기록한 후 대응표를 열었다. 독립 사람 블라인드 실험은 아니다.
- 결과: `/Users/johnhuh619/Documents/Codex/2026-11-11/n8n-4-codex-threads-01a1c617-ec03-2/outputs/공정_실행검증/실행검증_보고서.md`, `오익준_공정생성_pv2_미승인.md`, `실행검증_기록.json`.

## 결정

D-0175: n8n 없는 자체 실행을 명확히 했다. 자동 생성 품질 승인을 추가하지 않았다.

## 확인한 사실과 정정

기존 인계의 ‘외부 n8n 미반영’은 필요 작업이 아니다. 연결은 이미 공장 자체 경로다.
구조상 서로 다른 근거가 여럿이어도 각 세부 주장이 모두 반복 관찰된 것은 아니다. 좌석·콘센트는 인용 근거에 없었다.
추출 카드의 limit은 존재하지만 rule 요약에서 빠지고 조립은 rule만 사용했다. 실제 응답에서 맥락에 없는 작업 계획과 콘센트를 추가했다.
기존 표준판도 계정 부재를 졸업 때문으로 추정하는 한계가 있었다. 네 재사용 평가 장면으로 전체 승률이나 새로운 자료 일반화를 주장하지 않는다.
성공 응답은 1.54~2.91초였으나 한 요청이 180초 read timeout이었다. 실패 예약을 유지한 비용 가정 합계는 약 $0.126이며 실제 청구액은 미확인이다. 실행 제한은 최대 16회/$2였다.

## 미결

K-0116을 실제로 확인된 품질 한계로 갱신했다. 자동 추출 후보의 의미 검토와 배포 서버 반영은 남아 있다. 새 사용자 질문은 없다.

## 다음 할 일

1. 카드의 여러 주장을 각각 근거에 연결해 ‘약속 수락’의 반복 근거가 ‘콘센트 선호’의 근거가 되지 않게 한다.
2. trigger/first/shift/stop/limit의 필요한 조건이 최종 규칙에서 사라지지 않게 조립과 검토를 보완한다. 대사 예시나 인물별 정답은 넣지 않는다.
3. 새 revision에서 같은 결함을 재검증한 뒤 별도 미사용 장면과 후속 대화로 넓힌다. 현 pv2를 손으로 고쳐 승인한 것으로 취급하지 않는다.

## 떠 있는 것

없음. 실제 요청은 모두 종료했다. 시간 초과 한 건의 비용 예약만 보수적으로 남겼다. 원문·실험 사본은 위 work 폴더에 보존했다.
