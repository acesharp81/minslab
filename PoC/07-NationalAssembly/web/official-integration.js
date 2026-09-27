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
    if (part.kind === "deleted") {
      // This is an official-first view. Rendering deleted LIVE wording inline
      // duplicates the sentence and makes the official projection look like
      // it overwrote the draft. The before/after card preserves that wording.
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

function meetingBriefViewSwitch(activeView, onChange, sourceOnly = false) {
  const control = magazineElement("div", "meeting-brief-view-switch", "");
  control.setAttribute("role", "group");
  control.setAttribute("aria-label", "회의 보고서 자료 기준");
  for (const [view, label] of [
    ["official", sourceOnly ? "공식 발언·화자" : "공식 대조본"],
    ["provisional", "LIVE/STT 초안"],
  ]) {
    const button = magazineElement("button", "", label);
    button.type = "button";
    button.dataset.briefView = view;
    button.setAttribute("aria-pressed", String(activeView === view));
    button.addEventListener("click", () => onChange(view));
    control.append(button);
  }
  return control;
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
    const sourceOnly = integration.comparison_mode === "SOURCE_ONLY_TIMEOUT";
    const changes = Number(integration.change_count || 0);
    const points = (record?.official_brief?.topics || [])
      .flatMap((topic) => topic.speaker_points || []);
    const verifiedPoints = points.filter(
      (point) => point.speaker_official === true
        && point.official_evidence_ids?.length
        && !String(point.speaker_label || "").startsWith("화자"),
    ).length;
    const unresolvedPoints = (record?.official_brief?.topics || [])
      .flatMap((topic) => topic.draft_only_speaker_points || []).length;
    const speakers = Number(integration.speaker_stats?.confirmed_speakers || 0);
    bar.append(
      magazineElement(
        "strong", "",
        sourceOnly ? "공식 발언·화자 반영 · 요약 대조 지연"
          : unresolvedPoints ? "공식 대조 완료 · 화자 검토 필요" : "공식 자료 대조 완료",
      ),
      magazineElement("span", "", sourceOnly ? "요약은 LIVE 초안 기반"
        : changes ? `본문 변경 ${changes}곳` : "본문 변경 없음"),
      magazineElement(
        "span", "",
        points.length
          ? `화자 요지 ${verifiedPoints}/${points.length}개 확인 · ${unresolvedPoints}개 검토 필요`
          : speakers ? `공식 화자 ${speakers}명 반영` : "화자 근거 대조 완료",
      ),
    );
  } else {
    const stage = String(context.processing_stage || "");
    const stageLabels = {
      OFFICIAL_PUBLICATION_PENDING: "공식 자료 게시 대기",
      OFFICIAL_BODY_PENDING: "공식 본문 수집·연결 대기",
      COMPARISON_QUEUED: "비공식·공식 대조 대기",
      COMPARISON_PROCESSING: "비공식·공식 대조 중",
      COMPARISON_RETRY_WAIT: "대조 오류 · 자동 재시도 대기",
      COMPARISON_FAILED: "대조 오류 · 확인 필요",
    };
    bar.append(
      magazineElement("strong", "", "LIVE 잠정 결과"),
      magazineElement(
        "span", "", stageLabels[stage]
          || (context.official_status === "PUBLISHED"
            ? "비공식·공식 대조 대기" : "공식 자료 게시 대기"),
      ),
    );
    if (stage === "COMPARISON_RETRY_WAIT" && context.integration_next_attempt_at) {
      const retryAt = new Date(context.integration_next_attempt_at);
      if (!Number.isNaN(retryAt.getTime())) {
        bar.append(magazineElement(
          "small", "", `${retryAt.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })} 재시도`,
        ));
      }
    }
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

function officialChangeValue(value) {
  if (value === null || value === undefined || value === "") return "내용 없음";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function renderOfficialChangeReport(record) {
  const integration = record?.official_integration || {};
  if (integration.status !== "READY") return null;
  const state = record?.official_change_report || {};
  const status = state.status || "PENDING";
  const section = magazineElement(
    "section", `official-change-report is-${String(status).toLowerCase()}`, "",
  );
  const head = magazineElement("header", "", "");
  head.append(
    magazineElement("span", "", "비공식 보고 ↔ 공식 자료"),
    magazineElement("h4", "", "공식화 변화 간단 보고"),
  );
  if (["PENDING", "PROCESSING"].includes(status)) {
    head.append(magazineElement(
      "p", "", "검증된 변경을 묶어 한눈에 볼 수 있는 요약을 작성 중입니다. 기존 변경 표시는 계속 확인할 수 있습니다.",
    ));
    section.append(head, magazineElement("div", "official-change-loading", "공식화 변화 정리 중"));
    return section;
  }
  if (["FAILED", "LIMIT_REACHED"].includes(status)) {
    head.append(magazineElement(
      "p", "", "간단 요약을 만들지 못했습니다. 서버가 검증한 본문 변경 표시는 그대로 제공합니다.",
    ));
    section.append(head);
    return section;
  }
  if (status !== "READY") return null;
  const report = state.report || {};
  const summary = magazineElement("div", "official-change-summary", "");
  summary.append(
    magazineElement("strong", "", report.overall_assessment || "공식 자료 대조 완료"),
    magazineElement("p", "", report.summary || "공식 자료와 대조한 변경 결과입니다."),
  );
  if (report.speaker_note) summary.append(magazineElement("small", "", report.speaker_note));
  section.append(head, summary);
  const list = magazineElement("div", "official-change-list", "");
  for (const item of report.items || []) {
    const card = magazineElement("article", "official-change-item", "");
    const cardHead = magazineElement("header", "", "");
    cardHead.append(
      magazineElement("span", "", item.importance || "보완"),
      magazineElement("strong", "", item.title || "공식화 변경"),
      magazineElement("p", "", item.explanation || ""),
    );
    card.append(cardHead);
    const pairs = magazineElement("div", "official-change-pairs", "");
    for (const change of item.changes || []) {
      const pair = magazineElement("div", "official-change-pair", "");
      const before = magazineElement("div", "is-before", "");
      const after = magazineElement("div", "is-after", "");
      before.append(
        magazineElement("b", "", "비공식"),
        magazineElement("p", "", officialChangeValue(change.before)),
      );
      after.append(
        magazineElement("b", "", "공식"),
        magazineElement("p", "", officialChangeValue(change.after)),
      );
      pair.append(before, after);
      if (change.presentation_status === "FULL_REWRITE_SUPPRESSED") {
        pair.append(magazineElement(
          "small", "", "문장 전체 교체로 보이는 항목은 본문 워딩을 유지하고 공식 표현을 이 비교란에만 제공합니다.",
        ));
      }
      pairs.append(pair);
    }
    card.append(pairs);
    list.append(card);
  }
  if (list.children.length) {
    const disclosure = magazineElement("div", "official-change-disclosure", "");
    const toggle = magazineElement("button", "official-change-toggle", "");
    const toggleLabel = magazineElement("span", "", "상세 내용 펼치기");
    toggle.type = "button";
    toggle.setAttribute("aria-expanded", "false");
    toggle.append(
      toggleLabel,
      magazineElement("small", "", `${list.children.length}건`),
      magazineElement("i", "", "⌄"),
    );
    list.hidden = true;
    toggle.addEventListener("click", () => {
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      toggleLabel.textContent = expanded ? "상세 내용 펼치기" : "상세 내용 접기";
      list.hidden = expanded;
    });
    disclosure.append(toggle, list);
    section.append(disclosure);
  }
  return section;
}
