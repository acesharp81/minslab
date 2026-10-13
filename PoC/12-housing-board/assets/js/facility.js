/* 기존 건물 중 기반시설(학교·병원·공공·복지)을 가려내는 순수 함수. DOM 은 만지지 않는다(node --test 로 시험: tests/js/facility.test.cjs).
   입력은 V-World 건물 속성(n 이름, u 용도, eh 높이, d 법정동). 용도만으로는 틀리는 일이 많아(교육연구시설에 빌딩·아파트, 노유자시설에 상가)
   '이름의 키워드'를 먼저 보고, 이름이 없거나 일반명(가동·16동)일 때만 용도를 따른다. 상가·아파트 계열 이름은 용도 신호를 무시한다. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FacilityLib = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const NAMES = { edu: '교육시설', med: '의료시설', pub: '공공·복지시설' };
  const RE_MED = /병원|의원|보건소|보건지소|치과|한의원/;
  const RE_EDU = /학교|대학|유치원|어린이집|교육청|교육지원/;
  const RE_PUB = /구청|시청|군청|청사|주민센터|행정복지센터|주민자치센터|동사무소|경찰|파출소|지구대|소방서|우체국|복지관|복지회관|경로당|노인|문화센터|문화회관|체육센|체육관|청소년|수련관|여성회관|요양원|쉼터|사랑터|도서관|보건|수도사업소/;
  const RE_SHOP = /빌딩|아파트|APT|오피스텔|프라자|플라자|타워|\(주\)|주식회사|상가|팰리스|하이츠|빌라|리츠|교회|성당|농협|새마을금고/;   // 상가·주거·종교·농협 창고
  const RE_STRONG = /병원|학교|대학교|유치원|어린이집|구청|주민센터|행정복지센터|경찰서|소방서|우체국/;                           // 상가식 이름이 섞여도 믿는 키워드
  const RE_BARE = /^[0-9가-힣A-Za-z]{0,3}동$|주건축물|부속/;                                                              // '가동'·'16동'·'주건축물제1동' 같은 일반명
  const USE_MED = /^의료/, USE_EDU = /^교육연구/, USE_PUB = /^(공공|노유자)/;

  /* 'edu' | 'med' | 'pub' | null */
  function classify(p) {
    if (!p) return null;
    const n = String(p.n || '').trim(), u = String(p.u || '');
    if (n && !RE_BARE.test(n)) {
      const hit = RE_MED.test(n) ? 'med' : RE_EDU.test(n) ? 'edu' : RE_PUB.test(n) ? 'pub' : null;
      if (hit) return RE_SHOP.test(n) && !RE_STRONG.test(n) ? null : hit;
      if (RE_SHOP.test(n)) return null;
    }
    if (USE_MED.test(u)) return 'med';
    if (USE_EDU.test(u)) return 'edu';
    if (USE_PUB.test(u)) return 'pub';
    return null;
  }

  /* 지도에 적을 이름: 끝의 괄호·'주건축물N동'을 덜어 낸다 */
  const labelOf = (n) => String(n || '').replace(/\s*\([^)]*\)\s*$/, '').replace(/\s*주건축물\s*제?\d*동?$/, '').trim();

  const ring = (g) => (!g ? null : g.type === 'Polygon' ? g.coordinates[0] : g.type === 'MultiPolygon' ? g.coordinates[0][0] : null);
  const centroid = (r) => [r.reduce((a, q) => a + q[0], 0) / r.length, r.reduce((a, q) => a + q[1], 0) / r.length];

  /* 이름 있는 기반시설마다 라벨 한 점. 같은 이름·같은 동(d)은 가장 높은 한 동에만 붙여 경인교대 20동처럼 같은 글자가 쏟아지지 않게 한다.
     features 는 GeoJSON 건물 목록이고, 각 속성에 fc(분류)를 남긴다(그리는 쪽이 색·팝업에 쓴다). */
  function annotate(features) {
    const best = new Map(), count = { edu: 0, med: 0, pub: 0 };
    for (const f of features || []) {
      const p = f.properties || {}, cat = classify(p);
      if (!cat) { delete p.fc; continue; }
      p.fc = cat; count[cat]++;
      const name = labelOf(p.n);
      if (!name || RE_BARE.test(name)) continue;
      const key = `${name}|${p.d || ''}`, cur = best.get(key);
      if (!cur || (p.eh || 0) > (cur.eh || 0)) best.set(key, { f, name, cat, eh: p.eh || 0 });
    }
    const pts = [];
    for (const { f, name, cat, eh } of best.values()) {
      const r = ring(f.geometry); if (!r || !r.length) continue;
      pts.push({ type: 'Feature', properties: { n: name, cat, eh }, geometry: { type: 'Point', coordinates: centroid(r) } });
    }
    return { count, points: { type: 'FeatureCollection', features: pts } };
  }

  return { NAMES, classify, labelOf, annotate };
});
