/* 번들 유무(등급 A) 조회: regions/ 번들에서 시군구 코드 → 번들. /api/v1/resolve 의 coverage 와 /api/v1/codes/search 의 tier 가 같은 표를 쓴다.
   시험: tests/js/resolve.test.cjs */
'use strict';
const fs = require('fs');
const path = require('path');

/* regions/ 번들에서 시군구 코드 → 번들 {slug, name, updatedAt, visibility}. 번들이 없으면 빈 표.
   production 이면 visibility 가 preview 인 지역은 뺀다(운영 빌드가 그 지역을 배포에서 빼므로, 해석 결과가 열 수 없는 지역을 가리키지 않게) */
function readCoverage(root = path.join(require('./root.js').ROOT, 'regions'), production = false) {
  const map = {};
  try {
    const index = JSON.parse(fs.readFileSync(/*turbopackIgnore: true*/ path.join(root, 'index.json'), 'utf8'));
    for (const r of index.regions || []) {
      if (production && r.visibility === 'preview') continue;
      try {
        const region = JSON.parse(fs.readFileSync(/*turbopackIgnore: true*/ path.join(root, r.slug, 'region.json'), 'utf8'));
        for (const c of region.codes || []) if (c.type === 'sigungu') map[c.code] = { slug: r.slug, name: r.name, updatedAt: r.updatedAt, visibility: r.visibility || 'public' };
      } catch (e) { /* 이 지역은 건너뜀 */ }
    }
  } catch (e) { /* index 없음 */ }
  return map;
}

module.exports = { readCoverage };
