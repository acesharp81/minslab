#!/usr/bin/env node
/* 화면 비교용 스크린샷 촬영(개발 도구). 같은 주소·해상도·상호작용 상태를 찍어 두 번의 결과를 scripts/visual/diff.mjs 로 픽셀 비교한다.
   Tailwind·shadcn 전환(2026-10-09 결정: 픽셀 완전 동일)에서 '바뀌기 전과 같은가'를 확인하는 기준선이다.

     node scripts/visual/shoot.js --base http://localhost:3100 --out .visual/baseline [--only /area,/month] [--map] [--legacy] [--close]

   --close: 끝난 뒤 작업 공간을 닫는다(기본은 .visual/.ego-space 의 공간을 계속 쓴다). ego lite 를 앞으로 띄우지 않고 백그라운드에서 쓴다.
   --legacy: 종합상황판이 옛 마크업(.dir .reg 같은 클래스)이던 커밋의 빌드를 찍을 때. 상태 화면이 누르는 대상의 선택자만 옛 것으로 바꾼다.

   ego-browser 가 필요하다(환경변수를 못 받아서 이 파일이 설정을 스크립트에 끼워 넣어 stdin 으로 넘긴다).
   결정적이게 하려고 prefers-reduced-motion 을 켜고(시안의 순환·전환 끔), 해상도 1440·1100·390, 배율 1, 긴 페이지는 높이 6000 에서 자른다. */
'use strict';
const { spawn } = require('node:child_process');
const path = require('node:path');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, x, i, all) => (x.startsWith('--') ? [...a, [x.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true]] : a), []));
const base = (args.base || 'http://localhost:3100').replace(/\/$/, '');
const out = path.resolve(args.out || '.visual/shot');
const only = args.only ? String(args.only).split(',') : null;

/* 대시보드 경로(단일 화면). 알려진 모든 화면 종류를 한 번씩 */
const ROUTES = ['/', '/area', '/area/11', '/area/12', '/area/41450', '/area/11110', '/month/2026-08', '/month/2026-10', '/projects', '/project/PRJ-11290-0001', '/stage', '/stage/04', '/stage/01',
  '/agency', '/agency/lh', '/agency/local', '/agency/sh', '/agency/mnd', '/sources', '/reports', '/my-area', '/area/99'];
const WIDTHS = [1440, 1100, 390];

/* 상호작용 상태: [이름, 경로, 폭들, 동작(ego 스크립트 조각 — page 가 있다)] */
const STATES = [
  ['home-dir3', '/', [1440], 'await page.click("css:[data-slot=board-dir]:nth-child(3)");'],
  ['home-dir6', '/', [1440], 'await page.click("css:[data-slot=board-dir]:nth-child(6)");'],
  ['home-legend-start', '/', [1440], 'await page.click("css:[data-slot=board-legend] button:nth-child(3)");'],
  ['home-region-gg', '/', [1440], 'await page.click("css:[data-slot=board-region]:nth-child(2)");'],
  ['home-region-jn', '/', [1440], 'await page.click("css:[data-slot=board-region]:nth-child(14)");'],
  ['home-tip', '/', [1440], 'await page.mouse.move(520, 480); await page.mouse.move(540, 482); await page.mouse.move(560, 484); await page.waitForSelector("css:#p-chart [data-slot=board-tip]:not([hidden])", { timeout: 5000 });'],
  ['theme-dark-home', '/', [1440, 390], 'await page.evaluate(() => localStorage.setItem("theme", "dark")); await page.reload(); await page.waitForTimeout(600);'],
  ['theme-dark-area', '/area', [1440], 'await page.evaluate(() => localStorage.setItem("theme", "dark")); await page.reload(); await page.waitForTimeout(600);'],
  ['theme-dark-project', '/project/PRJ-11290-0001', [1440], 'await page.evaluate(() => localStorage.setItem("theme", "dark")); await page.reload(); await page.waitForTimeout(600);'],
  ['nav-menu-open', '/area', [390], 'await page.evaluate(() => document.querySelector("button[aria-label=메뉴]").click()); await page.waitForTimeout(400);'],
];

const config = { spaceDir: path.resolve('.visual'), spaceFile: path.resolve('.visual/.ego-space'), close: !!args.close, base, out, only, routes: ROUTES, widths: WIDTHS, states: STATES.map(([n, r, w]) => [n, r, w]), map: !!args.map };
/* 종합상황판 상태 화면이 누르는 대상: 새 마크업(data-slot) → 옛 마크업(클래스). --legacy 로 옛 커밋의 빌드를 찍을 때만 바꾼다 */
const LEGACY = [['[data-slot=board-dir]', '.dir'], ['[data-slot=board-legend] button', '.blegend button'], ['[data-slot=board-region]', '.reg'],
  ['[data-slot=board-tip]', '.tip']];
const code = (c) => (args.legacy ? LEGACY.reduce((x, [n, o]) => x.split(n).join(o), c) : c);
const actions = STATES.map(([, , , c]) => `async (page) => { ${code(c)} }`).join(',\n');

const script = `
const fs = await import("node:fs/promises");
const C = ${JSON.stringify(config)};
const ACT = [${actions}];
const H = 900, CAP = 6000;
const slug = (s) => (s === "/" ? "home" : s.replace(/^\\//, "").replace(/[\\/?=&]+/g, "-"));
/* 작업 공간은 하나를 계속 쓴다(.visual/.ego-space 에 번호를 적어 둔다). 실행마다 새로 만들어 닫으면 새 창이 생겼다 사라져 사용자 화면을 방해한다.
   기억한 공간이 사라졌으면 새로 만든다. 끝나도 닫지 않는다(--close 일 때만). */
let task = null;
try { const id = Number((await fs.readFile(C.spaceFile, "utf8")).trim()); if (id) task = await taskSpace(id); } catch (_) { task = null; }
if (!task) { task = await taskSpace("화면 점검"); await fs.mkdir(C.spaceDir, { recursive: true }); await fs.writeFile(C.spaceFile, String(task.spaceId)); }
console.log("작업 공간", task.spaceId);
const page = task.page("p1");
let injected = null;
try {
/* 방문한 링크의 색을 방문 전과 같게 보이게 한다. 브라우저가 방문 기록을 비동기로 반영해서, 같은 화면이 실행 때마다 링크 색이 달랐다
   (2026-10-09: 데이터 원본의 '기관별' 링크가 파랑/보라로 갈림). @layer base 안의 우선순위 0(:where)이라 색을 직접 정한 링크(Tailwind 유틸리티·옛 CSS)는 그대로다.
   상단 메뉴 바의 sticky 는 static 으로 찍는다: 맨 위(스크롤 0)에서 겉모습은 같지만, sticky 는 별도 합성 레이어를 만들어 본문 래스터가 미세하게(최대 차이 14)
   달라진다. 기준선이 이 조건(static)으로 두 번 찍어 검증됐으므로 같은 조건을 유지한다. */
/* 스크롤바를 숨긴다: 스크롤바가 있느냐에 따라 본문 폭이 소수 픽셀 달라져 카드·표의 1px 테두리가 실행마다 다르게 그려졌다
   (2026-10-09: 같은 화면 두 번에 최대 차이 25). 숨기면 폭이 화면 폭 그대로라 결정적이다. */
await page.cdp("Emulation.setScrollbarsHidden", { hidden: true });
injected = (await page.cdp("Page.addScriptToEvaluateOnNewDocument", { source: "document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); s.textContent = '@layer base{:where(a:visited){color:LinkText}} header.sticky{position:static!important}'; document.head.appendChild(s); });"  })).identifier;
await page.goto(C.base + "/");
await page.waitForLoadState();
const DPR = await page.evaluate(() => devicePixelRatio);   // 이 브라우저의 화면 배율(예 1.1). 뷰포트 폭은 이만큼 나뉘어 적용되므로 미리 곱해 준다
await page.cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
/* 모든 이동은 빈 문서를 거친다. 앞 화면이 모바일 폭이었는지·스크롤바가 있었는지에 따라 같은 화면의 본문 폭이 14px 달라져(1206/1220) 줄바꿈과 높이가 흔들렸다
   (2026-10-09: 같은 / 가 실행 이력에 따라 2083 과 2043 으로 측정됨. 빈 문서를 거치면 이력과 상관없이 같은 쪽이 된다). */
const nav = async (url) => { await page.goto("about:blank"); await page.goto(url); await page.waitForLoadState(); };
const setView = async (w) => {
  const mobile = w < 600; K = mobile ? 1 : DPR;   // 모바일 에뮬레이션은 배율 보정 없이 폭 그대로 적용된다
  await page.cdp("Emulation.setDeviceMetricsOverride", { width: mobile ? w : Math.round(w * DPR), height: mobile ? 844 : Math.round(H * DPR), deviceScaleFactor: mobile ? 1 : 1, mobile });
  const iw = await page.evaluate(() => innerWidth);
  if (iw !== w) console.log("경고: 뷰포트 폭", w, "요청, 실제", iw);
};
/* 포인터를 화면 밖으로 치운다: 이전 상태(툴팁 등)에서 남은 포인터가 다음 화면의 호버 효과를 만들면 같은 화면이 다르게 찍힌다 */
const park = () => page.cdp("Input.dispatchMouseEvent", { type: "mouseMoved", x: -50, y: -50, buttons: 0 });
const settle = async () => { await park(); await page.evaluate(() => document.fonts.ready.then(() => 0)); await page.waitForTimeout(350); };
/* CSS 픽셀 1:1 로 캡처한다(SDK 의 page.screenshot 은 배율 보정이 겹쳐 이미지가 1/1.1 로 줄어든다). clip.scale 1 = 이미지 1 픽셀이 CSS 1 픽셀.
   긴 페이지는 뷰포트 높이를 페이지 전체로 키워 화면 안에서 찍는다. captureBeyondViewport 로 화면 밖을 찍으면 스크롤 컨테이너 안 sticky 헤더의
   글자 가장자리가 CSS 와 무관하게 다르게 래스터되는 아티팩트가 생겼다(2026-10-09: 빈 css 와 @layer 한 줄만 있는 css 의 화면이 달랐고, 전체 높이로 키우자 같아졌다). */
/* 캡처 영역(clip)의 단위는 CSS 픽셀이 아니라 화면 배율이 곱해진 단위(DIP)다. 데스크톱 폭은 배율(예 1.1)만큼 곱한 영역을 1/배율로 줄여 찍어야
   이미지 1 픽셀이 CSS 1 픽셀이고 화면이 잘리지 않는다(2026-10-09: 그냥 scale 1 로 찍으면 오른쪽 9% 가 잘리고 1.1배로 확대돼 있었다. 모바일 에뮬레이션은 배율 1). */
let K = 1;
const cap = async (file, clip) => {
  const r = await page.cdp("Page.captureScreenshot", { format: "png", clip: { x: clip.x * K, y: clip.y * K, width: clip.width * K, height: clip.height * K, scale: 1 / K } });
  await fs.mkdir(C.out, { recursive: true });
  await fs.writeFile(C.out + "/" + file + ".png", Buffer.from(r.data, "base64"));
};
const fullView = async (w, h) => {
  const mobile = w < 600; K = mobile ? 1 : DPR;
  await page.cdp("Emulation.setDeviceMetricsOverride", { width: mobile ? w : Math.round(w * DPR), height: mobile ? h : Math.round(h * DPR), deviceScaleFactor: 1, mobile });
  await page.waitForTimeout(400);
};
/* 페이지 높이가 두 번 연속 같을 때까지 기다린다. 하이드레이션·글꼴·높이 예약(Reserve) 때문에 바로 재면 40px 짧게 잰 적이 있다
   (2026-10-09: 같은 화면이 2043 과 2083 으로 갈렸고, 기준선의 state-home-* 아홉 장이 아래 40px 잘려 있었다). */
const stableHeight = async () => {
  let prev = -1, same = 0;
  for (let i = 0; i < 40 && same < 3; i++) {
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    same = h === prev ? same + 1 : 0; prev = h;
    await page.waitForTimeout(150);
  }
  return prev;
};
const shot = async (file) => {
  await stableHeight();
  const m = await page.evaluate(() => ({ w: innerWidth, h: Math.ceil(document.documentElement.scrollHeight) }));
  const h = Math.min(m.h, CAP);
  await fullView(m.w, h);
  await cap(file, { x: 0, y: 0, width: m.w, height: h });
  await setView(m.w);   // 다음 화면을 위해 기본 높이로 되돌린다
  return m.h;
};
let n = 0;
const want = (r) => !C.only || C.only.includes(r);
for (const w of C.widths) {
  await setView(w);
  for (const r of C.routes) {
    if (!want(r)) continue;
    await nav(C.base + r); await settle();
    const h = await shot(slug(r) + "@" + w); n++;
    console.log(w, r, "height", h);
  }
}
for (let i = 0; i < C.states.length; i++) {
  const [name, route, widths] = C.states[i];
  if (!want(route)) continue;
  for (const w of widths) {
    await setView(w);
    await nav(C.base + route); await settle();
    await ACT[i](page); await page.waitForTimeout(450);
    await shot("state-" + name + "@" + w); n++;
    console.log("state", name, w);
    await park();
    await page.evaluate(() => localStorage.removeItem("theme"));
  }
}
if (C.map) {
  for (const w of [1440, 390]) {
    await setView(w);
    await nav(C.base + "/map?region=jeonnam-naju&selftest=1");
    await page.waitForFunction(() => window.__mapStatus && window.__mapStatus.loaded, undefined, { timeout: 60000 }).catch(() => {});
    await settle();
    /* 지도 화면의 상단 메뉴 바(48px)만 비교한다. 그 아래는 지도 캔버스라 타일·글자가 늦게 올라와 찍을 때마다 다르다 */
    await cap("map-nav@" + w, { x: 0, y: 0, width: w, height: 60 });
    n++; console.log("map-nav", w);
  }
}
console.log("찍은 장수:", n);
} finally {
  /* 중간에 죽어도 작업 공간을 남기지 않는다(남으면 다음 실행의 창이 가려져 캡처가 멈춘다) */
  await page.cdp("Emulation.setDeviceMetricsOverride", { width: 0, height: 0, deviceScaleFactor: 0, mobile: false }).catch(() => {});
  await page.cdp("Emulation.setScrollbarsHidden", { hidden: false }).catch(() => {});
  if (injected) await page.cdp("Page.removeScriptToEvaluateOnNewDocument", { identifier: injected }).catch(() => {});
  await page.evaluate(() => localStorage.removeItem("theme")).catch(() => {});
  if (C.close) await task.finish({ keep: [] }).catch(() => {});
}
`;

const child = spawn('ego-browser', ['nodejs'], { stdio: ['pipe', 'inherit', 'inherit'] });
child.stdin.end(script);
child.on('exit', (code) => process.exit(code ?? 1));
