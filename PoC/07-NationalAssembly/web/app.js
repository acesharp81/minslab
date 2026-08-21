const departmentScope = document.querySelector("#departmentScope");
const viewTabs = document.querySelectorAll(".view-tabs button");
const workspaceTabs = [...document.querySelectorAll("[data-workspace-tab]")];
const workspacePanels = [...document.querySelectorAll("[data-workspace-panel]")];
const liveNavTab = document.querySelector('[data-workspace-tab="live"]');
const magazineState = new Map();
const assemblyTranscriptState = {
  active: false,
  generation: 0,
  cursor: 0,
  committee: "",
  pollIntervalMs: 2000,
  pollTimer: null,
  nodes: new Map(),
  segments: new Map(),
  expanded: false,
  expandedMode: null,
  selectedBroadcastId: null,
  liveItems: [],
};
const liveInsightFilterState = {
  mode: "ALL",
  ministry: "",
};

for (const button of viewTabs) {
  button.addEventListener("click", () => {
    for (const tab of viewTabs) tab.classList.toggle("active", tab === button);
  });
}
function workspaceTabFromHash() {
  const hash = window.location.hash.replace("#", "");
  if (["cabinet", "presidential", "crossFlow"].includes(hash)) return "cabinet";
  if (["assembly", "committees", "bills"].includes(hash)) return "assembly";
  return "live";
}

function activateWorkspaceTab(name, options = {}) {
  const target = workspaceTabs.some((tab) => tab.dataset.workspaceTab === name) ? name : "live";
  for (const tab of workspaceTabs) {
    const active = tab.dataset.workspaceTab === target;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
    if (active) tab.setAttribute("aria-current", "page");
    else tab.removeAttribute("aria-current");
    tab.tabIndex = active ? 0 : -1;
  }
  for (const panel of workspacePanels) {
    panel.hidden = panel.dataset.workspacePanel !== target;
  }
  if (options.updateHash !== false) {
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${target}`);
  }
  if (options.focus === true) {
    workspaceTabs.find((tab) => tab.dataset.workspaceTab === target)?.focus();
  }
  document.dispatchEvent(new CustomEvent("workspace-tab-change", { detail: { tab: target } }));
}

for (const tab of workspaceTabs) {
  tab.addEventListener("click", (event) => {
    event.preventDefault();
    activateWorkspaceTab(tab.dataset.workspaceTab);
  });
  tab.addEventListener("keydown", (event) => {
    const current = workspaceTabs.indexOf(tab);
    let next = null;
    if (event.key === "ArrowRight") next = (current + 1) % workspaceTabs.length;
    if (event.key === "ArrowLeft") next = (current - 1 + workspaceTabs.length) % workspaceTabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = workspaceTabs.length - 1;
    if (next === null) return;
    event.preventDefault();
    activateWorkspaceTab(workspaceTabs[next].dataset.workspaceTab, { focus: true });
  });
}


window.addEventListener("hashchange", () => activateWorkspaceTab(workspaceTabFromHash(), { updateHash: false }));
activateWorkspaceTab(workspaceTabFromHash(), { updateHash: false });

departmentScope.addEventListener("change", () => {
  document.dispatchEvent(new CustomEvent("department-scope-change", {
    detail: { committee: departmentScope.value },
  }));
  if (departmentScope.value) {
    activateWorkspaceTab("assembly");
    document.querySelector("#committees").scrollIntoView({ behavior: "smooth" });
  }
  loadOfficialRotations(departmentScope.value).finally(loadLiveStatus);
});

function magazineElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text) element.textContent = text;
  return element;
}

function showMagazineCard(institution, nextIndex) {
  const state = magazineState.get(institution);
  if (!state || !state.cards.length) return;
  state.index = (nextIndex + state.cards.length) % state.cards.length;
  const card = state.cards[state.index];
  const container = state.container;
  container.className = "broadcast-stage magazine-stage";
  container.replaceChildren();

  const image = document.createElement("img");
  if (card.image_url) {
    image.src = card.image_url;
    image.alt = card.image_alt || "방송 리뷰 이미지";
  }
  const shade = magazineElement("div", "magazine-shade", "");
  const content = magazineElement("div", "magazine-content", "");
  const labels = magazineElement("div", "magazine-labels", "");
  labels.append(magazineElement(
    "span",
    card.simulation ? "simulation-label" : "review-label",
    card.simulation ? "SIMULATION" : card.authority_status === "OFFICIAL" ? "OFFICIAL" : "AUTO REVIEW",
  ));
  if (card.authority_status !== "OFFICIAL") {
    labels.append(magazineElement("span", "provisional-label", card.authority_status));
  }
  content.append(
    labels,
    magazineElement("span", "magazine-topic", card.topic),
    magazineElement("blockquote", "", card.major_quote),
    magazineElement("p", "magazine-byline", `${card.speaker_label} · ${card.meeting_date}`),
  );
  const chips = magazineElement("div", "magazine-chips", "");
  for (const label of [...card.ministries, ...card.committees]) {
    chips.append(magazineElement("span", "", label));
  }
  content.append(chips);
  if (!card.simulation && card.official_published) {
    const bodyCount = Number(card.official_utterance_count || 0);
    const stage = card.official_publication_stage === "TEMPORARY" ? "잠정본" : "정본";
    const label = card.official_link_label || (bodyCount ? `${stage} ${bodyCount}문장 · 원문 확인 ↗` : "공식 원문 확인 ↗");
    const official = magazineElement("a", "magazine-official-link", label);
    official.href = card.official_url || card.official_pdf_url;
    official.target = "_blank";
    official.rel = "noopener noreferrer";
    content.append(official);
  }

  const controls = magazineElement("div", "magazine-controls", "");
  const previous = magazineElement("button", "", "←");
  previous.type = "button";
  previous.setAttribute("aria-label", "이전 기록");
  previous.addEventListener("click", () => showMagazineCard(institution, state.index - 1));
  const count = magazineElement("span", "", `${state.index + 1} / ${state.cards.length}`);
  const pause = magazineElement("button", "", state.paused ? "재생" : "멈춤");
  pause.type = "button";
  pause.addEventListener("click", () => {
    state.paused = !state.paused;
    showMagazineCard(institution, state.index);
  });
  const next = magazineElement("button", "", "→");
  next.type = "button";
  next.setAttribute("aria-label", "다음 기록");
  next.addEventListener("click", () => showMagazineCard(institution, state.index + 1));
  controls.append(previous, count, pause, next);
  if (card.image_url) container.append(image);
  container.append(shade, content, controls);
}

function showEmptyMagazine(container, scope) {
  container.className = "broadcast-stage";
  container.replaceChildren();
  const mark = magazineElement("div", "signal-mark", "");
  mark.append(document.createElement("span"), document.createElement("span"), document.createElement("span"));
  container.append(
    mark,
    magazineElement("strong", "", `${scope} 관련 과거 방송 기록이 없습니다`),
    magazineElement("p", "", "전체 국정 흐름을 선택하면 모든 시뮬레이션 기록을 볼 수 있습니다."),
  );
}

function startMagazine(institution, container, cards, rotationMs) {
  const previousState = magazineState.get(institution);
  if (previousState?.timer) window.clearInterval(previousState.timer);
  if (!cards.length) {
    magazineState.delete(institution);
    showEmptyMagazine(container, departmentScope.selectedOptions[0].textContent);
    return;
  }
  const state = { cards: cards.slice(0, 5), container, index: 0, paused: false };
  magazineState.set(institution, state);
  showMagazineCard(institution, 0);
  state.timer = window.setInterval(() => {
    if (!state.paused && !document.hidden) showMagazineCard(institution, state.index + 1);
  }, rotationMs);
}

function stopMagazine(institution) {
  const state = magazineState.get(institution);
  if (state?.timer) window.clearInterval(state.timer);
  magazineState.delete(institution);
}

function stopAssemblyTranscript() {
  assemblyTranscriptState.active = false;
  assemblyTranscriptState.generation += 1;
  if (assemblyTranscriptState.pollTimer) window.clearTimeout(assemblyTranscriptState.pollTimer);
  assemblyTranscriptState.pollTimer = null;
  assemblyTranscriptState.nodes.clear();
  assemblyTranscriptState.segments.clear();
}

function transcriptParams(extra = {}) {
  const params = new URLSearchParams(extra);
  if (assemblyTranscriptState.committee) params.set("committee", assemblyTranscriptState.committee);
  return params;
}

function transcriptLine(item) {
  let line = assemblyTranscriptState.nodes.get(item.segment_id);
  if (!line) {
    line = magazineElement("div", "transcript-line", "");
    line.append(
      magazineElement("span", "transcript-speaker", ""),
      magazineElement("p", "transcript-text", ""),
      magazineElement("time", "transcript-time", ""),
    );
    assemblyTranscriptState.nodes.set(item.segment_id, line);
    document.querySelector("#assemblyTranscriptLines")?.append(line);
  }
  line.classList.toggle("is-final", item.is_final === true);
  const speaker = line.querySelector(".transcript-speaker");
  speaker.replaceChildren(document.createTextNode(item.speaker_label || item.committee_name || "발언자 확인 중"));
  const reconciliation = item.official_reconciliation;
  if (reconciliation?.status === "MATCHED") {
    const badge = magazineElement("span", "reconciliation-badge is-matched", "공식본 일치");
    badge.title = `${reconciliation.publication_stage || "공식본"} · ${reconciliation.match_method}`;
    speaker.append(badge);
  } else if (item.official_status === "PUBLISHED" && item.is_final === true) {
    const badge = magazineElement("span", "reconciliation-badge is-unresolved", "공식본 미확인");
    badge.title = "공식 회의록에서 유일한 exact 일치 문장을 확인하지 못했습니다.";
    speaker.append(badge);
  }
  line.querySelector(".transcript-text").textContent = item.text;
  const received = new Date(item.received_at);
  line.querySelector(".transcript-time").textContent = Number.isNaN(received.valueOf())
    ? "LIVE" : received.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return line;
}

const liveTopicRules = [
  { id: "disaster-recovery", topic: "재난 피해·복구", words: ["호우", "재난", "피해", "복구"] },
  { id: "recovery-budget", topic: "예산·재정 집행", words: ["예산", "재원", "집행", "재정"] },
  { id: "legal-support", topic: "법률 지원·권리 보호", words: ["법률", "권리", "구제", "법무"] },
  { id: "public-safety", topic: "국민 안전", words: ["안전", "소방", "경찰"] },
];

const liveMinistryRules = ["행정안전부", "기획재정부", "법무부", "국토교통부", "보건복지부", "고용노동부"];

function inferLiveHint(item) {
  if (item.insight_hint?.topic_id && item.insight_hint?.role) return item.insight_hint;
  const text = item.text || "";
  const matched = liveTopicRules.find((rule) => rule.words.some((word) => text.includes(word)));
  const question = /[?？]$|습니까|합니까|했습니까|겠습니까|는지/.test(text);
  const ministries = liveMinistryRules.filter((ministry) => text.includes(ministry));
  const resolved = /완료했(?:습니다|다)|조치했(?:습니다|다)|처리했(?:습니다|다)|해소됐(?:습니다|다)|반영했(?:습니다|다)/.test(text);
  const openCommitment = /알아보겠(?:습니다|다)|확인하겠(?:습니다|다)|검토하겠(?:습니다|다)|추진하겠(?:습니다|다)|마련하겠(?:습니다|다)|점검하겠(?:습니다|다)|보고하겠(?:습니다|다)|조치하겠(?:습니다|다)|해야 (?:합니다|한다|됩니다)|필요(?:합니다|하다)/.test(text);
  return {
    topic_id: matched?.id || "other-live-topic",
    topic: matched?.topic || "기타 현안",
    role: question ? "QUESTION" : "ANSWER",
    task: openCommitment && !resolved ? text : null,
    task_id: openCommitment ? item.segment_id : null,
    task_status: openCommitment && !resolved ? "OPEN" : null,
    resolution: resolved,
    ministries,
    derived: true,
  };
}

function buildLiveTopics(segmentItems = null) {
  const groups = new Map();
  const items = [...(segmentItems || assemblyTranscriptState.segments.values())]
    .filter((item) => item.is_final === true)
    .sort((a, b) => Number(a.cursor || 0) - Number(b.cursor || 0));
  for (const item of items) {
    const hint = inferLiveHint(item);
    let group = groups.get(hint.topic_id);
    if (!group) {
      group = { topic: hint.topic, questions: [], answers: [], tasks: new Map(), ministries: new Set(), derived: false };
      groups.set(hint.topic_id, group);
    }
    const evidence = {
      speaker: item.speaker_label || "발언자 확인 중",
      text: item.text,
      segmentId: item.segment_id,
      officialReconciliation: item.official_reconciliation || null,
      officialStatus: item.official_status || null,
    };
    if (hint.role === "QUESTION") group.questions.push(evidence);
    else group.answers.push(evidence);
    if (hint.resolution === true) group.tasks.clear();
    if (hint.task_status === "RESOLVED") {
      if (hint.task_id) group.tasks.delete(hint.task_id);
      else group.tasks.clear();
    }
    if (hint.task && hint.task_status === "OPEN") {
      const taskId = hint.task_id || `${hint.topic_id}:${hint.task}`;
      group.tasks.set(taskId, { text: hint.task, ministries: hint.ministries || [], evidence });
    }
    for (const ministry of hint.ministries || []) group.ministries.add(ministry);
    group.derived ||= hint.derived === true;
  }
  return [...groups.values()];
}

function renderInsightToolbar(container, groups, segmentItems) {
  const toolbar = magazineElement("div", "live-insight-toolbar", "");
  const taskCount = groups.reduce((sum, group) => sum + group.tasks.size, 0);
  const ministries = [...new Set(groups.flatMap((group) => [...group.ministries]))].sort();
  if (liveInsightFilterState.ministry && !ministries.includes(liveInsightFilterState.ministry)) {
    liveInsightFilterState.ministry = "";
  }
  const metrics = magazineElement("div", "live-insight-metrics", "");
  metrics.append(
    magazineElement("span", "", `주제 ${groups.length}`),
    magazineElement("span", taskCount ? "has-open-task" : "", `미해결 ${taskCount}`),
  );
  const controls = magazineElement("div", "live-insight-filters", "");
  for (const [mode, label] of [["ALL", "전체"], ["OPEN", "미해결 과제"]]) {
    const button = magazineElement("button", liveInsightFilterState.mode === mode ? "is-active" : "", label);
    button.type = "button";
    button.setAttribute("aria-pressed", String(liveInsightFilterState.mode === mode));
    button.addEventListener("click", () => {
      liveInsightFilterState.mode = mode;
      renderLiveInsights(container, segmentItems);
    });
    controls.append(button);
  }
  const select = document.createElement("select");
  select.setAttribute("aria-label", "담당 부서별 LIVE 인사이트 필터");
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "전체 부서";
  select.append(all);
  for (const ministry of ministries) {
    const option = document.createElement("option");
    option.value = ministry;
    option.textContent = ministry;
    select.append(option);
  }
  select.value = liveInsightFilterState.ministry;
  select.addEventListener("change", () => {
    liveInsightFilterState.ministry = select.value;
    renderLiveInsights(container, segmentItems);
  });
  controls.append(select);
  toolbar.append(metrics, controls);
  container.append(toolbar);
}

function renderLiveInsights(container = document.querySelector("#assemblyLiveInsights"), segmentItems = null) {
  if (!container) return;
  const allGroups = buildLiveTopics(segmentItems);
  container.replaceChildren();
  renderInsightToolbar(container, allGroups, segmentItems);
  if (!allGroups.length) {
    container.append(magazineElement("p", "live-insight-empty", "완료된 발언을 기다리며 주제 묶음을 준비하고 있습니다."));
    return;
  }
  const groups = allGroups.filter((group) => {
    if (liveInsightFilterState.mode === "OPEN" && !group.tasks.size) return false;
    return !liveInsightFilterState.ministry || group.ministries.has(liveInsightFilterState.ministry);
  });
  if (!groups.length) {
    container.append(magazineElement("p", "live-insight-empty is-filtered", "선택한 조건에 해당하는 주제나 미해결 과제가 없습니다."));
    return;
  }
  for (const group of groups) {
    const card = magazineElement("article", "live-topic-card", "");
    const head = magazineElement("header", "", "");
    head.append(
      magazineElement("strong", "", group.topic),
      magazineElement("span", group.derived ? "draft-label" : "structured-label", group.derived ? "AUTO GROUP · DRAFT" : "STRUCTURED · SIMULATION"),
    );
    const qa = magazineElement("div", "live-qa-list", "");
    for (const [label, entries, empty] of [
      ["질문", group.questions, "질문 분류 대기"],
      ["답변", group.answers, "답변 분류 대기"],
    ]) {
      const block = magazineElement("section", label === "질문" ? "live-question" : "live-answer", "");
      block.append(magazineElement("span", "live-qa-label", label));
      const utteranceList = magazineElement("div", "live-utterance-list", "");
      if (entries.length) {
        for (const entry of entries) {
          const quote = magazineElement("div", "live-utterance", "");
          const speaker = magazineElement("small", "", entry.speaker);
          if (entry.officialReconciliation?.status === "MATCHED") {
            speaker.append(magazineElement("span", "reconciliation-badge is-matched", "공식본 일치"));
          } else if (entry.officialStatus === "PUBLISHED") {
            speaker.append(magazineElement("span", "reconciliation-badge is-unresolved", "공식본 미확인"));
          }
          quote.append(speaker, magazineElement("p", "", entry.text));
          if (entry.officialReconciliation?.status === "MATCHED") {
            const official = document.createElement("details");
            official.className = "official-match-evidence";
            official.append(
              magazineElement("summary", "", "대조된 공식 발언 보기"),
              magazineElement("b", "", entry.officialReconciliation.official_speaker_name || "공식 발언자"),
              magazineElement("p", "", entry.officialReconciliation.official_text || "공식 문장 본문 확인 필요"),
            );
            quote.append(official);
          }
          utteranceList.append(quote);
        }
      } else {
        utteranceList.append(magazineElement("p", "live-unresolved", empty));
      }
      block.append(utteranceList);
      qa.append(block);
    }
    card.append(head, qa);
    if (group.tasks.size) {
      const outcome = magazineElement("div", "live-outcome", "");
      outcome.append(magazineElement("span", "live-task-heading", "미해결 후속 과제"));
      for (const task of group.tasks.values()) {
        const taskRow = magazineElement("div", "live-task-row", "");
        taskRow.append(magazineElement("strong", "", task.text));
        const ministries = magazineElement("div", "live-ministry-chips", "");
        if (task.ministries.length) {
          for (const ministry of task.ministries) ministries.append(magazineElement("b", "", ministry));
        } else {
          ministries.append(magazineElement("em", "", "담당 부서 미확정"));
        }
        taskRow.append(ministries);
        outcome.append(taskRow);
      }
      card.append(outcome);
    }
    container.append(card);
  }
}

function liveMedia(liveItem) {
  const media = magazineElement("div", "live-media", "");
  if (liveItem?.stream_url) {
    const video = document.createElement("video");
    video.controls = true;
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.src = liveItem.stream_url;
    media.append(video, magazineElement("span", "live-media-label", "OFFICIAL HLS STREAM"));
    video.addEventListener("error", () => media.classList.add("stream-error"));
  } else if (liveItem?.simulation) {
    const image = document.createElement("img");
    image.src = liveItem.thumbnail_url || "assets/magazine/sim-committee-hearing.png";
    image.alt = "실제 영상이 아닌 라이브 처리 데모 이미지";
    media.append(image, magazineElement("span", "live-media-label simulation-label", "VIDEO PLACEHOLDER · SIMULATION"));
  } else {
    media.append(magazineElement("p", "live-media-unavailable", "검증된 영상 스트림 주소를 기다리고 있습니다."));
  }
  const overlay = magazineElement("div", "live-caption-overlay", "자막 수신 대기 중");
  overlay.id = "assemblyCaptionOverlay";
  media.append(overlay);
  return media;
}

function officialStatusLabel(status) {
  return ({
    PUBLISHED: "공식본 연결",
    NOT_PUBLISHED: "공식본 미게시",
    AMBIGUOUS: "공식 회의 검토 필요",
    FAILED: "공식본 확인 실패",
  })[status] || "공식본 확인 중";
}

function renderOfficialContext(context = {}) {
  const container = document.querySelector("#assemblyOfficialContext");
  if (!container) return;
  container.replaceChildren();
  const live = magazineElement("div", "official-context-side is-live-record", "");
  live.append(
    magazineElement("span", "", "방송 기록"),
    magazineElement("strong", "", "LIVE 저장본 · PROVISIONAL"),
    magazineElement("small", "", context.review_status === "COMPLETED" ? "자동 리뷰 생성 완료" : "자동 리뷰 처리 상태 확인 중"),
  );
  const official = magazineElement("div", "official-context-side is-official-record", "");
  const published = context.official_status === "PUBLISHED";
  const stage = context.publication_stage === "FINAL" ? "정본" : context.publication_stage === "TEMPORARY" ? "잠정본" : "공식본";
  const authority = context.official_authority_status || (context.publication_stage === "FINAL" ? "OFFICIAL" : "PROVISIONAL");
  official.append(
    magazineElement("span", "", "공식 회의록"),
    magazineElement("strong", "", published ? `${stage} · ${authority}` : officialStatusLabel(context.official_status)),
  );
  if (published) {
    const matched = Number(context.matched_segment_count || 0);
    const total = Number(context.final_segment_count || 0);
    official.append(magazineElement("small", "", `LIVE final 문장 exact 일치 ${matched}/${total} · 공식 발언 ${context.official_utterance_count || 0}문장`));
    const url = context.official_url || context.official_pdf_url;
    if (typeof url === "string" && url.startsWith("https://")) {
      const link = magazineElement("a", "", "공식 회의록 원문 ↗");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      official.append(link);
    }
  } else {
    official.append(magazineElement("small", "", "공식본 게시 후 기존 LIVE 기록을 유지한 채 대조 상태가 추가됩니다."));
  }
  container.append(live, magazineElement("i", "official-context-arrow", "→"), official);
}

function renderTranscriptShell(liveItems, mode = "LIVE") {
  const stage = document.querySelector("#liveExpandedStage");
  stage.className = "broadcast-stage transcript-stage";
  stage.replaceChildren();
  const head = magazineElement("div", "transcript-head", "");
  const title = magazineElement("div", "", "");
  const simulation = liveItems.every((item) => item.simulation === true);
  const reviewMode = mode === "REVIEW";
  title.append(
    magazineElement("span", "detected-live-label", reviewMode
      ? simulation ? "LAST LIVE REVIEW · SIMULATION" : "LAST LIVE REVIEW · PROVISIONAL"
      : simulation ? "DEMO LIVE · SIMULATION" : "OFFICIAL LIVE CAPTION"),
    magazineElement("strong", "", liveItems.map((item) => item.title || item.committee_name).join(" · ")),
  );
  head.append(title, magazineElement("span", "transcript-continuity", reviewMode ? "처음부터 끝까지 · 공식본 대조" : "처음부터 현재까지 · 자동 갱신"));
  const workspace = magazineElement("div", "live-workspace", "");
  const insights = magazineElement("div", "live-insights", "");
  insights.id = "assemblyLiveInsights";
  insights.append(magazineElement("p", "live-insight-empty", "저장된 발언을 주제별로 묶는 중입니다."));
  workspace.append(liveMedia(liveItems[0]), insights);
  const raw = document.createElement("details");
  raw.className = "raw-transcript";
  const summary = magazineElement("summary", "", "전체 자막을 시간순으로 보기");
  const lines = magazineElement("div", "transcript-lines", "");
  lines.id = "assemblyTranscriptLines";
  lines.append(magazineElement("p", "transcript-waiting", "저장된 자막을 불러오는 중입니다."));
  raw.append(summary, lines);
  if (reviewMode) {
    const officialContext = magazineElement("div", "official-context", "");
    officialContext.id = "assemblyOfficialContext";
    stage.append(head, officialContext, workspace, raw);
    renderOfficialContext(liveItems[0]);
  } else {
    stage.append(head, workspace, raw);
  }
}

function collapseLiveExpansion() {
  assemblyTranscriptState.expanded = false;
  assemblyTranscriptState.expandedMode = null;
  assemblyTranscriptState.selectedBroadcastId = null;
  stopAssemblyTranscript();
  document.querySelector("#liveExpanded").hidden = true;
  document.querySelectorAll(".broadcast-row").forEach((row) => row.removeAttribute("aria-current"));
}

function expandLiveBroadcast(item, row) {
  assemblyTranscriptState.expanded = true;
  assemblyTranscriptState.expandedMode = "LIVE";
  assemblyTranscriptState.selectedBroadcastId = item.broadcast_id || item.meeting_external_id;
  document.querySelector("#liveExpanded").hidden = false;
  document.querySelector("#liveExpandedTitle").textContent = item.title || item.committee_name || "LIVE 방송 분석";
  document.querySelectorAll(".broadcast-row").forEach((candidate) => candidate.removeAttribute("aria-current"));
  row.setAttribute("aria-current", "true");
  startAssemblyTranscript([item]);
  document.querySelector("#liveExpanded").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function expandEndedBroadcast(item, row) {
  stopAssemblyTranscript();
  assemblyTranscriptState.expanded = true;
  assemblyTranscriptState.expandedMode = "REVIEW";
  assemblyTranscriptState.selectedBroadcastId = item.broadcast_id;
  document.querySelector("#liveExpanded").hidden = false;
  document.querySelector("#liveExpandedTitle").textContent = item.title || item.committee_name || "종료 방송 리뷰";
  document.querySelectorAll(".broadcast-row").forEach((candidate) => candidate.removeAttribute("aria-current"));
  row.setAttribute("aria-current", "true");
  renderTranscriptShell([item], "REVIEW");
  fetch(`api/live/broadcasts/${encodeURIComponent(item.broadcast_id)}/transcript`, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      if (assemblyTranscriptState.selectedBroadcastId !== item.broadcast_id) return;
      const broadcast = payload.broadcasts?.[0] || item;
      renderOfficialContext(payload.official_context || broadcast);
      const segments = (payload.segments || []).map((segment) => ({
        ...broadcast,
        ...segment,
        official_status: payload.official_context?.official_status,
      }));
      applyTranscriptItems(segments);
      if (!segments.length) {
        const waiting = document.querySelector(".transcript-waiting");
        if (waiting) waiting.textContent = "저장된 자막이 없는 종료 방송입니다.";
      }
    })
    .catch(() => {
      const waiting = document.querySelector(".transcript-waiting");
      if (waiting) waiting.textContent = "종료 방송 기록을 불러오지 못했습니다.";
    });
  document.querySelector("#liveExpanded").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function applyTranscriptItems(items) {
  const waiting = document.querySelector(".transcript-waiting");
  if (items.length && waiting) waiting.remove();
  for (const item of items) {
    transcriptLine(item);
    assemblyTranscriptState.segments.set(item.segment_id, item);
    const overlay = document.querySelector("#assemblyCaptionOverlay");
    if (overlay) overlay.textContent = `${item.speaker_label || "발언자 확인 중"} · ${item.text}`;
  }
  renderLiveInsights();
  const lines = document.querySelector("#assemblyTranscriptLines");
  while (lines && lines.children.length > 80) {
    const oldest = lines.firstElementChild;
    if (!oldest) break;
    for (const [key, value] of assemblyTranscriptState.nodes) {
      if (value === oldest) assemblyTranscriptState.nodes.delete(key);
    }
    oldest.remove();
  }
  if (lines && items.length) lines.scrollTop = lines.scrollHeight;
}

function scheduleTranscriptDelta(generation, delay) {
  if (!assemblyTranscriptState.active || generation !== assemblyTranscriptState.generation) return;
  assemblyTranscriptState.pollTimer = window.setTimeout(() => pollTranscriptDelta(generation), delay);
}

function pollTranscriptDelta(generation) {
  if (!assemblyTranscriptState.active || generation !== assemblyTranscriptState.generation) return;
  const params = transcriptParams({ after: String(assemblyTranscriptState.cursor), limit: "200" });
  fetch(`api/live/transcript/delta?${params}`, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      if (generation !== assemblyTranscriptState.generation) return;
      applyTranscriptItems(payload.items || []);
      assemblyTranscriptState.cursor = Number(payload.next_cursor || assemblyTranscriptState.cursor);
      scheduleTranscriptDelta(generation, payload.has_more ? 0 : assemblyTranscriptState.pollIntervalMs);
    })
    .catch(() => scheduleTranscriptDelta(generation, 5000));
}

function startAssemblyTranscript(liveItems) {
  const committee = liveItems.length === 1 ? liveItems[0].committee_name : departmentScope.value;
  if (assemblyTranscriptState.active && assemblyTranscriptState.committee === committee) return;
  stopAssemblyTranscript();
  assemblyTranscriptState.active = true;
  assemblyTranscriptState.committee = committee;
  const generation = assemblyTranscriptState.generation;
  renderTranscriptShell(liveItems);
  fetch(`api/live/transcript/snapshot?${transcriptParams()}`, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      if (!assemblyTranscriptState.active || generation !== assemblyTranscriptState.generation) return;
      assemblyTranscriptState.cursor = Number(payload.cursor || 0);
      assemblyTranscriptState.pollIntervalMs = Number(payload.poll_interval_ms || 2000);
      const broadcastById = new Map((payload.broadcasts || []).map((item) => [item.broadcast_id, item]));
      const items = (payload.segments || []).map((item) => ({ ...broadcastById.get(item.broadcast_id), ...item }));
      applyTranscriptItems(items);
      if (!items.length) {
        const waiting = document.querySelector(".transcript-waiting");
        if (waiting) waiting.textContent = "방송을 감지했습니다. 첫 공식 자막을 기다리고 있습니다.";
      }
      scheduleTranscriptDelta(generation, 0);
    })
    .catch(() => {
      const waiting = document.querySelector(".transcript-waiting");
      if (waiting) waiting.textContent = "저장된 자막을 불러오지 못했습니다. 자동으로 다시 확인합니다.";
      scheduleTranscriptDelta(generation, 5000);
    });
}

function renderDetectedAssemblyLive(items) {
  const liveItems = items.filter((item) => item.is_live);
  assemblyTranscriptState.liveItems = liveItems;
  if (!liveItems.length) {
    if (assemblyTranscriptState.expandedMode === "LIVE") collapseLiveExpansion();
    return false;
  }
  return true;
}

function addBroadcastRow(container, status, title, meta, onClick = null, broadcastId = null) {
  const row = document.createElement(onClick ? "button" : "div");
  row.className = `broadcast-row is-${status.toLowerCase()}`;
  if (broadcastId) row.dataset.broadcastId = broadcastId;
  if (broadcastId && broadcastId === assemblyTranscriptState.selectedBroadcastId) {
    row.setAttribute("aria-current", "true");
  }
  if (onClick) {
    row.type = "button";
    row.addEventListener("click", () => onClick(row));
  }
  row.append(
    magazineElement("span", "broadcast-status", status),
    magazineElement("strong", "", title),
    magazineElement("small", "", meta),
    magazineElement("i", "", onClick ? "열기" : ""),
  );
  container.append(row);
}

function renderBroadcastRows(statusPayload, schedulePayload, historyPayload) {
  const container = document.querySelector("#liveBroadcastRows");
  container.replaceChildren();
  const liveItems = (statusPayload.assembly?.items || []).filter((item) => item.is_live);
  for (const item of liveItems) {
    addBroadcastRow(
      container,
      "LIVE",
      item.title || item.committee_name,
      `${item.committee_name} · ${item.simulation ? "SIMULATION" : "공식 생중계"}`,
      (row) => expandLiveBroadcast(item, row),
      item.broadcast_id || item.meeting_external_id,
    );
  }
  if (statusPayload.executive?.is_live === true) {
    addBroadcastRow(container, "LIVE", statusPayload.executive.title || "국무회의 생중계", "KTV 공식 플레이어 · 스트림 계약 확인 중");
  }
  const now = new Date();
  const scheduled = (schedulePayload.items || []).filter((item) => {
    if (!item.is_target_committee || !item.start_time) return false;
    const start = new Date(`${schedulePayload.date}T${item.start_time}`);
    return !Number.isNaN(start.valueOf()) && start > now;
  });
  for (const item of scheduled.slice(0, 5)) {
    addBroadcastRow(container, "예정", item.title, `${item.time_text || item.start_time} · ${item.committee_name} · ${item.place || "장소 미표기"}`);
  }
  for (const ended of (historyPayload.items || []).slice(0, 5)) {
    const endedAt = new Date(ended.ended_at);
    const endedLabel = Number.isNaN(endedAt.valueOf())
      ? "종료 시각 미상"
      : endedAt.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
    addBroadcastRow(
      container,
      "종료",
      ended.title || ended.committee_name,
      `${ended.committee_name || "국회"} · ${endedLabel} · 자막 ${ended.segment_count || 0}건 · ${officialStatusLabel(ended.official_status)}`,
      (row) => expandEndedBroadcast(ended, row),
      ended.broadcast_id,
    );
  }
  if (!container.children.length) {
    container.append(magazineElement("p", "broadcast-empty", "현재 확인된 LIVE·예정·종료 방송 기록이 없습니다."));
  }
}

let followUpPayload = { items: [] };

function openTaskBroadcast(item, row) {
  liveInsightFilterState.mode = "OPEN";
  liveInsightFilterState.ministry = item.ministries?.length === 1 ? item.ministries[0] : "";
  const broadcastRow = document.querySelector(`.broadcast-row[data-broadcast-id="${item.broadcast_id}"]`);
  if (broadcastRow) {
    broadcastRow.click();
    return;
  }
  const broadcast = {
    ...item,
    title: item.broadcast_title,
    simulation: item.simulation,
    thumbnail_url: item.simulation ? "assets/magazine/sim-committee-hearing.png" : null,
  };
  if (item.lifecycle_status === "LIVE") expandLiveBroadcast(broadcast, row);
  else expandEndedBroadcast(broadcast, row);
}

function followUpTaskRow(item) {
  const row = magazineElement("button", "follow-up-row", "");
  row.type = "button";
  const content = magazineElement("div", "", "");
  content.append(magazineElement("strong", "", item.task), magazineElement("small", "", `${item.topic} · ${item.committee_name || "위원회 미확정"}`));
  const ministries = magazineElement("div", "follow-up-ministries", "");
  for (const ministry of item.ministries || []) ministries.append(magazineElement("b", "", ministry));
  if (!ministries.children.length) ministries.append(magazineElement("em", "", "담당 부서 미확정"));
  row.append(magazineElement("span", item.lifecycle_status === "LIVE" ? "is-live" : "", item.lifecycle_status === "LIVE" ? "LIVE" : "종료"), content, ministries, magazineElement("i", "", "방송 보기"));
  row.addEventListener("click", () => openTaskBroadcast(item, row));
  return row;
}
function renderFollowUpTasks(payload = followUpPayload) {
  followUpPayload = payload;
  const container = document.querySelector("#followUpTasks");
  const select = document.querySelector("#followUpMinistry");
  const current = select.value;
  const items = payload.items || [];
  const ministries = [...new Set(items.flatMap((item) => item.ministries || []))].sort();
  select.replaceChildren(new Option("전체 부서", ""));
  for (const ministry of ministries) select.append(new Option(ministry, ministry));
  select.value = ministries.includes(current) ? current : "";
  const visible = items.filter((item) => !select.value || item.ministries.includes(select.value));
  document.querySelector("#followUpCount").textContent = `${visible.length}건`;
  container.replaceChildren();
  if (!visible.length) {
    container.append(magazineElement("p", "follow-up-empty", select.value
      ? "선택한 부서에 배정된 미해결 과제가 없습니다."
      : "현재 근거 자막에서 확인된 미해결 후속 과제가 없습니다."));
    return;
  }
  for (const item of visible.slice(0, 8)) container.append(followUpTaskRow(item));
}

function loadLiveStatus() {
  const getJson = (url, fallback) => fetch(url, { cache: "no-store" })
    .then((response) => response.ok ? response.json() : fallback)
    .catch(() => fallback);
  const historyParams = new URLSearchParams({ limit: "5" });
  if (departmentScope.value) historyParams.set("committee", departmentScope.value);
  return Promise.all([
    getJson("api/live/status", null),
    getJson("api/schedule/today", { items: [] }),
    getJson(`api/live/broadcasts?${historyParams}`, { items: [] }),
    getJson(`api/live/tasks?${historyParams}`, { items: [] }),
  ]).then(([payload, schedule, history, tasks]) => {
      if (!payload) throw new Error("live status unavailable");
      const assemblyLive = renderDetectedAssemblyLive(payload.assembly.items || []);
      renderBroadcastRows(payload, schedule, history);
      renderFollowUpTasks(tasks);
      const demoLiveCount = Number(payload.assembly.demo_live_count || 0);
      const anyLive = assemblyLive || payload.executive.is_live === true;
      const liveLabel = assemblyLive
        ? demoLiveCount > 0
          ? ` 자동 기록 중 · E2E 데모 LIVE ${demoLiveCount}건 · ${payload.assembly.source_time}`
          : ` 자동 기록 중 · 국회 LIVE ${payload.assembly.live_count}건 · ${payload.assembly.source_time}`
        : payload.executive.is_live === true
          ? ` 자동 기록 중 · 국무회의 LIVE · ${payload.assembly.source_time}`
          : ` 현재 대상 생방송 없음 · ${payload.assembly.source_time}`;
      liveNavTab?.classList.toggle("has-live", anyLive);
      if (liveNavTab) {
        liveNavTab.title = liveLabel.trim();
        liveNavTab.setAttribute("aria-label", anyLive ? `LIVE 방송 중. ${liveLabel}` : `LIVE. ${liveLabel}`);
      }
    })
    .catch(() => {
      liveNavTab?.classList.remove("has-live");
      liveNavTab?.setAttribute("aria-label", "LIVE 방송 상태 확인 필요");
    });
}

function loadOfficialRotations(scope = "") {
  return Promise.all([
    fetch("api/executive/briefings?limit=5", { cache: "no-store" }).then((response) => response.json()),
    fetch("api/committees/meetings?limit=5", { cache: "no-store" }).then((response) => response.json()),
  ]).then(([executive, legislature]) => {
    const executiveCards = (executive.items || []).flatMap((meeting) => (meeting.agendas || []).slice(0, 2).map((agenda) => ({
      institution: "EXECUTIVE", authority_status: "OFFICIAL", topic: agenda.topic,
      major_quote: agenda.summary, speaker_label: meeting.title, meeting_date: meeting.published_date,
      ministries: agenda.ministries || [], committees: [], official_published: true,
      official_url: meeting.source_url, official_utterance_count: 0,
      official_link_label: "국무회의 공식 원문 ↗",
    }))).slice(0, 5);
    const legislatureCards = (legislature.items || [])
      .filter((meeting) => !scope || meeting.committee_name === scope)
      .map((meeting) => ({
        institution: "LEGISLATURE", authority_status: "OFFICIAL",
        topic: `${meeting.committee_name} · ${meeting.session_text || "회기 미상"} ${meeting.meeting_order_text || ""}`.trim(),
        major_quote: `${meeting.title} · 공식 회의록 ${meeting.official_utterance_count || 0}문장 · 의안 ${meeting.agenda_items || 0}건`,
        speaker_label: "국회 공식 회의자료", meeting_date: meeting.conference_date,
        ministries: [], committees: [meeting.committee_name], official_published: false,
      }));
    startMagazine(
      "EXECUTIVE",
      document.querySelector("#executiveMagazine"),
      executiveCards,
      5000,
    );
    startMagazine(
      "LEGISLATURE",
      document.querySelector("#assemblyMagazine"),
      legislatureCards,
      5000,
    );
  })
  .catch(() => {
    // 초기 OFF AIR 안내를 유지한다. 실패한 합성 자료를 공식 자료로 대체하지 않는다.
  });
}

document.querySelector("#liveExpandedClose").addEventListener("click", collapseLiveExpansion);
loadOfficialRotations().finally(loadLiveStatus);
window.setInterval(loadLiveStatus, 30_000);
document.querySelector("#followUpMinistry").addEventListener("change", () => renderFollowUpTasks());
