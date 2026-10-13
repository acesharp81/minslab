---
format: 1920x1080
duration: 15s
message: "정책에서 입주까지, 흩어진 공공 주택공급 정보를 한 화면의 상황판으로 본다"
arc: Hook → Problem → Solution(Proof) → Close
audience: "발표 청중 — 정책 담당자와 팀 프로젝트 평가자"
mode: autonomous
---

박자 기준: 128 BPM, 1박 = 0.46875s, 1마디 = 1.875s, 8마디 = 15.000s. 장면 경계는 마디선(0 / 3.75 / 5.625 / 11.25 / 15.0s)이다.
BGM은 같은 박자표로 합성한 `assets/audio/bgm-128bpm.wav`(1마디 3박~2마디 4박에 6단계 칩 핑, 5.625s 드롭, 11.25s 임팩트).

## Frame 1 — 정책에서 입주까지

- scene: 제목이 박자에 맞춰 떨어지고, 6단계 칩이 박마다 하나씩 켜진다
- duration: 3.75s
- poster: 3.3s
- transition_in: cut
- status: animated
- src: compositions/s1-hook.html
- blueprint: kinetic-type-beats
- rules: waterfall-entry, svg-path-draw, spring-pop-entrance
- music: 도입 — 패드와 6단계 칩에 맞춘 펜타토닉 핑

Hook. "정책에서 입주까지, 주택공급은 지금 어디쯤?" 발표자료 3장의 6단계(01 정책 · 02 사업화 · 03 인허가 · 04 건설 · 05 공급 · 06 입주)가 박마다 켜진다.

## Frame 2 — 흩어진 정보

- scene: 기관 카드 4장이 네 모서리에서 들어와 가운데 한 점으로 모인다
- duration: 1.875s
- poster: 1.0s
- transition_in: cut
- status: animated
- src: compositions/s2-gather.html
- blueprint: constellation-hub
- rules: center-outward-expansion, card-morph-anchor
- music: 3마디 빌드 — 스네어 롤과 라이저

Problem. LH · SH · 국방부 · 국토교통부 자료가 기관마다 따로 있다. 카드가 모여 지도 프레임이 될 점을 만든다.

## Frame 3 — 현황 지도

- scene: 인천 계양 3D 지도 화면에 수치 카드가 붙고, 층수 보기에서 공정율 보기로 넘어간다
- duration: 5.625s (+0.475s 겹침)
- poster: 4.6s
- transition_in: cut (5.625s 드롭, 프레임이 가운데 점에서 커짐)
- status: animated
- src: compositions/s3-map.html
- blueprint: device-surface-showcase
- rules: counting-dynamic-scale, stat-bars-and-fills, card-morph-anchor
- music: 4~6마디 드롭 — 킥·베이스·아르페지오

Proof. 지도 화면은 `index.html`을 프레임 단위로 캡처한 소재다. 6개 단지·3,173세대, 분양중 972 / 건설 단계 1,095 / 준공 임박 1,106, 공정율 A2·A3 100%.

## Frame 4 — 정리

- scene: 금색 바탕으로 원형 와이프, 「주택파동」 타이틀이 떨어지고 6단계 줄이 정렬된다
- duration: 3.75s
- poster: 3.4s
- transition_in: wipe (11.25s 임팩트, 원형)
- status: animated
- src: compositions/s4-close.html
- blueprint: titlecard-reveal
- rules: waterfall-entry, spring-pop-entrance
- music: 7~8마디 — 타이틀 임팩트와 여운, 마지막 0.95s 페이드아웃

Close. 「주택파동」 · 주택공급 디지털 상황판 PoC · 정책에서 입주까지, 한 화면에. 마지막 프레임은 그대로 유지된다.
