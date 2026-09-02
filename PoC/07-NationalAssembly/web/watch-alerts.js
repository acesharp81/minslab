(() => {
  const TOKEN_KEY = "poc07.watch.token.v1";
  const RULES_KEY = "poc07.watch.rules.v1";
  const ADMIN_SESSION_KEY = "poc07.watch.admin.session.v1";
  const NOTIFICATION_LIMIT = 12;
  const state = {
    token: window.localStorage.getItem(TOKEN_KEY) || "",
    cookieReady: false,
    rules: [],
    notifications: [],
    unread: 0,
    testId: "",
    testTimer: null,
    testFinishTimer: null,
    notificationTimer: null,
    editingRuleId: "",
    currentRuleReport: null,
    reportTimer: null,
    kakao: { configured: false, connected: false, status: "NOT_CONNECTED" },
  };

  const element = (selector) => document.querySelector(selector);
  const panel = element("#watchAlertPanel");
  const shade = element("#watchPanelShade");
  const trigger = element("#topTabLive");
  const mount = element("#liveAlertMount");
  const embedded = Boolean(panel?.classList.contains("is-embedded") && mount);
  if (embedded) {
    mount.append(panel);
    panel.hidden = false;
    shade.hidden = true;
  }

  async function ensureToken(force = false) {
    if (state.cookieReady && !force) return "";
    if (state.token && !force) {
      const response = await fetch("api/watch/session/upgrade", {
        method: "POST",
        headers: { "X-Watch-Token": state.token },
        cache: "no-store",
        credentials: "same-origin",
      });
      if (response.ok) {
        state.token = "";
        state.cookieReady = true;
        window.localStorage.removeItem(TOKEN_KEY);
        document.dispatchEvent(new CustomEvent("watch-session-ready"));
        return "";
      }
    }
    const response = await fetch("api/watch/session", {
      method: "POST", cache: "no-store", credentials: "same-origin",
    });
    if (!response.ok) throw new Error("관심주제 세션을 시작할 수 없습니다.");
    const payload = await response.json();
    if (String(payload.session_mode || "").toUpperCase().startsWith("COOKIE")) {
      state.token = "";
      state.cookieReady = true;
      window.localStorage.removeItem(TOKEN_KEY);
    } else {
      state.token = payload.token || "";
      if (state.token) window.localStorage.setItem(TOKEN_KEY, state.token);
    }
    document.dispatchEvent(new CustomEvent("watch-session-ready"));
    return state.token;
  }

  async function watchFetch(path, options = {}, retry = true) {
    await ensureToken();
    const headers = new Headers(options.headers || {});
    if (state.token) headers.set("X-Watch-Token", state.token);
    if (options.body) headers.set("Content-Type", "application/json");
    const response = await fetch(path, { ...options, headers, cache: "no-store" });
    if (response.status === 401 && retry) {
      state.cookieReady = false;
      state.token = "";
      window.localStorage.removeItem(TOKEN_KEY);
      await ensureToken(true);
      return watchFetch(path, options, false);
    }
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "요청을 처리할 수 없습니다.");
    }
    return response.json();
  }

  function openPanel() {
    if (embedded) {
      trigger?.click();
      panel.hidden = false;
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
      loadRules();
      loadNotifications();
      return;
    }
    panel.hidden = false;
    shade.hidden = false;
    trigger?.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
    loadRules();
    loadNotifications();
  }

  function closePanel() {
    if (embedded) {
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    panel.hidden = true;
    shade.hidden = true;
    trigger?.setAttribute("aria-expanded", "false");
    document.body.style.removeProperty("overflow");
  }

  function textNode(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text;
    return node;
  }

  function formatTime(value) {
    if (!value) return "";
    return new Intl.DateTimeFormat("ko-KR", {
      month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
    }).format(new Date(value));
  }

  function localRules() {
    const saved = window.localStorage.getItem(RULES_KEY);
    if (saved === null) return null;
    try {
      const parsed = JSON.parse(saved);
      return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
      window.localStorage.removeItem(RULES_KEY);
      return null;
    }
  }

  function saveLocalRules(rules) {
    window.localStorage.setItem(RULES_KEY, JSON.stringify(rules));
  }

  function serverRulePayload(rule) {
    return {
      name: rule.name,
      include_terms: rule.include_terms,
      exclude_terms: rule.exclude_terms || [],
      institution: rule.institution || null,
      committee_name: rule.committee_name || null,
      notification_policy: rule.notification_policy || "FIRST_PER_MEETING",
      digest_enabled: Boolean(rule.digest_enabled),
      kakao_enabled: Boolean(rule.kakao_enabled),
    };
  }

  function ruleIdentity(rule) {
    return JSON.stringify([
      String(rule.name || "").trim().toLocaleLowerCase("ko-KR"),
      [...(rule.include_terms || [])].map((term) => String(term).trim().toLocaleLowerCase("ko-KR")).sort(),
      rule.institution || "",
    ]);
  }

  async function synchronizeLocalRules(serverRules) {
    const saved = localRules();
    if (saved === null) {
      const seen = new Set();
      const unique = [];
      for (const rule of serverRules) {
        const identity = ruleIdentity(rule);
        if (seen.has(identity)) {
          continue;
        }
        seen.add(identity);
        unique.push(rule);
      }
      saveLocalRules(unique);
      return unique;
    }
    const serverById = new Map(serverRules.map((rule) => [String(rule.rule_id), rule]));
    const serverByIdentity = new Map(serverRules.map((rule) => [ruleIdentity(rule), rule]));
    const synchronized = [];
    for (const localRule of saved) {
      const serverRule = serverById.get(String(localRule.rule_id || ""))
        || serverByIdentity.get(ruleIdentity(localRule));
      if (serverRule) {
        synchronized.push(serverRule);
        serverById.delete(String(serverRule.rule_id));
        serverByIdentity.delete(ruleIdentity(serverRule));
        continue;
      }
      const created = await watchFetch("api/watch/rules", {
        method: "POST", body: JSON.stringify(serverRulePayload(localRule)),
      });
      synchronized.push(created);
    }
    for (const orphan of serverById.values()) synchronized.push(orphan);
    saveLocalRules(synchronized);
    return synchronized;
  }

  function renderRules() {
    const container = element("#watchRuleList");
    container.replaceChildren();
    if (!state.rules.length) {
      container.append(textNode("p", "watch-rule-empty", "아직 설정한 알림 주제가 없습니다."));
    }
    for (const rule of state.rules) {
      const item = textNode("article", "watch-rule-item", "");
      const body = document.createElement("div");
      const scope = rule.institution === "LEGISLATURE"
        ? "국회" : rule.institution === "EXECUTIVE" ? "정부" : "전체";
      body.append(
        textNode("strong", "", rule.name),
        textNode("span", "", rule.include_terms.join(" · ")),
      );
      const scopeBadge = textNode("small", "watch-rule-scope", scope);
      const policyLabel = {
        FIRST_PER_MEETING: "회의 1회",
        FIRST_PER_SPEAKER: "화자별",
        ONCE_PER_10_MINUTES: "10분",
        INTERVAL_15_MINUTES: "15분",
        INTERVAL_30_MINUTES: "30분",
        INTERVAL_60_MINUTES: "60분",
        EVERY_MATCH: "매회",
      }[rule.notification_policy] || "회의 1회";
      scopeBadge.textContent = `${scope} · ${policyLabel}${rule.digest_enabled ? " · 종료요약" : ""}${rule.kakao_enabled ? " · 카카오" : ""}`;
      const actions = textNode("div", "watch-rule-actions", "");
      const report = textNode("button", "watch-rule-report-button", "지금까지 보고서");
      report.type = "button";
      report.addEventListener("click", () => openRuleReport(rule));
      const edit = textNode("button", "", "수정");
      edit.type = "button";
      edit.addEventListener("click", () => editRule(rule));
      const remove = textNode("button", "", "삭제");
      remove.type = "button";
      remove.addEventListener("click", () => deleteRule(rule.rule_id));
      actions.append(report, edit, remove);
      item.append(body, scopeBadge, actions);
      container.append(item);
    }
    element("#watchTestStart").disabled = !state.rules.some((rule) => rule.enabled !== false);
  }

  async function loadRules() {
    const container = element("#watchRuleList");
    try {
      const payload = await watchFetch("api/watch/rules");
      state.rules = await synchronizeLocalRules(payload.items || []);
      renderRules();
    } catch (error) {
      container.replaceChildren(textNode("p", "", error.message));
    }
  }

  async function deleteRule(ruleId) {
    if (!window.confirm("이 관심주제를 삭제할까요? 과거 알림 기록도 함께 정리됩니다.")) return;
    await watchFetch(`api/watch/rules/${encodeURIComponent(ruleId)}`, { method: "DELETE" });
    state.rules = state.rules.filter((rule) => String(rule.rule_id) !== String(ruleId));
    saveLocalRules(state.rules);
    renderRules();
    await loadNotifications();
  }

  function ruleReportMarkdown(payload) {
    const lines = [
      "# " + (payload.rule_name || "알림 주제") + " 현재 보고서",
      "",
      "- 회의: " + (payload.title || "아직 감지된 회의 없음"),
      "- 범위: " + (payload.institution || "국회·정부 전체"),
      "- 감지 문구: " + (payload.include_terms || []).join(", "),
      "- 근거 발언: " + Number(payload.match_count || 0) + "개",
      "- 생성 기준: " + new Date().toLocaleString("ko-KR"),
      "- 이번 조회 새 요약 예약: " + (payload.summary_requested ? "예" : "아니오 · 저장본 재사용"),
      "",
      "## 현재까지 요약",
      "",
    ];
    if (payload.integrated_summary?.claims?.length) {
      lines.push(payload.integrated_summary.summary || "", "", "## 핵심 논의", "");
      for (const claim of payload.integrated_summary.claims) {
        lines.push("### " + (claim.title || "핵심 논의"), "", claim.text, "");
      }
    } else if (payload.current_summary?.length) {
      for (const item of payload.current_summary) {
        lines.push("- " + item.speaker_label + ": " + item.summary);
      }
    } else {
      lines.push("- 아직 이 주제와 일치하는 발언이 없습니다.");
    }
    lines.push("", "## 근거 발언", "");
    for (const match of payload.matches || []) {
      lines.push(
        "### " + (match.speaker_label || "화자 확인 중"),
        "",
        match.excerpt || "",
        "",
        "감지 문구: " + (match.matched_term || ""),
        "",
      );
    }
    return lines.join("\n");
  }

  function reportEvidenceDetails(matches, evidenceIds, label) {
    const allowed = evidenceIds?.length
      ? new Set(evidenceIds.map((value) => String(value)))
      : null;
    const selected = (matches || []).filter((match) => !allowed || allowed.has(String(match.match_id)));
    const details = textNode("details", "watch-rule-report-evidence-details", "");
    const toggle = textNode("summary", "", label + " · " + selected.length + "개");
    details.append(toggle);
    const list = textNode("div", "watch-rule-report-evidence-list", "");
    for (const match of selected) {
      const article = textNode("article", "", "");
      article.append(
        textNode("strong", "", match.speaker_label || "화자 확인 중"),
        textNode("span", "", match.matched_term || "감지 문구"),
      );
      const paragraph = document.createElement("p");
      appendHighlightedText(paragraph, match.excerpt || "", match.matched_term || "");
      article.append(paragraph);
      list.append(article);
    }
    details.append(list);
    return details;
  }

  function renderRuleReport(payload) {
    state.currentRuleReport = payload;
    const dialog = element("#watchRuleReportDialog");
    const body = element("#watchRuleReportBody");
    const hasIntegrated = Boolean(payload.integrated_summary?.claims?.length);
    element("#watchRuleReportTitle").textContent = payload.rule_name || "알림 주제 현재 보고서";
    element("#watchRuleReportMeta").textContent = payload.title
      ? payload.title + " · 관련 발언 " + Number(payload.match_count || 0) + "개"
      : "아직 감지된 회의가 없습니다.";
    body.replaceChildren();

    const summary = textNode("section", "watch-rule-report-summary", "");
    if (hasIntegrated && payload.integrated_summary.summary) {
      const overview = textNode("div", "watch-rule-report-overview", "");
      overview.append(textNode("strong", "", "현재까지의 종합 판단"));
      const overviewText = document.createElement("p");
      appendHighlightedTerms(
        overviewText, payload.integrated_summary.summary, payload.include_terms || [],
      );
      overview.append(overviewText);
      summary.append(overview);
    }
    summary.append(textNode("h3", "", hasIntegrated ? "핵심 논의" : "확인된 주요 발언"));
    const claimList = textNode("div", "watch-rule-report-claim-list", "");
    const claims = hasIntegrated
      ? payload.integrated_summary.claims.map((claim) => ({
          text: claim.text, evidence_ids: claim.evidence_ids || [],
          speaker_label: claim.title || "핵심 논의",
        }))
      : (payload.current_summary || []).map((item) => ({
          text: item.summary, evidence_ids: item.match_id ? [item.match_id] : [],
          speaker_label: item.speaker_label || "화자 확인 중",
        }));
    claims.forEach((claim, index) => {
      const article = textNode("article", "watch-rule-report-claim", "");
      const head = textNode("div", "", "");
      head.append(
        textNode("span", "watch-rule-report-claim-number", String(index + 1)),
        textNode("strong", "", claim.speaker_label),
      );
      const claimText = document.createElement("p");
      appendHighlightedTerms(claimText, claim.text || "", payload.include_terms || []);
      article.append(head, claimText);
      if (claim.evidence_ids.length) {
        article.append(reportEvidenceDetails(payload.matches, claim.evidence_ids, "근거 발언 확인"));
      }
      claimList.append(article);
    });
    if (!claims.length) {
      claimList.append(textNode("p", "watch-rule-report-empty", "아직 이 주제와 일치하는 발언이 없습니다."));
    }
    summary.append(claimList);
    summary.append(textNode(
      "small", "watch-rule-report-summary-status",
      payload.summary_status === "GENERATING"
        ? "OpenRouter가 종합 판단과 핵심 논점을 작성하는 중 · 현재 확인된 주요 발언 표시"
        : payload.summary_status === "UPDATING"
          ? "새 발언을 반영해 브리핑을 갱신하는 중 · 이전 저장본 표시"
          : hasIntegrated
            ? payload.integrated_summary.provider + " 브리핑 저장본 · 같은 근거 재호출 없음"
            : "주요 발언 임시 추출 · 관련 발언 3개부터 브리핑 생성",
    ));

    const evidence = textNode("section", "watch-rule-report-evidence", "");
    evidence.append(reportEvidenceDetails(
      payload.matches || [], null, "전체 근거 원문 보기",
    ));
    body.append(summary, evidence);
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  async function refreshRuleReport(rule, attempt = 0) {
    if (!element("#watchRuleReportDialog")?.open || attempt >= 30) return;
    try {
      const payload = await watchFetch(
        "api/watch/rules/" + encodeURIComponent(rule.rule_id) + "/report",
      );
      renderRuleReport(payload);
      if (["GENERATING", "UPDATING"].includes(payload.summary_status)) {
        window.clearTimeout(state.reportTimer);
        state.reportTimer = window.setTimeout(() => refreshRuleReport(rule, attempt + 1), 2000);
      } else {
        element("#watchRuleMessage").textContent = payload.integrated_summary
          ? "주제별 보고서가 갱신되었습니다. 같은 근거는 다시 호출하지 않습니다."
          : "현재 근거 기준 핵심 문장을 표시했습니다.";
      }
    } catch (error) {
      element("#watchRuleMessage").textContent = error.message;
    }
  }

  async function openRuleReport(rule) {
    const message = element("#watchRuleMessage");
    message.textContent = "현재 시점 보고서를 불러오는 중입니다.";
    try {
      const payload = await watchFetch(
        "api/watch/rules/" + encodeURIComponent(rule.rule_id) + "/report",
      );
      renderRuleReport(payload);
      if (["GENERATING", "UPDATING"].includes(payload.summary_status)) {
        message.textContent = "OpenRouter가 현재 발언을 주제별로 구조화하는 중입니다.";
        window.clearTimeout(state.reportTimer);
        state.reportTimer = window.setTimeout(() => refreshRuleReport(rule), 2000);
      } else {
        message.textContent = payload.integrated_summary
          ? "저장된 주제별 보고서를 표시했습니다. 추가 호출은 없습니다."
          : "현재 근거 기준 핵심 문장을 표시했습니다.";
      }
    } catch (error) {
      message.textContent = error.message;
    }
  }

  function downloadRuleReport() {
    if (!state.currentRuleReport) return;
    const blob = new Blob([ruleReportMarkdown(state.currentRuleReport)], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    const safeName = String(state.currentRuleReport.rule_name || "알림-주제")
      .replace(/[^가-힣a-zA-Z0-9_-]+/g, "-");
    link.href = url;
    link.download = safeName + "-현재보고서.md";
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function printRuleReport() {
    if (!state.currentRuleReport) return;
    document.body.classList.add("watch-rule-report-print-mode");
    window.print();
    window.setTimeout(() => document.body.classList.remove("watch-rule-report-print-mode"), 500);
  }

  function editRule(rule) {
    state.editingRuleId = rule.rule_id;
    element("#watchRuleName").value = rule.name;
    element("#watchRuleTerms").value = rule.include_terms.join(", ");
    element("#watchRuleInstitution").value = rule.institution || "";
    element("#watchRulePolicy").value = rule.notification_policy;
    element("#watchRuleDigest").checked = Boolean(rule.digest_enabled);
    element("#watchRuleKakao").checked = Boolean(rule.kakao_enabled);
    element("#watchRuleSubmit").textContent = "수정 내용 저장";
    element("#watchRuleCancel").hidden = false;
    element("#watchRuleComposer").open = true;
    element("#watchRuleName").focus();
  }

  function cancelRuleEdit() {
    state.editingRuleId = "";
    element("#watchRuleForm").reset();
    element("#watchRuleSubmit").textContent = "알림 주제 저장";
    element("#watchRuleCancel").hidden = true;
    element("#watchRuleMessage").textContent = "";
    element("#watchRuleComposer").open = false;
  }

  async function submitRule(event) {
    event.preventDefault();
    const message = element("#watchRuleMessage");
    const terms = element("#watchRuleTerms").value.split(",").map((value) => value.trim()).filter(Boolean);
    message.textContent = "저장하는 중입니다.";
    try {
      const draft = {
        name: element("#watchRuleName").value.trim(),
        include_terms: terms,
        exclude_terms: [],
        institution: element("#watchRuleInstitution").value || null,
        notification_policy: element("#watchRulePolicy").value,
        digest_enabled: element("#watchRuleDigest").checked,
        kakao_enabled: element("#watchRuleKakao").checked,
      };
      const duplicate = state.rules.find((rule) => (
        String(rule.rule_id) !== String(state.editingRuleId || "")
        && ruleIdentity(rule) === ruleIdentity(draft)
      ));
      if (duplicate) throw new Error("이미 같은 알림 주제가 등록되어 있습니다.");
      const rulePath = state.editingRuleId
        ? `api/watch/rules/${encodeURIComponent(state.editingRuleId)}` : "api/watch/rules";
      const savedRule = await watchFetch(rulePath, {
        method: state.editingRuleId ? "PUT" : "POST",
        body: JSON.stringify(draft),
      });
      const wasEditing = Boolean(state.editingRuleId);
      state.rules = wasEditing
        ? state.rules.map((rule) => String(rule.rule_id) === String(savedRule.rule_id) ? savedRule : rule)
        : [savedRule, ...state.rules];
      saveLocalRules(state.rules);
      cancelRuleEdit();
      message.textContent = wasEditing
        ? "수정했습니다. 이후 자막부터 새 조건을 적용합니다."
        : "등록했습니다. 지금 이후 자막부터 감지합니다.";
      renderRules();
    } catch (error) {
      message.textContent = error.message;
    }
  }

  function renderNotifications(payload) {
    const previousUnread = state.unread;
    state.notifications = [...(payload.items || [])]
      .sort((left, right) => new Date(right.created_at) - new Date(left.created_at))
      .slice(0, NOTIFICATION_LIMIT);
    state.unread = Number(payload.unread_count || 0);
    const badge = element("#watchAlertBadge");
    const unreadLabel = `새 알림 ${Math.min(state.unread, 99)}`;
    badge.textContent = unreadLabel;
    badge.title = `읽지 않은 알림 ${state.unread}건`;
    badge.setAttribute("aria-label", badge.title);
    badge.hidden = state.unread < 1;
    trigger?.classList.toggle("has-alert", state.unread > 0);
    element("#watchUnreadLabel").textContent = `새 알림 ${state.unread} · 최근 ${state.notifications.length}건`;
    element("#watchClearRead").disabled = !state.notifications.some((item) => item.read_at);
    const container = element("#watchNotificationList");
    container.replaceChildren();
    if (!state.notifications.length) {
      container.append(textNode("p", "", "아직 도착한 알림이 없습니다."));
      return;
    }
    for (const notification of state.notifications) {
      const row = textNode("article", "watch-notification-row", "");
      const button = textNode("button", `watch-notification${notification.read_at ? "" : " is-unread"}`, "");
      button.type = "button";
      button.append(
        textNode("span", "", notification.is_test
          ? "TEST"
          : notification.notification_type === "DIGEST" ? "회의 종료" : notification.matched_term || "LIVE 감지"),
        textNode("strong", "", notification.title),
        textNode("small", "", `${notification.meeting_title} · ${formatTime(notification.created_at)}`),
      );
      button.addEventListener("click", () => openEvidence(notification));
      const remove = textNode("button", "watch-notification-remove", "×");
      remove.type = "button";
      remove.setAttribute("aria-label", `${notification.title} 감지 기록 삭제`);
      remove.addEventListener("click", () => deleteNotification(notification.notification_id));
      row.append(button, remove);
      container.append(row);
    }
    if (state.unread > previousUnread && previousUnread >= 0) {
      const message = element("#watchRuleMessage");
      if (state.testId && message) message.textContent = "테스트 방송에서 관심 문구를 감지했습니다. 알림함에서 근거를 확인하세요.";
    }
  }

  async function loadNotifications() {
    try {
      renderNotifications(await watchFetch(`api/watch/notifications?limit=${NOTIFICATION_LIMIT}`));
    } catch (_) {
      // 알림 폴링 실패는 LIVE 본문을 방해하지 않고 다음 주기에 재시도한다.
    }
  }

  async function loadMetrics() {
    try {
      const metrics = await watchFetch("api/watch/metrics");
      element("#watchMetrics").textContent = `설정 ${metrics.active_rules} · 근거 ${metrics.matches} · LLM ${metrics.llm_calls || 0}회 · $${Number(metrics.cost_usd || 0).toFixed(2)}`;
    } catch (_) {
      element("#watchMetrics").textContent = "로컬 저장 · LLM 0회";
    }
  }

  function renderKakaoStatus(payload) {
    state.kakao = payload;
    const action = element("#watchKakaoAction");
    const status = element("#watchKakaoStatus");
    const checkbox = element("#watchRuleKakao");
    const help = element("#watchRuleKakaoHelp");
    if (payload.connected) {
      const deliveredAt = payload.last_delivery_status === "SENT" && payload.last_delivered_at
        ? ` · 최근 접수 ${new Date(payload.last_delivered_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}`
        : payload.last_delivery_status === "FAILED" ? " · 최근 발송 실패" : "";
      status.textContent = `연결됨 · ‘카카오로도 받기’를 켠 주제만 전송${deliveredAt}`;
      action.textContent = "연결 해제";
      action.disabled = false;
      action.dataset.action = "disconnect";
      checkbox.disabled = false;
      help.textContent = "이 주제의 다음 감지부터 카카오 전송";
      return;
    }
    checkbox.checked = false;
    checkbox.disabled = true;
    if (!payload.configured) {
      status.textContent = "운영 설정 대기 · in-app은 정상 동작";
      action.textContent = "설정 대기";
      action.disabled = true;
      help.textContent = "운영 설정 완료 후 선택 가능";
      return;
    }
    status.textContent = payload.status === "REAUTHORIZE"
      ? "메시지 전송 재동의 필요"
      : "연결하지 않음 · 선택 동의 필요";
    action.textContent = payload.status === "REAUTHORIZE"
      ? "다시 연결"
      : "나에게 보내기 연결";
    action.disabled = false;
    action.dataset.action = "connect";
    help.textContent = "계정 연결 후 선택 가능";
  }

  async function loadKakaoStatus() {
    try {
      renderKakaoStatus(await watchFetch("api/watch/kakao/status"));
    } catch (_) {
      renderKakaoStatus({ configured: false, connected: false, status: "UNAVAILABLE" });
    }
  }

  async function kakaoAction() {
    const action = element("#watchKakaoAction");
    action.disabled = true;
    try {
      if (action.dataset.action === "disconnect") {
        const result = await watchFetch("api/watch/kakao", { method: "DELETE" });
        element("#watchRuleMessage").textContent = result.warning || "카카오 나에게 보내기 연결을 해제했습니다.";
        await loadKakaoStatus();
        return;
      }
      const result = await watchFetch("api/watch/kakao/authorize", { method: "POST" });
      window.location.assign(result.authorization_url);
    } catch (error) {
      element("#watchRuleMessage").textContent = error.message;
      await loadKakaoStatus();
    }
  }

  async function adminFetch(path, options = {}) {
    const token = element("#watchAdminToken").value || window.sessionStorage.getItem(ADMIN_SESSION_KEY) || "";
    if (!token) throw new Error("운영자 비밀번호를 입력해 주세요.");
    window.sessionStorage.setItem(ADMIN_SESSION_KEY, token);
    const headers = new Headers(options.headers || {});
    headers.set("X-Watch-Admin-Token", token);
    if (options.body) headers.set("Content-Type", "application/json");
    const response = await fetch(path, { ...options, headers, cache: "no-store" });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      if (response.status === 401) window.sessionStorage.removeItem(ADMIN_SESSION_KEY);
      throw new Error(payload.detail || "운영 요청을 처리할 수 없습니다.");
    }
    return response.json();
  }

  function renderAdminReviews(payload) {
    const list = element("#watchAdminList");
    list.replaceChildren();
    if (!payload.items?.length) {
      list.append(textNode("p", "watch-rule-empty", "현재 수동 검토가 필요한 공식 근거가 없습니다."));
      return;
    }
    for (const review of payload.items) {
      const card = textNode("article", "watch-admin-card", "");
      card.append(
        textNode("strong", "", review.meeting_title),
        textNode("small", "", `자동 판정 ${review.automatic_status} · ${review.verification_method}`),
        textNode("p", "", `LIVE: ${review.live_speaker || "화자 확인 중"} · ${review.live_excerpt}`),
        textNode("p", "", `공식: ${review.official_speaker || "화자 미확인"} · ${review.official_text || "연결 문장 없음"}`),
      );
      const note = document.createElement("input");
      note.maxLength = 500;
      note.placeholder = "판단 근거 또는 보정 메모";
      note.value = review.latest_note || "";
      const actions = textNode("div", "watch-admin-actions", "");
      for (const [decision, label] of [["APPROVE", "자동판정 승인"], ["CORRECT", "보정 필요"], ["DEFER", "보류"]]) {
        const button = textNode("button", "", label);
        button.type = "button";
        button.addEventListener("click", () => saveAdminReview(review.verification_id, decision, note.value));
        actions.append(button);
      }
      card.append(note, actions);
      list.append(card);
    }
  }

  async function loadAdminReviews() {
    const message = element("#watchAdminMessage");
    message.textContent = "공식 근거 수동 검토 목록을 불러오는 중입니다.";
    try {
      const payload = await adminFetch("api/watch/admin/reviews?limit=50");
      renderAdminReviews(payload);
      message.textContent = `검토 대기 ${payload.count}건 · 자동 판정 원본 보존`;
    } catch (error) {
      message.textContent = error.message;
    }
  }

  async function saveAdminReview(verificationId, decision, note) {
    try {
      await adminFetch(`api/watch/admin/reviews/${encodeURIComponent(verificationId)}`, {
        method: "POST",
        body: JSON.stringify({ decision, note, reviewed_by: "PoC 7 운영자" }),
      });
      await loadAdminReviews();
    } catch (error) {
      element("#watchAdminMessage").textContent = error.message;
    }
  }

  async function runAdminAudit() {
    const message = element("#watchAdminMessage");
    message.textContent = "최근 실방송의 cursor·final·재연결·공식전환을 점검하는 중입니다.";
    try {
      const payload = await adminFetch("api/watch/admin/live-regression/run?limit=20", { method: "POST" });
      const list = element("#watchAdminList");
      list.replaceChildren();
      for (const audit of payload.items || []) {
        const card = textNode("article", `watch-admin-card is-${String(audit.status).toLowerCase()}`, "");
        card.append(
          textNode("strong", "", audit.title),
          textNode("small", "", `${audit.status} · revision ${audit.revision_count} · final ${audit.final_count} · gap ${audit.reconnect_gap_count}`),
        );
        list.append(card);
      }
      message.textContent = `최근 ${payload.count}개 회의 점검을 기록했습니다.`;
    } catch (error) {
      message.textContent = error.message;
    }
  }

  async function deleteNotification(notificationId) {
    try {
      await watchFetch(`api/watch/notifications/${encodeURIComponent(notificationId)}`, { method: "DELETE" });
      await loadNotifications();
    } catch (error) {
      element("#watchRuleMessage").textContent = error.message;
    }
  }

  async function clearReadNotifications() {
    if (!state.notifications.some((item) => item.read_at)) return;
    if (!window.confirm("읽은 감지 기록을 정리할까요?")) return;
    try {
      await watchFetch("api/watch/notifications", { method: "DELETE" });
      element("#watchEvidence").hidden = true;
      await loadNotifications();
    } catch (error) {
      element("#watchRuleMessage").textContent = error.message;
    }
  }

  function appendHighlightedTerms(container, text, terms) {
    const source = String(text || "");
    const needles = [...new Set((terms || [])
      .map((value) => String(value || "").trim())
      .filter(Boolean))]
      .sort((left, right) => right.length - left.length);
    if (!needles.length) {
      container.textContent = source;
      return;
    }
    const folded = source.toLocaleLowerCase("ko-KR");
    let offset = 0;
    while (offset < source.length) {
      let nextIndex = -1;
      let nextNeedle = "";
      for (const needle of needles) {
        const index = folded.indexOf(needle.toLocaleLowerCase("ko-KR"), offset);
        if (index >= 0 && (nextIndex < 0 || index < nextIndex || (index === nextIndex && needle.length > nextNeedle.length))) {
          nextIndex = index;
          nextNeedle = needle;
        }
      }
      if (nextIndex < 0) {
        container.append(document.createTextNode(source.slice(offset)));
        break;
      }
      if (nextIndex > offset) container.append(document.createTextNode(source.slice(offset, nextIndex)));
      container.append(textNode("mark", "watch-keyword-highlight", source.slice(nextIndex, nextIndex + nextNeedle.length)));
      offset = nextIndex + nextNeedle.length;
    }
    if (!source.length) container.textContent = "";
  }

  function appendHighlightedText(container, text, term) {
    appendHighlightedTerms(container, text, [term]);
  }

  async function openEvidence(notification) {
    try {
      const payload = await watchFetch(`api/watch/sessions/${encodeURIComponent(notification.session_id)}`);
      trigger?.click();
      const broadcastId = String(payload.broadcast_id || notification.broadcast_id || "");
      if (broadcastId) {
        const escapedId = window.CSS?.escape ? window.CSS.escape(broadcastId) : broadcastId.replace(/["\\]/g, "\\$&");
        const liveRow = element(`#liveBroadcastRows .broadcast-row[data-broadcast-id="${escapedId}"]`);
        if (liveRow) liveRow.click();
      }
      if (notification.notification_id) {
        await watchFetch(`api/watch/notifications/${encodeURIComponent(notification.notification_id)}/read`, { method: "POST" });
      }
      const section = element("#watchEvidence");
      element("#watchEvidenceTitle").textContent = payload.rule_name;
      element("#watchEvidenceCount").textContent = `발언 묶음 ${payload.match_count}개 · 화자 ${payload.distinct_speaker_count}명`;
      const verification = payload.official_verification || {};
      const verificationLabel = {
        OFFICIAL_CONFIRMED: "공식 근거 확인",
        OFFICIAL_CORRECTED: "공식 문장 보정",
        OFFICIAL_NOT_CONFIRMED: "공식본에서 미확인",
        REVIEW_REQUIRED: "공식 후보 확인 필요",
        PENDING_OFFICIAL: "공식자료 대기",
      }[verification.status] || "공식자료 대기";
      element("#watchEvidenceCount").textContent += ` · ${verificationLabel}`;
      const summary = element("#watchCurrentSummary");
      summary.dataset.label = payload.integrated_summary
        ? "발언 흐름 · 추가 호출 없음"
        : "현재까지 요약 · LLM 미사용";
      summary.replaceChildren();
      summary.hidden = Boolean(payload.integrated_summary?.claims?.length);
      for (const item of summary.hidden ? [] : (payload.current_summary || [])) {
        const paragraph = document.createElement("p");
        paragraph.append(textNode("b", "", `${item.speaker_label} · `), document.createTextNode(item.summary));
        summary.append(paragraph);
      }
      const integrated = element("#watchIntegratedSummary");
      integrated.replaceChildren();
      if (payload.integrated_summary?.claims?.length) {
        integrated.append(textNode("strong", "", "현재까지 논의 통합 요약"));
        for (const claim of payload.integrated_summary.claims) {
          integrated.append(textNode("p", "", claim.text));
        }
        integrated.append(textNode("small", "", `${payload.integrated_summary.provider} 저장본 · 화면 조회 시 재호출 없음`));
        integrated.hidden = false;
      } else {
        integrated.hidden = true;
      }
      const speakerFlow = element("#watchSpeakerFlow");
      speakerFlow.replaceChildren();
      for (const flow of payload.speaker_flows || []) {
        speakerFlow.append(textNode("span", "", `${flow.speaker_label} ${flow.match_count}묶음`));
      }
      const list = element("#watchEvidenceList");
      list.replaceChildren();
      for (const match of payload.matches || []) {
        const item = textNode("article", "watch-evidence-item", "");
        item.append(textNode("strong", "", match.speaker_label || "화자 확인 중"));
        const body = document.createElement("p");
        appendHighlightedText(body, match.excerpt, match.matched_term);
        item.append(body);
        list.append(item);
      }
      section.hidden = false;
      section.scrollIntoView({ behavior: "smooth", block: "start" });
      await loadNotifications();
    } catch (error) {
      element("#watchRuleMessage").textContent = error.message;
    }
  }

  function renderTest(payload, options = {}) {
    state.testId = payload.test_id;
    const button = element("#watchTestStart");
    const message = element("#watchRuleMessage");
    if (payload.status === "COMPLETED") {
      button.textContent = "테스트 방송 다시 송출";
      button.disabled = !state.rules.some((rule) => rule.enabled);
      message.textContent = state.notifications.some((item) => item.is_test)
        ? "테스트 완료 · 실제 LIVE 화면과 알림 근거 누적을 확인했습니다."
        : "테스트 완료 · 알림함에서 감지 결과를 확인하세요.";
      window.clearTimeout(state.testTimer);
      state.testTimer = null;
      window.clearTimeout(state.testFinishTimer);
      state.testFinishTimer = window.setTimeout(() => {
        document.dispatchEvent(new CustomEvent("watch-test-live-update", { detail: { payload: null } }));
      }, 5000);
    } else {
      button.textContent = `테스트 방송 중 ${payload.current_step} / ${payload.total_steps}`;
      button.disabled = true;
      message.textContent = "실제 LIVE 화면에 가상 국무회의를 송출하고 있습니다.";
    }
    document.dispatchEvent(new CustomEvent("watch-test-live-update", {
      detail: { payload, focus: options.focus === true },
    }));
  }

  async function pollTest() {
    if (!state.testId) return;
    try {
      const payload = await watchFetch(`api/watch/test-broadcasts/${encodeURIComponent(state.testId)}`);
      renderTest(payload);
      await loadNotifications();
      if (payload.status !== "COMPLETED" && payload.status !== "FAILED") {
        state.testTimer = window.setTimeout(pollTest, 1500);
      }
    } catch (error) {
      element("#watchRuleMessage").textContent = error.message;
      state.testTimer = window.setTimeout(pollTest, 3000);
    }
  }

  async function startTest() {
    const button = element("#watchTestStart");
    button.disabled = true;
    button.textContent = "송출 준비 중";
    try {
      const payload = await watchFetch("api/watch/test-broadcasts", { method: "POST" });
      state.testId = payload.test_id;
      renderTest({ ...payload, transcript: { broadcasts: [], segments: [], utterances: [] } }, { focus: true });
      window.clearTimeout(state.testTimer);
      state.testTimer = window.setTimeout(pollTest, 500);
    } catch (error) {
      element("#watchRuleMessage").textContent = error.message;
      button.disabled = !state.rules.some((rule) => rule.enabled);
      button.textContent = "테스트 방송 송출";
    }
  }

  async function restoreLatestTest() {
    try {
      const payload = await watchFetch("api/watch/test-broadcasts/latest");
      if (payload.item?.status === "LIVE") {
        state.testId = payload.item.test_id;
        pollTest();
      }
    } catch (_) {
      // 최초 방문 시 알림 UI만 준비하고 본문 로딩은 계속한다.
    }
  }

  if (!embedded) trigger?.addEventListener("click", openPanel);
  element("#watchAlertClose")?.addEventListener("click", closePanel);
  shade?.addEventListener("click", closePanel);
  element("#watchRuleForm")?.addEventListener("submit", submitRule);
  element("#watchRuleCancel")?.addEventListener("click", cancelRuleEdit);
  element("#watchClearRead")?.addEventListener("click", clearReadNotifications);
  element("#watchTestStart")?.addEventListener("click", startTest);
  element("#watchKakaoAction")?.addEventListener("click", kakaoAction);
  element("#watchRuleReportClose")?.addEventListener("click", () => element("#watchRuleReportDialog")?.close());
  element("#watchRuleReportDownload")?.addEventListener("click", downloadRuleReport);
  element("#watchRuleReportPrint")?.addEventListener("click", printRuleReport);
  element("#watchAdminLoad")?.addEventListener("click", loadAdminReviews);
  element("#watchAdminAudit")?.addEventListener("click", runAdminAudit);
  if (!embedded) window.addEventListener("keydown", (event) => { if (event.key === "Escape" && !panel.hidden) closePanel(); });

  ensureToken()
    .then(async () => {
      await Promise.all([loadKakaoStatus(), loadRules(), loadNotifications(), loadMetrics(), restoreLatestTest()]);
      const params = new URLSearchParams(window.location.search);
      const kakaoResult = params.get("watch_kakao");
      if (kakaoResult) {
        element("#watchRuleMessage").textContent = {
          connected: "카카오 나에게 보내기 연결이 완료되었습니다.",
          denied: "카카오 연결 동의가 취소되었습니다.",
          consent_required: "[선택] 카카오 메시지 전송에 동의해야 나와의 채팅으로 받을 수 있습니다.",
          failed: "카카오 연결을 완료하지 못했습니다. 다시 시도해 주세요.",
        }[kakaoResult] || "";
        params.delete("watch_kakao");
        window.history.replaceState({}, "", `${window.location.pathname}${params.size ? `?${params}` : ""}${window.location.hash}`);
      }
      const sessionId = params.get("watch_session");
      if (sessionId) openEvidence({ session_id: sessionId });
    })
    .catch(() => { if (trigger) trigger.title = "알림 연결을 확인할 수 없습니다."; });
  state.notificationTimer = window.setInterval(loadNotifications, 5000);
  window.setInterval(loadMetrics, 30000);
})();
