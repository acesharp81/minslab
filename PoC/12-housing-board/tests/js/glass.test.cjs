// HUD 표지·요약·범례·하단 바·옵션·툴바·상세 카드를 짙은 네이비 유리로 바꿔도 글자가 읽히는지 확인한다(상황판 시안 M3, 어두운 지도).
// 가장 밝은 지도(흰 점: 역·정류장)와 가장 어두운 지도(검정) 위에서 모두 본문·보조·상태 글자의 대비가 4.5:1 이상이어야 한다.
// 유리는 투명도(alpha)와 흐림(blur)만 쓴다. 밝기를 누르는 필터는 쓰지 않으므로 뒤 지도 색을 그대로 깔고 계산한다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const css = fs.readFileSync(path.join(ROOT, 'assets/css/app.css'), 'utf8');
const app = fs.readFileSync(path.join(ROOT, 'assets/js/app.js'), 'utf8');

const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
const ratio = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
const over = (rgba, backdrop) => { const [r, g, b, a] = rgba; return [r, g, b].map((v, i) => v * a + backdrop[i] * (1 - a)); };

function rootVars() {
  // 줄 맨 앞의 :root 블록만 읽는다(@supports not 안의 대체값 :root 는 따로 본다). 기반시설 보라·노랑(--edu·--power)은 아래쪽 :root 에 있다.
  const blocks = [...css.matchAll(/(?:^|\n):root\{([^}]*)\}/g)];
  assert.ok(blocks.length, ':root 블록이 있어야 한다');
  const vars = {};
  for (const b of blocks) for (const [, k, v] of b[1].matchAll(/(--[\w-]+):([^;]+);?/g)) vars[k] = v.trim();
  return vars;
}
const VARS = rootVars();
function glass(name) {
  const m = /^rgba\((\d+),(\d+),(\d+),([\d.]+)\)$/.exec(VARS[name] || '');
  assert.ok(m, `${name} 은 rgba(...) 여야 한다: ${VARS[name]}`);
  return [+m[1], +m[2], +m[3], +m[4]];
}
const STATUS = [...(/const COLOR = \{([^}]*)\}/.exec(app)[1]).matchAll(/#[0-9A-Fa-f]{6}/g)].map((x) => x[0]);   // 모집·착공·준공·입주·계획·공공택지 민간

// 지도에서 가장 밝은/어두운 면.
const MAP = { lightest: '#FFFFFF', darkest: '#000000' };
// 유리 위 글자: 본문·보조·경고, 기반시설 보라·노랑, 6단계 색 글자(HUD 표지의 상태 글자).
const TEXT = [VARS['--ink'], VARS['--ink2'], VARS['--mute'], VARS['--warn'], VARS['--edu'], VARS['--power'], ...STATUS];

function check(name, textColors, backdrops) {
  const g = glass(name);
  for (const bd of backdrops) for (const tx of textColors) {
    const r = ratio(hex(tx), over(g, hex(bd)));
    assert.ok(r >= 4.5, `${name} 위 ${tx} 글자가 ${bd} 지도 위에서 ${r.toFixed(2)}:1 (4.5:1 필요)`);
  }
}

test('표지·요약·상세 카드 유리 위 글자 대비가 밝은 지도·어두운 지도 모두에서 4.5:1 이상', () => {
  for (const n of ['--glass-tag', '--glass-tag-hover', '--glass-sum', '--glass-card', '--glass-hud']) check(n, TEXT, [MAP.lightest, MAP.darkest]);
});

/* 2026-10-10 피드백 '상세 카드는 HUD 처럼 투명하게, 안내 띠는 입력줄 아래 투명하게': 단지 상세 카드는 --glass-hud(.86, 대비가 지켜지는 가장 옅은 쪽),
   안내 띠는 본문 글자(--ink)만 쓰므로 더 옅은 --glass-note. Next 지도의 밝은 테마 값도 같은 기준으로 본다 */
test('상세 카드(--glass-hud)는 기존 카드보다 옅고, 안내 띠(--glass-note)는 본문 글자만으로 4.5:1 을 지킨다(두 테마)', () => {
  assert.ok(glass('--glass-hud')[3] < glass('--glass-card')[3], '상세 카드가 다른 카드보다 비친다');
  assert.ok(glass('--glass-note')[3] <= 0.7, `안내 띠 ${glass('--glass-note')[3]}`);
  check('--glass-note', [VARS['--ink']], [MAP.lightest, MAP.darkest]);
  const lightBlock = /html\[data-map-shell\]:not\(\.dark\)\{([^}]*)\}/.exec(css)[1];
  const L = {}; for (const [, k, v] of lightBlock.matchAll(/(--[\w-]+):([^;]+);?/g)) L[k] = v.trim();
  const rgba = (v) => /^rgba\((\d+),(\d+),(\d+),([\d.]+)\)$/.exec(v).slice(1).map(Number);
  for (const [n, texts] of [['--glass-hud', [L['--ink'], L['--ink2'], L['--mute'], L['--warn']]], ['--glass-note', [L['--ink']]]]) {
    assert.ok(L[n], `밝은 테마 ${n}`);
    for (const bd of [MAP.lightest, MAP.darkest]) for (const tx of texts) { const r = ratio(hex(tx), over(rgba(L[n]), hex(bd))); assert.ok(r >= 4.5, `밝은 테마 ${n} 위 ${tx} ${bd} ${r.toFixed(2)}:1`); }
  }
  assert.ok(rgba(L['--glass-hud'])[3] < rgba(L['--glass-card'])[3], '밝은 테마에서도 상세 카드가 더 비친다');
  assert.match(css, /(?:^|\n)\.maplibregl-popup-content\{[^}]*background:var\(--glass-hud\)/);
});

test('독립 지도는 기존 다크 배경을 유지하고 Next 지도는 저장된 테마에 따라 배경을 선택한다', () => {
  assert.match(app, /window\.VWORLD_LAYER \|\| 'midnight'/);
  assert.match(app, /ofm: 'dark'/);
  assert.match(app, /bg: '#0A1030'/);
  assert.match(app, /const TH = \(\) => LIGHT_MAP \? LIGHT_THEME : THEME/);
  assert.match(app, /vw: 'white', ofm: 'liberty'/, "라이트는 V-World 백지도: 'Base' 는 장소 글자가 그림에 박혀 기울인 지도에서 번지고 벡터 지명과 겹쳤다");
  assert.doesNotMatch(css, /data-theme/i);
  assert.doesNotMatch(app, /nightChip|setTheme|reTheme/i);
});

test('유리는 뒤 지도가 비칠 만큼은 투명하되 글자 대비를 지킬 만큼 짙다(.85~.97)', () => {
  for (const n of ['--glass-tag', '--glass-tag-hover', '--glass-sum', '--glass-card', '--glass-hud']) { const a = glass(n)[3]; assert.ok(a >= 0.85 && a <= 0.97, `${n} ${a}`); }
});

test('필터는 흐림(blur)과 채도만 쓰고 밝기를 누르지 않으며, 상세 카드는 덜 번진다(4px 이하)', () => {
  assert.match(css, /--glass-blur:blur\(\d+px\) saturate\([\d.]+\)/);
  assert.doesNotMatch(css, /brightness\(/);
  const m = /--glass-card-blur:blur\(([\d.]+)px\)/.exec(css);
  assert.ok(m, '--glass-card-blur 정의를 찾을 수 없음');
  assert.ok(+m[1] <= 4, `--glass-card-blur 흐림 ${m[1]}px`);
});

test('표지·요약·카드가 유리 변수와 backdrop-filter 를 쓴다(-webkit- 포함)', () => {
  const CARDS = ['.maplibregl-popup-content', '.optpanel'];   // 뒤 지도가 보이는 카드 필터를 쓰는 선택자
  for (const sel of ['.maplibregl-popup-content', '.hudtag', '.maplegend', '.tools', '.rctl', '.optpanel']) {   // 공급 요약은 2026-10-10 머리 줄로 옮겨 유리판이 아니고, 입주 시기 재생바는 없앴다
    const m = new RegExp(`(?:^|\\n)${sel.replace('.', '\\.')}\\{([^}]*)\\}`).exec(css);
    assert.ok(m, `${sel} 규칙을 찾을 수 없음`);
    assert.match(m[1], /var\(--glass-(tag|sum|card|hud)\)/, `${sel} 배경이 유리 변수여야 한다`);
    const f = CARDS.includes(sel) ? '--glass-card-blur' : '--glass-blur';
    assert.match(m[1], new RegExp(`-webkit-backdrop-filter:var\\(${f}\\)`));
    assert.match(m[1], new RegExp(`[^-]backdrop-filter:var\\(${f}\\)`));
  }
});

test('backdrop-filter 를 못 쓰는 브라우저용 @supports not 대체가 거의 불투명(.94 이상)하다', () => {
  const m = /@supports not \(\(backdrop-filter:blur\(1px\)\) or \(-webkit-backdrop-filter:blur\(1px\)\)\)\{:root\{([^}]*)\}\}/.exec(css);
  assert.ok(m, '@supports not 블록이 있어야 한다');
  for (const [, k, v] of m[1].matchAll(/(--glass-[\w-]+):([^;]+);?/g)) {
    const mm = /rgba\(\d+,\d+,\d+,([\d.]+)\)/.exec(v);
    if (mm) assert.ok(+mm[1] >= 0.94, `${k} 대체값 ${v}`);
  }
  assert.match(m[1], /--glass-card/); assert.match(m[1], /--glass-hud/); assert.match(m[1], /--glass-note/);
});

test('상태 칩과 막대 같은 작은 색 요소는 불투명을 유지한다', () => {
  assert.match(css, /\.pc-chip\.sale\{background:var\(--sale\)/);
  assert.match(css, /\.pc-chip\.priv\{background:#2A3568/);
  assert.doesNotMatch(css, /\.pc-chip[^{]*\{[^}]*rgba\(/);
});

test('칩 안의 글자(--on-c)가 6단계 색 바탕 위에서 4.5:1 이상이다', () => {
  for (const c of STATUS) { const r = ratio(hex(VARS['--on-c']), hex(c)); assert.ok(r >= 4.5, `${c} 바탕 위 --on-c ${r.toFixed(2)}:1`); }
});

test('패널 글자(본문·보조·6단계 색)가 카드 바탕(--pn, --pn2) 위에서 4.5:1 이상이다', () => {
  for (const bg of [VARS['--bg'], VARS['--pn'], VARS['--pn2']]) for (const tx of TEXT) {
    const r = ratio(hex(tx), hex(bg)); assert.ok(r >= 4.5, `${tx} 글자가 ${bg} 바탕에서 ${r.toFixed(2)}:1`);
  }
});

/* ---------- 주소 이동 입력줄: 어두운 유리 3단(입력 중 > 대기 > 비활성) ---------- */
const CMD = { active: glass('--glass-cmd-active'), idle: glass('--glass-cmd-idle'), off: glass('--glass-cmd-off') };

test('입력줄 유리: 상태가 투명도로 구별된다(입력 중 .90~.97 > 대기 .65~.85 > 비활성 .50~.70)', () => {
  const [a, i, o] = [CMD.active[3], CMD.idle[3], CMD.off[3]];
  assert.ok(a >= 0.9 && a <= 0.97, `입력 중 ${a}`); assert.ok(i >= 0.65 && i <= 0.85, `대기 ${i}`); assert.ok(o >= 0.5 && o <= 0.7, `비활성 ${o}`);
  assert.ok(a > i && i > o, '입력 중 > 대기 > 비활성 순서로 투명해져야 한다');
});

test('입력줄 유리: 입력 중·대기는 밝은 지도·어두운 지도 위에서 글자·보조 글자·자리표시가 4.5:1 이상, 비활성은 3:1 이상', () => {
  const text = hex(VARS['--cmd-text']), sub = hex(VARS['--cmd-sub']);   // 자리표시(placeholder)도 --cmd-sub 를 쓴다
  assert.match(css, /\.cmd-bar input::placeholder\{color:var\(--cmd-sub\)/);
  for (const bd of [MAP.lightest, MAP.darkest]) {
    const act = over(CMD.active, hex(bd)), sel = over([232, 237, 255, 0.14], act);   // 고른 줄은 밝은 막을 한 겹 더 쓴다
    for (const [name, tx, bg] of [['입력 중 글자', text, act], ['입력 중 보조', sub, act], ['입력 중 보조(고른 줄)', sub, sel]]) {
      const r = ratio(tx, bg); assert.ok(r >= 4.5, `${name} ${bd} 지도 위 ${r.toFixed(2)}:1`);
    }
    const idle = over(CMD.idle, hex(bd));
    for (const [name, tx] of [['대기 글자', text], ['대기 자리표시', sub]]) { const r = ratio(tx, idle); assert.ok(r >= 4.5, `${name} ${bd} 지도 위 ${r.toFixed(2)}:1`); }
    const off = over(CMD.off, hex(bd));
    for (const [name, tx] of [['비활성 글자', text], ['비활성 자리표시(이유 문구)', sub]]) { const r = ratio(tx, off); assert.ok(r >= 3, `${name} ${bd} 지도 위 ${r.toFixed(2)}:1 (비활성은 3:1)`); }
  }
});

test('입력줄 유리: 입력줄·후보·인식 칩이 상태별 변수와 backdrop-filter 를 쓰고, backdrop-filter 없는 브라우저는 거의 불투명', () => {
  const rule = (sel) => { const m = new RegExp(`(?:^|\\n)${sel.replace(/[.\[\]="]/g, '\\$&')}\\{([^}]*)\\}`).exec(css); assert.ok(m, `${sel} 규칙을 찾을 수 없음`); return m[1]; };
  const g = rule('.cmd-bar,.cmd-res,.cmd-parse');
  assert.match(g, /background:var\(--cmd-bg\)/); assert.match(g, /-webkit-backdrop-filter:var\(--glass-blur\)/); assert.match(g, /[^-]backdrop-filter:var\(--glass-blur\)/);
  assert.match(rule('.cmd'), /--cmd-bg:var\(--glass-cmd-idle\)/);
  assert.match(rule('.cmd[data-state="active"],.cmd[data-state="busy"]'), /--cmd-bg:var\(--glass-cmd-active\)/);
  assert.match(rule('.cmd[data-state="disabled"]'), /--cmd-bg:var\(--glass-cmd-off\)/);
  const fb = /@supports not[^{]*\{\s*:root\{([^}]*)\}\}/.exec(css)[1];
  for (const n of ['--glass-cmd-active', '--glass-cmd-idle', '--glass-cmd-off']) { const m = new RegExp(`${n}:rgba\\(\\d+,\\d+,\\d+,([\\d.]+)\\)`).exec(fb); assert.ok(m && +m[1] >= 0.94, `${n} 대체값`); }
});


test('라이트 지도 HUD 본문·보조·상태 글자는 가장 밝고 어두운 지도 위에서 4.5:1 이상이다', () => {
  const light = /html\[data-map-shell\]:not\(\.dark\)\{([^}]*)\}/.exec(css)[1];
  const shell = /html\[data-map-shell\]\{([^}]*)\}/.exec(css)[1];   // 두 테마 공통: 단계색·강조색은 대시보드 토큰을 가리킨다
  const tw = fs.readFileSync(path.join(ROOT, 'app/tailwind.css'), 'utf8'), twLight = tw.slice(tw.indexOf('\n:root {'), tw.indexOf('\n}\n', tw.indexOf('\n:root {')));
  const twVar = (n) => { const m = new RegExp(`${n}:\\s*(#[0-9A-Fa-f]{6})`).exec(twLight); assert.ok(m, `app/tailwind.css 라이트 ${n}`); return m[1]; };
  const resolve = (v) => { const m = /^var\((--[\w-]+)\)$/.exec(v); return m ? twVar(m[1]) : v; };
  const vars = Object.fromEntries([...shell.matchAll(/(--[\w-]+):([^;]+);?/g), ...light.matchAll(/(--[\w-]+):([^;]+);?/g)].map((m) => [m[1], resolve(m[2].trim())]));
  const text = ['--ink', '--ink2', '--mute', '--warn', '--sale', '--build', '--soon', '--move', '--plan', '--priv', '--edu', '--power'];
  for (const glassName of ['--glass-tag', '--glass-tag-hover', '--glass-sum', '--glass-card']) {
    const g = vars[glassName].match(/[\d.]+/g).map(Number);
    for (const backdrop of ['#FFFFFF', '#000000']) for (const name of text) {
      assert.ok(ratio(hex(vars[name]), over(g, hex(backdrop))) >= 4.5, `${glassName} 위 ${name} 대비`);
    }
  }
});
