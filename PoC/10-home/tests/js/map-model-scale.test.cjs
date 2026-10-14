const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const sandbox={};
vm.runInNewContext(fs.readFileSync('web/assets/map-3d.js','utf8').replace('return {start,render,focus,','return {modelFor,start,render,focus,')+';globalThis.model=MapThreeD.modelFor;',sandbox);
const block={id:'test',block:'A1',latitude:37.5,longitude:127,coordinate_basis:'APPROXIMATE_ADDRESS'};
const model=units=>sandbox.model({...block,target_units:units});
test('supply scale conserves units and volume from small blocks to large districts',()=>{
 for(const units of [1,199,200,201,381,558,1282,3235,3899,20000,100000]){
  const features=model(units);assert.equal(features.length,Math.ceil(units/200));
  const sum=key=>features.reduce((total,f)=>total+f.properties[key],0);
  assert.ok(Math.abs(sum('represented_units')-units)<1e-6);
  assert.ok(Math.abs(sum('render_height_m')-units*3/8)<1e-6);
  for(const f of features){assert.ok(f.properties.render_height_m>0&&f.properties.render_height_m<=75);assert.equal(f.properties.model_status,'ILLUSTRATIVE');}
 }
});
test('names and selection-independent repeated generation do not change building heights or coordinates',()=>{
 const first=model(558);const renamed=sandbox.model({...block,block:'대표 위치',target_units:558});
 assert.equal(JSON.stringify(first.map(f=>[f.geometry,f.properties.render_height_m])),JSON.stringify(renamed.map(f=>[f.geometry,f.properties.render_height_m])));
 assert.equal(JSON.stringify(first),JSON.stringify(model(558)));
});
test('unknown, zero and invalid supply never create invented buildings',()=>{
 for(const units of [null,undefined,0,-1,NaN,Infinity,'500'])assert.equal(model(units).length,0);
 assert.equal(sandbox.model({...block,target_units:200,latitude:null}).length,0);
});
test('model footprints stay the same size and do not overlap within a block',()=>{
 const features=model(20000);const boxes=features.map(f=>{const p=f.geometry.coordinates[0];return {west:Math.min(...p.map(c=>c[0])),east:Math.max(...p.map(c=>c[0])),south:Math.min(...p.map(c=>c[1])),north:Math.max(...p.map(c=>c[1]))};});
 const area=b=>(b.east-b.west)*(b.north-b.south);
 for(const box of boxes)assert.ok(Math.abs(area(box)-area(boxes[0]))<1e-12);
 for(let i=0;i<boxes.length;i++)for(let j=i+1;j<boxes.length;j++){const a=boxes[i],b=boxes[j];assert.ok(!(a.west<b.east&&a.east>b.west&&a.south<b.north&&a.north>b.south));}
});
