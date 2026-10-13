'use client';
/* 기존 index.html 의 로더와 같은 순서로 지도 스크립트를 불러온다:
   로딩 화면 진행(loadview) → 지도 라이브러리·어댑터·기반시설 점검·시설 분류·버스 → 지역 자료 읽기(어댑터가 전역을 채움) → 키 파일 → 앱 → 주소 이동 입력줄(없어도 지도는 열린다).
   스크립트·지역 자료를 받는 대로 로딩 화면(LoadView)에 알린다. 지도가 생긴 뒤의 타일은 app.js 가 알린다.
   app.js 는 최상위 const 를 선언하는 스크립트라 문서당 한 번만 돌아야 한다. 개발 모드의 효과 이중 실행은 플래그로 막는다. */
import { useEffect } from 'react';

type LoadCtl = { want: (a: string, k: string) => void; got: (a: string, k: string) => void; finish: (a: string) => void; trackFetch: (w: Window) => () => void };
type W = Window & {
  __mapBooted?: boolean;
  __housingMap?: unknown;
  LoadView?: { ctl: () => LoadCtl };
  RegionLoader?: { boot: (w: Window, d: Document) => Promise<{ ok?: boolean } | null> };
  GotoBar?: { mount: (w: Window, d: Document) => void };
  REGION?: { home?: unknown };
};

const BASE = '/poc/housing-board';
const LOADVIEW = `${BASE}/assets/js/loadview.js`;
const LIBS = [`${BASE}/assets/vendor/maplibre-gl/5.24.0/maplibre-gl.js`, `${BASE}/assets/js/region.js`, `${BASE}/assets/js/infra.js`, `${BASE}/assets/js/facility.js`, `${BASE}/assets/js/bus.js`];
const CONFIG = `${BASE}/config.js`, APP = `${BASE}/assets/js/app.js`, HOME_OVERLAY = `${BASE}/assets/js/home-overlay.js`;

function load(src: string) {
  return new Promise<void>((ok, no) => {
    const s = document.createElement('script');
    s.src = src; s.async = false; s.onload = () => ok(); s.onerror = () => no(new Error(src));
    document.body.appendChild(s);
  });
}

export default function MapIsland() {
  useEffect(() => {
    const w = window as W;
    if (w.__mapBooted) return;
    w.__mapBooted = true;
    const fatal = (e: Error) => {
      const f = document.getElementById('fatal'), l = document.getElementById('loading');
      if (l) l.hidden = true;
      if (f) {
        f.hidden = false; f.textContent = '화면을 준비하지 못했습니다: ' + e.message + ' ';
        const link = document.createElement('a'); link.href = `${BASE}/projects`; link.textContent = '9·7 사업후보 전체 목록 보기'; f.appendChild(link);
      }
    };
    const url = new URL(w.location.href);
    const permitted = new Set(['home-907', 'home-907-seoul', 'home-907-gyeonggi']);
    const selected = url.searchParams.get('region');
    const project = url.searchParams.get('homeProject');
    url.search = '';
    url.searchParams.set('region', permitted.has(selected || '') ? selected! : 'home-907');
    if (project) url.searchParams.set('homeProject', project);
    if (url.href !== w.location.href) w.history.replaceState(null, '', url);
    let lv: LoadCtl | null = null;
    const step = (src: string) => () => { if (lv) lv.got('code', src); };
    load(LOADVIEW).catch(() => {})
      .then(() => {
        lv = w.LoadView ? w.LoadView.ctl() : null;
        if (lv) [...LIBS, CONFIG, APP, HOME_OVERLAY].forEach((s) => lv!.want('code', s));
        return Promise.all(LIBS.map((s) => load(s).then(step(s))));
      })
      .then(async () => {
        const restore = lv ? lv.trackFetch(window) : () => {};
        return w.RegionLoader!.boot(window, document).finally(() => { restore(); if (lv) lv.finish('data'); });
      })
      .then((r) => {
        if (!r || !r.ok) return null;
        return load(CONFIG).catch(() => {}).then(step(CONFIG)).then(() => load(APP)).then(() => { if (w.REGION?.home && !w.__housingMap) throw new Error('3D 지도를 시작하지 못했습니다.'); }).then(step(APP)).then(() => { if (lv) lv.finish('code'); })
          .then(() => w.REGION?.home ? load(HOME_OVERLAY).then(step(HOME_OVERLAY)) : step(HOME_OVERLAY)());
      })
      .catch(fatal);
  }, []);
  return null;
}
