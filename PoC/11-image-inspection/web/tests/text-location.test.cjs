const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const ctx={};vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function findingCells('),source.indexOf('function sourceChecksHTML(')),ctx);
test('crop recheck uses verified position even for saved rows with old cells',()=>{
 const row={cell_ids:['R01C01'],location_evidence:{status:'VERIFIED_REGION',rects:[[.5,.5,.6,.6]]}};
 assert.deepEqual(Array.from(ctx.findingCells(row)),['R07C07','R07C08','R08C07','R08C08']);
 row.location_unresolved=true;assert.equal(ctx.findingCells(row).length,0);
});
test('legacy and crop inspections retain their own cell systems',()=>{
 assert.deepEqual(Array.from(ctx.findingCells({cell_ids:['R03C04']})),['R03C04']);
 assert.deepEqual(Array.from(ctx.findingCells({crop_id:'c',cell_ids:['R03C04'],location_evidence:{status:'VERIFIED_REGION',rects:[[.5,.5,.6,.6]]}})),['R03C04']);
});
