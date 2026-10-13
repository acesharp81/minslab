'use strict';
/* 데이터 그리드(계획서 17절, 2026-10-10): lib/grid/spec.ts 의 순수 계산과 components/ui/data-grid.tsx·화면 적용을 고정한다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const G = require('../../lib/grid/spec.ts');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

test('정렬값: 숫자는 숫자, 없음(null·na)은 undefined(늘 맨 뒤), 링크·견본 칸은 글자, sort 를 주면 그것', () => {
  assert.equal(G.sortValue(1200), 1200);
  assert.equal(G.sortValue(null), undefined);
  assert.equal(G.sortValue(undefined), undefined);
  assert.equal(G.sortValue(-3.5), -3.5);
  assert.equal(G.sortValue('경기'), '경기');
  assert.equal(G.sortValue({ text: '서울', href: '/area/11' }), '서울');
  assert.equal(G.sortValue({ text: '필지 3', sort: 3 }), 3);
  assert.equal(G.sortValue({ na: '미확인' }), undefined);
  assert.equal(G.sortValue({ text: 'x', sort: null }), undefined);
});

test('비교: 숫자는 크기, 글자는 한글 사전 순(숫자 섞인 글자는 자연 순)', () => {
  assert.ok(G.compare(2, 10) < 0);
  assert.ok(G.compare('가평', '나주') < 0);
  assert.ok(G.compare('A2BL', 'A10BL') < 0, '자연 순');
  assert.equal(G.compare('서울', '서울'), 0);
  const names = ['충남', '강원', '서울', '경기'].sort(G.compare);
  assert.deepEqual(names, ['강원', '경기', '서울', '충남']);
});

test('표시: 정수 쉼표, 증감은 ▲▼·색, 비율 %, 없음은 – 를 흐리게, na 는 그 문구', () => {
  assert.deepEqual(G.display(12345, 'int'), { text: '12,345' });
  assert.deepEqual(G.display(null, 'int'), { text: '–', tone: 'na' });
  assert.deepEqual(G.display(3.25, 'delta'), { text: '▲ 3.3%', tone: 'ok' });
  assert.deepEqual(G.display(-0.04, 'delta'), { text: '▼ 0.0%', tone: 'bad' });
  assert.deepEqual(G.display(0, 'delta'), { text: '▲ 0.0%', tone: 'ok' });
  assert.deepEqual(G.display(null, 'delta'), { text: '–', tone: 'na' });
  assert.deepEqual(G.display(54.321, 'pct'), { text: '54.3%' });
  assert.deepEqual(G.display('2027-03-31', 'text'), { text: '2027-03-31' });
  assert.deepEqual(G.display({ na: '위치 미연결' }, 'text'), { text: '위치 미연결', tone: 'na' });
  assert.deepEqual(G.display({ text: '전년 54.3%', muted: true }, 'text'), { text: '전년 54.3%', tone: 'na' });
  assert.deepEqual(G.display({ text: '서울', href: '/area/11' }, 'text'), { text: '서울' });
  assert.deepEqual(G.display({ text: '1,200', sort: 1200 }, 'int'), { text: '1,200' });
});

test('머리글: 묶음이 없으면 한 줄, 있으면 두 줄(묶이지 않은 열은 두 줄을 차지, 이어진 같은 묶음은 한 칸으로)', () => {
  const flat = [{ key: 'a', label: '시도' }, { key: 'b', label: '인허가' }];
  assert.deepEqual(G.headerRows(flat), [[{ key: 'a', label: '시도', colSpan: 1, rowSpan: 1 }, { key: 'b', label: '인허가', colSpan: 1, rowSpan: 1 }]]);
  const cols = [{ key: 'n', label: '시도' }, { key: 'm1', label: '인허가', group: '9월' }, { key: 'm2', label: '착공', group: '9월' }, { key: 'y1', label: '인허가', group: '누계', groupSwatch: '#f00' }];
  assert.deepEqual(G.headerRows(cols), [
    [{ key: 'n', label: '시도', colSpan: 1, rowSpan: 2 }, { label: '9월', colSpan: 2, rowSpan: 1 }, { label: '누계', colSpan: 1, rowSpan: 1, swatch: '#f00' }],
    [{ key: 'm1', label: '인허가', colSpan: 1, rowSpan: 1 }, { key: 'm2', label: '착공', colSpan: 1, rowSpan: 1 }, { key: 'y1', label: '인허가', colSpan: 1, rowSpan: 1 }],
  ]);
  assert.deepEqual([...G.groupStarts(cols)], ['m1', 'y1'], '묶음이 바뀌는 열에 세로 구분선');
  assert.deepEqual([...G.groupStarts(flat)], []);
});

test('검색: 칸의 표시 글자·숫자(쉼표 없이도)를 공백·대소문자 무시로 찾고, 빈 검색은 그대로', () => {
  const cols = [{ key: 'd', label: '사업지구', kind: 'text' }, { key: 'u', label: '세대수' }];
  const rows = [
    { id: '1', c: { d: '인천 계양 테크노밸리', u: 1200 } },
    { id: '2', c: { d: { text: '남양주 왕숙', href: '/x' }, u: 860 } },
    { id: '3', c: { d: 'Seoul A2BL', u: null } },
  ];
  assert.deepEqual(G.filterRows(rows, '', cols).map((r) => r.id), ['1', '2', '3']);
  assert.deepEqual(G.filterRows(rows, '  ', cols).map((r) => r.id), ['1', '2', '3']);
  assert.deepEqual(G.filterRows(rows, '계양테크노', cols).map((r) => r.id), ['1']);
  assert.deepEqual(G.filterRows(rows, '왕숙', cols).map((r) => r.id), ['2']);
  assert.deepEqual(G.filterRows(rows, '1,200', cols).map((r) => r.id), ['1']);
  assert.deepEqual(G.filterRows(rows, '1200', cols).map((r) => r.id), ['1']);
  assert.deepEqual(G.filterRows(rows, 'a2bl', cols).map((r) => r.id), ['3']);
  assert.deepEqual(G.filterRows(rows, '없는말', cols), []);
});

test('합계 행은 정렬·검색과 상관없이 위(전국)·아래(총계)에 고정된다', () => {
  const rows = [{ id: 'n', pin: 'top', c: {} }, { id: 'a', c: {} }, { id: 'b', c: {} }, { id: 't', pin: 'bottom', c: {} }];
  const s = G.splitPinned(rows);
  assert.deepEqual(s.top.map((r) => r.id), ['n']);
  assert.deepEqual(s.body.map((r) => r.id), ['a', 'b']);
  assert.deepEqual(s.bottom.map((r) => r.id), ['t']);
});

test('긴 표만 검색(30행 초과 — 시도 16행 표는 한눈에 보인다)·가상 스크롤(120행 초과)을 켠다', () => {
  assert.deepEqual(G.wants(16), { search: false, virtual: false });
  assert.deepEqual(G.wants(30), { search: false, virtual: false });
  assert.deepEqual(G.wants(31), { search: true, virtual: false });
  assert.deepEqual(G.wants(120), { search: true, virtual: false });
  assert.deepEqual(G.wants(351), { search: true, virtual: true });
});

test('그리드 부품: TanStack Table v9 정렬(값 없음 맨 뒤)·Virtual(긴 표), th aria-sort, 머리글·첫 열 고정, 합계 고정, 불투명 줄무늬', () => {
  const g = read('components/ui/data-grid.tsx');
  assert.match(g, /^'use client';/);
  assert.match(g, /tableFeatures\(\{\s*rowSortingFeature,\s*sortedRowModel: createSortedRowModel\(\),/);
  assert.match(g, /useTable\(\{ features, columns, data, state: \{ sorting \}, onSortingChange: setSorting, getRowId: \(r\) => r\.id \}\)/);
  assert.match(g, /sortUndefined: 'last'/);
  assert.match(g, /useVirtualizer\(\{\s*count: wantsVirtual \? list\.length : 0,/, '정렬·검색을 거친 행 모델을 가상화한다(원자료가 아니라)');
  assert.match(g, /initialRect: \{ width: 0, height: height \?\? 0 \}/, '서버 HTML 에도 첫 화면 행');
  assert.match(g, /aria-sort=\{can \? \(dir === 'asc' \? 'ascending' : dir === 'desc' \? 'descending' : 'none'\) : undefined\}/);
  assert.match(g, /<button type="button" onClick=\{column!\.getToggleSortingHandler\(\)\}/, '정렬은 키보드로도');
  assert.match(g, /const stickyCell = 'sticky left-0 z-\[1\] bg-inherit group-data-\[scrolled\]\/grid:shadow-/, '옆으로 밀면 붙은 첫 열 오른쪽에 그림자');
  assert.match(g, /onScroll: \(e\) => e\.currentTarget\.toggleAttribute\('data-scrolled', e\.currentTarget\.scrollLeft > 0\)/);
  assert.match(g, /color-mix\(in_srgb,var\(--pn2\)_45%,var\(--card\)\)/, '줄무늬는 불투명 색');
  assert.match(g, /splitPinned\(rows\)/);
  assert.match(g, /c\.kind === 'text' && 'text-left'/, '글자 열은 왼쪽, 숫자 열은 오른쪽 정렬(가독성)');
  assert.match(g, /c\.wrap && 'min-w-\[180px\] whitespace-normal \[word-break:keep-all\]'/, '줄바꿈 열은 한글 낱말 중간에서 끊지 않는다');
  assert.match(g, /h\.key && textCol\.has\(h\.key\) && 'text-left'/, '머리글도 열과 같은 쪽');
  assert.match(g, /aria-live="polite"/);
  assert.doesNotMatch(g, /useLegacyTable|stockFeatures/);
  assert.match(read('components/ui/table.tsx'), /containerProps\?: React\.ComponentProps<"div">/);
  const pkg = JSON.parse(read('package.json'));
  assert.equal(pkg.dependencies['@tanstack/react-table'], '9.2.8', '버전 고정');
  assert.equal(pkg.dependencies['@tanstack/react-virtual'], '3.14.14');
});

/* 데이터 표가 있는 화면(데이터 원본은 마지막 — 다른 세션이 고치는 중). 원시 <Table> 대신 DataGrid 를 쓴다 */
const PAGES = {
  'app/(dashboard)/area/page.tsx': 1, 'app/(dashboard)/area/[id]/page.tsx': 2, 'app/(dashboard)/month/[id]/page.tsx': 3,
  'app/(dashboard)/agency/page.tsx': 2, 'app/(dashboard)/agency/[id]/page.tsx': 4, 'app/(dashboard)/reports/page.tsx': 4,
  'app/(dashboard)/stage/[id]/page.tsx': 1, 'app/(dashboard)/projects/page.tsx': 6,
};
test('행 펼침: detail 이 있는 행은 첫 칸에 펼침 단추(aria-expanded)가 붙고, 행을 누르면 바로 아래에 예시 그리드가 열린다(링크 누름은 제외)', () => {
  const g = read('components/ui/data-grid.tsx'), spec = read('lib/grid/spec.ts');
  assert.match(spec, /export type Detail = \{ cols: Col\[\]; rows: Row\[\]; total: number; source: string \};/);
  assert.match(spec, /detail\?: Detail/);
  assert.match(g, /aria-expanded=\{open\.has\(r\.id\)\}/);
  assert.match(g, /closest\('a, button, input'\)/, '칸 안 링크·단추를 누르면 펼치지 않는다');
  assert.match(g, /const expandable = !wantsVirtual && rows\.some\(\(r\) => r\.detail\)/, '가상 스크롤 표는 펼치지 않는다');
  assert.match(g, /className="w-0 min-w-full[^"]*"/, '예시 표가 바깥 표의 열 너비를 넓히지 않는다');
});

test('데이터 원본 표는 잘리지 않는다: 칸 글자는 낱말 단위로 줄을 바꾸고(행이 높아짐), 날짜·범위 같은 하이픈 낱말은 끊지 않으며, 예시 값은 자르지 않는다', () => {
  const g = read('components/ui/data-grid.tsx'), spec = read('lib/grid/spec.ts'), samples = read('lib/board/samples.ts');
  assert.match(spec, /GRID_DENSE = '[^']*\[&_td\]:whitespace-normal[^']*\[&_td\]:\[word-break:keep-all\]/);
  assert.match(g, /const keepWords = /);
  assert.match(g, /keepWords\(d\.text\)/);
  assert.doesNotMatch(samples, /MAX_TEXT|…`/, '예시 글을 자르지 않는다');
  assert.doesNotMatch(read('app/(dashboard)/sources/page.tsx'), /maxHeight=\{620\}/, '카탈로그는 높이 제한 없이 펼친다');
});
