'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const R = require('../../assets/js/region.js');
const read = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, '../../data/home10', name), 'utf8'));
const scene = read('scene.json'), data = read('map.json');
const index = { policyOnly: 'POL_2025_0907', homeDefault: 'home-907', regions: [] };

test('모든 HOME 후보는 정확히 하나의 3D 모형에 연결되고 원천 좌표·호수는 보존된다', () => {
  const ids = [...scene.sites, ...scene.previews].flatMap((s) => s.candidateIds);
  assert.deepEqual(ids.sort(), data.projects.map((p) => p.id).sort());
  assert.equal(new Set(ids).size, data.projects.length);
  assert.equal(scene.candidateSnapshotAt, data.readFinishedAt);
  assert.equal(scene.sites.length, 61);
  assert.equal(scene.previews.length, 66);
  for (const site of [...scene.sites, ...scene.previews]) {
    const original = data.projects.find((p) => p.id === site.primaryCandidateId);
    assert.equal(site.units, original.plannedUnits);
    assert.ok(site.dongs.length > 0, site.id);
    if (site.homeLocationMode !== 'UNLOCATED_PREVIEW') assert.deepEqual(site.center, [original.longitude, original.latitude]);
    for (const dong of site.dongs) {
      assert.ok(dong.heightM > 0 && dong.floorsAbove > 0);
      for (const ring of dong.poly) assert.ok(ring.length >= 3 && ring.every((p) => p.length === 2 && p.every(Number.isFinite)));
    }
  }
});

test('사업 동일성이 미확인인 기존 건물은 후보로 쓰지 않고 가상 모형을 원본 렌더러에 전달한다', () => {
  const page = R.homeBundle(data, index, 'home-907', scene);
  assert.equal(page.GY_PROJECTS.blocks.length, 61);
  assert.equal(page.blocks.reduce((n, b) => n + b.dongs.length, 0), 479);
  assert.equal(page.view.pitch, 58);
  assert.ok(page.view.zoom >= 15);
  const real = page.blocks.filter((b) => b.homeModelKind === 'OBSERVED_BUILDINGS');
  assert.equal(real.length, 0);
  assert.ok(page.GY_BUILDINGS.features.some((f) => f.properties.n?.includes('통보8차')), '기존 아파트는 주변 건물로 남긴다');
  for (const b of page.blocks.filter((b) => b.homeModelKind === 'SCHEMATIC')) {
    assert.match(b.note, /실제 설계가 아닙니다/);
    assert.ok(b.dongs.every((d) => d.tier === 'schematic'));
  }
});

test('위치 없는 후보는 지도 좌표를 만들지 않고 단일 모형·배경 없는 미리보기로 연다', async () => {
  const unknown = data.projects.find((p) => p.longitude == null);
  const files = { 'regions/index.json': index, 'home10/map.json': data, 'home10/scene.json': scene };
  const page = await R.loadRegion({ search: `?region=home-907&homeProject=${unknown.id}`,
    fetch: async (url) => ({ ok: true, json: async () => files[url] }) });
  assert.equal(page.home.isSchematicPreview, true);
  assert.equal(page.blocks.length, 1);
  assert.deepEqual(page.blocks[0].candidateIds, [unknown.id]);
  assert.deepEqual(page.view.center, [0, 0]);
  assert.equal(page.GY_BUILDINGS.features.length, 0);
  assert.equal(page.GY_BUILDINGS.dynamic, false);
  assert.equal(unknown.latitude, null);
  assert.equal(unknown.longitude, null);
  assert.match(page.blocks[0].note, /위치 미확보/);
  const seoul = R.homeBundle(data, index, 'home-907-seoul', scene);
  assert.equal(seoul.home.projects.length, 10);
  assert.equal(seoul.home.isSchematicPreview, true);
});

test('선택한 후보로 카메라가 시작하고 지역 밖 후보 모형은 유입되지 않는다', () => {
  const selected = scene.sites.find((s) => s.homeModelKind === 'SCHEMATIC');
  const page = R.homeBundle(data, index, 'home-907-gyeonggi', scene, selected.primaryCandidateId);
  assert.deepEqual(page.view.center, selected.center);
  const allowed = new Set(page.home.projects.map((p) => p.id));
  assert.ok(page.blocks.every((b) => b.candidateIds.every((id) => allowed.has(id))));
});
