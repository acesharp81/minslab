/* Read the saved transcript without changing the active meeting report. */
function meetingTranscriptRows(payload) {
  const utterances = (payload.utterances || []).filter((row) => String(row.text || "").trim());
  const covered = new Set(utterances.flatMap((row) => row.segment_ids || []));
  const remaining = (payload.segments || []).filter((row) =>
    String(row.text || "").trim() && !covered.has(row.segment_id));
  return [...utterances, ...remaining].map((row) => ({
    id: row.utterance_id || row.segment_id || "",
    speaker: row.speaker_label || "화자 미확인",
    text: String(row.text),
    time: row.start_at || row.received_at || "",
    cursor: Number(row.first_cursor ?? row.cursor ?? 0),
  })).sort((a, b) => {
    const left = Date.parse(a.time), right = Date.parse(b.time);
    if (Number.isFinite(left) && Number.isFinite(right) && left !== right) return left - right;
    return a.cursor - b.cursor;
  });
}

function meetingTranscriptTime(value) {
  const date = new Date(value);
  if (!value || !Number.isFinite(date.getTime())) return "시간 미기록";
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(date);
}

function meetingTranscriptMarkdown(title, rows, sourceUrl) {
  const escape = (text) => String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/([\\`*_{}\[\]()#+.!|~-])/g, "\\$1");
  const lines = [
    `# ${escape(title.replace(/\s+/g, " "))}`, "", "## 전체 발언 기록", "",
    "LIVE/STT 저장 원문 · 비공식 자료. 시간은 수집 시각(KST, 한국시간) 기준입니다.", "",
    `전체 발언 ${rows.length}건`, "", `회의 보고서: <${sourceUrl}>`, "",
  ];
  for (const [index, row] of rows.entries()) {
    lines.push(`### ${index + 1}. ${meetingTranscriptTime(row.time)} · ${escape(row.speaker.replace(/\s+/g, " "))}`, "",
      ...row.text.split(/\r?\n/).map((line) => `> ${escape(line)}`), "");
  }
  return lines.join("\n");
}

function openMeetingTranscriptDocument(item) {
  document.querySelector("#meetingTranscriptDialog")?.close();
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const dialog = el("dialog", "meeting-transcript-dialog");
  dialog.id = "meetingTranscriptDialog";
  dialog.setAttribute("aria-labelledby", "meetingTranscriptTitle");
  const header = el("header", "meeting-transcript-header");
  const heading = el("h2", "", "전체 발언 기록");
  heading.id = "meetingTranscriptTitle";
  const buttons = el("div", "meeting-transcript-actions");
  const download = el("button", "", "MD 다운로드");
  download.type = "button";
  download.disabled = true;
  const close = el("button", "", "닫기");
  close.type = "button";
  close.autofocus = true;
  close.addEventListener("click", () => dialog.close());
  buttons.append(download, close);
  header.append(heading, buttons);
  const title = item.title || item.committee_name || "회의";
  const description = el("div", "meeting-transcript-description");
  description.append(el("strong", "", title), el("p", "", "LIVE/STT 저장 원문 · 비공식 자료. 시간은 수집 시각(KST) 기준입니다."));
  const status = el("p", "meeting-transcript-status", "전체 발언 기록을 불러오는 중입니다.");
  status.setAttribute("role", "status");
  const retry = el("button", "meeting-transcript-retry", "다시 불러오기");
  retry.type = "button";
  retry.hidden = true;
  const list = el("div", "meeting-transcript-list");
  list.setAttribute("role", "region");
  list.setAttribute("aria-label", "시간순 전체 발언");
  list.tabIndex = 0;
  dialog.append(header, description, status, retry, list);
  let rows = [], controller;
  async function load() {
    controller?.abort();
    const current = new AbortController();
    controller = current;
    const timeout = window.setTimeout(() => current.abort(), 30000);
    retry.hidden = true;
    download.disabled = true;
    status.textContent = "전체 발언 기록을 불러오는 중입니다.";
    list.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(`api/live/broadcasts/${encodeURIComponent(item.broadcast_id)}/transcript`, {
        cache: "no-store", signal: current.signal,
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "발언 기록을 불러오지 못했습니다.");
      if (!dialog.open || controller !== current) return;
      rows = meetingTranscriptRows(payload);
      const fragment = document.createDocumentFragment();
      for (const [index, row] of rows.entries()) {
        const article = el("article", "meeting-transcript-entry");
        const meta = el("header", "");
        const time = el("time", "", meetingTranscriptTime(row.time));
        if (Number.isFinite(Date.parse(row.time))) time.dateTime = row.time;
        meta.append(el("span", "meeting-transcript-number", String(index + 1)), time, el("strong", "", row.speaker));
        article.append(meta, el("p", "", row.text));
        fragment.append(article);
      }
      list.replaceChildren(fragment);
      status.textContent = rows.length ? `전체 발언 ${rows.length.toLocaleString("ko-KR")}건 · 시간순` : "저장된 발언 기록이 없습니다.";
      download.disabled = !rows.length;
    } catch (error) {
      if (!dialog.open || controller !== current) return;
      status.textContent = error.name === "AbortError" ? "응답이 지연되고 있습니다. 다시 불러와 주세요." : error.message;
      retry.hidden = false;
    } finally {
      window.clearTimeout(timeout);
      if (controller === current) list.removeAttribute("aria-busy");
    }
  }
  retry.addEventListener("click", load);
  download.addEventListener("click", () => {
    const source = new URL(window.location.href);
    source.searchParams.set("report", item.broadcast_id);
    source.hash = "reports";
    const blob = new Blob([meetingTranscriptMarkdown(title, rows, source.href)], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = el("a", "");
    anchor.href = url;
    anchor.download = `${title.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").slice(0, 100)}_전체발언.md`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  dialog.addEventListener("close", () => { controller?.abort(); dialog.remove(); }, { once: true });
  document.body.append(dialog);
  dialog.showModal();
  load();
}
