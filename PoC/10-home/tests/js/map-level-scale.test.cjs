const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const s={};vm.runInNewContext(fs.readFileSync('web/assets/map-monitor.js','utf8')+';globalThis.subject=MapMonitor;',s);
test('each camera scale covers 1.5 times the linear geographic range',()=>{for(const zoom of [8.6,10,11.1,13,15.3])assert.ok(Math.abs(2**(zoom-s.subject.wideZoom(zoom))-1.5)<1e-10);});
test('region, municipality and block boundaries use the same wider scale',()=>{assert.equal(s.subject.levelAt(s.subject.wideZoom(10)-.01),'region');assert.equal(s.subject.levelAt(s.subject.wideZoom(10)),'municipality');assert.equal(s.subject.levelAt(s.subject.wideZoom(13)-.01),'municipality');assert.equal(s.subject.levelAt(s.subject.wideZoom(13)),'block');});
