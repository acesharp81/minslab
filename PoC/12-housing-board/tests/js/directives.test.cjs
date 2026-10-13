'use strict';
// 총리 지시 6건을 요구사항으로 반영한 화면(docs/product/화면-배색-개선-계획.md 6절)을 확인한다.
// 8.14 정례 보고 → 보고자료, 9.4 국민 예측가능성 → 우리 동네, 9.30 쉬운 설명 → 사업 상세의 '다음 단계'. 숫자는 calc.ts 의 순수 함수로 다시 세어 대조한다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const C = require('../../lib/board/calc.ts');
const molit = require('../../data/board/molit.json');
const lh = require('../../data/board/lh-completion.json');
const { MENU } = require('../../lib/shell/menu.ts');

test('우리 동네 달력(lhCalendar): 시도별 달력을 모두 더하면 전국 LH 준공 예정(lhByMonth)과 같고, 달 안은 날짜 순이다', () => {
  const sido = [...new Set(lh.blocks.map((b) => b.sido))];
  const nation = C.lhByMonth(lh, C.AHEAD_FROM, 12);
  const cals = sido.map((s) => C.lhCalendar(lh, s, C.AHEAD_FROM, 12));
  nation.forEach((m, i) => {
    assert.equal(cals.reduce((a, c) => a + c[i].units, 0), m.units, `${m.ym} 세대수`);
    assert.equal(cals.reduce((a, c) => a + c[i].blocks.length, 0), m.blocks, `${m.ym} 블록 수`);
    assert.equal(cals[0][i].ym, m.ym);
  });
  for (const c of cals) for (const m of c) for (let k = 1; k < m.blocks.length; k++) assert.ok(m.blocks[k - 1].date <= m.blocks[k].date, '날짜 순');
  const gyeonggi = C.lhCalendar(lh, '41', C.AHEAD_FROM, 12);
  assert.ok(gyeonggi.some((m) => m.blocks.length), '경기는 1년 안 준공 예정이 있다');
});

test("메뉴: 보고자료·우리 동네는 화면이 생겨 '준비 중'이 아니고, 빈 화면을 그리던 [section] 경로는 없다", () => {
  assert.deepEqual(MENU.filter((m) => m.soon), []);
  assert.ok(!fs.existsSync(path.join(ROOT, 'app/(dashboard)/[section]')), '[section] 경로');
  for (const f of ['app/(dashboard)/reports/page.tsx', 'app/(dashboard)/my-area/page.tsx', 'app/(dashboard)/my-area/[sido]/page.tsx']) assert.ok(fs.existsSync(path.join(ROOT, f)), f);
});

test('종합상황판의 총리 지시 줄은 원래 카드 그대로다(그림을 넣지 않는다 — 사용자 피드백 2026-10-10)', () => {
  const b = read('components/board/Board.tsx');
  assert.match(b, /<div className="grid grid-cols-\[repeat\(auto-fit,minmax\(min\(190px,100%\),1fr\)\)\] gap-2">/);
  assert.match(b, /<span className="text-\[14px\] text-muted-foreground">\{x\.date\} · \{x\.t\}<\/span>/);
  assert.doesNotMatch(b, /DIR_TL|top-\[83\.5px\]/);
  assert.match(read('app/tailwind.css'), /\.board-desktop \[data-slot="board-dir"\] \{ padding-top: 15px; padding-bottom: 16px; \}/);
});

test('종합상황판 리본 차트: 상자는 가로로만 밀리고(세로 스크롤바로 그림이 흔들리지 않게), 선택한 달의 기준 막대는 테두리 없는 반투명 HUD 막대다', () => {
  const b = read('components/board/Board.tsx'), r = read('components/board/ribbon.ts');
  assert.match(b, /<div className="overflow-x-auto overflow-y-hidden rounded-\[10px\]">/);
  assert.match(b, /rx="3" fill=\{CUR\.fill\} className="rb-cur" pointerEvents="none" \/>/);
  assert.doesNotMatch(b, /stroke=\{CUR\./, '기준 막대에 테두리가 없다');
  assert.match(r, /export const CUR = \{ fill: 'url\(#cur-hud\)' \};/);
  assert.match(r, /<linearGradient id="cur-hud" x1="0" y1="0" x2="0" y2="1">/);
});

test('종합상황판 리본·12개월 막대 그라데이션: 층마다 위 하이라이트→단계색→아래 그늘, 색은 style 로 준다(stop-color 속성의 color-mix 는 검정으로 칠해졌다), 층 경계는 --rb-seam', () => {
  const r = read('components/board/ribbon.ts'), b = read('components/board/Board.tsx'), tw = read('app/tailwind.css');
  assert.match(r, /<stop offset="0" style="stop-color:color-mix\(in srgb, \$\{C\[k\]\} 70%, var\(--rb-hi\)\)"\/>/);
  assert.match(r, /<stop offset="1" style="stop-color:color-mix\(in srgb, \$\{C\[k\]\} 86%, var\(--rb-lo\)\)"\/>/);
  assert.doesNotMatch(r + b, /stop-color="color-mix|stopColor=\{`color-mix/, 'color-mix 를 stop-color 속성에 넣지 않는다');
  assert.match(r, /fill="url\(#rbg\$\{k\}\)"/);
  assert.match(r, /stroke="\$\{PAL\.seam\}" stroke-width="0\.9"/);
  assert.match(b, /style=\{\{ stopColor: `color-mix\(in srgb, \$\{C\[4\]\} 66%, var\(--rb-hi\)\)` \}\}/);
  assert.match(b, /fill="url\(#fm-g\)"/);
  for (const sel of ['\n:root {', '\n.dark {']) { const i = tw.indexOf(sel), blk = tw.slice(i, tw.indexOf('\n}\n', i)); assert.match(blk, /--rb-hi: #/); assert.match(blk, /--rb-lo: #/); }
});

test('리본 위 라벨·툴팁은 흰 판이 아니라 HUD 유리다: 반투명 남색 판 + 밝은 가장자리 + 강조 띠 + 흰 글자, 뒤가 가장 밝아도 4.5:1', () => {
  const r = read('components/board/ribbon.ts'), b = read('components/board/Board.tsx'), tw = read('app/tailwind.css');
  assert.match(r, /fill="\$\{PAL\.hud\}" stroke="\$\{PAL\.hudLine\}"/);
  assert.match(r, /fill="\$\{PAL\.hudTxt\}"/);
  assert.doesNotMatch(r + tw, /rb-halo/, '흰 판 토큰(--rb-halo)은 없다');
  assert.match(r, /labelSVG\(cx, py - 40, t, PAL\.band\)/);
  assert.match(r, /`\$\{f\(tot\(cur\)\)\}호`, PAL\.hudAcc\)/);
  assert.match(b, /data-slot="board-tip" className="dark [^"]*bg-\[color-mix\(in_srgb,var\(--popover\)_88%,transparent\)\][^"]*backdrop-blur-\[6px\]/, '툴팁은 다크 범위의 반투명 유리');
  // 대비: 유리(rgb a%)를 가장 밝은 바탕(흰색) 위에 깔았을 때 흰 글자
  const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  for (const sel of ['\n:root {', '\n.dark {']) {
    const i = tw.indexOf(sel), blk = tw.slice(i, tw.indexOf('\n}\n', i));
    const m = /--rb-hud: rgb\((\d+) (\d+) (\d+) \/ (\d+)%\);/.exec(blk); assert.ok(m, `${sel} --rb-hud`);
    const a = +m[4] / 100, bg = [+m[1], +m[2], +m[3]].map((v) => v * a + 255 * (1 - a));
    const r2 = (1.05) / (lum(bg) + 0.05); assert.ok(r2 >= 4.5, `${sel.trim()} 흰 바탕 위 HUD 판의 흰 글자 ${r2.toFixed(2)}:1`);
  }
});
