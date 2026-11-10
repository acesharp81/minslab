'use strict';
fetch('downloads/manifest.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(manifest=>{
 const root=document.querySelector('#downloads');root.replaceChildren();
 for(const file of manifest.files){const a=document.createElement('a');a.className='download';a.href='downloads/'+encodeURIComponent(file.file);a.download=file.file;const title=document.createElement('strong');title.textContent=file.title;const note=document.createElement('span');note.textContent=file.description+' · '+(file.bytes/1024/1024>=1?(file.bytes/1024/1024).toFixed(1)+' MB':Math.ceil(file.bytes/1024)+' KB');a.append(title,note);root.append(a);}
}).catch(()=>{document.querySelector('#downloads').textContent='배포 자료 목록을 불러오지 못했습니다. 잠시 후 새로 고침해 주세요. 샘플 ZIP은 위 버튼에서 받을 수 있습니다.';});
