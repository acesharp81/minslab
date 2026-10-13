/* 단계별 데이터 연계도(데이터 원본 /sources 의 '단계별 데이터 연계' 탭): 공급 6단계(종합상황판 리본 ①계획~⑥입주)마다
   지금 가진 자료와 추가로 확보할 자료가 키 사슬(시도 → 시군구 → 법정동 → 필지 → 곁가지 키 → 사업 번호)의 어느 고리까지 닿는지.
   숫자는 화면(page.tsx)이 원천에서 세어 넘기고(StageNumbers), 추가 자료는 조사 목록(ACQUIRE, 인자로 받음)의 id 로 가리켜 API·파일 건수를 센다.
   선: key 키로 바로 연결 · name 이름·주소 글자만(코드 변환·수동 짝짓기 필요) · need 추가로 확보하면 연결 · none 값·키 없음.
   그림은 components/sources/StageLinks.tsx 가 그린다. 시험: tests/js/pipeline.test.cjs */
import type { Acquire } from './acquire';

export type Level = 'sido' | 'sgg' | 'bjd' | 'pnu' | 'side' | 'prj';
export type Edge = 'key' | 'name' | 'need' | 'none';
/* 받는 방식 표지: 실시간 = 화면 조회 때 API 호출(캐시) · API = API 로 받아 보관 · CSV = CSV 파일 · 파일 = PDF·hwpx·SHP 등 · 가공 = 번들·레지스트리 JSON · 내부 = 기관 입력·일정 기록 */
export type Via = '실시간' | 'API' | 'CSV' | '파일' | '가공' | '내부';
export const VIAS: Via[] = ['실시간', 'API', 'CSV', '파일', '가공', '내부'];
export type LinkItem = { name: string; sub: string; level: Level; edge: Edge; label: string; ids?: string[]; internal?: boolean; via?: Via[] };
export type StageLink = {
  id: string; name: string; official: string;
  acquire?: { ext: number; api: number; file: number; internal: number };   // 추가 확보 건수(도식 오른쪽 머리)
  side: { name: string; sub: string; known: boolean; toPnu: { edge: Edge; label: string }; toPrj: { edge: Edge; label: string } };
  pnuToPrj: string;
  current: LinkItem[]; needed: LinkItem[];
  outcomes: { name: string; lines: string[] }[];
  rows: { data: string; keys: string; reach: string; cut: string; fix: string }[];
};
export const LEVELS: Level[] = ['sido', 'sgg', 'bjd', 'pnu', 'side', 'prj'];
export const LEVEL_NAME: Record<Exclude<Level, 'side'>, { name: string; key: string }> = {
  sido: { name: '시도', key: '2자리' }, sgg: { name: '시군구', key: '5자리' }, bjd: { name: '법정동', key: '10자리' },
  pnu: { name: '필지 PNU', key: '19자리' }, prj: { name: '사업 번호', key: 'PRJ-시군구5-일련4' },
};

export type StageNumbers = {
  regions: number; sgg: number; registryTotal: number; registryRefs: number; registry: Record<string, number>; bundle: Record<string, number>;
  molit: { permit: number; start: number; sale: number; complete: number; annual: number }; months: string;
  lhBlocks: number; lhAsOf: string; catalog: Record<string, number>;
  hubBasis: number; permits: number; permitsStarted: number; permitsCompleted: number; plat: number; ledger: number;
  lhNotices: number; myhome: number; myhomePnu: number; stan: number;
};

const f = (n: number) => n.toLocaleString('en-US');
const cache = (n: number, unit = '건') => (n ? `캐시 ${f(n)}${unit}` : '캐시 없음');

/* 추가 확보 칸(외부 API·파일은 ACQUIRE id 로, 내부 축적은 internal) */
const need = (ids: string[], name: string, sub: string, level: Level, label: string): LinkItem => ({ name, sub, level, edge: 'need', label, ids });
const inner = (name: string, sub: string, label: string): LinkItem => ({ name, sub, level: 'prj', edge: 'need', label, internal: true });
const AGENCY = (what: string) => inner('기관 입력', `${what} (내부)`, '사업 번호로 입력');
const SCHEDULE = (what: string) => inner('일정 기록', `${what} 월별 스냅샷 (내부)`, '월별 저장');

/* 지금 가진 자료의 받는 방식(상자 이름별). 추가 자료는 조사 목록의 구분(API)과 파일 형식(FILE_VIA)으로 정한다 */
const CURRENT_VIA: Record<string, Via[]> = {
  'LH 행복주택 공급계획': ['CSV'], "통계누리 인허가 연간 '계획' 행": ['CSV'], 'SH 공급계획 3종': ['CSV'], 'SH 공공재개발·재건축 현황': ['CSV'],
  'SH 행복주택·공공재개발 주소': ['CSV'], 'LH·GH 계획의 지구명': ['파일'], '사업 레지스트리': ['가공'],
  "지역 번들 '계획' 단지": ['가공'], "지역 번들 '건설 단계' 단지": ['가공'], "지역 번들 '분양중' 단지": ['가공'], "지역 번들 '준공 임박' 단지": ['가공'], "지역 번들 '입주 단계' 단지": ['가공'],
  '통계누리 인허가 월별 누계': ['CSV'], '통계누리 인허가 지역별 연간': ['CSV'], '통계누리 착공 월계': ['CSV'], '통계누리 분양 실적': ['CSV'], '통계누리 준공 월계': ['CSV'],
  '행정표준코드 API': ['실시간'], '건축HUB 주택인허가 개요': ['API', '실시간'], '건축물대장 총괄표제부': ['실시간'], '건축HUB 대지위치': ['실시간'],
  '건축HUB 건축인허가(계양 시설)': ['가공'], '건축HUB 착공일': ['실시간'], '건축물대장 사용승인일': ['실시간'], '건축HUB 사용검사일': ['실시간'],
  'LH 청약플러스 공사현황': ['CSV'], 'LH 건설공사현황 PDF': ['파일'], 'SH 공사계약 정보': ['CSV'],
  'SH 주택분양 · 국방부 군 공고': ['CSV'], '마이홈 모집공고 API': ['실시간'], 'LH 분양임대공고 API': ['실시간'],
  'LH 공공주택 준공예정현황': ['CSV'], 'LH 준공예정 위치': ['CSV'], 'LH 전국 LH아파트 단지정보': ['CSV'], 'LH 단지코드 · 입주지정일': ['CSV'], 'LH 주택입주계획 hwpx': ['파일'],
};
const FILE_VIA: Record<string, Via> = { F1: '파일', F2: '파일', F3: '파일', F4: '파일', F5: 'CSV', F6: 'CSV' };
export function viaOf(item: LinkItem, acquire: Pick<Acquire, 'id' | 'kind'>[]): Via[] {
  if (item.internal) return ['내부'];
  if (item.ids) return [...new Set(item.ids.map((id): Via => (acquire.find((a) => a.id === id)!.kind === 'API' ? 'API' : FILE_VIA[id] ?? '파일')))];
  return CURRENT_VIA[item.name] ?? [];
}

/* 추가 확보 건수: 외부(조사 목록 id 기준 API·파일) + 내부 */
export function acquireCount(needed: LinkItem[], acquire: Pick<Acquire, 'id' | 'kind'>[]) {
  const ids = [...new Set(needed.flatMap((n) => n.ids ?? []))];
  const api = ids.filter((id) => acquire.find((a) => a.id === id)!.kind === 'API').length;
  return { ext: ids.length, api, file: ids.length - api, internal: needed.filter((n) => n.internal).length };
}

export function stageLinks(n: StageNumbers, acquire: Pick<Acquire, 'id' | 'kind'>[]): StageLink[] {
  const reg = (code: string) => n.registry[code] ?? 0, bun = (status: string) => n.bundle[status] ?? 0;
  const registryItem = (label: string): LinkItem => ({ name: '사업 레지스트리', sub: `${f(n.registryTotal)}건 · ${label}`, level: 'prj', edge: 'key', label: '사업 번호' });
  const stages: StageLink[] = [];
  const via = (list: LinkItem[]) => list.map((i) => ({ ...i, via: viaOf(i, acquire) }));
  const add = (s: StageLink) => stages.push({ ...s, current: via(s.current), needed: via(s.needed), acquire: acquireCount(s.needed, acquire) });

  add({
    id: 'plan', name: '계획', official: '01 정책 · 02 사업화',
    side: { name: '지구·블록', sub: '지금 코드 없음', known: false, toPnu: { edge: 'need', label: '경계 안 필지' }, toPrj: { edge: 'need', label: 'LH 블록 = 사업' } },
    pnuToPrj: '레지스트리 pnus',
    current: [
      { name: 'LH 행복주택 공급계획', sub: `15043330 · ${f(n.catalog['datagokr-15043330'] ?? 0)}행 · 2022~2025`, level: 'sido', edge: 'key', label: '시도명' },
      { name: "통계누리 인허가 연간 '계획' 행", sub: `666 · ${f(n.molit.annual)}행 · 계획 값 비어 있음`, level: 'sido', edge: 'none', label: '값 없음' },
      { name: 'SH 공급계획 3종', sub: '국민임대 7 · 장기전세 30 · 행복주택 19행', level: 'sgg', edge: 'name', label: '자치구 이름' },
      { name: 'SH 공공재개발·재건축 현황', sub: `15124798 · ${f(n.catalog['datagokr-15124798'] ?? 0)}구역 · 2023-11`, level: 'sgg', edge: 'name', label: '자치구 이름' },
      { name: 'SH 행복주택·공공재개발 주소', sub: "지번 · '○○번지 일대' 글자만", level: 'pnu', edge: 'name', label: '주소검색 필요' },
      { name: "지역 번들 '계획' 단지", sub: `${f(bun('계획'))}단지 · 인허가·V-World 기반`, level: 'pnu', edge: 'key', label: 'PNU' },
      { name: 'LH·GH 계획의 지구명', sub: 'GH 계획 9행 · LH 입주계획 hwpx 2종', level: 'side', edge: 'name', label: '지구명만' },
      registryItem(`계획(01·02) ${f(reg('01') + reg('02'))}건`),
    ],
    needed: [
      need(['F5'], '법정동코드 전체', 'F5 · 15123287 · 53,387행', 'sgg', '이름 → 코드'),
      need(['A9'], '건축HUB 주택인허가 전국 수집', 'A9 · 15136560 · 신청됨·미연결', 'bjd', '법정동별 조회'),
      need(['F1'], '건축HUB 대용량 파일', 'F1 · 기본·행위개요·대지위치', 'pnu', '대지 PNU'),
      need(['F2'], '택지정보 속성 14종', 'F2 · 15149148 · 이용 중지(10-08~)', 'side', '지구코드'),
      need(['F3', 'A11'], '공공주택지구 경계', 'F3 15146641 · A11 15058609·15057171', 'side', '경계'),
      AGENCY('계획 호수 · 당초 일정'), SCHEDULE('예정일'),
    ],
    outcomes: [
      { name: '① 계획 층 · 종합상황판', lines: ['지금 SAMPLE', '택지정보 + 기관 입력'] },
      { name: '계획 대비 실적', lines: ['계획 호수 원천 없음', '기관 입력으로만'] },
      { name: '당초 대비 지연', lines: ['일정 기록 + 택지 진행이력', '+ 건축HUB 착공예정일'] },
      { name: "지도 '계획' 단지", lines: [`지금 ${f(bun('계획'))}단지`, '지구 경계로 전국'] },
    ],
    rows: [
      { data: `LH 행복주택 공급계획 · ${f(n.catalog['datagokr-15043330'] ?? 0)}행`, keys: '시도명 · 지구명', reach: '✓ 시도', cut: '지구명 → 지구코드 · 공급시기 2025년까지', fix: 'F2 택지정보 · F3·A11 지구 경계' },
      { data: `통계누리 인허가 연간 '계획' 행 · ${f(n.molit.annual)}행`, keys: '시도', reach: '✕ 값 없음', cut: '계획 칸 2021~2025 비어 있음', fix: '기관 입력(계획 호수)' },
      { data: 'SH 공급계획 3종 · 56행', keys: '자치구 이름 · 단지명 · 지번(행복주택)', reach: '△ 이름만', cut: '자치구 이름 → 코드 · 지번 → PNU', fix: 'F5 법정동코드 · V-World 주소검색(보유)' },
      { data: `SH 공공재개발·재건축 · ${f(n.catalog['datagokr-15124798'] ?? 0)}구역`, keys: '자치구 · 구역명 · 번지 일대', reach: '△ 이름만', cut: '구역 → 필지 · 2023-11 이후 갱신 없음', fix: 'F5 · 주소검색 · A9 사업승인 대조' },
      { data: 'GH 계획 9행 · LH 입주계획 hwpx 2종', keys: '사업지구명 · 블록', reach: '△ 이름만', cut: '카탈로그 밖 · 지구명 → 지구코드', fix: 'F2 택지정보 · A11 블록 경계' },
      { data: `지역 번들 '계획' ${f(bun('계획'))}단지`, keys: 'PNU · 사업 번호', reach: '✓ 사업 번호', cut: `${n.regions}개 지역만`, fix: 'A9·F1 건축HUB 전국 수집' },
      { data: `사업 레지스트리 · ${f(n.registryTotal)}건`, keys: `사업 번호 · PNU · 관리번호(${f(n.registryRefs)}건)`, reach: '✓ 사업 번호', cut: '계획 단계(01·02) 0건 · 당초 일정 없음', fix: '기관 입력 · 일정 기록 · F2 진행이력' },
      { data: '정책 후보 사업 266건(분석 표본 · 저장소 밖)', keys: '이름 · 계획 호수(222건)', reach: '✕ 키 없음', cut: '허가·공고와 이을 키 없음', fix: 'F2 택지정보 · 기관 입력' },
    ],
  });

  add({
    id: 'permit', name: '인허가', official: '03 인허가',
    side: { name: '관리번호', sub: 'mgmHsrgstPk · 허가 1건', known: true, toPnu: { edge: 'key', label: '대지위치' }, toPrj: { edge: 'key', label: `refs ${f(n.registryRefs)}건` } },
    pnuToPrj: '레지스트리 pnus',
    current: [
      { name: '통계누리 인허가 월별 누계', sub: `1946 · ${f(n.molit.permit)}행 · ${n.months}`, level: 'sido', edge: 'key', label: '시도 코드' },
      { name: '통계누리 인허가 지역별 연간', sub: `666 · ${f(n.molit.annual)}행 · 2021~2025`, level: 'sido', edge: 'key', label: '시도 코드' },
      { name: '행정표준코드 API', sub: `${cache(n.stan)} · 이름 → 코드`, level: 'bjd', edge: 'key', label: '법정동 코드' },
      { name: '건축HUB 주택인허가 개요', sub: `보관 ${f(n.hubBasis)}건 · ${cache(n.permits)}`, level: 'bjd', edge: 'key', label: '법정동별 조회' },
      { name: '건축물대장 총괄표제부', sub: `${cache(n.ledger)} · 위치·사용승인일`, level: 'pnu', edge: 'key', label: 'PNU' },
      { name: '건축HUB 대지위치', sub: `${cache(n.plat)} · 허가별 대지면적`, level: 'side', edge: 'key', label: '관리번호' },
      { name: '건축HUB 건축인허가(계양 시설)', sub: '지역 번들 2건 · 공공사업 선별 전', level: 'side', edge: 'name', label: '시설명' },
      registryItem(`인허가(03) ${f(reg('03'))}건 · refs ${f(n.registryRefs)}건`),
    ],
    needed: [
      need(['A7', 'A6'], '실적 자동 수집', 'A7 KOSIS DT_MLTM_1946 · A6 통계누리', 'sido', '시도 코드'),
      need(['F5'], '법정동코드 전체', 'F5 · 전국 순회 목록 18,865곳', 'bjd', '순회 목록'),
      need(['A9'], '건축HUB 주택인허가 전국 수집', 'A9 · 오퍼레이션별 하루 1만', 'bjd', '법정동별 조회'),
      need(['F1'], '건축HUB 대용량 파일', 'F1 · 2026-08분 · 전국 한 번에', 'side', '관리번호'),
      SCHEDULE('인허가 예정일'),
    ],
    outcomes: [
      { name: '② 인허가 층 · 종합상황판', lines: ['실적 = 통계누리(시도)', `사업 = ${n.sgg}개 시군구`] },
      { name: '전국 17개 시도 판정', lines: ['지금 SAMPLE', '전국 사업 원장 필요'] },
      { name: '지도 인허가 사업', lines: ['법정동 조회 · 캐시 24시간', '전국 조회 가능'] },
      { name: '인허가 지연', lines: ['예정일 이력 없음', '일정 기록 필요'] },
    ],
    rows: [
      { data: `통계누리 인허가 월별 누계 · ${f(n.molit.permit)}행`, keys: '시도 코드 · 부문 · 시행주체', reach: '✓ 시도', cut: '사업 단위 없음 · 수동 내려받기', fix: 'A7 KOSIS · A6 통계누리 API' },
      { data: `건축HUB 주택인허가 기본개요 · 보관 ${f(n.hubBasis)}건`, keys: '법정동 · 관리번호 · 대지 PNU', reach: '✓ 사업 번호', cut: `${n.sgg}개 시군구만 · 정기 수집 없음`, fix: 'A9 전국 수집 · F1 대용량 · F5 순회 목록' },
      { data: `건축물대장 총괄표제부 · ${cache(n.ledger)}`, keys: 'PNU · 사용승인일', reach: '✓ 필지', cut: '블록·합필 위치 매칭 실패', fix: 'F1 대지위치' },
      { data: '건축HUB 건축인허가(계양) · 2건', keys: '관리번호 · 시설명', reach: '△ 이름만', cut: '공공사업 선별 기준 없음 · 계양만', fix: '선별 기준 정한 뒤 전국 수집' },
      { data: `사업 레지스트리 · ${f(n.registryTotal)}건`, keys: '사업 번호 · PNU · 관리번호', reach: '✓ 사업 번호', cut: `인허가(03) ${f(reg('03'))}건 · 예정일 이력 없음`, fix: '일정 기록' },
    ],
  });

  add({
    id: 'start', name: '착공', official: '04 건설(착공)',
    side: { name: '관리번호 · LH 블록', sub: '건축HUB · LH 공사현황', known: true, toPnu: { edge: 'key', label: '대지위치' }, toPrj: { edge: 'key', label: 'refs · 번들 블록' } },
    pnuToPrj: '레지스트리 pnus',
    current: [
      { name: '통계누리 착공 월계', sub: `5386 · ${f(n.molit.start)}행 · ${n.months}`, level: 'sido', edge: 'key', label: '시도 코드' },
      { name: "지역 번들 '건설 단계' 단지", sub: `${f(bun('건설 단계'))}단지 · 공정율`, level: 'pnu', edge: 'key', label: 'PNU' },
      { name: '건축HUB 착공일', sub: `${cache(n.permits)} 중 착공일 ${f(n.permitsStarted)}건`, level: 'side', edge: 'key', label: '관리번호' },
      { name: 'LH 청약플러스 공사현황', sub: '전국 168블록 · 계양 이력 62행', level: 'side', edge: 'name', label: '블록명' },
      { name: 'LH 건설공사현황 PDF', sub: '2026-07 · 계양 22행 추출', level: 'side', edge: 'name', label: '공사명' },
      { name: 'SH 공사계약 정보', sub: `3045249 · ${f(n.catalog['datagokr-3045249'] ?? 0)}행`, level: 'prj', edge: 'none', label: '키 없음' },
      registryItem(`착공(04) ${f(reg('04'))}건`),
    ],
    needed: [
      need(['A7', 'A6'], '착공 실적 자동 수집', 'A7 KOSIS DT_MLTM_5386 · A6', 'sido', '시도 코드'),
      need(['A11'], 'V-World 택지개발지구지도', 'A11 · LT_C_LHBLPN 블록 경계', 'pnu', '블록 경계'),
      need(['A9'], '건축HUB 착공예정일 전국', 'A9 · stcnsSchedDay · 미연결', 'side', '관리번호'),
      need(['F1'], '건축HUB 대용량 파일', 'F1 · 행위개요 착공 예정일', 'side', '관리번호'),
      AGENCY('당초 착공 일정 · 지연 사유'), SCHEDULE('착공 예정일'),
    ],
    outcomes: [
      { name: '③ 착공 층 · 종합상황판', lines: ['실적 = 통계누리(시도)', `사업 = ${f(reg('04'))}건`] },
      { name: '병목 착공 · 지연 호수', lines: ['지금 SAMPLE', '당초 대비 비교 필요'] },
      { name: '지도 공정율', lines: ['계양 LH 공사현황', 'LH 전국 168블록 가공 전'] },
      { name: '착공 지연 판정', lines: ['착공예정일(A9·F1)', '+ 일정 기록'] },
    ],
    rows: [
      { data: `통계누리 착공 월계 · ${f(n.molit.start)}행`, keys: '시도 코드 · 부문 · 시행주체', reach: '✓ 시도', cut: '사업 단위 없음', fix: 'A7 KOSIS · A6 통계누리 API' },
      { data: `건축HUB 착공일 · ${cache(n.permits)}`, keys: '관리번호 · 대지 PNU · 착공일', reach: '✓ 사업 번호', cut: `${n.sgg}개 시군구만 · 착공예정일 미사용`, fix: 'A9 · F1' },
      { data: 'LH 청약플러스 공사현황 · 168블록', keys: '블록명 · 공정율 · 공사기간', reach: '△ 이름만', cut: '블록명 → 사업 수동 짝짓기 · 계양만 가공', fix: 'A11 블록 경계' },
      { data: 'LH 건설공사현황 PDF · 계양 22행', keys: '공사명 · 시공사 · 공정률', reach: '△ 이름만', cut: 'PDF 수동 추출 · 공정률 기준이 청약플러스와 다름', fix: '수동(원천 API 없음)' },
      { data: `SH 공사계약 · ${f(n.catalog['datagokr-3045249'] ?? 0)}행`, keys: '공사명 · 계약일', reach: '✕ 키 없음', cut: '사업 키 없음', fix: '기관 입력' },
      { data: `사업 레지스트리 · 착공(04) ${f(reg('04'))}건`, keys: '사업 번호', reach: '✓ 사업 번호', cut: '당초 착공일 없음', fix: '기관 입력 · 일정 기록' },
    ],
  });

  add({
    id: 'sale', name: '모집', official: '05 공급(분양·임대)',
    side: { name: '공고 ID', sub: 'PAN_ID · pblancId', known: true, toPnu: { edge: 'name', label: '단지 주소' }, toPrj: { edge: 'need', label: '연결표 필요' } },
    pnuToPrj: '레지스트리 pnus',
    current: [
      { name: '통계누리 분양 실적', sub: `5557 · ${f(n.molit.sale)}행 · ${n.months}`, level: 'sido', edge: 'key', label: '시도 코드' },
      { name: 'SH 주택분양 · 국방부 군 공고', sub: `${f(n.catalog['datagokr-15008820'] ?? 0)}행 · ${f(n.catalog['datagokr-15061908'] ?? 0)}행`, level: 'sgg', edge: 'none', label: '키 없음' },
      { name: '마이홈 모집공고 API', sub: `${cache(n.myhome)} · PNU ${f(n.myhomePnu)}건`, level: 'pnu', edge: 'key', label: 'PNU(일부)' },
      { name: "지역 번들 '분양중' 단지", sub: `${f(bun('분양중'))}단지 · LH 공고문 PDF`, level: 'pnu', edge: 'key', label: 'PNU' },
      { name: 'LH 분양임대공고 API', sub: `${cache(n.lhNotices)} · 시도명·PAN_ID`, level: 'side', edge: 'key', label: 'PAN_ID' },
      registryItem(`모집(05) ${f(reg('05'))}건`),
    ],
    needed: [
      need(['A2'], 'LH 공고별 상세정보', 'A2 · 15057999 · 단지명·주소·세대수', 'pnu', '단지 주소'),
      need(['A1'], 'LH 분양임대공고문 조회', 'A1 · 15058530 · PAN_ID·상세 주소', 'side', '공고 ID'),
      need(['A10'], '청약홈 분양정보', 'A10 · 15098547 · 신청됨·미연결', 'side', '공고번호'),
      inner('일정 기록', '모집 일정 일별 스냅샷 (내부)', '일별 저장'),
    ],
    outcomes: [
      { name: '④ 모집 층 · 종합상황판', lines: ['실적 = 통계누리 분양', `사업 = ${f(reg('05'))}건`] },
      { name: '지도 모집 공고', lines: ['조회 시 · 목록 1시간', '사업과 연결 안 됨'] },
      { name: '공고 ↔ 사업 연결표', lines: ['PAN_ID → 사업 번호', 'A1·A2 필요'] },
      { name: '모집 지연', lines: ['모집 예정 이력 없음', '일정 기록 필요'] },
    ],
    rows: [
      { data: `통계누리 분양 실적 · ${f(n.molit.sale)}행`, keys: '시도 · 분양/임대/조합', reach: '✓ 시도', cut: '사업 단위 없음', fix: 'A7 KOSIS(5557)' },
      { data: `LH 분양임대공고 · ${cache(n.lhNotices)}`, keys: '시도명 · PAN_ID', reach: '△ 공고 ID', cut: '단지·지구 식별자 없음', fix: 'A1 공고문 · A2 공고 상세' },
      { data: `마이홈 모집공고 · ${cache(n.myhome)}`, keys: `시군구명 · 단지명 · PNU(${f(n.myhomePnu)}건)`, reach: '△ 필지', cut: '사업 번호 연결 미구현 · 이력 미보관', fix: '일정 기록 · 연결표' },
      { data: `SH 주택분양 ${f(n.catalog['datagokr-15008820'] ?? 0)}행 · 국방부 ${f(n.catalog['datagokr-15061908'] ?? 0)}행`, keys: '단지명 · 공고명', reach: '✕ 키 없음', cut: '사업 키 없음', fix: 'A10 청약홈 분양정보' },
      { data: `지역 번들 '분양중' ${f(bun('분양중'))}단지`, keys: 'PNU · 사업 번호 · 공고문 PDF', reach: '✓ 사업 번호', cut: `${n.regions}개 지역만 · 공고문 수동 추출`, fix: 'A1 · A2' },
    ],
  });

  add({
    id: 'complete', name: '준공', official: '06 입주(준공 = 사용검사)',
    side: { name: '관리번호 · LH 블록', sub: '사용검사 · 준공예정 블록', known: true, toPnu: { edge: 'key', label: '대지위치' }, toPrj: { edge: 'key', label: 'refs · 번들 블록' } },
    pnuToPrj: '레지스트리 pnus',
    current: [
      { name: '통계누리 준공 월계', sub: `5372 · ${f(n.molit.complete)}행 · ${n.months}`, level: 'sido', edge: 'key', label: '시도 코드' },
      { name: 'LH 공공주택 준공예정현황', sub: `15141761 · ${f(n.lhBlocks)}블록 · ${n.lhAsOf}`, level: 'sido', edge: 'key', label: '시도' },
      { name: 'LH 준공예정 위치', sub: '사업지구·블록 · 위치 글자', level: 'pnu', edge: 'name', label: '주소검색 필요' },
      { name: '건축물대장 사용승인일', sub: `${cache(n.ledger)} · useAprDay`, level: 'pnu', edge: 'key', label: 'PNU' },
      { name: "지역 번들 '준공 임박' 단지", sub: `${f(bun('준공 임박'))}단지 · 공정율 90%+`, level: 'pnu', edge: 'key', label: 'PNU' },
      { name: '건축HUB 사용검사일', sub: `${cache(n.permits)} 중 준공일 ${f(n.permitsCompleted)}건`, level: 'side', edge: 'key', label: '관리번호' },
      registryItem(`06 단계 ${f(reg('06'))}건`),
    ],
    needed: [
      need(['A7', 'A6'], '준공 실적 자동 수집', 'A7 KOSIS DT_MLTM_5372 · A6', 'sido', '시도 코드'),
      need(['A9'], '건축HUB 사용검사예정일 전국', 'A9 · useInspt(예정)일 · 미연결', 'side', '관리번호'),
      need(['F1'], '건축HUB 대용량 파일', 'F1 · 기본개요 사용검사(예정)일', 'side', '관리번호'),
      SCHEDULE('준공 예정일'),
    ],
    outcomes: [
      { name: '⑤ 준공 층 · 종합상황판', lines: ['실적 = 통계누리', '예정 = LH만'] },
      { name: '향후 12개월 공급 예정', lines: [`실데이터 · LH ${f(n.lhBlocks)}블록`, `${n.lhAsOf} 기준 · 갱신 필요`] },
      { name: '지도 준공 임박', lines: [`번들 ${f(bun('준공 임박'))}단지`, '공정율 + 입주 예정월'] },
      { name: '준공 지연', lines: ['예정일 이력 없음', 'LH 외 시행자 예정 없음'] },
    ],
    rows: [
      { data: `통계누리 준공 월계 · ${f(n.molit.complete)}행`, keys: '시도 코드 · 부문 · 시행주체', reach: '✓ 시도', cut: '사업 단위 없음', fix: 'A7 KOSIS · A6 통계누리 API' },
      { data: `LH 준공예정 · ${f(n.lhBlocks)}블록`, keys: '시도 · 사업지구 · 블록 · 위치 글자', reach: '✓ 시도', cut: `위치 → PNU 미연결 · LH 외 없음 · ${n.lhAsOf} 기준`, fix: 'A9·F1 사용검사예정일 전국' },
      { data: `건축HUB 사용검사일 · ${cache(n.permits)}`, keys: '관리번호 · PNU · 준공일', reach: '✓ 사업 번호', cut: `${n.sgg}개 시군구만`, fix: 'A9 · F1' },
      { data: `건축물대장 사용승인일 · ${cache(n.ledger)}`, keys: 'PNU · 사용승인일', reach: '✓ 필지', cut: '블록·합필 위치 매칭 실패', fix: 'F1 대지위치' },
      { data: `사업 레지스트리 · 06 단계 ${f(reg('06'))}건`, keys: '사업 번호', reach: '✓ 사업 번호', cut: '준공 예정 변경 이력 없음', fix: '일정 기록' },
    ],
  });

  add({
    id: 'move', name: '입주', official: '06 입주',
    side: { name: '단지코드', sub: 'LH 단지코드만 · K-apt 없음', known: false, toPnu: { edge: 'need', label: '법정동·주소' }, toPrj: { edge: 'need', label: '단지 = 사업' } },
    pnuToPrj: '레지스트리 pnus',
    current: [
      { name: 'LH 전국 LH아파트 단지정보', sub: `15080989 · ${f(n.catalog['datagokr-15080989'] ?? 0)}행 · 주소 글자`, level: 'pnu', edge: 'name', label: '주소검색 필요' },
      { name: "지역 번들 '입주 단계' 단지", sub: `${f(bun('입주 단계'))}단지 · moveIn`, level: 'pnu', edge: 'key', label: 'PNU' },
      { name: 'LH 단지코드 · 입주지정일', sub: '15080989 단지코드 · 입주지정 시작·종료', level: 'side', edge: 'key', label: 'LH 단지코드' },
      { name: 'LH 주택입주계획 hwpx', sub: '2025·2026 · 지구·블록 · 입주 예정월', level: 'side', edge: 'name', label: '지구·블록명' },
      registryItem(`06 단계 ${f(reg('06'))}건`),
    ],
    needed: [
      need(['F6'], '부동산원 입주예정물량', 'F6 · 15111714 · 703행 · 2026.7~2028.6', 'sgg', '시군구·주소'),
      need(['A4'], 'K-apt 공동주택 단지 목록', 'A4 · 15057332 · 법정동별 단지코드', 'bjd', '법정동별 조회'),
      need(['A3'], '마이홈 공공임대 단지정보', 'A3 · 15110581 · hsmpSn·PNU·준공일자', 'pnu', 'PNU'),
      need(['A5'], 'K-apt 공동주택 기본정보', 'A5 · 15058453 · 사용승인일·세대수', 'side', '단지코드'),
      need(['A2', 'A10'], '공고의 입주예정월', 'A2 LH 공고 상세 · A10 청약홈', 'side', '단지명'),
      SCHEDULE('입주 예정일'),
    ],
    outcomes: [
      { name: '⑥ 입주 층 · 종합상황판', lines: ['지금 자료 없음', 'F6 입주예정물량'] },
      { name: '우리 동네 입주 일정', lines: [`번들 ${f(bun('입주 단계'))}단지 moveIn`, '전국은 F6 · A2'] },
      { name: '입주 실적', lines: ['LH 입주지정일(LH만)', 'K-apt 사용승인일'] },
      { name: '입주 지연', lines: ['입주 예정 이력 없음', '일정 기록 필요'] },
    ],
    rows: [
      { data: `LH 전국 LH아파트 단지정보 · ${f(n.catalog['datagokr-15080989'] ?? 0)}행`, keys: 'LH 단지코드 · 주소 글자 · 준공일 · 입주지정일', reach: '△ 이름만', cut: '주소 → PNU 미연결 · 주소 빈 행 있음 · LH만', fix: 'A3 마이홈 단지(PNU) · A4·A5 K-apt' },
      { data: 'LH 주택입주계획 hwpx 2종', keys: '지구·블록 · 입주 예정월', reach: '△ 이름만', cut: '카탈로그 밖 · 수동', fix: 'F6 입주예정물량 · A2' },
      { data: `지역 번들 '입주 단계' ${f(bun('입주 단계'))}단지`, keys: 'PNU · 사업 번호 · moveIn', reach: '✓ 사업 번호', cut: `${n.regions}개 지역만`, fix: 'F6 · A3' },
      { data: `사업 레지스트리 · 06 단계 ${f(reg('06'))}건`, keys: '사업 번호', reach: '✓ 사업 번호', cut: '실제 입주일 없음', fix: 'A5 K-apt 사용승인일 · 일정 기록' },
    ],
  });
  return stages;
}
