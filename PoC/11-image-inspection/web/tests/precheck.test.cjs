const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../app.js'),'utf8'),catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../../rules/precheck-library/catalog.json'),'utf8'));
const ctx={esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),BASE:'',job:{id:'job'}};vm.createContext(ctx);
vm.runInContext(source.slice(source.indexOf('function precheckItem('),source.indexOf('function sourceChecksHTML(')),ctx);
test('registry shows ten source-linked tips and labels illustrative photos',()=>{
 const p=catalog.items[4],ref={id:'guide5',name:'PDF 태극기',status:'APPROVED',content:JSON.stringify(p),parent_ids:p.parent_ids,version:p.version,document_file:'source.pdf',image_file:'page.png'};
 const html=ctx.precheckReferenceHTML(ref);
 assert.ok(html.includes('/api/references/guide5/document#page=7'));
 assert.equal((html.match(/class="audit-entry"/g)||[]).length,10);
 assert.ok(html.includes('공식 정상 도안과 구분'));
 ref.name='<script>';assert.ok(!ctx.precheckReferenceHTML(ref).includes('<script>'));
});
test('finding links only to saved snapshot page and matching tip IDs',()=>{
 const p=catalog.items[17],ref={id:'guide18',content:JSON.stringify(p),version:p.version,document_file:'source.pdf',image_file:'page.png'};
 const html=ctx.precheckEvidenceHTML({precheck_references:[{reference_id:'guide18',tip_ids:['OFFICIAL-18-02']}]},{id:'run',reference_snapshot:[ref]});
 assert.ok(html.includes('/api/jobs/job/runs/run/references/guide18/document#page=20'));
 assert.ok(html.includes('OFFICIAL-18-02')&&!html.includes('OFFICIAL-18-01'));
 assert.ok(html.includes('미래 조치일 사례는 실행 근거에서 제외'));
});
test('confirmed glyph reading is shown instead of an older context-completed OCR word',()=>{
 vm.runInContext(source.slice(source.indexOf('function textQualityHTML('),source.indexOf('function ocrEvidenceHTML(')),ctx);
 const html=ctx.textQualityHTML({spelling_audit_evidence:{literal:'안젼한 하루',source:{source:'confirmed-source-glyphs'}}});
 assert.ok(html.includes('안젼한 하루')&&html.includes('원본 획으로 확인한 문자'));
 assert.ok(!html.includes('획·외형 정상'));
});
