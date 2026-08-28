function appendOfficialInlineDiff(container, value, diffSpans, changeKind = "") {
  const spans = Array.isArray(diffSpans) && diffSpans.length
    ? diffSpans
    : changeKind === "added" ? [{ kind: "added", text: String(value || "") }]
      : changeKind === "deleted" ? [{ kind: "deleted", text: String(value || "") }]
        : [{ kind: "equal", text: String(value || "") }];
  for (const part of spans) {
    if (part.kind === "equal") {
      container.append(document.createTextNode(part.text || ""));
      continue;
    }
    const mark = magazineElement(
      "mark", `official-inline-change is-${part.kind}`, part.text || "",
    );
    const description = part.kind === "changed"
      ? `이전 문구: ${part.before || "내용 없음"}`
      : part.kind === "added" ? "공식 자료에서 추가된 문구"
        : "공식 자료 반영 과정에서 삭제된 문구";
    mark.dataset.changeDescription = description;
    mark.title = description;
    mark.tabIndex = 0;
    mark.setAttribute("aria-label", `${part.text || "삭제 문구"}. ${description}`);
    container.append(mark);
  }
  return container;
}

function officialTextElement(tag, className, value, entity, field) {
  const element = magazineElement(tag, className, "");
  return appendOfficialInlineDiff(
    element, value, entity?._official_diffs?.[field], entity?._official_change,
  );
}

function meetingIntegrationBar(item, record) {
  const integration = record?.official_integration || {};
  const context = record?.official_context || {};
  const bar = magazineElement("section", "meeting-integration-bar", "");
  if (integration.status === "READY") {
    const changes = Number(integration.change_count || 0);
    const speakers = Number(integration.speaker_stats?.confirmed_speakers || 0);
    bar.append(
      magazineElement("strong", "", "공식 자료 대조 완료"),
      magazineElement("span", "", changes ? `본문 변경 ${changes}곳` : "본문 변경 없음"),
      magazineElement(
        "span", "", speakers ? `공식 화자 ${speakers}명 반영` : "화자 근거 대조 완료",
      ),
    );
  } else {
    bar.append(
      magazineElement("strong", "", "LIVE 잠정 결과"),
      magazineElement(
        "span", "", context.official_status === "PUBLISHED"
          ? "공식 자료 대조 중" : "공식 자료 게시 대기",
      ),
    );
  }
  const url = context.official_url || context.official_pdf_url;
  if (url) {
    const link = magazineElement("a", "", "공식 원문 ↗");
    link.href = url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    bar.append(link);
  }
  return bar;
}
