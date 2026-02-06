# decg CLI

바이브 코딩 워크스페이스 관리 도구

## 설치

```bash
# 의존성 설치
pip install -r requirements.txt

# PATH에 추가 (선택)
chmod +x decg
ln -s $(pwd)/decg /usr/local/bin/decg
```

## 사용법

```bash
# 워크스페이스 초기화
decg init deep-ecg-analysis v0.0.1

# 새 버전 생성
decg version new deep-ecg-analysis v0.0.2

# 개발 환경 시작
decg dev start

# 작업 브랜치 생성
decg branch create DEA-001 login-ui

# 전체 테스트 실행
decg test all

# 상태 확인
decg status
```

## 명령어 목록

| 명령어 | 설명 |
|-------|------|
| `decg init <service> <version>` | 워크스페이스 초기화 |
| `decg version new <service> <version>` | 새 버전 생성 |
| `decg version list <service>` | 버전 목록 |
| `decg version current` | 현재 버전 |
| `decg dev start` | 개발 환경 시작 |
| `decg dev stop` | 개발 환경 중지 |
| `decg dev logs [service]` | 로그 확인 |
| `decg dev status` | 컨테이너 상태 |
| `decg dev rebuild [service]` | 재빌드 |
| `decg branch create <id> <desc>` | 브랜치 생성 |
| `decg branch list` | 브랜치 목록 |
| `decg branch sync` | 동기화 |
| `decg branch pr` | PR 생성 |
| `decg test unit [domain]` | 단위 테스트 |
| `decg test e2e [scenario]` | E2E 테스트 |
| `decg test all` | 전체 테스트 |
| `decg test coverage` | 커버리지 |
| `decg docs init <service> <version>` | 문서 템플릿 |
| `decg docs list <service>` | 문서 목록 |
| `decg docs diff <service> <v1> <v2>` | 문서 비교 |
| `decg release init <service> <version>` | 릴리스 폴더 |
| `decg release changelog <service> <version>` | CHANGELOG |
| `decg release tag <service> <version>` | 태그 생성 |
| `decg release publish <service> <version>` | GitHub Release |
| `decg status` | 전체 상태 |
