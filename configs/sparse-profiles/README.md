# Sparse Checkout 프로파일

이 디렉토리에 `{service}-{version}.yaml` 형식으로 프로파일을 저장하면 `decg init` 시 자동으로 해당 설정이 적용됩니다.

## 파일 구조

```txt
configs/sparse-profiles/
├── README.md                              # 이 파일
├── deep-ecg-analysis-v0.0.1.yaml          # ECG 분석 서비스 (include 예시)
├── sftp-monitor-v0.0.1.yaml      # SFTP 모니터 서비스 (exclude 예시)
└── ...
```

## 사용법

### 1. 자동 탐색 (권장)

```bash
# 프로파일 파일이 {service}-{version}.yaml 형식이면 자동 적용
decg init deep-ecg-analysis v0.0.1
# → configs/sparse-profiles/deep-ecg-analysis-v0.0.1.yaml 자동 로드
```

### 2. 명시적 지정

```bash
decg init deep-ecg-analysis v0.0.1 --profile configs/sparse-profiles/my-custom.yaml
```

### 3. CLI 옵션으로 직접 지정

```bash
decg init deep-ecg-analysis v0.0.1 \
  --include apps/sftp-monitor \
  --include packages/common
```

## YAML 스키마

```yaml
service: string           # 서비스 이름
version: string           # 버전

submodules:                # Submodule별 설정 (없는 항목은 초기화 안 함)
  {submodule-name}:        # decg-fe-monorepo, decg-be-monorepo, decg-go-monorepo
    include:               # 포함할 경로 목록 (whitelist)
      - apps/xxx
      - packages/yyy
    # 또는
    exclude:               # 제외할 경로 목록 (blacklist)
      - apps/zzz

options:                   # 추가 옵션
  shallow_clone: bool      # git clone --depth 1
  auto_branch: bool        # 자동 브랜치 생성
```

## include vs exclude 동작

| 설정 | 동작 |
|------|------|
| `include`만 있음 | 지정된 경로만 체크아웃 |
| `exclude`만 있음 | 전체 체크아웃 후 지정 경로 제외 |
| 둘 다 있음 | ⚠️ `include`만 적용 (`exclude` 무시) |
| 둘 다 없음 | 전체 체크아웃 |

> **권장**: 혼란을 피하려면 **둘 중 하나만** 사용하세요.

## 동작 원리

1. `decg init` 실행 시 프로파일 탐색
2. 프로파일에 정의된 submodule만 초기화 (없는 것은 건너뜀)
3. 각 submodule에 대해 `git sparse-checkout` 적용
4. 지정된 경로만 로컬에 체크아웃됨
