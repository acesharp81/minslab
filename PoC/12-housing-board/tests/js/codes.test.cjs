/* lib/codes.js — 표준코드(법정동·시군구·PNU) 판별 */
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../../lib/codes.js');

test('classify: 자릿수로 종류를 판별하고 8자리 법정동은 00을 붙이며, 시군구 행(…00000)은 시군구로 본다', () => {
  const t = (s) => C.classify(s);
  assert.deepEqual([t('28245').type, t('28245').canonical], ['sgg', '28245']);
  const b = t('2824510900'); assert.deepEqual([b.type, b.canonical, b.sgg, b.bjd, b.padded], ['bjd', '2824510900', '28245', '2824510900', false]);
  const e = t('28245109'); assert.deepEqual([e.type, e.canonical, e.padded], ['bjd', '2824510900', true]);
  assert.deepEqual([t('2824500000').type, t('2824500000').canonical], ['sgg', '28245']);
  const p = t('2824511000104790000'); assert.deepEqual([p.type, p.canonical, p.bjd, p.sgg, p.pnu], ['pnu', '2824511000104790000', '2824511000', '28245', '2824511000104790000']);
  assert.deepEqual([t('28').type, t('28').canonical], ['sido', '28']);
  assert.equal(t(' 28245-109 ').canonical, '2824510900');
});

test('classify: 잘못된 입력은 이유를 준다(비어 있음·숫자 아님·모르는 시도·자릿수·PNU 형식)', () => {
  const why = (s) => C.classify(s).reason;
  assert.equal(why(''), 'empty'); assert.equal(why(null), 'empty');
  assert.equal(why('28245a'), 'not-digits'); assert.equal(why('인천'), 'not-digits');
  assert.equal(why('99245'), 'unknown-sido'); assert.equal(why('29200'), 'unknown-sido');      // 광주(29)는 통합 이후 없음
  assert.equal(why('282451'), 'bad-length'); assert.equal(why('1'), 'unknown-sido');
  assert.equal(why('2824511000304790000'), 'bad-pnu');                                          // 대지구분 3
  assert.equal(why('2824511000100000000'), 'bad-pnu');                                          // 본번 0000
  assert.equal(C.classify('12345').ok, true);      // 구조만 본다. 코드가 실제로 있는지는 표준코드 표(resolve)가 확인한다
});

test('parsePnu: 본번·부번·지번과 건축HUB 인자(일반=platGbCd 0, 산=1)', () => {
  const p = C.parsePnu('2824511000104790000');
  assert.deepEqual(p.hub, { sigunguCd: '28245', bjdongCd: '11000', platGbCd: '0', bun: '0479', ji: '0000' });
  assert.equal(p.jibun, '479');
  const q = C.parsePnu('1233010600205460003'); assert.deepEqual([q.hub.platGbCd, q.jibun], ['1', '546-3']);
  assert.equal(C.parsePnu('123'), null);
});

test('bjdParts: 시도·시군구·읍면동·리와 V-World 8자리, 건축HUB 5자리', () => {
  assert.deepEqual(C.bjdParts('2824510900'), { sido: '28', sgg: '28245', umd: '109', ri: '00', vworldEmd8: '28245109', hubBjdongCd: '10900' });
});

test('levelOf·findRow·nameParts: 행정표준코드 행 해석', () => {
  const rows = [{ region_cd: '2824500000', sgg_cd: '245', umd_cd: '000', ri_cd: '00', locatadd_nm: '인천광역시 계양구' },
    { region_cd: '2824510900', sgg_cd: '245', umd_cd: '109', ri_cd: '00', locatadd_nm: '인천광역시 계양구 박촌동' },
    { region_cd: '4817025021', sgg_cd: '170', umd_cd: '250', ri_cd: '21', locatadd_nm: '경상남도 진주시 대평면 어떤리' }, { region_cd: '2800000000', sgg_cd: '000', umd_cd: '000', ri_cd: '00' }];
  assert.deepEqual(rows.map(C.levelOf), ['sgg', 'umd', 'ri', 'sido']);
  assert.equal(C.findRow(rows, '2824510900').locatadd_nm, '인천광역시 계양구 박촌동');
  assert.equal(C.findRow(rows, '1'), null);
  assert.deepEqual(C.nameParts('인천광역시 계양구 박촌동'), { sido: '인천광역시', rest: ['계양구', '박촌동'] });
});

test('KNOWN_SIDO: 전국 표의 시도 16개(광주 29·전남 46은 없음)', () => {
  assert.equal(C.KNOWN_SIDO.size, 16);
  assert.ok(C.KNOWN_SIDO.has('12') && C.KNOWN_SIDO.has('36') && !C.KNOWN_SIDO.has('29') && !C.KNOWN_SIDO.has('46'));
});
