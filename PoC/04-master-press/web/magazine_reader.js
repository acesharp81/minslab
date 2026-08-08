(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.MagazineReader = api;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function cleanText(value) {
    return String(value == null ? '' : value).replace(/\s+/g, ' ').trim();
  }

  function sentence(value, fallback) {
    var text = cleanText(value) || fallback || '';
    if (!text) return '';
    return /[.!?。！？]$/.test(text) ? text : text + '.';
  }

  function spokenDate(value) {
    var match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(cleanText(value));
    if (!match) return cleanText(value);
    return Number(match[1]) + '년 ' + Number(match[2]) + '월 ' + Number(match[3]) + '일';
  }

  function memberScore(member) {
    var scores = (member._readerMatches || []).map(function (item) {
      return Number(item.score || 0);
    });
    return scores.length ? Math.max.apply(null, scores) : 0;
  }

  function uniquePressReleaseCount(members) {
    var releases = {};
    members.forEach(function (member) {
      (member.related_press_releases || []).forEach(function (item) {
        var key = cleanText(item.url) || 'title:' + cleanText(item.title);
        if (key) releases[key] = true;
      });
    });
    return Object.keys(releases).length;
  }

  function visibleIssues(edition, selectedCaseIds) {
    var selected = selectedCaseIds || [];
    var groups = {};
    (edition.members || []).forEach(function (member) {
      var matches = (member.case_matches || []).filter(function (item) {
        return selected.indexOf(item.id) >= 0;
      });
      if (!matches.length) return;
      var copy = Object.assign({}, member, {_readerMatches: matches});
      var key = cleanText(member.issue_key) || 'article:' + cleanText(member.article_id);
      (groups[key] || (groups[key] = [])).push(copy);
    });

    return Object.keys(groups).map(function (key) {
      var members = groups[key].sort(function (left, right) {
        return memberScore(right) - memberScore(left);
      });
      return {
        issueKey: key,
        lead: members[0],
        members: members,
        pressCount: uniquePressReleaseCount(members)
      };
    }).sort(function (left, right) {
      return right.members.length - left.members.length ||
        right.pressCount - left.pressCount ||
        Number(left.lead.rank || 0) - Number(right.lead.rank || 0);
    });
  }

  function issueText(issue, index) {
    var lead = issue.lead || {};
    var parts = [
      (index + 1) + '번째 이슈.',
      sentence(lead.article_type, '기타'),
      sentence(lead.tone, '사실 전달'),
      sentence(lead.title, '제목이 준비되지 않았습니다'),
      sentence(lead.summary, '요약이 준비되지 않았습니다'),
      sentence((cleanText(lead.publisher) || '언론사 미확인') + ' 보도이며, 관련 기사는 ' + issue.members.length + '건입니다')
    ];
    return parts.filter(Boolean).join(' ');
  }

  function buildNarration(edition, selectedCaseIds) {
    edition = edition || {};
    var issues = visibleIssues(edition, selectedCaseIds);
    var organization = cleanText(edition.organization_name) || 'AI 뉴스';
    var slot = cleanText(edition.slot_label) || '에디션';
    var date = spokenDate(edition.edition_date);
    var introParts = [
      sentence(organization + ' ' + slot + ' 매거진입니다'),
      date ? sentence(date) : '',
      sentence('선택한 케이스의 주요 이슈는 총 ' + issues.length + '건입니다')
    ];
    var segments = [{kind: 'intro', text: introParts.filter(Boolean).join(' ')}];
    issues.forEach(function (issue, index) {
      segments.push({
        kind: 'issue',
        issueKey: issue.issueKey,
        articleId: cleanText(issue.lead.article_id),
        index: index,
        text: issueText(issue, index)
      });
    });
    if (issues.length) segments.push({kind: 'outro', text: '매거진 읽기를 마칩니다.'});
    return {issueCount: issues.length, issues: issues, segments: segments};
  }

  return {
    buildNarration: buildNarration,
    cleanText: cleanText,
    spokenDate: spokenDate,
    visibleIssues: visibleIssues
  };
}));
