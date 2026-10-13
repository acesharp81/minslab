'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const H = require('../../assets/js/home-overlay.js');
const RegionLoader = require('../../assets/js/region.js');
const root = path.join(__dirname, '../..');
const mapData = JSON.parse(fs.readFileSync(path.join(root, 'data/home10/map.json'), 'utf8'));

test('9·7 지도는 다른 정책 후보와 미확인 용지 도형을 싣지 않는다', () => {
  assert.equal(mapData.projects.length, 152);
  assert.ok(mapData.projects.every((p) => p.policyId === 'POL_2025_0907' && p.projectProgramStatus === 'REVIEW'));
  assert.equal(mapData.housingLands.features.length, 0);
  const all = RegionLoader.homeScope(mapData, 'home-907');
  const seoul = RegionLoader.homeScope(mapData, 'home-907-seoul');
  const gyeonggi = RegionLoader.homeScope(mapData, 'home-907-gyeonggi');
  assert.equal(all.projects.length, 152);
  assert.equal(seoul.projects.length, 10);
  assert.equal(gyeonggi.projects.length, 142);
  assert.equal(H.pointFeatures(all.projects).features.length, 86);
  assert.equal(H.anchorFeatures(all.projects).features.length, 61);
  assert.equal(H.pointFeatures(seoul.projects).features.length, 0);
});

test('9·7 지도는 근거 없는 후보에 위치점을 만들지 않는다', () => {
  const sample = { id: 'PRO_sample', region: '서울특별시', name: '위치 미확보', longitude: null, latitude: null, locationRole: null };
  assert.equal(H.pointFeatures([sample]).features.length, 0);
  assert.equal(H.located(sample), false);
});

test('9·7 전용 색인은 기존 예시 지역 요청에도 9·7 후보만 반환한다', async () => {
  const files = { 'regions/index.json': { policyOnly: 'POL_2025_0907', homeDefault: 'home-907', regions: [] }, 'home10/map.json': mapData };
  const fetch = async (url) => ({ ok: url in files, status: url in files ? 200 : 404, json: async () => files[url] });
  for (const search of ['', '?region=home-all', '?region=incheon-gyeyang']) {
    const page = await RegionLoader.loadRegion({ fetch, search });
    assert.equal(page.slug, 'home-907');
    assert.equal(page.home.projects.length, 152);
    assert.equal(page.view.pitch, 52);
    assert.match(page.regions.find((r) => r.slug === 'home-907').name, /152건 · 위치 61곳/);
    assert.match(page.regions.find((r) => r.slug === 'home-907-seoul').name, /10건 · 위치 0곳/);
  }
});
