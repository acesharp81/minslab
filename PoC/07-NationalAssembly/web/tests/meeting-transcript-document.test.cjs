const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');
const context = vm.createContext({});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../meeting-transcript-document.js'), 'utf8'), context);

test('chronological transcript preserves full text and adds only uncovered segments', () => {
  const rows = context.meetingTranscriptRows({utterances: [
    {utterance_id:'b', speaker_label:'김 위원', start_at:'2026-10-26T02:00:00Z', segment_ids:['s2'], text:'두 번째 원문', summary:'요약은 사용하지 않음'},
    {utterance_id:'a', start_at:'2026-10-26T01:00:00Z', segment_ids:['s1'], text:'긴 원문 '.repeat(300)},
  ], segments: [
    {segment_id:'s1', text:'중복 방지'}, {segment_id:'s2', text:'중복 방지'},
    {segment_id:'s3', received_at:'2026-10-26T03:00:00Z', text:'묶음 밖 원문'},
  ]});
  assert.deepEqual(Array.from(rows, r => r.id), ['a','b','s3']);
  assert.equal(rows[0].text, '긴 원문 '.repeat(300));
  assert.equal(rows[0].speaker, '화자 미확인');
  const md = context.meetingTranscriptMarkdown('회의', rows, 'https://example.test/?report=one#reports');
  assert.equal((md.match(/^### /gm) || []).length, 3);
  assert.ok(md.includes('2026-10-26 10:00:00'));
  assert.ok(md.includes('묶음 밖 원문'));
  assert.ok(!md.includes('요약은 사용하지 않음'));
});

test('MD retains multiline contents as quoted text and escapes source markup', () => {
  const md = context.meetingTranscriptMarkdown('회의 #1', [{speaker:'<미확인>',text:'첫 줄\n# 제목\n<script>alert(1)</script>', time:'',cursor:0}], 'https://example.test/');
  assert.ok(md.includes('> 첫 줄\n> \\# 제목'));
  assert.ok(md.includes('&lt;script&gt;'));
  assert.ok(md.includes('시간 미기록'));
  assert.ok(md.includes('비공식 자료'));
});

test('empty or segment-only snapshots work without fabricating speech', () => {
  assert.equal(context.meetingTranscriptRows({}).length, 0);
  const rows = context.meetingTranscriptRows({segments:[{segment_id:'s',text:'실제 원문',cursor:1},{text:' '}]});
  assert.equal(rows.length, 1);
  assert.equal(rows[0].text, '실제 원문');
});
