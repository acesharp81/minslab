'use strict';
/* 실재를 알 수 없는 도형은 솟지 않는 평면으로만 그리는가: app.js 정적 시험. 대상은 둘이다.
   ① src '정보없음'(높이·층수가 모두 없는 도형): V-World 건물 레이어에는 대장과 이어지지 않은 도형이 남아 있어 신도시(나주 혁신도시)에서 차로·공원 위에 놓인다(dataset.md 6.1).
   ② g=1(철거 의심): 신도시 지구 안에서 도로명주소 건물과 겹치지 않는 옛 건물(tools/regiontools/existence.py).
   세우면 '도로 위 건물'로 보이므로 입체·그림자·접지 음영에서 빼고, 팝업에서 실제와 다를 수 있음을 알린다. 동작은 브라우저 확인으로 본다 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');

const app = fs.readFileSync(path.join(__dirname, '..', '..', 'assets/js/app.js'), 'utf8');
const layerOf = (id) => { const m = new RegExp(`add\\(\\{ id: '${id}'[^\\n]*(?:\\n[^\\n]*)?`).exec(app); assert.ok(m, `${id} 층이 있어야 한다`); return m[0]; };

test('입체 층(벽·지붕·접지 음영)은 실재가 의심되지 않는 건물만 그리고, 평면 층은 정보없음·철거 의심(g=1) 도형만 그린다', () => {
  assert.match(app, /const KNOWN_H = \['all', \['!=', \['get', 'src'\], '정보없음'\], \['!=', \['get', 'g'\], 1\]\], NO_INFO = \['any', \['==', \['get', 'src'\], '정보없음'\], \['==', \['get', 'g'\], 1\]\]/);
  assert.match(app, /const isFlat = \(p\) => p\.src === '정보없음' \|\| p\.g === 1;/);
  for (const id of ['official-3d', 'official-roof', 'official-ao']) assert.match(layerOf(id), /filter: KNOWN_H/, `${id} 은 정보없음을 뺀다`);
  assert.match(layerOf('official-far'), /filter: \['all', \['>=', \['get', 'eh'\], 10\], KNOWN_H\]/);   // 저배율(확대 12~14) 층도 같다: 높이 10 m 이상 철거 의심 건물이 멀리서 솟던 구멍
  assert.match(app, /setFilter\('official-far', solid\(\['all', \['>=', \['get', 'eh'\], 10\], KNOWN_H\]\)\)/);   // 고르거나 흐리게를 바꿔 필터를 다시 걸어도 같다(applyOfficial)
  for (const id of ['official-flat', 'official-flat-line']) assert.match(layerOf(id), /filter: NO_INFO/, `${id} 은 정보없음만 그린다`);
  assert.match(layerOf('official-flat'), /type: 'fill'/);                       // 솟지 않는 면
  assert.match(layerOf('official-flat-line'), /'line-dasharray': \[2, 2\]/);    // 점선 윤곽
});

test('평면 층은 가장 아래(단지·지구 표시보다 먼저)에 깔려 신축 단지 용지를 가리지 않는다', () => {
  const at = (id) => app.indexOf(`add({ id: '${id}'`);
  assert.ok(at('official-flat') > 0 && at('official-flat') < at('district-mask'));
  assert.ok(at('official-flat-line') < at('blk-sale'));
});

test('그림자 판은 평면 도형(정보없음·철거 의심)을 만들지 않는다', () => {
  assert.match(app, /function officialShadowData\(\)[\s\S]*?if \(p\.eh < 3 \|\| isFlat\(p\)\) return;/);
});

test('고른 건물 표시: 입체 층 필터는 높이를 아는 건물을 지키면서 고른 건물을 빼고, 평면 도형은 얇은 판으로만 노랗게 칠한다', () => {
  assert.match(app, /notSel = selId == null \? null : \['!=', \['get', 'i'\], selId\]/);
  assert.match(app, /map\.setFilter\('official-3d', solid\(KNOWN_H\)\); map\.setFilter\('official-roof', solid\(KNOWN_H\)\)/);
  assert.match(app, /for \(const id of \['official-flat', 'official-flat-line'\]\) if \(map\.getLayer\(id\)\) map\.setFilter\(id, solid\(NO_INFO\)\)/);
  assert.match(app, /function applySel\(\) \{[\s\S]*?applyOfficial\(\);/);
  assert.match(app, /eh: isFlat\(sp\) \? FLAT_SEL_H : sp\.eh/);
  assert.match(app, /const FLAT_SEL_H = 0\.3;/);
});

test('평면 도형도 눌러 카드를 열 수 있고(맨 마지막 순위), 포인터 모양이 바뀐다', () => {
  assert.match(app, /pick\(\['official-3d', 'official-roof', 'official-far'\]\) \|\| pick\(\['official-flat'\]\) \|\| pick\(\['official-hit'\]\)/);
  assert.match(app, /\.\.\.OFFICIAL_LAYERS, 'official-flat', 'official-hit'\]/);
  assert.ok(!/const OFFICIAL_LAYERS = \[[^\]]*official-(flat|outline|hit)/.test(app), 'OFFICIAL_LAYERS 는 fill-extrusion 층만 담는다');
});

test('카드: 정보 없는 도형은 "건물 정보 없음" 제목·실제와 다를 수 있다는 안내를 보이고, 비어 있는 줄을 늘어놓지 않으며, 카드 위치 계산에 높이를 주지 않는다', () => {
  assert.match(app, /const none = p\.src === '정보없음';/);
  assert.match(app, /p\.n \? esc\(p\.n\) : none \? '건물 정보 없음' : '이름 없는 건물'/);
  assert.match(app, /건축물대장과 이어지는 정보가 없는 도형입니다\. 실제와 다를 수 있어/);
  assert.match(app, /chipHtml\('none', '정보 없음'\)/);
  assert.match(app, /\$\{rows\.length \? dlHtml\(rows\) : ''\}/);
  assert.match(app, /ringsOf\(geom\), none \|\| gone \? 0 : p\.eh, clickX\)/);
  assert.ok(!/3 m 평면으로 표시\(실제 높이 아님\)/.test(app), '3 m 건물로 세운다는 옛 안내가 남지 않는다');
});

test('카드: 철거 의심(g=1) 건물은 "현존 미확인" 칩과 도로명주소 건물과 겹치지 않는다는 안내를 보이되, 옛 대장 값(층수·용도·연도)은 그대로 보인다', () => {
  assert.match(app, /const gone = !none && p\.g === 1;/);
  assert.match(app, /if \(gone\) chip = chipHtml\('none', '현존 미확인'\);/);
  assert.match(app, /지금 있는 건물\(도로명주소 건물\)과 겹치지 않습니다\. 신도시를 만들며 철거된 옛 건물일 수 있어 입체로 그리지 않았습니다/);
  assert.match(app, /const rows = none \? \[/);   // 값이 있는 줄만 줄이는 것은 정보없음뿐이다(철거 의심은 전체 줄을 보인다)
});
