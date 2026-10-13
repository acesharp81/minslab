'use strict';
/* lib/permits.js — Python(tools/regiontools/build_region.py · status.py)과 같은 결과를 내는지, 번지 단위로 모으는 규칙이 맞는지 */
const test = require('node:test');
const assert = require('node:assert/strict');
const P = require('../../lib/permits.js');

const NOW = Date.parse('2026-10-05T03:00:00Z');
/* 아래 기준값은 Python 구현에서 뽑았다(기준일 2026-10-05) */
const PNU_IN = [["41450", "10800", "0569", "0000", "0"], ["41450", "10800", "569", null, "0"], ["41450", "10800", "0001", "0002", "1"], ["41450", "10800", "0001", "0002", "2"], ["41450", "10800", "0", "0", "0"], ["41450", "10800", "abc", "0", "0"], ["11290", "13800", "0025", "0055", null], ["11290", "13800", " 0025 ", "", "0"]], PNU_OUT = ["4145010800105690000", "4145010800105690000", "4145010800200010002", null, null, null, "1129013800100250055", "1129013800100250000"];
const YMD_IN = ["20260723", "20260230", "2026072", "  ", "abcdefgh", null, "19991231", "20240229"], YMD_OUT = ["2026-07-23", null, null, null, null, null, "1999-12-31", "2024-02-29"];
const NAMES = ["하남 호반써밋 에듀파크", "하남유시티대명루첸리버파크", "장위6구역 주택재개발정비사업", "한진해모로아파트", "위례 힐스테이트 1단지 신축공사", "래미안 강남 포레스트 3차 아파트", "    ", "주택건설사업", "대명강변타운아파트", "휴먼시아 12차", "어반라이프 힐스테이트 에코 2단지", "가나다라마바사아자차카타"], SHORT = ["하남", "하남유시티대명루", "장위6구역", "한진해모로", "위례 1단지", "래미안 3차", "", "", "대명강변타운", "휴먼시아 12차", "어반라이프 2", "가나다라마바사아"];
const RECS = [{"apprvDay": "20180904", "stcnsDay": "20181015", "useInsptDay": "20210806", "totHhldCnt": 999, "mgmHsrgstPk": 1}, {"apprvDay": "20240101", "stcnsDay": "20250101", "useInsptDay": "", "totHhldCnt": 100, "mgmHsrgstPk": 2}, {"apprvDay": "20250101", "stcnsDay": "", "useInsptDay": "", "totHhldCnt": 50, "mgmHsrgstPk": 3}, {"apprvDay": "20270101", "stcnsDay": "", "useInsptDay": "", "totHhldCnt": 50, "mgmHsrgstPk": 4}, {"apprvDay": "20250101", "stcnsDay": "20240101", "useInsptDay": "", "totHhldCnt": 50, "mgmHsrgstPk": 5}, {"apprvDay": "20200101", "stcnsDay": "20200601", "useInsptDay": "20200301", "totHhldCnt": 50, "mgmHsrgstPk": 6}, {"apprvDay": "20200101", "stcnsDay": "20260101", "useInsptDay": "20271231", "totHhldCnt": 50, "mgmHsrgstPk": 7}], EVENTS = [[{"type": "permit_approved", "date": "2018-09-04", "value": 999, "ref": "1"}, {"type": "construction_start", "date": "2018-10-15", "ref": "1"}, {"type": "completion_inspection", "date": "2021-08-06", "ref": "1"}], [{"type": "permit_approved", "date": "2024-01-01", "value": 100, "ref": "2"}, {"type": "construction_start", "date": "2025-01-01", "ref": "2"}], [{"type": "permit_approved", "date": "2025-01-01", "value": 50, "ref": "3"}], [{"type": "permit_approved", "date": "2027-01-01", "value": 50, "ref": "4", "suspect": true}], [{"type": "permit_approved", "date": "2025-01-01", "value": 50, "ref": "5", "suspect": true}, {"type": "construction_start", "date": "2024-01-01", "ref": "5", "suspect": true}], [{"type": "permit_approved", "date": "2020-01-01", "value": 50, "ref": "6"}, {"type": "construction_start", "date": "2020-06-01", "ref": "6", "suspect": true}, {"type": "completion_inspection", "date": "2020-03-01", "ref": "6", "suspect": true}], [{"type": "permit_approved", "date": "2020-01-01", "value": 50, "ref": "7"}, {"type": "construction_start", "date": "2026-01-01", "ref": "7"}, {"type": "completion_inspection", "date": "2027-12-31", "ref": "7", "suspect": true}]], STATUS = ["입주 단계", "건설 단계", "계획", "계획", "계획", "계획", "건설 단계"];

test('makePnu·ymd: Python 과 같다(대지 1·산 2·블록 거절, 본번 0·글자 거절, 달력에 없는 날짜)', () => {
  PNU_IN.forEach((a, i) => assert.equal(P.makePnu(...a), PNU_OUT[i], JSON.stringify(a)));
  YMD_IN.forEach((s, i) => assert.equal(P.ymd(s), YMD_OUT[i], String(s)));
});

test('shortLabel: 지도용 짧은 이름이 Python 과 같다(8자 이내, N차·N단지 보존)', () => {
  NAMES.forEach((n, i) => assert.equal(P.shortLabel(n), SHORT[i], n));
});

test('permitEvents·statusOf: 사건과 상태가 Python 과 같다(미래 실제 날짜·순서 모순은 suspect)', () => {
  RECS.forEach((r, i) => { assert.deepEqual(P.permitEvents(r, NOW), EVENTS[i], JSON.stringify(r)); assert.equal(P.statusOf(P.permitEvents(r, NOW), NOW), STATUS[i], JSON.stringify(r)); });
});

test('isCandidate: 공동주택이면서 총세대수가 있는 기록만', () => {
  assert.equal(P.isCandidate({ totHhldCnt: 10, purpsCdNm: '공동주택' }), true);
  assert.equal(P.isCandidate({ totHhldCnt: 0, purpsCdNm: '공동주택' }), false);
  assert.equal(P.isCandidate({ totHhldCnt: 10, purpsCdNm: '단독주택' }), false);
  assert.equal(P.isCandidate({ totHhldCnt: null, purpsCdNm: '공동주택(아파트)' }), false);
});

const rec = (over) => Object.assign({ sigunguCd: '41450', bjdongCd: '10800', bun: '0569', ji: '0000', platGbCd: '0', purpsCdNm: '공동주택', totHhldCnt: 100, bldNm: '테스트아파트', mgmHsrgstPk: 1, apprvDay: '20240101', stcnsDay: '', useInsptDay: '', mainBldCnt: 3, platPlc: '경기도 하남시 덕풍동 569번지' }, over);

test('aggregate: 같은 필지의 기록(변경허가)은 한 사업으로 모으고, 후보가 아닌 것·PNU 없는 것은 센다', () => {
  const out = P.aggregate([
    rec({ mgmHsrgstPk: 1, apprvDay: '20240101', totHhldCnt: 100 }),
    rec({ mgmHsrgstPk: 2, apprvDay: '20250601', totHhldCnt: 120, stcnsDay: '20250901', useInsptSchedDay: '20281231', bldNm: '테스트아파트 신축공사' }),
    rec({ mgmHsrgstPk: 3, bun: '0001', ji: '0002', bldNm: '다른곳', totHhldCnt: 50, apprvDay: '20180101', stcnsDay: '20180601', useInsptDay: '20200601' }),
    rec({ mgmHsrgstPk: 4, purpsCdNm: '단독주택' }), rec({ mgmHsrgstPk: 5, platGbCd: '2' }),
  ], NOW);
  assert.deepEqual(out.skipped, { notCandidate: 1, noPnu: 1 });
  assert.equal(out.projects.length, 2);
  const [a, b] = out.projects;                                                      // 건설 단계 → 입주 단계 순
  assert.equal(a.pnu, '4145010800105690000'); assert.equal(a.status, '건설 단계'); assert.equal(a.units, 120); assert.equal(a.records, 2);
  assert.equal(a.name, '테스트아파트 신축공사'); assert.equal(a.label, '테스트'); assert.equal(a.jibun, '569');
  assert.equal(a.approvedAt, '2025-06-01'); assert.equal(a.startedAt, '2025-09-01'); assert.equal(a.completedAt, null); assert.equal(a.plannedCompletion, '2028-12-31');
  assert.deepEqual(a.refs, ['1', '2']); assert.equal(a.address, '경기도 하남시 덕풍동 569번지'); assert.equal(a.mainBldCnt, 3);
  assert.equal(b.pnu, '4145010800100010002'); assert.equal(b.status, '입주 단계'); assert.equal(b.completedAt, '2020-06-01'); assert.equal(b.plannedCompletion, null); assert.equal(b.jibun, '1-2');
});

test('aggregate: 이름이 없으면 번지로, 정렬은 건설 단계 → 계획 → 입주 단계 안에서 세대수 큰 순, 미래 실제 날짜는 계획', () => {
  const out = P.aggregate([
    rec({ bun: '0010', bldNm: ' ', totHhldCnt: 40, mgmHsrgstPk: 10 }), rec({ bun: '0011', bldNm: '큰계획', totHhldCnt: 300, mgmHsrgstPk: 11, apprvDay: '20270101' }),
    rec({ bun: '0012', bldNm: '작은계획', totHhldCnt: 60, mgmHsrgstPk: 12 }), rec({ bun: '0013', bldNm: '공사중', totHhldCnt: 20, mgmHsrgstPk: 13, stcnsDay: '20250101' }),
  ], NOW);
  assert.deepEqual(out.projects.map((p) => p.label), ['공사중', '큰계획', '작은계획', '10번지']);
  assert.deepEqual(out.projects.map((p) => p.status), ['건설 단계', '계획', '계획', '계획']);
  assert.equal(out.projects[3].name, '10번지'); assert.equal(out.projects[1].approvedAt, null);                   // 미래 승인일은 suspect 라 쓰지 않음
  assert.deepEqual(P.aggregate([], NOW), { projects: [], blocks: [], skipped: { notCandidate: 0, noPnu: 0 } });
  assert.deepEqual(P.aggregate(null, NOW).projects, []);
});

test('ymdLoose·monthsBetween: 예정일은 YYYYMMDD·YYYYMM·YYYY 로 섞여 오고, 그 기간의 마지막 날로 경과를 센다', () => {
  assert.deepEqual(P.ymdLoose('20250101'), { iso: '2025-01-01', end: '2025-01-01' });
  assert.deepEqual(P.ymdLoose('200407'), { iso: '2004-07', end: '2004-07-31' });
  assert.deepEqual(P.ymdLoose('202402'), { iso: '2024-02', end: '2024-02-29' });
  assert.deepEqual(P.ymdLoose('2004'), { iso: '2004', end: '2004-12-31' });
  for (const bad of [' ', '', null, undefined, '202613', '202600', '1800', '20250230', 'abcd', '2004-07']) assert.equal(P.ymdLoose(bad), null, String(bad));
  assert.equal(P.monthsBetween('2025-12-31', NOW), 9); assert.equal(P.monthsBetween('2026-10-05', NOW), 0); assert.equal(P.monthsBetween('2026-10-04', NOW), 0); assert.equal(P.monthsBetween('2026-09-05', NOW), 1);
  assert.equal(P.monthsBetween('2027-01-01', NOW), 0);                                                              // 아직 안 지났으면 0
});

test('aggregate: 예정일이 지났는데 기록이 없으면 overdue(착공/준공)를 덧붙이고, 부분 날짜·예정일 없음·이미 입주는 건드리지 않는다', () => {
  const r = (over) => Object.assign({ sigunguCd: '11290', bjdongCd: '13800', bun: '0025', ji: '0055', platGbCd: '0', purpsCdNm: '공동주택', totHhldCnt: 100, bldNm: '구역', mgmHsrgstPk: 1, apprvDay: '20150501', stcnsDay: '', useInsptDay: '', mainBldCnt: 1 }, over);
  const one = (over) => P.aggregate([r(over)], NOW).projects[0];
  const a = one({ stcnsSchedDay: '20251231', useInsptSchedDay: '20291231' });
  assert.equal(a.status, '계획'); assert.equal(a.plannedStart, '2025-12-31'); assert.deepEqual(a.overdue, { kind: '착공', plannedAt: '2025-12-31', months: 9 }); assert.equal(a.plannedCompletion, '2029-12-31');
  const future = one({ stcnsSchedDay: '20270301' }); assert.equal(future.overdue, null); assert.equal(future.plannedStart, '2027-03-01');
  const old = one({ apprvDay: '20030630', stcnsSchedDay: ' ', useInsptSchedDay: '200603' }); assert.equal(old.overdue, null); assert.equal(old.plannedStart, null); assert.equal(old.plannedCompletion, '2006-03');   // 예정일 없는 옛 조합 허가
  const building = one({ stcnsDay: '20250101', useInsptSchedDay: '201911' }); assert.equal(building.status, '건설 단계'); assert.deepEqual(building.overdue, { kind: '준공', plannedAt: '2019-11', months: 82 }); assert.equal(building.plannedStart, null);
  const buildingOk = one({ stcnsDay: '20250101', useInsptSchedDay: '20281231' }); assert.equal(buildingOk.overdue, null);
  const done = one({ stcnsDay: '20250101', useInsptDay: '20260101', stcnsSchedDay: '20240101', useInsptSchedDay: '20250101' }); assert.equal(done.status, '입주 단계'); assert.equal(done.overdue, null); assert.equal(done.plannedStart, null); assert.equal(done.plannedCompletion, null);
  const multi = P.aggregate([r({ mgmHsrgstPk: 1, stcnsSchedDay: '20240320' }), r({ mgmHsrgstPk: 2, stcnsSchedDay: '20260501', apprvDay: '20250101' })], NOW).projects[0];
  assert.equal(multi.overdue.plannedAt, '2026-05-01'); assert.equal(multi.overdue.months, 5);                        // 기록이 여럿이면 가장 늦은 예정일
});

test('unlocatedReason: 입주 단계는 합필·분할, 산 지번·BL 은 택지개발지구, 15년 넘은 허가, 그 밖은 원인 미상', () => {
  assert.match(P.unlocatedReason({ status: '입주 단계', pnu: '1129013800101440024' }, NOW), /합필·분할/);
  assert.match(P.unlocatedReason({ status: '계획', pnu: '4145011600200010001', name: '위례' }, NOW), /택지개발지구/);       // 산(대지구분 2)
  assert.match(P.unlocatedReason({ status: '계획', pnu: '4145011600100010001', name: '위례지구 A3-3a BL 공동주택' }, NOW), /택지개발지구/);
  assert.match(P.unlocatedReason({ status: '계획', pnu: '4145010800104740006', name: '조합', approvedAt: '2003-06-30' }, NOW), /15년 넘은 허가/);
  assert.match(P.unlocatedReason({ status: '계획', pnu: '4145010800104740006', name: '신규', approvedAt: '2024-06-30' }, NOW), /원인 미상/);
  assert.match(P.unlocatedReason({ status: '건설 단계', pnu: '4145010800104740006', name: '신규' }, NOW), /원인 미상/);
});

test('aggregate: 공공주택지구의 블록 단위 허가(platGbCd 2)는 PNU 가 없어 지도에는 못 올리지만 blocks 로 모아 알린다(같은 블록은 하나로)', () => {
  const blk = (over) => Object.assign({ sigunguCd: '41450', bjdongCd: '11400', bun: '0000', ji: '0000', platGbCd: '2', purpsCdNm: '공동주택', totHhldCnt: 600, bldNm: 'LH아파트', block: 'B1BL', mgmHsrgstPk: 1, apprvDay: '20101230', stcnsDay: '', useInsptDay: '', platPlc: '경기도 하남시 감일동 블록' }, over);
  const out = P.aggregate([
    blk({ mgmHsrgstPk: 1 }), blk({ mgmHsrgstPk: 2, apprvDay: '20120101', totHhldCnt: 700, bldNm: 'LH아파트 B1BL' }),                                // 같은 블록의 변경허가
    blk({ mgmHsrgstPk: 3, block: 'A5블록', bldNm: '하남감일A5BL 아파트', totHhldCnt: 617, stcnsDay: '20190101' }),
    blk({ mgmHsrgstPk: 4, block: 'B-4BL', bldNm: '감일 B-4BL', totHhldCnt: 595, stcnsDay: '20190101', useInsptDay: '20220101' }),
    blk({ mgmHsrgstPk: 5, block: '', bldNm: '이름뿐', platGbCd: '2' }), blk({ mgmHsrgstPk: 6, bun: '0000', platGbCd: '0', bldNm: '블록 아님' }),   // 대지인데 본번 0 → 블록이 아니라 그냥 PNU 없음
  ], NOW);
  assert.deepEqual(out.projects, []); assert.deepEqual(out.skipped, { notCandidate: 0, noPnu: 5 + 1 });
  assert.deepEqual(out.blocks.map((b) => [b.block, b.status, b.units, b.records]), [['A5블록', '건설 단계', 617, 1], ['B1BL', '계획', 700, 2], [null, '계획', 600, 1], ['B-4BL', '입주 단계', 595, 1]]);
  assert.equal(out.blocks[1].name, 'LH아파트 B1BL'); assert.equal(out.blocks[1].approvedAt, '2012-01-01');             // 가장 최근 허가의 이름·승인일
});

/* ---------- 건물대장 보강(2026-10-05 하남·장위 실측값으로) ---------- */
const L = (over) => Object.assign({ pnu: '4145011500104580000', bjd: '4145011500', name: '힐스테이트 포웰시티', units: 932, platArea: 44521, useAprDay: '2020-10-27', platPlc: '경기도 하남시 감이동 458번지', purps: '공동주택' }, over);

test('ledgerRow: 총괄표제부 행에서 지번(PNU)·세대수·대지면적·사용승인일(ISO)만, 지번이 안 만들어지거나 값이 이상하면 안전하게', () => {
  const r = P.ledgerRow({ sigunguCd: '41450', bjdongCd: '11500', bun: '0458', ji: '0000', platGbCd: '0', hhldCnt: 932, platArea: 44521, useAprDay: '20201027', bldNm: ' 힐스테이트 포웰시티 ', platPlc: '경기도 하남시 감이동 458번지', mainPurpsCdNm: '공동주택' });
  assert.deepEqual(r, L({ name: '힐스테이트 포웰시티' }));
  assert.equal(P.ledgerRow({ sigunguCd: '41450', bjdongCd: '11500', bun: '0000', ji: '0000', platGbCd: '2' }), null);                  // 블록(지번 없음)
  const odd = P.ledgerRow({ sigunguCd: '41450', bjdongCd: '11500', bun: '0001', ji: '0002', platGbCd: '0', hhldCnt: 0, platArea: ' ', useAprDay: ' ', bldNm: null });
  assert.deepEqual([odd.units, odd.platArea, odd.useAprDay, odd.name], [0, 0, null, '']);
});

test('matchLedger: 세대수가 같고 대지면적 오차 2% 이내면 일치(오차 0.0%·0.1% 실측), 세대수만 같은 우연(면적 29.6% 차이)은 거절', () => {
  const rows = [L(), L({ pnu: '4145011500104590000', name: '다른곳', units: 932, platArea: 50000 }), L({ pnu: '4145011100109040000', name: '미사강변 한신휴플러스', units: 763, platArea: 38230 })];
  const exact = P.matchLedger({ units: 932, platArea: 44521, name: 'LH아파트' }, rows);
  assert.equal(exact.row.pnu, '4145011500104580000'); assert.equal(exact.diff, 0);
  const near = P.matchLedger({ units: 932, platArea: 44480, name: '' }, rows); assert.equal(near.row.pnu, '4145011500104580000'); assert.ok(near.diff < 0.001);
  assert.equal(P.matchLedger({ units: 763, platArea: 29504, name: '하남교산 A8블록 공공주택' }, rows), null);       // 교산 A8 ↔ 망월동 904번지: 세대수만 같음
  assert.equal(P.matchLedger({ units: 932, platArea: 0, name: 'x' }, rows), null);                                  // 허가 쪽 대지면적을 모르고 이름도 구별이 안 되면 채택하지 않는다
  assert.equal(P.matchLedger({ units: 932, platArea: 0, name: 'LH아파트' }, rows), null);
  assert.equal(P.matchLedger({ units: 0, platArea: 44521 }, rows), null); assert.equal(P.matchLedger(null, rows), null); assert.equal(P.matchLedger({ units: 932, platArea: 1 }, []), null);
  assert.equal(P.matchLedger({ units: 932, platArea: 44521 }, [L({ platArea: 0 })]), null);                         // 대장 쪽 면적이 없으면 제외
});

test('matchLedger: 후보가 둘이면 가장 가까운 것이 0.3%p 이상 가까울 때만, 아니면 이름이 같은 하나로, 그래도 못 가리면 모호(채택 안 함)', () => {
  const a = L({ pnu: '4145011500105010000', name: 'e편한세상감일', units: 866, platArea: 43339, useAprDay: '2021-09-07' });
  const b = L({ pnu: '4145011500105030000', name: '하남감일 제일풍경채', units: 866, platArea: 43306, useAprDay: '2023-03-31' });   // B-9블록: 두 단지가 0.0%·0.1%
  const amb = P.matchLedger({ units: 866, platArea: 43339, name: '하남감일 공공주택지구 B-9BL' }, [a, b]);
  assert.ok(amb.ambiguous && amb.ambiguous.length === 2);
  assert.equal(P.matchLedger({ units: 866, platArea: 43339, name: '하남감일 제일풍경채 아파트' }, [a, b]).row.pnu, b.pnu);   // 일반적이지 않은 이름이면 이름으로
  const far = L({ pnu: '4145011500105050000', units: 866, platArea: 43900 });
  assert.equal(P.matchLedger({ units: 866, platArea: 43339, name: 'LH아파트' }, [a, far]).row.pnu, a.pnu);               // 1.3% 차이가 0.0% 보다 0.3%p 넘게 멀다
  assert.deepEqual([P.isGenericName('LH아파트'), P.isGenericName('하남감일 공공주택사업지구 내 B-4BL'), P.isGenericName('하남감일스윗시티'), P.isGenericName(' ')], [true, true, false, true]);
});

test('ledgerCompletion: 허가 이후·오늘 이전의 사용승인일만 준공으로(옛 건물·미래·없음은 안 씀)', () => {
  assert.equal(P.ledgerCompletion(L(), '2018-01-01', NOW), '2020-10-27');
  assert.equal(P.ledgerCompletion(L({ useAprDay: '1993-06-18' }), '2015-05-01', NOW), null);                         // 정비구역의 옛 건물
  assert.equal(P.ledgerCompletion(L({ useAprDay: '2027-01-01' }), '2015-05-01', NOW), null);
  assert.equal(P.ledgerCompletion(L({ useAprDay: null }), '2015-05-01', NOW), null);
  assert.equal(P.ledgerCompletion(null, '2015-05-01', NOW), null); assert.equal(P.ledgerCompletion(L(), null, NOW), '2020-10-27');
});

test('aggregate: 사업·블록에 최신 허가의 관리번호(latestRef)를 남겨 대지위치 조회와 잇는다, 블록에는 착공·준공일도', () => {
  const r = (over) => Object.assign({ sigunguCd: '41450', bjdongCd: '11400', bun: '0000', ji: '0000', platGbCd: '2', purpsCdNm: '공동주택', totHhldCnt: 932, bldNm: '힐스테이트 포웰시티', block: 'B6', mgmHsrgstPk: 11, apprvDay: '20170101', stcnsDay: '20180101', useInsptDay: '20201027' }, over);
  const out = P.aggregate([r(), r({ mgmHsrgstPk: 12, apprvDay: '20190101' }), r({ bun: '0010', platGbCd: '0', mgmHsrgstPk: 21, bldNm: '지번 사업' })], NOW);
  assert.equal(out.blocks.length, 1); assert.equal(out.blocks[0].latestRef, '12'); assert.equal(out.blocks[0].startedAt, '2018-01-01'); assert.equal(out.blocks[0].completedAt, '2020-10-27');
  assert.equal(out.projects[0].latestRef, '21');
});

test('matchLedger: 허가에 대지면적이 없으면(산 지번 등) 세대수와 구별되는 이름이 같은 대장이 딱 하나일 때만(꿈의숲 푸르지오 714세대 실측), 이름이 다르거나 둘이면 거절·모호', () => {
  const k = L({ pnu: '1129013600102280000', name: '꿈의숲 푸르지오', units: 714, platArea: 32350.9, useAprDay: '2010-04-29', platPlc: '서울특별시 성북구 하월곡동 228번지' });
  const rows = [k, L({ pnu: '1129013600102290000', name: '다른 단지', units: 714, platArea: 50000 }), L({ pnu: '1129013600102300000', name: '꿈의숲 푸르지오', units: 500 })];
  const m = P.matchLedger({ units: 714, platArea: 0, name: '꿈의숲 푸르지오' }, rows);
  assert.equal(m.row.pnu, k.pnu); assert.equal(m.diff, null); assert.equal(m.by, 'name');
  assert.equal(P.matchLedger({ units: 714, platArea: 0, name: '꿈의숲 푸르지오 신축공사' }, rows).row.pnu, k.pnu);       // '신축공사'는 이름 비교에서 뺀다
  assert.equal(P.matchLedger({ units: 714, platArea: 0, name: '엉뚱한 이름' }, rows), null);
  const part = P.matchLedger({ units: 714, platArea: 20141, name: '꿈의숲 푸르지오' }, rows);                              // 허가 대지면적이 일부 필지뿐이라 38% 어긋나도 세대수·이름이 같으면
  assert.equal(part.row.pnu, k.pnu); assert.equal(part.by, 'name'); assert.equal(P.matchLedger({ units: 714, platArea: 20141, name: '엉뚱한 이름' }, rows), null);
  assert.equal(P.matchLedger({ units: 715, platArea: 0, name: '꿈의숲 푸르지오' }, rows), null);                          // 세대수가 다르면 이름이 같아도 안 됨
  assert.ok(P.matchLedger({ units: 714, platArea: 0, name: '꿈의숲 푸르지오' }, [k, { ...k, pnu: '1129013600102310000' }]).ambiguous);
});
