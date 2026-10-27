const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const assert = require('node:assert/strict');
const { test } = require('node:test');
const code = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
function run(rows) {
  const ctx = vm.createContext({ rows });
  vm.runInContext(code.slice(code.indexOf('function inferLiveHint('), code.indexOf('function renderInsightToolbar(')), ctx);
  return vm.runInContext('buildLiveTopics(rows)', ctx);
}
function row(id, topic, key, role='QUESTION', task=null) {
  return {utterance_id:id, content_hash:id, cursor:Number(id), is_final:true, summary:topic,
    live_insight:{topic, topic_key:key, role, task, owners:['행정안전위원회']}};
}
test('topic bridges cannot absorb a new issue into an earlier opening topic', () => {
  const items = [row('1','선관위 선거관리 투표용지','선관위 선거관리 투표용지'),
    row('2','선관위 선거관리 투표용지 중수청 수사독립','선관위 선거관리 투표용지 중수청 수사독립'),
    row('3','중수청 수사독립 국무회의','중수청 수사독립 국무회의')];
  const groups=run(items);
  assert.equal(groups.length,2);
  assert.equal(groups[0].questions.length,2);
  assert.equal(groups[1].questions.length,1);
  assert.ok(!groups[0].topicTokens.has('중수청'));
});
test('same subject question, answer and real data request remain together', () => {
  const items=[row('1','중수청 국무회의 참석 검토','중수청 국무회의 참석'),
    row('2','중수청 국무회의 참석 답변','중수청 국무회의 참석','ANSWER'),
    row('3','중수청 국무회의 참석 자료','중수청 국무회의 참석','REQUEST','참석 검토 자료 제출')];
  const groups=run(items);
  assert.equal(groups.length,1);
  assert.equal(groups[0].questions.length,1);
  assert.equal(groups[0].answers.length,2);
  assert.equal(groups[0].tasks.size,1);
});
test('reported interior meeting preserves every turn without a 301-turn opening bucket', () => {
  const items=JSON.parse(fs.readFileSync(path.join(__dirname,'../../backend/tests/fixtures/live-task-review/interior-grouping-20261026.json'),'utf8'));
  const groups=run(items);
  assert.equal(groups.reduce((n,g)=>n+g.questions.length+g.answers.length,0),items.filter(x=>x.is_final).length);
  assert.ok(Math.max(...groups.map(g=>g.questions.length+g.answers.length))<30);
  const opening=groups.find(g=>g.topic.includes('종합 국정감사 개회'));
  assert.ok(opening);
  assert.equal(opening.tasks.size,0);
  assert.ok(groups.some(g=>g.topic.includes('소방') || g.topic.includes('폐쇄')));
  assert.ok(groups.some(g=>g.topic.includes('중수청') && g.topic.includes('국무회의')));
});

test('model assigned issue IDs join paraphrased answers without lexical overlap',()=>{
  const items=[row('1','치료감호 청구율 저조','치료감호 청구율'),row('2','심신미약 인정 요건','심신미약 인정','ANSWER'),row('3','치료시설 확충 요구','시설 확충','REQUEST','치료시설 확충 검토')];
  for(const r of items)r.live_insight.discussion_group={id:'stable-issue',title:'정신질환 범죄자 치료·관리 제도'};
  const groups=run(items);assert.equal(groups.length,1);assert.equal(groups[0].questions.length+groups[0].answers.length,3);assert.equal(groups[0].tasks.size,1);
});

test('different semantic IDs are never merged by a shared institution or keywords',()=>{
  const items=[row('1','중수청 국무회의 출석','중수청 국무회의'),row('2','중수청 국무회의 업무보고','중수청 국무회의'),row('3','중수청 국무회의 출석','중수청 국무회의')];
  items[0].live_insight.discussion_group={id:'a',title:'수사기관 독립성'};
  items[1].live_insight.discussion_group={id:'b',title:'신설 청사와 장비 확보'};
  const groups=run(items);assert.equal(groups.length,3);
});

test('actual judiciary discussion keeps all 182 turns and tasks in 14 semantic groups',()=>{
  const rows=JSON.parse(fs.readFileSync(path.join(__dirname,'../../backend/tests/fixtures/live-task-review/judiciary-semantic-groups-20261026.json'),'utf8'));
  const groups=run(rows);
  assert.equal(groups.length,14);
  assert.equal(groups.reduce((n,g)=>n+g.questions.length+g.answers.length,0),182);
  assert.equal(groups.reduce((n,g)=>n+g.tasks.size,0),rows.filter(r=>r.live_insight.task).length);
  const treatment=groups.find(g=>g.topic.includes('정신질환 범죄자'));
  assert.ok(treatment.questions.length+treatment.answers.length>=15);
  assert.ok(treatment.tasks.size>0);
  const court=groups.find(g=>g.topic.includes('여론조사 사건'));
  assert.ok(court.questions.length+court.answers.length>=15);
  assert.notEqual(treatment,court);
  assert.ok(groups.some(g=>g.topic.includes('자료제출')));
});
