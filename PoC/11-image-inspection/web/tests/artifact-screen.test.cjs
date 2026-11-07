const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const ctx={esc:s=>String(s??'').replaceAll('<','&lt;').replaceAll('>','&gt;')};vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function artifactScreenHTML('),source.indexOf('function renderTokens(')),ctx);
test('candidate diagnostics stay collapsed and never create finding buttons or verdicts',()=>{
 const html=ctx.artifactScreenHTML({artifact_screen:{mode:'SHADOW',seconds:.1,note:'후보만 기록',candidates:[{source_id:'<img>',signals:['LOCAL_BLUR_SIGNAL']}],diagnostics:[]}});
 assert.match(html,/추가 재판독 꺼짐/);assert.match(html,/&lt;img&gt;/);assert.ok(!html.includes('data-finding')&&!html.includes('status-FAIL')&&!html.includes('<details open'));
 assert.equal(ctx.artifactScreenHTML({}),'');
});
