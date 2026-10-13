// 상황판 셸(사이드바 메뉴·파생 상세 경로·지도 섬)이 설계 문서(docs/product/상황판-셸-설계.md)와 어긋나지 않는지 정적으로 확인한다.
// 화면에서의 실제 전환·접힘·드로어는 브라우저로 따로 본다. lib/shell/menu.ts 는 Node 가 타입 표기를 지우고 바로 읽는다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const { MENU, SECTIONS, DETAILS, activeMenuId } = require('../../lib/shell/menu.ts');

test('사이드바 메뉴는 설계 1절의 아홉 목적지이고 경로·식별자가 겹치지 않는다', () => {
  assert.deepEqual(MENU.map((m) => m.href), ['/', '/map', '/projects', '/area', '/stage', '/agency', '/sources', '/reports', '/my-area']);
  assert.equal(new Set(MENU.map((m) => m.id)).size, MENU.length);
  assert.deepEqual(MENU.filter((m) => m.soon).map((m) => m.id), []);   // 보고자료·우리 동네도 화면이 생겨 '준비 중' 표지가 없다(2026-10-10)
});

test('목록 구역은 모두 사이드바 메뉴이고, 지도·종합상황판은 목록 구역이 아니다', () => {
  const ids = new Set(MENU.map((m) => m.id));
  for (const k of Object.keys(SECTIONS)) assert.ok(ids.has(k), `${k} 는 사이드바 메뉴여야 한다`);
  assert.ok(!('map' in SECTIONS) && !('home' in SECTIONS));
});

test('파생 상세는 부모 메뉴를 강조한다: 월은 종합상황판, 사업은 사업, 지도는 지도', () => {
  assert.equal(activeMenuId('/'), 'home');
  assert.equal(activeMenuId('/month/2026-10'), 'home');
  assert.equal(activeMenuId('/project/PRJ-11290-0001'), 'projects');
  assert.equal(activeMenuId('/area/41450'), 'area');
  assert.equal(activeMenuId('/stage/04'), 'stage');
  assert.equal(activeMenuId('/map'), 'map');
  assert.equal(activeMenuId('/poc/housing-board/map'), 'map');
  assert.equal(activeMenuId('/nope'), null);
});

test('상세 식별자는 새로 만들지 않는다: AreaRef 코드·PRJ id·6단계·기관·연월만 열리고 나머지는 거른다', () => {
  const ok = (s, id) => DETAILS[s].id.test(id);
  assert.ok(ok('area', '11') && ok('area', '41450') && !ok('area', '411') && !ok('area', '4145011400'));   // 시도 2·시군구 5자리(법정동은 지도가 연다)
  assert.ok(ok('project', 'PRJ-11290-0001') && !ok('project', 'PRJ-1129-0001') && !ok('project', '1009100003921'));   // 건축HUB 관리번호는 id 가 아니다(기획서 결정 5)
  assert.ok(ok('stage', '01') && ok('stage', '06') && !ok('stage', '00') && !ok('stage', '07'));
  assert.ok(ok('agency', 'lh') && ok('agency', 'mnd') && !ok('agency', 'etc'));
  assert.ok(ok('month', '2026-10') && !ok('month', '2026-13') && !ok('month', '202610'));
  assert.ok(ok('my-area', '41') && ok('my-area', '11') && !ok('my-area', '411') && !ok('my-area', '4145'));   // 우리 동네는 시도 2자리
  for (const d of Object.values(DETAILS)) assert.ok(d.list === '/' || Object.keys(SECTIONS).includes(d.list.slice(1)), `${d.list} 는 올라갈 목록이어야 한다`);
});

test('지도 섬이 원본 3D 로더 순서를 유지하고 HOME 근거를 원본 지도 위에 겹친다', () => {
  const island = read('components/MapIsland.tsx'), html = read('index.html');
  const js = (s) => [...new Set([...s.replaceAll('${BASE}/', '/').matchAll(/['"`]\/?(?:poc\/housing-board\/)?(assets\/[^'"`]+\.js|config\.js)['"`]/g)].map((m) => m[1]))];
  assert.deepEqual(js(island).filter((src) => src !== 'assets/js/home-overlay.js'), js(html).filter((src) => src !== 'assets/js/goto.js'));
  assert.ok(js(island).includes('assets/js/home-overlay.js'));
  assert.match(island, /load\(APP\)/);
  assert.match(island, /w\.REGION\?\.home/);
  assert.match(island, /if \(w\.__mapBooted\) return;/);   // 원본 app.js 는 문서당 한 번만 돌아야 한다
});

test('지도는 루트 레이아웃이 따로이고(들어갈 때·나올 때 새 문서), 지도로 가는 링크는 <Link> 가 아니라 <a> 다', () => {
  assert.match(read('app/(map)/layout.tsx'), /<html lang="ko" data-map-shell="" suppressHydrationWarning>/);   // 지도도 저장된 테마를 첫 화면 전에 복원한다
  assert.match(read('app/(dashboard)/layout.tsx'), /<html lang="ko" suppressHydrationWarning>/);   // 라이트가 기본, 저장된 테마가 다크일 때만 그리기 전에 class=dark
  assert.ok(!fs.existsSync(path.join(ROOT, 'app/layout.tsx')), '최상위 layout.tsx 가 있으면 두 레이아웃이 하나로 합쳐진다');
  const nav = read('components/TopNav.tsx');
  assert.match(nav, /compact \|\| m\.id === 'map'\s*\?\s*<a href=\{withBasePath\(m\.href\)\}/);
  assert.match(read('app/(map)/layout.tsx'), /<TopNav compact \/>/);
  assert.match(read('app/(dashboard)/layout.tsx'), /<TopNav \/>/);
});

test('지도 화면: 지도 앱(.app)이 상단 바 아래 남은 폭·높이를 모두 쓴다 — 마크업이 display:contents 래퍼 안이라 자손 선택자여야 한다', () => {
  assert.match(read('app/(map)/map/page.tsx'), /style=\{\{ display: 'contents' \}\}/, '지도 마크업은 display:contents 래퍼 안에 들어간다');
  const appCss = read('assets/css/app.css');
  assert.match(appCss, /\.shell-map \.app\{flex:1;min-width:0;min-height:0;height:auto\}/);
  assert.doesNotMatch(appCss, /\.shell-map>\.app/, '직계 자식 선택자는 래퍼 때문에 닿지 않는다(2026-10-09: 지도가 화면 폭을 다 쓰지 못함)');
  assert.match(read('app/(map)/layout.tsx'), /<div className="shell-map flex h-screen flex-col overflow-hidden">/);   // 세로 flex: 위 상단 바, 아래 .app
});

test('상단 메뉴 바는 화면 폭(100vw) 기준으로 자리·폭을 정해, 문서 스크롤바가 있는 화면과 없는 화면에서 같은 자리다(1470px 보다 좁아도)', () => {
  const nav = read('components/TopNav.tsx');
  assert.match(nav, /<div className="ml-\[max\(0px,50vw_-_720px\)\] flex h-16 w-\[min\(1440px,100vw\)\] items-center gap-2 px-7 mobile:ml-0 mobile:h-12 mobile:w-auto mobile:px-3">/);
  assert.match(nav, /<header className="sticky top-0 z-40 shrink-0 overflow-x-clip /, '스크롤바 밑으로 들어간 몫은 잘라 가로 스크롤이 생기지 않는다');
  assert.doesNotMatch(nav, /max-w-\[1440px\]/, '남은 폭(스크롤바를 뺀 폭)을 따르면 1470px 보다 좁은 화면에서 메뉴 7px·단추 14px 이 움직였다(2026-10-10)');
  assert.doesNotMatch(nav, /mx-auto flex h-16/, 'mx-auto 는 스크롤바를 뺀 폭 기준이라 종합상황판에서만 스크롤바 폭의 절반만큼 왼쪽으로 간다(2026-10-09: 7px)');
});

test('지도 머리 줄(.mhead)의 바탕·아래 선·지역 글자는 상단 메뉴 바와 같은 Tailwind 토큰을 쓴다', () => {
  const appCss = read('assets/css/app.css');
  assert.match(appCss, /html\[data-map-shell\] \.mhead\{background:var\(--card\);border-bottom-color:var\(--border\)\}/);
  assert.match(appCss, /html\[data-map-shell\] \.hd-region,html\[data-map-shell\] \.regionbox select\{color:var\(--muted-foreground\)\}/);
  assert.doesNotMatch(appCss, /html\[data-map-shell\]:not\(\.dark\) \.mhead\{/, '다크에서도 같은 토큰을 쓰므로 라이트 전용 바탕 규칙은 없다');
});

test('옛 지도 주소(/?region=…)는 쿼리를 그대로 두고 /map 으로 보낸다', () => {
  const proxy = read('proxy.ts');
  assert.match(proxy, /const \{ search \} = request\.nextUrl;/);
  assert.match(proxy, /NextResponse\.redirect\(new URL\('\/poc\/housing-board\/map' \+ search, request\.url\)\)/);
  assert.match(proxy, /matcher: '\/'/);
});
