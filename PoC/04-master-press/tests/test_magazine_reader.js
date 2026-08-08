'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const reader = require('../web/magazine_reader.js');

test('buildNarration reads only selected cases in magazine display order', () => {
  const edition = {
    organization_name: '행정안전부',
    slot_label: '점심',
    edition_date: '2026-08-08',
    members: [
      {
        article_id: 'one', issue_key: 'issue:group', rank: 2,
        title: '두 번째 기사', summary: '두 번째 요약', publisher: '나일보',
        article_type: '정책', tone: '사실전달',
        case_matches: [{id: 'selected', score: 80}]
      },
      {
        article_id: 'two', issue_key: 'issue:group', rank: 1,
        title: '대표 기사', summary: '대표 요약', publisher: '가일보',
        article_type: '정책', tone: '긍정적',
        case_matches: [{id: 'selected', score: 95}]
      },
      {
        article_id: 'hidden', issue_key: 'issue:hidden', rank: 0,
        title: '선택되지 않은 기사', case_matches: [{id: 'other', score: 99}]
      },
      {
        article_id: 'solo', issue_key: 'issue:solo', rank: 3,
        title: '단독 기사', summary: '', publisher: '',
        case_matches: [{id: 'selected', score: 70}]
      }
    ]
  };

  const result = reader.buildNarration(edition, ['selected']);

  assert.equal(result.issueCount, 2);
  assert.equal(result.segments[0].text, '행정안전부 점심 매거진입니다. 2026년 8월 8일. 선택한 케이스의 주요 이슈는 총 2건입니다.');
  assert.equal(result.segments[1].articleId, 'two');
  assert.match(result.segments[1].text, /1번째 이슈.*대표 기사.*대표 요약.*관련 기사는 2건입니다/);
  assert.match(result.segments[2].text, /2번째 이슈.*단독 기사.*요약이 준비되지 않았습니다.*언론사 미확인/);
  assert.equal(result.segments[3].text, '매거진 읽기를 마칩니다.');
  assert.doesNotMatch(result.segments.map((item) => item.text).join(' '), /선택되지 않은 기사/);
});

test('buildNarration returns an intro only when no issue is selected', () => {
  const result = reader.buildNarration({members: []}, []);
  assert.equal(result.issueCount, 0);
  assert.deepEqual(result.segments.map((item) => item.kind), ['intro']);
});
