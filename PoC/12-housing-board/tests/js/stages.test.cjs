'use strict';
// 단계 표기(docs/product/화면-배색-개선-계획.md 5절)를 정적으로 고정한다.
// 문구는 발표자료(docs/주택파동_발표자료.html)의 SHEET 03 '주택공급 6단계, 단계마다 답해야 할 질문'과 SHEET 02 '정책적 필요성'에서 직접 읽어 대조한다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const deck = read('docs/주택파동_발표자료.html');
const stages = read('lib/board/stages.ts'), sample = read('lib/board/sample.ts'), board = read('components/board/Board.tsx'), app = read('assets/js/app.js');
const strip = (h) => h.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();

test('공식 6단계: 이름·질문·공개 범위가 발표자료 SHEET 03 과 같다(01~04 담당자 열람, 05~06 국민 공개)', () => {
  const qs = [...deck.matchAll(/<p class="q"[^>]*data-k="(\d)"[^>]*>([^<]+)<\/p>/g)].map((m) => [Number(m[1]), m[2].trim()]).sort((a, b) => a[0] - b[0]).map((x) => x[1]);
  assert.equal(qs.length, 6, '발표자료에서 질문 6개를 찾아야 한다');
  const rows = [...stages.matchAll(/\{ code: '(\d\d)', name: '([^']+)', q: '([^']+)', scope: '(gov|pub)'/g)].map((m) => ({ code: m[1], name: m[2], q: m[3], scope: m[4] }));
  assert.deepEqual(rows.map((r) => r.name), ['정책', '사업화', '인허가', '건설', '공급', '입주']);
  assert.deepEqual(rows.map((r) => r.q), qs);
  assert.deepEqual(rows.map((r) => r.scope), ['gov', 'gov', 'gov', 'gov', 'pub', 'pub']);
});

test('단계를 표기하는 대시보드 화면(단계별·단계 상세·사업 상세·사업 목록)은 계단식 6단계(StageLadder)를 쓰고, 옛 Stepper 는 없다', () => {
  for (const f of ['app/(dashboard)/stage/page.tsx', 'app/(dashboard)/stage/[id]/page.tsx', 'app/(dashboard)/home-project/[id]/page.tsx', 'app/(dashboard)/projects/page.tsx']) {
    const s = read(f);
    assert.match(s, /import StageLadder from '[./]+components\/StageLadder';/, f);
    assert.match(s, /<StageLadder /, f);
    assert.doesNotMatch(s, /Stepper/, f);
  }
  assert.ok(!fs.existsSync(path.join(ROOT, 'components/ui/stepper.tsx')), '쓰는 곳이 없는 stepper.tsx 는 지운다');
  assert.match(read('app/(dashboard)/home-project/[id]/page.tsx'), /<StageLadder current=\{p\.stageCode\} \/>/, '사업 상세는 지금 단계를 강조한다');
  assert.match(read('app/(dashboard)/stage/[id]/page.tsx'), /<StageLadder className="mb-5" current=\{id\}/, '단계 상세는 그 단계를 강조한다');
});

test('StageLadder: 공개 범위 범례, 계단(단계마다 높아지는 상자), 질문, 현재 단계 표시(aria-current), 단계 목록 링크, 900px 이하 세로 목록', () => {
  const c = read('components/StageLadder.tsx');
  assert.match(c, /담당자 열람 \(01~04\)/);
  assert.match(c, /국민에게도 공개 \(05~06\)/);
  assert.match(c, /'--h': `\$\{64 \+ i \* 16\}px`/, '상자 높이가 단계마다 16px 씩 커진다');
  assert.match(c, /aria-current=\{on \? 'step' : undefined\}/);
  assert.match(c, /href=\{`\/stage\/\$\{s\.code\}`\}/);
  assert.match(c, /\{s\.q\}/);
  assert.match(c, /mobile:grid-cols-1/);
  assert.match(c, /gov: 'var\(--scope-gov\)', pub: 'var\(--scope-pub\)'/);
});

test('지도의 단계 필터·단지 카드 단계 위치는 공식 6단계이고, 단지 상태는 사업 레지스트리와 같은 매핑으로 묶인다', () => {
  assert.match(app, /const STAGES6 = \[\['01', '정책', \[\]\], \['02', '사업화', \[\]\], \['03', '인허가', \['계획'\]\], \['04', '건설', \['건설 단계', '준공 임박'\]\], \['05', '공급', \['분양중'\]\], \['06', '입주', \['입주 단계'\]\]\]/);
  const { stageOf } = require(path.join(ROOT, 'lib/projects.js'));
  const MAP = { '계획': '03', '건설 단계': '04', '준공 임박': '04', '분양중': '05', '입주 단계': '06' };
  for (const [status, code] of Object.entries(MAP)) assert.equal(stageOf(status, { approvedAt: true }), code, `레지스트리 stageOf(${status})`);
  assert.match(app, /data-status="\$\{live\.join\('\|'\)\}"/, '한 단계가 여러 상태를 함께 켜고 끈다');
  assert.match(app, /const now = sts\.includes\(b\.status\)/, '단지 카드의 지금 단계 = 상태가 속한 단계');
  assert.doesNotMatch(app, /'착공', '건설 단계'|'모집', '분양중'|PERMIT_COLOR/, '옛 단계 이름·인허가 대체색이 남지 않는다');
});

/* ---------- 실적 지표의 6단계 표기(계획서 11절, 2026-10-10 "6단계가 아닌 3단·4단 표기를 고쳐") ---------- */
test('통계누리 지표 → 6단계 대응은 사업 레지스트리(stageOf)와 같고, 지표 순서는 6단계 순서다', () => {
  const S = require('../../lib/board/stages.ts'), C = require('../../lib/board/calc.ts'), P = require('../../lib/projects.js');
  assert.deepEqual({ ...S.METRIC_STAGE }, { permit: '03', start: '04', sale: '05', complete: '06' });
  // 인허가(사업승인 있음) = 계획 → 03, 착공 = 건설 단계 → 04, 분양 = 분양중 → 05, 준공(사용검사) = 입주 단계 → 06
  const stageOf = /function stageOf[\s\S]*?\n\}/.exec(read('lib/projects.js'))[0];
  assert.match(stageOf, /case '입주 단계': return '06';/); assert.match(stageOf, /case '분양중': return '05';/); assert.match(stageOf, /case '건설 단계': case '준공 임박': return '04';/); assert.match(stageOf, /case '계획': return approvedAt \? '03'/);
  assert.deepEqual(C.METRICS, ['permit', 'start', 'sale', 'complete']);
  assert.deepEqual(C.METRICS.map((k) => S.METRIC_STAGE[k]), ['03', '04', '05', '06']);
  assert.ok(P);
});

test('지도 범례·옵션 창의 단지 상태는 6단계 순서이고 단계 번호가 붙는다(머리 줄 6단계 필터와 같은 대응)', () => {
  assert.match(app, /const BY_STAGE = STAGES6\.flatMap\(\(s\) => s\[2\]\);/);
  assert.match(app, /BY_STAGE\.forEach\(\(st\) => \{ if \(present\.has\(st\)\) add\(`<i class="sw \$\{KIND\[st\]\}"><\/i>`, st, `<small>\$\{stageOfSt\(st\)\}/);
  assert.match(app, /const present = BY_STAGE\.filter\(\(st\) => ALL_ST\.has\(st\)\);/);
  assert.match(app, /\$\{st\} <small>\$\{stageOfSt\(st\)\}<\/small><\/label>/);
});
