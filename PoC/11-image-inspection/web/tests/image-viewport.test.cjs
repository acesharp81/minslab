const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
const ctx={};vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function zoomAt('),source.indexOf('class ImageViewport')),ctx);const {zoomAt}=ctx;
test('zoom preserves the image point below the mouse',()=>{
 const view={scale:1.5,x:20,y:-10},center={x:300,y:250},point={x:350,y:200};
 const next=zoomAt(view,3,point,center);
 const newCenter={x:center.x+next.x-view.x,y:center.y+next.y-view.y};
 assert.equal((point.x-newCenter.x)/next.scale,(point.x-center.x)/view.scale);
 assert.equal((point.y-newCenter.y)/next.scale,(point.y-center.y)/view.scale);
});
test('zoom is bounded and zooming out reverses a centered zoom',()=>{
 const origin={scale:1,x:0,y:0},center={x:10,y:20};
 assert.equal(zoomAt(origin,100,center,center).scale,8);
 assert.equal(zoomAt(origin,.01,center,center).scale,.5);
 assert.equal(JSON.stringify(zoomAt(zoomAt(origin,2,center,center),1,center,center)),JSON.stringify(origin));
});
