/* 실제 화면 소비 경로를 기준으로 작성. ✓는 현재 사용, △는 일부/가공본,
   필요는 현재 연결되지 않은 자료다. API 구현 여부가 곧 화면 사용은 아니다. */
export type Usage = { board: string; map: string; gap: string; evidence: string[] };
export const SCREEN_USAGE: Record<string, Usage> = {
  'hub-hs': { board: '필요 · 미연결', map: '✓ 인허가 사업', gap: '전국 정기 수집·시행자·분양 정보·위치 미확인 사업 보완', evidence: ['assets/js/region.js', 'handlers/v1/permits.js'] },
  ledger: { board: '필요 · 미연결', map: '✓ 사업 번호·위치 연결', gap: '일부 시군구만 등록 · 전국 사업 원장·집계 미구현', evidence: ['handlers/v1/resolve.js', 'handlers/v1/permits.js'] },
  schedule: { board: '필요 · 미연결', map: '필요 · 미연결', gap: '당초·변경 예정일과 월별 이력 없음 · 지연 판단 불가', evidence: ['registry/projects.json', 'lib/board/pipeline.ts'] },
  'hub-ap': { board: '—', map: '△ 계양 시설 허가 번들', gap: '시설 허가 일부만 보관 · 전국 수집과 공공사업 선별 미구현', evidence: ['regions/incheon-gyeyang/infra.json', 'assets/js/app.js'] },
  'agency-input': { board: '필요 · 미연결', map: '필요 · 미연결', gap: '기관 입력 경로·계획 호수·당초 일정·지연 사유 없음', evidence: ['lib/board/pipeline.ts'] },
  molit: { board: '✓ 월별 실적', map: '—', gap: '최신 월 갱신·정기 수집 자동화 · 계획 대비 실적의 계획값 없음', evidence: ['components/board/RealPanels.tsx', 'tools/boarddata/molit.py'] },
  'lh-completion': { board: '✓ 향후 준공 예정', map: '△ 계양 단지 원천', gap: '2026-01-27 보관본 갱신 필요 · 준공예정일과 입주일 구분', evidence: ['app/(dashboard)/page.tsx', 'regions/incheon-gyeyang/region.json'] },
  stan: { board: '—', map: '✓ 지역·주소 검색', gap: '전국 행정코드 보관본과 개편 이력 없음', evidence: ['assets/js/goto.js', 'handlers/v1/resolve.js'] },
  bounds: { board: '필요 · 미연결', map: '— · 상세 경계는 별도 API', gap: '전국 시도·시군구 지도용 경계 단순화본 없음', evidence: ['lib/board/pipeline.ts'] },
  newschool: { board: '—', map: '✓ 신설예정 학교', gap: '기존 학교 배정·통학구역과 신설 일정의 연결 보완', evidence: ['assets/js/region.js', 'handlers/v1/infra.js'] },
  'school-zone': { board: '—', map: '△ 계양 통학구역', gap: '계양 외 통학구역·학교 배정 자료 없음', evidence: ['regions/incheon-gyeyang/infra.json', 'assets/js/app.js'] },
  notices: { board: '—', map: '✓ 모집 공고', gap: '공고↔사업 연결표·일별 모집 이력 없음', evidence: ['assets/js/region.js', 'handlers/v1/notices.js'] },
  buildings: { board: '—', map: '✓ 건물 윤곽·3D', gap: '건물 높이·층수 일부 미확인 · 응답 누적량 미집계', evidence: ['assets/js/app.js', 'handlers/v1/buildings.js'] },
  geom: { board: '—', map: '✓ 경계·필지', gap: '필지 미연결·합필·분할 사업의 위치 보완', evidence: ['assets/js/region.js', 'handlers/v1/resolve.js'] },
  stops: { board: '—', map: '✓ 버스 정류소', gap: '지역별 원천 누락 · 대체 OSM 자료의 완전성 미확인', evidence: ['assets/js/region.js', 'handlers/v1/infra.js'] },
  bus: { board: '—', map: '△ 지원 지역 차량 위치', gap: '지원 노선 제한 · 자동 갱신·위치 이력 없음', evidence: ['assets/js/app.js', 'handlers/bus.js'] },
  tiles: { board: '—', map: '✓ 배경·지형', gap: '타일 요청량·응답 누락 집계 없음', evidence: ['assets/js/app.js'] },
};

export function sourceUsage(id: string, usedBy: string[]): { board: string; map: string } {
  return {
    board: usedBy.includes('/') ? '✓ 사용' : '—',
    map: usedBy.includes('/map') ? '✓ 사용' : id === 'datagokr-15141761' ? '△ 계양 가공본' : id === 'hub-hs-basis' ? '△ 동일 원천 API' : '—',
  };
}

export function sourceGap(s: { id: string; sourceAsOf: string | null; collectedAt: string | null; usedBy: string[] }): string {
  const gaps: string[] = [];
  if (s.id === 'molit-permit-annual') gaps.push('계획 호수 열 비어 있음 · 검산용');
  else if (!s.usedBy.length) gaps.push('화면 미연결 · 사업 번호·활용 범위 검토');
  if (!s.sourceAsOf) gaps.push('원천 기준일 미확인');
  if (!s.collectedAt) gaps.push('수집일 기록 없음');
  if (s.id === 'datagokr-15141761') gaps.push('준공예정 보관본 갱신 필요');
  if (s.id.startsWith('molit-') && s.id !== 'molit-permit-annual') gaps.push('최신 월 갱신·자동 수집');
  if (s.id.startsWith('bundle-')) gaps.push('수동 보완 · 일정 변경 이력 없음');
  if (s.id === 'hub-hs-basis') gaps.push('전국 정기 수집·일정 이력 없음');
  return gaps.length ? gaps.join(' · ') : '정기 갱신·사업 연결 검토';
}
