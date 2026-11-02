const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function modules() {
  let suspensions = 0;
  const context = vm.createContext({PolicyRegionMap: {suspend() { suspensions++; }}});
  for (const name of ['policy-907.js', 'policy-geo.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../../web/assets', name), 'utf8'), context);
  }
  return {
    policy: vm.runInContext('Policy907', context),
    map: vm.runInContext('PolicyGeo3D', context),
    suspensions: () => suspensions,
  };
}

test('policy catalogue retains eligible programs across map suspension and invalidation', () => {
  const {policy, map, suspensions} = modules();
  policy.setPrograms([
    {id: 'active', policy_id: 'POL_2025_0907', status: 'REVIEW'},
    {id: 'rejected', policy_id: 'POL_2025_0907', status: 'REJECTED'},
    {id: 'released', policy_id: 'POL_2025_0907', status: 'RELEASED'},
    {id: 'other', policy_id: 'OTHER', status: 'REVIEW'},
  ]);
  policy.invalidate();
  map.hidden();
  map.resize();
  assert.deepEqual(Array.from(policy.programs(), row => row.id), ['active']);
  assert.equal(suspensions(), 1);
  policy.setPrograms(null);
  assert.equal(policy.programs().length, 0);
});

test('separate pages retain independent policy catalogues', () => {
  const first = modules(), second = modules();
  first.policy.setPrograms([{id: 'first', policy_id: 'POL_2025_0907', status: 'REVIEW'}]);
  assert.equal(first.policy.programs().length, 1);
  assert.equal(second.policy.programs().length, 0);
});
