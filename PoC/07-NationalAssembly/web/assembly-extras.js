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
  const svgNamespace = "http://www.w3.org/2000/svg";

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
    return state.filter === "target"
      ? committeeItems.filter((item) => Boolean(item.is_target_committee))
      : committeeItems;
  }

  function isCommitteeSchedule(item) {
    return String(item?.schedule_kind || "") === "위원회";
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
    return String(item.committee_name || item.host_name || item.schedule_kind || "국회 일정");
  }

  function timeLabel(item) {
    const value = String(item.start_time || item.time_text || "").slice(0, 5);
    return /^\d{2}:\d{2}$/.test(value) ? value : "시간 미정";
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
    const items = [...memberItems, ...committeeItems];
    agendaTitle.textContent = formatSelectedDate(state.selected);
    agendaCount.textContent = items.length
      ? `의원실 ${memberItems.length} · 위원회 ${committeeItems.length}`
      : "일정 없음";
    agendaList.replaceChildren();
    if (!items.length) {
      agendaList.append(element("p", "assembly-agenda-empty", "저장된 의원실·위원회 일정이 없습니다."));
      return;
    }
    for (const [kind, sectionItems] of [["의원실 일정", memberItems], ["위원회 일정", committeeItems]]) {
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
        tags.append(element("span", item.is_target_committee ? "is-target" : "", eventLabel(item)));
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
        const event = element("i", item.is_target_committee ? "is-target" : "", timeLabel(item) + " " + eventLabel(item));
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
      meta.textContent = `위원회 ${committeeItems.length.toLocaleString()}건 · 의원실 ${memberItems.length.toLocaleString()}건 · 저장 DB 기준`;
      const relevantItems = [...memberItems, ...committeeItems];
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

  function renderPolicyTimeline(payload) {
    const target = mount.querySelector("#assemblyPolicyTimeline");
    target.replaceChildren();
    const items = (payload.items || []).slice(0, 5);
    if (!items.length) {
      target.append(element("p", "assembly-insight-empty", "정부와 국회에서 공통 근거가 확인된 정책 흐름이 없습니다."));
      return;
    }
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
      target.append(card);
    }
  }

  function trendWindow(items) {
    const dates = items.flatMap((item) => (item.timeline || []).map((point) => String(point.date || ""))).filter(Boolean);
    if (!dates.length) return null;
    const latest = new Date([...dates].sort().at(-1) + "T00:00:00");
    const currentStart = new Date(latest);
    currentStart.setDate(currentStart.getDate() - 13);
    const previousStart = new Date(currentStart);
    previousStart.setDate(previousStart.getDate() - 14);
    const previousEnd = new Date(currentStart);
    previousEnd.setDate(previousEnd.getDate() - 1);
    return { latest, currentStart, previousStart, previousEnd };
  }

  function renderIssueTrends(payload) {
    const target = mount.querySelector("#assemblyIssueTrends");
    target.replaceChildren();
    const source = payload.items || [];
    const window = trendWindow(source);
    if (!window) {
      target.append(element("p", "assembly-insight-empty", "기간별 공식 정책 발언이 아직 충분하지 않습니다."));
      return;
    }
    const rows = source.map((item) => {
      let current = 0;
      let previous = 0;
      for (const point of item.timeline || []) {
        const date = new Date(String(point.date) + "T00:00:00");
        const count = Number(point.meeting_count || 0);
        if (date >= window.currentStart && date <= window.latest) current += count;
        else if (date >= window.previousStart && date <= window.previousEnd) previous += count;
      }
      let status = "신규 관측";
      if (current === 0 && previous > 0) status = "최근 미관측";
      else if (current > previous && current >= Math.max(2, Math.ceil(previous * 1.5))) status = "급증";
      else if (current > 0 && previous > 0) status = "지속";
      return { ...item, current, previous, status };
    }).sort((a, b) => {
      const order = { "급증": 4, "지속": 3, "신규 관측": 2, "최근 미관측": 1 };
      return order[b.status] - order[a.status] || b.current - a.current || b.statement_count - a.statement_count;
    }).slice(0, 6);
    for (const item of rows) {
      const row = element("section", "assembly-trend-row is-" + item.status.replace(/\s/g, "-"));
      row.append(
        element("span", "", item.status),
        element("strong", "", item.topic),
        element("b", "", `최근 ${item.current}회 · 이전 ${item.previous}회`),
        element("small", "", `누적 ${Number(item.meeting_count || 0).toLocaleString()}개 회의 · 정책 발언 ${Number(item.statement_count || 0).toLocaleString()}건`),
      );
      target.append(row);
    }
  }

  function renderInstitutionFlow(payload) {
    const target = mount.querySelector("#assemblyInstitutionFlow");
    target.replaceChildren();
    const items = [...(payload.items || [])].sort(
      (a, b) => (b.bills?.length || 0) - (a.bills?.length || 0) || b.statement_count - a.statement_count,
    ).slice(0, 6);
    if (!items.length) {
      target.append(element("p", "assembly-insight-empty", "제도화 흐름을 계산할 공식 정책 발언이 없습니다."));
      return;
    }
    for (const item of items) {
      const row = element("section", "assembly-institution-row");
      const copy = element("div", "");
      copy.append(
        element("strong", "", item.topic),
        element("small", "", `공식 논의 ${Number(item.statement_count || 0).toLocaleString()}건 · ${Number(item.meeting_count || 0).toLocaleString()}개 회의`),
      );
      const stage = element("div", "assembly-institution-stage");
      stage.append(element("span", "is-done", "논의 확인"));
      const bills = item.bills || [];
      if (!bills.length) {
        stage.append(element("span", "is-waiting", "직접 연결 의안 없음"));
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
      target.append(row);
    }
  }

  async function loadGovernmentInsights() {
    try {
      const [crossResponse, flowResponse] = await Promise.all([
        fetch("api/policy/cross-institution-flow", { cache: "no-store", headers: { Accept: "application/json" } }),
        fetch("api/committees/policy-flow", { cache: "no-store", headers: { Accept: "application/json" } }),
      ]);
      if (!crossResponse.ok || !flowResponse.ok) throw new Error("insights");
      const [cross, flow] = await Promise.all([crossResponse.json(), flowResponse.json()]);
      renderPolicyTimeline(cross);
      renderIssueTrends(flow);
      renderInstitutionFlow(flow);
    } catch (_) {
      for (const selector of ["#assemblyPolicyTimeline", "#assemblyIssueTrends", "#assemblyInstitutionFlow"]) {
        const target = mount.querySelector(selector);
        target.replaceChildren(element("p", "assembly-insight-empty", "공식 인사이트 자료를 불러오지 못했습니다."));
      }
    }
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

  mount.querySelector("#assemblySeatSelectionReset").addEventListener("click", () => {
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

  let initialized = false;
  function initialize() {
    if (initialized) return;
    initialized = true;
    loadCalendar();
    loadReference();
    loadGovernmentInsights();
  }
  document.addEventListener("workspace-tab-change", (event) => {
    if (event.detail?.tab === "extras") initialize();
  });
  if (window.location.hash === "#extras" || document.querySelector("#extras")?.hidden === false) initialize();
})();
