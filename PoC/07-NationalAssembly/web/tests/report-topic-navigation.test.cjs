const fs = require('node:fs'), vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const path = require('node:path');
const app = fs.readFileSync(path.join(__dirname, '../app.js'), 'utf8');
const reports = fs.readFileSync(path.join(__dirname, '../topic-reports.js'), 'utf8');
function context(href = 'https://example.test/poc/national-assembly/?report=other#topic-reports') {
  const c = vm.createContext({URL, window:{location:{href}}});
  vm.runInContext(app.slice(app.indexOf('function meetingReportSourceTarget('),
    app.indexOf('function restoredMeetingReportId(')), c);
  vm.runInContext(reports.slice(reports.indexOf('  function meetingReportHref('),
    reports.indexOf('  let meetingNavigationRequest')), c);
  return c;
}
test('structured result carries its exact issue ID and structured view in the link', () => {
  const c = context();
  const url = new URL(c.meetingReportHref({broadcast_id:'meeting', id:'meeting:structured-topic-mobile-id', authority_status:'PROVISIONAL'}), 'https://example.test');
  assert.equal(url.searchParams.get('report'), 'meeting');
  assert.equal(url.searchParams.get('report-topic'), 'structured-topic-mobile-id');
  assert.equal(url.searchParams.get('report-view'), 'structured');
  assert.equal(url.pathname, '/poc/national-assembly/');
  assert.equal(url.hash, '#reports');
});
test('official integration and original summaries use their own view and preserve colons in IDs', () => {
  const c = context();
  for (const [authority, view] of [['OFFICIAL_INTEGRATED','official'],['PROVISIONAL','provisional']]) {
    const target = c.meetingReportSourceTarget({broadcast_id:'meeting',id:'meeting:issue:sub-id',authority_status:authority});
    assert.equal(target.topicId, 'issue:sub-id');
    assert.equal(target.view, view);
  }
});
test('official executive material targets the source agenda instead of a LIVE topic', () => {
  const target = context().meetingReportSourceTarget({broadcast_id:'broadcast',id:'executive-official:148970595:report-3'});
  assert.equal(target.topicId, 'report-3');
  assert.equal(target.view, 'executive');
});
test('missing source IDs do not inherit an unrelated topic from the current URL', () => {
  const c = context('https://example.test/?report=old&report-topic=old-topic&report-view=structured');
  const url = new URL(c.meetingReportHref({broadcast_id:'meeting'}), 'https://example.test');
  assert.equal(url.searchParams.has('report-topic'), false);
  assert.equal(url.searchParams.has('report-view'), false);
});
test('a target applies only to its own meeting and a recognized view', () => {
  const c = context('https://example.test/?report=meeting&report-topic=issue&report-view=structured');
  assert.equal(c.requestedMeetingReportTopic('meeting').topicId, 'issue');
  assert.equal(c.requestedMeetingReportTopic('other'), null);
  c.window.location.href = 'https://example.test/?report=meeting&report-topic=issue&report-view=unknown';
  assert.equal(c.requestedMeetingReportTopic('meeting'), null);
});
