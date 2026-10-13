'use strict';
// 막대 그래프는 모서리를 둥글리지 않는다(2026-10-10 사용자 요청 "막대 그래프들은 라운드 처리 없이 표기해", 계획서 11절).
// 범례 견본·단추·카드·HUD 라벨은 막대가 아니라 대상이 아니다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

test('대시보드 막대: 상태 비율 막대·기관별 막대(bar3)·12개월 막대와 선택 테두리·쌓은 막대·계단 칸(넓은 화면)', () => {
  const board = read('components/board/Board.tsx');
  assert.match(board, /<div className="q-grow-x flex h-3\.5 gap-0\.5 overflow-hidden bg-pn2 /);
  assert.match(read('components/board/styles.ts'), /export const bar3 = "flex gap-px overflow-hidden";/);
  const fm = /<svg id="fmonths"[\s\S]*?<\/svg>/.exec(board)[0];
  assert.doesNotMatch(fm, /\brx=/, '12개월 막대·선택 테두리');
  assert.doesNotMatch(read('components/charts/StackedMonths.tsx'), /\brx=|rounded/);
  const ladder = read('components/StageLadder.tsx');
  assert.doesNotMatch(ladder, /rounded-t-/, '계단 칸 윗모서리');
  assert.match(ladder, /mobile:rounded-\[8px\]/, '900px 이하 세로 목록(막대가 아님)은 그대로');
});

test('지도 막대: 상태 막대(.sbar)·공정 막대(.mini·.pg .bar2·.hudtag .ht-bar)', () => {
  const css = read('assets/css/app.css');
  for (const sel of ['.sbar{', '.mini{', '.pg .bar2{', '.hudtag .ht-bar{']) {
    const i = css.indexOf(sel); assert.ok(i >= 0, sel);
    assert.doesNotMatch(css.slice(i, css.indexOf('}', i)), /border-radius/, sel);
  }
  assert.doesNotMatch(css, /\.(sbar|mini|bar2|ht-bar)[^{]*\{[^}]*border-radius/);
});
