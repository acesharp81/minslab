const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const ctx={document:{addEventListener(){}}};vm.createContext(ctx);vm.runInContext(fs.readFileSync(path.join(__dirname,'../../web/assets/collection-repairs.js'),'utf8')+';globalThis.repairs=CollectionRepairs;',ctx);
test('project-only repair without optional source IDs does not break lineage source nodes',()=>{
 const data={repairs:[{id:'general',stages:['CONSTRUCTION']},{id:'source',stages:['CONSTRUCTION'],source_ids:['lh_construction']}]},rows=[{id:'p',repair_ids:['general','source']}];
 assert.equal(ctx.repairs.relevant(data,rows,'ALL').length,2);
 assert.equal(ctx.repairs.relevant(data,rows,'CONSTRUCTION',['lh_construction']).length,1);
 assert.equal(ctx.repairs.relevant(data,rows,'SUPPLY',['lh_construction']).length,0);
 data.repairs[0].source_ids=null;assert.equal(ctx.repairs.relevant(data,rows,'ALL',['officer']).length,0);
});
