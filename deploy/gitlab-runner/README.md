# GitLab 동기화 전용 GitHub 실행기

GitHub 기본 실행 서버에서 `gitlab.aigov.go.kr:443`에 접속할 수 없어, GitLab에 접근 가능한 MinsLab 서버에서 동기화 전용 실행기를 사용합니다. 실행기는 `minslab` 저장소에 등록하고 `minslab-gitlab-sync` label로 선택합니다.

## 실행 경계

- Docker 컨테이너의 비특권 사용자 UID/GID `10001`로 실행합니다. 호스트의 코드·환경파일·홈 디렉터리·Docker 소켓을 연결하지 않습니다.
- 전용 Docker volume `minslab-gitlab-runner-data`에 실행기 등록 정보와 별도 GitHub checkout만 저장합니다. GitLab 프로젝트 토큰은 작업 실행 시 GitHub Secrets에서 전달되며 영구 환경변수로 등록하지 않습니다.
- 전용 bridge network `minslab-gitlab-sync`에서 외부 HTTPS로 접속하며, 운영 애플리케이션의 Docker network에는 연결하지 않습니다. 공개 포트를 열지 않습니다.
- 읽기 전용 컨테이너 파일시스템, `/tmp` tmpfs, capability 전체 제거, `no-new-privileges`, PID·CPU·메모리 제한을 적용합니다.
- 이미지에 포함된 읽기 전용 pre-job hook은 저장소·`main` ref·workflow 경로·이벤트를 검사합니다. `sync-gitlab-projects.yml@refs/heads/main`의 명시적 프로젝트·원본 SHA·승인이 있는 `workflow_dispatch` 이외에는 사용자 단계를 실행하기 전에 작업을 거부합니다. [GitHub 작업 hook 문서](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/run-scripts)
- 공개 저장소의 외부 기여자 PR 작업에는 관리자 승인을 요구하도록 `all_external_contributors` 정책을 적용합니다. 이 실행기의 허용 workflow를 PR·fork 작업으로 넓히지 않습니다. 컨테이너 격리와 별개로 신뢰 경계를 유지해야 합니다. [GitHub 실행기 보안 지침](https://docs.github.com/en/actions/reference/security/secure-use)

Docker 재시작 정책은 `unless-stopped`입니다. 한 실행기가 네 프로젝트의 승인된 수동 게시를 차례로 처리합니다. 과거 자동 실행과 승인 정보가 없는 과거 수동 실행을 재실행해도 hook에서 차단합니다.

## 빌드·등록

```bash
sudo docker build -t minslab-gitlab-runner:2.338.0 deploy/gitlab-runner
sudo docker network create minslab-gitlab-sync
sudo docker volume create minslab-gitlab-runner-data
```

Dockerfile은 GitHub API에서 확인한 Linux x64 실행기 `2.338.0`과 SHA-256을 고정합니다. 업데이트할 때 GitHub의 공식 다운로드 정보와 체크섬을 확인하고 이미지를 다시 빌드합니다.

저장소 관리자 인증으로 GitHub `POST /repos/acesharp81/minslab/actions/runners/registration-token`을 호출해 받은 단기 등록 토큰을 아래 명령의 표준입력으로 전달합니다. 토큰 값을 명령줄·파일·이미지·Docker 환경변수에 기록하지 않습니다. [GitHub 등록 API](https://docs.github.com/en/rest/actions/self-hosted-runners#create-a-registration-token-for-a-repository)

```bash
sudo docker run --rm -i --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges --pids-limit=256 \
  --memory=1g --memory-swap=1536m --cpus=0.5 \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  --network minslab-gitlab-sync \
  --mount type=volume,src=minslab-gitlab-runner-data,dst=/home/runner \
  --env RUNNER_URL=https://github.com/acesharp81/minslab \
  --env RUNNER_NAME=minslab-gitlab-sync \
  minslab-gitlab-runner:2.338.0 register
```

장기 GitHub 관리자 토큰은 실행기 컨테이너에 전달하지 않습니다. 등록 과정에서 발급된 실행기 자격증명만 전용 volume에 보관됩니다.

## 시작·점검

```bash
sudo docker run -d --name minslab-gitlab-runner --init \
  --restart unless-stopped --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges --pids-limit=256 \
  --memory=1g --memory-swap=1536m --cpus=0.5 \
  --tmpfs /tmp:rw,nosuid,nodev,size=256m \
  --network minslab-gitlab-sync \
  --mount type=volume,src=minslab-gitlab-runner-data,dst=/home/runner \
  --log-opt max-size=10m --log-opt max-file=3 \
  minslab-gitlab-runner:2.338.0

sudo docker logs --tail 20 minslab-gitlab-runner
sudo docker stats --no-stream minslab-gitlab-runner
```

GitHub **Settings → Actions → Runners**에서 `minslab-gitlab-sync`가 online인지 확인합니다. 동기화 workflow는 `[self-hosted, linux, x64, minslab-gitlab-sync]`를 요청합니다. GitLab 토큰 설정은 [서비스별 동기화](../gitlab-projects/README.md)를 따릅니다.

## 중지·제거

```bash
sudo docker stop minslab-gitlab-runner
```

등록 제거는 GitHub **Settings → Actions → Runners**에서 해당 실행기를 제거한 뒤 전용 컨테이너·volume·network만 정리합니다. 운영 애플리케이션이나 데이터 volume은 정리 대상이 아닙니다. 실행기를 제거하면 workflow가 대기하므로 대체 실행기나 workflow 변경도 함께 준비합니다.
