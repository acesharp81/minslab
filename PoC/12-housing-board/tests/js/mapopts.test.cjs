'use strict';
// 지도 옵션(2026-10-10 사용자 요청 "지도의 기본옵션은 전체 선택되어 있도록 하고 옵션 버튼에서 기존건물 흐리게는 이 hud에 추가 / 버스위치 조회는 '버스위치'로 요약").
// 옵션 창의 체크 상자는 기본이 모두 켬이고, 주소에는 끈 것만 =0 으로, 옵션 버튼의 숫자는 꺼 둔 옵션 수다. '되돌리기'도 모두 켬으로.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const app = read('assets/js/app.js'), html = read('index.html');

test('옵션 상태는 모두 기본 켬이고 주소 =0 으로만 끈다', () => {
  for (const [v, k] of [['privOn', 'priv'], ['hudOn', 'hud'], ['cardsOn', 'cards'], ['ctxOn', 'ctx'], ['ringOn', 'ring'], ['infraOn', 'infra'], ['zoneOn', 'zone'], ['busOn', 'bus']]) {
    assert.match(app, new RegExp(`let ${v} = q\\.get\\('${k}'\\) !== '0';`), v);
  }
  assert.match(app, /set\('ring', ringOn \? '' : '0'\); set\('hud', hudOn \? '' : '0'\); set\('cards', cardsOn \? '' : '0'\);/);
  assert.match(app, /set\('zone', HAS_INFRA && !zoneOn \? '0' : ''\);/);
  assert.doesNotMatch(app, /q\.get\('(hud|cards|ring|zone)'\) === '1'/);
});

test('옵션 버튼의 숫자는 꺼 둔 옵션 수, 기본값으로 되돌리기는 모두 켬', () => {
  const m = /const optCount = \(\) => ([^\n]+);/.exec(app);
  assert.ok(m);
  for (const part of ['SHOWN.size < ALL_ST.size ? 1 : 0', 'HAS_CTX && !ctxOn ? 1 : 0', 'HAS_CTX && ctxOn && !ringOn ? 1 : 0', '!hudOn ? 1 : 0', '!cardsOn ? 1 : 0', 'HAS_PRIV && !privOn ? 1 : 0', 'HAS_INFRA && !infraOn ? 1 : 0', 'HAS_INFRA && !zoneOn ? 1 : 0', 'HAS_BUS && !busOn ? 1 : 0']) assert.ok(m[1].includes(part), part);
  assert.match(app, /ctxOn = true; ringOn = true; infraOn = true; zoneOn = true; busOn = true; hudOn = true; cardsOn = true; privOn = true;/);
  assert.match(html, /<button type="button" class="reset" id="optReset">기본값으로 되돌리기<\/button>/);
});

test("버스 위치 단추 문구는 '버스위치'(조회 중·새로고침은 그대로)", () => {
  assert.match(html, /<button type="button" id="busLoad" class="opt" hidden title="[^"]+">버스위치<\/button>/);
  assert.match(app, /btn\.textContent = BUS\.loading \? '조회 중…' : has \? '버스 새로고침' : '버스위치';/);
  assert.doesNotMatch(app + html, /버스 위치 조회/);
});

test('public/ 사본이 원본과 같다(지도는 public/assets 를 내보낸다)', () => {
  assert.equal(read('public/assets/js/app.js'), app);
  assert.equal(read('public/assets/css/app.css'), read('assets/css/app.css'));
});
