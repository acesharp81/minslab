# resource — 데이터 원천 소스

기준: `dataset.md`(2026-10-07) + 호출 주소는 저장소 코드 상수. 키 값은 적지 않음.

| 표기 | 뜻 |
|---|---|
| 근거 `코드` | 저장소 코드에 그 주소가 있음 (`lib/` `api/` `tools/regiontools/`) |
| 근거 `문서` | `dataset.md`에만 적혀 있음 |
| 근거 `번호` | 데이터포털 번호로 구성한 상세 페이지 주소(코드·문서에 같은 형식이 있으나 해당 번호의 페이지는 직접 열어 보지 않음) |
| 인증 `포털키` | 공공데이터포털 서비스키 (`DATA_GO_KR_KEY…`, URL 인코딩해 전송) |
| 인증 `V-World` | V-World 인증키 + 등록 도메인(`domain`) |
| 상태 | 사용 · 이전 사용 · 미사용(수집만) · 안 씀 · 못 받음 |
| § | `dataset.md` 절 번호 |

## 1. API — 공공데이터포털 (data.go.kr)

| 자료 | ID | 호출 엔드포인트 | 포털 상세 페이지 | 근거 | 인증 | 쓰임 | 상태 | § |
|---|---|---|---|---|---|---|---|---|
| 마이홈포털 공공주택 모집공고 (HWSPR02) | 15108420 | `https://apis.data.go.kr/1613000/HWSPR02/rsdtRcritNtcList`(임대) · `…/ltRsdtRcritNtcList`(분양) | `https://www.data.go.kr/data/15108420/openapi.do` | 코드 | 포털키 | 광산·나주 번들, `/api/v1/notices` | 사용 | 2.20 |
| 건축HUB 주택인허가 (HsPmsHubService) | 15136560 | `https://apis.data.go.kr/1613000/HsPmsHubService/getHpBasisOulnInfo` · `getHpDongOulnInfo` · `getHpPlatPlcInfo` | `https://www.data.go.kr/data/15136560/openapi.do` | 코드 | 포털키 | 광산·나주 번들, `/api/v1/permits` | 사용 | 2.17 |
| 건축HUB 건축물대장 (BldRgstHubService) | 15134735 | `https://apis.data.go.kr/1613000/BldRgstHubService/getBrRecapTitleInfo` (총괄표제부) | `https://www.data.go.kr/data/15134735/openapi.do` | 코드 | 포털키 | 인허가 위치·합필·준공 보강 | 사용 | 2.17 |
| 〃 표제부 | 15134735 | `https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo` | 〃 | 문서 | 포털키 | 이름 없는 건물 보완 시험 | 시험만(503 타임아웃, 내용 미확인) | 5.12 |
| 건축HUB 건축인허가 (ArchPmsHubService) | 15136267 | `https://apis.data.go.kr/1613000/ArchPmsHubService/getApBasisOulnInfo` | `https://www.data.go.kr/data/15136267/openapi.do` | 코드 | 포털키 | 계양 `infra.json` `permits[]` | 사용 | 2.13 |
| 국토교통부 TAGO 버스정류소정보 (BusSttnInfoInqireService) | 15098534 | `https://apis.data.go.kr/1613000/BusSttnInfoInqireService/getCrdntPrxmtSttnList`(근접정류소) · `…/getSttnThrghRouteList`(경유노선) | `https://www.data.go.kr/data/15098534/openapi.do` | 코드 | 포털키 | 정류소 `stops`, `/api/v1/infra` | 사용 | 2.11 · 2.18 |
| 국토교통부 TAGO 버스노선정보 (BusRouteInfoInqireService) | 15098529 | `https://apis.data.go.kr/1613000/BusRouteInfoInqireService/getRouteAcctoThrghSttnList` | `https://www.data.go.kr/data/15098529/openapi.do` | 번호 | 포털키 | 노선 `path` | 사용 (`getRouteInfoIem`·`getRouteNoList`는 안 씀) | 2.11 |
| 국토교통부 TAGO 버스위치정보 (BusLcInfoInqireService) | 15098533 | `https://apis.data.go.kr/1613000/BusLcInfoInqireService/getRouteAcctoBusLcList` (`getCtyCodeList`: 도시코드) | `https://www.data.go.kr/data/15098533/openapi.do` | 번호 | 포털키 | `/api/bus` 3D 버스 | 사용 | 2.14 |
| 행정안전부 행정표준코드 법정동코드 (StanReginCd) | 미기록 | `https://apis.data.go.kr/1741000/StanReginCd/getStanReginCdList` | — | 코드 | 포털키 | `/api/v1/resolve` · `/api/v1/codes/search` | 사용 | 2.15 · 2.19 |
| 서울특별시 정류소정보조회 | 15000303 | `http://ws.bus.go.kr/api/rest/stationinfo/getStationByPos` (https는 시간 초과) | `https://www.data.go.kr/data/15000303/openapi.do` | 코드 | 포털키 | 서울 정류소 | 사용 (`getBusPosByRtid`·`getRouteByStation`은 호출만 확인) | 2.18 |
| LH 분양임대공고문 조회 (lhLeaseNoticeInfo1) | 15058530 | `https://apis.data.go.kr/B552555/lhLeaseNoticeInfo1/lhLeaseNoticeInfo1` | `https://www.data.go.kr/data/15058530/openapi.do` | 코드·번호 | 포털키 | `/api/v1/notices` | 사용 (2026-10-06~, 10-04에는 403) | 2.20 |
| LH 분양임대공고별 공급정보 (lhLeaseNoticeSplInfo1) | 15056765 | `https://apis.data.go.kr/B552555/lhLeaseNoticeSplInfo1/getLeaseNoticeSplInfo1` | `https://www.data.go.kr/data/15056765/openapi.do` | 코드·번호 | 포털키 | 단지명·금회공급 세대수 | 사용 | 2.20 |
| 인천광역시 버스위치정보 (busLocationService) | 15059206 | `https://apis.data.go.kr/6280000/busLocationService/getBusRouteLocation` | `https://www.data.go.kr/data/15059206/openapi.do` | 문서·번호 | 포털키 | 좌표 없음 | 안 씀 | 6.2 |
| 청약홈 분양정보 · 경쟁률 | 15098547 · 15098905 | — | `https://www.data.go.kr/data/15098547/openapi.do` · `https://www.data.go.kr/data/15098905/openapi.do` | 번호 | 포털키 | 활용신청만 | 호출 안 함 | 6.2 |
| 통계누리 통계리스트 · 행복도시 준공계획 | 미확인 | — | — | — | 포털키 | — | 호출 안 함 | 6.2 |

## 2. API — V-World (국토교통부)

공통: `https://api.vworld.kr/req/data` · `service=data&request=GetFeature&data=<레이어>&format=json&crs=EPSG:4326&geomFilter=BOX(…)` · 인증 `V-World` · 근거 `코드`(`lib/vworld.js` `tools/regiontools/api.py`) · **상자 요청은 10 km² 이내**

| 레이어 / 엔드포인트 | 자료 | 쓰임 | 상태 | § |
|---|---|---|---|---|
| `LT_C_BLDGINFO` | GIS건물통합정보 (건물 윤곽·높이·층수·용도·이름·사용승인일) | 광산·나주 `buildings.json`, `/api/v1/buildings` | 사용 | 2.6 · 2.16 |
| `LT_C_SPBD` | 도로명주소 건물 (현존 건물만) | 신도시 지구 안 철거 의심 `g` 판정 | 사용 | 2.6 |
| `LT_C_LHBLPN` | LH 사업지구 용지 윤곽 | 단지 블록 윤곽, 지구 경계 근사 | 사용 | 2.2 · 7.2 |
| `LP_PA_CBND_BUBUN` | 연속지적도 (`attrFilter=pnu:=:<PNU>`) | 필지 윤곽·중심 | 사용 | 2.15 · 2.17 |
| `LT_C_UPISUQ155` · `154` · `152` | 도시계획시설 (학교 · 전기공급설비 · 교통) | 학교·시설 부지 | 사용 | 2.9 |
| `LT_C_ADSIGG_INFO` · `LT_C_ADEMD_INFO` | 시군구 · 읍면동 경계 | `/api/v1/resolve` 경계, 건물 법정동 채움 | 사용 | 2.15 |
| `https://api.vworld.kr/req/search` (`type=place`) | 장소 이름 → 좌표·지번·도로명 | 주소 이동 입력줄 | 사용 | 2.19 |
| `https://api.vworld.kr/req/address` (`type=PARCEL` · `ROAD`) | 지번·도로명 → PNU·좌표 | 주소 이동 입력줄 | 사용 | 2.19 |
| `https://api.vworld.kr/req/wmts/1.0.0/{KEY}/white/{z}/{y}/{x}.png` | 배경 지도 (WMTS `white`, 최대 확대 18) | 배경 | 사용 | 1 · 6.1 |

## 3. API — 키 없음 · 공개 엔드포인트

| 자료 | 엔드포인트 | 방식 | 근거 | 쓰임 | 상태 | § |
|---|---|---|---|---|---|---|
| 지방교육재정알리미 신설예정학교 (전국 약 220교) | `POST https://eduinfo.go.kr/portal/theme/newSchInfoDetail.do` (Referer `https://eduinfo.go.kr/portal/theme/newSchMapPage.do`, 검색 조건 비움) | 화면 요청을 파악해 직접 POST | 코드 | 신설 학교, `/api/v1/infra` | 사용 | 2.9 · 2.18 |
| OpenStreetMap Overpass | `https://overpass-api.de/api/interpreter` · `https://overpass.kumi.systems/api/interpreter` | `railway=station` · `amenity=school` · `highway=bus_stop` · `public_transport=platform` | 코드 | 역·학교, 서울 정류장 보조 | 사용 (공개 서버 불안정) | 2.8 · 2.18 |
| OpenStreetMap 지구 경계 way 1062316054 | `https://www.openstreetmap.org/way/1062316054` (Overpass로 재수집 가능) | way id 고정 | 문서 | 계양 지구 경계 (저장 사본 `district.json`) | 사용 | 2.1 |
| AWS Terrain Tiles (terrarium) | `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` | 타일, 14단계까지 | 코드 | 3D 지형·음영 | 사용 | 6.6 |
| OpenFreeMap | `https://tiles.openfreemap.org/planet` · `https://tiles.openfreemap.org/styles/positron` · `https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf` | 벡터 타일·스타일·글꼴 | 코드 | 지명·도로명 글자, 키 없을 때 대체 배경 | 사용 | 6.6 |

## 4. 파일 — CSV

| 자료 | ID | URL | 근거 | 받는 방식 | 규모 | 쓰임 | 상태 | § |
|---|---|---|---|---|---|---|---|---|
| 한국교육시설안전원 학교학구도연계정보 | 15159266 | `https://www.data.go.kr/data/15159266/fileData.do` | 코드 | 포털 내려받기 (ego) | 3·9월 갱신, 기준 2026-09-20 | 단지 → 배정 초등학교 | 사용 | 2.10 |
| 한국교육시설안전원 초중등학교위치 | 15159184 | `https://www.data.go.kr/data/15159184/fileData.do` | 코드 | 〃 | 〃 | 학교 좌표 | 사용 | 2.10 |
| 전국 버스정류장 위치정보 | 15067528 | `https://www.data.go.kr/data/15067528/fileData.do` | 번호 | 〃 | 수집일 2025-10-31, 135곳 선별 | 번들 1.2.0까지 정류장 | 이전 사용 (TAGO API로 교체) | 2.11 |
| LH 공공주택 준공예정현황 (2026-01) | 15141761 | `https://www.data.go.kr/data/15141761/fileData.do` | 번호 | 〃 | 351행 | A10 준공 예정일 근거 (값은 상수로 옮김) | 미사용 | 2.3 · 3.2 |
| LH 행복주택 공급계획 (2025-09-22) | 15043330 | `https://www.data.go.kr/data/15043330/fileData.do` | 번호 | 〃 | 323행 | 기획·시장 파악 | 미사용 | 3.2 |
| LH 전국 LH아파트 단지정보 | 15080989 | `https://www.data.go.kr/data/15080989/fileData.do` | 번호 | 〃 | 6,217행 (층수·좌표 없음) | 기획·시장 파악 | 미사용 | 3.2 · 6.4 |
| SH 공급계획·분양·재개발·공사계약 | 15066029 · 15045310 · 15045311 · 15008820 · 15124798 · 3045249 | `https://www.data.go.kr/data/15066029/fileData.do` 외 번호별 | 번호 | 〃 | 4~792행 | 서울 자료, 인천 지도와 무관 | 미사용 | 3.2 |
| 국방부 군 특별공급 주택 공고 | 15061908 (국방부 `OA-9571`) | `https://www.data.go.kr/data/15061908/fileData.do` · `opendata.mnd.go.kr` | 번호·문서 | 〃 (공공저작물 제3유형) | 5,743행 | 기획·시장 파악 | 미사용 | 3.2 · 5.4 |
| 국토교통 통계누리 주택건설실적 5표 (인허가 월별누계 · 착공 월계 · 준공 월계 · 분양 공동주택 · 지역별 인허가 연간) | — | `stat.molit.go.kr` | 문서 | 화면에서 내려받기 (ego, 최대 60개월, 2021-09~2026-08) | 5개 표 | `molit_tidy.py` 정리본 | 미사용 | 3.2 |
| LH 청약플러스 공사현황 (전국 168행 · 인천계양 블록 62행) | — | `https://apply.lh.or.kr/lhapply/land/cwsttList.do` (`POST currPage`, `cnpCd`) | 문서 | 화면 조회 → CSV 저장 (ego) | 기준일 2026-09-21~30 | 계양 공정율·공사기간 | 사용 | 2.4 |

## 5. 파일 — SHP · XLSX · HWPX · PDF

| 자료 | 형식 | URL | 근거 | 받는 방식 | 쓰임 | 상태 | § |
|---|---|---|---|---|---|---|---|
| V-World GIS건물통합정보 인천 전체 (309,863동, 54.7 MB, 기준 2026-09-09) | SHP zip (EPSG:5186, CP949) | `vworld.kr` 건물 자료 `dtmk_ntads_s002.do?dsId=18` | 문서 | 로그인 후 내려받기 (ego) | 계양 `buildings.json` | 사용 | 2.6 |
| 한국교육시설안전원 초등학교통학구역 | SHP zip (CP949 파일명) | `https://www.data.go.kr/data/15159265/fileData.do` | 코드 | 포털 내려받기 (ego) | 통학구역 `zones` | 사용 | 2.10 |
| LH 입주자모집공고문 (A2·A3·A6·A9·A17) | PDF | `https://apply.lh.or.kr/` (첨부 `lhFile.do`, robots 금지) | 문서 | 한 건씩 내려받기 (ego) | 세대수·동수·최고층·입주 예정 → `META` 상수 (수동 판독) | 사용 | 2.3 |
| LH 팸플릿 (이미지 PDF) | PDF | 〃 | 문서 | 〃 | 단지배치도·동호배치도 → 동 윤곽·동별 층수 (수동 판독) | 사용 | 2.5 |
| LH 건설공사현황 | PDF | `lh.or.kr` 사전정보공표 게시판 (게시판 경로 미기록) | 문서 | 첨부 curl | 시공사·공사금액 → `META` 상수 (수동 판독) | 사용 | 2.3 |
| LH 입주계획 | HWPX 2개 | 〃 | 문서 | 〃 | 보관만 | 미사용 | 3.2 |
| LH 공급현황 | XLSX | 〃 | 문서 | 〃 | 보관만 | 미사용 | 3.2 |

## 6. 크롤링 · 화면 조회

| 사이트 | URL | 가져온 것 | 도구 | robots · 약관 | 저장 | 상태 | § |
|---|---|---|---|---|---|---|---|
| LH 청약플러스 | `https://apply.lh.or.kr/` | 공고문·팸플릿 첨부, 공사현황 목록·블록 상세 | ego-browser | 첨부(`lhFile.do`) 금지·공사현황 목록 허용 | PDF·CSV | 사용 | 5.11 · 6.3 |
| GH (경기주택도시공사) | `gh.or.kr` | 공고 목록 57쪽·계획 표 1쪽 | insane-search (`curl_cffi`) | **전체 금지(`Disallow: /`)**, 사용자 지시로 1.5초 간격 | 저장 | 미사용 | 5.5 · 5.11 |
| 청약홈 | `applyhome.co.kr` | 공고 목록·상세 (층수 유무 확인) | insane-search · ego-browser | robots 없음(404), 약관 미확인 | 안 함 | 확인만 | 5.5 |
| 마이홈포털 화면 | `https://www.myhome.go.kr/` | 메인·기능 화면 | curl · 헤드리스 Chrome | 전체 허용 | 안 함 | 비교 자료 | 5.3 · 5.11 |
| 교육재정알리미 · 학교알리미 | `eduinfo.go.kr` · `schoolinfo.go.kr` | 신설예정학교·학구도 화면 구조 → 호출 방식 파악 | ego-browser | — | 안 함 | 확인만 | 5.4 |
| 다른 PoC (minslab HOME) | `minslab.kr/poc/home` | 원천 8개 목록 비교 | insane-search · curl | — | **저장 안 함** | 비교만 | 5.5 |
| 뉴스·보도 | SBS Biz (2026-09-22) · 세계일보 (2026-04-15) · 파이낸셜뉴스 · asiae · mt · dealsite · mtn (URL 미기록) | 보도 대책 5건(`measures`), 나주 사업 확인, A10 | WebFetch · insane-search | — | 요약만 | 사용 (`measures`) | 2.12 · 5.5 |

## 7. 조사만 했거나 받지 못한 원천

| 원천 | URL | 결과 | 사유 | § |
|---|---|---|---|---|
| 택지정보시스템 속성자료 14종 | `openapi.jigu.go.kr` | 받지 않음 | 내려받기 전 팝업이 직업·소속·활용 목적 입력 요구 | 5.12 |
| 법정동 코드 전체 파일 | `code.go.kr` | 받지 못함 | 확인창·횟수 제한 | 5.5 · 5.12 |
| 건축물대장 세움터 파일 | — | 받지 못함 | — | 5.12 |
| GH 재건축 매입임대 | 데이터포털 15112600 | 받지 못함 | — | 5.12 |
| SH 주택관리현황 · 공고 | `sh.or.kr` (도메인 미기록) | 수집 안 함 | 자동 수집 차단 | 5.11 |
| iH | (도메인 미기록) | 확인 못 함 | 한 도메인 접속 실패 | 5.11 |
| V-World 시군구 경계 (파일) | `vworld.kr` | 받지 못함 | — | 5.12 |
| 카카오맵 API 문서 | `developers.kakao.com/docs/ko/kakaomap/common` · `apis.map.kakao.com/web/documentation` | 버스 위치 개발자 API 없음 | 조사 결과 | 6.7 |
| 카카오 '초정밀 버스' 보도자료 | `kakaocorp.com/page/detail/11734` | 앱 기능, API 제공 여부 자료에 없음 | 조사 결과 | 6.7 |
| TAGO 연계 현황 | `tago.go.kr/v5/link/current_data.jsp` | 실시간 144개 도시에 인천 포함 (2025.07) | 조사 결과 | 6.2 |
