/* 추가로 확보해야 할 공공 API·파일(2026-10-10 공공데이터포털·통계누리·KOSIS·SGIS·V-World·건축HUB 확인). 데이터 원본(/sources)의 '추가 확보 필요' 구역.
   checked: 확인 = 포털 상세·명세를 직접 봄, 일부 확인 = 절차·목록만 봄, 추정 = 명세를 열지 못함. 시험: tests/js/pipeline.test.cjs */
export const ACQUIRE_ASOF = '2026-10-10';

/* 채우는 부족: 화면이 지금 못 하는 것 */
export const GAPS: Record<number, { name: string; screen: string }> = {
  1: { name: '전국 사업 원장(인허가·착공 예정일)', screen: '종합상황판·지도' },
  2: { name: '일정 기록(당초·변경)·지구', screen: '종합상황판' },
  3: { name: '시도·시군구 경계', screen: '종합상황판' },
  4: { name: '공고↔사업 연결', screen: '지도' },
  5: { name: '입주 단계(단지·입주일)', screen: '종합상황판·지도' },
  6: { name: '실적 자동 수집', screen: '종합상황판' },
  7: { name: '법정동 코드 전체(전국 순회)', screen: '지도' },
  8: { name: '미분양·입주예정·지구 보강', screen: '종합상황판' },
};

export type AcquireStatus = '신규 신청 필요' | '신청됨·미연결' | '받기 조건 있음' | '파일 미수집';
export type Acquire = {
  id: string; kind: 'API' | '파일'; no: string; name: string; org: string; status: AcquireStatus;
  gaps: number[]; cycle: string; checked: '확인' | '일부 확인' | '추정'; note: string; url: string;
};

export const ACQUIRE: Acquire[] = [
  { id: 'A1', kind: 'API', no: '15058530', name: 'LH 분양임대공고문 조회', org: 'LH', status: '신규 신청 필요', gaps: [4], cycle: '실시간', checked: '확인', note: '공고 ID(PAN_ID)·상세 주소 · 단지·지구 식별자 없음 · 자동승인', url: 'https://www.data.go.kr/data/15058530/openapi.do' },
  { id: 'A2', kind: 'API', no: '15057999', name: 'LH 분양임대공고별 상세정보', org: 'LH', status: '신규 신청 필요', gaps: [4, 5], cycle: '실시간', checked: '확인', note: 'A1 의 PAN_ID 필수 · 단지명·주소·세대수·입주예정월 · 자동승인', url: 'https://www.data.go.kr/data/15057999/openapi.do' },
  { id: 'A3', kind: 'API', no: '15110581', name: '마이홈 공공임대주택 단지정보', org: '국토교통부', status: '신규 신청 필요', gaps: [5], cycle: '실시간', checked: '확인', note: '단지 식별자·PNU·준공일자·세대수 · 운영계정 심의승인', url: 'https://www.data.go.kr/data/15110581/openapi.do' },
  { id: 'A4', kind: 'API', no: '15057332', name: '공동주택 단지 목록(K-apt)', org: '국토교통부', status: '신규 신청 필요', gaps: [5], cycle: '실시간', checked: '확인', note: '법정동별 단지코드 · 자동승인', url: 'https://www.data.go.kr/data/15057332/openapi.do' },
  { id: 'A5', kind: 'API', no: '15058453', name: '공동주택 기본정보(K-apt)', org: '국토교통부', status: '신규 신청 필요', gaps: [5], cycle: '실시간', checked: '확인', note: '사용승인일·세대수·시행사·시공사 · 자동승인', url: 'https://www.data.go.kr/data/15058453/openapi.do' },
  { id: 'A6', kind: 'API', no: '통계누리', name: '통계누리 OPEN API', org: '국토교통부', status: '신규 신청 필요', gaps: [6], cycle: '통계 공표 주기', checked: '일부 확인', note: '회원 → 인증키 → 통계표별 승인 · 1회 최대 5년 · 통계표 ID 미확인', url: 'https://stat.molit.go.kr/portal/openapi/main.do' },
  { id: 'A7', kind: 'API', no: 'KOSIS', name: 'KOSIS 공유서비스 OpenAPI', org: '국가데이터처', status: '신규 신청 필요', gaps: [6, 8], cycle: '월', checked: '확인', note: '인허가 DT_MLTM_1946 · 착공 5386 · 준공 5372 · 분양 5557 · 미분양 2082', url: 'https://kosis.kr/openapi/index/index.jsp' },
  { id: 'A8', kind: 'API', no: 'SGIS', name: 'SGIS 행정구역 경계 API', org: '국가데이터처', status: '신규 신청 필요', gaps: [3], cycle: '기준연도별', checked: '일부 확인', note: '시도·시군구 GeoJSON · 경량화 경계 · accessToken', url: 'https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/addressBoundary.html' },
  { id: 'A9', kind: 'API', no: '15136560', name: '건축HUB 주택인허가 · 전국 수집·행위개요·지역지구', org: '국토교통부', status: '신청됨·미연결', gaps: [1], cycle: '월간', checked: '확인', note: '착공예정일·사용검사예정일 있음 · 법정동 순회 필요', url: 'https://www.data.go.kr/data/15136560/openapi.do' },
  { id: 'A10', kind: 'API', no: '15098547', name: '청약홈 분양정보', org: '한국부동산원', status: '신청됨·미연결', gaps: [4, 5], cycle: '실시간', checked: '추정', note: '항목 명세 미열람', url: 'https://www.data.go.kr/data/15098547/openapi.do' },
  { id: 'A11', kind: 'API', no: '15058609 · 15057171', name: 'V-World 사업지구경계도 · 택지개발지구지도', org: '국토교통부', status: '신청됨·미연결', gaps: [2], cycle: '실시간 / 연간', checked: '추정', note: '보유 V-World 키 적용 추정 · 지구 위치', url: 'https://www.data.go.kr/data/15058609/openapi.do' },
  { id: 'F1', kind: '파일', no: '건축HUB 대용량', name: '주택인허가 대용량 파일 · 기본개요·행위개요·대지위치', org: '국토교통부', status: '받기 조건 있음', gaps: [1], cycle: '월간', checked: '일부 확인', note: '2026-08분 · 이용목적 선택 · 전국 한 번에', url: 'https://www.hub.go.kr/portal/opn/lps/idx-lgcpt-pvsn-srvc-list.do' },
  { id: 'F2', kind: '파일', no: '15149148', name: '국토교통부 택지정보 · 속성 14종·공간 3종', org: '국토교통부(LX)', status: '받기 조건 있음', gaps: [2], cycle: '수시', checked: '확인', note: '지구단계·진행이력·단계별사업 · 택지정보시스템 이용 중지(2026-10-08~)', url: 'https://www.data.go.kr/data/15149148/fileData.do' },
  { id: 'F3', kind: '파일', no: '15146641', name: '공공주택특별법 지구 SHP', org: '국토교통부', status: '받기 조건 있음', gaps: [2, 8], cycle: '수시', checked: '확인', note: 'V-World 로그인 · 시도별 zip · 2024-01-15 갱신', url: 'https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?dsId=30273&svcCde=MK' },
  { id: 'F4', kind: '파일', no: '15129688', name: 'SGIS 행정구역 통계 및 경계(2025)', org: '국가데이터처', status: '파일 미수집', gaps: [3], cycle: '반기', checked: '확인', note: '경계 SHP + CSV · 바로 다운로드', url: 'https://www.data.go.kr/data/15129688/fileData.do' },
  { id: 'F5', kind: '파일', no: '15123287', name: '법정동코드(2026-09-29)', org: '국토교통부', status: '파일 미수집', gaps: [7], cycle: '연간', checked: '확인', note: '53,387행 · 폐지여부', url: 'https://www.data.go.kr/data/15123287/fileData.do' },
  { id: 'F6', kind: '파일', no: '15111714', name: '부동산원 입주예정물량', org: '한국부동산원', status: '파일 미수집', gaps: [8, 5], cycle: '반기', checked: '확인', note: '30세대 이상 단지 · 2026.7~2028.6 · 703행', url: 'https://www.data.go.kr/data/15111714/fileData.do' },
];
