const {test} = require('node:test');
const assert = require('node:assert/strict');
const {relatedTopics} = require('../executive-report-links.js');
const topic = (id, title) => ({id, title});
test('AI needs shared context; public administration does not select classroom education', () => {
 const brief={topics:[topic('public','공공기관 AI 대전환'),topic('class','인공지능 교육 시수 확보')]};
 assert.deepEqual(relatedTopics({topic:'공공기관 AI 활용'},brief).map(x=>x.id),['public']);
 assert.deepEqual(relatedTopics({text:'학생들의 AI 교육 방법을 고민해 달라'},brief).map(x=>x.id),['class']);
});
test('spacing and family wording connect the same policy subject', () => {
 const brief={topics:[topic('livestock','가축방역 개선대책 보고'),topic('family','다문화가족 학교 적응 지원')]};
 assert.equal(relatedTopics({topic:'K-가축 방역 개선 대책'},brief)[0].id,'livestock');
 assert.equal(relatedTopics({text:'다문화가정 학생을 지원하라'},brief)[0].id,'family');
});
test('generic wording, national spread, pilot projects and ministry alone cannot make a link', () => {
 const brief={topics:[topic('ai','정보통신망법 기반 AI 지원 시범사업 확대'),topic('disease','아프리카돼지열병의 현재 확산 범위와 전국 전파 여부'),topic('other','특정 대상을 다른 AI로 분류하는지에 관한 내용')]};
 assert.deepEqual(relatedTopics({topic:'농어촌 기본소득 시범사업의 전국 확산',ministries:['과학기술정보통신부']},brief),[]);
 assert.deepEqual(relatedTopics({topic:'해외진출기업의 국내복귀 지원에 관한 법률',summary:'면제대상을 확대하는 내용'},brief),[]);
 assert.deepEqual(relatedTopics({topic:'가축방역 개선대책'},{topics:[topic('other','산업안전 개선대책')]}),[]);
});
test('saved policy parent links children, preserves IDs and excludes speaking procedure', () => {
 const brief={topic_groups:[{title:'다문화가족 지원',topic_ids:['child','procedure']}],topics:[topic('child','학교 부적응과 진학률 저하'),topic('procedure','장관 발언 기회 요청')]};
 const before=JSON.stringify(brief);
 assert.deepEqual(relatedTopics({topic:'다문화가정 지원'},brief).map(x=>x.id),['child']);
 assert.equal(JSON.stringify(brief),before);
});
test('each topic appears once even with duplicate input, unrelated or unavailable data stays empty', () => {
 assert.equal(relatedTopics({topic:'가축방역'},{topics:[topic('a','가축방역'),topic('a','가축방역')]}).length,1);
 assert.deepEqual(relatedTopics({topic:'가축방역'},null),[]);
 assert.deepEqual(relatedTopics({topic:'주택공급 대책'},{topics:[topic('a','가축방역')]}),[]);
});
