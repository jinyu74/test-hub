#!/usr/bin/env python3
"""
decg CLI - 바이브 코딩 워크스페이스 관리 도구

Usage:
    decg <command> [options]

Commands:
    init        워크스페이스 초기화
    version     버전 관리
    dev         개발 환경 관리 (Docker)
    branch      브랜치 관리
    test        테스트 실행
    docs        문서 관리
    release     릴리스 관리
    status      상태 확인
"""

import typer
from pathlib import Path
from typing import Optional, List
import subprocess
import sys
import os
import yaml
import hashlib

app = typer.Typer(
    name="decg",
    help="바이브 코딩 워크스페이스 관리 도구",
    add_completion=False,
)

# Sub-apps
init_app = typer.Typer(help="워크스페이스 초기화")
version_app = typer.Typer(help="버전 관리")
dev_app = typer.Typer(help="개발 환경 관리 (Docker)")
branch_app = typer.Typer(help="브랜치 관리")
test_app = typer.Typer(help="테스트 실행")
docs_app = typer.Typer(help="문서 관리")
release_app = typer.Typer(help="릴리스 관리")


# ============================================================
# Utility Functions
# ============================================================

def get_hub_root() -> Path:
    """Find the root of decg-project-hub by looking for .gitmodules"""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".gitmodules").exists():
            return current
        current = current.parent
    typer.echo("❌ decg-project-hub 루트를 찾을 수 없습니다.", err=True)
    raise typer.Exit(1)


def run_shell(cmd: str, cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result"""
    typer.echo(f"  → {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        typer.echo(f"❌ 명령 실행 실패: {result.stderr}", err=True)
        raise typer.Exit(result.returncode)
    return result


def echo_success(msg: str):
    typer.echo(f"✅ {msg}")


def echo_info(msg: str):
    typer.echo(f"ℹ️  {msg}")


def echo_warning(msg: str):
    typer.echo(f"⚠️  {msg}")


# ============================================================
# INIT Commands
# ============================================================

def load_sparse_profile(hub_root: Path, service: str, version: str, profile_path: Optional[str] = None) -> Optional[dict]:
    """Sparse Checkout 프로파일 YAML 로드"""
    if profile_path:
        # 명시적으로 지정된 프로파일
        path = Path(profile_path)
        if not path.is_absolute():
            path = hub_root / path
    else:
        # 자동 탐색: configs/sparse-profiles/{service}-{version}.yaml
        path = hub_root / "configs" / "sparse-profiles" / f"{service}-{version}.yaml"
    
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return None


def apply_sparse_checkout(submodule_path: Path, config: dict):
    """
    Submodule에 Sparse Checkout 적용
    
    config 구조 (mode 자동 판단):
        - include가 있으면 → include 모드 (지정 경로만 가져옴)
        - exclude만 있으면 → exclude 모드 (전체에서 제외)
    """
    include_paths = config.get("include", [])
    exclude_paths = config.get("exclude", [])
    
    typer.echo(f"  🔧 Sparse Checkout 활성화: {submodule_path.name}")
    
    # include가 있으면 include 우선, 없으면 exclude 사용
    if include_paths:
        # Include 모드: 지정된 경로만 체크아웃
        run_shell("git sparse-checkout init --cone", cwd=submodule_path, check=False)
        paths = " ".join(include_paths)
        run_shell(f"git sparse-checkout set {paths} packages/", cwd=submodule_path, check=False)
        
        for p in include_paths:
            typer.echo(f"    ✓ {p}")
    elif exclude_paths:
        # Exclude 모드: 전체 체크아웃 후 특정 경로만 제외
        run_shell("git sparse-checkout init --no-cone", cwd=submodule_path, check=False)
        
        sparse_file = submodule_path / ".git" / "info" / "sparse-checkout"
        patterns = ["/*"]  # 전체 포함
        for path in exclude_paths:
            patterns.append(f"!/{path}")  # 제외 패턴
        
        sparse_file.write_text("\n".join(patterns) + "\n")
        run_shell("git read-tree -mu HEAD", cwd=submodule_path, check=False)
        
        typer.echo(f"    📂 전체 포함 (제외 항목 있음)")
        for p in exclude_paths:
            typer.echo(f"    ✗ {p} (제외)")


@app.command("init")
def init_workspace(
    service: str = typer.Argument(..., help="서비스 이름 (예: deep-ecg-analysis)"),
    version: str = typer.Argument(..., help="버전 (예: v0.0.1)"),
    modules: Optional[List[str]] = typer.Option(
        None, "--include", "-i",
        help="포함할 Submodule 앱 경로 (예: apps/sftp-monitor)"
    ),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p",
        help="Sparse Checkout 프로파일 YAML 경로 (예: configs/sparse-profiles/my-profile.yaml)"
    ),
    skip_docker: bool = typer.Option(False, "--skip-docker", help="Docker 환경 설정 건너뛰기"),
):
    """
    워크스페이스 초기화

    서비스와 버전을 지정하여 개발 환경을 설정합니다.
    Submodule 초기화, Sparse Checkout, 브랜치 생성을 수행합니다.

    Sparse Checkout 프로파일:
        configs/sparse-profiles/{service}-{version}.yaml 파일이 있으면 자동 로드
        --profile 옵션으로 명시적 지정 가능

    예시:
        decg init deep-ecg-analysis v0.0.1
        decg init deep-ecg-analysis v0.0.1 --include apps/sftp-monitor
        decg init deep-ecg-analysis v0.0.1 --profile configs/sparse-profiles/custom.yaml
    """
    hub_root = get_hub_root()
    branch_name = f"{service}/develop/{version}"
    
    typer.echo(f"\n🚀 워크스페이스 초기화: {service} {version}")
    typer.echo("=" * 50)
    
    # 프로파일 로드
    sparse_profile = load_sparse_profile(hub_root, service, version, profile)
    if sparse_profile:
        echo_info(f"Sparse Checkout 프로파일 로드됨: {service}-{version}.yaml")
    elif modules:
        echo_info(f"CLI 옵션으로 {len(modules)}개 모듈 지정됨")
    
    # 1. Hub 브랜치 생성/체크아웃
    typer.echo("\n📁 [1/4] Hub 브랜치 설정...")
    workspace_branch = f"workspace/{service}-{version}"
    result = run_shell(f"git rev-parse --verify {workspace_branch}", cwd=hub_root, check=False)
    if result.returncode == 0:
        run_shell(f"git checkout {workspace_branch}", cwd=hub_root)
        echo_info(f"기존 브랜치로 전환: {workspace_branch}")
    else:
        run_shell(f"git checkout -b {workspace_branch}", cwd=hub_root)
        echo_success(f"새 브랜치 생성: {workspace_branch}")
    
    # 2. Submodule 초기화
    typer.echo("\n📦 [2/4] Submodule 초기화...")
    
    # 전체 Submodule 매핑 (.gitmodules 기준)
    all_submodules = {
        "decg-fe-monorepo": "apps/decg-fe-monorepo",
        "decg-be-monorepo": "apps/decg-be-monorepo",
        "decg-go-monorepo": "apps/decg-go-monorepo",
    }
    
    # 프로파일에 submodules가 정의되어 있으면 해당 항목만 초기화
    # 프로파일이 없거나 submodules가 없으면 전체 초기화
    if sparse_profile and "submodules" in sparse_profile:
        target_submodules = {
            name: path for name, path in all_submodules.items()
            if name in sparse_profile["submodules"]
        }
        skipped_submodules = [
            name for name in all_submodules.keys()
            if name not in sparse_profile["submodules"]
        ]
        if skipped_submodules:
            echo_info(f"제외된 Submodule: {', '.join(skipped_submodules)}")
    else:
        target_submodules = all_submodules
    
    for submodule_name, submodule_relpath in target_submodules.items():
        submodule_path = hub_root / submodule_relpath
        
        # Submodule 초기화
        if not submodule_path.exists():
            run_shell(f"git submodule update --init --depth 1 {submodule_relpath}", cwd=hub_root)
        
        # Sparse Checkout 설정 가져오기
        checkout_config = {}
        
        if sparse_profile and "submodules" in sparse_profile:
            if submodule_name in sparse_profile["submodules"]:
                checkout_config = sparse_profile["submodules"][submodule_name]
        elif modules:
            # CLI --include 옵션에서 해당 submodule에 속하는 경로 필터링
            checkout_config = {"include": [m for m in modules if not m.startswith("apps/")]}
        
        # include 또는 exclude가 있으면 Sparse Checkout 적용
        if checkout_config.get("include") or checkout_config.get("exclude"):
            apply_sparse_checkout(submodule_path, checkout_config)
        else:
            typer.echo(f"  📂 {submodule_name}: 전체 체크아웃")
        
        # 브랜치 생성/체크아웃
        result = run_shell(f"git rev-parse --verify {branch_name}", cwd=submodule_path, check=False)
        if result.returncode == 0:
            run_shell(f"git checkout {branch_name}", cwd=submodule_path)
        else:
            run_shell(f"git checkout -b {branch_name}", cwd=submodule_path)
    
    echo_success("Submodule 초기화 완료")
    
    # 3. docs/releases 디렉토리 생성
    typer.echo("\n📄 [3/4] 문서 디렉토리 생성...")
    docs_path = hub_root / "docs" / service / version
    releases_path = hub_root / "releases" / service / version
    
    docs_path.mkdir(parents=True, exist_ok=True)
    releases_path.mkdir(parents=True, exist_ok=True)
    
    # 기본 문서 폴더 생성
    doc_folders = [
        "01.requirements",
        "02.user-stories", 
        "03.use-cases",
        "05.api-spec",
        "08.implementation-guide",
        "09.test-automation",
    ]
    for folder in doc_folders:
        (docs_path / folder).mkdir(exist_ok=True)
    
    # releases 기본 파일 생성
    for filename in ["RELEASE-NOTES.md", "VERSION-MATRIX.md", "CHANGELOG.md"]:
        filepath = releases_path / filename
        if not filepath.exists():
            filepath.write_text(f"# {filename.replace('.md', '')}\n\n## [{version}]\n\n")
    
    echo_success("문서 디렉토리 생성 완료")
    
    # 4. Docker 환경 (선택적)
    if not skip_docker:
        typer.echo("\n🐳 [4/4] Docker 환경 확인...")
        docker_compose = hub_root / "scripts" / "docker" / "docker-compose.dev.yml"
        if docker_compose.exists():
            echo_info("Docker Compose 파일 발견. 'decg dev start'로 환경을 시작하세요.")
        else:
            echo_warning("Docker Compose 파일이 없습니다. 수동 설정이 필요합니다.")
    else:
        typer.echo("\n⏭️  [4/4] Docker 환경 설정 건너뜀")
    
    typer.echo("\n" + "=" * 50)
    echo_success(f"워크스페이스 초기화 완료: {service} {version}")
    typer.echo(f"""
다음 단계:
  1. decg dev start        # 개발 환경 시작
  2. decg branch create    # 작업 브랜치 생성
  3. 개발 시작!
""")


# ============================================================
# VERSION Commands
# ============================================================

@version_app.command("new")
def version_new(
    service: str = typer.Argument(..., help="서비스 이름"),
    version: str = typer.Argument(..., help="새 버전 (예: v0.0.2)"),
    copy_from: Optional[str] = typer.Option(None, "--from", "-f", help="이전 버전에서 복사"),
):
    """
    새 버전 생성

    docs와 releases 디렉토리에 새 버전 폴더를 생성합니다.

    예시:
        decg version new deep-ecg-analysis v0.0.2
        decg version new deep-ecg-analysis v0.0.2 --from v0.0.1
    """
    hub_root = get_hub_root()
    
    typer.echo(f"\n📦 새 버전 생성: {service} {version}")
    
    docs_path = hub_root / "docs" / service / version
    releases_path = hub_root / "releases" / service / version
    
    if docs_path.exists():
        echo_warning(f"docs/{service}/{version} 이미 존재합니다.")
    else:
        docs_path.mkdir(parents=True)
        
        # 기본 폴더 구조 생성
        doc_folders = [
            "01.requirements",
            "02.user-stories",
            "03.use-cases", 
            "05.api-spec",
            "08.implementation-guide",
            "09.test-automation",
        ]
        for folder in doc_folders:
            (docs_path / folder).mkdir()
        
        echo_success(f"docs/{service}/{version} 생성 완료")
    
    if releases_path.exists():
        echo_warning(f"releases/{service}/{version} 이미 존재합니다.")
    else:
        releases_path.mkdir(parents=True)
        
        # CHANGELOG 복사 (이전 버전에서)
        if copy_from:
            prev_changelog = hub_root / "releases" / service / copy_from / "CHANGELOG.md"
            if prev_changelog.exists():
                content = prev_changelog.read_text()
                new_changelog = releases_path / "CHANGELOG.md"
                new_changelog.write_text(f"# Changelog\n\n## [{version}] - TBD\n\n### Added\n\n### Changed\n\n### Removed\n\n---\n\n{content}")
                echo_info(f"CHANGELOG.md 복사됨 (from {copy_from})")
        
        # 기본 파일 생성
        for filename in ["RELEASE-NOTES.md", "VERSION-MATRIX.md"]:
            filepath = releases_path / filename
            if not filepath.exists():
                filepath.write_text(f"# {filename.replace('.md', '').replace('-', ' ')}\n\n## {version}\n\n")
        
        if not (releases_path / "CHANGELOG.md").exists():
            (releases_path / "CHANGELOG.md").write_text(f"# Changelog\n\n## [{version}] - TBD\n\n### Added\n\n### Changed\n\n### Removed\n\n")
        
        echo_success(f"releases/{service}/{version} 생성 완료")


@version_app.command("list")
def version_list(
    service: str = typer.Argument(..., help="서비스 이름"),
):
    """서비스의 버전 목록 조회"""
    hub_root = get_hub_root()
    docs_path = hub_root / "docs" / service
    
    if not docs_path.exists():
        typer.echo(f"❌ 서비스를 찾을 수 없습니다: {service}", err=True)
        raise typer.Exit(1)
    
    versions = sorted([d.name for d in docs_path.iterdir() if d.is_dir()])
    
    typer.echo(f"\n📋 {service} 버전 목록:")
    for v in versions:
        releases_path = hub_root / "releases" / service / v
        status = "✅" if releases_path.exists() else "📝"
        typer.echo(f"  {status} {v}")


@version_app.command("current")
def version_current():
    """현재 작업 중인 버전 확인"""
    hub_root = get_hub_root()
    result = run_shell("git branch --show-current", cwd=hub_root, check=False)
    
    branch = result.stdout.strip()
    if branch.startswith("workspace/"):
        parts = branch.replace("workspace/", "").rsplit("-", 1)
        if len(parts) == 2:
            typer.echo(f"📌 현재 워크스페이스: {parts[0]} {parts[1]}")
            return
    
    typer.echo(f"📌 현재 브랜치: {branch}")
    echo_warning("워크스페이스 브랜치가 아닙니다. 'decg init'으로 초기화하세요.")


app.add_typer(version_app, name="version")


# ============================================================
# DEV Commands (Docker)
# ============================================================

@dev_app.command("start")
def dev_start(
    service: Optional[str] = typer.Option(None, "--service", "-s", help="특정 서비스만 시작"),
    detach: bool = typer.Option(True, "--detach/--attach", "-d/-a", help="백그라운드 실행"),
):
    """개발 환경 시작 (Docker Compose)"""
    hub_root = get_hub_root()
    docker_compose = hub_root / "scripts" / "docker" / "docker-compose.dev.yml"
    
    if not docker_compose.exists():
        echo_warning("Docker Compose 파일이 없습니다.")
        typer.echo(f"  예상 위치: {docker_compose}")
        raise typer.Exit(1)
    
    typer.echo("\n🚀 개발 환경 시작...")
    
    cmd = f"docker-compose -f {docker_compose} up"
    if detach:
        cmd += " -d"
    if service:
        cmd += f" {service}"
    
    run_shell(cmd, cwd=hub_root)
    
    if detach:
        typer.echo("""
✅ 개발 환경이 시작되었습니다.

  📱 Frontend:  http://localhost:3000
  🔧 Backend:   http://localhost:8000
  📚 API Docs:  http://localhost:8000/docs
  🗄️  pgAdmin:   http://localhost:5050

  로그 확인: decg dev logs
  종료:      decg dev stop
""")


@dev_app.command("stop")
def dev_stop():
    """개발 환경 중지"""
    hub_root = get_hub_root()
    docker_compose = hub_root / "scripts" / "docker" / "docker-compose.dev.yml"
    
    if not docker_compose.exists():
        echo_warning("Docker Compose 파일이 없습니다.")
        raise typer.Exit(1)
    
    typer.echo("\n🛑 개발 환경 중지...")
    run_shell(f"docker-compose -f {docker_compose} down", cwd=hub_root)
    echo_success("개발 환경이 중지되었습니다.")


@dev_app.command("logs")
def dev_logs(
    service: Optional[str] = typer.Argument(None, help="서비스 이름 (생략 시 전체)"),
    follow: bool = typer.Option(True, "--follow/--no-follow", "-f/-n", help="실시간 로그 추적"),
    tail: int = typer.Option(100, "--tail", "-t", help="표시할 로그 줄 수"),
):
    """서비스 로그 확인"""
    hub_root = get_hub_root()
    docker_compose = hub_root / "scripts" / "docker" / "docker-compose.dev.yml"
    
    cmd = f"docker-compose -f {docker_compose} logs --tail {tail}"
    if follow:
        cmd += " -f"
    if service:
        cmd += f" {service}"
    
    # 실시간 로그는 직접 실행
    os.system(f"cd {hub_root} && {cmd}")


@dev_app.command("status")
def dev_status():
    """컨테이너 상태 확인"""
    hub_root = get_hub_root()
    docker_compose = hub_root / "scripts" / "docker" / "docker-compose.dev.yml"
    
    if not docker_compose.exists():
        echo_warning("Docker Compose 파일이 없습니다.")
        return
    
    typer.echo("\n🐳 Docker 컨테이너 상태:\n")
    os.system(f"docker-compose -f {docker_compose} ps")


@dev_app.command("rebuild")
def dev_rebuild(
    service: Optional[str] = typer.Argument(None, help="서비스 이름 (생략 시 전체)"),
):
    """컨테이너 재빌드"""
    hub_root = get_hub_root()
    docker_compose = hub_root / "scripts" / "docker" / "docker-compose.dev.yml"
    
    typer.echo("\n🔄 컨테이너 재빌드...")
    
    cmd = f"docker-compose -f {docker_compose} up -d --build"
    if service:
        cmd += f" {service}"
    
    run_shell(cmd, cwd=hub_root)
    echo_success("재빌드 완료")


app.add_typer(dev_app, name="dev")


# ============================================================
# BRANCH Commands
# ============================================================

@branch_app.command("create")
def branch_create(
    task_id: str = typer.Argument(..., help="태스크 ID (예: DEA-001)"),
    description: str = typer.Argument(..., help="브랜치 설명 (예: login-ui)"),
    repos: Optional[List[str]] = typer.Option(
        None, "--repo", "-r",
        help="브랜치를 생성할 저장소 (fe, be, go)"
    ),
):
    """
    작업 브랜치 생성

    Submodule 저장소에 task 브랜치를 생성합니다.

    예시:
        decg branch create DEA-001 login-ui
        decg branch create DEA-001 login-ui --repo fe --repo be
    """
    hub_root = get_hub_root()
    branch_name = f"task/{task_id}-{description}"
    
    typer.echo(f"\n🌿 작업 브랜치 생성: {branch_name}")
    
    # 저장소 매핑
    repo_map = {
        "fe": "apps/decg-fe-monorepo",
        "be": "apps/decg-be-monorepo",
        "go": "apps/decg-go-monorepo",
    }
    
    target_repos = repos or ["fe", "be"]  # 기본값은 fe, be
    
    for repo_key in target_repos:
        if repo_key not in repo_map:
            echo_warning(f"알 수 없는 저장소: {repo_key}")
            continue
        
        repo_path = hub_root / repo_map[repo_key]
        if not repo_path.exists():
            echo_warning(f"저장소가 없습니다: {repo_map[repo_key]}")
            continue
        
        typer.echo(f"\n  📁 {repo_map[repo_key]}...")
        run_shell(f"git checkout -b {branch_name}", cwd=repo_path)
        echo_success(f"브랜치 생성됨: {branch_name}")


@branch_app.command("list")
def branch_list():
    """현재 워크스페이스 브랜치 목록"""
    hub_root = get_hub_root()
    
    typer.echo("\n📋 현재 브랜치 상태:\n")
    
    # Hub
    typer.echo("🏠 Hub (decg-project-hub):")
    result = run_shell("git branch --show-current", cwd=hub_root, check=False)
    typer.echo(f"  → {result.stdout.strip()}")
    
    # Submodules
    for submodule in ["apps/decg-fe-monorepo", "apps/decg-be-monorepo", "apps/decg-go-monorepo"]:
        submodule_path = hub_root / submodule
        if submodule_path.exists():
            typer.echo(f"\n📦 {submodule}:")
            result = run_shell("git branch --show-current", cwd=submodule_path, check=False)
            typer.echo(f"  → {result.stdout.strip()}")


@branch_app.command("sync")
def branch_sync():
    """Submodule 브랜치 동기화 (pull)"""
    hub_root = get_hub_root()
    
    typer.echo("\n🔄 Submodule 동기화 중...")
    
    for submodule in ["apps/decg-fe-monorepo", "apps/decg-be-monorepo", "apps/decg-go-monorepo"]:
        submodule_path = hub_root / submodule
        if submodule_path.exists():
            typer.echo(f"\n  📦 {submodule}...")
            run_shell("git pull --rebase", cwd=submodule_path, check=False)
    
    echo_success("동기화 완료")


@branch_app.command("pr")
def branch_pr(
    title: Optional[str] = typer.Option(None, "--title", "-t", help="PR 제목"),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="PR 설명"),
    draft: bool = typer.Option(False, "--draft", "-d", help="Draft PR로 생성"),
):
    """GitHub PR 생성 (gh cli 사용)"""
    hub_root = get_hub_root()
    
    # gh cli 확인
    result = run_shell("which gh", cwd=hub_root, check=False)
    if result.returncode != 0:
        echo_warning("GitHub CLI (gh)가 설치되어 있지 않습니다.")
        typer.echo("  설치: brew install gh")
        raise typer.Exit(1)
    
    cmd = "gh pr create"
    if title:
        cmd += f' --title "{title}"'
    if body:
        cmd += f' --body "{body}"'
    if draft:
        cmd += " --draft"
    
    typer.echo("\n🔗 PR 생성 중...")
    os.system(f"cd {hub_root} && {cmd}")


app.add_typer(branch_app, name="branch")


# ============================================================
# TEST Commands
# ============================================================

@test_app.command("unit")
def test_unit(
    domain: Optional[str] = typer.Argument(None, help="도메인 (예: auth, ecg)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="상세 출력"),
):
    """단위 테스트 실행"""
    hub_root = get_hub_root()
    
    typer.echo("\n🧪 단위 테스트 실행...")
    
    cmd = "pytest tests/unit/"
    if domain:
        cmd += f"{domain}/"
    if verbose:
        cmd += " -v"
    
    # BE 테스트
    be_path = hub_root / "apps" / "decg-be-monorepo"
    if be_path.exists():
        typer.echo("\n  📦 Backend 테스트...")
        run_shell(cmd, cwd=be_path, check=False)


@test_app.command("e2e")
def test_e2e(
    scenario: Optional[str] = typer.Argument(None, help="시나리오 이름"),
):
    """E2E 테스트 실행"""
    hub_root = get_hub_root()
    
    typer.echo("\n🎭 E2E 테스트 실행...")
    
    cmd = "pytest tests/e2e/"
    if scenario:
        cmd += f" -k {scenario}"
    
    be_path = hub_root / "apps" / "decg-be-monorepo"
    if be_path.exists():
        run_shell(cmd, cwd=be_path, check=False)


@test_app.command("all")
def test_all(
    coverage: bool = typer.Option(False, "--coverage", "-c", help="커버리지 리포트 생성"),
):
    """전체 테스트 (단위 + E2E)"""
    hub_root = get_hub_root()
    
    typer.echo("\n🧪 전체 테스트 실행...")
    
    cmd = "pytest"
    if coverage:
        cmd += " --cov=src --cov-report=html"
    
    be_path = hub_root / "apps" / "decg-be-monorepo"
    if be_path.exists():
        run_shell(cmd, cwd=be_path, check=False)


@test_app.command("coverage")
def test_coverage():
    """커버리지 리포트 생성"""
    hub_root = get_hub_root()
    
    typer.echo("\n📊 커버리지 리포트 생성...")
    
    be_path = hub_root / "apps" / "decg-be-monorepo"
    if be_path.exists():
        run_shell("pytest --cov=src --cov-report=html --cov-report=term", cwd=be_path, check=False)
        typer.echo(f"\n  📄 리포트: {be_path}/htmlcov/index.html")


app.add_typer(test_app, name="test")


# ============================================================
# DOCS Commands
# ============================================================

@docs_app.command("init")
def docs_init(
    service: str = typer.Argument(..., help="서비스 이름"),
    version: str = typer.Argument(..., help="버전"),
):
    """문서 템플릿 생성"""
    hub_root = get_hub_root()
    docs_path = hub_root / "docs" / service / version
    
    if docs_path.exists():
        echo_warning(f"이미 존재합니다: docs/{service}/{version}")
        return
    
    typer.echo(f"\n📄 문서 템플릿 생성: {service} {version}")
    
    docs_path.mkdir(parents=True)
    
    # 폴더 및 기본 파일 생성
    templates = {
        "01.requirements": "# 요구사항 정의\n\n## 기능 요구사항\n\n## 비기능 요구사항\n",
        "02.user-stories": "# 사용자 스토리\n\n## US-001: \n\n",
        "03.use-cases": "# 유즈케이스\n\n## UC-001: \n\n",
        "05.api-spec": "# API 명세\n\n## Endpoints\n\n",
        "08.implementation-guide": "# 구현 가이드\n\n## 기술 스택\n\n## 코딩 규칙\n\n",
        "09.test-automation": "# 테스트 자동화\n\n## 테스트 전략\n\n## 테스트 케이스\n\n",
    }
    
    for folder, content in templates.items():
        folder_path = docs_path / folder
        folder_path.mkdir()
        (folder_path / "README.md").write_text(content)
    
    echo_success(f"문서 템플릿 생성 완료: docs/{service}/{version}")


@docs_app.command("list")
def docs_list(
    service: str = typer.Argument(..., help="서비스 이름"),
):
    """서비스의 문서 버전 목록"""
    hub_root = get_hub_root()
    docs_path = hub_root / "docs" / service
    
    if not docs_path.exists():
        typer.echo(f"❌ 서비스를 찾을 수 없습니다: {service}")
        raise typer.Exit(1)
    
    typer.echo(f"\n📚 {service} 문서 버전:")
    
    for version_dir in sorted(docs_path.iterdir()):
        if version_dir.is_dir():
            doc_count = sum(1 for f in version_dir.rglob("*.md"))
            typer.echo(f"  📁 {version_dir.name} ({doc_count} files)")


@docs_app.command("diff")
def docs_diff(
    service: str = typer.Argument(..., help="서비스 이름"),
    v1: str = typer.Argument(..., help="이전 버전"),
    v2: str = typer.Argument(..., help="현재 버전"),
):
    """두 버전 간 문서 차이 비교"""
    hub_root = get_hub_root()
    
    path1 = hub_root / "docs" / service / v1
    path2 = hub_root / "docs" / service / v2
    
    if not path1.exists() or not path2.exists():
        typer.echo("❌ 버전 경로를 찾을 수 없습니다.")
        raise typer.Exit(1)
    
    typer.echo(f"\n📊 문서 비교: {v1} ↔ {v2}")
    
    files1 = set(f.relative_to(path1) for f in path1.rglob("*.md"))
    files2 = set(f.relative_to(path2) for f in path2.rglob("*.md"))
    
    added = files2 - files1
    removed = files1 - files2
    common = files1 & files2
    
    if added:
        typer.echo(f"\n  ➕ 추가된 파일 ({len(added)}):")
        for f in sorted(added):
            typer.echo(f"    + {f}")
    
    if removed:
        typer.echo(f"\n  ➖ 삭제된 파일 ({len(removed)}):")
        for f in sorted(removed):
            typer.echo(f"    - {f}")
    
    typer.echo(f"\n  📄 공통 파일: {len(common)}")


app.add_typer(docs_app, name="docs")


# ============================================================
# RELEASE Commands
# ============================================================

@release_app.command("init")
def release_init(
    service: str = typer.Argument(..., help="서비스 이름"),
    version: str = typer.Argument(..., help="버전"),
):
    """릴리스 폴더 생성"""
    hub_root = get_hub_root()
    releases_path = hub_root / "releases" / service / version
    
    if releases_path.exists():
        echo_warning(f"이미 존재합니다: releases/{service}/{version}")
        return
    
    typer.echo(f"\n📦 릴리스 폴더 생성: {service} {version}")
    
    releases_path.mkdir(parents=True)
    
    (releases_path / "RELEASE-NOTES.md").write_text(f"""# Release Notes - {version}

## 개요

## 주요 변경사항

### 새 기능

### 개선사항

### 버그 수정

## 알려진 이슈

## 업그레이드 가이드
""")
    
    (releases_path / "VERSION-MATRIX.md").write_text(f"""# Version Matrix - {version}

| 기능 ID | 기능명 | 상태 | 비고 |
|--------|-------|------|------|
|  |  |  |  |
""")
    
    (releases_path / "CHANGELOG.md").write_text(f"""# Changelog

## [{version}] - TBD

### Added

### Changed

### Removed
""")
    
    echo_success(f"릴리스 폴더 생성 완료: releases/{service}/{version}")


@release_app.command("changelog")
def release_changelog(
    service: str = typer.Argument(..., help="서비스 이름"),
    version: str = typer.Argument(..., help="버전"),
):
    """CHANGELOG.md 자동 생성 (Git 커밋 기반)"""
    hub_root = get_hub_root()
    
    typer.echo(f"\n📝 CHANGELOG 생성: {service} {version}")
    
    # Git 로그에서 커밋 메시지 수집
    result = run_shell(
        f'git log --oneline --pretty=format:"%s" --since="1 month ago"',
        cwd=hub_root,
        check=False
    )
    
    commits = result.stdout.strip().split("\n") if result.stdout else []
    
    added = []
    changed = []
    fixed = []
    
    for commit in commits:
        if commit.startswith("feat"):
            added.append(commit)
        elif commit.startswith("fix"):
            fixed.append(commit)
        elif commit.startswith(("refactor", "perf", "style")):
            changed.append(commit)
    
    changelog_content = f"""# Changelog

## [{version}] - {typer.prompt("릴리스 날짜 (YYYY-MM-DD)", default="TBD")}

### Added
{chr(10).join(f"- {c}" for c in added) if added else "- (없음)"}

### Changed
{chr(10).join(f"- {c}" for c in changed) if changed else "- (없음)"}

### Fixed
{chr(10).join(f"- {c}" for c in fixed) if fixed else "- (없음)"}
"""
    
    releases_path = hub_root / "releases" / service / version
    releases_path.mkdir(parents=True, exist_ok=True)
    (releases_path / "CHANGELOG.md").write_text(changelog_content)
    
    echo_success(f"CHANGELOG 생성 완료: releases/{service}/{version}/CHANGELOG.md")


@release_app.command("tag")
def release_tag(
    service: str = typer.Argument(..., help="서비스 이름"),
    version: str = typer.Argument(..., help="버전"),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="태그 메시지"),
):
    """릴리스 태그 생성"""
    hub_root = get_hub_root()
    tag_name = f"{service}-{version}"
    
    typer.echo(f"\n🏷️  태그 생성: {tag_name}")
    
    msg = message or f"Release {service} {version}"
    run_shell(f'git tag -a {tag_name} -m "{msg}"', cwd=hub_root)
    
    if typer.confirm("원격 저장소에 push할까요?"):
        run_shell(f"git push origin {tag_name}", cwd=hub_root)
    
    echo_success(f"태그 생성 완료: {tag_name}")


@release_app.command("publish")
def release_publish(
    service: str = typer.Argument(..., help="서비스 이름"),
    version: str = typer.Argument(..., help="버전"),
    draft: bool = typer.Option(False, "--draft", "-d", help="Draft 릴리스로 생성"),
):
    """GitHub Release 생성"""
    hub_root = get_hub_root()
    tag_name = f"{service}-{version}"
    
    # gh cli 확인
    result = run_shell("which gh", cwd=hub_root, check=False)
    if result.returncode != 0:
        echo_warning("GitHub CLI (gh)가 설치되어 있지 않습니다.")
        raise typer.Exit(1)
    
    typer.echo(f"\n🚀 GitHub Release 생성: {tag_name}")
    
    releases_path = hub_root / "releases" / service / version
    notes_file = releases_path / "RELEASE-NOTES.md"
    
    cmd = f"gh release create {tag_name}"
    if notes_file.exists():
        cmd += f" --notes-file {notes_file}"
    if draft:
        cmd += " --draft"
    
    run_shell(cmd, cwd=hub_root)
    echo_success("GitHub Release 생성 완료")


app.add_typer(release_app, name="release")


# ============================================================
# STATUS Command
# ============================================================

@app.command("status")
def status():
    """전체 워크스페이스 상태 확인"""
    hub_root = get_hub_root()
    
    typer.echo("\n" + "=" * 60)
    typer.echo("📊 DECG 워크스페이스 상태")
    typer.echo("=" * 60)
    
    # 1. 현재 브랜치
    typer.echo("\n🏠 Hub 브랜치:")
    result = run_shell("git branch --show-current", cwd=hub_root, check=False)
    typer.echo(f"  → {result.stdout.strip()}")
    
    # 2. Submodule 상태
    typer.echo("\n📦 Submodule 상태:")
    for submodule in ["apps/decg-fe-monorepo", "apps/decg-be-monorepo", "apps/decg-go-monorepo"]:
        submodule_path = hub_root / submodule
        if submodule_path.exists():
            result = run_shell("git branch --show-current", cwd=submodule_path, check=False)
            branch = result.stdout.strip()
            
            # 변경사항 확인
            changes = run_shell("git status --porcelain", cwd=submodule_path, check=False)
            status_icon = "🔴" if changes.stdout.strip() else "🟢"
            
            typer.echo(f"  {status_icon} {submodule}: {branch}")
    
    # 3. Docker 상태
    typer.echo("\n🐳 Docker 컨테이너:")
    docker_compose = hub_root / "scripts" / "docker" / "docker-compose.dev.yml"
    if docker_compose.exists():
        result = run_shell(f"docker-compose -f {docker_compose} ps --format json", cwd=hub_root, check=False)
        if result.stdout.strip():
            typer.echo("  (실행 중인 컨테이너 있음)")
        else:
            typer.echo("  (실행 중인 컨테이너 없음)")
    else:
        typer.echo("  (Docker Compose 파일 없음)")
    
    # 4. 미커밋 변경사항
    typer.echo("\n📝 Hub 변경사항:")
    result = run_shell("git status --short", cwd=hub_root, check=False)
    if result.stdout.strip():
        for line in result.stdout.strip().split("\n")[:5]:
            typer.echo(f"  {line}")
        lines = len(result.stdout.strip().split("\n"))
        if lines > 5:
            typer.echo(f"  ... 외 {lines - 5}개")
    else:
        typer.echo("  (변경사항 없음)")
    
    typer.echo("\n" + "=" * 60)


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    app()
