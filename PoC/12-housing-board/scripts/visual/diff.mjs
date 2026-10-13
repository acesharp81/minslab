#!/usr/bin/env node
/* 두 폴더의 스크린샷을 픽셀 단위로 비교한다.
     node scripts/visual/diff.mjs .visual/baseline .visual/current [--tol 2] [--allow 0]
   같은 이름의 PNG 를 비교한다. 한 픽셀의 R·G·B 중 가장 큰 차이가 --tol(기본 2) 이하이면 같은 것으로 본다:
   그라데이션 디더링 같은 래스터 잡음은 같은 화면을 두 번 찍어도 ±1~2 단계로 흔들린다(2026-10-09 확인). 그보다 큰 차이는 다른 그림이다.
   크기가 다르거나 다른 픽셀이 --allow(장당 개수, 기본 0)를 넘으면 실패(종료 코드 1). 다른 곳은 <current>/diff/ 에 빨간 PNG 로 남긴다. */
import fs from 'node:fs';
import path from 'node:path';
import { PNG } from 'pngjs';

const [a, b, ...rest] = process.argv.slice(2);
if (!a || !b) { console.error('사용: node scripts/visual/diff.mjs <기준 폴더> <새 폴더> [--tol N] [--allow N]'); process.exit(2); }
const opt = (name, d) => (rest.includes(name) ? Number(rest[rest.indexOf(name) + 1]) : d);
const tol = opt('--tol', 2), allow = opt('--allow', 0);
/* 알려진 잡음(noise.json): 이 파일은 그 픽셀 수까지 허용한다. state-home-tip@1440 은 툴팁 글자 가장자리가 가끔 다르게 그려진다(77px, 최대 차이 35) */
const noise = JSON.parse(fs.readFileSync(new URL('./noise.json', import.meta.url), 'utf8'));
const files = fs.readdirSync(a).filter((f) => f.endsWith('.png')).sort();
const outDir = path.join(b, 'diff');
fs.rmSync(outDir, { recursive: true, force: true });
let bad = 0, missing = 0;
for (const f of files) {
  const pb = path.join(b, f);
  if (!fs.existsSync(pb)) { missing++; console.log(`  ✖ ${f.padEnd(44)} 새 폴더에 없음`); continue; }
  const A = PNG.sync.read(fs.readFileSync(path.join(a, f))), B = PNG.sync.read(fs.readFileSync(pb));
  if (A.width !== B.width || A.height !== B.height) { bad++; console.log(`  ✖ ${f.padEnd(44)} 크기 ${A.width}x${A.height} → ${B.width}x${B.height}`); continue; }
  const D = new PNG({ width: A.width, height: A.height });
  let n = 0, max = 0;
  for (let i = 0; i < A.data.length; i += 4) {
    const d = Math.max(Math.abs(A.data[i] - B.data[i]), Math.abs(A.data[i + 1] - B.data[i + 1]), Math.abs(A.data[i + 2] - B.data[i + 2]));
    if (d > tol) { n++; if (d > max) max = d; D.data[i] = 255; D.data[i + 1] = 0; D.data[i + 2] = 0; D.data[i + 3] = 255; }
    else { const g = Math.round((A.data[i] + A.data[i + 1] + A.data[i + 2]) / 3 * 0.25 + 191); D.data[i] = D.data[i + 1] = D.data[i + 2] = g; D.data[i + 3] = 255; }
  }
  if (n > Math.max(allow, noise[f] || 0)) { bad++; fs.mkdirSync(outDir, { recursive: true }); fs.writeFileSync(path.join(outDir, f), PNG.sync.write(D)); console.log(`  ✖ ${f.padEnd(44)} ${String(n).padStart(7)}px (${(n / (A.width * A.height) * 100).toFixed(3)}%) 최대 차이 ${max}`); }
}
console.log(`${files.length}장 비교 — 같음 ${files.length - bad - missing}, 다름 ${bad}, 없음 ${missing} (채널 허용 ${tol}, 장당 허용 ${allow}px)`);
process.exit(bad || missing ? 1 : 0);
