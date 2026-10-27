const viewTabs = document.querySelectorAll(".view-tabs button");
const workspaceTabs = [...document.querySelectorAll("[data-workspace-tab]")];
const workspacePanels = [...document.querySelectorAll("[data-workspace-panel]")];
const liveNavTab = document.querySelector('[data-workspace-tab="live"]');
const magazineState = new Map();
let watchTestLiveState = null;
const assemblyTranscriptState = {
  active: false,
  generation: 0,
  cursor: 0,
  committee: "",
  broadcastId: "",
  briefPollTimer: null,
  pollIntervalMs: 2000,
  pollTimer: null,
  summaryRefreshTimer: null,
  summaryRefreshAttempts: 0,
  layoutObserver: null,
  lastActiveUtteranceId: null,
  nodes: new Map(),
  segments: new Map(),
  cachedSummaries: new Map(),
  meetingSessions: [],
  expanded: false,
  expandedMode: null,
  selectedBroadcastId: null,
  liveItems: [],
  followLatest: true,
  autoScrolling: false,
};
const liveInsightFilterState = {
  mode: "ALL",
  ministry: "",
};
const liveReportFilterState = {
  query: "",
};
const todayScheduleState = {
  items: [],
  index: 0,
  signature: null,
  timer: null,
  resetTimer: null,
};
const TODAY_SCHEDULE_HOLD_MS = 5000;
const TODAY_SCHEDULE_TRANSITION_MS = 2000;
const MEETING_HISTORY_INITIAL_LIMIT = 5;
const MEETING_HISTORY_PAGE_SIZE = 5;
const MEETING_OVERVIEW_VISIBLE_ROWS = 5;
const meetingBriefRequests = new Map();
const meetingBriefCache = new Map();
const MEETING_BRIEF_CACHE_LIMIT = 12;
let liveStatusLoadPromise = null;
const meetingRailHistoryState = {
  items: [],
  nextOffset: 0,
  hasMore: true,
  endReached: false,
  loading: false,
  initialized: false,
  statusPayload: null,
  executivePayload: { items: [] },
};
const MEETING_REPORT_SELECTION_KEY = "poc07.selectedMeetingReport.v1";
const MEETING_REPORT_QUERY_KEY = "report";

function restoredMeetingReportId() {
  try {
    const explicitId = new URL(window.location.href).searchParams.get(
      MEETING_REPORT_QUERY_KEY,
    );
    if (explicitId) return explicitId;
    const navigation = window.performance?.getEntriesByType?.("navigation")?.[0];
    if (navigation?.type !== "reload") return null;
    return window.sessionStorage.getItem(MEETING_REPORT_SELECTION_KEY) || null;
  } catch (_error) {
    return null;
  }
}

function rememberMeetingReportSelection(id) {
  const value = String(id || "");
  latestMeetingReportState.preferredId = value || null;
  try {
    if (value) window.sessionStorage.setItem(MEETING_REPORT_SELECTION_KEY, value);
    else window.sessionStorage.removeItem(MEETING_REPORT_SELECTION_KEY);
  } catch (_error) {
    // 브라우저 저장소가 차단돼도 현재 탭의 메모리 선택은 유지한다.
  }
  try {
    const url = new URL(window.location.href);
    if (value) url.searchParams.set(MEETING_REPORT_QUERY_KEY, value);
    else url.searchParams.delete(MEETING_REPORT_QUERY_KEY);
    window.history.replaceState(
      window.history.state, "", `${url.pathname}${url.search}${url.hash}`,
    );
  } catch (_error) {
    // URL 갱신이 제한된 환경에서는 sessionStorage 복원을 사용한다.
  }
}

const latestMeetingReportState = {
  pending: false,
  opening: false,
  preferredId: restoredMeetingReportId(),
};
const initialWorkspaceHash = window.location.hash.replace("#", "");
const explicitWorkspaceHashes = new Set([
  "live", "reports", "topic-reports", "extras",
  "cabinet", "presidential", "crossFlow", "assembly", "committees", "bills",
]);
let initialWorkspaceAutoSelectionPending = !explicitWorkspaceHashes.has(initialWorkspaceHash);

for (const button of viewTabs) {
  button.addEventListener("click", () => {
    for (const tab of viewTabs) tab.classList.toggle("active", tab === button);
  });
}
function workspaceTabFromHash() {
  const hash = window.location.hash.replace("#", "");
  if (hash === "reports") return "reports";
  if (hash === "topic-reports") return "topic-reports";
  if (hash === "extras") return "extras";
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
  if (target === "reports" && options.openLatest === true) {
    const selectedId = String(assemblyTranscriptState.selectedBroadcastId || "");
    if (selectedId) meetingBriefCache.delete(selectedId);
    requestLatestMeetingReport();
  }
}

function selectInitialWorkspaceForLiveStatus(anyLive) {
  if (!initialWorkspaceAutoSelectionPending) return;
  initialWorkspaceAutoSelectionPending = false;
  const target = anyLive ? "live" : "reports";
  activateWorkspaceTab(target, {
    updateHash: false,
    openLatest: target === "reports",
  });
}

for (const tab of workspaceTabs) {
  tab.addEventListener("click", (event) => {
    event.preventDefault();
    initialWorkspaceAutoSelectionPending = false;
    activateWorkspaceTab(tab.dataset.workspaceTab, {
      openLatest: tab.dataset.workspaceTab === "reports",
    });
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
    initialWorkspaceAutoSelectionPending = false;
    const target = workspaceTabs[next].dataset.workspaceTab;
    activateWorkspaceTab(target, { focus: true, openLatest: target === "reports" });
  });
}


window.addEventListener("hashchange", () => {
  initialWorkspaceAutoSelectionPending = false;
  const target = workspaceTabFromHash();
  activateWorkspaceTab(target, { updateHash: false, openLatest: target === "reports" });
});
const initialWorkspaceTab = workspaceTabFromHash();
activateWorkspaceTab(initialWorkspaceTab, {
  updateHash: false, openLatest: initialWorkspaceTab === "reports",
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
    "review-label",
    card.authority_status === "OFFICIAL" ? "OFFICIAL" : "AUTO REVIEW",
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
  if (card.official_published) {
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
    magazineElement("p", "", "수집·정리가 완료된 실제 회의 기록만 표시합니다."),
  );
}

function startMagazine(institution, container, cards, rotationMs) {
  const previousState = magazineState.get(institution);
  if (previousState?.timer) window.clearInterval(previousState.timer);
  if (!cards.length) {
    magazineState.delete(institution);
    showEmptyMagazine(container, "전체 국정");
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
  if (assemblyTranscriptState.summaryRefreshTimer) window.clearTimeout(assemblyTranscriptState.summaryRefreshTimer);
  if (assemblyTranscriptState.briefPollTimer) window.clearTimeout(assemblyTranscriptState.briefPollTimer);
  if (assemblyTranscriptState.layoutObserver) assemblyTranscriptState.layoutObserver.disconnect();
  assemblyTranscriptState.pollTimer = null;
  assemblyTranscriptState.summaryRefreshTimer = null;
  assemblyTranscriptState.briefPollTimer = null;
  assemblyTranscriptState.summaryRefreshAttempts = 0;
  assemblyTranscriptState.layoutObserver = null;
  assemblyTranscriptState.lastActiveUtteranceId = null;
  assemblyTranscriptState.nodes.clear();
  assemblyTranscriptState.segments.clear();
  assemblyTranscriptState.cachedSummaries.clear();
  assemblyTranscriptState.meetingSessions = [];
  assemblyTranscriptState.broadcastId = "";
}

function transcriptParams(extra = {}) {
  const params = new URLSearchParams(extra);
  if (assemblyTranscriptState.broadcastId) {
    params.set("broadcast_id", assemblyTranscriptState.broadcastId);
  } else if (assemblyTranscriptState.committee) {
    params.set("committee", assemblyTranscriptState.committee);
  }
  return params;
}

function summarizeUtterance(text, maxChars = 180) {
  const normalized = String(text || "").replace(/\s+/g, " ").trim();
  if (normalized.length <= maxChars) return normalized;
  const clipped = normalized.slice(0, maxChars + 1);
  const boundary = clipped.lastIndexOf(" ");
  const summary = boundary >= Math.floor(maxChars / 2)
    ? clipped.slice(0, boundary) : clipped.slice(0, maxChars);
  return `${summary.trimEnd()}…`;
}

function groupTranscriptSegments(items = [...assemblyTranscriptState.segments.values()]) {
  const ordered = [...items]
    .filter((item) => String(item.text || "").trim())
    .sort((a, b) => new Date(a.received_at) - new Date(b.received_at) || Number(a.cursor || 0) - Number(b.cursor || 0));
  const groups = [];
  for (const item of ordered) {
    const sourceLabel = String(item.source_speaker_label ?? item.speaker_label ?? "");
    const previous = groups.at(-1);
    const transientUnknown = ["", "-1"].includes(sourceLabel)
      && item.is_final !== true
      && previous
      && previous.broadcast_id === item.broadcast_id;
    const effectiveSourceLabel = transientUnknown ? previous.source_speaker_label : sourceLabel;
    const merge = previous
      && previous.broadcast_id === item.broadcast_id
      && previous.source_speaker_label === effectiveSourceLabel;
    if (!merge) {
      groups.push({
        ...item,
        utterance_id: item.segment_id,
        source_speaker_label: effectiveSourceLabel,
        speaker_label: transientUnknown ? previous.speaker_label : item.speaker_label,
        segment_ids: [item.segment_id],
        segment_count: 1,
        summary: summarizeUtterance(item.text),
        summary_kind: "EXTRACTIVE_FALLBACK",
        start_at: item.received_at,
      });
      continue;
    }
    previous.text = `${previous.text} ${String(item.text).trim()}`.trim();
    previous.summary = summarizeUtterance(previous.text);
    previous.received_at = item.received_at;
    previous.cursor = item.cursor;
    previous.segment_ids.push(item.segment_id);
    previous.segment_count += 1;
    previous.is_final = previous.is_final === true && item.is_final === true;
    if (item.official_reconciliation?.status === "MATCHED") {
      previous.official_reconciliation = item.official_reconciliation;
    }
  }
  return groups;
}

function normalizePreparedTranscriptGroups(preparedGroups = []) {
  return preparedGroups
    .filter((group) => String(group.text || "").trim())
    .map((group) => {
      const firstSegment = assemblyTranscriptState.segments.get(group.segment_ids?.[0]);
      const reconciliations = group.official_reconciliations || [];
      return {
        ...firstSegment,
        ...group,
        received_at: group.end_at || group.start_at || firstSegment?.received_at,
        cursor: group.last_cursor ?? group.first_cursor ?? firstSegment?.cursor,
        official_reconciliation: group.official_reconciliation
          || reconciliations.find((item) => item?.status === "MATCHED")
          || firstSegment?.official_reconciliation,
      };
    })
    .sort((left, right) => (
      Number(left.first_cursor ?? left.cursor ?? 0)
      - Number(right.first_cursor ?? right.cursor ?? 0)
    ));
}

function renderTranscriptGroups(groups = groupTranscriptSegments()) {
  const lines = document.querySelector("#assemblyTranscriptLines");
  if (!lines) return;
  const previousScrollTop = lines.scrollTop;
  const expandedOriginalIds = new Set(
    [...assemblyTranscriptState.nodes.entries()]
      .filter(([, line]) => line.querySelector(".transcript-original")?.open)
      .map(([lineId]) => lineId),
  );
  lines.replaceChildren();
  assemblyTranscriptState.nodes.clear();
  const visible = groups.slice(-160);
  const rawSummary = lines.closest(".raw-transcript")
    ?.querySelector(":scope > .raw-transcript-heading, :scope > summary");
  if (rawSummary) {
    rawSummary.textContent = `발언 묶음별 요약 + 원문 · ${groups.length.toLocaleString("ko-KR")}개`;
  }
  const latest = visible.at(-1);
  for (const group of visible) {
    const line = transcriptLine({
      ...group,
      original_open: expandedOriginalIds.has(group.utterance_id || group.segment_id),
      is_active_turn: group === latest
        && ["LIVE", "EXECUTIVE_LIVE"].includes(assemblyTranscriptState.expandedMode),
    });
    if (group === latest) {
      line.classList.add("is-latest");
      line.setAttribute("aria-current", "true");
    }
  }
  if (groups.length > visible.length) {
    const notice = magazineElement("p", "transcript-history-note", `이전 ${groups.length - visible.length}개 발언 묶음은 요약에서 확인할 수 있습니다.`);
    lines.prepend(notice);
  }
  if (!groups.length) lines.append(magazineElement("p", "transcript-waiting", "저장된 자막을 기다리고 있습니다."));
  if (visible.length) {
    if (assemblyTranscriptState.followLatest) {
      scrollTranscriptToLatest(lines);
    } else {
      window.requestAnimationFrame(() => {
        lines.scrollTop = Math.max(
          0, Math.min(previousScrollTop, lines.scrollHeight - lines.clientHeight),
        );
      });
    }
  }
}

function updateTranscriptFollowButton(lines) {
  const button = lines?.closest(".raw-transcript")?.querySelector(".transcript-follow-latest");
  if (!button) return;
  button.classList.toggle("is-paused", !assemblyTranscriptState.followLatest);
  button.textContent = assemblyTranscriptState.followLatest ? "최신 고정 중" : "최신으로";
  button.setAttribute("aria-pressed", String(assemblyTranscriptState.followLatest));
}

function updateTranscriptScrollRange(lines) {
  const range = lines?.closest(".raw-transcript")?.querySelector(".transcript-scroll-range");
  if (!range) return;
  const maximum = Math.max(0, lines.scrollHeight - lines.clientHeight);
  const percent = maximum > 0
    ? Math.max(0, Math.min(100, Math.round((lines.scrollTop / maximum) * 100)))
    : 100;
  range.value = String(percent);
  range.disabled = maximum <= 1;
  range.setAttribute("aria-valuetext", percent >= 99 ? "최신 발언" : "전체 발언의 " + percent + "% 위치");
}

function scrollTranscriptToLatest(lines, behavior = "auto") {
  if (!lines) return;
  assemblyTranscriptState.followLatest = true;
  assemblyTranscriptState.autoScrolling = true;
  const move = () => {
    const target = Math.max(0, lines.scrollHeight - lines.clientHeight);
    if (behavior === "auto") lines.scrollTop = target;
    else lines.scrollTo({ top: target, behavior });
    updateTranscriptFollowButton(lines);
    updateTranscriptScrollRange(lines);
  };
  window.requestAnimationFrame(() => {
    move();
    window.requestAnimationFrame(move);
  });
  window.setTimeout(move, 140);
  window.setTimeout(() => {
    if (assemblyTranscriptState.followLatest) move();
  }, 520);
  window.setTimeout(() => {
    assemblyTranscriptState.autoScrolling = false;
  }, behavior === "smooth" ? 500 : 80);
}

function bindTranscriptScrollControls(raw, lines) {
  const controls = magazineElement("div", "transcript-scroll-controls", "");
  const previous = magazineElement("button", "transcript-scroll-previous", "이전");
  previous.type = "button";
  previous.addEventListener("click", () => {
    assemblyTranscriptState.followLatest = false;
    assemblyTranscriptState.autoScrolling = true;
    lines.scrollBy({ top: -Math.max(160, lines.clientHeight * 0.72), behavior: "smooth" });
    updateTranscriptFollowButton(lines);
    window.setTimeout(() => { assemblyTranscriptState.autoScrolling = false; }, 500);
  });
  const range = document.createElement("input");
  range.type = "range";
  range.className = "transcript-scroll-range";
  range.min = "0";
  range.max = "100";
  range.value = "100";
  range.setAttribute("aria-label", "실시간 발언 스크롤 위치");
  range.setAttribute("aria-valuetext", "최신 발언");
  range.addEventListener("input", () => {
    const maximum = Math.max(0, lines.scrollHeight - lines.clientHeight);
    assemblyTranscriptState.autoScrolling = true;
    lines.scrollTop = maximum * (Number(range.value) / 100);
    assemblyTranscriptState.followLatest = Number(range.value) >= 99;
    updateTranscriptFollowButton(lines);
    window.requestAnimationFrame(() => {
      assemblyTranscriptState.autoScrolling = false;
    });
  });
  const rangeLabel = magazineElement("span", "transcript-scroll-label", "발언 위치");
  const latest = magazineElement("button", "transcript-follow-latest", "최신 고정 중");
  latest.type = "button";
  latest.setAttribute("aria-pressed", "true");
  latest.addEventListener("click", () => scrollTranscriptToLatest(lines, "smooth"));
  controls.append(previous, rangeLabel, range, latest);
  lines.addEventListener("scroll", () => {
    updateTranscriptScrollRange(lines);
    if (assemblyTranscriptState.autoScrolling) return;
    const distance = lines.scrollHeight - lines.scrollTop - lines.clientHeight;
    assemblyTranscriptState.followLatest = distance <= 28;
    updateTranscriptFollowButton(lines);
  }, { passive: true });
  raw.append(controls);
  window.requestAnimationFrame(() => updateTranscriptScrollRange(lines));
}

function transcriptLine(item) {
  const lineId = item.utterance_id || item.segment_id;
  let line = assemblyTranscriptState.nodes.get(lineId);
  if (!line) {
    line = magazineElement("div", "transcript-line", "");
    const body = magazineElement("div", "transcript-body", "");
    const summary = magazineElement("div", "transcript-summary", "");
    summary.append(
      magazineElement("small", "transcript-summary-label", "자동 발췌 요약"),
      magazineElement("p", "transcript-summary-text", ""),
    );
    const original = magazineElement("details", "transcript-original", "");
    original.append(
      magazineElement("summary", "", "원문 전체 보기"),
      magazineElement("p", "transcript-text", ""),
    );
    body.append(summary, original);
    const speaker = assemblyTranscriptState.expandedMode === "REVIEW"
      ? magazineElement("span", "transcript-speaker", "") : null;
    line.append(...[
      speaker, body, magazineElement("time", "transcript-time", ""),
    ].filter(Boolean));
    assemblyTranscriptState.nodes.set(lineId, line);
    document.querySelector("#assemblyTranscriptLines")?.append(line);
  }
  line.classList.toggle("is-final", item.is_final === true);
  line.classList.toggle("is-active-turn", item.is_active_turn === true);
  const speaker = line.querySelector(".transcript-speaker");
  const reconciliation = item.official_reconciliation;
  if (speaker) {
    const officialSpeaker = reconciliation?.status === "MATCHED"
      ? reconciliation.official_speaker_name : null;
    speaker.replaceChildren(document.createTextNode(officialSpeaker || "공식 화자 확인 중"));
    if (Number(item.segment_count || 1) > 1) {
      speaker.append(magazineElement("small", "transcript-segment-count", `${item.segment_count}개 자막 연결`));
    }
    if (reconciliation?.status === "MATCHED") {
      const badge = magazineElement("span", "reconciliation-badge is-matched", "공식본 일치");
      badge.title = `${reconciliation.publication_stage || "공식본"} · ${reconciliation.match_method}`;
      speaker.append(badge);
    } else if (item.official_status === "PUBLISHED" && item.is_final === true) {
      const badge = magazineElement("span", "reconciliation-badge is-unresolved", "공식본 미확인");
      badge.title = "공식 회의록에서 유일한 exact 일치 문장을 확인하지 못했습니다.";
      speaker.append(badge);
    }
  }
  const summaryProviderLabel = {
    gemini: "Gemini Flash",
    mistral: "Mistral Small",
    openrouter: "OpenRouter",
  }[item.summary_provider] || "AI";
  const activeTurn = item.is_active_turn === true;
  line.querySelector(".transcript-summary-label").textContent = activeTurn
    ? "현재 발언 · 실시간 누적"
    : item.summary_kind === "AI_CACHED" ? `${summaryProviderLabel} 요약 · DB 저장` : "요약 준비 중 · 원문 보존";
  const activeSummary = line.querySelector(".transcript-summary-text");
  activeSummary.textContent = activeTurn
    ? item.text : item.summary || summarizeUtterance(item.text);
  if (activeTurn) {
    window.requestAnimationFrame(() => {
      if (activeSummary.isConnected) {
        activeSummary.scrollTop = activeSummary.scrollHeight;
      }
    });
  }
  line.querySelector(".transcript-text").textContent = item.text;
  const original = line.querySelector(".transcript-original");
  original.hidden = activeTurn;
  if (!activeTurn) original.open = item.original_open === true;
  line.querySelector(".transcript-original > summary").textContent = `원문 전체 보기 · ${String(item.text || "").length.toLocaleString("ko-KR")}자`;
  const received = new Date(item.received_at);
  line.querySelector(".transcript-time").textContent = Number.isNaN(received.valueOf())
    ? "LIVE" : received.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return line;
}

function inferLiveHint(item) {
  const insight = item.live_insight;
  if (insight?.topic && insight?.topic_key) {
    const discussion = insight.discussion_group;
    const topicKey = String(insight.topic_key).toLocaleLowerCase("ko-KR")
      .replace(/[^가-힣a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    return {
      topic_id: discussion?.id ? `discussion:${discussion.id}` : `ai:${topicKey || insight.topic}`,
      semantic_group: Boolean(discussion?.id),
      topic_key: insight.topic_key,
      topic: discussion?.title || insight.topic,
      role: insight.role || "STATEMENT",
      task: insight.task || null,
      task_id: insight.task ? item.utterance_id || item.segment_id : null,
      task_status: insight.task ? "OPEN" : null,
      resolution: false,
      ministries: Array.isArray(insight.owners) ? insight.owners : [],
      derived: false,
    };
  }
  const hint = item.insight_hint || (Array.isArray(item.insight_hints) ? item.insight_hints.at(-1) : null);
  if (hint?.topic_id && hint?.role) return hint;
  return null;
}

function liveTopicTokens(...values) {
  const stop = new Set(["관련", "정책", "지원", "방안", "개선", "필요", "필요성", "요청", "검토", "추진",
    "국정감사", "종합", "질의", "답변", "요구", "확인", "논의", "설명", "문제", "제기", "위원", "위원회"]);
  return new Set(
    values.flatMap((value) => (
      String(value || "").toLocaleLowerCase("ko-KR").match(/[가-힣a-z0-9]{2,}/g) || []
    ))
      .filter((token) => !stop.has(token)),
  );
}

function liveOwnerTokens(values = []) {
  const source = Array.isArray(values) ? values : [values];
  const tokens = source.flatMap((value) => {
    const normalized = String(value || "").toLocaleLowerCase("ko-KR").replace(/[^가-힣a-z0-9]+/g, "");
    if (!normalized) return [];
    const stem = normalized.replace(
      /(위원회|위원장|본부|부처|청|처|부|원)$/u,
      "",
    );
    return stem && stem !== normalized ? [normalized, stem] : [normalized];
  });
  return new Set(tokens);
}

function liveTopicTokenRelated(left, right) {
  if (left === right) return true;
  const [shorter, longer] = left.length <= right.length ? [left, right] : [right, left];
  // A shared two-character fragment (국회/국감/위원) is not a shared issue.
  return shorter.length >= 3 && longer.startsWith(shorter);
}

function liveTopicOverlap(left, right) {
  const [smaller, larger] = left.size <= right.size ? [left, right] : [right, left];
  return [...smaller].filter((token) => (
    [...larger].some((candidate) => liveTopicTokenRelated(token, candidate))
  )).length;
}

function liveTopicSetsOverlap(left, right) {
  return [...left].some((token) => (
    [...right].some((candidate) => liveTopicTokenRelated(token, candidate))
  ));
}

function similarLiveTopic(groups, hintTokens, hintOwners, sequence) {
  if (!hintTokens.size) return null;
  let best = null;
  let bestScore = 0;
  for (const candidate of new Set(groups.values())) {
    if (candidate.semanticGroup) continue;
    const candidateTokens = candidate.topicTokens || new Set();
    const overlap = liveTopicOverlap(hintTokens, candidateTokens);
    const score = (2 * overlap) / (hintTokens.size + candidateTokens.size || Infinity);
    const ownerMatch = liveTopicSetsOverlap(hintOwners, candidate.ownerTokens || new Set());
    const recent = sequence - Number(candidate.lastSeen || 0) <= 8;
    const highConfidence = overlap >= 2 && score >= 0.72;
    const lexicalMatch = overlap >= 3 && score >= 0.6;
    const contextualMatch = ownerMatch && recent && overlap >= 2 && score >= 0.65;
    const rank = score + (ownerMatch ? 0.24 : 0) + (recent ? 0.08 : 0);
    if (
      (highConfidence || lexicalMatch || contextualMatch)
      && rank > bestScore
    ) {
      best = candidate;
      bestScore = rank;
    }
  }
  return best;
}

function buildLiveTopics(segmentItems = null) {
  const groups = new Map();
  let insightSequence = 0;
  const items = [...(segmentItems || assemblyTranscriptState.segments.values())]
    .filter((item) => item.is_final === true)
    .sort((a, b) => Number(a.cursor || a.first_cursor || a.last_cursor || 0) - Number(b.cursor || b.first_cursor || b.last_cursor || 0));
  for (const item of items) {
    const hint = inferLiveHint(item);
    if (!hint) continue;
    const sequence = insightSequence;
    insightSequence += 1;
    const hintTokens = liveTopicTokens(hint.topic_key, hint.topic);
    const hintOwners = liveOwnerTokens(hint.ministries);
    let group = groups.get(hint.topic_id) || (!hint.semantic_group && similarLiveTopic(groups, hintTokens, hintOwners, sequence));
    if (!group) {
      group = {
        topic: hint.topic,
        semanticGroup: Boolean(hint.semantic_group),
        // Immutable anchor: unioning every matched topic causes A→B→C chains
        // to absorb an entire meeting into its opening/procedural heading.
        topicTokens: new Set(hintTokens),
        ownerTokens: new Set(),
        lastSeen: sequence,
        questions: [], answers: [], tasks: new Map(), ministries: new Set(), derived: false,
      };
    }
    for (const owner of hintOwners) group.ownerTokens.add(owner);
    group.lastSeen = sequence;
    groups.set(hint.topic_id, group);
    const evidence = {
      speaker: item.speaker_label || "발언자 확인 중",
      summary: hint.summary || item.summary || summarizeUtterance(item.text),
      text: item.text,
      cursor: Number(item.cursor || item.last_cursor || 0),
      receivedAt: item.received_at || item.end_at || item.start_at || null,
      segmentCount: Number(item.segment_count || 1),
      segmentId: item.utterance_id || item.segment_id,
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
  return [...new Set(groups.values())]
    .sort((left, right) => Number(left.lastSeen || 0) - Number(right.lastSeen || 0));
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
  const compactMode = ["LIVE", "EXECUTIVE_LIVE", "POST_PROCESSING"].includes(
    assemblyTranscriptState.expandedMode,
  );
  const preparedItems = Array.isArray(segmentItems) ? [...segmentItems] : segmentItems;
  const latestItem = Array.isArray(preparedItems) ? preparedItems.at(-1) : null;
  const completedItems = compactMode
    && latestItem?.lifecycle_status === "LIVE"
    ? preparedItems.slice(0, -1)
    : preparedItems;
  const allGroups = buildLiveTopics(completedItems);
  container.classList.toggle("is-compact", compactMode);
  if (compactMode) {
    renderCompactLiveInsights(container, allGroups, completedItems);
    return;
  }
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
      magazineElement("span", group.derived ? "draft-label" : "structured-label", group.derived ? "AUTO GROUP · DRAFT" : "STRUCTURED"),
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
          const officialSpeaker = entry.officialReconciliation?.status === "MATCHED"
            ? entry.officialReconciliation.official_speaker_name : null;
          const speaker = magazineElement("small", "", officialSpeaker || "발언 묶음");
          if (entry.officialReconciliation?.status === "MATCHED") {
            speaker.append(magazineElement("span", "reconciliation-badge is-matched", "공식본 일치"));
          } else if (entry.officialStatus === "PUBLISHED") {
            speaker.append(magazineElement("span", "reconciliation-badge is-unresolved", "공식본 미확인"));
          }
          const original = magazineElement("details", "live-utterance-original", "");
          original.append(
            magazineElement("summary", "", `원문 전체 보기 · ${entry.segmentCount}개 자막`),
            magazineElement("p", "", entry.text),
          );
          quote.append(
            speaker,
            magazineElement("p", "live-utterance-summary", entry.summary),
            original,
          );
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

function liveReportSearchText(group) {
  return [
    group.topic,
    ...group.ministries,
    ...group.questions.flatMap((entry) => [entry.summary, entry.text]),
    ...group.answers.flatMap((entry) => [entry.summary, entry.text]),
    ...[...group.tasks.values()].flatMap((task) => [task.text, ...(task.ministries || [])]),
  ].filter(Boolean).join(" ").toLocaleLowerCase("ko-KR");
}

function liveDraftTopicMetadata(group, entries) {
  const officialSpeakers = [...new Set(entries
    .filter((entry) => entry.officialReconciliation?.status === "MATCHED")
    .map((entry) => String(entry.officialReconciliation?.official_speaker_name || "").trim())
    .filter(Boolean))];
  const identifiedSpeakers = new Set(entries
    .map((entry) => String(entry.speaker || "").trim())
    .filter((speaker) => speaker && speaker !== "발언자 확인 중"));
  const captionCount = entries.reduce(
    (sum, entry) => sum + Math.max(1, Number(entry.segmentCount || 1)), 0,
  );
  const metadata = [];
  if (officialSpeakers.length) {
    const names = officialSpeakers.slice(0, 3).join(" · ");
    metadata.push(`공식 확인 ${names}${officialSpeakers.length > 3 ? ` 외 ${officialSpeakers.length - 3}명` : ""}`);
  } else if (identifiedSpeakers.size) {
    metadata.push(`발언자 ${identifiedSpeakers.size}명`);
  }
  if (group.questions.length) metadata.push(`질의 ${group.questions.length}건`);
  if (group.answers.length) metadata.push(`답변·발언 ${group.answers.length}건`);
  if (captionCount > entries.length) metadata.push(`확정 자막 ${captionCount}개`);
  return metadata;
}

function renderCompactLiveInsights(container, allGroups, segmentItems = null) {
  const previousOverviewScroll = container.querySelector(".live-draft-overview-list")?.scrollTop || 0;
  const normalizedQuery = liveReportFilterState.query.trim().toLocaleLowerCase("ko-KR");
  const groups = normalizedQuery
    ? allGroups.filter((group) => liveReportSearchText(group).includes(normalizedQuery))
    : allGroups;
  const taskCount = groups.reduce((sum, group) => sum + group.tasks.size, 0);
  const utteranceCount = groups.reduce(
    (sum, group) => sum + group.questions.length + group.answers.length, 0,
  );
  const report = container.querySelector(":scope > .live-draft-report")
    || magazineElement("section", "meeting-brief-view live-draft-report", "");
  container.querySelector(":scope > .live-insight-empty")?.remove();
  if (report.parentElement !== container) container.append(report);
  const retainedFilterBar = report.querySelector(":scope > .live-report-filter");
  for (const child of [...report.children]) {
    if (child !== retainedFilterBar) child.remove();
  }
  report.setAttribute("aria-live", "polite");
  report.setAttribute("aria-label", "실시간 초안 보고서");
  const hero = magazineElement("header", "meeting-brief-hero", "");
  const identity = magazineElement("div", "", "");
  const labels = magazineElement("div", "meeting-brief-labels", "");
  const meetingSessions = assemblyTranscriptState.meetingSessions || [];
  const checkpointedSessions = meetingSessions.filter((item) => item.status === "CHECKPOINTED").length;
  labels.append(
    magazineElement("span", "institution-label", container.dataset.institutionLabel || "LIVE"),
    magazineElement("span", "provisional-label", "실시간 초안 · 잠정"),
    magazineElement("span", "", meetingSessions.length
      ? `세션 ${meetingSessions.length}회 · 중간정리 ${checkpointedSessions}회`
      : "화자 전환 시 갱신"),
  );
  identity.append(
    labels,
    magazineElement("h3", "", container.dataset.meetingTitle || "현재까지의 회의 초안"),
    magazineElement(
      "p", "", groups.length
        ? `${utteranceCount.toLocaleString("ko-KR")}개 확정 발언 묶음을 주제와 과제로 정리했습니다. 방송 종료 후 전체 분석을 거쳐 비공식 보고서로 확정됩니다.`
        : "첫 화자 발언이 끝나면 주제와 과제를 이 보고서 형식으로 누적합니다.",
    ),
  );
  const metrics = magazineElement("dl", "meeting-brief-metrics", "");
  for (const [label, value] of [
    ["핵심 주제", groups.length], ["도출 과제", taskCount], ["근거 발언", utteranceCount],
  ]) {
    const metric = document.createElement("div");
    metric.append(magazineElement("dt", "", label), magazineElement("dd", "", String(value)));
    metrics.append(metric);
  }
  hero.append(identity, metrics);

  report.prepend(hero);
  const filterBar = retainedFilterBar || magazineElement("div", "live-report-filter", "");
  let filterInput = filterBar.querySelector("input");
  let filterStatus = filterBar.querySelector("span");
  let clearFilter = filterBar.querySelector("button");
  if (!filterInput || !filterStatus || !clearFilter) {
    filterBar.replaceChildren();
    filterInput = document.createElement("input");
    filterInput.type = "search";
    filterInput.placeholder = "주제·부처·과제·발언 키워드 검색";
    filterInput.setAttribute("aria-label", "실시간 보고서 키워드 필터");
    filterStatus = magazineElement("span", "", "");
    clearFilter = magazineElement("button", "", "초기화");
    clearFilter.type = "button";
    filterInput.addEventListener("input", () => {
      liveReportFilterState.query = filterInput.value;
      renderLiveInsights(container);
    });
    clearFilter.addEventListener("click", () => {
      liveReportFilterState.query = "";
      filterInput.value = "";
      renderLiveInsights(container);
      filterInput.focus();
    });
    filterBar.append(filterInput, filterStatus, clearFilter);
  }
  if (document.activeElement !== filterInput) filterInput.value = liveReportFilterState.query;
  filterStatus.textContent = normalizedQuery
    ? allGroups.length + "개 중 " + groups.length + "개 표시"
    : "전체 " + allGroups.length + "개 주제";
  clearFilter.disabled = !normalizedQuery;
  if (filterBar.parentElement !== report) hero.after(filterBar);
  if (!groups.length) {
    report.append(magazineElement(
      "p", "meeting-result-empty",
      allGroups.length
        ? "입력한 키워드와 일치하는 주제·과제·발언이 없습니다."
        : "화자가 전환되어 첫 발언 묶음이 닫히면 요약된 논의 주제와 도출 과제가 나타납니다.",
    ));
    if (report.parentElement !== container) container.append(report);
    return;
  }
  const models = [];
  const overview = magazineElement("section", "meeting-topic-task-overview live-draft-overview", "");
  const overviewHead = magazineElement("header", "", "");
  overviewHead.append(
    magazineElement("strong", "", "요약된 논의 주제"),
    magazineElement("strong", "", "도출 과제"),
  );
  overview.append(overviewHead);
  const overviewList = magazineElement("div", "live-draft-overview-list", "");
  overviewList.tabIndex = 0;
  overviewList.setAttribute("aria-label", "요약된 논의 주제와 도출 과제 목록");
  for (const group of groups) {
    const rawMinistries = [...new Set([
      ...(group.ministries || []),
      ...[...group.tasks.values()].flatMap((task) => task.ministries || []),
    ].filter(Boolean))];
    const ministries = rawMinistries.filter((ministry) => !rawMinistries.some(
      (other) => other !== ministry && other.length > ministry.length && other.includes(ministry),
    ));
    const entries = [
      ...group.questions.map((entry) => ({ ...entry, draftRole: "질의" })),
      ...group.answers.map((entry) => ({ ...entry, draftRole: "답변·발언" })),
    ].sort((left, right) => left.cursor - right.cursor);
    const lastEntry = entries.at(-1);
    const tasks = [...group.tasks.values()];
    models.push({ group, ministries, entries, lastEntry, tasks });
    const overviewRow = magazineElement("article", "meeting-topic-task-row", "");
    const topicButton = magazineElement("button", "meeting-topic-summary-button", "");
    topicButton.type = "button";
    topicButton.append(magazineElement("strong", "", group.topic));
    topicButton.addEventListener("click", () => focusLiveDraftTopic(group.topic, lastEntry?.segmentId));
    const taskCell = magazineElement("div", "meeting-topic-task-cell", "");
    if (tasks.length) {
      const task = tasks[0];
      const taskButton = magazineElement("button", "meeting-topic-task-button", "");
      taskButton.type = "button";
      taskButton.append(magazineElement("strong", "", task.text));
      if (tasks.length > 1) {
        taskButton.append(magazineElement("span", "meeting-topic-task-more", "외 " + (tasks.length - 1) + "건"));
      }
      taskButton.addEventListener("click", () => focusLiveDraftTopic(group.topic, task.evidence?.segmentId));
      taskCell.append(taskButton);
    } else {
      taskCell.append(magazineElement("span", "meeting-topic-no-task", "이 주제에서 확인된 도출 과제가 없습니다."));
    }
    overviewRow.append(topicButton, taskCell);
    overviewList.append(overviewRow);
  }
  overview.append(overviewList);
  report.append(overview);
  window.requestAnimationFrame(() => {
    if (overviewList.isConnected) {
      overviewList.scrollTop = Math.min(previousOverviewScroll, overviewList.scrollHeight);
    }
  });
  const details = magazineElement("section", "meeting-topic-board live-draft-topic-board", "");
  details.append(magazineElement("header", "", "주요 논의 내용"));
  for (const { group, ministries, entries, lastEntry, tasks } of models) {
    const card = magazineElement("article", "meeting-result-topic live-draft-result-topic", "");
    card.dataset.liveTopic = group.topic;
    card.tabIndex = -1;
    const cardHead = magazineElement("div", "meeting-result-topic-head", "");
    const cardTitle = magazineElement("div", "", "");
    const ministryLabels = magazineElement("div", "live-draft-ministry-labels", "");
    for (const ministry of ministries.slice(0, 4)) ministryLabels.append(magazineElement("b", "", ministry));
    if (!ministries.length) ministryLabels.append(magazineElement("em", "", "소관 확인 중"));
    cardTitle.append(ministryLabels, magazineElement("h4", "", group.topic));
    const verifiedMetadata = liveDraftTopicMetadata(group, entries);
    if (verifiedMetadata.length) {
      const metadata = magazineElement("div", "live-draft-topic-metadata", "");
      for (const label of verifiedMetadata) metadata.append(magazineElement("span", "", label));
      cardTitle.append(metadata);
    }
    const evidenceButton = magazineElement("button", "meeting-evidence-button", `근거 발언 ${entries.length}개`);
    evidenceButton.type = "button";
    evidenceButton.addEventListener("click", () => openLiveDraftEvidenceDialog(
      group.topic, entries, "근거 발언 " + entries.length + "개",
    ));
    cardHead.append(cardTitle, evidenceButton);
    const points = magazineElement("div", "meeting-speaker-points", "");
    for (const entry of entries.slice(-3)) {
      const point = magazineElement("button", "", "");
      point.type = "button";
      point.append(
        magazineElement("strong", "", entry.draftRole),
        magazineElement("span", "", entry.summary),
        magazineElement("i", "", "발언 확인"),
      );
      point.addEventListener("click", () => openLiveDraftEvidenceDialog(
        group.topic, [entry], entry.draftRole + " · 원문 발언",
      ));
      points.append(point);
    }
    for (const task of tasks) {
      const taskRow = magazineElement("button", "meeting-topic-task-detail", "");
      taskRow.type = "button";
      taskRow.append(
        magazineElement("strong", "", "과제"),
        magazineElement("span", "", `${task.text}${task.ministries.length ? ` · ${task.ministries.join(" · ")}` : ""}`),
        magazineElement("i", "", "원문 보기"),
      );
      taskRow.addEventListener("click", () => openLiveDraftEvidenceDialog(
        task.text,
        task.evidence ? [{ ...task.evidence, draftRole: "과제 근거" }] : [],
        "도출 과제 · " + (task.ministries.join(" · ") || "담당 부처 확인 중"),
      ));
      points.append(taskRow);
    }
    card.append(cardHead, points);
    details.append(card);
  }
  report.append(details);
  if (report.parentElement !== container) container.append(report);
}

function openLiveDraftEvidenceDialog(title, entries, meta) {
  const dialog = document.querySelector("#liveDraftEvidenceDialog");
  const body = document.querySelector("#liveDraftEvidenceBody");
  if (!dialog || !body) return;
  document.querySelector("#liveDraftEvidenceTitle").textContent = title || "실시간 근거 발언";
  document.querySelector("#liveDraftEvidenceMeta").textContent = meta || "";
  body.replaceChildren();
  if (!entries.length) {
    body.append(magazineElement("p", "live-evidence-dialog-empty", "연결된 원문 발언을 아직 확인할 수 없습니다."));
  }
  for (const entry of entries) {
    const article = magazineElement("article", "live-evidence-dialog-item", "");
    article.append(
      magazineElement("span", "", entry.draftRole || "발언"),
      magazineElement("strong", "", entry.summary || "요약 준비 중"),
      magazineElement("p", "", entry.text || "원문을 확인하는 중입니다."),
    );
    body.append(article);
  }
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
}

function focusLiveDraftTopic(topic, segmentId) {
  const card = [...document.querySelectorAll(".live-draft-result-topic")]
    .find((candidate) => candidate.dataset.liveTopic === topic);
  if (card) {
    card.classList.add("is-focused");
    card.scrollIntoView({ behavior: "smooth", block: "start" });
    window.setTimeout(() => card.classList.remove("is-focused"), 2400);
  } else {
    focusLiveDraftEvidence(segmentId);
  }
}

function focusLiveDraftEvidence(segmentId) {
  if (!segmentId) return;
  const line = assemblyTranscriptState.nodes.get(segmentId);
  const raw = document.querySelector("#liveOperationsExpanded .raw-transcript");
  if (raw) raw.open = true;
  if (!line) return;
  line.classList.add("is-report-focus");
  line.scrollIntoView({ behavior: "smooth", block: "center" });
  window.setTimeout(() => line.classList.remove("is-report-focus"), 2400);
}

function syncLiveInsightHeight(media, insights) {
  const sync = () => {
    if (!media.isConnected || !insights.isConnected) return;
    if (!window.matchMedia("(min-width: 1101px)").matches) {
      insights.style.removeProperty("height");
      insights.style.removeProperty("max-height");
      return;
    }
    const height = Math.round(media.getBoundingClientRect().height);
    if (height > 0) {
      insights.style.height = `${height}px`;
      insights.style.maxHeight = `${height}px`;
      if (assemblyTranscriptState.followLatest && insights.matches(".raw-transcript")) {
        scrollTranscriptToLatest(insights.querySelector(".transcript-lines"));
      }
    }
  };
  window.requestAnimationFrame(sync);
  if (!("ResizeObserver" in window)) return;
  assemblyTranscriptState.layoutObserver?.disconnect();
  assemblyTranscriptState.layoutObserver = new ResizeObserver(sync);
  assemblyTranscriptState.layoutObserver.observe(media);
}

function isWatchReplaySource(sourceSystem) {
  return String(sourceSystem || "").startsWith("poc07.replay.");
}

function isWatchTestSource(sourceSystem) {
  return sourceSystem === "poc07.test" || isWatchReplaySource(sourceSystem);
}

function liveMedia(liveItem) {
  const media = magazineElement("div", "live-media", "");
  if (isWatchTestSource(liveItem?.source_system) && liveItem?.status === "COMPLETED") {
    media.classList.add("is-test-meeting", "is-test-ended");
    const endedStage = magazineElement("div", "test-meeting-stage", "");
    endedStage.append(
      magazineElement("span", "test-meeting-ended", "TEST END"),
      magazineElement("strong", "", "생방송 없음"),
      magazineElement("p", "", "테스트 영상 재생을 종료했습니다."),
      magazineElement("small", "", "아래 임시보고는 방송 종료 후 1분간만 유지됩니다."),
    );
    media.append(endedStage);
  } else if (isWatchReplaySource(liveItem?.source_system) && liveItem?.video_embed_url) {
    media.classList.add("is-replay-meeting");
    const iframe = document.createElement("iframe");
    iframe.src = liveItem.video_embed_url;
    iframe.title = "제438회 제1차 행정안전위원회 AI 데이터센터 질의답변 영상";
    iframe.allow = "autoplay; encrypted-media; picture-in-picture";
    iframe.allowFullscreen = true;
    iframe.referrerPolicy = "strict-origin-when-cross-origin";
    iframe.addEventListener("load", () => {
      window.setTimeout(() => {
        document.dispatchEvent(new CustomEvent("watch-replay-playback-ready", {
          detail: { testId: liveItem.test_id },
        }));
      }, 700);
    }, { once: true });
    media.append(iframe, magazineElement("span", "live-media-label", "REPLAY · 실제 저장 자막"));
  } else if (liveItem?.source_system === "poc07.test") {
    media.classList.add("is-test-meeting");
    const testStage = magazineElement("div", "test-meeting-stage", "");
    testStage.append(
      magazineElement("span", "test-meeting-live", "TEST LIVE"),
      magazineElement("strong", "", "가상 국무회의 방송 화면"),
      magazineElement("p", "", "실제 LIVE 화면에서 약 36초 동안 자막·화자 전환·주제·과제 갱신을 점검합니다."),
      magazineElement("small", "", "운영 방송과 분리된 테스트 데이터"),
    );
    media.append(testStage);
  } else if (liveItem?.stream_url) {
    const video = document.createElement("video");
    video.controls = true;
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.src = liveItem.stream_url;
    media.append(video);
    video.addEventListener("error", () => media.classList.add("stream-error"));
  } else {
    media.append(magazineElement("p", "live-media-unavailable", "검증된 영상 스트림 주소를 기다리고 있습니다."));
  }
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
  const liveMode = ["LIVE", "EXECUTIVE_LIVE", "POST_PROCESSING"].includes(mode);
  const stage = document.querySelector(liveMode ? "#liveOperationsExpandedStage" : "#liveExpandedStage");
  for (const id of ["assemblyLiveInsights", "assemblyTranscriptLines", "assemblyOfficialContext"]) {
    const previous = document.getElementById(id);
    if (previous && !stage.contains(previous)) previous.removeAttribute("id");
  }
  stage.className = "broadcast-stage transcript-stage";
  stage.replaceChildren();
  assemblyTranscriptState.followLatest = true;
  assemblyTranscriptState.autoScrolling = false;
  const head = magazineElement("div", "transcript-head", "");
  const title = magazineElement("div", "", "");
  const reviewMode = mode === "REVIEW";
  const postProcessingMode = mode === "POST_PROCESSING";
  if (reviewMode) {
    title.append(magazineElement(
      "span", "detected-live-label",
      "LAST LIVE REVIEW · PROVISIONAL",
    ));
  } else if (postProcessingMode) {
    title.append(magazineElement(
      "span", "detected-live-label is-processing",
      "방송 종료 · 비공식 보고서 정리 중",
    ));
  }
  title.append(
    magazineElement("strong", "", liveItems.map((item) => item.title || item.committee_name).join(" · ")),
  );
  const headActions = magazineElement("div", "transcript-head-actions", "");
  headActions.append(magazineElement(
    "span", "transcript-continuity",
    reviewMode
      ? "처음부터 끝까지 · 공식본 대조"
      : postProcessingMode
        ? "저장된 LIVE 초안과 발언 묶음 다시 보기"
        : "처음부터 현재까지 · 자동 갱신",
  ));
  if (!reviewMode) {
    const cinemaButton = magazineElement("button", "cinema-mode-toggle", "시네마 모드");
    cinemaButton.type = "button";
    cinemaButton.setAttribute("aria-pressed", "false");
    cinemaButton.addEventListener("click", () => toggleCinemaMode(stage));
    headActions.append(cinemaButton);
  }
  head.append(title, headActions);
  const workspace = magazineElement("div", `live-workspace${reviewMode ? "" : " is-live-layout"}`, "");
  const insights = magazineElement("aside", `live-insights${reviewMode ? "" : " is-compact"}`, "");
  insights.id = "assemblyLiveInsights";
  insights.dataset.meetingTitle = liveItems.map(
    (item) => item.title || item.committee_name,
  ).filter(Boolean).join(" · ");
  insights.dataset.institutionLabel = liveItems[0]?.institution === "EXECUTIVE"
    ? "국무회의" : "국회";
  insights.setAttribute("aria-label", "현재까지 확인된 주요 주제와 과제");
  insights.append(magazineElement("p", "live-insight-empty", "저장된 발언을 주제별로 묶는 중입니다."));
  const media = liveMedia(liveItems[0]);
  const raw = document.createElement(reviewMode ? "details" : "section");
  raw.className = `raw-transcript${reviewMode ? " is-review" : " is-live"}`;
  if (reviewMode) raw.open = true;
  const summary = magazineElement(reviewMode ? "summary" : "div", "raw-transcript-heading", reviewMode
    ? "발언 묶음별 요약 + 원문" : "실시간 자막 + 발언 묶음별 요약");
  const lines = magazineElement("div", "transcript-lines", "");
  lines.id = "assemblyTranscriptLines";
  lines.setAttribute("aria-live", "polite");
  lines.setAttribute("aria-label", "최신 자막으로 자동 이동하는 실시간 발언 묶음");
  lines.append(magazineElement("p", "transcript-waiting", "저장된 자막을 불러오는 중입니다."));
  raw.append(summary);
  bindTranscriptScrollControls(raw, lines);
  raw.append(lines);
  const cinemaExitButton = magazineElement("button", "cinema-mode-toggle cinema-mode-exit", "기본 보기");
  cinemaExitButton.type = "button";
  cinemaExitButton.setAttribute("aria-pressed", "true");
  cinemaExitButton.addEventListener("click", () => toggleCinemaMode(stage));
  if (reviewMode) {
    workspace.append(media, insights);
    const officialContext = magazineElement("div", "official-context", "");
    officialContext.id = "assemblyOfficialContext";
    stage.append(head, officialContext, workspace, raw);
    renderOfficialContext(liveItems[0]);
  } else {
    raw.classList.add("is-side");
    insights.classList.add("is-below");
    workspace.append(media, raw);
    stage.append(head, workspace, insights, cinemaExitButton);
    syncLiveInsightHeight(media, raw);
  }
}

function toggleCinemaMode(stage) {
  if (!stage) return;
  const enabled = !stage.classList.contains("is-cinema");
  stage.classList.toggle("is-cinema", enabled);
  stage.querySelectorAll(".cinema-mode-toggle").forEach((button) => {
    button.setAttribute("aria-pressed", String(enabled));
    button.textContent = button.classList.contains("cinema-mode-exit")
      ? "기본 보기"
      : enabled ? "기본 보기" : "시네마 모드";
  });
  if (enabled) {
    stage.scrollIntoView({ behavior: "smooth", block: "start" });
  }
  window.requestAnimationFrame(() => {
    const media = stage.querySelector(".live-media");
    const raw = stage.querySelector(".raw-transcript.is-side");
    if (!enabled && media && raw) {
      raw.style.removeProperty("height");
      raw.style.removeProperty("max-height");
      syncLiveInsightHeight(media, raw);
      scrollTranscriptToLatest(raw.querySelector(".transcript-lines"));
    }
    if (media) void media.offsetHeight;
  });
}

function applySpeakerDisplay(broadcastId, sourceLabel, displayName, overridden) {
  for (const [segmentId, item] of assemblyTranscriptState.segments) {
    if (item.broadcast_id !== broadcastId || String(item.source_speaker_label || "") !== sourceLabel) continue;
    assemblyTranscriptState.segments.set(segmentId, {
      ...item,
      speaker_label: displayName,
      speaker_overridden: overridden,
    });
  }
  const groups = groupTranscriptSegments();
  renderTranscriptGroups(groups);
  renderLiveInsights(document.querySelector("#assemblyLiveInsights"), groups);
}

function renderSpeakerEditor(broadcast, options = []) {
  const editor = document.querySelector("#assemblySpeakerEditor");
  if (!editor || !broadcast?.broadcast_id) return;
  const list = editor.querySelector(".speaker-editor-list");
  const status = editor.querySelector(".speaker-editor-status");
  list.replaceChildren();
  status.textContent = options.length
    ? "이름 수정은 원본 자막을 바꾸지 않고 이 방송의 표시 계층에만 적용됩니다."
    : "수집된 화자 코드가 없습니다.";
  for (const option of options) {
    const row = magazineElement("div", "speaker-editor-row", "");
    const sourceLabel = String(option.source_speaker_label || "");
    const label = document.createElement("label");
    label.append(
      document.createTextNode("원본 코드 "),
      magazineElement("b", "", sourceLabel || "-"),
      document.createTextNode(` · 자막 ${Number(option.segment_count || 0).toLocaleString("ko-KR")}개`),
    );
    const input = document.createElement("input");
    input.type = "text";
    input.maxLength = 80;
    input.value = option.display_name || "";
    input.placeholder = option.effective_display_name || "실제 화자 이름";
    input.setAttribute("aria-label", `화자 코드 ${sourceLabel || "-"}의 표시 이름`);
    const save = magazineElement("button", "primary", "저장");
    save.type = "button";
    const reset = magazineElement("button", "", "초기화");
    reset.type = "button";
    reset.disabled = !option.overridden;
    save.addEventListener("click", async () => {
      const displayName = input.value.trim();
      if (!displayName) {
        status.textContent = "표시할 화자 이름을 입력해 주세요.";
        input.focus();
        return;
      }
      save.disabled = true;
      status.textContent = "화자 이름을 저장하는 중입니다.";
      try {
        const response = await fetch(
          `api/live/broadcasts/${encodeURIComponent(broadcast.broadcast_id)}/speakers/${encodeURIComponent(sourceLabel)}`,
          { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ display_name: displayName }) },
        );
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || `저장 실패 (${response.status})`);
        option.display_name = payload.effective_display_name;
        option.effective_display_name = payload.effective_display_name;
        option.overridden = true;
        reset.disabled = false;
        applySpeakerDisplay(broadcast.broadcast_id, sourceLabel, payload.effective_display_name, true);
        status.textContent = `화자 코드 ${sourceLabel}을(를) ${payload.effective_display_name}(으)로 표시합니다.`;
      } catch (error) {
        status.textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });
    reset.addEventListener("click", async () => {
      reset.disabled = true;
      try {
        const response = await fetch(
          `api/live/broadcasts/${encodeURIComponent(broadcast.broadcast_id)}/speakers/${encodeURIComponent(sourceLabel)}`,
          { method: "DELETE" },
        );
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || `초기화 실패 (${response.status})`);
        input.value = "";
        option.display_name = null;
        option.effective_display_name = payload.effective_display_name;
        option.overridden = false;
        applySpeakerDisplay(broadcast.broadcast_id, sourceLabel, payload.effective_display_name, false);
        status.textContent = `화자 코드 ${sourceLabel}의 표시 이름을 초기화했습니다.`;
      } catch (error) {
        status.textContent = error.message;
        reset.disabled = false;
      }
    });
    row.append(label, input, save, reset);
    list.append(row);
  }
}

function collapseLiveExpansion() {
  const wasLive = ["LIVE", "EXECUTIVE_LIVE", "POST_PROCESSING"].includes(
    assemblyTranscriptState.expandedMode,
  );
  if (!wasLive) rememberMeetingReportSelection(null);
  assemblyTranscriptState.expanded = false;
  assemblyTranscriptState.expandedMode = null;
  assemblyTranscriptState.selectedBroadcastId = null;
  stopAssemblyTranscript();
  clearLiveReportHandoff();
  document.querySelector(wasLive ? "#liveOperationsExpandedStage" : "#liveExpandedStage")?.classList.remove("is-cinema");
  const target = document.querySelector(wasLive ? "#liveOperationsExpanded" : "#liveExpanded");
  if (target) target.hidden = true;
  document.querySelectorAll(".broadcast-row").forEach((row) => row.removeAttribute("aria-current"));
}

function expandLiveBroadcast(item, row) {
  clearLiveReportHandoff();
  assemblyTranscriptState.expanded = true;
  assemblyTranscriptState.expandedMode = "LIVE";
  assemblyTranscriptState.selectedBroadcastId = item.broadcast_id || item.meeting_external_id;
  document.querySelector("#liveOperationsExpanded").hidden = false;
  document.querySelector("#liveOperationsExpandedTitle").textContent = item.title || item.committee_name || "LIVE 방송 분석";
  document.querySelectorAll(".broadcast-row").forEach((candidate) => candidate.removeAttribute("aria-current"));
  row.setAttribute("aria-current", "true");
  startAssemblyTranscript([item]);
  document.querySelector("#liveOperationsExpanded").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function expandExecutiveLiveBroadcast(item, row) {
  clearLiveReportHandoff();
  assemblyTranscriptState.expanded = true;
  assemblyTranscriptState.expandedMode = "EXECUTIVE_LIVE";
  assemblyTranscriptState.selectedBroadcastId = item.broadcast_id || item.external_id;
  document.querySelector("#liveOperationsExpanded").hidden = false;
  document.querySelector("#liveOperationsExpandedTitle").textContent = item.title || "국무회의 생중계";
  document.querySelectorAll(".broadcast-row").forEach((candidate) => candidate.removeAttribute("aria-current"));
  row.setAttribute("aria-current", "true");
  startAssemblyTranscript([{ ...item, committee_name: "" }]);
  const continuity = document.querySelector(".transcript-continuity");
  if (continuity) continuity.textContent = item.source_system === "poc07.test"
    ? "격리 테스트 방송 · 공통 LIVE 자막·화자 묶음·초안 경로"
    : "KTV 공식 방송 · AI 음성 전사 · 종료 후 공식자료 교정";
  document.querySelector("#liveOperationsExpanded").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function watchTestBroadcast(payload) {
  const captured = payload?.transcript?.broadcasts?.[0] || {};
  const replay = payload?.replay_mode === "HASI_AI_REPLAY";
  return {
    ...captured,
    test_id: payload?.test_id,
    status: payload?.status || captured.status || "LIVE",
    broadcast_id: payload?.broadcast_id,
    external_id: `watch-test-${payload?.test_id || "live"}`,
    institution: payload?.institution || captured.institution || (replay ? "LEGISLATURE" : "EXECUTIVE"),
    committee_name: payload?.committee_name || captured.committee_name || (replay ? "행정안전위원회" : "국무회의"),
    title: payload?.title || captured.title || "관심주제 알림 가상방송",
    lifecycle_status: payload?.lifecycle_status || "LIVE",
    source_system: payload?.source_system || captured.source_system || "poc07.test",
    place: replay ? "국회 행정안전위원회 · 과거 방송 재현" : "가상 국무회의 테스트",
    video_embed_url: payload?.video_embed_url || captured.video_embed_url || null,
  };
}

function renderWatchTestLive(payload, options = {}) {
  if (!payload) return;
  const broadcast = watchTestBroadcast(payload);
  const broadcastId = String(broadcast.broadcast_id || payload.broadcast_id || "");
  const displayMode = broadcast.institution === "LEGISLATURE" ? "LIVE" : "EXECUTIVE_LIVE";
  const stage = document.querySelector("#liveOperationsExpandedStage");
  const needsShell = assemblyTranscriptState.expandedMode !== displayMode
    || String(assemblyTranscriptState.selectedBroadcastId || "") !== broadcastId
    || stage?.dataset.watchTestStatus !== payload.status
    || !document.querySelector("#liveOperationsExpandedStage .transcript-stage, #liveOperationsExpandedStage.transcript-stage");
  if (needsShell) {
    stopAssemblyTranscript();
    assemblyTranscriptState.expanded = true;
    assemblyTranscriptState.expandedMode = displayMode;
    assemblyTranscriptState.selectedBroadcastId = broadcastId;
    assemblyTranscriptState.broadcastId = broadcastId;
    document.querySelector("#liveOperationsExpanded").hidden = false;
    document.querySelector("#liveOperationsExpandedTitle").textContent = broadcast.title;
    renderTranscriptShell([broadcast], displayMode);
    stage.dataset.watchTestStatus = payload.status;
    const continuity = document.querySelector("#liveOperationsExpanded .transcript-continuity");
    if (continuity) continuity.textContent = payload.status === "COMPLETED"
      ? "테스트 방송 종료 · 생방송 없음 · 임시보고 1분 유지"
      : isWatchReplaySource(broadcast.source_system)
        ? "과거 행안위 참고 영상 · 저장 자막 빠른 재현 · 알람 경로 검증"
        : "격리 테스트 방송 · 공통 LIVE 자막·화자 묶음·초안 경로";
  }
  document.querySelectorAll("#liveBroadcastRows .broadcast-row").forEach((row) => {
    if (String(row.dataset.broadcastId || "") === broadcastId) row.setAttribute("aria-current", "true");
    else row.removeAttribute("aria-current");
  });
  const transcript = payload.transcript || {};
  const segments = (transcript.segments || []).map((segment) => ({ ...broadcast, ...segment }));
  applyTranscriptItems(segments, transcript.utterances || [], { detectTransition: false });
  if (!segments.length) {
    const waiting = document.querySelector("#liveOperationsExpanded .transcript-waiting");
    if (waiting) waiting.textContent = "가상 방송을 시작했습니다. 첫 자막을 기다리고 있습니다.";
  }
  if (options.focus === true) {
    document.querySelector("#liveOperationsExpanded")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function expandEndedExecutiveBroadcast(item, row) {
  stopAssemblyTranscript();
  rememberMeetingReportSelection(item.broadcast_id || item.external_id);
  assemblyTranscriptState.expanded = true;
  assemblyTranscriptState.expandedMode = "EXECUTIVE_ENDED";
  assemblyTranscriptState.selectedBroadcastId = item.broadcast_id || item.external_id;
  document.querySelector("#liveExpanded").hidden = false;
  document.querySelector("#liveExpandedTitle").textContent = item.title || "국무회의 결과";
  document.querySelectorAll(".broadcast-row").forEach((candidate) => candidate.removeAttribute("aria-current"));
  row?.setAttribute?.("aria-current", "true");
  const stage = document.querySelector("#liveExpandedStage");
  const root = magazineElement("section", "meeting-brief-view meeting-executive-view", "");
  const hero = magazineElement("header", "meeting-brief-hero", "");
  const labels = magazineElement("div", "meeting-brief-labels", "");
  labels.append(
    magazineElement("span", "institution-label", "국무회의"),
    magazineElement("span", "provisional-label", "LIVE 감지 기록"),
  );
  const detectedAt = item.detected_at ? new Date(item.detected_at).toLocaleString("ko-KR") : "감지 시각 미상";
  const endedAt = item.ended_at ? new Date(item.ended_at).toLocaleString("ko-KR") : "종료 시각 미상";
  hero.append(
    labels,
    magazineElement("h3", "", item.title || "국무회의 결과"),
    magazineElement("p", "", `${detectedAt} 감지 · ${endedAt} 종료`),
  );
  const tabs = magazineElement("div", "meeting-source-tabs", "");
  const liveTab = magazineElement("button", "", "LIVE 감지 기록 · 자막 없음");
  liveTab.type = "button";
  liveTab.setAttribute("aria-selected", "true");
  const officialTab = magazineElement("button", "", "공식 자료 · 발행 대기");
  officialTab.type = "button";
  officialTab.disabled = true;
  tabs.append(liveTab, officialTab);
  const notice = magazineElement("section", "executive-agenda-view", "");
  notice.append(
    magazineElement("strong", "", "공식 결과 자료를 기다리고 있습니다."),
    magazineElement("p", "meeting-result-empty", "KTV 편성에서 방송 시작과 종료는 확인했지만 기계 판독 자막이 없어 임시 발언 요약은 생성하지 않았습니다."),
    magazineElement("small", "", "공식 브리핑이 발행되면 같은 회의 번호로 이 카드에 자동 통합됩니다."),
  );
  const link = magazineElement("a", "meeting-official-source-link", "KTV 공식 온에어 확인 ↗");
  link.href = "https://www.ktv.go.kr/onair/tv";
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  notice.append(link);
  root.append(hero, tabs, notice);
  stage.replaceChildren(root);
}

function meetingBriefStatusLabel(task) {
  if (task.status === "OPEN" && task.owner_basis === "EXPLICIT") return "명시된 후속 조치";
  if (task.status === "RESOLVED") return "회의 내 해소";
  return "AI 검토 후보";
}

function meetingBriefOwnerLabel(task) {
  if (task.owner_basis === "EXPLICIT") return "발언에 명시";
  if (task.owner_basis === "INFERRED") return "AI 잠정 연결";
  return "담당부처 미확정";
}

function meetingEvidenceButton(item, entityType, entityId, label, title) {
  const button = magazineElement("button", "meeting-evidence-button", label);
  button.type = "button";
  button.addEventListener("click", () => {
    openMeetingBriefEvidence(item, entityType, entityId, title);
  });
  return button;
}

function meetingHighlightTerms(title) {
  const stop = new Set(["관련", "대한", "위한", "검토", "마련", "회의", "발언", "정부", "국회", "위원회"]);
  return [...new Set(String(title || "").match(/[가-힣A-Za-z0-9]{2,}/g) || [])]
    .filter((term) => !stop.has(term))
    .sort((a, b) => b.length - a.length)
    .slice(0, 8);
}

const MAX_MEETING_EVIDENCE_HIGHLIGHTS = 3;

function meetingSentenceRanges(value) {
  const sourceText = String(value || "");
  const ranges = [];
  const pattern = /[^.!?\n]+[.!?]?|\n+/g;
  let match;
  while ((match = pattern.exec(sourceText)) !== null) {
    if (match[0].trim()) ranges.push({ text: match[0], start: match.index, end: pattern.lastIndex });
  }
  return ranges;
}

function bestMeetingHighlightPhrase(value, context) {
  const sourceText = String(value || "");
  const terms = meetingHighlightTerms(context);
  let best = null;
  for (const sentence of meetingSentenceRanges(sourceText)) {
    const normalized = sentence.text.toLocaleLowerCase("ko-KR");
    const matchedTerms = terms.filter((term) => normalized.includes(term.toLocaleLowerCase("ko-KR")));
    if (!matchedTerms.length) continue;
    const tokens = [...sentence.text.matchAll(/[^\s,.;:!?]+/g)];
    if (tokens.length < 3) continue;
    const anchor = matchedTerms
      .map((term) => ({ term, index: normalized.indexOf(term.toLocaleLowerCase("ko-KR")) }))
      .filter((item) => item.index >= 0)
      .sort((left, right) => right.term.length - left.term.length || left.index - right.index)[0];
    const foundToken = tokens.findIndex((token) => (
      Number(token.index) <= anchor.index
      && Number(token.index) + token[0].length >= anchor.index + anchor.term.length
    ));
    const anchorToken = foundToken >= 0 ? foundToken : 0;
    let first = Math.max(0, anchorToken - 2);
    let last = Math.min(tokens.length - 1, anchorToken + 3);
    while (last - first < 2 && (first > 0 || last < tokens.length - 1)) {
      if (last < tokens.length - 1) last += 1;
      else first -= 1;
    }
    // A highlight is an explanatory phrase, never the whole sentence. Keep
    // one surrounding token unmarked when the source sentence is long enough.
    if (first === 0 && last === tokens.length - 1 && tokens.length > 2) {
      if (anchorToken - first > last - anchorToken) first += 1;
      else last -= 1;
    }
    const localStart = Number(tokens[first].index);
    const localEnd = Number(tokens[last].index) + tokens[last][0].length;
    const score = matchedTerms.reduce((total, term) => total + term.length, 0)
      + matchedTerms.length * 4;
    const candidate = {
      start: sentence.start + localStart,
      end: sentence.start + localEnd,
      score,
    };
    if (!best || candidate.score > best.score) best = candidate;
  }
  return best;
}

function selectMeetingEvidenceHighlights(items, title, limit = MAX_MEETING_EVIDENCE_HIGHLIGHTS) {
  return new Map(items
    .map((utterance, itemIndex) => {
      const summary = utterance.summary || summarizeUtterance(utterance.text);
      const candidate = bestMeetingHighlightPhrase(utterance.text, title + " " + summary);
      return { itemIndex, range: candidate, score: candidate?.score || 0 };
    })
    .filter((candidate) => candidate.range && candidate.score > 0)
    .sort((left, right) => right.score - left.score || left.itemIndex - right.itemIndex)
    .slice(0, limit)
    .map((candidate) => [candidate.itemIndex, candidate.range]));
}

function appendHighlightedPhrase(element, value, range = null) {
  const sourceText = String(value || "");
  if (!range || range.start < 0 || range.end <= range.start || range.end > sourceText.length) {
    element.textContent = sourceText;
    return element;
  }
  element.append(
    document.createTextNode(sourceText.slice(0, range.start)),
    magazineElement("mark", "", sourceText.slice(range.start, range.end)),
    document.createTextNode(sourceText.slice(range.end)),
  );
  return element;
}

function renderEvidencePlaceholder(panel) {
  panel.replaceChildren();
  const icon = magazineElement("span", "meeting-evidence-placeholder-icon", "↖");
  const copy = magazineElement("div", "", "");
  copy.append(
    magazineElement("span", "", "발언 확인"),
    magazineElement("strong", "", "주제·화자·과제를 선택하세요"),
    magazineElement("p", "", "선택한 내용과 연결된 화자별 자막 묶음 전체를 보여주고, 근거가 되는 핵심 문구만 표시합니다."),
  );
  panel.append(icon, copy);
}

function meetingEvidenceButton(item, entityType, entityId, label, title) {
  const button = magazineElement("button", "meeting-evidence-button", label);
  button.type = "button";
  button.dataset.evidenceType = entityType;
  button.dataset.evidenceId = entityId;
  button.setAttribute("aria-pressed", "false");
  button.addEventListener("click", () => {
    openMeetingBriefEvidence(item, entityType, entityId, title);
    const focusElementId = button.dataset.focusElementId
      || (button.dataset.focusTopicId
        ? "meeting-topic-detail-" + button.dataset.focusTopicId
        : "");
    if (focusElementId) {
      window.requestAnimationFrame(() => {
        const target = document.getElementById(focusElementId);
        const targetGroup = target?.matches("details.meeting-topic-group")
          ? target
          : target?.closest("details.meeting-topic-group");
        if (targetGroup) targetGroup.open = true;
        for (let parent = target?.parentElement; parent; parent = parent.parentElement) {
          if (parent.tagName === "DETAILS") parent.open = true;
        }
        target?.scrollIntoView({ behavior: "smooth", block: "start" });
        target?.focus({ preventScroll: true });
        target?.classList.add("is-focused");
        window.setTimeout(() => target?.classList.remove("is-focused"), 1400);
      });
    }
  });
  return button;
}

function setMeetingEvidenceSelection(entityType, entityId) {
  document.querySelectorAll("[data-evidence-id]").forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      String(button.dataset.evidenceType === entityType && button.dataset.evidenceId === entityId),
    );
  });
}

function officialEvidenceDetails(item) {
  const evidence = item.official_evidence || [];
  if (!evidence.length) {
    return magazineElement("p", "official-link-empty", "현재 공식 회의록에서 직접 연결할 근거를 찾지 못했습니다.");
  }
  const details = magazineElement("details", "official-evidence-details", "");
  details.append(magazineElement("summary", "", `관련 공식 발언 ${evidence.length}건 보기`));
  for (const record of evidence) {
    const row = magazineElement("article", "official-evidence-row", "");
    const meta = magazineElement("div", "", "");
    meta.append(
      magazineElement("strong", "", `공식 발언 #${record.sequence_number} · ${record.speaker_name}`),
      magazineElement("span", "", (record.agenda_titles || []).join(" · ") || "공식 회의록 본문"),
    );
    const tags = magazineElement("div", "official-evidence-tags", "");
    for (const ministry of record.ministries || []) {
      tags.append(magazineElement("b", "", ministry));
    }
    for (const term of record.shared_terms || []) {
      tags.append(magazineElement("em", "", term));
    }
    row.append(meta, magazineElement("p", "", record.excerpt), tags);
    details.append(row);
  }
  return details;
}

function renderOfficialBriefIntegration(integration) {
  const section = magazineElement("section", "meeting-official-integration", "");
  const head = magazineElement("header", "", "");
  head.append(
    magazineElement("span", "", "LIVE 분석 ↔ 공식 회의록"),
    magazineElement("h5", "", "주제와 과제별 관련 공식 근거"),
    magazineElement("p", "", integration.interpretation),
  );
  section.append(head);
  const categories = magazineElement("div", "official-category-chips", "");
  for (const category of integration.official_categories || []) {
    const chip = magazineElement("span", "", category.title);
    chip.append(magazineElement("b", "", String(category.official_utterance_count)));
    chip.title = (category.ministries || []).join(" · ");
    categories.append(chip);
  }
  if (categories.children.length) section.append(categories);

  const grid = magazineElement("div", "official-integration-grid", "");
  for (const [title, items, kind] of [
    ["논의 주제", integration.topics || [], "topic"],
    ["도출 과제", integration.tasks || [], "task"],
  ]) {
    const column = magazineElement("section", "official-integration-column", "");
    column.append(magazineElement("h6", "", title));
    for (const item of items) {
      const related = item.status === "OFFICIAL_RELATED";
      const card = magazineElement("article", `official-link-card ${related ? "is-related" : ""}`, "");
      const cardHead = magazineElement("header", "", "");
      cardHead.append(
        magazineElement("span", "", related ? `관련 공식 발언 ${item.official_evidence.length}건` : "공식 근거 미연결"),
        magazineElement("strong", "", item.title),
      );
      if (kind === "task" && (item.ministries || []).length) {
        const owners = magazineElement("div", "official-link-owners", "");
        for (const ministry of item.ministries) owners.append(magazineElement("b", "", ministry));
        cardHead.append(owners);
      }
      card.append(cardHead, officialEvidenceDetails(item));
      column.append(card);
    }
    if (!items.length) {
      column.append(magazineElement("p", "official-link-empty", "연결할 LIVE 분석 항목이 없습니다."));
    }
    grid.append(column);
  }
  section.append(grid);
  return section;
}

async function renderOfficialMeetingPanel(item) {
  const view = document.querySelector("#meetingBriefSourceView");
  if (!view) return;
  document.querySelectorAll(".meeting-source-tabs button").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.sourceTab === "official"));
  });
  view.replaceChildren(magazineElement("p", "meeting-brief-loading", "공식 자료와 LIVE 저장본의 매칭 상태를 확인하는 중입니다."));
  try {
    const response = await fetch(
      "api/live/broadcasts/" + encodeURIComponent(item.broadcast_id) + "/brief/official",
      { cache: "no-store" },
    );
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "HTTP " + response.status);
    const context = payload.context || {};
    const integration = payload.integration;
    const documentRecord = payload.document || {};
    const panel = magazineElement("section", "meeting-official-view", "");
    const status = magazineElement("header", "", "");
    const integrated = payload.status === "INTEGRATED";
    const documentStage = documentRecord.publication_stage === "FINAL"
      ? "정본" : documentRecord.publication_stage === "TEMPORARY" ? "임시회의록" : "공식 자료";
    status.append(
      magazineElement(
        "span", integrated ? "is-matched" : "",
        integrated ? `${documentStage} 통합 완료`
          : payload.status === "PUBLISHED" ? "공식본 분류 중" : "공식본 발행 대기",
      ),
      magazineElement("h4", "", payload.message),
      magazineElement(
        "p", "",
        integrated
          ? `${documentStage}의 공식 발언을 LIVE 잠정 분석과 나란히 연결했습니다. 연결 표시는 공식 승인이나 과제 확정을 뜻하지 않습니다.`
          : "LIVE 저장본은 빠른 이해를 위한 잠정 정보이며 공식 자료가 준비되면 별도 출처로 연결됩니다.",
      ),
    );
    const summary = integration?.summary || {};
    const metricItems = integration ? [
      ["공식 정책 발언", Number(summary.official_policy_utterances || 0).toLocaleString("ko-KR")],
      ["주제 관련 근거", `${summary.related_topic_count || 0}/${summary.live_topic_count || 0}`],
      ["과제 관련 근거", `${summary.related_task_count || 0}/${summary.live_task_count || 0}`],
    ] : [
      ["LIVE 최종 자막", Number(context.final_segment_count || 0).toLocaleString("ko-KR")],
      ["공식본 직접 일치", Number(context.matched_segment_count || 0).toLocaleString("ko-KR")],
      ["직접 일치율", Number(payload.match_rate || 0).toLocaleString("ko-KR") + "%"],
    ];
    const metrics = magazineElement("dl", "meeting-official-metrics", "");
    for (const [label, value] of metricItems) {
      const metric = document.createElement("div");
      metric.append(magazineElement("dt", "", label), magazineElement("dd", "", value));
      metrics.append(metric);
    }
    const links = magazineElement("div", "meeting-official-links", "");
    if (context.official_url) {
      const link = magazineElement("a", "", "공식 회의록 열기 ↗");
      link.href = context.official_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      links.append(link);
    }
    if (context.official_pdf_url) {
      const link = magazineElement("a", "", "공식 PDF 열기 ↗");
      link.href = context.official_pdf_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      links.append(link);
    }
    if (!links.children.length) links.append(magazineElement("small", "", "공식 원문이 발행되면 이곳에 바로 연결됩니다."));
    const exact = payload.exact_match || {};
    const exactNote = magazineElement(
      "p", "meeting-official-exact-note",
      `자막 문장 직접 일치 ${Number(exact.matched_segments || 0).toLocaleString("ko-KR")}/${Number(exact.final_segments || 0).toLocaleString("ko-KR")} · 관련 공식 근거 연결은 별도 보수 기준`,
    );
    panel.append(status, metrics, exactNote, links);
    if (integration) {
      panel.append(renderOfficialBriefIntegration(integration));
    }
    view.replaceChildren(panel);
  } catch (error) {
    view.replaceChildren(magazineElement("p", "meeting-result-empty", error.message));
  }
}

function renderMeetingLiveResolution(item, record) {
  const resolution = record.live_topic_resolution;
  const panel = magazineElement("details", "meeting-lineage-unmapped meeting-live-resolution", "");
  panel.append(
    magazineElement("summary", "", `실시간 논의 자동 분류 결과 · 미분류 ${resolution.review_count}묶음`),
    magazineElement("p", "", `기존 요약에서 연결되지 않았던 ${resolution.legacy_pending_count}묶음: 원문 기반 쟁점 연결 ${resolution.legacy_pending_linked_count} · 절차성 발언 ${resolution.legacy_pending_procedural_count} · 미분류 ${resolution.legacy_pending_review_count}.`),
    magazineElement("p", "", "아래 연결은 LIVE 원문을 재검토한 AI 잠정 결과입니다. 공식 대조본은 보존하며, 미분류 발언은 시스템이 앞뒤 문맥과 함께 재분석합니다. 재분석 후에도 원문이 불명확하면 그 사유를 표시합니다."),
  );
  const pending = resolution.entries.filter((entry) => ["PARTIAL", "UNRESOLVED"].includes(entry.status));
  for (const entry of pending) {
    const section = magazineElement("section", "meeting-live-resolution-pending", "");
    section.append(magazineElement("strong", "", entry.title), magazineElement("p", "",
      `연결된 세부 쟁점 ${entry.topics.length}개 · 자동 재분류·원문 한계 ${entry.review_evidence_ids.length}개`));
    for (const review of entry.review_items) {
      const button = meetingEvidenceButton(item, "structure_review", review.id, "", "분류 근거 원문 보기");
      button.append(magazineElement("strong", "", review.title), magazineElement("p", "", review.summary));
      if (review.reason) button.append(magazineElement("small", "", review.reason));
      section.append(button);
    }
    if (!entry.review_items.length && entry.structured_cluster_id) {
      section.append(meetingEvidenceButton(item, "live_topic_cluster", entry.structured_cluster_id, "", "묶음 원문 확인"));
    }
    panel.append(section);
  }
  const resolved = magazineElement("details", "meeting-live-resolution-linked", "");
  resolved.append(magazineElement("summary", "", `기존 미연결 항목의 처리 결과 ${resolution.legacy_pending_count}묶음`));
  for (const entry of resolution.entries.filter((entry) => entry.legacy_pending)) {
    const section = magazineElement("section", "", "");
    const label = entry.status === "LINKED" ? "쟁점 연결" : entry.status === "PROCEDURAL" ? "절차성 발언" : "미분류";
    section.append(magazineElement("strong", "", `${label} · ${entry.title}`));
    for (const topic of entry.topics) {
      const button = magazineElement("button", "", `연결 쟁점 보기 · ${topic.title}`);
      button.type = "button";
      button.dataset.resolutionTopicId = topic.id;
      button.addEventListener("click", () => renderMeetingBrief(item, {
        ...record, _brief_view: "structured", _focus_topic_id: topic.id,
      }));
      section.append(button);
    }
    if (entry.structured_cluster_id) {
      section.append(meetingEvidenceButton(item, "live_topic_cluster", entry.structured_cluster_id, "", "묶음 원문 확인"));
    }
    resolved.append(section);
  }
  panel.append(resolved);
  return panel;
}

function renderMeetingBrief(item, record, options = {}) {
  const stage = document.querySelector("#liveExpandedStage");
  const provisionalBrief = record?.provisional_brief || record?.brief || {};
  const officialBrief = record?.official_brief || null;
  const structuredBrief = record?.structured_brief || null;
  const officialStage = record?.official_context?.publication_stage;
  const provisionalSpeakerPoints = ((officialBrief || record?.brief || {}).topics || [])
    .flatMap((topic) => topic.speaker_points || []);
  const namedOfficialSpeakers = provisionalSpeakerPoints.filter(
    (point) => point.speaker_official === true
      && point.official_evidence_ids?.length
      && !String(point.speaker_label || "").startsWith("화자"),
  ).length;
  const unresolvedSpeakers = provisionalSpeakerPoints.filter(
    (point) => String(point.speaker_label || "").startsWith("화자"),
  ).length;
  const draftOnlyPoints = (officialBrief?.topics || [])
    .flatMap((topic) => topic.draft_only_speaker_points || []).length;
  const speakerCoverageNote = `공식 발언 원문 ${namedOfficialSpeakers}개 표시 · 초안 전용 ${draftOnlyPoints || unresolvedSpeakers}개 검토 필요`;
  const requestedView = record?._brief_view
    || (record?.default_brief_view === "OFFICIAL" ? "official" : structuredBrief ? "structured" : "provisional");
  const briefView = structuredBrief && requestedView === "structured" ? "structured"
    : officialBrief && requestedView === "official" ? "official" : "provisional";
  const brief = briefView === "structured" ? structuredBrief : briefView === "official" ? officialBrief : provisionalBrief;
  const structure = brief.topic_structure;
  const liveResolution = !structure && structuredBrief ? record.live_topic_resolution : null;
  const liveTopicLineage = brief.live_topic_lineage || {};
  const supplementaryCount = Number(brief.live_topic_coverage?.supplementary_topic_count || 0);
  const semanticMappingCompleted = ["COMPLETED", "COMPLETED_REVALIDATED"].includes(
    brief.live_topic_assignment?.semantic_mapping_status,
  );
  const liveTopicClusters = Array.isArray(liveTopicLineage.clusters)
    ? liveTopicLineage.clusters : [];
  const unmappedLiveTopics = liveTopicClusters.filter(
    (cluster) => ["UNMAPPED", "LEXICAL_CANDIDATE", "AMBIGUOUS", "MULTIPLE_FINAL_TOPICS", "REVIEW_REQUIRED"].includes(cluster.mapping_status),
  );
  const singleUtteranceUnmappedCount = unmappedLiveTopics.filter(
    (cluster) => Number(cluster.utterance_count || 0) === 1,
  ).length;
  const liveTopicClusterById = new Map(
    liveTopicClusters.map((cluster) => [cluster.id, cluster]),
  );
  const detailedTopics = Array.isArray(brief.topics) ? brief.topics : [];
  const topicById = new Map(detailedTopics.map((topic) => [String(topic.id), topic]));
  const storedTopicGroups = Array.isArray(brief.topic_groups) ? brief.topic_groups : [];
  const topicGroups = storedTopicGroups.length
    ? storedTopicGroups.map((group) => ({
      ...group,
      topic_ids: (group.topic_ids || []).map(String).filter((topicId) => topicById.has(topicId)),
    })).filter((group) => group.topic_ids.length)
    : detailedTopics.map((topic) => ({
      id: "topic-group-" + topic.id,
      title: topic.title,
      summary: topic.summary,
      topic_ids: [String(topic.id)],
      topic_count: 1,
    }));
  const openTasks = (brief.tasks || []).filter((task) => task.status !== "RESOLVED");
  stage.replaceChildren();
  const root = magazineElement("section", "meeting-brief-view", "");
  const hero = magazineElement("header", "meeting-brief-hero", "");
  const identity = magazineElement("div", "", "");
  const labels = magazineElement("div", "meeting-brief-labels", "");
  const sourceOnly = record?.official_integration?.comparison_mode === "SOURCE_ONLY_TIMEOUT";
  const finalizationPending = record?.brief_finalization && record.brief_finalization.status !== "COMPLETED";
  const resultLabel = finalizationPending ? "AI 요약 · 자동 검증 중인 초안"
    : briefView === "structured" ? "AI 요약 · 쟁점별 구조화 · 잠정"
    : briefView === "official"
    ? (sourceOnly ? "공식 발언·화자 반영 · 요약 대조 지연"
      : officialStage === "TEMPORARY"
      ? "공식 대조본 · 임시회의록 기준"
      : officialStage === "FINAL"
        ? "공식 대조본 · 정본 기준"
        : "공식 대조본 · 초안 별도 보존")
    : record?.provider === "deterministic"
      ? "자동 정리 · 잠정"
      : record?.provider === "pending" ? "결과 생성 대기" : "AI 요약 · 잠정";
  labels.append(
    magazineElement("span", "institution-label", item.institution_label || "국회"),
    magazineElement("span", "provisional-label", resultLabel),
    ...(Number(brief.meeting_session_count || 0) > 0
      ? [magazineElement("span", "", `세션 ${Number(brief.meeting_session_count).toLocaleString("ko-KR")}회 통합`)]
      : []),
    magazineElement("span", "", item.committee_name || "회의"),
  );
  identity.append(
    labels,
    officialTextElement("h3", "", brief.headline || item.title || "회의 결과 정리 중", brief, "headline"),
    officialTextElement("p", "", brief.summary || "저장된 회의 결과를 정리하는 중입니다.", brief, "summary"),
  );
  if (finalizationPending) {
    const stages = magazineElement("div", "meeting-stage-tags", "");
    stages.setAttribute("aria-label", "비공식 정리 단계별 진행 현황");
    for (const tag of meetingBriefStageTags({meeting_brief: record})) {
      const badge = magazineElement("span", `meeting-card-tag is-${tag.tone}`, tag.label);
      badge.title = tag.title || tag.label;
      stages.append(badge);
    }
    identity.append(stages);
    identity.append(magazineElement("p", "meeting-brief-scope-note",
      "주제 연결·정책 분류·세부 요약을 자동 점검하고 있습니다. 완료 전 초안이며, 처리 결과를 이어서 반영합니다."));
  }
  if (item.has_saved_live_record) {
    identity.append(magazineElement("p", "meeting-brief-scope-note",
      `${item.is_recess ? "정회 · 재개 대기 중" : "진행 중인 회의"}의 누적 저장본입니다. 최종 보고서는 회의 종료 후 정리됩니다.`));
  }
  const topicGrouping = brief.topic_grouping || {};
  if (!structuredBrief && record?.structure_progress?.status) {
    const progress = record.structure_progress;
    identity.append(magazineElement("p", "meeting-brief-scope-note",
      progress.status === "REVIEW_REQUIRED"
        ? "쟁점 재구조화의 추가 검토가 필요합니다. 기존 보고서와 근거를 표시합니다."
        : progress.status === "PROCESSING"
          ? `쟁점 재구조화 처리 중 · 발언 분류 ${progress.completed_batches || 0}구간 완료. 기존 보고서는 계속 열람할 수 있습니다.`
          : "쟁점 재구조화 대기 중 · 기존 보고서와 근거를 표시합니다.",
    ));
  }
  if (!structure && topicGrouping.quality_status === "REVIEW_REQUIRED") {
    const unclassified = Number(topicGrouping.unclassified_topic_count || 0);
    const singletons = Number(topicGrouping.singleton_unclassified_group_count || 0);
    identity.append(magazineElement(
      "p", "meeting-lineage-summary is-partial",
      `자동 분류 검토 필요 · 정책 대상 사전 미등록 ${unclassified.toLocaleString("ko-KR")}개 · 단독 보류 ${singletons.toLocaleString("ko-KR")}개`,
    ));
  }
  const lineageTotal = Number(liveTopicLineage.cluster_count || 0);
  if (lineageTotal > 0 && structure) {
    const details = magazineElement("details", "meeting-source-processing-details", "");
    details.append(magazineElement("summary", "", "주제 연결·원문 처리 내역"));
    details.append(magazineElement("p", "meeting-brief-scope-note", structuredLineageSummary(brief)));
    identity.append(details);
  }
  if (lineageTotal > 0 && !structure) {
    const lineageMapped = Number(liveTopicLineage.mapped_cluster_count || 0);
    const lineageAmbiguous = Number(liveTopicLineage.ambiguous_cluster_count || 0);
    const lineageUnmapped = Number(liveTopicLineage.unmapped_cluster_count || 0);
    const lineageNote = magazineElement(
      "p",
      `meeting-lineage-summary${lineageUnmapped || lineageAmbiguous ? " is-partial" : " is-complete"}`,
      liveResolution
        ? `실시간 ${liveResolution.cluster_count}묶음 재검토 · 잠정 쟁점 연결 ${liveResolution.linked_count} · 절차 ${liveResolution.procedural_count} · 미분류 ${liveResolution.review_count}`
        : structure
        ? `실시간 ${lineageTotal}묶음 재검토 · 쟁점 연결 ${lineageMapped} · 절차 ${liveTopicLineage.procedural_cluster_count || 0} · 판단 보류 ${lineageUnmapped} · 여러 세부 쟁점으로 분리 ${liveTopicLineage.split_cluster_count || 0}`
        : `실시간 주제 계보 ${lineageTotal.toLocaleString("ko-KR")}묶음 · 주제 연결 ${lineageMapped.toLocaleString("ko-KR")}${supplementaryCount ? ` (실시간 보완 ${supplementaryCount.toLocaleString("ko-KR")})` : ""} · 연결 후보·판단 보류 ${lineageAmbiguous.toLocaleString("ko-KR")} · 미연결 ${lineageUnmapped.toLocaleString("ko-KR")}${semanticMappingCompleted ? " · 자동 연결 실행 완료" : ""}`,
    );
    identity.append(lineageNote);
    if (supplementaryCount) identity.append(magazineElement(
      "p", "meeting-brief-scope-note",
      `기존 핵심 요약 ${Number(brief.live_topic_coverage.core_topic_count || 0)}개를 보존하고, 정책 대상과 발언 근거가 있는 누락 쟁점 ${supplementaryCount}개를 추가 표시했습니다. 보완 항목은 실시간 분석 기반의 잠정 내용이며 공식 원문 대조가 필요합니다.`,
    ));
  }
  const metrics = magazineElement("dl", "meeting-brief-metrics", "");
  for (const [label, value] of [
    ["대상 주제", topicGroups.length],
    ["도출 과제", openTasks.length],
    ["근거 발언", brief.utterance_count || item.utterance_count || 0],
  ]) {
    const metric = document.createElement("div");
    metric.append(magazineElement("dt", "", label), magazineElement("dd", "", String(value)));
    metrics.append(metric);
  }
  hero.append(identity, metrics);

  const reportTools = magazineElement("div", "meeting-report-tools", "");
  const printButton = magazineElement("button", "meeting-document-open-button", "요약 문서 · 인쇄/PDF");
  printButton.type = "button";
  const documentIcon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  documentIcon.setAttribute("viewBox", "0 0 24 24");
  documentIcon.setAttribute("width", "16");
  documentIcon.setAttribute("height", "16");
  documentIcon.setAttribute("fill", "none");
  documentIcon.setAttribute("stroke", "currentColor");
  documentIcon.setAttribute("stroke-width", "1.8");
  documentIcon.setAttribute("aria-hidden", "true");
  const documentPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  documentPath.setAttribute("d", "M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6");
  documentIcon.append(documentPath);
  printButton.prepend(documentIcon);
  printButton.addEventListener("click", async () => {
    reportTools.querySelector(".meeting-document-load-error")?.remove();
    if (brief.report_summary?.topics?.length) {
      openMeetingReportDocument(item, record, brief, briefView);
      return;
    }
    printButton.disabled = true;
    printButton.textContent = "요약 문서 준비 중…";
    try {
      // The initial list snapshot can render the toolbar before the full
      // structured narrative arrives. Never export that incomplete snapshot.
      const fullRecord = await requestMeetingBrief(item, { force: true });
      if (assemblyTranscriptState.selectedBroadcastId !== item.broadcast_id) return;
      const selected = meetingDocumentSource(fullRecord, record._brief_view);
      openMeetingReportDocument(item, fullRecord, selected.brief, selected.view);
    } catch (_) {
      const error = magazineElement("span", "meeting-document-load-error", "요약 문서를 불러오지 못했습니다. 다시 눌러 주세요.");
      error.setAttribute("role", "alert");
      reportTools.append(error);
    } finally {
      printButton.disabled = false;
      printButton.replaceChildren(documentIcon, document.createTextNode("요약 문서 · 인쇄/PDF"));
    }
  });
  const markdownLink = magazineElement("a", "", "Markdown 저장");
  markdownLink.href = `api/live/broadcasts/${encodeURIComponent(item.broadcast_id)}/brief.md?view=${briefView}`;
  markdownLink.download = `meeting-${item.broadcast_id}.md`;
  reportTools.append(printButton, markdownLink);
  identity.append(reportTools);

  const integrationBar = meetingIntegrationBar(item, record);
  if (structuredBrief) {
    for (const [view, label] of [["structured", "요약·쟁점·과제"], ...(!officialBrief ? [["provisional", "기존 요약"]] : [])]) {
      const button = magazineElement("button", "", label);
      button.type = "button";
      button.setAttribute("aria-pressed", String(briefView === view));
      button.addEventListener("click", () => renderMeetingBrief(item, { ...record, _brief_view: view }));
      integrationBar.append(button);
    }
  }
  if (officialBrief) {
    integrationBar.append(
      meetingBriefViewSwitch(briefView, (nextView) => {
        renderMeetingBrief(item, { ...record, _brief_view: nextView });
      }, sourceOnly),
      magazineElement(
        "small", "meeting-brief-source-note",
        briefView === "official"
          ? (sourceOnly
            ? `공식 회의록의 화자·발언 원문을 표시합니다. 주제 요약은 LIVE 초안에 근거하며 내용 대조는 지연 중입니다. ${speakerCoverageNote}.`
            : officialStage === "TEMPORARY"
            ? `임시회의록 근거로 확인된 내용을 표시합니다. ${speakerCoverageNote}. 정본 발행 시 다시 대조하며 LIVE/STT 초안은 보존됩니다.`
            : `공식 근거로 확인된 화자별 발언을 표시합니다. 주제 요약 문장은 LIVE/STT 초안의 해석이며 익명 화자 번호는 이름으로 추정하지 않습니다. ${speakerCoverageNote}. 초안 원문은 그대로 보존됩니다.`)
          : officialStage === "FINAL"
            ? `LIVE/STT 초안 내용 보존 · 정본 ${speakerCoverageNote}. 공식 변경은 별도 대조본에서 확인합니다.`
            : officialStage === "TEMPORARY"
              ? `LIVE/STT 초안 내용 보존 · 임시회의록 ${speakerCoverageNote}. 화자명은 정본 발행 후 다시 확인됩니다.`
              : "방송 당시 LIVE/STT 초안입니다. 공식 대조본은 자료 기준에서 선택할 수 있습니다.",
      ),
    );
  }
  const officialChangeReport = renderOfficialChangeReport(record);
  if (record?.brief_upgrade_pending) {
    const status = record.brief_upgrade_status;
    const upgradeCopy = status === "PROCESSING"
      ? "새 분석 기준으로 갱신 중입니다. 현재 보고서는 계속 열람할 수 있습니다."
      : "현재 보고서는 열람 가능하며, 새 분석 기준으로 순차 갱신됩니다.";
    integrationBar.append(magazineElement(
      "small", "meeting-brief-upgrade-note", upgradeCopy,
    ));
  }
  if (record?.brief_is_stale) {
    const previousTotal = Number(record.previous_utterance_count || 0);
    const currentTotal = Number(record.brief_progress?.total_utterances || evidenceCount);
    integrationBar.append(magazineElement(
      "small", "meeting-brief-upgrade-note",
      `새 발언 ${Math.max(0, currentTotal - previousTotal).toLocaleString("ko-KR")}개를 반영하는 중입니다. 완료 전까지 기존 보고서를 표시합니다.`,
    ));
  }

  const sourceView = magazineElement("div", "meeting-source-view", "");
  sourceView.id = "meetingBriefSourceView";
  const topicTaskOverview = magazineElement("section", "meeting-topic-task-overview", "");
  const overviewHead = magazineElement("header", "", "");
  overviewHead.append(
    magazineElement("strong", "", "대상 주제"),
    magazineElement("strong", "", "도출 과제"),
  );
  const topicTaskOverviewList = magazineElement("div", "meeting-topic-task-overview-list", "");
  topicTaskOverview.prepend(overviewHead);
  topicTaskOverview.append(topicTaskOverviewList);
  const linkedTaskIds = new Set();
  for (const group of topicGroups) {
    const overviewRow = magazineElement("article", "meeting-topic-task-row", "");
    const topicButton = meetingEvidenceButton(
      item, "topic_group", group.id, "", group.title,
    );
    topicButton.classList.add("meeting-topic-summary-button");
    topicButton.dataset.focusElementId = "meeting-topic-group-" + group.id;
    topicButton.append(
      magazineElement("strong", "", group.title),
      magazineElement(
        "small", "",
        `세부 쟁점 ${group.topic_ids.length.toLocaleString("ko-KR")}개`,
      ),
    );
    const taskCell = magazineElement("div", "meeting-topic-task-cell", "");
    const groupTopicIds = new Set(group.topic_ids);
    const groupTopicTitles = new Set(
      group.topic_ids.map((topicId) => topicById.get(topicId)?.title).filter(Boolean),
    );
    const matchesGroup = (task) => (
      (task.related_topic_ids || []).some((id) => groupTopicIds.has(String(id)))
      || (task.topic_id ? groupTopicIds.has(String(task.topic_id)) : groupTopicTitles.has(task.topic_title))
    );
    const linkedTasks = openTasks.filter(matchesGroup);
    for (const task of linkedTasks) linkedTaskIds.add(task.id);
    const moreTasks = magazineElement("details", "meeting-topic-more-tasks", "");
    moreTasks.append(magazineElement("summary", "", `추가 도출 과제 ${Math.max(0, linkedTasks.length - 1)}건`));
    for (const [taskIndex, task] of linkedTasks.entries()) {
      const taskButton = meetingEvidenceButton(item, "task", task.id, "", task.title);
      taskButton.classList.add("meeting-topic-task-button");
      const taskTitle = officialTextElement("strong", "", task.title, task, "title");
      taskButton.append(
        taskTitle,
        meetingTaskOwnerTags(task),
      );
      taskButton.dataset.focusTopicId = [task.topic_id, ...(task.related_topic_ids || [])].find((id) => groupTopicIds.has(id)) || group.topic_ids[0] || "";
      (taskIndex ? moreTasks : taskCell).append(taskButton);
    }
    if (linkedTasks.length > 1) taskCell.append(moreTasks);
    if (!linkedTasks.length) {
      taskCell.append(magazineElement(
        "span", "meeting-topic-no-task",
        "이 주제에서 확인된 도출 과제가 없습니다.",
      ));
    }
    overviewRow.append(topicButton, taskCell);
    topicTaskOverviewList.append(overviewRow);
  }
  const unlinkedTasks = openTasks.filter((task) => !linkedTaskIds.has(task.id));
  for (const task of unlinkedTasks) {
    const overviewRow = magazineElement("article", "meeting-topic-task-row", "");
    overviewRow.append(magazineElement("div", "meeting-topic-unlinked", "주제 연결 확인 필요"));
    const taskCell = magazineElement("div", "meeting-topic-task-cell", "");
    const taskButton = meetingEvidenceButton(item, "task", task.id, "", task.title);
    taskButton.classList.add("meeting-topic-task-button");
    taskButton.append(
      officialTextElement("strong", "", task.title, task, "title"),
      meetingTaskOwnerTags(task),
    );
    taskCell.append(taskButton);
    overviewRow.append(taskCell);
    topicTaskOverviewList.append(overviewRow);
  }
  if (!topicGroups.length) {
    topicTaskOverviewList.append(magazineElement("p", "meeting-result-empty", "요약된 논의 주제를 준비하는 중입니다."));
  }

  let lineageUnmappedPanel = null;
  if (liveResolution) {
    lineageUnmappedPanel = renderMeetingLiveResolution(item, record);
  } else if (unmappedLiveTopics.length) {
    lineageUnmappedPanel = magazineElement("details", "meeting-lineage-unmapped", "");
    const lineageSummary = magazineElement(
      "summary", "",
      `실시간 논의 ${structure?.automatic_review?.status === "COMPLETED" ? "재분석 후 원문 불명확" : "자동 분류 대기"} ${unmappedLiveTopics.length.toLocaleString("ko-KR")}묶음`,
    );
    const lineageHelp = magazineElement(
      "p", "",
      structure?.automatic_review?.status === "COMPLETED"
        ? "문맥을 포함한 자동 재분석을 마쳤으나 일부 발언의 대상을 특정할 근거가 부족합니다. 원문과 분류 사유를 보존합니다."
        : semanticMappingCompleted || structure
        ? `기존 연결 단계에서 미분류·부분 연결된 ${unmappedLiveTopics.length.toLocaleString("ko-KR")}묶음은 원문 문맥을 포함한 자동 재분류 대상입니다. 단일 발언 ${singleUtteranceUnmappedCount.toLocaleString("ko-KR")}묶음도 내용과 근거를 확인할 수 있습니다.`
        : "기존 연결 단계에서 미분류된 항목입니다. 시스템이 앞뒤 문맥을 재분석해 기존 쟁점에 연결하거나 별도 주제로 분류합니다.",
    );
    const lineageList = magazineElement("ul", "", "");
    for (const cluster of unmappedLiveTopics) {
      const row = magazineElement("li", "", "");
      const evidenceButton = magazineElement("button", "", "");
      evidenceButton.type = "button";
      evidenceButton.append(
        magazineElement("strong", "", cluster.title || "제목 확인 필요"),
        magazineElement(
          "small", "",
          [
            `발언 ${Number(cluster.utterance_count || 0).toLocaleString("ko-KR")}묶음`,
            ...(cluster.owners || []).slice(0, 3),
          ].join(" · "),
        ),
      );
      evidenceButton.addEventListener("click", () => openMeetingBriefEvidence(
        item, "live_topic_cluster", cluster.id, cluster.title || "실시간 주제",
      ));
      row.append(evidenceButton);
      lineageList.append(row);
    }
    lineageUnmappedPanel.append(lineageSummary, lineageHelp, lineageList);
  }

  const actions = magazineElement("div", "meeting-beta-actions", "");
  const fullTranscript = magazineElement("button", "", "전체 발언 기록 보기");
  fullTranscript.type = "button";
  fullTranscript.addEventListener("click", () => {
    const row = document.querySelector('.broadcast-row[data-broadcast-id="' + item.broadcast_id + '"]');
    expandEndedBroadcast(item, row || fullTranscript);
  });
  actions.append(
    magazineElement("small", "", "주제나 과제를 선택하면 해당 주요 논의 내용과 근거 발언으로 이동합니다."),
    fullTranscript,
  );

  const workspace = magazineElement("div", "meeting-result-workspace", "");
  const topics = magazineElement("section", "meeting-topic-board", "");
  topics.append(magazineElement("header", "", "주요 논의 요약"));
  let structureContainer = topics;
  {
    const narrative = brief.report_summary;
    const summaryTopics = narrative?.topics || [];
    const summaryById = new Map(summaryTopics.map((topic) => [topic.id, topic]));
    const summaryGroups = narrative?.topic_groups || summaryTopics.map((topic) => ({
      id: "summary-group-" + topic.id, title: topic.title, topic_ids: [topic.id],
    }));
    const summarySection = magazineElement("section", "meeting-narrative-summary", "");
    summarySection.setAttribute("aria-label", "대주제별 AI 논의 요약");
    summarySection.append(magazineElement("p", "meeting-brief-scope-note", "AI 요약 · 잠정 · 근거 원문은 각 요약에서 확인할 수 있습니다."));
    for (const group of summaryGroups) {
      const section = magazineElement("details", "meeting-topic-group meeting-summary-group", "");
      section.id = group.id;
      section.open = group === summaryGroups[0];
      const groupHead = magazineElement("summary", "meeting-topic-group-head", "");
      const countLabel = group.topic_ids.every((id) => summaryById.get(id)?.source_structured_topic_id)
        ? "세부 쟁점" : "발언 묶음";
      groupHead.append(magazineElement("span", "", "대주제"),
        magazineElement("h4", "", group.title),
        magazineElement("small", "", `${countLabel} ${group.topic_ids.length}개`));
      section.append(groupHead);
      for (const topicId of group.topic_ids) {
        const topic = summaryById.get(topicId);
        if (!topic) continue;
        const card = magazineElement("article", "meeting-result-topic meeting-summary-topic", "");
        const head = magazineElement("div", "meeting-result-topic-head", "");
        const copy = magazineElement("div", "", "");
        copy.append(officialTextElement("h4", "", topic.title, topic, "title"), officialTextElement("p", "", topic.summary, topic, "summary"));
        head.append(copy, meetingEvidenceButton(item, topic.evidence_type || "summary_topic", topic.id, `근거 발언 ${topic.evidence_ids?.length || 0}개`, topic.title));
        card.append(head);
        const rows = magazineElement("div", "meeting-speaker-points meeting-summary-rows", "");
        for (const point of topic.speaker_points || []) {
          const button = meetingEvidenceButton(item, point.evidence_type || "summary_speaker", point.id, "", topic.title);
          button.classList.add("meeting-summary-point");
          button.append(magazineElement("strong", "", point.speaker_label || "화자 미확인"),
            magazineElement("span", "", point.summary), magazineElement("i", "", "발언 확인"));
          rows.append(button);
        }
        for (const taskId of topic.task_ids || []) {
          const task = openTasks.find((task) => task.id === taskId);
          if (!task) continue;
          const button = meetingEvidenceButton(item, "task", task.id, "", task.title);
          button.classList.add("meeting-topic-task-detail", "meeting-summary-task");
          const copy = magazineElement("span", "meeting-topic-task-copy", "");
          copy.append(officialTextElement("span", "", task.title, task, "title"), meetingTaskOwnerTags(task));
          button.append(magazineElement("strong", "", "과제"), copy, magazineElement("i", "", "원문 보기"));
          rows.append(button);
        }
        if (rows.children.length) card.append(rows);
        section.append(card);
      }
      summarySection.append(section);
    }
    if (!summaryTopics.length) summarySection.append(magazineElement("p", "meeting-result-empty",
      "AI 주요 논의 요약 생성 대기 중입니다. 세부 쟁점과 근거 원문은 아래에서 확인할 수 있습니다."));
    structureContainer = magazineElement("details", "meeting-structure-appendix", "");
    structureContainer.append(magazineElement("summary", "", "세부 쟁점·과제 연결 및 근거 원문"));
    topics.append(summarySection, structureContainer);
  }
  if (!brief.topics?.length) {
    topics.append(magazineElement("p", "meeting-result-empty", "근거가 확인된 주요 주제가 없습니다."));
  }
  for (const group of topicGroups) {
    const groupSection = magazineElement("details", "meeting-topic-group", "");
    groupSection.id = "meeting-topic-group-" + group.id;
    groupSection.tabIndex = -1;
    groupSection.open = false;
    const groupHead = magazineElement("summary", "meeting-topic-group-head", "");
    groupHead.append(
      magazineElement("span", "", "대상 주제"),
      magazineElement("h4", "", group.title),
      magazineElement("p", "", group.summary || ""),
      magazineElement(
        "small", "",
        `세부 쟁점 ${group.topic_ids.length.toLocaleString("ko-KR")}개`,
      ),
    );
    groupSection.append(groupHead);
    for (const topicId of group.topic_ids) {
      const topic = topicById.get(topicId);
      if (!topic) continue;
    const card = magazineElement("article", "meeting-result-topic", "");
    card.id = "meeting-topic-detail-" + topic.id;
    card.tabIndex = -1;
    const head = magazineElement("div", "meeting-result-topic-head", "");
    head.append(
      magazineElement("div", "", ""),
      meetingEvidenceButton(item, "topic", topic.id, "근거 발언 " + (topic.evidence_ids?.length || 0) + "개", topic.title),
    );
    head.firstElementChild.append(
      officialTextElement("h4", "", topic.title, topic, "title"),
      officialTextElement("p", "", topic.summary, topic, "summary"),
    );
    if (topic.coverage_origin === "LIVE_TOPIC_SUPPLEMENT") head.firstElementChild.append(
      magazineElement("small", "provisional-label", "실시간 근거 복원 · 잠정 · 공식 대조 필요"),
    );
    if (topic.coverage_origin === "EVIDENCE_STRUCTURE") head.firstElementChild.append(
      magazineElement("small", "provisional-label", "원문 기반 세부 분류 · AI 잠정"),
    );
    const topicLineageClusters = (topic.live_topic_cluster_ids || [])
      .map((clusterId) => liveTopicClusterById.get(clusterId))
      .filter(Boolean);
    let topicLineageDetails = null;
    if (topicLineageClusters.length) {
      topicLineageDetails = magazineElement("details", "meeting-topic-lineage", "");
      topicLineageDetails.append(magazineElement(
        "summary", "",
        `실시간 주제 ${topicLineageClusters.length.toLocaleString("ko-KR")}묶음 통합 내역`,
      ));
      const lineageList = magazineElement("ul", "", "");
      for (const cluster of topicLineageClusters) {
        const row = magazineElement("li", "", "");
        const status = cluster.mapping_status === "STRUCTURED_MULTI_ISSUE" ? "세부 쟁점 분리"
          : cluster.mapping_status === "STRUCTURED_EVIDENCE" ? "원문 근거 연결"
          : cluster.mapping_status === "REVIEW_REQUIRED"
          ? (structure?.automatic_review?.status === "COMPLETED" ? "주제 연결·불명확 원문 별도 보존" : "부분 연결·자동 검토 중")
          : cluster.mapping_status === "MULTIPLE_FINAL_TOPICS"
          ? "교차 주제" : cluster.mapping_status === "DIRECT_EVIDENCE"
            ? "근거 직접 연결" : cluster.mapping_status === "SUPPLEMENTARY_EVIDENCE"
              ? "누락 쟁점 근거 복원" : "유사 주제 연결";
        const evidenceButton = magazineElement("button", "", "");
        evidenceButton.type = "button";
        evidenceButton.append(
          magazineElement("strong", "", cluster.title || "제목 확인 필요"),
          magazineElement(
            "small", "",
            `${status} · 발언 ${Number(cluster.utterance_count || 0).toLocaleString("ko-KR")}묶음 · 표현 ${Number(cluster.aliases?.length || 1).toLocaleString("ko-KR")}종`,
          ),
        );
        evidenceButton.addEventListener("click", () => openMeetingBriefEvidence(
          item, "live_topic_cluster", cluster.id, cluster.title || topic.title,
        ));
        row.append(evidenceButton);
        lineageList.append(row);
      }
      topicLineageDetails.append(lineageList);
    }
    const speakerList = magazineElement("div", "meeting-speaker-points", "");
    const sourceQuotes = magazineElement("details", "meeting-source-quotes", "");
    const sourceQuoteList = magazineElement("div", "meeting-speaker-points", "");
    for (const point of topic.speaker_points || []) {
      const pointRow = meetingEvidenceButton(item, "speaker", point.id, "", topic.title + " · " + point.speaker_label);
      pointRow.append(
        magazineElement("strong", "", point.speaker_label || "화자 미확인"),
        magazineElement("span", "", point.summary),
        magazineElement("i", "", "발언 확인"),
      );
      const isSourceQuote = topic.coverage_origin === "EVIDENCE_STRUCTURE"
        || point.summary_kind === "SOURCE_QUOTE"
        || point.summary_verification === "OFFICIAL_SOURCE_EXCERPT";
      (isSourceQuote ? sourceQuoteList : speakerList).append(pointRow);
    }
    if (sourceQuoteList.children.length) {
      sourceQuotes.append(magazineElement("summary", "",
        `근거 발언 원문 ${sourceQuoteList.children.length}건 보기`), sourceQuoteList);
      speakerList.append(sourceQuotes);
    }
    if (briefView === "official" && topic.draft_only_speaker_points?.length) {
      const draftDetails = magazineElement("details", "meeting-draft-only-speakers", "");
      draftDetails.append(magazineElement(
        "summary", "",
        `초안 전용 · 공식 발언 연결 미확인 ${topic.draft_only_speaker_points.length}개`,
      ));
      for (const point of topic.draft_only_speaker_points) {
        const pointRow = meetingEvidenceButton(
          item, "speaker", point.id, "", topic.title + " · 초안 전용",
        );
        pointRow.append(
          magazineElement("strong", "", "화자 미확인 · 초안"),
          magazineElement("span", "", point.summary || "초안 내용 확인 필요"),
          magazineElement("i", "", "LIVE 근거 보기"),
        );
        draftDetails.append(pointRow);
      }
      speakerList.append(draftDetails);
    }
    const topicTasks = openTasks.filter((task) => (task.related_topic_ids || []).includes(topic.id)
      || (task.topic_id ? task.topic_id === topic.id : task.topic_title === topic.title));
    for (const task of topicTasks) {
      const taskRow = meetingEvidenceButton(item, "task", task.id, "", task.title);
      taskRow.classList.add("meeting-topic-task-detail");
      const taskCopy = magazineElement("span", "meeting-topic-task-copy", "");
      taskCopy.append(
        officialTextElement("span", "", task.title, task, "title"),
        meetingTaskOwnerTags(task),
      );
      const directSpan = (task.task_evidence_spans || []).find((span) => (span.topic_ids || []).includes(topic.id))
        || (task.request_spans || []).find((span) => (span.related_topic_ids || []).includes(topic.id));
      if (directSpan) taskCopy.append(magazineElement("small", "meeting-task-direct-quote", `직접 언급 · ${directSpan.quote}`));
      else if (task.topic_link_method === "SOURCE_SPAN_REVIEW") taskCopy.append(magazineElement("small", "meeting-task-direct-quote", "직접 언급 구간 확인 필요"));
      taskRow.append(
        magazineElement("strong", "", "과제"),
        taskCopy,
        magazineElement("i", "", "원문 보기"),
      );
      speakerList.append(taskRow);
    }
    card.append(head);
    if (topicLineageDetails) card.append(topicLineageDetails);
    card.append(speakerList);
      groupSection.append(card);
    }
    structureContainer.append(groupSection);
  }

  const evidence = magazineElement("aside", "meeting-evidence-panel", "");
  evidence.id = "meetingBriefEvidence";
  renderEvidencePlaceholder(evidence);
  workspace.append(topics, evidence);
  sourceView.append(topicTaskOverview);
  if (briefView === "official") sourceView.append(renderOfficialUtteranceBrowser(item));
  if (lineageUnmappedPanel) sourceView.append(lineageUnmappedPanel);
  if (structure && brief.structure_review_items?.length) {
    const categories = [
      ["AUTO_PENDING", "자동 재분류 대기", "시스템이 앞뒤 발언을 함께 분석하여 주제와 발언 역할을 다시 분류합니다."],
      ["ANALYSIS_FAILED", "분석 지연", "모델 통신 오류로 분석되지 않은 원문입니다. 시스템이 제한된 횟수로 자동 재시도합니다."],
      ["SOURCE_LIMITED", "재분석 후 원문 불명확", "문맥을 포함해 재분석했으나 대상을 특정할 근거가 부족한 발언입니다."],
      ["REQUEST_SOURCE_LIMITED", "주제 특정이 어려운 자료 요구", "자료 요구는 보존했으며, 문맥 재분석 후에도 제출 대상을 특정 주제에 연결할 근거가 부족한 항목입니다."],
      ["PROCEDURAL", "회의 진행·의례 원문", "정책 주제가 아닌 발언 순서 안내, 인사, 단순 호응 등입니다."],
    ];
    for (const [state, title, description] of categories) {
      const entries = brief.structure_review_items.filter((entry) =>
        (entry.review_state || (entry.role === "PROCEDURE" ? "PROCEDURAL" : "AUTO_PENDING")) === state);
      if (!entries.length) continue;
      const review = magazineElement("details", "meeting-lineage-unmapped", "");
      review.append(magazineElement("summary", "", `${title} ${entries.length}건`), magazineElement("p", "", description));
      for (const entry of entries) {
        const button = meetingEvidenceButton(item, "structure_review", entry.id, "", `${title} · ${entry.title}`);
        button.append(magazineElement("strong", "", entry.title), magazineElement("p", "", entry.summary));
        if (entry.reason && ["SOURCE_LIMITED", "REQUEST_SOURCE_LIMITED", "AUTO_PENDING"].includes(state)) button.append(magazineElement("small", "", entry.reason));
        review.append(button);
      }
      sourceView.append(review);
    }
  }
  sourceView.append(actions, workspace);
  root.append(hero, integrationBar);
  if (officialChangeReport) root.append(officialChangeReport);
  root.append(sourceView);
  stage.append(root);
  limitMeetingOverviewRows(topicTaskOverviewList, MEETING_OVERVIEW_VISIBLE_ROWS);

  const focusTopic = briefView === "structured" && topicById.get(record._focus_topic_id);
  if (options.evidence) {
    openMeetingBriefEvidence(item, options.evidence.type, options.evidence.id, options.evidence.title);
  } else if (focusTopic) {
    const card = document.getElementById("meeting-topic-detail-" + focusTopic.id);
    if (card) {
      for (let parent = card.parentElement; parent; parent = parent.parentElement) {
        if (parent.tagName === "DETAILS") parent.open = true;
      }
      card.scrollIntoView({ block: "start" });
    }
    openMeetingBriefEvidence(item, "topic", focusTopic.id, focusTopic.title);
  } else {
    // 첫 묶음의 전체 근거를 선택하되 보고서의 스크롤 위치는 이동하지 않는다.
    root.querySelector(".meeting-summary-topic .meeting-result-topic-head .meeting-evidence-button")?.click();
  }
}

function renderOfficialUtteranceBrowser(item) {
  const section = magazineElement("details", "meeting-official-utterances", "");
  section.append(magazineElement("summary", "", "공식 회의록 전체 발언 · 화자별 원문 보기"));
  const search = document.createElement("input");
  search.type = "search";
  search.placeholder = "화자 이름 또는 발언 검색";
  search.setAttribute("aria-label", "공식 발언 검색");
  const list = magazineElement("div", "meeting-official-utterance-list", "");
  const more = magazineElement("button", "", "다음 발언 보기");
  more.type = "button";
  more.hidden = true;
  let nextOffset = 0;
  let loaded = false;
  let busy = false;
  let requestNumber = 0;
  async function loadPage(reset = false) {
    if (busy && !reset) return;
    if (reset) {
      requestNumber += 1;
      nextOffset = 0;
      list.replaceChildren();
      more.hidden = true;
    }
    const currentRequest = requestNumber;
    busy = true;
    const params = new URLSearchParams({
      offset: String(nextOffset), limit: "30", q: search.value.trim(),
    });
    try {
      const response = await fetch(
        `api/live/broadcasts/${encodeURIComponent(item.broadcast_id)}/official-utterances?${params}`,
        { cache: "no-store" },
      );
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      if (currentRequest !== requestNumber) return;
      for (const speech of payload.items || []) {
        const row = magazineElement("details", "meeting-official-utterance", "");
        row.append(
          magazineElement("summary", "", `${speech.sequence_number} · ${speech.speaker_name || "화자 미기재"}${speech.speaker_role ? ` · ${speech.speaker_role}` : ""}`),
          magazineElement("p", "", speech.text || "원문 없음"),
        );
        list.append(row);
      }
      if (!list.children.length) list.append(magazineElement("p", "", "검색 결과가 없습니다."));
      nextOffset = Number(payload.next_offset || 0);
      more.hidden = !payload.has_more;
    } catch (error) {
      if (currentRequest === requestNumber) list.append(magazineElement("p", "meeting-result-empty", error.message));
    } finally {
      if (currentRequest === requestNumber) busy = false;
    }
  }
  section.addEventListener("toggle", () => {
    if (section.open && !loaded) {
      loaded = true;
      loadPage(true);
    }
  });
  search.addEventListener("change", () => loadPage(true));
  more.addEventListener("click", () => loadPage());
  section.append(search, list, more);
  return section;
}

async function openMeetingBriefEvidence(item, entityType, entityId, title) {
  const panel = document.querySelector("#meetingBriefEvidence");
  if (!panel) return;
  const requestToken = Symbol("meeting-evidence");
  panel.evidenceRequestToken = requestToken;
  const isCurrentRequest = () => panel.isConnected && panel.evidenceRequestToken === requestToken;
  setMeetingEvidenceSelection(entityType, entityId);
  panel.replaceChildren(
    magazineElement("header", "", title),
    magazineElement("p", "meeting-evidence-loading", "연결된 근거 발언을 불러오는 중입니다."),
  );
  try {
    const params = new URLSearchParams({ entity_type: entityType, entity_id: entityId });
    const response = await fetch(
      "api/live/broadcasts/" + encodeURIComponent(item.broadcast_id) + "/brief/evidence?" + params,
      { cache: "no-store" },
    );
    const payload = await response.json();
    if (!isCurrentRequest()) return;
    if (!response.ok) throw new Error(payload.detail || "HTTP " + response.status);
    panel.replaceChildren();
    const head = magazineElement("header", "", "");
    const close = magazineElement("button", "", "선택 해제");
    close.type = "button";
    close.addEventListener("click", () => {
      panel.evidenceRequestToken = null;
      setMeetingEvidenceSelection("", "");
      renderEvidencePlaceholder(panel);
    });
    head.append(magazineElement("div", "", ""), close);
    const officialPresentation = payload.source === "OFFICIAL_TRANSCRIPT_PRESENTATION";
    const publicationLabel = payload.publication_stage === "FINAL"
      ? "공식 최종본"
      : payload.publication_stage === "TEMPORARY" ? "임시회의록 반영" : "공식 회의록";
    const changedCount = (payload.items || []).reduce(
      (total, utterance) => total + Number(utterance.change_count || 0), 0,
    );
    head.firstElementChild.append(
      magazineElement(
        "span", "",
        officialPresentation
          ? `발언 확인 · ${publicationLabel}`
          : payload.source === "LIVE_STRUCTURE_SNAPSHOT"
            ? "발언 확인 · 구조화 시점의 LIVE 저장본" : "발언 확인 · LIVE 저장본",
      ),
      magazineElement("strong", "", title),
      magazineElement(
        "small", "",
        officialPresentation
          ? `${payload.count}개 공식 발언 · LIVE 대비 수정 문구 ${changedCount}곳`
          : entityType === "task"
            ? payload.count + "개 발언 묶음 · " + ((payload.direct_task_spans || []).length ? "과제 직접 언급 구간 표시" : "과제 직접 언급 구간 확인 필요")
            : payload.count + "개 발언 묶음 · 핵심 문구 최대 3개를 표시합니다",
      ),
    );
    panel.append(head);
    const evidenceItems = payload.items || [];
    const highlightPlan = entityType === "task"
      ? new Map(evidenceItems.flatMap((utterance, index) => {
        const span = (payload.direct_task_spans || []).find((value) => value.evidence_id === utterance.utterance_id);
        if (!span) return [];
        const characters = Array.from(utterance.text || "");
        if (characters.slice(span.start, span.end).join("") !== span.quote) return [];
        return [[index, {start:characters.slice(0, span.start).join("").length,
          end:characters.slice(0, span.end).join("").length}]];
      }))
      : selectMeetingEvidenceHighlights(evidenceItems, title);
    if (!evidenceItems.length) {
      panel.append(magazineElement("p", "meeting-result-empty", "이 주제에 연결된 발언을 다시 대조하고 있습니다."));
      return;
    }
    for (const [utteranceIndex, utterance] of evidenceItems.entries()) {
      const official = utterance.source === "OFFICIAL_TRANSCRIPT_UTTERANCE";
      const row = magazineElement(
        "article",
        `meeting-evidence-utterance${official ? " is-official" : ""}`,
        "",
      );
      const speaker = magazineElement("div", "meeting-evidence-speaker", "");
      const sourceLabel = official
        ? utterance.publication_stage === "FINAL"
          ? "공식 최종본"
          : "임시회의록"
        : (utterance.segment_count || 1) + "개 자막 연결";
      speaker.append(
        magazineElement("strong", "", utterance.speaker_label || "화자 미확인"),
        magazineElement(
          "small", "",
          [utterance.speaker_role, sourceLabel].filter(Boolean).join(" · "),
        ),
      );
      const transcript = magazineElement("p", "meeting-evidence-transcript", "");
      if (official) {
        const importantRange = highlightPlan.get(utteranceIndex);
        if (Number(utterance.change_count || 0) > 0) {
          appendOfficialInlineDiff(
            transcript, utterance.text, utterance.diff_spans,
          );
        } else {
          appendHighlightedPhrase(transcript, utterance.text, importantRange);
        }
      } else {
        appendHighlightedPhrase(
          transcript, utterance.text, highlightPlan.get(utteranceIndex),
        );
      }
      row.append(speaker, transcript);
      if (official && utterance.comparison_status === "LOW_CONFIDENCE") {
        row.append(magazineElement(
          "small", "meeting-evidence-compare-note",
          "공식 문장을 반영했습니다 · LIVE 자막과 문장 구조 차이가 커 세부 변경 표시는 생략합니다.",
        ));
      } else if (official && Number(utterance.change_count || 0) > 0) {
        row.append(magazineElement(
          "small", "meeting-evidence-compare-note",
          "색상 문구에 마우스를 올리거나 키보드로 선택하면 기존 LIVE 자막 문구를 확인할 수 있습니다.",
        ));
      }
      const liveOnly = Array.isArray(utterance.live_only_fragments)
        ? utterance.live_only_fragments.filter(Boolean) : [];
      if (official && liveOnly.length) {
        const disclosure = magazineElement(
          "details", "meeting-evidence-live-only", "",
        );
        disclosure.append(magazineElement(
          "summary", "", `LIVE에만 기록된 문구 ${liveOnly.length.toLocaleString("ko-KR")}곳`,
        ));
        for (const fragment of liveOnly) {
          disclosure.append(magazineElement("p", "", fragment));
        }
        row.append(disclosure);
      }
      panel.append(row);
    }
  } catch (error) {
    if (!isCurrentRequest()) return;
    panel.replaceChildren(
      magazineElement("header", "", title),
      magazineElement("p", "meeting-result-empty", error.message),
    );
  }
}

function meetingReportLoadingVisual(label) {
  const visual = magazineElement("div", "meeting-report-loader", "");
  visual.setAttribute("role", "img");
  visual.setAttribute("aria-label", label);
  const sheet = magazineElement("div", "meeting-report-loader-sheet", "");
  sheet.append(
    magazineElement("b", "", ""),
    magazineElement("i", "", ""),
    magazineElement("i", "", ""),
    magazineElement("i", "", ""),
    magazineElement("i", "", ""),
  );
  visual.append(sheet, magazineElement("span", "meeting-report-loader-scan", ""));
  return visual;
}

function meetingBriefProgressTag(item) {
  const progress = item.brief_progress || item.meeting_brief?.brief_progress || {};
  const total = Number(progress.total_chunks);
  const done = Number(progress.completed_chunks);
  const valid = Number.isInteger(total) && total > 0 && Number.isInteger(done) && done >= 0
    && progress.status !== "COMPLETED";
  const count = valid ? `${Math.min(done, total)}/${total}` : "";
  const waiting = ["DEFERRED", "FAILED"].includes(progress.status);
  const validationPhase = {STRUCTURING: "주제 검증중", REVIEWING: "발언 재검토중", ONTOLOGY: "정책 분류중", NARRATIVE: "세부 요약중", FINALIZING: "최종 검증중"}[progress.phase];
  if (validationPhase) return {label: waiting ? "검증 재시도 대기" : validationPhase, tone: "processing",
    title: "요약 초안은 열람할 수 있습니다. 원문 연결과 정책 분류·세부 요약을 확인한 뒤 완료됩니다."};
  const phase = waiting ? "재시도 대기"
    : progress.phase === "CONSOLIDATING" ? "쟁점 통합중"
    : progress.phase === "SYNTHESIZING" ? "최종 통합중"
    : progress.phase === "REDUCING" ? "주제 통합중" : "정리중";
  const unit = progress.phase === "REDUCING" ? "주제 통합 묶음" : "발언 분석 구간";
  return { label: count ? `${phase} ${count}` : phase, tone: "processing",
    title: count ? `${unit} ${count} 완료 · ${phase}. 전체 보고서 완료율과는 다릅니다.` : `${phase}입니다.` };
}

function structuredLineageSummary(brief) {
  const clusters = brief.live_topic_lineage?.clusters || [];
  const linked = clusters.filter(c => c.final_topic_ids?.length).length;
  const partial = clusters.filter(c => c.final_topic_ids?.length && c.review_evidence_ids?.length).length;
  const unlinked = clusters.filter(c => !c.final_topic_ids?.length && c.mapping_status !== "PROCEDURAL").length;
  const meta = brief.topic_structure || {};
  const pending = Number(meta.automatic_review?.pending_atom_count || 0);
  const saved = new Set((meta.uncertain || []).map(f => f.atom_id)).size;
  return `${clusters.length}묶음 중 ${linked}묶음에 주제가 연결되어 있습니다.`
    + (partial ? ` 이 중 ${partial}묶음에는 별도로 보존한 불명확 원문이 포함되어 있습니다.` : "")
    + (unlinked ? ` 주제 미연결 ${unlinked}묶음.` : "")
    + (saved ? ` 불명확 원문 ${saved}건은 근거에서 확인할 수 있습니다.` : "")
    + (pending ? ` 자동 재분류 대상 ${pending}건을 처리하고 있습니다.` : "");
}

function meetingBriefStageTags(item) {
  const record = item.meeting_brief || item;
  const progress = item.brief_progress || record.brief_progress || {};
  const finalization = item.brief_finalization || record.brief_finalization || {};
  const ready = item.brief_status === "READY" || record.brief_status === "READY";
  if (finalization.status === "COMPLETED" || (ready && !finalization.status)) {
    return [{label: "비공식 정리 완료", tone: "provisional"}];
  }
  const definitions = [
    ["ANALYZING", "발언 분석"], ["INTEGRATION", "통합"], ["REVIEWING", "주제 검증"],
    ["ONTOLOGY", "정책 분류"], ["NARRATIVE", "세부 요약"], ["FINALIZING", "최종 확인"],
  ];
  let stages = progress.stages || finalization.stages;
  if (!stages?.length) {
    const phase = finalization.phase || progress.phase;
    const currentKey = ["REDUCING", "SYNTHESIZING", "STRUCTURING", "CONSOLIDATING"].includes(phase)
      ? "INTEGRATION" : phase;
    const position = Math.max(0, definitions.findIndex(([key]) => key === currentKey));
    stages = definitions.map(([key], index) => ({key, status: index < position ? "COMPLETED"
      : index > position || phase === "QUEUED" ? "PENDING"
      : ["DEFERRED", "FAILED"].includes(progress.status) ? "WAITING" : "PROCESSING"}));
    const countStage = ["ANALYZING", "REDUCING", "CONSOLIDATING"].includes(phase) ? stages[position] : null;
    if (countStage && Number(progress.total_chunks) > 0) {
      Object.assign(countStage, {completed: progress.completed_chunks, total: progress.total_chunks, unit: "묶음"});
    }
  }
  return stages.map(stage => {
    const name = definitions.find(([key]) => key === stage.key)?.[1] || "정리";
    const done = Number(stage.completed), total = Number(stage.total);
    const count = stage.completed != null && stage.total != null && Number.isInteger(done)
      && Number.isInteger(total) && total > 0 && done >= 0 ? ` (${Math.min(done, total)}/${total})` : "";
    const complete = stage.status === "COMPLETED", future = stage.status === "PENDING";
    const waiting = stage.status === "WAITING";
    const suffix = complete ? " 완료" : future ? " 대기" : waiting ? " 재시도 대기" : " 중";
    let title = `${name}${suffix}${count}${stage.unit ? ` · ${stage.unit} 기준` : ""}. 숫자는 검증을 통과해 저장된 완료 수/현재 전체 대상 수입니다. 추가 대상이 발견되면 총수가 바뀔 수 있습니다.`;
    const retryAt = progress.retry_after || finalization.retry_after;
    if (waiting && retryAt && !Number.isNaN(new Date(retryAt).valueOf())) {
      title += ` 다음 재시도 가능 시각: ${new Date(retryAt).toLocaleString("ko-KR")}`;
    }
    return {label: `${name}${suffix}${complete || future ? "" : count}`,
      tone: complete ? "stage-done" : future ? "stage-pending" : waiting ? "stage-waiting" : "processing", title};
  });
}

function renderMeetingBriefProcessing(item, progress = item.brief_progress || {}, record = item.meeting_brief) {
  const stage = document.querySelector("#liveExpandedStage");
  if (!stage) return;
  const brief = record?.brief || {};
  const total = Math.max(
    Number(progress.total_utterances || 0),
    Number(brief.utterance_count || 0),
    Number(item.utterance_count || 0),
  );
  const completed = Math.min(total, Number(progress.processed_utterances || 0));
  const percent = total ? Math.round(completed / total * 100) : 0;
  const phaseLabel = progress.status === "DEFERRED" || progress.status === "FAILED"
    ? "재시도 대기 중"
    : ["REDUCING", "SYNTHESIZING"].includes(progress.phase) ? "전체 주제 통합 중" : "발언별 주제 분석 중";
  const phaseDetail = "완료되면 자동으로 결과를 표시합니다.";
  const previousTotal = Number(record?.previous_utterance_count || 0);
  const staleCopy = record?.brief_is_stale && previousTotal
    ? `이전 보고서는 ${previousTotal.toLocaleString("ko-KR")}개 발언 기준입니다. 새로 확인된 ${Math.max(0, total - previousTotal).toLocaleString("ko-KR")}개 발언을 포함해 다시 정리합니다.`
    : "회의에서 논의된 주제와 도출 과제를 발언 근거에 연결하고 있습니다.";
  const root = magazineElement("section", "meeting-brief-view meeting-brief-processing", "");
  root.setAttribute("aria-busy", "true");
  const preview = magazineElement("div", "meeting-processing-preview", "");
  preview.setAttribute("aria-hidden", "true");
  const hero = magazineElement("header", "meeting-brief-hero", "");
  const identity = magazineElement("div", "", "");
  identity.append(
    magazineElement("span", "provisional-label", "AI 요약 · 잠정"),
    magazineElement("h3", "", item.title || item.committee_name || "회의 결과"),
    magazineElement("p", "", staleCopy),
  );
  const stages = magazineElement("div", "meeting-stage-tags", "");
  stages.setAttribute("aria-label", "비공식 정리 단계별 진행 현황");
  for (const tag of meetingBriefStageTags({...item, brief_progress: progress, meeting_brief: record})) {
    const badge = magazineElement("span", `meeting-card-tag is-${tag.tone}`, tag.label);
    badge.title = tag.title || tag.label;
    stages.append(badge);
  }
  identity.append(stages);
  const metrics = magazineElement("dl", "meeting-brief-metrics", "");
  for (const [label, value] of [["수집 발언", total], ["정리 완료", completed], ["진행률", `${percent}%`]]) {
    const metric = document.createElement("div");
    metric.append(magazineElement("dt", "", label), magazineElement("dd", "", String(value)));
    metrics.append(metric);
  }
  hero.append(identity, metrics);
  const integrationBar = meetingIntegrationBar(item, record);
  const sourceView = magazineElement("div", "meeting-source-view", "");
  const processingArea = magazineElement("section", "meeting-topic-task-overview meeting-topic-task-processing", "");
  const processingHead = magazineElement("header", "", "");
  processingHead.append(
    magazineElement("strong", "", "요약된 논의 주제"),
    magazineElement("strong", "", "도출 과제"),
  );
  processingArea.append(processingHead);
  for (const width of ["92%", "74%", "86%", "64%", "81%", "70%"]) {
    const line = magazineElement("i", "", "");
    line.style.width = width;
    preview.append(line);
  }
  const overlay = magazineElement("div", "meeting-processing-overlay", "");
  overlay.setAttribute("role", "status");
  overlay.setAttribute("aria-live", "polite");
  const progressTrack = magazineElement("div", "meeting-processing-progress", "");
  const progressFill = magazineElement("i", "", "");
  progressFill.style.width = `${percent}%`;
  progressTrack.append(progressFill);
  const loadingCard = magazineElement("div", "meeting-processing-card", "");
  loadingCard.append(
    meetingReportLoadingVisual("회의 발언과 주제 관계를 분석하고 있습니다"),
    magazineElement("span", "", "방송 종료 · LIVE 저장본 분석"),
    magazineElement("strong", "", "결과 정리 중"),
    magazineElement("p", "meeting-processing-count", total ? `전체 ${total.toLocaleString("ko-KR")}개 발언 중 ${completed.toLocaleString("ko-KR")}개 정리 완료` : "저장된 발언 수를 확인하고 있습니다."),
    progressTrack,
    magazineElement("small", "", `${phaseLabel} · ${phaseDetail}`),
  );
  const processingBody = magazineElement("div", "meeting-processing-body", "");
  processingBody.append(preview, overlay);
  overlay.append(loadingCard);
  processingArea.append(processingBody);
  const actions = magazineElement("div", "meeting-beta-actions", "");
  const fullTranscript = magazineElement("button", "", "전체 발언 기록 보기");
  fullTranscript.type = "button";
  fullTranscript.addEventListener("click", () => {
    const selectedRow = document.querySelector('.broadcast-row[data-broadcast-id="' + item.broadcast_id + '"]');
    expandEndedBroadcast(item, selectedRow || fullTranscript);
  });
  actions.append(
    magazineElement("small", "", "주제·과제 정리 중에도 저장된 전체 발언은 확인할 수 있습니다."),
    fullTranscript,
  );
  sourceView.append(processingArea, actions);
  root.append(hero, integrationBar, sourceView);
  stage.replaceChildren(root);
}

function meetingBriefIsReady(record) {
  if (!record) return false;
  if (record.brief_status) return record.brief_status === "READY";
  return record.provider === "mistral";
}

function meetingBriefVersion(item) {
  const record = item?.meeting_brief || {};
  return [
    record.brief_id || "",
    record.generated_at || "",
    record.brief_status || item?.brief_status || "",
    item?.official_integration_updated_at || "",
  ].join("|");
}

function cachedMeetingBrief(item) {
  const key = String(item?.broadcast_id || "");
  const cached = meetingBriefCache.get(key);
  if (!cached || cached.version !== meetingBriefVersion(item) || Date.now() - cached.fetchedAt >= 60000) return null;
  return cached.payload;
}

function rememberMeetingBrief(item, payload) {
  const key = String(item?.broadcast_id || "");
  if (!key || !payload) return;
  meetingBriefCache.delete(key);
  meetingBriefCache.set(key, { version: meetingBriefVersion(item), payload, fetchedAt: Date.now() });
  while (meetingBriefCache.size > MEETING_BRIEF_CACHE_LIMIT) {
    meetingBriefCache.delete(meetingBriefCache.keys().next().value);
  }
}

function renderMeetingBriefLoading(item) {
  const stage = document.querySelector("#liveExpandedStage");
  if (!stage) return;
  const root = magazineElement("section", "meeting-brief-view", "");
  root.setAttribute("aria-busy", "true");
  const loading = magazineElement("div", "meeting-brief-loading", "");
  const copy = magazineElement("div", "", "");
  copy.append(
    magazineElement("small", "meeting-brief-loading-kicker", "REPORT DATA PIPELINE · ACTIVE"),
    magazineElement("strong", "", "회의 보고서를 불러오는 중입니다"),
    magazineElement(
      "p", "",
      `${item.title || item.committee_name || "선택한 회의"}의 주제와 근거 발언을 준비하고 있습니다.`,
    ),
    magazineElement("span", "meeting-brief-loading-status", "저장본 확인 · 근거 연결 · 화면 구성"),
  );
  loading.append(meetingReportLoadingVisual("저장된 회의 보고서를 구성하고 있습니다"), copy);
  root.append(loading);
  stage.replaceChildren(root);
}

function requestMeetingBrief(item, options = {}) {
  const key = String(item?.broadcast_id || "");
  const cached = cachedMeetingBrief(item);
  if (cached && options.force !== true) return Promise.resolve(cached);
  if (meetingBriefRequests.has(key)) return meetingBriefRequests.get(key);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 20000);
  const request = fetch(
    `api/live/broadcasts/${encodeURIComponent(key)}/brief`,
    { cache: "no-store", signal: controller.signal },
  ).then(async (response) => {
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
    rememberMeetingBrief(item, payload);
    return payload;
  }).finally(() => {
    window.clearTimeout(timeout);
    meetingBriefRequests.delete(key);
  });
  meetingBriefRequests.set(key, request);
  return request;
}

function renderMeetingBriefLoadError(retry, preserveReport = false) {
  const stage = document.querySelector("#liveExpandedStage");
  if (!stage) return;
  stage.querySelector(".meeting-brief-load-error")?.remove();
  const notice = magazineElement("section", "meeting-brief-view meeting-brief-load-error", "");
  notice.setAttribute("role", "alert");
  notice.append(
    magazineElement("strong", "", "회의 보고서를 불러오지 못했습니다"),
    magazineElement("p", "", preserveReport
      ? "최신 내용을 확인하지 못했습니다. 아래에는 앞서 불러온 보고서를 유지합니다."
      : "응답이 지연되거나 연결에 문제가 있습니다. 다시 시도해 주세요."),
  );
  const button = magazineElement("button", "meeting-evidence-button", "다시 불러오기");
  button.type = "button";
  button.addEventListener("click", retry, { once: true });
  notice.append(button);
  if (preserveReport) stage.prepend(notice);
  else stage.replaceChildren(notice);
}

function prefetchMeetingBriefs(items) {
  const preferredId = String(latestMeetingReportState.preferredId || "");
  const candidates = (items || [])
    .filter((item) => meetingBriefIsReady(item.meeting_brief))
    .sort((left, right) => (
      Number(String(right.broadcast_id) === preferredId)
      - Number(String(left.broadcast_id) === preferredId)
    ));
  for (const item of candidates.slice(0, 2)) {
    if (item.meeting_brief?.brief_content_loaded || cachedMeetingBrief(item)) continue;
    requestMeetingBrief(item).catch(() => {});
  }
}

function meetingBriefRenderSignature(record) {
  const content = (value) => {
    if (!value) return null;
    const {finalization, ...body} = value;
    return body;
  };
  return JSON.stringify([
    record?.brief_status, record?.brief_finalization?.status, record?.brief_finalization?.phase,
    record?.brief_progress?.stages,
    content(record?.brief), content(record?.structured_brief), content(record?.official_brief),
    record?.official_integration, record?.official_change_report, record?.structure_progress,
  ]);
}

function expandMeetingBrief(item, row, options = {}) {
  stopAssemblyTranscript();
  const requestGeneration = assemblyTranscriptState.generation;
  rememberMeetingReportSelection(item.broadcast_id);
  assemblyTranscriptState.expanded = true;
  assemblyTranscriptState.expandedMode = "BRIEF";
  assemblyTranscriptState.selectedBroadcastId = item.broadcast_id;
  document.querySelector("#liveExpanded").hidden = false;
  document.querySelector("#liveExpandedTitle").textContent = item.title || item.committee_name || "회의 결과";
  document.querySelectorAll(".broadcast-row").forEach((candidate) => candidate.removeAttribute("aria-current"));
  row?.setAttribute?.("aria-current", "true");
  let renderedRecord = null;
  let renderedSignature = null;
  const renderRecord = (record) => {
    document.querySelector(".meeting-brief-load-error")?.remove();
    const signature = meetingBriefRenderSignature(record);
    if (signature === renderedSignature) return;
    const scrollY = window.scrollY;
    renderMeetingBrief(item, record, options);
    if (renderedRecord) window.scrollTo({top: scrollY, behavior: "instant"});
    renderedRecord = record;
    renderedSignature = signature;
  };
  const cached = cachedMeetingBrief(item);
  const visibleRecord = cached || item.meeting_brief;
  if (visibleRecord?.brief_content_loaded) renderRecord(visibleRecord);
  else if (meetingBriefIsReady(visibleRecord)) renderMeetingBriefLoading(item);
  else renderMeetingBriefProcessing(item);
  const loadBrief = (force = false) => {
    const ready = requestMeetingBrief(item, { force });
    ready.then((record) => {
      if (
        assemblyTranscriptState.generation !== requestGeneration
        || assemblyTranscriptState.selectedBroadcastId !== item.broadcast_id
      ) return;
      if (assemblyTranscriptState.briefPollTimer) window.clearTimeout(assemblyTranscriptState.briefPollTimer);
      assemblyTranscriptState.briefPollTimer = null;
      item.meeting_brief = record;
      item.brief_progress = record.brief_progress || item.brief_progress || {};
      if (!meetingBriefIsReady(record)) {
        item.brief_status = "PROCESSING";
        if (record?.brief_content_loaded) renderRecord(record);
        else renderMeetingBriefProcessing(item, item.brief_progress, record);
        assemblyTranscriptState.briefPollTimer = window.setTimeout(() => loadBrief(true), 5000);
        return;
      }

      item.brief_status = "READY";
      renderRecord(record);
      if (["PENDING", "PROCESSING"].includes(record?.official_change_report?.status)) {
        assemblyTranscriptState.briefPollTimer = window.setTimeout(() => loadBrief(true), 5000);
      }
    }).catch(() => {
      if (
        assemblyTranscriptState.generation !== requestGeneration
        || assemblyTranscriptState.selectedBroadcastId !== item.broadcast_id
      ) return;
      if (assemblyTranscriptState.briefPollTimer) window.clearTimeout(assemblyTranscriptState.briefPollTimer);
      assemblyTranscriptState.briefPollTimer = null;
      renderMeetingBriefLoadError(() => {
        if (assemblyTranscriptState.generation !== requestGeneration
            || assemblyTranscriptState.selectedBroadcastId !== item.broadcast_id) return;
        document.querySelector(".meeting-brief-load-error")?.remove();
        if (!renderedRecord) renderMeetingBriefLoading(item);
        loadBrief(true);
      }, Boolean(renderedRecord));
    });
  };
  loadBrief();
}

function expandEndedBroadcast(item, row) {
  stopAssemblyTranscript();
  rememberMeetingReportSelection(item.broadcast_id);
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
      assemblyTranscriptState.meetingSessions = payload.meeting_sessions || [];
      const broadcast = payload.broadcasts?.[0] || item;
      renderOfficialContext(payload.official_context || broadcast);
      const segments = (payload.segments || []).map((segment) => ({
        ...broadcast,
        ...segment,
        official_status: payload.official_context?.official_status,
      }));
      applyTranscriptItems(segments, payload.utterances || []);
      renderSpeakerEditor(broadcast, payload.speaker_options?.[String(broadcast.broadcast_id)] || []);
      if (!segments.length) {
        const waiting = document.querySelector(".transcript-waiting");
        if (waiting) waiting.textContent = "저장된 자막이 없는 종료 방송입니다.";
      }
    })
    .catch(() => {
      const waiting = document.querySelector(".transcript-waiting");
      if (waiting) waiting.textContent = "종료 방송 기록을 불러오지 못했습니다.";
    });
}

function expandPostProcessingBroadcast(item, row) {
  clearLiveReportHandoff();
  stopAssemblyTranscript();
  assemblyTranscriptState.expanded = true;
  assemblyTranscriptState.expandedMode = "POST_PROCESSING";
  assemblyTranscriptState.selectedBroadcastId = item.broadcast_id;
  assemblyTranscriptState.broadcastId = String(item.broadcast_id || "");
  document.querySelector("#liveOperationsExpanded").hidden = false;
  document.querySelector("#liveOperationsExpandedTitle").textContent = item.title
    || item.committee_name || "종료 방송 기록";
  document.querySelectorAll(".broadcast-row").forEach((candidate) => candidate.removeAttribute("aria-current"));
  row?.setAttribute?.("aria-current", "true");
  renderTranscriptShell([item], "POST_PROCESSING");
  fetch(`api/live/broadcasts/${encodeURIComponent(item.broadcast_id)}/transcript`, { cache: "no-store" })
    .then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      if (String(assemblyTranscriptState.selectedBroadcastId || "") !== String(item.broadcast_id)) return;
      assemblyTranscriptState.meetingSessions = payload.meeting_sessions || [];
      const broadcast = payload.broadcasts?.[0] || item;
      const segments = (payload.segments || []).map((segment) => ({ ...broadcast, ...segment }));
      applyTranscriptItems(segments, payload.utterances || [], { detectTransition: false });
      if (!segments.length) {
        const waiting = document.querySelector("#liveOperationsExpanded .transcript-waiting");
        if (waiting) waiting.textContent = "저장된 자막이 없는 종료 방송입니다.";
      }
    })
    .catch((error) => {
      const waiting = document.querySelector("#liveOperationsExpanded .transcript-waiting");
      if (waiting) waiting.textContent = error.message || "종료 방송 기록을 불러오지 못했습니다.";
    });
  document.querySelector("#liveOperationsExpanded")?.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function applyTranscriptItems(items, preparedGroups = [], options = {}) {
  const previousActiveUtteranceId = assemblyTranscriptState.lastActiveUtteranceId;
  let activeSourceRevision = "";
  for (const item of items) {
    const parentId = String(item.source_parent_segment_id || "");
    const sourceRevision = parentId ? `${parentId}:${item.cursor}` : "";
    if (parentId && sourceRevision !== activeSourceRevision) {
      for (const [segmentId, existing] of assemblyTranscriptState.segments) {
        if (String(segmentId) === parentId
            || String(existing.source_parent_segment_id || "") === parentId) {
          assemblyTranscriptState.segments.delete(segmentId);
        }
      }
      activeSourceRevision = sourceRevision;
    } else if (!parentId) {
      activeSourceRevision = "";
    }
    assemblyTranscriptState.segments.set(item.segment_id, item);
  }
  for (const group of preparedGroups) {
    if (group.summary_kind === "AI_CACHED") {
      assemblyTranscriptState.cachedSummaries.set(group.utterance_id, {
        summary: group.summary,
        summary_kind: group.summary_kind,
        summary_model: group.summary_model,
        summary_provider: group.summary_provider,
        live_insight: group.live_insight,
      });
    }
  }
  // Snapshot/review responses already contain the canonical server-side turns.
  // Use those directly so the browser never invents different boundaries.
  const groups = preparedGroups.length
    ? normalizePreparedTranscriptGroups(preparedGroups)
    : groupTranscriptSegments();
  for (const group of groups) {
    const cached = assemblyTranscriptState.cachedSummaries.get(group.utterance_id);
    if (cached) Object.assign(group, cached);
  }
  renderTranscriptGroups(groups);
  renderLiveInsights(document.querySelector("#assemblyLiveInsights"), groups);
  const latest = groups.at(-1);
  const activeUtteranceId = latest?.utterance_id || null;
  assemblyTranscriptState.lastActiveUtteranceId = activeUtteranceId;
  if (options.detectTransition !== false
      && previousActiveUtteranceId
      && activeUtteranceId
      && previousActiveUtteranceId !== activeUtteranceId) {
    assemblyTranscriptState.summaryRefreshAttempts = 0;
    scheduleTranscriptSummaryRefresh(assemblyTranscriptState.generation, 3000);
  }
}

function scheduleTranscriptSummaryRefresh(generation, delay = 3000) {
  if (!assemblyTranscriptState.active || generation !== assemblyTranscriptState.generation) return;
  if (assemblyTranscriptState.summaryRefreshTimer) window.clearTimeout(assemblyTranscriptState.summaryRefreshTimer);
  assemblyTranscriptState.summaryRefreshTimer = window.setTimeout(() => {
    refreshTranscriptPresentation(generation);
  }, delay);
}

function refreshTranscriptPresentation(generation) {
  if (!assemblyTranscriptState.active || generation !== assemblyTranscriptState.generation) return;
  assemblyTranscriptState.summaryRefreshTimer = null;
  fetch(`api/live/transcript/snapshot?${transcriptParams()}`, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then((payload) => {
      if (!assemblyTranscriptState.active || generation !== assemblyTranscriptState.generation) return;
      assemblyTranscriptState.meetingSessions = payload.meeting_sessions || assemblyTranscriptState.meetingSessions;
      const broadcastById = new Map((payload.broadcasts || []).map((item) => [item.broadcast_id, item]));
      const items = (payload.segments || []).map((item) => ({ ...broadcastById.get(item.broadcast_id), ...item }));
      applyTranscriptItems(items, payload.utterances || [], { detectTransition: false });
      const closedTurn = (payload.utterances || []).at(-2);
      if (closedTurn && closedTurn.summary_kind !== "AI_CACHED" && assemblyTranscriptState.summaryRefreshAttempts < 4) {
        assemblyTranscriptState.summaryRefreshAttempts += 1;
        scheduleTranscriptSummaryRefresh(generation, 4000);
      } else {
        assemblyTranscriptState.summaryRefreshAttempts = 0;
      }
    })
    .catch(() => {
      if (assemblyTranscriptState.summaryRefreshAttempts >= 4) return;
      assemblyTranscriptState.summaryRefreshAttempts += 1;
      scheduleTranscriptSummaryRefresh(generation, 4000);
    });
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
  const committee = liveItems.length === 1 ? liveItems[0].committee_name : "";
  const broadcastId = liveItems.length === 1 ? (liveItems[0].broadcast_id || "") : "";
  if (assemblyTranscriptState.active
      && assemblyTranscriptState.committee === committee
      && assemblyTranscriptState.broadcastId === broadcastId) return;
  stopAssemblyTranscript();
  assemblyTranscriptState.active = true;
  assemblyTranscriptState.committee = committee;
  assemblyTranscriptState.broadcastId = broadcastId;
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
      assemblyTranscriptState.meetingSessions = payload.meeting_sessions || [];
      const broadcastById = new Map((payload.broadcasts || []).map((item) => [item.broadcast_id, item]));
      const items = (payload.segments || []).map((item) => ({ ...broadcastById.get(item.broadcast_id), ...item }));
      const selectedBroadcast = payload.broadcasts?.[0];
      renderSpeakerEditor(selectedBroadcast, payload.speaker_options?.[String(selectedBroadcast?.broadcast_id)] || []);
      applyTranscriptItems(items, payload.utterances || []);
      if (!items.length) {
        const waiting = document.querySelector(".transcript-waiting");
        if (waiting) waiting.textContent = liveItems[0]?.institution === "EXECUTIVE"
          ? "방송을 감지했습니다. 첫 AI 음성 전사를 준비하고 있습니다."
          : "방송을 감지했습니다. 첫 공식 자막을 기다리고 있습니다.";
      }
      scheduleTranscriptDelta(generation, 0);
    })
    .catch(() => {
      const waiting = document.querySelector(".transcript-waiting");
      if (waiting) waiting.textContent = "저장된 자막을 불러오지 못했습니다. 자동으로 다시 확인합니다.";
      scheduleTranscriptDelta(generation, 5000);
    });
}

function mergeOfficialLiveBroadcasts(statusPayload, activeTranscript) {
  const active = (activeTranscript?.broadcasts || []).filter((item) => (
    item.lifecycle_status === "LIVE" && item.source_system === "assembly.webcast.go.kr"
    && !isWatchTestSource(item.source_system)
  ));
  if (!statusPayload?.assembly) return;
  const items = statusPayload.assembly.items || (statusPayload.assembly.items = []);
  const matched = new Set();
  for (const item of items) {
    const match = active.find((candidate) => (
      item.meeting_external_id
        ? String(candidate.external_id || "") === String(item.meeting_external_id)
        : item.is_live && candidate.committee_name === item.committee_name
    ));
    if (!match) continue;
    matched.add(match.broadcast_id);
    Object.assign(item, {
      broadcast_id: match.broadcast_id, external_id: match.external_id,
      detected_at: match.detected_at, lifecycle_status: match.lifecycle_status,
      source_system: match.source_system, has_saved_live_record: true,
      is_recess: !item.is_live && /정회|계속.*예정|재개.*예정/.test(String(item.status_text || "")),
    });
    item.stream_url = item.stream_url || match.stream_url || null;
  }
  // A temporary source-list omission must not hide an unfinished saved meeting.
  for (const match of active) {
    const lastSeen = Date.parse(match.last_seen_at || match.detected_at || "");
    if (matched.has(match.broadcast_id) || !Number.isFinite(lastSeen)
        || Date.now() - lastSeen > 24 * 60 * 60 * 1000) continue;
    items.push({ ...match, meeting_external_id: match.external_id,
      is_live: false, has_saved_live_record: true, is_recess: false,
      status_text: "방송 상태 확인 중" });
  }
}

function visibleAssemblyMeetings(items) {
  return items.filter((item) => item.is_live || item.has_saved_live_record);
}

function renderDetectedAssemblyLive(items) {
  const liveItems = items.filter((item) => item.is_live);
  assemblyTranscriptState.liveItems = liveItems;
  if (!liveItems.length) return false;
  return true;
}

function officialPendingBroadcasts(items) {
  return items
    .filter((item) => !item.is_live && item.meeting_external_id
      && String(item.status_text || "").includes("예정"))
    .sort((left, right) => {
      const time = (item) => String(item.status_text).match(/\d{1,2}:\d{2}/)?.[0] || "99:99";
      return time(left).localeCompare(time(right), "ko-KR", { numeric: true });
    });
}

function addMeetingRailCard(container, card) {
  const row = document.createElement(card.onClick ? "button" : "article");
  row.className = "broadcast-row meeting-card is-" + card.state;
  const tags = card.tags || [
    { label: card.status, tone: card.state },
    { label: card.institution, tone: "institution" },
  ];
  if (card.id) row.dataset.broadcastId = card.id;
  if (Number.isFinite(Number(card.reportTimestamp))) {
    row.dataset.reportTimestamp = String(Number(card.reportTimestamp));
  }
  if (card.id && card.id === assemblyTranscriptState.selectedBroadcastId) row.setAttribute("aria-current", "true");
  if (card.onClick) {
    row.type = "button";
    row.addEventListener("click", () => {
      if (card.rememberReportSelection && card.id) {
        rememberMeetingReportSelection(card.id);
      }
      card.onClick(row);
    });
  }
  row.setAttribute("aria-label", [...tags.map((tag) => tag.label), card.title, card.date, card.place, card.onClick ? "상세보기" : ""].filter(Boolean).join(" · "));
  const top = magazineElement("span", "meeting-card-tags", "");
  for (const tag of tags) {
    const badge = magazineElement("em", `meeting-card-tag is-${tag.tone || "default"}`, tag.label);
    if (tag.title) badge.title = tag.title;
    top.append(badge);
  }
  const bottom = magazineElement("span", "meeting-card-bottom", "");
  const meta = magazineElement("span", "meeting-card-meta", "");
  meta.append(
    magazineElement("small", "meeting-card-date", card.date || "일시 미정"),
    magazineElement("small", "meeting-card-place", card.place || "장소 미표기"),
  );
  bottom.append(
    meta,
    magazineElement("i", "", card.onClick ? "상세보기" : card.hint || "상세 준비 중"),
  );
  const title = magazineElement("strong", "meeting-card-title", card.title);
  title.title = card.title || "";
  row.append(
    top,
    title,
    bottom,
  );
  container.append(row);
  return row;
}

function reportTimestamp(...values) {
  for (const value of values) {
    if (!value) continue;
    const text = String(value).trim();
    const parts = text.match(
      /^(\d{4})[.\/-](\d{1,2})[.\/-](\d{1,2})(?:[T\s](\d{1,2}):(\d{2})(?::(\d{2}(?:\.\d+)?))?)?/,
    );
    const hasExplicitZone = /T.*(?:Z|[+-]\d{2}:?\d{2})$/i.test(text);
    const parsed = hasExplicitZone
      ? Date.parse(text)
      : parts
      ? new Date(
        Number(parts[1]), Number(parts[2]) - 1, Number(parts[3]),
        Number(parts[4] || 0), Number(parts[5] || 0), Math.floor(Number(parts[6] || 0)),
      ).valueOf()
      : Date.parse(text);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

function sortMeetingReportCards(container) {
  const rows = [...container.querySelectorAll(
    ":scope > .meeting-card.broadcast-row[data-report-timestamp]",
  )];
  rows.sort((left, right) => (
    Number(right.dataset.reportTimestamp || 0)
      - Number(left.dataset.reportTimestamp || 0)
  ));
  container.append(...rows);
}

function visibleExecutiveTimelineMeetings(historyPayload, executivePayload) {
  const candidates = (executivePayload?.items || []).slice(0, 4);
  if (!historyPayload?.has_more) return candidates;
  const loadedTimestamps = (historyPayload?.items || [])
    .map((item) => reportTimestamp(item.started_at, item.detected_at))
    .filter((value) => value > 0);
  if (!loadedTimestamps.length) return [];
  const oldestLoadedTimestamp = Math.min(...loadedTimestamps);
  return candidates.filter((meeting) => {
    const timestamp = reportTimestamp(
      meeting.meeting_date, meeting.published_date, meeting.retrieved_at,
    );
    return timestamp >= oldestLoadedTimestamp;
  });
}

function captureMeetingRailAnchor(rail) {
  if (!rail) return null;
  const rows = [...rail.querySelectorAll(
    ":scope > .meeting-card.broadcast-row[data-broadcast-id]",
  )];
  const left = rail.scrollLeft;
  const row = rows.find((candidate) => (
    candidate.offsetLeft + candidate.offsetWidth > left + 1
  )) || rows[0];
  if (!row) return null;
  return {
    id: row.dataset.broadcastId,
    offset: row.offsetLeft - left,
  };
}

function restoreMeetingRailAnchor(rail, anchor) {
  if (!rail || !anchor?.id) return false;
  const row = [...rail.querySelectorAll(
    ":scope > .meeting-card.broadcast-row[data-broadcast-id]",
  )].find((candidate) => candidate.dataset.broadcastId === anchor.id);
  if (!row) return false;
  rail.scrollLeft = Math.max(0, row.offsetLeft - Number(anchor.offset || 0));
  return true;
}

async function openLatestMeetingReport() {
  if (latestMeetingReportState.opening) return false;
  const panel = document.querySelector('[data-workspace-panel="reports"]');
  const rail = document.querySelector("#reportBroadcastRows");
  if (!rail || panel?.hidden !== false) return false;
  if (!meetingRailHistoryState.initialized) return false;
  latestMeetingReportState.opening = true;
  try {
    const preferredId = latestMeetingReportState.preferredId;
    let rows = [...rail.querySelectorAll(".meeting-card.broadcast-row[data-report-timestamp]")];
    let target = preferredId
      ? rows.find((row) => row.dataset.broadcastId === preferredId)
      : null;
    while (preferredId && !target && meetingRailHistoryState.hasMore) {
      const loaded = await loadMoreMeetingHistory();
      rows = [...rail.querySelectorAll(".meeting-card.broadcast-row[data-report-timestamp]")];
      target = rows.find((row) => row.dataset.broadcastId === preferredId);
      if (!loaded) break;
    }
    if (preferredId && !target) rememberMeetingReportSelection(null);
    rows.sort((left, right) => (
      Number(right.dataset.reportTimestamp || 0) - Number(left.dataset.reportTimestamp || 0)
    ));
    target ||= rows[0];
    if (!target) return false;
    latestMeetingReportState.pending = false;
    rail.scrollTo({ left: Math.max(0, target.offsetLeft - rail.offsetLeft), behavior: "smooth" });
    target.click();
    return true;
  } finally {
    latestMeetingReportState.opening = false;
  }
}

function requestLatestMeetingReport() {
  latestMeetingReportState.pending = true;
  window.requestAnimationFrame(() => openLatestMeetingReport());
}

function expandScheduledMeeting(item, row) {
  stopAssemblyTranscript();
  assemblyTranscriptState.expanded = true;
  assemblyTranscriptState.expandedMode = "SCHEDULE";
  assemblyTranscriptState.selectedBroadcastId = String(item.id || item.meeting_id || item.title);
  document.querySelector("#liveExpanded").hidden = false;
  document.querySelector("#liveExpandedTitle").textContent = item.title || "예정 회의";
  document.querySelectorAll(".broadcast-row").forEach((candidate) => candidate.removeAttribute("aria-current"));
  row?.setAttribute?.("aria-current", "true");
  const stage = document.querySelector("#liveExpandedStage");
  const root = magazineElement("section", "meeting-schedule-view", "");
  root.append(
    magazineElement("span", "meeting-institution-badge", "국회"),
    magazineElement("h3", "", item.title || "예정 회의"),
    magazineElement("p", "", scheduleDateLabel(item) + " · " + (item.place || "장소 미표기")),
    magazineElement("strong", "", "회의가 시작되면 LIVE 저장본이 연결되고, 종료 후 결과 요약이 이 자리에 표시됩니다."),
  );
  if (item.source_url) {
    const link = magazineElement("a", "", "공식 일정 원문 보기 ↗");
    link.href = item.source_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    root.append(link);
  }
  stage.replaceChildren(root);
}

function expandExecutiveBriefing(meeting, row, options = {}) {
  stopAssemblyTranscript();
  const selectionId = meeting.live_capture?.broadcast_id
    || "executive-" + (meeting.id || meeting.source_url || meeting.published_date);
  rememberMeetingReportSelection(selectionId);
  assemblyTranscriptState.expanded = true;
  assemblyTranscriptState.expandedMode = "EXECUTIVE_OFFICIAL";
  assemblyTranscriptState.selectedBroadcastId = selectionId;
  document.querySelector("#liveExpanded").hidden = false;
  document.querySelector("#liveExpandedTitle").textContent = meeting.title || "국무회의 결과";
  document.querySelectorAll(".broadcast-row").forEach((candidate) => candidate.removeAttribute("aria-current"));
  row?.setAttribute?.("aria-current", "true");
  const stage = document.querySelector("#liveExpandedStage");
  const root = magazineElement("section", "meeting-brief-view meeting-executive-view", "");
  const hero = magazineElement("header", "meeting-brief-hero", "");
  const identity = magazineElement("div", "", "");
  const labels = magazineElement("div", "meeting-brief-labels", "");
  labels.append(
    magazineElement("span", "institution-label", "정부 정책 흐름"),
    magazineElement("span", "official-label", "공식 자료"),
  );
  identity.append(
    labels,
    magazineElement("h3", "", meeting.title || "국무회의 결과"),
    magazineElement(
      "p", "",
      meeting.presentation_summary || "공식 배포 자료의 주요 안건입니다.",
    ),
  );
  hero.append(identity);
  const tabs = magazineElement("div", "meeting-source-tabs", "");
  const liveCapture = meeting.live_capture;
  const liveMatch = meeting.live_match;
  const liveTab = magazineElement(
    "button", "", liveCapture
      ? liveMatch?.status === "VERIFIED"
        ? Number(liveCapture.segment_count || 0) > 0
          ? "LIVE 저장본 연결됨 · 회차·날짜 일치"
          : "LIVE 감지 기록 연결됨 · 자막 저장 전 감지"
        : "LIVE 감지 기록 · 자막 없음"
      : "LIVE 저장본 없음",
  );
  liveTab.type = "button";
  liveTab.disabled = true;
  liveTab.setAttribute("aria-selected", "false");
  const officialTab = magazineElement("button", "", "국무회의 공식 결과 · 발행됨");
  officialTab.type = "button";
  officialTab.setAttribute("aria-selected", "true");
  tabs.append(liveTab, officialTab);
  const appendDirectiveSource = (container, guidance) => {
    const paragraphs = (guidance.source_paragraphs || []).filter((item) => item?.text);
    if (!paragraphs.length) return;
    const details = magazineElement("details", "presidential-directive-source", "");
    const summary = magazineElement(
      "summary", "", `공식 발언 ${paragraphs.length}개 보기`,
    );
    const body = magazineElement("div", "", "");
    for (const paragraph of paragraphs) {
      body.append(magazineElement("p", "", paragraph.text));
    }
    details.append(summary, body);
    container.append(details);
  };
  const renderAgendaCard = (agenda) => {
    const card = magazineElement("article", "", "");
    if ((agenda.ministries || []).length) {
      card.append(magazineElement("span", "", (agenda.ministries || []).join(" · ")));
    }
    card.append(magazineElement("h4", "", agenda.topic || "공식 안건"));
    if (agenda.agenda_type === "REPORT") {
      const reportContent = agenda.report_content || {
        label: "부처 보고 내용",
        source_label: "공식자료만 반영 · 상세내용 미공개",
        text: "공식 결과문에는 세부 보고 내용이 공개되지 않아 확인 가능한 보고 제목·소관 부처·대통령 지시만 제공합니다.",
      };
      const reportSection = magazineElement("section", "executive-report-content", "");
      const reportHeader = magazineElement("header", "", "");
      reportHeader.append(
        magazineElement("strong", "", reportContent.label || "부처 보고 내용"),
        magazineElement("span", "", reportContent.source_label || ""),
      );
      reportSection.append(
        reportHeader,
        magazineElement("p", "", reportContent.text || "보고 내용 없음"),
      );
      card.append(reportSection);
    } else {
      card.append(
        magazineElement("b", "executive-summary-label", "심의 내용"),
        magazineElement("p", "", agenda.summary || "공식 요약 없음"),
      );
    }
    for (const guidance of agenda.presidential_guidance || []) {
      const directive = magazineElement("section", "presidential-guidance", "");
      const directiveHeader = magazineElement("header", "", "");
      directiveHeader.append(magazineElement(
        "strong", "", guidance.label || "대통령 지시",
      ));
      const targets = magazineElement("div", "presidential-guidance-targets", "");
      for (const ministry of guidance.target_ministries || []) {
        targets.append(magazineElement("b", "", ministry));
      }
      directiveHeader.append(targets);
      directive.append(
        directiveHeader,
        magazineElement("p", "", guidance.display_text || guidance.text || ""),
      );
      appendDirectiveSource(directive, guidance);
      card.append(directive);
    }
    for (const briefing of agenda.related_ministry_briefings || []) {
      const related = magazineElement("section", "related-ministry-briefing", "");
      related.append(
        magazineElement("span", "", "부처 추가 발표"),
        magazineElement("strong", "", briefing.title || "부처 공식 브리핑"),
      );
      if (briefing.display_summary) {
        related.append(magazineElement("p", "", briefing.display_summary));
      }
      if (briefing.source_url) {
        const link = magazineElement("a", "", "원문 확인 ↗");
        link.href = briefing.source_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        related.append(link);
      }
      card.append(related);
    }
    return card;
  };
  const fallbackGroups = [
    {
      key: "ministry_reports", label: "부처 보고 내용",
      description: "국무회의에서 관계 부처가 보고한 정책·현안",
      items: (meeting.agendas || []).filter((agenda) => agenda.agenda_type === "REPORT"),
    },
    {
      key: "deliberated_agendas", label: "심의안건",
      description: "국무회의가 심의·의결한 법률안·대통령령안 등",
      items: (meeting.agendas || []).filter((agenda) => agenda.agenda_type !== "REPORT"),
    },
  ];
  const groups = meeting.content_groups?.length ? meeting.content_groups : fallbackGroups;
  const view = magazineElement("section", "executive-agenda-view executive-content-groups", "");
  let presidentialView = null;
  for (const group of groups) {
    const groupSection = magazineElement(
      "section", `executive-content-group is-${group.key || "other"}`, "",
    );
    const groupHeader = magazineElement("header", "", "");
    const groupTitle = magazineElement("div", "", "");
    groupTitle.append(
      magazineElement("h4", "", group.label || "공식 내용"),
      magazineElement("p", "", group.description || ""),
    );
    groupHeader.append(
      groupTitle,
      magazineElement("span", "", `${group.count ?? group.items?.length ?? 0}건`),
    );
    const groupBody = magazineElement("div", "executive-content-group-body", "");
    if (group.key === "presidential_directives") {
      presidentialView = groupSection;
      for (const guidance of group.items || []) {
        const article = magazineElement(
          "article", "presidential-guidance standalone is-compact", "",
        );
        const ministries = (guidance.target_ministries || []).filter(Boolean);
        const heading = magazineElement("header", "presidential-directive-heading", "");
        heading.append(
          magazineElement(
            "strong", "", guidance.topic || "국정 현안 후속조치",
          ),
          magazineElement(
            "span", "", ministries.length ? ministries.join(" · ") : "관계부처",
          ),
        );
        const line = magazineElement("p", "presidential-directive-line", "");
        line.append(
          magazineElement(
            "b", "presidential-directive-owner",
            `(${ministries.length ? ministries.join("·") : "관계부처"})`,
          ),
          magazineElement("span", "", guidance.display_text || guidance.text || ""),
        );
        article.append(heading, line);
        appendDirectiveSource(article, guidance);
        groupBody.append(article);
      }
    } else {
      for (const agenda of group.items || []) groupBody.append(renderAgendaCard(agenda));
    }
    if (!groupBody.children.length) {
      groupBody.append(magazineElement(
        "p", "meeting-result-empty", `확인된 ${group.label || "공식 내용"}이 없습니다.`,
      ));
    }
    groupSection.append(groupHeader, groupBody);
    view.append(groupSection);
  }
  if (meeting.source_url) {
    const link = magazineElement("a", "meeting-official-source-link", "공식 배포 자료 원문 보기 ↗");
    link.href = meeting.source_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    view.append(link);
  }
  root.append(hero, tabs);
  root.append(view);
  stage.replaceChildren(root);
  if (options.focus === "presidential") {
    const target = presidentialView || view.querySelector(".presidential-guidance");
    if (!target) return;
    window.requestAnimationFrame(() => target.scrollIntoView({
      behavior: "smooth", block: "start",
    }));
  }
}


function localIsoDate(value = new Date()) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function scheduleStartDate(item) {
  const dateText = String(item.scheduled_date || "");
  const timeText = String(item.start_time || item.time_text || "").match(/\d{1,2}:\d{2}/)?.[0];
  if (!dateText || !timeText) return null;
  const parsed = new Date(`${dateText}T${timeText}:00`);
  return Number.isNaN(parsed.valueOf()) ? null : parsed;
}

function scheduleDateLabel(item) {
  const start = scheduleStartDate(item);
  if (!start) return item.time_text || item.start_time || "시간 미정";
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const target = new Date(start);
  target.setHours(0, 0, 0, 0);
  const dayOffset = Math.round((target - today) / 86_400_000);
  const dateLabel = dayOffset === 0
    ? "오늘"
    : dayOffset === 1
      ? "내일"
      : start.toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" });
  return `${dateLabel} · ${start.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}`;
}

function mergedOfficialSchedules(statusPayload, schedulePayload) {
  const items = [...(schedulePayload.items || [])];
  const today = localIsoDate();
  const keys = new Set(items.map((item) => (
    `${item.scheduled_date}|${item.committee_name}|${String(item.start_time || item.time_text || "").slice(0, 5)}`
  )));
  for (const liveItem of statusPayload.assembly?.items || []) {
    if (liveItem.is_live || !liveItem.meeting_external_id || !String(liveItem.status_text || "").includes("예정")) continue;
    const timeText = String(liveItem.status_text || liveItem.title || "").match(/\d{1,2}:\d{2}/)?.[0];
    if (!timeText) continue;
    const key = `${today}|${liveItem.committee_name}|${timeText}`;
    if (keys.has(key)) continue;
    keys.add(key);
    items.push({
      id: liveItem.meeting_external_id,
      meeting_external_id: liveItem.meeting_external_id,
      title: liveItem.title || liveItem.committee_name,
      committee_name: liveItem.committee_name,
      scheduled_date: today,
      start_time: timeText,
      time_text: timeText,
      place: "국회 의사중계",
      is_target_committee: true,
      authority_status: "OFFICIAL",
      source_url: "https://assembly.webcast.go.kr/",
    });
  }
  return items;
}

function todayScheduledItems(statusPayload, schedulePayload) {
  const now = new Date();
  const today = localIsoDate(now);
  const liveItems = (statusPayload.assembly?.items || []).filter((item) => item.is_live);
  const liveIds = new Set(liveItems.map((item) => String(item.meeting_external_id || item.broadcast_id || "")));
  const liveCommittees = new Set(liveItems.map((item) => item.committee_name));
  return mergedOfficialSchedules(statusPayload, schedulePayload)
    .filter((item) => {
      if (!item.is_target_committee || String(item.scheduled_date || "") !== today) return false;
      if (liveIds.has(String(item.meeting_external_id || item.id || ""))) return false;
      const start = scheduleStartDate(item);
      if (start && start < now) return false;
      return !(start && start <= now && liveCommittees.has(item.committee_name));
    })
    .sort((left, right) => {
      const leftStart = scheduleStartDate(left);
      const rightStart = scheduleStartDate(right);
      if (!leftStart) return 1;
      if (!rightStart) return -1;
      return leftStart - rightStart;
    });
}

function todayScheduleRow(item) {
  const row = magazineElement("button", "today-schedule-row", "");
  row.type = "button";
  const title = item.title || item.committee_name || "예정 회의";
  const time = scheduleDateLabel(item).replace(/^오늘 · /, "");
  const metadata = [time, item.committee_name, item.place].filter(Boolean).join(" · ");
  row.append(
    magazineElement("strong", "", title),
    magazineElement("small", "", metadata || "시간·장소 확인 중"),
  );
  row.title = `${title} · ${metadata}`;
  row.addEventListener("click", () => expandScheduledMeeting(item, row));
  return row;
}

function setTodayScheduleOffset(animated) {
  const track = document.querySelector("#todayScheduleTrack");
  if (!track) return;
  track.style.transition = animated
    ? `transform ${TODAY_SCHEDULE_TRANSITION_MS}ms cubic-bezier(.22,.8,.32,1)`
    : "none";
  track.style.transform = `translateY(calc(var(--schedule-row-step) * -${todayScheduleState.index}))`;
}

function startTodayScheduleRotation(delay = TODAY_SCHEDULE_HOLD_MS) {
  if (todayScheduleState.timer) window.clearTimeout(todayScheduleState.timer);
  if (todayScheduleState.items.length <= 2) return;
  todayScheduleState.timer = window.setTimeout(() => {
    moveTodaySchedule(1);
    startTodayScheduleRotation(
      TODAY_SCHEDULE_TRANSITION_MS + TODAY_SCHEDULE_HOLD_MS,
    );
  }, delay);
}

function moveTodaySchedule(direction, fromUser = false) {
  const count = todayScheduleState.items.length;
  if (count <= 2) return;
  if (todayScheduleState.resetTimer) window.clearTimeout(todayScheduleState.resetTimer);
  if (direction < 0 && todayScheduleState.index === 0) {
    todayScheduleState.index = count;
    setTodayScheduleOffset(false);
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      todayScheduleState.index = count - 1;
      setTodayScheduleOffset(true);
    }));
  } else {
    todayScheduleState.index += direction;
    setTodayScheduleOffset(true);
    if (todayScheduleState.index >= count) {
      todayScheduleState.resetTimer = window.setTimeout(() => {
        todayScheduleState.index = 0;
        setTodayScheduleOffset(false);
      }, TODAY_SCHEDULE_TRANSITION_MS + 40);
    }
  }
  if (fromUser) startTodayScheduleRotation(
    TODAY_SCHEDULE_TRANSITION_MS + TODAY_SCHEDULE_HOLD_MS,
  );
}

function renderTodayScheduleBoard(statusPayload, schedulePayload) {
  const items = todayScheduledItems(statusPayload, schedulePayload);
  const signature = items.map((item) => [
    item.id || item.meeting_id || item.title, item.start_time || item.time_text, item.title,
  ].join("|")).join("::");
  document.querySelector("#todayScheduleCount").textContent = `${items.length}건`;
  if (signature === todayScheduleState.signature) return;
  if (todayScheduleState.timer) window.clearTimeout(todayScheduleState.timer);
  if (todayScheduleState.resetTimer) window.clearTimeout(todayScheduleState.resetTimer);
  todayScheduleState.items = items;
  todayScheduleState.signature = signature;
  todayScheduleState.index = 0;
  const track = document.querySelector("#todayScheduleTrack");
  track.replaceChildren();
  if (!items.length) {
    track.append(magazineElement("p", "today-schedule-empty", "오늘 남은 예정 회의가 없습니다."));
    setTodayScheduleOffset(false);
    return;
  }
  const visibleItems = items.length > 2 ? items.concat(items.slice(0, 2)) : items;
  for (const item of visibleItems) track.append(todayScheduleRow(item));
  setTodayScheduleOffset(false);
  startTodayScheduleRotation();
}

function executiveMeetingNumber(value) {
  return String(value || "").match(/제\s*(\d+)\s*회/)?.[1] || null;
}
function normalizeExecutiveDate(value) {
  const digits = String(value || "").replace(/[^0-9]/g, "");
  if (digits.length < 8) return null;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)}`;
}
function seoulDateFromTimestamp(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return null;
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(parsed);
}
function executiveOfficialMatchKey(item, liveRecord = false) {
  const meetingNumber = executiveMeetingNumber(item?.title);
  const meetingDate = liveRecord
    ? normalizeExecutiveDate(item?.schedule_date)
      || seoulDateFromTimestamp(item?.detected_at)
    : normalizeExecutiveDate(item?.published_date);
  return meetingNumber && meetingDate ? `${meetingNumber}|${meetingDate}` : null;
}

function meetingTaskOwnerTags(task) {
  const owners = magazineElement("span", "meeting-task-owner-tags", "");
  owners.setAttribute("aria-label", "담당 부서");
  const ministries = [...new Set((task?.ministries || []).filter(Boolean))];
  if (ministries.length) {
    for (const ministry of ministries) owners.append(magazineElement("b", "", ministry));
  } else {
    owners.append(magazineElement("em", "", "담당 부서 미확정"));
  }
  return owners;
}

function limitMeetingOverviewRows(list, visibleCount = 5) {
  const rows = [...list.children].filter(
    (child) => child.classList.contains("meeting-topic-task-row"),
  );
  list.dataset.visibleRows = String(visibleCount);
  list.classList.toggle("is-scrollable", rows.length > visibleCount);
  const overview = list.closest(".meeting-topic-task-overview");
  if (overview && !overview.classList.contains("live-draft-overview")) {
    overview.style.setProperty("--overview-scrollbar-width", `${Math.max(0, list.offsetWidth - list.clientWidth)}px`);
  }
}

function meetingBriefResultCounts(item) {
  const brief = item?.meeting_brief?.brief || {};
  return {
    topics: Array.isArray(brief.topics) ? brief.topics.length : 0,
    tasks: Array.isArray(brief.tasks)
      ? brief.tasks.filter((task) => task.status !== "RESOLVED").length : 0,
    utterances: Number(brief.utterance_count || item?.utterance_count || 0),
  };
}

const LIVE_CONTINUITY_WINDOW_MS = 24 * 60 * 60 * 1000;

function broadcastWasActiveWithin24Hours(item, referenceNow = Date.now()) {
  const activityTimes = [item?.ended_at, item?.last_caption_received_at, item?.detected_at]
    .map((value) => new Date(value).valueOf())
    .filter(Number.isFinite);
  if (!activityTimes.length) return false;
  const latestActivity = Math.max(...activityTimes);
  return latestActivity >= referenceNow - LIVE_CONTINUITY_WINDOW_MS
    && latestActivity <= referenceNow + (5 * 60 * 1000);
}

function selectedBroadcastMatches(item) {
  const selected = String(assemblyTranscriptState.selectedBroadcastId || "");
  return Boolean(selected) && [item?.broadcast_id, item?.external_id]
    .some((value) => String(value || "") === selected);
}

function clearLiveReportHandoff() {
  document.querySelector("#liveOperationsExpanded > .live-report-handoff")?.remove();
}

function showLiveReportHandoff(item, openReport) {
  const expanded = document.querySelector("#liveOperationsExpanded");
  const stage = document.querySelector("#liveOperationsExpandedStage");
  if (!expanded || !stage || expanded.hidden) return;
  const counts = meetingBriefResultCounts(item);
  let banner = expanded.querySelector(":scope > .live-report-handoff");
  if (!banner) {
    banner = magazineElement("section", "live-report-handoff", "");
    expanded.querySelector(":scope > header")?.after(banner);
  }
  banner.dataset.broadcastId = String(item.broadcast_id || "");
  banner.replaceChildren();
  const copy = magazineElement("div", "", "");
  copy.append(
    magazineElement("span", "", "비공식 보고서 정리 완료"),
    magazineElement("strong", "", "실시간 초안이 회의 보고서로 통합되었습니다."),
    magazineElement(
      "p", "",
      `아래 실시간 초안은 그대로 확인할 수 있습니다. 전체 발언 묶음 ${counts.utterances.toLocaleString("ko-KR")}개를 분석해 상위 핵심 주제 ${counts.topics}건과 도출 과제 ${counts.tasks}건으로 정리했습니다.`,
    ),
  );
  const button = magazineElement("button", "", "회의 보고서 보기 →");
  button.type = "button";
  button.addEventListener("click", openReport);
  banner.append(copy, button);
}

function renderBroadcastRows(statusPayload, historyPayload, executivePayload = { items: [] }) {
  const liveContainer = document.querySelector("#liveBroadcastRows");
  const reportContainer = document.querySelector("#reportBroadcastRows");
  liveContainer.replaceChildren();
  reportContainer.replaceChildren();
  const replayBroadcast = watchTestLiveState?.status === "LIVE"
    ? watchTestBroadcast(watchTestLiveState) : null;
  if (replayBroadcast?.institution === "LEGISLATURE") {
    const exists = (statusPayload.assembly?.items || []).some(
      (item) => String(item.broadcast_id || "") === String(replayBroadcast.broadcast_id || ""),
    );
    if (!exists) {
      statusPayload.assembly.items = [
        { ...replayBroadcast, is_live: true, source_status: "REPLAY" },
        ...(statusPayload.assembly?.items || []),
      ];
    }
  } else if (statusPayload.executive?.is_live !== true && replayBroadcast) {
    statusPayload.executive = {
      ...(statusPayload.executive || {}),
      ...replayBroadcast,
      is_live: true,
      source_status: "TEST",
      place: "가상 국무회의 테스트",
    };
  }
  const officialExecutiveByKey = new Map();
  const officialExecutiveByNumber = new Map();
  const officialExecutiveById = new Map();
  for (const meeting of executivePayload.items || []) {
    const meetingNumber = executiveMeetingNumber(meeting.title);
    const matchKey = executiveOfficialMatchKey(meeting);
    if (matchKey) officialExecutiveByKey.set(matchKey, meeting);
    if (meeting.news_id) officialExecutiveById.set(String(meeting.news_id), meeting);
    if (meetingNumber) {
      const candidates = officialExecutiveByNumber.get(meetingNumber) || [];
      candidates.push(meeting);
      officialExecutiveByNumber.set(meetingNumber, candidates);
    }
  }
  const matchedExecutiveKeys = new Set();
  const liveItems = visibleAssemblyMeetings(statusPayload.assembly?.items || []);
  for (const item of liveItems) {
    const onAir = Boolean(item.is_live);
    const stateLabel = onAir ? "진행중" : item.is_recess ? "정회 · 재개 대기" : "방송 상태 확인 중";
    addMeetingRailCard(liveContainer, {
      state: onAir ? "live" : "processing", status: stateLabel, institution: "국회",
      tags: [
        { label: stateLabel, tone: onAir ? "active" : "processing" },
        { label: onAir ? "기록 중" : "누적 기록 보기", tone: onAir ? "recording" : "provisional" },
        ...(isWatchTestSource(item.source_system) ? [{ label: "재현", tone: "processing" }] : []),
        { label: "국회", tone: "institution" },
      ],
      title: item.title || item.committee_name,
      date: onAir ? "지금 LIVE" : item.status_text, place: item.place || "국회", id: item.broadcast_id || item.meeting_external_id,
      onClick: (row) => isWatchTestSource(item.source_system)
        ? renderWatchTestLive(watchTestLiveState, { focus: true, row })
        : expandLiveBroadcast(item, row),
    });
    if (item.has_saved_live_record && !(historyPayload.items || []).some((saved) => saved.broadcast_id === item.broadcast_id)) {
      addMeetingRailCard(reportContainer, {
        state: "processing", status: stateLabel, institution: "국회",
        tags: [{ label: stateLabel, tone: "processing" }, { label: "누적 저장본", tone: "provisional" }],
        title: item.title || item.committee_name, date: onAir ? "회의 진행 중" : item.status_text,
        place: "현재까지 저장된 요약·원문", id: item.broadcast_id,
        reportTimestamp: reportTimestamp(item.detected_at), rememberReportSelection: true,
        onClick: (row) => expandMeetingBrief(item, row),
      });
    }
  }
  if (statusPayload.executive?.is_live === true) {
    const executiveLive = {
      ...statusPayload.executive,
      institution: "EXECUTIVE",
      committee_name: "국무회의",
      place: statusPayload.executive.place || "KTV 국민방송",
    };
    addMeetingRailCard(liveContainer, {
      state: "live", status: executiveLive.source_system === "poc07.test" ? "TEST · 기록 중" : "진행중 · 기록 중", institution: "국무회의",
      tags: [
        { label: "진행중", tone: "active" },
        { label: "기록 중", tone: "recording" },
        ...(executiveLive.source_system === "poc07.test" ? [{ label: "TEST", tone: "processing" }] : []),
        { label: "국무회의", tone: "institution" },
      ],
      title: executiveLive.title || "국무회의 생중계",
      date: "지금 LIVE", place: executiveLive.place,
      id: executiveLive.broadcast_id || executiveLive.external_id,
      onClick: (row) => executiveLive.source_system === "poc07.test"
        ? renderWatchTestLive(watchTestLiveState, { focus: true, row })
        : expandExecutiveLiveBroadcast(executiveLive, row),
    });
    const liveMatchKey = executiveOfficialMatchKey(executiveLive, true);
    if (liveMatchKey && officialExecutiveByKey.has(liveMatchKey)) {
      matchedExecutiveKeys.add(liveMatchKey);
    }
  }
  const hasLive = liveItems.some((item) => item.is_live) || statusPayload.executive?.is_live === true;
  let firstProcessingRow = null;
  for (const ended of historyPayload.items || []) {
    const isExecutive = ended.institution === "EXECUTIVE";
    const meetingNumber = isExecutive ? executiveMeetingNumber(ended.title) : null;
    const matchKey = isExecutive ? executiveOfficialMatchKey(ended, true) : null;
    const sameNumberCandidates = meetingNumber
      ? officialExecutiveByNumber.get(meetingNumber) || []
      : [];
    const serverMatchedExecutive = ended.official_briefing_id
      ? officialExecutiveById.get(String(ended.official_briefing_id)) : null;
    const officialExecutive = serverMatchedExecutive || (matchKey
      ? officialExecutiveByKey.get(matchKey)
      : sameNumberCandidates.length === 1 ? sameNumberCandidates[0] : null);
    if (officialExecutive) {
      matchedExecutiveKeys.add(executiveOfficialMatchKey(officialExecutive));
    }
    ended.institution_label = isExecutive ? "국무회의" : "국회";
    const startedAt = new Date(ended.detected_at);
    const endedLabel = Number.isNaN(startedAt.valueOf())
      ? "시작 시각 미상"
      : `시작 ${startedAt.toLocaleString("ko-KR", {
        month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
      })}`;
    const hasProvisionalResult = ended.brief_status === "READY"
      || meetingBriefIsReady(ended.meeting_brief);
    const hasOfficialPublication = ended.official_status === "PUBLISHED";
    const hasOfficialResult = isExecutive
      ? Boolean(officialExecutive)
      : Boolean(ended.official_integration_updated_at);
    const hasReportResult = hasProvisionalResult || hasOfficialResult;
    const showInLiveContinuity = broadcastWasActiveWithin24Hours(ended);
    const processingTag = meetingBriefProgressTag(ended);
    const stageTags = hasOfficialResult && !ended.meeting_brief ? [] : meetingBriefStageTags(ended);
    const resultTags = [];
    if (hasProvisionalResult) {
      resultTags.push(...stageTags);
    } else if (!hasOfficialResult) {
      resultTags.push(...stageTags);
    }
    if (hasOfficialResult) {
      if (!resultTags.length) resultTags.push(...stageTags);
      resultTags.push({ label: "공식 정리 완료", tone: "official" });
    } else if (!isExecutive && hasOfficialPublication) {
      const comparisonProgress = Math.max(
        0, Math.min(99, Number(ended.official_comparison_progress || 0)),
      );
      resultTags.push({
        label: `공식대조중(${Math.round(comparisonProgress)}%)`, tone: "processing",
      });
    }
    const openReport = (row) => officialExecutive ? expandExecutiveBriefing({
      ...officialExecutive,
      live_capture: ended,
      live_match: {
        status: "VERIFIED",
        match_type: matchKey ? "MEETING_NUMBER_AND_DATE" : "UNIQUE_MEETING_NUMBER",
        meeting_number: meetingNumber,
        meeting_date: matchKey?.split("|")[1] || null,
      },
    }, row) : isExecutive && Number(ended.segment_count || 0) === 0
        && ended.capture_status !== "POST_PROCESSING"
      ? expandEndedExecutiveBroadcast(ended, row)
      : expandMeetingBrief(ended, row);
    const openReportWorkspace = () => {
      latestMeetingReportState.pending = false;
      activateWorkspaceTab("reports");
      window.requestAnimationFrame(() => {
        const reportRow = reportContainer.querySelector(
          `.broadcast-row[data-broadcast-id="${ended.broadcast_id}"]`,
        );
        openReport(reportRow);
      });
    };
    if (!hasReportResult) {
      let processingRow = null;
      if (showInLiveContinuity) {
        processingRow = addMeetingRailCard(liveContainer, {
          state: "processing", status: `완료 · ${processingTag.label}`, institution: ended.institution_label,
          tags: [
            { label: "방송 종료", tone: "complete" },
            ...stageTags,
            { label: ended.institution_label, tone: "institution" },
          ],
          title: ended.title || ended.committee_name,
          date: endedLabel,
          place: `실시간 초안 전체 보기 · 발언 묶음 ${Number(ended.utterance_count || 0).toLocaleString("ko-KR")}개`,
          id: ended.broadcast_id,
          onClick: (row) => expandPostProcessingBroadcast(ended, row),
        });
        if (!firstProcessingRow) firstProcessingRow = processingRow;
      }
      if (selectedBroadcastMatches(ended)) {
        clearLiveReportHandoff();
        if (processingRow && ["LIVE", "EXECUTIVE_LIVE"].includes(
          assemblyTranscriptState.expandedMode,
        )) {
          expandPostProcessingBroadcast(ended, processingRow);
        }
      }
      if (ended.meeting_brief?.brief) {
        addMeetingRailCard(reportContainer, {
          state: "processing", status: `완료 · ${processingTag.label}`, institution: ended.institution_label,
          tags: [
            ...stageTags,
            { label: ended.institution_label, tone: "institution" },
          ],
          title: ended.title || ended.committee_name,
          date: endedLabel,
          place: ended.place || (isExecutive ? "KTV 국민방송" : "국회"),
          id: ended.broadcast_id,
          reportTimestamp: reportTimestamp(ended.started_at, ended.detected_at),
          rememberReportSelection: true,
          onClick: (row) => expandMeetingBrief(ended, row),
        });
      }
      continue;
    }
    addMeetingRailCard(reportContainer, {
      state: "result", status: resultTags.map((tag) => tag.label).join(" · ") || "완료",
      institution: ended.institution_label,
      tags: [
        ...resultTags,
        { label: ended.institution_label, tone: "institution" },
      ],
      title: ended.title || ended.committee_name,
      date: endedLabel,
      place: ended.place || (isExecutive ? "KTV 국민방송" : "국회"),
      id: ended.broadcast_id,
      reportTimestamp: reportTimestamp(ended.started_at, ended.detected_at),
      rememberReportSelection: true,
      onClick: openReport,
    });
    if (showInLiveContinuity) {
      const counts = meetingBriefResultCounts(ended);
      addMeetingRailCard(liveContainer, {
        state: "handoff", status: "완료 · 보고서 이동", institution: ended.institution_label,
        tags: [
          { label: "완료", tone: "complete" },
          ...stageTags,
          ...(hasOfficialResult ? [{ label: "공식 정리 완료", tone: "official" }] : []),
          { label: ended.institution_label, tone: "institution" },
        ],
        title: ended.title || ended.committee_name,
        date: endedLabel,
        place: `발언 묶음 ${counts.utterances.toLocaleString("ko-KR")}개 분석 → 상위 핵심 주제 ${counts.topics}건 · 도출 과제 ${counts.tasks}건`,
        id: ended.broadcast_id,
        onClick: openReportWorkspace,
      });
    }
    if (selectedBroadcastMatches(ended)
        && ["LIVE", "EXECUTIVE_LIVE", "POST_PROCESSING"].includes(
          assemblyTranscriptState.expandedMode,
        )) {
      showLiveReportHandoff(ended, openReportWorkspace);
    }
  }
  for (const meeting of visibleExecutiveTimelineMeetings(
    historyPayload, executivePayload,
  )) {
    const matchKey = executiveOfficialMatchKey(meeting);
    if (matchKey && matchedExecutiveKeys.has(matchKey)) continue;
    const identity = "executive-" + (meeting.id || meeting.source_url || meeting.published_date);
    addMeetingRailCard(reportContainer, {
      state: "result", status: "공식 정리", institution: "국무회의",
      tags: [
        { label: "완료", tone: "complete" },
        { label: "공식 정리 완료", tone: "official" },
        { label: "국무회의", tone: "institution" },
      ],
      title: meeting.title || "국무회의",
      date: meeting.published_date || "",
      place: meeting.place || "장소 미표기",
      id: identity,
      reportTimestamp: reportTimestamp(
        meeting.meeting_date, meeting.published_date, meeting.retrieved_at,
      ),
      rememberReportSelection: true,
      onClick: (row) => expandExecutiveBriefing(meeting, row),
    });
  }
  sortMeetingReportCards(reportContainer);
  const reportsVisible = document.querySelector('[data-workspace-panel="reports"]')?.hidden === false;
  if (hasLive && !reportsVisible && !["LIVE", "EXECUTIVE_LIVE"].includes(assemblyTranscriptState.expandedMode)) {
    liveContainer.querySelector(".broadcast-row")?.click();
  } else if (!hasLive && firstProcessingRow && !assemblyTranscriptState.expanded) {
    firstProcessingRow.click();
  }
  if (reportsVisible && latestMeetingReportState.pending) {
    window.requestAnimationFrame(() => openLatestMeetingReport());
  }
  if (!liveContainer.children.length) {
    liveContainer.append(magazineElement("p", "broadcast-empty", "현재 진행 중이거나 최근 24시간 내 진행된 방송이 없습니다."));
    const retainingTestReport = watchTestLiveState?.status === "COMPLETED";
    if (!retainingTestReport && ["LIVE", "EXECUTIVE_LIVE", "POST_PROCESSING"].includes(assemblyTranscriptState.expandedMode)) collapseLiveExpansion();
  }
  if (!reportContainer.children.length) {
    reportContainer.append(magazineElement("p", "broadcast-empty", "아직 확인된 회의 보고서가 없습니다."));
  }
}

function meetingBriefTasks(historyItems = []) {
  return historyItems.flatMap((broadcast) => {
    const brief = broadcast.meeting_brief?.brief;
    return (brief?.tasks || [])
      .filter((task) => task.status !== "RESOLVED")
      .map((task) => ({
        ...task,
        task: task.title,
        topic: task.topic_title || "주제 미분류",
        broadcast_id: broadcast.broadcast_id,
        broadcast_title: broadcast.title,
        committee_name: broadcast.committee_name,
        lifecycle_status: broadcast.lifecycle_status,
        brief_entity_id: task.id,
        broadcast,
      }));
  });
}

let followUpPayload = { items: [] };

function openTaskBroadcast(item, row) {
  if (item.brief_entity_id && item.broadcast) {
    expandMeetingBrief(item.broadcast, row, {
      evidence: { type: "task", id: item.brief_entity_id, title: item.task },
    });
    return;
  }
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
  };
  if (item.lifecycle_status === "LIVE") expandLiveBroadcast(broadcast, row);
  else expandMeetingBrief(broadcast, row);
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

function renderCollectionOverview(payload) {
  const container = document.querySelector("#liveCollectionOverview");
  if (!container || !payload) return;
  const values = container.querySelectorAll("strong");
  const hours = Number(payload.captured_seconds || 0) / 3600;
  const metrics = [
    `${Number(payload.broadcast_count || 0).toLocaleString("ko-KR")}건`,
    `${hours.toFixed(1)}시간`,
    `${Number(payload.segment_count || 0).toLocaleString("ko-KR")}개`,
    `${Number(payload.utterance_count || 0).toLocaleString("ko-KR")}묶음`,
  ];
  values.forEach((node, index) => { node.textContent = metrics[index]; });
  const start = payload.period_start ? new Date(payload.period_start).toLocaleDateString("ko-KR", { month: "long", day: "numeric" }) : "수집 전";
  const end = payload.period_end ? new Date(payload.period_end).toLocaleDateString("ko-KR", { month: "long", day: "numeric" }) : "";
  const named = Number(payload.named_speaker_count || 0);
  const sourceSpeakers = Number(payload.source_speaker_count || 0);
  container.querySelector("p").innerHTML = `<span><b>${start}${end && end !== start ? `–${end}` : ""}</b> 수집분 · 화자 코드 ${sourceSpeakers}개 중 이름 확정 ${named}개</span>`;
}

function formatUsageValue(value, unit) {
  const amount = Number(value || 0);
  if (unit === "requests") return `${amount.toLocaleString("ko-KR")}회`;
  if (amount >= 1_000_000) return `${(amount / 1_000_000).toFixed(amount >= 10_000_000 ? 1 : 2)}M`;
  if (amount >= 1_000) return `${(amount / 1_000).toFixed(1)}K`;
  return amount.toLocaleString("ko-KR");
}

function formatUsageReset(value) {
  const reset = new Date(value);
  if (Number.isNaN(reset.valueOf())) return "갱신일 확인 필요";
  const date = `${reset.getMonth() + 1}.${reset.getDate()}`;
  const time = reset.toLocaleTimeString("ko-KR", {
    hour: "2-digit", minute: "2-digit", hour12: false,
  });
  return `${date} ${time} 갱신`;
}

function setAiUsageMeter(selector, percent) {
  const meter = document.querySelector(selector);
  const value = Math.min(100, Math.max(0, Number(percent || 0)));
  meter.querySelector("i").style.width = `${value}%`;
  meter.setAttribute("aria-valuenow", String(Math.round(value)));
}

function compactUsageNumber(value) {
  const amount = Number(value || 0);
  if (amount >= 1_000_000) return `${(amount / 1_000_000).toFixed(2)}M`;
  if (amount >= 1_000) return `${(amount / 1_000).toFixed(1)}K`;
  return amount.toLocaleString("ko-KR");
}

function modelUsageLine(item) {
  const monthlyRequests = Number(item.monthly_request_count || 0);
  const audioRequests = Number(item.audio_request_count || 0);
  if (audioRequests) {
    return `이번 달 STT ${audioRequests.toLocaleString("ko-KR")}회 · ${(Number(item.audio_seconds || 0) / 60).toFixed(1)}분 · $${Number(item.cost_usd || 0).toFixed(2)}`;
  }
  if (item.provider === "openrouter") {
    return `오늘 ${Number(item.today_request_count || 0).toLocaleString("ko-KR")}회 · 월 ${monthlyRequests.toLocaleString("ko-KR")}회 · ${compactUsageNumber(item.total_tokens)} token`;
  }
  if (item.provider === "openai") {
    return `오늘 ${Number(item.today_request_count || 0).toLocaleString("ko-KR")}회 · ${compactUsageNumber(item.today_total_tokens)} token`;
  }
  if (item.provider === "nvidia") {
    return `이번 달 ${monthlyRequests.toLocaleString("ko-KR")}회 · ${compactUsageNumber(item.total_tokens)} token · 계정 한도 별도 확인`;
  }
  return `이번 달 ${monthlyRequests.toLocaleString("ko-KR")}회 · ${compactUsageNumber(item.total_tokens)} token · $${Number(item.cost_usd || 0).toFixed(2)}`;
}

function renderAiModelUsage(payload) {
  if (!document.querySelector("#aiModelUsageOpen")) return;
  const models = payload.models || [];
  document.querySelector("#aiModelUsageOpen").title = `${models.length.toLocaleString("ko-KR")}개 모델별 사용량 보기`;
  document.querySelector("#aiModelUsageSummary").textContent = `${Number(payload.platform_count || 0).toLocaleString("ko-KR")}개 공급 경로 · ${models.length.toLocaleString("ko-KR")}개 모델을 60초마다 갱신합니다.`;
  const providers = Object.fromEntries((payload.providers || []).map((item) => [item.provider, item]));
  const list = document.querySelector("#aiModelUsageList");
  list.replaceChildren();
  if (!models.length) {
    list.append(magazineElement("p", "ai-model-usage-empty", "사용 중이거나 설정된 외부 AI 모델이 없습니다."));
    return;
  }
  for (const providerName of ["nvidia", "openrouter", "openai", "mistral", ...new Set(models.map((item) => item.provider))]) {
    const providerModels = models.filter((item) => item.provider === providerName);
    if (!providerModels.length || list.querySelector(`[data-provider="${providerName}"]`)) continue;
    const provider = providers[providerName] || {};
    const group = magazineElement("section", "ai-model-provider-group", "");
    group.dataset.provider = providerName;
    const groupHead = magazineElement("header", "", "");
    const groupTitle = magazineElement("div", "", "");
    const providerLabel = providerName === "nvidia" ? "NVIDIA NIM" : providerName === "openrouter" ? "OpenRouter" : providerName === "mistral" ? "Mistral" : providerName === "openai" ? "OpenAI" : providerName;
    groupTitle.append(
      magazineElement("strong", "", providerLabel),
      magazineElement("span", "", providerName === "openrouter" ? "모든 경유 모델 공용" : "직접 호출 모델 공용"),
    );
    const quota = providerName === "openrouter"
      ? `오늘 ${Number(provider.used || 0).toLocaleString("ko-KR")} / ${Number(provider.official_limit || provider.limit || 1000).toLocaleString("ko-KR")}회 · 운영 안전선 ${Number(provider.operational_limit || 950).toLocaleString("ko-KR")}회`
      : providerName === "nvidia"
        ? "무료 시험 엔드포인트 · 한도는 NVIDIA 계정에서 확인"
        : providerName === "mistral"
        ? `이번 달 $${Number(provider.cost_usd || 0).toFixed(2)} / $${Number(provider.credit_usd || 0).toFixed(2)}`
        : providerName === "openai"
          ? `오늘 ${Number(provider.used || 0).toLocaleString("ko-KR")} / ${Number(provider.limit || 650000).toLocaleString("ko-KR")} token · 남음 ${Number(provider.remaining || 0).toLocaleString("ko-KR")} · ${formatUsageReset(provider.resets_at)}`
          : "공급자 한도 미설정";
    groupHead.append(groupTitle, magazineElement("b", "", quota));
    const cards = magazineElement("div", "ai-model-provider-models", "");
    for (const item of providerModels) {
      const card = magazineElement("article", "ai-model-usage-card", "");
      const heading = magazineElement("header", "", "");
      const title = magazineElement("div", "", "");
      title.append(
        magazineElement("strong", "", item.vendor_label || item.provider),
        magazineElement("span", "", item.access_label || item.provider),
      );
      const state = magazineElement(
        "b",
        item.configured ? "is-configured" : "is-recorded",
        item.configured ? "운영 설정" : "이번 달 사용",
      );
      heading.append(title, state);
      const model = magazineElement("code", "", item.model || "모델 미확인");
      const usage = magazineElement("p", "ai-model-usage-primary", modelUsageLine(item));
      const workloads = magazineElement("div", "ai-model-workloads", "");
      for (const workload of item.workloads || []) {
        workloads.append(magazineElement("span", "", workload));
      }
      if (!workloads.childElementCount) {
        workloads.append(magazineElement("span", "", "저장 장부에서 확인"));
      }
      card.append(heading, model, usage, workloads);
      cards.append(card);
    }
    group.append(groupHead, cards);
    list.append(group);
  }
}

function aiRemainingCards(payload) {
  const providers = Object.fromEntries((payload.providers || []).map((item) => [item.provider, item]));
  const auxiliaries = Object.fromEntries((payload.auxiliary_models || []).map((item) => [item.provider, item]));
  const number = (value) => value === null || value === undefined || value === "" ? NaN : Number(value);
  const unknown = (provider) => ({ provider, percent: null, label: "확인 불가", detail: "잔여량 미확인", title: "사용량 정보를 확인하지 못했습니다." });
  const remaining = (provider, left, cap, detail, title, requestRatio = 1) => {
    if (!Number.isFinite(left) || !Number.isFinite(cap) || cap <= 0 || !Number.isFinite(requestRatio)) return unknown(provider);
    const percent = Math.max(0, Math.min(100, (left / cap) * 100, requestRatio * 100));
    return { provider, percent, detail, title,
      label: percent === 0 ? "소진" : percent < 1 ? "1% 미만" : `${Math.floor(percent)}% 남음` };
  };
  return ["openrouter", "gemini", "groq", "openai", "mistral"].map((provider) => {
    if (payload.status === "UNAVAILABLE") return unknown(provider);
    const item = providers[provider];
    if (provider === "gemini" || provider === "groq") {
      const aux = auxiliaries[provider];
      if (!aux) return unknown(provider);
      const cap = number(aux.daily_token_cap), left = Math.max(0, cap - number(aux.charged_tokens));
      const requests = number(aux.daily_request_cap), requestLeft = Math.max(0, requests - number(aux.request_count));
      const ratio = requests > 0 ? requestLeft / requests : NaN;
      return remaining(provider, left, cap, "일일 기준",
        `이 서비스의 일일 배정량 기준: 약 ${Math.floor(left).toLocaleString("ko-KR")}토큰 · ${requestLeft.toLocaleString("ko-KR")}회 남음. 공급자 계정 전체의 무료 잔여량과 다를 수 있습니다.`, ratio);
    }
    if (!item) return unknown(provider);
    if (provider === "openrouter") {
      const cap = number(item.operational_limit ?? item.limit);
      const left = number(item.operational_remaining ?? (cap - number(item.used)));
      return remaining(provider, left, cap, "일일 기준", `이 서비스가 사용하는 일일 운영 한도 기준: ${Math.max(0,left).toLocaleString("ko-KR")}회 남음`);
    }
    if (provider === "openai") {
      const cap = number(item.limit);
      const left = number(item.remaining ?? (cap - number(item.used) - number(item.reserved_tokens ?? 0)));
      return remaining(provider, left, cap, "일일 기준", `이 서비스의 일일 배정량 기준: 약 ${Math.max(0,left).toLocaleString("ko-KR")}토큰 남음`);
    }
    const cap = number(item.credit_usd), left = cap - number(item.cost_usd);
    return remaining(provider, left, cap, "이번 달 기준", `설정된 월간 이용 금액 기준: 약 $${Math.max(0,left).toFixed(2)} 남음`);
  });
}

function renderAiUsage(payload) {
  for (const item of aiRemainingCards(payload)) {
    const card = document.querySelector(`[data-usage-provider="${item.provider}"]`);
    if (!card) continue;
    card.querySelector(".ai-usage-value").textContent = item.label;
    card.querySelector(".ai-usage-meta span").textContent = item.detail;
    card.title = item.title;
    const known = item.percent !== null;
    card.classList.toggle("is-low", known && item.percent > 0 && item.percent < 10);
    card.classList.toggle("is-exhausted", known && item.percent === 0);
    const meter = card.querySelector(".ai-usage-meter");
    meter.classList.toggle("is-unknown", !known);
    meter.setAttribute("role", known ? "progressbar" : "img");
    meter.setAttribute("aria-label", `${card.querySelector("strong").textContent} · ${item.label} · ${item.detail}`);
    for (const [key,value] of [["aria-valuemin",0],["aria-valuemax",100],["aria-valuenow",Math.floor(item.percent || 0)]]) {
      if (known) meter.setAttribute(key,String(value));
      else meter.removeAttribute(key);
    }
    meter.querySelector("i").style.width = known ? `${item.percent}%` : "0%";
  }
  document.querySelector("#aiUsage").classList.toggle("is-unavailable", payload.status === "UNAVAILABLE");
}

function loadAiUsage() {
  return fetch("api/ai/usage", { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    })
    .then(renderAiUsage)
    .catch(() => renderAiUsage({ status: "UNAVAILABLE" }));
}

document.querySelector("#aiModelUsageOpen")?.addEventListener("click", () => {
  document.querySelector("#aiModelUsageDialog")?.showModal();
});
document.querySelector("#aiModelUsageClose")?.addEventListener("click", () => {
  document.querySelector("#aiModelUsageDialog")?.close();
});
document.querySelector("#aiModelUsageDialog")?.addEventListener("click", (event) => {
  if (event.target === event.currentTarget) event.currentTarget.close();
});

function loadLiveStatus() {
  if (liveStatusLoadPromise) return liveStatusLoadPromise;
  const getJson = (url, fallback) => fetch(url, { cache: "no-store" })
    .then((response) => response.ok ? response.json() : fallback)
    .catch(() => fallback);
  const historyParams = new URLSearchParams({
    limit: String(MEETING_HISTORY_INITIAL_LIMIT), offset: "0",
    include_latest_content: String(!meetingRailHistoryState.initialized),
  });
  const request = Promise.all([
    getJson("api/live/status", null),
    getJson("api/schedule/today", { items: [] }),
    getJson("api/live/broadcasts?" + historyParams, { items: [] }),
    getJson("api/executive/briefings?limit=5", { items: [] }),
    getJson("api/live/transcript/snapshot", { broadcasts: [] }),
  ]).then(([payload, schedule, history, executive, activeTranscript]) => {
      const checkedAt = Date.parse(payload?.checked_at || "");
      if (!Number.isFinite(checkedAt) || Date.now() - checkedAt > 120_000) {
        throw new Error("live status unavailable or stale");
      }
      const testExecutive = (activeTranscript.broadcasts || []).find(
        (item) => item.lifecycle_status === "LIVE" && item.source_system === "poc07.test",
      );
      if (testExecutive && payload.executive?.is_live !== true) {
        payload.executive = {
          ...(payload.executive || {}),
          ...testExecutive,
          is_live: true,
          institution: "EXECUTIVE",
          source_status: "TEST",
          place: "가상 국무회의 테스트",
        };
      }
      mergeOfficialLiveBroadcasts(payload, activeTranscript);
      const assemblyLive = renderDetectedAssemblyLive(payload.assembly.items || []);
      renderTodayScheduleBoard(payload, schedule);
      const merged = new Map(
        meetingRailHistoryState.items.map((item) => [item.broadcast_id, item]),
      );
      for (const item of history.items || []) merged.set(item.broadcast_id, item);
      meetingRailHistoryState.items = [...merged.values()].sort(
        (left, right) => new Date(right.detected_at) - new Date(left.detected_at),
      );
      meetingRailHistoryState.nextOffset = Math.max(
        meetingRailHistoryState.nextOffset, Number(history.next_offset || 0),
      );
      if (!meetingRailHistoryState.initialized) {
        meetingRailHistoryState.hasMore = Boolean(history.has_more);
        meetingRailHistoryState.initialized = true;
      } else if (!meetingRailHistoryState.endReached) {
        meetingRailHistoryState.hasMore = Boolean(history.has_more);
      }
      meetingRailHistoryState.statusPayload = payload;
      meetingRailHistoryState.executivePayload = executive;
      prefetchMeetingBriefs(meetingRailHistoryState.items);
      const meetingRail = document.querySelector("#reportBroadcastRows");
      const preservedAnchor = captureMeetingRailAnchor(meetingRail);
      const preserveReportScroll = !latestMeetingReportState.pending;
      renderBroadcastRows(
        payload, {
          ...history,
          items: meetingRailHistoryState.items,
          has_more: meetingRailHistoryState.hasMore,
        }, executive,
      );
      window.requestAnimationFrame(() => {
        if (meetingRail && preserveReportScroll) {
          restoreMeetingRailAnchor(meetingRail, preservedAnchor);
        }
      });
      const assemblyLiveCount = (payload.assembly.items || []).filter((item) => item.is_live).length;
      const liveCount = assemblyLiveCount + (payload.executive.is_live === true ? 1 : 0);
      const anyLive = liveCount > 0;
      const pendingBroadcasts = officialPendingBroadcasts(payload.assembly.items || []);
      const pendingLabel = pendingBroadcasts.map((item) =>
        `${item.short_name || item.committee_name} ${item.status_text}`,
      ).join(" · ");
      const liveLabel = assemblyLiveCount > 0
        ? ` 자동 기록 중 · 국회 LIVE ${assemblyLiveCount}건 · ${payload.assembly.source_time}`
        : payload.executive.is_live === true
          ? payload.executive.source_system === "poc07.test"
            ? ` 가상방송 테스트 중 · 공통 LIVE 처리 · ${payload.assembly.source_time}`
            : ` 자동 기록 중 · 국무회의 LIVE · ${payload.assembly.source_time}`
          : ` 현재 대상 생방송 없음${pendingLabel ? ` · 공식 중계 상태: ${pendingLabel}` : ""} · ${payload.assembly.source_time}`;
      liveNavTab?.classList.toggle("has-live", anyLive);
      const liveStatus = document.querySelector("#topLiveStatus");
      if (liveStatus) liveStatus.textContent = anyLive
        ? `생방송 ${liveCount}건`
        : pendingBroadcasts[0]?.status_text || "방송없음";
      if (liveNavTab) {
        liveNavTab.title = liveLabel.trim();
        liveNavTab.setAttribute("aria-label", anyLive ? `LIVE 방송 중. ${liveLabel}` : `LIVE. ${liveLabel}`);
      }
      selectInitialWorkspaceForLiveStatus(anyLive);
    })
    .catch(() => {
      liveNavTab?.classList.remove("has-live");
      const liveStatus = document.querySelector("#topLiveStatus");
      if (liveStatus) liveStatus.textContent = "상태 확인 필요";
      if (liveNavTab) {
        liveNavTab.title = "공식 방송 상태 확인 필요";
        liveNavTab.setAttribute("aria-label", "LIVE 방송 상태 확인 필요");
      }
    })
    .finally(() => {
      if (liveStatusLoadPromise === request) liveStatusLoadPromise = null;
    });
  liveStatusLoadPromise = request;
  return request;
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
document.querySelector("#liveOperationsExpandedClose")?.addEventListener("click", collapseLiveExpansion);
document.querySelector("#liveDraftEvidenceClose")?.addEventListener("click", () => {
  document.querySelector("#liveDraftEvidenceDialog")?.close();
});
loadLiveStatus();
loadAiUsage();
// 화면 복귀는 읽던 보고서·근거 선택·스크롤을 유지한다.
// 방송 상태는 아래의 주기적 갱신으로 확인하며 보고서를 다시 열지 않는다.
document.addEventListener("watch-test-live-update", (event) => {
  const payload = event.detail?.payload || null;
  const previousId = watchTestLiveState?.broadcast_id || null;
  if (!payload) {
    watchTestLiveState = null;
    if (previousId && String(assemblyTranscriptState.selectedBroadcastId || "") === String(previousId)) {
      collapseLiveExpansion();
    }
    loadLiveStatus();
    return;
  }
  const firstUpdate = !watchTestLiveState || watchTestLiveState.test_id !== payload.test_id;
  watchTestLiveState = payload;
  if (payload.status === "COMPLETED") {
    renderWatchTestLive(payload, { focus: false });
    loadLiveStatus();
  } else if (firstUpdate) {
    loadLiveStatus().then(() => renderWatchTestLive(payload, { focus: event.detail?.focus === true }));
  } else {
    renderWatchTestLive(payload, { focus: false });
  }
});
window.setInterval(loadLiveStatus, 30_000);
window.setInterval(loadAiUsage, 60_000);
function scrollMeetingRailByOneCard(rail, direction) {
  const card = rail?.querySelector(".meeting-card.broadcast-row");
  if (!card) return;
  const styles = window.getComputedStyle(rail);
  const gap = Number.parseFloat(styles.columnGap || styles.gap || "0") || 0;
  const cardStep = card.getBoundingClientRect().width + gap;
  rail.scrollBy({ left: direction * cardStep, behavior: "smooth" });
}

function meetingRailNearLoadedEnd(rail) {
  const card = rail?.querySelector(".meeting-card.broadcast-row");
  if (!card) return false;
  const styles = window.getComputedStyle(rail);
  const gap = Number.parseFloat(styles.columnGap || styles.gap || "0") || 0;
  const threshold = (card.getBoundingClientRect().width + gap) * 2;
  return rail.scrollWidth - rail.clientWidth - rail.scrollLeft <= threshold;
}

async function loadMoreMeetingHistory() {
  if (
    meetingRailHistoryState.loading
    || !meetingRailHistoryState.hasMore
    || meetingRailHistoryState.endReached
  ) return false;
  meetingRailHistoryState.loading = true;
  const rail = document.querySelector("#reportBroadcastRows");
  rail?.setAttribute("aria-busy", "true");
  try {
    const params = new URLSearchParams({
      limit: String(MEETING_HISTORY_PAGE_SIZE),
      offset: String(meetingRailHistoryState.nextOffset),
    });
    const response = await fetch("api/live/broadcasts?" + params, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const page = await response.json();
    const before = meetingRailHistoryState.items.length;
    const merged = new Map(
      meetingRailHistoryState.items.map((item) => [item.broadcast_id, item]),
    );
    for (const item of page.items || []) merged.set(item.broadcast_id, item);
    meetingRailHistoryState.items = [...merged.values()].sort(
      (left, right) => new Date(right.detected_at) - new Date(left.detected_at),
    );
    meetingRailHistoryState.nextOffset = Number(
      page.next_offset ?? meetingRailHistoryState.nextOffset,
    );
    meetingRailHistoryState.hasMore = Boolean(page.has_more);
    meetingRailHistoryState.endReached = !meetingRailHistoryState.hasMore;
    const preservedAnchor = captureMeetingRailAnchor(rail);
    renderBroadcastRows(
      meetingRailHistoryState.statusPayload,
      {
        ...page,
        items: meetingRailHistoryState.items,
        has_more: meetingRailHistoryState.hasMore,
      },
      meetingRailHistoryState.executivePayload,
    );
    const refreshed = document.querySelector("#reportBroadcastRows");
    restoreMeetingRailAnchor(refreshed, preservedAnchor);
    return meetingRailHistoryState.items.length > before;
  } catch (_error) {
    return false;
  } finally {
    meetingRailHistoryState.loading = false;
    document.querySelector("#reportBroadcastRows")?.removeAttribute("aria-busy");
  }
}

for (const [selector, direction] of [["#meetingRailPrev", -1], ["#meetingRailNext", 1]]) {
  document.querySelector(selector)?.addEventListener("click", async () => {
    const rail = document.querySelector("#reportBroadcastRows");
    if (direction > 0 && meetingRailNearLoadedEnd(rail)) {
      await loadMoreMeetingHistory();
    }
    scrollMeetingRailByOneCard(rail, direction);
  });
}

for (const [selector, direction] of [["#todaySchedulePrev", -1], ["#todayScheduleNext", 1]]) {
  document.querySelector(selector)?.addEventListener("click", () => moveTodaySchedule(direction, true));
}

document.querySelector("#todayScheduleViewport")?.addEventListener("keydown", (event) => {
  if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
  event.preventDefault();
  moveTodaySchedule(event.key === "ArrowUp" ? -1 : 1, true);
});

// The guide lives in its own document so its print styles cannot affect the service.
const userGuideDialog = document.querySelector("#userGuideDialog");
document.querySelector(".usage-guide-button")?.addEventListener("click", () => {
  const frame = document.querySelector("#userGuideFrame");
  if (!frame.getAttribute("src")) frame.src = "assets/user-guide/index.html?embedded=1&v=20261020-quick-sheet-1";
  if (!userGuideDialog.open) userGuideDialog.showModal();
});
document.querySelector("#userGuideDialogClose")?.addEventListener("click", () => userGuideDialog.close());
userGuideDialog?.addEventListener("click", (event) => {
  if (event.target === userGuideDialog) {
    const bounds = userGuideDialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) userGuideDialog.close();
  }
});
