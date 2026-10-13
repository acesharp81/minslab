// 우측 사이드바: 처음엔 접힌 채 열리고(데스크톱, 2026-10-10 피드백 — 문서 5.6c '기본 접힘'), 접어도 요약이 지도 위에 남고, 작은 글자·긴 목록 없이 읽히는지 정적으로 확인한다.
// 화면에서의 실제 겹침·높이는 별도 헤드리스 Chrome 점검으로 본다(문서 5.5·5.6c).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const html = read('index.html'), css = read('assets/css/app.css'), app = read('assets/js/app.js');

// 규칙 본문 찾기: 선택자 목록(쉼표)에 sel 이 정확히 들어 있는 규칙을 모두 돌려준다(@media 안 규칙 포함).
function bodies(sel) {
  const out = [];
  for (const m of css.matchAll(/([^{}]+)\{([^{}]*)\}/g)) {
    if (m[1].split(',').map((s) => s.trim()).includes(sel)) out.push(m[2]);
  }
  return out;
}
const fontPx = (sel) => {
  const sizes = bodies(sel).map((b) => /font-size:([\d.]+)px/.exec(b)).filter(Boolean).map((m) => +m[1]);
  assert.ok(sizes.length, `${sel} 에 font-size(px) 규칙이 있어야 한다`);
  return sizes;
};

test('데스크톱은 처음부터 접힌 채 그린다(마크업이 접힘이어야 지도 폭이 한 번 더 바뀌지 않는다)', () => {
  assert.match(html, /<div class="app collapsed">/);
  const t = /<button[^>]*id="panelToggle"[^>]*>(.)/.exec(html);
  assert.ok(t, '#panelToggle 이 있어야 한다');
  assert.match(t[0], /aria-expanded="false"/);
  assert.match(t[0], /aria-label="사이드바 펼치기"/);
  assert.match(html, /id="panelToggle"[^>]*><span aria-hidden="true">‹<\/span>/);
  assert.match(css, /@media \(min-width:901px\)\{\.app\.collapsed \.panel\{display:none\}\}/);
});

test('주소 ?panel=1 이면 펼친 채 열고, 접고 펼 때마다 주소에 반영한다(기억 저장은 쓰지 않는다)', () => {
  assert.match(app, /setCollapsed\(!REG\.home && q\.get\('panel'\) !== '1', \{ quiet: true \}\)/);   // 9·7 후보 지도는 목록 패널을 기본으로 펼침
  assert.match(app, /set\('panel', \$\('\.app'\)\.classList\.contains\('collapsed'\) \? '' : '1'\)/);
  assert.doesNotMatch(app, /localStorage[^;]*panel/i);
  // 시작할 때 알림을 읽어 주지 않는다(조용히 적용)
  assert.match(app, /function setCollapsed\(on, \{ quiet = false \} = \{\}\)/);
});

test('공급 요약은 머리 줄에 늘 있어 사이드바를 접어도 보이고, 지역 이름·바꾸기는 머리 줄 왼쪽에 있다(요약에 지역 선택을 두지 않는다)', () => {
  const head = /<header class="mhead" id="mhead">[\s\S]*?<\/header>/.exec(html)[0];
  assert.match(head, /id="regionSel"/); assert.match(head, /<div class="hudsum" id="hudSum" role="group" aria-label="공급 요약"><\/div>/);
  assert.doesNotMatch(app, /hs-region|hudRegion|\$\('#hudSum'\)\.hidden/);
  assert.doesNotMatch(css, /\.hudsum \.hs-region/);
});

test('사이드바 글자는 13px 아래로 내려가지 않는다', () => {
  const SEL = ['.pcur', '.sleg', '.card .st', '.card .sub', '.stage span', '.stage span small', '.pg', '.fl em', '.bld', '.foot',
    '.next span.s', '.inote', '.isub h3', '.icard .iw', '.im', '.ichip', '.imeta', '.isrc', '.ibtn .s',
    '#infraMeasures small', '.isum-go', '.ihead b', '.ibtn b'];
  for (const s of SEL) for (const px of fontPx(s)) assert.ok(px >= 13, `${s} ${px}px (13px 이상 필요)`);
});

test('데스크톱 사이드바 글자는 한 단계 작게(2026-10-10 피드백 "글씨가 너무 크다", 문서 5.6c): 구역 제목 16px ≥ 단지 이름 15.5px, 보조 글자 13px, 폭 380px', () => {
  const desk = /\/\* 데스크톱 가독성[\s\S]*?\n\}\n/.exec(css)[0];
  const deskPx = (sel) => [...desk.matchAll(/([^{}]+)\{([^{}]*)\}/g)].filter((m) => m[1].split(',').map((x) => x.trim()).includes(sel)).map((m) => /font-size:([\d.]+)px/.exec(m[2])).filter(Boolean).map((m) => +m[1]);
  const only = (sel, px) => { const v = deskPx(sel); assert.ok(v.length && v.every((x) => x === px), `${sel} ${v} (모두 ${px}px)`); };
  only('h2', 16); only('.card b', 15.5); only('h1', 18);   // 구역 제목 16px ≥ 단지 이름 15.5px
  for (const sel of ['.card .sub', '.card .st', '.next span.s', '.sleg', '.stage span', '.foot', '.inote', '.pcur', '.sum .cnt']) only(sel, 13);
  only('.next b', 14.5); only('.sum b', 15);
  assert.ok(fontPx('.sum .big').every((x) => x <= 32), `합계 숫자 ${fontPx('.sum .big')}px (32px 이하)`);
  assert.match(css, /grid-template-columns:minmax\(0,1fr\) 380px/);
  assert.doesNotMatch(css, /grid-template-columns:minmax\(0,1fr\) 420px/);
});

test('사이드바 보조 글자에 옅은 회색(#5C6068·#6B6F77)을 쓰지 않는다', () => {
  for (const s of ['.stage span', '.fl em', '.im.info', '.im.none']) {
    const colors = bodies(s).map((b) => /(?:^|;)color:(#[0-9A-Fa-f]{6})/.exec(b)).filter(Boolean).map((m) => m[1].toUpperCase());
    for (const c of colors) assert.ok(!['#5C6068', '#6B6F77'].includes(c), `${s} 색 ${c}`);
  }
});

test('입주 전 점검: 단지 카드는 제목 한 줄 + 주의(▲) 줄만 두고, 펼침·참고 줄은 없다', () => {
  assert.match(app, /class="iw"/);
  assert.match(app, /r\.level === 'warn'/);
  assert.doesNotMatch(app, /class="imore"|class="irow|class="igrp|icollapse/);
  assert.doesNotMatch(css, /\.irow|\.igrp|\.imore|\.icollapse/);
  const m = /\$\('#infraList'\)\.addEventListener\('click'[^\n]*\n/.exec(app);
  assert.ok(m && !/aria-expanded/.test(m[0]), '#infraList 클릭은 지도 이동만 한다');
});

test('서술 문장 요약: 안내 문단·인허가 목록을 두지 않고, 기준일은 출처 상자로 옮겼다', () => {
  assert.doesNotMatch(html, /id="infraIntro"|id="infraPermits/);
  assert.doesNotMatch(app, /infraIntro|infraPermits|공개 자료로 점검합니다/);
  assert.match(app, /\$\('#infraSrc'\)\.textContent = `기준 \$\{INFRA\.asOf\}\. 출처: /);
  // 타임라인 설명은 두 문장 이내(막대 안 '새 학교 없는 기간 N개월'과 겹치는 문장은 뺀다)
  const note = /\$\('#infraTlNote'\)\.textContent = t\.gap\s*\? `([^`]*)`\s*: '([^']*)'/.exec(app);
  assert.ok(note, '#infraTlNote 문구를 찾을 수 없음');
  assert.ok(note[1].split(/[.]\s/).length <= 2 && note[1].length <= 80, `타임라인 설명이 길다: ${note[1].length}자`);
  assert.doesNotMatch(note[1], /개월 동안은 새 학교가 없습니다/);
});

test('개교 일정은 일정이 공시된 학교만 늘어놓고, 부지만 있는 곳은 개수로만 알린다', () => {
  assert.match(app, /sched = schools\.filter\(\(s\) => s\.status === '신설예정'\)/);
  assert.match(app, /일정 미공시 부지 \$\{sites\}곳\(지도에 표시\)/);
  assert.doesNotMatch(app, /일정 미공시<\/span>/);
});

test('계획·대책 상세는 두 줄까지만 보이고 출처 줄은 한 줄로 줄인다', () => {
  assert.match(bodies('#infraMeasures small').join(';'), /-webkit-line-clamp:2/);
  const b = bodies('.isrc').join(';');
  assert.match(b, /white-space:nowrap/); assert.match(b, /text-overflow:ellipsis/);
});

test('푸터: 건물 출처·기준일 한 줄만 보이고 윤곽·공정율·출처 설명은 접힌다(자료 안내)', () => {
  const region = fs.readFileSync(path.join(ROOT, 'assets/js/region.js'), 'utf8');
  assert.match(region, /<details class="fnote"><summary>자료 안내<\/summary>/);
  assert.match(html, /<div class="foot">/);          // <p> 안에 <details> 를 넣지 않는다
  assert.ok(bodies('.foot summary').length);
});

test('입주 전 점검: 구역 전체가 기본 접힘이고, 안의 개교 일정·계획·출처도 접이식이다', () => {
  const btn = /<button[^>]*id="infraToggle"[^>]*>/.exec(html);
  assert.ok(btn, '#infraToggle(구역 제목 단추)이 있어야 한다');
  assert.match(btn[0], /aria-expanded="false"/);
  assert.match(btn[0], /aria-controls="infraBody"/);
  assert.match(html, /<h2 id="h-infra"><button/);                      // 구역 제목(h2)이 곧 단추라 고정 제목·레일 코드는 그대로 쓴다
  assert.match(html, /<div class="sbody" id="infraBody" hidden>/);
  for (const id of ['infraSchoolsBox', 'infraMeasuresBox']) assert.match(html, new RegExp(`<details class="isub" id="${id}" hidden>`));   // open 없음
  assert.match(html, /<details class="isub" id="infraSrcBox">/);
  assert.match(css, /\.isub>summary/);
  assert.match(css, /\.sbody\[hidden\]\{display:none\}/);        // flex 가 hidden 을 덮지 않게
  // 열리는 길 셋: 구역 제목, 요약의 '기반시설 보기', 보기 기준의 '기반시설'(openInfra), 오른쪽 레일
  assert.match(app, /function setInfraOpen\(open\)/);
  assert.match(app, /\$\('#infraToggle'\)\.addEventListener\('click'/);
  assert.match(app, /function openInfra\(\)[\s\S]*?setInfraOpen\(true\)/);
  assert.match(app, /dataset\.sec === 'h-infra'\) setInfraOpen\(true\)/);
});

test('사이드바 글은 어절 단위로 줄을 바꾼다(keep-all + overflow-wrap) / 지역 상자는 머리 줄(#mhead)에 있다', () => {
  const b = bodies('.pscroll').join(';');
  assert.match(b, /word-break:keep-all/);
  assert.match(b, /overflow-wrap:break-word/);
  const head = /<header class="mhead" id="mhead">[\s\S]*?<\/header>/.exec(html);
  assert.ok(head && /id="regionBox"/.test(head[0]) && /id="regionSel"/.test(head[0]), '지역 고르기는 머리 줄 안에 있어야 한다');
  assert.doesNotMatch(/<aside class="panel"[\s\S]*?<\/aside>/.exec(html)[0], /id="regionBox"/);
});

test('입주 전 점검 카드에 같은 안내 문구를 되풀이하지 않는다', () => {
  assert.doesNotMatch(app, /누르면 지도에서 보기<\/span><span class="irows">/);
});

test('타임라인 글자에는 바탕색 후광을 둬 띠·축 위에서도 읽힌다', () => {
  assert.match(css, /\.itl text\{[^}]*paint-order:stroke/);
});
