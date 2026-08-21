const dashboard = {
  meetingMetric: document.querySelector("#meetingMetric"),
  minuteMetric: document.querySelector("#minuteMetric"),
  billMetric: document.querySelector("#billMetric"),
  meetingList: document.querySelector("#committeeMeetingList"),
  billExplorer: document.querySelector("#billExplorer"),
  assemblyFallback: document.querySelector("#meetingState"),
  policyFlow: document.querySelector("#committeePolicyFlow"),
  policyFlowMeta: document.querySelector("#policyFlowMeta"),
  executiveStream: document.querySelector("#presidentialState"),
  executiveFallback: document.querySelector("#executiveFallback"),
  executiveFilterForm: document.querySelector("#executiveFilterForm"),
  executiveMinistry: document.querySelector("#executiveMinistry"),
  executiveQuery: document.querySelector("#executiveQuery"),
  executiveFilterMeta: document.querySelector("#executiveFilterMeta"),
  crossFlow: document.querySelector("#crossInstitutionFlow"),
  crossFlowMeta: document.querySelector("#crossFlowMeta"),
};
const voteSummaries = new Map();
let latestMeetings = null;
let latestExecutiveBriefings = null;
let executiveViewMode = "topic";
let executiveMeetingId = "";
let executiveMinistryFilter = "";
let executiveQueryFilter = "";

async function dashboardJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
  return payload;
}

function textElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = text;
  return element;
}

function koreanDate(value) {
  if (!value) return "날짜 미상";
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(`${value}T00:00:00`));
}

function committeeForMinistry(label) {
  if (/행정안전|행복청/.test(label)) return "행정안전위원회";
  if (/재정경제|기획재정/.test(label)) return "예산결산특별위원회";
  if (/법무부|법제처/.test(label)) return "법제사법위원회";
  return "";
}

function syncExecutiveFilterControls(payload) {
  dashboard.executiveMinistry.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "전체 부처";
  dashboard.executiveMinistry.append(all);
  for (const item of payload.facets?.ministries || []) {
    const option = document.createElement("option");
    option.value = item.label;
    option.textContent = item.label + " (" + item.count + ")";
    dashboard.executiveMinistry.append(option);
  }
  dashboard.executiveMinistry.value = executiveMinistryFilter;
  dashboard.executiveQuery.value = executiveQueryFilter;
  const labels = [];
  if (executiveMinistryFilter) labels.push(executiveMinistryFilter);
  if (executiveQueryFilter) labels.push("‘" + executiveQueryFilter + "’");
  dashboard.executiveFilterMeta.textContent = (labels.length ? labels.join(" · ") : "최근 공식본 전체")
    + " · 회의 " + payload.count + "회 · 안건 " + (payload.agenda_count || 0) + "건";
}

function renderExecutiveBriefings(payload, mode = "topic") {
  latestExecutiveBriefings = payload;
  executiveViewMode = mode;
  syncExecutiveFilterControls(payload);
  if (executiveMeetingId && !payload.items.some((meeting) => meeting.news_id === executiveMeetingId)) {
    executiveMeetingId = "";
  }
  const selectedScope = document.querySelector("#departmentScope")?.value || "";
  const selectedMeetings = executiveMeetingId
    ? payload.items.filter((meeting) => meeting.news_id === executiveMeetingId)
    : payload.items;
  const rows = selectedMeetings.flatMap((meeting) => meeting.agendas.map((agenda) => ({
    ...agenda,
    meeting_title: meeting.title,
    meeting_date: meeting.published_date,
    source_url: meeting.source_url,
    related_committee: committeeForMinistry(agenda.ministries.join(" ")),
  }))).filter((item) => !selectedScope || item.related_committee === selectedScope);
  if (mode === "ministry") rows.sort((a, b) => a.ministries.join("").localeCompare(b.ministries.join(""), "ko"));
  const latest = payload.items[0];
  document.querySelector("#executiveLatestMeeting").textContent = latest ? latest.title.replace(" 브리핑", "") : "공식본 없음";
  document.querySelector("#executiveAgendaMetric").textContent = String(rows.length) + "건";
  const filteredMessageCount = payload.items.reduce(
    (count, meeting) => count + (meeting.presidential_briefing?.message_count || 0), 0,
  );
  document.querySelector("#executiveMessageMetric").textContent = String(filteredMessageCount) + "개";
  dashboard.executiveStream.replaceChildren();
  const meetingList = document.createElement("div");
  meetingList.className = "executive-meeting-list";
  const allMeetings = document.createElement("button");
  allMeetings.type = "button";
  allMeetings.dataset.active = String(!executiveMeetingId);
  allMeetings.append(textElement("strong", "", "최근 전체"), textElement("span", "", payload.count + "회 공식본"));
  allMeetings.addEventListener("click", () => {
    executiveMeetingId = "";
    renderExecutiveBriefings(payload, executiveViewMode);
  });
  meetingList.append(allMeetings);
  for (const meeting of payload.items) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.active = String(executiveMeetingId === meeting.news_id);
    button.append(
      textElement("strong", "", meeting.title.replace(" 국무회의 브리핑", "").replace(" 브리핑", "")),
      textElement("span", "", meeting.published_date + " · 안건 " + meeting.agenda_count
        + (meeting.presidential_briefing ? " · 발언 " + meeting.presidential_briefing.message_count : "")),
    );
    button.addEventListener("click", () => {
      executiveMeetingId = meeting.news_id;
      renderExecutiveBriefings(payload, executiveViewMode);
    });
    meetingList.append(button);
  }
  dashboard.executiveStream.append(meetingList);
  const messageMeeting = selectedMeetings[0];
  const presidential = messageMeeting?.presidential_briefing;
  if (presidential?.messages?.length) {
    const messagePanel = document.createElement("section");
    messagePanel.className = "executive-message-panel";
    const messageHead = document.createElement("header");
    messageHead.append(
      textElement("span", "", "OFFICIAL MESSAGE"),
      textElement("strong", "", presidential.title),
    );
    const messageSource = textElement("a", "", "청와대 공식 원문 ↗");
    messageSource.href = presidential.source_url;
    messageSource.target = "_blank";
    messageSource.rel = "noopener noreferrer";
    messageHead.append(messageSource);
    messagePanel.append(messageHead);
    const messageGrid = document.createElement("div");
    for (const message of presidential.messages.slice(0, 3)) {
      const messageCard = document.createElement("article");
      messageCard.append(
        textElement("small", "", message.source_span_id + " · 대통령"),
        textElement("p", "", message.text),
      );
      messageGrid.append(messageCard);
    }
    messagePanel.append(messageGrid);
    dashboard.executiveStream.append(messagePanel);
  } else if (executiveMeetingId && messageMeeting) {
    dashboard.executiveStream.append(textElement(
      "div", "executive-message-unavailable",
      "동일 날짜·회차의 청와대 공식 브리핑은 확인되지 않았습니다.",
    ));
  }
  const columns = document.createElement("div");
  columns.className = "stream-columns";
  ["정책 주제", "공식 내용", "소관 부처", "국회 진행"].forEach((label) => columns.append(textElement("span", "", label)));
  dashboard.executiveStream.append(columns);
  if (!rows.length) {
    dashboard.executiveStream.append(textElement("div", "policy-empty executive-empty", "선택 분야에 명시적으로 연결된 공식 국무회의 안건이 없습니다."));
  }
  for (const item of rows.slice(0, 12)) {
    const row = document.createElement("article");
    row.className = "executive-policy-row";
    const topic = document.createElement("div");
    topic.append(textElement("span", "", item.meeting_title.replace(" 국무회의 브리핑", "")), textElement("strong", "", item.topic));
    const statement = document.createElement("div");
    statement.append(textElement("p", "", item.summary), textElement("small", "", item.meeting_date + " · " + item.source_span_id + " · OFFICIAL"));
    const ministries = document.createElement("div");
    for (const ministry of item.ministries) ministries.append(textElement("b", "", ministry));
    const flow = document.createElement("div");
    if (item.related_committee) {
      flow.append(textElement("span", "rule-link", "RULE LINK"), textElement("strong", "", item.related_committee.replace("위원회", "위")));
    } else {
      flow.append(textElement("span", "unresolved-link", "연결 검토"));
    }
    const source = textElement("a", "executive-source-link", "공식 원문 ↗");
    source.href = item.source_url;
    source.target = "_blank";
    source.rel = "noopener noreferrer";
    flow.append(source);
    row.append(topic, statement, ministries, flow);
    dashboard.executiveStream.append(row);
  }
  dashboard.executiveFallback.replaceChildren();
  const fallbackHead = document.createElement("div");
  fallbackHead.className = "fallback-head";
  fallbackHead.append(textElement("span", "", "최근 공식 정보"), textElement("b", "", "OFFICIAL"));
  dashboard.executiveFallback.append(fallbackHead);
  if (latest) {
    const recent = document.createElement("div");
    recent.className = "recent-meeting";
    recent.append(textElement("strong", "", latest.title), textElement("span", "", latest.published_date + " · 대통령 주재"));
    const link = textElement("a", "fallback-official-link", "공식 안건 " + latest.agenda_count + "건 ↗");
    link.href = latest.source_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    recent.append(link);
    dashboard.executiveFallback.append(recent);
  }
}

async function loadExecutiveBriefings(mode = "topic") {
  const params = new URLSearchParams({ limit: "10" });
  if (executiveMinistryFilter) params.set("ministry", executiveMinistryFilter);
  if (executiveQueryFilter) params.set("q", executiveQueryFilter);
  return fetch("api/executive/briefings?" + params, { cache: "no-store" })
    .then(dashboardJson)
    .then((payload) => renderExecutiveBriefings(payload, mode))
    .catch((error) => showDashboardError(dashboard.executiveStream, error.message));
}

function renderCrossInstitutionFlow(payload) {
  dashboard.crossFlow.replaceChildren();
  dashboard.crossFlowMeta.textContent = payload.count
    ? payload.count + "개 공통 정책 신호 · 직접 안건 연결 아님 · DRAFT"
    : "공통 taxonomy로 연결된 주제가 없습니다.";
  for (const item of payload.items) {
    const card = document.createElement("details");
    card.className = "cross-flow-card";
    const summary = document.createElement("summary");
    summary.append(
      textElement("strong", "", item.topic),
      textElement("span", "", "국무회의 " + item.executive_evidence.published_date + " · 안건 " + item.executive_agenda_count),
      textElement("i", "", "↔"),
      textElement("span", "", "국회 " + item.legislative_evidence.conference_date + " · 발언 " + item.legislative_statement_count),
      textElement("b", "", item.bills.length ? "국회측 의안 " + item.bills.length : "국회측 의안 없음"),
    );
    card.append(summary);
    const body = document.createElement("div");
    body.className = "cross-flow-evidence";
    const executive = document.createElement("article");
    executive.append(
      textElement("span", "", "EXECUTIVE · OFFICIAL"),
      textElement("strong", "", item.executive_evidence.agenda_topic),
      textElement("p", "", item.executive_evidence.summary),
      textElement("small", "", item.executive_evidence.meeting_title + " · "
        + item.executive_evidence.source_span_id + " · 근거 "
        + item.executive_evidence.evidence_keywords.join(" · ")),
    );
    const executiveLink = textElement("a", "", "정책브리핑 원문 ↗");
    executiveLink.href = item.executive_evidence.source_url;
    executiveLink.target = "_blank";
    executiveLink.rel = "noopener noreferrer";
    executive.append(executiveLink);
    const legislature = document.createElement("article");
    const evidence = item.legislative_evidence;
    legislature.append(
      textElement("span", "", "LEGISLATURE · OFFICIAL TEXT"),
      textElement("strong", "", evidence ? evidence.committee_name + " · " + (evidence.speaker_name || "발언자 미상") : "국회 근거 확인 중"),
      textElement("p", "", evidence?.text || "공식 발언 근거를 불러오지 못했습니다."),
      textElement("small", "", evidence ? evidence.conference_date + " · " + evidence.source_span_id : ""),
    );
    if (evidence?.source_url) {
      const link = textElement("a", "", "국회 회의록 원문 ↗");
      link.href = evidence.source_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      legislature.append(link);
    }
    body.append(executive, textElement("i", "", "↔"), legislature);
    card.append(body);
    const rule = document.createElement("div");
    rule.className = "cross-flow-rule";
    rule.append(
      textElement("b", "", item.temporal_label),
      textElement("span", "", "양쪽 공통 근거 · " + item.shared_evidence_keywords.join(" · ")),
      textElement("em", "", "공통 정책 신호 · 직접 인과·동일 안건 확정 아님"),
    );
    card.append(rule);
    if (item.bills.length) {
      const bills = document.createElement("div");
      bills.className = "cross-flow-bills";
      bills.append(textElement("strong", "", "국회 발언 근거에 연결된 의안"));
      for (const bill of item.bills) {
        const vote = voteSummaries.get(bill.bill_id);
        const link = textElement("a", "", bill.bill_name + " · "
          + (vote ? "찬성 " + vote.yes + " / 반대 " + vote.no + " / 기권 " + vote.abstain : bill.plenary_result || "처리 확인"));
        link.href = bill.official_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        bills.append(link);
      }
      card.append(bills);
    }
    dashboard.crossFlow.append(card);
  }
  if (!payload.items.length) {
    dashboard.crossFlow.append(textElement("div", "loading-card", "선택 범위에 공통 정책 주제가 없습니다."));
  }
}

async function loadCrossInstitutionFlow(committee = "") {
  const params = new URLSearchParams();
  if (committee) params.set("committee", committee);
  return fetch("api/policy/cross-institution-flow?" + params, { cache: "no-store" })
    .then(dashboardJson)
    .then(renderCrossInstitutionFlow)
    .catch((error) => showDashboardError(dashboard.crossFlow, error.message));
}

function showDashboardError(container, message) {
  container.replaceChildren(textElement("div", "dashboard-error", message));
}

function renderPolicyFlow(payload) {
  dashboard.policyFlow.replaceChildren();
  dashboard.policyFlowMeta.textContent = `${payload.policy_statement_count}개 POLICY 발언 · ${payload.topic_count}개 주제 · 연결 의안 ${payload.linked_bill_count}개 · AUTO DRAFT`;
  if (!payload.items.length) {
    dashboard.policyFlow.append(textElement("div", "loading-card", "선택 범위에 분류된 정책 발언이 없습니다."));
    return;
  }
  const maxCount = Math.max(...payload.items.map((item) => item.statement_count), 1);
  const grid = document.createElement("div");
  grid.className = "policy-flow-grid";
  for (const item of payload.items) {
    const card = document.createElement("details");
    card.className = "policy-signal-card";
    const summary = document.createElement("summary");
    const title = document.createElement("div");
    title.className = "policy-signal-title";
    title.append(textElement("strong", "", item.topic), textElement("b", "", String(item.statement_count)));
    const bar = document.createElement("span");
    bar.className = "policy-signal-bar";
    const fill = document.createElement("i");
    fill.style.width = `${Math.max(8, Math.round(item.statement_count / maxCount * 100))}%`;
    bar.append(fill);
    const links = textElement(
      "small", "",
      [
        ...item.committees.map((value) => `${value.label} ${value.count}`),
        ...item.ministries.map((value) => `${value.label} 관련 ${value.count}`),
      ].join(" · "),
    );
    summary.append(title, bar, links);
    card.append(summary);
    if (item.evidence) {
      const evidence = document.createElement("div");
      evidence.className = "policy-signal-evidence";
      const speaker = [item.evidence.speaker_role, item.evidence.speaker_name].filter(Boolean).join(" ") || "발언자 미상";
      evidence.append(
        textElement("span", "", `${item.evidence.committee_name} · ${speaker}`),
        textElement("blockquote", "", item.evidence.text),
      );
      const source = textElement("a", "", `공식 근거 ${item.evidence.source_span_id} ↗`);
      source.href = item.evidence.source_url;
      source.target = "_blank";
      source.rel = "noopener noreferrer";
      evidence.append(source);
      card.append(evidence);
    }
    if (item.bills?.length) {
      const bills = document.createElement("div");
      bills.className = "policy-bill-flow";
      bills.append(textElement("span", "", "EXACT AGENDA → BILL → VOTE"));
      for (const bill of item.bills) {
        const row = document.createElement("div");
        row.className = "policy-linked-bill";
        const info = document.createElement("div");
        info.append(
          textElement("strong", "", bill.bill_name || bill.agenda_name),
          textElement("small", "", `${bill.process_stage_code || "처리단계 미상"} · ${bill.plenary_result || bill.committee_result || "처리결과 확인 중"}`),
        );
        const vote = voteSummaries.get(bill.bill_id);
        const voteText = vote
          ? `찬성 ${vote.yes} · 반대 ${vote.no} · 기권 ${vote.abstain}`
          : "본회의 표결자료 없음";
        const result = textElement("b", vote ? "has-vote" : "", voteText);
        row.append(info, result);
        if (bill.official_url) {
          const link = textElement("a", "", "의안정보 ↗");
          link.href = bill.official_url;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
          row.append(link);
        }
        bills.append(row);
      }
      card.append(bills);
    }
    grid.append(card);
  }
  dashboard.policyFlow.append(grid);
}

async function loadPolicyFlow(committee = "") {
  const params = new URLSearchParams();
  if (committee) params.set("committee", committee);
  return fetch(`api/committees/policy-flow?${params}`, { cache: "no-store" })
    .then(dashboardJson)
    .then(renderPolicyFlow)
    .catch((error) => showDashboardError(dashboard.policyFlow, error.message));
}

async function openOfficialTranscript(item) {
  const dialog = document.querySelector("#officialTranscriptDialog");
  const body = document.querySelector("#officialTranscriptBody");
  dialog.showModal();
  async function load(topic = "", ministry = "") {
    body.replaceChildren(textElement("div", "loading-card", "공식 발언을 불러오는 중입니다."));
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (topic) params.set("topic", topic);
      if (ministry) params.set("ministry", ministry);
      const response = await fetch(`api/committees/meetings/${encodeURIComponent(item.conference_id)}/transcript?${params}`, { cache: "no-store" });
      if (!response.ok) throw new Error(`공식 회의록 조회 실패 (${response.status})`);
      const payload = await response.json();
      document.querySelector("#officialTranscriptTitle").textContent = payload.title || item.title || "공식 회의록";
      document.querySelector("#officialTranscriptStage").textContent = payload.publication_stage === "TEMPORARY" ? "잠정 회의록 · PROVISIONAL" : "정본 회의록 · OFFICIAL";
      document.querySelector("#officialTranscriptMeta").textContent = `${payload.committee_name} · ${koreanDate(payload.conference_date)} · 전체 ${payload.utterance_count}문장 · 현재 ${payload.count}문장`;
      document.querySelector("#officialTranscriptSource").href = payload.source_url;
      const insights = document.querySelector("#officialTranscriptInsights");
      insights.replaceChildren(textElement("span", "insight-label", "AUTO CLASSIFICATION · DRAFT"));
      const reset = textElement("button", "insight-chip", "전체");
      reset.type = "button";
      reset.dataset.active = String(!topic && !ministry);
      reset.addEventListener("click", () => load());
      insights.append(reset);
      for (const insight of payload.insights.topics) {
        const chip = textElement("button", "insight-chip", `${insight.label} ${insight.count}`);
        chip.type = "button";
        chip.dataset.active = String(topic === insight.label);
        chip.addEventListener("click", () => load(insight.label, ""));
        insights.append(chip);
      }
      for (const insight of payload.insights.ministries) {
        const chip = textElement("button", "insight-chip ministry-chip", `${insight.label} ${insight.count}`);
        chip.type = "button";
        chip.dataset.active = String(ministry === insight.label);
        chip.addEventListener("click", () => load("", insight.label));
        insights.append(chip);
      }
      body.replaceChildren();
      for (const utterance of payload.items) {
        const row = document.createElement("article");
        row.className = "official-utterance";
        const speaker = [utterance.speaker_role, utterance.speaker_name].filter(Boolean).join(" ") || "발언자 미상";
        const content = document.createElement("div");
        content.className = "utterance-content";
        content.append(textElement("p", "", utterance.text));
        const labels = document.createElement("div");
        labels.className = "utterance-labels";
        labels.append(textElement("span", "utterance-kind", utterance.utterance_kind || "OTHER"));
        for (const link of [...utterance.topic_links, ...utterance.ministry_links]) {
          const tag = textElement("span", "", link.relation ? `${link.label} · 관련` : link.label);
          tag.title = link.keywords?.length ? `분류 근거: ${link.keywords.join(" · ")}` : "자동 분류 근거 없음";
          labels.append(tag);
        }
        content.append(labels);
        if (utterance.evidence_keywords?.length) {
          content.append(textElement("small", "utterance-evidence", `근거 키워드: ${utterance.evidence_keywords.join(" · ")}`));
        }
        row.append(textElement("strong", "", speaker), content, textElement("code", "", utterance.source_span_id));
        body.append(row);
      }
      if (!payload.items.length) body.append(textElement("div", "loading-card", "선택한 분류에 해당하는 발언이 없습니다."));
    } catch (error) {
      showDashboardError(body, error.message);
    }
  }
  await load();
}

document.querySelector("#officialTranscriptClose")?.addEventListener("click", () => {
  document.querySelector("#officialTranscriptDialog")?.close();
});

function renderCommitteeMeetings(payload) {
  latestMeetings = payload;
  dashboard.meetingMetric.textContent = String(payload.count);
  dashboard.minuteMetric.textContent = String(
    payload.items.reduce((sum, item) => sum + item.minute_sections, 0),
  );
  dashboard.meetingList.replaceChildren();
  renderAssemblyFallback(payload);
  if (!payload.items.length) {
    dashboard.meetingList.append(textElement("div", "loading-card", "수집된 대상 위원회 회의가 없습니다."));
    return;
  }

  for (const item of payload.items) {
    const card = document.createElement("article");
    card.className = "committee-card committee-row";
    const top = document.createElement("div");
    top.className = "committee-card-top";
    top.append(
      textElement("span", "committee-name", item.committee_name),
      textElement("span", "authority-chip", item.authority_status),
    );
    const title = textElement("h3", "", `${item.session_text || "회기 미상"} · ${item.meeting_order_text || "차수 미상"}`);
    card.title = item.title;
    const meta = textElement(
      "p",
      "committee-meta", koreanDate(item.conference_date),
    );
    const counts = document.createElement("div");
    counts.className = "source-counts";
    counts.append(
      textElement("span", "", `회의록 자료 ${item.minute_sections}건`),
      textElement("span", "", `연결 의안 ${item.agenda_items}건`),
    );
    if (item.top_policy_topic) {
      counts.append(textElement(
        "span", "policy-flow-summary",
        `${item.top_policy_topic} ${item.top_policy_topic_count} · ${item.top_related_ministry || "관련 부처 없음"}`,
      ));
    }
    const footer = document.createElement("div");
    footer.className = "committee-card-footer";
    footer.append(textElement("code", "conference-id", item.conference_id));
    const transcriptButton = textElement("button", "text-button", item.official_utterance_count ? `공식 발언 ${item.official_utterance_count}` : "본문 수집 중");
    transcriptButton.type = "button";
    transcriptButton.disabled = !item.official_utterance_count;
    transcriptButton.addEventListener("click", () => openOfficialTranscript(item));
    const button = textElement("button", "text-button", "연결 의안 보기");
    button.type = "button";
    button.disabled = item.agenda_items === 0;
    button.dataset.committee = item.committee_name;
    button.addEventListener("click", () => {
      const select = document.querySelector("#billCommittee");
      if (select) {
        select.value = item.committee_name;
        document.querySelector("#billSearchForm").requestSubmit();
        document.querySelector("#bills").scrollIntoView({ behavior: "smooth" });
      }
    });
    footer.append(transcriptButton, button);
    card.append(top, title, meta, counts, footer);
    dashboard.meetingList.append(card);
  }
  const selectedScope = document.querySelector("#departmentScope")?.value || "";
  for (const row of dashboard.meetingList.querySelectorAll(".committee-row")) {
    const rowCommittee = row.querySelector(".committee-name")?.textContent || "";
    row.hidden = Boolean(selectedScope && rowCommittee !== selectedScope);
  }
}

function renderAssemblyFallback(payload) {
  const container = dashboard.assemblyFallback;
  container.replaceChildren();
  const head = document.createElement("div");
  head.className = "fallback-head";
  head.append(textElement("span", "", "최근 공식 정보"), textElement("b", "", "OFFICIAL"));
  container.append(head);
  if (!payload.items.length) {
    const empty = document.createElement("div");
    empty.className = "feed-empty";
    empty.append(textElement("strong", "", "최근 대상 위원회 회의가 없습니다."), textElement("span", "", "확인된 회의록만 표시합니다."));
    container.append(empty);
    return;
  }
  const item = payload.items[0];
  const recent = document.createElement("div");
  recent.className = "recent-meeting";
  recent.append(
    textElement("strong", "", `${item.committee_name} · ${item.session_text || "회기 미상"} ${item.meeting_order_text || ""}`.trim()),
    textElement("span", "", `${koreanDate(item.conference_date)} · 회의록 ${item.minute_sections}건`),
    textElement("b", "", `의안 ${item.agenda_items}건`),
  );
  container.append(recent);
}

function buildBillExplorer() {
  dashboard.billExplorer.innerHTML = `
    <form class="bill-filters" id="billSearchForm">
      <label><span>검색어</span><input id="billQuery" name="q" type="search" placeholder="의안명, 발의자, 의안번호" maxlength="100"></label>
      <label><span>대상 위원회</span><select id="billCommittee" name="committee">
        <option value="">전체 위원회</option><option value="행정안전위원회">행정안전위원회</option>
        <option value="예산결산특별위원회">예산결산특별위원회</option><option value="법제사법위원회">법제사법위원회</option>
      </select></label>
      <label><span>처리단계</span><select id="billStage" name="stage">
        <option value="">전체 처리단계</option><option value="공포">공포</option><option value="대안반영폐기">대안반영폐기</option>
      </select></label>
      <div class="filter-actions"><button class="primary-button" type="submit">검색</button><button class="secondary-button" id="billFilterReset" type="button">초기화</button></div>
    </form>
    <div class="result-heading"><p id="billResultSummary">공식 의안을 불러오는 중입니다.</p><span class="official-label">OFFICIAL</span></div>
    <div class="bill-list" id="billList"></div>`;

  document.querySelector("#billSearchForm").addEventListener("submit", (event) => {
    event.preventDefault();
    loadBills();
  });
  document.querySelector("#billFilterReset").addEventListener("click", () => {
    document.querySelector("#billSearchForm").reset();
    loadBills();
  });
}
function processingSummary(item) {
  const committee = item.target_meeting_committees?.join(" · ") || item.committee_name || "소관위원회";
  const parts = [`${committee} 소관 의안`];
  if (item.committee_result) parts.push(`위원회 심사 ${item.committee_result}`);
  if (item.plenary_result) parts.push(`본회의 ${item.plenary_result}`);
  if (item.process_stage_code) parts.push(`현재 ${item.process_stage_code} 단계`);
  return `${parts.join(" · ")}입니다.`;
}

function votePanel(item) {
  const panel = document.createElement("aside");
  panel.className = "vote-panel";
  panel.append(textElement("span", "vote-kicker", "PLENARY VOTE"));
  const vote = voteSummaries.get(item.bill_id);
  if (!vote) {
    panel.classList.add("vote-unavailable");
    panel.append(
      textElement("strong", "", "본회의 개별 표결 없음"),
      textElement("p", "", item.committee_result === "대안반영폐기"
        ? "위원회 대안에 반영되어 이 의안 자체의 본회의 표결은 없습니다."
        : "공식 의원별 표결자료가 확인되지 않았습니다."),
    );
    return panel;
  }

  const present = vote.yes + vote.no + vote.abstain;
  const denominator = Math.max(present, 1);
  panel.append(textElement("strong", "vote-result", vote.result || item.plenary_result || "표결 완료"));
  const counts = document.createElement("div");
  counts.className = "vote-counts";
  for (const [label, value, className] of [
    ["찬성", vote.yes, "yes"], ["반대", vote.no, "no"], ["기권", vote.abstain, "abstain"],
  ]) {
    const stat = document.createElement("span");
    stat.className = className;
    stat.append(textElement("b", "", String(value)), textElement("small", "", label));
    counts.append(stat);
  }
  const bar = document.createElement("div");
  bar.className = "vote-bar";
  for (const [value, className] of [[vote.yes, "yes"], [vote.no, "no"], [vote.abstain, "abstain"]]) {
    const segment = document.createElement("i");
    segment.className = className;
    segment.style.width = `${(value / denominator) * 100}%`;
    bar.append(segment);
  }
  panel.append(
    counts,
    bar,
    textElement("p", "vote-meta", `표결 참여 ${present}명 · 불참 ${vote.absent}명 · ${koreanDate(vote.vote_date.slice(0, 10))}`),
  );
  const source = document.createElement("details");
  source.className = "vote-source";
  source.append(textElement("summary", "", "공식 표결 출처"), textElement("p", "", "국회 국회사무처 의원별 본회의 표결정보를 집계했습니다."));
  panel.append(source);
  return panel;
}

function inlineVoteText(item) {
  const vote = voteSummaries.get(item.bill_id);
  if (!vote) return item.committee_result === "대안반영폐기" ? "본회의 표결 없음" : "표결자료 없음";
  return `${vote.result || item.plenary_result || "표결 완료"} · 찬성 ${vote.yes} · 반대 ${vote.no} · 기권 ${vote.abstain}`;
}

function renderBills(payload) {
  const list = document.querySelector("#billList");
  const summary = document.querySelector("#billResultSummary");
  summary.textContent = `검색 결과 ${payload.count}건 · 공식 상세정보만 표시`;
  list.replaceChildren();
  if (!payload.items.length) {
    list.append(textElement("div", "bill-empty", "조건에 맞는 연결 의안이 없습니다."));
    return;
  }

  let currentCommittee = "";
  for (const item of payload.items) {
    const committee = item.target_meeting_committees?.[0] || item.committee_name || "기타";
    if (committee !== currentCommittee) {
      currentCommittee = committee;
      const group = document.createElement("div");
      group.className = "committee-bill-heading";
      group.append(textElement("strong", "", committee), textElement("span", "", "위원회 연결 의안"));
      list.append(group);
    }
    const card = document.createElement("article");
    card.className = "bill-card bill-row";
    card.tabIndex = 0;
    card.setAttribute("aria-label", `${item.bill_name}, ${inlineVoteText(item)}. 상세 요약 보기`);
    card.title = "마우스를 올리거나 초점을 두면 요약과 표결 상세가 표시됩니다.";
    const head = document.createElement("div");
    head.className = "bill-card-head";
    head.append(
      textElement("span", `stage-chip stage-${item.process_stage_code === "공포" ? "promulgated" : "closed"}`, item.process_stage_code || "단계 미상"),
      textElement("span", "bill-number", `의안번호 ${item.bill_number || "미상"}`),
    );
    const billSummary = textElement("p", "bill-summary", processingSummary(item));
    const info = document.createElement("div");
    info.className = "bill-info";
    const title = textElement("h3", "", item.bill_name);
    const facts = document.createElement("dl");
    facts.className = "bill-facts";
    const values = [
      ["발의", item.proposer_name || item.proposer_kind || "정보 없음"],
      ["제안일", item.proposal_date || "정보 없음"],
      ["소관위 결과", item.committee_result || "정보 없음"],
      ["본회의 결과", item.plenary_result || "정보 없음"],
    ];
    for (const [label, value] of values) {
      facts.append(textElement("dt", "", label), textElement("dd", "", value));
    }
    info.append(billSummary, facts);
    if (item.official_document?.sections?.length) {
      const officialText = document.createElement("div");
      officialText.className = "bill-official-text";
      officialText.append(textElement("span", "", "OFFICIAL PDF TEXT"));
      for (const section of item.official_document.sections) {
        const block = document.createElement("section");
        block.append(
          textElement("strong", "", section.heading),
          textElement("p", "", section.text + (section.is_excerpt ? "…" : "")),
          textElement("small", "", section.source_span_id + " · " + section.page_start + "–" + section.page_end + "쪽"),
        );
        officialText.append(block);
      }
      const documentLink = textElement("a", "", "공식 PDF 원문 ↗");
      documentLink.href = item.official_document.source_url;
      documentLink.target = "_blank";
      documentLink.rel = "noreferrer";
      officialText.append(documentLink);
      info.append(officialText);
    }
    const inlineVote = textElement("span", "inline-vote", inlineVoteText(item));
    inlineVote.dataset.hasVote = voteSummaries.has(item.bill_id) ? "true" : "false";
    const content = document.createElement("div");
    content.className = "bill-card-content";
    content.append(info, votePanel(item));
    const foot = document.createElement("div");
    foot.className = "bill-card-foot";
    foot.append(textElement("span", "", item.target_meeting_committees.join(" · ")));
    const link = textElement("a", "official-link", "공식 의안 상세 ↗");
    link.href = item.official_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    foot.append(link);
    const provenance = document.createElement("details");
    provenance.className = "provenance";
    provenance.append(textElement("summary", "", "출처·수집 정보"));
    provenance.append(textElement("p", "", `수집 ${item.retrieved_at} · ${item.parser_version} · SHA-256 ${item.content_hash.slice(0, 12)}…`));
    const hoverDetail = document.createElement("div");
    hoverDetail.className = "bill-hover-detail";
    hoverDetail.append(content, foot, provenance);
    card.append(head, title, inlineVote, hoverDetail);
    list.append(card);
  }
}

async function loadBills() {
  const list = document.querySelector("#billList");
  const summary = document.querySelector("#billResultSummary");
  summary.textContent = "공식 의안을 검색하는 중입니다.";
  list.replaceChildren(textElement("div", "loading-card", "검색 결과를 불러오는 중입니다."));
  const params = new URLSearchParams();
  const query = document.querySelector("#billQuery").value.trim();
  const committee = document.querySelector("#billCommittee").value;
  const stage = document.querySelector("#billStage").value;
  if (query) params.set("q", query);
  if (committee) params.set("committee", committee);
  if (stage) params.set("stage", stage);
  try {
    const payload = await fetch(`api/bills?${params}`, { cache: "no-store" }).then(dashboardJson);
    if (!query && !committee && !stage) dashboard.billMetric.textContent = String(payload.count);
    renderBills(payload);
  } catch (error) {
    summary.textContent = "의안 검색에 실패했습니다.";
    showDashboardError(list, error.message);
  }
}

async function initializeDashboard() {
  buildBillExplorer();
  const selectedScope = document.querySelector("#departmentScope")?.value || "";
  if (selectedScope) document.querySelector("#billCommittee").value = selectedScope;
  await fetch("assets/data/vote_summaries.json", { cache: "no-store" })
    .then(dashboardJson)
    .then((payload) => {
      voteSummaries.clear();
      for (const item of payload.items || []) voteSummaries.set(item.bill_id, item);
    })
    .catch(() => voteSummaries.clear());
  const meetingsPromise = fetch("api/committees/meetings", { cache: "no-store" })
    .then(dashboardJson)
    .then(renderCommitteeMeetings)
    .catch((error) => showDashboardError(dashboard.meetingList, error.message));
  await Promise.all([
    meetingsPromise, loadBills(), loadPolicyFlow(selectedScope),
    loadExecutiveBriefings(), loadCrossInstitutionFlow(selectedScope),
  ]);
}

initializeDashboard();
document.querySelector("#refreshButton").addEventListener("click", initializeDashboard);

dashboard.executiveFilterForm.addEventListener("submit", (event) => {
  event.preventDefault();
  executiveMinistryFilter = dashboard.executiveMinistry.value;
  executiveQueryFilter = dashboard.executiveQuery.value.trim();
  executiveMeetingId = "";
  loadExecutiveBriefings(executiveViewMode);
});

dashboard.executiveFilterForm.addEventListener("reset", (event) => {
  event.preventDefault();
  executiveMinistryFilter = "";
  executiveQueryFilter = "";
  executiveMeetingId = "";
  dashboard.executiveMinistry.value = "";
  dashboard.executiveQuery.value = "";
  loadExecutiveBriefings(executiveViewMode);
});

document.addEventListener("department-scope-change", (event) => {
  const committee = event.detail.committee;
  const select = document.querySelector("#billCommittee");
  if (select) {
    select.value = committee;
    document.querySelector("#billSearchForm").requestSubmit();
  }
  if (latestMeetings) {
    for (const row of dashboard.meetingList.querySelectorAll(".committee-row")) {
      const rowCommittee = row.querySelector(".committee-name")?.textContent || "";
      row.hidden = Boolean(committee && rowCommittee !== committee);
    }
  }
  loadPolicyFlow(committee);
  loadCrossInstitutionFlow(committee);
  if (latestExecutiveBriefings) renderExecutiveBriefings(latestExecutiveBriefings, executiveViewMode);
});

for (const tab of document.querySelectorAll(".view-tabs button")) {
  tab.addEventListener("click", () => {
    if (latestExecutiveBriefings) renderExecutiveBriefings(
      latestExecutiveBriefings,
      tab.textContent.includes("소관") ? "ministry" : "topic",
    );
  });
}
