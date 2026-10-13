/* 데이터 원본 화면의 '수집 흐름': 원천(시작) → 보관·실시간 두 갈래 → 화면(끝)과 계획.
   근거는 2026-10-10 데이터 설계 분석(dataset.md · resource.md · docs/analysis/주택공급상황판_데이터설계_정리본.html · 스펙 5.4·6.4·7절).
   '지금' 문구는 저장소 코드로 확인한 상태이고, 외삽한 값은 estimate(추정)로 표시한다. 한도 사용률은 식으로 두어 화면과 시험(tests/js/pipeline.test.cjs)이 같은 숫자를 쓴다. */

export type Status = 'done' | 'part' | 'plan';
export const STATUS_LABEL: Record<Status, string> = { done: '구현됨', part: '일부', plan: '계획' };

/* 처음 보는 사람을 위한 용어 풀이: 화면 곳곳에 되풀이되는 낱말을 한 번만 풀어 둔다 */
export const GLOSSARY: { term: string; mean: string }[] = [
  { term: '원천', mean: '자료를 내주는 곳. 기관의 공개 API(신청해서 받은 인증키로 프로그램이 자료를 요청하는 창구)·내려받는 파일·공고문·담당자의 직접 입력이 있다.' },
  { term: '보관', mean: '정해 둔 주기로 미리 받아 저장해 두고 화면이 그것을 읽는 방식. 지난 기록과 여러 지역의 합계에 쓴다.' },
  { term: '실시간', mean: '위치 하나를 열 때 원천에 그때그때 요청하는 방식. 결과는 저장하지 않고 최대 24시간만 기억(캐시)해 둔다.' },
  { term: '사업 원장', mean: '주택 사업마다 번호·위치·단계·호수를 한 줄씩 적어 둔, 상황판이 직접 만들어 관리하는 목록. 지금은 사업 레지스트리 파일이 이 역할을 한다.' },
  { term: '신호판', mean: '사업이 정상·주의·지연 중 어디인지 알려 주는 판정. 월별 예정 일정 기록이 쌓여야 계산할 수 있다.' },
  { term: 'LH·SH', mean: '한국토지주택공사(LH)와 서울주택도시공사(SH). 공공주택을 짓고 공급하는 기관.' },
  { term: '지도 번들', mean: '지도 화면에 쓰려고 지역별로 미리 만들어 둔 단지·사업 자료 묶음.' },
  { term: '통계누리', mean: '국토교통부가 달마다 내는 시도별 주택 인허가·착공·준공·분양 실적 통계.' },
  { term: '건축HUB', mean: '국토교통부의 건축행정 공개 자료(인허가·건물대장). 주택 사업만 담은 주택인허가와, 모든 건축물을 담아 훨씬 큰(수백만 건) 건축인허가가 있다.' },
];

/* 시작: 원천을 받는 방식 네 가지 */
export type Origin = { id: string; name: string; how: string; examples: string[]; status: Status };
export const ORIGINS: Origin[] = [
  { id: 'api', name: '공공 API', how: '인증키로 기관 서버에 요청', examples: ['건축HUB 인허가·건물대장', '마이홈·LH 공고', 'V-World 경계·필지·건물', 'TAGO·서울 버스', '행정표준코드'], status: 'done' },
  { id: 'file', name: '파일·화면 조회', how: '파일 내려받기·화면 조회', examples: ['통계누리 5표', 'LH 준공예정', '학구도·학교위치', 'LH 공사현황'], status: 'done' },
  { id: 'doc', name: '공고문·보도', how: '사람이 읽고 옮김', examples: ['LH 모집공고 PDF', '팸플릿 배치도', '보도 대책'], status: 'part' },
  { id: 'input', name: '기관 입력', how: '담당자 입력(지금은 시연용 가상 기관으로 시험)', examples: ['당초·변경 일정', '계획 호수', '지연 사유'], status: 'plan' },
];

/* 가운데: 보관 줄의 여덟 단계와 실시간 줄. now = 저장소에서 확인한 지금, next = 계획 */
export type Step = { id: string; no: string; name: string; does: string; inputs: string; outputs: string; now: string; next: string; status: Status; code: string[] };
export const STEPS: Step[] = [
  { id: 'collect', no: '1', name: '수집', does: '정해 둔 주기(달마다·하루마다)로 원천에서 자료를 한꺼번에 받아 온다.', inputs: '공공 API · 파일 · 공고 · 기관 입력', outputs: '원천 응답 · 파일',
    now: '통계누리·LH 파일, 법정동 단위의 건축HUB 자료, 지역 지도 번들을 사람이 직접 받는다. 전국을 자동으로 도는 일은 아직 없다.', next: '주택 인허가를 전국 단위로 달마다 한 번 받고, 공고는 하루 한 번 기록한다', status: 'part',
    code: ['tools/boarddata', 'scripts/issue-projects.js', 'tools/regiontools'] },
  { id: 'raw', no: '2', name: '원천 기록', does: '받은 자료를 고치지 않고 날짜별로 남겨 둔다. 원천 기관이 재배포를 금지해서 이 원본은 배포하지 않는다.', inputs: '원천 응답 · 파일', outputs: '날짜별 원본 + 카탈로그(받은 시각·원천 기준일)',
    now: '파일 원천은 data/raw 에 있다(배포하지 않음). API 응답은 24시간 기억해 둘 뿐이라 날짜별 기록이 없다.', next: '정해 둔 주기로 받은 응답을 날짜별로 보관', status: 'part',
    code: ['data/raw', 'data/board/sources.json'] },
  { id: 'normalize', no: '3', name: '모양 맞추기', does: '원천마다 다른 자료 모양을 하나의 "사건 기록"(무엇을·어디서·언제(실제/예정)·몇 호·출처·기준일)으로 통일한다(정규화).', inputs: '날짜별 원본', outputs: '사건 레코드',
    now: '인허가는 같은 번지끼리 한 사업으로 묶는다(허가 기록 한 건씩 판정하면 약 46%를 잘못 잡는다). 지도 번들의 단지는 사건 목록을 따로 갖고 있다. 둘의 모양은 아직 다르다.', next: '하나의 공통 사건 기록 형식으로', status: 'part',
    code: ['lib/permits.js', 'tools/regiontools/status.py'] },
  { id: 'link', no: '4', name: '연결', does: '사건을 번호 사슬(시도 → 시군구 → 법정동 → 필지 → 사업)에 붙여 같은 사업의 자료끼리 잇는다. 주소 글자만 있으면 V-World 주소검색으로 필지를 찾고, 못 찾으면 사람이 정한다.', inputs: '사건 레코드', outputs: '사업 id 가 붙은 사건',
    now: '인허가 사업은 필지에, 지도 번들 단지는 윤곽 중심에 있는 필지에 붙였다(22곳 모두 연결). 공고·청약홈 자료는 필지 정보가 없어 아직 못 붙인다.', next: '공고와 사업을 짝짓는 연결표를 만들고, 연결된 비율을 잰다', status: 'part',
    code: ['scripts/issue-projects.js', 'lib/projects.js'] },
  { id: 'ledger', no: '5', name: '사업 원장·일정 기록', does: '사업마다 내부 번호·원천 쪽 번호(외부 참조키)·위치·단계·호수를 적고, 예정일을 달마다 저장해 이력으로 쌓는다.', inputs: '사업 id 가 붙은 사건 · 기관 입력', outputs: '사업 원장 + 월별 일정 이력',
    now: '사업 레지스트리(사업 번호 목록) 77건(5개 시군구). 일정(당초·변경·현재)이 있는 사업은 0건이다.', next: '기존 77건부터 달마다 일정을 기록하고, 이어서 전국 주택 인허가로 사업 번호를 발급', status: 'part',
    code: ['registry/projects.json', 'lib/registry.js'] },
  { id: 'judge', no: '6', name: '판정', does: '사업의 6단계, 당초·변경·현재 일정, 정상·주의·지연 신호, 30일 넘게 갱신이 없는지를 계산한다.', inputs: '사업 원장 + 일정 이력', outputs: '단계 · 신호 · 지연 개월',
    now: '6단계는 77건 모두 있다. 인허가 예정일이 지났는데 기록이 없으면 그 사실만 덧붙인다. 신호(정상·주의·지연)와 지연 개월은 아직 없다.', next: '일정 기록 2회차부터 일정 변경을 알아채고, 기관 입력으로 당초 일정을 받는다', status: 'part',
    code: ['lib/projects.js', 'lib/permits.js'] },
  { id: 'aggregate', no: '7', name: '집계', does: '시도·시군구·기관·월·단계별로 합치고, 통계누리와 같은 칸에서 나눠 커버율(사업 원장이 통계의 몇 %를 담았나)을 낸다.', inputs: '판정된 사업 · 통계누리', outputs: '롤업 · 커버율',
    now: '통계누리를 시도·시행주체·월별로 합친다(시도 합계 = 전국 합계로 검산). 사업 원장을 합친 값과 커버율은 아직 없다.', next: '사업 원장의 시도별 합계 ÷ 통계누리 = 커버율', status: 'part',
    code: ['tools/boarddata/molit.py', 'lib/board/calc.ts'] },
  { id: 'serve', no: '8', name: '화면 자료', does: '계산 결과를 작은 JSON 파일로 만들어 배포하고, 화면이 그 파일을 읽는다.', inputs: '롤업 · 원장', outputs: '화면',
    now: 'data/board 파일 3개(통계누리·LH 준공예정·원천 카탈로그)와 사업 레지스트리를 미리 만들어 둔 파일로 읽는다.', next: '원장·판정·집계 결과도 같은 방식으로', status: 'done',
    code: ['data/board', 'lib/board/data.ts'] },
];
export const LIVE: Step = {
  id: 'live', no: '별도', name: '실시간 API', does: '한 위치를 볼 때만 원천을 호출하고 잠깐(최대 24시간) 기억해 둔다. 결과를 사업 원장에는 쓰지 않는다.', inputs: '화면의 요청(코드·칸·필지)', outputs: '최소 필드 + 출처·받은 시각',
  now: '8개: 지역 코드 해석·주소 검색·공고·건물·인허가·기반시설·버스·지형. 인증키 여러 개를 돌려 쓰고(키 풀), 24시간 기억해 두고, 시간당 호출 수에 상한을 둔다.', next: '공고·인허가는 보관본을 먼저 읽고 실시간은 최신 확인에만', status: 'done',
  code: ['app/api', 'lib/keys.js', 'lib/cache.js'],
};
/* 보관 줄을 그림에서 네 묶음으로 보인다 */
export const PHASES: { name: string; steps: string[] }[] = [
  { name: '수집·기록', steps: ['collect', 'raw'] },
  { name: '모양 맞추기·연결', steps: ['normalize', 'link'] },
  { name: '원장·판정', steps: ['ledger', 'judge'] },
  { name: '집계·화면 자료', steps: ['aggregate', 'serve'] },
];

/* 끝: 화면을 쓰는 사람. 지도(/map)는 문서가 따로라 <a> 로 잇는다 */
export const ENDS: { who: string; asks: string; screens: [string, string][] }[] = [
  { who: '정책 담당자', asks: '계획대로인가 · 어디서 막혔나 · 어느 사업이 늦나', screens: [['종합상황판', '/'], ['지역별', '/area'], ['단계별', '/stage'], ['기관별', '/agency'], ['보고자료', '/reports']] },
  { who: '국민', asks: '내 동네 사업은 몇 단계 · 다음 일정 · 신청 가능한 공고', screens: [['우리 동네', '/my-area'], ['사업', '/projects'], ['지도', '/map']] },
];
export const TRACE = ['화면의 숫자', '사업에 붙은 원천 쪽 관리번호(외부 참조키)', '원천 카탈로그(⑥)', '받아 둔 원문(원천 기록)'];

/* 키 사슬: 원천은 어느 고리에 걸리느냐로 자리가 정해진다(결정 3·5·9 의 식별자를 그대로 쓴다) */
export type LinkId = 'sido' | 'sgg' | 'bjd' | 'pnu' | 'prj' | 'keyless';
export const CHAIN: { id: LinkId; name: string; key: string; sources: string[] }[] = [
  { id: 'sido', name: '시도', key: '2자리', sources: ['통계누리 5표', 'LH 준공예정', 'LH 행복주택 공급계획'] },
  { id: 'sgg', name: '시군구', key: '5자리', sources: ['마이홈·LH 공고', 'SH 공공재개발 현황'] },
  { id: 'bjd', name: '법정동', key: '10자리', sources: ['건축HUB 주택·건축인허가', '행정표준코드'] },
  { id: 'pnu', name: '필지', key: 'PNU 19자리', sources: ['인허가 대지위치', '건물대장 총괄표제부', '연속지적도', '지도 번들 단지'] },
  { id: 'prj', name: '사업', key: 'PRJ-시군구5-일련4', sources: ['사업 레지스트리', '기관 입력(계획)'] },
];
export const KEYLESS = {
  id: 'keyless' as LinkId, name: '번호 없는 자료', sources: ['청약홈 분양정보', 'LH 공고문·단지정보', 'SH 공급계획·분양·공사계약', '국방부 군 특별공급'],
  bridge: '주소 글자만 있는 자료는 V-World 주소검색으로 필지 번호를 찾아 붙이고(지번 주소를 검색하면 그 코드가 곧 PNU), 이름·블록만 있는 자료는 사람이 짝지어 둔 연결표로 붙인다.',
};
export const POINT = { name: '좌표로 쓰는 자료', sources: ['V-World 건물', '신설예정 학교', '버스 정류소', '버스 위치'], note: '번호가 아니라 위치(좌표)로 찾는 자료. 지도에서 한 곳을 볼 때만 쓴다' };

/* 실시간·보관 판정 기준: 보관(B)은 하나라도 맞으면, 실시간(R)은 위치 하나의 상세일 때 */
export type RuleId = 'B1' | 'B2' | 'B3' | 'B4' | 'B5' | 'R1' | 'R2' | 'R3' | 'R4';
export const RULES: Record<RuleId, string> = {
  B1: '화면이 원천에 없는 과거를 요구한다(당초·현재 일정, 추이, 30일 미갱신)',
  B2: '여러 지역을 합친다(시도·전국 집계)',
  B3: '사람이 판단하거나 읽어 옮긴다(사업 id 발급, 블록 위치, PDF, 기관 입력)',
  B4: '원천이 파일·화면 조회뿐이다',
  B5: '요청 때 부르면 한도를 넘는다',
  R1: '위치 하나의 상세이고 한도 안에서 부를 수 있다',
  R2: '이력보다 지금 값이 중요하다',
  R3: '전국을 두기엔 크고 보는 곳은 일부다',
  R4: '이용허락상 최소 필드·짧은 캐시만 둔다',
};

/* 자료별 판정. now = 지금 받는 방식(none = 아직 없음), meter = 한도 대비 호출(80% 를 넘지 않게 운영, 스펙 5.4) */
export type Mode = 'store' | 'mixed' | 'live';
export const MODE_LABEL: Record<Mode, string> = { store: '보관', mixed: '혼합', live: '실시간' };
export type Meter = { label: string; used: number; limit: number };
export type Item = { id: string; name: string; mode: Mode; now: Mode | 'none'; why: RuleId[]; cycle: string; calc: string; meter?: Meter; estimate?: boolean };
export const ITEMS: Item[] = [
  { id: 'hub-hs', name: '건축HUB 주택인허가', mode: 'store', now: 'live', why: ['B1', 'B2', 'B5'], cycle: '달마다 전국을 돌며 받기',
    calc: '조회 단위가 법정동 18,865곳이라 순회 1회에 기본개요 약 2.1만·대지위치 약 2.7만·동별 약 2.1만 호출. 오퍼레이션별 하루 1만이라 키 1개로 약 2.7일. 화면에서 전국 집계를 실시간으로 하면 한 번에 1.8만 호출 이상.',
    meter: { label: '대지위치 전국 순회 ÷ 인증키 1개의 월 한도', used: 27000, limit: 300000 }, estimate: true },
  { id: 'ledger', name: '사업 원장', mode: 'store', now: 'store', why: ['B2', 'B3'], cycle: '전국을 돈 뒤 번호를 매기고 검토해 배포',
    calc: '레코드 약 31만 → 사업 약 1만 건(성북 비율 3.3% 외삽). 1건 약 1 KB면 약 10 MB, 시도별로 나누면 저장소에 둘 수 있다.', estimate: true },
  { id: 'schedule', name: '일정 기록', mode: 'store', now: 'none', why: ['B1'], cycle: '월 1회',
    calc: '예정일 필드만 찍으면 1만 건 × 약 150 B ≈ 월 1.5 MB, 연 18 MB. 레코드를 통째로 찍으면 월 약 130 MB.', estimate: true },
  { id: 'hub-ap', name: '건축HUB 건축인허가', mode: 'store', now: 'none', why: ['B2', 'B5'], cycle: '공공 사업인지 가려낼 방법을 찾은 뒤(보류)',
    calc: '레코드 약 585만, 필요 항목만 약 2.5 GB, 사업 약 74만. 저장소에 못 둔다 — 공공 여부 신호를 얻은 뒤 공공 사업만.',
    meter: { label: '기본개요 전국 순회 ÷ 인증키 1개의 월 한도', used: 69000, limit: 300000 }, estimate: true },
  { id: 'agency-input', name: '기관 입력', mode: 'store', now: 'none', why: ['B1', 'B3'], cycle: '입력할 때',
    calc: '당초 일정·계획 호수·지연 사유는 여기서만 나온다. PoC 는 가상 기관 CSV → 검증기 → 원장.' },
  { id: 'molit', name: '통계누리 5표', mode: 'store', now: 'store', why: ['B2', 'B4'], cycle: '월 1회 내려받기',
    calc: '60개월 시도·시행주체 계열. 화면 자료 60 KB.' },
  { id: 'lh-completion', name: 'LH 준공예정', mode: 'store', now: 'store', why: ['B4'], cycle: '파일이 갱신될 때',
    calc: '351블록 · 151,590호, 화면 자료 64 KB. 지금 파일은 2026-01-27 기준.' },
  { id: 'stan', name: '행정표준코드', mode: 'store', now: 'live', why: ['B2'], cycle: '월 1회 · 행정구역 개편 때',
    calc: '약 2만 행 · 약 3 MB. 전국 롤업의 이름 표가 되어 손으로 적은 시군구 이름 표를 대신한다.', estimate: true },
  { id: 'bounds', name: '시도·시군구 경계 단순화본', mode: 'store', now: 'none', why: ['B2'], cycle: '행정구역 개편 때',
    calc: '시도 17 · 시군구 약 250, 약 1~2 MB. 전국 지도(어디를 먼저 챙길까)에 한꺼번에 필요하다.', estimate: true },
  { id: 'newschool', name: '신설예정 학교', mode: 'store', now: 'live', why: ['B4'], cycle: '해마다 5월 공시',
    calc: '전국 약 220교가 화면 요청 한 번에 온다. 실시간으로 부를 이유가 없다.' },
  { id: 'school-zone', name: '학구도·학교위치·통학구역', mode: 'store', now: 'store', why: ['B4'], cycle: '3월 · 9월',
    calc: '포털 파일뿐. 지금은 계양 번들만.' },
  { id: 'notices', name: '공고(마이홈·LH)', mode: 'mixed', now: 'live', why: ['R2', 'B1', 'B3'], cycle: '목록은 1시간 기억 + 하루 1번 기록',
    calc: '목록은 지금처럼 실시간: 마이홈 종류당 최대 6쪽 → 인스턴스 하나가 하루 최대 144호출. 따로 하루 1회 기록(수십 호출, 1회 약 0.2 MB)으로 모집 이력과 공고↔사업 연결을 쌓는다.',
    meter: { label: '마이홈 공고 목록 ÷ 하루 한도(신청 문서 기준 1,000)', used: 144, limit: 1000 } },
  { id: 'buildings', name: '건물 윤곽', mode: 'live', now: 'live', why: ['R1', 'R3'], cycle: '열 때마다 요청 · 24시간 기억',
    calc: '화면 1회 최대 12칸 × 5쪽 = 60호출, 시간당 1,200쪽 상한. 인천만 309,863동 · 54.7 MB라 전국 보관은 비현실적. 공급 단지의 동 3D(팸플릿 판독)만 번들로 보관.' },
  { id: 'geom', name: '경계·필지 형상', mode: 'live', now: 'live', why: ['R1', 'R4'], cycle: '열 때마다 요청 · 24시간 기억',
    calc: '법정동·필지 하나씩. 원장에는 PNU 문자열만 둔다.' },
  { id: 'stops', name: '버스 정류소', mode: 'live', now: 'live', why: ['R1'], cycle: '열 때마다 요청 · 24시간 기억',
    calc: 'TAGO 시간당 600 상한. 서울은 서울시 API, 실패하면 OpenStreetMap.' },
  { id: 'bus', name: '버스 위치', mode: 'live', now: 'live', why: ['R2'], cycle: '버튼을 누를 때 현재 위치 1번 · 저장 안 함',
    calc: '계양 4노선 × 86,400초 ÷ 60초 = 하루 최대 5,760호출. 한도 10,000의 80%(8,000) 안.',
    meter: { label: '계양 4개 노선 ÷ 하루 한도', used: 4 * Math.floor(86400 / 60), limit: 10000 } },
  { id: 'tiles', name: '지형·배경 타일', mode: 'live', now: 'live', why: ['R3'], cycle: '브라우저가 직접 받음(지형은 서버가 중계)',
    calc: '타일은 보관 대상이 아니다.' },
];
export const GUIDE = 0.8;   // 한도의 80% 까지만 쓴다(스펙 5.4)
export const pct = (m: Meter) => Math.round((m.used / m.limit) * 1000) / 10;

/* 끝에서 본 결과: 정책 담당자 질문(매트릭스 3절)과 국민 화면이 지금 답할 수 있는가 */
export type Can = 'yes' | 'part' | 'no';
export const CAN_LABEL: Record<Can, string> = { yes: '지금 가능', part: '일부', no: '아직 못 함' };
export const QUESTIONS: { q: string; can: Can; has: string; needs: string }[] = [
  { q: 'Q1 지금 계획대로 가고 있는가', can: 'part', has: '실적 — 통계누리의 시도·월별 수치', needs: '계획 호수 — 기관이 입력해야만 알 수 있어서, 그 전에는 실적만 보인다' },
  { q: 'Q2 어디서 막혀 있는가', can: 'no', has: '사업 77건의 6단계', needs: '단계마다 머문 기간 — 일정 기록이 쌓여야 계산된다' },
  { q: 'Q3 어떤 사업이 늦어지고 있는가', can: 'no', has: '인허가 예정일이 지났다는 사실', needs: '당초·현재 일정 — 일정 기록과 기관 입력' },
  { q: 'Q4 어디를 먼저 챙겨야 하는가', can: 'no', has: '시도 번호뿐(지도에 그릴 경계가 없음)', needs: 'Q3의 답 + 시도·시군구 경계 단순화본(전국 지도용으로 줄여 만든 가벼운 경계 파일)' },
  { q: 'Q5 앞으로 실제 공급 물량은', can: 'part', has: '준공(LH 준공예정), 모집(공고 목록)', needs: '착공(사업 원장의 착공예정일), 입주(청약홈 분양정보 — 이용 신청은 했고 아직 호출하지 않음)' },
  { q: '국민 화면: 내 동네 사업·다음 일정·공고', can: 'part', has: '5개 시군구의 사업, 실시간 공고와 지도', needs: '전국 사업 원장 — 지금은 5개 시군구뿐' },
];
export const SIGNAL_NOTE = '지금 신호를 낼 수 있는 범위는 예정일이 적힌 주택 인허가 사업(서울 성북구 기준 152건 중 82건, 54%)과 기관이 직접 입력한 사업뿐이다. 건축 인허가 자료에는 예정일이 아예 없다.';
export const COVER_NOTE = '통계누리는 전국을 빠짐없이 담고, 사업 원장은 아직 일부 사업만 담았다. 같은 시도·같은 달 칸에서 원장 값 ÷ 통계누리 값을 낸 것이 커버율(원장이 통계의 몇 %를 담았나)이고, 신호판에서 원천과 상황판 자료가 얼마나 어긋나는지를 보여 주는 값으로 쓰인다.';

/* 시간으로만 채워지는 것: 일정 기록을 시작한 달부터 센다 */
export const TIMELINE: { ym: string; short: string; what: string }[] = [
  { ym: '2026-10', short: '기록 시작', what: '일정 기록 1회차 — 이 달 이전의 지연은 0으로 보이므로 관측 시작일을 함께 적는다' },
  { ym: '2026-11', short: '일정 변경 확인', what: '2회차 — 일정 변경을 감지하기 시작' },
  { ym: '2027-04', short: '6개월 변화 확인', what: '기록이 6개월 쌓여 6개월 추이를 처음 그린다' },
];

/* 계획: 시간이 걸리는 것부터, 단계마다 확인 기준 */
export const PLAN: { what: string; check: string }[] = [
  { what: '일정 기록 시작 — 기존 77건의 예정일을 달마다 한 번 저장한다', check: '다음 달 두 번째 기록에서 일정 변경을 알아채는지 시험' },
  { what: '전국 주택 인허가 자료(2011년 이후 허가)를 받아 사업마다 번호를 매겨 사업 원장에 올린다', check: '원장의 시도별 합계 ÷ 통계누리 = 커버율을 계산하고, 사업 번호 검사를 통과' },
  { what: '행정표준코드(행정구역 이름·번호표)와 시도·시군구 경계 단순화본(전국 지도용 가벼운 경계 파일)을 보관', check: '직접 적어 둔 시군구 이름 표를 대신하고, 이름이 맞는지 대조 시험을 통과' },
  { what: '공고를 하루 한 번 기록하고, 공고와 사업을 짝짓는 연결표를 만든다', check: '공고 중 사업에 연결된 비율을 잰다' },
  { what: '시연용 가상 기관의 일정 입력(CSV 파일 → 형식 검사 → 사업 원장)', check: '입력한 1건이 신호판과 사업 상세의 근거 보기까지 이어지는지 확인' },
  { what: '청약홈 분양정보 호출 시작', check: '앞으로 공급 물량의 입주 예정 줄이 채워지는지 확인' },
];
export const STORAGE: { name: string; when: string; pros: string; cons: string }[] = [
  { name: '안 A · 저장소 JSON', when: '지금(시범 단계)', pros: '지금 구조와 검사를 그대로 쓰고, 사람의 검토가 커밋으로 남는다. 비용이 없다.', cons: '웹에서 입력할 수 없다(기관 입력은 CSV). 건축인허가 전국은 둘 수 없다.' },
  { name: '안 B · 공유 저장소', when: '웹 입력이 필요하거나 건축인허가를 전국 적재할 때', pros: '웹 기관 입력, 배포 없이 반영, 기록 누적.', cons: '새 외부 서비스, 키·비밀번호 관리, 옮기는 작업이 생긴다. 어느 서비스로 할지는 정할 일이다.' },
];
export const RISKS: string[] = [
  '사업 약 1만 건은 성북 비율을 전국에 늘린 값이라 서울 재개발 쪽으로 치우쳤을 수 있다. 2011년 이후 허가 비율은 재지 않았다.',
  '마이홈 하루 한도가 신청 문서에는 1,000건, lib/keys.js 기본값에는 10,000건이다. 문서가 맞다면 인증키 묶음(키 풀)이 한도를 10배 높게 잡고 있다.',
  '공고 목록 6쪽(600행) 상한이 전국 건수보다 작은지 확인하지 못했다.',
  '운영계정·V-World 한도와 서버가 몇 대 도는지를 몰라, 서버 한 대당 호출 예산은 근사치다.',
  '원장 보관이 건축HUB 약관(복제·제공 제한)에 맞는지 확인하지 못했다. 파생 필드와 관리번호만 둔다는 전제로 계산했다.',
];

/* 원천 카탈로그(data/board/sources.json) 항목이 흐름의 어디에 있는가: 키 사슬의 고리와 판정(ITEMS 의 id) */
export const PLACE: Record<string, { link: LinkId; item: string | null }> = {
  'molit-permit-monthly': { link: 'sido', item: 'molit' },
  'molit-start-monthly': { link: 'sido', item: 'molit' },
  'molit-complete-monthly': { link: 'sido', item: 'molit' },
  'molit-sale-apt': { link: 'sido', item: 'molit' },
  'molit-permit-annual': { link: 'sido', item: 'molit' },
  'datagokr-15141761': { link: 'sido', item: 'lh-completion' },
  'datagokr-15043330': { link: 'sido', item: null },
  'datagokr-15124798': { link: 'sgg', item: null },
  'datagokr-15008820': { link: 'keyless', item: null },
  'datagokr-15045310': { link: 'keyless', item: null },
  'datagokr-15045311': { link: 'keyless', item: null },
  'datagokr-15061908': { link: 'keyless', item: null },
  'datagokr-15066029': { link: 'keyless', item: null },
  'datagokr-15080989': { link: 'keyless', item: null },
  'datagokr-3045249': { link: 'keyless', item: null },
  'hub-hs-basis': { link: 'bjd', item: 'hub-hs' },
  'bundle-incheon-gyeyang': { link: 'pnu', item: 'ledger' },
  'bundle-gwangju-gwangsan': { link: 'pnu', item: 'ledger' },
  'bundle-jeonnam-naju': { link: 'pnu', item: 'ledger' },
};
export const linkName = (id: LinkId) => (id === 'keyless' ? KEYLESS.name : CHAIN.find((c) => c.id === id)?.name ?? id);
