const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../app.js'), 'utf8');
const grouping = source.slice(source.indexOf('function measuredFlags()'), source.indexOf('function pinRows()'));
function fixture(scope='FULL_IMAGE',showNormal=false,overrides={}) {
  const run = {
    scope, observation:{objects:[]}, reviews:[],
    structural_checks:{flags:[0,1,2,3].map(i=>({
      id:'flag-'+i,label:'태극기 '+(i+1),status:i===1?'MATCH':'MISMATCH',
      rect:[.1+(i%2)*.45,.2+Math.floor(i/2)*.3,.4+(i%2)*.45,.4+Math.floor(i/2)*.3]
    }))},
    results:[
      ...['h','i'].map(s=>({id:s,rule_id:'H-04-'+s,parent_id:'H-04',status:'REVIEW',document_review:true,
        reason:'퀴즈 오답 문맥 확인',rects:[[.1,.2,.4,.4]],reference_ids:[],cell_ids:[]})),
      {id:'license',rule_id:'D-03-e',parent_id:'D-03',status:'REVIEW',document_review:true,
        reason:'이용권 증빙 필요',rects:[],reference_ids:[],cell_ids:[]}
    ]
  };
  Object.assign(run,overrides);
  const context = {
    activeRun:()=>run,findings:()=>run.results,effective:r=>r.status,selected:null,
    pack:{parents:[{id:'H-04',title:'국가상징'},{id:'D-03',title:'이용권'}]},
    $:s=>s==='#pass-toggle'?{checked:showNormal}:{getBoundingClientRect:()=>({width:500,height:600})}
  };
  vm.createContext(context);vm.runInContext(grouping,context);
  return context.issueGroups();
}
test('measured differences retain one location per object even when AI verdict is REVIEW',()=>{
  const groups=fixture(),pins=groups.filter(g=>g.anchor);
  assert.equal(pins.length,3);
  assert.equal(new Set(pins.map(g=>g.id)).size,3);
  assert.ok(pins.every(g=>g.technical&&g.status==='FAIL'&&g.rows.length===2&&g.rows.every(r=>r.status==='REVIEW')&&g.rects.length===1));
  assert.equal(groups.filter(g=>!g.anchor).length,1); // license stays nonspatial
});
test('matching diagram is opt-in; whole-image measurements are not drawn on crop coordinates',()=>{
  assert.equal(fixture('FULL_IMAGE',true).filter(g=>g.anchor).length,4);
  assert.equal(fixture('CROP').filter(g=>g.technical).length,0);
});

test('measured emblem location overrides coarse scene cells for its object only',()=>{
 const rect=[.2,.3,.4,.5];
 const groups=fixture('FULL_IMAGE',false,{
  observation:{objects:[{id:'logo',label:'문양',cell_ids:['R01C01'],text_legibility:'NOT_TEXT'}]},
  results:[{id:'logo-proof',rule_id:'H-07-b',parent_id:'H-07',status:'FAIL',reason:'측정 차이',evidence_ids:['logo'],rects:[rect],cell_ids:['R01C01'],emblem_geometry:{rect}}]
 });
 const logo=groups.find(g=>g.id==='logo');
 assert.deepEqual(Array.from(logo.rects[0]),rect);
 assert.ok(Math.abs(logo.anchor[0]-.3)<1e-9&&Math.abs(logo.anchor[1]-.4)<1e-9);
});

test('disconnected text blocks stay one issue without inventing a midpoint marker',()=>{
  const rects=[[2/12,10/12,3/12,11/12],[7/12,10/12,8/12,11/12]];
  const rows=['H-06-b','D-02-l'].map(id=>({id,rule_id:id,parent_id:id.slice(0,4),status:'FAIL',reason:'문구 오타 후보',evidence_ids:['O7'],rects}));
  const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:rows,observation:{objects:[{id:'O7',label:'좌우 안내 문구',cell_ids:['R11C03','R11C08']}]}});
  assert.equal(groups.length,1);assert.equal(groups[0].rows.length,2);
  assert.equal(groups[0].locationAmbiguous,true);assert.equal(groups[0].locationRegions.length,2);
  assert.equal(groups[0].anchor,undefined);assert.equal(groups[0].calloutAnchor,undefined);assert.equal(groups[0].number,1);assert.equal(groups[0].status,'FAIL');
  assert.ok(groups[0].rows.every(r=>r.reason==='문구 오타 후보'));
});
test('connected cells keep one number anchored inside observed evidence',()=>{
  const rects=[[2/12,10/12,3/12,11/12],[3/12,10/12,4/12,11/12]];
  const row={id:'text',rule_id:'D-02-l',parent_id:'D-02',status:'FAIL',reason:'오타 후보',evidence_ids:['text'],rects};
  const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'text',label:'문구',cell_ids:['R11C03','R11C04']}]}});
  assert.equal(groups[0].number,1);assert.equal(groups[0].locationAmbiguous,false);
  const [x,y]=groups[0].anchor;assert.ok(rects.some(r=>x>=r[0]&&x<=r[2]&&y>=r[1]&&y<=r[3]));
});
test('multiple defects on the same measured object share one numbered group',()=>{
 const rows=['H-04-i','H-04-e','D-02-j'].map(id=>({id,rule_id:id,parent_id:id.slice(0,4),status:'FAIL',reason:'객체 오류',rects:[[.2,.25,.3,.35]],evidence_ids:['flag'],reference_ids:[],cell_ids:[]}));
 const groups=fixture('FULL_IMAGE',false,{analysis_observation:{objects:[{id:'flag',label:'태극기',rects:[[.2,.25,.3,.35]]}]},results:rows});
 assert.equal(groups.filter(g=>g.anchor).length,1);
 assert.equal(groups[0].rows.length,3);assert.equal(groups[0].number,1);
});

test('unreadable text alone remains accessible without a defect marker',()=>{
 const row={id:'text',rule_id:'D-02-l',parent_id:'D-02',status:'REVIEW',reason:'문자 획 판독 불확실',evidence_ids:['text'],error_type:'OCR_UNREADABLE',rects:[[.2,.3,.3,.4]]};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'text',label:'작은 표지',rects:row.rects}]}});
 assert.equal(groups[0].number,null);assert.equal(groups[0].anchor,undefined);assert.equal(groups[0].status,'REVIEW');
});

test('small background figures do not get OCR warning pins; context conflicts remain visible',()=>{
 const objects=[{id:'person',label:'작은 보행 인물',text:'',text_legibility:'NOT_TEXT',rects:[[.3,.3,.4,.4]]},{id:'symbol',label:'본체 부속 표식',text:'',text_legibility:'NOT_TEXT',rects:[[.8,.1,.9,.2]]}];
 const rows=[{id:'p',rule_id:'D-04-b',parent_id:'D-04',status:'REVIEW',reason:'작아서 식별 불가',error_type:'OCR_UNREADABLE',evidence_ids:['person'],rects:objects[0].rects},{id:'s',rule_id:'H-05-c',parent_id:'H-05',status:'REVIEW',reason:'국가 정체성 설명과 표식 충돌',review_basis:'CONTEXT_CONFLICT',evidence_ids:['symbol'],rects:objects[1].rects}];
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},observation:{objects},results:rows});
 assert.deepEqual(Array.from(groups.filter(g=>g.number),g=>g.id),['symbol']);
 assert.ok(groups.find(g=>g.rows.includes(rows[0]))); // retained in report, not a visual defect
 rows[0].review_basis='READING_LIMIT';rows[0].visual_issue=true;
 assert.equal(fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},observation:{objects},results:rows}).filter(g=>g.number).length,1);
});

test('text reading limits without damage evidence stay unmarked',()=>{
 const row={id:'text',rule_id:'D-02-l',parent_id:'D-02',status:'REVIEW',reason:'획을 판독할 수 없음',review_basis:'READING_LIMIT',error_type:'OCR_UNREADABLE',evidence_ids:['text'],rects:[[.2,.3,.3,.4]]};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'text',label:'작은 안내판',text_legibility:'UNREADABLE',rects:row.rects}]}});
 assert.equal(groups[0].number,null);assert.equal(groups[0].rows[0].id,row.id);
});

test('unresolved text location stays in results without using stale object coordinates',()=>{
 const row={id:'missing',rule_id:'D-02-l',parent_id:'D-02',status:'FAIL',reason:'지적한 문구 위치 미확정',evidence_ids:['sign'],rects:[[.1,.1,.3,.2]],location_unresolved:true};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'sign',label:'다른 문구',rects:row.rects}]}});
 assert.equal(groups.length,1);assert.equal(groups[0].rows[0].status,'FAIL');assert.equal(groups[0].anchor,undefined);assert.equal(groups[0].rects.length,0);
});

test('independently grounded text uses detector rectangle rather than coarse scene object',()=>{
 const rect=[.2,.3,.4,.34];
 const row={id:'text',rule_id:'D-02-l',parent_id:'D-02',status:'FAIL',reason:'문구 오류',evidence_ids:['sign'],rects:[rect],location_evidence:{status:'VERIFIED_REGION',rects:[rect]}};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'sign',label:'문구',rects:[[0,0,.7,.7]]}]}});
 assert.deepEqual(Array.from(groups[0].rects[0]),rect);
});

test('observed agency-name mismatch stays yellow even when policy references are missing',()=>{
 const row={id:'name',rule_id:'D-01-c',parent_id:'D-01',status:'REVIEW',review_basis:'OBSERVED_ANOMALY',document_review:true,reason:'행정안정부 표기가 공식 명칭과 다름 · 승인된 기준자료 미확보: policy',evidence_ids:['sign'],rects:[[.1,.1,.3,.2]]};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'sign',label:'기관명',rects:row.rects}]}});
 assert.equal(groups.length,1);assert.ok(groups[0].anchor);assert.equal(groups[0].status,'REVIEW');assert.equal(row.status,'REVIEW');
});
test('ordinary hand reading limits remain available without yellow image markers',()=>{
 const rows=['D-02-c','D-02-d','D-02-i'].map(id=>({id,rule_id:id,parent_id:'D-02',status:'REVIEW',review_basis:'READING_LIMIT',reason:'가림 때문에 손가락 구조를 확정하기 어려움',evidence_ids:['hand'],rects:[[.3,.4,.4,.5]]}));
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:rows,observation:{objects:[{id:'hand',label:'남성 오른손',text_legibility:'NOT_TEXT',rects:rows[0].rects}]}});
 assert.equal(groups.length,1);assert.equal(groups[0].rows.length,3);assert.equal(groups[0].anchor,undefined);assert.equal(groups[0].number,null);assert.equal(groups[0].status,'REVIEW');
});
test('specific hand anomalies stay visible even if some fingers are hidden',()=>{
 const row={id:'h',rule_id:'D-02-e',parent_id:'D-02',status:'REVIEW',review_basis:'READING_LIMIT',reason:'일부 가림',evidence_ids:['hand'],rects:[[.3,.4,.4,.5]],hand_scope:{hands:[{visible_structure:'ANOMALOUS',anomaly_evidence:'손가락이 손목에서 두 갈래로 연결됨'}]}};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'hand',label:'손',rects:row.rects}]}});
 assert.ok(groups[0].anchor);assert.equal(groups[0].status,'REVIEW');
 row.review_basis='OBSERVED_ANOMALY';delete row.hand_scope;
 assert.ok(fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[]}})[0].anchor);
});
test('OCR engine uncertainty without a visual defect stays in the diagnostic list',()=>{
 const row={id:'ocr',rule_id:'D-02-l',parent_id:'D-02',status:'REVIEW',review_basis:'READING_LIMIT',diagnostic_only:true,error_type:'OCR_MISMATCH',reason:'판독 차이',evidence_ids:['text'],rects:[[.1,.1,.3,.2]]};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'text',label:'문자',text:'안내',rects:row.rects}]}});
 assert.equal(groups[0].number,null);assert.equal(groups[0].anchor,undefined);
});
test('unconfirmed emblem comparison and missing paperwork stay in extra review',()=>{
 const rows=[{id:'emblem',rule_id:'H-07-g',parent_id:'H-07',status:'REVIEW',review_basis:'REFERENCE_MISSING',document_review:true,reason:'세부 도안 비교 미확정',evidence_ids:['hat'],rects:[[.3,.3,.4,.4]]},{id:'license',rule_id:'D-03-a',parent_id:'D-03',status:'REVIEW',review_basis:'DOCUMENT_CHECK',reason:'이용권 서류 필요',evidence_ids:['hat'],rects:[[.3,.3,.4,.4]]}];
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:rows,observation:{objects:[{id:'hat',label:'경찰 모자 표장',rects:rows[0].rects}]},rule_pack:{steps:[{rule_id:'H-07-g',reference_requirements:['official-emblems']}]}});
 assert.equal(groups.filter(g=>g.anchor).length,0);assert.equal(groups.flatMap(g=>g.rows).length,2);
});
test('uncertain OCR and missing location remain discoverable without an invented image position',()=>{
 const row={id:'ocr',rule_id:'D-02-l',parent_id:'D-02',status:'REVIEW',review_basis:'READING_LIMIT',error_type:'OCR_UNCERTAIN',reason:'한복/한북 독립 판독 차이',independent_reading_conflicts:[{status:'UNRESOLVED',detector_text:'한복',independent_text:'한북'}],location_unresolved:true,evidence_ids:['sign'],rects:[]};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'sign',label:'한복 체험 안내',text_legibility:'DEGRADED',rects:[[.1,.1,.3,.2]]}]}});
 assert.equal(groups[0].number,1);assert.equal(groups[0].anchor,undefined);assert.equal(groups[0].status,'REVIEW');assert.equal(groups[0].rects.length,0);
});
test('coverage fallback and a normal observation awaiting human approval do not become defect pins',()=>{
 const rows=[{id:'missing',rule_id:'D-02-i',parent_id:'D-02',status:'REVIEW',review_basis:'READING_LIMIT',coverage_fallback:true,reason:'이 행동에 대한 모델 판정 누락',evidence_ids:['hand'],rects:[[.3,.3,.4,.4]]},{id:'normal',rule_id:'D-02-e',parent_id:'D-02',status:'REVIEW',review_basis:'NONE',reason:'추가 손가락은 보이지 않음 · 사람 검토 필요',evidence_ids:['hand'],rects:[[.3,.3,.4,.4]]}];
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:rows,observation:{objects:[{id:'hand',label:'손',rects:rows[0].rects}]}});
 assert.equal(groups.filter(g=>g.anchor).length,0);assert.equal(groups.flatMap(g=>g.rows).length,2);
});
test('contradictory verdict without actual visual evidence stays in the extra review list',()=>{
 const row={id:'conflict',rule_id:'D-02-l',parent_id:'D-02',status:'REVIEW',review_basis:'READING_LIMIT',decision_conflict:true,error_type:'NONE',reason:'판정은 오류이나 설명은 오탈자 없음',evidence_ids:['text'],rects:[[.1,.1,.4,.2]]};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'text',text:'정상 문구',text_legibility:'CLEAR',rects:row.rects}]}});
 assert.equal(groups.length,1);assert.equal(groups[0].number,null);assert.equal(groups[0].anchor,undefined);
});
test('a matched trigram measurement cannot turn a separate visual REVIEW into a blue marker',()=>{
 const row={id:'review',rule_id:'H-04-i',parent_id:'H-04',status:'REVIEW',review_basis:'OBSERVED_ANOMALY',reason:'추가 도안 차이 확인',evidence_ids:['flag'],rects:[[.6,.2,.7,.3]]};
 const groups=fixture('FULL_IMAGE',true,{results:[row],analysis_observation:{objects:[{id:'flag',label:'국기',rects:row.rects}]}});
 const match=groups.find(g=>g.comparison?.status==='MATCH');assert.ok(match);assert.equal(match.status,'REVIEW');
});
test('unnumbered review list exposes every opinion and escapes model text',()=>{
 const ctx={esc:s=>String(s).replaceAll('<','&lt;').replaceAll('>','&gt;')};vm.createContext(ctx);
 vm.runInContext(source.slice(source.indexOf('function reviewMarkerKind('),source.indexOf('function issueGroups(')),ctx);
 vm.runInContext(source.slice(source.indexOf('function unmarkedReviewHTML('),source.indexOf('// Hit testing uses')),ctx);
 const rows=[{id:'a',rule_id:'D-03-a',status:'REVIEW',review_basis:'DOCUMENT_CHECK',reason:'서류 확인 <script>'},{id:'b',rule_id:'D-03-b',status:'REVIEW',review_basis:'DOCUMENT_CHECK',reason:'다른 조건 확인'}];
 const html=ctx.unmarkedReviewHTML([{id:'doc',label:'이용권',rows},{id:'pinned',number:1,anchor:[.1,.1],rows:[{...rows[0],id:'c'}]}],{});
 assert.match(html,/번호 없는 검토 의견 2건/);assert.ok(html.includes('data-finding="a"')&&html.includes('data-finding="b"'));assert.ok(!html.includes('data-finding="c"'));assert.ok(html.includes('&lt;script&gt;')&&!html.includes('<script>'));
});

test('approval exceptions cannot become visual anomalies through a model label',()=>{
 const rows=['D-04-e','D-04-d','D-03-a'].map(id=>({id,rule_id:id,parent_id:id.slice(0,4),status:'REVIEW',review_basis:'OBSERVED_ANOMALY',reason:'예외 근거 없음',evidence_ids:['person'],rects:[[.1,.1,.3,.3]]}));
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:rows,observation:{objects:[]}});
 assert.equal(groups.filter(g=>g.number).length,0);assert.equal(groups.flatMap(g=>g.rows).length,3);
});
test('diagnostic and misbound readings cannot override the visibility guard',()=>{
 for(const flag of ['diagnostic_only','coverage_fallback','binding_uncertain']){
  const row={id:flag,rule_id:'D-02-l',parent_id:'D-02',status:'REVIEW',review_basis:'OBSERVED_ANOMALY',reason:'판독 차이',error_type:'OCR_MISMATCH',[flag]:true,rects:[[.1,.1,.3,.2]]};
  assert.equal(fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row]})[0].number,null);
 }
});
test('localized physical damage and independent syllable differences retain markers',()=>{
 const row={id:'proof',rule_id:'D-02-l',parent_id:'D-02',status:'REVIEW',review_basis:'READING_LIMIT',reason:'받침 획 융합',glyph_audit_evidence:{assessment:{issue:true,location_verified:true,error_type:'VISUAL_TEXT_DEFECT'}},rects:[[.1,.1,.3,.2]]};
 assert.equal(fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row]})[0].number,1);
 row.glyph_audit_evidence={assessment:{issue:true,location_verified:true},isolated_glyphs:{reading_conflicts:[{contextual_char:'을',readings:{a:'울'}}]}};
 assert.equal(fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row]})[0].number,1);
});
