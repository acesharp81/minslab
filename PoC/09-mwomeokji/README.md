# ㅁㅁㅈ(뭐먹지?) — 대화형 매장 주문 PoC

**누구나, 자기 말로 주문할 수 있게.** 손님은 **먹고 가기/가져가기**를 고른 뒤 일행과 취향을 평소 말처럼 입력하고, 여러 차례 대화하며 메뉴를 함께 골라 모의 결제로 주문합니다. 전체 메뉴판은 참고용입니다. 사장님은 별도 화면에서 메뉴·알레르기·옵션을 관리하고 주문과 직원 호출을 접수합니다. 이 문서만으로 현재 서비스를 사용하고 재현할 수 있도록 실제 동작 기준으로 작성했습니다. 팀의 목표·진척·담당 인수인계는 [단일 공유 계획](docs/PLAN.md)에 있습니다.

> **현재 상태 (2026-09-24): 내부 테스트 가능.** 메뉴·주문·점주 관리가 공개 HTTPS 주소에서 동작합니다. 데모 매장과 모든 음식·알레르기 표시는 가상 테스트 데이터입니다. 실제 음식을 주문하거나 안전 판단에 사용하지 마세요. 실제 돈은 결제되지 않습니다.

## 바로 사용하기

| 사용자 | 주소 | 하는 일 |
| --- | --- | --- |
| 손님 | <https://www.minslab.kr/mmj> → **손님으로 주문하기** | 방문 방식 선택·대화형 그룹 추천·장바구니·모의 결제·주문 내역·직원 호출 |
| 테이블 손님 | `/poc/mwomeokji/s/orange-table/?table=A1` | 미래 QR 진입 호환용 A1 테이블 힌트. 현재 화면에서 테이블 선택은 요구하지 않음 |
| 사장님 | `/poc/mwomeokji/merchant/` | 주문·직원 호출·메뉴·옵션·메뉴판 초안 관리 |
| 운영 점검 | `/poc/mwomeokji/api/health/` | DB 연결을 포함한 앱 상태 |

사장님 로그인 화면에는 공개 내부 테스트 계정 `demo@mmj.local` / `demo1234`가 자동 입력되어 있습니다. **로그인**만 누르면 됩니다. 별도 비공개 점주 계정은 루트 `.env`의 `POC09_MERCHANT_EMAIL`, `POC09_MERCHANT_PASSWORD`로 설정할 수 있습니다. 공개 데모 계정은 가상 매장 전용입니다. 현재 매장은 `오렌지 테이블`, 메뉴 20개, 테이블 5개입니다.

### 손님 흐름 — Tap · Talk · Together

1. **손님으로 주문하기**를 누르고 **먹고 가기** 또는 **가져가기**를 탭합니다. 테이블 번호나 회원가입은 필요하지 않습니다.
2. 대화창에 “2살 딸이랑 와이프랑 나랑 밥 먹을게. 나는 매운 걸로, 아이는 키즈 메뉴 중 달달하고 맵지 않은 걸로, 와이프는 국물 있는 걸로 주문해줘”라고 입력합니다. 세 사람의 조건을 따로 기억하고 실제 메뉴와 가격을 추천합니다. 이때 “주문해줘”는 메뉴를 골라 달라는 뜻으로 처리하며 곧바로 주문을 접수하지 않습니다. 데모 매장에는 순하고 달콤한 키즈 덮밥이 있습니다. 2살 아이에게 맞는 재료와 식감인지 보호자가 확인해야 합니다.
3. “와이프꺼는 더 얼큰한걸로 보여줘”라고 이어 말하면 와이프의 국물 메뉴를 얼큰한 메뉴로 바꿔 추천합니다. 곧이어 “알러지는 없고 얼큰한걸로”처럼 짧게 말해도 직전에 고르던 와이프 메뉴를 이어서 다룹니다. “추천한 거 전부 담아줘” 또는 “추천한 거 전부 주문해줘”로 제안을 장바구니에 담습니다. “첫 번째 담아줘”, “다른 거”, “4만원 안에서 다시 추천해줘”처럼 이어 말해도 앞서 파악한 일행을 기억합니다. “많이” 등 옵션명을 함께 말하면 해당 옵션을 우선 확인합니다. 카드의 **자세히**는 재료와 옵션을 직접 확인하는 보조 조작입니다.
4. **장바구니**에서 금액·일행별 메뉴·수량을 확인합니다. 대화에서 “주문할게”라고 말하고 “응”으로 확인하거나 장바구니의 **모의 카드/현장 결제** 버튼을 누릅니다. 실제 돈은 결제되지 않습니다. **주문 내역**에서 상태를 확인합니다.
5. 알레르기·못 먹는 재료는 대화로 알려 주세요. **내 취향** 패널에서 지속 취향·큰 글씨를 설정할 수도 있습니다. **전체 메뉴 참고**는 대화가 어려울 때만 열면 됩니다. 필요하면 “직원 불러줘”라고 말합니다.

문자 입력과 스마트폰 **음성 키보드** 입력은 같은 대화 API를 사용합니다. 앱 자체 마이크·STT·음성 출력은 아직 제공하지 않습니다. 브라우저를 새로고침하면 화면의 채팅 문장은 다시 시작하지만, 같은 주문 세션에서는 파악한 조건과 장바구니가 유지됩니다. 재방문 후 일행과 식사 조건을 처음부터 다시 설명하면 오래된 메뉴 취향·예산을 새 설명으로 교체합니다. 같은 사람에게 기록된 알레르기·엄격한 식사 조건과 **내 취향 설정**은 유지됩니다. 이전 일행의 알레르기 대상을 새 설명만으로 확인할 수 없으면 이번 주문의 공통 제한으로 유지합니다. 조건 때문에 메뉴가 없으면 화면에 저장된 제한을 알려 줍니다.

### 사장님 흐름

1. 입력된 데모 계정으로 **로그인**만 누릅니다. 새 주문에 먹고 가기/가져가기 방식이 표시됩니다. 주문·직원 호출 화면은 약 12초마다 새로고침되고 수동 새로고침도 가능합니다.
2. 주문의 상태를 **새 주문 → 접수 → 조리 중 → 준비 완료 → 전달 완료** 등으로 변경합니다. 손님 주문 내역에 반영됩니다. 직원 호출은 **처리 완료**로 닫습니다.
3. **메뉴 관리**에서 새 메뉴를 만들거나 기존 메뉴를 수정하고 공개·판매 상태를 바꿉니다. 재료와 10개 알레르기 항목은 실제 확인 결과에 따라 `포함 / 확인: 미포함 / 미확인`으로 입력합니다. 공개 전 재료와 모든 항목의 점주 확인이 필요합니다.
4. 메뉴 편집기의 **메뉴 옵션**에서 그룹(예: 밥 양), 필수·최대 선택 수, 각 선택지의 추가 금액·재료·알레르기 정보를 등록하거나 삭제합니다. 옵션을 바꾸면 손님의 기존 장바구니는 주문 전에 재검증됩니다.
5. **메뉴판 가져오기**에는 `메뉴명 | 가격 | 설명`을 한 줄씩 입력합니다. 초안으로만 저장되며 재료·알레르기 확인 뒤 공개합니다. 루트 `.env`에서 별도 이미지 AI 스위치인 `POC09_AI_PROVIDER=openrouter`를 켜면 JPG/PNG/WEBP 이미지 인식도 사용할 수 있습니다. AI 결과는 안전 정보로 확정하지 않습니다.

## 이번 PoC의 경계

- **이번 범위에서 제외:** QR 코드 발행·인쇄, RF/NFC 태그, STT·음성 입출력, 실제 PG 결제, POS/KDS 연동, 회원가입, 다중 기기 공동 장바구니. 일반 URL의 `?table=` 진입은 동작합니다.
- 대화창은 일반 텍스트 입력이므로 스마트폰의 음성 키보드로 말해 입력할 수 있습니다. 앱 STT를 나중에 붙일 때도 같은 의도 해석 → 안전 필터 → 메뉴 선택 → 주문 API를 사용합니다.
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

이미 같은 이름의 DB 컨테이너가 있다면 새로 만들지 말고 `sudo docker start poc09-mwomeokji-db`로 시작합니다. Seed는 재실행할 수 있습니다. 개발 중에는 `npm run dev`를 사용합니다. 위 npm 명령은 모두 `PATH`의 Node 24가 필요합니다. `prisma/migrations/202609240001_init`가 초기 스키마이고 `202609240002_visit_mode`가 식사 방식 필드를 추가합니다. 새 스키마 변경은 `db:dev-migrate`로 별도 마이그레이션을 만들고 운영에는 `db:migrate`를 적용합니다.

운영 서버에는 [PoC9 systemd 유닛](deploy/poc09.service)과 [만료 세션 정리 타이머](deploy/poc09-cleanup.timer)를 설치했습니다. `sudo systemctl status poc09.service`, `sudo journalctl -u poc09.service -n 100 --no-pager`, `sudo systemctl restart poc09.service`로 확인·재시작합니다. DB는 `sudo docker ps --filter name=poc09-mwomeokji-db`로 확인합니다. 변경 배포 순서는 `npm ci → db:generate → db:migrate → build → poc09.service 재시작 → smoke`입니다. Python 프록시 코드가 바뀐 경우에만 `myservice.service`도 재시작합니다. DB 백업은 `sudo docker exec poc09-mwomeokji-db pg_dump -U poc09 poc09 > poc09-backup.sql`처럼 별도 안전한 경로에 저장하고, 복구는 새 DB에 검증 후 수행합니다.

### 설정

설정과 API 키는 **루트 `.env`**에만 둡니다. `scripts/with-root-env.mjs`가 허용된 변수만 자식 프로세스에 전달합니다. 전체 루트 `.env`를 컨테이너에 주입하지 않으며 `NEXT_PUBLIC_*`에 비밀값을 두지 않습니다. 비밀값 없이 추천을 시험하려면 AI/판단 제공자를 Mock/Rules로 둡니다.

| 변수 | 기본/역할 |
| --- | --- |
| `POC09_DATABASE_URL` | 전용 PostgreSQL 접속. 미설정 시 위 로컬 DB URL |
| `POC09_MERCHANT_EMAIL`, `POC09_MERCHANT_PASSWORD` | 별도 비공개 점주 로그인, 루트 `.env`에서 설정 |
| `POC09_SESSION_SECRET` | 방문자·점주 세션 토큰의 HMAC 키 |
| `POC09_CONVERSATION_PROVIDER` | 운영 `openrouter`; 손님의 현재 입력 문장만 LLM이 해석. `mock`으로 즉시 규칙 해석 복귀 |
| `POC09_AI_PROVIDER` | 메뉴판 이미지 인식용 별도 스위치. 현재 공개 서비스는 `mock` |
| `POC09_METER_TOKEN`, `POC09_METER_URL` | 공용 AI 장부 인증 토큰과 내부 URL. 요청 내용은 기록하지 않음 |
| `POC09_LLM_MODEL`, `POC09_VISION_MODEL` | OpenRouter 모델 ID, 서버 전용. 대화 기본값 `openai/gpt-4.1-mini` |
| `POC09_DECISION_PROVIDER` | 기본 `rules`; `jev-openrouter`면 검증된 후보의 순위만 선택적으로 조정 |
| `POC09_JEV_MODEL` | 선택 실험 모델 ID. 실패·낮은 신뢰도·형식 오류면 룰 순위를 유지 |
| `POC09_UPSTREAM` | Python 프록시의 PoC9 서비스 주소, 기본 `http://127.0.0.1:18090` |

사용자가 현재 발화 한 개의 외부 전송을 승인하여 `POC09_CONVERSATION_PROVIDER=openrouter`로 운영합니다. 메뉴판 이미지용 `POC09_AI_PROVIDER=mock`, 실험 판단용 `POC09_DECISION_PROVIDER=rules`는 그대로입니다. LLM 장애·형식 오류·공유 키 소진 시 주문 대화는 로컬 규칙 해석으로 이어집니다. Rule 단독과 Jev 비교는 같은 입력을 두 설정에서 실행하고 추천 순서·지연을 기록합니다. Jev는 가격·안전판정·메뉴 존재 여부를 바꿀 수 없습니다.

### 대화형 LLM 연결과 개인정보 범위

서버의 `lib/ai.ts`에 OpenRouter `openai/gpt-4.1-mini` 해석기를 연결했습니다. **한 번의 입력 문장만** 구조화 응답으로 해석하며, 이전 대화 원문·저장된 알레르기/식이 조건·장바구니·추천 목록·세션 식별자는 외부 요청에 싣지 않습니다. OpenRouter 요청에는 `zdr: true`, `data_collection: deny`, 구조화 응답 강제를 설정했습니다. 실제 모델에 가상 문장을 보내 응답을 확인했고, 응답 형식이 틀리거나 지연되면 로컬 규칙 해석으로 돌아옵니다.

서버는 이전 턴의 **구조화된** 인원·개인별 조건·마지막 추천 ID를 세션에 저장합니다. LLM이 현재 문장에서 새 조건과 “두 번째”, “그거”, “다른 거” 같은 지시어를 추출하면 서버가 기억한 상태와 결합합니다. 이름이 붙은 일행의 조건은 해당 손님에게만 적용하고, “한 명 더 왔어” 같은 인원 변경과 명확한 정정도 이어서 처리합니다. 여러 명 중 “그 친구”가 누구인지 모호하면 다시 묻습니다. 메뉴·옵션·가격·알레르기 허용 여부는 언제나 DB와 서버 검증 코드가 결정합니다.

**배포 상태:** 사용자 승인 후 공개 서비스에서 대화 LLM이 활성화됐습니다. 매 호출의 모델·상태·토큰 수만 PoC7의 공용 계량 장부에 기록합니다. 프롬프트, 모델 응답, 세션 ID는 장부로 전송하지 않습니다. 운영자는 이 폴더에서 `PATH="$PWD/.runtime/bin:$PATH" npm run ai:usage`로 같은 OpenRouter 키의 계정 잔액, PoC4·7의 무료 모델 요청, PoC9의 직접 대화 호출을 함께 확인합니다. 공용 장부가 잠시 닿지 않아도 주문은 계속되므로 계정 잔액이 최종 비용 기준입니다.

## 검증과 안전 정책

```bash
PATH="$PWD/.runtime/bin:$PATH" npm run typecheck
PATH="$PWD/.runtime/bin:$PATH" npm run lint
PATH="$PWD/.runtime/bin:$PATH" npm run test
PATH="$PWD/.runtime/bin:$PATH" npm run build
PATH="$PWD/.runtime/bin:$PATH" npm run smoke
cd ../.. && .venv/bin/python -m unittest tests.test_site_api -q
```

`smoke`는 실제 HTTP 경로에서 방문자·점주 전체 흐름, 중복 주문, 메뉴판 초안 승인까지 확인하고 테스트 주문·초안을 정리합니다. 공개 HTTPS의 Firefox 390px 모바일·768px 태블릿·1280px PC에서 식사 방식 선택·그룹 발화·추천 담기·장바구니와 사장님 자동 입력 로그인을 확인했습니다. 운영 중에는 `/api/health/` → PoC9 systemd → DB → 루트 프록시 순서로 장애를 살핍니다.

알레르기는 메뉴와 선택 옵션 **둘 다** `merchant_verified + excludes`일 때만 해당 알레르기 조건으로 추천·주문을 허용합니다. `contains`, `unknown`, AI 추정은 통과하지 않습니다. 엄격한 식사 조건과 맵기 상한도 자동으로 완화하지 않습니다. 주문 가격은 클라이언트 값을 받지 않고 DB 메뉴·옵션에서 계산하며, 확정 트랜잭션에서 재계산합니다. 중복 요청은 idempotency key로 같은 주문을 반환합니다. 로그인 없는 점주 API는 401, 출처가 다른 변경 요청은 403, 로그인 반복은 일시 제한합니다.

## 발표 데모 시나리오

1. 손님 화면에서 **가져가기**를 선택합니다.
2. “우리 3명인데 한 명은 채식하고 한 명은 매운 걸 못 먹어”라고 말합니다. 화면 위에 추론한 일행 조건이 표시됩니다.
3. “따뜻한 거 4만원 안에서 추천해줘”라고 이어 말하고 개인별 추천과 실제 가격을 확인합니다.
4. “추천한 거 전부 담아줘”, “주문할게”, “응”으로 모의 주문을 완료합니다.
5. 사장님 화면의 **로그인** 버튼만 누르고 **가져가기** 주문을 확인·접수합니다.
6. **전체 메뉴 참고**는 대화가 어려울 때의 보조 경로임을 보여 주고, 메뉴판 초안 승인과 직원 호출을 시연합니다.
