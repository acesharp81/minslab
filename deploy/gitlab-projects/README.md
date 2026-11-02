# 서비스별 GitLab 동기화

GitHub의 MinsLab 저장소를 개발 원본으로 사용하고, 서비스별 폴더를 각각의 GitLab 저장소 최상위에 게시합니다.

| 선택값 | 원본 폴더 | GitLab 대상 |
| --- | --- | --- |
| `kjon` | `PoC/07-NationalAssembly/` | <https://gitlab.aigov.go.kr/acesharp/kjon> |
| `home` | `PoC/10-home/` | <https://gitlab.aigov.go.kr/acesharp/HOME> |
| `all` | 위 두 폴더 | 위 두 프로젝트 |

예를 들어 `PoC/07-NationalAssembly/README.md`는 `kjon` 저장소의 `README.md`가 됩니다. 상위 `PoC/` 폴더나 다른 서비스 코드는 포함되지 않습니다. `git subtree split`이 해당 폴더에 영향을 준 변경 이력을 분리하므로 이후 갱신은 기존 이력에 이어집니다. 다른 폴더만 바뀌면 분리된 커밋은 동일하여 해당 GitLab 프로젝트에는 새 변경이 생기지 않습니다.

## 자동 동기화

[sync-gitlab-projects.yml](../../.github/workflows/sync-gitlab-projects.yml)은 GitHub `main`의 두 서비스 폴더 또는 동기화 도구가 변경될 때 실행됩니다. 두 프로젝트를 각각 처리하며, 실패한 프로젝트 때문에 다른 프로젝트의 작업을 취소하지 않습니다. 프로젝트별 작업을 직렬화하고 실행 시 최신 `main`을 받아 오래된 실행이 최신 결과를 되돌리는 것을 방지합니다.

GitHub 저장소의 **Settings → Secrets and variables → Actions → New repository secret**에 다음 두 값을 각각 등록합니다.

| Secret 이름 | 등록할 값 |
| --- | --- |
| `GITLAB_KJON_TOKEN` | 국정ON `acesharp/kjon`에서 발급한 프로젝트 액세스 토큰 |
| `GITLAB_HOME_TOKEN` | the주택 `acesharp/HOME`에서 발급한 프로젝트 액세스 토큰 |

각 토큰은 `write_repository` 범위와 대상 `main`에 push할 수 있는 역할·브랜치 권한이 필요합니다. 프로젝트 액세스 토큰은 발급한 프로젝트에만 사용합니다. HTTPS 인증의 사용자명은 비어 있지 않은 값이면 되므로 workflow는 `gitlab-sync`를 사용하며 별도의 사용자명 secret은 필요하지 않습니다. [GitLab 프로젝트 토큰 문서](https://docs.gitlab.com/user/project/settings/project_access_tokens/)

workflow는 프로젝트에 해당하는 secret만 해당 작업에 전달합니다. 기존 `GITLAB_TOKEN`·`GITLAB_USERNAME` secrets는 자동 동기화에서 더 이상 사용하지 않습니다. 인증값은 URL이나 파일 내용에 기록하지 않고 임시 `GIT_ASKPASS`를 통해 전달합니다.

최초 동기화는 이 workflow와 도구를 GitHub `main`에 반영하면 시작됩니다. 재실행이나 특정 프로젝트만 갱신하려면 GitHub **Actions → Sync service projects to GitLab → Run workflow**에서 브랜치 `main`과 `all`·`kjon`·`home`을 선택합니다. `main` 이외의 브랜치에서는 게시하지 않습니다.

전체 저장소 미러링 workflow는 제거했습니다. 동기화 대상은 이 문서의 두 서비스이며, `GITLAB_REPOSITORY` secret은 더 이상 사용하지 않습니다. 기존 GitLab 전체 미러 저장소와 이미 게시한 코드는 별도로 유지됩니다.

### GitLab 네트워크 접근

2026-11-02 최초 실행에서는 GitHub 기본 실행 서버에서 `gitlab.aigov.go.kr:443`으로 연결하지 못해 두 작업이 실패했습니다. workflow는 GitLab 접속이 정상인 MinsLab 서버의 [격리된 동기화 전용 실행기](../gitlab-runner/README.md)를 사용합니다. 요청 label은 `[self-hosted, linux, x64, minslab-gitlab-sync]`이며 두 프로젝트는 순서대로 처리합니다. 실행기가 중지되면 작업이 대기하므로 GitHub **Settings → Actions → Runners**와 전용 컨테이너 상태를 확인합니다. [기존 기본 실행 서버의 실패 로그](https://github.com/acesharp81/minslab/actions/runs/41363450261)

## 로컬 실행

Git과 Python 3.10 이상이 필요합니다. Git subtree가 포함된 전체 clone에서 실행합니다.

```bash
# 네트워크 게시 없이 분리 결과 확인
python3 deploy/gitlab_sync.py all

# 선택한 프로젝트만 GitLab에 반영
python3 deploy/gitlab_sync.py kjon --push
python3 deploy/gitlab_sync.py home --push
```

로컬 push는 기존 Git credential helper를 사용할 수 있습니다. 또는 비밀관리 도구로 `GITLAB_KJON_TOKEN`·`GITLAB_HOME_TOKEN` 환경변수를 주입하면 `all --push`도 각 프로젝트의 토큰으로 나누어 인증합니다. 한 프로젝트의 토큰을 설정한 상태에서 다른 프로젝트의 토큰이 누락되면 게시 전에 중단하며 다른 프로젝트나 공통 토큰으로 대체하지 않습니다. 각 Git 프로세스에는 선택한 토큰 하나만 전달합니다.

호환성을 위해 프로젝트별 토큰을 하나도 설정하지 않은 로컬 환경에서는 기존 공통 `GITLAB_TOKEN`과 선택적인 `GITLAB_USERNAME`도 지원합니다. 사용자명을 생략하면 `gitlab-sync`를 사용합니다. GitHub secrets의 값은 서버로 자동 전달되지 않으므로 서버에서 실행할 때는 서버의 비밀관리 환경에도 토큰을 별도로 등록해야 합니다. 토큰을 명령줄이나 저장소 파일에 쓰지 않습니다.

동기화는 **커밋된 파일과 이력만** 대상으로 합니다. 대상 폴더에 미커밋 수정이나 미추적 파일이 있으면 미리보기에서 표시하고 push는 중단합니다. 다른 서비스 폴더의 미커밋 수정은 영향을 주지 않습니다. `.gitignore`로 제외된 `.env`·운영 데이터는 새로 포함되지 않으며, 이미 커밋된 파일과 과거 이력은 분리 이력에 포함되므로 공개 전 원본에서 확인합니다.

대상 브랜치는 `main` 하나입니다. 강제 push·전체 mirror·태그 동기화·서버 재배포는 수행하지 않습니다. GitLab에서 직접 만든 README나 별도 코드 수정으로 이력이 갈라지면 일반 push가 거부됩니다. 원본과 대상의 변경을 검토해 이력을 정리한 뒤 다시 실행합니다.

## 검증

```bash
python3 -m unittest discover -s tests -p 'test_gitlab_sync.py' -v
```

테스트는 임시 원본 저장소와 로컬 bare 저장소 두 개만 사용합니다. 실제 GitLab에는 접속하거나 게시하지 않습니다. 프로젝트 범위·이력 분리, 반복 실행, 선택 갱신·삭제, 미커밋 변경 차단, 대상의 독립 수정 보호를 검증합니다.
