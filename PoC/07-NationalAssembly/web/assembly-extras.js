(() => {
  const mount = document.querySelector("#assemblyExtrasApp");
  if (!mount) return;

  const grid = mount.querySelector("#assemblyCalendarGrid");
  const monthLabel = mount.querySelector("#assemblyCalendarMonth");
  const meta = mount.querySelector("#assemblyCalendarMeta");
  const agendaTitle = mount.querySelector("#assemblyDayAgendaTitle");
  const agendaCount = mount.querySelector("#assemblyDayAgendaCount");
  const agendaList = mount.querySelector("#assemblyDayAgendaList");
  const filterButtons = [...mount.querySelectorAll("[data-calendar-filter]")];
  const state = {
    month: new Date(new Date().getFullYear(), new Date().getMonth(), 1),
    selected: localIso(new Date()),
    filter: "all",
    items: [],
    loadedKey: "",
    loading: false,
  };
  const partyColors = ["#174f9b", "#e3545d", "#e6a83a", "#32a27b", "#7256c7", "#3594b5", "#8a6c4a", "#7a8798", "#b85c9b"];
  const hemicycleState = { payload: null, selected: new Set() };
  const ontologyState = {
    payload: null,
    nodes: [],
    selected: null,
    activeDomain: "",
    hover: null,
    zoom: 1,
    panX: 0,
    panY: 0,
    dragging: false,
    moved: false,
    pointerX: 0,
    pointerY: 0,
    animation: 0,
    wired: false,
    scene3d: null,
    force2d: false,
  };
  const svgNamespace = "http://www.w3.org/2000/svg";
  let ontology3dLoader = null;

  async function loadOntology3DEngine() {
    if (window.AssemblyOntology3D) return window.AssemblyOntology3D;
    if (!ontology3dLoader) {
      ontology3dLoader = import("./ontology-starmap.js?v=20260917-4")
        .then(() => window.AssemblyOntology3D);
    }
    return ontology3dLoader;
  }

  function element(tag, className = "", text = "") {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== "") node.textContent = text;
    return node;
  }

  function localIso(value) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return year + "-" + month + "-" + day;
  }

  function parseLocal(value) {
    const parts = String(value || "").split("-").map(Number);
    return new Date(parts[0], (parts[1] || 1) - 1, parts[2] || 1);
  }

  function displayRange(month) {
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const last = new Date(month.getFullYear(), month.getMonth() + 1, 0);
    const start = new Date(first);
    start.setDate(first.getDate() - first.getDay());
    const end = new Date(last);
    end.setDate(last.getDate() + (6 - last.getDay()));
    return { start, end };
  }

  function visibleItems() {
    const committeeItems = state.items.filter(isCommitteeSchedule);
    const executiveItems = state.items.filter(isExecutiveSchedule);
    const visibleCommittees = state.filter === "target"
      ? committeeItems.filter((item) => Boolean(item.is_target_committee))
      : committeeItems;
    return uniqueSchedules([...executiveItems, ...visibleCommittees]);
  }

  function isCommitteeSchedule(item) {
    return String(item?.schedule_kind || "") === "위원회";
  }

  function isExecutiveSchedule(item) {
    return String(item?.institution || "") === "EXECUTIVE"
      || String(item?.schedule_kind || "") === "국무회의";
  }

  function isMemberOfficeSchedule(item) {
    return String(item?.schedule_kind || "") === "국회행사"
      && /의원실/.test(String(item?.host_name || ""));
  }

  function uniqueSchedules(items) {
    const seen = new Set();
    return items.filter((item) => {
      const key = [
        item.scheduled_date, item.start_time || item.time_text,
        item.title, item.committee_name, item.host_name, item.place,
      ].map((value) => String(value || "").trim()).join("|");
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }

  function groupedItems() {
    const groups = new Map();
    for (const item of visibleItems()) {
      const key = String(item.scheduled_date || "");
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    }
    return groups;
  }

  function eventLabel(item) {
    if (isExecutiveSchedule(item)) return "국무회의";
    return String(item.committee_name || item.host_name || item.schedule_kind || "국회 일정");
  }

  function isUpcomingBroadcast(item) {
    if (!item?.broadcast_scheduled || item.broadcast_status === "LIVE") return false;
    const start = scheduleStartDate(item);
    if (start) return start > new Date();
    return String(item.scheduled_date || "") >= localIso(new Date());
  }

  function isCompletedBroadcast(item) {
    return item?.broadcast_status === "COMPLETED";
  }

  function timeLabel(item) {
    const value = String(item.start_time || item.time_text || "").slice(0, 5);
    return /^\d{2}:\d{2}$/.test(value) ? value : "시간 미정";
  }

  function scheduleStartDate(item) {
    const dateText = String(item?.scheduled_date || "");
    const match = String(item?.start_time || item?.time_text || "").match(/\d{1,2}:\d{2}/);
    if (!dateText || !match) return null;
    const timeText = match[0].padStart(5, "0");
    const parsed = new Date(dateText + "T" + timeText + ":00");
    return Number.isNaN(parsed.valueOf()) ? null : parsed;
  }

  function formatSelectedDate(value) {
    return new Intl.DateTimeFormat("ko-KR", {
      year: "numeric", month: "long", day: "numeric", weekday: "short",
    }).format(parseLocal(value));
  }

  function renderAgenda() {
    const selectedItems = state.items.filter(
      (item) => String(item.scheduled_date || "") === state.selected,
    );
    const memberItems = uniqueSchedules(selectedItems.filter(isMemberOfficeSchedule));
    const committeeItems = uniqueSchedules(selectedItems.filter(isCommitteeSchedule));
    const executiveItems = uniqueSchedules(selectedItems.filter(isExecutiveSchedule));
    const items = [...executiveItems, ...committeeItems, ...memberItems];
    agendaTitle.textContent = formatSelectedDate(state.selected);
    agendaCount.textContent = items.length
      ? `국무회의 ${executiveItems.length} · 위원회 ${committeeItems.length} · 의원실 ${memberItems.length}`
      : "일정 없음";
    agendaList.replaceChildren();
    if (!items.length) {
      agendaList.append(element("p", "assembly-agenda-empty", "저장된 국무회의·위원회·의원실 일정이 없습니다."));
      return;
    }
    for (const [kind, sectionItems] of [["국무회의 일정", executiveItems], ["위원회 일정", committeeItems], ["의원실 일정", memberItems]]) {
      if (!sectionItems.length) continue;
      const section = element("section", "assembly-agenda-section");
      const sectionHead = element("header", "");
      sectionHead.append(element("strong", "", kind), element("small", "", sectionItems.length + "건"));
      section.append(sectionHead);
      for (const item of sectionItems) {
        const card = element("article", "assembly-agenda-card");
        const time = element("time", "", timeLabel(item));
        const copy = element("div", "");
        const tags = element("div", "assembly-agenda-tags");
        tags.append(element("span", isExecutiveSchedule(item) ? "is-executive" : item.is_target_committee ? "is-target" : "", eventLabel(item)));
        if (isUpcomingBroadcast(item)) tags.append(element("span", "is-broadcast", "● 방송예정"));
        if (item.broadcast_status === "LIVE") tags.append(element("span", "is-live", "● 생방송"));
        if (isCompletedBroadcast(item)) tags.append(element("span", "is-completed", "● 방송 완료"));
        if (item.meeting_type) tags.append(element("span", "", String(item.meeting_type)));
        copy.append(
          tags,
          element("h4", "", String(item.title || "제목 미확인")),
          element("p", "", [item.place || "장소 미표기", item.host_name || ""].filter(Boolean).join(" · ")),
        );
        card.append(time, copy);
        if (item.source_url) {
          const link = element("a", "", "공식 출처 ↗");
          link.href = String(item.source_url);
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          card.append(link);
        }
        section.append(card);
      }
      agendaList.append(section);
    }
  }

  function renderCalendar() {
    const range = displayRange(state.month);
    const groups = groupedItems();
    const today = localIso(new Date());
    monthLabel.textContent = state.month.getFullYear() + "년 " + (state.month.getMonth() + 1) + "월";
    grid.replaceChildren();
    for (let cursor = new Date(range.start); cursor <= range.end; cursor.setDate(cursor.getDate() + 1)) {
      const date = new Date(cursor);
      const key = localIso(date);
      const events = groups.get(key) || [];
      const button = element("button", "assembly-calendar-day");
      button.type = "button";
      button.dataset.date = key;
      button.setAttribute("aria-label", formatSelectedDate(key) + (events.length ? ", 일정 " + events.length + "개" : ""));
      if (date.getMonth() !== state.month.getMonth()) button.classList.add("is-outside");
      if (key === today) button.classList.add("is-today");
      if (key === state.selected) button.classList.add("is-selected");
      if (events.length) button.classList.add("has-events");
      const head = element("span", "assembly-calendar-date", String(date.getDate()));
      if (key === today) head.append(element("em", "", "오늘"));
      button.append(head);
      const eventList = element("span", "assembly-calendar-events");
      for (const item of events.slice(0, 2)) {
        const classes = [
          isExecutiveSchedule(item) ? "is-executive" : item.is_target_committee ? "is-target" : "",
          isUpcomingBroadcast(item) ? "is-broadcast" : "",
          item.broadcast_status === "LIVE" ? "is-live" : "",
          isCompletedBroadcast(item) ? "is-completed" : "",
        ].filter(Boolean).join(" ");
        const prefix = item.broadcast_status === "LIVE"
          ? "● 생방송 · "
          : isUpcomingBroadcast(item)
            ? "● 방송예정 · "
            : isCompletedBroadcast(item) ? "● 방송 완료 · " : "";
        const event = element("i", classes, prefix + timeLabel(item) + " " + eventLabel(item));
        eventList.append(event);
      }
      if (events.length > 2) eventList.append(element("b", "", "+" + (events.length - 2) + "개 더보기"));
      button.append(eventList);
      button.addEventListener("click", () => {
        state.selected = key;
        renderCalendar();
      });
      grid.append(button);
    }
    renderAgenda();
  }

  async function loadCalendar(force = false) {
    const range = displayRange(state.month);
    const key = localIso(range.start) + ":" + localIso(range.end);
    if (!force && state.loadedKey === key) {
      renderCalendar();
      return;
    }
    if (state.loading) return;
    state.loading = true;
    meta.textContent = "공식 일정 저장소를 확인하는 중입니다.";
    try {
      const params = new URLSearchParams({ start: localIso(range.start), end: localIso(range.end) });
      const response = await fetch("api/schedule/calendar?" + params.toString(), { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("calendar");
      const payload = await response.json();
      state.items = payload.items || [];
      state.loadedKey = key;
      const committeeItems = uniqueSchedules(state.items.filter(isCommitteeSchedule));
      const memberItems = uniqueSchedules(state.items.filter(isMemberOfficeSchedule));
      const executiveItems = uniqueSchedules(state.items.filter(isExecutiveSchedule));
      meta.textContent = `국무회의 ${executiveItems.length.toLocaleString()}건 · 위원회 ${committeeItems.length.toLocaleString()}건 · 의원실 ${memberItems.length.toLocaleString()}건 · 공식 일정 기준`;
      const relevantItems = [...executiveItems, ...committeeItems, ...memberItems];
      const hasSelected = relevantItems.some((item) => String(item.scheduled_date) === state.selected);
      const currentMonth = new Date().getFullYear() === state.month.getFullYear() && new Date().getMonth() === state.month.getMonth();
      if (!hasSelected && !currentMonth) {
        state.selected = relevantItems[0]?.scheduled_date || localIso(new Date(state.month.getFullYear(), state.month.getMonth(), 1));
      }
      renderCalendar();
    } catch (_) {
      state.items = [];
      state.loadedKey = key;
      meta.textContent = "공식 일정을 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.";
      renderCalendar();
    } finally {
      state.loading = false;
    }
  }

  function factCard(label, rows) {
    const card = element("section", "assembly-fact-card");
    card.append(element("span", "", label));
    const values = element("div", "");
    for (const row of rows || []) {
      const item = element("p", "");
      item.append(element("b", "", String(row.count)), element("small", "", String(row.label)));
      values.append(item);
    }
    card.append(values);
    return card;
  }

  function insightDate(value) {
    const parsed = new Date(String(value || "").replace(/\./g, "-").replace(/-+$/, ""));
    if (Number.isNaN(parsed.getTime())) return String(value || "날짜 미확인");
    return new Intl.DateTimeFormat("ko-KR", { month: "short", day: "numeric" }).format(parsed);
  }

  function insightSourceLink(value) {
    if (!value) return null;
    const link = element("a", "", "공식 근거 ↗");
    link.href = String(value);
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    return link;
  }

  function makeInsightInteractive(node, open) {
    node.classList.add("is-clickable");
    node.tabIndex = 0;
    node.setAttribute("role", "button");
    node.addEventListener("click", (event) => {
      if (event.target.closest("a, button")) return;
      open();
    });
    node.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      if (event.target.closest("a, button")) return;
      event.preventDefault();
      open();
    });
  }

  function openInsightDialog(eyebrow, title, meta, content) {
    const dialog = document.querySelector("#assemblyInsightDialog");
    const body = document.querySelector("#assemblyInsightDialogBody");
    if (!dialog || !body) return;
    document.querySelector("#assemblyInsightDialogEyebrow").textContent = eyebrow;
    document.querySelector("#assemblyInsightDialogTitle").textContent = title;
    document.querySelector("#assemblyInsightDialogMeta").textContent = meta || "";
    body.replaceChildren(content);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function insightMetaTags(values) {
    const tags = element("div", "assembly-insight-dialog-tags");
    for (const value of values.filter(Boolean)) {
      tags.append(element("span", "", String(value)));
    }
    return tags;
  }

  function comparisonPanel(kind, title, summary, metaValues, sourceUrl) {
    const panel = element("section", "assembly-insight-compare-panel is-" + kind);
    panel.append(
      element("span", "", kind === "executive" ? "정부 · 국무회의 공식 자료" : "국회 · 회의 보고서"),
      element("h3", "", title),
      insightMetaTags(metaValues),
      element("p", "", summary || "저장된 요약이 없습니다."),
    );
    const link = insightSourceLink(sourceUrl);
    if (link) panel.append(link);
    return panel;
  }

  function openPolicyComparison(item) {
    const executive = item.executive_evidence || {};
    const legislative = item.legislative_evidence || {};
    const content = element("div", "assembly-insight-comparison");
    const basis = element("section", "assembly-insight-match-basis");
    basis.append(
      element("strong", "", "같은 흐름으로 본 근거"),
      insightMetaTags([
        ...(item.shared_evidence_keywords || []).slice(0, 5),
        ...(item.shared_ministries || []).slice(0, 2),
      ]),
      element("p", "", "구체 주제명과 핵심 고유어가 직접 일치한 잠정 연결이며 인과관계를 뜻하지 않습니다."),
    );
    const columns = element("div", "assembly-insight-compare-grid");
    columns.append(
      comparisonPanel(
        "executive",
        executive.agenda_topic || executive.meeting_title || "정부 공식 안건",
        executive.summary,
        [
          insightDate(executive.published_date),
          ...(executive.ministries || []).slice(0, 3),
        ],
        executive.source_url,
      ),
      comparisonPanel(
        "legislative",
        item.topic || legislative.committee_name || "국회 논의 주제",
        legislative.text,
        [insightDate(legislative.conference_date), legislative.committee_name],
        legislative.source_url,
      ),
    );
    content.append(basis, columns);
    openInsightDialog(
      "POLICY FLOW COMPARISON",
      item.topic || "정부·국회 정책 흐름 비교",
      item.temporal_label || "정부와 국회의 저장 요약 비교",
      content,
    );
  }

  function openTopicSummary(item, mode) {
    const latest = item.latest_meeting || {};
    const content = element("div", "assembly-insight-summary");
    const summary = element("section", "");
    const status = mode === "trend" ? item.trend_status : item.transition_label;
    summary.append(
      insightMetaTags([
        status,
        ...(item.ministries || []).slice(0, 3),
        latest.committee_name,
        insightDate(latest.date),
      ]),
      element("h3", "", item.topic || "정책 주제"),
      element("p", "", item.summary || "저장된 요약이 없습니다."),
    );
    if (mode === "trend") {
      summary.append(element(
        "small",
        "",
        "최근 14일 " + Number(item.current_meeting_count || 0)
          + "회 · 이전 14일 " + Number(item.previous_meeting_count || 0) + "회",
      ));
    } else if (item.transition_stage !== "BILL_LINKED") {
      summary.append(element(
        "small",
        "is-caution",
        "공식 의안과 직접 연결되지 않은 보고서상 단계입니다. 의안 발의로 해석하지 않습니다.",
      ));
    }
    content.append(summary);
    if (mode === "institution") {
      const flow = element("section", "assembly-institution-detail");
      const discussionBlock = element("div", "assembly-institution-block is-discussion");
      discussionBlock.append(
        element("span", "assembly-institution-kicker", "1 · 논의 관측"),
        element("h4", "", "어떤 회의에서 논의됐나"),
      );
      const discussions = element("div", "assembly-institution-events");
      for (const discussion of item.discussion_events || []) {
        const event = element("article", "");
        event.append(
          element("time", "", insightDate(discussion.date)),
          element("strong", "", discussion.meeting_title || discussion.committee_name || "회의"),
          element("b", "", discussion.topic || item.topic || "논의 주제"),
          element("p", "", discussion.summary || "저장된 회의 보고서에서 논의가 확인됐습니다."),
          element("small", "", `${discussion.committee_name || "소관 확인 중"} · 근거 ${Number(discussion.evidence_count || 0).toLocaleString()}건`),
        );
        discussions.append(event);
      }
      if (!discussions.children.length) {
        discussions.append(element("p", "assembly-institution-empty", "회의 이력을 확인하는 중입니다."));
      }
      discussionBlock.append(discussions);
      flow.append(discussionBlock);

      const bills = item.bills || [];
      const billBlock = element("div", "assembly-institution-block is-bill");
      billBlock.append(
        element("span", "assembly-institution-kicker", "2 · 의안 연결"),
        element("h4", "", "어떤 의안으로 상정됐나"),
      );
      if (!bills.length) {
        billBlock.append(element(
          "p", "assembly-institution-empty",
          Number(item.rejected_bill_link_count || 0) > 0
            ? "주제와 일치하지 않는 안건 연결을 제외했습니다. 공식 의안번호를 확인하는 중입니다."
            : "직접 연결된 공식 의안이 없습니다. 발의 또는 상정을 의미하지 않습니다.",
        ));
      }
      for (const bill of bills) {
        const billCard = element("article", "assembly-institution-bill");
        billCard.append(
          insightMetaTags([bill.bill_number ? `의안 ${bill.bill_number}` : "공식 의안", "주제명 교차검증"]),
          element("h5", "", bill.bill_name || bill.agenda_name || "연결 의안"),
          element("p", "", bill.agenda_name || "회의 안건에서 직접 연결됐습니다."),
        );
        const sourceLink = insightSourceLink(bill.official_url);
        if (sourceLink) billCard.append(sourceLink);
        billBlock.append(billCard);
      }
      flow.append(billBlock);

      const processBlock = element("div", "assembly-institution-block is-process");
      processBlock.append(
        element("span", "assembly-institution-kicker", "3 · 처리 절차와 현재 상태"),
        element("h4", "", "어떤 절차를 거쳐 어디까지 왔나"),
      );
      if (!bills.length) {
        processBlock.append(element("p", "assembly-institution-empty", "공식 의안이 확인되면 발의·위원회·본회의 처리 이력이 이곳에 이어집니다."));
      }
      for (const bill of bills) {
        const process = element("div", "assembly-bill-process");
        for (const step of bill.process_steps || []) {
          const stepNode = element("div", step.status === "CURRENT" ? "is-current" : "is-done");
          stepNode.append(
            element("span", "", step.status === "CURRENT" ? "현재" : "완료"),
            element("strong", "", step.label || "처리 단계"),
            element("time", "", insightDate(step.date)),
            element("p", "", step.detail || "공식 처리 정보 확인 중"),
          );
          process.append(stepNode);
        }
        const current = element("aside", "assembly-bill-current");
        current.append(
          element("span", "", "현재 상태"),
          element("strong", "", bill.current_status || "처리 단계 수집 중"),
          element("small", "", bill.status_as_of ? `기준 ${insightDate(bill.status_as_of)}` : "공식 의안 데이터 최신 수집 기준"),
        );
        processBlock.append(process, current);
      }
      flow.append(processBlock);
      content.append(flow);
    }
    openInsightDialog(
      mode === "trend" ? "ISSUE TREND SUMMARY" : "INSTITUTIONALIZATION SUMMARY",
      item.topic || "정책 주제 요약",
      mode === "trend" ? "지속·급증·최근 미관측 판단 요약" : "논의→제도화 단계 요약",
      content,
    );
  }

  function renderPolicyTimeline(payload) {
    const target = mount.querySelector("#assemblyPolicyTimeline");
    target.replaceChildren();
    const items = (payload.items || []).slice(0, 5);
    if (!items.length) {
      target.append(element("p", "assembly-insight-empty", "정부와 국회에서 공통 근거가 확인된 정책 흐름이 없습니다."));
      return;
    }
    target.append(element(
      "p",
      "assembly-insight-guide",
      "구체 주제명과 핵심 고유어가 함께 맞는 정부·국회 근거만 연결합니다.",
    ));
    for (const item of items) {
      const card = element("section", "assembly-policy-timeline-row");
      const head = element("header", "");
      head.append(element("strong", "", item.topic), element("small", "", item.temporal_label || "시간 관계 확인 필요"));
      const steps = element("div", "assembly-policy-steps");
      const executive = item.executive_evidence || {};
      const executiveStep = element("div", "is-executive");
      executiveStep.append(
        element("span", "", "정부 · " + insightDate(executive.published_date)),
        element("b", "", executive.agenda_topic || executive.meeting_title || "공식 안건"),
        element("p", "", executive.summary || "공식 안건 근거가 확인됐습니다."),
      );
      const executiveLink = insightSourceLink(executive.source_url);
      if (executiveLink) executiveStep.append(executiveLink);
      const legislative = item.legislative_evidence || {};
      const legislativeStep = element("div", "is-legislature");
      legislativeStep.append(
        element("span", "", "국회 · " + insightDate(legislative.conference_date)),
        element("b", "", legislative.committee_name || "위원회"),
        element("p", "", legislative.text || "공식 정책 발언이 확인됐습니다."),
      );
      const legislativeLink = insightSourceLink(legislative.source_url);
      if (legislativeLink) legislativeStep.append(legislativeLink);
      steps.append(executiveStep, legislativeStep);
      const bills = item.bills || [];
      if (bills.length) {
        const billStep = element("div", "is-bill");
        billStep.append(
          element("span", "", "제도화"),
          element("b", "", bills[0].bill_name || bills[0].agenda_name || "연결 의안"),
          element("p", "", bills[0].plenary_result || bills[0].committee_result || bills[0].process_stage_code || "처리 단계 확인 중"),
        );
        const billLink = insightSourceLink(bills[0].official_url);
        if (billLink) billStep.append(billLink);
        steps.append(billStep);
      }
      card.append(head, steps);
      makeInsightInteractive(card, () => openPolicyComparison(item));
      target.append(card);
    }
  }

  function renderIssueTrends(payload) {
    const target = mount.querySelector("#assemblyIssueTrends");
    target.replaceChildren();
    const rows = (payload.items || []).slice(0, 8);
    if (!rows.length) {
      target.append(element("p", "assembly-insight-empty", "비교할 구체 논의 주제가 아직 없습니다."));
      return;
    }
    target.append(element(
      "p",
      "assembly-insight-guide",
      "신규: 이전 14일 0회 · 급증: 이전 1회 이상이며 최근 3회 이상·2배 이상",
    ));
    for (const item of rows) {
      const status = item.trend_status || "관측 부족";
      const latest = item.latest_meeting || {};
      const ministry = (item.ministries || []).slice(0, 2).join(" · ");
      const context = [ministry, latest.committee_name, insightDate(latest.date)].filter(Boolean).join(" · ");
      const row = element("section", "assembly-trend-row is-" + status.replace(/\s/g, "-"));
      row.append(
        element("span", "", status),
        element("strong", "", item.topic),
        element("b", "", `최근 ${Number(item.current_meeting_count || 0)}회 · 이전 ${Number(item.previous_meeting_count || 0)}회`),
        element("p", "", item.summary || "회의 보고서에서 구체 주제가 확인됐습니다."),
        element("small", "", `${context || "소관 확인 중"} · 누적 ${Number(item.meeting_count || 0).toLocaleString()}개 회의 · 근거 발언 ${Number(item.mention_count || 0).toLocaleString()}건`),
      );
      makeInsightInteractive(row, () => openTopicSummary(item, "trend"));
      target.append(row);
    }
  }

  function renderInstitutionFlow(payload) {
    const target = mount.querySelector("#assemblyInstitutionFlow");
    target.replaceChildren();
    const stageOrder = { BILL_LINKED: 4, DECISION_MENTIONED: 3, FORMALIZATION_MENTIONED: 2, FOLLOW_UP_TASK: 1 };
    const items = [...(payload.items || [])]
      .filter((item) => item.transition_stage !== "DISCUSSION")
      .sort((a, b) => (stageOrder[b.transition_stage] || 0) - (stageOrder[a.transition_stage] || 0)
        || Number(b.current_meeting_count || 0) - Number(a.current_meeting_count || 0))
      .slice(0, 8);
    if (!items.length) {
      target.append(element("p", "assembly-insight-empty", "후속 과제·의결·공식 의안으로 전환된 구체 주제가 아직 없습니다."));
      return;
    }
    target.append(element(
      "p",
      "assembly-insight-guide",
      "‘보고서상’ 단계는 발의 확인이 아닙니다. 의안번호가 직접 연결된 경우만 공식 의안입니다.",
    ));
    for (const item of items) {
      const row = element("section", "assembly-institution-row");
      const copy = element("div", "");
      copy.append(
        element("strong", "", item.topic),
        element("p", "", item.summary || "회의 보고서에서 전환 근거가 확인됐습니다."),
        element("small", "", `${(item.ministries || []).join(" · ") || item.latest_meeting?.committee_name || "소관 확인 중"} · ${Number(item.meeting_count || 0).toLocaleString()}개 회의`),
      );
      const stage = element("div", "assembly-institution-stage");
      stage.append(element("span", "is-done", item.transition_label || "논의 확인"));
      const bills = item.bills || [];
      if (!bills.length && item.transition_stage === "DECISION_MENTIONED") {
        stage.append(element("span", "is-waiting", "의안번호 미연결 · 발의 확인 아님"));
      } else if (!bills.length && item.transition_stage === "FORMALIZATION_MENTIONED") {
        stage.append(element("span", "is-waiting", "법안 언급 · 발의 확인 아님"));
      } else if (!bills.length && item.transition_stage === "FOLLOW_UP_TASK") {
        const task = (item.tasks || [])[0];
        if (task) stage.append(element("span", "is-task", task));
        stage.append(element("span", "is-waiting", "후속 이행 확인 필요"));
      } else {
        const bill = bills[0];
        stage.append(
          element("span", "is-done", "의안 " + bills.length + "건"),
          element("span", bill.plenary_result || bill.committee_result ? "is-done" : "is-waiting", bill.plenary_result || bill.committee_result || bill.process_stage_code || "처리 중"),
        );
        const link = insightSourceLink(bill.official_url);
        if (link) stage.append(link);
      }
      row.append(copy, stage);
      makeInsightInteractive(row, () => openTopicSummary(item, "institution"));
      target.append(row);
    }
  }

  function ontologyMetric(label, value, className = "") {
    const item = element("div", className);
    item.append(element("span", "", label), element("strong", "", value));
    return item;
  }

  function renderOntologyMetrics(payload) {
    const target = document.querySelector("#assemblyOntologyMetrics");
    const metrics = payload.metrics || {};
    const coverage = Math.round(Number(metrics.ontology_coverage || 0) * 1000) / 10;
    target.replaceChildren(
      ontologyMetric("정책 영역", Number((payload.domains || []).length).toLocaleString()),
      ontologyMetric("세부 분류", Number((payload.groups || []).length).toLocaleString()),
      ontologyMetric("검증 보고서", Number(metrics.report_count || 0).toLocaleString()),
      ontologyMetric("분류된 주제", `${Number(metrics.ontology_topic_count || 0).toLocaleString()}건`),
      ontologyMetric("온톨로지 적용률", `${coverage.toFixed(1)}%`, coverage >= 95 ? "is-good" : "is-review"),
      ontologyMetric("무결성 오류", `${Number(metrics.integrity_failure_count || 0).toLocaleString()}건`, Number(metrics.integrity_failure_count || 0) ? "is-review" : "is-good"),
    );
  }

  function renderOntologyDetail(node) {
    const target = document.querySelector("#assemblyOntologyDetail");
    const payload = ontologyState.payload || {};
    const metrics = payload.metrics || {};
    const domains = payload.domains || [];
    target.replaceChildren();
    if (!node || node.type === "root") {
      const coverage = Math.round(Number(metrics.ontology_coverage || 0) * 1000) / 10;
      target.style.setProperty("--detail-color", "#5eead4");
      target.append(
        element("span", "", String(payload.version || "ONTOLOGY").replace("assembly-meeting-topic-grouping/", "ONTOLOGY ").toUpperCase()),
        element("h3", "", payload.root?.title || "국정 온톨로지"),
        element("p", "", "회의 보고서의 세부 주제를 정책 대상으로 묶는 현재 운영 분류 체계입니다."),
      );
      const stats = element("dl");
      stats.append(
        element("dt", "", "정책 영역"), element("dd", "", `${domains.length}개`),
        element("dt", "", "세부 분류"), element("dd", "", `${(payload.groups || []).length}개`),
        element("dt", "", "전체 세부 주제"), element("dd", "", Number(metrics.topic_count || 0).toLocaleString() + "건"),
        element("dt", "", "온톨로지 적용률"), element("dd", "", coverage + "%"),
        element("dt", "", "동적·미분류"), element("dd", "", Number(metrics.unclassified_topic_count || 0).toLocaleString() + "건"),
      );
      const status = element("div", Number(metrics.integrity_failure_count || 0) ? "assembly-ontology-status is-review" : "assembly-ontology-status");
      status.textContent = Number(metrics.integrity_failure_count || 0)
        ? `무결성 재검토 ${Number(metrics.integrity_failure_count).toLocaleString()}개 보고서`
        : "모든 세부 주제가 중복·누락 없이 한 번씩 묶였습니다.";
      target.append(stats, status);
      return;
    }
    const domain = domains.find((item) => item.key === (node.domain_key || node.key));
    const color = domain?.color || "#5eead4";
    target.style.setProperty("--detail-color", color);
    if (node.type === "domain") {
      const children = (payload.groups || []).filter((item) => item.domain_key === node.key);
      target.append(
        element("span", "", "POLICY DOMAIN"),
        element("h3", "", node.title),
        element("p", "", "정책 대상 분류가 연결되는 상위 영역입니다."),
      );
      const stats = element("dl");
      stats.append(
        element("dt", "", "세부 분류"), element("dd", "", `${children.length}개`),
        element("dt", "", "적용 주제"), element("dd", "", Number(node.topic_count || 0).toLocaleString() + "건"),
      );
      target.append(stats, element("h4", "", "연결된 분류"));
      const tags = element("div", "assembly-ontology-keywords");
      children.forEach((item) => {
        const button = element("button", "", item.title);
        button.type = "button";
        button.title = `${item.title} 세부 분류 선택`;
        button.addEventListener("click", () => {
          if (ontologyState.scene3d?.select(item.key)) return;
          ontologyState.selected = { ...item, type: "group" };
          ontologyState.activeDomain = item.domain_key;
          renderOntologyDetail(ontologyState.selected);
        });
        tags.append(button);
      });
      target.append(tags);
      return;
    }
    target.append(
      element("span", "", "POLICY TARGET"),
      element("h3", "", node.title),
      element("p", "", domain?.title || "정책 영역"),
    );
    const stats = element("dl");
    stats.append(
      element("dt", "", "적용 세부 주제"), element("dd", "", Number(node.topic_count || 0).toLocaleString() + "건"),
      element("dt", "", "등장 회의 보고서"), element("dd", "", Number(node.report_count || 0).toLocaleString() + "개"),
      element("dt", "", "매칭 키워드"), element("dd", "", Number(node.keyword_count || 0).toLocaleString() + "개"),
    );
    target.append(stats, element("h4", "", "판별 키워드"));
    const keywords = element("div", "assembly-ontology-keywords");
    (node.keywords || []).forEach((keyword) => keywords.append(element("span", "", keyword)));
    target.append(keywords);
  }

  function ontologyLayout(width, height) {
    const payload = ontologyState.payload || {};
    const centerX = width / 2;
    const centerY = height / 2 - Math.min(22, height * .03);
    const size = Math.min(width, height);
    const domainRadius = Math.max(72, size * .2);
    const groupRadius = Math.max(138, size * .39);
    const nodes = [{ type: "root", key: "national-policy", title: payload.root?.title || "국정 온톨로지", x: centerX, y: centerY, radius: 18 }];
    const groups = payload.groups || [];
    (payload.domains || []).forEach((domain, domainIndex, domains) => {
      const angle = -Math.PI / 2 + domainIndex * Math.PI * 2 / domains.length;
      nodes.push({ ...domain, type: "domain", domain_key: domain.key, x: centerX + Math.cos(angle) * domainRadius, y: centerY + Math.sin(angle) * domainRadius, radius: 11 });
      const children = groups.filter((group) => group.domain_key === domain.key);
      const arc = Math.PI * 2 / domains.length * .78;
      children.forEach((group, index) => {
        const fraction = children.length === 1 ? .5 : index / (children.length - 1);
        const childAngle = angle - arc / 2 + arc * fraction;
        const stagger = index % 2 ? size * .022 : 0;
        nodes.push({
          ...group,
          type: "group",
          color: domain.color,
          x: centerX + Math.cos(childAngle) * (groupRadius + stagger),
          y: centerY + Math.sin(childAngle) * (groupRadius + stagger),
          radius: Math.min(9, 4.2 + Math.log2(Number(group.topic_count || 0) + 1) * .72),
        });
      });
    });
    return nodes;
  }

  function ontologyScreenPoint(node, width, height) {
    return {
      x: (node.x - width / 2) * ontologyState.zoom + width / 2 + ontologyState.panX,
      y: (node.y - height / 2) * ontologyState.zoom + height / 2 + ontologyState.panY,
    };
  }

  function drawOntology() {
    const canvas = document.querySelector("#assemblyOntologyCanvas");
    const dialog = document.querySelector("#assemblyOntologyDialog");
    if (!canvas || !dialog?.open || !ontologyState.payload) return;
    if (!window.AssemblyOntology3D && !ontologyState.force2d) {
      ontologyState.animation = requestAnimationFrame(drawOntology);
      return;
    }
    if (window.AssemblyOntology3D && !ontologyState.scene3d && !ontologyState.force2d) {
      try {
        ontologyState.scene3d = window.AssemblyOntology3D.create(
          canvas,
          ontologyState.payload,
          {
            onSelect(node) {
              ontologyState.selected = node;
              ontologyState.activeDomain = node.type === "root" ? "" : (node.domain_key || node.key);
              renderOntologyDetail(node);
              document.querySelectorAll("#assemblyOntologyLegend button").forEach((button, index) => {
                button.classList.toggle("is-active", (ontologyState.payload.domains || [])[index]?.key === ontologyState.activeDomain);
              });
            },
          },
        );
        document.querySelector("#assemblyOntologyMeta").textContent = `실시간 3D 지식 성단 · Three.js r${window.AssemblyOntology3D.version}`;
      } catch (error) {
        ontologyState.force2d = true;
        canvas.dataset.renderer = "canvas2d";
        canvas.dataset.rendererError = String(error?.message || error || "WEBGL_UNAVAILABLE");
        document.querySelector("#assemblyOntologyMeta").textContent = "이 장치에서는 호환형 스타맵으로 표시합니다.";
      }
    }
    if (ontologyState.scene3d) {
      ontologyState.scene3d.start();
      return;
    }
    const rect = canvas.getBoundingClientRect();
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#050812";
    context.fillRect(0, 0, width, height);
    const now = performance.now() / 1000;
    for (let index = 0; index < 90; index += 1) {
      const x = ((index * 83.37) % 100) / 100 * width;
      const y = ((index * 47.11 + 13) % 100) / 100 * height;
      const alpha = .12 + ((Math.sin(now * .7 + index) + 1) * .08);
      context.fillStyle = `rgba(181,205,239,${alpha})`;
      context.fillRect(x, y, index % 7 === 0 ? 1.6 : 1, index % 7 === 0 ? 1.6 : 1);
    }
    const nodes = ontologyLayout(width, height);
    const screen = new Map(nodes.map((node) => [node.key, ontologyScreenPoint(node, width, height)]));
    const domainMap = new Map((ontologyState.payload.domains || []).map((item) => [item.key, item]));
    context.lineWidth = 1;
    for (const node of nodes.filter((item) => item.type === "domain")) {
      const root = screen.get("national-policy");
      const point = screen.get(node.key);
      context.beginPath();
      context.moveTo(root.x, root.y);
      context.lineTo(point.x, point.y);
      context.strokeStyle = node.color + "66";
      context.stroke();
    }
    for (const node of nodes.filter((item) => item.type === "group")) {
      const parent = screen.get(node.domain_key);
      const point = screen.get(node.key);
      const active = !ontologyState.activeDomain || ontologyState.activeDomain === node.domain_key;
      context.beginPath();
      context.moveTo(parent.x, parent.y);
      context.lineTo(point.x, point.y);
      context.strokeStyle = node.color + (active ? "50" : "12");
      context.stroke();
    }
    for (const node of nodes) {
      const point = screen.get(node.key);
      const domain = domainMap.get(node.domain_key || node.key);
      const color = node.type === "root" ? "#ffffff" : (domain?.color || node.color || "#5eead4");
      const active = !ontologyState.activeDomain || node.type === "root" || ontologyState.activeDomain === (node.domain_key || node.key);
      const focused = ontologyState.selected?.key === node.key || ontologyState.hover?.key === node.key;
      const pulse = 1 + Math.sin(now * 2.1 + point.x * .01) * .08;
      const radius = node.radius * ontologyState.zoom * (focused ? 1.35 : pulse);
      context.save();
      context.globalAlpha = active ? 1 : .14;
      context.shadowColor = color;
      context.shadowBlur = focused ? 28 : (node.type === "group" ? 11 : 22);
      context.beginPath();
      context.arc(point.x, point.y, Math.max(2.5, radius), 0, Math.PI * 2);
      context.fillStyle = color;
      context.fill();
      context.restore();
      if (node.type !== "group" || focused || ontologyState.zoom > 1.35) {
        context.save();
        context.globalAlpha = active ? (node.type === "group" ? .82 : 1) : .18;
        context.fillStyle = node.type === "root" ? "#ffffff" : "#dce8f8";
        context.font = `${node.type === "root" ? 700 : 600} ${node.type === "root" ? 13 : node.type === "domain" ? 11 : 9}px sans-serif`;
        context.textAlign = "center";
        context.fillText(node.title, point.x, point.y + radius + (node.type === "root" ? 19 : 14));
        context.restore();
      }
      node.screenX = point.x;
      node.screenY = point.y;
      node.hitRadius = Math.max(12, radius + 5);
    }
    ontologyState.nodes = nodes;
    ontologyState.animation = requestAnimationFrame(drawOntology);
  }

  function ontologyNodeAt(x, y) {
    return [...ontologyState.nodes].reverse().find((node) => Math.hypot(node.screenX - x, node.screenY - y) <= node.hitRadius) || null;
  }

  function renderOntologyLegend(payload) {
    const target = document.querySelector("#assemblyOntologyLegend");
    target.replaceChildren();
    (payload.domains || []).forEach((domain) => {
      const button = element("button", "", domain.title);
      button.type = "button";
      button.style.setProperty("--domain-color", domain.color);
      button.prepend(element("i"));
      button.addEventListener("click", () => {
        ontologyState.activeDomain = ontologyState.activeDomain === domain.key ? "" : domain.key;
        ontologyState.selected = ontologyState.activeDomain ? { ...domain, type: "domain" } : null;
        ontologyState.scene3d?.filter(ontologyState.activeDomain);
        [...target.children].forEach((item) => item.classList.toggle("is-active", item === button && Boolean(ontologyState.activeDomain)));
        renderOntologyDetail(ontologyState.selected);
      });
      target.append(button);
    });
  }

  function resetOntologyView() {
    ontologyState.zoom = 1;
    ontologyState.panX = 0;
    ontologyState.panY = 0;
    ontologyState.activeDomain = "";
    ontologyState.selected = null;
    ontologyState.scene3d?.reset();
    document.querySelectorAll("#assemblyOntologyLegend button").forEach((button) => button.classList.remove("is-active"));
    renderOntologyDetail(null);
  }

  function wireOntologyCanvas() {
    if (ontologyState.wired) return;
    ontologyState.wired = true;
    const canvas = document.querySelector("#assemblyOntologyCanvas");
    canvas.addEventListener("pointerdown", (event) => {
      if (ontologyState.scene3d) return;
      ontologyState.dragging = true;
      ontologyState.moved = false;
      ontologyState.pointerX = event.clientX;
      ontologyState.pointerY = event.clientY;
      canvas.classList.add("is-dragging");
      canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointermove", (event) => {
      if (ontologyState.scene3d) return;
      const rect = canvas.getBoundingClientRect();
      if (ontologyState.dragging) {
        const dx = event.clientX - ontologyState.pointerX;
        const dy = event.clientY - ontologyState.pointerY;
        ontologyState.panX += dx;
        ontologyState.panY += dy;
        ontologyState.pointerX = event.clientX;
        ontologyState.pointerY = event.clientY;
        if (Math.abs(dx) + Math.abs(dy) > 2) ontologyState.moved = true;
        return;
      }
      ontologyState.hover = ontologyNodeAt(event.clientX - rect.left, event.clientY - rect.top);
    });
    canvas.addEventListener("pointerup", (event) => {
      if (ontologyState.scene3d) return;
      const rect = canvas.getBoundingClientRect();
      if (!ontologyState.moved) {
        const node = ontologyNodeAt(event.clientX - rect.left, event.clientY - rect.top);
        if (node) {
          ontologyState.selected = node;
          ontologyState.activeDomain = node.type === "domain" ? node.key : (node.type === "group" ? node.domain_key : "");
          renderOntologyDetail(node);
          document.querySelectorAll("#assemblyOntologyLegend button").forEach((button, index) => {
            button.classList.toggle("is-active", (ontologyState.payload.domains || [])[index]?.key === ontologyState.activeDomain);
          });
        }
      }
      ontologyState.dragging = false;
      canvas.classList.remove("is-dragging");
      if (canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
    });
    canvas.addEventListener("pointercancel", () => {
      if (ontologyState.scene3d) return;
      ontologyState.dragging = false;
      canvas.classList.remove("is-dragging");
    });
    canvas.addEventListener("wheel", (event) => {
      if (ontologyState.scene3d) return;
      event.preventDefault();
      ontologyState.zoom = Math.min(2.2, Math.max(.72, ontologyState.zoom * (event.deltaY > 0 ? .9 : 1.1)));
    }, { passive: false });
    new ResizeObserver(() => {
      if (document.querySelector("#assemblyOntologyDialog")?.open) {
        if (ontologyState.scene3d) ontologyState.scene3d.resize();
        else {
          cancelAnimationFrame(ontologyState.animation);
          ontologyState.animation = requestAnimationFrame(drawOntology);
        }
      }
    }).observe(canvas);
  }

  async function openOntologyMap() {
    const dialog = document.querySelector("#assemblyOntologyDialog");
    if (!dialog.open) dialog.showModal();
    wireOntologyCanvas();
    const engineLoad = loadOntology3DEngine().catch((error) => {
      ontologyState.force2d = true;
      document.querySelector("#assemblyOntologyCanvas").dataset.rendererError = String(error?.message || error || "MODULE_LOAD_FAILED");
    });
    if (!ontologyState.payload) {
      document.querySelector("#assemblyOntologyMetrics").replaceChildren(ontologyMetric("온톨로지", "불러오는 중"));
      document.querySelector("#assemblyOntologyDetail").replaceChildren(element("p", "", "현재 온톨로지 구성을 불러오는 중입니다."));
      try {
        const response = await fetch("api/policy/ontology", { cache: "no-store", headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("ontology");
        ontologyState.payload = await response.json();
        renderOntologyMetrics(ontologyState.payload);
        renderOntologyLegend(ontologyState.payload);
        renderOntologyDetail(null);
      } catch (_) {
        document.querySelector("#assemblyOntologyMetrics").replaceChildren(ontologyMetric("온톨로지", "연결 실패", "is-review"));
        document.querySelector("#assemblyOntologyDetail").replaceChildren(element("p", "", "온톨로지 구성을 불러오지 못했습니다."));
        return;
      }
    }
    await engineLoad;
    cancelAnimationFrame(ontologyState.animation);
    ontologyState.animation = requestAnimationFrame(drawOntology);
  }

  async function loadGovernmentInsights() {
    const loadIssues = async () => {
      try {
        const response = await fetch("api/policy/specific-issues?limit=80", { cache: "no-store", headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("issues");
        const payload = await response.json();
        renderIssueTrends(payload);
        renderInstitutionFlow(payload);
      } catch (_) {
        for (const selector of ["#assemblyIssueTrends", "#assemblyInstitutionFlow"]) {
          mount.querySelector(selector).replaceChildren(element("p", "assembly-insight-empty", "저장된 회의 쟁점을 불러오지 못했습니다."));
        }
      }
    };
    const loadTimeline = async () => {
      try {
        const response = await fetch("api/policy/cross-institution-flow", { cache: "no-store", headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("timeline");
        renderPolicyTimeline(await response.json());
      } catch (_) {
        mount.querySelector("#assemblyPolicyTimeline").replaceChildren(element("p", "assembly-insight-empty", "정부·국회 정책 연결 자료를 불러오지 못했습니다."));
      }
    };
    await Promise.allSettled([loadIssues(), loadTimeline()]);
  }

  function distributeRows(total) {
    const base = [34, 40, 46, 52, 60, 68];
    const raw = base.map((count) => count * total / 300);
    const rows = raw.map(Math.floor);
    let remaining = total - rows.reduce((sum, count) => sum + count, 0);
    const order = raw.map((value, index) => ({ index, fraction: value - rows[index] }))
      .sort((a, b) => b.fraction - a.fraction || b.index - a.index);
    for (let index = 0; index < remaining; index += 1) rows[order[index % order.length].index] += 1;
    return rows;
  }

  function hemicyclePositions(total) {
    const rows = distributeRows(total);
    const radii = [145, 190, 235, 280, 325, 370];
    const positions = [];
    rows.forEach((count, rowIndex) => {
      for (let seatIndex = 0; seatIndex < count; seatIndex += 1) {
        const angle = Math.PI + ((seatIndex + 0.5) / count) * Math.PI;
        positions.push({
          angle,
          radius: radii[rowIndex],
          x: 500 + Math.cos(angle) * radii[rowIndex],
          y: 420 + Math.sin(angle) * radii[rowIndex],
        });
      }
    });
    return positions.sort((a, b) => a.angle - b.angle || a.radius - b.radius);
  }

  function toggleParty(label) {
    if (hemicycleState.selected.has(label)) hemicycleState.selected.delete(label);
    else hemicycleState.selected.add(label);
    renderHemicycle(hemicycleState.payload || {});
  }

  function renderQuorum(total, selectedCount, hasSelection) {
    const target = mount.querySelector("#assemblyQuorumGrid");
    target.replaceChildren();
    const thresholds = [
      { count: Math.floor(total / 2) + 1, label: "재적 과반선", detail: "일반 의결의 출석 기준 참고" },
      { count: Math.ceil(total * 3 / 5), label: "재적 3/5선", detail: "무제한토론 종결·신속처리 예시" },
      { count: Math.ceil(total * 2 / 3), label: "재적 2/3선", detail: "헌법개정안 의결 예시" },
    ];
    for (const threshold of thresholds) {
      const card = element("section", "assembly-quorum-card");
      card.append(element("span", "", threshold.label), element("strong", "", threshold.count.toLocaleString() + "석"));
      if (hasSelection) {
        const difference = selectedCount - threshold.count;
        card.classList.add(difference >= 0 ? "is-met" : "is-short");
        card.append(element("b", "", difference >= 0 ? difference.toLocaleString() + "석 상회" : Math.abs(difference).toLocaleString() + "석 부족"));
      } else {
        card.append(element("b", "", "정당 선택 후 비교"));
      }
      card.append(element("small", "", threshold.detail));
      target.append(card);
    }
  }

  function renderHemicycle(payload) {
    hemicycleState.payload = payload;
    const stage = mount.querySelector("#assemblyHemicycleStage");
    const legend = mount.querySelector("#assemblyHemicycleLegend");
    const reset = mount.querySelector("#assemblySeatSelectionReset");
    const countLabel = mount.querySelector("#assemblySelectedSeatCount");
    const parties = (payload.party_seats || []).filter((party) => Number(party.count) > 0);
    const total = Number(payload.seat_count || parties.reduce((sum, party) => sum + Number(party.count || 0), 0));
    const validLabels = new Set(parties.map((party) => String(party.label)));
    for (const label of [...hemicycleState.selected]) {
      if (!validLabels.has(label)) hemicycleState.selected.delete(label);
    }
    stage.replaceChildren();
    legend.replaceChildren();
    if (!parties.length || !total) {
      stage.append(element("p", "assembly-reference-empty", "의석 현황을 동기화하는 중입니다."));
      countLabel.textContent = "-";
      reset.hidden = true;
      renderQuorum(300, 0, false);
      return;
    }

    const hasSelection = hemicycleState.selected.size > 0;
    const selectedCount = parties.reduce((sum, party) => hemicycleState.selected.has(String(party.label)) ? sum + Number(party.count) : sum, 0);
    countLabel.textContent = hasSelection ? selectedCount.toLocaleString() + "석" : "전체 " + total.toLocaleString() + "석";
    reset.hidden = !hasSelection;

    const svg = document.createElementNS(svgNamespace, "svg");
    svg.setAttribute("viewBox", "0 0 1000 455");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-labelledby", "assemblySeatSvgTitle assemblySeatSvgDescription");
    const title = document.createElementNS(svgNamespace, "title");
    title.id = "assemblySeatSvgTitle";
    title.textContent = "정당별 의석수 비례 부채형 시각화";
    const description = document.createElementNS(svgNamespace, "desc");
    description.id = "assemblySeatSvgDescription";
    description.textContent = parties.map((party) => party.label + " " + party.count + "석").join(", ");
    svg.append(title, description);

    const seatParties = [];
    parties.forEach((party, index) => {
      for (let count = 0; count < Number(party.count); count += 1) seatParties.push({ ...party, color: partyColors[index % partyColors.length] });
    });
    const positions = hemicyclePositions(Math.min(total, seatParties.length));
    positions.forEach((position, index) => {
      const party = seatParties[index];
      const circle = document.createElementNS(svgNamespace, "circle");
      circle.setAttribute("cx", position.x.toFixed(2));
      circle.setAttribute("cy", position.y.toFixed(2));
      circle.setAttribute("r", "7.2");
      circle.setAttribute("fill", party.color);
      circle.classList.add("assembly-seat-dot");
      if (hasSelection && !hemicycleState.selected.has(String(party.label))) circle.classList.add("is-muted");
      if (hemicycleState.selected.has(String(party.label))) circle.classList.add("is-selected");
      const seatTitle = document.createElementNS(svgNamespace, "title");
      seatTitle.textContent = party.label + " · 전체 " + Number(party.count).toLocaleString() + "석";
      circle.append(seatTitle);
      circle.addEventListener("click", () => toggleParty(String(party.label)));
      svg.append(circle);
    });
    stage.append(svg);

    parties.forEach((party, index) => {
      const label = String(party.label);
      const button = element("button", "assembly-party-select");
      button.type = "button";
      button.setAttribute("aria-pressed", hemicycleState.selected.has(label) ? "true" : "false");
      const dot = element("i", "");
      dot.style.background = partyColors[index % partyColors.length];
      button.append(dot, element("span", "", label), element("b", "", Number(party.count).toLocaleString() + "석"));
      button.addEventListener("click", () => toggleParty(label));
      legend.append(button);
    });
    renderQuorum(total, selectedCount, hasSelection);
  }

  function renderReference(payload) {
    const parties = payload.party_seats || [];
    const total = Number(payload.seat_count || 0);
    mount.querySelector("#assemblyTerm").textContent = payload.assembly_term || "국회";
    mount.querySelector("#assemblySeatCount").textContent = total ? total.toLocaleString() : "-";
    const generated = payload.generated_at ? new Date(payload.generated_at) : null;
    mount.querySelector("#assemblyReferenceMeta").textContent = generated && !Number.isNaN(generated.getTime())
      ? "공식 API · " + new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(generated) + " 갱신"
      : "공식 의원 현황 동기화 대기";

    const bar = mount.querySelector("#assemblySeatBar");
    const list = mount.querySelector("#assemblyPartyList");
    bar.replaceChildren();
    list.replaceChildren();
    if (!parties.length || !total) {
      list.append(element("p", "assembly-reference-empty", "의석 현황을 동기화하는 중입니다."));
    } else {
      parties.forEach((party, index) => {
        const color = partyColors[index % partyColors.length];
        const segment = element("span", "");
        segment.style.width = (Number(party.count) / total * 100) + "%";
        segment.style.background = color;
        segment.title = party.label + " " + party.count + "석";
        bar.append(segment);
        const row = element("div", "assembly-party-row");
        const label = element("span", "");
        const dot = element("i", "");
        dot.style.background = color;
        label.append(dot, document.createTextNode(String(party.label)));
        row.append(label, element("b", "", Number(party.count).toLocaleString() + "석"));
        list.append(row);
      });
    }

    const facts = mount.querySelector("#assemblyReferenceFacts");
    facts.replaceChildren(
      factCard("선출 구분", payload.election_type_seats),
      factCard("성별 현황", payload.gender_seats),
      factCard("위원회", [{ label: "확인된 위원회", count: Number(payload.committee_count || 0) }]),
    );
    const source = payload.source?.catalog_url;
    if (source) mount.querySelector("#assemblyReferenceSource").href = String(source);
    renderHemicycle(payload);
  }

  async function loadReference() {
    try {
      const response = await fetch("api/assembly/reference", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("reference");
      renderReference(await response.json());
    } catch (_) {
      renderReference({ source_status: "ERROR", seat_count: 0, party_seats: [], election_type_seats: [], gender_seats: [] });
      mount.querySelector("#assemblyReferenceMeta").textContent = "공식 의원 현황을 불러오지 못했습니다.";
    }
  }

  mount.querySelector("#assemblySeatSelectionReset")?.addEventListener("click", () => {
    hemicycleState.selected.clear();
    renderHemicycle(hemicycleState.payload || {});
  });

  mount.querySelector("#assemblyCalendarPrev").addEventListener("click", () => {
    state.month = new Date(state.month.getFullYear(), state.month.getMonth() - 1, 1);
    loadCalendar();
  });
  mount.querySelector("#assemblyCalendarNext").addEventListener("click", () => {
    state.month = new Date(state.month.getFullYear(), state.month.getMonth() + 1, 1);
    loadCalendar();
  });
  mount.querySelector("#assemblyCalendarToday").addEventListener("click", () => {
    const today = new Date();
    state.month = new Date(today.getFullYear(), today.getMonth(), 1);
    state.selected = localIso(today);
    loadCalendar();
  });
  for (const button of filterButtons) {
    button.addEventListener("click", () => {
      state.filter = button.dataset.calendarFilter || "all";
      for (const item of filterButtons) item.classList.toggle("is-active", item === button);
      renderCalendar();
    });
  }

  document.querySelector("#assemblyInsightDialogClose")?.addEventListener("click", () => {
    document.querySelector("#assemblyInsightDialog")?.close();
  });
  document.querySelector("#assemblyInsightDialog")?.addEventListener("click", (event) => {
    if (event.target === event.currentTarget) event.currentTarget.close();
  });
  document.querySelector("#assemblyOntologyOpen")?.addEventListener("click", openOntologyMap);
  document.querySelector("#assemblyOntologyReset")?.addEventListener("click", resetOntologyView);
  document.querySelector("#assemblyOntologyClose")?.addEventListener("click", () => {
    document.querySelector("#assemblyOntologyDialog")?.close();
  });
  document.querySelector("#assemblyOntologyDialog")?.addEventListener("click", (event) => {
    if (event.target === event.currentTarget) event.currentTarget.close();
  });
  document.querySelector("#assemblyOntologyDialog")?.addEventListener("close", () => {
    cancelAnimationFrame(ontologyState.animation);
    ontologyState.animation = 0;
    ontologyState.scene3d?.stop();
  });

  let initialized = false;
  function initialize() {
    if (initialized) return;
    initialized = true;
    loadCalendar();
    loadGovernmentInsights();
  }
  document.addEventListener("workspace-tab-change", (event) => {
    if (event.detail?.tab === "extras") initialize();
  });
  if (window.location.hash === "#extras" || document.querySelector("#extras")?.hidden === false) initialize();
})();
