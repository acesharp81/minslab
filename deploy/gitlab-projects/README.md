# 서비스별 GitLab 동기화

GitHub의 MinsLab 저장소를 개발 원본으로 사용하고, 서비스별 폴더를 각각의 GitLab 저장소 최상위에 게시합니다. GitLab만 받아 독립 설치·테스트·수정할 수 있도록 소스·설정 예시·의존성·DB migration·실행 데이터·fixture·문서를 포함합니다. 검증용 덤프·화면 캡처인 `docs/evidence/`와 운영 복구용 캡처·감사 스냅샷인 `data/recovery/`는 GitHub에 남깁니다.

| 선택값 | 원본 폴더 | GitLab 대상 |
| --- | --- | --- |
| `kjon` | `PoC/07-NationalAssembly/` | <https://gitlab.aigov.go.kr/acesharp/kjon> |
| `home` | `PoC/10-home/` | <https://gitlab.aigov.go.kr/acesharp/HOME> |
| `check` | `PoC/08-AICommonPlatformRadar/` | <https://gitlab.aigov.go.kr/acesharp/check> |
| `baton` | `PoC/13-handover/` | <https://gitlab.aigov.go.kr/acesharp/baton> |
| `all` | 위 네 폴더 | 위 네 프로젝트 |

예를 들어 `PoC/07-NationalAssembly/README.md`는 `kjon` 저장소의 `README.md`가 됩니다. 상위 `PoC/` 폴더나 다른 서비스 코드는 포함되지 않습니다. `git subtree split`으로 프로젝트 이력을 분리한 다음 `git fast-export`·`fast-import`의 경로 선택으로 `docs/evidence/`와 `data/recovery/`를 과거 이력에서도 제외합니다. 국정ON은 `e9482fd`, Home은 `1d9fd7d`의 재구성·보안 보완 버전을 최초 공개 기준으로 삼고 그 이전 이력은 GitHub에 보존합니다. 기준 버전의 전체 파일로 공유 이력을 시작하고 이후 작성자·메시지·변경 이력을 이어 갑니다. 트리는 원본에서 이 생성 증빙 경로만 제외한 결과와 일치하는지 검증합니다. 원본 branch·index·작업 파일·FETCH_HEAD는 바꾸지 않습니다. 다른 폴더만 바뀌면 분리된 커밋은 동일하여 해당 GitLab 프로젝트에는 새 변경이 생기지 않습니다.

PoC 8·13의 최초 공개 기준 원본은 `72d1af3ffdd3cc2761f83f778dc16f9d7c7d598e`입니다. 현재 파일 전체로 독립 이력을 시작하고 이후에는 같은 기준점을 유지합니다. 이 기준점은 이미 게시한 이력을 재작성하는 용도로 바꾸지 않습니다.

## 승인 후 수동 게시

2026-11-11부터 네 프로젝트 모두 **자동 게시를 중단**합니다. GitHub에서 개발·커밋·push·병합해도 GitLab 제출본은 변경되지 않습니다. [sync-gitlab-projects.yml](../../.github/workflows/sync-gitlab-projects.yml)은 `workflow_dispatch`만 허용합니다.

GitHub **Actions → Sync service projects to GitLab → Run workflow**에서:

1. 브랜치 `main`을 선택합니다.
2. 게시할 `check`·`baton`·`kjon`·`home` 중 하나를 선택합니다. `all`은 네 프로젝트 모두를 갱신합니다.
3. 사용자가 검토하고 승인한 GitHub 원본 커밋 SHA **40자리 전체**를 입력합니다.
4. 제출본 갱신 승인 항목을 체크하고 실행합니다.

SHA는 실행 시점의 controller 커밋에 포함된 이력이어야 합니다. 승인 입력이 없거나 형식이 다르면 게시하지 않습니다. 대기 중 새 커밋이 올라와도 입력한 SHA만 내보내며, 재실행도 같은 승인 SHA를 사용합니다. SHA가 오래되어 GitLab 이력을 되돌려야 하는 경우 일반 push가 거부합니다. 서로 다른 수동 실행도 한 번에 하나만 처리합니다. `all`은 토큰과 미커밋 상태를 사전 검사한 뒤 순서대로 게시하지만, 별도 저장소 네 개의 원격 반영은 원자적이지 않으므로 중간 서버 오류 시 일부만 반영될 수 있습니다.

출품 이후 새 버전 게시 여부는 사용자가 결정합니다. 작업 요청이나 GitHub 병합 자체를 GitLab 게시 승인으로 간주하지 않습니다. 실행기 이미지의 읽기 전용 hook도 자동 `push` 이벤트와 승인 정보가 없는 과거 수동 실행의 재실행을 거부합니다. 토큰을 가진 사용자 또는 저장소 관리자가 직접 실행하는 변경까지 이 워크플로가 제한하는 것은 아닙니다.

GitHub 저장소의 **Settings → Secrets and variables → Actions → New repository secret**에 다음 값을 각각 등록합니다.

| Secret 이름 | 등록할 값 |
| --- | --- |
| `GITLAB_KJON_TOKEN` | 국정ON `acesharp/kjon`의 프로젝트 액세스 토큰 |
| `GITLAB_HOME_TOKEN` | the주택 `acesharp/HOME`의 프로젝트 액세스 토큰 |
| `GITLAB_CHECK_TOKEN` | PoC 8 `acesharp/check`의 프로젝트 액세스 토큰 |
| `GITLAB_BATON_TOKEN` | PoC 13 `acesharp/baton`의 프로젝트 액세스 토큰 |

각 토큰은 `write_repository` 범위와 대상 `main`에 push할 수 있는 역할·브랜치 권한이 필요합니다. 기본 보호 브랜치에 맞춰 Maintainer 역할을 사용하며 `api`·`read_api`는 필요하지 않습니다. 프로젝트 액세스 토큰은 발급한 프로젝트에만 사용합니다. HTTPS 인증 사용자명은 `gitlab-sync`이며 별도 사용자명 secret은 필요하지 않습니다. [GitLab 프로젝트 토큰 문서](https://docs.gitlab.com/user/project/settings/project_access_tokens/)

workflow는 네 토큰을 게시 도구에 전달하고, 도구는 각 Git 자식 프로세스에 선택한 프로젝트의 토큰 하나만 전달합니다. 기존 `GITLAB_TOKEN`·`GITLAB_USERNAME`·`GITLAB_REPOSITORY` secrets는 workflow에서 사용하지 않습니다. 인증값은 URL이나 파일 내용에 기록하지 않고 임시 `GIT_ASKPASS`를 통해 전달합니다. 실행 가능한 `RUNNER_TEMP`에 인증 도구를 만들고 삭제합니다.

최초 PoC 8·13 게시도 자동으로 시작하지 않습니다. 현재 버전으로 게시해 달라는 사용자 요청에 따라 검증된 초기 커밋 SHA를 지정하여 두 프로젝트만 수동 실행합니다. 기존 국정ON·the주택 제출본은 이 최초 게시에 포함하지 않습니다. 네 프로젝트 모두 이후 변경에는 별도 승인이 필요합니다.

전체 저장소 미러링 workflow는 제거된 상태를 유지합니다. 기존 GitLab 전체 미러 저장소와 이미 게시한 코드는 별도로 유지됩니다.

### GitLab 네트워크 접근

2026-11-02 최초 실행에서는 GitHub 기본 실행 서버에서 `gitlab.aigov.go.kr:443`으로 연결하지 못해 두 작업이 실패했습니다. workflow는 GitLab 접속이 정상인 MinsLab 서버의 [격리된 동기화 전용 실행기](../gitlab-runner/README.md)를 사용합니다. 요청 label은 `[self-hosted, linux, x64, minslab-gitlab-sync]`이며 선택한 프로젝트를 순서대로 처리합니다. 실행기가 중지되면 작업이 대기하므로 GitHub **Settings → Actions → Runners**와 전용 컨테이너 상태를 확인합니다. [기존 기본 실행 서버의 실패 로그](https://github.com/acesharp81/minslab/actions/runs/41363450261)

## 로컬 실행

Git과 Python 3.10 이상이 필요합니다. Git subtree가 포함된 전체 clone에서 실행합니다.

```bash
# 네트워크 게시 없이 분리 결과 확인
python3 deploy/gitlab_sync.py all

# 사용자가 승인한 전체 커밋 SHA를 직접 지정 (HEAD를 자동으로 선택하지 않음)
source_sha=승인한_40자리_커밋_SHA
python3 deploy/gitlab_sync.py check --source "$source_sha"
python3 deploy/gitlab_sync.py check --source "$source_sha" --approve-source "$source_sha" --push
```

로컬 push는 기존 Git credential helper를 사용할 수 있습니다. 또는 비밀관리 도구로 위 네 프로젝트별 토큰 환경변수를 주입하면 승인 SHA를 지정한 `all --push`도 각 프로젝트의 토큰으로 나누어 인증합니다. 한 프로젝트의 토큰을 설정한 상태에서 다른 프로젝트의 토큰이 누락되면 게시 전에 중단하며 다른 프로젝트나 공통 토큰으로 대체하지 않습니다. 각 Git 프로세스에는 선택한 토큰 하나만 전달합니다.

호환성을 위해 프로젝트별 토큰을 하나도 설정하지 않은 로컬 환경에서는 기존 공통 `GITLAB_TOKEN`과 선택적인 `GITLAB_USERNAME`도 지원합니다. 사용자명을 생략하면 `gitlab-sync`를 사용합니다. GitHub secrets의 값은 서버로 자동 전달되지 않으므로 서버에서 실행할 때는 서버의 비밀관리 환경에도 토큰을 별도로 등록해야 합니다. 토큰을 명령줄이나 저장소 파일에 쓰지 않습니다.

동기화는 **커밋된 파일과 이력만** 대상으로 합니다. 대상 폴더에 미커밋 수정이나 미추적 파일이 있으면 미리보기에서 표시하고 push는 중단합니다. 다른 서비스 폴더의 미커밋 수정은 영향을 주지 않습니다. `.gitignore`로 제외된 `.env`·운영 데이터는 새로 포함되지 않으며, 증빙 제외 정책을 적용한 커밋 파일과 과거 이력은 분리 이력에 포함되므로 공개 전 원본에서 확인합니다.

대상 브랜치는 `main` 하나입니다. 강제 push·전체 mirror·태그 동기화·서버 재배포는 수행하지 않습니다. GitLab에서 직접 만든 README나 별도 코드 수정으로 이력이 갈라지면 일반 push가 거부됩니다. 원본과 대상의 변경을 검토해 이력을 정리한 뒤 다시 실행합니다.

최초 대용량 push에서는 GitLab 앞단의 재전송 요구로 `unable to rewind rpc post data`·`curl 65`가 발생할 수 있습니다. 이 서버의 실제 실패에 맞춰 push 명령에만 `http.postBuffer=268435456`을 적용합니다. 256MiB 이하의 요청을 버퍼링해 재전송할 수 있게 하며 전역 Git 설정은 바꾸지 않습니다. HTTP/1.1도 해당 push에만 지정합니다. workflow의 `--diagnose`는 HTTP 상태 코드·요청 바이트 수·업로드 완료 시각·총 소요 시간만 출력합니다. 인증 헤더·응답 본문은 출력하지 않고 임시 추적 파일은 성공·실패 모두 삭제합니다.

## 필수 보안 검사 대응과 실제 게시 확인

GitLab의 필수 pre-receive 검사는 그대로 유지합니다. 최초 실행에서 나타난 XML·pickle·동적 SQL·URL 처리·SHA1 경고에 맞춰 코드를 보완했습니다. 국정ON의 세 Docker 이미지 식별자와 Home의 공개 체크섬·예시 변수명은 정확한 전체 줄만 Gitleaks 예외로 기록하고 기본 탐지 규칙은 유지했습니다. 별도의 임의 비밀값 탐지 테스트도 유지합니다.

국정ON은 [2026-11-02 실행](https://github.com/acesharp81/minslab/actions/runs/41373360452)에서 Gitleaks·Semgrep·OSV-Scanner·Trivy·Syft를 모두 통과하고 실제 `main` 게시가 완료됐습니다. 공개 GitLab을 새로 clone하여 Python 924 passed / 28 skipped를 확인했습니다. 선택하지 않은 작업의 생략 표시는 게시 성공으로 계산하지 않습니다.

Home은 전송량과 최초 이력을 줄여도 업로드 후 약 60초 응답 대기와 재전송·502가 반복됐습니다. 재현한 전체 웹 소스 검사는 약 54초였고, 파일 전체 IIFE를 비공개 블록 범위와 동일한 공개 함수 속성을 유지하는 구조로 바꾸자 약 27초로 줄었습니다. 규칙·소스 파일·탐지 결과를 제외하지 않았습니다. 이후 서버가 약 57초 안에 실제 검사 결과를 반환하여 502 대신 구체적인 거부 항목을 확인할 수 있었습니다. 마지막 대형 모듈 두 파일도 같은 방식으로 개선했습니다.

서버가 지적한 다섯 검증 스크립트의 `urllib` 요청은 HTTP 전용 requests로 바꾸고, HTTP 실패를 원문으로 저장하지 않게 했습니다. 키를 포함한 요청 예외는 URL·키를 출력하지 않습니다. JavaScript 조건식 `조건?.6:값`은 계산 의미를 유지한 `조건 ? 0.6 : 값`으로 표기하여 검사기 오류를 해결했습니다. OSV가 지적한 anyio·certifi 등 HTTP 간접 의존성은 검증 버전을 명시하고, Docker는 UID/GID `1000:1000`으로 실행하도록 보완했습니다. 기존 root 소유 bind mount를 새 이미지에서 재사용할 때의 권한 이관 조건은 [Home 재구성 문서](../../PoC/10-home/RECONSTRUCT.md)에 기록했습니다.

[최초 두 프로젝트 게시 성공](https://github.com/acesharp81/minslab/actions/runs/41378740360) 후 [후속 갱신 성공](https://github.com/acesharp81/minslab/actions/runs/41379457979)을 확인했습니다. Home은 `32b437da`에서 `8845269b`로 강제 push 없이 전진했고 국정ON은 기존 `3af1d4e8`을 유지했습니다. Home 후속 push는 약 57.3초였습니다. 새 변경으로 검사 부하가 커지면 약 60초 응답 제한과 맞물린 502가 재발할 수 있으므로 `--diagnose`의 업로드 완료·상태·소요 시간과 최신 서버 검사 결과를 구분해 확인합니다.

## 검증

```bash
python3 -m unittest discover -s tests -p 'test_gitlab_sync.py' -v
```

테스트는 임시 원본 저장소와 로컬 bare 저장소 네 개만 사용합니다. 실제 GitLab에는 접속하거나 게시하지 않습니다. 프로젝트 범위·이력 분리, 반복 실행, 선택 갱신·삭제, 미커밋 변경 차단, 대상의 독립 수정 보호, 승인 누락 차단과 오래된 승인 버전의 고정 게시를 검증합니다. 실행기 검사는 `python3 -m unittest discover -s tests -p 'test_gitlab_runner_guard.py' -v`로 실행합니다.

## 2026-11-02 Home 전송 진단 및 게시 범위

79,281,811바이트 요청은 약 1.3초 만에 전송됐습니다. 이후 약 60초 뒤 재전송되고 다시 약 60초 뒤 502가 반환됐습니다. HTTP/1.1에서도 동일했습니다. 인증이나 전송 속도 실패가 아니라 업로드 이후 응답 대기에서 실패했으며, 서버 내부 원인은 직접 관측하지 못했습니다. [진단 실행](https://github.com/acesharp81/minslab/actions/runs/41369865934)

최신 Home 트리 약 404MiB 중 약 371MiB가 `docs/evidence/`입니다. 사용자와 합의하여 이 생성 증빙을 공개 이력에서 제외합니다. 2026-11-08부터 국정ON의 복구 음성·감사 덤프인 `data/recovery/`도 같은 생성 증빙으로 분류합니다. 실행 코드·회귀 테스트에서 이 복구 경로를 참조하지 않는 것을 확인했으며 GitHub 원본은 보존합니다. 실행·다른 방식의 재사용에 필요한 데이터, migration, dependency, fixture는 포함합니다. 증빙을 읽던 월별 통계 회귀 테스트의 공식 HTML/PDF는 `tests/fixtures/monthly_release_202608/`에 보존해 제외 정책과 분리했습니다. 다른 파일이나 보안 검사 규칙을 임의로 제외하지 않습니다.

### 최초 공개 기준

증빙 제외로 전송량을 약 79MB에서 8MB로 줄인 뒤에도 업로드 후 약 60초 재전송·60초 뒤 502가 반복됐습니다. 단순 용량 감소만으로 해결됐다고 볼 수 없습니다. 전체 과거 이력의 일괄 전송을 분리하기 위해 최초 공유 이력은 국정ON `e9482fd1005e7a01301d908ec91d8d2de6912272`, Home `1d9fd7d34f85190c1ca97337e8b5aa5465146d2f`부터 시작합니다. Home의 기준은 빈 저장소임을 확인한 뒤 의존성·화면 모듈 보완까지 포함하도록 확정했습니다. `git fast-export --full-tree`로 기준 시점의 모든 필수 파일을 포함하고 이후 커밋은 일반 fast-forward로 갱신합니다. 이전 이력은 GitHub에 남으며 이 기준점은 최초 게시 후 임의로 바꾸지 않습니다. 강제 push나 필수 검사 우회는 사용하지 않습니다.

실제 공개 GitLab clone 검증: 국정ON Python 924 passed / 28 skipped, Home Python 1124 passed / 2 skipped, JavaScript 141 passed. 두 이미지 빌드와 새 DB migration·health 응답을 확인했습니다. Home의 0018 migration 중복 생성과 Git에 빠졌던 HWPX fixture도 보완했습니다. [국정ON 재구성](../../PoC/07-NationalAssembly/RECONSTRUCT.md), [Home 재구성](../../PoC/10-home/RECONSTRUCT.md).

## 2026-11-02 최종 상태와 운영 영향

| 대상 | 확인 결과 |
| --- | --- |
| 국정ON GitLab `main` | `3af1d4e84a6d454df8751b26cb0164b43b528964`, 해당 프로젝트 557개 파일 |
| Home GitLab `main` | `8845269b343d63350cd9b1235d158717eb783293`, 해당 프로젝트 922개 파일 |
| GitHub | 서비스 변경은 `71c28b2b`까지 `main` 반영, 두 게시 작업 성공 |
| 독립 설치 | 새 DB migration·이미지 빌드·health 200, Home UID1000 데이터 쓰기 확인 |
| Firefox | 수정 소스의 초기 화면·정책 지도 표시, JavaScript 예외 0 |
| 본서비스 | 메인·Home 화면·Home 조회 API·국정ON health 모두 HTTP 200 |

Home 내부·공개 overview의 최종 재확인은 각각 0.03초·0.02초였습니다. 앞선 조회에서는 17.84초도 관측되어 이 결과를 전체 조회의 지연 보장으로 해석하지 않습니다. 운영 API 컨테이너의 기존 시작 시각과 재시작 0회를 확인했으며 이번 작업에서 API·worker를 교체하지 않았습니다. 새 DB·데이터 volume을 사용한 임시 검증 컨테이너·network·volume은 정리했습니다. 동기화 실행기는 별도 컨테이너·제한된 자원·격리된 volume으로 유지합니다.

GitLab 공개 파일로 새 환경의 앱·DB schema·테스트를 재구성할 수 있습니다. 설치용 외부 의존성, 자신의 원천 API 키, 운영 누적 기록을 복원할 때 필요한 별도 백업은 각 재구성 문서에 설명합니다.
