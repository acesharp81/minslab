# HOME 운영

현재 배포는 Docker CLI 방식입니다. 전용 컨테이너 `poc10-home-api`, `poc10-home-db`, network `poc10-home`, DB volume `poc10-home-pgdata`, loopback API `18100`을 사용합니다.

## 재배포와 점검

저장소 루트에서 실행합니다.

```bash
sudo python3 PoC/10-home/scripts/deploy.py
curl --fail http://127.0.0.1:18100/health
sudo docker logs --tail 50 poc10-home-api
```

실행기는 `.env`를 서버 전용 `data/runtime/*.env`에 권한 `600`으로 전달하고 Alembic migration 후 API를 시작합니다. 이전 API 컨테이너는 중지 후 timestamp가 붙은 backup 이름으로 보존합니다. DB volume과 `data/raw`는 유지합니다.

부모 `main.py`/`poc10_proxy.py` 변경 시 회귀 검사 후 `sudo systemctl restart myservice`가 필요합니다. HOME 내부 코드는 HOME API만 재배포합니다. Compose 방식과 현재 CLI 방식은 컨테이너 관리자를 혼용하지 않습니다.

## 수집

최신 정책·사업 원천 7개와 과거 정책·공사 원천 2개를 시작 시와 24시간마다 자동 수집합니다. MinsLab 관리자 로그인 → HOME → 수집 원천 → `지금 수집`으로 요청할 수 있습니다. API 테스트 표본 3개 원천은 `manual_only=True`로 제외하며, HOME → API 테스트 데이터 → `확대 표본 수집`으로 실행합니다.

```bash
sudo docker exec poc10-home-api python -m scripts.collect
sudo docker exec poc10-home-api python -m scripts.collect --source lh_sale
sudo docker exec poc10-home-api python -m scripts.collect --samples
sudo docker exec poc10-home-api python -m scripts.collect --history
sudo docker exec poc10-home-api python -m scripts.collect --source vworld_district
sudo docker exec poc10-home-api python -m scripts.collect --source lh_block_location
```

`lh_block_location`은 LH 공개 지도의 블록 라벨점을 키 없이 자동 수집합니다. 정확한 블록 경계나 건물 형상이 아니며 서울·경기 현재 사업 블록 98개 중 66개에 완전 일치로 연결됐습니다. 자세한 기준과 미확보 범위는 [MAPS_UI_PLAN.md](MAPS_UI_PLAN.md#14-1차-구현검증-2026-10-03)에 기록합니다.

`vworld_district`는 기존 VWorld 키로 공식 공동주택용지 도형을 수집하는 수동 지도 원천입니다. 기본 자동수집과 `--samples`에서 제외합니다. 지구 대표 위치와 개별 블록 연결 상태를 구분하며 수집·화면 검증은 [MAP_INTERFACE.md](MAP_INTERFACE.md)에 기록합니다. 배경지도는 서버의 고정 VWorld WMTS 요청을 PNG로 검증·캐시하고 브라우저에는 HOME 타일 경로만 제공합니다.

블록 확대 시 실제 3D 주변 건물은 `GET /poc/home/api/map/buildings?block_id=...`에서 기존 `POC10_VWORLD_API_KEY`로 VWorld GIS건물통합정보를 조회합니다. 원문은 `data/raw/vworld_building_context`에 키를 제거한 SHA-256 이름으로 보관하고 결과는 최근 8개 블록까지 메모리에 6시간 캐시합니다. 조회 반경은 최대 1km이며 최대 5,000개 도형까지 페이지 수집합니다. 더 조밀한 곳에서는 750·500·300m로 범위를 줄입니다. 공식 높이를 우선 사용하고, 높이가 없으면 공식 층수×3m를 추정 높이로, 둘 다 없으면 지도 표현용 7.5m로 세웁니다. 높이 근거별 수량은 화면에 구분해 표시합니다. 건물과 정책 사업·블록의 관계는 미연계이므로 건물 수·높이를 공급 실적으로 집계하지 않습니다. 공급현황은 첫 화면부터 상시 3D 지도를 사용합니다. 상세 기준은 [MAPS_UI_PLAN.md](MAPS_UI_PLAN.md#15-접이식-우측-패널실제-주변-건물-3d-2026-10-04)에 기록합니다.

지도 `자료 연도`로 2018년부터 과거 발표·인허가·보고 상태를 조회합니다. 상단 `수집 조회일`은 해당 날짜까지 확보한 자료의 시점이므로 최초 수집일보다 과거로 바꾸지 않습니다. 과거 보고서도 VWorld 지구 수집 대상에 포함되며 현재 확보 경계를 참고 위치로 표시합니다. 정책/프로그램/지역 물량과 모집/입주/준공 누적 예정량 조회는 [SUPPLY_MAP.md](SUPPLY_MAP.md)를 따릅니다.

프로세스 잠금과 PostgreSQL advisory lock으로 중복 수집을 막습니다. 재시작 시 중단 배치는 `INTERRUPTED`로 기록합니다. 실패 시 마지막 정상 데이터를 조회할 수 있으며 원천별 실패 상태를 표시합니다.

누적 수집 기본값: `POC10_NOTICE_START_DATE` 미설정 시 정책 기원 연도 1월 1일(현재 2018-01-01), `POC10_PERMIT_DISTRICT_LIMIT=0`으로 법정동별 전체 페이지, `POC10_GEOCODE_PER_KIND_REGION=10`입니다. 인허가는 기존 6개 법정동·안전 상한 10,000건, 좌표는 한 배치 최대 40개입니다. 설정을 바꾼 뒤 HOME을 재배포합니다. 청약은 연도·지역별 전체 페이지를 검증하며 과거 원천은 기준일별 별도 레코드로 보존합니다. [소급 수집 결과](HISTORICAL_COLLECTION.md).

## 사업 연도별 목표

관리자 로그인 → 공급 현황 → 사업의 `목표 관리`에서 오늘 기준의 당해연도·향후 10년을 편집합니다. 연도별 계획/인허가/착공/공급/준공/입주 목표, 선택적 목표 호수, 필수 근거·메모, 선택적 HTTPS URL을 저장합니다. 미등록 선택은 해당 관리자 목표를 해제하며 원천 예정은 보존합니다. 과거 기준일은 읽기 전용입니다.

`GET /poc/home/api/roadmap?horizon=10`, `/roadmap/export.csv`, `/projects/{id}/targets`로 조회합니다. 관리자 `POST /api/admin/targets/{id}`는 부모 세션·동일 출처·내부 서명을 확인하고 `revision_no` 충돌 시 409를 반환합니다. 목표는 별도 `goal` revision과 `TARGETS_UPDATED` 감사이력으로 보관합니다. 목표 감사이력을 과거 정책 매핑에 적용하지 않습니다. 목표 저장은 실제 달성·공식 공급총량에 영향을 주지 않습니다.

## 공개·관리 경계

공개 경로는 GET/HEAD 조회만 허용합니다. 관리자 수집·매핑 변경은 부모 MinsLab 세션과 동일 출처 Origin 검증을 거친 뒤 서버가 서명한 짧은 유효기간의 내부 요청으로 전달합니다. 브라우저가 보낸 내부 서명·다른 PoC 쿠키는 HOME으로 전달하지 않습니다. API는 loopback에만 공개합니다.

`.env`, raw 디렉터리, DB와 운영 로그는 정적 경로로 제공하지 않습니다. 인증 API는 고정된 공식 HTTPS endpoint를 호출하며 credential query를 manifest에서 제거하고, 응답에 키가 포함돼도 제거한 bytes를 저장·해시합니다. 인증 요청 redirect는 같은 HTTPS 호스트만 허용합니다. API 표본은 정책 사업과 별도로 조회·다운로드합니다.

## 백업과 복구

```bash
mkdir -p PoC/10-home/backups
sudo docker exec poc10-home-db pg_dump -U home -d home -Fc > PoC/10-home/backups/home.dump
tar -czf PoC/10-home/backups/raw.tar.gz -C PoC/10-home/data raw
chmod 600 PoC/10-home/backups/home.dump PoC/10-home/backups/raw.tar.gz
```

DB와 raw를 함께 백업합니다. `.env`는 접근 제한된 별도 보관소에 보관합니다. 복구는 별도 DB·컨테이너에서 `pg_restore` 후 snapshot hash·revision·감사이력·health를 확인하고 전환합니다. 격리 복구 훈련은 후속 운영 검증 항목입니다.

## 기준일의 의미

화면 기본 기준일은 오늘(KST)이며 최초 수집일 이후를 선택합니다. 자료를 늦게 수집했다고 과거 시점에 알고 있던 정보로 소급 생성하지 않습니다. 과거 조회는 해당 날짜 종료 전 수집된 revision과 매핑을 재현합니다. 원천 기준일과 수집일을 구분하며 수집 원천 메뉴는 현재 운영 상태를 보여줍니다.

정책 흐름·과거 자료의 `자료연도`는 별도 필터로 2018년부터 조회합니다. 오늘 확보한 과거 문서는 현재 저장 지식 안에서 해당 원천 연도로 분류하며 실제 `recorded_at`을 앞당기지 않습니다.

선택 블록 주변 지하철역·초중고교·병원은 `GET /poc/home/api/map/infrastructure?block_id=...`에서 기존 `POC10_VWORLD_API_KEY`로 VWorld 장소 검색 API 2.0을 조회합니다. 반경 3.5km, 블록 라벨점 기준 직선거리이며 24시간 메모리 캐시합니다. 원천 응답은 키를 제거한 SHA-256 이름으로 `data/raw/vworld_infrastructure`에 보관합니다. 지도는 시설 분류와 좌표가 확인된 항목만 표시하며, 학교는 가까운 25곳, 병원 12곳, 지하철역 10곳까지 표시합니다. 시설이 안 보이면 먼저 이 API의 `status`, `counts`, `items`와 VWorld 키 상태를 확인하세요.
