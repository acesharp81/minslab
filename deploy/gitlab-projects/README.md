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

기존 전체 미러링과 같은 GitHub Actions secrets를 사용합니다.

- `GITLAB_USERNAME`: GitLab 사용자명
- `GITLAB_TOKEN`: 두 대상 프로젝트의 `main`에 push할 수 있는 토큰 (`write_repository` 권한)

기존 토큰이 전체 미러 저장소 전용 프로젝트 토큰이면 새 프로젝트에 쓸 수 없습니다. 두 프로젝트에 접근 가능한 사용자 토큰 또는 적절한 그룹 토큰으로 `GITLAB_TOKEN` secret을 갱신해야 합니다. 실제 토큰은 GitHub secrets에만 입력합니다. 인증값은 URL이나 파일 내용에 기록하지 않고 임시 `GIT_ASKPASS`를 통해 전달합니다.

최초 동기화는 이 workflow와 도구를 GitHub `main`에 반영하면 시작됩니다. 재실행이나 특정 프로젝트만 갱신하려면 GitHub **Actions → Sync service projects to GitLab → Run workflow**에서 브랜치 `main`과 `all`·`kjon`·`home`을 선택합니다. `main` 이외의 브랜치에서는 게시하지 않습니다.

기존 [전체 저장소 미러링](../../.github/workflows/mirror-to-gitlab.yml)은 그대로 별도 실행됩니다. 그 workflow의 `GITLAB_REPOSITORY` secret은 기존 전체 미러 저장소를 가리켜야 합니다. 이 값을 `acesharp/kjon` 또는 `acesharp/HOME`으로 바꾸면 전체 미러가 서비스 저장소를 덮어쓸 수 있으므로 서비스별 대상은 새 도구에 지정된 주소를 사용합니다.

## 로컬 실행

Git과 Python 3.10 이상이 필요합니다. Git subtree가 포함된 전체 clone에서 실행합니다.

```bash
# 네트워크 게시 없이 분리 결과 확인
python3 deploy/gitlab_sync.py all

# 선택한 프로젝트만 GitLab에 반영
python3 deploy/gitlab_sync.py kjon --push
python3 deploy/gitlab_sync.py home --push
```

로컬 push는 기존 Git credential helper를 사용할 수 있습니다. 또는 비밀관리 도구로 `GITLAB_USERNAME`·`GITLAB_TOKEN` 환경변수를 주입합니다. 토큰을 명령줄이나 저장소 파일에 쓰지 않습니다.

동기화는 **커밋된 파일과 이력만** 대상으로 합니다. 대상 폴더에 미커밋 수정이나 미추적 파일이 있으면 미리보기에서 표시하고 push는 중단합니다. 다른 서비스 폴더의 미커밋 수정은 영향을 주지 않습니다. `.gitignore`로 제외된 `.env`·운영 데이터는 새로 포함되지 않으며, 이미 커밋된 파일과 과거 이력은 분리 이력에 포함되므로 공개 전 원본에서 확인합니다.

대상 브랜치는 `main` 하나입니다. 강제 push·전체 mirror·태그 동기화·서버 재배포는 수행하지 않습니다. GitLab에서 직접 만든 README나 별도 코드 수정으로 이력이 갈라지면 일반 push가 거부됩니다. 원본과 대상의 변경을 검토해 이력을 정리한 뒤 다시 실행합니다.

## 검증

```bash
python3 -m unittest discover -s tests -p 'test_gitlab_sync.py' -v
```

테스트는 임시 원본 저장소와 로컬 bare 저장소 두 개만 사용합니다. 실제 GitLab에는 접속하거나 게시하지 않습니다. 프로젝트 범위·이력 분리, 반복 실행, 선택 갱신·삭제, 미커밋 변경 차단, 대상의 독립 수정 보호를 검증합니다.
