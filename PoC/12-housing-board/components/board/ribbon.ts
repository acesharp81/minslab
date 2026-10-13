/* 월별 공급 파동 리본 차트의 SVG 문자열(시안 buildChart·renderRibbon·pinSVG 를 그대로 옮김). 수식은 lib/board/sample.ts 와 같다.
   정적 부분(층·띠·축)은 범례 강조(hl)에만, 동적 부분(연도 띠·굵기 괄호·병목 핀)은 선택 시점(cur)에만 달라진다. */
import { C, GEO, K, LAST, NOW, PEAK, PH, PITCH, PW, PX0, S2, TOP, BOT, X, Y0, YT, argmax, dStage, f, ml, r10, rp, tot, vals, yr } from '../../lib/board/sample';

/* 리본 차트의 선·글자·층 경계 색: 테마별 값은 app/tailwind.css 의 --rb-* (라이트·다크). SVG 속성이 var() 로 읽는다 */
/* 층마다 세로 그라데이션(#rbg0~5): 위 = 단계색 70% + 하이라이트 30%, 가운데 = 단계색, 아래 = 단계색 86% + 그늘 14%. 두 테마 모두 위가 빛나고 아래가 깊어 물결처럼 보인다.
   색은 stop-color '속성'이 아니라 style 로 준다: 속성 값의 color-mix() 는 브라우저가 읽지 못해 검정으로 칠했다(2026-10-10 화면으로 확인). */
const grad = (k: number) => `<linearGradient id="rbg${k}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style="stop-color:color-mix(in srgb, ${C[k]} 70%, var(--rb-hi))"/><stop offset=".5" style="stop-color:${C[k]}"/><stop offset="1" style="stop-color:color-mix(in srgb, ${C[k]} 86%, var(--rb-lo))"/></linearGradient>`;
const PAL = { mid: 'var(--rb-mid)', sep: 'var(--rb-sep)', sc: 'var(--rb-sc)', axis: 'var(--rb-axis)', ink: 'var(--rb-ink)', cur: 'var(--rb-cur)', hatch: 'var(--rb-hatch)', hatchOp: '.32', seam: 'var(--rb-seam)', band: 'var(--rb-band)', acc: 'var(--rb-acc)', dim: 'var(--rb-dim)', pos: 'var(--rb-pos)', yrOn: 'var(--rb-yr-on)', yrOff: 'var(--rb-yr-off)', hud: 'var(--rb-hud)', hudLine: 'var(--rb-hud-line)', hudTxt: 'var(--rb-hud-txt)', hudAcc: 'var(--rb-hud-acc)' };
export const HOVER = { fill: 'var(--rb-hover)', opacity: '.10' };
/* 선택한 달의 기준 막대: 테두리 없는 반투명 HUD 막대(위·아래가 조금 진하고 가운데가 옅은 세로 그라데이션 #cur-hud, 주색). 뒤의 층·지연 띠가 비쳐 보인다 */
export const CUR = { fill: 'url(#cur-hud)' };
export const RIBBON = { PX0, PITCH, TOP, PH };

const dimK = (hl: number, k: number) => (hl >= 0 && hl !== k ? 0.28 : 1);
const ln = (x1: number, y1: number, x2: number, y2: number, st: string, w: number, d?: string) =>
  `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${st}" stroke-width="${w}"${d ? ` stroke-dasharray="${d}"` : ''} pointer-events="none"/>`;
const tt = (x: number, y: number | string, t: string, fill: string, fs: number, a: string) => `<text x="${x.toFixed(1)}" y="${y}" fill="${fill}" font-size="${fs}" text-anchor="${a}">${t}</text>`;

/* 정적 부분: 층 6개(실적·예정), 지연 띠, 예정 구간 빗금, 기준일 선, 축 글자. hl = 범례에서 고른 단계(없으면 -1). */
export function chartStatic(hl: number): string {
  const nowX = X(NOW + 1);
  let s = `<defs><pattern id="hatch" width="14" height="14" patternUnits="userSpaceOnUse"><path d="M-3 3 L3 -3 M0 14 L14 0 M11 17 L17 11" fill="none" stroke="${PAL.hatch}" stroke-width="1.2" stroke-opacity="${PAL.hatchOp}"/></pattern>`
    + `<linearGradient id="cur-hud" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${PAL.acc}" stop-opacity=".34"/><stop offset=".16" stop-color="${PAL.acc}" stop-opacity=".14"/><stop offset=".84" stop-color="${PAL.acc}" stop-opacity=".14"/><stop offset="1" stop-color="${PAL.acc}" stop-opacity=".34"/></linearGradient>${[0, 1, 2, 3, 4, 5].map(grad).join('')}`
    + `<linearGradient id="rb-scan-g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="${PAL.hudAcc}" stop-opacity="0"/><stop offset=".6" stop-color="${PAL.hudAcc}" stop-opacity=".38"/><stop offset=".86" stop-color="#FFFFFF" stop-opacity=".9"/><stop offset="1" stop-color="${PAL.hudAcc}" stop-opacity="0"/></linearGradient></defs>`;
  /* 첫 화면 연출(app/tailwind.css 의 [data-intro]): 축(rb-axes)·층(rb-layers)·기준일(rb-now)을 따로 묶어 차례로 등장시킨다 */
  const half = 12500 * S2;
  s += '<g class="rb-axes">' + ln(PX0, Y0, PX0 + PW, Y0, PAL.mid, 1, '3 4');
  s += ln(22, Y0 - half, 22, Y0 + half, PAL.sc, 1.6) + ln(17, Y0 - half, 27, Y0 - half, PAL.sc, 1.6) + ln(17, Y0 + half, 27, Y0 + half, PAL.sc, 1.6);
  s += tt(22, (Y0 - half - 8).toFixed(1), '굵기', PAL.axis, 14, 'middle') + tt(22, (Y0 + half + 20).toFixed(1), '25,000', PAL.axis, 14, 'middle') + tt(22, (Y0 + half + 36).toFixed(1), '호', PAL.axis, 14, 'middle');
  [1, 2, 3].forEach((i) => { s += ln(X(i * 12), TOP - 10, X(i * 12), BOT, PAL.sep, 1, '2 4'); });
  s += '</g><g class="rb-layers">';
  for (let k = 5; k >= 0; k--) {
    s += `<path d="${rp(k, 0, NOW + 1, false, 3)}" fill="url(#rbg${k})" opacity="${dimK(hl, k).toFixed(2)}"/>`;
    s += `<path d="${rp(k, NOW + 1, LAST + 1, false, 3)}" fill="url(#rbg${k})" opacity="${(0.62 * dimK(hl, k)).toFixed(2)}"/>`;
  }
  /* 층 경계: 전 구간 한 줄로 그어(과거·예정 사이에 세로 이음선이 생기지 않게) 층이 또렷하게 갈린다. 라이트 흰색, 다크 남색(--rb-seam) */
  for (let k = 5; k >= 0; k--) s += `<path d="${rp(k, 0, LAST + 1, false, 3)}" fill="none" stroke="${PAL.seam}" stroke-width="0.9" stroke-opacity="${(0.85 * dimK(hl, k)).toFixed(2)}" stroke-linejoin="round" pointer-events="none"/>`;
  for (let k = 0; k < 6; k++) s += `<path d="${rp(k, 0, LAST + 1, true, 3)}" fill="${PAL.band}" fill-opacity="${(0.94 * dimK(hl, k)).toFixed(2)}"/>`;
  s += `<rect x="${nowX.toFixed(1)}" y="${TOP}" width="${(PX0 + PW - nowX).toFixed(1)}" height="${PH}" fill="url(#hatch)" pointer-events="none"/>`;
  s += '</g><g class="rb-now">' + ln(nowX, TOP - 8, nowX, BOT + 2, PAL.ink, 1.4, '5 4');
  s += tt(nowX, 376, '기준일 2026.10', PAL.ink, 14, 'middle') + '</g><g class="rb-axes">';
  [0, 6, 12, 18, 30, 36, 42].forEach((m) => { s += tt(X(m + 0.5), 392, ml(m), PAL.axis, 14, 'middle'); });
  s += `<rect x="${PX0 + 8}" y="64" width="12" height="12" rx="2" fill="${PAL.band}"/>` + tt(PX0 + 24, 73, '붉은 띠 = 단계별 지연 호수', PAL.sc, 14, 'start') + '</g>';
  return s;
}

/* 리본 위 라벨: HUD 판(남색 반투명 유리 + 밝은 가장자리 선 + 왼쪽 3px 강조 띠) 위에 흰 글자. 흰 판이 리본 색을 가리던 것을 바꿨다(2026-10-10).
   글자에 외곽선을 겹치면 축소 시 획이 뭉개져서 판과 글자를 따로 그린다. accent = 강조 띠 색(총량은 밝은 주색 --rb-hud-acc, 병목·정점 핀은 지연 띠 색) */
function labelSVG(x: number, baseline: number, text: string, accent: string): string {
  const width = [...text].reduce((sum, c) => sum + (/[가-힣]/.test(c) ? 15 : 9), 0) + 22;
  const center = Math.max(width / 2 + 6, Math.min(PX0 + PW - width / 2, x)), left = center - width / 2, top = baseline - 17;
  return `<rect x="${left.toFixed(2)}" y="${top.toFixed(2)}" width="${width}" height="24" rx="5" fill="${PAL.hud}" stroke="${PAL.hudLine}" stroke-width=".75"/>`
    + `<rect x="${(left + 3).toFixed(2)}" y="${(top + 4).toFixed(2)}" width="3" height="16" rx="1.5" fill="${accent}"/>`
    + `<text x="${(center + 3).toFixed(2)}" y="${baseline.toFixed(2)}" fill="${PAL.hudTxt}" font-size="15" font-weight="600" text-anchor="middle">${text}</text>`;
}

/* 병목 핀: 그 달 병목 단계의 지연 띠 한가운데 */
function pinSVG(m: number, main: boolean): string {
  const g = GEO[4 * m + 2], ds = dStage(m), k = argmax(ds);
  const px = X(m + 0.5), py = g.lw[k] - g.dl[k] / 2, cx = Math.max(PX0 + 95, Math.min(PX0 + PW - 95, px));
  const t = main ? `${K[k]} 지연 ${f(r10(ds[k]))}호 · ${(ds[k] / vals(m)[k] * 100).toFixed(1)}%` : `정점 · ${K[k]} ${f(r10(ds[k]))}호`;
  return `<g class="rb-pin"><line x1="${px.toFixed(1)}" y1="${(py - 7).toFixed(1)}" x2="${cx.toFixed(1)}" y2="${(py - 34).toFixed(1)}" stroke="${PAL.cur}" stroke-width="1.2" stroke-dasharray="2 2"/>`
    + `<circle cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="6" fill="var(--rb-pin)" stroke="${PAL.acc}" stroke-width="3"/>`
    + labelSVG(cx, py - 40, t, PAL.band) + '</g>';
}

/* 동적 부분: 연도 띠 · 굵기 괄호 · 병목 핀(선택 시점과 정점) */
export function ribbonDynamic(cur: number): string {
  const yi = yr(cur);
  let s = '';
  YT.forEach((tv, i) => {
    const ma = i * 12, mb = Math.min(ma + 11, LAST), xa = X(ma), xb = X(mb + 1), act = i === yi, bc = act ? PAL.acc : PAL.dim, bw = act ? 2.2 : 1.2, cx = ((xa + xb) / 2).toFixed(1);
    const bl = (x1: number, y1: number, x2: number, y2: number) => `<line x1="${x1.toFixed(1)}" y1="${y1}" x2="${x2.toFixed(1)}" y2="${y2}" stroke="${bc}" stroke-width="${bw}"/>`;
    s += `<g class="rb-yr" style="--i:${i}"><text x="${cx}" y="16" fill="${act ? PAL.yrOn : PAL.yrOff}" font-size="15" font-weight="700" text-anchor="middle">${2025 + i}년 ${f(tv)}호</text>`;
    s += i > 0
      ? `<text x="${cx}" y="31" fill="${PAL.pos}" font-size="14" font-weight="700" text-anchor="middle">▲ +${f(tv - YT[i - 1])}호 (+${Math.round((tv - YT[i - 1]) / YT[i - 1] * 100)}%)</text>`
      : `<text x="${cx}" y="31" fill="${PAL.axis}" font-size="14" text-anchor="middle">기준 연도</text>`;
    s += bl(xa + 3, 38, xb - 3, 38) + bl(xa + 3, 34, xa + 3, 38) + bl(xb - 3, 34, xb - 3, 38) + '</g>';
  });
  const hh = tot(cur) * S2 / 2, bx = X(cur + 0.5);
  const cl = (x1: number, y1: number, x2: number, y2: number, w: number, d?: boolean) => `<line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" stroke="${PAL.cur}" stroke-width="${w}"${d ? ' stroke-dasharray="2 2"' : ''}/>`;
  s += '<g class="rb-marks">' + cl(bx, Y0 - hh, bx, Y0 + hh, 1.4, true) + cl(bx - 8, Y0 - hh, bx + 8, Y0 - hh, 2) + cl(bx - 8, Y0 + hh, bx + 8, Y0 + hh, 2);
  s += labelSVG(bx, Math.max(TOP + 22, Y0 - hh + 22), `${f(tot(cur))}호`, PAL.hudAcc);
  s += pinSVG(cur, true);
  if (Math.abs(PEAK - cur) > 4) s += pinSVG(PEAK, false);
  return s + '</g>';
}
