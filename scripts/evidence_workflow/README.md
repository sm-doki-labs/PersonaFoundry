# 원문에서 예시 대사 없이 페르소나를 만드는 순서

S0의 corpus.jsonl, holdout.jsonl, digest.json과 승인된 FACTS 본문을 사용한다. 상대 말 → 본인의 첫 반응 → 초점 이동 → 상대에게 말을 넘긴 지점을 관찰하고, 어느 관계·장면에서만 성립하는 규칙인지 먼저 정한다. FACTS는 추출 모델이 다시 쓰지 않는다. 인물·원문·실행 결과는 이 디렉터리에 넣지 않는다.

1. prepare.py에 --corpus, --holdout, --digest, --profile, --out, --review PRIVATE_REVIEW.json을 주어 근거를 정리한다. 익명화 도구가 아니다. review에는 비공개 원문이 포함되므로 해당 인물 자료를 볼 수 있는 로컬 작업자만 열어야 한다. 평가 대화는 검토 자료에 넣지 않는다.
2. 추출지시문으로 관찰 후보를 만들고 검토지시문으로 근거·적용 범위·말차례 종료를 따로 검토한다. 제출 파일은 role, scene, sections 필드를 가진다. 예시는 넣지 않는다. 승인 카드 하나에는 다른 대화 묶음의 근거가 두 개 이상 있어야 한다. 근거가 한 건뿐인 명시적 사실은 반복 경향으로 만들지 않고 사실표의 별도 검토 절차로 보낸다.
3. 저장소 루트에서 아래 명령으로 승인된 입력을 검증하고 같은 프롬프트를 재생성한다. FACTS에는 제목이 아닌 승인 본문 원문을 준다. --out에는 버전별 새 작업 폴더를 사용한다.

    python3 scripts/evidence_workflow/form.py \
      --corpus "$SOURCE/corpus.jsonl" --holdout "$SOURCE/holdout.jsonl" \
      --digest "$SOURCE/digest.json" --profile scripts/evidence_workflow/메신저_분석설정.json \
      --approved "$REVIEWED_CARDS" --facts "$FACTS_FILE" --out "$OUT_DIR" \
      --compiler src/character_factory_poc/stages/s8_prompts/evidence_compiler.py

선택적으로 --approved 대신 --brief BRIEF.json, --author '["/absolute/local-author"]', --reviewer '["/absolute/local-reviewer"]'를 준다. 두 어댑터는 stdin으로 instruction·data JSON을 받아 stdout으로 지시문에 지정된 JSON만 반환한다. 도구에 모델 서버·어댑터가 내장돼 있지는 않다. 외부 전송이 허용되지 않는 데이터는 오프라인에서만 구동하는 별도 환경을 쓴다. 자동 경로에서도 원문 ID 잘못 인용, 누락된 검토, 독립 근거 부족은 빌드를 중단한다.

4. 한 번 고정한 후보는 평가 대화로 고치지 않는다. 실제 답을 가리고 두 판에 같은 문맥을 주어 다음 말을 생성한 뒤, 길이·표기와 반응의 적절성을 나눠 확인한다. 메신저의 짧은 확인과 회견의 조건 설명을 같은 평균으로 합치지 않는다. 합성 대화로는 기억 유도·정정·진지한 전환을 따로 점검한다. 소표본이나 AI의 판정만으로 실제 사용자가 인물을 알아본다고 결론내리지 않는다.

입력 패턴은 상대 발화를 표집할 단서이지 화행의 정답이 아니다. 메신저 설정은 30분 초과 공백, 연락·송금·미디어 표시를 경계로 쓴다. 다른 언어·대면록·인터뷰라면 간격, 장면 구분, 재전재 단위와 중복 정책을 먼저 맞춘다. 이 로컬 도구는 기본 생성 경로나 운영 서버를 자동 교체하지 않는다.

local_mlx.py는 Apple Silicon용 오프라인 어댑터다. mlx-lm이 설치된 파이썬과 이미 내려받은 instruct 모델 폴더가 있어야 한다. 호출 배열은 ["로컬 파이썬 절대경로","local_mlx.py 절대경로","모델 폴더 절대경로"]다. 같은 모델을 두 단계에 연결하는 것은 독립적인 품질 판정이 아니다. 모델이 자기 후보를 승인하더라도 근거가 하나뿐이거나 예시를 실은 카드는 앞단 검사에서 보류한다. 후보가 모두 보류되면 최종 프롬프트를 만들지 않는다. 재실행은 새로운 빈 출력 폴더에 남긴다.

친구의 두 번째 반응까지 이어지는 현상을 검토할 때는 [네 말차례 추출·검토 절차](후속반응_검토.md)를 사용한다. 이 선택 절차는 단일 답장용 표집과 기존 캐릭터 프롬프트를 변경하지 않는다.
