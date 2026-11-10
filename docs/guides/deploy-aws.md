# 팀용 캐릭터 공장 배포

> 2026-11-10 현재 코드와 계획 확인까지만 준비했다. 실제 적용(`tofu apply`)은 하지 않았다(D-0155).

모티브 원문 업로드·G6까지의 텍스트 제작용이다. 공장 전용 VPC(10.42.0.0/16) 안에서 전용 ALB가 Cognito 로그인을 확인한 뒤 태스크에 요청을 보낸다. 회사 dev VPC·NAT·보안 그룹과 나눠 쓰는 것이 없고, 겹치는 곳은 `dev.dokilabs.com` 존의 레코드 두 개(공장 주소, 인증서 검증)뿐이다. 태스크는 공용 서브넷에서 자기 공인 IP로 나가며(NAT 없음), 들어오는 길은 보안 그룹이 ALB로만 연다. 팀원 간 데이터는 공유된다. 상태와 작업 기록은 EFS, 업로드 원본은 비공개 S3의 `sources/`에 둔다. 태스크는 하나다. 교체할 때 화면 접속이 잠시 끊기며 실행 중인 작업은 이어서 돌지 않을 수 있다. 배포 전에 팀에 알리고 작업 수가 0인지 확인한다.

## 처음 한 번

1. 묶음 A까지 합친 커밋에서 임시 볼륨으로 업로드 → S0을 먼저 확인한다. AWS CLI v2, OpenTofu 1.10 이상, ARM64 빌드를 지원하는 Docker Buildx와 대상 계정 자격이 필요하다. VPC 대역(`vpc_cidr`)과 두 AZ(`azs`)는 `deploy/aws/network.tf`의 변수다. 회사 VPC와 대역이 겹치지 않게 둔다. 기존 VPC·ALB·보안 그룹은 읽지도 고치지도 않는다.
2. 별도로 준비한 암호화·버전 관리·공개 차단 S3 상태 버킷을 사용한다. 상태에는 Cognito 클라이언트 비밀이 들어가므로 배포 담당자만 읽고 쓰게 한다. 저장소 루트에서 아래 순서로 진행한다. 승인 전에 계획의 계정·리전·DNS 존과 변경 목록을 확인한다. 운영 서비스나 기존 DNS 레코드가 나오면 중단한다.

```sh
cp deploy/aws/backend.hcl.example deploy/aws/backend.hcl
# backend.hcl의 버킷 이름을 채운다. factory/dev/ 아래 전용 키를 유지한다.
tofu -chdir=deploy/aws init -reconfigure -backend-config=backend.hcl
tofu -chdir=deploy/aws apply -target=aws_ecr_repository.app -target=aws_secretsmanager_secret.key
scripts/deploy_factory.sh bootstrap
```

3. 서울 리전 Secrets Manager에서 `persona-factory-dev/OPENAI_API_KEY`, `persona-factory-dev/GEMINI_API_KEY`, `persona-factory-dev/TYPESAFE_API_KEY` 각각에 키 문자열만 **일반 텍스트**로 저장한다(JSON 객체 아님). 설정 파일·명령줄·상태에는 값을 넣지 않는다. ECS 실행 역할이 시작할 때 환경변수로 주입한다. 키를 교체하면 재배포해야 반영된다.
4. `tofu -chdir=deploy/aws apply`로 남은 자원을 만든다. 인증서 검증에는 시간이 걸릴 수 있다. 서비스가 안정되면 Cognito 사용자를 초대한다. 아래 메일 주소는 실제 팀원 주소로 바꾼다.

```sh
aws cognito-idp admin-create-user --region ap-northeast-2 \
  --user-pool-id "$(tofu -chdir=deploy/aws output -raw user_pool_id)" \
  --username team@example.org --desired-delivery-mediums EMAIL \
  --user-attributes Name=email,Value=team@example.org Name=email_verified,Value=true
tofu -chdir=deploy/aws output -raw url
```

로그아웃 상태로 주소의 `/studio/`와 `/api/health`를 열면 둘 다 로그인으로 이동해야 한다. 초대 메일의 임시 비밀번호로 로그인해 새 비밀번호를 정하고, 스튜디오에서 합성 원문 하나를 올려 S0 결과와 상태 저장을 확인한다. 유료 단계는 별도 실행 승인 뒤 확인한다.

## 업데이트와 되돌리기

깨끗한 커밋에서 `scripts/deploy_factory.sh`를 실행한다. 커밋 SHA 태그는 변경할 수 없고 `release`만 새 이미지로 옮긴다. 스크립트는 태스크를 교체하고 실행 중인 이미지의 다이제스트를 확인한다. 두 담당자가 동시에 배포하지 않는다. 실패하면 ECS 서비스 이벤트와 CloudWatch의 `/ecs/persona-factory-dev`를 확인한다. `scripts/deploy_factory.sh rollback <이전 40자리 SHA>`는 ECR에 남은 이미지로 돌아간다. EFS·S3 내용은 복원하지 않으므로 저장 형식 변경 전에는 별도로 백업한다.

## 비용과 삭제

소규모 팀이 월 730시간 켠다는 가정에서 예산은 **월 60~90 USD** 정도로 잡는다(견적, 실측 아님). ARM64 1 vCPU·2 GiB 한 대, 공용 ALB 한 대와 두 AZ의 공인 IPv4, 소량의 로그·저장 공간을 전제로 한다. NAT는 쓰지 않는다. 태스크 공인 IPv4 한 개가 더해진다. 모델 사용료, 세금, 전송량과 백업은 별도다. 배포 전에 [AWS 요금 계산기](https://calculator.aws/)에서 서울 리전·예상 사용량을 입력한다. [Fargate 과금 기준](https://aws.amazon.com/fargate/pricing/)을 참고한다.

삭제하기 전에 새 작업을 막고 EFS 백업과 원본 보관·삭제 범위를 확인한다. 공장 전용 버킷과 ECR만 비운 뒤 `tofu -chdir=deploy/aws destroy`의 삭제 목록을 검토한다. **EFS 파일과 사용자 풀도 삭제된다.** 키는 Secrets Manager 복구 기간 뒤 삭제되므로 같은 이름으로 바로 다시 만들 수 없다. 공장 전용 VPC·서브넷도 함께 삭제된다. 상태 버킷과 호스팅 영역은 이 스택이 삭제하지 않는다.
