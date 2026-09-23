# ㅁㅁㅈ(뭐먹지?) — 대화형 매장 주문 PoC

**누구나, 자기 말로 주문할 수 있게.** 손님은 매장 메뉴를 둘러보거나 원하는 식사를 글로 설명하고, 확인된 메뉴와 옵션을 골라 모의 결제로 주문합니다. 사장님은 별도 화면에서 메뉴·알레르기·옵션을 관리하고 주문과 직원 호출을 접수합니다. 이 문서만으로 현재 서비스를 사용하고 재현할 수 있도록 실제 동작 기준으로 작성했습니다. 팀의 목표·진척·담당 인수인계는 [단일 공유 계획](docs/PLAN.md)에 있습니다.

> **현재 상태 (2026-09-24): 내부 테스트 가능.** 메뉴·주문·점주 관리가 공개 HTTPS 주소에서 동작합니다. 데모 매장과 모든 음식·알레르기 표시는 가상 테스트 데이터입니다. 실제 음식을 주문하거나 안전 판단에 사용하지 마세요. 실제 돈은 결제되지 않습니다.

## 바로 사용하기

| 사용자 | 주소 | 하는 일 |
| --- | --- | --- |
| 손님 | <https://www.minslab.kr/mmj> → **손님으로 주문하기** | 메뉴·취향·대화·그룹 추천·장바구니·모의 결제·주문 내역·직원 호출 |
| 테이블 손님 | `/poc/mwomeokji/s/orange-table/?table=A1` | A1 테이블이 선택된 손님 화면. A2/B1/B2/포장도 선택 가능 |
| 사장님 | `/poc/mwomeokji/merchant/` | 주문·직원 호출·메뉴·옵션·메뉴판 초안 관리 |
| 운영 점검 | `/poc/mwomeokji/api/health/` | DB 연결을 포함한 앱 상태 |

점주 데모 로그인 정보는 **저장소 루트의 비공개 `.env`**에 있는 `POC09_MERCHANT_EMAIL`, `POC09_MERCHANT_PASSWORD`입니다. 비밀번호를 이 문서나 커밋에 넣지 않습니다. 현재 매장은 `오렌지 테이블`, 메뉴 19개, 테이블 5개입니다.

### 손님 흐름

1. **손님으로 주문하기**를 누른 뒤 테이블을 선택합니다. 테이블 선택은 테스트에서는 선택 사항입니다.
2. **내 취향 맞추기**에서 알레르기, 엄격한 식사 조건, 맵기, 큰 글씨를 설정합니다. 이 기기의 브라우저에 저장되고 **설정 초기화**로 삭제할 수 있습니다. 서버는 현재 주문 세션의 검증에만 사용하며 24시간 만료 후 취향 상태를 정리합니다.
3. **메뉴 보기**에서 카테고리·검색으로 직접 고르거나 **추천 대화**에 “안 맵고 따뜻한 거 만원 정도로 추천해줘”처럼 적습니다. 추천 카드를 누르면 실제 메뉴·재료·가격·옵션·알레르기 확인 상태를 볼 수 있습니다.
4. 일행이 있으면 대화 화면의 **함께 주문해요**에서 손님을 추가하고 각자의 알레르기·채식·맵기 제한을 설정합니다. “3명, 4만원 안에서”처럼 입력하면 총예산 안에서 개인별 메뉴를 제안합니다. 선택한 손님의 조건은 장바구니와 주문 시 다시 검사합니다.
5. 옵션과 수량을 고른 뒤 장바구니에서 금액을 확인합니다. **모의 카드 결제** 또는 **모의 현장 결제**를 누르면 주문이 생성됩니다. 카드번호나 실제 결제 정보는 입력하지 않습니다. **주문 내역**에서 상태를 새로고침할 수 있습니다.
6. 도움이 필요하면 **직원 부르기**를 누릅니다. 사장님 화면의 직원 호출에 나타납니다.

### 사장님 흐름

1. 위 데모 계정으로 로그인합니다. 주문·직원 호출 화면은 약 12초마다 새로고침되고 수동 새로고침도 가능합니다.
2. 주문의 상태를 **새 주문 → 접수 → 조리 중 → 준비 완료 → 전달 완료** 등으로 변경합니다. 손님 주문 내역에 반영됩니다. 직원 호출은 **처리 완료**로 닫습니다.
3. **메뉴 관리**에서 새 메뉴를 만들거나 기존 메뉴를 수정하고 공개·판매 상태를 바꿉니다. 재료와 10개 알레르기 항목은 실제 확인 결과에 따라 `포함 / 확인: 미포함 / 미확인`으로 입력합니다. 공개 전 재료와 모든 항목의 점주 확인이 필요합니다.
4. 메뉴 편집기의 **메뉴 옵션**에서 그룹(예: 밥 양), 필수·최대 선택 수, 각 선택지의 추가 금액·재료·알레르기 정보를 등록하거나 삭제합니다. 옵션을 바꾸면 손님의 기존 장바구니는 주문 전에 재검증됩니다.
5. **메뉴판 가져오기**에는 `메뉴명 | 가격 | 설명`을 한 줄씩 입력합니다. 초안으로만 저장되며 재료·알레르기 확인 뒤 공개합니다. 루트 `.env`에서 OpenRouter 모드를 켜면 JPG/PNG/WEBP 이미지 인식도 사용할 수 있습니다. AI 결과는 안전 정보로 확정하지 않습니다.

## 이번 PoC의 경계

- **이번 범위에서 제외:** QR 코드 발행·인쇄, RF/NFC 태그, STT·음성 입출력, 실제 PG 결제, POS/KDS 연동, 회원가입, 다중 기기 공동 장바구니. 일반 URL의 `?table=` 진입은 동작합니다.
- 대화 입력은 **텍스트**이고 모든 중요한 조작은 터치·키보드로도 가능합니다. 음성을 나중에 붙일 때도 같은 의도 해석 → 안전 필터 → 메뉴 선택 → 주문 API를 사용하도록 분리했습니다.
- 화면 문구는 현재 한국어 중심입니다. 영어 문장은 규칙 파서의 일부 표현을 이해하지만 전체 영어 UI와 다양한 언어 번역은 후속 범위입니다.
- 데모의 `merchant_verified`는 **가상 레시피를 테스트하기 위한 상태**입니다. 실매장 도입 전 메뉴·옵션·제조 과정·교차 접촉 가능성을 실제 점주가 확인해야 합니다. “안전하다”는 보증은 하지 않습니다.

## 구조와 같은 홈페이지 내 버전 결정

```text
www.minslab.kr/mmj ─307→ /poc/mwomeokji/
기존 Python ASGI 홈페이지(main.py)
  └─ poc09_proxy.py: /poc/mwomeokji/*만 127.0.0.1:18090에 전달
      └─ PoC9 Next.js 16.3.6 / React 19.3 / Node.js 24 LTS
          ├─ 방문자·점주 화면 및 API
          ├─ 룰 추천 + 선택적 OpenRouter LLM/Jev·이미지 분석
          ├─ Prisma 7.10 + 전용 PostgreSQL 16 (127.0.0.1:18091)
          └─ 모의 결제
```

호스트 기본 Node 18이나 다른 PoC의 런타임을 변경하지 않고, **PoC9에만 Node 24**를 둡니다. Next `basePath=/poc/mwomeokji`, `trailingSlash=true`로 같은 출처의 URL과 정적 파일을 유지합니다. DB 컨테이너·볼륨·포트와 `POC09_*` 설정도 독립입니다. Python 홈페이지가 잠시 PoC9에 연결하지 못하면 해당 경로에 503을 주고 다른 PoC 경로는 계속 처리합니다.

### 실행·재현

저장소 루트에서 PoC9 폴더로 이동합니다. 호스트에 Node 24가 없으면 Docker의 `node:24-bookworm` 이미지에서 **Node 바이너리만 이 폴더 `.runtime/`에 준비**합니다. 기존 호스트 Node 버전은 바꾸지 않습니다.

```bash
cd PoC/09-mwomeokji
./scripts/prepare-node24.sh
PATH="$PWD/.runtime/bin:$PATH" npx -y npm@11 ci
```

PostgreSQL 16을 독립 실행합니다. 이 서버에는 Compose 플러그인이 없어 아래 `docker run`을 사용했습니다. Compose가 있는 개발 환경은 `docker compose up -d db`를 사용할 수 있습니다.

```bash
sudo docker run -d --name poc09-mwomeokji-db --restart unless-stopped \
  -e POSTGRES_USER=poc09 -e POSTGRES_PASSWORD=poc09_local_only -e POSTGRES_DB=poc09 \
  -p 127.0.0.1:18091:5432 -v poc09_pgdata:/var/lib/postgresql/data postgres:16-alpine
PATH="$PWD/.runtime/bin:$PATH" npm run db:generate
PATH="$PWD/.runtime/bin:$PATH" npm run db:migrate
PATH="$PWD/.runtime/bin:$PATH" npm run db:seed
PATH="$PWD/.runtime/bin:$PATH" npm run build
PATH="$PWD/.runtime/bin:$PATH" npm run start
```

이미 같은 이름의 DB 컨테이너가 있다면 새로 만들지 말고 `sudo docker start poc09-mwomeokji-db`로 시작합니다. Seed는 재실행할 수 있습니다. 개발 중에는 `npm run dev`를 사용합니다. 위 npm 명령은 모두 `PATH`의 Node 24가 필요합니다. `prisma/migrations/202609240001_init`가 초기 스키마입니다. 새 스키마 변경은 `db:dev-migrate`로 별도 마이그레이션을 만들고 운영에는 `db:migrate`를 적용합니다.

운영 서버에는 [PoC9 systemd 유닛](deploy/poc09.service)과 [만료 세션 정리 타이머](deploy/poc09-cleanup.timer)를 설치했습니다. `sudo systemctl status poc09.service`, `sudo journalctl -u poc09.service -n 100 --no-pager`, `sudo systemctl restart poc09.service`로 확인·재시작합니다. DB는 `sudo docker ps --filter name=poc09-mwomeokji-db`로 확인합니다. 변경 배포 순서는 `npm ci → db:generate → db:migrate → build → poc09.service 재시작 → smoke`입니다. Python 프록시 코드가 바뀐 경우에만 `myservice.service`도 재시작합니다. DB 백업은 `sudo docker exec poc09-mwomeokji-db pg_dump -U poc09 poc09 > poc09-backup.sql`처럼 별도 안전한 경로에 저장하고, 복구는 새 DB에 검증 후 수행합니다.

### 설정

설정과 API 키는 **루트 `.env`**에만 둡니다. `scripts/with-root-env.mjs`가 허용된 변수만 자식 프로세스에 전달합니다. 전체 루트 `.env`를 컨테이너에 주입하지 않으며 `NEXT_PUBLIC_*`에 비밀값을 두지 않습니다. 비밀값 없이 추천을 시험하려면 AI/판단 제공자를 Mock/Rules로 둡니다.

| 변수 | 기본/역할 |
| --- | --- |
| `POC09_DATABASE_URL` | 전용 PostgreSQL 접속. 미설정 시 위 로컬 DB URL |
| `POC09_MERCHANT_EMAIL`, `POC09_MERCHANT_PASSWORD` | 점주 로그인, 반드시 루트 `.env`에서 설정 |
| `POC09_SESSION_SECRET` | 방문자·점주 세션 토큰의 HMAC 키 |
| `POC09_AI_PROVIDER` | 기본 `mock`; `openrouter`면 대화 의도 추출과 이미지 읽기에 `OPENROUTER_API_KEY` 사용 |
| `POC09_LLM_MODEL`, `POC09_VISION_MODEL` | OpenRouter 모델 ID, 서버 전용 |
| `POC09_DECISION_PROVIDER` | 기본 `rules`; `jev-openrouter`면 검증된 후보의 순위만 선택적으로 조정 |
| `POC09_JEV_MODEL` | 선택 실험 모델 ID. 실패·낮은 신뢰도·형식 오류면 룰 순위를 유지 |
| `POC09_UPSTREAM` | Python 프록시의 PoC9 서비스 주소, 기본 `http://127.0.0.1:18090` |

`OPENROUTER_API_KEY` 값이 있어도 `POC09_AI_PROVIDER=mock`, `POC09_DECISION_PROVIDER=rules`이면 외부 AI를 호출하지 않습니다. Rule 단독과 Jev 비교는 같은 입력을 두 설정에서 실행하고 추천 순서·지연을 기록합니다. Jev는 가격·안전판정·메뉴 존재 여부를 바꿀 수 없습니다.

## 검증과 안전 정책

```bash
PATH="$PWD/.runtime/bin:$PATH" npm run typecheck
PATH="$PWD/.runtime/bin:$PATH" npm run lint
PATH="$PWD/.runtime/bin:$PATH" npm run test
PATH="$PWD/.runtime/bin:$PATH" npm run build
PATH="$PWD/.runtime/bin:$PATH" npm run smoke
cd ../.. && .venv/bin/python -m unittest tests.test_site_api -q
```

`smoke`는 실제 HTTP 경로에서 방문자·점주 전체 흐름, 중복 주문, 메뉴판 초안 승인까지 확인하고 테스트 주문·초안을 정리합니다. 공개 HTTPS의 모바일·PC Firefox에서도 메뉴 로딩과 화면을 확인했습니다. 운영 중에는 `/api/health/` → PoC9 systemd → DB → 루트 프록시 순서로 장애를 살핍니다.

알레르기는 메뉴와 선택 옵션 **둘 다** `merchant_verified + excludes`일 때만 해당 알레르기 조건으로 추천·주문을 허용합니다. `contains`, `unknown`, AI 추정은 통과하지 않습니다. 엄격한 식사 조건과 맵기 상한도 자동으로 완화하지 않습니다. 주문 가격은 클라이언트 값을 받지 않고 DB 메뉴·옵션에서 계산하며, 확정 트랜잭션에서 재계산합니다. 중복 요청은 idempotency key로 같은 주문을 반환합니다. 로그인 없는 점주 API는 401, 출처가 다른 변경 요청은 403, 로그인 반복은 일시 제한합니다.

## 발표 데모 시나리오

1. 손님 화면에서 A1 테이블을 고르고 **땅콩 알레르기·매운 음식 제외**를 설정합니다.
2. “안 맵고 따뜻한 거 만원 정도로 추천해줘”를 입력하고 실제 메뉴 가격·추천 이유를 확인합니다.
3. **햇살 치킨 덮밥**의 밥 양 옵션을 골라 2개를 담으면 **21,800원**이 됩니다.
4. 모의 카드 결제로 주문합니다. 주문 코드와 내역을 봅니다.
5. 사장님 화면에서 같은 코드·금액을 찾아 **접수**로 바꿉니다. 손님 내역을 새로고침합니다.
6. 메뉴판 가져오기에서 `새 메뉴 | 5500 | 설명`을 초안으로 만든 뒤 성분을 확인하고 공개합니다.

추가로 한 기기에서 손님 3명을 만들어 채식·알레르기·총예산을 각각 시험하고, 조건에 맞는 메뉴가 없을 때 직원 호출 경로를 확인합니다.
