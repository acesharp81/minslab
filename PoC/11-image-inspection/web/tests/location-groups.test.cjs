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

test('observed unreadable text stays spatial while document-only review stays separate',()=>{
 const row={id:'text',rule_id:'D-02-l',parent_id:'D-02',status:'REVIEW',reason:'문자 획 판독 불확실',evidence_ids:['text'],error_type:'OCR_UNREADABLE',rects:[[.2,.3,.3,.4]]};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'text',label:'작은 표지',rects:row.rects}]}});
 assert.equal(groups[0].number,1);assert.ok(groups[0].anchor);assert.equal(groups[0].status,'REVIEW');
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

test('text reading limits remain actionable without flagging ordinary background simplification',()=>{
 const row={id:'text',rule_id:'D-02-l',parent_id:'D-02',status:'REVIEW',reason:'획을 판독할 수 없음',review_basis:'READING_LIMIT',error_type:'OCR_UNREADABLE',evidence_ids:['text'],rects:[[.2,.3,.3,.4]]};
 const groups=fixture('FULL_IMAGE',false,{structural_checks:{flags:[]},results:[row],observation:{objects:[{id:'text',label:'작은 안내판',text_legibility:'UNREADABLE',rects:row.rects}]}});
 assert.equal(groups[0].number,1);
});
