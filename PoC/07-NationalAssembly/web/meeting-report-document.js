// 저장된 요약 투영을 문서로 표시한다. 화면의 펼침 상태나 원문 인용은 복사하지 않는다.
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
  copy.append(title, magazineElement("p", "", "대주제 → 소주제 → 발언 요약 · PDF는 인쇄 창에서 ‘PDF로 저장’을 선택하세요."));
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
