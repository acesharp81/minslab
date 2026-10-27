const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const {test} = require('node:test');
const context = vm.createContext({window: {addEventListener() {}}});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../meeting-report-document.js'), 'utf8'), context);
const overview = (brief, groups) => JSON.parse(JSON.stringify(context.meetingDocumentOverview(brief, groups)));
test('loading the full document selects current narrative while respecting an explicit official or legacy view', () => {
  const record = {default_brief_view: 'STRUCTURED', structured_brief: {summary: '현재'}, provisional_brief: {summary: '이전'}, official_brief: {summary: '공식'}};
  assert.equal(context.meetingDocumentSource(record).brief.summary, '현재');
  assert.equal(context.meetingDocumentSource(record, 'provisional').brief.summary, '이전');
  assert.equal(context.meetingDocumentSource(record, 'official').brief.summary, '공식');
});
test('overview preserves the saved meeting summary and does not substitute a topic summary', () => {
  const result = overview({summary: '회의 전체 요약', report_summary: {summary: '다른 요약'}}, []);
  assert.equal(result.summary, '회의 전체 요약');
  assert.equal(overview({summary: null}, []).summary, '');
});
test('top groups and other include the full population without double counting IDs', () => {
  const groups = Array.from({length: 9}, (_, i) => ({title: `주제 ${i}`, topics: [{id: `t${i}`, title: '예산 검토'}]}));
  groups[0].topics.push({id: 't0', title: '예산 검토'});
  groups[1].topics.push({id: 't0', title: '예산 검토'});
  const result = overview({}, groups);
  assert.equal(result.total, 9);
  assert.equal(result.topicRows.length, 7);
  assert.equal(result.topicRows.at(-1).label, '기타 3개 대주제');
  assert.equal(result.topicRows.reduce((sum, row) => sum + row.count, 0), 9);
});
test('keyword frequency counts titles, ignores repeated words and excludes summary/body text', () => {
  const result = overview({summary: '한강버스 한강버스'}, [{title: '한강버스', topics: [
    {id: 'one', title: '경찰 예산·예산 검토', summary: '원문 전용 단어'},
    {id: 'two', title: '경찰 인력 예산 요구'},
  ]}]);
  assert.equal(result.keywordRows.find(r => r.label === '예산').count, 2);
  assert.equal(result.keywordRows.find(r => r.label === '경찰').count, 2);
  assert.ok(!result.keywordRows.some(r => ['검토', '요구', '한강버스', '원문'].includes(r.label)));
});
test('empty and legacy topics produce finite, complete counts without inventing a summary', () => {
  assert.deepEqual(overview({}, []), {summary: '', total: 0, topicRows: [], keywordRows: []});
  const result = overview({}, [{title: '이전 보고서', topics: [{title: '예산'}, {title: '예산'}]}]);
  assert.equal(result.total, 2);
  assert.equal(result.keywordRows[0].count, 2);
});
