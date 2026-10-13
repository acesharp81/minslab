'use strict';
/* lib/datagokr.js — 건축HUB 22자리 관리번호가 JSON 숫자로 와서 정밀도를 잃는 문제(실측 2026-10-06)와 fetchPage 의 기본 동작 */
const test = require('node:test');
const assert = require('node:assert/strict');
const { fetchPage, protectBigInts } = require('../../lib/datagokr.js');

const RAW = '{"response":{"header":{"resultCode":"00"},"body":{"totalCount":3,"items":{"item":['
  + '{"mgmHsrgstPk":1000000000000000339484,"bldNm":"가","platArea":123.45},{"mgmHsrgstPk":1000000000000000339485,"bldNm":"나"},{"mgmHsrgstPk":1234567890123,"bldNm":"다","mgmUpBldrgstPk":1000000000000000000001}]}}}}';

test('protectBigInts: 16자리 이상 mgm…Pk 숫자만 문자열로 감싼다(13자리 이하·다른 필드는 그대로)', () => {
  const out = JSON.parse(protectBigInts(RAW)).response.body.items.item;
  assert.deepEqual(out.map((r) => r.mgmHsrgstPk), ['1000000000000000339484', '1000000000000000339485', 1234567890123]);
  assert.equal(out[2].mgmUpBldrgstPk, '1000000000000000000001'); assert.equal(out[0].platArea, 123.45);
  assert.equal(protectBigInts('{"mgmHsrgstPk" : 1000000000000000339484}'), '{"mgmHsrgstPk" : "1000000000000000339484"}');
  assert.equal(protectBigInts('{"mgmHsrgstPk":"1000000000000000339484"}'), '{"mgmHsrgstPk":"1000000000000000339484"}', '이미 문자열이면 그대로');
  assert.equal(protectBigInts('{"other":1000000000000000339484}'), '{"other":1000000000000000339484}', '다른 필드는 건드리지 않는다');
  assert.equal(protectBigInts('{"mgmHsrgstPk":123456789012345}'), '{"mgmHsrgstPk":123456789012345}', '15자리는 정확히 표현되어 그대로');
});

test('숫자로 파싱하면 서로 다른 관리번호가 뭉개진다(보호 전의 결함 재현) — fetchPage 는 자릿수를 지킨다', async () => {
  const lossy = JSON.parse(RAW).response.body.items.item;
  assert.equal(String(lossy[0].mgmHsrgstPk), String(lossy[1].mgmHsrgstPk), '보호 없이 파싱하면 다른 값이 같아진다');
  const got = await fetchPage({ doFetch: async () => ({ ok: true, status: 200, text: async () => RAW }), sleep: async () => {}, url: 'https://x.example/api', params: { a: '1' } });
  assert.deepEqual(got.items.map((r) => String(r.mgmHsrgstPk)), ['1000000000000000339484', '1000000000000000339485', '1234567890123']);
  assert.equal(new Set(got.items.map((r) => String(r.mgmHsrgstPk))).size, 3);
  assert.equal(got.total, 3);
});
