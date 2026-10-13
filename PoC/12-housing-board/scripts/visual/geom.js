#!/usr/bin/env node
/* 두 서버(옛 코드와 새 코드)의 같은 화면에서 모든 요소의 위치·크기를 DOM 순서대로 비교한다(개발 도구).
   스크린샷이 다르다고만 나올 때 '어느 요소부터 어긋나는지'를 알려 준다.

     node scripts/visual/geom.js --a http://localhost:3200 --b http://localhost:3100 [--route /] [--widths 1440,390] [--root main]

   스크롤바를 숨기고 잰다(본문 폭이 화면 높이에 따라 14px 달라지는 것을 없애려고). 요소 구조(태그·id)가 다르면 거기서 멈춘다.
   ego lite 를 앞으로 띄우지 않고 shoot.js 와 같은 작업 공간(.visual/.ego-space)을 쓴다. 시간에 따라 변하는 값(재생 막대 등)은 어긋나 보일 수 있으니 눈으로 거른다. */
'use strict';
const { spawn } = require('node:child_process');

const args = Object.fromEntries(process.argv.slice(2).reduce((a, v, i, all) => (v.startsWith('--') ? [...a, [v.slice(2), all[i + 1] && !all[i + 1].startsWith('--') ? all[i + 1] : true]] : a), []));
const config = { spaceDir: require('node:path').resolve('.visual'), spaceFile: require('node:path').resolve('.visual/.ego-space'), a: args.a, b: args.b, route: args.route || '/', widths: (args.widths || '1440,390').split(',').map(Number), root: args.root || 'main' };
if (!config.a || !config.b) { console.error('사용: node scripts/visual/geom.js --a <옛 서버> --b <새 서버> [--route /] [--widths 1440,390] [--root main]'); process.exit(2); }

const script = `
const fs = await import("node:fs/promises");
const C = ${JSON.stringify(config)};
let task = null;   // shoot.js 와 같은 작업 공간을 쓴다(새 창을 만들지 않는다)
try { const id = Number((await fs.readFile(C.spaceFile, "utf8")).trim()); if (id) task = await taskSpace(id); } catch (_) { task = null; }
if (!task) { task = await taskSpace("화면 점검"); await fs.mkdir(C.spaceDir, { recursive: true }); await fs.writeFile(C.spaceFile, String(task.spaceId)); }
const page = task.page("p1");
try {
  await page.goto(C.a + C.route); await page.waitForLoadState();
  const DPR = await page.evaluate(() => devicePixelRatio);
  const grab = async (base, w) => {
    await page.goto("about:blank"); await page.goto(base + C.route); await page.waitForLoadState();
    await page.cdp("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
    await page.cdp("Emulation.setScrollbarsHidden", { hidden: true });
    await page.cdp("Emulation.setDeviceMetricsOverride", { width: w < 600 ? w : Math.round(w * DPR), height: w < 600 ? 844 : Math.round(900 * DPR), deviceScaleFactor: 1, mobile: w < 600 });
    await page.waitForTimeout(900);
    return await page.evaluate((sel) => [...document.querySelector(sel).querySelectorAll("*")].map((e) => { const b = e.getBoundingClientRect(); return [e.tagName.toLowerCase() + (e.id ? "#" + e.id : ""), +b.left.toFixed(1), +b.top.toFixed(1), +b.width.toFixed(1), +b.height.toFixed(1), (e.textContent || "").trim().slice(0, 14)]; }), C.root);
  };
  for (const w of C.widths) {
    const o = await grab(C.a, w), n = await grab(C.b, w);
    console.log("폭", w, "요소 수 a", o.length, "b", n.length);
    let shown = 0;
    for (let i = 0; i < Math.min(o.length, n.length) && shown < 8; i++) {
      const x = o[i], y = n[i];
      if (x[0] !== y[0]) { console.log("  구조 다름 @", i, x[0], "vs", y[0]); break; }
      if ([1, 2, 3, 4].some((k) => Math.abs(x[k] - y[k]) > 0.6)) { console.log("  @" + i, x[0], JSON.stringify(x.slice(1)), "→", JSON.stringify(y.slice(1))); shown++; }
    }
    if (!shown) console.log("  어긋난 요소 없음");
  }
} finally {
  await page.cdp("Emulation.setScrollbarsHidden", { hidden: false }).catch(() => {});
  await page.cdp("Emulation.setDeviceMetricsOverride", { width: 0, height: 0, deviceScaleFactor: 0, mobile: false }).catch(() => {});
}
`;
const child = spawn('ego-browser', ['nodejs'], { stdio: ['pipe', 'inherit', 'inherit'] });
child.stdin.end(script);
child.on('exit', (code) => process.exit(code ?? 1));
