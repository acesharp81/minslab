const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app.js'),'utf8');
function setup({role=null,fail=false}={}){
 const button={disabled:false},events=[];
 const context=vm.createContext({$:()=>button,post:async path=>{events.push(path);if(fail)throw Error('연결 실패')},api:async()=>({role}),clearTimeout:id=>events.push(`clear:${id}`),timer:42,location:{reload:()=>events.push('reload')}});
 vm.runInContext(source.slice(source.indexOf('async function logoutSession(){'),source.indexOf("$('#login-button').onclick=")),context);
 return {button,events,context};
}
test('confirmed logout discards polling and reloads private page state',async()=>{
 const {button,events,context}=setup();await context.logoutSession();assert.deepEqual(events,['/logout','clear:42','reload']);assert.equal(context.timer,null);assert.equal(button.disabled,false);
});
test('remaining shared session is not reported as a successful logout',async()=>{
 const {button,events,context}=setup({role:'admin'});await assert.rejects(context.logoutSession(),/아직 남아/);assert.deepEqual(events,['/logout']);assert.equal(button.disabled,false);
});
test('network failure keeps retry available and never reloads as logged out',async()=>{
 const {button,events,context}=setup({fail:true});await assert.rejects(context.logoutSession(),/연결 실패/);assert.deepEqual(events,['/logout']);assert.equal(button.disabled,false);
});
