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
    pendingIntent:"",
    lastProposalIntent:"",
    pendingPlan:null,
    pendingStoreAction:"",
    builderDraft:null,
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
    $("orchestratorState").textContent=session?"의도 분석 완료 · "+loaded.length+"개 MCP 로딩":"문서 컨텍스트 사용 중";
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
    var candidates=document.querySelectorAll("#documentPaper h1,#documentPaper .doc-subtitle,#documentPaper td,#targetParagraph");
    candidates.forEach(function(node,index){node.dataset.editId=node.id||node.dataset.field||"document-field-"+index;node.contentEditable="true";node.spellcheck=true;node.setAttribute("role","textbox");node.setAttribute("aria-label","문서 내용 직접 편집")});
  }
  function initializeDirectEditing(){
    enableTemplateEditing();
    try{restoreDocumentSnapshot(JSON.parse(localStorage.getItem(state.documentStorageKey)||"null"))}catch(error){localStorage.removeItem(state.documentStorageKey)}
    state.documentSavedSnapshot=documentSnapshot();
    $("documentPaper").addEventListener("input",markDocumentDirty);
    $("documentPaper").addEventListener("focusin",function(event){if(event.target.closest("[contenteditable='true']")&&!state.documentUndoSnapshot)state.documentUndoSnapshot=documentSnapshot()});
    $("documentPaper").addEventListener("paste",function(event){var target=event.target.closest("[contenteditable='true']");if(!target)return;event.preventDefault();document.execCommand("insertText",false,(event.clipboardData||window.clipboardData).getData("text"))});
    $("documentPaper").addEventListener("keydown",function(event){if(event.key==="Enter"&&event.target.closest("td")){event.preventDefault();event.target.blur()}});
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
    if(state.activeView!=="editor")return;
    var workspace=state.workspaceDocuments.map(function(item){return"<button class='tree-row child' data-workspace-document='"+escapeHtml(item.id)+"'><span class='ext'>문</span>"+escapeHtml(item.name)+" <small>r"+item.revision+"</small></button>"}).join("");
    var versions=state.documentVersions.filter(function(item){return item.bytes}).slice(0,8).map(function(item){return"<button class='tree-row child' data-document-version='"+escapeHtml(item.id)+"'><span class='ext'>한</span>"+escapeHtml(item.filename)+" <small>"+Number(item.bytes).toLocaleString()+"B</small></button>"}).join("");
    $("sidebarContent").innerHTML="<div class='section-label'>작업 문서</div><div class='file-tree'><button class='tree-row' id='newWorkspaceDocument'>＋ 새 예산요청서</button>"+(workspace||"<div class='sidebar-empty'>저장된 작업 문서 없음</div>")+"</div><div class='section-label'>HWPX 산출물</div><div class='file-tree'>"+(versions||"<div class='sidebar-empty'>저장된 HWPX 버전 없음</div>")+"</div><div class='sidebar-stat'><div><span>작업 문서</span><b>"+state.workspaceDocuments.length+"개</b></div><div><span>HWPX 버전</span><b>"+state.documentVersions.length+"개</b></div></div>";
    $("newWorkspaceDocument").onclick=function(){if(state.documentDirty&&!window.confirm("저장하지 않은 편집을 버리고 새 문서를 열까요?"))return;activateTemplateDocument({},"새 예산요청서",null);toast("새 예산요청서를 열었습니다.")};
    document.querySelectorAll("[data-workspace-document]").forEach(function(button){button.onclick=function(){openWorkspaceDocument(button.dataset.workspaceDocument)}});
    document.querySelectorAll("[data-document-version]").forEach(function(button){button.onclick=function(){openDocumentVersion(button.dataset.documentVersion)}});
  }
  async function syncDocumentLibrary(){
    try{var results=await Promise.all([api("/documents/workspace"),api("/documents/versions")]);state.workspaceDocuments=results[0].items||[];state.documentVersions=results[1].items||[];renderEditorSidebar()}catch(error){if(state.activeView==="editor")setStatus("문서 목록을 불러오지 못함")}
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
  function renderSourceEditor(session){
    var paper=$("documentPaper"),snapshot=session.snapshot,content=String(snapshot.content||""),markdown=snapshot.language==="markdown";
    paper.className="paper source-editor-paper";
    paper.innerHTML="<div class='source-editor-header'><b>"+escapeHtml(session.filename)+"</b><small>"+escapeHtml(session.adapter)+"</small><span>UTF-8 · "+escapeHtml(snapshot.language)+"</span></div><div class='source-editor-shell "+(markdown?"markdown-mode":"")+"'><pre class='source-line-numbers' id='sourceLineNumbers'></pre><textarea class='source-editor' id='sourceEditor' spellcheck='false'></textarea>"+(markdown?"<div class='markdown-preview' id='markdownPreview'></div>":"")+"</div>";
    var editor=$("sourceEditor");editor.value=content;
    function updateSource(){var lines=editor.value.split("\n").length;$("sourceLineNumbers").textContent=Array.from({length:lines},function(_,index){return index+1}).join("\n");if(markdown)$("markdownPreview").innerHTML=renderMarkdownPreview(editor.value)}
    editor.onselect=function(){captureSourceSelection(editor)};editor.onkeyup=function(){captureSourceSelection(editor)};editor.onmouseup=function(){captureSourceSelection(editor)};
    editor.oninput=function(){state.sourceEditorDirty=true;updateSource();updateDocumentSaveState("직접 편집 중 · 저장 필요",true)};
    updateSource();state.documentMode="native-session";state.sourceEditorDirty=false;
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
      await editor.loadFile(bytes,session.filename,{skipUnsavedGuard:true,suppressDialogs:true});state.rhwpEditor=editor;$("rhwpEditorHost").dataset.ready="true";
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
  }
  async function renderNativeSession(session,selectionMode){
    state.nativeSession=session;state.nativeSelection=null;state.currentDocument=null;state.workspaceDocument=null;
    var nativeRhwp=session.snapshot.kind==="structured-hwpx"||session.snapshot.kind==="rhwp-web";
    $("workbench").classList.toggle("native-rhwp-mode",nativeRhwp);document.querySelector(".app-shell").classList.toggle("native-rhwp-shell",nativeRhwp);
    if(!nativeRhwp)["nativeCompactTitle","aiSelectionMode"].forEach(function(id){var node=$(id);if(node)node.remove()});
    $("activeFileName").textContent=session.filename;
    configureEditorPlugin(session);enterWorkspace(true);var oldPanel=$("nativeMcpPanel");if(oldPanel)oldPanel.remove();
    if(session.snapshot.kind==="structured-hwpx"){
      if(selectionMode){if(state.rhwpEditor){var current=state.rhwpEditor;state.rhwpEditor=null;current.destroy()}renderImportedHwpx(session.snapshot.document)}else await mountRhwpEditor(session);
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
      var session=await api("/documents/sessions/"+state.nativeSession.id+"/commands",{method:"POST",body:JSON.stringify({base_revision:state.nativeSession.revision,command:command,arguments:commandArguments,confirmed:true,actor:"workspace-user"})});
      if(options&&options.preserveEditor&&state.rhwpEditor){
        state.nativeSession=session;state.nativeSelection=null;$("activeFileName").textContent=session.filename;$("contextFile").textContent="⌁ "+session.filename;if($("nativeCompactTitle"))$("nativeCompactTitle").textContent=session.filename;
        $("contextSelection").textContent="선택 영역 없음";$("contextSelection").classList.remove("has-selection");
        updateDocumentSaveState("MCP 세션 r"+session.revision+" · 현재 화면 유지 · 원본 저장됨",false);
      }else{
        await renderNativeSession(session);
      }
      await syncDocumentLibrary();setStatus(session.adapter+" · revision "+session.revision+" 적용 완료");toast("문서 MCP가 원본 산출물에 변경을 적용했습니다.");addAudit("Document MCP",command+" · "+session.adapter+" · r"+session.revision,"완료");return true;
    }catch(error){setStatus("문서 MCP 명령 실패");toast(error.message);return false}
  }
  function applyNativeSelection(){
    if(!state.nativeSession)return;
    var before=$("nativeBefore").value;var after=$("nativeAfter").value;
    if(!before){toast("선택하거나 찾을 원문이 필요합니다.");return}
    if(before===after){toast("변경할 내용이 원문과 같습니다.");return}
    runNativeSessionCommand("replace_selection",{target:state.nativeSelection&&state.nativeSelection.target||"",before:before,after:after});
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
        if($("sourceEditor")&&state.sourceEditorDirty){var sourceSaved=await runNativeSessionCommand("replace_document",{content:$("sourceEditor").value});if(sourceSaved)state.sourceEditorDirty=false;return sourceSaved}
        if(state.rhwpEditor&&/^(hwp|hwpx|hwt|hml)$/.test(state.nativeSession.format)){
          var outputFormat=state.nativeSession.format==="hwpx"?"hwpx":state.nativeSession.format==="hml"?"hml":"hwp";
          var bytes=outputFormat==="hwpx"?await state.rhwpEditor.exportHwpx():outputFormat==="hml"?await state.rhwpEditor.exportHml():await state.rhwpEditor.exportHwp();var binary="";for(var offset=0;offset<bytes.length;offset+=32768)binary+=String.fromCharCode.apply(null,bytes.subarray(offset,offset+32768));
          return await runNativeSessionCommand("replace_artifact",{contentBase64:btoa(binary),format:outputFormat},{preserveEditor:true});
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
  function undoDirectEdit(){
    if(!state.documentUndoSnapshot){toast("되돌릴 직접 편집 내용이 없습니다.");return}
    restoreDocumentSnapshot(state.documentUndoSnapshot);state.documentUndoSnapshot=null;clearTimeout(state.documentAutoSaveTimer);
    saveBrowserDocumentDraft(false);updateDocumentSaveState("직접 편집을 되돌림",false);toast("마지막 직접 편집을 되돌렸습니다.");
  }
  function setView(view){
    state.activeView=view;
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
  }

  function renderData(){
    var rows=state.commonData.map(function(item){
      return "<tr data-key='"+escapeHtml(item.key)+"'><td><b>"+escapeHtml(item.label)+"</b><br><small>"+escapeHtml(item.key)+"</small></td><td>"+escapeHtml(item.value)+"</td><td><span class='type-chip'>"+escapeHtml(item.kind)+"</span></td><td>"+escapeHtml(item.date)+"</td><td><button class='inline-link source-button'>"+escapeHtml(item.source)+"</button></td><td class='confidence'>"+item.confidence+"%</td></tr>";
    }).join("");
    $("dataView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Grounded Knowledge Layer</span><h1>공통데이터와 지식 탐색</h1><p>문서 값, 노트와 출처를 연결하고 현재 값·특정 시점·변화량을 근거와 함께 조회합니다.</p></div><div class='module-actions'><button id='refreshKnowledge'>지식 그래프 새로고침</button><button class='primary' id='addDataButton'>＋ 값 추가</button></div></div><div class='cards'><div class='metric-card'><span>지식 노드</span><b id='knowledgeNodeCount'>-</b><small>문서·데이터·노트</small></div><div class='metric-card'><span>출처 연결</span><b id='knowledgeSourceCount'>-</b><small>근거 없는 답변 차단</small></div><div class='metric-card'><span>관계</span><b id='knowledgeEdgeCount'>-</b><small>출처·활용 연결</small></div></div><section class='surface'><div class='surface-head'><h2>출처 기반 질의응답</h2><small>내부 데이터 · 로컬 검색</small></div><div class='knowledge-query'><input id='knowledgeQuestion' value='SW 기술자 월평균임금은 얼마인가?'><input id='knowledgeAsOf' type='date' value='2026-08-11'><button class='primary' id='askKnowledge'>근거 찾기</button></div><div class='knowledge-answer' id='knowledgeAnswer'>질문하면 답변과 원문 위치가 함께 표시됩니다.</div></section><section class='surface'><div class='surface-head'><h2>현재 문서 데이터</h2><small>기준일 2026-08-11</small></div><table class='data-table'><thead><tr><th>항목</th><th>현재 값</th><th>유형</th><th>기준일</th><th>출처 위치</th><th>신뢰도</th></tr></thead><tbody>"+rows+"</tbody></table></section><section class='surface'><div class='surface-head'><h2>SW 기술자 월평균임금 · 시점 비교</h2><small id='knowledgeDelta'>계산 중</small></div><div class='timeline' id='knowledgeTimeline'></div></section><section class='surface'><div class='surface-head'><h2>지식 관계</h2><small>노트 ↔ 공통데이터 ↔ 원문</small></div><div class='knowledge-grid' id='knowledgeGraph'>그래프를 불러오는 중입니다.</div></section></div>";
    document.querySelectorAll(".source-button").forEach(function(button){button.onclick=function(){toast("원문 위치를 열었습니다: "+button.textContent);setView("editor")}});
    $("addDataButton").onclick=function(){toast("새 공통데이터 등록 폼은 다음 버전에서 서버 저장소와 연결됩니다.")};
    $("refreshKnowledge").onclick=function(){loadKnowledgeGraph(true)};
    $("askKnowledge").onclick=askKnowledge;
    $("knowledgeQuestion").onkeydown=function(event){if(event.key==="Enter")askKnowledge()};
    loadKnowledgeGraph(false);loadKnowledgeComparison();
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
      var result=await api("/knowledge/compare",{method:"POST",body:JSON.stringify({record_id:"cost.engineer.monthly",from_date:"2025-12-31",to_date:"2026-12-31"})});
      $("knowledgeDelta").textContent="변화량 "+Number(result.delta).toLocaleString()+"원 · "+(result.percentChange>=0?"+":"")+result.percentChange+"%";
      $("knowledgeTimeline").innerHTML=[result.from,result.to].map(function(item,index){return"<div><b>"+escapeHtml(item.effectiveDate)+(index?" 현재":"")+"</b><span>"+Number(item.value).toLocaleString()+" "+escapeHtml(result.unit)+"</span><small>"+escapeHtml(item.source.documentId)+" · "+escapeHtml(item.source.locator)+"</small></div>"}).join("");
    }catch(error){$("knowledgeTimeline").textContent=error.message}
  }

  async function loadKnowledgeGraph(notify){
    try{
      var graph=await api("/knowledge/graph");$("knowledgeNodeCount").textContent=graph.counts.nodes;$("knowledgeSourceCount").textContent=graph.counts.sources;$("knowledgeEdgeCount").textContent=graph.counts.edges;
      var names={};graph.nodes.forEach(function(node){names[node.id]=node.title});
      $("knowledgeGraph").innerHTML=graph.edges.map(function(edge){return"<div class='knowledge-edge'><span>"+escapeHtml(names[edge.source]||edge.source)+"</span><b>"+escapeHtml(edge.relation)+"</b><span>"+escapeHtml(names[edge.target]||edge.target)+"</span><small>"+Math.round(edge.weight*100)+"%</small></div>"}).join("");
      if(notify)toast("지식 노드, 관계와 출처를 새로 불러왔습니다.");
    }catch(error){$("knowledgeGraph").textContent=error.message}
  }

  function highlightJson(text){return escapeHtml(text).replace(/(&quot;[^&]+?&quot;)(?=\s*:)/g,"<span class='key'>$1</span>").replace(/:\s*(&quot;.*?&quot;)/g,": <span class='string'>$1</span>")}
  function showBuilderDraft(draft){
    state.builderDraft=draft;
    $("manifestPreview").innerHTML=highlightJson(JSON.stringify(draft.manifest,null,2));
    var passed=draft.validation&&draft.validation.passed;
    $("manifestStatus").textContent=draft.status==="published"?"스토어 게시 완료":passed?"샌드박스 검증 통과":draft.status==="rejected"?"검증 실패":"서버 초안 저장됨";
    $("testList").innerHTML=(draft.validation.tests||[]).length?(draft.validation.tests||[]).map(function(test){return"<div><i>"+(test.passed?"✓":"×")+"</i> "+escapeHtml(test.id)+" · "+escapeHtml(test.detail)+"</div>"}).join(""):"<div><i>○</i> Manifest 생성 후 서버 샌드박스 검증을 실행하세요.</div>";
    $("publishMcp").disabled=draft.status!=="validated";
    $("runSandbox").disabled=draft.status==="published";
    $("mcpName").value=draft.manifest.name||"";
    $("mcpPackageId").value=draft.manifest.id||"";
    $("mcpVersion").value=draft.manifest.version||"0.1.0";
    $("mcpDescription").value=draft.manifest.description||"";
    var visibility=document.querySelector("input[name='visibility'][value='"+draft.manifest.visibility+"']");
    if(visibility)visibility.checked=true;
    $("sourceIncluded").checked=Boolean(draft.manifest.sourceIncluded);
    $("allowExternal").checked=draft.manifest.runtime!=="local";
    $("referenceList").innerHTML=(draft.references||[]).length?(draft.references||[]).map(function(item){var summary=item.summary||{};return"<div class='reference-item'><b>"+escapeHtml(item.filename)+"</b><span>"+Number(item.bytes).toLocaleString()+" bytes · "+escapeHtml((item.sha256||"").slice(0,12))+"…</span><small>"+escapeHtml(summary.excerpt||summary.kind||"구조 검사 완료")+"</small></div>"}).join(""):"<div class='empty-reference'>첨부 없음 · HWPX, PDF, Markdown, TXT 지원</div>";
  }
  async function loadBuilderDrafts(){
    try{
      var result=await api("/builder/drafts");var items=result.items||[];
      $("builderDraftList").innerHTML=items.length?items.slice(0,8).map(function(item){return"<button data-draft-id='"+escapeHtml(item.id)+"'><b>"+escapeHtml(item.manifest.name)+"</b><span>"+escapeHtml(item.status)+" · "+(item.references||[]).length+"개 문서</span><small>"+escapeHtml(item.manifest.id)+"@"+escapeHtml(item.manifest.version)+"</small></button>"}).join(""):"<span class='empty-reference'>저장된 초안이 없습니다.</span>";
      document.querySelectorAll("[data-draft-id]").forEach(function(button){button.onclick=function(){var draft=items.find(function(item){return item.id===button.dataset.draftId});if(draft){showBuilderDraft(draft);toast(draft.manifest.name+" 초안을 다시 열었습니다.")}}});
    }catch(error){$("builderDraftList").textContent=error.message}
  }
  function renderBuilder(){
    $("builderView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>MCP Studio</span><h1>플랫폼 전용 MCP 제작기</h1><p>자연어 업무 설명을 서버에 저장된 계약으로 변환하고, 검증된 버전만 서명해 스토어에 등록합니다.</p></div><div class='module-actions'><button class='primary' id='publishMcp' disabled>검증 후 스토어 등록</button></div></div><section class='surface draft-history'><div class='surface-head'><h2>저장된 제작 작업</h2><small>초안·검증·게시 상태</small></div><div id='builderDraftList' class='draft-list'>불러오는 중...</div></section><div class='builder-grid'><section class='surface'><div class='surface-head'><h2>1. 목적과 사용 조건</h2><small>자연어 → 구조화 계약</small></div><label class='field'><span>MCP 이름</span><input id='mcpName' value='예산 검증 MCP'></label><div class='builder-id-grid'><label class='field'><span>패키지 ID · 비우면 자동 생성</span><input id='mcpPackageId' placeholder='org.budget-checker'></label><label class='field'><span>버전</span><input id='mcpVersion' value='0.1.0'></label></div><label class='field'><span>어떤 업무를 처리하나요?</span><textarea id='mcpDescription' rows='6'>예산요청서에서 필수 항목 누락과 산출 근거 오류를 찾고, 최신 SW대가 기준과 비교해 수정안을 제안한다. 원문은 외부로 보내지 않는다.</textarea></label><div class='field'><span>기준 문서 · 외부 전송 없이 구조 검사</span><div id='referenceList' class='reference-list'><div class='empty-reference'>초안을 만든 뒤 실제 기준 문서를 첨부하세요.</div></div></div><input id='referenceFile' type='file' accept='.hwpx,.pdf,.md,.txt' hidden><div class='toggle-row'><label><input type='radio' name='visibility' value='private'> 개인 전용</label><label><input type='radio' name='visibility' value='organization' checked> 조직 공개</label><label><input type='radio' name='visibility' value='public'> 공개</label></div><div class='toggle-row'><label><input type='checkbox' id='sourceIncluded'> 게시 패키지에 원본 포함</label><label><input type='checkbox' id='allowExternal'> 외부 모델·MCP 전송 허용</label></div><div class='form-actions'><button id='attachReference'>＋ 기준 문서 첨부</button><button class='primary' id='generateManifest'>새 초안·Manifest 생성</button></div></section><section class='surface'><div class='surface-head'><h2>2. Manifest 미리보기</h2><small id='manifestStatus'>아직 생성되지 않음</small></div><pre class='code-preview' id='manifestPreview'>서버 초안을 생성하면 계약이 표시됩니다.</pre></section></div><section class='surface'><div class='surface-head'><h2>3. 샌드박스 계약 테스트</h2><button class='inline-link' id='runSandbox' disabled>전체 테스트 실행</button></div><div class='test-list' id='testList'><div><i>○</i> Manifest 생성 후 서버 샌드박스 검증을 실행하세요.</div></div></section></div>";
    $("generateManifest").onclick=async function(){
      try{
        setStatus("MCP 계약 생성 중");
        var visibility=document.querySelector("input[name='visibility']:checked").value;
        var draft=await api("/builder/drafts",{method:"POST",body:JSON.stringify({name:$("mcpName").value,package_id:$("mcpPackageId").value,version:$("mcpVersion").value,description:$("mcpDescription").value,visibility:visibility,source_included:$("sourceIncluded").checked,allow_external:$("allowExternal").checked,actor:"workspace-user"})});
        showBuilderDraft(draft);$("runSandbox").disabled=false;setStatus("MCP 초안 저장됨");toast("서버에 Manifest와 입출력 Schema 초안을 저장했습니다.");addAudit("MCP 제작기","초안 생성 · "+draft.manifest.id,"완료");
      }catch(error){setStatus("MCP 초안 생성 실패");toast(error.message)}
    };
    $("runSandbox").onclick=async function(){
      if(!state.builderDraft)return toast("먼저 Manifest를 생성하세요.");
      try{
        setStatus("샌드박스 계약 테스트 실행 중");$("testList").innerHTML="<div><i>◌</i> 계약, 고정 의존성, 최소권한과 전송 경계를 검사 중...</div>";
        var draft=await api("/builder/drafts/"+state.builderDraft.id+"/validate",{method:"POST",body:JSON.stringify({actor:"workspace-user"})});
        showBuilderDraft(draft);setStatus(draft.validation.passed?"샌드박스 검증 통과":"샌드박스 검증 실패");toast(draft.validation.passed?"모든 계약 테스트를 통과했습니다.":"검증 실패 항목을 확인하세요.");addAudit("Sandbox","MCP 계약 테스트 "+draft.validation.tests.filter(function(item){return item.passed}).length+"/"+draft.validation.tests.length,draft.validation.passed?"완료":"차단");
      }catch(error){setStatus("샌드박스 검증 실패");toast(error.message)}
    };
    $("publishMcp").onclick=async function(){
      var draft=state.builderDraft;if(!draft||draft.status!=="validated")return;
      try{
        setStatus("MCP 패키지 서명·게시 중");
        var result=await api("/builder/drafts/"+draft.id+"/publish",{method:"POST",body:JSON.stringify({actor:"workspace-user",confirm_visibility:draft.manifest.visibility,confirm_source_included:draft.manifest.sourceIncluded})});
        showBuilderDraft(result.draft);await syncStore(false);setStatus("MCP 스토어 게시 완료");toast(result.package.manifest.name+" v"+result.package.version+"을 서명해 게시했습니다.");addAudit("MCP 제작기","스토어 게시 · "+result.package.packageId+"@"+result.package.version,"완료");setView("store");
      }catch(error){setStatus("MCP 게시 실패");toast(error.message)}
    };
    $("attachReference").onclick=function(){if(!state.builderDraft||state.builderDraft.status==="published")return toast("먼저 새 초안을 생성하세요.");$("referenceFile").click()};
    $("referenceFile").onchange=async function(){var file=this.files&&this.files[0];if(!file)return;try{setStatus("기준 문서 구조와 SHA-256 검사 중");var result=await api("/builder/drafts/"+state.builderDraft.id+"/references",{method:"POST",body:JSON.stringify({filename:file.name,content_base64:await fileBase64(file),actor:"workspace-user"})});showBuilderDraft(result.draft);await loadBuilderDrafts();setStatus("기준 문서 로컬 저장 완료");toast(file.name+"을 외부 전송 없이 초안에 연결했습니다.")}catch(error){setStatus("기준 문서 첨부 실패");toast(error.message)}finally{this.value=""}};
    if(state.builderDraft)showBuilderDraft(state.builderDraft);
    loadBuilderDrafts();
  }

  function renderStore(filter){
    var term=String(filter||"").toLowerCase();
    var list=state.mcps.filter(function(item){return !term||item.name.toLowerCase().indexOf(term)>=0||item.desc.toLowerCase().indexOf(term)>=0});
    var cards=list.map(function(item){
      var installed=Boolean(item.installedVersion);var update=installed&&item.installedVersion!==item.version;
      var action=update?"<button data-install='"+escapeHtml(item.id)+"'>v"+escapeHtml(item.version)+" 업데이트</button>":(!installed?"<button data-install='"+escapeHtml(item.id)+"'>권한 확인 후 설치</button>":(item.rollbackVersion?"<button data-rollback='"+escapeHtml(item.id)+"'>v"+escapeHtml(item.rollbackVersion)+" 롤백</button>":"<button class='installed' disabled>v"+escapeHtml(item.installedVersion)+" 고정</button>"));
      return "<article class='store-card'><div class='store-card-head'><span class='mcp-logo'>⌘</span><div><h3>"+escapeHtml(item.name)+"</h3><div class='store-meta'><span>"+escapeHtml(item.publisher)+"</span><span>최신 v"+escapeHtml(item.version)+"</span><span>✓ 서명 · 취약점 0</span></div></div></div><p>"+escapeHtml(item.desc)+"</p><div>"+item.permissions.map(function(p){return "<span class='permission-chip'>"+escapeHtml(p)+"</span> "}).join("")+"</div><footer><span class='type-chip'>"+escapeHtml(item.runtime)+(installed?" · 설치 v"+escapeHtml(item.installedVersion):"")+"</span>"+action+"</footer></article>";
    }).join("");
    var quarantine=state.quarantined.length?"<div class='quarantine-warning'><b>검증 실패 패키지 "+state.quarantined.length+"개 격리</b><span>"+state.quarantined.map(function(item){return escapeHtml(item.packageId+"@"+item.version)}).join(", ")+"</span></div>":"";
    $("storeView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Signed MCP Marketplace</span><h1>조직 MCP 스토어</h1><p>조직 서명과 패키지 해시를 검증하고 승인된 권한으로 정확한 버전을 고정 설치합니다.</p></div><div class='module-actions'><button data-view-jump='builder'>내 MCP 만들기</button></div></div>"+quarantine+"<div class='store-toolbar'><input class='store-search' id='storeSearch' placeholder='MCP 이름, 업무 또는 게시자 검색' value='"+escapeHtml(filter||"")+"'><button class='filter-button' id='refreshStore'>서명 다시 검증</button></div><div class='store-grid'>"+cards+"</div></div>";
    $("storeSearch").oninput=function(){renderStore(this.value);var input=$("storeSearch");input.focus();input.setSelectionRange(input.value.length,input.value.length)};
    document.querySelector("[data-view-jump]") .onclick=function(){setView("builder")};
    $("refreshStore").onclick=function(){syncStore(true)};
    document.querySelectorAll("[data-install]").forEach(function(button){button.onclick=function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.install});state.pendingStoreAction="install";item.targetVersion=item.version;state.pendingIntent=item.name+" v"+item.targetVersion+"을 서명 검증 후 고정 설치";showApproval(state.pendingIntent,true,item)}});
    document.querySelectorAll("[data-rollback]").forEach(function(button){button.onclick=function(){var item=state.mcps.find(function(mcp){return mcp.id===button.dataset.rollback});state.pendingStoreAction="rollback";item.targetVersion=item.rollbackVersion;state.pendingIntent=item.name+"을 검증된 v"+item.targetVersion+"으로 롤백";showApproval(state.pendingIntent,true,item)}});
  }

  async function syncStore(notify){
    try{
      var data=await api("/store/packages");
      state.quarantined=data.quarantined||[];
      state.mcps=(data.items||[]).map(function(item){return{id:item.packageId,name:item.name,version:item.versions[0].version,versions:item.versions,installedVersion:item.installedVersion,rollbackVersion:item.rollbackVersion,runtime:item.runtime,desc:item.description,permissions:item.permissions,rating:"서명됨",publisher:item.publisher}});
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

  function renderSettings(){
    var models=(state.models||[]).map(function(model){return"<article class='store-card'><div class='store-card-head'><span class='mcp-logo'>AI</span><div><h3>"+escapeHtml(model.label)+"</h3><div class='store-meta'><span>"+escapeHtml(model.personality)+"</span><span>입력 $0</span><span>출력 $0</span></div></div></div><p>"+escapeHtml(model.description)+"</p><div>"+model.strengths.slice(0,3).map(function(item){return"<span class='permission-chip'>"+escapeHtml(item)+"</span> "}).join("")+"</div><footer><span class='type-chip'>:free 전용</span><small>"+Number(model.contextTokens).toLocaleString()+" context</small></footer></article>"}).join("");
    var presetCards=(state.presets||[]).map(function(preset){return"<article class='store-card'><div class='store-card-head'><span class='mcp-logo'>"+escapeHtml(preset.modality.slice(0,2).toUpperCase())+"</span><div><h3>"+escapeHtml(preset.name)+"</h3><div class='store-meta'><span>"+escapeHtml(preset.modality)+"</span><span>"+(preset.status==="ready"?"실행 준비":"계약 미리보기")+"</span></div></div></div><p>"+escapeHtml(preset.description)+"</p><div>"+preset.acceptedFormats.map(function(format){return"<span class='permission-chip'>"+escapeHtml(format)+"</span> "}).join("")+"</div><footer><span class='type-chip'>"+escapeHtml(preset.status)+"</span><button data-workflow='"+escapeHtml(preset.id)+"'>계획 확인</button></footer></article>"}).join("");
    $("settingsView").innerHTML="<div class='module-page'><div class='module-hero'><div><span class='eyebrow'>Model & Workflow Management</span><h1>모델 관리와 업무 프리셋</h1><p>의도와 파일 형식에 따라 무료 모델과 최소권한 어댑터 실행 순서를 선택합니다.</p></div><div class='module-actions'><button class='primary' id='saveSettings'>설정 저장</button></div></div><div class='store-grid'>"+models+"</div><section class='surface routing-lab'><div class='surface-head'><h2>의도별 자동 전환 테스트</h2><small>"+(state.openrouter.configured?"API Key 연결됨":"API Key 미설정 · 선택만 검증")+"</small></div><div class='toggle-row'><label><input type='checkbox' id='liveRouteTest' "+(state.openrouter.configured?"":"disabled")+"> OpenRouter 실제 무료 호출 포함</label><label><input type='checkbox' checked disabled> :free 외 모델 차단</label></div><div class='route-test-actions'><button data-route-intent='선택 문장을 2줄 공문체로 다듬어줘'>문서 작성 의도 테스트</button><button data-route-intent='최신 기준과 비교해 예산 산출 근거를 검증해줘'>복합 추론 의도 테스트</button></div><pre class='code-preview route-result' id='routeResult'>테스트를 선택하면 의도 유형, 선택 모델과 선택 근거가 표시됩니다.</pre></section><section class='surface workflow-lab'><div class='surface-head'><h2>멀티모달 업무 프리셋</h2><div><input id='assetInspectorInput' type='file' accept='.py,.js,.ts,.json,.md,.png,.jpg,.jpeg,.wav,.mp4' hidden><button class='inline-link' id='inspectAssetButton'>파일 로컬 검사</button></div></div><div class='store-grid'>"+presetCards+"</div><pre class='code-preview workflow-result' id='workflowResult'>프리셋 계획 또는 로컬 파일 검사 결과가 표시됩니다.</pre></section><section class='surface'><div class='surface-head'><h2>데이터·권한 정책</h2><small>기본 거부</small></div><div class='toggle-row'><label><input type='checkbox' checked> 개인정보 자동 마스킹</label><label><input type='checkbox' checked> 외부 전송 매회 승인</label><label><input type='checkbox' checked> 실행 감사 로그</label></div></section></div>";
    $("settingsView").querySelector(".module-page").insertAdjacentHTML("beforeend","<section class='surface'><div class='surface-head'><h2>RHWP 전체 기능 MCP</h2><small id='rhwpRuntimeStatus'>브리지 확인 중</small></div><p class='empty-reference'>HAction/HParameterSet을 포함한 한글 자동화 기능은 문서 읽기·쓰기 승인 후 같은 사용자 Windows 브리지에서 실행됩니다.</p><div class='toggle-row' id='rhwpToolCatalog'>도구 목록을 불러오는 중입니다.</div></section>");
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
    $("transferDescription").textContent=external?"선택 문단이 OpenRouter 무료 endpoint로 전송됩니다. 원본 파일 전체와 공통데이터 전체는 전송하지 않습니다.":"외부 모델 전송이 없는 로컬 작업입니다.";
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
        setStatus(item.name+" v"+pinned+" 고정 완료");toast(item.name+" v"+pinned+" "+(action==="rollback"?"롤백":"설치")+"을 완료했습니다.");addAudit("MCP Store",(action==="rollback"?"롤백":"서명 검증 설치")+" · "+item.id+"@"+pinned,"완료");renderStore();
      }catch(error){setStatus("MCP 패키지 처리 실패");toast(error.message);addAudit("MCP Store",item.id+" · "+error.message,"차단")}
      return;
    }
    if(state.pendingPlan){
      try{
        setStatus("서명된 승인 토큰 발급 중");
        var plan=state.pendingPlan;
        var approval=await api("/approvals",{method:"POST",body:JSON.stringify({plan_id:plan.id,actor:"demo-user",permissions:plan.requiredPermissions})});
        setStatus("서버 샌드박스 실행 대기");
        var activeSelection=state.nativeSession&&state.nativeSelection&&state.nativeSelection.before?state.nativeSelection:null;
        var selectionText=activeSelection?activeSelection.before:$("targetParagraph").textContent;
        var selectionId=activeSelection?(activeSelection.target||"document.native-selection"):(state.currentDocument?state.currentDocument.target:"document.paragraph.background");
        addAssistant(activeSelection?"승인된 선택 문구만 실제 LLM에 전송합니다. 원본 파일 전체는 전송하지 않습니다.":"승인 토큰이 발급되었습니다. 토큰은 한 번만 사용할 수 있습니다.");
        var execution=await api("/executions",{method:"POST",body:JSON.stringify({approval_token:approval.approvalToken,idempotency_key:"web-"+plan.id,input:{selection:selectionText,selection_id:selectionId,require_live_model:Boolean(activeSelection)}})});
        var patch=execution.result&&execution.result.patches&&execution.result.patches[0];
        if(!patch)throw new Error("서버 실행 결과에 문서 변경안이 없습니다.");
        if(String(patch.after||"").trim()===String(patch.before||"").trim())throw new Error("모델이 원문과 동일한 문장을 반환하여 변경 제안을 중단했습니다.");
        var model=execution.result.model||{},modelLabel=model.resolvedModel||model.name||"선택 모델";state.lastProposalIntent=intent;
        $("beforeText").textContent="- "+patch.before;$("afterText").textContent="+ "+patch.after;$("proposal").dataset.before=patch.before;$("proposal").dataset.after=patch.after;$("proposal").dataset.executionId=execution.id;$("proposalIntent").textContent=(model.mode==="live"?"실제 LLM":"모델")+" · "+modelLabel+" · "+execution.id;$("proposal").hidden=false;
        setStatus("실제 LLM 생성 완료 · 변경 제안 준비됨");addAssistant(modelLabel+"이 수정 지시를 반영한 문구를 생성했습니다. 비교 후 적용해 주세요.");addAudit("Server","LLM 문구 생성 완료 · "+modelLabel+" · "+execution.id,"완료");
        state.pendingPlan=null;setView("editor");return;
      }catch(error){
        state.pendingPlan=null;setStatus("서버 실행 실패");addAssistant("서버 실행을 완료하지 못했습니다: "+error.message);toast(error.message);return;
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
  function addAssistant(text){
    var node=document.createElement("div");node.className="message assistant";node.innerHTML="<span class='mini-orb'>✦</span><div><p>"+escapeHtml(text)+"</p></div>";$("chat").appendChild(node);$("chat").scrollTop=$("chat").scrollHeight;
  }
  function streamAssistant(text){
    var node=document.createElement("div");node.className="message assistant streaming";node.innerHTML="<span class='mini-orb'>✦</span><div><p></p></div>";$("chat").appendChild(node);var output=node.querySelector("p"),chars=Array.from(String(text||"")),index=0;
    return new Promise(function(resolve){var timer=setInterval(function(){index=Math.min(chars.length,index+Math.max(1,Math.ceil(chars.length/45)));output.textContent=chars.slice(0,index).join("");$("chat").scrollTop=$("chat").scrollHeight;if(index>=chars.length){clearInterval(timer);node.classList.remove("streaming");resolve(node)}},18)});
  }
  async function proposeNativeSelection(intent){
    var selection=state.nativeSelection,documentId=state.nativeSession?state.nativeSession.id:"native-document";
    addAssistant("선택한 글귀와 수정 지시를 분석해 실제 LLM 실행 계획을 만들고 있습니다.");
    try{
      setStatus("선택 문구 LLM 실행 계획 생성 중");
      state.pendingPlan=await api("/plans",{method:"POST",body:JSON.stringify({intent:intent,actor:"demo-user",document_context:{document_id:documentId,classification:"internal",selection_id:selection.target||"document.native-selection"}})});
      state.serverOnline=true;addAssistant("사용할 모델과 외부 전송 범위를 확인한 뒤 실행을 승인해 주세요.");
      setStatus("선택 문구 외부 전송 승인 대기");showApproval(intent,false,null);
    }catch(error){
      state.pendingPlan=null;addAssistant("LLM 실행 계획을 만들지 못했습니다: "+error.message);setStatus("LLM 실행 계획 실패");toast(error.message);
    }
  }
  async function submitIntent(intent){
    intent=String(intent||"").trim();if(!intent)return;
    var user=document.createElement("div");user.className="message user";user.innerHTML="<div>"+escapeHtml(intent)+"</div>";$("chat").appendChild(user);$("chatInput").value="";$("chat").scrollTop=$("chat").scrollHeight;
    if(state.nativeSession&&state.rhwpEditor){
      if(!state.nativeSelection||!state.nativeSelection.rhwpNative)await captureRhwpSelection(true);
      if(state.nativeSelection&&state.nativeSelection.before){await proposeNativeSelection(intent);return}
      addAssistant("RHWP 편집기에서 먼저 바꿀 문구를 마우스로 선택한 뒤 같은 요청을 보내 주세요.");setStatus("RHWP 선택 영역 대기");return
    }
    if(state.nativeSession&&state.nativeSelection&&state.nativeSelection.before){await proposeNativeSelection(intent);return}
    addAssistant("요청을 분석하고 서버에 실행 계획을 저장하고 있습니다.");
    try{
      setStatus("서버 실행 계획 생성 중");
      var documentId=state.currentDocument?state.currentDocument.id:"doc-budget-2027-01";
      var selectionId=state.currentDocument?state.currentDocument.target:"document.paragraph.background";
      state.pendingPlan=await api("/plans",{method:"POST",body:JSON.stringify({intent:intent,actor:"demo-user",document_context:{document_id:documentId,classification:"internal",selection_id:selectionId}})});
      state.serverOnline=true;
      addAssistant("실행 계획 "+state.pendingPlan.id+"을 저장했습니다. 필요한 권한과 실행 순서를 확인해 주세요.");
      setStatus("사용자 승인 대기");showApproval(intent,false,null);
    }catch(error){
      state.pendingPlan=null;addAssistant("서버 계획 생성에 실패했습니다. 실행하지 않았습니다: "+error.message);setStatus("계획 생성 실패");toast(error.message);
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
      await syncStore(false);
      await syncWorkflowPresets();
      document.querySelector(".local-badge").innerHTML="<i></i> 서버 샌드박스 v"+escapeHtml(data.version);
      setStatus("서버 실행 계층 연결됨 · 승인 토큰 "+data.policies.approvalTokenTtlSeconds+"초");
    }catch(error){state.serverOnline=false;setStatus("서버 실행 계층 연결 실패")}
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
    if(!/\.(hwp|hwpx|hwt|hml|md|txt|py|js|ts|json)$/i.test(file.name)){toast("지원하는 편집기 MCP가 없는 파일입니다.");return}
    try{
      setStatus("의도 분석 · 문서 MCP 선택 중");
      var contentBase64=await fileBase64(file);
      state.undoDocument=null;state.workspaceDocument=null;
      var session=await api("/documents/sessions",{method:"POST",body:JSON.stringify({filename:file.name,content_base64:contentBase64,intent:intent||"이 문서를 원본 형식과 구조를 유지하며 열고 수정",confirmed:true,actor:"workspace-user"})});
      await renderNativeSession(session);
      await streamAssistant("의도 분석 결과 ‘"+(session.intentAnalysis.label||session.intentAnalysis.intentType)+"’ 작업으로 분류했습니다. "+session.workspace.loadedMcps.length+"개 MCP를 순서대로 로딩했습니다.");
      var pipeline=document.createElement("div");pipeline.className="message assistant";pipeline.innerHTML="<span class='mini-orb'>⌘</span><div><p><b>실행 파이프라인</b></p><div class='pipeline'>"+session.workspace.pipeline.map(function(step,index){return"<span>"+(index+1)+". "+escapeHtml(step)+"</span>"}).join("")+"</div></div>";$("chat").appendChild(pipeline);$("chat").scrollTop=$("chat").scrollHeight;
      setStatus(session.adapter+" 로딩 완료 · "+session.runtime);
      toast("문서 MCP 세션을 열었습니다.");addAudit("Core Orchestrator","문서 MCP 로딩 · "+session.adapter,"완료");
    }catch(error){setStatus("문서 MCP 로딩 실패");toast(error.message);addAssistant("문서를 열지 못했습니다: "+error.message)}
    finally{$("hwpxFile").value=""}
  }
  function updateWelcomeFile(file){state.welcomeFile=file||null;$("welcomeFileChip").hidden=!file;if(file)$("welcomeFileName").textContent=file.name}
  async function launchWelcome(){
    var intent=$("welcomePrompt").value.trim();if(!intent){toast("원하는 작업을 입력하세요.");$("welcomePrompt").focus();return}
    if(!state.welcomeFile){enterWorkspace(true);$("chat").innerHTML="";addAssistant("요청을 시작했습니다. 작업할 문서를 첨부하면 형식에 맞는 편집기 MCP를 자동으로 불러옵니다.");$("chatInput").value=intent;$("chatInput").focus();return}
    var file=state.welcomeFile;enterWorkspace(true);$("chat").innerHTML="";var user=document.createElement("div");user.className="message user";user.innerHTML="<div><small>첨부 · "+escapeHtml(file.name)+"</small><br>"+escapeHtml(intent)+"</div>";$("chat").appendChild(user);
    await importHwpx(file,intent);
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

  document.querySelectorAll(".activitybar button[data-view]").forEach(function(button){button.onclick=function(){setView(button.dataset.view)}});
  document.addEventListener("click",function(event){
    var quick=event.target.closest("[data-prompt]");if(quick)submitIntent(quick.dataset.prompt);
    var link=event.target.closest("[data-view-link]");if(link)setView(link.dataset.viewLink);
    var nativeBlock=event.target.closest("#documentPaper [data-native-target]");if(nativeBlock)selectNativeBlock(nativeBlock);
  });
  $("chatForm").onsubmit=function(event){event.preventDefault();submitIntent($("chatInput").value)};
  $("chatInput").addEventListener("focus",function(){if(state.nativeSession&&state.rhwpEditor)captureRhwpSelection(true)});
  $("commandButton").onclick=function(){$("chatInput").focus();toast("AI Orchestrator에 작업을 입력하세요.")};
  $("approvalDialog").addEventListener("close",function(){if($("approvalDialog").returnValue==="approve"){runApproved()}else if(state.pendingIntent){addAudit("사용자","실행 취소 · "+state.pendingIntent,"차단");state.pendingIntent="";state.pendingInstall=null;state.pendingStoreAction="";state.pendingPlan=null}});
  $("approveRun").addEventListener("click",function(event){if(!$("externalTransfer").disabled&&!$("externalTransfer").checked){event.preventDefault();toast("선택 모델과 전송 데이터를 확인하고 외부 전송을 승인해 주세요.")}});
  $("applyProposal").onclick=async function(){
    var after=$("proposal").dataset.after;state.undoText=$("targetParagraph")?$("targetParagraph").textContent:null;
    try{
      if(state.nativeSession){
        if(state.nativeSelection&&state.nativeSelection.rhwpNative&&state.rhwpEditor){
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
  document.querySelectorAll("[data-welcome-prompt]").forEach(function(button){button.onclick=function(){$("welcomePrompt").value=button.dataset.welcomePrompt;$("welcomePrompt").focus()}});
  $("enterDemo").onclick=function(){enterWorkspace(true);configureEditorPlugin(null);setStatus("샘플 작업공간 · 직접 편집 가능")};
  $("closePreview").onclick=function(){$("previewPane").hidden=true};
  $("splitButton").onclick=function(){updateLivePreview();$("previewPane").hidden=false;toast("문서와 산출물 미리보기를 분할했습니다.")};
  [["formatParagraph","formatBlock","P"],["formatBold","bold"],["formatItalic","italic"],["formatAlign","justifyLeft"],["formatList","insertUnorderedList"]].forEach(function(binding){
    var button=$(binding[0]);button.addEventListener("mousedown",function(event){event.preventDefault()});button.onclick=function(){applyDocumentFormat(binding[1],binding[2])};
  });
  $("saveDocument").onclick=saveDocumentChanges;
  $("undoDirectEdit").onclick=function(){if(state.nativeSession){if(state.nativeSession.runtime==="windows-native-bridge")runNativeSessionCommand("undo",{});else toast("HWPX 대체 세션은 저장 버전 목록에서 이전 산출물을 다시 여세요.")}else undoDirectEdit()};
  $("exportButton").onclick=async function(){var saved=await saveDocumentChanges();if(!saved)return;if(state.nativeSession){try{var artifact=await api("/documents/sessions/"+state.nativeSession.id+"/artifact");downloadBase64(artifact.filename,artifact.contentBase64);toast(artifact.filename+" MCP 산출물 다운로드를 시작했습니다.");addAudit("Document MCP","원본 산출물 내보내기 · "+artifact.adapter,"완료")}catch(error){toast(error.message)}}else if(state.currentDocument){downloadBase64(state.currentDocument.filename,state.currentDocument.contentBase64);toast(state.currentDocument.filename+" 다운로드를 시작했습니다.");addAudit("사용자","HWPX 내보내기 · "+state.currentDocument.filename,"완료")}else{downloadEditableHtml();toast("직접 편집한 문서를 HTML로 내보냈습니다.");addAudit("사용자","편집 문서 HTML 내보내기","완료")}};
  $("clearChat").onclick=function(){toast("실행 이력은 유지하고 대화 컨텍스트만 초기화했습니다.")};
  document.addEventListener("keydown",function(event){var key=event.key.toLowerCase();if((event.ctrlKey||event.metaKey)&&key==="k"){event.preventDefault();$("chatInput").focus()}if((event.ctrlKey||event.metaKey)&&key==="s"){event.preventDefault();saveDocumentChanges()}if((event.ctrlKey||event.metaKey)&&key==="z"&&!event.target.closest("input,textarea,[contenteditable='true']")){event.preventDefault();undoChange()}});

  initializeDirectEditing();
  updateLivePreview();
  setView("editor");
  bootstrapServer();
})();
