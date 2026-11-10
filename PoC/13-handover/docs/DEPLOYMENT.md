# 업무바통 웹 주소 연결 기록

## v1.1.1 항목별 연필 편집 (2026-11-09)

- 업무 단위 수정 대신 각 항목의 연필에서 값·원문·수정 이력을 함께 확인합니다.
- 기존 인수인계함 14개의 포인터 보존. 이미지 `sha256:41d3bdd5f11947059e558d124cfef998cbe5e383c980b4093e54bc0bf505ab47`.
- 자동 테스트 37개와 실제 HTTPS 항목 편집·모바일·후임자 읽기 전용 검사 통과. LLM 재호출 없음.
- 공개 사용 안내·소스·시연 패키지를 1.1.1로 갱신하고 다운로드 14개 해시 확인.
- [변경 안내](FIELD_EDIT_V111.md), [검증 기록](RELEASE_VALIDATION_V111.json).


## v1.1.0 간트·다중 보고서 흐름 (2026-11-09)

- [실제 시연 인수인계함](https://www.minslab.kr/handover/#23f3f895d6dc4fceaaaff7ec1cd65c6b), [공개 완성 간트 보고서](https://www.minslab.kr/handover/downloads/flow-report.html).
- 단계별 11개 문서 → 5개 후보 → 담당자 확인·매칭 → 4개 업무 확정 → 양측 동일 보고서·인수 확인까지 실제 HTTPS/Solar로 통과.
- 39/39 작성 정답 조건, 원문 인용 177개 일치. 이번 GPT 재호출 없음. 기존 1회 평가 기록 보존.
- 자동 테스트 37개 통과. 최종 미리보기 서식·모바일·14개 공개 다운로드 해시 확인.
- 최종 이미지 `sha256:2159c1caa405533d27107124bebcbe662085064bcf3becaf66d319612d4d7b89`. 업무바통 인수인계함 13개의 포인터를 보존. 공용 Nginx·다른 PoC 컨테이너 변경 없음.
- 최초 업데이트 전 1.0 컨테이너는 `poc13-handover-before-v110-20261109`로 보존. 최종 교체 직전 백업은 `poc13-handover-before-v110-csp-20261109`.
- 상세 [검증 기록](RELEASE_VALIDATION_V110.json), [보고서 변경 내용](REPORT_GANTT_V110.md).


## 현재 배포: v1.0.0 프로그램·체험 자료 (2026-11-09)

- [사용법·샘플 자료실](https://www.minslab.kr/handover/guide), [공개 웹에서 직접 생성·확정한 시연 인수인계함](https://www.minslab.kr/handover/#75efa1db2ffc4eb3b189ffa3b0f378ac).
- 이미지 `poc13-handover:1.0.0`, ID `sha256:6f616b56a82042ae0b3ea5dc1d7c619fa273b0ce5d55e03339ec142fcad2c895`.
- 기존 인수인계함 10개의 현재·확정·인수 포인터 보존. 이전 컨테이너 `poc13-handover-before-v100-20261109` 및 자체 데이터 백업 보존.
- 자동화 테스트 34개 통과. 동일 이미지의 네트워크 차단·읽기 전용 시험과 ZIP을 별도 폴더에 풀어 실행한 시험도 각 34개 통과. 후자는 기존 잠금 의존성 환경을 재사용한 자동 재현이며 외부인의 설치 시험은 아님.
- 공개 HTTPS에서 다운로드 파일 13개의 SHA-256 일치 확인. 로그인 전 자료실 접근·업무 API 401 분리, 홈페이지 PoC 메뉴·모바일 화면 정상.
- 실제 브라우저로 받은 ZIP 등록 → Solar 분석 → 기한 원문 확인·수정 → 확정 → HTML/MD/DOCX 다운로드·PDF 출력 → 후임자 인수 → Solar 질문에서 확정 기한 우선까지 통과. JavaScript 오류 0건.
- 공개 웹 생성 결과도 7개 업무·56/56 정답값 조건, 원문 인용 76개 일치. 합성 자료 한정이며 일반 업무 정확도 100%를 뜻하지 않음.
- GPT-5.4-mini 추론 요청은 총 1회, 18,628토큰. 응답·원장 정산·수동 판정·프롬프트 변경을 보존하고 추가 GPT 호출 없이 재사용.
- 사용자 정정에 따라 영상은 제작하지 않았으며, 참가 정보·공공 GitLab 등록·공모 접수는 미정입니다.
- 검증 기록: `test-results/submission/`, 공개 비교 보고서: `release/public/quality-report.md`. 기존 타 PoC 코드·설정·컨테이너는 변경하지 않았습니다.


## 홈페이지 PoC 메뉴 연결 (2026-11-09)

- 홈페이지 PoC 메뉴에 **13. 업무바통** 추가. [메뉴 바로가기](https://www.minslab.kr/poc?project=handover).
- `project.json`을 통해 `/handover/` 앱 화면과 새 창 열기를 연결했습니다. 홈페이지 서버 재시작은 필요하지 않았습니다.
- 앱의 `frame-ancestors`를 `self`로 설정해 같은 출처의 홈페이지 안에서 앱과 최종 보고서를 표시합니다.
- 실행 이미지: `poc13-handover:0.4.0-menu` (호환 태그 `0.4.0`), ID `sha256:1f1c3ad3dd28fe5050fe089e1925248342a10528d1e55a9273fb338addb1e4fb`.
- 업무바통 컨테이너만 교체했으며, 기존 인수인계함 10개의 현재·확정·인수 포인터 보존을 확인했습니다. 이전 컨테이너는 `poc13-handover-before-menu-20261109`로 보존했습니다.
- 앱 자동화 시험 30개와 홈페이지 카탈로그 시험 2개 통과.
- 실제 Chromium에서 메뉴 클릭 → 홈페이지 스크롤 → 앱 로그인 → 최종 보고서 표시를 확인했습니다. 새 창 링크 정상, JavaScript 오류 0건. 데스크톱·모바일 화면은 `test-results/homepage-menu*.png`에 보존했습니다.

## 0.4.0 후임자 활용 기능

- 실행 이미지: `poc13-handover:0.4.0`, ID `sha256:16ebe51ab5f26bb7ae022ddeb9d9eb72f0e67377073d65b820c42b45ef77753c`.
- [새 기능을 체험할 확정 인수인계함](https://www.minslab.kr/handover/#d12cc95895dc477595456a6d91afaac4).
- 기존 사건 5개의 현재·확정·인수 포인터 보존 확인. 백업 `test-results/deployment-backup-v030/`, 이전 앱 `poc13-handover-rollback-v030` 중지 상태 보존.
- 공용 Nginx·기존 PoC 운영 코드·DB·컨테이너는 추가 변경하지 않았습니다. 업무바통만 교체했습니다.
- 최종 이미지에서 네트워크 차단·읽기 전용 자동화 시험 **30개 통과**.
- 실제 Solar 생성·수정·확정 후, 해당 합성 확정본을 재사용해 질의응답·일정/연락망·다중 파일/폴더 등록·보완 안내·HTML/MD/PDF 출력·모바일 화면을 검증했습니다. JavaScript 오류 0건.
- 테스트 중 발견한 동일 페이지의 주소 fragment 이동 미반영을 수정했습니다. 실제 Chromium에서 인수인계함 링크 이동·뒤로 가기·앞으로 가기도 검증했습니다.
- [배포·웹 확인 JSON](v040-deployment.json), [요구사항 대조 점검](COMPLETION_AUDIT_V040.md), [질의 화면](screenshots/questions-v040.png), [일정·연락망](screenshots/schedule-v040.png), [보완 안내](screenshots/readiness-v040.png).
- [자동 브라우저 조작 기록](browser-smoke-v040.webm): 약 11초의 빠른 무음 회귀 시험 기록이며 확정본 재사용부터 시작합니다. 공모 설명용 내레이션·편집 시연 영상은 아닙니다.

## 이전 배포: 0.3.0 보고서 보강

- 이미지: `poc13-handover:0.3.0`, ID `sha256:240557a82869342264e24365ef9c29ccf5c43fe3a8b6d48de74a5ffc16cc0647`.
- [확정 보고서가 있는 체험 인수인계함](https://www.minslab.kr/handover/#5d0db79ed1fc4436a5f7b99b7fdbdcfd). 로그인 후 보고서가 기본 표시됩니다.
- 기존 사건 3개의 현재·확정·인수 포인터를 보존했고, 구버전 확정본도 새 보고서 렌더러에서 정상 표시됨을 확인했습니다. 배포 중 추가한 합성 시험 사건은 별도 보존했습니다.
- 자체 데이터 백업: `test-results/deployment-backup-v020/`. 이전 정상 앱은 `poc13-handover-rollback-v020`으로 중지 상태 보존합니다. 검증 중 화면 내 표시를 막았던 보안 헤더를 수정하고 재배포했습니다.
- 업무바통 컨테이너만 교체했습니다. 공용 Nginx·기존 서비스·기존 데이터 볼륨 설정은 변경하지 않았습니다.
- 최종 이미지에서 자동화 시험 **24개 통과**.
- 실제 HTTPS/Chromium에서 Solar 분석 → 수정 → 확정 → 보고서 → 인수자 확인 → MD/HTML 다운로드 통과. 양측 보고서 URL과 본문이 동일하고, 브라우저 오류 0건·모바일 가로 넘침 없음.
- 화면 내 보고서의 CSS 적용과 인쇄 버튼 실행을 확인했습니다. A4 PDF 14쪽에서 완료 실적·남은 업무·현안 텍스트를 직접 추출해 확인했습니다. 부록도 포함된 분량입니다.
- [브라우저·배포 확인 JSON](report-v030-deployment.json), [보고서 첫 화면](screenshots/report-top.png), [보고서 PDF](examples/report-v030-demo.pdf), [변경 상세](REPORT_V030.md).

아래는 최초 연결 및 0.2.0 배포 당시의 기록입니다.

- 적용 시각: 2026-11-08 09:55 KST.
- 주소: **https://www.minslab.kr/handover/**
- 사용자 승인: “웹 주소 연결 허용 — /handover/ 경로만 추가”.
- 독립 앱: `poc13-handover` 컨테이너, `127.0.0.1:18130`, `poc13-handover-data` 영구 볼륨.
- 당시 버전·모델: **0.2.0 / Solar Pro 4 실제 연결 완료**. 최초 0.1.0 배포는 로컬 규칙 모드였으며 아래 업그레이드로 전환했습니다.

## 변경 범위

`/etc/nginx/sites-available/myservice`의 `www.minslab.kr` HTTPS 서버 블록에 다음 두 경로만 추가했습니다.

- `/handover` → `/handover/` 리디렉션.
- `/handover/` → 독립 앱 `http://127.0.0.1:18130/` 프록시.

기존 `/` 경로, TLS 인증서, 기존 PoC 앱·DB·컨테이너 설정은 그대로 유지했습니다. 설정 원본을 백업하고 `nginx -t` 성공 후 `systemctl reload nginx`로 재적용했습니다. 전체 서비스 종료·재시작은 하지 않았습니다.

## 백업과 식별

- 백업: `/var/backups/poc13-handover/myservice-20261108T005545Z.conf` (root 전용).
- 변경 전 SHA-256: `e882bc1eb717405d8975256a6bc51195ee7f75c43b79c4dff7933c317d8d959f`.
- 변경 후 SHA-256: `94e68de4210ff926f426979febe4c0125a21470d95fe20c55ddb23f919c5aa33`.
- 적용한 경로 설정: [nginx-handover.conf.example](nginx-handover.conf.example).

롤백 시 현재 설정과 위 변경 후 해시가 같은지 먼저 확인합니다. 이후 다른 운영 변경이 있었다면 백업 전체를 덮어쓰지 말고 업무바통의 두 location 블록만 제거해야 합니다. 복원 후 반드시 `nginx -t`를 통과시킨 뒤 reload합니다. 앱 컨테이너나 전용 데이터 볼륨을 지울 필요는 없습니다.

## 실제 HTTPS 검증

| 확인 항목 | 결과 |
|---|---|
| 기존 홈페이지 `/` | HTTP 200, 기존 MinsLab 화면 |
| `/handover` | HTTP 302 → `/handover/` |
| 앱 홈·정적 JS | HTTP 200 |
| `/handover/api/health` | HTTP 200, 앱 JSON 응답 |
| 로그인 전 사건 API | HTTP 401 |
| 올바른 공유 코드 로그인 | HTTP 200 |
| 접속 쿠키 | Secure, HttpOnly 적용 |
| 실제 Chromium 조작 | 샘플 등록·초안·기한 수정·근거 조회·검색·확정·후임자 확인·MD 다운로드 PASS |
| 모바일 390×844 | 가로 넘침 없음 |
| 브라우저 JavaScript 오류 | 0건 |

검증에는 합성 샘플만 사용했습니다. 접속 코드나 모델 키는 이 문서에 기록하지 않습니다. 접속 코드는 프로젝트 전용 Git 제외 `.env`에서 관리합니다.

## 0.2.0 Solar Pro 4 업그레이드

2026-11-08에 기존 업무바통의 활성 작업이 없음을 확인하고 자체 데이터 전체를 백업한 뒤 해당 컨테이너만 교체했습니다. 공용 Nginx 설정은 추가 변경하지 않았습니다.

- 실행 이미지: `poc13-handover:0.2.0`.
- 이미지 ID: `sha256:67e641901c99f00a392c5037534b75c81257f651547322cade860962a2e31e03`.
- 백업: `test-results/deployment-backup-v010/` (Git 제외).
- 이전 앱: `poc13-handover-rollback-v010`이라는 이름으로 중지 상태 보존.
- 기존 사건 2개의 현재·확정·인수 포인터 보존 확인. 같은 `poc13-handover-data` 볼륨 사용.
- 프로젝트 `.env`에서 모델 연결을 유지하며 기존 다른 서비스의 설정 파일은 변경하지 않았습니다. 자격 증명 사용 범위는 [Solar 보고서](SOLAR4_VALIDATION.md)에 기록했습니다.

실제 HTTPS에서 새 합성 샘플을 등록해 **Solar 분석 → 원문·검색 → 기한 수정 → 확정 → 후임자 인수 확인 → MD 다운로드**를 Chromium으로 수행했습니다. API에서도 해당 확정본의 모드가 `llm`, 응답 모델이 `solar-pro4-260806`임을 확인했습니다. JavaScript 오류는 0건이며 모바일 가로 넘침이 없었습니다.

이어 업무바통만 재시작한 뒤 모델 연결과 동일 확정 판본 ID·내용 해시가 유지됨을 확인했습니다. 컨테이너는 `running / healthy`이며 기존 홈페이지도 HTTP 200입니다. [기계 판독 확인 기록](solar4-deployment-report.json), [갱신한 화면](screenshots/review.png), [실제 조작 영상](browser-smoke.webm)을 함께 보존했습니다.

롤백이 필요하면 활성 작업이 없는지 확인한 뒤 새 업무바통 컨테이너만 중지하고 이전 컨테이너 이름을 복원해 시작합니다. 볼륨은 삭제하지 않습니다. 이전 컨테이너의 환경에는 Solar 키가 없으므로 0.1.0 롤백은 로컬 규칙 모드로 돌아갑니다.
