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
    activeConversationId:null,
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
    templateMcps:[],
    templateMcpsLoaded:false,
    templateSwitchInFlight:false,
    builderResolution:null,
    quarantined:[],
    latestAcceptance:null,
    externalMcpProfiles:[],
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
    welcomeFiles:[],
    projectSources:[],
    selectedProjectSourceIds:[],
    templateSelection:null,
    lastAnswer:"",
    sourceContext:null,
    sourceEditorDirty:false,
    rhwpEditor:null,
    installed:[],audit:[],commonData:[],mcps:[]
  };

  var sidebarByView={
    editor:'<div class="section-label">프로젝트 문서</div><div class="sidebar-list"><button>문서 내용</button><button>완성 문서</button><button>내보낸 파일</button></div><div class="section-label">도움말</div><p class="sidebar-help">프로젝트를 선택하면 마지막으로 작업한 문서와 탭이 복원됩니다.</p>',
    data:'<div class="section-label">프로젝트 자료</div><div class="sidebar-list"><button>첨부 자료</button><button>기준정보</button><button>근거 검색</button></div><div class="section-label">고급</div><div class="sidebar-list"><button>시점 비교</button><button>지식 관계</button></div>',
    builder:'<div class="section-label">MCP 제작</div><div class="sidebar-list"><button>＋ 새 MCP</button><button>초안　1</button><button>검증 대기　0</button><button>내가 게시한 MCP　2</button></div><div class="section-label">제작 단계</div><div class="sidebar-list"><button>1　목적·조건</button><button>2　Manifest</button><button>3　Schema</button><button>4　샌드박스 테스트</button><button>5　공개 범위</button></div>',
    store:'<div class="section-label">MCP 스토어</div><div class="sidebar-list"><button>추천</button><button>문서 업무</button><button>데이터·지식</button><button>개발 도구</button><button>보안·운영</button></div><div class="section-label">내 라이브러리</div><div class="sidebar-list"><button>설치됨　4</button><button>업데이트　1</button><button>사전 승인　4</button></div>',
    audit:'<div class="section-label">실행 관리</div><div class="sidebar-list"><button>오늘의 실행</button><button>승인 요청</button><button>오류·차단</button><button>변경 이력</button></div><div class="section-label">필터</div><div class="sidebar-list"><button>사용자 실행</button><button>MCP 호출</button><button>모델 호출</button><button>데이터 접근</button></div>',
    settings:'<div class="section-label">설정</div><div class="sidebar-list"><button>모델 라우팅</button><button>MCP 권한</button><button>데이터 정책</button><button>샌드박스</button><button>감사·보존</button></div>'
  };
  var titleByView={editor:"문서",data:"자료",builder:"MCP 만들기",store:"Store",audit:"AI 작업 이력",settings:"설정"};

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
    $("orchestrationResources").textContent="자료 "+Number(summary.sourceCount||state.projectSources.length||0)+" · 문서 "+Number(summary.documentCount||0)+" · 기준정보 "+Number(summary.factCount||0);
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
      api("/projects/"+encodeURIComponent(state.activeProjectId)+"/workspace-state",{method:"POST",body:JSON.stringify({active_document_id:documentId,active_tab:state.activeWorkbenchTab||"markdown",active_view:state.activeView||"editor",chat:captureProjectChat(),last_answer:state.lastAnswer||"",actor:"workspace-user"})}).then(function(saved){if(saved&&saved.conversationId)state.activeConversationId=saved.conversationId}).catch(function(){});
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
      return"<div class='project-list-item active'><button class='project-list-open' type='button' data-select-project='"+escapeHtml(project.id)+"'><strong>"+escapeHtml(project.name)+"</strong><span>문서 "+Number(project.documentCount||0)+" · 프로젝트 메타 "+Number(project.factCount||0)+"</span><i>최근 작업 "+escapeHtml(updated)+" · "+escapeHtml(project.classification||"internal")+"</i></button><div class='project-list-actions'><small>열기</small><button type='button' data-delete-project='"+escapeHtml(project.id)+"' aria-label='"+escapeHtml(project.name)+" 프로젝트 삭제'>삭제</button></div></div>";
    }).join("");
    var archivedHtml=state.archivedProjects.length?"<div class='project-archive-divider'><span>삭제된 프로젝트 · 복원 가능</span><small>"+state.archivedProjects.length+"</small></div>"+state.archivedProjects.map(function(project){
      var updated=project.updatedAt?new Date(project.updatedAt).toLocaleDateString("ko-KR"):"-";
      return"<div class='project-list-item archived'><strong>"+escapeHtml(project.name)+"</strong><span>문서와 메타정보가 안전하게 보존되어 있습니다.</span><button type='button' data-restore-project='"+escapeHtml(project.id)+"'>복원</button><i>삭제일 "+escapeHtml(updated)+" · "+escapeHtml(project.classification||"internal")+"</i></div>";
    }).join(""):"";
    host.innerHTML=activeHtml+archivedHtml;
    host.querySelectorAll("[data-select-project]").forEach(function(button){button.onclick=function(){selectProject(button.dataset.selectProject)}});
    host.querySelectorAll("[data-delete-project]").forEach(function(button){button.onclick=async function(){
      var projectId=button.dataset.deleteProject,project=state.projects.find(function(item){return item.id===projectId}),projectName=project&&project.name||"이 프로젝트";
      if(!window.confirm("'"+projectName+"' 프로젝트를 삭제할까요?\n\n기본 MD 문서와 메타정보는 보존되며 아래 삭제 목록에서 복원할 수 있습니다."))return;
      button.disabled=true;
      try{
        await api("/projects/"+encodeURIComponent(projectId)+"/status",{method:"POST",body:JSON.stringify({action:"archive",actor:"workspace-user"})});
        if(state.activeProjectId===projectId){
          clearWorkbenchTabCache();clearWorkbenchCanvas();state.activeProjectId=null;state.activeProject=null;state.activeConversationId=null;state.projectWorkspace=null;state.projectWorkbench=null;state.projectDocuments=[];state.lastAnswer="";renderProjectChat([]);updateProjectContext();
        }
        await loadProjects();toast(projectName+" 프로젝트를 삭제 목록으로 이동했습니다. 필요하면 복원할 수 있습니다.");
      }catch(error){button.disabled=false;toast(error.message)}
    }});
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
      toast("프로젝트 메타정보와 기본 MD 문서 백업을 다운로드했습니다.");setStatus("프로젝트 백업 완료");
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
    await loadProjectSources(false);updateProjectContext();renderEditorSidebar();return workspace;
  }
  async function selectProject(projectId){
    updateOrchestration("프로젝트 문서와 메타정보 복원","active","Solar 자동 선택");setStatus("프로젝트 작업공간 불러오는 중");
    try{
      state.restoreViewOverride="";
      clearWorkbenchTabCache();clearWorkbenchCanvas();state.restoringWorkspace=true;state.activeProjectId=projectId;state.activeConversationId=null;state.projectWorkbench=null;state.activeWorkbenchTab="";state.nativeSession=null;state.sourceContext=null;state.lastAnswer="";state.projectSources=[];state.selectedProjectSourceIds=[];
      var workspace=await refreshActiveProjectWorkspace();
      var saved=workspace.workspaceState||{};state.activeConversationId=saved.conversationId||null;state.lastAnswer=String(saved.lastAnswer||"");renderProjectChat(saved.chat||[]);
      $("projectGate").hidden=true;
      var summary=workspace.summary||{};updateOrchestration("프로젝트 작업공간 복원 완료","done","Solar 자동 선택");
      setStatus(workspace.project.name+" · 문서 "+Number(summary.documentCount||0)+" · 프로젝트 메타 "+Number(summary.factCount||0));
      if((workspace.documents||[]).length){
        var restoredDocument=(workspace.documents||[]).find(function(item){return item.id===saved.activeDocumentId})||workspace.documents[0];
        state.projectWorkbench=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+restoredDocument.id+"/workbench");state.activeWorkbenchTab=saved.activeTab||"markdown";renderProjectWorkbenchTabs();
        enterWorkspace(true);await switchProjectWorkbenchTab(state.activeWorkbenchTab,{restoring:true});
        setView(state.restoreViewOverride||saved.activeView||"editor",{restoring:true});state.restoreViewOverride="";
      }else{
        $("welcomeTask").hidden=true;enterWorkspace(true);activateEmptyWorkspace();renderEditorSidebar();setView("editor",{restoring:true});
      }
      if((saved.chat||[]).length===0){
        if(workspace.documents.length)addAssistant(workspace.project.name+" 프로젝트의 마지막 문서와 작업 탭을 복원했습니다.",{skipPersist:true});
        else addAssistant(workspace.project.name+" 프로젝트를 열었습니다. 아직 기본 문서가 없습니다. 대화창에 첫 업무를 요청하거나 파일을 첨부하면 기본 MD 문서를 만듭니다.",{skipPersist:true});
      }
      await loadProjectFacts(true);state.restoringWorkspace=false;scheduleWorkspaceStateSave(false);toast(workspace.project.name+" 프로젝트의 마지막 작업을 복원했습니다.");
    }catch(error){state.restoringWorkspace=false;state.activeProjectId=null;state.activeProject=null;state.activeConversationId=null;state.projectWorkspace=null;updateProjectContext();updateOrchestration("프로젝트 복원 실패","error");toast(error.message)}
  }
  async function openSelectedProjectWorkspace(){
    if(!state.activeProjectId){showProjectGate();toast("프로젝트를 먼저 선택하세요.");return}
    enterWorkspace(true);
    var summary=state.projectWorkspace&&state.projectWorkspace.summary||{};
    if(!$("chat").querySelector(".message"))addAssistant((state.activeProject&&state.activeProject.name||state.activeProjectId)+" 프로젝트를 열었습니다. 기본 문서 "+Number(summary.documentCount||0)+"개와 프로젝트 메타정보 "+Number(summary.factCount||0)+"개를 작업 문맥으로 사용합니다. 최종 산출물은 각 문서에서 별도로 생성합니다.");
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
      document_excerpt:documentExcerpt(),
      project_source_ids:state.selectedProjectSourceIds.slice()
    };
  }
  function explainedMcpPlan(source){
    var workflow=source&&source.workflow||source||{},declared=workflow.mcpPlan||[],byRef={};
    declared.forEach(function(item){if(item&&item.packageRef)byRef[item.packageRef]=item});
    return(workflow.loadedMcps||declared.map(function(item){return item.packageRef})).map(function(packageRef){
      if(byRef[packageRef])return byRef[packageRef];
      var packageId=String(packageRef||"").split("@",1)[0],binding=(workflow.capabilityBindings||[]).find(function(item){return item.packageRef===packageRef})||{},storeItem=(state.mcps||[]).find(function(item){return item.id===packageId});
      return{packageRef:packageRef,name:binding.name||storeItem&&storeItem.name||packageId,description:binding.description||storeItem&&storeItem.desc||"이 작업에 필요한 확장 기능을 제공합니다.",reason:"이번 요청을 완료하는 데 이 MCP의 기능이 필요하다고 의도 분석 단계에서 판단해 호출합니다.",actions:[],permissions:binding.permissions||[]};
    });
  }
  function mcpPlanItemHtml(item,tagName){
    var actions=(item.actions||[]).length?(item.actions||[]).join(" → "):"계획에 따라 필요한 기능 실행",permissions=(item.permissions||[]).length?(item.permissions||[]).join(", "):"추가 권한 없음";
    return"<"+tagName+" class='explained-mcp'><header><strong>"+escapeHtml(item.name||item.packageId||"MCP")+"</strong><code>"+escapeHtml(item.packageRef||"")+"</code></header><p><b>무엇을 하나요</b><span>"+escapeHtml(item.description||"")+"</span></p><p><b>왜 호출하나요</b><span>"+escapeHtml(item.reason||"")+"</span></p><small>수행 작업 · "+escapeHtml(actions)+"</small><small>사용 권한 · "+escapeHtml(permissions)+"</small></"+tagName+">";
  }
  function addWorkflowPipeline(workflow,plan){
    if(!workflow)return;
    var planned=plan&&plan.workflow||{},explanationSource=Object.assign({},workflow,{mcpPlan:planned.mcpPlan||workflow.mcpPlan||[],capabilityBindings:planned.capabilityBindings||workflow.capabilityBindings||[]}),items=explainedMcpPlan(explanationSource);
    var node=document.createElement("div");node.className="message assistant workflow-message";
    node.innerHTML="<span class='mini-orb'>⌘</span><div><p><b>이 작업에 사용한 MCP</b></p><div class='pipeline mcp-pipeline'>"+items.map(function(item){return mcpPlanItemHtml(item,"article")}).join("")+"</div></div>";
    $("chat").appendChild(node);$("chat").scrollTop=$("chat").scrollHeight;scheduleWorkspaceStateSave(false);
  }
  function activateEmptyWorkspace(){
    clearWorkbenchCanvas();state.projectWorkbench=null;state.activeWorkbenchTab="";
    var projectName=state.activeProject&&state.activeProject.name||"새 프로젝트";
    state.templateDocumentHtml="<div class='doc-meta'><span>현재 프로젝트</span><span>"+new Date().toLocaleDateString("ko-KR")+"</span></div><h1>"+escapeHtml(projectName)+"</h1><p class='doc-subtitle'>프로젝트가 선택되었습니다. 오른쪽 대화창에서 첫 업무를 시작하세요.</p><section><h2>아직 기본 문서가 없습니다.</h2><p id='targetParagraph' data-report-editable>자료 조회나 보고서 작성을 요청하면 기본 MD 문서가 생성되고, 필요한 경우 양식을 적용한 파생 문서를 만들 수 있습니다.</p></section>";
    activateTemplateDocument({},projectName,null);state.documentStorageKey="aiworks.project."+state.activeProjectId+".empty";
    $("projectWorkbenchTabs").innerHTML="<span id='activeFileName' hidden>"+escapeHtml(projectName)+"</span><button class='active empty-project-tab' type='button'><span class='workbench-tab-icon'>＋</span><span>첫 문서 준비</span><small>프로젝트 선택됨</small></button>";
    configureEditorPlugin({filename:projectName,adapter:"output.text@1.0.0",workspace:{loadedMcps:["output.text@1.0.0"]}});updateWorkbenchSyncActions();setStatus(projectName+" · 첫 업무 요청 대기");
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
    var summary=state.projectWorkspace&&state.projectWorkspace.summary||{};
    $("sidebarContent").innerHTML="<div class='section-label'>현재 프로젝트</div><div class='project-sidebar-head'><b>"+escapeHtml(state.activeProject&&state.activeProject.name||state.activeProjectId)+"</b><button id='sidebarChangeProject'>변경</button></div><div class='file-tree'><button class='tree-row' id='projectMetadataRow'><span>◇</span>프로젝트 메타정보 <small>"+Number(summary.factCount||0)+"</small></button></div><div class='section-label'>프로젝트 기본 문서</div><div class='file-tree'>"+(projectDocuments||"<div class='sidebar-empty'>프로젝트 문서 없음</div>")+"</div><div class='sidebar-stat'><div><span>기본 MD 문서</span><b>"+Number(summary.documentCount||0)+"개</b></div><div><span>프로젝트 메타정보</span><b>"+Number(summary.factCount||0)+"개</b></div></div>";
    $("sidebarChangeProject").onclick=requestProjectChange;
    $("projectMetadataRow").onclick=function(){if(state.projectWorkbench)switchProjectWorkbenchTab("metadata");else{setView("data");loadProjectFacts(true)}};
    document.querySelectorAll("[data-project-workbench]").forEach(function(button){button.onclick=function(){openProjectWorkbench(button.dataset.projectWorkbench,"markdown")}});
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
      if(saved){state.sourceEditorDirty=false;await refreshProjectWorkbench();updateDocumentSaveState("MD r"+state.projectWorkbench.document.revision+" 저장됨 · 파생 문서는 명시적 반영 필요",false);updateWorkbenchSyncActions()}
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
      var module=await import("/poc/aiworks/vendor/rhwp-editor/index.js?v=embedded-recovery-1");
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
        if(session.projectSync&&session.projectSync.status==="failed")updateDocumentSaveState("MD 저장됨 · 파생 문서 탭 갱신 실패",false);else updateDocumentSaveState("MD 저장됨 · 파생 문서는 명시적 반영 필요",false);
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
      setStatus(committed?"파생 문서 작업본 저장 완료":"문서 초안 저장 완료");
      toast(committed?"직접 편집한 파생 문서 작업본을 저장했습니다.":"문서 편집 내용을 저장했습니다.");
      addAudit("사용자",committed?"파생 문서 직접 편집 저장":"문서 초안 저장","완료");
      return true;
    }catch(error){updateDocumentSaveState("저장 실패 · 다시 시도",true);setStatus("문서 저장 실패");toast(error.message);return false}
  }
  function saveDocumentChanges(){
    if(state.documentSaveInFlight)return state.documentSaveInFlight;
    state.documentSaveInFlight=performDocumentSave().finally(function(){state.documentSaveInFlight=null});
    return state.documentSaveInFlight;
  }
  async function loadTemplateMcps(force){
    if(state.templateMcpsLoaded&&!force)return state.templateMcps;
    var result=await api("/template-mcps");state.templateMcps=result.items||[];state.templateMcpsLoaded=true;return state.templateMcps;
  }
  function appliedTemplateRef(artifact){
    var explicit=String(artifact&&artifact.templateId||"");if(explicit)return explicit;
    var renderer=String(artifact&&artifact.renderer||"");
    return state.templateMcps.some(function(item){return item.packageRef===renderer})?renderer:"";
  }
  function defaultTemplateUsage(item){
    var name=item&&item.name||"양식 MCP",triggers=item&&item.triggerExamples||[],quick=triggers[0]||("현재 문서를 "+name+"으로 바꿔줘");
    return{contractVersion:"template-mcp-usage/1.0",quickPrompt:quick,prerequisites:["작업할 프로젝트를 선택합니다.","프로젝트 안에 기준이 되는 Markdown 문서가 있어야 합니다.","사용할 양식 MCP가 Store에 설치되어 있어야 합니다."],directSteps:["문서 내용 탭에서 완성 문서를 만들거나 기존 완성 문서 탭을 엽니다.","상단 양식 콤보에서 이 양식 MCP를 선택합니다.","현재 MD 내용으로 새 HWPX 완성 문서가 생성되면 검토 후 내보냅니다."],chatSteps:["오른쪽 AI 업무 오케스트레이터에 호출 문구를 입력합니다.","실행 계획에서 데이터·보고서·양식 MCP와 사용 이유를 확인합니다.","승인 후 생성된 완성 문서를 RHWP에서 확인합니다."],result:"프로젝트 MD는 내용 원본으로 유지되고, 선택 양식을 적용한 HWPX는 완성 문서와 내보낸 파일로 저장됩니다.",notes:["양식을 바꿔도 MD 원본과 이전 내보낸 파일은 유지됩니다.","RHWP 수정 내용을 MD에 반영하려면 ‘파생 문서 → MD 반영’을 명시적으로 실행합니다."]};
  }
  function templateUsageEntry(packageRef){
    var installed=(state.templateMcps||[]).find(function(item){return item.packageRef===packageRef});
    if(installed)return Object.assign({installed:true},installed);
    var parts=String(packageRef||"").split("@"),store=(state.mcps||[]).find(function(item){return item.id===parts[0]&&(!parts[1]||item.version===parts[1])});
    if(!store)return null;
    return{packageId:store.id,version:store.version,packageRef:store.id+"@"+store.version,name:store.name,description:store.desc,mcpType:"template",triggerExamples:[],sourceFilename:null,installed:Boolean(store.installedVersion),usage:null};
  }
  function usageOrderedList(items){
    return"<ol>"+(items||[]).map(function(step){return"<li>"+escapeHtml(step)+"</li>"}).join("")+"</ol>";
  }
  function renderTemplateUsageGuide(item){
    var dialog=$("templateUsageDialog"),body=$("templateUsageBody");if(!dialog||!body)return;
    var usage=item&&item.usage||defaultTemplateUsage(item),installed=Boolean(item&&((state.templateMcps||[]).some(function(candidate){return candidate.packageRef===item.packageRef}))),store=(state.mcps||[]).find(function(candidate){return item&&candidate.id===item.packageId});
    var options=(state.templateMcps||[]).map(function(candidate){return"<option value='"+escapeHtml(candidate.packageRef)+"' "+(item&&candidate.packageRef===item.packageRef?"selected":"")+">"+escapeHtml(candidate.name)+" · v"+escapeHtml(candidate.version)+"</option>"}).join("");
    if(item&&!installed)options="<option value='"+escapeHtml(item.packageRef)+"' selected>"+escapeHtml(item.name)+" · 설치 필요</option>"+options;
    var projectReady=Boolean(state.activeProjectId),documentReady=Boolean(state.projectWorkbench&&state.projectWorkbench.document),checks=[{label:"프로젝트 선택",ready:projectReady},{label:"MD 문서 준비",ready:documentReady},{label:"양식 MCP 설치",ready:installed}];
    body.innerHTML="<label class='template-usage-select'><span>안내할 양식</span><select id='templateUsageSelect'>"+(options||"<option value=''>설치된 양식 MCP 없음</option>")+"</select></label>"+(!item?"<div class='template-usage-empty'><b>먼저 양식 MCP를 설치하세요.</b><p>Store에서 양식 MCP의 권한을 확인하고 설치하면 여기에서 실제 호출 문구와 적용 순서를 확인할 수 있습니다.</p></div>":"<section class='template-usage-summary'><div><span class='type-chip'>"+(installed?"설치됨":"설치 필요")+"</span><h3>"+escapeHtml(item.name)+"</h3><p>"+escapeHtml(item.description||"등록된 HWPX 서식을 현재 Markdown 문서에 적용합니다.")+"</p></div><dl><div><dt>고정 버전</dt><dd>"+escapeHtml(item.packageRef)+"</dd></div><div><dt>양식 원본</dt><dd>"+escapeHtml(item.sourceFilename||"패키지 원본 확인 필요")+"</dd></div></dl></section><div class='template-usage-checks'>"+checks.map(function(check){return"<span class='"+(check.ready?"ready":"pending")+"'><i>"+(check.ready?"✓":"!")+"</i>"+escapeHtml(check.label)+"</span>"}).join("")+"</div><div class='template-usage-flow'><b>실제 변환 흐름</b><span>프로젝트 MD 원본</span><i>→</i><span>"+escapeHtml(item.name)+"</span><i>→</i><span>HWPX 완성 문서</span><i>→</i><span>내보낸 파일</span></div><div class='template-usage-modes'><article><span class='usage-number'>1</span><h4>양식 콤보로 바로 적용</h4>"+usageOrderedList(usage.directSteps)+"</article><article><span class='usage-number'>2</span><h4>대화로 호출</h4><code>"+escapeHtml(usage.quickPrompt)+"</code>"+usageOrderedList(usage.chatSteps)+"</article></div><section class='template-usage-result'><b>적용 결과</b><p>"+escapeHtml(usage.result)+"</p><ul>"+(usage.notes||[]).map(function(note){return"<li>"+escapeHtml(note)+"</li>"}).join("")+"</ul></section>");
    dialog.dataset.packageRef=item&&item.packageRef||"";
    var selector=$("templateUsageSelect");if(selector)selector.onchange=function(){renderTemplateUsageGuide(templateUsageEntry(this.value))};
    $("templateUsageChat").disabled=!item;
    $("templateUsageApply").disabled=!item||!installed||!documentReady;
    $("templateUsageApply").title=!documentReady?"프로젝트 MD 문서를 먼저 만드세요.":!installed?"Store에서 이 양식 MCP를 먼저 설치하세요.":"현재 MD를 이 양식으로 즉시 변환합니다.";
    $("templateUsageEdit").disabled=!store;
  }
  async function openTemplateMcpUsage(packageRef){
    try{
      await loadTemplateMcps(false);
      var selectedRef=packageRef||$("templateMcpSelect")&&$("templateMcpSelect").value||(state.templateMcps[0]&&state.templateMcps[0].packageRef)||"";
      var item=templateUsageEntry(selectedRef)||(state.templateMcps[0]?Object.assign({installed:true},state.templateMcps[0]):null);
      renderTemplateUsageGuide(item);
      if(!$("templateUsageDialog").open)$("templateUsageDialog").showModal();
    }catch(error){toast("양식 MCP 사용 안내를 불러오지 못했습니다: "+error.message)}
  }
  async function renderTemplateMcpSelector(artifact){
    var control=$("templateMcpControl"),select=$("templateMcpSelect"),help=$("templateMcpHelp");if(!control||!select)return;
    if(!state.projectWorkbench||state.activeWorkbenchTab!=="artifact:hwpx"){control.hidden=true;if(help)help.hidden=true;return}
    control.hidden=false;if(help)help.hidden=false;select.disabled=true;select.innerHTML="<option value=''>양식 불러오는 중</option>";
    try{
      await loadTemplateMcps(false);
      var current=appliedTemplateRef(artifact),known=state.templateMcps.some(function(item){return item.packageRef===current}),options=[];
      if(current&&!known)options.push("<option value='"+escapeHtml(current)+"' selected>현재 적용 · "+escapeHtml(current)+"</option>");
      if(!current)options.push("<option value='' selected>양식 MCP 선택</option>");
      state.templateMcps.forEach(function(item){options.push("<option value='"+escapeHtml(item.packageRef)+"' "+(item.packageRef===current?"selected":"")+">"+escapeHtml(item.name)+" · v"+escapeHtml(item.version)+"</option>")});
      if(!options.length)options.push("<option value='' selected>설치된 양식 MCP 없음</option>");
      select.innerHTML=options.join("");select.disabled=state.templateSwitchInFlight||!state.templateMcps.length;
      select.title=current?"현재 적용 양식: "+current:"Store에 설치된 양식 MCP를 선택하면 현재 MD로 즉시 변환합니다.";
      select.onchange=function(){if(this.value&&this.value!==current)applyTemplateMcpImmediately(this.value,current);else this.value=current};
    }catch(error){select.innerHTML="<option value=''>양식 목록 로딩 실패</option>";select.disabled=true;select.title=error.message}
  }
  async function applyTemplateMcpImmediately(packageRef,previousRef){
    if(state.templateSwitchInFlight||!state.projectWorkbench)return;
    var select=$("templateMcpSelect"),selected=state.templateMcps.find(function(item){return item.packageRef===packageRef});
    try{
      state.templateSwitchInFlight=true;if(select)select.disabled=true;
      if(state.rhwpEditor&&!await saveDocumentChanges())throw new Error("현재 완성 문서를 저장하지 못해 양식 변경을 중단했습니다.");
      var workbench=await refreshProjectWorkbench(),documentData=workbench.document,artifact=(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"});
      if(artifact&&artifact.status==="diverged"&&!window.confirm("완성 문서에 아직 문서 원본으로 반영하지 않은 수정이 있습니다. 새 양식을 적용하면 현재 MD 내용으로 완성 문서를 다시 만듭니다. 기존 내보낸 파일은 유지됩니다. 계속할까요?")){if(select)select.value=previousRef||appliedTemplateRef(artifact);return}
      setStatus((selected&&selected.name||packageRef)+" 양식 적용 중");updateOrchestration("양식 MCP 즉시 전환 · "+(selected&&selected.name||packageRef),"active");
      var rendered=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+documentData.id+"/render",{method:"POST",body:JSON.stringify({format:"hwpx",template_package_ref:packageRef,instruction:(selected&&selected.name||packageRef)+" 양식 MCP 적용",preserve_layout:false,structural_render:true,force:true,actor:"workspace-user"})});
      clearWorkbenchTabCache();clearWorkbenchCanvas();state.projectWorkbench=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+documentData.id+"/workbench");state.activeWorkbenchTab="artifact:hwpx";renderProjectWorkbenchTabs();
      rendered.artifact.content=documentData.markdown;await openGeneratedArtifact(rendered.artifact,["document.markdown@1.0.0",packageRef,"document.rhwp@1.0.0"]);
      var applied=(state.projectWorkbench.artifacts||[]).find(function(item){return item.format==="hwpx"});await renderTemplateMcpSelector(applied);
      api("/projects/"+encodeURIComponent(state.activeProjectId)+"/decisions",{method:"POST",body:JSON.stringify({conversation_id:state.activeConversationId||undefined,decision_type:"template-selection",status:"accepted",summary:"완성 문서 양식을 "+(selected&&selected.name||packageRef)+"로 선택",scope:{templatePackageRef:packageRef,documentId:documentData.id,revision:documentData.revision},document_id:documentData.id,document_version_id:documentData.versionId,actor:"workspace-user"})}).catch(function(){});
      updateOrchestration("양식 MCP 전환 완료 · "+(selected&&selected.name||packageRef),"done");setStatus("현재 양식 · "+(selected&&selected.name||packageRef));toast("'"+(selected&&selected.name||packageRef)+"' 양식으로 변환했습니다.");scheduleWorkspaceStateSave(false);
    }catch(error){if(select)select.value=previousRef||"";updateOrchestration("양식 MCP 전환 실패","error");setStatus("양식 변경 실패");toast(error.message)}finally{state.templateSwitchInFlight=false;if(select)select.disabled=!state.templateMcps.length}
  }
  async function syncMarkdownToHwpx(){
    if(!state.projectWorkbench)return;
    try{
      if(state.sourceEditorDirty&&!await saveDocumentChanges())return;
      var workbench=await refreshProjectWorkbench(),documentData=workbench.document,artifact=(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"});
      if(artifact&&artifact.status==="diverged"&&!window.confirm("파생 문서에 아직 MD로 반영하지 않은 변경이 있습니다. 현재 MD로 파생 문서를 다시 만들면 그 변경이 대체됩니다. 계속할까요?"))return;
      setStatus("MD r"+documentData.revision+" → 양식 MCP → 파생 문서 생성 중");updateOrchestration("MD → 파생 문서 반영","active");
      await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+documentData.id+"/render",{method:"POST",body:JSON.stringify({format:"hwpx",instruction:(artifact&&artifact.instruction)||"표준 보고서 양식으로 변환",preserve_layout:true,structural_render:true,force:true,actor:"workspace-user"})});
      await refreshProjectWorkbench();updateWorkbenchSyncActions();updateOrchestration("MD → 파생 문서 반영 완료","done");setStatus("파생 문서 생성 완료 · MD r"+state.projectWorkbench.document.revision);toast("현재 MD를 파생 문서에 반영했습니다.");scheduleWorkspaceStateSave(false);
    }catch(error){updateOrchestration("MD → 파생 문서 반영 실패","error");toast(error.message)}
  }
  async function syncHwpxToMarkdown(){
    if(!state.projectWorkbench)return;
    try{
      if(state.rhwpEditor&&!await saveDocumentChanges())return;
      var workbench=await refreshProjectWorkbench(),artifact=(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"&&item.id});
      if(!artifact)throw new Error("MD로 반영할 파생 문서가 없습니다.");
      setStatus("파생 문서 변경점 분석 → MD 새 revision 준비 중");updateOrchestration("파생 문서 → MD 반영","active");
      var promoted=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+workbench.document.id+"/artifacts/"+artifact.id+"/promote-markdown",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});
      await refreshProjectWorkbench();updateWorkbenchSyncActions();updateOrchestration("파생 문서 → MD 반영 완료","done");setStatus("MD r"+promoted.document.revision+" 생성 완료 · 파생 문서와 동기화됨");toast("파생 문서 변경을 MD 새 revision으로 반영했습니다.");scheduleWorkspaceStateSave(false);
    }catch(error){updateOrchestration("파생 문서 → MD 반영 실패","error");toast(error.message)}
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

  async function loadProjectSources(render){
    if(!state.activeProjectId)return;
    var data=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/sources");state.projectSources=data.items||[];
    var available=new Set(state.projectSources.map(function(item){return item.id}));state.selectedProjectSourceIds=state.selectedProjectSourceIds.filter(function(id){return available.has(id)});
    if(!state.selectedProjectSourceIds.length)state.selectedProjectSourceIds=state.projectSources.map(function(item){return item.id});
    if(state.projectWorkspace&&state.projectWorkspace.summary)state.projectWorkspace.summary.sourceCount=state.projectSources.length;
    if(render!==false)renderProjectSources();updateProjectContext();
  }
  function renderProjectSources(){
    var host=$("projectSourceList");if(!host)return;
    host.innerHTML=state.projectSources.length?state.projectSources.map(function(item){var selected=state.selectedProjectSourceIds.indexOf(item.id)>=0;return"<article class='project-source-card'><label><input type='checkbox' data-source-select='"+item.id+"' "+(selected?"checked":"")+"><span class='source-kind'>"+escapeHtml(String(item.kind||"file").toUpperCase())+"</span><span><b>"+escapeHtml(item.filename||item.title)+"</b><small>검색 "+Number(item.chunkCount||0)+"개 · v"+Number(item.version||1)+" · "+Math.max(1,Math.round(Number(item.bytes||0)/1024))+"KB</small></span></label><p>"+escapeHtml(item.excerpt||"검색 가능한 텍스트가 인덱싱되었습니다.")+"</p><footer><button data-source-reindex='"+item.id+"'>검색 다시 구성</button><button class='danger-text' data-source-delete='"+item.id+"'>자료 삭제</button></footer></article>"}).join(""):"<div class='empty-reference'><b>아직 프로젝트 자료가 없습니다.</b><p>PDF·HWPX·DOCX·XLSX·MD·TXT를 추가하면 로컬 검색 인덱스를 만들고 다음 AI 작업의 근거로 사용합니다.</p></div>";
    host.querySelectorAll("[data-source-select]").forEach(function(input){input.onchange=function(){state.selectedProjectSourceIds=Array.from(host.querySelectorAll("[data-source-select]:checked")).map(function(node){return node.dataset.sourceSelect});updateProjectContext()}});
    host.querySelectorAll("[data-source-delete]").forEach(function(button){button.onclick=function(){deleteProjectSource(button.dataset.sourceDelete)}});host.querySelectorAll("[data-source-reindex]").forEach(function(button){button.onclick=function(){reindexProjectSource(button.dataset.sourceReindex)}});
  }
  async function uploadProjectSourceFiles(files){var list=Array.from(files||[]),added=[];for(var index=0;index<list.length;index+=1){var file=list[index];setStatus("프로젝트 자료 분석 중 · "+file.name+" ("+(index+1)+"/"+list.length+")");var result=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/sources",{method:"POST",body:JSON.stringify({filename:file.name,content_base64:await fileBase64(file),classification:"internal",actor:"workspace-user"})});added.push(result.source)}await loadProjectSources(true);if(added.length){setStatus("프로젝트 자료 "+added.length+"개 등록 완료");toast("자료를 저장하고 검색 인덱스를 구성했습니다.")}return added}
  async function deleteProjectSource(sourceId){var source=state.projectSources.find(function(item){return item.id===sourceId});if(!source||!window.confirm("'"+(source.filename||source.title)+"' 자료를 프로젝트에서 삭제할까요? 문서와 완성 파일은 삭제하지 않습니다."))return;try{await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/sources/"+sourceId,{method:"DELETE",body:JSON.stringify({actor:"workspace-user"})});await loadProjectSources(true);toast("프로젝트 자료를 삭제했습니다.")}catch(error){toast(error.message)}}
  async function reindexProjectSource(sourceId){try{setStatus("자료 검색 다시 구성 중");await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/sources/"+sourceId+"/reindex",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});await loadProjectSources(true);toast("검색 인덱스를 새 버전으로 갱신했습니다.")}catch(error){toast(error.message)}}

  function renderData(){
    var rows=state.commonData.map(function(item){
      return "<tr data-key='"+escapeHtml(item.key)+"'><td><b>"+escapeHtml(item.label)+"</b><br><small>"+escapeHtml(item.key)+"</small></td><td>"+escapeHtml(item.value)+"</td><td><span class='type-chip'>"+escapeHtml(item.kind)+"</span></td><td>"+escapeHtml(item.date)+"</td><td><button class='inline-link source-button'>"+escapeHtml(item.source)+"</button></td><td class='confidence'>"+item.confidence+"%</td></tr>";
    }).join("");
    $("dataView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>PROJECT SOURCES</span><h1>자료와 기준정보</h1><p>업무 자료를 프로젝트에 저장하고 체크한 자료만 다음 AI 작업의 검색 근거로 사용합니다.</p></div><div class='module-actions'><button id='refreshKnowledge'>새로고침</button><button class='primary' id='addSourceButton'>＋ 자료 추가</button><input id='projectSourceInput' type='file' multiple accept='.pdf,.hwpx,.docx,.odt,.xlsx,.md,.txt' hidden><button id='addDataButton'>＋ 기준정보</button></div></div><section class='surface project-sources-surface'><div class='surface-head'><h2>프로젝트 자료</h2><small>원본은 프로젝트에 영속 저장되며 검색은 로컬에서 구성됩니다.</small></div><div class='project-source-list' id='projectSourceList'>자료를 불러오는 중입니다.</div></section><details class='advanced-data'><summary>고급: 문서·기준정보·지식 관계 관리</summary><section class='surface'><div class='surface-head'><h2>프로젝트 Markdown 원본</h2><small>내용 원본 · 양식과 분리</small></div><div class='store-grid' id='projectMarkdownList'>문서 목록을 불러오는 중입니다.</div></section><div class='cards'><div class='metric-card'><span>지식 노드</span><b id='knowledgeNodeCount'>-</b><small>문서·데이터·노트</small></div><div class='metric-card'><span>출처 연결</span><b id='knowledgeSourceCount'>-</b><small>근거 없는 답변 차단</small></div><div class='metric-card'><span>관계</span><b id='knowledgeEdgeCount'>-</b><small>출처·활용 연결</small></div></div><section class='surface'><div class='surface-head'><h2>출처 기반 질의응답</h2><small>내부 데이터 · 로컬 검색</small></div><div class='knowledge-query'><input id='knowledgeQuestion' placeholder='프로젝트 기준정보와 연결된 근거를 질문하세요'><input id='knowledgeAsOf' type='date'><button class='primary' id='askKnowledge'>근거 찾기</button></div><div class='knowledge-answer' id='knowledgeAnswer'>질문하면 답변과 원문 위치가 함께 표시됩니다.</div></section><section class='surface'><div class='surface-head'><h2>프로젝트 확정 기준정보</h2><small>Markdown과 별도 관리</small></div><table class='data-table'><thead><tr><th>항목</th><th>현재 값</th><th>유형</th><th>기준일</th><th>출처 위치</th><th>신뢰도</th></tr></thead><tbody>"+rows+"</tbody></table></section><section class='surface' id='knowledgeComparison'><div class='surface-head'><h2 id='knowledgeComparisonTitle'>기준정보 시점 비교</h2><small id='knowledgeDelta'>비교 가능한 데이터를 확인 중입니다.</small></div><div class='timeline' id='knowledgeTimeline'></div></section><section class='surface'><div class='surface-head'><h2>지식 관계</h2><small>노트 ↔ 기준정보 ↔ 원문</small></div><div class='knowledge-grid' id='knowledgeGraph'>그래프를 불러오는 중입니다.</div></section></details></div>";
    document.querySelectorAll(".source-button").forEach(function(button){button.onclick=function(){toast("원문 위치를 열었습니다: "+button.textContent);setView("editor")}});
    $("addDataButton").onclick=addProjectFact;
    $("refreshKnowledge").onclick=function(){loadKnowledgeGraph(true)};
    $("addSourceButton").onclick=function(){$("projectSourceInput").click()};
    $("projectSourceInput").onchange=async function(){try{await uploadProjectSourceFiles(this.files)}catch(error){toast(error.message)}finally{this.value=""}};
    $("askKnowledge").onclick=askKnowledge;
    $("knowledgeQuestion").onkeydown=function(event){if(event.key==="Enter")askKnowledge()};
    renderProjectSources();loadKnowledgeGraph(false);loadKnowledgeComparison();loadProjectFacts();loadProjectDocuments();
  }

  function utf8Base64(value){var bytes=new TextEncoder().encode(String(value||"")),binary="";bytes.forEach(function(byte){binary+=String.fromCharCode(byte)});return btoa(binary)}
  async function loadProjectDocuments(){
    var host=$("projectMarkdownList");if(!host)return;
    try{
      var data=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents");state.projectDocuments=data.items||[];
      host.innerHTML=state.projectDocuments.length?state.projectDocuments.map(function(item){return"<article class='store-card "+(item.duplicateOf?"duplicate-document":"")+"'><div class='store-card-head'><span class='mcp-logo'>MD</span><div><h3>"+escapeHtml(item.title)+"</h3><div class='store-meta'><span>revision "+item.revision+"</span><span>"+escapeHtml(item.source.format)+"</span>"+(item.duplicateOf?"<span>내용 중복</span>":"")+"</div></div></div><p>"+escapeHtml(item.excerpt)+"</p><footer><button data-open-md='"+item.id+"'>MD 열기</button><button class='primary' data-render-md='"+item.id+"'>파생 문서 만들기</button>"+(item.duplicateOf?"<button data-archive-duplicate='"+item.id+"' data-canonical='"+item.duplicateOf+"'>중복 보관</button>":"")+"</footer></article>"}).join(""):"<p class='empty-reference'>파일을 첨부하거나 보고서를 생성하면 프로젝트 기본 MD 문서가 여기에 저장됩니다.</p>";
      host.querySelectorAll("[data-open-md]").forEach(function(button){button.onclick=function(){openProjectMarkdown(button.dataset.openMd)}});
      host.querySelectorAll("[data-render-md]").forEach(function(button){button.onclick=function(){renderProjectMarkdown(button.dataset.renderMd)}});
      host.querySelectorAll("[data-archive-duplicate]").forEach(function(button){button.onclick=function(){archiveDuplicateMarkdown(button.dataset.archiveDuplicate,button.dataset.canonical)}});
    }catch(error){host.textContent=error.message}
  }
  async function archiveDuplicateMarkdown(documentId,canonicalId){
    if(!window.confirm("내용 SHA-256이 같은 중복 Markdown을 보관할까요? revision과 문서별 작업본·최종 산출물은 삭제하지 않고 보존됩니다."))return;
    try{
      await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/status",{method:"POST",body:JSON.stringify({action:"archive",document_ids:[documentId],canonical_document_id:canonicalId,actor:"workspace-user"})});
      if(state.projectWorkbench&&state.projectWorkbench.document.id===documentId)await openProjectWorkbench(canonicalId,"markdown");
      await loadProjectDocuments();toast("중복 Markdown을 삭제하지 않고 보관했습니다.");
    }catch(error){toast(error.message)}
  }
  function workbenchStatusLabel(status){return({synced:"최신",stale:"완성 문서 다시 만들기 필요",diverged:"완성 문서에서 수정됨",rendering:"완성 문서 만드는 중",failed:"생성 실패",missing:"완성 문서 없음"})[status]||status||"-"}
  function renderProjectWorkbenchTabs(){
    var host=$("projectWorkbenchTabs"),workbench=state.projectWorkbench;if(!host||!workbench)return;
    var documentData=workbench.document,artifacts=workbench.artifacts||[],outputs=workbench.outputs||[];
    var openConflicts=(workbench.conflicts||[]).filter(function(item){return item.status==="open"}),buttons=[{id:"markdown",icon:"MD",label:"문서 내용",status:"r"+documentData.revision}].concat(artifacts.map(function(item){return{id:"artifact:"+item.format,icon:"문",label:"완성 문서",status:workbenchStatusLabel(item.status)}})).concat([{id:"outputs",icon:"✓",label:"내보낸 파일",status:String(outputs.length)},{id:"metadata",icon:"◇",label:"기준정보",status:String((workbench.factCounts.confirmed||0)+(workbench.factCounts.candidate||0))},{id:"history",icon:"≡",label:"변경 이력",status:openConflicts.length?"!"+openConflicts.length:String((workbench.events||[]).length)}]);
    var options=state.projectDocuments.map(function(item){return"<option value='"+escapeHtml(item.id)+"' "+(item.id===documentData.id?"selected":"")+">"+escapeHtml(item.title)+" · r"+Number(item.revision||0)+"</option>"}).join("");
    host.innerHTML="<span id='activeFileName' hidden>"+escapeHtml(documentData.title)+"</span><label class='project-document-switcher'><span>프로젝트 문서</span><select id='projectDocumentSwitcher'>"+options+"</select></label>"+buttons.map(function(item){return"<button data-workbench-tab='"+escapeHtml(item.id)+"' class='"+(state.activeWorkbenchTab===item.id?"active":"")+"'><span class='workbench-tab-icon'>"+escapeHtml(item.icon)+"</span><span>"+escapeHtml(item.label)+"</span><small>"+escapeHtml(item.status)+"</small></button>"}).join("");
    $("projectDocumentSwitcher").onchange=function(){openProjectWorkbench(this.value,"markdown")};
    host.querySelectorAll("[data-workbench-tab]").forEach(function(button){button.onclick=function(){switchProjectWorkbenchTab(button.dataset.workbenchTab)}});
    updateWorkbenchSyncActions();
  }
  function updateWorkbenchSyncActions(){
    var mdButton=$("syncMdToHwpx"),hwpxButton=$("syncHwpxToMd"),downloadButton=$("downloadProjectHwpx"),templateControl=$("templateMcpControl"),templateHelp=$("templateMcpHelp"),workbench=state.projectWorkbench;if(!mdButton||!hwpxButton)return;
    var artifact=workbench&&(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"});
    mdButton.hidden=!(workbench&&state.activeWorkbenchTab==="markdown");
    hwpxButton.hidden=!(workbench&&state.activeWorkbenchTab==="artifact:hwpx"&&artifact&&artifact.id);
    if(downloadButton)downloadButton.hidden=!(workbench&&state.activeWorkbenchTab==="artifact:hwpx"&&artifact&&artifact.id);
    if(templateControl)templateControl.hidden=!(workbench&&state.activeWorkbenchTab==="artifact:hwpx");
    mdButton.textContent=artifact&&artifact.id?"완성 문서 다시 만들기" : "완성 문서 만들기";
    if(templateHelp)templateHelp.hidden=!(workbench&&state.activeWorkbenchTab==="artifact:hwpx");
    mdButton.classList.toggle("primary",Boolean(artifact&&artifact.status==="stale"||artifact&&artifact.status==="missing"));
    hwpxButton.textContent=artifact&&artifact.status==="diverged"?"수정 내용을 문서 원본에 반영":"문서 원본에 반영";
    hwpxButton.classList.toggle("primary",Boolean(artifact&&artifact.status==="diverged"));
  }
  async function downloadProjectHwpx(){
    if(!state.projectWorkbench)return;
    try{
      if(state.rhwpEditor&&!await saveDocumentChanges())return;
      var workbench=await refreshProjectWorkbench(),artifact=(workbench.artifacts||[]).find(function(item){return item.format==="hwpx"&&item.id});
      if(!artifact)throw new Error("다운로드할 파생 문서가 없습니다.");
      var detail=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+workbench.document.id+"/artifacts/"+artifact.id);
      downloadBase64(detail.filename||workbench.document.title+".hwpx",detail.contentBase64);
      setStatus("파생 문서 다운로드 시작 · "+(detail.filename||""));
      toast("현재 양식과 Markdown 계층이 적용된 파생 문서를 다운로드합니다.");
      addAudit("사용자","파생 문서 다운로드 · "+(detail.filename||""),"완료");
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
    if(entry.paper&&entry.paper.isConnected)entry.paper.remove();
    delete state.workbenchTabCache[key];state.workbenchTabCacheOrder=state.workbenchTabCacheOrder.filter(function(item){return item!==key});
  }
  function clearWorkbenchTabCache(){
    Object.keys(state.workbenchTabCache).forEach(discardWorkbenchTabCache);state.workbenchTabCache={};state.workbenchTabCacheOrder=[];
  }
  function cacheCurrentWorkbenchTab(){
    var tab=state.activeWorkbenchTab;
    if(!state.projectWorkbench||!state.nativeSession||tab!=="markdown")return false;
    var key=workbenchTabCacheKey(tab),paper=$("documentPaper"),parent=paper.parentElement;
    discardWorkbenchTabCache(key);
    paper.removeAttribute("id");paper.hidden=true;paper.dataset.cachedWorkbenchTab=tab;
    var replacement=document.createElement("article");replacement.id="documentPaper";replacement.className="paper";replacement.setAttribute("aria-label","직접 편집 가능한 문서");parent.insertBefore(replacement,paper.nextSibling);
    state.workbenchTabCache[key]={
      paper:paper,editor:state.rhwpEditor,session:state.nativeSession,selection:state.nativeSelection,
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
    var current=$("documentPaper"),paper=entry.paper;clearWorkbenchCanvas();current.remove();paper.id="documentPaper";paper.hidden=false;delete paper.dataset.cachedWorkbenchTab;paper.className=entry.paperClass;
    var restored=tab==="markdown"?Boolean(paper.querySelector("#sourceEditor")):Boolean(paper.querySelector("#rhwpEditorHost")||paper.querySelector("[data-native-target]"));
    if(!restored){
      if(entry.editor)try{entry.editor.destroy()}catch(_error){}
      paper.remove();var replacement=document.createElement("article");replacement.id="documentPaper";replacement.className="paper";replacement.setAttribute("aria-label","직접 편집 가능한 문서");document.querySelector(".document-stage").appendChild(replacement);
      delete state.workbenchTabCache[key];state.workbenchTabCacheOrder=state.workbenchTabCacheOrder.filter(function(item){return item!==key});return false;
    }
    state.rhwpEditor=entry.editor;state.nativeSession=entry.session;state.nativeSelection=entry.selection;state.sourceEditorDirty=false;
    $("workbench").classList.toggle("native-rhwp-mode",entry.nativeRhwp);document.querySelector(".app-shell").classList.toggle("native-rhwp-shell",entry.shellRhwp);
    delete state.workbenchTabCache[key];state.workbenchTabCacheOrder=state.workbenchTabCacheOrder.filter(function(item){return item!==key});
    configureEditorPlugin(entry.session);configureNativeToolbar(entry.session,false);updateDocumentSaveState("캐시된 편집 세션 r"+entry.session.revision+" · 재마운트 없음",false);
    if(state.rhwpEditor)configureRhwpToolboxes(state.rhwpEditor);
    else if(paper.querySelector("[data-native-target]"))ensureNativeMcpPanel();
    return true;
  }

  function clearWorkbenchCanvas(){
    clearTimeout(state.workbenchAutoSaveTimer);
    if(state.rhwpEditor){var editor=state.rhwpEditor;state.rhwpEditor=null;try{editor.destroy()}catch(_error){}}
    if(state.nativePreviewUrl){URL.revokeObjectURL(state.nativePreviewUrl);state.nativePreviewUrl=null}
    state.nativeSession=null;state.nativeSelection=null;state.sourceEditorDirty=false;
    $("workbench").classList.remove("native-rhwp-mode");document.querySelector(".app-shell").classList.remove("native-rhwp-shell");
    ["nativeCompactTitle","aiSelectionMode"].forEach(function(id){var node=$(id);if(node)node.remove()});var panel=$("nativeMcpPanel");if(panel)panel.remove();
    var paper=$("documentPaper");paper.replaceChildren();paper.className="paper";
  }
  async function openWorkbenchMarkdown(){
    if(restoreWorkbenchTabCache("markdown")){setStatus("MD 원본 r"+state.projectWorkbench.document.revision+" · 캐시 복원 · 재마운트 없음");return}
    var documentData=state.projectWorkbench.document;
    var session=await api("/documents/sessions",{method:"POST",body:JSON.stringify({filename:documentData.title+".md",content_base64:utf8Base64(documentData.markdown),project_id:state.activeProjectId,markdown_document_id:documentData.id,markdown_base_revision:documentData.revision,intent:"프로젝트 Markdown 원본 편집",actor:"workspace-user"})});
    await renderNativeSession(session);setStatus("MD 원본 r"+documentData.revision+" · 자동 동기화 준비됨");
  }
  async function openWorkbenchArtifact(format){
    var workbench=state.projectWorkbench,documentData=workbench.document,artifact=(workbench.artifacts||[]).find(function(item){return item.format===format});
    await renderTemplateMcpSelector(artifact);
    if(artifact&&artifact.id&&restoreWorkbenchTabCache("artifact:"+format)){setStatus("파생 문서 작업본 · 캐시 복원 · 재마운트 없음");updateWorkbenchSyncActions();return}
    if(!artifact||!artifact.id){
      clearWorkbenchCanvas();$("documentPaper").className="paper workbench-info-paper";$("documentPaper").innerHTML="<div class='workbench-info-head'><span>DERIVED DOCUMENT</span><h1>아직 파생 문서가 없습니다.</h1><p>탭 이동만으로 문서를 만들지 않습니다. 현재 MD를 확인한 뒤 명시적으로 파생 문서를 생성하세요.</p><button class='primary' id='createDerivedHwpx'>MD → 파생 문서 생성</button></div>";$("createDerivedHwpx").onclick=syncMarkdownToHwpx;configureEditorPlugin({filename:documentData.title,adapter:"document.rhwp@1.0.0",workspace:{loadedMcps:["document.markdown@1.0.0","document.rhwp@1.0.0"]}});setStatus("파생 문서 생성 필요 · MD r"+documentData.revision);updateWorkbenchSyncActions();return;
    }
    setStatus("저장된 파생 문서 작업본 여는 중");
    var detail=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+documentData.id+"/artifacts/"+artifact.id);
    await openGeneratedArtifact({title:documentData.title,filename:detail.filename,format:detail.format,contentBase64:detail.contentBase64,content:documentData.markdown,markdownDocument:{id:documentData.id,versionId:documentData.versionId,revision:documentData.revision,markdownSha256:documentData.markdownSha256},projectArtifact:detail},["document.markdown@1.0.0","document.report-structure@0.1.0","template.report-style@0.1.0",detail.renderer||"document.report-hwpx@0.1.0","document.rhwp@1.0.0"]);
    setStatus("파생 문서 작업본 열림 · "+workbenchStatusLabel(artifact.status)+(artifact.status==="stale"?" · MD → 파생 문서 반영 필요":""));updateWorkbenchSyncActions();
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

  async function createPortableFinalOutput(format){
    var workbench=state.projectWorkbench;if(!workbench||!workbench.document)return;
    try{
      setStatus(format.toUpperCase()+" 최종 산출물 생성 중");
      var rendered=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+workbench.document.id+"/render",{method:"POST",body:JSON.stringify({format:format,instruction:"현재 Markdown을 "+format.toUpperCase()+" 최종 산출물로 생성",actor:"workspace-user"})});
      if(rendered.artifact&&rendered.artifact.contentBase64)downloadBase64(rendered.artifact.filename,rendered.artifact.contentBase64);
      await refreshProjectWorkbench();renderDocumentFinalOutputs();setStatus(format.toUpperCase()+" 최종 산출물 생성 완료");toast(format.toUpperCase()+" 파일을 생성하고 최종 산출물 저장소에 보관했습니다.");
    }catch(error){setStatus(format.toUpperCase()+" 산출물 생성 실패");toast(error.message)}
  }

  function renderDocumentFinalOutputs(){
    clearWorkbenchCanvas();var workbench=state.projectWorkbench,outputs=workbench.outputs||[];
    var items=outputs.map(function(item){var created=item.createdAt?new Date(item.createdAt).toLocaleString("ko-KR"):"-";return"<article><div><b>"+escapeHtml(item.filename)+"</b><p>MD r"+Number(item.sourceRevision||0)+" · "+escapeHtml(item.templateId||"양식 없음")+" · "+escapeHtml(item.renderer||"-")+"</p></div><time>"+escapeHtml(created)+"</time><button class='primary' data-download-output='"+escapeHtml(item.id)+"'>다운로드</button></article>"}).join("");
    $("documentPaper").className="paper workbench-info-paper";$("documentPaper").innerHTML="<div class='workbench-info-head'><span>DOCUMENT OUTPUT REPOSITORY</span><h1>최종 산출물</h1><p>현재 문서와 양식을 합쳐 만든 불변 파일입니다. 프로젝트 백업과 프로젝트 자산에는 포함되지 않습니다.</p></div><div class='workbench-history'>"+(items||"<p>아직 저장된 최종 산출물이 없습니다. MD → 파생 문서 생성을 실행하면 여기에 별도로 보관됩니다.</p>")+"</div>";
    $("documentPaper").querySelector(".workbench-info-head").insertAdjacentHTML("afterend","<div class='workbench-output-create'><b>다른 형식으로 만들기</b><span>MD 원본에서 의미 구조를 유지해 새 최종 산출물을 생성합니다.</span><div><button data-create-output='docx'>DOCX</button><button data-create-output='odt'>ODT</button><button data-create-output='pdf'>PDF</button><button data-create-output='xlsx'>XLSX</button></div></div>");
    $("documentPaper").querySelectorAll("[data-create-output]").forEach(function(button){button.onclick=function(){createPortableFinalOutput(button.dataset.createOutput)}});
    $("documentPaper").querySelectorAll("[data-download-output]").forEach(function(button){button.onclick=async function(){try{var detail=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+workbench.document.id+"/outputs/"+button.dataset.downloadOutput);downloadBase64(detail.filename,detail.contentBase64);toast("최종 산출물을 다운로드합니다.")}catch(error){toast(error.message)}}});
    configureEditorPlugin({filename:workbench.document.title,adapter:"document.output-repository@1.0.0",workspace:{loadedMcps:["document.markdown@1.0.0","document.output-repository@1.0.0"]}});
  }

  async function runCurrentDocumentQualityReview(){
    var workbench=state.projectWorkbench;if(!workbench||!workbench.document)return;
    var chat=captureProjectChat(),lastRequest="";for(var index=chat.length-1;index>=0;index--){if(chat[index].role==="user"){lastRequest=chat[index].text;break}}
    try{
      setStatus("현재 MD 품질 검토 중");
      var result=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+workbench.document.id+"/quality-review",{method:"POST",body:JSON.stringify({intent:lastRequest,actor:"workspace-user"})});
      var review=result.review||{},failures=(review.checks||[]).filter(function(check){return !check.passed});
      var dialog=document.createElement("dialog");dialog.className="quality-review-dialog";
      dialog.innerHTML="<form method='dialog' class='approval-card quality-review-card'><header><div><h2>MD 품질 검토</h2><small>점수 "+Math.round(Number(review.score||0)*100)+"% · 블록 "+Number(review.blockCount||0)+"개 · 요청·근거 대조</small></div><button value='cancel'>×</button></header><div class='quality-check-list'>"+((review.checks||[]).map(function(check){var blockIds=check.target&&check.target.blockIds||[];return"<label class='quality-check "+(check.passed?"passed":"failed")+"'><input type='checkbox' data-quality-check='"+escapeHtml(check.id)+"' "+(check.passed?"disabled":"checked")+"><span><b>"+(check.passed?"✓ ":"보완 · ")+escapeHtml(check.id)+"</b><small>"+escapeHtml(check.message)+(blockIds.length?" · 블록 "+escapeHtml(blockIds.join(", ")):"")+"</small></span></label>"}).join("")||"<p>검토 항목이 없습니다.</p>")+"</div><footer><button value='cancel'>닫기</button><button type='button' class='primary' id='repairSelectedQuality' "+(failures.length?"":"disabled")+">선택 항목 보완 계획 만들기</button></footer></form>";
      document.body.appendChild(dialog);dialog.addEventListener("close",function(){dialog.remove()});
      dialog.querySelector("#repairSelectedQuality").onclick=function(){var selected=Array.from(dialog.querySelectorAll("[data-quality-check]:checked")).map(function(node){return node.dataset.qualityCheck}),targets=(review.repairPlan||[]).filter(function(item){return selected.indexOf(item.checkId)>=0});if(!targets.length)return toast("보완할 항목을 선택해 주세요.");var instruction="현재 열린 Markdown 문서 ‘"+workbench.document.title+"’의 다음 품질 항목만 보완해줘. 선택되지 않은 블록과 확정된 수치·출처는 변경하지 말고 새 MD revision으로 저장해줘.\n"+targets.map(function(item){return"- "+item.checkId+": "+item.message+(item.blockIds&&item.blockIds.length?" (대상 블록: "+item.blockIds.join(", ")+")":" (문서 범위)")}).join("\n");dialog.close();setView("editor");$("chatInput").value=instruction;submitIntent(instruction)};
      dialog.showModal();setStatus(review.passed?"현재 MD 품질 검토 통과":"보완 후보 "+failures.length+"개");
    }catch(error){setStatus("MD 품질 검토 실패");toast(error.message)}
  }

  async function renderWorkbenchHistory(){
    clearWorkbenchCanvas();var workbench=state.projectWorkbench,openConflicts=(workbench.conflicts||[]).filter(function(item){return item.status==="open"}),decisionResult={items:[]};
    try{decisionResult=await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/decisions")}catch(_error){}
    var conflictHtml=openConflicts.length?"<section class='workbench-conflicts'><h2>해결 대기 충돌</h2>"+openConflicts.map(function(item){var changes=item.diffBlocks||[],diff=changes.length?"<div class='conflict-block-diff'><h3>반영할 HWPX 변경 블록 선택</h3>"+changes.map(function(change){return"<label><input type='checkbox' data-conflict-change='"+escapeHtml(change.id)+"' checked><span><b>"+escapeHtml(change.blockId||change.paragraphId||change.id)+"</b><del>"+escapeHtml(change.before||"(비어 있음)")+"</del><ins>"+escapeHtml(change.after||"(삭제)")+"</ins></span></label>"}).join("")+"</div>":"<p class='empty-reference'>블록 단위 매핑이 없어 전체 문서 기준으로만 선택할 수 있습니다.</p>";return"<article class='workbench-conflict-card' data-conflict-card='"+escapeHtml(item.id)+"'><div><b>MD와 파생 문서가 각각 변경됨</b><small>"+escapeHtml(item.id)+"</small></div>"+diff+"<details><summary>전체 문서 미리보기</summary><p><strong>파생 문서 변경 초안</strong>"+escapeHtml(item.source.excerpt||"내용 미리보기 없음")+"</p><p><strong>현재 MD</strong>"+escapeHtml(item.target.excerpt||"내용 미리보기 없음")+"</p></details><footer><button data-conflict-resolution='keep-markdown' data-conflict-id='"+escapeHtml(item.id)+"'>현재 MD 유지</button>"+(changes.length?"<button data-conflict-resolution='merge-selected' data-conflict-id='"+escapeHtml(item.id)+"'>선택 블록만 병합</button>":"")+"<button class='primary' data-conflict-resolution='use-hwpx' data-conflict-id='"+escapeHtml(item.id)+"'>파생 문서 전체 채택</button></footer></article>"}).join("")+"</section>":"";
    var graph=workbench.relationGraph||{},nodeNames={};(graph.nodes||[]).forEach(function(item){nodeNames[item.id]=item.label});var relationHtml=(graph.edges||[]).length?"<section class='artifact-relations'><h2>산출물 재현 관계</h2>"+graph.edges.map(function(edge){return"<div><span>"+escapeHtml(nodeNames[edge.source]||edge.source)+"</span><b>"+escapeHtml(edge.relation)+"</b><span>"+escapeHtml(nodeNames[edge.target]||edge.target)+"</span><small>"+escapeHtml(edge.evidence||"")+"</small></div>"}).join("")+"</section>":"";
    var evidenceHtml=(workbench.evidence||[]).length?"<section class='artifact-relations'><h2>근거 추적</h2><div class='artifact-evidence-list'>"+workbench.evidence.map(function(item){return"<div><b>"+escapeHtml(item.locator)+"</b> · "+escapeHtml(item.excerpt)+" <small>신뢰도 "+Math.round(Number(item.confidence||0)*100)+"% · "+escapeHtml(item.excerptSha256.slice(0,12))+"</small></div>"}).join("")+"</div></section>":"";
    var decisions=decisionResult.items||[],decisionHtml=decisions.length?"<section class='project-decisions'><h2>사용자 결정</h2><p>대화·문서·실행과 연결해 보존된 프로젝트 기준 결정입니다.</p>"+decisions.map(function(item){return"<article><i class='sync-state "+escapeHtml(item.status)+"'></i><div><b>"+escapeHtml(item.summary)+"</b><p>"+escapeHtml(item.decisionType)+" · "+escapeHtml(item.status)+(item.rationale?" · "+escapeHtml(item.rationale):"")+"</p></div><time>"+escapeHtml(item.decidedAt)+"</time></article>"}).join("")+"</section>":"";
    $("documentPaper").className="paper workbench-info-paper";$("documentPaper").innerHTML="<div class='workbench-info-head'><span>SYNC HISTORY</span><h1>변경 이력</h1><p>MD revision, 완성 문서와 사용자 결정을 함께 추적합니다.</p></div>"+conflictHtml+decisionHtml+relationHtml+evidenceHtml+"<div class='workbench-history'>"+((workbench.events||[]).map(function(item){return"<article><i class='sync-state "+escapeHtml(item.status)+"'></i><div><b>"+escapeHtml(item.eventType)+"</b><p>"+escapeHtml(item.origin)+" · "+escapeHtml(item.status)+"</p></div><time>"+escapeHtml(item.createdAt)+"</time></article>"}).join("")||"<p>아직 변경 이력이 없습니다.</p>")+"</div>";
    $("documentPaper").querySelector(".workbench-info-head").insertAdjacentHTML("beforeend","<button class='inline-link' id='reviewCurrentMarkdownQuality'>현재 MD 품질 점검</button>");
    $("reviewCurrentMarkdownQuality").onclick=runCurrentDocumentQualityReview;
    $("documentPaper").querySelectorAll("[data-conflict-resolution]").forEach(function(button){button.onclick=function(){resolveWorkbenchConflict(button.dataset.conflictId,button.dataset.conflictResolution,button)}});
    configureEditorPlugin({filename:workbench.document.title,adapter:"project.sync-history@1.0.0",workspace:{loadedMcps:["document.markdown@1.0.0","project.sync-history@1.0.0"]}});
  }
  async function resolveWorkbenchConflict(conflictId,resolution,button){
    var selectedChangeIds=[],card=button&&button.closest("[data-conflict-card]");if(resolution==="merge-selected"&&card){selectedChangeIds=Array.from(card.querySelectorAll("[data-conflict-change]:checked")).map(function(node){return node.dataset.conflictChange});if(!selectedChangeIds.length)return toast("MD에 반영할 변경 블록을 하나 이상 선택해 주세요.")}
    var message=resolution==="keep-markdown"?"현재 MD를 유지하고 파생 문서 변경 초안을 폐기할까요? 파생 문서는 갱신 필요 상태가 됩니다.":resolution==="merge-selected"?"선택한 "+selectedChangeIds.length+"개 변경 블록만 현재 MD의 새 revision으로 병합할까요?":"파생 문서 변경 초안을 새 MD revision으로 채택할까요? 기존 MD revision은 이력에 보존됩니다.";
    if(!window.confirm(message))return;
    try{
      setStatus("문서 충돌 해결 중");
      var workbench=state.projectWorkbench;
      await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/documents/"+workbench.document.id+"/conflicts/"+conflictId+"/resolve",{method:"POST",body:JSON.stringify({resolution:resolution,selected_change_ids:selectedChangeIds,actor:"workspace-user"})});
      await refreshProjectWorkbench();await renderWorkbenchHistory();renderProjectWorkbenchTabs();setStatus("문서 충돌 해결 완료");toast(resolution==="keep-markdown"?"현재 MD를 유지했습니다. 필요하면 MD → 파생 문서를 실행하세요.":resolution==="merge-selected"?"선택한 변경 블록만 MD 새 revision으로 병합했습니다.":"파생 문서 변경을 MD 새 revision으로 반영했습니다.");
    }catch(error){setStatus("문서 충돌 해결 실패");toast(error.message)}
  }
  async function switchProjectWorkbenchTab(tab,options){
    if(!state.projectWorkbench)return;
    if(state.activeWorkbenchTab==="markdown"&&state.sourceEditorDirty){var saved=await saveDocumentChanges();if(!saved)return}
    if(tab!==state.activeWorkbenchTab)cacheCurrentWorkbenchTab();
    state.activeWorkbenchTab=tab;renderProjectWorkbenchTabs();if(!(options&&options.restoring))setView("editor");
    try{if(tab==="markdown")await openWorkbenchMarkdown();else if(tab.indexOf("artifact:")===0)await openWorkbenchArtifact(tab.split(":")[1]);else if(tab==="outputs")renderDocumentFinalOutputs();else if(tab==="metadata")await renderWorkbenchMetadata();else if(tab==="history")await renderWorkbenchHistory();if(!(options&&options.restoring))scheduleWorkspaceStateSave(false)}catch(error){setStatus("탭 동기화 실패");toast(error.message);await refreshProjectWorkbench()}
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
    var source=sources[sources.length-1],profile=source&&source.summary&&source.summary.templateProfile,schema=source&&source.summary&&source.summary.templateSchema,quality=source&&source.summary&&source.summary.templateQuality,extraction=source&&source.summary&&source.summary.templateExtraction||{};
    var multiple=sources.length>1,editable=Boolean(draft&&draft.status!=="published"),slotReady=Boolean(schema&&schema.required&&schema.required.title&&schema.required.body),structuralReady=Boolean(schema&&schema.structuralBindingReady),needsConversion=Boolean(source&&!slotReady);
    lab.classList.toggle("has-error",multiple);
    var lowConfidence=Boolean((extraction.generated&&Number(extraction.sourceConfidence||1)<.8&&!extraction.userConfirmed)||(/_양식등록/i.test(source&&source.filename||"")&&!extraction.userConfirmed));
    $("templateAuthoringStatus").textContent=!draft?"먼저 양식 MCP 초안을 만드세요.":draft.status==="published"?"게시 버전은 고정되어 있습니다. 스토어에서 ‘수정’을 눌러 새 버전 초안을 만드세요.":multiple?("양식 기준 HWPX가 "+sources.length+"개입니다. 첨부 목록에서 하나만 남겨 주세요."):source?(source.filename+" · "+(lowConfidence?"자동 추정 결과를 실제 내용으로 확인해야 합니다.":needsConversion?"제목·본문 위치 확인 필요":structuralReady?"양식 구조 준비 완료":"자동 추출 완료 · 매핑 검토 필요")):"완성본·빈칸·작성요령 HWPX 중 하나를 ‘양식 원본’으로 첨부하세요.";
    var summary=$("templateConversionSummary");
    if(summary)summary.textContent=multiple?"기준 파일이 여러 개이면 변환 대상을 결정할 수 없습니다.":source?((extraction.sourceMode||profile&&profile.mode||"분석 대기")+" · 자동 분석 "+Math.round(Number(extraction.sourceConfidence||profile&&profile.confidence||0)*100)+"% · 제목/본문 "+(slotReady?"감지":"미확정")+" · 표 "+(schema&&schema.templateTables||0)+"개 · "+(extraction.userConfirmed?"사용자 확인 완료":lowConfidence?"사용자 확인 필요":quality&&quality.passed?"실검증 통과":"실검증 대기")):"HWPX 한 개를 첨부하면 원본과 실제 적용 결과를 비교할 수 있습니다.";
    $("previewDraftTemplate").disabled=!editable||!source||multiple;
    $("convertDraftTemplate").disabled=!editable||!source||multiple;
    $("convertDraftTemplate").textContent=multiple?"원본 하나만 남겨 주세요":"변환본 다시 생성 · 고급";
    $("downloadDraftTemplateSample").disabled=!editable||multiple;
    $("openTemplateAuthoring").disabled=!editable||multiple;
    $("verifyDraftTemplate").disabled=!draft||!source||multiple||!slotReady;
    $("correctDraftTemplate").disabled=!editable||!source||multiple;
    $("openTemplateAuthoring").textContent=source?"RHWP 단독 편집":"샘플 생성 후 RHWP로 편집";
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


  var templatePreviewState=null;

  function destroyTemplatePreviewEditor(){
    if(templatePreviewState&&templatePreviewState.editor){try{templatePreviewState.editor.destroy()}catch(_error){}templatePreviewState.editor=null}
    var host=$("templatePreviewHwpxHost");if(host)host.innerHTML="";
    templatePreviewState=null;
  }

  function describeTemplatePreview(result){
    var analysis=result.analysis||{},confidence=Math.round(Number(analysis.sourceConfidence||0)*100),box=$("templatePreviewAnalysis");
    box.classList.toggle("is-warning",Boolean(analysis.requiresConfirmation));
    box.classList.toggle("is-confirmed",Boolean(analysis.userConfirmed));
    if(analysis.requiresConfirmation){
      box.textContent="자동 추출 신뢰도 "+confidence+"% · 완성 문서에서 제목·본문 위치를 추정했습니다. 오른쪽 결과가 원본의 서식과 배치를 유지하는지 확인한 뒤 확정하세요.";
    }else if(analysis.userConfirmed){
      box.textContent="사용자가 실제 적용 결과를 확인한 양식입니다. 렌더링 블록 "+analysis.renderedBlocks+"개 · 표 "+analysis.renderedTables+"개 · 매핑률 "+Math.round(Number(analysis.mappingCoverage||0)*100)+"%.";
    }else{
      box.textContent="명시된 양식 필드를 감지했습니다. 렌더링 블록 "+analysis.renderedBlocks+"개 · 표 "+analysis.renderedTables+"개 · 매핑률 "+Math.round(Number(analysis.mappingCoverage||0)*100)+"%.";
    }
    $("confirmTemplatePreview").textContent=analysis.userConfirmed?"확인 완료 · 다시 저장":"이 결과를 양식으로 사용";
  }

  async function showTemplatePreviewDocument(kind){
    if(!templatePreviewState||!templatePreviewState.editor)return;
    var original=kind==="original",record=original?templatePreviewState.result.original:templatePreviewState.result.rendered;
    $("showTemplateOriginal").classList.toggle("active",original);$("showTemplateResult").classList.toggle("active",!original);
    $("templatePreviewModeLabel").textContent=original?"업로드한 원본 HWPX":"실제 Markdown 적용 결과";
    $("templatePreviewHwpxState").textContent="RHWP 로딩 중";
    await templatePreviewState.editor.loadFile(base64Bytes(record.contentBase64),record.filename,{skipUnsavedGuard:true,suppressDialogs:true});
    $("templatePreviewHwpxState").textContent=original?"원본 · 읽기 비교":"적용 결과 · 읽기 비교";
  }

  async function fetchTemplatePreview(markdown){
    var result=await api("/builder/drafts/"+state.builderDraft.id+"/template-preview",{method:"POST",body:JSON.stringify({markdown:markdown||"",actor:"workspace-user"})});
    if(!templatePreviewState)templatePreviewState={draftId:state.builderDraft.id,result:result,editor:null};else templatePreviewState.result=result;
    $("templatePreviewMarkdown").value=result.markdown||"";
    describeTemplatePreview(result);
    return result;
  }

  async function openTemplatePreview(){
    if(!state.builderDraft)return toast("먼저 양식 MCP 초안을 만드세요.");
    try{
      setStatus("실제 Markdown을 양식에 적용하는 중");
      destroyTemplatePreviewEditor();
      var result=await fetchTemplatePreview("");
      $("templatePreviewDialog").showModal();$("templatePreviewHwpxState").textContent="RHWP 준비 중";
      var module=await import("/poc/aiworks/vendor/rhwp-editor/index.js?v=embedded-recovery-1");
      if(!templatePreviewState)return;
      var previewSession=templatePreviewState,editor=await module.createEditor($("templatePreviewHwpxHost"),{studioUrl:"/poc/aiworks/rhwp/",renderer:"canvas2d",height:"100%",suppressRecovery:true});
      if(templatePreviewState!==previewSession){editor.destroy();return}
      previewSession.editor=editor;await showTemplatePreviewDocument("result");
      setStatus("양식 실제 적용 결과 확인 중");
    }catch(error){destroyTemplatePreviewEditor();setStatus("양식 적용 미리보기 실패");toast(error.message)}
  }

  async function refreshTemplatePreview(){
    if(!templatePreviewState)return;
    try{
      $("refreshTemplatePreview").disabled=true;setStatus("수정한 Markdown으로 다시 렌더링 중");
      await fetchTemplatePreview($("templatePreviewMarkdown").value);
      await showTemplatePreviewDocument("result");setStatus("양식 적용 결과 갱신 완료");
    }catch(error){setStatus("양식 적용 결과 갱신 실패");toast(error.message)}
    finally{$("refreshTemplatePreview").disabled=false}
  }

  async function confirmTemplatePreview(){
    if(!templatePreviewState)return;
    try{
      $("confirmTemplatePreview").disabled=true;setStatus("확인한 양식 결과 저장 중");
      var result=await api("/builder/drafts/"+templatePreviewState.draftId+"/template-confirm",{method:"POST",body:JSON.stringify({markdown:$("templatePreviewMarkdown").value,actor:"workspace-user"})});
      state.builderDraft=result.draft;showBuilderDraft(result.draft);await loadBuilderDrafts();$("templatePreviewDialog").close();
      setStatus("양식 적용 결과 확인 완료");toast("실제 보고서 적용 결과를 확인한 양식으로 저장했습니다. 이제 구조 검증 후 게시하세요.");
    }catch(error){setStatus("양식 확인 저장 실패");toast(error.message)}
    finally{$("confirmTemplatePreview").disabled=false}
  }



  var templateMappingState=null;

  function base64Bytes(value){var binary=atob(value||""),bytes=new Uint8Array(binary.length);for(var index=0;index<binary.length;index++)bytes[index]=binary.charCodeAt(index);return bytes}
  function bytesBase64(bytes){var binary="";for(var offset=0;offset<bytes.length;offset+=32768)binary+=String.fromCharCode.apply(null,bytes.subarray(offset,offset+32768));return btoa(binary)}
  function destroyTemplateMappingEditor(){
    if(templateMappingState&&templateMappingState.editor){try{templateMappingState.editor.destroy()}catch(_error){}templateMappingState.editor=null}
    var host=$("templateMappingHwpxHost");if(host)host.innerHTML="";
    templateMappingState=null;
  }

  function refreshTemplateMappingPreview(){
    if(!templateMappingState)return;
    var ids=["mappingTitle","mappingBody","mappingMain","mappingSub","mappingNote","mappingDepartment","mappingAuthor","mappingDocumentNumber","mappingApproval","mappingSectionRepeater","mappingConditional","mappingTableRepeater"],
      labels=["제목","본문","○ 원형","- 원형","※ 원형","담당 부서","작성자","문서번호","결재란","반복 section","조건부 영역","반복 표"];
    var rows=ids.map(function(id,index){
      var locator=$(id).value,item=(templateMappingState.candidates||[]).find(function(candidate){return candidate.locator===locator});
      return item?labels[index]+" · "+item.locator+(item.insideTable?" · 표 R"+(Number(item.tableRow)+1)+"C"+(Number(item.tableColumn)+1)+(item.tableMerged?" · 병합 "+item.rowSpan+"×"+item.colSpan:""):"")+"\n"+(item.text||"(빈 문단)"):"";
    }).filter(Boolean);
    $("templateMappingPreview").textContent=rows.join("\n\n")||"문단을 선택하면 현재 텍스트와 위치를 확인할 수 있습니다.";
    var title=$("mappingTitle").value,body=$("mappingBody").value;
    $("templateBindingRail").textContent="# {{title}} → "+(title||"미지정")+"\n{{content}} → "+(body||"미지정")+"\n반복 section → "+($("mappingSectionRepeater").value||"본문 구조 자동")+"\n조건부 영역 → "+($("mappingConditional").value||"없음")+"\n반복 표 → "+($("mappingTableRepeater").value||"표 구조 자동");
  }

  async function openTemplateMapping(){
    if(!state.builderDraft)return toast("먼저 양식 MCP 초안을 만드세요.");
    try{
      setStatus("HWPX 문단과 현재 TemplateSchema 분석 중");
      var result=await api("/builder/drafts/"+state.builderDraft.id+"/template-mapping"),mapping=result.mapping||{},candidates=mapping.candidates||[],slots=mapping.currentSlots||{};
      destroyTemplateMappingEditor();
      templateMappingState={draftId:state.builderDraft.id,candidates:candidates,filename:result.filename,editor:null};
      var semanticCandidates=candidates.filter(function(item){return item.slots&&item.slots.length||(!item.insideTable&&(item.text||"").trim())}).slice(0,100);
      candidates.forEach(function(item){if(item.slots&&item.slots.length&&!semanticCandidates.some(function(candidate){return candidate.locator===item.locator}))semanticCandidates.push(item)});
      var options=semanticCandidates.map(function(item){var role=item.slots&&item.slots.length?"["+item.slots.join(", ")+"] ":item.insideTable?"[표] ":"";return"<option value='"+escapeHtml(item.locator)+"'>"+escapeHtml(role+(item.preview||"빈 문단"))+"</option>"}).join("");
      ["mappingTitle","mappingBody"].forEach(function(id){$(id).innerHTML=options});
      ["mappingMain","mappingSub","mappingNote","mappingDepartment","mappingAuthor","mappingDocumentNumber","mappingApproval","mappingSectionRepeater","mappingConditional"].forEach(function(id){$(id).innerHTML="<option value=''>자동 감지 / 지정 안 함</option>"+options});
      var tableOptions=candidates.filter(function(item){return item.insideTable}).map(function(item){return"<option value='"+escapeHtml(item.locator)+"'>"+escapeHtml("R"+(Number(item.tableRow)+1)+"C"+(Number(item.tableColumn)+1)+(item.tableMerged?" 병합 "+item.rowSpan+"×"+item.colSpan:"")+" · "+item.preview)+"</option>"}).join("");
      $("mappingTableRepeater").innerHTML="<option value=''>표 구조 자동 / 지정 안 함</option>"+tableOptions;
      var nonblank=candidates.filter(function(item){return item.text&&!item.insideTable}),auto=result.autoMapping||{},titleDefault=slots.title||auto.title||(nonblank[0]&&nonblank[0].locator)||"",bodyDefault=slots.content||slots.body||auto.body||(nonblank.find(function(item){return item.locator!==titleDefault})||{}).locator||"";
      $("mappingTitle").value=titleDefault;$("mappingBody").value=bodyDefault;
      var patterns={mappingMain:/^\s*[○ㅇ]/,mappingSub:/^\s*[-·]/,mappingNote:/^\s*[※*]/};
      Object.keys(patterns).forEach(function(id){var found=candidates.find(function(item){return patterns[id].test(item.text||"")});$(id).value=found?found.locator:""});
      var metadataDefaults={mappingDepartment:"department",mappingAuthor:"author",mappingDocumentNumber:"document_number",mappingApproval:"approval_line"};
      Object.keys(metadataDefaults).forEach(function(id){$(id).value=slots[metadataDefaults[id]]||""});
      if(!$('mappingApproval').value){var approval=candidates.find(function(item){return item.approvalLike});$('mappingApproval').value=approval?approval.locator:""}
      var structural=result.structuralRoles||{};$("mappingSectionRepeater").value=structural.sectionRepeater||bodyDefault;$("mappingConditional").value=structural.conditionalBlock||"";$("mappingTableRepeater").value=structural.tableRepeater||"";
      $("templateBlueprintMarkdown").value=result.blueprintMarkdown||"# {{title}}\n\n{{content}}";
      var extraction=result.extraction||{};
      $("templateMappingHelp").textContent="고급 보정 화면 · "+result.filename+" · 자동 추출 문단 "+mapping.total+"개. 실제 적용 결과가 틀릴 때만 제목·본문 위치를 바꾸세요.";
      ["mappingTitle","mappingBody","mappingMain","mappingSub","mappingNote","mappingDepartment","mappingAuthor","mappingDocumentNumber","mappingApproval","mappingSectionRepeater","mappingConditional","mappingTableRepeater"].forEach(function(id){$(id).onchange=refreshTemplateMappingPreview});
      refreshTemplateMappingPreview();$("templateMappingDialog").showModal();setStatus("MD·HWPX 매핑 편집기 로딩 중");
      $("templateHwpxState").textContent="RHWP 로딩 중";
      var module=await import("/poc/aiworks/vendor/rhwp-editor/index.js?v=embedded-recovery-1");
      if(!templateMappingState)return;
      var mappingSession=templateMappingState;
      var editor=await module.createEditor($("templateMappingHwpxHost"),{studioUrl:"/poc/aiworks/rhwp/",renderer:"canvas2d",height:"100%",suppressRecovery:true});
      if(templateMappingState!==mappingSession){editor.destroy();return}
      mappingSession.editor=editor;
      await editor.loadFile(base64Bytes(result.contentBase64),result.filename,{skipUnsavedGuard:true,suppressDialogs:true});
      if(templateMappingState!==mappingSession)return;
      $("templateHwpxState").textContent="RHWP 편집 가능";setStatus("MD·HWPX 양식 매핑 수정 중");
    }catch(error){setStatus("양식 슬롯 분석 실패");toast(error.message)}
  }

  async function applyTemplateMapping(){
    if(!templateMappingState)return;
    if($("mappingTitle").value===$("mappingBody").value)return toast("제목과 본문은 서로 다른 문단이어야 합니다.");
    var blueprint=$("templateBlueprintMarkdown").value.trim();
    if(blueprint.indexOf("{{title}}")<0||!(/{{(?:content|body)}}/.test(blueprint)))return toast("MD 내용 계약에 {{title}}과 {{content}} 슬롯을 유지해 주세요.");
    try{
      $("applyTemplateMapping").disabled=true;setStatus("슬롯 보정·실렌더링 검증 중");
      var editedBase64="";if(templateMappingState.editor)editedBase64=bytesBase64(await templateMappingState.editor.exportHwpx());
      var result=await api("/builder/drafts/"+templateMappingState.draftId+"/template-mapping",{method:"POST",body:JSON.stringify({title_locator:$("mappingTitle").value,body_locator:$("mappingBody").value,main_locator:$("mappingMain").value,sub_locator:$("mappingSub").value,note_locator:$("mappingNote").value,department_locator:$("mappingDepartment").value,author_locator:$("mappingAuthor").value,document_number_locator:$("mappingDocumentNumber").value,approval_locator:$("mappingApproval").value,section_repeater_locator:$("mappingSectionRepeater").value,conditional_locator:$("mappingConditional").value,table_repeater_locator:$("mappingTableRepeater").value,blueprint_markdown:blueprint,content_base64:editedBase64,actor:"workspace-user"})});
      if(templateMappingState.editor&&templateMappingState.editor.notifySaved)await templateMappingState.editor.notifySaved(result.filename||templateMappingState.filename);
      state.builderDraft=result.draft;showBuilderDraft(result.draft);await loadBuilderDrafts();$("templateMappingDialog").close();setStatus("MD·HWPX 양식 매핑 저장·실검증 완료");toast("MD 내용 계약과 HWPX 고정 서식을 하나의 양식 MCP로 저장했습니다.");
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
    if($("externalTransport"))$("externalTransport").value=connector.transport||"streamable-http";
    if($("externalServerProfile"))$("externalServerProfile").value=connector.serverProfile||"";
    if($("externalEndpointEnv"))$("externalEndpointEnv").value=connector.endpointEnv||"AIWORKS_EXTERNAL_MCP_URL";
    if($("externalToolName"))$("externalToolName").value=connector.toolName||"query";
    if($("externalCapability"))$("externalCapability").value=(draft.manifest.capabilities||[])[0]||"external.tool.invoke";
    if($("externalPreset"))$("externalPreset").value=connector.preset||"default";
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
    populateEditableTemplateMcps();
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
    external:{label:"외부 MCP 연결",guide:"원격 MCP는 Streamable HTTP로, 로컬 MCP는 운영자가 승인한 stdio 프로필로 연결합니다. 임의 명령은 실행하지 않고 tools/list에서 확인된 도구만 사용합니다.",role:"guide",roleLabel:"연동 가이드",procedure:"전송 방식과 승인된 서버 위치를 확인한다.\ntools/list에서 연결할 도구와 Schema를 검증한다.\nAIWorks Capability와 입출력 필드를 대응한다.\n샌드박스 연결 테스트 후 게시·설치한다."}
  };
  var builderQuickPresets={
    template:{name:"부처 보고서 양식 MCP",description:"사용자가 등록한 HWPX 양식을 기준으로 현재 문서의 제목과 본문을 해당 보고 형식으로 변환한다.",instructions:"등록 양식의 고정 문구와 서식은 유지하고 현재 문서의 제목·본문·작성 정보를 플레이스홀더에 대응한다.",cautions:"원문에 없는 수치나 기관명을 추측하지 않는다.\n확인할 수 없는 값은 확인 필요로 표시한다.",procedure:"양식의 고정 영역과 플레이스홀더를 확인한다.\n현재 문서의 제목과 본문을 대응한다.\n유의사항을 검사하고 새 revision으로 저장한다.",triggers:"등록한 부처 보고서 양식으로 바꿔줘",useModel:false,allowExternal:false,sourceIncluded:true},
    process:{name:"결재 전 검토 처리 MCP",description:"제출 자료의 필수 항목과 누락 내용을 확인하고 단계별 검토 결과를 보고서로 작성한다.",instructions:"입력 자료를 검토 기준과 처리 순서에 따라 확인하고 누락 항목·확인 결과·후속 조치를 구조화한다.",cautions:"원문을 직접 변경하지 않는다.\n누락 근거와 확인 위치를 함께 기록한다.",procedure:"입력 자료와 실행 조건을 확인한다.\n필수 항목과 누락 내용을 검사한다.\n검토 결과와 후속 조치를 보고서로 작성한다.",triggers:"이 자료를 결재 전 검토 보고서로 작성해줘",useModel:true,allowExternal:true,sourceIncluded:false},
    data:{name:"예산 정책 데이터 MCP",description:"사용자가 등록한 예산·정책 PDF를 RAG로 검색하여 연도, 기관, 정책 항목과 수치를 원문 근거와 함께 답한다.",instructions:"질문과 관련된 등록 문서 청크만 사용하고 모든 핵심 수치와 설명에 파일명·페이지 출처를 연결한다.",cautions:"출처가 없는 값은 추측하지 않는다.\n기준연도와 단위를 확인한다.\n서로 다른 시점의 수치를 임의로 합치지 않는다.",procedure:"질문에서 기관·연도·정책 항목을 파악한다.\n등록 PDF의 관련 청크를 검색한다.\n근거 번호와 원문 위치를 포함해 답한다.",triggers:"우리부 예산 현황을 확인해줘\n등록된 예산 정책 자료에서 관련 수치를 찾아줘",dataSource:"사용자 등록 PDF · 로컬 RAG · 원문 페이지 인용",useModel:false,allowExternal:false,sourceIncluded:true},
    tool:{name:"회의 핵심 요약 MCP",description:"회의 기록에서 결정 사항, 담당자와 후속 조치를 빠르게 추출하여 간결하게 요약한다.",instructions:"회의 기록을 읽고 결정 사항과 담당자별 후속 조치를 분리해 최종 결과만 반환한다.",cautions:"발언에 없는 결정을 만들지 않는다.\n담당자가 불명확하면 확인 필요로 표시한다.",procedure:"회의 기록의 핵심 안건을 확인한다.\n결정 사항과 담당자를 추출한다.\n후속 조치를 기한과 함께 정리한다.",triggers:"회의 핵심과 후속 조치를 요약해줘",useModel:true,allowExternal:true,sourceIncluded:false},
    external:{name:"공개 MCP 연결",description:"운영자가 승인한 로컬 stdio 프로필 또는 Streamable HTTP 서버의 도구를 AIWorks Capability로 연결한다.",instructions:"서버의 tools/list에서 도구명과 입력 Schema를 확인하고 AIWorks의 입력·출력 계약에 대응한 뒤 결과를 검증한다.",cautions:"운영자가 승인하지 않은 로컬 실행 파일은 사용할 수 없다.\n원격 전송 범위와 인증 환경변수를 확인한다.\n실패한 외부 결과는 원본 문서나 데이터를 덮어쓰지 않는다.",procedure:"전송 방식과 서버 위치를 선택한다.\ntools/list에서 연결할 도구를 확인한다.\nAIWorks Capability와 입출력 필드를 대응한다.\n연결 테스트 후 게시·설치한다.",triggers:"등록된 외부 MCP로 이 작업을 처리해줘\n공개 MCP 도구를 연결해줘",useModel:false,allowExternal:true,sourceIncluded:false}
  };

  function applyBuilderPreset(type,silent){
    var preset=builderQuickPresets[type]||builderQuickPresets.tool;
    $("mcpType").value=type;updateBuilderTypeUi(type,false);
    $("mcpName").value=preset.name;$("mcpPackageId").value="";$("mcpVersion").value="0.1.0";
    $("mcpDescription").value=preset.description;$("mcpInstructions").value=preset.instructions;
    $("mcpCautions").value=preset.cautions;$("mcpProcedure").value=preset.procedure;$("mcpTriggers").value=preset.triggers;
    $("mcpDataSource").value=preset.dataSource||"";$("useModel").checked=preset.useModel;$("allowExternal").checked=preset.allowExternal;$("sourceIncluded").checked=preset.sourceIncluded;
    if(type==="external"){$("externalTransport").value="streamable-http";$("externalServerProfile").value="";$("externalEndpointEnv").value="AIWORKS_EXTERNAL_MCP_URL";$("externalToolName").value="query";$("externalCapability").value="external.tool.invoke";$("externalPreset").value="default";$("externalOutputContent").value="contentBase64";$("externalOutputFilename").value="filename";updateExternalTransportUi()}
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
      output.innerHTML=result.items.map(function(item,index){var evaluation=item.evaluation||{},ranking=item.ranking||{},components=ranking.components||{};return"<article class='resolver-hit "+(index===0?"best":"")+"'><span>"+(index===0?"선택 예정":"대안 "+(index+1))+" · 종합 "+Number(item.rankScore||0).toFixed(1)+"점</span><b>"+escapeHtml(item.name)+"</b><small>"+escapeHtml(item.packageRef)+" · "+escapeHtml(item.capabilityId)+"</small><p>왜 후보인가: "+escapeHtml((item.matchedBy||[]).join(", ")+" · 의도 "+Math.round(Number(components.intent||0)*100)+"%")+"</p><p>운영 지표: 품질 "+Math.round(Number(evaluation.quality||0)*100)+"% · 성공률 "+Math.round(Number(evaluation.successRate||0)*100)+"% · "+Math.round(Number(evaluation.latencyMs||0))+"ms · 실행비용 "+Number(evaluation.costPerRun||0).toFixed(4)+"</p>"+(index===0?"<em>프로젝트 선호도와 품질·속도·비용 가중치를 합산해 이 후보를 선택합니다.</em>":"")+"</article>"}).join("")+(result.excluded&&result.excluded.length?"<small class='resolver-excluded'>권한 또는 입출력 계약이 맞지 않아 제외된 후보 "+result.excluded.length+"개</small>":"");$("runResolvedIntent").disabled=false;
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
    if($("externalProbeStatus"))$("externalProbeStatus").textContent=isStdio?"초안 생성 후 운영자 승인 프로필과 tools/list를 확인합니다.":"초안 생성 후 URL 환경변수와 tools/list를 확인합니다.";
  }
  function populateExternalMcpProfiles(){
    var select=$("externalServerProfile");
    if(!select)return;
    var selected=select.value,profiles=state.externalMcpProfiles||[];
    select.innerHTML=profiles.length?profiles.map(function(profile){
      var label=profile.name+" · "+profile.version+(profile.available?" · 사용 가능":" · 런타임 확인 필요");
      return"<option value='"+escapeHtml(profile.id)+"'>"+escapeHtml(label)+"</option>";
    }).join(""):"<option value=''>운영자 승인 프로필 없음</option>";
    if(selected&&profiles.some(function(profile){return profile.id===selected}))select.value=selected;
  }
  function populateEditableTemplateMcps(){
    var select=$("editableTemplateMcp"),open=$("openEditableTemplateMcp"),status=$("editableTemplateMcpStatus");
    if(!select)return;
    var templates=(state.mcps||[]).filter(function(item){return item.mcpType==="template"&&item.editable!==false});
    var current=state.builderDraft&&state.builderDraft.manifest||{},derived=String(current.derivedFrom||""),selected=select.value;
    select.innerHTML="<option value=''>수정할 양식 MCP를 선택하세요</option>"+templates.map(function(item){return "<option value='"+escapeHtml(item.id)+"'>"+escapeHtml(item.name)+" · v"+escapeHtml(item.version)+(item.installedVersion?" · 사용 중":" · 게시됨")+"</option>"}).join("");
    var derivedItem=templates.find(function(item){return derived===item.id+"@"+item.version});
    if(derivedItem)select.value=derivedItem.id;else if(templates.some(function(item){return item.id===selected}))select.value=selected;
    open.disabled=!select.value;
    status.textContent=!templates.length?"스토어에 등록된 양식 MCP가 없습니다.":derivedItem?("현재 "+derivedItem.name+" v"+derivedItem.version+"의 수정 초안을 편집 중입니다."):"양식을 선택하면 원본 HWPX와 MD 매핑을 보존한 새 버전 초안을 엽니다.";
  }
  async function forkStoreItemForEdit(item,fromBuilder){
    if(!item)throw new Error("수정할 MCP를 찾을 수 없습니다.");setStatus(item.name+" 편집 초안 준비 중");
    var result=await api("/store/edit",{method:"POST",body:JSON.stringify({package_id:item.id,version:item.version,actor:"workspace-user"})});
    state.builderDraft=result.draft;if(!fromBuilder)setView("builder");showBuilderDraft(result.draft);await loadBuilderDrafts();populateEditableTemplateMcps();
    var source=(result.draft.references||[]).find(function(reference){return reference.role==="template-source"});
    setStatus(item.name+" 수정 초안 열림 · v"+result.draft.manifest.version);toast(result.reused?"기존 수정 초안을 다시 열었습니다.":("서명된 v"+item.version+"을 보존하고 v"+result.draft.manifest.version+" 수정 초안을 만들었습니다."));
    if(item.mcpType==="template"&&!source)toast("이 게시 버전에는 양식 원본 HWPX가 없어 새 기준 파일 첨부가 필요합니다.");return result;
  }
  async function openSelectedTemplateMcpForEdit(){
    var select=$("editableTemplateMcp"),item=(state.mcps||[]).find(function(candidate){return candidate.id===select.value&&candidate.mcpType==="template"});
    if(!item)return toast("수정할 양식 MCP를 선택해 주세요.");
    try{await forkStoreItemForEdit(item,true);var lab=$("builderTemplateLab");if(lab)lab.scrollIntoView({block:"center",behavior:"smooth"})}
    catch(error){setStatus("양식 MCP 수정 초안을 열지 못했습니다");toast(error.message)}
  }
  function renderBuilder(){
  var builderManualStep=0;
  var builderManualSteps=[
    {title:"유형 선택",caption:"만들 기능을 카드로 고릅니다.",target:".studio-type-grid",hint:"양식·처리·데이터·도구·외부 연결 중 하나를 누르세요."},
    {title:"내용과 자료",caption:"이름·설명·호출 문구를 채우고 필요한 파일을 놓습니다.",target:"#mcpDescription",hint:"파일 역할을 먼저 고르면 양식 원본과 데이터 원본이 섞이지 않습니다."},
    {title:"실제 검증",caption:"계약·권한·파일·검색을 샌드박스에서 확인합니다.",target:"#runSandbox",hint:"빨간 항목이 남으면 게시하지 말고 해당 입력으로 돌아가세요."},
    {title:"게시와 설치",caption:"서명된 버전을 게시한 뒤 사용할 버전을 설치합니다.",target:"#publishMcp",hint:"게시만으로는 대화에서 호출되지 않습니다. 설치까지 완료하세요."},
    {title:"호출 시험",caption:"사용자 문장으로 MCP가 선택되는지 확인합니다.",target:"#resolverIntent",hint:"선택 이유와 고정 버전을 확인한 뒤 채팅에서 실행하세요."}
  ];
  function builderManualScene(index){
    if(index===0)return"<div class='manual-choice-scene'><button><i>▤</i><b>양식</b><small>HWPX 서식</small></button><button><i>◫</i><b>데이터</b><small>PDF 검색</small></button><button class='picked'><i>✦</i><b>도구</b><small>요약·변환</small></button></div><div class='manual-pointer'>① 카드를 누르면 아래 입력 항목이 유형에 맞게 바뀝니다.</div>";
    if(index===1)return"<div class='manual-form-scene'><span><b>MCP 이름</b><i>회의 요약 MCP</i></span><span class='wide'><b>사용자가 부를 문장</b><i>회의 결과와 할 일을 정리해줘</i></span><span class='drop'><b>＋ 자료 추가</b><i>필요한 경우에만</i></span><button>새 초안·Manifest 생성</button></div>";
    if(index===2)return"<div class='manual-test-scene'><span class='pass'><i>✓</i><b>Manifest 계약</b></span><span class='pass'><i>✓</i><b>최소 권한</b></span><span><i>○</i><b>실행 샌드박스</b></span><button>전체 테스트 실행</button></div>";
    if(index===3)return"<div class='manual-publish-scene'><span><i>3</i><b>검증 완료</b></span><em>→</em><span><i>4</i><b>서명·게시</b></span><em>→</em><span class='active'><i>5</i><b>버전 설치</b></span></div><div class='manual-pointer'>게시 버전은 보존되며, 설치한 한 버전만 대화에서 사용됩니다.</div>";
    return"<div class='manual-call-scene'><div>회의 결과와 할 일을 정리해줘</div><button>MCP 찾기</button><article><small>선택 이유</small><b>회의 요약 MCP · v0.1.0</b><p>‘회의’, ‘정리’, ‘할 일’ 호출 문구가 일치하여 선택</p></article></div>";
  }
  function renderBuilderManual(){
    var dialog=$("builderManualDialog"),step=builderManualSteps[builderManualStep];if(!dialog||!step)return;
    $("builderManualNav").innerHTML=builderManualSteps.map(function(item,index){return"<button type='button' class='"+(index===builderManualStep?"current":"")+"' data-manual-step='"+index+"'><i>"+(index+1)+"</i><span><b>"+escapeHtml(item.title)+"</b><small>"+escapeHtml(item.caption)+"</small></span></button>"}).join("");
    $("builderManualStage").innerHTML="<span class='eyebrow'>STEP "+(builderManualStep+1)+"</span><h3>"+escapeHtml(step.title)+"</h3><p>"+escapeHtml(step.caption)+"</p>"+builderManualScene(builderManualStep)+"<aside><b>지금 할 일</b><span>"+escapeHtml(step.hint)+"</span></aside>";
    $("builderManualProgress").textContent=(builderManualStep+1)+" / "+builderManualSteps.length;
    $("builderManualPrev").disabled=builderManualStep===0;
    $("builderManualNext").textContent=builderManualStep===builderManualSteps.length-1?"처음부터 다시":"다음";
    dialog.querySelectorAll("[data-manual-step]").forEach(function(button){button.onclick=function(){builderManualStep=Number(button.dataset.manualStep);renderBuilderManual()}});
  }
  function openBuilderManual(step){
    builderManualStep=Math.max(0,Math.min(builderManualSteps.length-1,Number(step)||0));renderBuilderManual();
    var dialog=$("builderManualDialog");
    $("builderManualPrev").onclick=function(){builderManualStep=Math.max(0,builderManualStep-1);renderBuilderManual()};
    $("builderManualNext").onclick=function(){builderManualStep=builderManualStep===builderManualSteps.length-1?0:builderManualStep+1;renderBuilderManual()};
    $("builderManualExample").onclick=function(){dialog.close();applyBuilderPreset("tool");toast("일반 도구 MCP 예시를 불러왔습니다. 이름과 호출 문구만 바꿔 시작하세요.")};
    $("builderManualGo").onclick=function(){var selector=builderManualSteps[builderManualStep].target;dialog.close();var target=$(selector.replace("#",""))||document.querySelector(selector);if(target){target.scrollIntoView({behavior:"smooth",block:"center"});if(target.focus)target.focus()}};
    if(!dialog.open)dialog.showModal();
  }
    $("builderView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>MCP Studio</span><h1>플랫폼 전용 MCP 제작기</h1><p>자연어 업무 설명을 서버에 저장된 계약으로 변환하고, 검증된 버전만 서명해 스토어에 등록합니다.</p></div><div class='module-actions'><button id='managePublishedMcp' hidden>스토어에서 수정·삭제</button><button class='primary' id='publishMcp' disabled>검증 후 스토어 등록</button></div></div><section class='surface draft-history'><div class='surface-head'><h2>저장된 제작 작업</h2><small>초안·검증·게시 상태</small></div><div id='builderDraftList' class='draft-list'>불러오는 중...</div></section><div class='builder-grid'><section class='surface'><div class='surface-head'><h2>1. 목적과 사용 조건</h2><small>자연어 → 구조화 계약</small></div><label class='field'><span>MCP 이름</span><input id='mcpName' value='예산 검증 MCP'></label><div class='builder-id-grid'><label class='field'><span>패키지 ID · 비우면 자동 생성</span><input id='mcpPackageId' placeholder='org.budget-checker'></label><label class='field'><span>버전</span><input id='mcpVersion' value='0.1.0'></label></div><label class='field'><span>어떤 업무를 처리하나요?</span><textarea id='mcpDescription' rows='6'>예산요청서에서 필수 항목 누락과 산출 근거 오류를 찾고, 최신 SW대가 기준과 비교해 수정안을 제안한다. 원문은 외부로 보내지 않는다.</textarea></label><div class='field'><span>기준 문서 · 로컬 추출 및 SHA-256 검사</span><div id='referenceList' class='reference-list'><div class='empty-reference'>초안을 만든 뒤 실제 기준 문서를 첨부하세요.</div></div></div><div id='builderRagLab' class='builder-rag-lab' hidden><div><b>등록 자료 RAG 미리보기</b><span id='draftRagIndex'>데이터 원본 PDF를 첨부하면 검색할 수 있습니다.</span></div><div class='builder-rag-query'><input id='draftRagQuery' placeholder='예: 이 자료에서 예산 총액과 주요 정책을 찾아줘'><button id='runDraftRag' disabled>근거 검색</button></div><div id='draftRagResult' class='resolver-result'><div class='registry-empty'>게시 전에도 실제 검색 청크와 원문 위치를 확인할 수 있습니다.</div></div></div><input id='referenceFile' type='file' accept='.hwpx,.pdf,.docx,.odt,.xlsx,.md,.txt' multiple hidden><div class='toggle-row'><label><input type='radio' name='visibility' value='private'> 개인 전용</label><label><input type='radio' name='visibility' value='organization' checked> 조직 공개</label><label><input type='radio' name='visibility' value='public'> 공개</label></div><div class='toggle-row'><label><input type='checkbox' id='sourceIncluded'> 게시 패키지에 원본 포함</label><label><input type='checkbox' id='allowExternal'> 외부 모델·MCP 전송 허용</label></div><div class='form-actions'><button id='attachReference'>＋ PDF·자료 추가</button><button class='primary' id='generateManifest'>새 초안·Manifest 생성</button></div></section><section class='surface'><div class='surface-head'><h2>2. Manifest 미리보기</h2><small id='manifestStatus'>아직 생성되지 않음</small></div><pre class='code-preview' id='manifestPreview'>서버 초안을 생성하면 계약이 표시됩니다.</pre></section></div><section class='surface'><div class='surface-head'><h2>3. 샌드박스 계약 테스트</h2><button class='inline-link' id='runSandbox' disabled>전체 테스트 실행</button></div><div class='test-list' id='testList'><div><i>○</i> Manifest 생성 후 서버 샌드박스 검증을 실행하세요.</div></div></section></div>";
    var page=$("builderView").querySelector(".module-page"),hero=page.querySelector(".module-hero");page.classList.add("mcp-studio-page");
    hero.querySelector(".eyebrow").textContent="MCP STUDIO · BUILD → INSTALL → RUN";
    hero.querySelector("h1").textContent="필요한 MCP를 만들고 바로 불러보세요";
    hero.querySelector("p").textContent="업무 유형을 고르고 예시를 수정하면 계약·권한·실행 가이드가 자동 생성됩니다. 게시·설치 후 호출 문구가 어떤 MCP를 선택하는지 이 화면에서 확인할 수 있습니다.";
    hero.querySelector(".module-actions").insertAdjacentHTML("afterbegin","<button class='builder-manual-open' id='openBuilderManual'>◎ 처음부터 따라하기</button><button id='downloadTemplateStarter'>HWPX 시작 양식</button><button id='newBuilderDraft'>＋ 새 MCP</button>");
    hero.insertAdjacentHTML("afterend","<section class='studio-overview'><div class='studio-status-bar'><div><span>현재 제작 상태</span><b id='studioDraftStatus'>새 MCP를 시작하세요</b></div><div class='studio-live-metrics'><span><b id='studioDraftCount'>-</b> 저장 작업</span><span><b id='registryPackageCount'>-</b> 설치 MCP</span><span><b id='registryCapabilityCount'>-</b> Capability</span></div></div><div class='studio-steps' id='studioSteps'><div class='studio-step current'><i>1</i><b>초안</b><span>목적·호출 문구</span></div><div class='studio-step'><i>2</i><b>자료</b><span>양식·PDF·지침</span></div><div class='studio-step'><i>3</i><b>검증</b><span>계약·권한 검사</span></div><div class='studio-step'><i>4</i><b>게시</b><span>서명 패키지</span></div><div class='studio-step'><i>5</i><b>설치</b><span>대화 자동 검색</span></div></div><div class='studio-type-head'><div><b>무엇을 만들까요?</b><span>유형을 선택하면 작성 항목과 안전 검사가 자동으로 바뀝니다.</span></div><small>빠른 예시를 불러온 뒤 문구만 바꿔도 됩니다.</small></div><div class='studio-type-grid'><button data-builder-type='template'><i>▤</i><b>양식 MCP</b><span>내 HWPX 양식으로 변환</span><small>완성본·빈칸·예시·작성요령 분석</small></button><button data-builder-type='process'><i>↳</i><b>처리 MCP</b><span>반복 절차를 자동 실행</span><small>단계 + 체크포인트 + 결과</small></button><button data-builder-type='data'><i>◫</i><b>데이터 MCP</b><span>PDF 자료를 RAG로 조회</span><small>여러 파일 + 페이지 근거 + 인용</small></button><button data-builder-type='tool'><i>✦</i><b>일반 도구 MCP</b><span>요약·변환·분석 기능</span><small>Prompt + 입력·출력 계약</small></button><button data-builder-type='external'><i>⇄</i><b>외부 MCP 연결</b><span>공개·사내 MCP 연결</span><small>stdio 프로필 또는 HTTP 매핑</small></button></div></section>");
    page.insertAdjacentHTML("beforeend","<section class='surface studio-runtime'><div class='surface-head'><div><h2>4. 설치된 MCP를 실제 요청으로 찾아보기</h2><small>Capability Registry · 활성 설치 버전만 검색</small></div><button class='inline-link' id='refreshRegistry'>Registry 새로고침</button></div><div class='registry-layout'><div><div class='registry-title'><b>대화에서 사용할 수 있는 MCP</b><span>게시만 한 MCP는 표시되지 않습니다. 설치 승인까지 완료해야 합니다.</span></div><div id='capabilityRegistryList' class='capability-registry-list'><div class='registry-empty'>Registry를 불러오는 중입니다.</div></div></div><div class='resolver-lab'><span class='eyebrow'>CALL TEST</span><h3>호출 문구를 입력해 보세요</h3><p>실행 전에 어떤 MCP와 버전이 선택되는지 확인합니다.</p><textarea id='resolverIntent' rows='3' placeholder='예: 회의 핵심과 후속 조치를 요약해줘'></textarea><div class='resolver-actions'><button id='resolveIntent'>MCP 찾기</button><button class='primary' id='runResolvedIntent' disabled>채팅에서 실행</button></div><div id='resolverResult' class='resolver-result'><div class='registry-empty'>호출 문구를 입력하면 선택 예정 MCP와 매칭 근거가 표시됩니다.</div></div></div></div></section>");
    $("mcpName").closest(".field").insertAdjacentHTML("beforebegin","<label class='field'><span>MCP 유형</span><select id='mcpType'><option value='template'>양식 MCP</option><option value='process'>처리 MCP</option><option value='data'>데이터 MCP</option><option value='tool'>일반 도구 MCP</option><option value='external'>외부 MCP 연결</option></select></label><div id='builderTypeGuide' class='builder-type-guide'></div>");
    $("mcpDescription").closest(".field").insertAdjacentHTML("afterend","<label class='field'><span>실행 지침·프롬프트</span><textarea id='mcpInstructions' rows='5' placeholder='이 MCP가 입력을 어떻게 해석하고 결과를 만들어야 하는지 작성하세요.'>사용자 요청과 입력 자료를 확인하고, 등록된 기준과 절차에 따라 결과를 생성한다.</textarea></label><div class='builder-guide-grid'><label class='field'><span>유의사항 · 한 줄에 하나</span><textarea id='mcpCautions' rows='4' placeholder='원문에 없는 수치는 추측하지 않는다.&#10;확정 전에는 결과를 제출하지 않는다.'></textarea></label><label class='field'><span>처리 순서 · 한 줄에 한 단계</span><textarea id='mcpProcedure' rows='4'></textarea></label></div><label class='field'><span>사용자가 부를 수 있는 요청 예시</span><textarea id='mcpTriggers' rows='3' placeholder='행안부 보고서 양식으로 바꿔줘&#10;이 자료를 등록된 절차대로 처리해줘'></textarea></label><label class='field' id='builderDataSourceField' hidden><span>데이터 출처·접속 방식</span><input id='mcpDataSource' placeholder='내부 예산 DB · 읽기 전용 API · 기준일 필수'></label><div class='toggle-row'><label><input type='checkbox' id='useModel'> 프롬프트 처리에 모델 사용</label></div>");
    $("builderDataSourceField").insertAdjacentHTML("afterend","<div id='builderExternalFields' class='external-mcp-fields' hidden><div class='builder-guide-grid'><label class='field'><span>전송 방식</span><select id='externalTransport'><option value='streamable-http'>Streamable HTTP · 실행 승인 필요</option><option value='stdio'>로컬 stdio · 운영자 승인 필요</option></select></label><label class='field external-stdio-only'><span>승인된 서버 프로필</span><select id='externalServerProfile'><option value=''>운영자 승인 프로필 없음</option></select></label><label class='field external-http-only' hidden><span>서버 URL 환경변수</span><input id='externalEndpointEnv' value='AIWORKS_EXTERNAL_MCP_URL'></label><label class='field'><span>MCP 도구명</span><input id='externalToolName' value='query'></label><label class='field'><span>AIWorks Capability</span><input id='externalCapability' value='external.tool.invoke'></label><label class='field'><span>도구 프리셋 · 선택</span><input id='externalPreset' value='default'></label><label class='field external-http-only' hidden><span>결과 HWPX base64 경로</span><input id='externalOutputContent' value='contentBase64'></label><label class='field external-http-only' hidden><span>결과 파일명 경로</span><input id='externalOutputFilename' value='filename'></label></div><div class='external-probe-row'><button id='probeExternalMcp' disabled>런타임·tools/list 테스트</button><span id='externalProbeStatus'>초안 생성 후 서버 연결과 tools/list를 확인하세요.</span></div></div>");
    populateExternalMcpProfiles();
    $("referenceList").insertAdjacentHTML("beforebegin","<label class='field reference-role-field'><span>첨부파일 역할</span><select id='referenceRole'></select></label>");
    $("referenceList").closest(".field").insertAdjacentHTML("afterend","<section id='builderTemplateLab' class='builder-template-lab'><div class='builder-template-existing'><div><b>등록된 양식 MCP 수정</b><small id='editableTemplateMcpStatus'>등록 목록을 불러오는 중입니다.</small></div><div><select id='editableTemplateMcp'><option value=''>수정할 양식 MCP를 선택하세요</option></select><button id='openEditableTemplateMcp' disabled>수정 초안 열기</button><button id='templateUsageHelp'>실제 사용법</button></div></div><div><b>HWPX 1개 → 실제 결과 확인 → 양식 MCP</b><span id='templateAuthoringStatus'>먼저 양식 MCP 초안을 만들고 HWPX 원본을 첨부하세요.</span><small id='templateConversionSummary'>원본은 보존하고 실제 Markdown 적용 결과를 확인한 뒤 양식으로 확정합니다.</small></div><div class='builder-template-actions'><button class='primary' id='previewDraftTemplate' disabled>1. 실제 내용으로 결과 확인</button><button id='correctDraftTemplate' disabled>2. 고급 매핑 · 필요할 때만</button><button id='verifyDraftTemplate' disabled>3. 구조 실검증</button><button id='downloadDraftTemplateSample' disabled>확정 양식 다운로드</button><button id='openTemplateAuthoring' disabled>RHWP에서 서식 수정</button><button id='convertDraftTemplate' disabled>변환본 다시 생성 · 고급</button></div></section>");
    $("runDraftRag").insertAdjacentHTML("afterend","<button class='primary' id='runDraftRagReport' disabled>편집 보고서 만들기</button>");
    $("builderRagLab").querySelector(".builder-rag-query").insertAdjacentHTML("beforebegin","<div class='rag-test-scenarios'><b>빠른 검증 시나리오</b><button data-rag-sample='행안부 25년, 26년 인공지능 공통기반 주요 지적사항을 확인해줘'>근거 조회</button><button data-rag-sample='행안부 인공지능 공통기반 예산관련 지적사항을 연도별로 정리해줘'>연도별 정리</button><button data-rag-sample='행안부 인공지능 공통기반 예산관련 지적사항을 연도별 보고서로 작성해줘'>보고서 작성</button></div>");
    document.querySelectorAll("[data-rag-sample]").forEach(function(button){button.onclick=function(){$("draftRagQuery").value=button.dataset.ragSample}});
    $("mcpType").onchange=function(){updateBuilderTypeUi(this.value,false)};
    $("externalTransport").onchange=updateExternalTransportUi;
    document.querySelectorAll("[data-builder-type]").forEach(function(card){card.onclick=function(){applyBuilderPreset(card.dataset.builderType)}});
    $("downloadTemplateStarter").onclick=async function(){try{setStatus("HWPX 시작 양식 생성 중");var starter=await api("/builder/template-starter");downloadBase64(starter.filename,starter.contentBase64);setStatus("HWPX 시작 양식 다운로드 완료");toast("한글에서 서식을 편집한 뒤 플레이스홀더를 유지해 양식 원본으로 첨부하세요.")}catch(error){toast(error.message)}};
    $("openBuilderManual").onclick=function(){openBuilderManual(0)};
    $("convertDraftTemplate").onclick=convertDraftTemplateSource;
    $("previewDraftTemplate").onclick=openTemplatePreview;
    $("editableTemplateMcp").onchange=function(){$("openEditableTemplateMcp").disabled=!this.value};
    $("templateUsageHelp").onclick=function(){var selected=(state.mcps||[]).find(function(item){return item.id===$("editableTemplateMcp").value}),derived=state.builderDraft&&state.builderDraft.manifest&&state.builderDraft.manifest.derivedFrom||"";openTemplateMcpUsage(selected?selected.id+"@"+selected.version:derived)};
    $("openEditableTemplateMcp").onclick=openSelectedTemplateMcpForEdit;
    $("correctDraftTemplate").onclick=openTemplateMapping;
    $("applyTemplateMapping").onclick=applyTemplateMapping;
    $("templateMappingDialog").onclose=destroyTemplateMappingEditor;
    $("refreshTemplatePreview").onclick=refreshTemplatePreview;
    $("showTemplateOriginal").onclick=function(){showTemplatePreviewDocument("original").catch(function(error){toast(error.message)})};
    $("showTemplateResult").onclick=function(){showTemplatePreviewDocument("result").catch(function(error){toast(error.message)})};
    $("confirmTemplatePreview").onclick=confirmTemplatePreview;
    $("openAdvancedTemplateMapping").onclick=function(){$("templatePreviewDialog").close();setTimeout(openTemplateMapping,0)};
    $("templatePreviewDialog").onclose=destroyTemplatePreviewEditor;
    $("verifyDraftTemplate").onclick=verifyDraftTemplateQuality;
    $("downloadDraftTemplateSample").onclick=downloadDraftTemplateSample;
    $("openTemplateAuthoring").onclick=openTemplateAuthoring;
    $("probeExternalMcp").onclick=async function(){if(!state.builderDraft)return toast("먼저 외부 MCP 초안을 만드세요.");var status=$("externalProbeStatus");status.textContent="MCP initialize와 tools/list를 확인하는 중...";try{var result=await api("/builder/drafts/"+state.builderDraft.id+"/external/probe",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});if(!result.connected){status.textContent=result.serverProfile?(result.serverProfile+" · "+(result.reason==="profile-not-approved"?"운영자 승인 프로필 필요":"프로필 실행 파일 설치·권한 확인 필요")):(result.endpointEnv+" 미설정 · 서버 주소를 환경변수에 넣어 주세요.");return}status.textContent=(result.configuredToolFound?"연결 완료 · 도구 확인: ":"연결됨 · 설정 도구를 찾지 못함: ")+result.configuredToolName+" · 서버 도구 "+(result.tools||[]).length+"개";toast(result.configuredToolFound?"외부 MCP 계약 확인 완료":"tools/list에서 설정 도구명을 다시 확인하세요.")}catch(error){status.textContent=error.message;toast(error.message)}};
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
        await prepareStoreApproval(item,"install");toast(result.identityAdjustment?"ID 충돌을 "+result.identityAdjustment.packageId+"로 자동 해결해 게시했습니다. 권한을 확인하고 설치해 주세요.":"게시했습니다. 권한을 확인하고 설치하면 이 화면에서 바로 호출 테스트할 수 있습니다.");
      }catch(error){setStatus("MCP 게시 실패");toast(error.message)}
    };
    $("attachReference").onclick=function(){if(!state.builderDraft||state.builderDraft.status==="published")return toast("먼저 새 초안을 생성하세요.");var single=$("mcpType").value==="template"&&$("referenceRole").value==="template-source";$("referenceFile").toggleAttribute("multiple",!single);$("referenceFile").click()};
    $("referenceFile").onchange=async function(){var files=Array.from(this.files||[]);if(!files.length)return;try{var role=$("referenceRole").value,lastResult=null,isTemplate=$("mcpType").value==="template"&&role==="template-source";if(isTemplate&&files.length!==1)throw new Error("양식 기준 HWPX는 한 번에 하나만 선택해 주세요.");for(var index=0;index<files.length;index++){var file=files[index];setStatus((index+1)+"/"+files.length+(isTemplate?" · HWPX 유형 판별·양식 데이터 자동 추출 중":" · 텍스트 추출·RAG 청크 생성 중"));lastResult=await api("/builder/drafts/"+state.builderDraft.id+"/references",{method:"POST",body:JSON.stringify({filename:file.name,role:role,content_base64:await fileBase64(file),actor:"workspace-user"})});showBuilderDraft(lastResult.draft)}await loadBuilderDrafts();setStatus(isTemplate?"기준 HWPX 교체·양식 데이터 자동 추출 완료":files.length+"개 자료 RAG 준비 완료");if(isTemplate){var extraction=lastResult.reference&&lastResult.reference.summary&&lastResult.reference.summary.templateExtraction||{};toast("기존 기준 파일을 교체하고 "+(extraction.sourceMode||"HWPX")+"에서 양식 슬롯을 자동 추출했습니다. ‘MD↔HWPX 매핑 수정’에서 확인하세요.")}else toast(files.length+"개 파일을 "+role+" 역할로 연결했습니다.")}catch(error){setStatus("자료 첨부 실패");toast(error.message)}finally{this.value=""}};
    syncStore(false).then(populateEditableTemplateMcps);
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
      var usage=item.mcpType==="template"?"<button class='store-template-usage' data-template-usage='"+escapeHtml(item.id)+"'>사용법</button>":"";
      var manage=usage+configure+"<button class='store-edit' data-edit='"+escapeHtml(item.id)+"'>수정</button>"+(item.deletable?"<button class='store-delete' data-delete='"+escapeHtml(item.id)+"'>삭제</button>":"");
      var evaluation=(item.versions[0]&&item.versions[0].evaluation)||{};
      return "<article class='store-card'><div class='store-card-head'><span class='mcp-logo'>⌘</span><div><h3>"+escapeHtml(item.name)+"</h3><div class='store-meta'><span>"+escapeHtml(item.id)+"@"+escapeHtml(item.version)+"</span><span>"+escapeHtml(item.publisher)+"</span><span>✓ 서명 · 취약점 0</span></div></div></div><p>"+escapeHtml(item.desc)+"</p><div>"+item.permissions.map(function(p){return "<span class='permission-chip'>"+escapeHtml(p)+"</span> "}).join("")+"</div><div class='store-operations'><span>품질 <b>"+Math.round(Number(evaluation.quality||0)*100)+"%</b></span><span>성공률 <b>"+Math.round(Number(evaluation.successRate||0)*100)+"%</b></span><span>지연 <b>"+Math.round(Number(evaluation.latencyMs||0))+"ms</b></span><span>비용 <b>"+Number(evaluation.costPerRun||0).toFixed(4)+"</b></span></div><small class='store-policy'>라이선스 "+escapeHtml(item.license||"UNSPECIFIED")+" · 보존 "+escapeHtml(item.dataRetention&&item.dataRetention.policy||"미선언")+" · 샌드박스 "+escapeHtml(item.security&&item.security.sandbox||"미선언")+"</small><footer><span class='type-chip'>"+escapeHtml(item.runtime)+(installed?" · 설치 v"+escapeHtml(item.installedVersion):"")+"</span><div class='store-card-actions'>"+manage+action+"</div></footer></article>";
    }).join("");
    var quarantine=state.quarantined.length?"<div class='quarantine-warning'><b>검증 실패 패키지 "+state.quarantined.length+"개 격리</b><span>"+state.quarantined.map(function(item){return escapeHtml(item.packageId+"@"+item.version)}).join(", ")+"</span></div>":"";
    $("storeView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Signed MCP Marketplace</span><h1>조직 MCP 스토어</h1><p>조직 서명과 패키지 해시를 검증하고 승인된 권한으로 정확한 버전을 고정 설치합니다.</p></div><div class='module-actions'><button data-view-jump='builder'>내 MCP 만들기</button></div></div>"+quarantine+"<div class='store-toolbar'><input class='store-search' id='storeSearch' placeholder='MCP 이름, ID, 업무 또는 게시자 검색' value='"+escapeHtml(filter||"")+"'><button class='filter-button' id='refreshStore'>서명 다시 검증</button></div><div class='store-grid'>"+(cards||"<div class='registry-empty'>검색 조건에 맞는 MCP가 없습니다.</div>")+"</div></div>";
    $("storeSearch").oninput=function(){renderStore(this.value);var input=$("storeSearch");input.focus();input.setSelectionRange(input.value.length,input.value.length)};
    document.querySelector("[data-view-jump]") .onclick=function(){setView("builder")};
    $("refreshStore").onclick=function(){syncStore(true)};
    document.querySelectorAll("[data-install]").forEach(function(button){button.onclick=function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.install});prepareStoreApproval(item,"install").catch(function(error){toast(error.message)})}});
    document.querySelectorAll("[data-rollback]").forEach(function(button){button.onclick=function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.rollback});prepareStoreApproval(item,"rollback").catch(function(error){toast(error.message)})}});
    document.querySelectorAll("[data-configure]").forEach(function(button){button.onclick=function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.configure});if(item)openMcpConfiguration(item)}});
    document.querySelectorAll("[data-template-usage]").forEach(function(button){button.onclick=function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.templateUsage});if(item)openTemplateMcpUsage(item.id+"@"+item.version)}});
    document.querySelectorAll("[data-edit]").forEach(function(button){button.onclick=async function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.edit});try{await forkStoreItemForEdit(item,false)}catch(error){setStatus("MCP 수정 초안을 열지 못했습니다");toast(error.message)}}});
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
      state.mcps=(data.items||[]).map(function(item){return{id:item.packageId,name:item.name,version:item.versions[0].version,versions:item.versions,mcpType:item.mcpType||"tool",installedVersion:item.installedVersion,rollbackVersion:item.rollbackVersion,runtime:item.runtime,desc:item.description,permissions:item.permissions,rating:"서명됨",publisher:item.publisher,license:item.license||"UNSPECIFIED",dataRetention:item.dataRetention||{},security:item.security||{},compatibility:item.compatibility||{},editable:item.editable!==false,deletable:Boolean(item.deletable),configurable:Boolean(item.configurable),configuration:item.configuration||null,configurationRevision:Number(item.configurationRevision||0),configurationUpdatedAt:item.configurationUpdatedAt||null}});
      state.installed=state.mcps.filter(function(item){return item.installedVersion}).map(function(item){return item.id});
      if(state.activeView==="store")renderStore();
      if(notify)toast(state.quarantined.length?"검증 실패 패키지를 격리했습니다.":"조직 서명과 패키지 해시를 다시 검증했습니다.");
    }catch(error){if(notify)toast(error.message)}
  }

  function renderAudit(){
    var rows=state.audit.map(function(item){return "<div class='audit-row'><time>"+escapeHtml(item.time)+"</time><span>"+escapeHtml(item.actor)+"</span><strong>"+escapeHtml(item.event)+"</strong><span class='audit-status "+(item.status==="차단"?"denied":"")+"'>"+escapeHtml(item.status)+"</span></div>"}).join("");
    $("auditView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Operations & Acceptance</span><h1>운영 상태와 실행 이력</h1><p>저장소·서명·모델·어댑터 준비상태와 예산요청서 전체 승인 시나리오를 검증합니다.</p></div><div class='module-actions'><button id='undoChange'>마지막 변경 되돌리기</button><button id='downloadOperationsSbom'>SBOM</button><button id='runRecoveryDrill'>복구 훈련</button><button class='primary' id='runAcceptance'>E2E 실행</button></div></div><div class='cards'><div class='metric-card'><span>운영 준비상태</span><b id='readinessStatus'>확인 중</b><small id='readinessSummary'>핵심 경계 검사</small></div><div class='metric-card'><span>최근 수용성 테스트</span><b id='acceptanceStatus'>-</b><small id='acceptanceTime'>실행 이력 없음</small></div><div class='metric-card'><span>감사 이벤트</span><b>"+state.audit.length+"</b><small>실행 ID 추적</small></div></div><section class='surface'><div class='surface-head'><h2>운영 진단</h2><button class='inline-link' id='refreshReadiness'>다시 점검</button></div><div class='operation-checks' id='operationChecks'>진단을 불러오는 중입니다.</div></section><section class='surface'><div class='surface-head'><h2>실행·MCP 관찰성</h2><small>Workflow · Step · 1회 lease · 파생 산출물</small></div><div class='operations-metrics' id='operationsMetrics'>운영 지표를 집계하는 중입니다.</div></section><section class='surface'><div class='surface-head'><h2>예산요청서 E2E 수용성 테스트</h2><button class='inline-link danger-link' id='runFailureAcceptance'>stale-document 실패 검증</button></div><div class='acceptance-result' id='acceptanceResult'>문서 분석 → 실행계획 → 승인 → 변경안 → HWPX 산출물 → 감사 로그를 로컬 합성 실행으로 검증합니다.</div></section><section class='surface'><div class='surface-head'><h2>감사 이벤트</h2><small>영속 저장 · 실행 ID 기준</small></div><div class='audit-list'>"+rows+"</div></section></div>";
    $("undoChange").onclick=undoChange;
    $("refreshReadiness").onclick=loadOperationalStatus;
    $("runAcceptance").onclick=function(){runAcceptanceScenario("none")};
    $("runFailureAcceptance").onclick=function(){runAcceptanceScenario("stale-document")};
    $("downloadOperationsSbom").onclick=async function(){try{var sbom=await api("/operations/sbom"),blob=new Blob([JSON.stringify(sbom,null,2)],{type:"application/json"}),url=URL.createObjectURL(blob),link=document.createElement("a");link.href=url;link.download="aiworks-sbom.cdx.json";document.body.appendChild(link);link.click();link.remove();setTimeout(function(){URL.revokeObjectURL(url)},1000);toast("CycloneDX SBOM을 다운로드했습니다.")}catch(error){toast(error.message)}};
    $("runRecoveryDrill").onclick=async function(){if(!state.activeProjectId)return toast("프로젝트를 먼저 선택해 주세요.");try{setStatus("프로젝트 백업 복구 훈련 중");var drill=await api("/operations/projects/"+encodeURIComponent(state.activeProjectId)+"/recovery-drill",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});toast("복구 훈련 "+drill.status+" · RTO "+drill.rtoMilliseconds+"ms");setStatus("복구 훈련 "+drill.status);loadOperationalStatus()}catch(error){setStatus("복구 훈련 실패");toast(error.message)}};
    loadOperationalStatus();if(state.latestAcceptance)renderAcceptanceReport(state.latestAcceptance);
  }

  function renderAcceptanceReport(report){
    if(!$("acceptanceResult")||!report)return;
    $("acceptanceResult").innerHTML="<strong class='"+(report.status==="passed"?"pass":"fail")+"'>"+escapeHtml(report.status.toUpperCase())+"</strong><span>"+escapeHtml(report.id)+"</span>"+report.checks.map(function(check){return"<div class='"+(check.passed?"pass":"fail")+"'><i>"+(check.passed?"✓":"×")+"</i><b>"+escapeHtml(check.id)+"</b><span>"+escapeHtml(check.detail)+"</span></div>"}).join("")+(report.error?"<p>"+escapeHtml(report.error)+"</p>":"");
  }

  async function loadOperationalStatus(){
    try{
      var results=await Promise.all([api("/operations/readiness"),api("/acceptance/runs"),api("/operations/metrics")]);var readiness=results[0];var runs=results[1].items||[],metrics=results[2]||{};
      $("readinessStatus").textContent=readiness.ready?"READY":"NOT READY";$("readinessSummary").textContent="통과 "+readiness.summary.passed+" · 경고 "+readiness.summary.warnings+" · 실패 "+readiness.summary.failed;
      $("operationChecks").innerHTML=readiness.checks.map(function(check){return"<div class='operation-check "+escapeHtml(check.status)+"'><i>"+(check.status==="pass"?"✓":check.status==="warn"?"!":"×")+"</i><b>"+escapeHtml(check.id)+"</b><span>"+escapeHtml(check.detail)+"</span></div>"}).join("");
      if($("operationsMetrics")){var executions=metrics.executions||{},workflows=metrics.workflows||{},leases=metrics.approvalLeases||{},outputs=metrics.outputs||[],evaluations=metrics.mcpEvaluations||[];$("operationsMetrics").innerHTML="<article><small>실행</small><b>"+Number((executions.counts||{}).completed||0)+" 완료</b><span>평균 "+Number(executions.averageLatencyMs||0).toFixed(0)+"ms · 실패 "+Number((executions.counts||{}).failed||0)+"</span></article><article><small>Workflow</small><b>"+Number((workflows.counts||{}).completed||0)+" 완료</b><span>실행 중 "+Number(workflows.active||0)+" · Step 실패 "+Number((workflows.stepCounts||{}).failed||0)+"</span></article><article><small>1회 승인 lease</small><b>"+Number(leases.consumed||0)+" 소비</b><span>전체 "+Number(leases.total||0)+" · 미사용 만료 "+Number(leases.expiredUnused||0)+"</span></article><article><small>파생 산출물</small><b>"+outputs.reduce(function(total,item){return total+Number(item.count||0)},0)+"개</b><span>"+escapeHtml(outputs.map(function(item){return item.format+" "+item.count}).join(" · ")||"아직 없음")+"</span></article><article><small>MCP 평가</small><b>"+evaluations.length+"개 버전</b><span>"+escapeHtml(evaluations.slice(0,2).map(function(item){return item.packageRef+" "+Math.round(Number(item.quality||0)*100)+"%"}).join(" · ")||"기준값 사용 중")+"</span></article>"}
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
      $("archiveActiveProject").onclick=async function(){if(!window.confirm("현재 프로젝트를 보관할까요? 문서와 산출물은 삭제되지 않습니다."))return;try{await api("/projects/"+encodeURIComponent(state.activeProjectId)+"/status",{method:"POST",body:JSON.stringify({action:"archive",actor:"workspace-user"})});state.activeProjectId=null;state.activeProject=null;state.activeConversationId=null;await loadProjects();showProjectGate();toast("프로젝트를 비파괴적으로 보관했습니다.")}catch(error){toast(error.message)}};
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
  async function loadModelUsage(){
    var host=$("modelUsagePanel");if(!host)return;
    host.innerHTML="<p class='empty-reference'>사용량 예약과 정산 이력을 불러오는 중입니다.</p>";
    try{
      var data=await api("/operations/model-usage?limit=20"),totals=data.totals||{},limits=data.limits||{};
      host.innerHTML="<div class='store-grid'><article class='store-card'><h3>호출·실패</h3><b>"+Number(totals.requests||0).toLocaleString()+"회</b><p>실패 "+Number(totals.failures||0).toLocaleString()+"회 · 예약 중 "+Number(totals.reservedRequests||0).toLocaleString()+"회</p></article><article class='store-card'><h3>토큰</h3><b>"+Number(totals.totalTokens||0).toLocaleString()+"</b><p>월 한도 "+Number(limits.monthlyTokens||0).toLocaleString()+" · 예약 "+Number(totals.reservedTokens||0).toLocaleString()+"</p></article><article class='store-card'><h3>정산 비용</h3><b>"+Number(totals.actualCost||0).toFixed(6)+" USD</b><p>월 한도 "+(Number(limits.monthlyCost||0)?Number(limits.monthlyCost).toFixed(2)+" USD":"미설정")+" · 예약 "+Number(totals.reservedCost||0).toFixed(6)+"</p></article></div><pre class='code-preview'>"+escapeHtml(JSON.stringify({credentialIdentity:data.credentialIdentity,recent:data.items||[]},null,2))+"</pre>";
    }catch(error){host.innerHTML="<p class='empty-reference'>"+escapeHtml(error.message)+"</p>"}
  }

    var models=(state.models||[]).map(function(model){return"<article class='store-card'><div class='store-card-head'><span class='mcp-logo'>AI</span><div><h3>"+escapeHtml(model.label)+"</h3><div class='store-meta'><span>"+escapeHtml(model.personality)+"</span><span>입력 $"+Number(model.price.input)+"/M</span><span>출력 $"+Number(model.price.output)+"/M</span></div></div></div><p>"+escapeHtml(model.description)+"</p><div>"+model.strengths.slice(0,3).map(function(item){return"<span class='permission-chip'>"+escapeHtml(item)+"</span> "}).join("")+"</div><footer><span class='type-chip'>"+(model.default?"빠른 기본":model.freeOnly?"무료 대체":"대체 모델")+"</span><small>"+Number(model.contextTokens).toLocaleString()+" context</small></footer></article>"}).join("");
    var presetCards=(state.presets||[]).map(function(preset){return"<article class='store-card'><div class='store-card-head'><span class='mcp-logo'>"+escapeHtml(preset.modality.slice(0,2).toUpperCase())+"</span><div><h3>"+escapeHtml(preset.name)+"</h3><div class='store-meta'><span>"+escapeHtml(preset.modality)+"</span><span>"+(preset.status==="ready"?"실행 준비":"계약 미리보기")+"</span></div></div></div><p>"+escapeHtml(preset.description)+"</p><div>"+preset.acceptedFormats.map(function(format){return"<span class='permission-chip'>"+escapeHtml(format)+"</span> "}).join("")+"</div><footer><span class='type-chip'>"+escapeHtml(preset.status)+"</span><button data-workflow='"+escapeHtml(preset.id)+"'>계획 확인</button></footer></article>"}).join("");
    $("settingsView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Model & Workflow Management</span><h1>모델 관리와 업무 프리셋</h1><p>의도와 파일 형식에 따라 무료 모델과 최소권한 어댑터 실행 순서를 선택합니다.</p></div><div class='module-actions'><button class='primary' id='saveSettings'>설정 저장</button></div></div><div class='store-grid'>"+models+"</div><section class='surface routing-lab'><div class='surface-head'><h2>의도별 자동 전환 테스트</h2><small>"+(state.openrouter.configured?"API Key 연결됨":"API Key 미설정 · 선택만 검증")+"</small></div><div class='toggle-row'><label><input type='checkbox' id='liveRouteTest' "+(state.openrouter.configured?"":"disabled")+"> OpenRouter 실제 무료 호출 포함</label><label><input type='checkbox' checked disabled> :free 외 모델 차단</label></div><div class='route-test-actions'><button data-route-intent='선택 문장을 2줄 공문체로 다듬어줘'>문서 작성 의도 테스트</button><button data-route-intent='최신 기준과 비교해 예산 산출 근거를 검증해줘'>복합 추론 의도 테스트</button></div><pre class='code-preview route-result' id='routeResult'>테스트를 선택하면 의도 유형, 선택 모델과 선택 근거가 표시됩니다.</pre></section><section class='surface workflow-lab'><div class='surface-head'><h2>멀티모달 업무 프리셋</h2><div><input id='assetInspectorInput' type='file' accept='.py,.js,.ts,.json,.md,.png,.jpg,.jpeg,.wav,.mp4' hidden><button class='inline-link' id='inspectAssetButton'>파일 로컬 검사</button></div></div><div class='store-grid'>"+presetCards+"</div><pre class='code-preview workflow-result' id='workflowResult'>프리셋 계획 또는 로컬 파일 검사 결과가 표시됩니다.</pre></section><section class='surface'><div class='surface-head'><h2>데이터·권한 정책</h2><small>기본 거부</small></div><div class='toggle-row'><label><input type='checkbox' checked> 개인정보 자동 마스킹</label><label><input type='checkbox' checked> 외부 전송 매회 승인</label><label><input type='checkbox' checked> 실행 감사 로그</label></div></section></div>";
    $("settingsView").querySelector(".module-hero p").textContent="조회는 Solar Pro 3 Fast, 문서·RAG는 Solar Pro 3, 복합 검증은 Solar Pro 4로 자동 전환합니다.";
    $("settingsView").querySelector(".routing-lab .surface-head small").textContent=state.openrouter.liveExecutionEnabled?"Solar 실호출 활성":"Solar 선택 검증 · 외부 전송 대기";
    $("settingsView").querySelector(".routing-lab .toggle-row").innerHTML="<label><input type='checkbox' id='liveRouteTest' "+(state.openrouter.liveExecutionEnabled?"":"disabled")+"> 승인된 Solar 실호출 포함</label><label><input type='checkbox' checked disabled> Fast / Pro 3 / Pro 4 자동 선택</label>";
    $("settingsView").querySelector(".module-page").insertAdjacentHTML("beforeend","<section class='surface'><div class='surface-head'><h2>RHWP 전체 기능 MCP</h2><small id='rhwpRuntimeStatus'>브리지 확인 중</small></div><p class='empty-reference'>HAction/HParameterSet을 포함한 한글 자동화 기능은 문서 읽기·쓰기 승인 후 같은 사용자 Windows 브리지에서 실행됩니다.</p><div class='toggle-row' id='rhwpToolCatalog'>도구 목록을 불러오는 중입니다.</div></section>");
    $("settingsView").querySelector(".module-page").insertAdjacentHTML("beforeend","<section class='surface project-governance-panel'><div class='surface-head'><h2>프로젝트 거버넌스</h2><small>멤버십 · Grant · Resolver · 비파괴 보관</small></div><div id='projectGovernance'></div></section>");
    $("settingsView").querySelector(".module-page").insertAdjacentHTML("beforeend","<section class='surface recipe-library-panel'><div class='surface-head'><h2>업무 Recipe Library</h2><div class='recipe-search'><input id='recipeSearchInput' placeholder='이름·태그·ID 검색'><button id='searchWorkflowRecipes'>검색</button><button id='createSampleRecipe'>새 Recipe</button></div></div><p class='empty-reference'>설치 전에 권한·비용·지연·라이선스·보안 상태를 확인합니다.</p><div id='workflowRecipeLibrary' class='recipe-library'></div></section>");
    $("settingsView").querySelector(".module-page").insertAdjacentHTML("beforeend","<section class='surface model-usage-panel'><div class='surface-head'><div><h2>모델 API 사용량·비용</h2><small>자격증명 범위 · 호출 전 예약 · 성공/실패 정산</small></div><button id='refreshModelUsage'>새로고침</button></div><div id='modelUsagePanel'></div></section>");
    $("refreshModelUsage").onclick=loadModelUsage;
    loadModelUsage();
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

  async function prepareStoreApproval(item,action){
    state.pendingStoreAction=action;item.targetVersion=action==="rollback"?item.rollbackVersion:item.version;
    if(action==="install"){var preview=await api("/store/install-preview",{method:"POST",body:JSON.stringify({package_id:item.id,version:item.targetVersion})});item.permissionDiff=preview.permissionDiff||null}
    state.pendingIntent=action==="rollback"?item.name+"을 검증된 v"+item.targetVersion+"으로 롤백":item.name+" v"+item.targetVersion+"을 서명 검증 후 고정 설치";
    showApproval(state.pendingIntent,true,item);
  }

  function planFor(intent,isInstall,item){
    if(isInstall)return[
      {name:"Manifest, 번들 해시 및 조직 서명 검증",meta:item.id+" v"+(item.targetVersion||item.version)+" · 게시자 "+item.publisher},
      {name:"요청 권한 검토",meta:item.permissions.join(", ")},
      ...(item.permissionDiff&&item.permissionDiff.requiresExplicitApproval?[{name:"업데이트 권한 차이 재승인",meta:"추가 "+item.permissionDiff.addedPermissions.map(function(permission){return permission.scope}).join(", ")+" · 외부 전송 변경 "+(item.permissionDiff.dataMovementChanged?"있음":"없음")}]:[]),
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
    var mcpPlan=!isInstall&&state.pendingPlan?explainedMcpPlan(state.pendingPlan):[];
    var workflow=state.pendingPlan&&state.pendingPlan.workflow||{},userSteps=isInstall?planFor(intent,true,item||{}).map(function(step){return step.name}):(workflow.pipeline||[]);
    $("approvalUserSteps").innerHTML=(userSteps.length?userSteps:["요청 확인","필요한 기능 실행","결과 표시"]).slice(0,7).map(function(step,index){return"<li><span>"+(index+1)+"</span><b>"+escapeHtml(step)+"</b></li>"}).join("");
    $("approvalTechnicalDetails").open=false;
    $("planSteps").classList.toggle("mcp-explanation-plan",Boolean(mcpPlan.length));
    $("planSteps").innerHTML=mcpPlan.length?mcpPlan.map(function(mcp){return mcpPlanItemHtml(mcp,"li")}).join(""):planFor(intent,isInstall,item||{}).map(function(step){return "<li><strong>"+escapeHtml(step.name)+"</strong><span>"+escapeHtml(step.meta)+"</span></li>"}).join("");
    var capabilityDag=workflow.capabilityDag;if(!isInstall&&capabilityDag){$("planSteps").insertAdjacentHTML("beforeend","<li class='capability-dag-summary'><strong>입출력 Schema 연결 검증</strong><span>Capability "+Math.max(0,(capabilityDag.nodes||[]).length-2)+"개 · artifact 연결 "+(capabilityDag.edges||[]).length+"개 · "+(capabilityDag.valid?"호환 통과":"호환 실패")+"</span></li>");}
    $("externalTransfer").checked=false;
    var external=Boolean(!isInstall&&state.pendingPlan&&state.pendingPlan.dataPolicy.externalTransfer);
    $("externalTransfer").disabled=!external;
    var markdownDocs=workflow.markdownContext||[],selectedIds=workflow.projectSourceIds||[],selectedSources=state.projectSources.filter(function(source){return selectedIds.indexOf(source.id)>=0}),scope=workflow.hasSelection?"선택 문구와 요청":"요청과 현재 대화 문맥";
    if(selectedSources.length)scope+=" 및 프로젝트 자료 검색 발췌 "+selectedSources.length+"개("+selectedSources.map(function(item){return item.filename||item.title}).join(", ")+")";
    if(markdownDocs.length)scope+=" 및 프로젝트 Markdown "+markdownDocs.length+"개("+markdownDocs.map(function(item){return item.title+" r"+item.revision}).join(", ")+")";
    var route=state.pendingPlan&&state.pendingPlan.routing||{},model=route.model||{},provider=model.provider||((model.id||"").indexOf("solar")>=0?"Upstage":"외부 모델 제공자");
    if($("approvalLease"))$("approvalLease").textContent="이 승인은 현재 계획 "+(state.pendingPlan&&state.pendingPlan.id||"")+"의 표시된 권한에만 적용됩니다. 10분 안에 한 번 실행하면 즉시 소멸하며 프로젝트 결정 이력에 남습니다.";
    var finalAction=!isInstall?(workflow.finalConfirmation||null):null,row=$("approvalFinalActionRow"),finalCheckbox=$("finalActionConfirm");row.hidden=!finalAction;finalCheckbox.checked=false;$("approveRun").disabled=Boolean(finalAction);if(finalAction){$("finalActionLabel").textContent=finalAction.label+"을 실제로 수행하는 것에 동의합니다.";finalCheckbox.onchange=function(){$("approveRun").disabled=!this.checked}}else finalCheckbox.onchange=null;
    var permissionDiff=isInstall&&item&&item.permissionDiff;
    $("transferDescription").textContent=permissionDiff&&permissionDiff.requiresExplicitApproval?("업데이트 권한 차이: 추가 "+(permissionDiff.addedPermissions.map(function(permission){return permission.scope}).join(", ")||"없음")+" · 외부 전송/보존정책 변경 "+(permissionDiff.dataMovementChanged?"있음":"없음")+". 이 승인에는 변경 계약 해시가 함께 기록됩니다."):(external?scope+"을 "+provider+" 모델에 전송합니다. 개인정보는 자동 마스킹하고 첨부 원본 파일 전체는 전송하지 않으며 검색된 발췌만 전송합니다.":"외부 모델 전송이 없는 로컬 작업입니다. 선택 자료도 로컬 검색에만 사용됩니다.");
    $("transferModel").textContent=external?(model.label||model.id||"선택 모델")+" · "+provider:"외부 전송 불필요";
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
        if(action==="install"){request.version=item.targetVersion||item.version;if(item.permissionDiff&&item.permissionDiff.requiresExplicitApproval){request.acknowledge_permission_diff=true;request.permission_diff_sha256=item.permissionDiff.sha256}}
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
        var approval=await api("/approvals",{method:"POST",body:JSON.stringify({plan_id:plan.id,actor:"demo-user",permissions:plan.requiredPermissions,rationale:"승인 대화상자에서 처리 순서·권한·외부 전송 범위를 확인함"})});
        setStatus("서버 샌드박스 실행 대기");updateOrchestration("MCP 실행과 Solar 응답 생성","active");
        var context=currentRequestContext(),activeSelection=state.nativeSelection&&state.nativeSelection.before?state.nativeSelection:state.templateSelection;
        var selectionText=activeSelection?activeSelection.before:"";
        var selectionId=activeSelection?(activeSelection.editId||activeSelection.target||"document.selection"):"";
        addAssistant(activeSelection?"승인된 선택 문구와 필요한 최소 문맥으로 실행합니다.":"현재 계획에만 유효한 1회 실행 권한이 발급되었습니다. 필요한 MCP를 순서대로 실행합니다.");
        var transferApproved=Boolean(!$("externalTransfer").disabled&&$("externalTransfer").checked);
        var execution=await api("/executions",{method:"POST",body:JSON.stringify({approval_token:approval.approvalToken,idempotency_key:"web-"+plan.id,input:Object.assign({},context,{selection:selectionText,selection_id:selectionId,require_live_model:false,project_markdown_transfer_approved:transferApproved,project_sources_transfer_approved:transferApproved,final_action_confirmed:Boolean($("finalActionConfirm")&&$("finalActionConfirm").checked)})})});
        var result=execution.result||{},responseType=result.responseType||"selection-edit",resultModel=result.model||{},resultModelLabel=resultModel.resolvedModel||resultModel.name||"선택 모델";
        addWorkflowPipeline(result.workflow||plan.workflow,plan);
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
          state.lastAnswer=String(result.artifact.content||"");
          if(result.artifact.contentBase64){
            await openGeneratedArtifact(result.artifact,result.loadedMcps);await refreshActiveProjectWorkspace();
            addAssistant(resultModelLabel+"이 보고서 초안을 생성했습니다. 문구를 선택해 후속 MCP 작업을 계속할 수 있습니다.");
            updateOrchestration("MD 저장·양식 적용·파생 문서 생성 완료","done",resultModelLabel);
            setStatus("보고서 MCP 산출물 편집 중 · "+resultModelLabel);addAudit("Server","보고서 산출물 생성 · "+execution.id,"완료");
          }else{
            await refreshActiveProjectWorkspace();var markdownDocument=result.artifact.markdownDocument||{};
            if(markdownDocument.id)await openProjectWorkbench(markdownDocument.id,"markdown");
            var renderReason=result.artifact.rendering&&result.artifact.rendering.error||"HWPX renderer를 사용할 수 없습니다.";
            addAssistant("보고서 Markdown은 안전하게 저장했습니다. 완성 문서 생성만 실패했으며 ‘완성 문서 다시 만들기’로 재시도할 수 있습니다. ("+renderReason+")");
            updateOrchestration("MD 저장 완료 · 파생 문서 재생성 필요","done",resultModelLabel);setStatus("Markdown 저장됨 · HWPX 재생성 필요");addAudit("Server","보고서 MD 보존 · renderer 실패 · "+execution.id,"주의");
          }
          state.pendingPlan=null;return;
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
      var data=await api("/bootstrap");state.serverOnline=true;state.models=data.models||[];state.openrouter=data.openrouter||state.openrouter;state.externalMcpProfiles=(data.capabilities&&data.capabilities.externalMcpProfiles)||[];populateExternalMcpProfiles();
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
    if(!/\.(hwp|hwpx|hwt|hml|docx|xlsx|md|txt|py|js|ts|json)$/i.test(file.name)){toast("지원하는 편집기 MCP가 없는 파일입니다.");return}
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
  function updateWelcomeFiles(files){state.welcomeFiles=Array.from(files||[]);$("welcomeFileChip").hidden=!state.welcomeFiles.length;if(state.welcomeFiles.length)$("welcomeFileName").textContent=state.welcomeFiles.length===1?state.welcomeFiles[0].name:state.welcomeFiles.length+"개 자료 · "+state.welcomeFiles.map(function(file){return file.name}).join(", ")}
  async function launchWelcome(){
    if(!state.activeProjectId){showProjectGate();toast("프로젝트를 먼저 선택하세요.");return}
    var intent=$("welcomePrompt").value.trim();if(!intent){toast("원하는 작업을 입력하세요.");$("welcomePrompt").focus();return}
    if(!state.welcomeFiles.length){enterWorkspace(true);$("chat").innerHTML="";state.sourceContext=null;if(state.projectWorkbench){renderProjectWorkbenchTabs();await switchProjectWorkbenchTab(state.activeWorkbenchTab||"markdown")}else activateEmptyWorkspace();await submitIntent(intent);return}
    var files=state.welcomeFiles.slice();enterWorkspace(true);$("chat").innerHTML="";var user=document.createElement("div");user.className="message user";user.innerHTML="<div><small>첨부 · "+escapeHtml(files.map(function(file){return file.name}).join(", "))+"</small><br>"+escapeHtml(intent)+"</div>";$("chat").appendChild(user);
    try{
      var sourceable=files.filter(function(file){return/\.(pdf|hwpx|docx|xlsx|md|txt)$/i.test(file.name)}),added=await uploadProjectSourceFiles(sourceable);
      state.selectedProjectSourceIds=Array.from(new Set(state.selectedProjectSourceIds.concat(added.map(function(item){return item.id}))));
      state.sourceContext={filename:files.map(function(file){return file.name}).join(", "),excerpt:added.map(function(item){return item.excerpt||""}).join("\n").slice(0,8000),projectSourceIds:added.map(function(item){return item.id})};
      var editable=files.length===1&&!/\.pdf$/i.test(files[0].name);if(editable)await importHwpx(files[0],intent);
      await submitIntent(intent,{skipUser:true});updateWelcomeFiles([]);$("welcomeFile").value="";
    }catch(error){toast(error.message);addAssistant("첨부 자료를 처리하지 못했습니다: "+error.message)}
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
  $("welcomeFile").onchange=function(){updateWelcomeFiles(this.files)};
  $("welcomeFileRemove").onclick=function(){updateWelcomeFiles([]);$("welcomeFile").value=""};
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
  $("templateMcpHelp").onclick=function(){var artifact=state.projectWorkbench&&(state.projectWorkbench.artifacts||[]).find(function(item){return item.format==="hwpx"}),current=$("templateMcpSelect").value||appliedTemplateRef(artifact);openTemplateMcpUsage(current)};
  $("templateUsageChat").onclick=function(){var item=templateUsageEntry($("templateUsageDialog").dataset.packageRef),usage=item&&item.usage||defaultTemplateUsage(item),prompt=usage.quickPrompt;$("templateUsageDialog").close();if(!state.activeProjectId){if($("welcomePrompt"))$("welcomePrompt").value=prompt;showProjectGate();toast("프로젝트를 선택한 뒤 준비된 호출 문구를 실행하세요.");return}enterWorkspace(true);setView("editor");$("chatInput").value=prompt;$("chatInput").focus();toast("실제 호출 문구를 대화창에 넣었습니다. 내용을 확인한 뒤 전송하세요.")};
  $("templateUsageApply").onclick=function(){var ref=$("templateUsageDialog").dataset.packageRef,previous=$("templateMcpSelect").value;if(!ref)return toast("적용할 양식 MCP를 선택해 주세요.");$("templateUsageDialog").close();applyTemplateMcpImmediately(ref,previous)};
  $("templateUsageEdit").onclick=async function(){var ref=$("templateUsageDialog").dataset.packageRef,packageId=String(ref).split("@")[0],item=(state.mcps||[]).find(function(candidate){return candidate.id===packageId});if(!item)return toast("수정할 스토어 패키지를 찾을 수 없습니다.");$("templateUsageDialog").close();try{await forkStoreItemForEdit(item,false)}catch(error){toast(error.message)}};
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
