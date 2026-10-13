'use strict';
// Tailwind CSS v4 + shadcn/ui 기반(app/tailwind.css, components.json)이 계획대로인지 정적으로 확인한다.
// 겉모습이 그대로인지는 scripts/visual(스크린샷 80장 픽셀 비교)이 본다. 여기서는 그 전제 — preflight 보류·토큰·연결 — 를 지킨다.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const css = read('app/tailwind.css');
const pkg = JSON.parse(read('package.json'));

test('preflight(전역 리셋)를 가져오지 않는다: theme·utilities 만 레이어로 가져온다(옛 CSS 가 걷히는 마지막 단계에서 켠다)', () => {
  assert.match(css, /@layer theme, base, components, utilities;/);
  assert.match(css, /@import "tailwindcss\/theme\.css" layer\(theme\);/);
  assert.match(css, /@import "tailwindcss\/utilities\.css" layer\(utilities\);/);
  assert.doesNotMatch(css, /@import "tailwindcss";/, '전체 가져오기는 preflight 를 포함한다');
  assert.doesNotMatch(css, /preflight\.css/);
});

/* tailwind.css 에서 `:root {…}`(라이트)와 `.dark {…}`(다크) 블록의 본문을 꺼낸다 */
const block = (sel) => { const i = css.indexOf(`\n${sel} {`); assert.ok(i >= 0, `${sel} 블록`); return css.slice(i, css.indexOf('\n}\n', i)); };
const token = (b, n) => { const m = new RegExp(`--${n}:\\s*(#[0-9A-Fa-f]{6})`).exec(b); assert.ok(m, `--${n}`); return m[1].toUpperCase(); };

test('다크 바탕·상태 토큰은 기존 남색 팔레트를 유지하고 조작 색은 상태 색과 분리한다', () => {
  /* 시안 팔레트(옛 dash.css 의 :root 변수). 옛 CSS 를 걷어낸 뒤에도 값이 바뀌지 않게 여기에 고정한다. */
  const PALETTE = { bg: '#0A1030', bg2: '#0E1740', pn: '#101A44', pn2: '#16225A', on: '#1B2A66', line: '#22305E', line2: '#3A4C8C', ink: '#E8EDFF', ink2: '#D6DEFA', sub: '#9AA8D6', mute: '#8FA0C8', acc: '#FF8A65', 'acc-ink': '#2A0E04', ok: '#4ADE9E', warn: '#FFC24D', bad: '#FF6B88' };
  const dark = block('.dark');
  const same = { background: 'bg', card: 'pn', secondary: 'pn2', muted: 'bg2', accent: 'on', border: 'line', foreground: 'ink', 'muted-foreground': 'sub', destructive: 'bad', ok: 'ok', warn: 'warn', bad: 'bad', ink2: 'ink2', mute: 'mute', line2: 'line2' };
  for (const [shadcn, ours] of Object.entries(same)) assert.equal(token(dark, shadcn), PALETTE[ours], `--${shadcn} = 시안 --${ours}`);
  assert.equal(token(dark, 'input'), PALETTE.line2);
  assert.equal(token(dark, 'ring'), token(dark, 'primary'));
  for (const state of ['ok', 'warn', 'bad']) assert.notEqual(token(dark, 'primary'), token(dark, state));
  assert.match(dark, /color-scheme: dark/);
});

test('라이트가 기본(:root)이고 같은 이름의 토큰을 모두 갖는다. 글자색은 카드·바탕 위에서 4.5:1 이상이다', () => {
  const light = block(':root'), dark = block('.dark');
  const names = (b) => [...b.matchAll(/--([a-z0-9-]+):/g)].map((m) => m[1]).filter((n) => n !== 'radius' && n !== 'page-bg');
  assert.deepEqual(names(light).sort(), names(dark).sort(), '라이트와 다크는 같은 토큰 이름을 정의한다');
  assert.match(light, /color-scheme: light/);
  const lum = (hex) => { const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const t = (n) => token(light, n);
  for (const [fg, bg] of [['foreground', 'card'], ['foreground', 'background'], ['muted-foreground', 'card'], ['muted-foreground', 'muted'], ['primary', 'card'], ['primary-foreground', 'primary'], ['ink2', 'card'], ['bad', 'card'], ['ok', 'card']]) {
    assert.ok(ratio(t(fg), t(bg)) >= 4.4, `${fg} 위 ${bg}: ${ratio(t(fg), t(bg)).toFixed(2)}`);
  }
  assert.ok(ratio(t('warn'), t('card')) >= 4.5, 'warn 글자');
});

/* ---------- 배색 개선(docs/product/화면-배색-개선-계획.md): 색은 의미 이름 한 곳에서, 글자 4.5:1 · 차트 면 3:1 ---------- */
const lum = (hex) => { const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
/* OKLCH 색상각(°): 색이 같은 계열인지 본다 */
const hue = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255).map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b), m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b), s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s, bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
  return (Math.atan2(bb, a) * 180 / Math.PI + 360) % 360;
};
const hueGap = (a, b) => { const d = Math.abs(hue(a) - hue(b)) % 360; return Math.min(d, 360 - d); };
const STAGES = ['plan', 'permit', 'build', 'sale', 'soon', 'move'];
const THEMES = [['라이트', () => block(':root')], ['다크', () => block('.dark')]];

test('6단계 색: 차트 면(--st-*)은 차트 바탕 위 3:1 이상, 글자(--st-*-ink)는 카드 위 4.5:1 이상. 다크 면은 글자보다 앞서지 않게 9.5:1 이하', () => {
  for (const [name, get] of THEMES) {
    const b = get(), t = (n) => token(b, n);
    for (const s of STAGES) {
      const fill = ratio(t(`st-${s}`), t('chartbg')), ink = ratio(t(`st-${s}-ink`), t('card'));
      assert.ok(fill >= 3, `${name} --st-${s} 차트 바탕 위 ${fill.toFixed(2)}:1`);
      assert.ok(ink >= 4.5, `${name} --st-${s}-ink 카드 위 ${ink.toFixed(2)}:1`);
      if (name === '다크') assert.ok(fill <= 9.5, `다크 --st-${s} ${fill.toFixed(2)}:1 은 너무 밝다`);
    }
    assert.ok(ratio(t('st-priv-ink'), t('card')) >= 4.5, `${name} --st-priv-ink`);
  }
});

/* 고치기 전 라이트는 1.5°(같은 색상), 다크 시안 원값은 19.8°였다. 다크 값은 그대로 두고 라이트를 다크만큼 떼어 놓는다 */
test('주의(--warn)는 착공(--st-build) 색과 색상각이 18° 이상 떨어진다 — 상태색과 단계색이 같은 계열로 읽히지 않게', () => {
  for (const [name, get] of THEMES) {
    const b = get();
    for (const s of ['st-build', 'st-build-ink']) { const g = hueGap(token(b, 'warn'), token(b, s)); assert.ok(g >= 18, `${name} warn↔${s} ${g.toFixed(1)}°`); }
  }
});

test('차트 축·보조 글자(--mute, 리본 축)는 카드·차트 바탕 위 4.5:1 이상이다', () => {
  for (const [name, get] of THEMES) {
    const b = get(), t = (n) => token(b, n);
    for (const fg of ['mute', 'rb-axis', 'rb-yr-off', 'rb-sc']) for (const bg of ['card', 'chartbg']) {
      const r = ratio(t(fg), t(bg)); assert.ok(r >= 4.5, `${name} --${fg} 위 --${bg}: ${r.toFixed(2)}`);
    }
  }
});

test('시행주체 색: 막대가 차트 바탕 위 3:1 이상이고, 공공 3주체(지자체·LH·주택업체)는 서로 색상각이 30° 이상 다르다', () => {
  for (const [name, get] of THEMES) {
    const b = get(), t = (n) => token(b, n);
    for (const a of ['local', 'lh', 'builder', 'private']) { const r = ratio(t(`actor-${a}`), t('chartbg')); assert.ok(r >= 3, `${name} --actor-${a} ${r.toFixed(2)}:1`); }
    const pub = ['local', 'lh', 'builder'];
    for (let i = 0; i < pub.length; i++) for (let j = i + 1; j < pub.length; j++) {
      const g = hueGap(t(`actor-${pub[i]}`), t(`actor-${pub[j]}`)); assert.ok(g >= 30, `${name} ${pub[i]}↔${pub[j]} ${g.toFixed(1)}°`);
    }
  }
});

test('6단계 공개 범위 색(--scope-gov·--scope-pub)은 카드 위 4.5:1, 옅은 면(14%) 위에서도 4.5:1 이상이다', () => {
  const mix = (fg, bg, a) => '#' + [1, 3, 5].map((i) => Math.round(parseInt(fg.slice(i, i + 2), 16) * a + parseInt(bg.slice(i, i + 2), 16) * (1 - a)).toString(16).padStart(2, '0')).join('');
  for (const [name, get] of THEMES) {
    const b = get(), t = (n) => token(b, n);
    for (const s of ['scope-gov', 'scope-pub']) {
      const card = ratio(t(s), t('card')), tint = ratio(t(s), mix(t(s), t('card'), 0.14));
      assert.ok(card >= 4.5 && tint >= 4.5, `${name} --${s} 카드 ${card.toFixed(2)} · 옅은 면 ${tint.toFixed(2)}`);
    }
  }
});

test('지연율 바탕색 6단계는 밝기가 한 방향으로 변하고(라이트는 짙어지고 다크는 밝아진다), 그 위 글자(본문·ink2)가 4.5:1 이상이다', () => {
  for (const [name, get] of THEMES) {
    const b = get(), t = (n) => token(b, n), L = [0, 1, 2, 3, 4, 5].map((i) => lum(t(`region-${i}`)));
    for (let i = 1; i < 6; i++) assert.ok(name === '라이트' ? L[i] < L[i - 1] : L[i] > L[i - 1], `${name} region-${i} 밝기 순서`);
    for (let i = 0; i < 6; i++) for (const fg of ['foreground', 'ink2']) { const r = ratio(t(fg), t(`region-${i}`)); assert.ok(r >= 4.5, `${name} --${fg} 위 region-${i}: ${r.toFixed(2)}`); }
  }
});

test('색 이름이 아니라 의미 이름을 쓴다: 옛 계열색(--s-blue…--s-amber)은 남아 있지 않고, 면 그림자는 테마 토큰이다', () => {
  const files = ['app/tailwind.css', 'components/board/Board.tsx', 'components/charts/palette.ts', 'lib/board/sample.ts'];
  for (const f of files) assert.doesNotMatch(read(f), /--s-(blue|teal|orange|gray|lime|violet|amber)\b/, f);
  for (const [, get] of THEMES) { const b = get(); assert.match(b, /--shadow-card:/); assert.match(b, /--shadow-pop:/); }
});

test('두 루트 레이아웃이 tailwind.css 를 가져온다: 대시보드는 라이트 기본(저장된 다크만 그리기 전에 켠다), 지도도 저장된 테마를 적용', () => {
  for (const f of ['app/(dashboard)/layout.tsx', 'app/(map)/layout.tsx']) assert.match(read(f), /import '\.\.\/tailwind\.css';/, f);
  const dash = read('app/(dashboard)/layout.tsx');
  assert.match(read('lib/shell/theme.ts'), /localStorage\.getItem\('theme'\)==='dark'/);
  assert.match(dash, /import \{ THEME_INIT \} from/);
  assert.doesNotMatch(dash, /className="dark"/, '대시보드는 기본이 라이트다');
  assert.match(read('app/(map)/layout.tsx'), /<html lang="ko" data-map-shell="" suppressHydrationWarning>/);
  assert.match(read('components/TopNav.tsx'), /localStorage\.setItem\('theme'/);
});

test('Tailwind 는 Turbopack 로더로 연결하고, shadcn 설정(components.json)이 우리 CSS 를 가리킨다', () => {
  assert.match(read('next.config.ts'), /'\*\.css': \{ loaders: \['@tailwindcss\/turbopack'\], as: '\*\.css' \}/);
  const c = JSON.parse(read('components.json'));
  assert.equal(c.tailwind.css, 'app/tailwind.css');
  assert.equal(c.tailwind.config, '', 'Tailwind v4 는 CSS 우선 설정이라 config 파일이 없다');
  assert.equal(c.aliases.ui, '@/components/ui');
  assert.deepEqual(JSON.parse(read('tsconfig.json')).compilerOptions.paths, { '@/*': ['./*'] });
});

test('의존성: 화면이 쓰는 것은 운영 의존성, shadcn CLI·Tailwind 는 개발 의존성(CLI 의 하위 패키지 취약점이 운영 트리에 들어가지 않게)', () => {
  for (const d of ['@base-ui/react', 'class-variance-authority', 'cn', 'lucide-react', 'tw-animate-css']) assert.ok(pkg.dependencies[d], `${d} 는 운영 의존성`);
  for (const d of ['tailwindcss', '@tailwindcss/turbopack', 'shadcn']) assert.ok(pkg.devDependencies[d], `${d} 는 개발 의존성`);
  assert.ok(!pkg.dependencies.shadcn, 'shadcn 은 CSS 한 줄(shadcn/tailwind.css)만 쓴다');
  for (const v of [...Object.values(pkg.dependencies), ...Object.values(pkg.devDependencies)]) assert.match(v, /^\d/, `정확한 버전으로 고정한다: ${v}`);
});
