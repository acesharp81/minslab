// 저장된 요약 투영을 문서로 표시한다. 화면의 펼침 상태나 원문 인용은 복사하지 않는다.
const MEETING_DOCUMENT_KEYWORD_STOPWORDS = new Set((
  "관련 대한 관한 위한 통해 대해 따른 등 및 또는 이번 현재 경우 상황 문제 지적 필요 필요성 개선 " +
  "요구 요청 제기 의혹 논란 여부 방안 현황 검토 자료 제출 입장 질의 답변 설명 주장 확인 추진 " +
  "대응 관리 운영 실태 사항 강화 점검 과정 제도 국정감사 국회 표명 우려"
).split(" "));

function meetingDocumentSource(record, preferredView) {
  const view = preferredView || (record.default_brief_view === "OFFICIAL" ? "official"
    : record.structured_brief ? "structured" : "provisional");
  if (view === "official" && record.official_brief) return { view, brief: record.official_brief };
  if (view === "structured" && record.structured_brief) return { view, brief: record.structured_brief };
  return { view: "provisional", brief: record.provisional_brief || record.brief || {} };
}

function meetingDocumentOverview(brief, groups) {
  // Count each displayed subtopic once, including older reports without IDs.
  const seen = new Set();
  const keywords = new Map();
  const distribution = [];
  let total = 0;
  groups.forEach((group, groupIndex) => {
    let count = 0;
    group.topics.forEach((topic, topicIndex) => {
      const id = topic.id || `${groupIndex}:${topicIndex}`;
      if (seen.has(id)) return;
      seen.add(id);
      count += 1;
      total += 1;
      // Document frequency in subtopic titles, not raw speech frequency.
      const words = new Set((String(topic.title || "").normalize("NFC").match(/[가-힣A-Za-z][가-힣A-Za-z0-9]+/g) || [])
        .map((word) => /^[A-Za-z0-9]+$/.test(word) ? word.toUpperCase() : word)
        .filter((word) => !MEETING_DOCUMENT_KEYWORD_STOPWORDS.has(word) && word.length <= 24));
      for (const word of words) keywords.set(word, (keywords.get(word) || 0) + 1);
    });
    if (count) distribution.push({ label: group.title || "대주제", count });
  });
  distribution.sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "ko"));
  const topicRows = distribution.slice(0, 6);
  const remainder = distribution.slice(6);
  if (remainder.length) topicRows.push({
    label: `기타 ${remainder.length}개 대주제`, count: remainder.reduce((sum, row) => sum + row.count, 0), other: true,
  });
  const keywordRows = [...keywords].map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "ko")).slice(0, 8);
  const summary = [brief.summary, brief.report_summary?.summary].find((value) => typeof value === "string" && value.trim()) || "";
  return { summary: summary.trim(), total, topicRows, keywordRows };
}

function meetingDocumentBarChart(title, description, rows, total, kind) {
  const figure = magazineElement("figure", `meeting-summary-chart is-${kind}`, "");
  const caption = magazineElement("figcaption", "", "");
  caption.append(magazineElement("h3", "", title), magazineElement("p", "meeting-summary-chart-note", description));
  figure.append(caption);
  if (!rows.length) {
    figure.append(magazineElement("p", "meeting-summary-paper-empty", "집계할 항목이 없습니다."));
    return figure;
  }
  const list = magazineElement("ol", "meeting-summary-chart-list", "");
  const maximum = Math.max(...rows.map((row) => row.count), 1);
  for (const row of rows) {
    const li = magazineElement("li", row.other ? "is-other" : "", "");
    const label = magazineElement("div", "meeting-summary-chart-label", "");
    const percent = total ? (row.count / total * 100).toLocaleString("ko-KR", { maximumFractionDigits: 1 }) : "0";
    label.append(magazineElement("span", "", row.label), magazineElement("strong", "",
      kind === "topics" ? `${row.count}개 · ${percent}%` : `${row.count}개 제목`));
    const track = magazineElement("div", "meeting-summary-chart-track", "");
    track.setAttribute("aria-hidden", "true");
    const bar = magazineElement("span", "meeting-summary-chart-bar", "");
    bar.style.width = `${row.count / maximum * 100}%`;
    track.append(bar);
    li.append(label, track);
    list.append(li);
  }
  figure.append(list);
  return figure;
}

function buildMeetingReportDocument(item, record, brief, briefView) {
  const narrative = brief.report_summary || {};
  const topics = narrative.topics || [];
  const byId = new Map(topics.map((topic) => [topic.id, topic]));
  const groups = (narrative.topic_groups?.length ? narrative.topic_groups : topics.map((topic) => ({
    title: topic.title, topic_ids: [topic.id],
  }))).map((group) => ({
    ...group, topics: (group.topic_ids || []).map((id) => byId.get(id)).filter(Boolean),
  })).filter((group) => group.topics.length);
  const paper = magazineElement("article", "meeting-summary-paper", "");
  const header = magazineElement("header", "meeting-summary-paper-header", "");
  header.append(
    magazineElement("p", "meeting-summary-paper-brand", "국정ON · 회의 요약 보고서"),
    magazineElement("h1", "", brief.headline || item.title || "회의 요약 보고서"),
  );
  const viewLabel = briefView === "official" ? "공식 회의록 대조 화면 기준"
    : briefView === "structured" ? "구조화된 LIVE 저장본 기준" : "LIVE 잠정 보고서 기준";
  const metadata = [item.committee_name, viewLabel].filter(Boolean);
  if (record.generated_at) {
    const date = new Date(record.generated_at);
    if (!Number.isNaN(date.valueOf())) metadata.push(`보고서 생성 ${new Intl.DateTimeFormat("ko-KR", {
      timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", hour12: false,
    }).format(date)} (KST)`);
  }
  header.append(magazineElement("p", "meeting-summary-paper-meta", metadata.join(" · ")));
  const pointCount = groups.reduce((total, group) => total + group.topics.reduce(
    (count, topic) => count + (topic.speaker_points || []).filter((point) => point.summary?.trim()).length, 0,
  ), 0);
  header.append(
    magazineElement("p", "meeting-summary-paper-counts", `대주제 ${groups.length}개 · 소주제 ${groups.reduce((total, group) => total + group.topics.length, 0)}개 · 세부 발언 요약 ${pointCount}개`),
    magazineElement("p", "meeting-summary-paper-authority", "AI 요약 · 잠정 정보 | 근거 발언과 공식 원문은 온라인 보고서에서 확인할 수 있습니다."),
  );
  paper.append(header);
  const overview = meetingDocumentOverview(brief, groups);
  if (overview.summary || overview.total) {
    const section = magazineElement("section", "meeting-summary-overview", "");
    section.setAttribute("aria-label", "회의 전체 요약과 주요 논의 분포");
    if (overview.summary) {
      const introduction = magazineElement("div", "meeting-summary-introduction", "");
      introduction.append(magazineElement("h2", "", "회의 전체 요약"),
        magazineElement("p", "meeting-summary-introduction-text", overview.summary));
      section.append(introduction);
    }
    if (overview.total) {
      const charts = magazineElement("div", "meeting-summary-charts", "");
      charts.append(
        meetingDocumentBarChart("주제별 논의 분포", `소주제 ${overview.total}개 기준 · 상위 6개 대주제와 기타`, overview.topicRows, overview.total, "topics"),
        meetingDocumentBarChart("주요 키워드 빈도", "소주제 제목에 등장한 주요 단어 · 상위 8개", overview.keywordRows, overview.total, "keywords"),
      );
      section.append(charts, magazineElement("p", "meeting-summary-overview-note",
        "주제 비중은 소주제 수 기준입니다. 키워드는 제목별 동일 단어를 한 번씩 집계하며 일반 표현은 제외합니다. 발언 횟수·시간이나 중요도 순위는 아닙니다. 전체 논의는 다음 본문에 수록했습니다."));
    }
    paper.append(section);
  }
  groups.forEach((group, groupIndex) => {
    const section = magazineElement("section", "meeting-summary-paper-group", "");
    section.append(magazineElement("h2", "", `${groupIndex + 1}. ${group.title || "대주제"}`));
    group.topics.forEach((topic, topicIndex) => {
      const subsection = magazineElement("section", "meeting-summary-paper-topic", "");
      subsection.dataset.topicId = topic.id;
      subsection.append(magazineElement("h3", "", `${groupIndex + 1}-${topicIndex + 1}. ${topic.title || "소주제"}`));
      if (topic.summary?.trim()) subsection.append(magazineElement("p", "meeting-summary-paper-topic-summary", topic.summary));
      const points = (topic.speaker_points || []).filter((point) => point.summary?.trim());
      if (points.length) {
        const list = magazineElement("ul", "meeting-summary-paper-points", "");
        for (const point of points) {
          const row = magazineElement("li", "", "");
          row.dataset.pointId = point.id;
          const speaker = String(point.speaker_label || "").trim();
          if (speaker && !speaker.startsWith("화자")) {
            row.append(magazineElement("strong", "", speaker + " · "));
          }
          row.append(document.createTextNode(point.summary));
          list.append(row);
        }
        subsection.append(list);
      } else if (!topic.summary?.trim()) {
        subsection.append(magazineElement("p", "meeting-summary-paper-empty", "저장된 발언 요약이 없습니다."));
      }
      section.append(subsection);
    });
    paper.append(section);
  });
  if (!groups.length) paper.append(magazineElement("p", "meeting-summary-paper-empty", "아직 저장된 AI 요약이 없습니다. 요약이 생성된 뒤 다시 확인해 주세요."));
  const footer = magazineElement("footer", "meeting-summary-paper-footer", "");
  const url = new URL(window.location.href);
  url.search = "";
  url.searchParams.set("report", item.broadcast_id);
  url.hash = "reports";
  const link = magazineElement("a", "", "온라인 보고서 · 근거 발언 확인");
  link.href = url.href;
  footer.append(magazineElement("span", "", "국정ON · 회의 요약 보고서"), link);
  paper.append(footer);
  return paper;
}

function openMeetingReportDocument(item, record, brief, briefView) {
  document.querySelector("#meetingReportDocumentDialog")?.close();
  const dialog = magazineElement("dialog", "meeting-summary-document-dialog", "");
  dialog.id = "meetingReportDocumentDialog";
  dialog.setAttribute("aria-labelledby", "meetingReportDocumentTitle");
  const toolbar = magazineElement("header", "meeting-summary-document-toolbar", "");
  const copy = magazineElement("div", "", "");
  const title = magazineElement("h2", "", "회의 요약 문서");
  title.id = "meetingReportDocumentTitle";
  copy.append(title, magazineElement("p", "", "전체 요약·주제 및 키워드 그래프 → 대주제 → 소주제 → 발언 요약 · PDF는 인쇄 창에서 ‘PDF로 저장’을 선택하세요."));
  const actions = magazineElement("div", "meeting-summary-document-actions", "");
  const print = magazineElement("button", "is-primary", "인쇄 · PDF 저장");
  print.type = "button";
  print.addEventListener("click", () => window.print());
  const close = magazineElement("button", "", "닫기");
  close.type = "button";
  close.autofocus = true;
  close.addEventListener("click", () => dialog.close());
  actions.append(print, close);
  toolbar.append(copy, actions);
  const viewport = magazineElement("div", "meeting-summary-document-body", "");
  viewport.tabIndex = 0;
  viewport.setAttribute("aria-label", "회의 요약 문서 본문");
  viewport.append(buildMeetingReportDocument(item, record, brief, briefView));
  dialog.append(toolbar, viewport);
  dialog.addEventListener("close", () => {
    document.body.classList.remove("meeting-summary-document-open");
    finishMeetingReportPrint();
    dialog.remove();
  }, { once: true });
  document.body.append(dialog);
  document.body.classList.add("meeting-summary-document-open");
  dialog.showModal();
}

let meetingReportPrintTitle = null;
function finishMeetingReportPrint() {
  document.body.classList.remove("meeting-document-print-mode");
  if (meetingReportPrintTitle !== null) {
    document.title = meetingReportPrintTitle;
    meetingReportPrintTitle = null;
  }
}

// 미리보기에서 Ctrl+P를 눌러도 동일한 문서를 출력하고 인쇄 취소 후 미리보기를 유지한다.
window.addEventListener("beforeprint", () => {
  if (document.querySelector("#meetingReportDocumentDialog[open]")) {
    document.body.classList.add("meeting-document-print-mode");
    if (meetingReportPrintTitle === null) meetingReportPrintTitle = document.title;
    document.title = document.querySelector("#meetingReportDocumentDialog h1").textContent + " · 국정ON";
  }
});
window.addEventListener("afterprint", finishMeetingReportPrint);
