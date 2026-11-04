/* Related discussion navigation only: never an official quotation/equality claim. */
(function (root) {
  const stop = new Set(('정부 대통령 장관 국무회의 부처 관계부처 보고 보고서 발언 질의 답변 과제 내용 관련 대한 위한 통해 요청 지시 주문 당부 검토 지원 추진 개선 대책 방안 마련 필요 필요성 강화 확대 정책 사업 현황 상황 결과 계획 기준 여부 문제 부분 국민 전체 올해 일상 변화 변화되는 확인 정리 반영 발표 운영 관리 평가 체계 논의 준비 언급 지금 현재 우리 사전 사후 비용 투자 시범사업 대상 특정 관한 전면 전환 전국 전파 활용 효율성 제고 요구 제도 방식 서비스 기회 일정').split(' '));
  const normalize = (value) => String(value || '').normalize('NFKC').toLowerCase()
    .replace(/\bai\b/g, '인공지능').replace(/다문화가정/g, '다문화가족')
    .replace(/가축\s+방역/g, '가축방역').replace(/k[\s-]*브랜드/g, '케이브랜드');
  const compact = (value) => normalize(value).replace(/[^가-힣a-z0-9]/g, '');
  function tokens(value) {
    return [...new Set((normalize(value).match(/[가-힣a-z][가-힣a-z0-9]+/g) || [])
      .map(word => word.replace(/(?:에서는|으로부터|이라면서|에대한|에서|에게|으로|들은|들이|하고|하는|하며|에는|까지|부터|보다|처럼|이라|라는|이란|은|는|을|를|이|가|의|과|와|도|에)$/, ''))
      .filter(word => word.length >= 2 && !stop.has(word)
        && !/^(?:개선|지원|추진|강화|운영|보완|검토|대응)(?:대책|방안|계획|현황|결과|상황|체계|정책|필요성|여부|사업|방향)$/.test(word)
        && !/(?:장관|위원장|부위원장)$/.test(word)))];
  }
  function score(text, candidate) {
    const source = compact(text), target = compact(candidate);
    const shared = tokens(candidate).filter(word => source.includes(word));
    // Avoid a lone broad AI/education/government term linking unrelated subjects.
    const specific = shared.filter(word => word.length >= 3 && !['인공지능', '공공기관', '공공서비스'].includes(word));
    const aiContext = source.includes('인공지능') && target.includes('인공지능')
      && ['교육', '공공'].some(context => source.includes(context) && target.includes(context));
    if (!aiContext && !specific.length) return 0;
    if (!aiContext && shared.length < 2 && !specific.some(word => word.length >= 4)) return 0;
    return shared.length + specific.length + (target.length >= 8 && source.includes(target) ? 4 : 0);
  }
  function relatedTopics(item, brief) {
    if (!brief) return [];
    // Keep the official item's scope. Ministry names and other agenda items do not count.
    const officialText = [item.topic, item.text, item.summary, item.discussion_summary,
      ...(item.source_paragraphs || []).map(p => p.text),
      ...(item.presidential_guidance || []).map(p => p.text)].filter(Boolean).join(' ');
    const groups = (brief.topic_groups || []).filter(group => score(officialText, group.title) > 0);
    const groupIds = new Set(groups.flatMap(group => group.topic_ids || []).map(String));
    const seen = new Set();
    return (brief.topics || []).flatMap(topic => {
      if (!topic.id || seen.has(String(topic.id))) return [];
      if (/발언\s*(?:기회|일정)|의사진행|정회\s*선언|산회\s*선언/.test(topic.title || '')) return [];
      const direct = score(officialText, topic.title);
      // A saved parent association expands a matching policy subject to its detailed issues.
      if (!direct && !groupIds.has(String(topic.id))) return [];
      seen.add(String(topic.id));
      return [{id: String(topic.id), title: topic.title || '관련 논의', score: direct,
        relation: direct ? 'TOPIC_TEXT' : 'SAVED_PARENT'}];
    }).sort((a, b) => b.score - a.score);
  }
  root.ExecutiveReportLinks = {relatedTopics};
  if (typeof module !== 'undefined' && module.exports) module.exports = root.ExecutiveReportLinks;
})(typeof window !== 'undefined' ? window : globalThis);
