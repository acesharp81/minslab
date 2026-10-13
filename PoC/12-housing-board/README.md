# PoC 12 · 9·7 주택공급 정책 상황판

원본 [housing-board](https://github.com/bcchung81/housing-board)의 화면 구조와 MapLibre 3D 지도를 PoC 등록 방식에 맞춰 사용합니다. 공개 화면의 숫자와 사업 목록은 PoC 10 HOME의 9·7 정책(`POL_2025_0907`) 관련 자료만 읽습니다. 원본 SAMPLE 차트, 예시 PRJ 사업, 다른 정책의 후보, 정책과 무관한 전국 통계는 화면에서 제외했습니다.

- 단축주소 `/home2` → `/poc/housing-board`
- 사업후보 `/poc/housing-board/projects` (152건)
- 3D 지도 `/poc/housing-board/map` (위치 연결 86건 → 61개 아파트 모형, 위치 미확보 66건 → 개별 가상 미리보기)
- 지역 `/poc/housing-board/area` (서울·경기), 단계 `/stage`, 기관 `/agency`, 근거 `/sources`, 보고 `/reports`

후보 152건 모두 사업→프로그램 연결이 `REVIEW`입니다. 정책 목표 135만 호는 수도권(인천 포함) 2026~2030년 착공 목표이고, 후보 자료는 서울·경기 일부입니다. 후보 호수 합계를 목표 달성률로 계산하지 않습니다. 실제 준공·입주 호수는 사업 원천에서 확보되지 않아 비워 둡니다. 위치점은 LH 블록 라벨명 대조 결과로 공식 사업 경계가 아닙니다. [9·7 결측 현황](docs/POLICY_907_DATA_GAPS.md)을 참고하세요.

## 실행과 갱신

```bash
cd /home/ubuntu/apps/myservice/PoC/12-housing-board
python3 scripts/import-home10.py
python3 scripts/build-home10-3d.py
PATH="$PWD/.runtime/bin:$PATH" npm run build
PATH="$PWD/.runtime/bin:$PATH" npm test
sudo systemctl restart poc12.service
```

독립 런타임은 `127.0.0.1:18120`에서 실행되며 루트 `main.py`가 `/poc/housing-board/*`를 중계합니다. `deploy/poc12.service`가 운영 유닛입니다. 변환기는 PoC 10의 읽기 전용 API를 호출해 **9·7 정책과 연결 후보·원천만 담은** `data/home10/converted.json`과 `data/home10/map.json`을 만듭니다. 원본 식별자·결측값·출처는 보존합니다. 여러 API를 순차 조회하므로 한 시점의 트랜잭션 스냅샷은 아닙니다.

`build-home10-3d.py`는 HOME의 LH 공동주택용지와 원본 V-World 건물 조회 방식을 사용해 `scene.json`을 만듭니다. 운영 서비스의 건물 API와 PoC 10 API가 실행 중이어야 합니다. 기본은 구역별 수집 캐시를 재사용하며 `--refresh`로 다시 조회합니다. 빌드는 후보 스냅샷과 장면의 생성 기준이 다르면 중단합니다. 원본의 단지 경계·아파트 동·층수 높이·그림자·상세 카드를 그대로 사용하고, 부족한 형상만 가상 모형으로 보완합니다. 수집 실적과 가정은 [3D 데이터 연결 기록](docs/HOME10_3D.md)에 정리했습니다.

원본 저장소 설명은 [UPSTREAM_README.md](UPSTREAM_README.md), 원본 데이터 설명은 [dataset.md](dataset.md)에 보관합니다. 이 파일과 원본 코드가 존재해도 공개 화면과 지도에는 예시 사업·SAMPLE 수치를 사용하지 않습니다.
