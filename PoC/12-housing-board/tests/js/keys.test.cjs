/* lib/keys.js — 인증키 풀(.env.local 용도별 키, 서비스별 일일 한도, 한도 오류 시 전환) */
const test = require('node:test');
const assert = require('node:assert/strict');
const K = require('../../lib/keys.js');

const T0 = Date.parse('2026-10-05T03:00:00Z');   // 한국시간 12:00
const ENV = {
  DATA_GO_KR_KEY_BUS_2: 'bus+2/key==', DATA_GO_KR_KEY_BUS_1: 'bus+1/key==', DATA_GO_KR_KEY_BUILD_1: 'build-1',
  DATA_GO_KR_KEY_DEMO_1: 'demo%2B1', DATA_GO_KR_SERVICES_BUILD_1: 'hub,tago', DATA_GO_KR_KEY: 'legacy-key',
};
const pool = (env = ENV, clock = { t: T0 }) => ({ p: K.createKeyPool({ env, now: () => clock.t }), clock });

test('loadKeys: 용도·번호별로 읽고 번호 순으로 정렬, %로 인코딩된 값은 한 번 디코딩, 서비스 목록은 소문자 집합', () => {
  const k = K.loadKeys(ENV);
  assert.deepEqual(k.byPurpose.BUS.map((x) => x.label), ['BUS_1', 'BUS_2']);
  assert.equal(k.byPurpose.DEMO[0].value, 'demo+1');
  assert.deepEqual([...k.byPurpose.BUILD[0].services].sort(), ['hub', 'tago']);
  assert.equal(k.byPurpose.BUS[0].services, null);
  assert.equal(k.fallback.label, 'DEFAULT');
  assert.equal(K.loadKeys({}).fallback, null);
  assert.deepEqual(K.loadKeys({ DATA_GO_KR_KEY_BUS_1: '', DATA_GO_KR_KEY_bus_2: 'x', OTHER: 'y' }).byPurpose, {});   // 빈 값·소문자 이름·무관한 변수는 무시
});

test('parseLimits: 서비스별 한도 문자열, 이상한 값은 버린다', () => {
  assert.deepEqual(K.parseLimits('tago=10000, Seoul=500,bad=x,=3,neg=-1'), { tago: 10000, seoul: 500 });
  assert.equal(K.createKeyPool({ env: { DATA_GO_KR_LIMITS: 'seoul=5' } }).limits.seoul, 5);
  assert.equal(K.createKeyPool({ env: {} }).limits.seoul, 1000);          // 서울은 개발계정 1,000건/일이 기본
});

test('pick: 가장 적게 쓴 키를 고르고 같으면 돌려 쓴다, 서비스 목록에 없는 키는 건너뛴다, 용도에 키가 없으면 기본 키', () => {
  const { p } = pool();
  const a = p.pick('BUS', 'tago'); p.record(a.label, 'tago');
  const b = p.pick('BUS', 'tago'); assert.notEqual(a.label, b.label);       // 사용량이 적은 쪽
  p.record(b.label, 'tago');
  const labels = new Set([p.pick('BUS', 'tago').label, p.pick('BUS', 'tago').label]);
  assert.deepEqual([...labels].sort(), ['BUS_1', 'BUS_2']);                  // 같은 사용량이면 돌려 쓴다
  assert.equal(p.pick('BUILD', 'seoul').label, 'DEFAULT');                    // BUILD_1 은 hub,tago 만 신청 → 서울에는 기본 키
  assert.equal(p.pick('BUILD', 'hub').label, 'BUILD_1');
  assert.equal(p.pick('NOPE', 'tago').label, 'DEFAULT');
  assert.equal(K.createKeyPool({ env: {} }).pick('BUS', 'tago'), null);
});

test('한도: 서비스별 한도에 닿으면 그 키는 건너뛰고, 다른 서비스에는 계속 쓴다', () => {
  const { p } = pool({ DATA_GO_KR_KEY_BUS_1: 'a', DATA_GO_KR_KEY_BUS_2: 'b', DATA_GO_KR_LIMITS: 'seoul=2,tago=3' });
  p.record('BUS_1', 'seoul', 2);
  assert.equal(p.pick('BUS', 'seoul').label, 'BUS_2');
  p.record('BUS_2', 'seoul', 2);
  assert.equal(p.pick('BUS', 'seoul'), null);                                  // 둘 다 소진
  assert.ok(p.pick('BUS', 'tago'));                                            // tago 는 별개로 센다
});

test('한국시간 자정에 사용량이 초기화되고, 자정까지 남은 초를 알려 준다', () => {
  const clock = { t: Date.parse('2026-10-05T14:50:00Z') };                   // 한국시간 23:50
  const { p } = pool({ DATA_GO_KR_KEY_BUS_1: 'a', DATA_GO_KR_LIMITS: 'seoul=1' }, clock);
  p.record('BUS_1', 'seoul'); assert.equal(p.pick('BUS', 'seoul'), null);
  assert.equal(K.secondsToKstMidnight(clock.t), 600);
  clock.t = Date.parse('2026-10-05T15:01:00Z');                              // 한국시간 다음 날 00:01
  assert.equal(p.pick('BUS', 'seoul').label, 'BUS_1');
  assert.equal(K.kstDate(Date.parse('2026-10-05T14:59:59Z')), '2026-10-05');
  assert.equal(K.kstDate(Date.parse('2026-10-05T15:00:00Z')), '2026-10-06');
});

test('run: 한도 오류(JSON 22·XML 22·429·오류 이름)를 받으면 그 키를 쉬게 하고 다음 키로 다시 시도한다', async () => {
  const { p } = pool({ DATA_GO_KR_KEY_BUS_1: 'k1', DATA_GO_KR_KEY_BUS_2: 'k2' });
  const seen = [];
  const out = await p.run('BUS', 'tago', async (key, label) => { seen.push(label); return label === 'BUS_1' || seen.length === 1 ? { response: { header: { resultCode: '22' } } } : { ok: key }; });
  assert.equal(seen.length, 2);
  assert.equal(out.ok, 'k2');                                                // 두 번째 키로 성공
  assert.ok(p.usage().keys[seen[0]].tago.exhausted);
  for (const bad of [{ status: 429 }, new Error('LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR'), '<returnReasonCode>22</returnReasonCode>', { OpenAPI_ServiceResponse: { cmmMsgHeader: { returnReasonCode: '22' } } }]) assert.equal(K.isQuotaError(bad), true, JSON.stringify(bad));
  for (const good of [null, { response: { header: { resultCode: '00' } } }, new Error('timeout'), { status: 500 }]) assert.equal(K.isQuotaError(good), false);
});

test('run: 키가 없으면 NO_KEY, 모두 소진되면 EXHAUSTED(자정까지 초 포함), 일반 오류는 그대로 던지고 키 값은 어디에도 없다', async () => {
  await assert.rejects(K.createKeyPool({ env: {} }).run('BUS', 'tago', async () => 1), (e) => e.code === 'NO_KEY');
  const { p } = pool({ DATA_GO_KR_KEY_BUS_1: 'SECRET-ONE' });
  await assert.rejects(p.run('BUS', 'tago', async () => ({ status: 429 })), (e) => e instanceof K.KeyPoolError && e.code === 'EXHAUSTED' && e.retryAfterSec > 0 && !e.message.includes('SECRET-ONE'));
  const { p: q } = pool({ DATA_GO_KR_KEY_BUS_1: 'SECRET-TWO' });
  await assert.rejects(q.run('BUS', 'tago', async () => { throw new Error('boom'); }), /boom/);
  assert.ok(!JSON.stringify(q.usage()).includes('SECRET-TWO'));              // 사용 현황에도 값이 없다
  assert.equal(q.usage().keys.BUS_1.tago.used, 1);
});

test('fileStore: 날짜별 사용량이 파일에 남고 다시 열어도 이어진다(깨진 파일은 새로 시작)', () => {
  const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'keys-')), file = path.join(dir, 'usage.json');
  const p1 = K.createKeyPool({ env: { DATA_GO_KR_KEY_BUS_1: 'a' }, now: () => T0, store: K.fileStore(file) });
  p1.record('BUS_1', 'tago', 5);
  const p2 = K.createKeyPool({ env: { DATA_GO_KR_KEY_BUS_1: 'a' }, now: () => T0, store: K.fileStore(file) });
  assert.equal(p2.usage().keys.BUS_1.tago.used, 5);
  fs.writeFileSync(file, '{깨짐');
  assert.equal(K.createKeyPool({ env: { DATA_GO_KR_KEY_BUS_1: 'a' }, now: () => T0, store: K.fileStore(file) }).usage().keys.BUS_1.tago, undefined);
  fs.rmSync(dir, { recursive: true, force: true });
});

test('count: 용도의 키 수, 용도 키가 없으면 기본 키 1개, 아무것도 없으면 0', () => {
  const pool = K.createKeyPool({ env: { DATA_GO_KR_KEY_BUS_1: 'a', DATA_GO_KR_KEY_BUS_2: 'b', DATA_GO_KR_KEY: 'z' } });
  assert.equal(pool.count('BUS'), 2); assert.equal(pool.count('bus'), 2); assert.equal(pool.count('BUILD'), 1);
  assert.equal(K.createKeyPool({ env: {} }).count('BUS'), 0);
});

test('DATA_GO_KR_PROFILE=demo: 서버 용도(BUS·RESOLVE)는 DEMO 키를 먼저 쓰고, BUILD 는 그대로, DEMO 키가 없으면 개발 키', () => {
  const env = { DATA_GO_KR_KEY_BUS_1: 'dev-bus', DATA_GO_KR_KEY_BUILD_1: 'dev-build', DATA_GO_KR_KEY_DEMO_1: 'demo-1', DATA_GO_KR_KEY_DEMO_2: 'demo-2', DATA_GO_KR_PROFILE: 'demo' };
  const pool = K.createKeyPool({ env });
  assert.equal(pool.profile, 'demo');
  assert.equal(pool.pick('BUS', 'tago').label.startsWith('DEMO_'), true);
  assert.equal(pool.pick('RESOLVE', 'stan').label.startsWith('DEMO_'), true);
  assert.equal(pool.pick('BUILD', 'hub').label, 'BUILD_1');
  assert.equal(pool.count('BUS'), 2);
  const noDemo = K.createKeyPool({ env: { DATA_GO_KR_KEY_BUS_1: 'dev-bus', DATA_GO_KR_PROFILE: 'demo' } });
  assert.equal(noDemo.pick('BUS', 'tago').label, 'BUS_1');
  const dev = K.createKeyPool({ env: { ...env, DATA_GO_KR_PROFILE: '' } });
  assert.equal(dev.profile, 'dev'); assert.equal(dev.pick('BUS', 'tago').label, 'BUS_1');
});

test('초당 호출 한도(…PER_SECOND…)는 하루 한도로 보지 않는다(키를 하루 쉬게 하지 않음)', () => {
  const { isQuotaError, isThrottle } = require('../../lib/keys.js');
  const perSec = { OpenAPI_ServiceResponse: { cmmMsgHeader: { errMsg: 'SERVICE ERROR', returnAuthMsg: 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR', returnReasonCode: '22' } } };
  assert.equal(isThrottle(perSec), true); assert.equal(isQuotaError(perSec), false);
  assert.equal(isThrottle('LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR'), true); assert.equal(isQuotaError('LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR'), false);
  const e = new Error('초당 호출 한도'); e.throttled = true; e.status = 429; assert.equal(isQuotaError(e), false); assert.equal(isThrottle(e), true);
  assert.equal(isQuotaError(new Error('LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR')), false);
  const daily = { OpenAPI_ServiceResponse: { cmmMsgHeader: { errMsg: 'SERVICE ERROR', returnAuthMsg: 'LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR', returnReasonCode: '22' } } };
  assert.equal(isQuotaError(daily), true); assert.equal(isThrottle(daily), false);                                                           // 일일 한도는 그대로
  assert.equal(isQuotaError({ status: 429 }), true); assert.equal(isQuotaError('LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR'), true);
});
