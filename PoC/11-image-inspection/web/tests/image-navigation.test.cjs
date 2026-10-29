const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const ctx={};vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function flagRelatedRows('),source.indexOf('function locationComponents(')),ctx);vm.runInContext(source.slice(source.indexOf('function imageAnalysisTargets('),source.indexOf('function selectedAnalysisGroup(')),ctx);
const row=(id,status='FAIL')=>({id,rule_id:'D-02-l',status,evidence_ids:['text'],rects:[]});
test('unnumbered PASS and multiple opinions are clickable but gaps and absent rules are not',()=>{
 const run={scope:'FULL_IMAGE',observation:{objects:[{id:'text',label:'문구',cell_ids:['R11C03','R11C08','R99C99']}]},results:[row('a'),row('b','PASS'),row('c','NOT_APPLICABLE'),row('d','ERROR')]};
 const targets=ctx.imageAnalysisTargets(run),hits=ctx.analysisAtPoint(targets,2.5/12,10.5/12);
 assert.equal(hits.length,2);assert.equal(hits[1].row.status,'PASS');assert.equal(ctx.analysisAtPoint(targets,5/12,10.5/12).length,0);
 assert.equal(ctx.analysisAtPoint([...targets,...targets],2.5/12,10.5/12).length,2);
});
test('matching flag can be selected without visible normal pin; crop uses global result rectangles',()=>{
 const r={id:'flagcheck',rule_id:'H-04-h',status:'REVIEW',evidence_ids:[],rects:[[.7,.7,.9,.9]]};
 const run={scope:'FULL_IMAGE',results:[r],structural_checks:{flags:[{id:'normal',label:'정상 도안',status:'MATCH',rect:[.1,.1,.3,.3]}]}};
 assert.equal(ctx.analysisAtPoint(ctx.imageAnalysisTargets(run),.2,.2)[0].groupId,'structure:normal');
 run.scope='CROP';assert.equal(ctx.analysisAtPoint(ctx.imageAnalysisTargets(run),.2,.2).length,0);
 assert.equal(ctx.analysisAtPoint(ctx.imageAnalysisTargets(run),.8,.8)[0].row.id,'flagcheck');
});
test('each measured flag only opens the opinions of its observed object',()=>{
 const flags=[{id:'left',label:'왼쪽',status:'MISMATCH',rect:[.1,.1,.4,.4]},{id:'right',label:'오른쪽',status:'MATCH',rect:[.6,.1,.9,.4]}];
 const run={scope:'FULL_IMAGE',analysis_observation:{objects:[{id:'o1',rects:[[.2,.2,.3,.3]]},{id:'o2',rects:[[.7,.2,.8,.3]]}]},structural_checks:{flags},results:[{id:'a',rule_id:'H-04-i',status:'FAIL',evidence_ids:['o1'],rects:[]},{id:'b',rule_id:'H-04-i',status:'PASS',evidence_ids:['o2'],rects:[]}]};
 const targets=ctx.imageAnalysisTargets(run);
 assert.deepEqual(Array.from(ctx.analysisAtPoint(targets,.2,.2),x=>x.row.id),['a']);
 assert.deepEqual(Array.from(ctx.analysisAtPoint(targets,.7,.2),x=>x.row.id),['b']);
});
