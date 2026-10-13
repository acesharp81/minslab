'use strict';
const tabs=[...document.querySelectorAll('[role="tab"]')];
const panels=[...document.querySelectorAll('[role="tabpanel"]')];
function selectTab(id,{focus=false,hash=false}={}){
  const active=tabs.find(tab=>tab.getAttribute('aria-controls')===id)||tabs[0];
  tabs.forEach(tab=>{const selected=tab===active;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;});
  panels.forEach(panel=>{panel.hidden=panel.id!==active.getAttribute('aria-controls');});
  if(focus)active.focus();
  if(hash){
    history.replaceState(null,'','#'+active.getAttribute('aria-controls'));
    requestAnimationFrame(()=>document.getElementById(active.getAttribute('aria-controls')).scrollIntoView({block:'start'}));
  }
}
function restoreHash(){
  let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}
  const target=document.getElementById(id);
  const panel=target?.matches('[role="tabpanel"]')?target:target?.closest('[role="tabpanel"]');
  if(panel){selectTab(panel.id);if(target!==panel)requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));}
  else if(!id)selectTab('overview');
}
tabs.forEach((tab,index)=>{
  tab.addEventListener('click',()=>selectTab(tab.getAttribute('aria-controls'),{hash:true}));
  tab.addEventListener('keydown',event=>{
    let next;if(event.key==='ArrowRight')next=(index+1)%tabs.length;
    else if(event.key==='ArrowLeft')next=(index+tabs.length-1)%tabs.length;
    else if(event.key==='Home')next=0;else if(event.key==='End')next=tabs.length-1;else return;
    event.preventDefault();selectTab(tabs[next].getAttribute('aria-controls'),{focus:true,hash:true});
  });
});
window.addEventListener('hashchange',restoreHash);restoreHash();
const dialog=document.getElementById('diagram-dialog'),expanded=document.getElementById('diagram-expanded');let zoom=100;
function resize(){const svg=expanded.querySelector('svg');if(svg)svg.style.width=zoom+'%';}
document.getElementById('report-print').addEventListener('click',()=>window.print());
// Printed reports include every tab and the expanded interface example.
const printDetails=new Map();
window.addEventListener('beforeprint',()=>document.querySelectorAll('details').forEach(item=>{printDetails.set(item,item.open);item.open=true;}));
window.addEventListener('afterprint',()=>{printDetails.forEach((open,item)=>{item.open=open;});printDetails.clear();});
document.querySelectorAll('.zoom-diagram').forEach(button=>button.addEventListener('click',()=>{
  const svg=button.closest('figure').querySelector('svg').cloneNode(true);
  // Cloned SVG definitions must not share IDs with the original diagram.
  svg.querySelectorAll('[id]').forEach(node=>{const old=node.id;node.id=old+'-expanded';svg.querySelectorAll('[marker-end]').forEach(path=>{if(path.getAttribute('marker-end')==='url(#'+old+')')path.setAttribute('marker-end','url(#'+node.id+')');});});
  expanded.replaceChildren(svg);document.getElementById('diagram-title').textContent=svg.getAttribute('aria-label');zoom=100;resize();dialog.showModal();
}));
document.getElementById('zoom-in').onclick=()=>{zoom=Math.min(300,zoom+25);resize();};
document.getElementById('zoom-out').onclick=()=>{zoom=Math.max(50,zoom-25);resize();};
document.getElementById('zoom-fit').onclick=()=>{zoom=100;resize();};
document.getElementById('zoom-close').onclick=()=>dialog.close();
