// 피드백 버튼 핸들링
function handleFeedbackThumb(articleId, caseId, type) {
  if (type === 'up') {
    // 긍정 피드백
    req('/api/poc/master-press/analysis/' + encodeURIComponent(articleId) + '/' + encodeURIComponent(caseId) + '/feedback', {
      method: 'POST',
      body: JSON.stringify({ reasons: ['good_judgment'], comment: '' })
    }).then(function() {
      toast('긍정 피드백이 저장되었습니다.');
    }).catch(function(error) {
      toast(error.message);
    });
  } else {
    // 부정 피드백 - 이유 선택 UI 표시
    showFeedbackReasons(articleId, caseId);
  }
}

function showFeedbackReasons(articleId, caseId) {
  var panel = $('feedbackReasonsPanel') || createFeedbackReasonsPanel();
  var options = [
    { id: 'required_terms_missing', label: '필수 키워드 미확인' },
    { id: 'include_terms_missing', label: '포함 키워드 미확인' },
    { id: 'negative_signal_missing', label: '부정 신호 부족' },
    { id: 'topic_target_not_verified', label: '대상 근거 부족' },
    { id: 'topic_stance_not_verified', label: '어조 근거 부족' },
    { id: 'body_unavailable', label: '본문 미확보' },
    { id: 'llm_insufficient_relevance', label: 'LLM 관련성 낮음' },
    { id: 'llm_topic_mismatch', label: '주제 불일치' },
    { id: 'llm_different_context', label: '다른 맥락' },
    { id: 'llm_body_insufficient', label: '본문 근거 부족' },
    { id: 'required_topic_not_verified', label: '필수 주제 미확인' },
    { id: 'excluded_term', label: '제외 기준 과도' },
    { id: 'other', label: '기타' }
  ];

  var html = '<div class="feedback-reasons-panel">';
  html += '<h4>이유를 알려주세요</h4>';
  html += '<div class="feedback-reasons-list">';
  options.forEach(function(opt) {
    html += '<label class="feedback-reason-option"><input type="checkbox" value="' + esc(opt.id) + '"> ' + esc(opt.label) + '</label>';
  });
  html += '</div>';
  html += '<label class="full">추가 코멘트<textarea id="feedbackComment" rows="2" placeholder="예: 케이스 조건과 맞지 않습니다"></textarea></label>';
  html += '<div class="feedback-actions">';
  html += '<button type="button" class="button secondary" onclick="closeFeedbackReasons()">취소</button>';
  html += '<button type="button" class="button" onclick="submitFeedbackReasons(\'' + esc(articleId) + '\', \'' + esc(caseId) + '\')">제출</button>';
  html += '</div>';
  html += '</div>';

  panel.innerHTML = html;
  panel.classList.add('expanded');
}

function createFeedbackReasonsPanel() {
  var panel = document.createElement('div');
  panel.id = 'feedbackReasonsPanel';
  panel.className = 'feedback-reasons-modal';
  document.body.appendChild(panel);
  return panel;
}

function closeFeedbackReasons() {
  var panel = $('feedbackReasonsPanel');
  if (panel) {
    panel.classList.remove('expanded');
  }
}

function submitFeedbackReasons(articleId, caseId) {
  var reasons = Array.from(document.querySelectorAll('#feedbackReasonsPanel input[type="checkbox"]:checked')).map(function(el) {
    return el.value;
  });
  var comment = ($('feedbackComment') && $('feedbackComment').value.trim()) || '';

  if (!reasons.length) {
    toast('최소 하나의 이유를 선택해주세요.');
    return;
  }

  req('/api/poc/master-press/analysis/' + encodeURIComponent(articleId) + '/' + encodeURIComponent(caseId) + '/feedback', {
    method: 'POST',
    body: JSON.stringify({ reasons: reasons, comment: comment })
  }).then(function() {
    toast('부정 피드백이 저장되었습니다.');
    closeFeedbackReasons();
    loadDashboard(state.activeCase, state.activeOrganization);
  }).catch(function(error) {
    toast(error.message);
  });
}
