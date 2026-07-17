# 04. 마스터언론

마스터언론은 최대 5개 관심 주제로 뉴스를 수집하고, 제목·검색 요약·기사 본문을 기준으로 관련성을 계산한 뒤 카카오톡 개인별 `나와의 채팅`에 제목, 요약, 원문 링크를 전송하는 PoC입니다.

이 폴더는 뉴스 도메인 로직과 화면을 모두 포함합니다. 다른 `projects/` 또는 `PoC/` 코드를 import하지 않습니다. 배포와 관리자 인증만 기존 홈페이지의 `main.py`, `/admin`, 루트 `.env`, Uvicorn 프로세스를 그대로 사용합니다. 별도 포트·Node.js·Docker 컨테이너·웹서비스는 띄우지 않습니다.

## 동작 구조

```text
기존 Nginx
  └─ 기존 Uvicorn main.py
       ├─ /poc/master-press/                 정적 대시보드
       ├─ /api/poc/master-press/*            PoC 04 API
       ├─ 기존 /admin 세션                   관리자 API 보호
       └─ 기존 ASGI lifespan
            └─ 30초마다 worker_tick()
                 ├─ NAVER 뉴스 검색 API / 공식 RSS
                 ├─ robots.txt 확인 후 제한적 본문 수집
                 ├─ 키워드 + 임베딩 + Local LLM 평가
                 ├─ SQLite 작업·캐시·발송 큐
                 ├─ Supabase 메타데이터 미러
                 └─ Kakao OAuth 사용자별 나에게 보내기
```

## 폴더 구조

```text
04-master-press/
├── backend.py                  # 홈페이지가 동적 로드하는 단일 진입점
├── project.json                # PoC 메뉴 메타데이터
├── requirements.txt            # 추가 Python 의존성
├── .env.example                # 필요한 루트 .env 변수 설명
├── supabase_schema.sql         # 격리된 Supabase 미러 테이블
├── master_press/
│   ├── config.py               # 루트/폴더 .env와 운영 제한
│   ├── storage.py              # SQLite 스키마·CRUD·큐·집계
│   ├── collectors.py           # NAVER API, RSS, robots, 본문 추출
│   ├── scoring.py              # 키워드·임베딩·LLM 복합 관련도
│   ├── kakao.py                # OAuth, 토큰 암호화·갱신, 나에게 보내기
│   ├── supabase_mirror.py      # 장애 격리형 best-effort 미러
│   └── service.py              # 수집·분석·발송 스케줄 오케스트레이션
├── web/
│   ├── index.html              # 공개 대시보드와 관리자 화면
│   ├── styles.css
│   └── app.js
└── tests/
```

생성되는 `data/master_press.sqlite3`는 Git에 포함하지 않습니다.

## 케이스 설정

홈페이지 `/admin`에서 로그인한 뒤 `마스터언론` 탭을 엽니다. 관리자 화면은 기존 `minslab_admin_session` HttpOnly 쿠키를 사용합니다.

케이스별 설정:

- 이름, 구체적인 주제 설명, 활성 상태
- 포함·필수·제외·긴급 키워드
- 포함·제외 언론사와 공식 RSS
- 5/10/30/60분 수집 또는 지정 시각
- 즉시 발송 또는 복수 지정 시각
- 전송/보류 관련도 임계점
- 키워드·의미·LLM 점수 비중
- 복수 카카오 수신자

케이스는 서버와 DB 양쪽에서 최대 5개로 제한합니다. 설정을 저장할 때마다 버전과 JSON snapshot을 SQLite에 보관합니다.

## 수집 정책

1. NAVER 뉴스 검색 API에서 케이스 키워드별 최신 100건을 요청합니다.
2. 관리자 또는 환경변수의 공식 RSS를 합칩니다.
3. 추적 파라미터를 제거한 URL로 중복을 제거합니다.
4. 제목·검색 요약문에서 필수/제외/포함 조건을 먼저 확인합니다.
5. 실행당 기본 20건만 robots.txt를 확인하고 본문을 수집합니다.
6. 도메인별 요청 간격을 1초 이상 두고 응답 본문을 2MB로 제한합니다.
7. 정밀 추출은 `trafilatura`, 미설치 시 표준 HTML parser를 사용합니다.
8. 원문 본문은 기본 7일, 메타데이터는 90일 보관합니다.

차단·유료·robots 비허용 페이지는 우회하지 않고 제목과 검색 요약문만 평가합니다.

## 관련도와 개선 자료

기본 최종 점수:

```text
키워드 30% + 임베딩 의미 유사도 40% + Local LLM 관련성 30%
```

Ollama 장애처럼 일부 평가가 불가능하면 사용 가능한 점수의 가중치를 다시 정규화합니다. 기본 전송 임계점은 75, 보류 임계점은 55입니다. 긴급 키워드는 임계점과 예약 발송을 우회할 수 있습니다.

저유사도 분류 예:

- 필수 키워드 누락
- 제외 키워드 일치
- 제목에만 키워드 존재
- 낮은 의미 유사도
- 본문 접근 불가
- LLM이 판정한 동음이의어·단순 언급·주제 불일치

관리자 화면은 최근 7일 저점 표본 수, 평균 점수, 원인 분포와 설정 개선 제안을 보여줍니다. 자동으로 키워드를 바꾸지 않으므로 설정 drift를 방지합니다.

## 카카오 수신자 방식

수신자에게 API 키나 토큰 문자열을 요구하지 않습니다.

1. 관리자가 일회용 수신자 등록 링크를 생성합니다.
2. 수신자가 링크에서 같은 Kakao Developers 앱에 로그인합니다.
3. `talk_message`에 동의합니다.
4. 서버가 사용자별 access/refresh token을 발급받습니다.
5. 토큰은 `MASTER_PRESS_TOKEN_ENCRYPTION_KEY`로 암호화해 SQLite에 저장합니다.
6. 발송 시 해당 사용자의 토큰으로 `나에게 보내기`를 호출합니다.
7. 만료 5분 전 access token을 자동 갱신합니다.

이 방식은 각 수신자의 `나와의 채팅`에 보내는 것이며 일반 단체방 자동 발송이 아닙니다. 수신자 테스트, 재동의 상태, 연결 해제를 관리자에서 처리합니다.

카카오 기본 텍스트 템플릿의 200자 제한에 맞춰 케이스명, 최종 관련도, 제목과 압축 요약을 전송합니다. `원문 보기` 버튼은 등록된 홈페이지 도메인의 기사 ID 경로를 거쳐 저장된 실제 원문 URL로 이동합니다.

## 환경설정

루트 `.env`에 [`.env.example`](.env.example)의 값을 추가합니다. 특히 다음 값이 필요합니다.

- 뉴스 수집: `MASTER_PRESS_NAVER_CLIENT_ID`, `MASTER_PRESS_NAVER_CLIENT_SECRET`
- 카카오: REST API key, client secret, 정확히 등록한 redirect URI
- 토큰 암호화: `MASTER_PRESS_TOKEN_ENCRYPTION_KEY`
- 로컬 AI: 기존 `OLLAMA_BASE_URL`, 설치 모델
- 선택 미러: 기존 `SUPABASE2_URL`, `SUPABASE2_SERVICE_ROLE_KEY`

Fernet 키 생성:

```bash
.venv/bin/python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

카카오 Redirect URI:

```text
https://홈페이지도메인/poc/master-press/oauth/kakao/callback
```

키와 토큰은 브라우저 응답, JavaScript, 로그, Supabase에 저장하지 않습니다.

## Supabase

먼저 [supabase_schema.sql](supabase_schema.sql)을 기존 프로젝트 SQL Editor에 적용합니다. RLS는 활성화하지만 브라우저용 정책은 만들지 않습니다. 홈페이지 Python service-role 경계만 미러 테이블에 접근합니다.

SQLite가 운영 원본이므로 Supabase 장애가 수집·점수화·발송 큐를 중단시키지 않습니다. Supabase에는 원문 본문과 카카오 토큰을 보내지 않고 케이스, 기사 메타데이터, 요약, 관련도 기록만 보냅니다.

## API

공개:

- `GET /api/poc/master-press/dashboard`
- `GET /api/poc/master-press/dashboard?case_id={uuid}`

기존 관리자 세션 필요:

- `GET /api/poc/master-press/admin/bootstrap`
- `POST /api/poc/master-press/admin/cases`
- `PUT|DELETE /api/poc/master-press/admin/cases/{id}`
- `POST /api/poc/master-press/admin/cases/{id}/run`
- `GET /api/poc/master-press/admin/cases/{id}/improvements`
- `POST /api/poc/master-press/admin/invites`
- `POST /api/poc/master-press/admin/recipients/{id}/test`
- `DELETE /api/poc/master-press/admin/recipients/{id}`
- `POST /api/poc/master-press/admin/tick`

OAuth:

- `GET /poc/master-press/connect?invite=...`
- `GET /poc/master-press/oauth/kakao/callback`
- `GET /poc/master-press/article/{article_id}`

## 설치와 배포

기존 가상환경에 의존성을 추가합니다.

```bash
cd /home/ubuntu/apps/myservice
.venv/bin/pip install -r requirements.txt
python3 -m py_compile main.py PoC/04-master-press/backend.py PoC/04-master-press/master_press/*.py
sudo systemctl restart myservice
curl -fsS http://127.0.0.1:8000/api/poc/master-press/dashboard
```

별도 Worker service는 만들지 않습니다. 예약 수집은 기존 Uvicorn lifespan이 관리합니다. 운영에서 Uvicorn worker 수를 늘릴 경우 중복 Worker를 막기 위한 프로세스 간 lease를 추가해야 합니다. 현재처럼 단일 프로세스에서는 모듈의 실행 lock으로 수동 실행과 예약 실행의 겹침을 막습니다.

## 운영 전 확인

- NAVER API 애플리케이션과 무료 호출량
- Kakao Login 활성화, 제품 연결 Web domain `https://www.minslab.kr`, Redirect URI, `talk_message` 동의항목
- Fernet 키 백업과 파일 권한
- Supabase 스키마 적용 여부
- 5분 수집 시 CPU/LLM 대기열
- 언론사별 robots.txt와 이용약관
- 카카오 발신자·수신자·pair 일일 쿼터
- 낮은 점수 사례의 주간 설정 개선
