# QLoRA 실제 학습·평가 실행 안내 (D-0077)

이 안내는 G7에서 승인한 데이터셋으로 Gemma 4 31B QLoRA를 실제로 학습하고, 체크포인트를 고르고, 평가와 패키지까지 잇는 절차다. 학습 설정은 머스크 N3b에서 결과를 낸 방식이 기본값이며, 근거와 구현 세부는 [상세 설계 §21](../architecture/lld.md)에 있다. 창작 인물의 데이터·평가 기준은 [창작 인물 QLoRA 규격](qlora-authored/README.md)을 따른다.

## 1. 준비

`factory.toml`에 [factory.example.toml](../../factory.example.toml)의 `[stages.s10t]`·`[stages.s10t.gemma_qlora]`·`[stages.s10]` 절을 옮긴다. `vastai_bin`에는 로그인된 vastai CLI 경로를 적는다. API 키는 vastai CLI 설정에 있고 공장은 키 값을 읽지 않는다. SSH 키는 `~/.ssh/id_ed25519(.pub)`를 쓰며, GPU를 빌릴 때마다 공개 키를 그 인스턴스에 붙인다. 계정에 등록된 키는 쓰지 않는다.

창작 인물 정책을 쓰려면 `[stages.s9] policy = "qlora-authored-v1"`을 넣고 S9부터 다시 계획한다. 정책을 켜면 15~30턴 긴 대화 클러스터와 턴 분포 검사가 함께 들어간다.

## 2. 비용을 먼저 본다

`cfp train plan <캐릭터>`는 호출 없이 예상 비용을 낸다. 학습 시간은 `ceil(학습 대화 × 2 epoch / 4) × 8.7초 + 준비 900초`, 선별은 `(36출력 × 체크포인트 4개 + 기반 모델 36출력) × 12초 + 420초`로 잡는다. 학습 640대화라면 학습 약 1.0시간, 선별 약 0.7시간으로 합계 약 1.7시간이고, 시간당 상한 $0.90 기준 약 $1.6이다. 실제 단가는 고른 GPU 제안에 따라 낮을 수 있으며, 실측은 `lease.json`의 잔액 전후로 확인한다.

## 3. 학습부터 체크포인트 선택까지

`cfp train drive <캐릭터> --execute`가 GPU 임대 → 데이터 전송 → 학습 → 같은 GPU의 선별 생성 → 회수(해시 확인) → 체크포인트 선택 → GPU 삭제를 끝까지 진행한다. `cfp run --execute --submit-training`도 같은 경로를 탄다. GPU를 빌리기 전에 분리 감시 프로세스(guard)가 먼저 뜨고, 공장 프로세스가 죽거나 노트북이 잠들어도 마감 시각(학습 상한 + 준비 대기 + 회수 여유 2시간)이나 잔액 하한에서 GPU를 지운다. 학습 중 예외·Ctrl-C·종료 신호가 오면 로그를 남기고 GPU를 지운다. 학습이 끝난 뒤 회수만 실패하면 결과를 지키려고 GPU를 남기고 멈추므로 `cfp train collect <캐릭터> --execute`로 다시 받은 뒤 `cfp train cleanup`을 한다. 같은 명령을 다시 돌려도 지워지지 않은 임대 기록이 있으면 새 GPU를 빌리지 않고 이어 간다.

결과는 `s10-train/tr<k>/gemma_qlora/`에 남는다. `training-run.json`의 binding이 고른 체크포인트를 가리키고, `checkpoint-selection.json`에 결함 지표·짝 판정·결정값이 있다. 결정값이 `KEEP_INCUMBENT`면 같은 짧은 프롬프트의 기반 모델이 어댑터보다 나았다는 뜻이고, `BLOCKED_*`면 쓸 체크포인트가 없다는 뜻이다. 두 경우 모두 binding을 남기지 않으므로 평가 단계가 학습 없이 진행할지 G8에서 묻는다. 판정 모델을 끈 경우의 `INCONCLUSIVE`는 결함 기준만 통과한 마지막 체크포인트를 넘긴 것이다.

## 4. 평가와 패키지

`cfp eval prereg <캐릭터>` 뒤 `cfp eval run <캐릭터> --execute`를 돌리면 SHORT_GEMMA_SFT 조건은 GPU를 다시 빌려 어댑터 서버로 답을 받는다. 비용은 `(턴 수 × 10초 + 900초) × 시간당 요금`이고 `gpu_budget_usd`를 넘으면 시작하지 않는다. 네 세트 전체(약 900턴)는 약 2.7시간·$2.5로 계산된다. 판정·보고서 뒤 G8에서 사람이 채택을 정하고, Gemma 어댑터가 채택되면 S11 패키지에 `sft/serving.json`이 생긴다.

## 5. 남은 GPU 정리

`cfp train cleanup <캐릭터> --execute`는 모든 학습 revision과 평가 세션의 임대 기록을 훑어 남은 GPU를 지우고, ID 없이 남은 기록은 라벨로 찾아 지운다. Vast 화면에서도 `cfp-`로 시작하는 라벨이 남지 않았는지 확인한다.

## 6. 아직 실제로 확인하지 않은 것

2026-11-02 현재 이 경로는 가짜 호스트·가짜 vastai·가짜 터널로만 시험했다. 실제 vastai 응답 형태(`new_contract`, 포트 필드, `attach ssh`), 원격 `timeout`·`nohup` 동작, 32k 토큰 평가 서버의 GPU 메모리, 실제 판정 모델의 짝 판정 형식은 첫 실제 실행에서 확인해야 한다. 알려진 문제의 K-0061~K-0064를 참고한다.
