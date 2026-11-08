# 선택적 암호화 백업 · 로컬 파일럿

검증된 평문 백업을 **새 암호화 사본**으로 봉인하는 기능입니다. 암호화 파일만 유출되고 강한 비밀번호가 공개되지 않았을 때 내용의 기밀성과 무결성을 보호하도록 설계했습니다. 조직 보안 인증, 전자서명, 사용자 인증, 랜섬웨어 방어 또는 실제 기업 데이터 사용 승인이 아닙니다. 자신이 만든 검증된 합성 백업만 다루며, 타인이 제공한 암호화 파일을 안전하게 실행/분석하는 도구로 쓰지 마세요.

**원본 작업 DB, 기존 평문 백업, 복원된 작업 공간은 계속 평문입니다.** 이 기능이 기존 파일을 자동 암호화·삭제하거나 실행 중 메모리를 보호한다고 해석하지 마세요. 현재 지원 자료는 동봉된 합성 실행과 검토 메모입니다.

## 설치와 지원 범위

- 기본 작업대·평문 백업은 Python 3.10+ 표준 라이브러리만으로 동작합니다.
- 선택적 암호화는 Python **3.10+와 고정된 cryptography 의존성**이 필요합니다. 지원하지 않으면 비밀번호 입력 전에 거부합니다.
- 검증 대상은 x86-64 Windows/Ubuntu의 CPython입니다. 다른 환경은 검증 완료로 주장하지 않습니다.

```bash
python -m venv .venv
# 운영체제에 맞게 가상 환경을 활성화한 뒤:
python -m pip install --require-hashes --only-binary=:all: -r requirements-encryption.txt
python -m pip check
```

패키지·전이 의존성의 버전, wheel SHA-256, 라이선스, 보안 공지 확인 범위는 [DEPENDENCIES.md](DEPENDENCIES.md)를 따릅니다. 설치가 실패하면 hash/버전 검사를 끄거나 평문으로 조용히 대체하지 마세요.

## 사용

1. [RECOVERY.md](RECOVERY.md)로 일관된 평문 백업을 만듭니다.
2. 본인만 접근하는 **로컬 숨김 입력 터미널**에서 새 암호화 파일을 만듭니다.
3. 별도 검사와 새 작업 공간 복원 훈련을 완료한 뒤 보관 방침을 정합니다. 원본을 자동 삭제하지 않습니다.

```bash
python manage_sealed.py seal --source /private/ax-backup-001 --destination /private/ax-backup-001.axsealed
python manage_sealed.py inspect --source /private/ax-backup-001.axsealed
python manage_sealed.py restore --source /private/ax-backup-001.axsealed --destination /private/ax-restored-002
python manage_evidence.py --workspace /private/ax-restored-002 verify
```

`seal`은 비밀번호를 두 번, `inspect`와 `restore`는 한 번 숨겨 입력받습니다. 최소 12문자, UTF-8 최대 1024바이트 제한은 형식 검사이며 강도를 보장하지 않습니다. 길고 예측하기 어려운 별도 문구를 사용하고 다른 계정 비밀번호를 재사용하지 마세요.

**비밀번호를 채팅, 명령줄 인수, 환경변수, 파이프, 로그, 설정 파일로 전달하지 마세요.** CLI는 비밀번호 옵션을 제공하지 않고 non-TTY 입력과 getpass의 평문 fallback을 거부합니다. 앱은 비밀번호나 파생 키를 저장하지 않습니다. Python의 문자열·메모리 사본을 확실히 지운다고 보장하지는 않습니다.

기존 대상 파일/폴더, symlink·hardlink, 지원하지 않는 경로는 덮어쓰지 않습니다. 네트워크 공유·UNC/device 경로는 지원하지 않습니다. Windows ACL과 디스크 암호화는 운영자가 확인해야 합니다. 프로그램이 보안 설정을 대신 변경하지 않습니다.

## 암호화 형식과 실패 경계

- cryptography의 AES-256-GCM으로 암호화하고 태그를 검증합니다. 자체 암호 알고리즘을 만들지 않습니다.
- 고정 scrypt N=2^17, r=8, p=1, 32바이트 키를 사용합니다. 매번 16바이트 무작위 salt와 12바이트 무작위 nonce를 새로 만듭니다.
- version 1 binary header 전체를 추가 인증 데이터(AAD)로 보호합니다. 파일 입력에서 KDF 비용·알고리즘을 협상하지 않습니다. 버전·선언 길이·실제 길이를 비싼 키 유도 전에 확인합니다.
- 인증된 payload에는 정확한 manifest 길이, canonical manifest, 원본 SQLite bytes만 들어갑니다. 임의 파일 이름·압축 파일·SQL·URL을 실행하지 않습니다.
- 원본 검사 후 실제 읽은 DB bytes도 checksum을 다시 확인해 검사/읽기 사이 변경을 거부합니다.
- 잘못된 비밀번호·변조·잘린 파일은 일반 실패로 처리합니다. 태그·manifest·DB checksum 검증을 마치기 전에 평문 출력 폴더를 만들지 않습니다.
- `inspect`는 `AUTHENTICATED_ENVELOPE`, `database_verified:false`를 반환합니다. 암호문과 내부 checksum 검증이며, SQLite schema/ledger 전체 검증은 아닙니다. 메모리 deserialize나 평문 임시파일을 만들지 않습니다.
- `seal`은 source bundle의 파일 기반 schema/ledger 검사와 실제 bytes checksum을 확인해 `SOURCE_DATABASE_VERIFIED`를 반환합니다.
- `restore`는 인증과 checksum을 통과한 원본 bytes를 새 private incomplete 폴더에 쓴 뒤 파일 기반 schema/ledger 검증을 수행합니다. 성공 시만 `RESTORED_DATABASE_VERIFIED`, `database_verified:true`로 완료합니다. WAL을 포함한 원본 bytes를 바꾸지 않습니다.
- 성공 출력의 `integrity_protected:true`는 비밀번호에서 유도한 키에 의한 AEAD 검증입니다. `authenticated:false`와 `signer_authenticated:false`는 작성자·검토자 신원이나 서명을 인증하지 않았다는 뜻입니다. 비밀번호 보유자는 새 유효 파일을 만들 수 있습니다.

암호화 출력은 private ciphertext 임시파일을 fsync한 뒤 기존 파일을 덮어쓰지 않는 방식으로 게시합니다. 파일시스템이 이를 지원하지 않으면 실패합니다. 암호화가 성공했어도 원본 평문 백업은 그대로 남습니다.

복원은 새 private 폴더에만 씁니다. 인증 이후 내부 schema/ledger 검사나 디스크 쓰기가 실패하면 그 새 폴더에 평문 일부와 incomplete 표식이 남을 수 있습니다. 작업대는 이를 열지 못합니다. 원본/암호화 파일은 보존하며 자동 재시도·삭제·안전한 지우기를 약속하지 않습니다. 기존 데이터를 지우지 말고 상태를 확인한 뒤 새 경로로 다시 시도하세요.

## 키 관리와 복구 훈련

- 잃어버린 비밀번호를 서버나 이 프로젝트가 복구할 수 없습니다. 별도 복구 키·escrow·조직 키 관리·비밀번호 재설정 기능은 없습니다.
- 조직이 승인한 비밀번호 보관 수단을 사용하고 백업 파일과 분리해 관리하세요. 이 프로그램이 새 보관 수단에 비밀번호를 저장하지 않습니다.
- 새 비밀번호로 새 사본을 만들어도 기존 사본의 이전 비밀번호는 폐기되지 않습니다. 키 교체와 기존 사본 보존·폐기는 운영자의 별도 절차입니다.
- 봉인 후 검사와 별도 새 폴더 복원을 실행해 ID, hash, 부분 범위와 검토 revision이 보존되는지 확인하세요. 비밀번호를 잘못 입력한 시험은 출력 폴더를 만들지 않아야 합니다.
- 예전의 정상 암호화 파일을 되돌려 놓는 rollback, 모든 사본의 삭제, 파일 크기 노출, 메모리 유출, 악성 로컬 사용자/관리자를 막지 않습니다. 별도 보관·보존 정책과 운영 감시는 여전히 필요합니다.

## 자원과 검증 한계

DB 128 MiB, manifest 4 KiB 및 고정 header/tag 상한을 적용합니다. scrypt 자체가 약 128 MiB 메모리를 사용하며, one-shot AEAD·파일 기반 SQLite·ledger 검사 사본 때문에 실제 최고 메모리는 파일 크기보다 훨씬 큽니다. 크기 상한은 최대 크기의 성능/SLA를 보증하지 않습니다. 실제 측정 환경·자료 크기·시험 결과만 VALIDATION.md에 기록합니다.

이 기능은 암호화된 사본 하나의 보호 단계입니다. 실기업 운영 전에는 승인된 데이터 범위, SSO/RBAC·조직 격리, 인증된 검토자와 직무 분리, OS/디스크 보호, 조직 키 관리, 보존·삭제·복구 목표와 현업 검증이 추가로 필요합니다.

공식 참고:
- https://cryptography.io/en/latest/hazmat/primitives/aead/
- https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/#scrypt
- https://docs.python.org/3/library/getpass.html
- https://sqlite.org/backup.html
