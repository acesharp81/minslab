/* 사이드바 메뉴와 파생 상세 화면의 경로 표(docs/product/상황판-셸-설계.md 1절).
   사이드바에는 1차 목적지만 두고, 상세(월·시도·시군구·사업·단계·기관)는 위젯·표에서 내려가며 부모 메뉴가 강조된다. */

export type MenuId = 'home' | 'map' | 'projects' | 'area' | 'stage' | 'agency' | 'sources' | 'reports' | 'my-area';
export type MenuItem = { id: MenuId; href: string; label: string; soon?: boolean };

export const MENU: MenuItem[] = [
  { id: 'home', href: '/', label: '종합상황판' },
  { id: 'map', href: '/map', label: '지도' },
  { id: 'projects', href: '/projects', label: '사업' },
  { id: 'area', href: '/area', label: '지역별' },
  { id: 'stage', href: '/stage', label: '단계별' },
  { id: 'agency', href: '/agency', label: '기관별' },
  { id: 'sources', href: '/sources', label: '데이터 원본' },
  { id: 'reports', href: '/reports', label: '보고자료' },
  { id: 'my-area', href: '/my-area', label: '우리 동네' },
];

/* 첫 경로 마디 → 강조할 사이드바 메뉴. 월 상세는 종합상황판 위젯에서 내려가므로 ①을, 사업 상세는 ③을 강조한다. */
const PARENT: Record<string, MenuId> = {
  '': 'home', month: 'home', map: 'map', projects: 'projects', 'home-projects': 'projects', project: 'projects', 'home-project': 'projects', area: 'area', stage: 'stage',
  agency: 'agency', sources: 'sources', reports: 'reports', 'my-area': 'my-area',
};
export const activeMenuId = (pathname: string): MenuId | null => PARENT[pathname.replace(/^\/poc\/housing-board(?=\/|$)/, '').split('/')[1] ?? ''] ?? null;

/* 목록 화면(/projects ...)이 있는 구역. 준비 중 화면도 여기서 이름과 들어올 내용을 얻는다. */
export const SECTIONS: Record<string, { label: string; note: string; soon?: boolean }> = {
  projects: { label: '9·7 사업후보', note: 'PoC 10 공개 원천의 9·7 연결 검토 후보 152건.' },
  area: { label: '지역별', note: '서울·경기 9·7 관련 후보만 표시.' },
  stage: { label: '단계별', note: '원천 상태를 탐색용 단계에 대응.' },
  agency: { label: '기관별', note: 'LH·GH·SH 원천별 후보 행.' },
  sources: { label: '데이터 원본', note: '9·7 후보에 사용한 원천 6종과 수집 공백.' },
  reports: { label: '보고자료', note: '9·7 정책 발표 목표와 검토 후보를 분리해 표시.' },
  'my-area': { label: '우리 동네', note: '서울·경기 9·7 후보를 지역별로 탐색.' },
};

/* 파생 상세 `/{section}/{id}`: 이름·식별자 모양·올라갈 목록. 식별자는 새로 만들지 않는다(지역은 AreaRef 코드, 사업은 PRJ-{시군구5}-{일련4}). */
export const DETAILS: Record<string, { label: string; id: RegExp; list: string; idLabel: string }> = {
  area: { label: '지역 상세', id: /^(\d{2}|\d{5})$/, list: '/area', idLabel: '시도 2자리 · 시군구 5자리 코드' },
  project: { label: '사업 상세', id: /^PRJ-\d{5}-\d{4}$/, list: '/projects', idLabel: '사업 id' },
  stage: { label: '단계 상세', id: /^0[1-6]$/, list: '/stage', idLabel: '6단계 코드' },
  agency: { label: '기관 상세', id: /^(lh|gh|sh|local|mnd)$/, list: '/agency', idLabel: '기관' },
  month: { label: '월 상세', id: /^\d{4}-(0[1-9]|1[0-2])$/, list: '/', idLabel: '연-월' },
  'my-area': { label: '우리 동네 시도', id: /^\d{2}$/, list: '/my-area', idLabel: '시도 2자리 코드' },
};
