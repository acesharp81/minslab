'use strict';
/* next.config.ts + vercel.json: 지도를 iframe 에 넣지 못하게 막는 헤더, 함수가 읽는 번들 파일 포함, 실행 시간 상한, 캐시 규칙.
   (이전에는 vercel.json 의 headers·functions 였고, Next.js 전환으로 next.config.ts 와 라우트 파일(app/api/**)로 옮겼다.) */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..', '..');
const config = require('../../next.config.ts').default;   // Node 가 타입 표기를 지우고 읽는다
const vercel = JSON.parse(fs.readFileSync(path.join(ROOT, 'vercel.json'), 'utf8'));
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const headersOf = async (source) => Object.fromEntries(((await config.headers()).find((h) => h.source === source) || { headers: [] }).headers.map((h) => [h.key, h.value]));

/* app/api 라우트 ↔ 핸들러 파일. 라우트 파일이 핸들러를 가져오고 maxDuration 을 정한다. */
const ROUTES = {
  '/api/bus': ['app/api/bus/route.ts', 'handlers/bus.js'],
  '/api/v1/resolve': ['app/api/v1/resolve/route.ts', 'handlers/v1/resolve.js'],
  '/api/v1/codes/search': ['app/api/v1/codes/search/route.ts', 'handlers/v1/codes/search.js'],
  '/api/v1/notices': ['app/api/v1/notices/route.ts', 'handlers/v1/notices.js'],
  '/api/v1/buildings': ['app/api/v1/buildings/route.ts', 'handlers/v1/buildings.js'],
  '/api/v1/permits': ['app/api/v1/permits/route.ts', 'handlers/v1/permits.js'],
  '/api/v1/infra': ['app/api/v1/infra/route.ts', 'handlers/v1/infra.js'],
  '/api/v1/terrain': ['app/api/v1/terrain/route.ts', 'handlers/v1/terrain.js'],
};
const maxDuration = (route) => Number(/export const maxDuration = (\d+);/.exec(read(ROUTES[route][0]))[1]);

test('모든 경로에서 같은 출처의 홈페이지 미리보기만 iframe 으로 허용한다', async () => {
  const h = await headersOf('/:path*');
  assert.equal(h['X-Frame-Options'], 'SAMEORIGIN');
  assert.equal(h['Content-Security-Policy'], "frame-ancestors 'self'");
  assert.equal(h['X-Content-Type-Options'], 'nosniff');
  assert.equal(h['Referrer-Policy'], 'strict-origin-when-cross-origin');
});

test('저장소에 iframe 으로 지도를 넣는 곳이 없다(상황판→지도는 같은 창의 화면 전환)', () => {
  const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.name === 'vendor' || e.name === 'node_modules' ? [] : e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
  const files = ['index.html', ...['assets/js', 'app', 'components'].flatMap((d) => walk(path.join(ROOT, d)).map((f) => path.relative(ROOT, f)))].filter((f) => /\.(html|js|tsx?)$/.test(f));
  for (const f of files) assert.doesNotMatch(read(f), /<iframe/i, f);
});

test('API 는 app/api 라우트가 handlers 의 핸들러를 가져오고, 실행 시간 상한이 있다', () => {
  for (const [route, [routeFile, handlerFile]] of Object.entries(ROUTES)) {
    assert.ok(fs.existsSync(path.join(ROOT, routeFile)), `${routeFile} 가 있어야 한다`);
    assert.ok(fs.existsSync(path.join(ROOT, handlerFile)), `${handlerFile} 가 있어야 한다`);
    assert.ok(read(routeFile).includes(`/${handlerFile}'`), `${routeFile} 가 ${handlerFile} 를 가져와야 한다`);
    assert.match(read(routeFile), /export const dynamic = 'force-dynamic';/, `${route} 는 요청마다 실행한다`);
    const d = maxDuration(route);
    assert.ok(d > 0 && d <= 60, `${route} maxDuration ${d}`);
  }
  for (const r of ['/api/v1/buildings', '/api/v1/permits', '/api/v1/infra']) assert.ok(maxDuration(r) >= 20, `${r} 는 원천 호출이 길어 20초 이상`);
  assert.ok(!fs.existsSync(path.join(ROOT, 'api')), '루트 api/ 는 Next.js 의 /api 라우트와 겹치므로 두지 않는다(핸들러는 handlers/)');
});

test('함수 묶음: resolve 는 색인·지역 region.json·레지스트리를, bus 는 infra.json 을 포함하고, 로컬 캐시와 큰 번들은 뺀다', () => {
  const inc = config.outputFileTracingIncludes, exc = config.outputFileTracingExcludes;
  assert.deepEqual(inc['/api/v1/resolve'], ['./regions/index.json', './regions/*/region.json', './registry/projects.json']);   // 사업 id 해석은 사업 레지스트리를 읽는다
  assert.deepEqual(inc['/api/v1/permits'], ['./registry/projects.json']);                                                        // 인허가 사업에 사업 id 를 붙인다
  assert.deepEqual(inc['/api/bus'], ['./regions/*/infra.json']);
  assert.deepEqual(inc['/api/v1/codes/search'], ['./regions/index.json', './regions/*/region.json']);                            // 검색 후보의 번들 유무(tier)를 resolve 와 같은 표로 정한다
  assert.ok(!('/api/v1/notices' in inc) && !('/api/v1/buildings' in inc) && !('/api/v1/infra' in inc), '공고·건물·기반시설 함수는 번들 파일을 읽지 않는다');
  // 함수 묶음에 로컬 캐시(.cache)와 큰 번들(buildings 등)이 딸려 가지 않게 한다(vercel build 로 확인했던 resolve.func 8.9 MB → 44 KB)
  for (const k of ['/api/*', '/api/v1/*']) { assert.ok(exc[k].includes('./.cache/**'), k); for (const f of ['buildings', 'projects', 'context']) assert.ok(exc[k].includes(`./regions/*/${f}.json`), `${k} ${f}`); }
  // 제외 패턴은 경로 어디에든 일치하므로 흔한 폴더 이름(dist·docs·tests·public·tools·schemas·workspace·node_modules)을 쓰면 node_modules 안 파일까지 빠져 함수가 죽는다
  const generic = /^\.\/(dist|docs|tests|public|tools|schemas|workspace|node_modules|lib|build|src)\//;
  for (const [k, list] of Object.entries(exc)) for (const e of list) assert.ok(!generic.test(e), `${k}: ${e} 는 node_modules 안의 같은 이름 폴더까지 제외한다`);
  assert.ok(exc['/api/v1/*'].includes('./regions/*/infra.json'), 'v1 함수는 infra.json 도 읽지 않는다(bus 만 읽는다)');
  assert.ok(fs.existsSync(path.join(ROOT, 'regions', 'index.json')));
  const index = JSON.parse(read('regions/index.json'));
  for (const r of index.regions) assert.ok(fs.existsSync(path.join(ROOT, 'regions', r.slug, 'region.json')), r.slug);
});

test('vercel.json 은 Next.js·빌드 명령·출력 폴더·함수 지역(icn1)만 정한다: 프로젝트 설정에 남은 옛 파이프라인(node scripts/build.js · public)을 덮어쓴다', () => {
  assert.equal(vercel.framework, 'nextjs');
  assert.equal(vercel.buildCommand, 'npm run build');   // prebuild 가 scripts/build.js 로 public/ 을 채우고 next build 가 이어진다(package.json)
  assert.equal(vercel.outputDirectory, '.next');         // 프로젝트 설정의 Output Directory 가 public 이면 routes-manifest.json 을 못 찾아 배포가 실패한다(2026-10-09 미리보기에서 확인)
  assert.deepEqual(vercel.regions, ['icn1']);            // 미국 지역에서는 V-World 호출이 연결 실패했다
  for (const k of ['functions', 'headers', 'rewrites', 'redirects']) assert.ok(!(k in vercel), `${k} 는 next.config.ts 가 정한다`);
  const pkg = JSON.parse(read('package.json'));
  assert.equal(pkg.scripts.prebuild, 'node scripts/build.js'); assert.equal(pkg.scripts.build, 'next build');
});

test('.vercelignore 에 .cache 가 있어 로컬 캐시·사용량 파일이 배포로 올라가지 않고, 지도 마크업(index.html)·레지스트리·지역 자료는 올라간다', () => {
  const ignore = read('.vercelignore');
  assert.match(ignore, /^\.cache\/?$/m);
  assert.match(read('.gitignore'), /^\.cache\/$/m);
  for (const need of ['index.html', 'registry', 'regions', 'data', 'app', 'components', 'handlers', 'lib', 'proxy.ts', 'next.config.ts', 'package.json', 'package-lock.json']) {
    assert.ok(!ignore.split('\n').some((l) => l.trim().replace(/\/$/, '') === need), `${need} 는 배포(빌드)에 필요하다`);
  }
});

test('지역 자료·외부 라이브러리 캐시 규칙은 그대로다', async () => {
  assert.match((await headersOf('/regions/:path*'))['Cache-Control'], /max-age=300/);
  assert.match((await headersOf('/assets/vendor/:path*'))['Cache-Control'], /immutable/);
});
