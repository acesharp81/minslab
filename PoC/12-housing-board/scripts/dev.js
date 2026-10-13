#!/usr/bin/env node
/* 로컬 개발 서버: 저장소 루트의 정적 파일 + /api/bus · /api/v1/resolve · /api/v1/codes/search · /api/v1/notices · /api/v1/buildings · /api/v1/permits · /api/v1/infra(api/ 의 함수 그대로).
   node scripts/dev.js [포트=8000]
   버스 위치(/api/bus)는 .env.local 의 공공데이터포털 키(DATA_GO_KR_KEY_BUS_<N> 여러 개 또는 DATA_GO_KR_KEY 하나)가 있어야 동작한다. 없으면 503 이고 지도는 버스 없이 뜬다.
   키 이름·용도·한도는 env.example 과 lib/keys.js 참고. 키 사용량은 .cache/key-usage.json, 응답 캐시는 .cache/ (모두 gitignore).
   127.0.0.1 에만 열고, 점(.)으로 시작하는 파일(.env.local·.git)과 node_modules 는 내주지 않는다. 배포 빌드(scripts/build.js)와 무관하다. */
const http = require('http');
const fs = require('fs');
const path = require('path');
const { createKeyPool } = require('../lib/keys.js');

const ROOT = path.resolve(__dirname, '..');
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.ico': 'image/x-icon', '.pbf': 'application/x-protobuf', '.wasm': 'application/wasm', '.txt': 'text/plain; charset=utf-8' };

function loadEnv(file) {
  const env = {};
  if (!fs.existsSync(file)) return env;
  for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
    const t = line.trim();
    if (!t || t.startsWith('#') || !t.includes('=')) continue;
    const i = t.indexOf('=');
    env[t.slice(0, i).trim()] = t.slice(i + 1).trim().replace(/^["']|["']$/g, '');
  }
  return env;
}

/* 시작할 때 보여 줄 키 현황(라벨·개수만, 값은 절대 안 찍는다) */
function keySummary(env) {
  const pool = createKeyPool({ env });
  const parts = ['BUS', 'RESOLVE'].map((p) => `${p} ${pool.count(p)}개`);
  const vw = env.VWORLD_DEV_KEY ? `V-World 개발키(domain ${env.VWORLD_DOMAIN || 'localhost'})` : env.VWORLD_KEY ? `V-World 운영키(domain ${env.VWORLD_DOMAIN || 'localhost'})` : 'V-World 키 없음';
  return { text: `${parts.join(' · ')}${pool.profile === 'demo' ? ' · 시연 프로파일' : ''} · ${vw}`, bus: pool.hasKeys('BUS') };
}

function createServer(root = ROOT, env = process.env) {
  const bus = require(path.join(root, 'handlers', 'bus.js')).createHandler({ env });
  const resolve = require(path.join(root, 'handlers', 'v1', 'resolve.js')).createHandler({ env });
  const search = require(path.join(root, 'handlers', 'v1', 'codes', 'search.js')).createHandler({ env });
  const notices = require(path.join(root, 'handlers', 'v1', 'notices.js')).createHandler({ env });
  const buildings = require(path.join(root, 'handlers', 'v1', 'buildings.js')).createHandler({ env });
  const permits = require(path.join(root, 'handlers', 'v1', 'permits.js')).createHandler({ env });
  const infra = require(path.join(root, 'handlers', 'v1', 'infra.js')).createHandler({ env });
  return http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    res.setHeader('Cache-Control', 'no-store');
    res.setHeader('X-Frame-Options', 'DENY'); res.setHeader('Content-Security-Policy', "frame-ancestors 'none'");   // vercel.json 과 같게: 지도는 팝업으로만 연다
    if (url.pathname === '/api/bus') return bus(req, res);
    if (url.pathname === '/api/v1/resolve') return resolve(req, res);
    if (url.pathname === '/api/v1/codes/search') return search(req, res);
    if (url.pathname === '/api/v1/notices') return notices(req, res);
    if (url.pathname === '/api/v1/buildings') return buildings(req, res);
    if (url.pathname === '/api/v1/permits') return permits(req, res);
    if (url.pathname === '/api/v1/infra') return infra(req, res);
    let rel = decodeURIComponent(url.pathname);
    if (rel.endsWith('/')) rel += 'index.html';
    const file = path.resolve(root, '.' + rel);
    const parts = path.relative(root, file).split(path.sep);
    if (file !== root && !file.startsWith(root + path.sep)) { res.statusCode = 403; return res.end('forbidden'); }
    if (parts.some((p) => p.startsWith('.') || p === 'node_modules')) { res.statusCode = 404; return res.end('not found'); }
    fs.stat(file, (err, st) => {
      if (err || !st.isFile()) { res.statusCode = 404; return res.end('not found'); }
      res.setHeader('Content-Type', TYPES[path.extname(file)] || 'application/octet-stream');
      fs.createReadStream(file).pipe(res);
    });
  });
}

if (require.main === module) {
  const port = Number(process.argv[2]) || 8000;
  const env = Object.assign({}, loadEnv(path.join(ROOT, '.env.local')), process.env);
  const keys = keySummary(env);
  require('../lib/cache.js').createCache({ dir: require('../lib/cache.js').defaultDir(env) }).purgeExpired();   // 시작할 때 만료된 캐시 파일 정리
  createServer(ROOT, env).listen(port, '127.0.0.1', () => console.log(`http://127.0.0.1:${port}/  (키: ${keys.text} · 버스 위치 ${keys.bus ? '켬' : '꺼짐: .env.local 에 DATA_GO_KR_KEY_BUS_1 또는 DATA_GO_KR_KEY 가 없음'})`));
}
module.exports = { createServer, loadEnv, keySummary };
