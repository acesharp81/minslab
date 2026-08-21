(function(){
  "use strict";

  var $=function(id){return document.getElementById(id)};
  var escapeHtml=function(value){return String(value==null?"":value).replace(/[&<>"']/g,function(char){return({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[char]})};
  var API="/api/poc/aiworks";
  async function api(path,options){
    var response=await fetch(API+path,Object.assign({headers:{"Content-Type":"application/json"}},options||{}));
    var data=await response.json().catch(function(){return{}});
    if(!response.ok)throw new Error(data.error||"AIWorks 서버 요청에 실패했습니다.");
    return data;
  }
  var state={
    activeView:"editor",
    restoreViewOverride:"",
    activeProjectId:null,
    activeProject:null,
    projects:[],
    archivedProjects:[],
    projectWorkspace:null,
    projectFactsLoaded:false,
    projectDocuments:[],
    projectWorkbench:null,
    activeWorkbenchTab:"",
    workspaceStateSaveTimer:null,
    restoringWorkspace:false,
    workbenchAutoSaveTimer:null,
    workbenchSaveSequence:0,
    workbenchTabCache:{},
    workbenchTabCacheOrder:[],
    pendingIntent:"",
    lastProposalIntent:"",
    pendingPlan:null,
    pendingStoreAction:"",
    builderDraft:null,
    templateAuthoringDraftId:null,
    mcpConfiguration:null,
    capabilityRegistry:[],
    builderResolution:null,
    quarantined:[],
    latestAcceptance:null,
    serverOnline:false,
    models:[],
    presets:[],
    openrouter:{configured:false,liveExecutionEnabled:false},
    originalText:$("targetParagraph").textContent,
    undoText:null,
    currentDocument:null,
    undoDocument:null,
    documentStorageKey:"aiworks.document.draft.v1",
    documentSavedSnapshot:null,
    documentAutoSaveTimer:null,
    documentSaveInFlight:null,
    documentDirty:false,
    documentUndoSnapshot:null,
    templateDocumentHtml:$("documentPaper").innerHTML,
    documentMode:"template",
    workspaceDocument:null,
    workspaceDocuments:[],
    documentVersions:[],
    nativeSession:null,
    nativeSelection:null,
    nativePreviewUrl:null,
    welcomeFile:null,
    templateSelection:null,
    lastAnswer:"",
    sourceContext:null,
    sourceEditorDirty:false,
    rhwpEditor:null,
    installed:["document.hwpx","budget.form","common-data.registry"],
    audit:[
      {time:"오늘 14:32:11",actor:"사용자",event:"문서 열기 · 예산요청서_초안.hwpx",status:"완료"},
      {time:"오늘 14:32:12",actor:"Core",event:"핵심 값 7개 추출 · 출처 위치 연결",status:"완료"},
      {time:"오늘 14:32:13",actor:"Policy",event:"외부 네트워크 전송 기본 차단",status:"적용"}
    ],
    commonData:[
      {label:"사업명",key:"project.name",value:"지능형 민원지원 기반 구축",kind:"고정",date:"2026-08-11",source:"1쪽 > 사업 개요",confidence:99},
      {label:"사업기간",key:"project.period",value:"2027.01 – 2027.12",kind:"고정",date:"2026-08-11",source:"1쪽 > 사업 개요",confidence:98},
      {label:"사업대상",key:"project.target",value:"민원 담당자·대국민 이용자",kind:"고정",date:"2026-08-11",source:"1쪽 > 사업 개요",confidence:96},
      {label:"총사업비",key:"budget.total",value:"1,284백만원",kind:"갱신",date:"2026-08-11",source:"2쪽 > 소요 예산",confidence:99},
      {label:"SW 기술자 월임금",key:"cost.engineer.monthly",value:"8,560,000원",kind:"갱신",date:"2026-01-01",source:"대가산정 가이드 > 표 2",confidence:97},
      {label:"개발 투입인력",key:"budget.engineers",value:"10명",kind:"갱신",date:"2026-08-11",source:"2쪽 > 산출 근거",confidence:95},
      {label:"개발기간",key:"budget.devMonths",value:"10개월",kind:"갱신",date:"2026-08-11",source:"2쪽 > 산출 근거",confidence:95}
    ],
    mcps:[
      {id:"document.hwpx",name:"HWPX 문서 어댑터",version:"1.2.0",runtime:"로컬",desc:"HWPX 문서 구조를 읽고 문단·표 단위 변경 제안을 적용합니다.",permissions:["문서 읽기","문서 쓰기"],rating:"4.9",publisher:"AIWorks Core"},
      {id:"budget.form",name:"예산요청서 양식",version:"1.0.3",runtime:"로컬",desc:"행정기관 예산요청서 구조와 필수 항목을 검증하고 초안을 생성합니다.",permissions:["공통데이터 읽기","문서 쓰기"],rating:"4.8",publisher:"업무자동화팀"},
      {id:"sw-cost",name:"SW 대가산정",version:"2.1.0",runtime:"하이브리드",desc:"최신 SW사업 대가산정 기준을 적용해 인력·기간별 산출 근거를 만듭니다.",permissions:["공통데이터 읽기","네트워크"],rating:"4.7",publisher:"공개 MCP"},
      {id:"common-data.registry",name:"공통데이터 레지스트리",version:"1.1.0",runtime:"로컬",desc:"업무 값을 출처·기준일·신뢰도와 함께 저장하고 시점별로 비교합니다.",permissions:["공통데이터 읽기","공통데이터 쓰기"],rating:"5.0",publisher:"AIWorks Core"},
      {id:"citation.linker",name:"출처·인용 연결기",version:"0.9.4",runtime:"로컬",desc:"생성 문장과 근거 문서의 정확한 위치를 양방향으로 연결합니다.",permissions:["문서 읽기"],rating:"4.6",publisher:"Knowledge Lab"},
      {id:"privacy.mask",name:"개인정보 마스킹",version:"1.4.1",runtime:"로컬",desc:"외부 실행 전에 개인정보와 기관 비공개 식별자를 탐지·마스킹합니다.",permissions:["문서 읽기"],rating:"4.9",publisher:"Security Lab"}
    ]
  };

  var sidebarByView={
    editor:'<div class="section-label">⌄ AIWORKS</div><div class="file-tree"><button class="tree-row"><span>⌄</span> 업무 문서</button><button class="tree-row child active"><span class="ext">한</span>예산요청서_초안.hwpx <small>M</small></button><button class="tree-row child"><span class="ext pdf">P</span>사업계획서.pdf</button><button class="tree-row"><span>⌄</span> 기준 문서</button><button class="tree-row child"><span class="ext pdf">P</span>SW대가산정_2026.pdf</button><button class="tree-row child"><span class="ext pdf">P</span>예산편성지침.pdf</button><button class="tree-row"><span>⌄</span> 산출물</button><button class="tree-row child"><span class="ext">한</span>예산요청서_완성.hwpx</button></div><div class="section-label">열린 문서</div><div class="sidebar-list"><button>한　예산요청서_초안.hwpx</button></div><div class="sidebar-stat"><div><span>문서 상태</span><b>편집 중</b></div><div><span>공통데이터</span><b>7개 연결</b></div><div><span>출처</span><b>3개</b></div></div>',
    data:'<div class="section-label">데이터 공간</div><div class="sidebar-list"><button>◇ 현재 문서 데이터　7</button><button>◇ 조직 공통데이터　24</button><button>◇ 외부 기준값　8</button></div><div class="section-label">보기</div><div class="sidebar-list"><button>현재 값</button><button>시점별 비교</button><button>출처별 보기</button><button>변경 제안</button></div>',
    builder:'<div class="section-label">MCP 제작</div><div class="sidebar-list"><button>＋ 새 MCP</button><button>초안　1</button><button>검증 대기　0</button><button>내가 게시한 MCP　2</button></div><div class="section-label">제작 단계</div><div class="sidebar-list"><button>1　목적·조건</button><button>2　Manifest</button><button>3　Schema</button><button>4　샌드박스 테스트</button><button>5　공개 범위</button></div>',
    store:'<div class="section-label">MCP 스토어</div><div class="sidebar-list"><button>추천</button><button>문서 업무</button><button>데이터·지식</button><button>개발 도구</button><button>보안·운영</button></div><div class="section-label">내 라이브러리</div><div class="sidebar-list"><button>설치됨　4</button><button>업데이트　1</button><button>사전 승인　4</button></div>',
    audit:'<div class="section-label">실행 관리</div><div class="sidebar-list"><button>오늘의 실행</button><button>승인 요청</button><button>오류·차단</button><button>변경 이력</button></div><div class="section-label">필터</div><div class="sidebar-list"><button>사용자 실행</button><button>MCP 호출</button><button>모델 호출</button><button>데이터 접근</button></div>',
    settings:'<div class="section-label">설정</div><div class="sidebar-list"><button>모델 라우팅</button><button>MCP 권한</button><button>데이터 정책</button><button>샌드박스</button><button>감사·보존</button></div>'
  };
  var titleByView={editor:"탐색기",data:"공통데이터",builder:"MCP 제작기",store:"MCP 스토어",audit:"실행 이력",settings:"설정"};

  function toast(message){
    $("toast").textContent=message;$("toast").classList.add("show");
    clearTimeout(toast.timer);toast.timer=setTimeout(function(){$("toast").classList.remove("show")},2200);
  }
  function setStatus(message){$("statusText").textContent=message}
  function updateOrchestration(phase,status,model){
    var dock=$("orchestrationDock");if(!dock)return;
    status=status||"idle";dock.classList.toggle("is-active",status==="active");dock.classList.toggle("is-error",status==="error");
    $("orchestrationPhase").textContent=phase||"프로젝트 작업 준비";
    $("orchestrationProgress").textContent=status==="active"?"진행 중":status==="error"?"확인 필요":status==="done"?"완료":"대기";
    if(model)$("orchestrationModel").textContent=model;
  }
  function updateProjectContext(){
    var summary=state.projectWorkspace&&state.projectWorkspace.summary||{};
    var projectName=state.activeProject&&state.activeProject.name||"프로젝트 미선택";
    $("contextProject").textContent="◫ "+projectName;
    $("orchestrationResources").textContent="MD "+Number(summary.documentCount||0)+" · 메타 "+Number(summary.factCount||0)+" · 파생 "+Number(summary.artifactCount||0);
    $("welcomeProjectName").textContent=projectName;
    $("orchestratorState").textContent=state.activeProject?"프로젝트 문맥 연결됨 · "+projectName:"프로젝트를 먼저 선택하세요";
  }
  function captureProjectChat(){
    return Array.from($("chat").querySelectorAll(".message")).slice(-100).map(function(node){
      return{role:node.classList.contains("user")?"user":"assistant",text:node.textContent.trim(),kind:node.classList.contains("workflow-message")?"workflow":"message"};
    }).filter(function(item){return item.text});
  }
  function renderProjectChat(items){
    $("chat").innerHTML="";
    (items||[]).forEach(function(item){
      var node=document.createElement("div");node.className="message "+(item.role==="user"?"user":"assistant")+(item.kind==="workflow"?" workflow-message":"");
      node.innerHTML=item.role==="user"?"<div>"+escapeHtml(item.text)+"</div>":"<span class='mini-orb'>✦</span><div><p>"+escapeHtml(item.text)+"</p></div>";
      $("chat").appendChild(node);
    });
    $("chat").scrollTop=$("chat").scrollHeight;
  }
  function scheduleWorkspaceStateSave(immediate){
    if(!state.activeProjectId||state.restoringWorkspace)return;
    clearTimeout(state.workspaceStateSaveTimer);
    var save=function(){
      var documentId=state.projectWorkbench&&state.projectWorkbench.document&&state.projectWorkbench.document.id||"";
      api("/projects/"+encodeURIComponent(state.activeProjectId)+"/workspace-state",{method:"POST",body:JSON.stringify({active_document_id:documentId,active_tab:state.activeWorkbenchTab||"markdown",active_view:state.activeView||"editor",chat:captureProjectChat(),last_answer:state.lastAnswer||"",actor:"workspace-user"})}).catch(function(){});
    };
    if(immediate)save();else state.workspaceStateSaveTimer=setTimeout(save,450);
  }
  function showProjectGate(){
    $("workbench").hidden=true;$("welcomeScreen").hidden=false;$("projectGate").hidden=false;$("welcomeTask").hidden=true;
    updateOrchestration("프로젝트 선택 대기","idle","Solar 자동 선택");
  }
  async function requestProjectChange(){
    if((state.sourceEditorDirty||state.documentDirty||state.nativeSession&&state.rhwpEditor)&&!await saveDocumentChanges()){toast("현재 문서를 저장한 뒤 프로젝트를 변경해 주세요.");return}
    await loadProjects();showProjectGate();
  }
  function renderProjectList(){
    var host=$("projectList");if(!host)return;
    if(!state.projects.length&&!state.archivedProjects.length){host.innerHTML="<div class='project-list-empty'>사용할 프로젝트가 없습니다.<br>왼쪽에서 새 프로젝트를 만들어 주세요.</div>";return}
    var activeHtml=state.projects.map(function(project){
      var updated=project.updatedAt?new Date(project.updatedAt).toLocaleDateString("ko-KR"):"-";
      return"<button class='project-list-item' type='button' data-select-project='"+escapeHtml(project.id)+"'><strong>"+escapeHtml(project.name)+"</strong><span>MD "+Number(project.documentCount||0)+" · 메타 "+Number(project.factCount||0)+" · 파생 "+Number(project.artifactCount||0)+"</span><small>열기</small><i>최근 작업 "+escapeHtml(updated)+" · "+escapeHtml(project.classification||"internal")+"</i></button>";
    }).join("");
    var archivedHtml=state.archivedProjects.length?"<div class='project-archive-divider'><span>보관된 프로젝트</span><small>"+state.archivedProjects.length+"</small></div>"+state.archivedProjects.map(function(project){
      var updated=project.updatedAt?new Date(project.updatedAt).toLocaleDateString("ko-KR"):"-";
      return"<div class='project-list-item archived'><strong>"+escapeHtml(project.name)+"</strong><span>문서와 메타정보가 보존되어 있습니다.</span><button type='button' data-restore-project='"+escapeHtml(project.id)+"'>복원</button><i>보관일 "+escapeHtml(updated)+" · "+escapeHtml(project.classification||"internal")+"</i></div>";
    }).join(""):"";
    host.innerHTML=activeHtml+archivedHtml;
    host.querySelectorAll("[data-select-project]").forEach(function(button){button.onclick=function(){selectProject(button.dataset.selectProject)}});
    host.querySelectorAll("[data-restore-project]").forEach(function(button){button.onclick=async function(){
      button.disabled=true;
      try{
        await api("/projects/"+encodeURIComponent(button.dataset.restoreProject)+"/status",{method:"POST",body:JSON.stringify({action:"restore",actor:"workspace-user"})});
        await loadProjects();toast("프로젝트를 복원했습니다.");
      }catch(error){button.disabled=false;toast(error.message)}
    }});
  }
  async function downloadProjectBackup(){
    if(!state.activeProjectId)return toast("프로젝트를 먼저 선택하세요.");
    setStatus("프로젝트 백업 구성 중");
    try{
      var bundle=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/backup"),blob=new Blob([JSON.stringify(bundle,null,2)],{type:"application/json"}),url=URL.createObjectURL(blob),link=document.createElement("a");
      link.href=url;link.download=bundle.filename||"AIWorks-project.aiworks.json";document.body.appendChild(link);link.click();link.remove();setTimeout(function(){URL.revokeObjectURL(url)},1000);
      toast("MD·메타정보·파생 파일·근거 백업을 다운로드했습니다.");setStatus("프로젝트 백업 완료");
    }catch(error){toast(error.message);setStatus("프로젝트 백업 실패")}
  }
  async function importProjectBackupFile(file){
    if(!file)return;
    if(file.size>50*1024*1024){toast("프로젝트 백업은 50MB를 넘을 수 없습니다.");return}
    setStatus("프로젝트 백업 무결성 확인 중");
    try{
      var bundle=JSON.parse(await file.text()),result=await api("/projects/import",{method:"POST",body:JSON.stringify({bundle:bundle,actor:"workspace-user"})});
      await loadProjects();$("projectBackupFile").value="";toast("백업을 새 프로젝트로 복원했습니다.");await selectProject(result.project.id);
    }catch(error){toast(error.message);setStatus("프로젝트 가져오기 실패")}
  }

  async function loadProjects(){
    var host=$("projectList");if(host)host.innerHTML="<div class='project-list-loading'>프로젝트를 불러오는 중입니다.</div>";
    try{
      var results=await Promise.all([api("/projects"),api("/projects/archived")]);
      state.projects=results[0].items||[];state.archivedProjects=results[1].items||[];renderProjectList();
    }catch(error){if(host)host.innerHTML="<div class='project-list-empty'>프로젝트 목록을 불러오지 못했습니다.<br>"+escapeHtml(error.message)+"</div>"}
  }
  async function refreshActiveProjectWorkspace(){
    if(!state.activeProjectId)return null;
    var workspace=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/workspace");
    state.projectWorkspace=workspace;state.activeProject=workspace.project;state.projectDocuments=workspace.documents||[];state.projectFactsLoaded=false;
    updateProjectContext();renderEditorSidebar();return workspace;
  }
  async function selectProject(projectId){
    updateOrchestration("프로젝트 문서와 메타정보 복원","active","Solar 자동 선택");setStatus("프로젝트 작업공간 불러오는 중");
    try{
      state.restoreViewOverride="";
      clearWorkbenchTabCache();clearWorkbenchCanvas();state.restoringWorkspace=true;state.activeProjectId=projectId;state.projectWorkbench=null;state.activeWorkbenchTab="";state.nativeSession=null;state.sourceContext=null;state.lastAnswer="";
      var workspace=await refreshActiveProjectWorkspace();
      var saved=workspace.workspaceState||{};state.lastAnswer=String(saved.lastAnswer||"");renderProjectChat(saved.chat||[]);
      $("projectGate").hidden=true;
      var summary=workspace.summary||{};updateOrchestration("프로젝트 작업공간 복원 완료","done","Solar 자동 선택");
      setStatus(workspace.project.name+" · MD "+Number(summary.documentCount||0)+" · 메타 "+Number(summary.factCount||0)+" · 파생 "+Number(summary.artifactCount||0));
      if((workspace.documents||[]).length){
        var restoredDocument=(workspace.documents||[]).find(function(item){return item.id===saved.activeDocumentId})||workspace.documents[0];
        state.projectWorkbench=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+restoredDocument.id+"/workbench");state.activeWorkbenchTab=saved.activeTab||"markdown";renderProjectWorkbenchTabs();
        enterWorkspace(true);await switchProjectWorkbenchTab(state.activeWorkbenchTab,{restoring:true});
        setView(state.restoreViewOverride||saved.activeView||"editor",{restoring:true});state.restoreViewOverride="";
      }else{$("welcomeTask").hidden=false;activateEmptyWorkspace()}
      if((saved.chat||[]).length===0&&workspace.documents.length)addAssistant(workspace.project.name+" 프로젝트의 마지막 문서와 작업 탭을 복원했습니다.",{skipPersist:true});
      await loadProjectFacts(true);state.restoringWorkspace=false;scheduleWorkspaceStateSave(false);toast(workspace.project.name+" 프로젝트의 마지막 작업을 복원했습니다.");
    }catch(error){state.restoringWorkspace=false;state.activeProjectId=null;state.activeProject=null;state.projectWorkspace=null;updateProjectContext();updateOrchestration("프로젝트 복원 실패","error");toast(error.message)}
  }
  async function openSelectedProjectWorkspace(){
    if(!state.activeProjectId){showProjectGate();toast("프로젝트를 먼저 선택하세요.");return}
    enterWorkspace(true);
    var summary=state.projectWorkspace&&state.projectWorkspace.summary||{};
    if(!$("chat").querySelector(".message"))addAssistant((state.activeProject&&state.activeProject.name||state.activeProjectId)+" 프로젝트를 열었습니다. MD "+Number(summary.documentCount||0)+"개, 메타정보 "+Number(summary.factCount||0)+"개, 파생 파일 "+Number(summary.artifactCount||0)+"개를 작업 문맥으로 사용합니다.");
    if(state.projectWorkbench){renderProjectWorkbenchTabs();await switchProjectWorkbenchTab(state.activeWorkbenchTab||"markdown")}else activateEmptyWorkspace();
    renderEditorSidebar();updateOrchestration("다음 업무 요청 대기","idle","Solar 자동 선택");setView("editor");
  }
  function enterWorkspace(studioMode){
    $("welcomeScreen").hidden=true;$("workbench").hidden=false;
    $("workbench").classList.toggle("studio-mode",studioMode!==false);
  }
  function configureEditorPlugin(session){
    var adapter=session&&session.adapter||"document.hwpx@1.2.0";var isSource=/markdown|code\.editor/.test(adapter);
    var name=/markdown/.test(adapter)?"Markdown 편집기 MCP":/code\.editor/.test(adapter)?"코드 편집기 MCP":"RHWP 한글 편집기 MCP";
    $("editorPluginName").textContent=name;$("editorPluginRoute").textContent=adapter;
    $("editorPluginBar").querySelector(".plugin-mark").textContent=/markdown/.test(adapter)?"MD":/code\.editor/.test(adapter)?"</>":"한";
    $("hwpMenuBar").classList.toggle("is-source",isSource);
    $("hwpMenuBar").innerHTML=isSource?"<button>파일</button><button>편집</button><button>선택</button><button>보기</button><button>명령</button>":"<button>파일</button><button>편집</button><button>보기</button><button>입력</button><button>서식</button><button>쪽</button><button>표</button><button>도구</button>";
    var loaded=session&&session.workspace&&session.workspace.loadedMcps||[adapter];
    $("loadedMcpBadges").innerHTML=loaded.map(function(id){return"<i>"+escapeHtml(id)+"</i>"}).join("");
    $("contextFile").textContent="⌁ "+(session?session.filename:$("activeFileName").textContent);
    $("orchestratorState").textContent=session?"의도 분석 완료 · "+loaded.length+"개 MCP 로딩":state.activeProject?"프로젝트 문맥 연결됨 · "+state.activeProject.name:"프로젝트를 먼저 선택하세요";
  }
  function addAudit(actor,event,status){
    state.audit.unshift({time:"방금",actor:actor,event:event,status:status||"완료"});
    if(state.activeView==="audit")renderAudit();
  }
  function documentEditableNodes(){
    return Array.from(document.querySelectorAll("#documentPaper [data-edit-id]"));
  }
  function sanitizeEditableHtml(value){
    var template=document.createElement("template");template.innerHTML=String(value==null?"":value);
    var allowed={B:true,STRONG:true,I:true,EM:true,BR:true,UL:true,OL:true,LI:true,DIV:true,P:true};
    Array.from(template.content.querySelectorAll("*")).reverse().forEach(function(node){
      if(!allowed[node.tagName]){node.replaceWith(document.createTextNode(node.textContent));return}
      Array.from(node.attributes).forEach(function(attribute){node.removeAttribute(attribute.name)});
    });
    return template.innerHTML;
  }
  function documentSnapshot(){
    var result={};documentEditableNodes().forEach(function(node){result[node.dataset.editId]=sanitizeEditableHtml(node.innerHTML)});return result;
  }
  function restoreDocumentSnapshot(snapshot){
    if(!snapshot||typeof snapshot!=="object")return;
    documentEditableNodes().forEach(function(node){if(Object.prototype.hasOwnProperty.call(snapshot,node.dataset.editId))node.innerHTML=sanitizeEditableHtml(snapshot[node.dataset.editId])});
    updateLivePreview();
  }
  function updateLivePreview(){
    var preview=$("liveDocumentPreview");var paper=$("documentPaper");if(!preview||!paper)return;
    var clone=paper.cloneNode(true);clone.removeAttribute("id");clone.classList.add("preview-document");
    clone.querySelectorAll("[contenteditable],[role],[aria-label],[data-edit-id],[data-hwpx-target]").forEach(function(node){node.removeAttribute("contenteditable");node.removeAttribute("role");node.removeAttribute("aria-label");node.removeAttribute("data-edit-id");node.removeAttribute("data-hwpx-target")});
    preview.replaceChildren(clone);
  }
  function applyDocumentFormat(command,value){
    if(state.documentMode==="native-session"){toast("가져온 문서의 서식은 RHWP MCP HAction에서 적용하세요.");return}
    var selection=window.getSelection();var anchor=selection&&selection.anchorNode;var editable=anchor&&(anchor.nodeType===3?anchor.parentElement:anchor).closest("#documentPaper [contenteditable='true']");
    if(!editable){toast("서식을 적용할 문서 내용을 먼저 선택하세요.");return}
    state.documentUndoSnapshot=state.documentUndoSnapshot||documentSnapshot();
    document.execCommand(command,false,value||null);markDocumentDirty();editable.focus();
  }
  function updateDocumentSaveState(message,dirty){
    state.documentDirty=Boolean(dirty);$("documentSaveState").textContent=message;
    var tab=document.querySelector(".editor-tabs>button i");if(tab)tab.style.color=dirty?"#ffd477":"#5ed8c5";
  }
  function saveBrowserDocumentDraft(manual){
    try{localStorage.setItem(state.documentStorageKey,JSON.stringify(documentSnapshot()))}catch(error){if(manual)throw error}
    if(manual){state.documentSavedSnapshot=documentSnapshot();state.documentUndoSnapshot=null}
    updateDocumentSaveState(manual?"저장됨 · 브라우저 초안":"자동 초안 저장됨",false);
  }
  function markDocumentDirty(){
    updateDocumentSaveState("편집 중 · 저장 필요",true);
    updateLivePreview();
    clearTimeout(state.documentAutoSaveTimer);
    state.documentAutoSaveTimer=setTimeout(function(){saveBrowserDocumentDraft(false)},700);
  }
  function enableTemplateEditing(){
    var candidates=document.querySelectorAll("#documentPaper h1,#documentPaper .doc-subtitle,#documentPaper td,#targetParagraph,#documentPaper [data-report-editable]");
    candidates.forEach(function(node,index){node.dataset.editId=node.id||node.dataset.field||"document-field-"+index;node.contentEditable="true";node.spellcheck=true;node.setAttribute("role","textbox");node.setAttribute("aria-label","문서 내용 직접 편집")});
  }
  function initializeDirectEditing(){
    enableTemplateEditing();
    try{restoreDocumentSnapshot(JSON.parse(localStorage.getItem(state.documentStorageKey)||"null"))}catch(error){localStorage.removeItem(state.documentStorageKey)}
    $("documentPaper").addEventListener("mouseup",captureTemplateSelection);
    $("documentPaper").addEventListener("keyup",function(event){if(event.shiftKey)captureTemplateSelection()});
    state.documentSavedSnapshot=documentSnapshot();
    $("documentPaper").addEventListener("input",markDocumentDirty);
    $("documentPaper").addEventListener("focusin",function(event){if(event.target.closest("[contenteditable='true']")&&!state.documentUndoSnapshot)state.documentUndoSnapshot=documentSnapshot()});
    $("documentPaper").addEventListener("paste",function(event){var target=event.target.closest("[contenteditable='true']");if(!target)return;event.preventDefault();document.execCommand("insertText",false,(event.clipboardData||window.clipboardData).getData("text"))});
    $("documentPaper").addEventListener("keydown",function(event){if(event.key==="Enter"&&event.target.closest("td")){event.preventDefault();event.target.blur()}});
  }
  function captureTemplateSelection(){
    if(state.documentMode==="native-session")return;
    var active=document.activeElement;
    if(active&&active!==document.body&&!(active.closest&&active.closest("#documentPaper")))return;
    var selection=window.getSelection();if(!selection||!selection.rangeCount)return;
    var anchor=selection.anchorNode,element=anchor&&(anchor.nodeType===3?anchor.parentElement:anchor);
    var editable=element&&element.closest("#documentPaper [contenteditable='true']");
    var before=selection.toString();
    if(!editable||!before.trim())return;
    var full=editable.textContent,start=full.indexOf(before);if(start<0)return;
    state.templateSelection={target:editable,before:before,start:start,end:start+before.length,editId:editable.dataset.editId||"document.selection"};
    $("contextSelection").textContent="선택: "+before.slice(0,42)+(before.length>42?"…":"");$("contextSelection").classList.add("has-selection");
    $("chatInput").placeholder="선택한 글귀에 요청할 작업을 입력하세요...";
  }
  function documentExcerpt(){
    if(state.sourceContext&&state.sourceContext.excerpt)return state.sourceContext.excerpt.slice(0,8000);
    if(state.nativeSession&&state.nativeSession.snapshot){
      var snapshot=state.nativeSession.snapshot;
      if(snapshot.content)return String(snapshot.content).slice(0,8000);
      if(snapshot.document&&snapshot.document.paragraphs)return snapshot.document.paragraphs.map(function(item){return item.text}).join("\n").slice(0,8000);
    }
    return $("documentPaper").textContent.trim().slice(0,8000);
  }
  function currentRequestContext(){
    var selection=state.nativeSelection&&state.nativeSelection.before?state.nativeSelection:state.templateSelection;
    var filename=state.sourceContext&&state.sourceContext.filename||state.nativeSession&&state.nativeSession.filename||$("activeFileName").textContent;
    return{
      document_id:state.nativeSession?state.nativeSession.id:state.workspaceDocument?state.workspaceDocument.id:"workspace-document",
      current_markdown_document_id:state.projectWorkbench&&state.projectWorkbench.document&&state.projectWorkbench.document.id||"",
      current_markdown_revision:state.projectWorkbench&&state.projectWorkbench.document&&state.projectWorkbench.document.revision||null,
      project_id:state.activeProjectId,
      classification:"internal",
      has_attachment:Boolean(state.sourceContext),
      has_selection:Boolean(selection&&selection.before),
      filename:filename,
      selection_id:selection?(selection.editId||selection.target||"document.selection"):"",
      selection_text:selection&&selection.before||"",
      previous_answer:state.lastAnswer||"",
      document_excerpt:documentExcerpt()
    };
  }
  function addWorkflowPipeline(workflow){
    if(!workflow)return;
    var node=document.createElement("div");node.className="message assistant workflow-message";
    node.innerHTML="<span class='mini-orb'>⌘</span><div><p><b>동적 MCP 로딩</b></p><div class='pipeline'>"+(workflow.loadedMcps||[]).map(function(id,index){return"<span>"+(index+1)+". "+escapeHtml(id)+"</span>"}).join("")+"</div></div>";
    $("chat").appendChild(node);$("chat").scrollTop=$("chat").scrollHeight;scheduleWorkspaceStateSave(false);
  }
  function activateEmptyWorkspace(){
    state.templateDocumentHtml="<div class='doc-meta'><span>새 업무 프로젝트</span><span>"+new Date().toLocaleDateString("ko-KR")+"</span></div><h1>프로젝트 작업공간</h1><p class='doc-subtitle'>대화에서 자료를 조회하거나 새로운 산출물을 요청하세요.</p><section><h2>아직 생성된 산출물이 없습니다.</h2><p id='targetParagraph' data-report-editable>분석 결과를 바탕으로 보고서 작성을 요청하면 필요한 MCP가 로딩되고 이 영역에 편집 가능한 산출물이 열립니다.</p></section>";
    activateTemplateDocument({},"새 프로젝트",null);configureEditorPlugin({filename:"새 프로젝트",adapter:"output.text@1.0.0",workspace:{loadedMcps:["output.text@1.0.0"]}});
  }
  async function openGeneratedArtifact(artifact,loadedMcps){
    if(!artifact||artifact.format!=="hwpx"||!artifact.contentBase64)throw new Error("보고서 MCP가 RHWP용 HWPX 산출물을 반환하지 않았습니다.");
    state.templateSelection=null;
    var filename=artifact.filename||((artifact.title||"AIWorks 파생 보고서")+".hwpx");
    var sourceMarkdown=artifact.markdownDocument||{};
    var projectArtifact=artifact.projectArtifact||{};
    var session=await api("/documents/sessions",{method:"POST",body:JSON.stringify({filename:filename,content_base64:artifact.contentBase64,intent:(artifact.title||"파생 보고서")+"를 RHWP에서 열고 후속 MCP 편집",project_id:state.activeProjectId,markdown_document_id:sourceMarkdown.id||"",markdown_base_revision:sourceMarkdown.revision,project_artifact_id:projectArtifact.id||"",canonical_markdown:String(artifact.content||""),confirmed:true,actor:"workspace-user"})});
    state.sourceContext={filename:filename,excerpt:String(artifact.content||"").slice(0,8000),sessionId:session.id,derived:true};
    await renderNativeSession(session);
    if(sourceMarkdown.id){state.projectWorkbench=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+sourceMarkdown.id+"/workbench");state.activeWorkbenchTab="artifact:hwpx";renderProjectWorkbenchTabs()}
    $("contextFile").textContent="⌁ "+filename;if(!state.restoringWorkspace)setView("editor");updateLivePreview();
    return session;
  }
  function applyTemplateSelection(before,after){
    var selected=state.templateSelection;if(!selected||!selected.target||!selected.target.isConnected)return false;
    var target=selected.target,full=target.textContent,index=full.slice(selected.start,selected.end)===before?selected.start:full.indexOf(before);if(index<0)return false;
    var stage=document.querySelector(".document-stage"),scrollTop=stage.scrollTop;
    target.textContent=full.slice(0,index)+after+full.slice(index+before.length);markDocumentDirty();target.focus();stage.scrollTop=scrollTop;
    state.templateSelection=null;$("contextSelection").textContent="선택 영역 없음";$("contextSelection").classList.remove("has-selection");return true;
  }
  function activateTemplateDocument(content,name,workspace){
    state.nativeSession=null;state.nativeSelection=null;$("workbench").classList.remove("native-rhwp-mode");document.querySelector(".app-shell").classList.remove("native-rhwp-shell");["nativeCompactTitle","aiSelectionMode"].forEach(function(id){var node=$(id);if(node)node.remove()});if(state.nativePreviewUrl){URL.revokeObjectURL(state.nativePreviewUrl);state.nativePreviewUrl=null}var nativePanel=$("nativeMcpPanel");if(nativePanel)nativePanel.remove();
    $("documentPaper").innerHTML=state.templateDocumentHtml;enableTemplateEditing();restoreDocumentSnapshot(content||{});
    state.currentDocument=null;state.undoDocument=null;state.workspaceDocument=workspace||null;state.documentMode="template";
    state.documentStorageKey=workspace?"aiworks.document."+workspace.id:"aiworks.document.draft.v1";
    state.documentSavedSnapshot=documentSnapshot();state.documentUndoSnapshot=null;updateDocumentSaveState("서버 문서 열림 · 저장됨",false);
    $("activeFileName").textContent=name||"새 예산요청서";
    updateLivePreview();
  }
  async function openWorkspaceDocument(documentId){
    if(state.documentDirty&&!window.confirm("저장하지 않은 편집을 버리고 다른 문서를 열까요?"))return;
    try{setStatus("작업 문서 여는 중");var document=await api("/documents/workspace/"+documentId);activateTemplateDocument(document.content,document.name,document);setStatus("작업 문서 열림 · revision "+document.revision);toast(document.name+"을 열었습니다.");setView("editor")}catch(error){toast(error.message)}
  }
  async function openDocumentVersion(versionId){
    if(state.documentDirty&&!window.confirm("저장하지 않은 편집을 버리고 HWPX 버전을 열까요?"))return;
    try{
      setStatus("HWPX 버전 여는 중");var version=await api("/documents/versions/"+versionId);
      var binary=atob(version.contentBase64);var bytes=new Uint8Array(binary.length);for(var index=0;index<binary.length;index+=1)bytes[index]=binary.charCodeAt(index);
      await importHwpx(new File([bytes],version.filename,{type:"application/hwp+zip"}));toast(version.filename+" 버전을 다시 열었습니다.");
    }catch(error){setStatus("HWPX 버전 열기 실패");toast(error.message)}
  }
  function renderEditorSidebar(){
    if(state.activeView!=="editor"||!state.activeProjectId)return;
    var projectDocuments=state.projectDocuments.map(function(item){return"<button class='tree-row child "+(state.projectWorkbench&&state.projectWorkbench.document.id===item.id?"active":"")+"' data-project-workbench='"+escapeHtml(item.id)+"'><span class='ext md'>MD</span>"+escapeHtml(item.title)+" <small>r"+item.revision+"</small></button>"}).join("");
    var artifacts=state.projectDocuments.reduce(function(items,documentData){return items.concat((documentData.artifacts||[]).map(function(artifact){return{documentId:documentData.id,format:artifact.format,status:artifact.status,filename:artifact.filename||documentData.title+"."+artifact.format}}))},[]).map(function(item){return"<button class='tree-row child' data-project-artifact-doc='"+escapeHtml(item.documentId)+"' data-project-artifact-format='"+escapeHtml(item.format)+"'><span class='ext'>"+escapeHtml(item.format.slice(0,2).toUpperCase())+"</span>"+escapeHtml(item.filename)+" <small>"+escapeHtml(item.status)+"</small></button>"}).join("");
    var summary=state.projectWorkspace&&state.projectWorkspace.summary||{};
    $("sidebarContent").innerHTML="<div class='section-label'>현재 프로젝트</div><div class='project-sidebar-head'><b>"+escapeHtml(state.activeProject&&state.activeProject.name||state.activeProjectId)+"</b><button id='sidebarChangeProject'>변경</button></div><div class='file-tree'><button class='tree-row' id='projectMetadataRow'><span>◇</span>프로젝트 메타정보 <small>"+Number(summary.factCount||0)+"</small></button></div><div class='section-label'>Markdown 원본</div><div class='file-tree'>"+(projectDocuments||"<div class='sidebar-empty'>프로젝트 문서 없음</div>")+"</div><div class='section-label'>파생 파일</div><div class='file-tree'>"+(artifacts||"<div class='sidebar-empty'>생성된 파생 파일 없음</div>")+"</div><div class='sidebar-stat'><div><span>프로젝트 MD</span><b>"+Number(summary.documentCount||0)+"개</b></div><div><span>메타정보</span><b>"+Number(summary.factCount||0)+"개</b></div><div><span>파생 파일</span><b>"+Number(summary.artifactCount||0)+"개</b></div></div>";
    $("sidebarChangeProject").onclick=requestProjectChange;
    $("projectMetadataRow").onclick=function(){if(state.projectWorkbench)switchProjectWorkbenchTab("metadata");else{setView("data");loadProjectFacts(true)}};
    document.querySelectorAll("[data-project-workbench]").forEach(function(button){button.onclick=function(){openProjectWorkbench(button.dataset.projectWorkbench,"markdown")}});
    document.querySelectorAll("[data-project-artifact-doc]").forEach(function(button){button.onclick=function(){openProjectWorkbench(button.dataset.projectArtifactDoc,"artifact:"+button.dataset.projectArtifactFormat)}});
  }
  async function syncDocumentLibrary(){
    if(!state.activeProjectId)return;
    try{await refreshActiveProjectWorkspace()}catch(error){if(state.activeView==="editor")setStatus("프로젝트 문서 목록을 불러오지 못함")}
  }
  function renderImportedHwpx(result){
    var paper=$("documentPaper");var paragraphs=result.paragraphs||[];
    var paragraphById={};var paragraphIndex={};paragraphs.forEach(function(item,index){paragraphById[item.id]=item;paragraphIndex[item.id]=index});
    var firstRendered=true;
    function renderParagraph(paragraphId,inCell){
      var item=paragraphById[paragraphId];if(!item)return"";
      var index=paragraphIndex[paragraphId];var first=firstRendered;firstRendered=false;
      return"<p "+(first?"id='targetParagraph' ":"")+"class='native-document-block "+(first?"selected ":"")+(inCell?"table-paragraph":"")+"' tabindex='0' data-native-target='"+escapeHtml(item.id)+"'>"+(item.text?escapeHtml(item.text):"<br>")+"</p>";
    }
    var sections=result.layout&&result.layout.sections||[];
    var structure=sections.map(function(section){
      return"<section class='hwpx-section' data-section='"+escapeHtml(section.id)+"'>"+(section.blocks||[]).map(function(block){
        if(block.type==="paragraph")return renderParagraph(block.paragraphId,false);
        if(block.type==="table")return"<div class='hwpx-table-wrap'><table class='hwpx-table'><tbody>"+block.rows.map(function(row){return"<tr>"+row.cells.map(function(cell){var sizing=(cell.widthPx?"width:"+Number(cell.widthPx)+"px;":"")+(cell.heightPx?"height:"+Number(cell.heightPx)+"px;":"");return"<td rowspan='"+Number(cell.rowSpan||1)+"' colspan='"+Number(cell.colSpan||1)+"' style='"+sizing+"'>"+cell.paragraphIds.map(function(id){return renderParagraph(id,true)}).join("")+"</td>"}).join("")+"</tr>"}).join("")+"</tbody></table></div>";
        if(block.type==="object")return"<div class='hwpx-object-placeholder'><span>개체</span><b>"+escapeHtml(block.objectType)+"</b><small>정확한 배치는 Windows RHWP 원본 미리보기에서 확인</small></div>";
        return"";
      }).join("")+"</section>";
    }).join("");
    if(!structure)structure="<section class='imported-paragraphs'>"+paragraphs.map(function(item){return renderParagraph(item.id,false)}).join("")+"</section>";
    var stats=result.stats||{};
    paper.className="paper";
    paper.innerHTML="<div class='editor-ruler'><span><b>1</b><b>2</b><b>3</b><b>4</b><b>5</b><b>6</b><b>7</b><b>8</b><b>9</b><b>10</b></span></div><div class='native-editor-attribution'><b>RHWP AI 선택 모드</b><span>원본 구조를 유지한 문단·표 단위 AI 변경</span></div><div class='doc-meta'><span>가져온 HWPX · AI 선택 모드</span><span>"+new Date().toLocaleDateString("ko-KR")+"</span></div><h1>"+escapeHtml(result.document.name)+"</h1><p class='doc-subtitle'>문단 "+paragraphs.length+"개 · 표 "+Number(stats.tables||0)+"개 · 셀 "+Number(stats.cells||0)+"개 · 개체 "+Number(stats.objects||0)+"개</p>"+structure;
    paper.querySelectorAll("[data-native-target]").forEach(function(node){node.setAttribute("role","button");node.setAttribute("aria-label",node.closest("td")?"MCP로 수정할 표 셀 문단 선택":"MCP로 수정할 문단 선택")});
    state.documentMode="native-session";state.documentStorageKey="aiworks.native-session";
    updateLivePreview();
  }
  function ensureNativeMcpPanel(){
    var panel=$("nativeMcpPanel");
    if(!panel){
      panel=document.createElement("aside");panel.id="nativeMcpPanel";panel.className="native-mcp-panel";
      $("documentPaper").insertAdjacentElement("afterend",panel);
    }
    var session=state.nativeSession;var nativeRuntime=session&&session.runtime==="windows-native-bridge";
    panel.innerHTML="<div class='native-mcp-head'><span class='mcp-logo'>한</span><div><b>문서 MCP 세션</b><small>"+escapeHtml(session?session.adapter:"-")+" · revision "+Number(session?session.revision:0)+"</small></div></div><div class='native-route'><span>"+(nativeRuntime?"RHWP 원본 실행":"HWPX 안전 대체")+"</span><small>"+escapeHtml(session&&session.orchestration?session.orchestration.requestedAdapter+" → "+session.orchestration.selectedAdapter:"문서 편집 의도")+"</small></div><label><span>선택/찾을 원문</span><textarea id='nativeBefore' rows='4' placeholder='캔버스에서 문단을 선택하거나 찾을 내용을 입력하세요.'></textarea></label><label><span>변경할 내용</span><textarea id='nativeAfter' rows='5' placeholder='RHWP MCP가 반영할 내용을 입력하세요.'></textarea></label><div class='native-mcp-actions'><button id='nativeUndo' "+(nativeRuntime?"":"disabled")+">실행 취소</button><button class='primary' id='nativeApply'>MCP로 적용</button></div><details "+(nativeRuntime?"":"class='is-disabled'")+"><summary>고급 HAction 실행</summary><label><span>Action</span><input id='nativeAction' placeholder='TableCreate, CharShape...'></label><label><span>HParameterSet</span><input id='nativeParameterSet' placeholder='HTableCreation, HCharShape...'></label><label><span>ParameterSet JSON</span><textarea id='nativeActionParameters' rows='4'>{}</textarea></label><button id='nativeRunAction' "+(nativeRuntime?"":"disabled")+">승인 후 HAction 실행</button></details><p class='native-mcp-note'>브라우저 DOM은 원본이 아닙니다. 모든 변경은 이 세션의 "+escapeHtml(session?session.adapter:"문서 MCP")+"가 원본 파일에 적용합니다.</p>";
    $("nativeApply").onclick=function(){applyNativeSelection()};
    $("nativeUndo").onclick=function(){runNativeSessionCommand("undo",{})};
    $("nativeRunAction").onclick=function(){try{runNativeSessionCommand("action",{action:$("nativeAction").value,parameterSet:$("nativeParameterSet").value||null,parameters:JSON.parse($("nativeActionParameters").value||"{}")})}catch(error){toast("HAction JSON을 확인하세요.")}};
  }
  function selectNativeBlock(node){
    document.querySelectorAll("#documentPaper [data-native-target].selected").forEach(function(item){item.classList.remove("selected")});node.classList.add("selected");
    state.nativeSelection={target:node.dataset.nativeTarget,before:node.textContent};
    $("contextSelection").textContent="선택: "+node.textContent.slice(0,42)+(node.textContent.length>42?"…":"");$("contextSelection").classList.add("has-selection");
    $("chatInput").placeholder="선택한 글귀에 요청할 작업을 입력하세요...";
    setStatus("AI 컨텍스트 선택 · "+node.dataset.nativeTarget);$("chatInput").focus();
  }
  function renderMarkdownPreview(value){
    return escapeHtml(value).replace(/^### (.*)$/gm,"<h3>$1</h3>").replace(/^## (.*)$/gm,"<h2>$1</h2>").replace(/^# (.*)$/gm,"<h1>$1</h1>").replace(/\*\*(.*?)\*\*/g,"<strong>$1</strong>").replace(/`([^`]+)`/g,"<code>$1</code>").replace(/\n/g,"<br>");
  }
  function captureSourceSelection(editor){
    var before=editor.value.slice(editor.selectionStart,editor.selectionEnd);
    if(!before){state.nativeSelection=null;$("contextSelection").textContent="선택 영역 없음";$("contextSelection").classList.remove("has-selection");return}
    state.nativeSelection={target:"",before:before,start:editor.selectionStart,end:editor.selectionEnd};
    $("contextSelection").textContent="선택: "+before.slice(0,42)+(before.length>42?"…":"");$("contextSelection").classList.add("has-selection");
    $("chatInput").placeholder="선택한 글귀에 요청할 작업을 입력하세요...";
  }
  function scheduleWorkbenchMarkdownSync(editor){
    if(!state.projectWorkbench||state.activeWorkbenchTab!=="markdown")return;
    clearTimeout(state.workbenchAutoSaveTimer);var sequence=++state.workbenchSaveSequence;
    state.workbenchAutoSaveTimer=setTimeout(async function(){
      if(sequence!==state.workbenchSaveSequence||!state.nativeSession||!state.sourceEditorDirty)return;
      updateDocumentSaveState("MD 원본 저장 중…",true);
      var saved=await runNativeSessionCommand("replace_document",{content:editor.value},{preserveSource:true,autoRender:false,quiet:true});
      if(saved){state.sourceEditorDirty=false;await refreshProjectWorkbench();updateDocumentSaveState("MD r"+state.projectWorkbench.document.revision+" 저장됨 · HWPX는 명시적 반영 필요",false);updateWorkbenchSyncActions()}
    },900);
  }
  function renderSourceEditor(session){
    var paper=$("documentPaper"),snapshot=session.snapshot,content=String(snapshot.content||""),markdown=snapshot.language==="markdown";
    paper.className="paper source-editor-paper";
    paper.innerHTML="<div class='source-editor-header'><b>"+escapeHtml(session.filename)+"</b><small>"+escapeHtml(session.adapter)+"</small><span>UTF-8 · "+escapeHtml(snapshot.language)+"</span></div><div class='source-editor-shell "+(markdown?"markdown-mode":"")+"'><pre class='source-line-numbers' id='sourceLineNumbers'></pre><textarea class='source-editor' id='sourceEditor' spellcheck='false'></textarea>"+(markdown?"<div class='markdown-preview' id='markdownPreview'></div>":"")+"</div>";
    var editor=$("sourceEditor");editor.value=content;
    function updateSource(){var lines=editor.value.split("\n").length;$("sourceLineNumbers").textContent=Array.from({length:lines},function(_,index){return index+1}).join("\n");if(markdown)$("markdownPreview").innerHTML=renderMarkdownPreview(editor.value)}
    editor.onselect=function(){captureSourceSelection(editor)};editor.onkeyup=function(){captureSourceSelection(editor)};editor.onmouseup=function(){captureSourceSelection(editor)};
    editor.oninput=function(){state.sourceEditorDirty=true;updateSource();updateDocumentSaveState("MD 편집 중 · 자동 저장 대기",true);scheduleWorkbenchMarkdownSync(editor)};
    updateSource();state.documentMode="native-session";state.sourceEditorDirty=false;
  }
  function configureRhwpToolboxes(editor){
    var frame=editor&&editor.element,doc=frame&&frame.contentDocument;
    if(!doc)return false;
    var definitions={
      basic:{item:doc.querySelector('[data-cmd="view:toolbox-basic"]'),toolbar:doc.getElementById("icon-toolbar")},
      format:{item:doc.querySelector('[data-cmd="view:toolbox-format"]'),toolbar:doc.getElementById("style-bar")}
    };
    function setVisible(name,visible){
      var definition=definitions[name];if(!definition||!definition.item||!definition.toolbar)return;
      if(visible)definition.toolbar.style.removeProperty("display");else definition.toolbar.style.display="none";
      definition.item.classList.remove("disabled");definition.item.classList.toggle("active",visible);
      definition.item.setAttribute("role","menuitemcheckbox");definition.item.setAttribute("aria-checked",visible?"true":"false");
      var icon=definition.item.querySelector(".md-icon");
      if(!icon){icon=doc.createElement("span");icon.className="md-icon";icon.setAttribute("aria-hidden","true");definition.item.insertBefore(icon,definition.item.firstChild)}
      icon.textContent=visible?"✓":"";
    }
    if(doc.documentElement.dataset.aiworksToolboxBindings!=="true"){
      doc.addEventListener("click",function(event){
        var target=event.target&&event.target.closest&&event.target.closest('[data-cmd="view:toolbox-basic"],[data-cmd="view:toolbox-format"]');
        if(!target)return;
        event.preventDefault();event.stopImmediatePropagation();
        var name=target.dataset.cmd==="view:toolbox-basic"?"basic":"format",definition=definitions[name];
        if(definition&&definition.toolbar)setVisible(name,frame.contentWindow.getComputedStyle(definition.toolbar).display==="none");
      },true);
      doc.documentElement.dataset.aiworksToolboxBindings="true";
    }
    setVisible("basic",false);
    setVisible("format",true);
    doc.documentElement.dataset.aiworksDefaultToolbox="format";
    return true;
  }
  async function mountRhwpEditor(session){
    var paper=$("documentPaper");paper.className="rhwp-embed-shell";paper.innerHTML="<div id='rhwpEditorHost' style='height:100%'></div>";
    var editor=null;
    try{
      if(state.rhwpEditor){var previous=state.rhwpEditor;state.rhwpEditor=null;previous.destroy()}
      var module=await import("/poc/aiworks/vendor/rhwp-editor/index.js");
      editor=await module.createEditor($("rhwpEditorHost"),{studioUrl:"/poc/aiworks/rhwp/",renderer:"canvas2d",height:"100%"});
      var artifact=await api("/documents/sessions/"+session.id+"/artifact");
      var binary=atob(artifact.contentBase64),bytes=new Uint8Array(binary.length);for(var index=0;index<binary.length;index++)bytes[index]=binary.charCodeAt(index);
      await editor.loadFile(bytes,session.filename,{skipUnsavedGuard:true,suppressDialogs:true});configureRhwpToolboxes(editor);state.rhwpEditor=editor;$("rhwpEditorHost").dataset.ready="true";
      setStatus("RHWP 원본 편집기 로딩 완료 · 직접 수정 및 AI 선택 가능");
    }catch(error){if(editor)editor.destroy();state.rhwpEditor=null;if(session.snapshot.document)renderImportedHwpx(session.snapshot.document);else{paper.className="paper";paper.innerHTML="<h2>RHWP 편집기를 시작하지 못했습니다.</h2><p>"+escapeHtml(error.message)+"</p>"}addAssistant("RHWP 편집기를 초기화하지 못했습니다: "+error.message)}
  }
  async function captureRhwpSelection(silent){
    if(!state.rhwpEditor)return false;
    try{
      var selection=await state.rhwpEditor.getSelectionText();var before=String(selection&&selection.text||"");
      if(!selection||!selection.hasSelection||!before){
        if(state.nativeSelection&&state.nativeSelection.rhwpNative)state.nativeSelection=null;
        $("contextSelection").textContent="선택 영역 없음";$("contextSelection").classList.remove("has-selection");
        if(!silent)addAssistant("RHWP 편집기에서 먼저 바꿀 문구를 마우스로 선택한 뒤 요청해 주세요.");
        return false;
      }
      state.nativeSelection={target:"__rhwp_native__",before:before,rhwpNative:true};
      $("contextSelection").textContent="선택: "+before.slice(0,42)+(before.length>42?"…":"");$("contextSelection").classList.add("has-selection");
      $("chatInput").placeholder="선택한 글귀에 요청할 작업을 입력하세요...";setStatus("RHWP 네이티브 선택 · "+before.length+"자");
      return true;
    }catch(error){
      if(!silent)addAssistant("RHWP 선택 영역을 읽지 못했습니다: "+error.message);
      return false;
    }
  }
  function configureNativeToolbar(session,selectionMode){
    var statebar=document.querySelector(".document-state"),title=$("nativeCompactTitle");
    if(!title){title=document.createElement("strong");title.id="nativeCompactTitle";title.className="native-compact-title";statebar.insertBefore(title,statebar.firstChild)}
    title.textContent=session.filename;title.title=session.adapter+" · 로컬 자체 호스팅 · 외부 문서 전송 없음";
    var toggle=$("aiSelectionMode");
    if(session.snapshot.kind==="structured-hwpx"){
      if(!toggle){toggle=document.createElement("button");toggle.id="aiSelectionMode";toggle.className="editor-mode-toggle"}
      if(toggle.parentElement!==statebar)statebar.insertBefore(toggle,title.nextSibling);
      toggle.textContent=selectionMode?"RHWP 직접 편집":"AI 선택 모드";toggle.onclick=function(){renderNativeSession(state.nativeSession,!selectionMode)};
    }else if(toggle){toggle.remove()}
    ["templateAuthoringCommit","templateAuthoringCancel"].forEach(function(id){var node=$(id);if(node)node.remove()});
    if(session.purpose==="template-authoring"){
      var cancel=document.createElement("button");cancel.id="templateAuthoringCancel";cancel.className="editor-mode-toggle";cancel.textContent="MCP 만들기로 돌아가기";cancel.onclick=cancelTemplateAuthoring;
      var commit=document.createElement("button");commit.id="templateAuthoringCommit";commit.className="editor-mode-toggle primary";commit.textContent="양식 수정 완료·초안 반영";commit.onclick=commitTemplateAuthoring;
      statebar.appendChild(cancel);statebar.appendChild(commit);
    }
  }
  async function renderNativeSession(session,selectionMode){
    state.nativeSession=session;state.nativeSelection=null;state.currentDocument=null;state.workspaceDocument=null;
    var nativeRhwp=session.snapshot.kind==="structured-hwpx"||session.snapshot.kind==="rhwp-web";
    $("workbench").classList.toggle("native-rhwp-mode",nativeRhwp);document.querySelector(".app-shell").classList.toggle("native-rhwp-shell",nativeRhwp);
    if(!nativeRhwp)["nativeCompactTitle","aiSelectionMode"].forEach(function(id){var node=$(id);if(node)node.remove()});
    $("activeFileName").textContent=session.filename;
    configureEditorPlugin(session);enterWorkspace(true);var oldPanel=$("nativeMcpPanel");if(oldPanel)oldPanel.remove();
    if(session.snapshot.kind==="structured-hwpx"){
      if(selectionMode){if(state.rhwpEditor){var current=state.rhwpEditor;state.rhwpEditor=null;current.destroy()}renderImportedHwpx(session.snapshot.document);ensureNativeMcpPanel()}else await mountRhwpEditor(session);
      configureNativeToolbar(session,selectionMode);
    }else if(session.snapshot.kind==="native-pdf"){
      if(state.nativePreviewUrl)URL.revokeObjectURL(state.nativePreviewUrl);
      var binary=atob(session.snapshot.previewPdfBase64);var bytes=new Uint8Array(binary.length);for(var index=0;index<binary.length;index++)bytes[index]=binary.charCodeAt(index);
      state.nativePreviewUrl=URL.createObjectURL(new Blob([bytes],{type:"application/pdf"}));
      $("documentPaper").innerHTML="<div class='native-pdf-header'><b>RHWP 원본 미리보기</b><span>"+escapeHtml(session.adapter)+" · revision "+session.revision+"</span></div><object class='native-pdf-object' type='application/pdf' data='"+state.nativePreviewUrl+"'><p>PDF 미리보기를 표시할 수 없습니다.</p></object>";
      state.documentMode="native-session";
    }else if(session.snapshot.kind==="rhwp-web"){await mountRhwpEditor(session);configureNativeToolbar(session,false)}
    else if(session.snapshot.kind==="text-editor"){renderSourceEditor(session)}
    var first=selectionMode&&document.querySelector("#documentPaper [data-native-target]");if(first)selectNativeBlock(first);
    updateDocumentSaveState("MCP 세션 r"+session.revision+" · 원본 저장됨",false);updateLivePreview();
  }
  async function runNativeSessionCommand(command,commandArguments,options){
    if(!state.nativeSession)return false;
    try{
      setStatus(state.nativeSession.adapter+" · "+command+" 실행 중");
      var session=await api("/documents/sessions/"+state.nativeSession.id+"/commands",{method:"POST",body:JSON.stringify({base_revision:state.nativeSession.revision,command:command,arguments:commandArguments,auto_render:Boolean(options&&options.autoRender),sync_markdown:Boolean(options&&options.syncMarkdown),instruction:String(options&&options.instruction||""),preserve_layout:true,confirmed:true,actor:"workspace-user"})});
      if(options&&options.preserveSource){
        state.nativeSession=session;state.nativeSelection=null;state.sourceEditorDirty=false;
        if(session.projectSync&&session.projectSync.status==="failed")updateDocumentSaveState("MD 저장됨 · 파생 탭 갱신 실패",false);else updateDocumentSaveState("MD 저장됨 · HWPX는 명시적 반영 필요",false);
      }else if(options&&options.selectionMode){
        await renderNativeSession(session,true);
      }else if(options&&options.preserveEditor&&state.rhwpEditor){
        state.nativeSession=session;state.nativeSelection=null;$("activeFileName").textContent=session.filename;$("contextFile").textContent="⌁ "+session.filename;if($("nativeCompactTitle"))$("nativeCompactTitle").textContent=session.filename;
        $("contextSelection").textContent="선택 영역 없음";$("contextSelection").classList.remove("has-selection");
        updateDocumentSaveState("MCP 세션 r"+session.revision+" · 현재 화면 유지 · 원본 저장됨",false);
      }else{
        await renderNativeSession(session);
      }
      if(state.sourceContext){state.sourceContext.filename=session.filename;state.sourceContext.sessionId=session.id}
      await syncDocumentLibrary();if(state.projectWorkbench)await refreshProjectWorkbench();setStatus(session.adapter+" · revision "+session.revision+" 적용 완료");if(!(options&&options.quiet))toast("문서 MCP가 원본 산출물에 변경을 적용했습니다.");addAudit("Document MCP",command+" · "+session.adapter+" · r"+session.revision,"완료");return true;
    }catch(error){setStatus("문서 MCP 명령 실패");toast(error.message);return false}
  }
  function applyNativeSelection(){
    if(!state.nativeSession)return;
    var before=$("nativeBefore").value;var after=$("nativeAfter").value;
    if(!before){toast("선택하거나 찾을 원문이 필요합니다.");return}
    if(before===after){toast("변경할 내용이 원문과 같습니다.");return}
    runNativeSessionCommand("replace_selection",{target:state.nativeSelection&&state.nativeSelection.target||"",before:before,after:after},{selectionMode:true});
  }
  async function commitDirectHwpxEdit(){
    if(!state.currentDocument)return false;
    var nodes=Array.from(document.querySelectorAll("#documentPaper [data-hwpx-target]"));
    var changes=nodes.filter(function(node){return node.textContent!==state.currentDocument.savedTexts[node.dataset.hwpxTarget]});
    if(!changes.length)return false;
    var previous=Object.assign({},state.currentDocument,{savedTexts:Object.assign({},state.currentDocument.savedTexts)});
    for(var index=0;index<changes.length;index+=1){
      var node=changes[index];var target=node.dataset.hwpxTarget;var before=state.currentDocument.savedTexts[target];var after=node.textContent;
      var result=await api("/documents/apply-hwpx",{method:"POST",body:JSON.stringify({
        filename:state.currentDocument.filename,document_id:state.currentDocument.id,
        content_base64:state.currentDocument.contentBase64,actor:"workspace-user",
        patch:{op:"replace",target:target,expectedBefore:before,after:after,sourceSha256:state.currentDocument.sha256,sources:[]}
      })});
      state.currentDocument.id=result.documentId;state.currentDocument.filename=result.filename;state.currentDocument.contentBase64=result.contentBase64;state.currentDocument.sha256=result.artifactSha256;state.currentDocument.artifactReady=true;state.currentDocument.versionId=result.versionId;state.currentDocument.savedTexts[target]=after;
    }
    state.undoDocument=previous;$("activeFileName").textContent=state.currentDocument.filename;
    return true;
  }
  async function performDocumentSave(){
    try{
      setStatus("문서 변경 저장 중");updateDocumentSaveState("원본 저장 중…",true);
      if(state.nativeSession){
        if($("sourceEditor")&&state.sourceEditorDirty){clearTimeout(state.workbenchAutoSaveTimer);var sourceSaved=await runNativeSessionCommand("replace_document",{content:$("sourceEditor").value},{preserveSource:true,autoRender:false});if(sourceSaved)state.sourceEditorDirty=false;return sourceSaved}
        if(state.rhwpEditor&&/^(hwp|hwpx|hwt|hml)$/.test(state.nativeSession.format)){
          var outputFormat=state.nativeSession.format==="hwpx"?"hwpx":state.nativeSession.format==="hml"?"hml":"hwp";
          var bytes=outputFormat==="hwpx"?await state.rhwpEditor.exportHwpx():outputFormat==="hml"?await state.rhwpEditor.exportHml():await state.rhwpEditor.exportHwp();var binary="";for(var offset=0;offset<bytes.length;offset+=32768)binary+=String.fromCharCode.apply(null,bytes.subarray(offset,offset+32768));
          return await runNativeSessionCommand("replace_artifact",{contentBase64:btoa(binary),format:outputFormat},{preserveEditor:true,syncMarkdown:false});
        }
        updateDocumentSaveState("MCP 세션 r"+state.nativeSession.revision+" · 원본 저장됨",false);setStatus(state.nativeSession.adapter+"에 저장됨");toast("문서 MCP 산출물이 저장되어 있습니다.");return true
      }
      var committed=await commitDirectHwpxEdit();
      if(!state.currentDocument){
        var title=($("documentPaper").querySelector("h1")||{}).textContent||$("activeFileName").textContent;
        var payload={name:title.trim()||"제목 없는 문서",content:documentSnapshot(),actor:"workspace-user"};
        if(state.workspaceDocument){payload.id=state.workspaceDocument.id;payload.base_revision=state.workspaceDocument.revision}
        state.workspaceDocument=await api("/documents/workspace",{method:"POST",body:JSON.stringify(payload)});
        $("activeFileName").textContent=state.workspaceDocument.name;
      }
      saveBrowserDocumentDraft(true);
      await syncDocumentLibrary();
      setStatus(committed?"HWPX 새 버전 저장 완료":"문서 초안 저장 완료");
      toast(committed?"직접 편집한 HWPX 새 버전을 저장했습니다.":"문서 편집 내용을 저장했습니다.");
      addAudit("사용자",committed?"HWPX 직접 편집 저장":"문서 초안 저장","완료");
      return true;
    }catch(error){updateDocumentSaveState("저장 실패 · 다시 시도",true);setStatus("문서 저장 실패");toast(error.message);return false}
  }
  function saveDocumentChanges(){
    if(state.documentSaveInFlight)return state.documentSaveInFlight;
    state.documentSaveInFlight=performDocumentSave().finally(function(){state.documentSaveInFlight=null});
    return state.documentSaveInFlight;
  }
  async function syncMarkdownToHwpx(){
    if(!state.projectWorkbench)return;
    try{
      if(state.sourceEditorDirty&&!await saveDocumentChanges())return;
      var workbench=await refreshProjectWorkbench(),documentData=workbench.document,artifact=(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"});
      if(artifact&&artifact.status==="diverged"&&!window.confirm("HWPX에 아직 MD로 반영하지 않은 변경이 있습니다. 현재 MD로 HWPX를 다시 만들면 그 변경이 대체됩니다. 계속할까요?"))return;
      setStatus("MD r"+documentData.revision+" → 양식 MCP → HWPX 생성 중");updateOrchestration("명시적 MD → HWPX 반영","active");
      await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+documentData.id+"/render",{method:"POST",body:JSON.stringify({format:"hwpx",instruction:(artifact&&artifact.instruction)||"표준 보고서 양식으로 변환",preserve_layout:true,structural_render:true,force:true,actor:"workspace-user"})});
      await refreshProjectWorkbench();updateWorkbenchSyncActions();updateOrchestration("MD → HWPX 반영 완료","done");setStatus("HWPX 파생 버전 생성 완료 · MD r"+state.projectWorkbench.document.revision);toast("현재 MD를 HWPX에 명시적으로 반영했습니다.");scheduleWorkspaceStateSave(false);
    }catch(error){updateOrchestration("MD → HWPX 반영 실패","error");toast(error.message)}
  }
  async function syncHwpxToMarkdown(){
    if(!state.projectWorkbench)return;
    try{
      if(state.rhwpEditor&&!await saveDocumentChanges())return;
      var workbench=await refreshProjectWorkbench(),artifact=(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"&&item.id});
      if(!artifact)throw new Error("MD로 반영할 HWPX 파생 문서가 없습니다.");
      setStatus("HWPX 변경점 분석 → MD 새 revision 준비 중");updateOrchestration("명시적 HWPX → MD 반영","active");
      var promoted=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+workbench.document.id+"/artifacts/"+artifact.id+"/promote-markdown",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});
      await refreshProjectWorkbench();updateWorkbenchSyncActions();updateOrchestration("HWPX → MD 반영 완료","done");setStatus("MD r"+promoted.document.revision+" 생성 완료 · HWPX와 동기화됨");toast("HWPX 변경을 MD 새 revision으로 반영했습니다.");scheduleWorkspaceStateSave(false);
    }catch(error){updateOrchestration("HWPX → MD 반영 실패","error");toast(error.message)}
  }
  function undoDirectEdit(){
    if(!state.documentUndoSnapshot){toast("되돌릴 직접 편집 내용이 없습니다.");return}
    restoreDocumentSnapshot(state.documentUndoSnapshot);state.documentUndoSnapshot=null;clearTimeout(state.documentAutoSaveTimer);
    saveBrowserDocumentDraft(false);updateDocumentSaveState("직접 편집을 되돌림",false);toast("마지막 직접 편집을 되돌렸습니다.");
  }
  function setView(view,options){
    if(state.restoringWorkspace&&!(options&&options.restoring))state.restoreViewOverride=view;
    state.activeView=view;
    $("workbench").classList.toggle("builder-mode",view==="builder");
    document.querySelectorAll(".activitybar button[data-view]").forEach(function(button){button.classList.toggle("active",button.dataset.view===view)});
    document.querySelectorAll(".view").forEach(function(node){node.classList.remove("active")});
    $(view+"View").classList.add("active");
    $("sidebarTitle").textContent=titleByView[view];
    $("sidebarContent").innerHTML=sidebarByView[view];
    if(view==="data")renderData();if(view==="editor")syncDocumentLibrary();
    if(view==="builder")renderBuilder();
    if(view==="store")renderStore();
    if(view==="audit"){renderAudit();syncServerAudit()}
    if(view==="settings")renderSettings();
    scheduleWorkspaceStateSave(false);
  }

  function renderData(){
    var rows=state.commonData.map(function(item){
      return "<tr data-key='"+escapeHtml(item.key)+"'><td><b>"+escapeHtml(item.label)+"</b><br><small>"+escapeHtml(item.key)+"</small></td><td>"+escapeHtml(item.value)+"</td><td><span class='type-chip'>"+escapeHtml(item.kind)+"</span></td><td>"+escapeHtml(item.date)+"</td><td><button class='inline-link source-button'>"+escapeHtml(item.source)+"</button></td><td class='confidence'>"+item.confidence+"%</td></tr>";
    }).join("");
    $("dataView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Markdown Source of Truth</span><h1>프로젝트 문서와 메타정보</h1><p>문서 내용은 Markdown revision으로 관리하고, 양식 MCP와 형식 어댑터가 HWPX 등 파생 산출물을 만듭니다.</p></div><div class='module-actions'><button id='refreshKnowledge'>새로고침</button><button class='primary' id='addDataButton'>＋ 메타정보</button></div></div><section class='surface'><div class='surface-head'><h2>프로젝트 Markdown 원본</h2><small>내용 원본 · 양식과 분리</small></div><div class='store-grid' id='projectMarkdownList'>문서 목록을 불러오는 중입니다.</div></section><div class='cards'><div class='metric-card'><span>지식 노드</span><b id='knowledgeNodeCount'>-</b><small>문서·데이터·노트</small></div><div class='metric-card'><span>출처 연결</span><b id='knowledgeSourceCount'>-</b><small>근거 없는 답변 차단</small></div><div class='metric-card'><span>관계</span><b id='knowledgeEdgeCount'>-</b><small>출처·활용 연결</small></div></div><section class='surface'><div class='surface-head'><h2>출처 기반 질의응답</h2><small>내부 데이터 · 로컬 검색</small></div><div class='knowledge-query'><input id='knowledgeQuestion' placeholder='프로젝트 데이터와 연결된 근거를 질문하세요'><input id='knowledgeAsOf' type='date'><button class='primary' id='askKnowledge'>근거 찾기</button></div><div class='knowledge-answer' id='knowledgeAnswer'>질문하면 답변과 원문 위치가 함께 표시됩니다.</div></section><section class='surface'><div class='surface-head'><h2>프로젝트 확정 메타정보</h2><small>Markdown과 별도 관리</small></div><table class='data-table'><thead><tr><th>항목</th><th>현재 값</th><th>유형</th><th>기준일</th><th>출처 위치</th><th>신뢰도</th></tr></thead><tbody>"+rows+"</tbody></table></section><section class='surface' id='knowledgeComparison'><div class='surface-head'><h2 id='knowledgeComparisonTitle'>기준정보 시점 비교</h2><small id='knowledgeDelta'>비교 가능한 데이터를 확인 중입니다.</small></div><div class='timeline' id='knowledgeTimeline'></div></section><section class='surface'><div class='surface-head'><h2>지식 관계</h2><small>노트 ↔ 공통데이터 ↔ 원문</small></div><div class='knowledge-grid' id='knowledgeGraph'>그래프를 불러오는 중입니다.</div></section></div>";
    document.querySelectorAll(".source-button").forEach(function(button){button.onclick=function(){toast("원문 위치를 열었습니다: "+button.textContent);setView("editor")}});
    $("addDataButton").onclick=addProjectFact;
    $("refreshKnowledge").onclick=function(){loadKnowledgeGraph(true)};
    $("askKnowledge").onclick=askKnowledge;
    $("knowledgeQuestion").onkeydown=function(event){if(event.key==="Enter")askKnowledge()};
    loadKnowledgeGraph(false);loadKnowledgeComparison();loadProjectFacts();loadProjectDocuments();
  }

  function utf8Base64(value){var bytes=new TextEncoder().encode(String(value||"")),binary="";bytes.forEach(function(byte){binary+=String.fromCharCode(byte)});return btoa(binary)}
  async function loadProjectDocuments(){
    var host=$("projectMarkdownList");if(!host)return;
    try{
      var data=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents");state.projectDocuments=data.items||[];
      host.innerHTML=state.projectDocuments.length?state.projectDocuments.map(function(item){return"<article class='store-card "+(item.duplicateOf?"duplicate-document":"")+"'><div class='store-card-head'><span class='mcp-logo'>MD</span><div><h3>"+escapeHtml(item.title)+"</h3><div class='store-meta'><span>revision "+item.revision+"</span><span>"+escapeHtml(item.source.format)+"</span>"+(item.duplicateOf?"<span>내용 중복</span>":"")+"</div></div></div><p>"+escapeHtml(item.excerpt)+"</p><footer><button data-open-md='"+item.id+"'>MD 열기</button><button class='primary' data-render-md='"+item.id+"'>HWPX 만들기</button>"+(item.duplicateOf?"<button data-archive-duplicate='"+item.id+"' data-canonical='"+item.duplicateOf+"'>중복 보관</button>":"")+"</footer></article>"}).join(""):"<p class='empty-reference'>HWPX 또는 MD를 첨부하거나 보고서를 생성하면 프로젝트 Markdown 원본이 여기에 저장됩니다.</p>";
      host.querySelectorAll("[data-open-md]").forEach(function(button){button.onclick=function(){openProjectMarkdown(button.dataset.openMd)}});
      host.querySelectorAll("[data-render-md]").forEach(function(button){button.onclick=function(){renderProjectMarkdown(button.dataset.renderMd)}});
      host.querySelectorAll("[data-archive-duplicate]").forEach(function(button){button.onclick=function(){archiveDuplicateMarkdown(button.dataset.archiveDuplicate,button.dataset.canonical)}});
    }catch(error){host.textContent=error.message}
  }
  async function archiveDuplicateMarkdown(documentId,canonicalId){
    if(!window.confirm("내용 SHA-256이 같은 중복 Markdown을 보관할까요? revision과 파생 파일은 삭제하지 않고 보존됩니다."))return;
    try{
      await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/status",{method:"POST",body:JSON.stringify({action:"archive",document_ids:[documentId],canonical_document_id:canonicalId,actor:"workspace-user"})});
      if(state.projectWorkbench&&state.projectWorkbench.document.id===documentId)await openProjectWorkbench(canonicalId,"markdown");
      await loadProjectDocuments();toast("중복 Markdown을 삭제하지 않고 보관했습니다.");
    }catch(error){toast(error.message)}
  }
  function workbenchStatusLabel(status){return({synced:"동기화됨",stale:"갱신 필요",diverged:"MD 반영 필요",rendering:"갱신 중",failed:"실패",missing:"생성 필요"})[status]||status||"-"}
  function renderProjectWorkbenchTabs(){
    var host=$("projectWorkbenchTabs"),workbench=state.projectWorkbench;if(!host||!workbench)return;
    var documentData=workbench.document,artifacts=workbench.artifacts||[];
    var openConflicts=(workbench.conflicts||[]).filter(function(item){return item.status==="open"}),buttons=[{id:"markdown",icon:"MD",label:"MD 원본",status:"r"+documentData.revision}].concat(artifacts.map(function(item){return{id:"artifact:"+item.format,icon:item.format.toUpperCase(),label:item.format.toUpperCase(),status:workbenchStatusLabel(item.status)}})).concat([{id:"metadata",icon:"◇",label:"메타정보",status:String((workbench.factCounts.confirmed||0)+(workbench.factCounts.candidate||0))},{id:"history",icon:"≡",label:"변경 이력",status:openConflicts.length?"!"+openConflicts.length:String((workbench.events||[]).length)}]);
    var options=state.projectDocuments.map(function(item){return"<option value='"+escapeHtml(item.id)+"' "+(item.id===documentData.id?"selected":"")+">"+escapeHtml(item.title)+" · r"+Number(item.revision||0)+"</option>"}).join("");
    host.innerHTML="<span id='activeFileName' hidden>"+escapeHtml(documentData.title)+"</span><label class='project-document-switcher'><span>프로젝트 문서</span><select id='projectDocumentSwitcher'>"+options+"</select></label>"+buttons.map(function(item){return"<button data-workbench-tab='"+escapeHtml(item.id)+"' class='"+(state.activeWorkbenchTab===item.id?"active":"")+"'><span class='workbench-tab-icon'>"+escapeHtml(item.icon)+"</span><span>"+escapeHtml(item.label)+"</span><small>"+escapeHtml(item.status)+"</small></button>"}).join("");
    $("projectDocumentSwitcher").onchange=function(){openProjectWorkbench(this.value,"markdown")};
    host.querySelectorAll("[data-workbench-tab]").forEach(function(button){button.onclick=function(){switchProjectWorkbenchTab(button.dataset.workbenchTab)}});
    updateWorkbenchSyncActions();
  }
  function updateWorkbenchSyncActions(){
    var mdButton=$("syncMdToHwpx"),hwpxButton=$("syncHwpxToMd"),downloadButton=$("downloadProjectHwpx"),workbench=state.projectWorkbench;if(!mdButton||!hwpxButton)return;
    var artifact=workbench&&(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"});
    mdButton.hidden=!(workbench&&state.activeWorkbenchTab==="markdown");
    hwpxButton.hidden=!(workbench&&state.activeWorkbenchTab==="artifact:hwpx"&&artifact&&artifact.id);
    if(downloadButton)downloadButton.hidden=!(workbench&&state.activeWorkbenchTab==="artifact:hwpx"&&artifact&&artifact.id);
    mdButton.textContent=artifact&&artifact.id?"MD → HWPX 반영" : "MD → HWPX 생성";
    mdButton.classList.toggle("primary",Boolean(artifact&&artifact.status==="stale"||artifact&&artifact.status==="missing"));
    hwpxButton.textContent=artifact&&artifact.status==="diverged"?"HWPX → MD 반영 필요":"HWPX → MD 반영";
    hwpxButton.classList.toggle("primary",Boolean(artifact&&artifact.status==="diverged"));
  }
  async function downloadProjectHwpx(){
    if(!state.projectWorkbench)return;
    try{
      if(state.rhwpEditor&&!await saveDocumentChanges())return;
      var workbench=await refreshProjectWorkbench(),artifact=(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"&&item.id});
      if(!artifact)throw new Error("다운로드할 HWPX 파생 문서가 없습니다.");
      var detail=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+workbench.document.id+"/artifacts/"+artifact.id);
      downloadBase64(detail.filename||workbench.document.title+".hwpx",detail.contentBase64);
      setStatus("양식 적용 HWPX 다운로드 시작 · "+(detail.filename||""));
      toast("현재 양식과 Markdown 계층이 적용된 HWPX를 다운로드합니다.");
      addAudit("사용자","프로젝트 파생 HWPX 다운로드 · "+(detail.filename||""),"완료");
    }catch(error){toast(error.message)}
  }
  async function refreshProjectWorkbench(){
    if(!state.projectWorkbench)return null;
    state.projectWorkbench=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+state.projectWorkbench.document.id+"/workbench");renderProjectWorkbenchTabs();return state.projectWorkbench;
  }

  function workbenchTabCacheKey(tab){
    return state.activeProjectId+":"+(state.projectWorkbench&&state.projectWorkbench.document.id||"")+":"+tab;
  }
  function workbenchTabFingerprint(tab){
    var workbench=state.projectWorkbench;if(!workbench)return"";
    if(tab==="markdown")return"md:"+workbench.document.versionId;
    if(tab==="artifact:hwpx"){var artifact=(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"});return"hwpx:"+(artifact&&artifact.artifactSha256||"missing")}
    return"";
  }
  function discardWorkbenchTabCache(key){
    var entry=state.workbenchTabCache[key];if(!entry)return;
    if(entry.editor)try{entry.editor.destroy()}catch(_error){}
    delete state.workbenchTabCache[key];state.workbenchTabCacheOrder=state.workbenchTabCacheOrder.filter(function(item){return item!==key});
  }
  function clearWorkbenchTabCache(){
    Object.keys(state.workbenchTabCache).forEach(discardWorkbenchTabCache);state.workbenchTabCache={};state.workbenchTabCacheOrder=[];
  }
  function cacheCurrentWorkbenchTab(){
    var tab=state.activeWorkbenchTab;
    if(!state.projectWorkbench||!state.nativeSession||!/^markdown$|^artifact:hwpx$/.test(tab))return false;
    var key=workbenchTabCacheKey(tab),paper=$("documentPaper"),fragment=document.createDocumentFragment();
    discardWorkbenchTabCache(key);
    while(paper.firstChild)fragment.appendChild(paper.firstChild);
    state.workbenchTabCache[key]={
      fragment:fragment,editor:state.rhwpEditor,session:state.nativeSession,selection:state.nativeSelection,
      paperClass:paper.className,fingerprint:workbenchTabFingerprint(tab),nativeRhwp:$("workbench").classList.contains("native-rhwp-mode"),
      shellRhwp:document.querySelector(".app-shell").classList.contains("native-rhwp-shell"),cachedAt:Date.now()
    };
    state.workbenchTabCacheOrder.push(key);
    while(state.workbenchTabCacheOrder.length>4)discardWorkbenchTabCache(state.workbenchTabCacheOrder[0]);
    state.rhwpEditor=null;state.nativeSession=null;state.nativeSelection=null;state.sourceEditorDirty=false;
    return true;
  }
  function restoreWorkbenchTabCache(tab){
    var key=workbenchTabCacheKey(tab),entry=state.workbenchTabCache[key];if(!entry)return false;
    if(entry.fingerprint!==workbenchTabFingerprint(tab)){discardWorkbenchTabCache(key);return false}
    var paper=$("documentPaper");clearWorkbenchCanvas();paper.className=entry.paperClass;paper.appendChild(entry.fragment);
    state.rhwpEditor=entry.editor;state.nativeSession=entry.session;state.nativeSelection=entry.selection;state.sourceEditorDirty=false;
    $("workbench").classList.toggle("native-rhwp-mode",entry.nativeRhwp);document.querySelector(".app-shell").classList.toggle("native-rhwp-shell",entry.shellRhwp);
    delete state.workbenchTabCache[key];state.workbenchTabCacheOrder=state.workbenchTabCacheOrder.filter(function(item){return item!==key});
    configureEditorPlugin(entry.session);configureNativeToolbar(entry.session,false);updateDocumentSaveState("캐시된 편집 세션 r"+entry.session.revision+" · 재마운트 없음",false);
    if(state.rhwpEditor)configureRhwpToolboxes(state.rhwpEditor);
    return true;
  }

  function clearWorkbenchCanvas(){
    if(state.rhwpEditor){var editor=state.rhwpEditor;state.rhwpEditor=null;editor.destroy()}
    state.nativeSession=null;state.nativeSelection=null;state.sourceEditorDirty=false;
    $("workbench").classList.remove("native-rhwp-mode");document.querySelector(".app-shell").classList.remove("native-rhwp-shell");
    ["nativeCompactTitle","aiSelectionMode"].forEach(function(id){var node=$(id);if(node)node.remove()});var panel=$("nativeMcpPanel");if(panel)panel.remove();
  }
  async function openWorkbenchMarkdown(){
    if(restoreWorkbenchTabCache("markdown")){setStatus("MD 원본 r"+state.projectWorkbench.document.revision+" · 캐시 복원 · 재마운트 없음");return}
    var documentData=state.projectWorkbench.document;
    var session=await api("/documents/sessions",{method:"POST",body:JSON.stringify({filename:documentData.title+".md",content_base64:utf8Base64(documentData.markdown),project_id:state.activeProjectId,markdown_document_id:documentData.id,markdown_base_revision:documentData.revision,intent:"프로젝트 Markdown 원본 편집",actor:"workspace-user"})});
    await renderNativeSession(session);setStatus("MD 원본 r"+documentData.revision+" · 자동 동기화 준비됨");
  }
  async function openWorkbenchArtifact(format){
    var workbench=state.projectWorkbench,documentData=workbench.document,artifact=(workbench.artifacts||[]).find(function(item){return item.format===format});
    if(artifact&&artifact.id&&restoreWorkbenchTabCache("artifact:"+format)){setStatus(format.toUpperCase()+" 저장본 · 캐시 복원 · 재마운트 없음");updateWorkbenchSyncActions();return}
    if(!artifact||!artifact.id){
      clearWorkbenchCanvas();$("documentPaper").className="paper workbench-info-paper";$("documentPaper").innerHTML="<div class='workbench-info-head'><span>DERIVED DOCUMENT</span><h1>아직 HWPX가 없습니다.</h1><p>탭 이동만으로 문서를 만들지 않습니다. 현재 MD를 확인한 뒤 명시적으로 파생 문서를 생성하세요.</p><button class='primary' id='createDerivedHwpx'>MD → HWPX 생성</button></div>";$("createDerivedHwpx").onclick=syncMarkdownToHwpx;configureEditorPlugin({filename:documentData.title,adapter:"document.rhwp@1.0.0",workspace:{loadedMcps:["document.markdown@1.0.0","document.rhwp@1.0.0"]}});setStatus("HWPX 생성 필요 · MD r"+documentData.revision);updateWorkbenchSyncActions();return;
    }
    var detail=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+documentData.id+"/artifacts/"+artifact.id);
    await openGeneratedArtifact({title:documentData.title,filename:detail.filename,format:detail.format,contentBase64:detail.contentBase64,content:documentData.markdown,markdownDocument:{id:documentData.id,versionId:documentData.versionId,revision:documentData.revision,markdownSha256:documentData.markdownSha256},projectArtifact:detail},["document.markdown@1.0.0","template.report-style@0.1.0",detail.renderer||"integration.kordoc@1.0.0","document.rhwp@1.0.0"]);
    setStatus(format.toUpperCase()+" 저장본 열림 · "+workbenchStatusLabel(artifact.status)+(artifact.status==="stale"?" · MD → HWPX 반영 필요":""));updateWorkbenchSyncActions();
  }
  async function renderWorkbenchMetadata(){
    clearWorkbenchCanvas();var result=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/facts"),facts=result.snapshot.facts||{},candidates=result.candidates||[];
    $("documentPaper").className="paper workbench-info-paper";$("documentPaper").innerHTML="<div class='workbench-info-head'><span>PROJECT METADATA</span><h1>"+escapeHtml(state.projectWorkbench.project.name)+"</h1><p>프로젝트 확정값은 모든 MD와 파생 문서가 공동으로 참조합니다.</p></div><section><h2>확정 메타정보</h2><div class='workbench-fact-grid'>"+(Object.keys(facts).map(function(key){var item=facts[key];return"<article><small>"+escapeHtml(key)+"</small><b>"+escapeHtml(item.label)+"</b><p>"+escapeHtml(String(item.value==null?"":item.value)+(item.unit||""))+"</p><span>"+escapeHtml(item.effectiveDate||"현재")+"</span></article>"}).join("")||"<p>확정된 메타정보가 없습니다.</p>")+"</div></section><section><h2>문서에서 추출한 후보</h2><div class='workbench-candidates'>"+(candidates.map(function(item){return"<div><span><b>"+escapeHtml(item.label)+"</b> "+escapeHtml(String(item.value))+"</span><span><button data-workbench-fact='confirmed' data-value-id='"+item.valueId+"'>확정</button><button data-workbench-fact='rejected' data-value-id='"+item.valueId+"'>거부</button></span></div>"}).join("")||"<p>검토할 후보가 없습니다.</p>")+"</div></section>";
    if(candidates.length){
      var candidateHeading=Array.from($("documentPaper").querySelectorAll("section h2")).find(function(node){return node.textContent.indexOf("문서에서 추출한 후보")>=0});
      if(candidateHeading)candidateHeading.insertAdjacentHTML("afterend","<div class='workbench-bulk-actions'><span>후보 "+candidates.length+"개</span><button data-bulk-fact='rejected'>전체 거부</button><button class='primary' data-bulk-fact='confirmed'>전체 확정</button></div>");
      $("documentPaper").querySelectorAll("[data-bulk-fact]").forEach(function(button){button.onclick=function(){bulkDecideWorkbenchFacts(candidates.map(function(item){return item.valueId}),button.dataset.bulkFact)}});
    }
      if(candidates.some(function(item){return Boolean(item.conflict)})){var bulkConfirm=$("documentPaper").querySelector("[data-bulk-fact='confirmed']");if(bulkConfirm)bulkConfirm.remove()}
      Array.from($("documentPaper").querySelectorAll(".workbench-candidates>div")).forEach(function(node,index){
        var candidate=candidates[index],conflict=candidate&&candidate.conflict;if(!conflict)return;
        var actions=node.lastElementChild,confirmButton=actions&&actions.querySelector("[data-workbench-fact='confirmed']");if(confirmButton)confirmButton.remove();
        var current=conflict.current||{},description=conflict.type==="time-change"?"기준일이 더 최신이어서 시점 변화 후보입니다.":"기존 확정값과 달라 오기 여부 확인이 필요합니다.";
        node.firstElementChild.insertAdjacentHTML("beforeend","<small class='fact-conflict-note'>"+escapeHtml(description)+"<br>현재값 "+escapeHtml(String(current.value==null?"":current.value))+" · "+escapeHtml(current.effectiveDate||"기준일 없음")+"</small>");
        actions.insertAdjacentHTML("afterbegin","<button data-workbench-fact='confirmed' data-fact-resolution='correction' data-value-id='"+candidate.valueId+"'>오기 수정</button>"+(candidate.effectiveDate?"<button data-workbench-fact='confirmed' data-fact-resolution='time-change' data-value-id='"+candidate.valueId+"'>시간 변화</button>":""));
      });


    $("documentPaper").querySelectorAll("[data-workbench-fact]").forEach(function(button){button.onclick=async function(){await decideProjectFact(button.dataset.valueId,button.dataset.workbenchFact,button.dataset.factResolution);await refreshProjectWorkbench();await renderWorkbenchMetadata()}});configureEditorPlugin({filename:state.projectWorkbench.project.name,adapter:"common-data.registry@1.1.0",workspace:{loadedMcps:["common-data.registry@1.1.0"]}});
  }
  async function bulkDecideWorkbenchFacts(valueIds,decision){
    var label=decision==="confirmed"?"확정":"거부";
    if(!window.confirm("후보 "+valueIds.length+"개를 모두 "+label+"할까요?"))return;
    try{
      setStatus("메타정보 후보 일괄 "+label+" 중");
      await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/facts/decisions",{method:"POST",body:JSON.stringify({value_ids:valueIds,decision:decision,actor:"workspace-user"})});
      state.projectFactsLoaded=false;await loadProjectFacts(true);await refreshProjectWorkbench();await renderWorkbenchMetadata();setStatus("메타정보 후보 "+valueIds.length+"개 "+label+" 완료");toast("후보 "+valueIds.length+"개를 "+label+"했습니다.");
    }catch(error){setStatus("메타정보 후보 일괄 처리 실패");toast(error.message)}
  }

  function renderWorkbenchHistory(){
    clearWorkbenchCanvas();var workbench=state.projectWorkbench,openConflicts=(workbench.conflicts||[]).filter(function(item){return item.status==="open"});
    var conflictHtml=openConflicts.length?"<section class='workbench-conflicts'><h2>해결 대기 충돌</h2>"+openConflicts.map(function(item){return"<article class='workbench-conflict-card'><div><b>MD와 HWPX가 각각 변경됨</b><small>"+escapeHtml(item.id)+"</small></div><p><strong>HWPX 변경 초안</strong>"+escapeHtml(item.source.excerpt||"내용 미리보기 없음")+"</p><p><strong>현재 MD</strong>"+escapeHtml(item.target.excerpt||"내용 미리보기 없음")+"</p><footer><button data-conflict-resolution='keep-markdown' data-conflict-id='"+escapeHtml(item.id)+"'>현재 MD 유지</button><button class='primary' data-conflict-resolution='use-hwpx' data-conflict-id='"+escapeHtml(item.id)+"'>HWPX 변경 채택</button></footer></article>"}).join("")+"</section>":"";
    var graph=workbench.relationGraph||{},nodeNames={};(graph.nodes||[]).forEach(function(item){nodeNames[item.id]=item.label});var relationHtml=(graph.edges||[]).length?"<section class='artifact-relations'><h2>산출물 재현 관계</h2>"+graph.edges.map(function(edge){return"<div><span>"+escapeHtml(nodeNames[edge.source]||edge.source)+"</span><b>"+escapeHtml(edge.relation)+"</b><span>"+escapeHtml(nodeNames[edge.target]||edge.target)+"</span><small>"+escapeHtml(edge.evidence||"")+"</small></div>"}).join("")+"</section>":"";
    var evidenceHtml=(workbench.evidence||[]).length?"<section class='artifact-relations'><h2>근거 추적</h2><div class='artifact-evidence-list'>"+workbench.evidence.map(function(item){return"<div><b>"+escapeHtml(item.locator)+"</b> · "+escapeHtml(item.excerpt)+" <small>신뢰도 "+Math.round(Number(item.confidence||0)*100)+"% · "+escapeHtml(item.excerptSha256.slice(0,12))+"</small></div>"}).join("")+"</div></section>":"";
    $("documentPaper").className="paper workbench-info-paper";$("documentPaper").innerHTML="<div class='workbench-info-head'><span>SYNC HISTORY</span><h1>변경 이력</h1><p>MD revision과 파생 문서 사이의 동기화 기록입니다.</p></div>"+conflictHtml+relationHtml+evidenceHtml+"<div class='workbench-history'>"+((workbench.events||[]).map(function(item){return"<article><i class='sync-state "+escapeHtml(item.status)+"'></i><div><b>"+escapeHtml(item.eventType)+"</b><p>"+escapeHtml(item.origin)+" · "+escapeHtml(item.status)+"</p></div><time>"+escapeHtml(item.createdAt)+"</time></article>"}).join("")||"<p>아직 변경 이력이 없습니다.</p>")+"</div>";
    $("documentPaper").querySelectorAll("[data-conflict-resolution]").forEach(function(button){button.onclick=function(){resolveWorkbenchConflict(button.dataset.conflictId,button.dataset.conflictResolution)}});
    configureEditorPlugin({filename:workbench.document.title,adapter:"project.sync-history@1.0.0",workspace:{loadedMcps:["document.markdown@1.0.0","project.sync-history@1.0.0"]}});
  }
  async function resolveWorkbenchConflict(conflictId,resolution){
    var message=resolution==="keep-markdown"?"현재 MD를 유지하고 HWPX 변경 초안을 폐기할까요? HWPX는 갱신 필요 상태가 됩니다.":"HWPX 변경 초안을 새 MD revision으로 채택할까요? 기존 MD revision은 이력에 보존됩니다.";
    if(!window.confirm(message))return;
    try{
      setStatus("문서 충돌 해결 중");
      var workbench=state.projectWorkbench;
      await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+workbench.document.id+"/conflicts/"+conflictId+"/resolve",{method:"POST",body:JSON.stringify({resolution:resolution,actor:"workspace-user"})});
      await refreshProjectWorkbench();renderWorkbenchHistory();renderProjectWorkbenchTabs();setStatus("문서 충돌 해결 완료");toast(resolution==="keep-markdown"?"현재 MD를 유지했습니다. 필요하면 MD → HWPX를 실행하세요.":"HWPX 변경을 MD 새 revision으로 반영했습니다.");
    }catch(error){setStatus("문서 충돌 해결 실패");toast(error.message)}
  }
  async function switchProjectWorkbenchTab(tab,options){
    if(!state.projectWorkbench)return;
    if(state.activeWorkbenchTab==="markdown"&&state.sourceEditorDirty){var saved=await saveDocumentChanges();if(!saved)return}
    if(tab!==state.activeWorkbenchTab)cacheCurrentWorkbenchTab();
    state.activeWorkbenchTab=tab;renderProjectWorkbenchTabs();if(!(options&&options.restoring))setView("editor");
    try{if(tab==="markdown")await openWorkbenchMarkdown();else if(tab.indexOf("artifact:")===0)await openWorkbenchArtifact(tab.split(":")[1]);else if(tab==="metadata")await renderWorkbenchMetadata();else if(tab==="history")renderWorkbenchHistory();if(!(options&&options.restoring))scheduleWorkspaceStateSave(false)}catch(error){setStatus("탭 동기화 실패");toast(error.message);await refreshProjectWorkbench()}
  }
  async function openProjectWorkbench(documentId,tab){
    try{if(state.activeWorkbenchTab==="markdown"&&state.sourceEditorDirty){var saved=await saveDocumentChanges();if(!saved)return}if(state.projectWorkbench&&state.projectWorkbench.document.id!==documentId)cacheCurrentWorkbenchTab();state.projectWorkbench=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+documentId+"/workbench");state.activeWorkbenchTab=tab||"markdown";state.sourceEditorDirty=false;renderProjectWorkbenchTabs();setView("editor");await switchProjectWorkbenchTab(state.activeWorkbenchTab);toast(state.projectWorkbench.document.title+" 프로젝트 문서를 열었습니다.")}catch(error){toast(error.message)}
  }
  async function openProjectMarkdown(documentId){return openProjectWorkbench(documentId,"markdown")}
  async function renderProjectMarkdown(documentId){return openProjectWorkbench(documentId,"artifact:hwpx")}

  async function loadProjectFacts(force){
    if(state.projectFactsLoaded&&!force)return;
    try{
      var result=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/facts");
      state.commonData=Object.keys(result.snapshot.facts||{}).map(function(key){
        var item=result.snapshot.facts[key],value=item.value;
        return{label:item.label,key:key,value:String(value==null?"":value)+(item.unit||""),kind:"확정",date:item.effectiveDate||"-",source:item.source&&item.source.locator||"프로젝트 메타정보",confidence:Math.round(Number(item.confidence||0)*100)};
      });
      state.commonData=state.commonData.concat((result.candidates||[]).map(function(item){return{label:item.label,key:item.key,value:String(item.value==null?"":item.value)+(item.unit||""),kind:"후보",date:item.effectiveDate||"-",source:(item.source&&item.source.documentId||"Markdown")+" · "+(item.source&&item.source.locator||"추출"),confidence:Math.round(Number(item.confidence||0)*100),candidateId:item.valueId}}));
      state.projectFactsLoaded=true;
      if(state.activeView==="data"){
        var body=document.querySelector("#dataView .data-table tbody");
        if(body){body.innerHTML=state.commonData.map(function(item){return "<tr data-key='"+escapeHtml(item.key)+"'><td><b>"+escapeHtml(item.label)+"</b><br><small>"+escapeHtml(item.key)+"</small></td><td>"+escapeHtml(item.value)+"</td><td><span class='type-chip'>"+escapeHtml(item.kind)+"</span></td><td>"+escapeHtml(item.date)+"</td><td>"+escapeHtml(item.source)+(item.candidateId?"<br><button data-fact-decision='confirmed' data-value-id='"+item.candidateId+"'>확정</button> <button data-fact-decision='rejected' data-value-id='"+item.candidateId+"'>거부</button>":"")+"</td><td class='confidence'>"+item.confidence+"%</td></tr>"}).join("");body.querySelectorAll("[data-fact-decision]").forEach(function(button){button.onclick=function(){decideProjectFact(button.dataset.valueId,button.dataset.factDecision)}})}
      }
    }catch(error){toast(error.message)}
  }

  async function decideProjectFact(valueId,decision,resolution){
    try{await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/facts/"+valueId+"/decision",{method:"POST",body:JSON.stringify({decision:decision,resolution:resolution||undefined,actor:"workspace-user"})});state.projectFactsLoaded=false;await loadProjectFacts(true);toast(resolution==="time-change"?"시점별 값으로 확정했습니다.":resolution==="correction"?"기존 값을 이력으로 보존하고 오기를 수정했습니다.":decision==="confirmed"?"메타정보 후보를 확정했습니다.":"메타정보 후보를 거부했습니다.")}catch(error){toast(error.message)}
  }

  async function addProjectFact(){
    var key=window.prompt("프로젝트 메타정보 키를 입력하세요. 예: organization.department");if(!key)return;
    var label=window.prompt("화면에 표시할 항목명을 입력하세요.",key);if(!label)return;
    var value=window.prompt("확정값을 입력하세요.");if(value===null)return;
    try{
      await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/facts",{method:"POST",body:JSON.stringify({key:key,label:label,value:value,status:"confirmed",confidence:1,actor:"workspace-user",source:{documentId:"manual",locator:"사용자 직접 입력"}})});
      state.projectFactsLoaded=false;await loadProjectFacts(true);toast("프로젝트 확정 메타정보를 저장했습니다.");addAudit("사용자","프로젝트 Fact 확정 · "+key,"완료");
    }catch(error){toast(error.message)}
  }

  async function askKnowledge(){
    var output=$("knowledgeAnswer");output.textContent="연결된 출처를 검색하고 있습니다.";
    try{
      var result=await api("/knowledge/query",{method:"POST",body:JSON.stringify({question:$("knowledgeQuestion").value,as_of:$("knowledgeAsOf").value,clearance:"internal"})});
      if(!result.answerable){output.innerHTML="<p>"+escapeHtml(result.answer)+"</p><small>답변을 생성하지 않았습니다.</small>";return}
      var citations=result.citations.map(function(source,index){return "<button class='knowledge-citation' data-locator='"+escapeHtml(source.locator)+"'>["+(index+1)+"] "+escapeHtml(source.title)+" · "+escapeHtml(source.documentId)+" · "+escapeHtml(source.locator)+" · 신뢰도 "+Math.round(source.confidence*100)+"%</button>"}).join("");
      output.innerHTML="<p>"+escapeHtml(result.answer)+"</p><div>"+citations+"</div>";
      document.querySelectorAll(".knowledge-citation").forEach(function(button){button.onclick=function(){toast("원문 위치: "+button.dataset.locator)}});
      addAudit("Knowledge","출처 기반 질의 · 인용 "+result.citations.length+"개","완료");
    }catch(error){output.textContent=error.message}
  }

  async function loadKnowledgeComparison(){
    try{
      var graph=await api("/knowledge/graph"),candidate=(graph.nodes||[]).find(function(node){return node.nodeType==="common-data"&&node.metadata&&Array.isArray(node.metadata.versions)&&node.metadata.versions.length>1});
      if(!candidate){$("knowledgeDelta").textContent="비교 가능한 시계열 기준정보가 없습니다.";$("knowledgeTimeline").innerHTML="<p class='empty-reference'>데이터 MCP 또는 프로젝트 메타정보에 기준일별 값을 등록하면 변화가 표시됩니다.</p>";return}
      var versions=candidate.metadata.versions.slice().sort(function(a,b){return String(a.effectiveDate||"").localeCompare(String(b.effectiveDate||""))}),first=versions[0],last=versions[versions.length-1];
      var result=await api("/knowledge/compare",{method:"POST",body:JSON.stringify({record_id:candidate.id.replace(/^data:/,""),from_date:first.effectiveDate||"",to_date:last.effectiveDate||""})});
      $("knowledgeComparisonTitle").textContent=result.label+" · 시점 비교";
      $("knowledgeDelta").textContent="변화량 "+Number(result.delta).toLocaleString()+"원 · "+(result.percentChange>=0?"+":"")+result.percentChange+"%";
      $("knowledgeTimeline").innerHTML=[result.from,result.to].map(function(item,index){return"<div><b>"+escapeHtml(item.effectiveDate)+(index?" 현재":"")+"</b><span>"+Number(item.value).toLocaleString()+" "+escapeHtml(result.unit)+"</span><small>"+escapeHtml(item.source.documentId)+" · "+escapeHtml(item.source.locator)+"</small></div>"}).join("");
    }catch(error){$("knowledgeTimeline").textContent=error.message}
  }

  async function loadKnowledgeGraph(notify){
    try{
      var graph=await api("/knowledge/graph");$("knowledgeNodeCount").textContent=graph.counts.nodes;$("knowledgeSourceCount").textContent=graph.counts.sources;$("knowledgeEdgeCount").textContent=graph.counts.edges;
      var names={};graph.nodes.forEach(function(node){names[node.id]=node.title});
      $("knowledgeGraph").innerHTML=graph.edges.length?graph.edges.map(function(edge){return"<div class='knowledge-edge'><span>"+escapeHtml(names[edge.source]||edge.source)+"</span><b>"+escapeHtml(edge.relation)+"</b><span>"+escapeHtml(names[edge.target]||edge.target)+"</span><small>"+Math.round(edge.weight*100)+"%</small></div>"}).join(""):"<p class='empty-reference'>연결된 지식 관계가 없습니다. 데이터 MCP를 게시하거나 프로젝트 메타정보에 출처를 연결하세요.</p>";
      if(notify)toast("지식 노드, 관계와 출처를 새로 불러왔습니다.");
    }catch(error){$("knowledgeGraph").textContent=error.message}
  }

  function highlightJson(text){return escapeHtml(text).replace(/(&quot;[^&]+?&quot;)(?=\s*:)/g,"<span class='key'>$1</span>").replace(/:\s*(&quot;.*?&quot;)/g,": <span class='string'>$1</span>")}

  function updateBuilderTemplateLab(){
    var lab=$("builderTemplateLab");if(!lab)return;
    var draft=state.builderDraft,type=$("mcpType")&&$("mcpType").value;
    lab.hidden=type!=="template";
    if(type!=="template")return;
    var sources=draft?(draft.references||[]).filter(function(item){return item.role==="template-source"&&/\.hwpx$/i.test(item.filename)}):[];
    var source=sources[sources.length-1],profile=source&&source.summary&&source.summary.templateProfile,schema=source&&source.summary&&source.summary.templateSchema,quality=source&&source.summary&&source.summary.templateQuality;
    var multiple=sources.length>1,editable=Boolean(draft&&draft.status!=="published"),slotReady=Boolean(schema&&schema.required&&schema.required.title&&schema.required.body),structuralReady=Boolean(schema&&schema.structuralBindingReady),needsConversion=Boolean(source&&!slotReady);
    lab.classList.toggle("has-error",multiple);
    $("templateAuthoringStatus").textContent=!draft?"먼저 양식 MCP 초안을 만드세요.":draft.status==="published"?"게시 버전은 고정되어 있습니다. 스토어에서 ‘수정’을 눌러 새 버전 초안을 만드세요.":multiple?("양식 기준 HWPX가 "+sources.length+"개입니다. 첨부 목록에서 하나만 남겨 주세요."):source?(source.filename+" · "+(needsConversion?"일반 HWPX 분석 완료 · 양식용 변환 필요":structuralReady?"양식 구조 준비 완료":"제목·본문 슬롯 확인 필요")):"일반 HWPX를 ‘양식 원본’으로 첨부하거나 기본 시작 양식을 사용하세요.";
    var summary=$("templateConversionSummary");
    if(summary)summary.textContent=multiple?"기준 파일이 여러 개이면 변환 대상을 결정할 수 없습니다.":source?((profile&&profile.mode||"분석 대기")+" · 제목/본문 "+(slotReady?"확정":"미확정")+" · 목록 "+(schema&&schema.repeaters&&schema.repeaters.lists?"감지":"검토")+" · 표 "+(schema&&schema.templateTables||0)+"개 · 실검증 "+(quality?(quality.passed?"통과":"실패"):"미실행")):"완성 보고서·빈 양식·예시 포함 HWPX를 모두 분석할 수 있습니다.";
    $("convertDraftTemplate").disabled=!editable||!source||!needsConversion||multiple;
    $("convertDraftTemplate").textContent=multiple?"원본 하나만 남겨 주세요":needsConversion?"일반 HWPX → 양식용 변환·반영":"양식용 변환 완료";
    $("downloadDraftTemplateSample").disabled=!editable||multiple;
    $("openTemplateAuthoring").disabled=!editable||multiple;
    $("verifyDraftTemplate").disabled=!draft||!source||multiple||!slotReady;
    $("correctDraftTemplate").disabled=!editable||!source||multiple;
    $("openTemplateAuthoring").textContent=source?"양식 수정 (RHWP로 편집)":"샘플 생성 후 RHWP로 편집";
  }

  async function verifyDraftTemplateQuality(){
    if(!state.builderDraft)return toast("먼저 양식 MCP 초안을 만드세요.");
    try{
      setStatus("양식 실렌더링·재파싱 검증 중");
      var result=await api("/builder/drafts/"+state.builderDraft.id+"/template-quality"),quality=result.quality||{},metrics=quality.metrics||{};
      $("templateConversionSummary").textContent=(quality.passed?"실검증 통과":"실검증 실패")+" · 본문 블록 "+(metrics.renderedBlocks||0)+"개 · 표 "+(metrics.renderedTables||0)+"개 · 매핑률 "+Math.round((metrics.mappingCoverage||0)*100)+"%";
      setStatus(quality.passed?"양식 실렌더링 검증 통과":"양식 실렌더링 검증 실패");
      if(!quality.passed){var failed=(quality.checks||[]).filter(function(item){return !item.passed}).map(function(item){return item.detail}).join(" · ");return toast(failed||"양식 구조를 다시 확인해 주세요.")}
      toast("제목·본문·목록"+(metrics.tableCapability?"·표":"")+"를 실제 렌더링하고 재파싱했습니다.");
    }catch(error){setStatus("양식 실렌더링 검증 실패");toast(error.message)}
  }



  var templateMappingState=null;

  function refreshTemplateMappingPreview(){
    if(!templateMappingState)return;
    var ids=["mappingTitle","mappingBody","mappingMain","mappingSub","mappingNote","mappingDepartment","mappingAuthor","mappingDocumentNumber","mappingApproval"],
      labels=["제목","본문","○ 원형","- 원형","※ 원형","담당 부서","작성자","문서번호","결재란"];
    var rows=ids.map(function(id,index){
      var locator=$(id).value,item=(templateMappingState.candidates||[]).find(function(candidate){return candidate.locator===locator});
      return item?labels[index]+" · "+item.locator+(item.insideTable?" · 표 안":"")+"\n"+(item.text||"(빈 문단)"):"";
    }).filter(Boolean);
    $("templateMappingPreview").textContent=rows.join("\n\n")||"문단을 선택하면 현재 텍스트와 위치를 확인할 수 있습니다.";
  }

  async function openTemplateMapping(){
    if(!state.builderDraft)return toast("먼저 양식 MCP 초안을 만드세요.");
    try{
      setStatus("HWPX 문단과 현재 TemplateSchema 분석 중");
      var result=await api("/builder/drafts/"+state.builderDraft.id+"/template-mapping"),mapping=result.mapping||{},candidates=mapping.candidates||[],slots=mapping.currentSlots||{};
      templateMappingState={draftId:state.builderDraft.id,candidates:candidates};
      var options=candidates.map(function(item){return"<option value='"+escapeHtml(item.locator)+"'>"+escapeHtml("P"+item.paragraphIndex+(item.insideTable?" · 표":"")+" · "+item.preview)+"</option>"}).join("");
      ["mappingTitle","mappingBody"].forEach(function(id){$(id).innerHTML=options});
      ["mappingMain","mappingSub","mappingNote","mappingDepartment","mappingAuthor","mappingDocumentNumber","mappingApproval"].forEach(function(id){$(id).innerHTML="<option value=''>자동 감지 / 지정 안 함</option>"+options});
      var nonblank=candidates.filter(function(item){return item.text&&!item.insideTable}),titleDefault=slots.title||(nonblank[0]&&nonblank[0].locator)||"",bodyDefault=slots.content||slots.body||(nonblank.find(function(item){return item.locator!==titleDefault})||{}).locator||"";
      $("mappingTitle").value=titleDefault;$("mappingBody").value=bodyDefault;
      var patterns={mappingMain:/^\s*[○ㅇ]/,mappingSub:/^\s*[-·]/,mappingNote:/^\s*[※*]/};
      Object.keys(patterns).forEach(function(id){var found=candidates.find(function(item){return patterns[id].test(item.text||"")});$(id).value=found?found.locator:""});
      var metadataDefaults={mappingDepartment:"department",mappingAuthor:"author",mappingDocumentNumber:"document_number",mappingApproval:"approval_line"};
      Object.keys(metadataDefaults).forEach(function(id){$(id).value=slots[metadataDefaults[id]]||""});
      if(!$('mappingApproval').value){var approval=candidates.find(function(item){return item.approvalLike});$('mappingApproval').value=approval?approval.locator:""}
      $("templateMappingHelp").textContent=result.filename+" · 보정 가능 문단 "+mapping.total+"개 · 제목과 본문은 서로 다른 문단으로 지정하세요.";
      ["mappingTitle","mappingBody","mappingMain","mappingSub","mappingNote","mappingDepartment","mappingAuthor","mappingDocumentNumber","mappingApproval"].forEach(function(id){$(id).onchange=refreshTemplateMappingPreview});
      refreshTemplateMappingPreview();$("templateMappingDialog").showModal();setStatus("양식 슬롯 선택 대기");
    }catch(error){setStatus("양식 슬롯 분석 실패");toast(error.message)}
  }

  async function applyTemplateMapping(){
    if(!templateMappingState)return;
    if($("mappingTitle").value===$("mappingBody").value)return toast("제목과 본문은 서로 다른 문단이어야 합니다.");
    try{
      $("applyTemplateMapping").disabled=true;setStatus("슬롯 보정·실렌더링 검증 중");
      var result=await api("/builder/drafts/"+templateMappingState.draftId+"/template-mapping",{method:"POST",body:JSON.stringify({title_locator:$("mappingTitle").value,body_locator:$("mappingBody").value,main_locator:$("mappingMain").value,sub_locator:$("mappingSub").value,note_locator:$("mappingNote").value,department_locator:$("mappingDepartment").value,author_locator:$("mappingAuthor").value,document_number_locator:$("mappingDocumentNumber").value,approval_locator:$("mappingApproval").value,actor:"workspace-user"})});
      state.builderDraft=result.draft;showBuilderDraft(result.draft);await loadBuilderDrafts();$("templateMappingDialog").close();setStatus("양식 슬롯 보정·실검증 완료");toast("제목·본문·목록·메타·결재란 슬롯을 반영했습니다.");
    }catch(error){setStatus("양식 슬롯 보정 실패");toast(error.message)}
    finally{$("applyTemplateMapping").disabled=false}
  }


  async function convertDraftTemplateSource(){
    if(!state.builderDraft)return toast("먼저 양식 MCP 초안을 만드세요.");
    try{
      setStatus("일반 HWPX 구조 분석 및 양식용 변환 중");
      var result=await api("/builder/drafts/"+state.builderDraft.id+"/template-convert",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});
      state.builderDraft=result.draft;showBuilderDraft(result.draft);downloadBase64(result.filename,result.contentBase64);await loadBuilderDrafts();setStatus("양식용 HWPX 변환·초안 반영 완료");
      var inference=result.conversion&&result.conversion.inference||{},prototypes=inference.prototypes||[];
      toast("제목·본문"+(prototypes.length?"·"+prototypes.join("·"):"")+" 구조를 양식 슬롯으로 변환해 반영하고 다운로드했습니다.");
    }catch(error){setStatus("양식용 HWPX 변환 실패");toast(error.message)}
  }

  async function downloadDraftTemplateSample(){
    if(!state.builderDraft)return toast("먼저 양식 MCP 초안을 만드세요.");
    try{
      setStatus("첨부 양식 기반 등록 샘플 생성 중");
      var sample=await api("/builder/drafts/"+state.builderDraft.id+"/template-sample");
      downloadBase64(sample.filename,sample.contentBase64);
      setStatus("양식 등록 샘플 HWPX 생성 완료");
      toast("첨부 양식의 서식을 유지한 등록 샘플을 만들었습니다. {{title}}과 {{content}}는 유지해 주세요.");
    }catch(error){setStatus("양식 등록 샘플 생성 실패");toast(error.message)}
  }

  async function openTemplateAuthoring(){
    if(!state.builderDraft)return toast("먼저 양식 MCP 초안을 만드세요.");
    try{
      setStatus("RHWP 양식 제작 세션 준비 중");
      var session=await api("/builder/drafts/"+state.builderDraft.id+"/template-authoring/session",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});
      state.templateAuthoringDraftId=state.builderDraft.id;
      setView("editor");
      await renderNativeSession(session);
      setStatus("양식 수정 중 · 완료 후 초안 반영 필요");
      toast("RHWP에서 고정 문구와 서식을 수정하세요. 제목·본문 슬롯 문자열은 삭제하지 마세요.");
    }catch(error){setStatus("RHWP 양식 제작 세션 시작 실패");toast(error.message)}
  }

  async function commitTemplateAuthoring(){
    if(!state.nativeSession||state.nativeSession.purpose!=="template-authoring")return toast("현재 양식 수정 세션이 없습니다.");
    try{
      setStatus("RHWP 수정본 저장 중");
      if(!await performDocumentSave())return;
      var draftId=state.nativeSession.builderDraftId||state.templateAuthoringDraftId;
      var result=await api("/builder/drafts/"+draftId+"/template-authoring/commit",{method:"POST",body:JSON.stringify({session_id:state.nativeSession.id,actor:"workspace-user"})});
      state.builderDraft=result.draft;state.templateAuthoringDraftId=null;
      if(state.rhwpEditor){var editor=state.rhwpEditor;state.rhwpEditor=null;editor.destroy()}
      state.nativeSession=null;["templateAuthoringCommit","templateAuthoringCancel"].forEach(function(id){var node=$(id);if(node)node.remove()});
      setView("builder");
      setStatus("양식 수정본 초안 반영 완료 · 재검증 필요");
      toast("RHWP 수정본을 유일한 양식 원본으로 반영했습니다. 샌드박스 검증을 다시 실행하세요.");
    }catch(error){setStatus("양식 수정본 반영 실패");toast(error.message)}
  }

  function cancelTemplateAuthoring(){
    if(state.rhwpEditor){var editor=state.rhwpEditor;state.rhwpEditor=null;editor.destroy()}
    state.nativeSession=null;state.templateAuthoringDraftId=null;["templateAuthoringCommit","templateAuthoringCancel"].forEach(function(id){var node=$(id);if(node)node.remove()});
    setView("builder");toast("수정본을 초안에 반영하지 않고 MCP 제작 화면으로 돌아왔습니다.");
  }

  async function deleteBuilderReference(referenceId,filename){
    if(!state.builderDraft)return;
    if(!window.confirm("첨부 파일 ‘"+filename+"’을 삭제할까요?"))return;
    try{
      setStatus("첨부 파일 삭제 중");
      var result=await api("/builder/drafts/"+state.builderDraft.id+"/references/"+referenceId,{method:"DELETE",body:JSON.stringify({actor:"workspace-user"})});
      showBuilderDraft(result.draft);await loadBuilderDrafts();setStatus("첨부 파일 삭제 완료");toast(filename+"을 삭제했습니다.");
    }catch(error){setStatus("첨부 파일 삭제 실패");toast(error.message)}
  }

  function showBuilderDraft(draft){
    state.builderDraft=draft;
    $("manifestPreview").innerHTML=highlightJson(JSON.stringify(draft.manifest,null,2));
    var passed=draft.validation&&draft.validation.passed;
    $("manifestStatus").textContent=draft.status==="published"?"스토어 게시 완료":passed?"샌드박스 검증 통과":draft.status==="rejected"?"검증 실패":"서버 초안 저장됨";
    $("testList").innerHTML=(draft.validation.tests||[]).length?(draft.validation.tests||[]).map(function(test){return"<div><i>"+(test.passed?"✓":"×")+"</i> "+escapeHtml(test.id)+" · "+escapeHtml(test.detail)+"</div>"}).join(""):"<div><i>○</i> Manifest 생성 후 서버 샌드박스 검증을 실행하세요.</div>";
    $("publishMcp").disabled=draft.status!=="validated";
    $("publishMcp").textContent=draft.status==="validated"?"게시하고 대화 검색 활성화":draft.status==="published"?"게시 완료 · 설치 상태 확인":"검증 후 게시·설치";
    if($("managePublishedMcp"))$("managePublishedMcp").hidden=draft.status!=="published";
    $("runSandbox").disabled=draft.status==="published";
    $("generateManifest").disabled=true;$("generateManifest").textContent="초안 생성 완료";
    $("mcpName").value=draft.manifest.name||"";
    $("mcpPackageId").value=draft.manifest.id||"";
    $("mcpVersion").value=draft.manifest.version||"0.1.0";
    $("mcpDescription").value=draft.manifest.description||"";
    var guide=draft.manifest.builderGuide||{};
    if($("mcpType")){$("mcpType").value=draft.manifest.mcpType||"tool";updateBuilderTypeUi($("mcpType").value,true)}
    if($("mcpInstructions"))$("mcpInstructions").value=guide.instructions||draft.manifest.description||"";
    if($("mcpCautions"))$("mcpCautions").value=(guide.cautions||[]).join("\n");
    if($("mcpProcedure"))$("mcpProcedure").value=(guide.procedure||[]).join("\n");
    if($("mcpTriggers"))$("mcpTriggers").value=(guide.triggerExamples||[]).join("\n");
    if($("mcpDataSource"))$("mcpDataSource").value=guide.dataSource||"";
    var connector=draft.manifest.externalMcp||{};
    if($("externalTransport"))$("externalTransport").value=connector.transport||"stdio";
    if($("externalServerProfile"))$("externalServerProfile").value=connector.serverProfile||"kordoc@4.7.3";
    if($("externalEndpointEnv"))$("externalEndpointEnv").value=connector.endpointEnv||"AIWORKS_EXTERNAL_MCP_URL";
    if($("externalToolName"))$("externalToolName").value=connector.toolName||"generate_document";
    if($("externalCapability"))$("externalCapability").value=(draft.manifest.capabilities||[])[0]||"document.hwpx.finalize";
    if($("externalPreset"))$("externalPreset").value=connector.preset||"보고서";
    if($("externalOutputContent"))$("externalOutputContent").value=connector.outputContentPath||"contentBase64";
    if($("externalOutputFilename"))$("externalOutputFilename").value=connector.outputFilenamePath||"filename";
    updateExternalTransportUi();
    if($("useModel"))$("useModel").checked=Boolean(guide.useModel);
    var visibility=document.querySelector("input[name='visibility'][value='"+draft.manifest.visibility+"']");
    if(visibility)visibility.checked=true;
    $("sourceIncluded").checked=Boolean(draft.manifest.sourceIncluded);
    $("allowExternal").checked=draft.manifest.runtime!=="local";
    $("referenceList").innerHTML=(draft.references||[]).length?(draft.references||[]).map(function(item){var summary=item.summary||{},rag=summary.ragReady?"<em class='rag-ready'>RAG 준비 · "+Number(summary.chunks||0).toLocaleString()+"개 청크"+(summary.pagesWithText?" · "+summary.pagesWithText+"쪽":"")+"</em>":"",profile=summary.templateProfile,template=profile?"<em class='template-ready'>양식 분석 · "+escapeHtml(profile.mode)+" · 신뢰도 "+Math.round(Number(profile.confidence||0)*100)+"%</em>":"",remove=draft.status==="published"?"":"<button class='reference-delete' data-delete-reference='"+escapeHtml(item.id)+"' data-reference-filename='"+escapeHtml(item.filename)+"'>삭제</button>";return"<div class='reference-item'><b>"+escapeHtml(item.filename)+"</b><span>"+escapeHtml(item.role||"guide")+" · "+Number(item.bytes).toLocaleString()+" bytes</span>"+remove+rag+template+"<small>"+escapeHtml(String((profile&&profile.notice)||summary.excerpt||summary.kind||"구조 검사 완료").slice(0,320))+"</small></div>"}).join(""):"<div class='empty-reference'>첨부 없음 · HWPX, PDF, DOCX, XLSX, Markdown, TXT 지원</div>";
    document.querySelectorAll("[data-delete-reference]").forEach(function(button){button.onclick=function(){deleteBuilderReference(button.dataset.deleteReference,button.dataset.referenceFilename)}});
    if($("builderRagLab")){
      var isData=draft.manifest.mcpType==="data",ragReferences=(draft.references||[]).filter(function(item){return item.role==="data-source"&&item.summary&&item.summary.ragReady});
      $("builderRagLab").hidden=!isData;$("runDraftRag").disabled=!ragReferences.length;if($("runDraftRagReport"))$("runDraftRagReport").disabled=!ragReferences.length;
      $("draftRagIndex").textContent=ragReferences.length?ragReferences.length+"개 원본 · "+ragReferences.reduce(function(total,item){return total+Number(item.summary.chunks||0)},0)+"개 검색 청크":"데이터 원본 PDF를 첨부하면 검색할 수 있습니다.";
    }
    if($("probeExternalMcp"))$("probeExternalMcp").disabled=draft.manifest.mcpType!=="external";
    if($("resolverIntent")&&!$("resolverIntent").value&&(guide.triggerExamples||[]).length)$("resolverIntent").value=guide.triggerExamples[0];
    updateBuilderTemplateLab();
    updateBuilderStudioProgress();
  }
  async function loadBuilderDrafts(){
    try{
      var result=await api("/builder/drafts");var items=result.items||[];
      if($("studioDraftCount"))$("studioDraftCount").textContent=items.length;
      $("builderDraftList").innerHTML=items.length?items.slice(0,8).map(function(item){var refs=item.references||[],chunks=refs.reduce(function(total,ref){return total+Number((ref.summary||{}).chunks||0)},0),labels={draft:"작성 중",validated:"검증 통과",rejected:"검증 실패",published:"게시 완료"},asset=refs.length?refs.length+"개 문서"+(chunks?" · RAG "+chunks+"청크":""):"첨부 없음";return"<button data-draft-id='"+escapeHtml(item.id)+"'><b>"+escapeHtml(item.manifest.name)+"</b><span>"+escapeHtml(labels[item.status]||item.status)+" · "+asset+"</span><small>"+escapeHtml(item.manifest.id)+"@"+escapeHtml(item.manifest.version)+" · "+escapeHtml(item.id.slice(-8))+"</small></button>"}).join(""):"<span class='empty-reference'>저장된 초안이 없습니다.</span>";
      document.querySelectorAll("[data-draft-id]").forEach(function(button){button.onclick=function(){var draft=items.find(function(item){return item.id===button.dataset.draftId});if(draft){showBuilderDraft(draft);var chunks=(draft.references||[]).reduce(function(total,ref){return total+Number((ref.summary||{}).chunks||0)},0);toast(draft.manifest.name+" 초안을 열었습니다"+(chunks?" · RAG "+chunks+"청크":" · 첨부 없음"))}}});
    }catch(error){$("builderDraftList").textContent=error.message}
  }
  var builderTypeUi={
    template:{label:"양식 MCP",guide:"HWPX 양식의 {{title}}, {{content}}, {{body}}, {{date}}, {{source_filename}} 위치에 원문을 대응합니다. 양식 파일·유의사항·처리 순서를 함께 등록하세요.",role:"template-source",roleLabel:"양식 원본",procedure:"양식 원본의 고정 영역과 플레이스홀더 입력 영역을 구분한다.\n현재 문서의 제목과 본문을 등록 필드에 대응한다.\n유의사항을 검사한 뒤 새 문서 revision으로 저장한다."},
    process:{label:"처리 MCP",guide:"반복 업무를 2단계 이상의 처리 순서와 체크포인트로 구성합니다.",role:"guide",roleLabel:"업무 지침",procedure:"입력 자료와 실행 조건을 확인한다.\n업무 단계를 순서대로 처리한다.\n결과를 검증하고 산출물과 로그를 저장한다."},
    data:{label:"데이터 MCP",guide:"PDF·HWPX·텍스트 자료를 로컬에서 페이지별로 추출하고 RAG 검색 인덱스를 만듭니다. 대화에서 데이터 의도가 감지되면 설치된 MCP를 자동 선택해 출처와 함께 답합니다.",role:"data-source",roleLabel:"검색 데이터 원본",procedure:"사용자 질의에서 기관·연도·항목을 파악한다.\n등록된 문서의 관련 청크를 검색한다.\n확인된 근거와 원문 위치를 인용해 답한다."},
    tool:{label:"일반 도구 MCP",guide:"특정 도구 호출이나 변환 기능을 입력·출력 계약으로 감쌉니다.",role:"guide",roleLabel:"도구 가이드",procedure:"입력값을 검증한다.\n도구를 실행한다.\n결과와 오류를 표준 형식으로 반환한다."},
    external:{label:"외부 MCP 연결",guide:"검증된 공개 MCP는 고정 버전의 로컬 stdio 프로필로, 원격 MCP는 Streamable HTTP로 연결합니다. 임의 명령은 실행하지 않으며 문서 자동 후처리는 로컬·오프라인 프로필만 허용합니다.",role:"guide",roleLabel:"연동 가이드",procedure:"MCP 서버 프로필과 고정 버전을 확인한다.\ntools/list에서 연결할 도구를 검증한다.\n입출력 파일을 격리된 작업 폴더에 매핑한다.\n반환 HWPX를 검사하고 RHWP에서 연다."}
  };
  var builderQuickPresets={
    template:{name:"부처 보고서 양식 MCP",description:"사용자가 등록한 HWPX 양식을 기준으로 현재 문서의 제목과 본문을 해당 보고 형식으로 변환한다.",instructions:"등록 양식의 고정 문구와 서식은 유지하고 현재 문서의 제목·본문·작성 정보를 플레이스홀더에 대응한다.",cautions:"원문에 없는 수치나 기관명을 추측하지 않는다.\n확인할 수 없는 값은 확인 필요로 표시한다.",procedure:"양식의 고정 영역과 플레이스홀더를 확인한다.\n현재 문서의 제목과 본문을 대응한다.\n유의사항을 검사하고 새 revision으로 저장한다.",triggers:"등록한 부처 보고서 양식으로 바꿔줘",useModel:false,allowExternal:false,sourceIncluded:true},
    process:{name:"결재 전 검토 처리 MCP",description:"제출 자료의 필수 항목과 누락 내용을 확인하고 단계별 검토 결과를 보고서로 작성한다.",instructions:"입력 자료를 검토 기준과 처리 순서에 따라 확인하고 누락 항목·확인 결과·후속 조치를 구조화한다.",cautions:"원문을 직접 변경하지 않는다.\n누락 근거와 확인 위치를 함께 기록한다.",procedure:"입력 자료와 실행 조건을 확인한다.\n필수 항목과 누락 내용을 검사한다.\n검토 결과와 후속 조치를 보고서로 작성한다.",triggers:"이 자료를 결재 전 검토 보고서로 작성해줘",useModel:true,allowExternal:true,sourceIncluded:false},
    data:{name:"예산 정책 데이터 MCP",description:"사용자가 등록한 예산·정책 PDF를 RAG로 검색하여 연도, 기관, 정책 항목과 수치를 원문 근거와 함께 답한다.",instructions:"질문과 관련된 등록 문서 청크만 사용하고 모든 핵심 수치와 설명에 파일명·페이지 출처를 연결한다.",cautions:"출처가 없는 값은 추측하지 않는다.\n기준연도와 단위를 확인한다.\n서로 다른 시점의 수치를 임의로 합치지 않는다.",procedure:"질문에서 기관·연도·정책 항목을 파악한다.\n등록 PDF의 관련 청크를 검색한다.\n근거 번호와 원문 위치를 포함해 답한다.",triggers:"우리부 예산 현황을 확인해줘\n등록된 예산 정책 자료에서 관련 수치를 찾아줘",dataSource:"사용자 등록 PDF · 로컬 RAG · 원문 페이지 인용",useModel:false,allowExternal:false,sourceIncluded:true},
    tool:{name:"회의 핵심 요약 MCP",description:"회의 기록에서 결정 사항, 담당자와 후속 조치를 빠르게 추출하여 간결하게 요약한다.",instructions:"회의 기록을 읽고 결정 사항과 담당자별 후속 조치를 분리해 최종 결과만 반환한다.",cautions:"발언에 없는 결정을 만들지 않는다.\n담당자가 불명확하면 확인 필요로 표시한다.",procedure:"회의 기록의 핵심 안건을 확인한다.\n결정 사항과 담당자를 추출한다.\n후속 조치를 기한과 함께 정리한다.",triggers:"회의 핵심과 후속 조치를 요약해줘",useModel:true,allowExternal:true,sourceIncluded:false},
    external:{name:"KODAK 한글 문서 변환 MCP",description:"공개 kordoc 4.7.3 MCP를 로컬 stdio로 실행하여 현재 보고서 내용을 정부 보고서 서식의 HWPX로 생성한다.",instructions:"현재 보고서의 제목과 본문을 Markdown으로 정규화하고 kordoc generate_document를 보고서 프리셋으로 실행한 뒤 반환 HWPX의 무결성을 검사한다.",cautions:"kordoc은 고정 버전 로컬 런타임만 사용한다.\nKORDOC_OFFLINE=1과 작업 폴더 제한을 유지한다.\n반환 HWPX가 열리지 않으면 원본 보고서를 유지한다.",procedure:"kordoc stdio 서버의 tools/list를 조회한다.\ngenerate_document 입력에 보고서 Markdown과 출력 경로를 매핑한다.\n보고서 프리셋으로 HWPX를 생성한다.\n반환 HWPX를 검사하고 RHWP에서 연다.",triggers:"이 보고서를 제대로 서식이 적용된 한글 문서로 만들어줘\nKODAK으로 HWPX를 변환해줘",useModel:false,allowExternal:false,sourceIncluded:false}
  };

  function applyBuilderPreset(type,silent){
    var preset=builderQuickPresets[type]||builderQuickPresets.tool;
    $("mcpType").value=type;updateBuilderTypeUi(type,false);
    $("mcpName").value=preset.name;$("mcpPackageId").value="";$("mcpVersion").value="0.1.0";
    $("mcpDescription").value=preset.description;$("mcpInstructions").value=preset.instructions;
    $("mcpCautions").value=preset.cautions;$("mcpProcedure").value=preset.procedure;$("mcpTriggers").value=preset.triggers;
    $("mcpDataSource").value=preset.dataSource||"";$("useModel").checked=preset.useModel;$("allowExternal").checked=preset.allowExternal;$("sourceIncluded").checked=preset.sourceIncluded;
    if(type==="external"){$("externalTransport").value="stdio";$("externalServerProfile").value="kordoc@4.7.3";$("externalEndpointEnv").value="AIWORKS_EXTERNAL_MCP_URL";$("externalToolName").value="generate_document";$("externalCapability").value="document.hwpx.finalize";$("externalPreset").value="보고서";$("externalOutputContent").value="contentBase64";$("externalOutputFilename").value="filename";updateExternalTransportUi()}
    document.querySelectorAll("[data-builder-type]").forEach(function(card){card.classList.toggle("active",card.dataset.builderType===type)});
    if(!silent){setStatus(preset.name+" 빠른 예시를 불러옴");toast("내용을 수정하거나 그대로 초안을 만들어 체험할 수 있습니다.")}
  }

  function updateBuilderStudioProgress(){
    if(!$("studioSteps"))return;
    var draft=state.builderDraft,installed=Boolean(draft&&state.capabilityRegistry.some(function(item){return item.packageRef===draft.manifest.id+"@"+draft.manifest.version}));
    var needsReference=draft&&["template","data"].indexOf(draft.manifest.mcpType)>=0;
    var stages=[Boolean(draft),Boolean(draft&&(!needsReference||(draft.references||[]).length)),Boolean(draft&&draft.validation&&draft.validation.passed),Boolean(draft&&draft.status==="published"),installed];
    document.querySelectorAll("#studioSteps .studio-step").forEach(function(node,index){node.classList.toggle("done",stages[index]);node.classList.toggle("current",!stages[index]&&(index===0||stages[index-1]))});
    if($('studioDraftStatus'))$('studioDraftStatus').textContent=!draft?"새 MCP를 시작하세요":installed?"설치 완료 · 대화에서 자동 검색":draft.status==="published"?"게시 완료 · 설치 승인 필요":draft.validation&&draft.validation.passed?"검증 통과 · 게시 가능":"초안 편집 중";
  }

  async function loadCapabilityRegistry(){
    if(!$("capabilityRegistryList"))return;
    try{
      var data=await api("/capabilities/registry");state.capabilityRegistry=data.items||[];
      var packages=[];state.capabilityRegistry.forEach(function(item){if(!packages.some(function(existing){return existing.packageRef===item.packageRef}))packages.push(item)});
      $("registryPackageCount").textContent=data.installedPackages||0;$("registryCapabilityCount").textContent=data.count||0;
      $("capabilityRegistryList").innerHTML=packages.length?packages.map(function(item){return"<article class='registry-card'><span class='registry-status'>사용 가능</span><b>"+escapeHtml(item.name)+"</b><small>"+escapeHtml(item.packageRef)+" · "+escapeHtml(item.executionAdapter)+"</small><p>"+escapeHtml((item.triggerExamples||[])[0]||"호출 예시를 등록하세요")+"</p></article>"}).join(""):"<div class='registry-empty'><b>아직 설치된 사용자 MCP가 없습니다.</b><span>위에서 예시를 선택해 초안 생성 → 검증 → 게시 → 설치하면 이곳에 나타납니다.</span></div>";
      updateBuilderStudioProgress();
    }catch(error){$("capabilityRegistryList").innerHTML="<div class='registry-empty'>"+escapeHtml(error.message)+"</div>"}
  }

  async function resolveBuilderIntent(){
    var intent=$("resolverIntent").value.trim(),output=$("resolverResult");if(!intent)return toast("검색할 호출 문구를 입력하세요.");
    output.innerHTML="<div class='registry-empty'>설치된 Capability와 호출 예시를 비교하고 있습니다.</div>";
    try{
      var result=await api("/capabilities/resolve",{method:"POST",body:JSON.stringify({intent:intent,limit:3})});state.builderResolution=result;
      if(!result.items.length){output.innerHTML="<div class='resolver-miss'><b>일치하는 설치 MCP가 없습니다.</b><span>먼저 MCP를 게시·설치하거나 호출 예시를 더 구체적으로 입력하세요.</span></div>";$("runResolvedIntent").disabled=true;return}
      output.innerHTML=result.items.map(function(item,index){return"<article class='resolver-hit "+(index===0?"best":"")+"'><span>"+(index===0?"선택 예정":"대안")+" · 일치도 "+item.score+"</span><b>"+escapeHtml(item.name)+"</b><small>"+escapeHtml(item.packageRef)+" · "+escapeHtml(item.capabilityId)+"</small><p>근거: "+escapeHtml((item.matchedBy||[]).join(", "))+"</p></article>"}).join("");$("runResolvedIntent").disabled=false;
    }catch(error){output.innerHTML="<div class='resolver-miss'>"+escapeHtml(error.message)+"</div>";$("runResolvedIntent").disabled=true}
  }
  async function queryDraftRag(makeReport){
    var query=$("draftRagQuery").value.trim(),output=$("draftRagResult");
    if(!state.builderDraft)return toast("먼저 데이터 MCP 초안을 만드세요.");
    if(!query)return toast("등록 자료에서 찾을 질문을 입력하세요.");
    output.innerHTML="<div class='registry-empty'>"+(makeReport?"근거를 연도별로 정리하고 편집용 HWPX를 만들고 있습니다.":"PDF 청크에서 관련 근거를 찾고 있습니다.")+"</div>";
    try{
      var result=await api("/builder/drafts/"+state.builderDraft.id+"/rag/query",{method:"POST",body:JSON.stringify({query:query,limit:5,report:Boolean(makeReport),actor:"workspace-user"})});
      var hits=(result.hits||[]).map(function(hit){return"<article class='rag-preview-hit'><span>["+hit.rank+"] "+escapeHtml(hit.locator)+" · 점수 "+hit.score+"</span><p>"+escapeHtml(hit.excerpt)+"</p></article>"}).join("");
      output.innerHTML="<div class='rag-preview-answer'>"+escapeHtml(result.answer)+"</div>"+(hits||"<div class='resolver-miss'>일치하는 근거가 없습니다.</div>");
      if(makeReport&&result.artifact){
        await openGeneratedArtifact(result.artifact,result.loadedMcps||[]);
        addAssistant("데이터 MCP의 검색 근거를 연도·지적사항·출처로 정리해 편집 가능한 보고서 초안을 열었습니다.");
        setStatus("데이터 MCP → 보고서 MCP → RHWP 연결 완료");
        return;
      }
      setStatus("로컬 근거 정리 완료 · 출처 "+(result.hits||[]).length+"개");
    }catch(error){output.innerHTML="<div class='resolver-miss'>"+escapeHtml(error.message)+"</div>"}
  }
  function updateBuilderTypeUi(type,preserve){
    var config=builderTypeUi[type]||builderTypeUi.tool;
    document.querySelectorAll("[data-builder-type]").forEach(function(card){card.classList.toggle("active",card.dataset.builderType===type)});
    if($("builderTypeGuide"))$("builderTypeGuide").innerHTML="<b>"+escapeHtml(config.label)+"</b><span>"+escapeHtml(config.guide)+"</span>";
    if($("referenceRole")){
      var roles={template:[["template-source","양식 원본"],["guide","작성 지침"],["sample-input","입력 예시"]],process:[["guide","업무 지침"],["sample-input","입력 예시"],["sample-output","결과 예시"]],data:[["data-source","검색 데이터 원본"],["data-schema","데이터 Schema"],["guide","조회 지침"],["sample-output","응답 예시"]],tool:[["guide","도구 가이드"],["sample-input","입력 예시"],["sample-output","결과 예시"]],external:[["guide","연동 가이드"],["sample-input","요청 예시"],["sample-output","응답 예시"]]};
      $("referenceRole").innerHTML=roles[type].map(function(item){return"<option value='"+item[0]+"'>"+item[1]+"</option>"}).join("");
    }
    if($("builderDataSourceField"))$("builderDataSourceField").hidden=type!=="data";
    if($("builderExternalFields"))$("builderExternalFields").hidden=type!=="external";
    if(!preserve&&$("mcpProcedure"))$("mcpProcedure").value=config.procedure;
    if(!preserve&&["template","data"].indexOf(type)>=0)$("sourceIncluded").checked=true;
    if($("builderRagLab"))$("builderRagLab").hidden=type!=="data";
    updateBuilderTemplateLab();
    if(type==="external"){updateExternalTransportUi();$("allowExternal").disabled=true}else $("allowExternal").disabled=false;
  }
  function updateExternalTransportUi(){
    if(!$("externalTransport"))return;
    var isStdio=$("externalTransport").value==="stdio";
    document.querySelectorAll(".external-stdio-only").forEach(function(field){field.hidden=!isStdio});
    document.querySelectorAll(".external-http-only").forEach(function(field){field.hidden=isStdio});
    if($("allowExternal"))$("allowExternal").checked=!isStdio;
    if($("externalProbeStatus"))$("externalProbeStatus").textContent=isStdio?"초안 생성 후 로컬 kordoc 4.7.3 설치 상태와 tools/list를 확인합니다.":"초안 생성 후 URL 환경변수와 tools/list를 확인합니다.";
  }
  function renderBuilder(){
    $("builderView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>MCP Studio</span><h1>플랫폼 전용 MCP 제작기</h1><p>자연어 업무 설명을 서버에 저장된 계약으로 변환하고, 검증된 버전만 서명해 스토어에 등록합니다.</p></div><div class='module-actions'><button id='managePublishedMcp' hidden>스토어에서 수정·삭제</button><button class='primary' id='publishMcp' disabled>검증 후 스토어 등록</button></div></div><section class='surface draft-history'><div class='surface-head'><h2>저장된 제작 작업</h2><small>초안·검증·게시 상태</small></div><div id='builderDraftList' class='draft-list'>불러오는 중...</div></section><div class='builder-grid'><section class='surface'><div class='surface-head'><h2>1. 목적과 사용 조건</h2><small>자연어 → 구조화 계약</small></div><label class='field'><span>MCP 이름</span><input id='mcpName' value='예산 검증 MCP'></label><div class='builder-id-grid'><label class='field'><span>패키지 ID · 비우면 자동 생성</span><input id='mcpPackageId' placeholder='org.budget-checker'></label><label class='field'><span>버전</span><input id='mcpVersion' value='0.1.0'></label></div><label class='field'><span>어떤 업무를 처리하나요?</span><textarea id='mcpDescription' rows='6'>예산요청서에서 필수 항목 누락과 산출 근거 오류를 찾고, 최신 SW대가 기준과 비교해 수정안을 제안한다. 원문은 외부로 보내지 않는다.</textarea></label><div class='field'><span>기준 문서 · 로컬 추출 및 SHA-256 검사</span><div id='referenceList' class='reference-list'><div class='empty-reference'>초안을 만든 뒤 실제 기준 문서를 첨부하세요.</div></div></div><div id='builderRagLab' class='builder-rag-lab' hidden><div><b>등록 자료 RAG 미리보기</b><span id='draftRagIndex'>데이터 원본 PDF를 첨부하면 검색할 수 있습니다.</span></div><div class='builder-rag-query'><input id='draftRagQuery' placeholder='예: 이 자료에서 예산 총액과 주요 정책을 찾아줘'><button id='runDraftRag' disabled>근거 검색</button></div><div id='draftRagResult' class='resolver-result'><div class='registry-empty'>게시 전에도 실제 검색 청크와 원문 위치를 확인할 수 있습니다.</div></div></div><input id='referenceFile' type='file' accept='.hwpx,.pdf,.docx,.xlsx,.md,.txt' multiple hidden><div class='toggle-row'><label><input type='radio' name='visibility' value='private'> 개인 전용</label><label><input type='radio' name='visibility' value='organization' checked> 조직 공개</label><label><input type='radio' name='visibility' value='public'> 공개</label></div><div class='toggle-row'><label><input type='checkbox' id='sourceIncluded'> 게시 패키지에 원본 포함</label><label><input type='checkbox' id='allowExternal'> 외부 모델·MCP 전송 허용</label></div><div class='form-actions'><button id='attachReference'>＋ PDF·자료 추가</button><button class='primary' id='generateManifest'>새 초안·Manifest 생성</button></div></section><section class='surface'><div class='surface-head'><h2>2. Manifest 미리보기</h2><small id='manifestStatus'>아직 생성되지 않음</small></div><pre class='code-preview' id='manifestPreview'>서버 초안을 생성하면 계약이 표시됩니다.</pre></section></div><section class='surface'><div class='surface-head'><h2>3. 샌드박스 계약 테스트</h2><button class='inline-link' id='runSandbox' disabled>전체 테스트 실행</button></div><div class='test-list' id='testList'><div><i>○</i> Manifest 생성 후 서버 샌드박스 검증을 실행하세요.</div></div></section></div>";
    var page=$("builderView").querySelector(".module-page"),hero=page.querySelector(".module-hero");page.classList.add("mcp-studio-page");
    hero.querySelector(".eyebrow").textContent="MCP STUDIO · BUILD → INSTALL → RUN";
    hero.querySelector("h1").textContent="필요한 MCP를 만들고 바로 불러보세요";
    hero.querySelector("p").textContent="업무 유형을 고르고 예시를 수정하면 계약·권한·실행 가이드가 자동 생성됩니다. 게시·설치 후 호출 문구가 어떤 MCP를 선택하는지 이 화면에서 확인할 수 있습니다.";
    hero.querySelector(".module-actions").insertAdjacentHTML("afterbegin","<button id='downloadTemplateStarter'>HWPX 시작 양식</button><button id='newBuilderDraft'>＋ 새 MCP</button>");
    hero.insertAdjacentHTML("afterend","<section class='studio-overview'><div class='studio-status-bar'><div><span>현재 제작 상태</span><b id='studioDraftStatus'>새 MCP를 시작하세요</b></div><div class='studio-live-metrics'><span><b id='studioDraftCount'>-</b> 저장 작업</span><span><b id='registryPackageCount'>-</b> 설치 MCP</span><span><b id='registryCapabilityCount'>-</b> Capability</span></div></div><div class='studio-steps' id='studioSteps'><div class='studio-step current'><i>1</i><b>초안</b><span>목적·호출 문구</span></div><div class='studio-step'><i>2</i><b>자료</b><span>양식·PDF·지침</span></div><div class='studio-step'><i>3</i><b>검증</b><span>계약·권한 검사</span></div><div class='studio-step'><i>4</i><b>게시</b><span>서명 패키지</span></div><div class='studio-step'><i>5</i><b>설치</b><span>대화 자동 검색</span></div></div><div class='studio-type-head'><div><b>무엇을 만들까요?</b><span>유형을 선택하면 작성 항목과 안전 검사가 자동으로 바뀝니다.</span></div><small>빠른 예시를 불러온 뒤 문구만 바꿔도 됩니다.</small></div><div class='studio-type-grid'><button data-builder-type='template'><i>▤</i><b>양식 MCP</b><span>내 HWPX 양식으로 변환</span><small>완성본·빈칸·예시·작성요령 분석</small></button><button data-builder-type='process'><i>↳</i><b>처리 MCP</b><span>반복 절차를 자동 실행</span><small>단계 + 체크포인트 + 결과</small></button><button data-builder-type='data'><i>◫</i><b>데이터 MCP</b><span>PDF 자료를 RAG로 조회</span><small>여러 파일 + 페이지 근거 + 인용</small></button><button data-builder-type='tool'><i>✦</i><b>일반 도구 MCP</b><span>요약·변환·분석 기능</span><small>Prompt + 입력·출력 계약</small></button><button data-builder-type='external'><i>⇄</i><b>외부 MCP 연결</b><span>KODAK 등 공개 MCP 변환</span><small>stdio 프로필 또는 HTTP 매핑</small></button></div></section>");
    page.insertAdjacentHTML("beforeend","<section class='surface studio-runtime'><div class='surface-head'><div><h2>4. 설치된 MCP를 실제 요청으로 찾아보기</h2><small>Capability Registry · 활성 설치 버전만 검색</small></div><button class='inline-link' id='refreshRegistry'>Registry 새로고침</button></div><div class='registry-layout'><div><div class='registry-title'><b>대화에서 사용할 수 있는 MCP</b><span>게시만 한 MCP는 표시되지 않습니다. 설치 승인까지 완료해야 합니다.</span></div><div id='capabilityRegistryList' class='capability-registry-list'><div class='registry-empty'>Registry를 불러오는 중입니다.</div></div></div><div class='resolver-lab'><span class='eyebrow'>CALL TEST</span><h3>호출 문구를 입력해 보세요</h3><p>실행 전에 어떤 MCP와 버전이 선택되는지 확인합니다.</p><textarea id='resolverIntent' rows='3' placeholder='예: 회의 핵심과 후속 조치를 요약해줘'></textarea><div class='resolver-actions'><button id='resolveIntent'>MCP 찾기</button><button class='primary' id='runResolvedIntent' disabled>채팅에서 실행</button></div><div id='resolverResult' class='resolver-result'><div class='registry-empty'>호출 문구를 입력하면 선택 예정 MCP와 매칭 근거가 표시됩니다.</div></div></div></div></section>");
    $("mcpName").closest(".field").insertAdjacentHTML("beforebegin","<label class='field'><span>MCP 유형</span><select id='mcpType'><option value='template'>양식 MCP</option><option value='process'>처리 MCP</option><option value='data'>데이터 MCP</option><option value='tool'>일반 도구 MCP</option><option value='external'>외부 MCP 연결</option></select></label><div id='builderTypeGuide' class='builder-type-guide'></div>");
    $("mcpDescription").closest(".field").insertAdjacentHTML("afterend","<label class='field'><span>실행 지침·프롬프트</span><textarea id='mcpInstructions' rows='5' placeholder='이 MCP가 입력을 어떻게 해석하고 결과를 만들어야 하는지 작성하세요.'>사용자 요청과 입력 자료를 확인하고, 등록된 기준과 절차에 따라 결과를 생성한다.</textarea></label><div class='builder-guide-grid'><label class='field'><span>유의사항 · 한 줄에 하나</span><textarea id='mcpCautions' rows='4' placeholder='원문에 없는 수치는 추측하지 않는다.&#10;확정 전에는 결과를 제출하지 않는다.'></textarea></label><label class='field'><span>처리 순서 · 한 줄에 한 단계</span><textarea id='mcpProcedure' rows='4'></textarea></label></div><label class='field'><span>사용자가 부를 수 있는 요청 예시</span><textarea id='mcpTriggers' rows='3' placeholder='행안부 보고서 양식으로 바꿔줘&#10;이 자료를 등록된 절차대로 처리해줘'></textarea></label><label class='field' id='builderDataSourceField' hidden><span>데이터 출처·접속 방식</span><input id='mcpDataSource' placeholder='내부 예산 DB · 읽기 전용 API · 기준일 필수'></label><div class='toggle-row'><label><input type='checkbox' id='useModel'> 프롬프트 처리에 모델 사용</label></div>");
    $("builderDataSourceField").insertAdjacentHTML("afterend","<div id='builderExternalFields' class='external-mcp-fields' hidden><div class='builder-guide-grid'><label class='field'><span>전송 방식</span><select id='externalTransport'><option value='stdio'>로컬 stdio · 자동 실행 가능</option><option value='streamable-http'>Streamable HTTP · 실행 승인 필요</option></select></label><label class='field external-stdio-only'><span>승인된 서버 프로필</span><select id='externalServerProfile'><option value='kordoc@4.7.3'>KODAK · kordoc 4.7.3</option></select></label><label class='field external-http-only' hidden><span>서버 URL 환경변수</span><input id='externalEndpointEnv' value='AIWORKS_EXTERNAL_MCP_URL'></label><label class='field'><span>MCP 도구명</span><input id='externalToolName' value='generate_document'></label><label class='field'><span>AIWorks Capability</span><input id='externalCapability' value='document.hwpx.finalize'></label><label class='field external-stdio-only'><span>KODAK 문서 프리셋</span><select id='externalPreset'><option value='보고서'>보고서 · 1페이지 요약</option><option value='개조식'>개조식 · 정부 표준 보고서</option><option value='계획서'>계획서 · 추진계획</option><option value='기안문'>기안문 · 행정 공문</option></select></label><label class='field external-http-only' hidden><span>결과 HWPX base64 경로</span><input id='externalOutputContent' value='contentBase64'></label><label class='field external-http-only' hidden><span>결과 파일명 경로</span><input id='externalOutputFilename' value='filename'></label></div><div class='external-probe-row'><button id='probeExternalMcp' disabled>런타임·tools/list 테스트</button><span id='externalProbeStatus'>초안 생성 후 로컬 kordoc 설치 상태를 확인하세요.</span></div></div>");
    $("referenceList").insertAdjacentHTML("beforebegin","<label class='field reference-role-field'><span>첨부파일 역할</span><select id='referenceRole'></select></label>");
    $("referenceList").closest(".field").insertAdjacentHTML("afterend","<section id='builderTemplateLab' class='builder-template-lab'><div><b>일반 HWPX → 양식 MCP 원본</b><span id='templateAuthoringStatus'>먼저 양식 MCP 초안을 만들고 HWPX 원본을 첨부하세요.</span><small id='templateConversionSummary'>제목·본문·목록·표 구조를 분석해 재사용 가능한 양식 슬롯으로 바꿉니다.</small></div><div class='builder-template-actions'><button class='primary' id='convertDraftTemplate' disabled>일반 HWPX → 양식용 변환·반영</button><button id='correctDraftTemplate' disabled>슬롯 시각 보정</button><button id='verifyDraftTemplate' disabled>구조 실검증</button><button id='downloadDraftTemplateSample' disabled>변환본 미리 다운로드</button><button id='openTemplateAuthoring' disabled>RHWP에서 확인·수정</button></div></section>");
    $("runDraftRag").insertAdjacentHTML("afterend","<button class='primary' id='runDraftRagReport' disabled>편집 보고서 만들기</button>");
    $("builderRagLab").querySelector(".builder-rag-query").insertAdjacentHTML("beforebegin","<div class='rag-test-scenarios'><b>빠른 검증 시나리오</b><button data-rag-sample='행안부 25년, 26년 인공지능 공통기반 주요 지적사항을 확인해줘'>근거 조회</button><button data-rag-sample='행안부 인공지능 공통기반 예산관련 지적사항을 연도별로 정리해줘'>연도별 정리</button><button data-rag-sample='행안부 인공지능 공통기반 예산관련 지적사항을 연도별 보고서로 작성해줘'>보고서 작성</button></div>");
    document.querySelectorAll("[data-rag-sample]").forEach(function(button){button.onclick=function(){$("draftRagQuery").value=button.dataset.ragSample}});
    $("mcpType").onchange=function(){updateBuilderTypeUi(this.value,false)};
    $("externalTransport").onchange=updateExternalTransportUi;
    document.querySelectorAll("[data-builder-type]").forEach(function(card){card.onclick=function(){applyBuilderPreset(card.dataset.builderType)}});
    $("downloadTemplateStarter").onclick=async function(){try{setStatus("HWPX 시작 양식 생성 중");var starter=await api("/builder/template-starter");downloadBase64(starter.filename,starter.contentBase64);setStatus("HWPX 시작 양식 다운로드 완료");toast("한글에서 서식을 편집한 뒤 플레이스홀더를 유지해 양식 원본으로 첨부하세요.")}catch(error){toast(error.message)}};
    $("convertDraftTemplate").onclick=convertDraftTemplateSource;
    $("correctDraftTemplate").onclick=openTemplateMapping;
    $("applyTemplateMapping").onclick=applyTemplateMapping;
    $("verifyDraftTemplate").onclick=verifyDraftTemplateQuality;
    $("downloadDraftTemplateSample").onclick=downloadDraftTemplateSample;
    $("openTemplateAuthoring").onclick=openTemplateAuthoring;
    $("probeExternalMcp").onclick=async function(){if(!state.builderDraft)return toast("먼저 외부 MCP 초안을 만드세요.");var status=$("externalProbeStatus");status.textContent="MCP initialize와 tools/list를 확인하는 중...";try{var result=await api("/builder/drafts/"+state.builderDraft.id+"/external/probe",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});if(!result.connected){status.textContent=result.serverProfile?(result.serverProfile+" · "+(result.reason==="node-not-installed"?"Node.js 런타임 설치 필요":"고정 버전 kordoc 런타임 설치 필요")):(result.endpointEnv+" 미설정 · 서버 주소를 환경변수에 넣어 주세요.");return}status.textContent=(result.configuredToolFound?"연결 완료 · 도구 확인: ":"연결됨 · 설정 도구를 찾지 못함: ")+result.configuredToolName+" · 서버 도구 "+(result.tools||[]).length+"개";toast(result.configuredToolFound?"외부 MCP 계약 확인 완료":"tools/list에서 설정 도구명을 다시 확인하세요.")}catch(error){status.textContent=error.message;toast(error.message)}};
    $("newBuilderDraft").onclick=function(){state.builderDraft=null;state.builderResolution=null;renderBuilder();applyBuilderPreset("template",true);toast("새 MCP 작성 화면을 준비했습니다.")};
    $("refreshRegistry").onclick=loadCapabilityRegistry;$("resolveIntent").onclick=resolveBuilderIntent;
    $("managePublishedMcp").onclick=function(){var name=state.builderDraft&&state.builderDraft.manifest&&state.builderDraft.manifest.name||"";setView("store");setTimeout(function(){var input=$("storeSearch");if(input){input.value=name;renderStore(name)}},0)};
    $("resolverIntent").oninput=function(){state.builderResolution=null;$("runResolvedIntent").disabled=true};
    $("resolverIntent").onkeydown=function(event){if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();resolveBuilderIntent()}};
    $("runResolvedIntent").onclick=function(){var intent=$("resolverIntent").value.trim();if(!intent||!state.builderResolution||!state.builderResolution.items.length)return;setView("editor");$("chatInput").value=intent;submitIntent(intent)};
    $("runDraftRag").onclick=function(){queryDraftRag(false)};
    $("runDraftRagReport").onclick=function(){queryDraftRag(true)};
    $("draftRagQuery").onkeydown=function(event){if(event.key==="Enter"){event.preventDefault();queryDraftRag(false)}};
    updateBuilderTypeUi("template",false);
    $("generateManifest").onclick=async function(){
      try{
        setStatus("MCP 계약 생성 중");
        var visibility=document.querySelector("input[name='visibility']:checked").value;
        var draft=await api("/builder/drafts",{method:"POST",body:JSON.stringify({name:$("mcpName").value,package_id:$("mcpPackageId").value,version:$("mcpVersion").value,description:$("mcpDescription").value,mcp_type:$("mcpType").value,instructions:$("mcpInstructions").value,cautions:$("mcpCautions").value,procedure:$("mcpProcedure").value,trigger_examples:$("mcpTriggers").value,data_source:$("mcpDataSource").value,use_model:$("useModel").checked,visibility:visibility,source_included:$("sourceIncluded").checked,allow_external:$("allowExternal").checked,external_endpoint_env:$("externalEndpointEnv").value,external_server_profile:$("externalServerProfile").value,external_tool_name:$("externalToolName").value,external_capability:$("externalCapability").value,external_transport:$("externalTransport").value,external_preset:$("externalPreset").value,external_output_content:$("externalOutputContent").value,external_output_filename:$("externalOutputFilename").value,actor:"workspace-user"})});
        showBuilderDraft(draft);$("runSandbox").disabled=false;setStatus("MCP 초안 저장됨");toast(draft.identityAdjustment?"기존 MCP와 ID가 겹쳐 "+draft.identityAdjustment.packageId+"로 자동 변경했습니다.":"서버에 Manifest와 입출력 Schema 초안을 저장했습니다.");addAudit("MCP 제작기","초안 생성 · "+draft.manifest.id,"완료");
      }catch(error){setStatus("MCP 초안 생성 실패");toast(error.message)}
    };
    $("runSandbox").onclick=async function(){
      if(!state.builderDraft)return toast("먼저 Manifest를 생성하세요.");
      try{
        setStatus("샌드박스 계약 테스트 실행 중");$("testList").innerHTML="<div><i>◌</i> 계약, 고정 의존성, 최소권한과 전송 경계를 검사 중...</div>";
        var draft=await api("/builder/drafts/"+state.builderDraft.id+"/validate",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});
        showBuilderDraft(draft);setStatus(draft.validation.passed?"검증 통과 · 게시·설치 필요":"샌드박스 검증 실패");toast(draft.validation.passed?"검증을 통과했습니다. 대화에서 사용하려면 ‘게시하고 대화 검색 활성화’를 눌러 설치까지 완료하세요.":"검증 실패 항목을 확인하세요.");addAudit("Sandbox","MCP 계약 테스트 "+draft.validation.tests.filter(function(item){return item.passed}).length+"/"+draft.validation.tests.length,draft.validation.passed?"완료":"차단");
      }catch(error){setStatus("샌드박스 검증 실패");toast(error.message)}
    };
    $("publishMcp").onclick=async function(){
      var draft=state.builderDraft;if(!draft||draft.status!=="validated")return;
      try{
        setStatus("MCP 패키지 서명·게시 중");
        var result=await api("/builder/drafts/"+draft.id+"/publish",{method:"POST",body:JSON.stringify({actor:"workspace-user",confirm_visibility:draft.manifest.visibility,confirm_source_included:draft.manifest.sourceIncluded})});
        showBuilderDraft(result.draft);await syncStore(false);setStatus("게시 완료 · 설치 승인 대기");addAudit("MCP 제작기","스토어 게시 · "+result.package.packageId+"@"+result.package.version,"완료");
        var manifest=result.package.manifest,item={id:result.package.packageId,name:manifest.name,version:result.package.version,targetVersion:result.package.version,publisher:result.package.publisher||"workspace-user",permissions:(manifest.permissions||[]).map(function(permission){return permission.scope}),runtime:manifest.runtime};
        state.pendingStoreAction="install";state.pendingIntent=manifest.name+" v"+result.package.version+"을 설치해 대화 자동 검색 활성화";showApproval(state.pendingIntent,true,item);toast(result.identityAdjustment?"ID 충돌을 "+result.identityAdjustment.packageId+"로 자동 해결해 게시했습니다. 권한을 확인하고 설치해 주세요.":"게시했습니다. 권한을 확인하고 설치하면 이 화면에서 바로 호출 테스트할 수 있습니다.");
      }catch(error){setStatus("MCP 게시 실패");toast(error.message)}
    };
    $("attachReference").onclick=function(){if(!state.builderDraft||state.builderDraft.status==="published")return toast("먼저 새 초안을 생성하세요.");var single=$("mcpType").value==="template"&&$("referenceRole").value==="template-source";$("referenceFile").toggleAttribute("multiple",!single);$("referenceFile").click()};
    $("referenceFile").onchange=async function(){var files=Array.from(this.files||[]);if(!files.length)return;try{var role=$("referenceRole").value,lastResult=null,isTemplate=$("mcpType").value==="template"&&role==="template-source";if(isTemplate&&files.length!==1)throw new Error("양식 기준 HWPX는 한 번에 하나만 선택해 주세요.");for(var index=0;index<files.length;index++){var file=files[index];setStatus((index+1)+"/"+files.length+(isTemplate?" · HWPX 양식 구조 분석 중":" · 텍스트 추출·RAG 청크 생성 중"));lastResult=await api("/builder/drafts/"+state.builderDraft.id+"/references",{method:"POST",body:JSON.stringify({filename:file.name,role:role,content_base64:await fileBase64(file),actor:"workspace-user"})});showBuilderDraft(lastResult.draft)}await loadBuilderDrafts();setStatus(isTemplate?"기존 기준 파일 교체 완료 · 양식용 변환을 실행하세요.":files.length+"개 자료 RAG 준비 완료");toast(isTemplate?"HWPX 기준 파일을 하나로 교체했습니다. ‘양식용 변환·반영’을 눌러 주세요.":files.length+"개 파일을 "+role+" 역할로 연결했습니다.")}catch(error){setStatus("자료 첨부 실패");toast(error.message)}finally{this.value=""}};
    if(state.builderDraft)showBuilderDraft(state.builderDraft);else applyBuilderPreset("template",true);
    loadBuilderDrafts();loadCapabilityRegistry();updateBuilderStudioProgress();
  }

  function renderStore(filter){
    var term=String(filter||"").toLowerCase();
    var list=state.mcps.filter(function(item){return !term||item.name.toLowerCase().indexOf(term)>=0||item.id.toLowerCase().indexOf(term)>=0||item.publisher.toLowerCase().indexOf(term)>=0||item.desc.toLowerCase().indexOf(term)>=0});
    var cards=list.map(function(item){
      var installed=Boolean(item.installedVersion);var update=installed&&item.installedVersion!==item.version;
      var action=update?"<button data-install='"+escapeHtml(item.id)+"'>v"+escapeHtml(item.version)+" 업데이트</button>":(!installed?"<button data-install='"+escapeHtml(item.id)+"'>권한 확인 후 설치</button>":(item.rollbackVersion?"<button data-rollback='"+escapeHtml(item.id)+"'>v"+escapeHtml(item.rollbackVersion)+" 롤백</button>":"<button class='installed' disabled>v"+escapeHtml(item.installedVersion)+" 고정</button>"));
      var configure=item.configurable&&installed?"<button class='store-configure' data-configure='"+escapeHtml(item.id)+"'>환경설정</button>":"";
      var manage=configure+"<button class='store-edit' data-edit='"+escapeHtml(item.id)+"'>수정</button>"+(item.deletable?"<button class='store-delete' data-delete='"+escapeHtml(item.id)+"'>삭제</button>":"");
      return "<article class='store-card'><div class='store-card-head'><span class='mcp-logo'>⌘</span><div><h3>"+escapeHtml(item.name)+"</h3><div class='store-meta'><span>"+escapeHtml(item.id)+"@"+escapeHtml(item.version)+"</span><span>"+escapeHtml(item.publisher)+"</span><span>✓ 서명 · 취약점 0</span></div></div></div><p>"+escapeHtml(item.desc)+"</p><div>"+item.permissions.map(function(p){return "<span class='permission-chip'>"+escapeHtml(p)+"</span> "}).join("")+"</div><footer><span class='type-chip'>"+escapeHtml(item.runtime)+(installed?" · 설치 v"+escapeHtml(item.installedVersion):"")+"</span><div class='store-card-actions'>"+manage+action+"</div></footer></article>";
    }).join("");
    var quarantine=state.quarantined.length?"<div class='quarantine-warning'><b>검증 실패 패키지 "+state.quarantined.length+"개 격리</b><span>"+state.quarantined.map(function(item){return escapeHtml(item.packageId+"@"+item.version)}).join(", ")+"</span></div>":"";
    $("storeView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Signed MCP Marketplace</span><h1>조직 MCP 스토어</h1><p>조직 서명과 패키지 해시를 검증하고 승인된 권한으로 정확한 버전을 고정 설치합니다.</p></div><div class='module-actions'><button data-view-jump='builder'>내 MCP 만들기</button></div></div>"+quarantine+"<div class='store-toolbar'><input class='store-search' id='storeSearch' placeholder='MCP 이름, ID, 업무 또는 게시자 검색' value='"+escapeHtml(filter||"")+"'><button class='filter-button' id='refreshStore'>서명 다시 검증</button></div><div class='store-grid'>"+(cards||"<div class='registry-empty'>검색 조건에 맞는 MCP가 없습니다.</div>")+"</div></div>";
    $("storeSearch").oninput=function(){renderStore(this.value);var input=$("storeSearch");input.focus();input.setSelectionRange(input.value.length,input.value.length)};
    document.querySelector("[data-view-jump]") .onclick=function(){setView("builder")};
    $("refreshStore").onclick=function(){syncStore(true)};
    document.querySelectorAll("[data-install]").forEach(function(button){button.onclick=function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.install});state.pendingStoreAction="install";item.targetVersion=item.version;state.pendingIntent=item.name+" v"+item.targetVersion+"을 서명 검증 후 고정 설치";showApproval(state.pendingIntent,true,item)}});
    document.querySelectorAll("[data-rollback]").forEach(function(button){button.onclick=function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.rollback});state.pendingStoreAction="rollback";item.targetVersion=item.rollbackVersion;state.pendingIntent=item.name+"을 검증된 v"+item.targetVersion+"으로 롤백";showApproval(state.pendingIntent,true,item)}});
    document.querySelectorAll("[data-configure]").forEach(function(button){button.onclick=function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.configure});if(item)openMcpConfiguration(item)}});
    document.querySelectorAll("[data-edit]").forEach(function(button){button.onclick=async function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.edit});try{setStatus(item.name+" 편집 초안 준비 중");var result=await api("/store/edit",{method:"POST",body:JSON.stringify({package_id:item.id,version:item.version,actor:"workspace-user"})});state.builderDraft=result.draft;setView("builder");toast("서명된 v"+item.version+"을 보존하고 v"+result.draft.manifest.version+" 편집 초안을 만들었습니다.")}catch(error){toast(error.message)}}});
    document.querySelectorAll("[data-delete]").forEach(function(button){button.onclick=async function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.delete}),ref=item.id+"@"+item.version;if(!window.confirm(ref+" 버전을 스토어에서 삭제할까요?\nBuilder 초안은 복구·재게시할 수 있도록 남겨둡니다."))return;try{await api("/store/delete",{method:"POST",body:JSON.stringify({package_id:item.id,version:item.version,confirm_package_ref:ref,actor:"workspace-user"})});await syncStore(false);renderStore();toast(ref+" 삭제 완료 · 제작 초안은 유지했습니다.")}catch(error){toast(error.message)}}});
  }

  function configurationFieldHtml(key,field,value){
    var title=field.title||key;
    var description=field.description?"<small>"+escapeHtml(field.description)+"</small>":"";
    if(Array.isArray(field.enum)){
      var labels=field.enumLabels||{};
      var selected=field.enum.findIndex(function(option){return option===value});
      if(selected<0)selected=0;
      return "<label class='field mcp-config-field'><span>"+escapeHtml(title)+"</span><select data-config-key='"+escapeHtml(key)+"'>"+field.enum.map(function(option,index){return "<option value='"+index+"' "+(index===selected?"selected":"")+">"+escapeHtml(labels[String(option)]||String(option))+"</option>"}).join("")+"</select>"+description+"</label>";
    }
    if(field.type==="boolean")return "<label class='mcp-config-toggle'><input type='checkbox' data-config-key='"+escapeHtml(key)+"' "+(value?"checked":"")+"><span><b>"+escapeHtml(title)+"</b>"+description+"</span></label>";
    var inputType=field.type==="integer"||field.type==="number"?"number":"text";
    return "<label class='field mcp-config-field'><span>"+escapeHtml(title)+"</span><input type='"+inputType+"' step='"+(field.type==="integer"?"1":"any")+"' data-config-key='"+escapeHtml(key)+"' value='"+escapeHtml(value==null?"":value)+"'>"+description+"</label>";
  }

  async function openMcpConfiguration(item){
    try{
      setStatus(item.name+" 환경설정 불러오는 중");
      var data=await api("/store/configuration/get",{method:"POST",body:JSON.stringify({package_id:item.id})});
      state.mcpConfiguration=data;
      var dialog=$("mcpConfigurationDialog");
      if(!dialog){dialog=document.createElement("dialog");dialog.id="mcpConfigurationDialog";document.body.appendChild(dialog)}
      var properties=data.schema&&data.schema.properties||{};
      dialog.innerHTML="<form method='dialog' class='approval-card mcp-config-card'><header><div><h2>"+escapeHtml(data.name)+" 환경설정</h2><small>"+escapeHtml(data.packageId)+" · 설정 버전 "+escapeHtml(data.schema.version||"1.0")+"</small></div><button value='cancel' aria-label='닫기'>×</button></header><div class='mcp-config-body'>"+Object.keys(properties).map(function(key){return configurationFieldHtml(key,properties[key],data.values[key])}).join("")+"</div><footer><button value='cancel'>취소</button><button type='button' class='primary' id='saveMcpConfiguration'>저장</button></footer></form>";
      dialog.querySelector("#saveMcpConfiguration").onclick=async function(){
        var values={};
        dialog.querySelectorAll("[data-config-key]").forEach(function(node){var key=node.dataset.configKey;var field=properties[key]||{};if(Array.isArray(field.enum))values[key]=field.enum[Number(node.value)];else if(field.type==="boolean")values[key]=node.checked;else if(field.type==="integer")values[key]=Number.parseInt(node.value,10);else if(field.type==="number")values[key]=Number(node.value);else values[key]=node.value});
        try{var saved=await api("/store/configuration/save",{method:"POST",body:JSON.stringify({package_id:data.packageId,values:values,base_revision:data.revision})});dialog.close();await syncStore(false);renderStore();toast(saved.name+" 환경설정을 저장했습니다.");setStatus("MCP 환경설정 저장 완료")}catch(error){toast(error.message)}
      };
      dialog.showModal();setStatus(item.name+" 환경설정");
    }catch(error){toast(error.message);setStatus("MCP 환경설정을 불러오지 못했습니다")}
  }

  async function syncStore(notify){
    try{
      var data=await api("/store/packages");
      state.quarantined=data.quarantined||[];
      state.mcps=(data.items||[]).map(function(item){return{id:item.packageId,name:item.name,version:item.versions[0].version,versions:item.versions,installedVersion:item.installedVersion,rollbackVersion:item.rollbackVersion,runtime:item.runtime,desc:item.description,permissions:item.permissions,rating:"서명됨",publisher:item.publisher,editable:item.editable!==false,deletable:Boolean(item.deletable),configurable:Boolean(item.configurable),configuration:item.configuration||null,configurationRevision:Number(item.configurationRevision||0),configurationUpdatedAt:item.configurationUpdatedAt||null}});
      state.installed=state.mcps.filter(function(item){return item.installedVersion}).map(function(item){return item.id});
      if(state.activeView==="store")renderStore();
      if(notify)toast(state.quarantined.length?"검증 실패 패키지를 격리했습니다.":"조직 서명과 패키지 해시를 다시 검증했습니다.");
    }catch(error){if(notify)toast(error.message)}
  }

  function renderAudit(){
    var rows=state.audit.map(function(item){return "<div class='audit-row'><time>"+escapeHtml(item.time)+"</time><span>"+escapeHtml(item.actor)+"</span><strong>"+escapeHtml(item.event)+"</strong><span class='audit-status "+(item.status==="차단"?"denied":"")+"'>"+escapeHtml(item.status)+"</span></div>"}).join("");
    $("auditView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Operations & Acceptance</span><h1>운영 상태와 실행 이력</h1><p>저장소·서명·모델·어댑터 준비상태와 예산요청서 전체 승인 시나리오를 검증합니다.</p></div><div class='module-actions'><button id='undoChange'>마지막 변경 되돌리기</button><button class='primary' id='runAcceptance'>E2E 실행</button></div></div><div class='cards'><div class='metric-card'><span>운영 준비상태</span><b id='readinessStatus'>확인 중</b><small id='readinessSummary'>핵심 경계 검사</small></div><div class='metric-card'><span>최근 수용성 테스트</span><b id='acceptanceStatus'>-</b><small id='acceptanceTime'>실행 이력 없음</small></div><div class='metric-card'><span>감사 이벤트</span><b>"+state.audit.length+"</b><small>실행 ID 추적</small></div></div><section class='surface'><div class='surface-head'><h2>운영 진단</h2><button class='inline-link' id='refreshReadiness'>다시 점검</button></div><div class='operation-checks' id='operationChecks'>진단을 불러오는 중입니다.</div></section><section class='surface'><div class='surface-head'><h2>예산요청서 E2E 수용성 테스트</h2><button class='inline-link danger-link' id='runFailureAcceptance'>stale-document 실패 검증</button></div><div class='acceptance-result' id='acceptanceResult'>문서 분석 → 실행계획 → 승인 → 변경안 → HWPX 산출물 → 감사 로그를 로컬 합성 실행으로 검증합니다.</div></section><section class='surface'><div class='surface-head'><h2>감사 이벤트</h2><small>영속 저장 · 실행 ID 기준</small></div><div class='audit-list'>"+rows+"</div></section></div>";
    $("undoChange").onclick=undoChange;
    $("refreshReadiness").onclick=loadOperationalStatus;
    $("runAcceptance").onclick=function(){runAcceptanceScenario("none")};
    $("runFailureAcceptance").onclick=function(){runAcceptanceScenario("stale-document")};
    loadOperationalStatus();if(state.latestAcceptance)renderAcceptanceReport(state.latestAcceptance);
  }

  function renderAcceptanceReport(report){
    if(!$("acceptanceResult")||!report)return;
    $("acceptanceResult").innerHTML="<strong class='"+(report.status==="passed"?"pass":"fail")+"'>"+escapeHtml(report.status.toUpperCase())+"</strong><span>"+escapeHtml(report.id)+"</span>"+report.checks.map(function(check){return"<div class='"+(check.passed?"pass":"fail")+"'><i>"+(check.passed?"✓":"×")+"</i><b>"+escapeHtml(check.id)+"</b><span>"+escapeHtml(check.detail)+"</span></div>"}).join("")+(report.error?"<p>"+escapeHtml(report.error)+"</p>":"");
  }

  async function loadOperationalStatus(){
    try{
      var results=await Promise.all([api("/operations/readiness"),api("/acceptance/runs")]);var readiness=results[0];var runs=results[1].items||[];
      $("readinessStatus").textContent=readiness.ready?"READY":"NOT READY";$("readinessSummary").textContent="통과 "+readiness.summary.passed+" · 경고 "+readiness.summary.warnings+" · 실패 "+readiness.summary.failed;
      $("operationChecks").innerHTML=readiness.checks.map(function(check){return"<div class='operation-check "+escapeHtml(check.status)+"'><i>"+(check.status==="pass"?"✓":check.status==="warn"?"!":"×")+"</i><b>"+escapeHtml(check.id)+"</b><span>"+escapeHtml(check.detail)+"</span></div>"}).join("");
      if(runs.length){$("acceptanceStatus").textContent=runs[0].status.toUpperCase();$("acceptanceTime").textContent=new Date(runs[0].completedAt).toLocaleString("ko-KR");if(!state.latestAcceptance){state.latestAcceptance=runs[0];renderAcceptanceReport(runs[0])}}
    }catch(error){$("readinessStatus").textContent="ERROR";$("operationChecks").textContent=error.message}
  }

  async function runAcceptanceScenario(injection){
    var button=injection==="none"?$("runAcceptance"):$("runFailureAcceptance");button.disabled=true;setStatus("예산요청서 E2E 수용성 테스트 실행 중");
    try{var report=await api("/acceptance/budget-request",{method:"POST",body:JSON.stringify({actor:"demo-user",inject_failure:injection})});state.latestAcceptance=report;renderAcceptanceReport(report);setStatus("E2E "+report.status);toast(injection==="none"?"전체 승인 시나리오 검증 완료":"원본 변경 충돌 차단 검증 완료");await syncServerAudit()}catch(error){toast(error.message);setStatus("E2E 실행 실패")}finally{button.disabled=false}
  }



  async function loadProjectGovernance(){
    var host=$("projectGovernance");
    if(!host||!state.activeProjectId)return;
    host.innerHTML="<p class='empty-reference'>프로젝트 정책과 권한을 불러오는 중입니다.</p>";
    try{
      var data=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/governance"),policy=data.policy&&data.policy.policy||{},resolver=policy.resolver||{};
      host.innerHTML="<div class='governance-summary'><span><small>현재 역할</small><b>"+escapeHtml(data.currentRole||"-")+"</b></span><span><small>보안 등급</small><b>"+escapeHtml(data.project.classification)+"</b></span><span><small>정책 revision</small><b>"+Number(data.policy&&data.policy.revision||0)+"</b></span><span><small>Grant</small><b>"+(data.grants||[]).filter(function(item){return item.status==="active"}).length+"</b></span></div><div class='surface-head'><h3>프로젝트 구성원</h3><button id='addProjectMember'>구성원 추가</button></div><div class='governance-list'>"+(data.members||[]).map(function(item){return"<div><span><b>"+escapeHtml(item.actor)+"</b><small>"+escapeHtml(item.role)+" · "+escapeHtml(item.status)+"</small></span>"+(item.role!=="owner"&&item.status==="active"?"<button data-revoke-member='"+escapeHtml(item.actor)+"'>해제</button>":"")+"</div>"}).join("")+"</div><div class='surface-head'><h3>MCP Permission Grant</h3><button id='addProjectGrant'>Grant 추가</button></div><div class='governance-list'>"+((data.grants||[]).map(function(item){return"<div><span><b>"+escapeHtml(item.packageId)+"</b><small>"+escapeHtml(item.actor)+" · "+escapeHtml((item.scopes||[]).join(", "))+" · "+escapeHtml(item.status)+"</small></span></div>"}).join("")||"<p class='empty-reference'>프로젝트 1회 승인 Grant가 없습니다.</p>")+"</div><div class='governance-policy'><small>Resolver 가중치</small><code>의도 "+Number(resolver.intentWeight||0)+" · 품질 "+Number(resolver.qualityWeight||0)+" · 비용 "+Number(resolver.costWeight||0)+" · 지연 "+Number(resolver.latencyWeight||0)+"</code><button id='editResolverPreference'>선호 MCP 설정</button><button class='danger-link' id='archiveActiveProject'>프로젝트 보관</button></div>";
      $("editResolverPreference").insertAdjacentHTML("afterend","<button id='downloadProjectBackup'>프로젝트 백업</button>");
      $("addProjectMember").onclick=async function(){var member=window.prompt("추가할 사용자 ID를 입력하세요.");if(!member)return;var role=window.prompt("역할을 입력하세요: viewer / editor / admin","editor");if(!role)return;try{await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/members",{method:"POST",body:JSON.stringify({member_actor:member,role:role,status:"active",actor:"workspace-user"})});toast("프로젝트 구성원을 추가했습니다.");loadProjectGovernance()}catch(error){toast(error.message)}};
      host.querySelectorAll("[data-revoke-member]").forEach(function(button){button.onclick=async function(){if(!window.confirm(button.dataset.revokeMember+" 사용자의 프로젝트 접근을 해제할까요?"))return;try{await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/members",{method:"POST",body:JSON.stringify({member_actor:button.dataset.revokeMember,role:"viewer",status:"revoked",actor:"workspace-user"})});loadProjectGovernance()}catch(error){toast(error.message)}}});
      $("addProjectGrant").onclick=async function(){var packageId=window.prompt("Grant를 부여할 MCP package ID를 입력하세요.");if(!packageId)return;var scopes=window.prompt("허용할 권한을 쉼표로 입력하세요.","document.read,data.read");if(!scopes)return;try{await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/grants",{method:"POST",body:JSON.stringify({package_id:packageId,member_actor:"workspace-user",version_range:"*",scopes:scopes.split(",").map(function(item){return item.trim()}).filter(Boolean),classification:data.project.classification,status:"active",actor:"workspace-user"})});toast("프로젝트 Grant를 저장했습니다.");loadProjectGovernance()}catch(error){toast(error.message)}};
      $("editResolverPreference").onclick=async function(){var preferred=window.prompt("우선 사용할 MCP package ID를 쉼표로 입력하세요.",(resolver.preferredPackages||[]).join(","));if(preferred===null)return;var next=Object.assign({},policy,{resolver:Object.assign({},resolver,{preferredPackages:preferred.split(",").map(function(item){return item.trim()}).filter(Boolean)})});try{await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/policy",{method:"POST",body:JSON.stringify({policy:next,expected_revision:data.policy.revision,actor:"workspace-user"})});toast("프로젝트 Resolver 선호를 저장했습니다.");loadProjectGovernance()}catch(error){toast(error.message)}};
      $("downloadProjectBackup").onclick=downloadProjectBackup;
      $("archiveActiveProject").onclick=async function(){if(!window.confirm("현재 프로젝트를 보관할까요? 문서와 산출물은 삭제되지 않습니다."))return;try{await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/status",{method:"POST",body:JSON.stringify({action:"archive",actor:"workspace-user"})});state.activeProjectId=null;state.activeProject=null;await loadProjects();showProjectGate();toast("프로젝트를 비파괴적으로 보관했습니다.")}catch(error){toast(error.message)}};
    }catch(error){host.innerHTML="<p class='empty-reference'>"+escapeHtml(error.message)+"</p>"}
  }

  async function loadWorkflowRecipes(query){
    var host=$("workflowRecipeLibrary");if(!host)return;
    if(!state.activeProjectId){host.innerHTML="<p class='empty-reference'>프로젝트를 선택하면 Recipe를 설치할 수 있습니다.</p>";return}
    host.innerHTML="<p class='empty-reference'>공유 Recipe와 설치 상태를 불러오는 중입니다.</p>";
    try{
      var data=query?await api("/recipes/search",{method:"POST",body:JSON.stringify({project_id:state.activeProjectId,q:query,actor:"workspace-user"})}):await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/recipes");
      host.innerHTML=(data.items||[]).map(function(recipe){
        var latest=(recipe.versions||[])[0]||{},installed=recipe.installed&&recipe.installed.status==="active",preview=recipe.preview||{},risks=preview.riskFlags||[],tags=preview.tags||[],permissions=preview.permissions||[];
        var previewHtml="<div class='recipe-preview'>"+tags.map(function(item){return"<span>#"+escapeHtml(item)+"</span>"}).join("")+"<span>권한 "+permissions.length+"</span><span>비용 "+Number(preview.estimatedCost||0)+"</span><span>예상 "+Number(preview.estimatedLatencyMs||0)+"ms</span>"+risks.map(function(item){return"<span class='risk'>"+escapeHtml(item)+"</span>"}).join("")+"</div>";
        return"<article class='recipe-card'><div><span class='type-chip'>"+escapeHtml(recipe.visibility)+"</span><h3>"+escapeHtml(recipe.name)+"</h3><p>"+escapeHtml(recipe.description||"설명 없음")+"</p><small>"+escapeHtml(recipe.id)+" @ "+escapeHtml(latest.version||"-")+" · "+(latest.definition&&latest.definition.steps||[]).length+"단계 · "+escapeHtml(preview.license||"UNSPECIFIED")+"</small>"+previewHtml+"</div><footer><button data-fork-recipe='"+escapeHtml(recipe.id)+"'>포크</button>"+(recipe.owner==="workspace-user"?"<button data-deprecate-recipe='"+escapeHtml(recipe.id)+"'>폐기</button>":"")+"<button class='primary' data-install-recipe='"+escapeHtml(recipe.id)+"' data-risks='"+escapeHtml(risks.join(","))+"' "+(installed||risks.indexOf("security-blocked")>=0?"disabled":"")+">"+(installed?"설치됨":risks.indexOf("security-blocked")>=0?"보안 차단":"프로젝트 설치")+"</button></footer></article>";
      }).join("")||"<p class='empty-reference'>검색 조건에 맞는 Recipe가 없습니다.</p>";
      host.querySelectorAll("[data-install-recipe]").forEach(function(button){button.onclick=async function(){var risks=button.dataset.risks?button.dataset.risks.split(",").filter(Boolean):[];if(risks.length&&!window.confirm("위험 플래그: "+risks.join(", ")+"\n권한·외부 전송 범위를 확인하고 설치할까요?"))return;try{await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/recipes/"+encodeURIComponent(button.dataset.installRecipe)+"/install",{method:"POST",body:JSON.stringify({actor:"workspace-user",acknowledge_risks:true})});toast("Recipe를 현재 프로젝트에 설치했습니다.");loadWorkflowRecipes(query)}catch(error){toast(error.message)}}});
      host.querySelectorAll("[data-fork-recipe]").forEach(function(button){button.onclick=async function(){var target=window.prompt("새 Recipe ID를 입력하세요.",button.dataset.forkRecipe+"-custom");if(!target)return;try{await api("/recipes/"+encodeURIComponent(button.dataset.forkRecipe)+"/fork",{method:"POST",body:JSON.stringify({id:target,name:"사용자 정의 Recipe",visibility:"private",actor:"workspace-user"})});toast("Recipe를 개인 사본으로 포크했습니다.");loadWorkflowRecipes(query)}catch(error){toast(error.message)}}});
      host.querySelectorAll("[data-deprecate-recipe]").forEach(function(button){button.onclick=async function(){if(!window.confirm("이 Recipe를 폐기할까요? 기존 실행 기록은 유지됩니다."))return;try{await api("/recipes/"+encodeURIComponent(button.dataset.deprecateRecipe)+"/deprecate",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});loadWorkflowRecipes(query)}catch(error){toast(error.message)}}});
    }catch(error){host.innerHTML="<p class='empty-reference'>"+escapeHtml(error.message)+"</p>"}
  }

  function renderSettings(){
    var models=(state.models||[]).map(function(model){return"<article class='store-card'><div class='store-card-head'><span class='mcp-logo'>AI</span><div><h3>"+escapeHtml(model.label)+"</h3><div class='store-meta'><span>"+escapeHtml(model.personality)+"</span><span>입력 $"+Number(model.price.input)+"/M</span><span>출력 $"+Number(model.price.output)+"/M</span></div></div></div><p>"+escapeHtml(model.description)+"</p><div>"+model.strengths.slice(0,3).map(function(item){return"<span class='permission-chip'>"+escapeHtml(item)+"</span> "}).join("")+"</div><footer><span class='type-chip'>"+(model.default?"빠른 기본":model.freeOnly?"무료 대체":"대체 모델")+"</span><small>"+Number(model.contextTokens).toLocaleString()+" context</small></footer></article>"}).join("");
    var presetCards=(state.presets||[]).map(function(preset){return"<article class='store-card'><div class='store-card-head'><span class='mcp-logo'>"+escapeHtml(preset.modality.slice(0,2).toUpperCase())+"</span><div><h3>"+escapeHtml(preset.name)+"</h3><div class='store-meta'><span>"+escapeHtml(preset.modality)+"</span><span>"+(preset.status==="ready"?"실행 준비":"계약 미리보기")+"</span></div></div></div><p>"+escapeHtml(preset.description)+"</p><div>"+preset.acceptedFormats.map(function(format){return"<span class='permission-chip'>"+escapeHtml(format)+"</span> "}).join("")+"</div><footer><span class='type-chip'>"+escapeHtml(preset.status)+"</span><button data-workflow='"+escapeHtml(preset.id)+"'>계획 확인</button></footer></article>"}).join("");
    $("settingsView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Model & Workflow Management</span><h1>모델 관리와 업무 프리셋</h1><p>의도와 파일 형식에 따라 무료 모델과 최소권한 어댑터 실행 순서를 선택합니다.</p></div><div class='module-actions'><button class='primary' id='saveSettings'>설정 저장</button></div></div><div class='store-grid'>"+models+"</div><section class='surface routing-lab'><div class='surface-head'><h2>의도별 자동 전환 테스트</h2><small>"+(state.openrouter.configured?"API Key 연결됨":"API Key 미설정 · 선택만 검증")+"</small></div><div class='toggle-row'><label><input type='checkbox' id='liveRouteTest' "+(state.openrouter.configured?"":"disabled")+"> OpenRouter 실제 무료 호출 포함</label><label><input type='checkbox' checked disabled> :free 외 모델 차단</label></div><div class='route-test-actions'><button data-route-intent='선택 문장을 2줄 공문체로 다듬어줘'>문서 작성 의도 테스트</button><button data-route-intent='최신 기준과 비교해 예산 산출 근거를 검증해줘'>복합 추론 의도 테스트</button></div><pre class='code-preview route-result' id='routeResult'>테스트를 선택하면 의도 유형, 선택 모델과 선택 근거가 표시됩니다.</pre></section><section class='surface workflow-lab'><div class='surface-head'><h2>멀티모달 업무 프리셋</h2><div><input id='assetInspectorInput' type='file' accept='.py,.js,.ts,.json,.md,.png,.jpg,.jpeg,.wav,.mp4' hidden><button class='inline-link' id='inspectAssetButton'>파일 로컬 검사</button></div></div><div class='store-grid'>"+presetCards+"</div><pre class='code-preview workflow-result' id='workflowResult'>프리셋 계획 또는 로컬 파일 검사 결과가 표시됩니다.</pre></section><section class='surface'><div class='surface-head'><h2>데이터·권한 정책</h2><small>기본 거부</small></div><div class='toggle-row'><label><input type='checkbox' checked> 개인정보 자동 마스킹</label><label><input type='checkbox' checked> 외부 전송 매회 승인</label><label><input type='checkbox' checked> 실행 감사 로그</label></div></section></div>";
    $("settingsView").querySelector(".module-hero p").textContent="조회는 Solar Pro 3 Fast, 문서·RAG는 Solar Pro 3, 복합 검증은 Solar Pro 4로 자동 전환합니다.";
    $("settingsView").querySelector(".routing-lab .surface-head small").textContent=state.openrouter.liveExecutionEnabled?"Solar 실호출 활성":"Solar 선택 검증 · 외부 전송 대기";
    $("settingsView").querySelector(".routing-lab .toggle-row").innerHTML="<label><input type='checkbox' id='liveRouteTest' "+(state.openrouter.liveExecutionEnabled?"":"disabled")+"> 승인된 Solar 실호출 포함</label><label><input type='checkbox' checked disabled> Fast / Pro 3 / Pro 4 자동 선택</label>";
    $("settingsView").querySelector(".module-page").insertAdjacentHTML("beforeend","<section class='surface'><div class='surface-head'><h2>RHWP 전체 기능 MCP</h2><small id='rhwpRuntimeStatus'>브리지 확인 중</small></div><p class='empty-reference'>HAction/HParameterSet을 포함한 한글 자동화 기능은 문서 읽기·쓰기 승인 후 같은 사용자 Windows 브리지에서 실행됩니다.</p><div class='toggle-row' id='rhwpToolCatalog'>도구 목록을 불러오는 중입니다.</div></section>");
    $("settingsView").querySelector(".module-page").insertAdjacentHTML("beforeend","<section class='surface project-governance-panel'><div class='surface-head'><h2>프로젝트 거버넌스</h2><small>멤버십 · Grant · Resolver · 비파괴 보관</small></div><div id='projectGovernance'></div></section>");
    $("settingsView").querySelector(".module-page").insertAdjacentHTML("beforeend","<section class='surface recipe-library-panel'><div class='surface-head'><h2>업무 Recipe Library</h2><div class='recipe-search'><input id='recipeSearchInput' placeholder='이름·태그·ID 검색'><button id='searchWorkflowRecipes'>검색</button><button id='createSampleRecipe'>새 Recipe</button></div></div><p class='empty-reference'>설치 전에 권한·비용·지연·라이선스·보안 상태를 확인합니다.</p><div id='workflowRecipeLibrary' class='recipe-library'></div></section>");
    loadProjectGovernance();
    loadWorkflowRecipes();
    $("searchWorkflowRecipes").onclick=function(){loadWorkflowRecipes($("recipeSearchInput").value.trim())};
    $("recipeSearchInput").onkeydown=function(event){if(event.key==="Enter"){event.preventDefault();loadWorkflowRecipes(this.value.trim())}};
    $("createSampleRecipe").onclick=async function(){var recipeId=window.prompt("Recipe ID를 입력하세요.","workspace.report-flow");if(!recipeId)return;var name=window.prompt("Recipe 이름을 입력하세요.","근거 기반 보고서 흐름");if(!name)return;var definition={description:"데이터 조회부터 Markdown·HWPX 생성까지",inputArtifactTypes:["document.markdown"],outputArtifactTypes:["document.hwpx"],steps:[{id:"query",name:"근거 조회",capability:"data.query",permissions:["data.read"]},{id:"draft",name:"보고서 초안",capability:"document.generate",permissions:["document.write"],outputArtifactType:"document.markdown"},{id:"format",name:"양식 적용",capability:"document.hwpx.render",permissions:["document.read","document.write"],outputArtifactType:"document.hwpx"}]};try{await api("/recipes",{method:"POST",body:JSON.stringify({id:recipeId,name:name,description:definition.description,version:"0.1.0",visibility:"organization",definition:definition,actor:"workspace-user"})});toast("Recipe 0.1.0을 게시했습니다.");loadWorkflowRecipes()}catch(error){toast(error.message)}};
    api("/rhwp/capabilities").then(function(data){$("rhwpRuntimeStatus").textContent=(data.installation?"설치 v"+data.installation.pinned_version:"미설치")+" · "+(data.runtime.available?"Windows 연결됨":"Windows 브리지 대기");$("rhwpToolCatalog").innerHTML=data.tools.map(function(tool){return"<span class='permission-chip' title='"+escapeHtml(tool.description)+"'>"+escapeHtml(tool.name)+"</span>"}).join(" ")}).catch(function(error){$("rhwpRuntimeStatus").textContent="조회 실패";$("rhwpToolCatalog").textContent=error.message});
    $("saveSettings").onclick=function(){toast("플랫폼 정책을 로컬에 저장했습니다.");addAudit("Policy","모델·데이터 정책 변경","완료")};
    document.querySelectorAll("[data-route-intent]").forEach(function(button){button.onclick=async function(){var output=$("routeResult");output.textContent="의도 분석 및 모델 선택 중...";try{var data=await api("/routing/test",{method:"POST",body:JSON.stringify({intent:button.dataset.routeIntent,classification:"public",live:Boolean($("liveRouteTest").checked),actor:"demo-user"})});output.textContent=JSON.stringify({intent:data.intentAnalysis.label,intentType:data.intentAnalysis.intentType,confidence:data.intentAnalysis.confidence,signals:data.intentAnalysis.matchedSignals,selectedModel:data.routing.model.id,personality:data.routing.model.personality,reason:data.routing.reason,live:data.live,resolvedModel:data.response&&data.response.resolvedModel,response:data.response&&data.response.content,usage:data.response&&data.response.usage},null,2);toast(data.routing.model.label+" 선택 완료");addAudit("Model Router","자동 선택 · "+data.routing.model.id,"완료")}catch(error){output.textContent="테스트 실패: "+error.message;toast(error.message)}}});
    document.querySelectorAll("[data-workflow]").forEach(function(button){button.onclick=async function(){var preset=state.presets.find(function(item){return item.id===button.dataset.workflow});var samples={document:["sample.hwpx",2400],code:["service.py",1200],image:["brief.png",2400],audio:["meeting.wav",3200],video:["summary.mp4",4800]};var sample=samples[preset.modality];var output=$("workflowResult");output.textContent="프리셋 실행 경계를 확인하고 있습니다.";try{var result=await api("/workflows/plan",{method:"POST",body:JSON.stringify({preset_id:preset.id,classification:"internal",assets:[{filename:sample[0],bytes:sample[1]}]})});output.textContent=JSON.stringify({preset:result.preset.name,modality:result.preset.modality,executable:result.executable,blockedBy:result.blockedBy,permissions:result.requiredPermissions,externalTransfer:result.externalTransfer,model:result.model&&result.model.id,steps:result.steps},null,2)}catch(error){output.textContent=error.message}}});
    $("inspectAssetButton").onclick=function(){$("assetInspectorInput").click()};
    $("assetInspectorInput").onchange=async function(){var file=this.files&&this.files[0];if(!file)return;var output=$("workflowResult");output.textContent="파일 바이트와 형식을 로컬 검사 중...";try{var result=await api("/assets/inspect",{method:"POST",body:JSON.stringify({filename:file.name,content_base64:await fileBase64(file),actor:"demo-user"})});output.textContent=JSON.stringify(result,null,2);toast("외부 전송 없이 "+result.modality+" 파일을 검사했습니다.")}catch(error){output.textContent=error.message}finally{this.value=""}};
  }

  async function syncWorkflowPresets(){
    try{var data=await api("/workflows/presets");state.presets=data.items||[];if(state.activeView==="settings")renderSettings()}catch(error){state.presets=[]}
  }

  function planFor(intent,isInstall,item){
    if(isInstall)return[
      {name:"Manifest, 번들 해시 및 조직 서명 검증",meta:item.id+" v"+(item.targetVersion||item.version)+" · 게시자 "+item.publisher},
      {name:"요청 권한 검토",meta:item.permissions.join(", ")},
      {name:"격리 설치 및 테스트",meta:"조직 데이터 접근 전 사전 승인"}
    ];
    var budget=intent.indexOf("예산")>=0||intent.indexOf("현재")>=0;
    return[
      {name:"문서 컨텍스트 읽기",meta:"HWPX 문서 어댑터 · document.read"},
      {name:budget?"현재 기준값 대조":"선택 문장 의도 분석",meta:(budget?"SW 대가산정 MCP · 공통데이터 읽기":"Core Intent MCP · 로컬 실행")},
      {name:budget?"예산 양식 초안 생성":"공문체 변경안 생성",meta:"Local · Qwen 3 8B · 외부 전송 없음"},
      {name:"변경 제안 만들기",meta:"문서 쓰기는 사용자가 적용할 때만 수행"}
    ];
  }
  function showApproval(intent,isInstall,item){
    state.pendingIntent=intent;state.pendingInstall=isInstall?item:null;
    $("approvalDialog").returnValue="";
    $("approvalIntent").textContent=intent;
    var serverSteps=!isInstall&&state.pendingPlan?(state.pendingPlan.steps||[]).map(function(step){return{name:step.action,meta:step.mcp+" · "+(step.permissions||[]).join(", ")}}):null;
    $("planSteps").innerHTML=(serverSteps||planFor(intent,isInstall,item||{})).map(function(step){return "<li><strong>"+escapeHtml(step.name)+"</strong><span>"+escapeHtml(step.meta)+"</span></li>"}).join("");
    $("externalTransfer").checked=false;
    var external=Boolean(!isInstall&&state.pendingPlan&&state.pendingPlan.dataPolicy.externalTransfer);
    $("externalTransfer").disabled=!external;
    var workflow=state.pendingPlan&&state.pendingPlan.workflow||{},markdownDocs=workflow.markdownContext||[],scope=workflow.hasSelection?"선택 문구와 요청":workflow.hasAttachment?"첨부 문서에서 로컬 추출한 발췌, 요청과 이전 분석":"요청과 이전 분석";
    if(markdownDocs.length)scope+=" 및 프로젝트 Markdown "+markdownDocs.length+"개("+markdownDocs.map(function(item){return item.title+" r"+item.revision}).join(", ")+")";
    $("transferDescription").textContent=external?scope+"이 운영자가 라이브 모델을 활성화한 경우 OpenRouter로 전송됩니다. 원본 파일 전체는 전송하지 않습니다.":"외부 모델 전송이 없는 로컬 작업입니다.";
    $("transferModel").textContent=external?state.pendingPlan.routing.model.label+" · "+state.pendingPlan.routing.reason:"외부 전송 불필요";
    $("approvalDialog").showModal();
    addAudit("Core","실행 계획 생성 · "+intent,"승인 대기");
  }
  async function runApproved(){
    var intent=state.pendingIntent;
    if(state.pendingInstall){
      var item=state.pendingInstall;var action=state.pendingStoreAction||"install";state.pendingInstall=null;state.pendingStoreAction="";
      try{
        setStatus(item.name+" 패키지 서명 검증 중");
        var endpoint=action==="rollback"?"/store/rollback":"/store/install";
        var request={package_id:item.id,actor:"demo-user",approved_permissions:item.permissions,acknowledge_signature:true};
        if(action==="install")request.version=item.targetVersion||item.version;
        var storeResult=await api(endpoint,{method:"POST",body:JSON.stringify(request)});
        await syncStore(false);
        var pinned=storeResult.installation.pinned_version;
        setStatus(item.name+" v"+pinned+" 고정 완료");toast(item.name+" v"+pinned+" "+(action==="rollback"?"롤백":"설치")+"을 완료했습니다.");addAudit("MCP Store",(action==="rollback"?"롤백":"서명 검증 설치")+" · "+item.id+"@"+pinned,"완료");
        if(state.activeView==="builder"){await loadCapabilityRegistry();if($("resolverIntent")&&state.builderDraft){var examples=(state.builderDraft.manifest.builderGuide||{}).triggerExamples||[];if(examples.length)$("resolverIntent").value=examples[0]}}else renderStore();
      }catch(error){setStatus("MCP 패키지 처리 실패");toast(error.message);addAudit("MCP Store",item.id+" · "+error.message,"차단")}
      return;
    }
    if(state.pendingPlan){
      try{
        setStatus("서명된 승인 토큰 발급 중");updateOrchestration("승인 토큰 발급과 실행 범위 고정","active");
        var plan=state.pendingPlan;
        var approval=await api("/approvals",{method:"POST",body:JSON.stringify({plan_id:plan.id,actor:"demo-user",permissions:plan.requiredPermissions})});
        setStatus("서버 샌드박스 실행 대기");updateOrchestration("MCP 실행과 Solar 응답 생성","active");
        var context=currentRequestContext(),activeSelection=state.nativeSelection&&state.nativeSelection.before?state.nativeSelection:state.templateSelection;
        var selectionText=activeSelection?activeSelection.before:"";
        var selectionId=activeSelection?(activeSelection.editId||activeSelection.target||"document.selection"):"";
        addAssistant(activeSelection?"승인된 선택 문구와 필요한 최소 문맥으로 실행합니다.":"승인 토큰이 발급되었습니다. 필요한 MCP를 순서대로 실행합니다.");
        var execution=await api("/executions",{method:"POST",body:JSON.stringify({approval_token:approval.approvalToken,idempotency_key:"web-"+plan.id,input:Object.assign({},context,{selection:selectionText,selection_id:selectionId,require_live_model:false,project_markdown_transfer_approved:Boolean(!$("externalTransfer").disabled&&$("externalTransfer").checked)})})});
        var result=execution.result||{},responseType=result.responseType||"selection-edit",resultModel=result.model||{},resultModelLabel=resultModel.resolvedModel||resultModel.name||"선택 모델";
        addWorkflowPipeline(result.workflow||plan.workflow);
        if(responseType==="text-answer"||responseType==="context-answer"){
          state.lastAnswer=String(result.answer||"");
          var answerNode=await streamAssistant(state.lastAnswer);
          addResultSources(answerNode,result.sources||[]);
          if(responseType==="text-answer")addRhwpEditAction(answerNode);
          updateOrchestration("분석 답변 생성 완료","done",resultModelLabel);
          setStatus((resultModel.mode==="live"?"Solar 응답 완료":"로컬 체험 응답 완료")+" · "+resultModelLabel);
          addAudit("Server",responseType+" · "+resultModelLabel+" · "+execution.id,"완료");state.pendingPlan=null;return;
        }
        if(responseType==="report-artifact"){
          if(!result.artifact)throw new Error("서버 실행 결과에 보고서 산출물이 없습니다.");
          state.lastAnswer=String(result.artifact.content||"");await openGeneratedArtifact(result.artifact,result.loadedMcps);await refreshActiveProjectWorkspace();
          addAssistant(resultModelLabel+"이 보고서 초안을 생성했습니다. 문구를 선택해 후속 MCP 작업을 계속할 수 있습니다.");
          updateOrchestration("MD 저장·양식 적용·파생 문서 생성 완료","done",resultModelLabel);
          setStatus("보고서 MCP 산출물 편집 중 · "+resultModelLabel);addAudit("Server","보고서 산출물 생성 · "+execution.id,"완료");state.pendingPlan=null;return;
        }
        if(responseType==="template-transform"){
          if(!state.nativeSession)throw new Error("양식을 적용할 현재 RHWP 문서 세션이 없습니다.");
          if(!result.artifact||!result.artifact.contentBase64)throw new Error("양식 MCP가 HWPX 산출물을 반환하지 않았습니다.");
          var templateApplied=await runNativeSessionCommand("replace_artifact",{contentBase64:result.artifact.contentBase64,filename:result.artifact.filename,canonical_markdown:String(result.artifact.content||"")});
          if(!templateApplied)throw new Error("행안부 보고서 양식을 현재 문서에 적용하지 못했습니다.");
          var templateName=result.artifact.template&&result.artifact.template.name||"행안부 보고서 양식";
          addAssistant(templateName+"을 현재 HWPX의 새 revision으로 적용했습니다. 등록된 양식 원본, 플레이스홀더와 작성 가이드에 따라 제목·본문·작성 정보를 대응했습니다.");
          await refreshActiveProjectWorkspace();updateOrchestration("양식 적용과 프로젝트 동기화 완료","done",resultModelLabel);
          setStatus("양식 MCP 적용 완료 · "+templateName);addAudit("Template MCP",templateName+" · "+execution.id,"완료");state.pendingPlan=null;return;
        }
        if(responseType==="document-transform"){
          if(!state.nativeSession)throw new Error("전체 내용을 바꿀 현재 RHWP 문서 세션이 없습니다.");
          if(!result.artifact||!result.artifact.contentBase64)throw new Error("보고서 MCP가 변환된 HWPX를 반환하지 않았습니다.");
          var transformed=await runNativeSessionCommand("replace_artifact",{contentBase64:result.artifact.contentBase64,filename:result.artifact.filename,canonical_markdown:String(result.artifact.content||"")});
          if(!transformed)throw new Error("변환된 전체 보고서를 현재 문서에 적용하지 못했습니다.");
          state.lastAnswer=String(result.artifact.content||"");
          addAssistant("보고서 전체 내용을 요청한 형식으로 다듬어 현재 RHWP 문서의 새 revision으로 적용했습니다.");
          await refreshActiveProjectWorkspace();updateOrchestration("문서 전체 변환과 MD 동기화 완료","done",resultModelLabel);
          setStatus("보고서 전체 변환 완료 · revision "+state.nativeSession.revision);addAudit("Report MCP","전체 문서 변환 · "+execution.id,"완료");state.pendingPlan=null;return;
        }
        var patch=execution.result&&execution.result.patches&&execution.result.patches[0];
        if(!patch)throw new Error("서버 실행 결과에 문서 변경안이 없습니다.");
        if(String(patch.after||"").trim()===String(patch.before||"").trim())throw new Error("모델이 원문과 동일한 문장을 반환하여 변경 제안을 중단했습니다.");
        var model=execution.result.model||{},modelLabel=model.resolvedModel||model.name||"선택 모델";state.lastProposalIntent=intent;
        $("beforeText").textContent="- "+patch.before;$("afterText").textContent="+ "+patch.after;$("proposal").dataset.before=patch.before;$("proposal").dataset.after=patch.after;$("proposal").dataset.executionId=execution.id;$("proposalIntent").textContent=(model.mode==="live"?"실제 LLM":"모델")+" · "+modelLabel+" · "+execution.id;$("proposal").hidden=false;
        updateOrchestration("수정 문구 비교·적용 대기","done",modelLabel);setStatus("실제 LLM 생성 완료 · 변경 제안 준비됨");addAssistant(modelLabel+"이 수정 지시를 반영한 문구를 생성했습니다. 비교 후 적용해 주세요.");addAudit("Server","LLM 문구 생성 완료 · "+modelLabel+" · "+execution.id,"완료");
        state.pendingPlan=null;setView("editor");return;
      }catch(error){
        state.pendingPlan=null;updateOrchestration("실행 실패 · 원인 확인 필요","error");setStatus("서버 실행 실패");addAssistant("서버 실행을 완료하지 못했습니다: "+error.message);toast(error.message);return;
      }
    }
    setStatus("MCP 1/4 · 문서 컨텍스트 확인 중");
    addAssistant("실행을 승인했습니다. 원문 전체 전송 없이 로컬 샌드박스에서 4단계를 실행합니다.");
    var stages=["MCP 2/4 · 공통데이터 대조 중","MCP 3/4 · 로컬 모델 생성 중","MCP 4/4 · 변경안 검증 중"];
    stages.forEach(function(stage,index){setTimeout(function(){setStatus(stage)},350*(index+1))});
    setTimeout(function(){
      var before=$("targetParagraph").textContent;
      var after=intent.indexOf("현재")>=0||intent.indexOf("예산")>=0?"2026년 SW사업 대가산정 기준을 적용하여 중급기술자 월평균임금 856만원과 투입기간 10개월을 반영함. 이에 따라 SW 개발비 856백만원, 총사업비 1,284백만원을 산정함.":"민원 대응의 신속성과 답변 품질의 일관성을 확보하기 위해 축적된 행정 지식과 최신 업무 기준을 연계한 지능형 지원 기반을 구축하고자 함.\n담당자의 업무 부담을 줄이고 대국민 서비스 품질을 향상하는 것을 목적으로 함.";
      $("beforeText").textContent="- "+before;$("afterText").textContent="+ "+after;$("proposal").dataset.before=before;$("proposal").dataset.after=after;$("proposal").dataset.executionId="";$("proposalIntent").textContent="실행 계획에 따라 변경안을 만들었습니다.";$("proposal").hidden=false;
      setStatus("변경 제안 준비됨");addAssistant("실행이 완료되었습니다. 문서에 바로 반영하지 않고 비교 가능한 변경 제안으로 준비했습니다.");addAudit("Orchestrator","실행 완료 · 로컬 모델 + 문서 MCP","완료");
      setView("editor");
    },1500);
  }
  function addAssistant(text,options){
    var node=document.createElement("div");node.className="message assistant";node.innerHTML="<span class='mini-orb'>✦</span><div><p>"+escapeHtml(text)+"</p></div>";$("chat").appendChild(node);$("chat").scrollTop=$("chat").scrollHeight;
    if(!(options&&options.skipPersist))scheduleWorkspaceStateSave(false);
  }
  function streamAssistant(text){
    var node=document.createElement("div");node.className="message assistant streaming";node.innerHTML="<span class='mini-orb'>✦</span><div><p></p></div>";$("chat").appendChild(node);var output=node.querySelector("p"),chars=Array.from(String(text||"")),index=0;
    return new Promise(function(resolve){var timer=setInterval(function(){index=Math.min(chars.length,index+Math.max(1,Math.ceil(chars.length/45)));output.textContent=chars.slice(0,index).join("");$("chat").scrollTop=$("chat").scrollHeight;if(index>=chars.length){clearInterval(timer);node.classList.remove("streaming");scheduleWorkspaceStateSave(false);resolve(node)}},18)});
  }
  function addRhwpEditAction(messageNode){
    if(!messageNode||!messageNode.querySelector("div"))return;
    var button=document.createElement("button");button.type="button";button.className="inline-link rhwp-edit-answer";button.textContent="이 답변을 RHWP에서 편집 →";
    button.onclick=function(){button.disabled=true;submitIntent("이 내용을 편집 가능한 문서로 만들어줘")};
    messageNode.querySelector("div").appendChild(button);
  }
  function addResultSources(messageNode,sources){
    if(!messageNode||!messageNode.querySelector("div")||!sources.length)return;
    var panel=document.createElement("div");panel.className="result-sources";
    panel.innerHTML="<strong>검색 근거 "+sources.length+"개</strong>"+sources.map(function(source,index){return"<button type='button' data-source-locator='"+escapeHtml(source.locator||"")+"'><b>["+(index+1)+"] "+escapeHtml(source.locator||source.documentId||"등록 자료")+"</b>"+(source.excerpt?"<small>"+escapeHtml(source.excerpt)+"</small>":"")+"</button>"}).join("");
    panel.querySelectorAll("button").forEach(function(button){button.onclick=function(){toast("원문 위치: "+button.dataset.sourceLocator)}});
    messageNode.querySelector("div").appendChild(panel);$("chat").scrollTop=$("chat").scrollHeight;
  }
  async function proposeNativeSelection(intent){
    if(!state.activeProjectId){showProjectGate();toast("프로젝트를 먼저 선택하세요.");return}
    var context=currentRequestContext();
    addAssistant("선택한 글귀와 수정 지시를 분석해 실제 LLM 실행 계획을 만들고 있습니다.");
    try{
      setStatus("선택 문구 LLM 실행 계획 생성 중");updateOrchestration("선택 문구와 수정 의도 분석","active","Solar 자동 선택");
      state.pendingPlan=await api("/plans",{method:"POST",body:JSON.stringify({intent:intent,actor:"demo-user",document_context:context})});
      state.serverOnline=true;addAssistant("사용할 모델과 외부 전송 범위를 확인한 뒤 실행을 승인해 주세요.");
      var model=state.pendingPlan.routing&&state.pendingPlan.routing.model&&state.pendingPlan.routing.model.label||"Solar 자동 선택";updateOrchestration("실행 계획 검토 및 승인","done",model);setStatus("선택 문구 외부 전송 승인 대기");showApproval(intent,false,null);
    }catch(error){
      state.pendingPlan=null;updateOrchestration("실행 계획 생성 실패","error");addAssistant("LLM 실행 계획을 만들지 못했습니다: "+error.message);setStatus("LLM 실행 계획 실패");toast(error.message);
    }
  }
  async function submitIntent(intent,options){
    intent=String(intent||"").trim();if(!intent)return;
    if(!state.activeProjectId){showProjectGate();toast("프로젝트를 먼저 선택하세요.");return}
    if(!(options&&options.skipUser)){var user=document.createElement("div");user.className="message user";user.innerHTML="<div>"+escapeHtml(intent)+"</div>";$("chat").appendChild(user);scheduleWorkspaceStateSave(false)}$("chatInput").value="";$("chat").scrollTop=$("chat").scrollHeight;
    if(state.nativeSession&&state.rhwpEditor){
      if(!state.nativeSelection||!state.nativeSelection.rhwpNative)await captureRhwpSelection(true);
      if(state.nativeSelection&&state.nativeSelection.before){await proposeNativeSelection(intent);return}
    }
    if(state.nativeSession&&state.nativeSelection&&state.nativeSelection.before){await proposeNativeSelection(intent);return}
    if(state.templateSelection&&state.templateSelection.before){await proposeNativeSelection(intent);return}
    addAssistant("요청을 분석하고 프로젝트 문맥에서 필요한 MCP와 Solar 모델을 찾고 있습니다.");
    try{
      setStatus("서버 실행 계획 생성 중");updateOrchestration("요청 의도와 프로젝트 문맥 분석","active","Solar 자동 선택");
      var context=currentRequestContext();
      state.pendingPlan=await api("/plans",{method:"POST",body:JSON.stringify({intent:intent,actor:"demo-user",document_context:context})});
      state.serverOnline=true;
      addAssistant("필요한 MCP를 찾았습니다. 실행 계획 "+state.pendingPlan.id+"의 권한과 데이터 범위를 확인해 주세요.");
      var selectedModel=state.pendingPlan.routing&&state.pendingPlan.routing.model&&state.pendingPlan.routing.model.label||"Solar 자동 선택";$("chatForm").querySelector(".model-select").textContent=selectedModel+" · 의도 기반 자동 선택";updateOrchestration("실행 계획 검토 및 승인","done",selectedModel);setStatus("사용자 승인 대기");showApproval(intent,false,null);
    }catch(error){
      state.pendingPlan=null;updateOrchestration("실행 계획 생성 실패","error");addAssistant("서버 계획 생성에 실패했습니다. 실행하지 않았습니다: "+error.message);setStatus("계획 생성 실패");toast(error.message);
    }
  }
  async function syncServerAudit(){
    try{
      var data=await api("/audit");
      var translated=(data.items||[]).slice(0,30).map(function(item){
        var status=item.eventType.indexOf("failed")>=0?"실패":item.eventType.indexOf("denied")>=0?"차단":"완료";
        return{time:new Date(item.createdAt).toLocaleString("ko-KR",{hour:"2-digit",minute:"2-digit",second:"2-digit"}),actor:item.actor,event:item.eventType+(item.executionId?" · "+item.executionId:""),status:status};
      });
      if(translated.length){state.audit=translated;renderAudit()}
    }catch(error){setStatus("서버 감사 로그를 불러오지 못함")}
  }
  async function bootstrapServer(){
    try{
      var data=await api("/bootstrap");state.serverOnline=true;state.models=data.models||[];state.openrouter=data.openrouter||state.openrouter;
      await loadProjects();
      await syncStore(false);
      await syncWorkflowPresets();
      document.querySelector(".local-badge").innerHTML="<i></i> 서버 샌드박스 v"+escapeHtml(data.version);
      setStatus("서버 실행 계층 연결됨 · 승인 토큰 "+data.policies.approvalTokenTtlSeconds+"초");
    }catch(error){state.serverOnline=false;setStatus("서버 실행 계층 연결 실패");updateOrchestration("서버 연결 실패","error")}
  }
  function fileBase64(file){
    return new Promise(function(resolve,reject){
      var reader=new FileReader();
      reader.onload=function(){resolve(String(reader.result||"").split(",",2)[1]||"")};
      reader.onerror=function(){reject(new Error("파일을 읽지 못했습니다."))};
      reader.readAsDataURL(file);
    });
  }
  async function importHwpx(file,intent){
    if(!file)return;
    if(!state.activeProjectId){showProjectGate();toast("문서를 저장할 프로젝트를 먼저 선택하세요.");return}
    if(!/\.(hwp|hwpx|hwt|hml|md|txt|py|js|ts|json)$/i.test(file.name)){toast("지원하는 편집기 MCP가 없는 파일입니다.");return}
    try{
      setStatus("의도 분석 · 문서 MCP 선택 중");updateOrchestration("첨부 문서 분석과 편집기 MCP 선택","active","로컬 문서 분석");
      var contentBase64=await fileBase64(file);
      state.undoDocument=null;state.workspaceDocument=null;
      var session=await api("/documents/sessions",{method:"POST",body:JSON.stringify({filename:file.name,content_base64:contentBase64,intent:intent||"이 문서를 원본 형식과 구조를 유지하며 열고 수정",project_id:state.activeProjectId,confirmed:true,actor:"workspace-user"})});
      var snapshot=session.snapshot||{},excerpt=snapshot.content||snapshot.document&&snapshot.document.paragraphs&&snapshot.document.paragraphs.map(function(item){return item.text}).join("\n")||"";
      state.sourceContext={filename:file.name,excerpt:String(excerpt).slice(0,8000),sessionId:session.id};
      await renderNativeSession(session);
      await streamAssistant("의도 분석 결과 ‘"+(session.intentAnalysis.label||session.intentAnalysis.intentType)+"’ 작업으로 분류했습니다. "+session.workspace.loadedMcps.length+"개 MCP를 순서대로 로딩했습니다.");
      var pipeline=document.createElement("div");pipeline.className="message assistant";pipeline.innerHTML="<span class='mini-orb'>⌘</span><div><p><b>실행 파이프라인</b></p><div class='pipeline'>"+session.workspace.pipeline.map(function(step,index){return"<span>"+(index+1)+". "+escapeHtml(step)+"</span>"}).join("")+"</div></div>";$("chat").appendChild(pipeline);$("chat").scrollTop=$("chat").scrollHeight;
      await refreshActiveProjectWorkspace();updateOrchestration("첨부 문서 프로젝트 저장 완료","done","로컬 문서 분석");setStatus(session.adapter+" 로딩 완료 · "+session.runtime);
      toast("문서 MCP 세션을 열었습니다.");addAudit("Core Orchestrator","문서 MCP 로딩 · "+session.adapter,"완료");
      return session;
    }catch(error){updateOrchestration("첨부 문서 처리 실패","error");setStatus("문서 MCP 로딩 실패");toast(error.message);addAssistant("문서를 열지 못했습니다: "+error.message)}
    finally{$("hwpxFile").value=""}
  }
  function updateWelcomeFile(file){state.welcomeFile=file||null;$("welcomeFileChip").hidden=!file;if(file)$("welcomeFileName").textContent=file.name}
  async function launchWelcome(){
    if(!state.activeProjectId){showProjectGate();toast("프로젝트를 먼저 선택하세요.");return}
    var intent=$("welcomePrompt").value.trim();if(!intent){toast("원하는 작업을 입력하세요.");$("welcomePrompt").focus();return}
    if(!state.welcomeFile){enterWorkspace(true);$("chat").innerHTML="";state.sourceContext=null;if(state.projectWorkbench){renderProjectWorkbenchTabs();await switchProjectWorkbenchTab(state.activeWorkbenchTab||"markdown")}else activateEmptyWorkspace();await submitIntent(intent);return}
    var file=state.welcomeFile;enterWorkspace(true);$("chat").innerHTML="";var user=document.createElement("div");user.className="message user";user.innerHTML="<div><small>첨부 · "+escapeHtml(file.name)+"</small><br>"+escapeHtml(intent)+"</div>";$("chat").appendChild(user);
    var session=await importHwpx(file,intent);
    if(session)await submitIntent(intent,{skipUser:true});
  }
  function downloadBase64(filename,contentBase64){
    var binary=atob(contentBase64);var bytes=new Uint8Array(binary.length);
    for(var index=0;index<binary.length;index+=1){bytes[index]=binary.charCodeAt(index)}
    var url=URL.createObjectURL(new Blob([bytes],{type:"application/hwp+zip"}));
    var link=document.createElement("a");link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();
    setTimeout(function(){URL.revokeObjectURL(url)},1000);
  }
  function downloadEditableHtml(){
    var clone=$("documentPaper").cloneNode(true);clone.querySelectorAll("[contenteditable]").forEach(function(node){node.removeAttribute("contenteditable");node.removeAttribute("role");node.removeAttribute("aria-label")});
    var html="<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>AIWorks 문서</title><style>body{margin:40px;font-family:sans-serif;color:#222}article{max-width:760px;margin:auto}table{width:100%;border-collapse:collapse}th,td{border:1px solid #bbb;padding:8px}h1{text-align:center}</style></head><body>"+clone.outerHTML+"</body></html>";
    var url=URL.createObjectURL(new Blob([html],{type:"text/html;charset=utf-8"}));var link=document.createElement("a");link.href=url;link.download="AIWorks_예산요청서.html";document.body.appendChild(link);link.click();link.remove();setTimeout(function(){URL.revokeObjectURL(url)},1000);
  }
  function undoChange(){
    if(!state.undoText){toast("되돌릴 변경이 없습니다.");return}
    var current=$("targetParagraph").textContent;$("targetParagraph").textContent=state.undoText;state.undoText=null;
    if(state.undoDocument){state.currentDocument=state.undoDocument;state.undoDocument=null;state.workspaceDocument=null;$("activeFileName").textContent=state.currentDocument.filename}
    updateLivePreview();toast("마지막 문서 변경을 되돌렸습니다.");addAudit("사용자","변경 되돌리기 · 추진 배경 문단","완료");setStatus("변경 되돌림");setView("editor");
  }

  function initializeWorkspaceResizer(){
    var handle=$("workspaceResizer"),workbench=$("workbench"),storageKey="aiworks.orchestrator.width.v1";if(!handle||!workbench)return;
    function limits(){return{min:280,max:Math.max(320,Math.min(680,window.innerWidth-570))}}
    function applyWidth(value,persist){var boundary=limits(),width=Math.max(boundary.min,Math.min(boundary.max,Number(value)||350));workbench.style.setProperty("--orchestrator-width",width+"px");handle.setAttribute("aria-valuemin",String(boundary.min));handle.setAttribute("aria-valuemax",String(boundary.max));handle.setAttribute("aria-valuenow",String(Math.round(width)));if(persist)localStorage.setItem(storageKey,String(Math.round(width)));return width}
    applyWidth(Number(localStorage.getItem(storageKey)||350),false);
    handle.addEventListener("pointerdown",function(event){if(event.button!==0)return;event.preventDefault();document.body.classList.add("is-resizing");handle.setPointerCapture(event.pointerId);applyWidth(event.clientX-48,true)});
    handle.addEventListener("pointermove",function(event){if(!document.body.classList.contains("is-resizing"))return;applyWidth(event.clientX-48,true)});
    function stopResize(event){if(!document.body.classList.contains("is-resizing"))return;document.body.classList.remove("is-resizing");if(event&&handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId)}
    handle.addEventListener("pointerup",stopResize);handle.addEventListener("pointercancel",stopResize);
    handle.addEventListener("dblclick",function(){applyWidth(350,true);toast("대화창 비율을 기본값으로 되돌렸습니다.")});
    handle.addEventListener("keydown",function(event){if(event.key!=="ArrowLeft"&&event.key!=="ArrowRight"&&event.key!=="Home")return;event.preventDefault();var current=Number(handle.getAttribute("aria-valuenow")||350);applyWidth(event.key==="Home"?350:current+(event.key==="ArrowRight"?18:-18),true)});
    window.addEventListener("resize",function(){applyWidth(Number(handle.getAttribute("aria-valuenow")||350),false)});
  }

  document.querySelectorAll(".activitybar button[data-view]").forEach(function(button){button.onclick=function(){setView(button.dataset.view)}});
  document.querySelectorAll(".top-menu button[data-top-view]").forEach(function(button){button.onclick=function(){if(!state.activeProjectId){showProjectGate();toast("프로젝트를 먼저 선택하세요.");return}enterWorkspace(true);setView(button.dataset.topView)}});
  document.addEventListener("click",function(event){
    var quick=event.target.closest("[data-prompt]");if(quick)submitIntent(quick.dataset.prompt);
    var link=event.target.closest("[data-view-link]");if(link)setView(link.dataset.viewLink);
    var nativeBlock=event.target.closest("#documentPaper [data-native-target]");if(nativeBlock)selectNativeBlock(nativeBlock);
  });
  $("chatForm").onsubmit=function(event){event.preventDefault();submitIntent($("chatInput").value)};
  $("chatInput").addEventListener("focus",function(){if(state.nativeSession&&state.rhwpEditor)captureRhwpSelection(true)});
  $("commandButton").onclick=function(){if(!state.activeProjectId){showProjectGate();toast("프로젝트를 먼저 선택하세요.");return}if($("workbench").hidden)openSelectedProjectWorkspace();else $("chatInput").focus()};
  $("approvalDialog").addEventListener("close",function(){if($("approvalDialog").returnValue==="approve"){runApproved()}else if(state.pendingIntent){updateOrchestration("실행 취소 · 다음 요청 대기","idle");addAudit("사용자","실행 취소 · "+state.pendingIntent,"차단");state.pendingIntent="";state.pendingInstall=null;state.pendingStoreAction="";state.pendingPlan=null}});
  $("approveRun").addEventListener("click",function(event){if(!$("externalTransfer").disabled&&!$("externalTransfer").checked){event.preventDefault();toast("선택 모델과 전송 데이터를 확인하고 외부 전송을 승인해 주세요.")}});
  $("applyProposal").onclick=async function(){
    var after=$("proposal").dataset.after;state.undoText=$("targetParagraph")?$("targetParagraph").textContent:null;
    try{
      if(state.nativeSession){
        if(state.rhwpEditor&&(state.nativeSelection&&state.nativeSelection.rhwpNative||$("proposal").dataset.before)){
          setStatus("RHWP 네이티브 선택에 제안 적용 중");
          await state.rhwpEditor.replaceSelection(after);
          var nativeSaved=await saveDocumentChanges();
          if(!nativeSaved)throw new Error("RHWP 변경 산출물을 저장하지 못했습니다.");
          $("proposal").hidden=true;state.undoText=null;
          addAudit("사용자","RHWP 네이티브 선택 제안 적용 · "+state.nativeSession.adapter,"완료");
          return;
        }
        var applied=await runNativeSessionCommand("replace_selection",{target:state.nativeSelection&&state.nativeSelection.target||"",before:$("proposal").dataset.before,after:after});
        if(applied){$("proposal").hidden=true;state.undoText=null}return;
      }
      if(state.currentDocument){
        if(!state.currentDocument.target)throw new Error("수정할 HWPX 본문 문단이 없습니다.");
        setStatus("HWPX 변경 검증 및 새 버전 생성 중");
        var previous=Object.assign({},state.currentDocument,{savedTexts:Object.assign({},state.currentDocument.savedTexts)});
        var result=await api("/documents/apply-hwpx",{method:"POST",body:JSON.stringify({
          filename:state.currentDocument.filename,document_id:state.currentDocument.id,
          content_base64:state.currentDocument.contentBase64,actor:"demo-user",
          patch:{op:"replace",target:state.currentDocument.target,expectedBefore:$("proposal").dataset.before,after:after,sourceSha256:state.currentDocument.sha256,executionId:$("proposal").dataset.executionId||null,sources:[]}
        })});
        state.undoDocument=previous;
        state.currentDocument.id=result.documentId;state.currentDocument.filename=result.filename;state.currentDocument.contentBase64=result.contentBase64;state.currentDocument.sha256=result.artifactSha256;state.currentDocument.target=result.target;state.currentDocument.artifactReady=true;state.currentDocument.versionId=result.versionId;state.currentDocument.savedTexts[result.target]=after;
        $("activeFileName").textContent=result.filename;
      }
      if(state.templateSelection&&applyTemplateSelection($("proposal").dataset.before,after)){state.documentSavedSnapshot=documentSnapshot();state.documentUndoSnapshot=null;saveBrowserDocumentDraft(true);updateLivePreview();$("proposal").hidden=true;setStatus("선택 문구 변경 적용됨 · 현재 위치 유지");toast("선택한 문구에 변경을 적용했습니다.");addAudit("사용자","보고서 선택 문구 변경 적용","완료");return}
      $("targetParagraph").textContent=after;state.documentSavedSnapshot=documentSnapshot();state.documentUndoSnapshot=null;saveBrowserDocumentDraft(true);updateLivePreview();$("proposal").hidden=true;setStatus("변경 적용됨 · HWPX 새 버전 준비");toast("변경을 적용했습니다. 내보내기로 HWPX를 받을 수 있습니다.");addAudit("사용자","AI 변경 제안 적용 · "+(state.currentDocument?state.currentDocument.target:"추진 배경 문단"),"완료");
    }catch(error){state.undoText=null;setStatus("HWPX 변경 적용 실패");toast(error.message);addAssistant("변경을 적용하지 않았습니다: "+error.message)}
  };
  $("cancelProposal").onclick=function(){$("proposal").hidden=true;setStatus("변경 제안 취소");addAudit("사용자","AI 변경 제안 취소","완료")};
  $("regenerateProposal").onclick=function(){var intent=(state.lastProposalIntent||"선택 문구를 자연스럽게 수정해줘")+" 이전 결과와 다른 표현으로 다시 작성하고 원문을 그대로 반복하지 마.";$("proposal").hidden=true;submitIntent(intent)};
  $("previewToggle").onclick=function(){updateLivePreview();$("previewPane").hidden=!$("previewPane").hidden};
  $("importHwpx").onclick=function(){$("hwpxFile").click()};
  $("hwpxFile").onchange=function(){importHwpx(this.files&&this.files[0])};
  $("welcomeAttach").onclick=function(){$("welcomeFile").click()};
  $("welcomeFile").onchange=function(){updateWelcomeFile(this.files&&this.files[0])};
  $("welcomeFileRemove").onclick=function(){updateWelcomeFile(null);$("welcomeFile").value=""};
  $("welcomeForm").onsubmit=function(event){event.preventDefault();launchWelcome()};
  $("projectCreateForm").onsubmit=async function(event){event.preventDefault();var name=$("projectNameInput").value.trim();if(!name)return;var button=this.querySelector("button[type='submit']");button.disabled=true;button.textContent="프로젝트 생성 중...";try{var project=await api("/projects",{method:"POST",body:JSON.stringify({name:name,classification:"internal",actor:"workspace-user"})});await loadProjects();$("projectNameInput").value="";await selectProject(project.id)}catch(error){toast(error.message)}finally{button.disabled=false;button.textContent="프로젝트 생성 후 시작"}};
  $("importProjectBackup").onclick=function(){$("projectBackupFile").click()};
  $("projectBackupFile").onchange=function(){importProjectBackupFile(this.files&&this.files[0])};
  $("refreshProjects").onclick=loadProjects;
  $("changeProject").onclick=requestProjectChange;
  document.querySelectorAll("[data-welcome-prompt]").forEach(function(button){button.onclick=function(){$("welcomePrompt").value=button.dataset.welcomePrompt;$("welcomePrompt").focus()}});
  $("enterDemo").onclick=openSelectedProjectWorkspace;
  $("closePreview").onclick=function(){$("previewPane").hidden=true};
  $("splitButton").onclick=function(){updateLivePreview();$("previewPane").hidden=false;toast("문서와 산출물 미리보기를 분할했습니다.")};
  [["formatParagraph","formatBlock","P"],["formatBold","bold"],["formatItalic","italic"],["formatAlign","justifyLeft"],["formatList","insertUnorderedList"]].forEach(function(binding){
    var button=$(binding[0]);button.addEventListener("mousedown",function(event){event.preventDefault()});button.onclick=function(){applyDocumentFormat(binding[1],binding[2])};
  });
  $("saveDocument").onclick=saveDocumentChanges;
  $("syncMdToHwpx").onclick=syncMarkdownToHwpx;
  $("syncHwpxToMd").onclick=syncHwpxToMarkdown;
  $("downloadProjectHwpx").onclick=downloadProjectHwpx;
  $("undoDirectEdit").onclick=function(){if(state.nativeSession){if(state.nativeSession.runtime==="windows-native-bridge")runNativeSessionCommand("undo",{});else toast("HWPX 대체 세션은 저장 버전 목록에서 이전 산출물을 다시 여세요.")}else undoDirectEdit()};
  $("exportButton").onclick=async function(){var saved=await saveDocumentChanges();if(!saved)return;if(state.nativeSession){try{var artifact=await api("/documents/sessions/"+state.nativeSession.id+"/artifact");downloadBase64(artifact.filename,artifact.contentBase64);toast(artifact.filename+" MCP 산출물 다운로드를 시작했습니다.");addAudit("Document MCP","원본 산출물 내보내기 · "+artifact.adapter,"완료")}catch(error){toast(error.message)}}else if(state.currentDocument){downloadBase64(state.currentDocument.filename,state.currentDocument.contentBase64);toast(state.currentDocument.filename+" 다운로드를 시작했습니다.");addAudit("사용자","HWPX 내보내기 · "+state.currentDocument.filename,"완료")}else{downloadEditableHtml();toast("직접 편집한 문서를 HTML로 내보냈습니다.");addAudit("사용자","편집 문서 HTML 내보내기","완료")}};
  $("clearChat").onclick=function(){$("chat").innerHTML="";state.lastAnswer="";var summary=state.projectWorkspace&&state.projectWorkspace.summary||{};addAssistant((state.activeProject&&state.activeProject.name||"현재")+" 프로젝트 문맥은 유지합니다. MD "+Number(summary.documentCount||0)+"개와 메타정보 "+Number(summary.factCount||0)+"개를 계속 사용할 수 있습니다.");scheduleWorkspaceStateSave(true);updateOrchestration("다음 업무 요청 대기","idle");toast("실행 이력과 프로젝트 문맥은 유지하고 대화만 초기화했습니다.")};
  document.addEventListener("keydown",function(event){var key=event.key.toLowerCase();if((event.ctrlKey||event.metaKey)&&key==="k"){event.preventDefault();$("chatInput").focus()}if((event.ctrlKey||event.metaKey)&&key==="s"){event.preventDefault();saveDocumentChanges()}if((event.ctrlKey||event.metaKey)&&key==="z"&&!event.target.closest("input,textarea,[contenteditable='true']")){event.preventDefault();undoChange()}});

  initializeDirectEditing();
  initializeWorkspaceResizer();
  updateLivePreview();
  setView("editor");
  showProjectGate();
  bootstrapServer();
})();
