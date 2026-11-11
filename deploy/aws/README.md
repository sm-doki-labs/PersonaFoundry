# 공장 전용 OpenTofu 상태

`backend.hcl.example`을 `backend.hcl`로 복사하고 공장용 S3 상태 버킷 이름을 채운다. 키는 `factory/dev/factory.tfstate`다. 팀 서비스의 상태 파일이나 워크스페이스를 재사용하지 않는다. 버킷 버전 관리와 암호화를 켜고 상태 객체와 잠금 파일 접근을 배포 담당자로 제한한다.

리소스를 만들지 않고 구문을 확인할 때는 이 폴더에서 `tofu init -backend=false && tofu validate && tofu fmt -check`를 실행한다. 실제 초기화·키 등록·배포·롤백·삭제는 [팀 배포 안내](../../docs/guides/deploy-aws.md)를 따른다.
