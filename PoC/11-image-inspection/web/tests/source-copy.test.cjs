const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const ctx={esc:s=>String(s).replaceAll('<','&lt;').replaceAll('>','&gt;')};vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function readingConflictHTML('),source.indexOf('function renderDetail(')),ctx);
test('copy diff shows literal, expected, spaces and uncertainty safely',()=>{
 const html=ctx.sourceChecksHTML({source_copy_check:{literal:'안젼한하루',expected:'안전한 하루',confirmed:false,differences:[{observed:'젼',expected:'전'},{observed:'',expected:' '},{observed:'<script>',expected:'문구'}]}});
 for(const text of ['안젼한하루','안전한 하루','␠','∅','판독 미확정','&lt;script&gt;'])assert.ok(html.includes(text));
 assert.ok(!html.includes('<script>'));
});
test('pixel evidence shows source crop and independently confirmed candidate',()=>{
 ctx.job={id:'safe-job',image:{width:1600,height:1000}};ctx.BASE='';
 const html=ctx.sourceChecksHTML({pixel_text_evidence:{detector_text:'안전',shape_text:'안젼',shape_checks:[{ocr_char:'전',shape_char:'젼',accepted:true,rect:[.1,.2,.2,.3],independent_comparison:{agrees:true}}]}});
 for(const text of ['원본 문자 획 대조','안전','안젼','형태 일치','/api/jobs/safe-job/image','viewBox='])assert.ok(html.includes(text));
});
test('spelling evidence separates observed text from a proposed correction',()=>{
 const html=ctx.sourceChecksHTML({spelling_audit_evidence:{literal:'힘께 만드는 미래',correction:'함께 만드는 미래',reason:'철자 확인'}});
 for(const text of ['독립 철자 검사','확인된 원문: 힘께 만드는 미래','수정 후보: 함께 만드는 미래'])assert.ok(html.includes(text));
});
