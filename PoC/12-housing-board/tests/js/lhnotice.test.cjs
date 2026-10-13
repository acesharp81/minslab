'use strict';
/* lib/lhnotice.js — LH 분양임대공고문(15058530)·공급정보(15056765) 변환·시군구 거르기. 네트워크 없이 시험한다. 응답 모양과 제목은 2026-10-06 실측에서 가져왔다. */
const test = require('node:test');
const assert = require('node:assert/strict');
const L = require('../../lib/lhnotice.js');

const row = (over) => ({ PAN_ID: '2015122300020858', PAN_NM: '인천석남 어울림센터 행복주택 입주자 최초모집', CNP_CD_NM: '인천광역시', UPP_AIS_TP_CD: '06', AIS_TP_CD_NM: '임대주택', UPP_AIS_TP_NM: '임대주택', PAN_SS: '공고중',
  PAN_NT_ST_DT: '2026.09.30', CLSG_DT: '2026.10.20', SPL_INF_TP_CD: '063', CCR_CNNT_SYS_DS_CD: '03', ALL_CNT: '134',
  DTL_URL: 'https://apply.lh.or.kr/lhapply/apply/wt/wrtanc/selectWrtancInfo.do?panId=2015122300020858&ccrCnntSysDsCd=03&uppAisTpCd=06&aisTpCd=10&mi=1026', ...over });

test('dateOf·safeUrl·titleKey: 점 날짜(달력에 없으면 null)·LH 링크만·글자와 숫자만 남긴 제목 키', () => {
  assert.equal(L.dateOf('2026.10.02'), '2026-10-02'); assert.equal(L.dateOf('2026-10-02'), '2026-10-02');
  for (const bad of ['2026.02.30', '20261002', '', null, '26.10.02']) assert.equal(L.dateOf(bad), null);
  assert.equal(L.safeUrl('https://apply.lh.or.kr/x'), 'https://apply.lh.or.kr/x'); assert.equal(L.safeUrl('http://evil.example/x'), ''); assert.equal(L.safeUrl('https://apply.lh.or.kr.evil.example/x'), '');
  assert.equal(L.titleKey("익산인화 행복주택 모집 공고('26.10.02)"), L.titleKey('익산인화 행복주택 모집 공고(26.10.02)'));
  assert.notEqual(L.titleKey('공고 1'), L.titleKey('공고 2'));
});

test('notice: 주택 공고만(분양 05·39·54 → sale, 임대 06·13 → rental), 진행 중만, 마이홈 공고와 같은 모양에 source:lh', () => {
  const n = L.notice(row());
  assert.deepEqual(n, { id: 'lh-2015122300020858', kind: 'rental', title: '인천석남 어울림센터 행복주택 입주자 최초모집', agency: '한국토지주택공사', status: '공고중', housingType: '임대주택', supplyType: '임대주택',
    complex: null, units: null, address: null, pnu: null, announcedAt: '2026-09-30', applyFrom: null, applyTo: '2026-10-20', url: row().DTL_URL, source: 'lh' });
  for (const [code, kind] of [['05', 'sale'], ['39', 'sale'], ['54', 'sale'], ['06', 'rental'], ['13', 'rental']]) assert.equal(L.notice(row({ UPP_AIS_TP_CD: code })).kind, kind);
  for (const code of ['01', '22', '', '99']) assert.equal(L.notice(row({ UPP_AIS_TP_CD: code })), null, `유형 ${code} 는 주택 공고가 아님`);
  for (const ss of ['접수마감', '상담요청', '']) assert.equal(L.notice(row({ PAN_SS: ss })), null);
  for (const st of L.STATUSES) assert.ok(L.notice(row({ PAN_SS: st })), st);
  assert.equal(L.notice(row({ PAN_NM: ' ' })), null); assert.equal(L.notice(row({ PAN_ID: '' })), null); assert.equal(L.notice(null), null);
  assert.equal(L.notice(row({ DTL_URL: 'http://evil', DTL_URL_MOB: 'https://apply.lh.or.kr/m' })).url, 'https://apply.lh.or.kr/m');
});

test('placeWords·dongParts·sidoOf·sidoStem', () => {
  assert.deepEqual(L.placeWords('하남시'), ['하남시', '하남']); assert.deepEqual(L.placeWords('영통구'), ['영통구', '영통']); assert.deepEqual(L.placeWords('서구'), ['서구']); assert.deepEqual(L.placeWords('중구'), ['중구']);
  assert.deepEqual(L.placeWords('울릉군'), ['울릉군', '울릉']); assert.deepEqual(L.placeWords('가'), []);
  assert.deepEqual(L.dongParts('석남동'), { full: '석남동', stem: '석남' }); assert.deepEqual(L.dongParts('을지로3가'), { full: '을지로3가', stem: '을지로' }); assert.deepEqual(L.dongParts('장위1동'), { full: '장위1동', stem: '장위' });
  assert.deepEqual(L.dongParts('중동'), { full: '중동', stem: '' }, '줄임이 한 글자면 쓰지 않는다'); assert.equal(L.dongParts('오정').stem, '');
  assert.equal(L.sidoOf('인천광역시 외'), '인천광역시'); assert.equal(L.sidoOf('전국'), '전국'); assert.equal(L.sidoOf(null), '');
  assert.deepEqual(['경기도', '제주특별자치도', '인천광역시', '서울특별시', '세종특별자치시', '전남광주통합특별시'].map(L.sidoStem), ['경기', '제주', '인천', '서울', '세종', '전남광주통합']);
});

const HANAM = '경기도 하남시', HANAM_UMD = ['감일동', '풍산동', '덕풍동', '미사동'];
test('inRegion: 시도가 같고 제목에 시군구 이름이나 법정동 이름이 있을 때만(실측 제목)', () => {
  const t = (name, cnp, region, umd, expect) => assert.equal(L.inRegion(row({ PAN_NM: name, CNP_CD_NM: cnp }), region, umd), expect, `${cnp} ${name} → ${region}`);
  t('하남시 신혼희망타운 행복주택 예비입주자 모집공고(2026.10.01)', '경기도', HANAM, HANAM_UMD, true);
  t('하남감일8단지. 미사13단지 영구임대주택 예비입주자 모집공고', '경기도', HANAM, HANAM_UMD, true);           // 시 이름 줄임('하남')
  t('[정정공고]경기도 하남시 청년 매입임대', '경기도', HANAM, [], true);
  t('덕풍동 다가구 매입임대', '경기도', HANAM, HANAM_UMD, true);                                                  // 법정동 전체 이름
  t('하남시 신혼희망타운', '서울특별시', HANAM, HANAM_UMD, false);                                                // 시도가 다르면 아니다
  t('하남시 전국 공고', '전국', HANAM, HANAM_UMD, false);
  t('경기 성남금토 A-4블록 신혼희망타운', '경기도', HANAM, HANAM_UMD, false);
  assert.equal(L.inRegion(row({ PAN_NM: '하남시 행복주택', CNP_CD_NM: '경기도 외' }), HANAM, []), true, "'경기도 외' 는 경기도 공고로 본다");
  assert.equal(L.inRegion(row({ PAN_NM: '' }), HANAM, []), false); assert.equal(L.inRegion(null, HANAM, []), false); assert.equal(L.inRegion(row(), '경기도', []), false);
  // 구가 있는 시: 구 이름만(시 이름 '수원'은 다른 구의 공고에도 쓰인다). 시 전체는 시 이름이면 된다
  const YT = '경기도 수원시 영통구', YT_UMD = ['매탄동', '원천동', '영통동'];
  t('수원당수 A-3블록 신혼희망타운(공공분양) 잔여세대', '경기도', YT, YT_UMD, false);
  t('수원시 수원매탄6 국민임대 예비입주자 모집공고', '경기도', YT, YT_UMD, true);                                  // '수원'+'매탄'(영통구 매탄동)
  t('영통 행복주택', '경기도', YT, YT_UMD, true);
  t('수원당수 A-3블록 신혼희망타운(공공분양) 잔여세대', '경기도', '경기도 수원시', [], true);
  // 줄임말만으로는 안 된다: 다른 시의 같은 동 이름('전주평화', '부천대장')
  const IKSAN = '전북특별자치도 익산시', IKSAN_UMD = ['평화동', '부송동', '인화동'], SN = '경기도 성남시 분당구', SN_UMD = ['대장동', '금토동', '판교동'];
  t('전주평화1 영구임대주택 입주자격완화 예비입주자 모집공고', '전북특별자치도', IKSAN, IKSAN_UMD, false);
  t('익산평화 공공분양주택 추가 입주자모집', '전북특별자치도', IKSAN, IKSAN_UMD, true);
  t('부천대장 A5·A6블록 신혼희망타운 행복주택 입주자 최초모집', '경기도', SN, SN_UMD, false);
  t('성남금토 A-4블록 신혼희망타운 행복주택 입주자 모집공고', '경기도', SN, SN_UMD, true);
  // 시도 줄임말과 같은 시 이름: '[제주지역본부-서귀포시]' 가 제주시 공고가 되면 안 된다
  const JEJU = '제주특별자치도 제주시';
  t('[제주지역본부-서귀포시] 든든전세주택 (예비)입주자 모집 공고', '제주특별자치도', JEJU, ['일도일동', '삼도이동'], false);
  t('[제주지역본부-제주시] 청년 매입임대주택 예비입주자 모집 공고', '제주특별자치도', JEJU, [], true);
  t('인천 서구 행복주택', '인천광역시', '인천광역시 서구', [], true);
  t('인천석남 어울림센터 행복주택', '인천광역시', '인천광역시 서구', ['석남동', '가좌동'], true);                       // 시도 줄임('인천')+동 줄임('석남')
  t('인천 중구 행복주택', '인천광역시', '인천광역시 서구', [], false);
});

test('forRegion: 진행 중 주택 공고만, 공고일 최신 순, 같은 id 한 번, 마이홈과 같은 제목은 제외, 공급정보를 부를 연결값(_supply)을 붙인다', () => {
  const rows = [
    row({ PAN_ID: 'A', PAN_NM: '하남시 행복주택 A', PAN_NT_ST_DT: '2026.09.01' }), row({ PAN_ID: 'B', PAN_NM: '하남시 행복주택 B', PAN_NT_ST_DT: '2026.10.01', CNP_CD_NM: '경기도', UPP_AIS_TP_CD: '05' }),
    row({ PAN_ID: 'A', PAN_NM: '하남시 행복주택 A', PAN_NT_ST_DT: '2026.09.01' }), row({ PAN_ID: 'C', PAN_NM: '하남시 상가', UPP_AIS_TP_CD: '22' }), row({ PAN_ID: 'D', PAN_NM: '하남시 행복주택 마이홈', PAN_SS: '공고중' }),
    row({ PAN_ID: 'E', PAN_NM: '하남시 행복주택 E', PAN_SS: '접수마감' }), row({ PAN_ID: 'F', PAN_NM: '하남시 행복주택 F', CNP_CD_NM: '서울특별시' }),
  ].map((r) => ({ ...r, CNP_CD_NM: r.CNP_CD_NM === '인천광역시' ? '경기도' : r.CNP_CD_NM }));
  const out = L.forRegion(rows, HANAM, HANAM_UMD, new Set([L.titleKey('하남시 행복주택 (마이홈)')]));
  assert.deepEqual(out.map((n) => n.id), ['lh-B', 'lh-A'], 'D 는 괄호만 다른 같은 제목이라 마이홈 쪽만 남기고 뺀다. 접수마감·상가·다른 시도·중복 id 도 빠진다');
  assert.deepEqual(out[0]._supply, { PAN_ID: 'B', SPL_INF_TP_CD: '063', CCR_CNNT_SYS_DS_CD: '03', UPP_AIS_TP_CD: '05' });
  assert.equal(L.forRegion(null, HANAM).length, 0);
});

test('supplyOf: 단지명(중복 제거, 3곳부터 "외 N")과 금회공급 세대수의 합(없으면 세대수), 쓸 것이 없으면 null', () => {
  const blk = (rows) => [{ dsSch: [{}] }, { dsList01Nm: [{}], resHeader: [{ SS_CODE: 'Y' }], dsList01: rows }];
  const real = [{ SBD_LGO_NM: '인천석남 어울림센터 행복주택', HTY_NNA: '21A', NOW_HSH_CNT: '56', HSH_CNT: '62' }, { SBD_LGO_NM: '인천석남 어울림센터 행복주택', HTY_NNA: '21B', NOW_HSH_CNT: '4', HSH_CNT: '10' }];
  assert.deepEqual(L.supplyOf(blk(real)), { complex: '인천석남 어울림센터 행복주택', units: 60 });
  assert.deepEqual(L.supplyOf(blk([{ SBD_LGO_NM: 'a', HSH_CNT: '1,200' }, { SBD_LGO_NM: 'b', NOW_HSH_CNT: '' , HSH_CNT: '30' }])), { complex: 'a, b', units: 1230 });
  assert.deepEqual(L.supplyOf(blk(['a', 'b', 'c', 'd'].map((n) => ({ SBD_LGO_NM: n, NOW_HSH_CNT: '1' })))), { complex: 'a, b 외 2', units: 4 });
  assert.deepEqual(L.supplyOf(blk([{ SBD_LGO_NM: 'x', NOW_HSH_CNT: '공고문 참조' }])), { complex: 'x', units: null });
  assert.deepEqual(L.supplyOf(blk([{ NOW_HSH_CNT: '5' }])), { complex: null, units: 5 });
  for (const none of [blk([]), blk([{}]), [], null, {}, [{ dsSch: [] }]]) assert.equal(L.supplyOf(none), null);
});

const ok = (json) => ({ ok: true, status: 200, text: async () => JSON.stringify(json) });
const raw = (status, text) => ({ ok: status < 400, status, text: async () => text });
const LIST = (rows) => [{ dsSch: [{}] }, { dsList: rows, resHeader: [{ RS_DTTM: '20261006', SS_CODE: 'Y' }] }];
const go = (doFetch, over = {}) => L.fetchLh({ doFetch, sleep: async () => {}, url: L.LIST_URL, params: { serviceKey: 'K+/=', PG_SZ: '100' }, ...over });

test('listOf: 행과 전체 건수(ALL_CNT), 빈 목록은 0', () => {
  assert.deepEqual(L.listOf(LIST([row({ ALL_CNT: '134' }), row()])), { rows: [row({ ALL_CNT: '134' }), row()], total: 134 });
  assert.deepEqual(L.listOf(LIST([])), { rows: [], total: 0 });
  assert.deepEqual(L.listOf(LIST([row({ ALL_CNT: '' })])).total, 1); assert.deepEqual(L.listOf(null), { rows: [], total: 0 });
});

test('fetchLh: 정상·빈 목록, 키는 한 번만 인코딩, SS_CODE 가 Y 가 아니면 오류, 모양이 이상하면 다시 시도', async () => {
  const seen = [];
  assert.deepEqual(L.listOf(await go(async (url) => { seen.push(url); return ok(LIST([row()])); })).rows.length, 1);
  assert.ok(seen[0].startsWith(`${L.LIST_URL}?`)); assert.ok(seen[0].includes('serviceKey=K%2B%2F%3D'));
  assert.deepEqual(L.listOf(await go(async () => ok(LIST([])))).rows, []);
  await assert.rejects(go(async () => ok([{ dsSch: [] }, { resHeader: [{ SS_CODE: 'N' }] }])), /SS_CODE N/);
  let n = 0; await assert.rejects(go(async () => { n++; return ok({ nope: 1 }); }), /응답 모양 이상/); assert.equal(n, 3);
});

test('fetchLh: 일시 오류는 다시, 4xx 는 바로, 하루 한도는 e.quota, 초당 한도는 쉬었다 다시(끝내 안 풀리면 e.throttled), 오류 문구에 키가 없다', async () => {
  for (const [label, bad] of [['network', () => { throw new Error('x'); }], ['HTTP 502', () => raw(502, '')], ['빈 본문', () => raw(200, ' ')], ['JSON 아님', () => raw(200, '<html>')]]) {
    let n = 0; await assert.rejects(go(async () => { n++; return bad(); }), (e) => e.message === label && !e.quota); assert.equal(n, 3, label);
  }
  let m = 0; await assert.rejects(go(async () => { m++; return raw(403, '<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</errMsg></cmmMsgHeader></OpenAPI_ServiceResponse>'); }), (e) => e.message === 'HTTP 403' && !/K\+/.test(e.message)); assert.equal(m, 1);
  const xml = '<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR</returnAuthMsg><returnReasonCode>22</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>';
  for (const bad of [() => raw(429, ''), () => raw(200, xml)]) await assert.rejects(go(async () => bad()), (e) => e.quota === true);
  const perSec = '<cmmMsgHeader><returnAuthMsg>LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR</returnAuthMsg></cmmMsgHeader>';
  const waits = []; let k = 0;
  assert.equal(L.listOf(await go(async () => (++k < 3 ? raw(429, perSec) : ok(LIST([row()]))), { sleep: async (ms) => { waits.push(ms); } })).rows.length, 1); assert.deepEqual(waits, [1100, 2200]);
  await assert.rejects(go(async () => raw(429, perSec)), (e) => e.throttled === true && !e.quota);
});
