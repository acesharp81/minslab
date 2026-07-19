# 04 - AI 언론동향 비서

AI 언론동향 비서는 기관 키워드로 뉴스를 공동 수집하고, 로컬 Ollama가 기사별 공통 분류·어조·요약을 한 번 확정한 뒤 OpenRouter의 `google/gemma-4-26b-a4b-it:free`가 케이스 적합성을 병렬 판정하는 뉴스 모니터링 PoC입니다. 외부 모델에는 공개 제목, 220자 이내 로컬 요약, 추출 근거 후보, 공개 기관·인물명과 고정 케이스 유형만 전달합니다. 로컬 근거 검증과 전송 기준을 모두 통과한 기사만 카카오톡 개인별 `나와의 채팅`에 제목, 요약, 원문 링크를 전송합니다.

이 폴더는 뉴스 도메인 로직과 화면을 모두 포함합니다. 다른 `projects/` 또는 `PoC/` 코드를 import하지 않습니다. 배포와 관리자 인증만 기존 홈페이지의 `main.py`, `/admin`, 루트 `.env`, Uvicorn 프로세스를 그대로 사용합니다. 별도 포트·Node.js·Docker 컨테이너·웹서비스는 띄우지 않습니다.

## 동작 구조

```text
기존 Nginx
  └─ 기존 Uvicorn main.py
       ├─ /poc/master-press/                 정적 대시보드
       ├─ /api/poc/master-press/*            PoC 04 API
       ├─ 기존 /admin 세션                   관리자 API 보호
       └─ 기존 ASGI lifespan
            ├─ 30초 오케스트레이터: 기관 수집·후보 배분·발송 큐
            ├─ Local Worker 1개: Ollama 공통 분류·어조·요약·임베딩
            ├─ Remote Worker 1개: OpenRouter Gemma 케이스 판정
            ├─ Remote Burst Worker 1개: 대기 10건 이상일 때 추가 처리
            ├─ SQLite 원본 DB·단계별 작업 큐·호출 사용량
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

홈페이지 `/admin`에서 로그인한 뒤 `AI 언론동향 비서` 탭을 엽니다. 관리자 화면은 기존 `minslab_admin_session` HttpOnly 쿠키를 사용합니다.

기관별 설정:

- 기관명, 약칭, 이전 명칭, 관련 인물, 제외 키워드
- 기관 공식 도메인과 RSS 주소
- 1/5/10/30/60분, 3/6시간, 1일 또는 지정 시각 수집
- 활성/중지 상태
- 회차당 검색어 수와 기사 수 제한
- 삭제 대신 중지·보관하여 기존 통계 유지

기관명·약칭·이전 명칭·인물은 각각 검색어로 요청하고 URL 기준으로 합칩니다. 기관 기사 본문은 한 번만 수집한 뒤 연결된 여러 케이스로 재분배합니다.


케이스별 설정:

- 이름, 주제 검색 사용자 프롬프트, 활성 상태
- 포함·필수·제외·긴급 키워드
- 포함·제외 언론사와 공식 RSS
- 1/5/10/30/60분 수집 또는 지정 시각
- LLM 주제 일치 시 즉시 발송 또는 기존 발송 일정 적용
- LLM 전송 기준점과 분석 보류 참고점수
- 후보 진단 보고서용 키워드·의미·LLM 혼합점수 비중(표시 유사도·발송에는 미사용)
- 복수 카카오 수신자

케이스 전체 개수 제한은 제거했습니다. 운영 케이스는 반드시 사용 기관에 종속되며 기관 공동 수집 주기를 사용합니다. 관리 화면에서도 기관 카드 안에서 소속 케이스를 생성·수정합니다. 설정을 저장할 때마다 버전과 JSON snapshot을 SQLite에 보관합니다.

## 업무 정의와 프롬프트 구조

```text
1. 기관 키워드 수집
   기관명·약칭·이전 명칭·인물·공식 RSS로 기사 수집 및 URL 중복 제거
2. Local 공통 분석
   Ollama가 기사별 본문을 한 번 읽고 주제 분류·배타적 어조·요약·엔터티·공통 근거를 확정
3. 케이스 후보 선정
   기관에 속한 케이스의 포함·필수·제외 키워드로 후보를 좁혀 독립 평가 작업 생성
4. Remote 케이스 판정
   OpenRouter Gemma가 공개 제목·220자 요약·추출 근거와 고정 케이스 유형만 받아 엄격한 JSON으로 관련 여부와 점수를 반환
5. Local 근거 재검증·발송
   모델이 고른 근거 ID가 실제 기사에 존재하는지 로컬에서 다시 확인하고 케이스별 기준을 통과한 건만 독립 발송
```

`주제 검색 사용자 프롬프트`는 로컬에서 케이스 유형과 근거 조건을 해석하는 운영 설정입니다. 외부 모델에는 원문을 보내지 않습니다. 현재 PoC의 부정 모니터링은 `행정안전부 관련 부정적 기사`처럼 짧게 작성해도 공통 시스템 규칙이 기관 직접 비판과 운영 사실 예외를 적용합니다. 재난 케이스는 이름 또는 설정에 `재난`, `사건`, `사고`, `안전` 중 핵심 범위를 명시합니다.

## 수집 정책

1. 기관명·약칭·이전 명칭·인물별로 NAVER 뉴스 검색 API의 최신 100건을 요청합니다.
2. 기관과 환경변수의 공식 RSS를 합칩니다.
3. 추적 파라미터를 제거한 URL로 중복을 제거하고 기관 제외 키워드를 적용합니다.
4. 기관 기사 본문을 한 번 수집한 뒤 연결된 케이스의 키워드로 후보를 재분배합니다.
5. `article_id` 공통분석 플래그와 `article_id + case_id` 케이스판정 플래그를 영구 관리합니다. 본문 해시나 케이스 버전이 바뀌어도 완료된 자동 분석은 다시 처리하지 않으며, 명시적인 관리자 재분석만 별도 기록으로 실행합니다.
6. 로컬 공통분석은 본문을 한 번만 읽고, OpenRouter 케이스평가는 최소 공개 증거만 사용합니다. 케이스별 결과와 발송 상태는 서로 덮어쓰지 않습니다.
7. 도메인별 요청 간격을 1초 이상 두고 응답 본문을 2MB로 제한합니다.
8. 정밀 추출은 `trafilatura`, 미설치 시 표준 HTML parser를 사용합니다.
9. 원문 본문은 기본 7일, 메타데이터는 90일 보관합니다.

차단·유료·robots 비허용 페이지는 우회하지 않고 제목과 검색 요약문만 평가합니다.

## 관련도와 개선 자료

사용자 표시 유사도와 발송 임계값:

```text
실제 유사도 = OpenRouter Gemma 케이스 점수(0~100)
발송 조건 = 실제 유사도 ≥ 케이스 임계값 + 로컬 대상·어조 근거 검증 통과
```

키워드 점수는 후보 선정과 분석보고서 진단값으로만 사용하며 표시 퍼센트에 섞지 않습니다. 기사 임베딩은 신경망·이벤트 분석에 보존하지만 케이스 판정 때 두 번째 로컬 임베딩 호출은 생략합니다. 과거 혼합점수는 감사 기록으로 남지만 기사 카드·일일 평균·신경망·카카오 메시지는 임계값과 같은 Gemma 유사도를 사용합니다. 실제 발송은 유사도가 전송 기준점 이상이고 로컬 대상·어조 근거 검증까지 통과할 때만 허용합니다. 단순 언급·연관성 부족·다른 맥락·본문 부족은 대시보드에 `발송 제외`로 남습니다. LLM 장애 시에는 `확인 대기`로 기록하고 발송하지 않습니다.

`LLM 주제 일치 시 즉시 발송`을 사용하면 기사 판정 직후 발송 큐를 처리합니다. 긴급 키워드는 주제 일치 판정을 통과한 기사에 한해 예약 시간을 우회합니다. 분석·카카오 메시지의 분류 태그 첫머리에는 기관 태그를 붙입니다. 대시보드는 기관을 먼저 선택한 뒤 해당 기관의 케이스만 선택할 수 있고, 최신 기사 20건을 스크롤로 표시하며 1분마다 자동 갱신합니다. 언론사 분포 아래에는 분류별 `기사 수(발송 수)`, 발송 상태와 최근 발송 기사를 함께 표시합니다.

저유사도 분류 예:

대시보드의 처리 현황은 한국시간 00:00부터 오늘의 처리 전·처리 중·완료·실패 건수와 완료 작업의 평균 처리시간을 보여줍니다. 기존 평가 기록은 배포 시 완료 작업으로 자동 이관하되 처리시간 평균에서는 제외합니다.

LLM은 관련도 판정과 함께 대표 분야와 세부 태그를 생성합니다. 대표 분야는 통계 기준이 흔들리지 않도록 다음 15개 중 하나로 정규화합니다.

```text
정책·행정, 정치·입법, 경제·산업, 사회·안전, 재난·환경,
과학·기술, AI·디지털, 보건·복지, 교육, 지역, 국제,
문화·생활, 인사·조직, 사건·논란, 기타
```

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
- 케이스 AI: `OPENROUTER_API_MYKEY`, `MASTER_PRESS_OPENROUTER_CASE_MODEL`
- 일일 안전 한도: `MASTER_PRESS_OPENROUTER_DAILY_SOFT_LIMIT`(기본 800회)
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

SQLite가 운영 원본이므로 Supabase 장애가 수집·점수화·발송 큐를 중단시키지 않습니다. 언론 기사 원문 본문과 카카오 토큰은 Supabase에 보내지 않고 케이스, 기사 메타데이터, 요약, 관련도만 미러링합니다. 공개된 행안부 보도자료는 RAG 검색을 위해 Markdown 본문과 청크 임베딩을 저장합니다.


## 행안부 보도자료 RAG와 보도동향

- 행정안전부 공식 보도자료 RSS(ctxCd=1012)로 신규 게시물을 찾고 상세 페이지의 #desc_pc 본문을 수집합니다.
- 원문은 data/press_releases/mois/{연도}/{nttId}.md에 front matter가 포함된 Markdown으로 저장합니다.
- 1,200자 단위(160자 겹침)로 청킹하고 기존 nomic-embed-text 임베딩을 사용합니다. 생성형 LLM 호출은 추가하지 않습니다.
- 기사–보도자료 조합은 press_release_match_jobs의 복합 PK와 article_press_release_matches 완료 기록으로 한 번만 처리합니다.
- 기관 공통 문맥으로 높아지는 코사인 기준선을 보정한 의미점수 80%와 핵심어 근거 20%를 연관도 퍼센트로 사용합니다.
- 보도동향에서는 보도자료별 사실전달·부정적·긍정적 기사 수, 요약, 담당부서·담당자·연락처, Markdown 전체와 관련 기사를 확인합니다.
- 기사 카드의 '관련 보도자료 (N)' 버튼은 연관 보도자료 팝업을 열고, 제목 선택 시 보도동향 상세로 이동합니다.

Supabase RAG 테이블은 [supabase_schema.sql](supabase_schema.sql)을 SQL Editor에서 한 번 적용해야 합니다. 이후에는 30초마다 예약 상태를 확인하고 30분 주기로 행안부 RSS 수집, Markdown 저장, 768차원 임베딩, Supabase 미러링과 관련 기사 매칭을 자동 수행합니다. Supabase 장애나 스키마 지연으로 실패한 데이터도 `supabase_synced_at`이 비어 있는 건만 다음 주기에 자동 재시도하므로 수동 버튼은 즉시 실행이 필요할 때만 사용합니다. SQL 적용 전에도 SQLite 운영 DB를 사용해 화면·매칭은 정상 동작하며 'Supabase 스키마 적용 대기'로 표시됩니다.

공개 API:

- GET /api/poc/master-press/press-releases
- GET /api/poc/master-press/press-releases/{release_id}
- GET /api/poc/master-press/articles/{article_id}/press-releases

관리자 API:

- POST /api/poc/master-press/admin/press-releases/sync

## API

공개:

- `GET /api/poc/master-press/dashboard`
- `GET /api/poc/master-press/dashboard?case_id={uuid}`

기존 관리자 세션 필요:

- `GET /api/poc/master-press/admin/bootstrap`
- `POST /api/poc/master-press/admin/organizations`
- `PUT|DELETE /api/poc/master-press/admin/organizations/{id}`
- `POST /api/poc/master-press/admin/organizations/{id}/run`
- `POST /api/poc/master-press/admin/cases`
- `PUT|DELETE /api/poc/master-press/admin/cases/{id}`
- `POST /api/poc/master-press/admin/cases/{id}/run`
- `GET /api/poc/master-press/admin/cases/{id}/improvements`
- `PUT /api/poc/master-press/admin/settings/llm-model`
- `PUT /api/poc/master-press/admin/settings/case-llm-model`
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
