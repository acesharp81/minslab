/* 수집 기록: sources.json의 건수·날짜와 data/README.md의 원천 갱신 주기.
   원천 갱신 주기는 자동 수집이 실행되는 주기를 뜻하지 않는다. */
export const COLLECTION: Record<string, { name: string; method: string; cycle: string; unit: string }> = {
  'molit-permit-monthly': { name: '주택 인허가 실적 · 월별 누계', method: '통계누리 CSV 내려받기', cycle: '수동 / 원천 월간', unit: '행' },
  'molit-start-monthly': { name: '주택 착공 실적 · 월계', method: '통계누리 CSV 내려받기', cycle: '수동 / 원천 월간', unit: '행' },
  'molit-complete-monthly': { name: '주택 준공 실적 · 월계', method: '통계누리 CSV 내려받기', cycle: '수동 / 원천 월간', unit: '행' },
  'molit-sale-apt': { name: '공동주택 분양 실적', method: '통계누리 CSV 내려받기', cycle: '수동 / 원천 월간', unit: '행' },
  'molit-permit-annual': { name: '지역별 주택 인허가 실적 · 연간', method: '통계누리 CSV 내려받기', cycle: '수동 / 원천 연간', unit: '행' },
  'datagokr-15008820': { name: 'SH 주택분양 정보', method: '공공데이터포털 CSV', cycle: '수동 / 원천 1회성', unit: '행' },
  'datagokr-15043330': { name: 'LH 행복주택 공급계획', method: '공공데이터포털 CSV', cycle: '수동 / 원천 연간', unit: '행' },
  'datagokr-15045310': { name: 'SH 국민임대주택 공급계획', method: '공공데이터포털 CSV', cycle: '수동 / 원천 연간', unit: '행' },
  'datagokr-15045311': { name: 'SH 장기전세주택 공급계획', method: '공공데이터포털 CSV', cycle: '수동 / 원천 연간', unit: '행' },
  'datagokr-15061908': { name: '군 특별공급 주택 공고 이력', method: '공공데이터포털 CSV', cycle: '수동 / 원천 연간', unit: '행' },
  'datagokr-15066029': { name: 'SH 행복주택 공급계획', method: '공공데이터포털 CSV', cycle: '수동 / 원천 연간', unit: '행' },
  'datagokr-15080989': { name: '전국 LH아파트 단지정보', method: '공공데이터포털 CSV', cycle: '수동 / 원천 연간', unit: '행' },
  'datagokr-15124798': { name: 'SH 공공재개발·재건축 현황', method: '공공데이터포털 CSV', cycle: '수동 / 원천 1회성', unit: '행' },
  'datagokr-15141761': { name: 'LH 공공주택 준공예정 현황', method: '공공데이터포털 CSV', cycle: '수동 / 원천 연간', unit: '블록' },
  'datagokr-3045249': { name: 'SH 공사계약 정보', method: '공공데이터포털 CSV', cycle: '수동 / 원천 분기', unit: '행' },
  'hub-hs-basis': { name: '건축HUB 주택인허가 · 기본개요', method: '공공 API · 법정동 조회', cycle: '수동 / 정기 수집 미구현', unit: '원천 기록' },
  'bundle-incheon-gyeyang': { name: '인천 계양구 사업 번들', method: '원천 가공 → 지역 JSON', cycle: '수동 / 자료 보완 시', unit: '연결 단지' },
  'bundle-gwangju-gwangsan': { name: '광주 광산구 사업 번들', method: '원천 가공 → 지역 JSON', cycle: '수동 / 자료 보완 시', unit: '연결 단지' },
  'bundle-jeonnam-naju': { name: '전남 나주시 사업 번들', method: '원천 가공 → 지역 JSON', cycle: '수동 / 자료 보완 시', unit: '연결 단지' },
};

/* 현재 동작은 코드·보관 파일로 확인. ITEMS.cycle은 목표 주기여서 현재 열에 쓰지 않는다. */
export const OPERATIONS: Record<string, { method: string; cycle: string; amount: string }> = {
  'hub-hs': { method: '건축HUB API', cycle: '조회 시 · 캐시 24시간', amount: '보관 연결 기록 58건' },
  ledger: { method: 'API·지역 번들 연결 → JSON', cycle: '수동 발급·검토·배포', amount: '사업 원장' },
  schedule: { method: '월별 예정일 스냅샷', cycle: '미수집', amount: '일정 기록 없음' },
  'hub-ap': { method: '건축HUB API (계획)', cycle: '미수집 · 보류', amount: '미수집' },
  'agency-input': { method: '기관 CSV 입력 (계획)', cycle: '미구현', amount: '입력 기록 없음' },
  molit: { method: '통계누리 CSV → JSON', cycle: '수동 내려받기', amount: '원천 통계표 5개' },
  'lh-completion': { method: '공공데이터포털 CSV → JSON', cycle: '수동 내려받기', amount: '보관 블록 수' },
  stan: { method: '행정표준코드 API', cycle: '조회 시 · 캐시 24시간', amount: '요청별 응답 · 누적량 미집계' },
  bounds: { method: '경계 단순화·가공 (계획)', cycle: '미수집', amount: '미수집' },
  newschool: { method: '지방교육재정알리미 JSON 조회', cycle: '조회 시 · 캐시 24시간', amount: '요청별 응답 · 누적량 미집계' },
  'school-zone': { method: '포털 파일 → 지역 번들', cycle: '수동 보완', amount: '계양 번들 · 레코드 수 미집계' },
  notices: { method: '마이홈·LH API', cycle: '조회 시 · 목록 캐시 1시간', amount: '요청별 응답 · 이력 미보관' },
  buildings: { method: 'V-World API · 지도 칸별', cycle: '조회 시 · 캐시 24시간', amount: '요청별 응답 · 누적량 미집계' },
  geom: { method: 'V-World API · 경계·필지별', cycle: '조회 시 · 캐시 최대 24시간', amount: '요청별 응답 · 누적량 미집계' },
  stops: { method: 'TAGO·서울시·OSM', cycle: '조회 시 · 캐시 24시간', amount: '요청별 응답 · 누적량 미집계' },
  bus: { method: 'TAGO API · 노선별', cycle: '버튼 요청 시 · 캐시 최소 60초', amount: '요청별 차량 응답 · 이력 미보관' },
  tiles: { method: '타일 요청 · 지형 서버 중계', cycle: '지도 조회 시', amount: '요청별 타일 · 누적량 미집계' },
};

export function bytesLabel(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB`;
}
