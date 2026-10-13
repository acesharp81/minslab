/* 기관(기획서 3.2·분석 문서 2.4). ready = 이 저장소에 화면에 쓸 수 있는 데이터가 있는가. */
export const AGENCIES = [
  { id: 'lh', name: 'LH', ready: true, summary: '통계누리 LH 시행 호수 + 준공 예정 351블록', actor: 'LH' as const },
  { id: 'local', name: '지자체', ready: true, summary: '통계누리 지자체 시행 호수(시도별)', actor: '지자체' as const },
  { id: 'gh', name: 'GH', ready: false, summary: '경기주택도시공사 자료는 아직 원천 카탈로그에 없음', actor: null },
  { id: 'sh', name: 'SH', ready: false, summary: '서울주택도시공사 파일 6종을 받았으나 화면에서 아직 쓰지 않음', actor: null },
  { id: 'mnd', name: '국방부', ready: false, summary: '수작업 입력 대기(받은 파일은 과거 청약 공고 이력)', actor: null },
] as const;
export type AgencyId = (typeof AGENCIES)[number]['id'];
