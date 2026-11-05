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

function meetingTranscriptMarkdown(title, rows, sourceUrl, mode = "provisional") {
  const escape = (text) => String(text).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/([\\`*_{}\[\]()#+.!|~-])/g, "\\$1");
  const lines = [
    `# ${escape(title.replace(/\s+/g, " "))}`, "", "## 전체 발언 기록", "",
    mode === "official" ? "공식 자료 발언 · 원문 순서 기준입니다." : "LIVE/STT 저장 원문 · 비공식 자료. 시간은 수집 시각(KST, 한국시간) 기준입니다.", "",
    `전체 발언 ${rows.length}건`, "", `회의 보고서: <${sourceUrl}>`, "",
  ];
  for (const [index, row] of rows.entries()) {
    lines.push(`### ${index + 1}. ${mode === "official" ? "공식 발언 " + (row.sequence || index + 1) : meetingTranscriptTime(row.time)} · ${escape(row.speaker.replace(/\s+/g, " "))}`, "",
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
  const sourceNote = el("p", "", "공식 자료 유무를 확인하고 있습니다.");
  description.append(el("strong", "", title), sourceNote);
  const switches = el("div", "meeting-transcript-switch");
  switches.hidden = true;
  switches.setAttribute("role", "group");
  switches.setAttribute("aria-label", "발언 자료 선택");
  const switchButtons = {};
  for (const [key, label] of [["official", "공식 자료 발언"], ["provisional", "실시간 회의록(비공식)"]]) {
    const button = el("button", "", label); button.type = "button";
    button.addEventListener("click", () => load(key));
    switchButtons[key] = button; switches.append(button);
  }
  const status = el("p", "meeting-transcript-status", "전체 발언 기록을 불러오는 중입니다.");
  status.setAttribute("role", "status");
  const retry = el("button", "meeting-transcript-retry", "다시 불러오기");
  retry.type = "button";
  retry.hidden = true;
  const list = el("div", "meeting-transcript-list");
  list.setAttribute("role", "region");
  list.setAttribute("aria-label", "시간순 전체 발언");
  list.tabIndex = 0;
  dialog.append(header, description, switches, status, retry, list);
  let rows = [], controller, mode = null, officialAvailable = null;
  const cache = {};
  const endpoint = `api/live/broadcasts/${encodeURIComponent(item.broadcast_id)}`;
  async function load(requestedMode = null) {
    controller?.abort();
    const current = new AbortController(); controller = current;
    const timeout = window.setTimeout(() => current.abort(), 60000);
    retry.hidden = true; download.disabled = true;
    list.replaceChildren(); list.setAttribute("aria-busy", "true");
    status.textContent = "발언 기록을 불러오는 중입니다.";
    async function get(url, allowMissing = false) {
      const response = await fetch(url, {cache:"no-store", signal:current.signal});
      if (allowMissing && response.status === 404) return null;
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "발언 기록을 불러오지 못했습니다.");
      return data;
    }
    try {
      let firstPage;
      if (officialAvailable === null) {
        firstPage = await get(endpoint + "/official-utterances?limit=100&offset=0", true);
        if (controller !== current) return;
        officialAvailable = firstPage !== null;
        switches.hidden = !officialAvailable;
      }
      mode = requestedMode || (officialAvailable ? "official" : "provisional");
      for (const [key, button] of Object.entries(switchButtons)) button.setAttribute("aria-pressed", String(mode === key));
      sourceNote.textContent = mode === "official"
        ? "공식 자료 발언 · 원문에 수록된 발언 순서입니다."
        : "LIVE/STT 저장 원문 · 비공식 자료. 시간은 수집 시각(KST) 기준입니다.";
      let loaded = cache[mode];
      if (!loaded && mode === "official") {
        let page = firstPage || await get(endpoint + "/official-utterances?limit=100&offset=0");
        loaded = []; let offset = 0;
        while (true) {
          loaded.push(...(page.items || []).map((row) => ({
            id: row.utterance_id, sequence: row.sequence_number,
            speaker: [row.speaker_name || "화자 미기재", row.speaker_role].filter(Boolean).join(" · "),
            text: String(row.text || ""),
          })));
          if (!page.has_more) break;
          const next = Number(page.next_offset);
          if (!Number.isFinite(next) || next <= offset) throw new Error("발언 목록의 다음 위치를 확인할 수 없습니다.");
          offset = next;
          status.textContent = `공식 발언 ${loaded.length.toLocaleString("ko-KR")}건 불러오는 중…`;
          page = await get(endpoint + `/official-utterances?limit=100&offset=${offset}`);
        }
      } else if (!loaded) loaded = meetingTranscriptRows(await get(endpoint + "/transcript"));
      if (!dialog.open || controller !== current) return;
      cache[mode] = loaded; rows = loaded;
      const fragment = document.createDocumentFragment();
      for (const [index, row] of rows.entries()) {
        const article = el("article", "meeting-transcript-entry");
        const meta = el("header", "");
        const time = el("time", "", mode === "official" ? `공식 발언 ${row.sequence || index + 1}` : meetingTranscriptTime(row.time));
        if (mode !== "official" && Number.isFinite(Date.parse(row.time))) time.dateTime = row.time;
        meta.append(el("span", "meeting-transcript-number", String(index + 1)), time, el("strong", "", row.speaker));
        article.append(meta, el("p", "", row.text)); fragment.append(article);
      }
      list.replaceChildren(fragment); list.scrollTop = 0;
      status.textContent = rows.length ? `${mode === "official" ? "공식" : "비공식"} 발언 ${rows.length.toLocaleString("ko-KR")}건 · ${mode === "official" ? "원문 순서" : "시간순"}` : "저장된 발언 기록이 없습니다.";
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
  retry.addEventListener("click", () => load(mode));
  download.addEventListener("click", () => {
    const source = new URL(window.location.href);
    source.searchParams.set("report", item.broadcast_id);
    source.hash = "reports";
    const blob = new Blob([meetingTranscriptMarkdown(title, rows, source.href, mode)], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = el("a", "");
    anchor.href = url;
    anchor.download = `${title.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_").slice(0, 100)}_${mode === "official" ? "공식" : "비공식"}_전체발언.md`;
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
