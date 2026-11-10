"""Self-contained source dialogs for both online and downloaded HTML reports."""
import base64
import hashlib
SCRIPT=r'''(()=>{
let dialog,trigger,position;
function close(){dialog.close();if(trigger?.isConnected)trigger.focus({preventScroll:true});window.scrollTo(position.x,position.y);}
document.addEventListener('click',event=>{
 const button=event.target.closest('[data-source-ids],a[href^="#source-"]');if(!button)return;
 const ids=button.dataset.sourceIds?.split(',')||[button.getAttribute('href').slice(8)];
 const sources=ids.map(id=>document.getElementById('source-'+id)).filter(Boolean);if(!sources.length)return;
 event.preventDefault();trigger=button;position={x:window.scrollX,y:window.scrollY};
 if(!dialog){dialog=document.createElement('dialog');dialog.className='source-dialog';dialog.setAttribute('aria-label','원문 기록 확인');dialog.innerHTML='<div class="source-dialog-head"><strong>원문 기록 확인</strong><button type="button" class="source-close" aria-label="원문 팝업 닫기">닫기 ×</button></div><div class="source-dialog-content"></div>';document.body.append(dialog);dialog.querySelector('.source-close').onclick=close;dialog.addEventListener('cancel',e=>{e.preventDefault();close()});dialog.addEventListener('click',e=>{if(e.target===dialog){const b=dialog.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)close()}});}
 const content=dialog.querySelector('.source-dialog-content');content.replaceChildren(...sources.map(source=>{const clone=source.cloneNode(true);clone.removeAttribute('id');clone.hidden=false;return clone}));dialog.showModal();
});
})();'''
CSS='''
.source-check{font:inherit;font-size:11px;color:#286b50;background:#edf4ee;border:1px solid #d6e3d9;border-radius:5px;padding:3px 8px;cursor:pointer;margin-left:5px}.source-check:focus-visible,.source-close:focus-visible{outline:3px solid #799f7d;outline-offset:3px}.source-dialog{width:760px;max-width:calc(100vw - 30px);max-height:80vh;padding:0;border:1px solid #cddbcf;border-radius:12px;background:#fff;color:#213e35;box-shadow:0 16px 70px #102c3540;overflow:hidden}.source-dialog[open]{display:flex;flex-direction:column}.source-dialog::backdrop{background:#17382b70}.source-dialog-head{padding:15px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #dce5df;flex-shrink:0}.source-close{font:inherit;cursor:pointer;padding:7px 12px;border:1px solid #d7e0d8;background:#f7faf5;border-radius:6px}.source-dialog-content{padding:10px 20px 22px;overflow:auto;min-height:0}.source-dialog .source{display:block;padding:12px 0}.source-dialog blockquote{white-space:pre-wrap;overflow-wrap:anywhere;border-left:3px solid #acc6b5;padding:10px 14px;margin:12px 0;background:#f5f8f2}.source-dialog small{display:block}.source-records{display:none}.inheritance-banner{border:1px solid #d6e3d9;background:#f2f7ef;border-radius:10px;padding:14px 20px;margin:18px 0}.inheritance-banner h2{font-size:17px;margin:0 0 8px}.inheritance-banner ol{padding-left:23px;margin:8px 0}.inheritance-banner p,.inheritance-banner li{font-size:12px}.inheritance-banner small{font-size:10px}@media print{.source-dialog,.source-check{display:none!important}.inheritance-banner{break-inside:avoid}}
'''

def citation(refs):
    return '<button type="button" class="source-check" data-source-ids="'+','.join(str(int(n)) for n in refs)+'">원문 기록 확인</button>' if refs else ''

def decorate(body):
    return body.replace('</head>','<style>'+CSS+'</style></head>').replace('</body>','<script>'+SCRIPT+'</script></body>')

def csp():
    hashed=base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    return "default-src 'none'; script-src 'sha256-"+hashed+"'; style-src 'unsafe-inline'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
