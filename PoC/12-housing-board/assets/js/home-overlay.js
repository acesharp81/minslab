/* PoC 10 후보 근거를 원래 3D 공급 지도 위에 올린다. 점은 LH 블록 라벨 이름 대조 결과다. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else api.mount(root, root.document);
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const BASE = '/poc/housing-board';
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v) => Number(v).toLocaleString('ko-KR');
  const fc = (features) => ({ type: 'FeatureCollection', features });
  const located = (p) => p.locationRole === 'LH_PUBLIC_BLOCK_LABEL_POINT' && p.locationJoinStatus === 'NAME_MATCH_REVIEW'
    && Number.isFinite(p.longitude) && Number.isFinite(p.latitude);
  const pointFeatures = (projects) => fc(projects.filter(located).map((p) => ({ type: 'Feature',
    geometry: { type: 'Point', coordinates: [p.longitude, p.latitude] },
    properties: { id: p.id, name: p.name, region: p.region, municipality: p.municipality || '', stageCode: p.stageCode || '', plannedUnits: p.plannedUnits, locationRole: p.locationRole },
  })));
  const anchorFeatures = (projects) => {
    const anchors = new Map(), byId = new Map(projects.map((p) => [p.id, p]));
    pointFeatures(projects).features.forEach((feature) => {
      const project = byId.get(feature.properties.id);
      const key = project.locationAnchorId || feature.geometry.coordinates.join(',');
      if (anchors.has(key)) anchors.get(key).properties.candidateCount += 1;
      else anchors.set(key, { ...feature, properties: { ...feature.properties, anchorId: key, candidateCount: 1 } });
    });
    return fc([...anchors.values()]);
  };
  const detailUrl = (id) => `${BASE}/home-project/${encodeURIComponent(id)}`;
  function mount(win, doc) {
    const home = win.REGION && win.REGION.home, map = win.__housingMap;
    if (!home || !map) return;
    const $ = (id) => doc.getElementById(id);
    const rows = home.projects, points = pointFeatures(rows), byId = new Map(rows.map((p) => [p.id, p]));
    const native = win.__homeScene;
    const modelByCandidate = new Map([...(home.sites || []), ...(home.previewModels || [])].flatMap((site) => site.candidateIds.map((id) => [id, site])));
    const modelLabel = (p) => modelByCandidate.get(p.id)?.homeModelKind === 'OBSERVED_BUILDINGS' ? '공식 건물 형상 · 연결 검토'
      : located(p) ? '가상 아파트 모형 · 실제 설계 아님' : '위치 미확보 · 가상 3D 미리보기';
    const counts = new Map();
    rows.forEach((p) => counts.set(p.stageCode || '?', (counts.get(p.stageCode || '?') || 0) + 1));
    let active = 'all', query = '', popup = null;
    const colors = { '02': 'var(--plan)', '03': 'var(--sale)', '04': 'var(--build)' };
    const stages = [['01', '정책'], ['02', '사업화'], ['03', '인허가'], ['04', '건설'], ['05', '공급'], ['06', '입주']];
    const locatedCount = points.features.length;
    const blockCount = anchorFeatures(rows).features.length;
    let visibleRows = rows;
    const knownUnits = rows.filter((p) => Number.isFinite(p.plannedUnits));
    const showNotice = `${win.REGION.name}: 9·7 관련 검토 후보 ${fmt(rows.length)}건 · LH 블록 라벨점 검토 ${fmt(locatedCount)}건 · ${fmt(blockCount)}개 블록 · 단계 미확인 ${fmt(counts.get('?') || 0)}건. 위치점은 사업 경계가 아닙니다.`;
    $('pvBanner').textContent = home.isSchematicPreview ? '위치 미확보 · 실제 지도가 아닌 가상 아파트 미리보기입니다. 동수·층수·배치는 실제 설계가 아닙니다.' : showNotice + ' 아파트를 누르면 원본 3D 상세 카드가 열립니다. 가상 모형은 실제 설계가 아닙니다.';
    $('pvBanner').hidden = false;
    $('h-sum').textContent = '9·7 관련 검토 후보';
    $('h-sum').closest('section').hidden = false;
    $('prail').querySelector('[data-sec="h-sum"]').hidden = false;
    $('sumTotal').innerHTML = `<span class="big">${fmt(rows.length)}</span><span class="unit">건</span> <span class="cnt">위치 연결 ${fmt(locatedCount)}건(${fmt(blockCount)}개 블록) · 미연결 ${fmt(rows.length - locatedCount)}건</span>`;
    $('sumBar').innerHTML = [...counts].map(([stage, n]) => `<i style="width:${n / rows.length * 100}%;background:${colors[stage] || 'var(--mute)'}" title="${esc(stage)}단계 ${fmt(n)}건"></i>`).join('');
    $('sumBar').setAttribute('aria-label', `사업화 ${counts.get('02') || 0}건, 인허가 ${counts.get('03') || 0}건, 건설 ${counts.get('04') || 0}건, 단계 미확인 ${counts.get('?') || 0}건`);
    $('sumLeg').innerHTML = `<span>계획 규모 확인 ${fmt(knownUnits.length)}건 (중복 미조정)</span><span>위치 미연결 ${fmt(rows.length - locatedCount)}건 · 단계 미확인 ${fmt(counts.get('?') || 0)}건</span><a href="${BASE}/projects">전체 ${fmt(rows.length)}건 목록에서 찾기 →</a>`;
    $('hudSum').innerHTML = `<div class="hs-a"><div class="hs-total"><b>${fmt(rows.length)}건 후보</b><span class="hs-meta" title="PoC 10 사업후보 ${fmt(rows.length)}건"><span>위치 연결 ${fmt(locatedCount)}건</span></span></div><div class="sbar" role="img" aria-label="${esc($('sumBar').getAttribute('aria-label'))}">${$('sumBar').innerHTML}</div><div class="sleg"><span>계획 규모 확인 ${fmt(knownUnits.length)}건 · 호수 합산 제외</span></div></div>`;
    for (const id of ['h-next', 'h-tl']) { const section = $(id)?.closest('section'); if (section) section.hidden = true; const rail = $('prail')?.querySelector(`[data-sec="${id}"]`); if (rail) rail.hidden = true; }
    $('stageF').hidden = false;
    $('stageF').innerHTML = stages.map(([code, name]) => {
      const n = counts.get(code) || 0;
      return `<button type="button" class="sf" data-home-stage="${code}" style="--c:${colors[code] || 'var(--mute)'}" aria-pressed="${n > 0}"${n ? '' : ' disabled'}><span class="sf-h"><i class="sf-sw"></i>${code} ${name}<span class="sf-n">${n ? `${fmt(n)}건` : '없음'}</span></span><b class="sf-v">${fmt(n)}<small>후보</small></b></button>`;
    }).join('');
    $('stageF').addEventListener('click', (event) => {
      const button = event.target.closest('[data-home-stage]');
      if (!button || button.disabled) return;
      active = active === button.dataset.homeStage ? 'all' : button.dataset.homeStage;
      $('stageF').querySelectorAll('[data-home-stage]').forEach((b) => b.setAttribute('aria-pressed', String(active === 'all' ? !b.disabled : b.dataset.homeStage === active)));
      renderList();
    });
    $('h-proj').textContent = `사업후보 ${fmt(rows.length)}건 (위치 없는 후보 포함)`;
    $('h-proj').closest('section').hidden = false;
    $('prail').querySelector('[data-sec="h-proj"]').hidden = false;
    const search = doc.createElement('input');
    search.type = 'search'; search.id = 'homeProjectSearch'; search.placeholder = '9·7 후보 사업명·시군구·지구 검색';
    search.setAttribute('aria-label', 'PoC 10 사업후보 검색'); search.autocomplete = 'off';
    $('projList').before(search);
    const count = doc.createElement('p'); count.id = 'homeProjectCount'; count.className = 'home-count'; $('projList').before(count);
    search.addEventListener('input', () => { query = search.value.trim().toLocaleLowerCase('ko-KR'); renderList(); });
    function renderList() {
      const visible = rows.filter((p) => (active === 'all' || p.stageCode === active)
        && (!query || [p.name, p.municipality, p.district, p.block, p.sourceName].some((v) => String(v || '').toLocaleLowerCase('ko-KR').includes(query))));
      count.textContent = `${fmt(visible.length)}건 표시 · 위치점 ${fmt(visible.filter(located).length)}건`;
      $('projList').innerHTML = visible.map((p) => `<li class="home-row"><button type="button" class="card" data-home-id="${esc(p.id)}"><i class="sw ${p.stageCode === '04' ? 'build' : p.stageCode === '03' ? 'sale' : 'plan'}"></i><b>${esc(p.name)}</b><span class="st">${esc(p.stageLabel || '단계 미확인')}</span><span class="sub">${esc([p.municipality || p.region, p.district, p.block].filter(Boolean).join(' · '))}</span><span class="sub">계획 ${Number.isFinite(p.plannedUnits) ? fmt(p.plannedUnits) + '호' : '호수 미확보'} · ${located(p) ? 'LH 라벨점(검토)' : '위치 미연결'}</span><span class="sub">${esc(modelLabel(p))} · 3D 보기</span></button><a href="${detailUrl(p.id)}">근거·상세</a></li>`).join('') || '<li class="empty">조건에 맞는 사업후보가 없습니다.</li>';
      visibleRows = visible;
      if (native) native.filter(visible.map((p) => p.id));
      const source = map.getSource('home-candidates'); if (source) source.setData(anchorFeatures(visible));
    }
    function showProject(p) {
      if (!p) return;
      if (native?.focus(p.id)) return;
      if (modelByCandidate.has(p.id)) {
        win.location.assign(`${BASE}/map?region=home-907&homeProject=${encodeURIComponent(p.id)}`);
        return;
      }
      if (!located(p)) { win.location.assign(detailUrl(p.id)); return; }
      map.flyTo({ center: [p.longitude, p.latitude], zoom: 16.5, pitch: 58, duration: 750 });
    }
    function showAnchor(anchorId) {
      const members = visibleRows.filter((p) => located(p) && (p.locationAnchorId || [p.longitude, p.latitude].join(',')) === anchorId);
      if (!members.length) return;
      if (members.length === 1) { showProject(members[0]); return; }
      const p = members[0];
      map.flyTo({ center: [p.longitude, p.latitude], zoom: Math.max(map.getZoom(), 14.7), pitch: 55, duration: 750 });
      if (popup) popup.remove();
      popup = new win.maplibregl.Popup({ offset: 14, maxWidth: '310px' }).setLngLat([p.longitude, p.latitude])
        .setHTML(`<div class="home-popup"><b>같은 LH 블록 라벨점 · ${fmt(members.length)}개 후보</b><p>동일 사업 여부는 검토 중입니다.</p>${members.map((item) => `<p><a href="${detailUrl(item.id)}">${esc(item.name)}</a> · ${esc(item.stageLabel || '단계 미확인')}</p>`).join('')}</div>`).addTo(map);
    }
    $('projList').addEventListener('click', (event) => {
      const button = event.target.closest('[data-home-id]');
      if (button) showProject(byId.get(button.dataset.homeId));
    });
    function setupLayers() {
      if (home.isSchematicPreview) return;
      const addSource = (id, data) => { if (!map.getSource(id)) map.addSource(id, { type: 'geojson', data }); };
      const addLayer = (spec) => { if (!map.getLayer(spec.id)) map.addLayer(spec, map.getLayer('dong-3d') ? 'dong-3d' : undefined); };
      addSource('home-municipalities', home.municipalities);
      addSource('home-lands', home.lands);
      addSource('home-candidates', anchorFeatures(rows.filter((p) => active === 'all' || p.stageCode === active)));
      addLayer({ id: 'home-municipality-fill', type: 'fill', source: 'home-municipalities', paint: { 'fill-color': '#7BA7FF', 'fill-opacity': ['case', ['>', ['get', 'candidateCount'], 0], 0.055, 0] } });
      addLayer({ id: 'home-municipality-outline', type: 'line', source: 'home-municipalities', paint: { 'line-color': '#7BA7FF', 'line-opacity': 0.45, 'line-width': 1 } });
      addLayer({ id: 'home-land-fill', type: 'fill', source: 'home-lands', minzoom: 10.5, paint: { 'fill-color': '#A5E56D', 'fill-opacity': 0.14 } });
      addLayer({ id: 'home-land-outline', type: 'line', source: 'home-lands', minzoom: 10.5, paint: { 'line-color': '#A5E56D', 'line-opacity': 0.7, 'line-width': 1.5 } });
      if (!native?.blocks.length) addLayer({ id: 'home-candidate-halo', type: 'circle', source: 'home-candidates', paint: { 'circle-radius': 11, 'circle-color': '#101A44', 'circle-opacity': 0.85 } });
      if (!native?.blocks.length) addLayer({ id: 'home-candidate-point', type: 'circle', source: 'home-candidates', paint: { 'circle-radius': 6, 'circle-color': '#FF9F43', 'circle-stroke-color': '#fff', 'circle-stroke-width': 1.5 } });
    }
    map.on('style.load', setupLayers);
    if (map.isStyleLoaded()) setupLayers();
    map.on('click', 'home-candidate-point', (event) => {
      const anchorId = event.features && event.features[0] && event.features[0].properties.anchorId;
      showAnchor(anchorId);
    });
    map.on('mouseenter', 'home-candidate-point', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'home-candidate-point', () => { map.getCanvas().style.cursor = ''; });
    renderList();
    const selected = new URLSearchParams(win.location.search).get('homeProject') || home.previewProjectId;
    if (selected && byId.has(selected)) {
      const show = () => showProject(byId.get(selected));
      if (map.loaded()) show(); else map.once('load', show);
    }
    win.__homeOverlayStatus = { projects: rows.length, located: locatedCount, blocks: blockCount, original3DMap: true, layers: () => !!(map.getLayer('dong-3d') || map.getLayer('home-candidate-point')), models: native?.blocks.length || 0, preview: !!home.isSchematicPreview };
  }
  return { mount, located, pointFeatures, anchorFeatures };
});
