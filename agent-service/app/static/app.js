const conversation = document.querySelector("#conversation");
const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-button");
const fillDemoButton = document.querySelector("#fill-demo-button");
const loginHint = document.querySelector("#login-hint");
const authGuest = document.querySelector("#auth-guest");
const authExpandButton = document.querySelector("#auth-expand-button");
const authChecking = document.querySelector("#auth-checking");
const signedIn = document.querySelector("#signed-in");
const signedInName = document.querySelector("#signed-in-name");
const logoutButton = document.querySelector("#logout-button");
const pendingAction = document.querySelector("#pending-action");
const pendingActionCopy = document.querySelector("#pending-action-copy");
const pendingActionContinue = document.querySelector("#pending-action-continue");
const pendingActionCancel = document.querySelector("#pending-action-cancel");
const agentStatus = document.querySelector("#agent-status");
const modelStatus = document.querySelector("#model-status");
const topbarStatus = document.querySelector("#topbar-status");
const appShell = document.querySelector("#app-shell");
const sidebarOpen = document.querySelector("#sidebar-open");
const sidebarClose = document.querySelector("#sidebar-close");
const shellBackdrop = document.querySelector("#shell-backdrop");
const newChatButton = document.querySelector("#new-chat-button");
const inspectorPanel = document.querySelector("#inspector-panel");
const inspectorClose = document.querySelector("#inspector-close");
const inspectorEmpty = document.querySelector("#inspector-empty");
const inspectorRun = document.querySelector("#inspector-run");
const inspectorRunTitle = document.querySelector("#inspector-run-title");
const inspectorRunState = document.querySelector("#inspector-run-state");
const inspectorQuery = document.querySelector("#inspector-query");
const inspectorMetrics = document.querySelector("#inspector-metrics");
const inspectorTimeline = document.querySelector("#inspector-timeline");
const inspectorSseDot = document.querySelector("#inspector-sse-dot");
const inspectorSseStatus = document.querySelector("#inspector-sse-status");
const inspectorModel = document.querySelector("#inspector-model");
const inspectorSession = document.querySelector("#inspector-session");
const viewButtons = document.querySelectorAll("[data-view-mode]");
const welcomeState = document.querySelector("#welcome-state");
const welcomeAuthNote = document.querySelector("#welcome-auth-note");
const welcomeAuthCopy = document.querySelector("#welcome-auth-copy");
const appAnnouncer = document.querySelector("#app-announcer");
const workspace = document.querySelector("#workspace");

const removedCredentialQuery = removeCredentialQueryParameters();
const storedAccessToken = sessionStorage.getItem("ordermate_token");
const state = {
  sessionId: sessionStorage.getItem("ordermate_session") || crypto.randomUUID(),
  accessToken: storedAccessToken,
  username: sessionStorage.getItem("ordermate_username"),
  authStatus: storedAccessToken ? "checking" : "anonymous",
  loginExpanded: removedCredentialQuery,
  pendingPrompt: null,
  pendingLabel: null,
  sending: false,
  confirming: 0,
  inspector: null,
  activeRequest: null,
};

sessionStorage.setItem("ordermate_session", state.sessionId);
syncInspectorSession();
syncAuthUi();
void restoreAuthSession();
checkHealth();
resizeComposer();

if (removedCredentialQuery && !storedAccessToken) {
  loginHint.textContent = "为保护账号安全，地址栏中的登录信息已被移除，请在此处重新登录。";
  loginHint.classList.add("error");
}

viewButtons.forEach((button) => {
  button.addEventListener("click", () => setViewMode(button.dataset.viewMode));
  button.addEventListener("keydown", handleViewSwitchKeydown);
});

sidebarOpen.addEventListener("click", () => setSidebarOpen(true));
sidebarClose.addEventListener("click", () => setSidebarOpen(false, true));
shellBackdrop.addEventListener("click", () => closeOverlayPanels(false));
inspectorClose.addEventListener("click", () => {
  setViewMode("customer");
  viewButtons[1]?.focus();
});
newChatButton.addEventListener("click", async () => {
  setSidebarOpen(false);
  await startNewConversation();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeOverlayPanels(true);
});

document.addEventListener("click", (event) => {
  const promptButton = event.target.closest("[data-prompt]");
  if (!promptButton) return;
  if (promptButton.dataset.authRequired === "true" && state.authStatus !== "authenticated") {
    requestLoginForAction(promptButton.dataset.prompt, promptButton.dataset.authLabel);
    return;
  }
  messageInput.value = promptButton.dataset.prompt;
  resizeComposer();
  messageInput.focus();
});

pendingActionContinue.addEventListener("click", () => {
  if (!state.pendingPrompt || state.authStatus !== "authenticated") return;
  const prompt = state.pendingPrompt;
  clearPendingAction();
  setSidebarOpen(false);
  messageInput.value = prompt;
  resizeComposer();
  chatForm.requestSubmit();
});

pendingActionCancel.addEventListener("click", () => {
  clearPendingAction();
  loginHint.textContent = "已取消继续操作，你仍然保持登录状态。";
  announce("已取消刚才保留的操作。")
});

chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message || state.sending) return;

  addUserMessage(message);
  messageInput.value = "";
  resizeComposer();
  setSending(true);
  const pendingMessage = addPendingMessage();
  beginInspectorRun(message);
  const request = { id: crypto.randomUUID(), controller: new AbortController() };
  state.activeRequest = request;

  try {
    const response = await fetchChatStream(
      {
        message,
        session_id: state.sessionId,
        access_token: state.accessToken,
      },
      (event) => {
        if (state.activeRequest?.id !== request.id) return;
        updateStreamingStatus(pendingMessage, event);
        recordInspectorEvent(event);
      },
      request.controller.signal,
    );
    if (state.activeRequest?.id !== request.id) return;
    fillAssistantMessage(pendingMessage, response);
    completeInspectorRun(response, "success");
    announce("回复已生成，可以继续提问。");
  } catch (error) {
    if (error.name === "AbortError" || state.activeRequest?.id !== request.id) return;
    fillAssistantMessage(pendingMessage, {
      answer: error.message,
      tool_calls: [],
      isError: true,
    });
    completeInspectorRun({ detail: error.message }, "error");
    announce("请求未完成，请检查提示后重试。");
  } finally {
    if (state.activeRequest?.id === request.id) {
      state.activeRequest = null;
      setSending(false);
      messageInput.focus();
    }
  }
});

messageInput.addEventListener("input", resizeComposer);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginHint.classList.remove("error");

  const form = new FormData(loginForm);
  const username = String(form.get("username") || "").trim();
  const password = String(form.get("password") || "");
  setAuthStatus("authenticating");

  try {
    const response = await fetchJson("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    cancelActiveRequest();
    void rotateSessionContext(state.accessToken);
    state.accessToken = response.access_token;
    state.username = username;
    sessionStorage.setItem("ordermate_token", state.accessToken);
    sessionStorage.setItem("ordermate_username", username);
    loginForm.reset();
    loginHint.textContent = "登录成功，购物车和订单工具已经解锁。";
    setAuthStatus("authenticated");
    addSystemMessage(`已切换到「${username}」的个人会话上下文，订单和购物车工具已解锁。`);
  } catch (error) {
    loginHint.textContent = error.message;
    loginHint.classList.add("error");
    setAuthStatus("anonymous");
  }
});

fillDemoButton.addEventListener("click", () => {
  loginForm.elements.username.value = "testuser";
  loginForm.elements.password.value = "password";
  loginForm.elements.username.focus();
  loginHint.textContent = "演示账号已填入，点击上方按钮登录。";
  loginHint.classList.remove("error");
});

authExpandButton.addEventListener("click", () => {
  state.loginExpanded = true;
  syncAuthUi();
  loginForm.elements.username.focus();
  announce("登录表单已展开。");
});

logoutButton.addEventListener("click", () => {
  if (state.confirming > 0) return;
  const previousAccessToken = state.accessToken;
  cancelActiveRequest();
  clearAuth();
  state.loginExpanded = false;
  syncAuthUi();
  void rotateSessionContext(previousAccessToken);
  loginHint.textContent = "已退出。商品搜索仍可匿名使用。";
  addSystemMessage("已退出登录，切换到匿名会话。历史上下文已清除，商品搜索仍可匿名使用。");
});

document.documentElement.dataset.appReady = "true";

async function startNewConversation() {
  if (state.confirming > 0) return;
  cancelActiveRequest();
  conversation.querySelectorAll(".message").forEach((message) => message.remove());
  showWelcome();
  const serverCleared = await rotateSessionContext(state.accessToken);
  announce("当前对话已清空，已开始新会话。");
  addSystemMessage(
    serverCleared
      ? "会话已清空，历史上下文已重置。"
      : "本地会话已重置；服务端历史清理状态暂时无法确认。",
  );
}

function setViewMode(mode) {
  const nextMode = mode === "developer" ? "developer" : "customer";
  if (nextMode === "developer") setSidebarOpen(false);
  appShell.dataset.view = nextMode;
  viewButtons.forEach((button) => {
    const active = button.dataset.viewMode === nextMode;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  inspectorPanel.setAttribute("aria-hidden", String(nextMode !== "developer"));
  announce(nextMode === "developer" ? "已打开调试视图。" : "已切换到对话视图。");
}

function setSidebarOpen(open, restoreFocus = false) {
  if (open) setViewMode("customer");
  appShell.classList.toggle("sidebar-open", open);
  sidebarOpen.setAttribute("aria-expanded", String(open));
  if (open) {
    requestAnimationFrame(() => sidebarClose.focus());
    announce("功能栏已打开。");
  } else if (restoreFocus) {
    sidebarOpen.focus();
  }
}

function closeOverlayPanels(restoreFocus = false) {
  const sidebarWasOpen = appShell.classList.contains("sidebar-open");
  setSidebarOpen(false, restoreFocus && sidebarWasOpen);
  if (window.matchMedia("(max-width: 1100px)").matches) {
    const inspectorWasOpen = appShell.dataset.view === "developer";
    setViewMode("customer");
    if (restoreFocus && inspectorWasOpen) viewButtons[1]?.focus();
  }
}

function handleViewSwitchKeydown(event) {
  const keys = ["ArrowLeft", "ArrowRight", "Home", "End"];
  if (!keys.includes(event.key)) return;
  event.preventDefault();
  const current = [...viewButtons].indexOf(event.currentTarget);
  const targetIndex = event.key === "Home"
    ? 0
    : event.key === "End"
      ? viewButtons.length - 1
      : (current + (event.key === "ArrowRight" ? 1 : -1) + viewButtons.length) % viewButtons.length;
  const target = viewButtons[targetIndex];
  target.focus();
  setViewMode(target.dataset.viewMode);
}

function announce(message) {
  appAnnouncer.textContent = "";
  requestAnimationFrame(() => { appAnnouncer.textContent = message; });
}

function requestLoginForAction(prompt, label = "这项个人功能") {
  state.pendingPrompt = prompt;
  state.pendingLabel = label;
  state.loginExpanded = true;
  setSidebarOpen(true);
  syncAuthUi();
  loginHint.textContent = `登录后可${label}，登录成功后可选择是否继续。`;
  loginHint.classList.remove("error");
  requestAnimationFrame(() => loginForm.elements.username.focus());
  announce(`${label}需要登录，登录表单已展开。`);
}

function clearPendingAction() {
  state.pendingPrompt = null;
  state.pendingLabel = null;
  syncPendingActionUi();
}

function syncPendingActionUi() {
  const visible = state.authStatus === "authenticated" && Boolean(state.pendingPrompt);
  pendingAction.classList.toggle("hidden", !visible);
  if (visible) pendingActionCopy.textContent = `是否继续“${state.pendingLabel || "刚才的操作"}”？`;
}

function configureAuthRequiredButton(button, label) {
  button.dataset.authRequired = "true";
  button.dataset.authLabel = label;
  const locked = state.authStatus !== "authenticated";
  button.dataset.locked = String(locked);
  button.setAttribute("aria-disabled", String(locked));
  button.title = locked ? `登录后可${label}` : "";
}

async function checkHealth() {
  try {
    const health = await fetchJson("/health");
    agentStatus.classList.add("online");
    agentStatus.querySelector("span").textContent = "在线";
    topbarStatus.classList.add("online");
    topbarStatus.querySelector("span").textContent = "在线";
    modelStatus.textContent =
      health.agent_mode === "demo"
        ? "本地演示"
        : health.model_configured
          ? "真实模型"
          : "待配置";
    inspectorModel.textContent = modelStatus.textContent;
  } catch {
    agentStatus.classList.add("offline");
    agentStatus.querySelector("span").textContent = "离线";
    topbarStatus.classList.add("offline");
    topbarStatus.querySelector("span").textContent = "离线";
    modelStatus.textContent = "不可用";
    inspectorModel.textContent = "不可用";
  }
}

function syncAuthUi() {
  const loggedIn = state.authStatus === "authenticated" && Boolean(state.accessToken);
  const checking = state.authStatus === "checking";
  const authenticating = state.authStatus === "authenticating";
  const showLoginForm = !checking && !loggedIn && state.loginExpanded;
  loginForm.classList.toggle("hidden", !showLoginForm);
  authGuest.classList.toggle("hidden", checking || loggedIn || state.loginExpanded);
  authExpandButton.setAttribute("aria-expanded", String(state.loginExpanded));
  authChecking.classList.toggle("hidden", !checking);
  signedIn.classList.toggle("hidden", !loggedIn);
  loginForm.setAttribute("aria-busy", String(authenticating));
  loginForm.querySelectorAll("input, button").forEach((control) => {
    control.disabled = authenticating;
  });
  loginButton.textContent = authenticating ? "正在登录…" : "登录";
  loginButton.classList.toggle("is-loading", authenticating);
  loginForm.closest(".login-panel").dataset.authState = state.authStatus;
  if (loggedIn) signedInName.textContent = state.username || "已登录";
  welcomeAuthNote.classList.toggle("authenticated", loggedIn);
  welcomeAuthCopy.textContent = loggedIn
    ? "演示账号已登录，商品、购物车和订单功能均可使用。"
    : "商品搜索可以直接使用；购物车和订单功能需要先登录演示账号。";
  document.querySelectorAll('[data-auth-required="true"]').forEach((button) => {
    const locked = !loggedIn;
    button.dataset.locked = String(locked);
    button.setAttribute("aria-disabled", String(locked));
    button.title = locked ? `登录后可${button.dataset.authLabel || "使用这项功能"}` : "";
  });
  syncPendingActionUi();
}

function setAuthStatus(status) {
  state.authStatus = status;
  syncAuthUi();
}

async function restoreAuthSession() {
  if (!state.accessToken) {
    setAuthStatus("anonymous");
    return;
  }
  setAuthStatus("checking");
  try {
    const response = await fetchJson("/auth/session", {
      method: "POST",
      body: JSON.stringify({ access_token: state.accessToken }),
      handleAuthFailure: false,
    });
    state.username = response.username || state.username || "已登录";
    sessionStorage.setItem("ordermate_username", state.username);
    setAuthStatus("authenticated");
  } catch {
    clearAuth();
    loginHint.textContent = "登录已失效，请重新登录。";
    loginHint.classList.add("error");
  }
}

function removeCredentialQueryParameters() {
  const url = new URL(window.location.href);
  const sensitiveNames = ["username", "password", "access_token", "token"];
  const removed = sensitiveNames.some((name) => url.searchParams.has(name));
  if (!removed) return false;
  sensitiveNames.forEach((name) => url.searchParams.delete(name));
  const query = url.searchParams.toString();
  window.history.replaceState(null, "", `${url.pathname}${query ? `?${query}` : ""}${url.hash}`);
  return true;
}

function addUserMessage(text) {
  hideWelcome();
  const fragment = document
    .querySelector("#user-message-template")
    .content.cloneNode(true);
  fragment.querySelector(".message-bubble p").textContent = text;
  conversation.append(fragment);
  scrollToLatest(true);
}

function addSystemMessage(text) {
  const fragment = document
    .querySelector("#system-message-template")
    .content.cloneNode(true);
  fragment.querySelector("p").textContent = text;
  conversation.append(fragment);
  scrollToLatest();
}

function addPendingMessage() {
  const fragment = document
    .querySelector("#assistant-message-template")
    .content.cloneNode(true);
  const article = fragment.querySelector(".message");
  article.classList.add("streaming-message");
  article.querySelector(".message-bubble p").textContent = "正在理解你的需求";
  setMessageStatus(article, "正在连接服务", "loading");
  conversation.append(fragment);
  scrollToLatest(true);
  return article;
}

function fillAssistantMessage(article, response) {
  article.classList.remove("streaming-message");
  setMessageStatus(article, "", "idle");
  article.querySelector(".message-bubble p").textContent =
    response.answer || "暂时没有回复。";

  if (response.isError) {
    article.classList.add("error-message");
    setMessageStatus(article, "请求未完成，请检查服务后重试", "error");
  } else if (!state.accessToken && /登录|认证|未授权/.test(response.answer || "")) {
    article.classList.add("auth-message");
    setMessageStatus(article, "登录演示账号后可继续", "auth");
  }

  if (response.reference) {
    const refBar = article.querySelector(".reference-bar");
    if (refBar) {
      refBar.classList.remove("hidden");
      const typeLabel =
        response.reference.type === "order" ? "订单" : "商品";
      refBar.textContent = `已确认你指的是${typeLabel} #${response.reference.value}`;
    }
  }

  renderResultData(article, response.data, response.tool_calls);

  if (response.confirmation) {
    renderConfirmation(article, response.confirmation);
  }
  scrollToLatest();
}

function updateStreamingStatus(article, event) {
  const copy = streamingCopy(event);
  if (copy) {
    article.querySelector(".message-bubble p").textContent = copy.message;
    setMessageStatus(article, copy.status, copy.tone);
  }
  if (event.type === "reference") {
    article.querySelector(".message-bubble p").textContent =
      `已找到相关${event.data.type === "order" ? "订单" : "商品"}，正在核对信息`;
    setMessageStatus(article, "上下文已确认", "success");
  }
}

function streamingCopy(event) {
  if (event.type === "started") {
    return { message: "正在理解你的需求", status: "分析问题", tone: "loading" };
  }
  if (event.type === "progress") {
    return { message: "正在为你处理，请稍候", status: "处理中", tone: "loading" };
  }
  if (event.type === "clarification") {
    return {
      message: event.data.message || "还需要你补充一些信息",
      status: "等待补充",
      tone: "warning",
    };
  }
  if (event.type === "tool_error") {
    return {
      message: "处理这一步时遇到问题，正在整理结果",
      status: "部分步骤未完成",
      tone: "error",
    };
  }
  if (event.type === "tool") {
    return toolStatusCopy(event.data.name, event.data.outcome);
  }
  if (event.type === "confirmation_required") {
    return {
      message: "这项操作需要你确认后才能继续",
      status: "等待你的确认",
      tone: "warning",
    };
  }
  return null;
}

function toolStatusCopy(name, outcome) {
  const labels = {
    search_knowledge_base: "已查询相关规则",
    search_products: "已完成商品筛选",
    get_product_detail: "已核对商品信息",
    get_cart: "已读取购物车",
    add_to_cart: "已更新购物车",
    update_cart: "已准备购物车变更",
    remove_from_cart: "已准备移除商品",
    clear_cart: "已准备清空购物车",
    get_my_orders: "已查询你的订单",
    get_order_detail: "已核对订单信息",
    cancel_order: "已准备取消申请",
    create_order: "已准备创建订单",
    pay_order: "已准备支付确认",
  };
  const failed = outcome === "error";
  return {
    message: failed ? "处理请求时遇到问题，正在生成说明" : labels[name] || "已完成信息处理",
    status: failed ? "处理未完成" : "信息已更新",
    tone: failed ? "error" : "success",
  };
}

function setMessageStatus(article, text, tone) {
  const label = article.querySelector(".message-status-label");
  if (!label) return;
  label.textContent = text;
  label.dataset.tone = tone;
  label.classList.toggle("hidden", !text);
}

function hideWelcome() {
  welcomeState.classList.add("hidden");
}

function showWelcome() {
  welcomeState.classList.remove("hidden");
}

function syncInspectorSession() {
  inspectorSession.textContent = state.sessionId.slice(0, 8);
}

async function rotateSessionContext(accessTokenForClear = null) {
  const previousSessionId = state.sessionId;
  state.sessionId = crypto.randomUUID();
  sessionStorage.setItem("ordermate_session", state.sessionId);
  resetInspector();
  try {
    const response = await fetch("/conversation/clear", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: previousSessionId,
        access_token: accessTokenForClear,
      }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return true;
  } catch (error) {
    console.warn("服务端会话记忆清理失败：", error);
    return false;
  }
}

function resetInspector() {
  state.inspector = null;
  syncInspectorSession();
  inspectorEmpty.classList.remove("hidden");
  inspectorRun.classList.add("hidden");
  inspectorTimeline.replaceChildren();
  setInspectorConnection("idle");
}

function beginInspectorRun(message) {
  state.inspector = { startedAt: performance.now(), events: [], tools: 0 };
  syncInspectorSession();
  inspectorEmpty.classList.add("hidden");
  inspectorRun.classList.remove("hidden");
  inspectorRunTitle.textContent = "Agent 正在执行";
  inspectorRunState.textContent = "运行中";
  inspectorRunState.dataset.tone = "running";
  inspectorQuery.textContent = message;
  inspectorTimeline.replaceChildren();
  renderInspectorMetrics(0, 0);
  setInspectorConnection("streaming");
}

function recordInspectorEvent(event) {
  const run = state.inspector;
  if (!run) return;
  const elapsed = Math.max(0, Math.round(performance.now() - run.startedAt));
  run.events.push({ ...event, elapsed });
  if (event.type === "tool") run.tools += 1;
  inspectorTimeline.append(createInspectorEvent(event, elapsed));
  renderInspectorMetrics(elapsed, run.tools);
  inspectorTimeline.parentElement.scrollTop = inspectorTimeline.parentElement.scrollHeight;
}

function completeInspectorRun(response, outcome) {
  const run = state.inspector;
  if (!run) return;
  const elapsed = Math.max(0, Math.round(performance.now() - run.startedAt));
  inspectorRunTitle.textContent = outcome === "success" ? "本轮执行完成" : "本轮执行中断";
  inspectorRunState.textContent = outcome === "success" ? "成功" : "失败";
  inspectorRunState.dataset.tone = outcome;
  renderInspectorMetrics(elapsed, run.tools);
  setInspectorConnection(outcome === "success" ? "complete" : "error");
  if (!run.events.some((item) => item.type === (outcome === "success" ? "result" : "error"))) {
    inspectorTimeline.append(createInspectorEvent({ type: outcome === "success" ? "result" : "error", data: response }, elapsed));
  }
}

function renderInspectorMetrics(elapsed, toolCount) {
  inspectorMetrics.replaceChildren(
    createInspectorMetric("观测时长", formatObservedTime(elapsed)),
    createInspectorMetric("工具调用", String(toolCount)),
    createInspectorMetric("事件数量", String(state.inspector?.events.length || 0)),
  );
}

function createInspectorMetric(label, value) {
  const item = document.createElement("span");
  const strong = document.createElement("strong");
  strong.textContent = value;
  item.append(strong, document.createTextNode(label));
  return item;
}

function createInspectorEvent(event, elapsed) {
  const labels = inspectorEventPresentation(event);
  const item = document.createElement("li");
  item.className = `inspector-event tone-${labels.tone}`;
  const marker = document.createElement("span");
  marker.className = "inspector-event-marker";
  const content = document.createElement("div");
  content.className = "inspector-event-content";
  const head = document.createElement("div");
  head.className = "inspector-event-head";
  const title = document.createElement("strong");
  title.textContent = labels.title;
  const time = document.createElement("time");
  time.textContent = `+${formatObservedTime(elapsed)}`;
  head.append(title, time);
  const summary = document.createElement("p");
  summary.textContent = labels.summary;
  content.append(head, summary);
  if (event.type === "tool" && event.data?.name) {
    const tool = document.createElement("code");
    tool.className = "inspector-tool-name";
    tool.textContent = event.data.name;
    content.append(tool);
  }
  if (event.data && typeof event.data === "object") {
    const details = document.createElement("details");
    const detailSummary = document.createElement("summary");
    detailSummary.textContent = "查看脱敏原始事件";
    const raw = document.createElement("pre");
    raw.textContent = JSON.stringify(redactSensitive(event.data), null, 2);
    details.append(detailSummary, raw);
    content.append(details);
  }
  item.append(marker, content);
  return item;
}

function inspectorEventPresentation(event) {
  const data = event.data || {};
  if (event.type === "started") return { title: "开始分析", summary: "已建立流式连接并接收任务。", tone: "running" };
  if (event.type === "progress") return { title: "执行计划", summary: data.message || "Agent 正在推进当前任务。", tone: "running" };
  if (event.type === "reference") return { title: "解析业务引用", summary: `已定位${data.type === "order" ? "订单" : "商品"}引用。`, tone: "success" };
  if (event.type === "clarification") return { title: "等待补充信息", summary: data.message || "需要用户补充信息。", tone: "warning" };
  if (event.type === "confirmation_required") return { title: "等待风险确认", summary: "高风险操作已暂停，等待用户确认。", tone: "warning" };
  if (event.type === "tool") {
    const ok = data.outcome !== "error";
    return { title: toolBusinessLabel(data.name), summary: `${formatOutcome(data.outcome)}${data.result_message ? ` · ${data.result_message}` : ""}`, tone: ok ? "success" : "error" };
  }
  if (event.type === "tool_error") return { title: "工具执行异常", summary: data.message || data.detail || "工具未能完成。", tone: "error" };
  if (event.type === "result") return { title: "生成最终结果", summary: "业务结果已返回到对话区。", tone: "success" };
  if (event.type === "error") return { title: "执行中断", summary: data.detail || "流式请求异常结束。", tone: "error" };
  return { title: `事件 · ${event.type}`, summary: "已收到执行事件。", tone: "neutral" };
}

function toolBusinessLabel(name) {
  const labels = {
    search_knowledge_base: "查询业务规则", search_products: "筛选商品", get_product_detail: "读取商品详情",
    get_cart: "读取购物车", add_to_cart: "添加购物车商品", update_cart: "更新购物车",
    update_cart_items: "批量更新购物车", remove_from_cart: "移除购物车商品", clear_cart: "清空购物车",
    get_my_orders: "查询订单", get_order_detail: "读取订单详情", cancel_order: "取消订单",
    create_order: "创建订单", pay_order: "支付订单",
  };
  return labels[name] || "调用业务工具";
}

function redactSensitive(value, key = "") {
  const sensitive = /pass(word)?|token|secret|authorization|cookie|api[-_]?key|access[-_]?token/i;
  if (sensitive.test(key)) return "[已脱敏]";
  if (Array.isArray(value)) return value.map((item) => redactSensitive(item));
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([childKey, child]) => [childKey, redactSensitive(child, childKey)]));
  }
  return value;
}

function formatObservedTime(milliseconds) {
  return milliseconds < 1000 ? `${milliseconds} ms` : `${(milliseconds / 1000).toFixed(1)} s`;
}

function setInspectorConnection(status) {
  const copy = { idle: "SSE 空闲", streaming: "SSE 接收中", complete: "SSE 已完成", error: "SSE 异常" };
  inspectorSseStatus.textContent = copy[status] || copy.idle;
  inspectorSseDot.dataset.status = status;
}

async function fetchChatStream(payload, onEvent, signal) {
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `请求失败（HTTP ${response.status}）`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result = null;
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";
    if (done && buffer.trim()) {
      frames.push(buffer);
      buffer = "";
    }
    for (const frame of frames) {
      const lines = frame.split(/\r?\n/);
      const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const data = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!event || !data) continue;
      let parsed;
      try {
        parsed = JSON.parse(data);
      } catch {
        throw new Error(`收到无法解析的流式事件（${event}）。`);
      }
      onEvent({ type: event, data: parsed });
      if (event === "result") result = parsed;
      if (event === "error") throw new Error(parsed.detail || "Agent 执行失败");
    }
    if (done) break;
  }
  if (!result) throw new Error("流式响应意外结束。");
  return result;
}

function renderConfirmation(article, confirmation) {
  const card = article.querySelector(".confirmation-card");
  const presentation = confirmationPresentation(confirmation);
  const titleId = `confirmation-${crypto.randomUUID()}`;
  card.classList.remove("hidden");
  card.dataset.action = confirmation.action || "unknown";
  card.setAttribute("role", "alertdialog");
  card.setAttribute("aria-modal", "false");
  card.setAttribute("aria-labelledby", titleId);

  const header = document.createElement("div");
  header.className = "confirmation-header";
  const icon = document.createElement("span");
  icon.className = `confirmation-icon tone-${presentation.tone}`;
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = presentation.icon;
  const heading = document.createElement("div");
  const eyebrow = document.createElement("span");
  eyebrow.className = "confirmation-eyebrow";
  eyebrow.textContent = "写操作确认";
  const title = document.createElement("strong");
  title.id = titleId;
  title.textContent = presentation.title;
  heading.append(eyebrow, title);
  const badge = document.createElement("span");
  badge.className = `confirmation-risk risk-${presentation.tone}`;
  badge.textContent = presentation.badge;
  header.append(icon, heading, badge);

  const description = document.createElement("p");
  description.className = "confirmation-description";
  description.textContent = confirmation.description;

  const facts = createConfirmationFacts(confirmation.action, confirmation.arguments || {});
  const impact = document.createElement("div");
  impact.className = `confirmation-impact tone-${presentation.tone}`;
  const impactLabel = document.createElement("strong");
  impactLabel.textContent = "执行影响";
  const impactCopy = document.createElement("p");
  impactCopy.textContent = presentation.impact;
  impact.append(impactLabel, impactCopy);

  const safety = document.createElement("p");
  safety.className = "confirmation-safety";
  safety.textContent = "只有点击确认后，服务端才会执行这项操作。";

  const actions = document.createElement("div");
  actions.className = "confirmation-actions";
  const approve = document.createElement("button");
  approve.className = `confirm-button tone-${presentation.tone}`;
  approve.type = "button";
  approve.dataset.buttonLevel = presentation.tone === "danger" ? "danger" : "primary";
  approve.textContent = presentation.confirmLabel;
  const reject = document.createElement("button");
  reject.className = "reject-button";
  reject.type = "button";
  reject.dataset.buttonLevel = "secondary";
  reject.textContent = "返回，不执行";
  actions.append(reject, approve);

  const status = document.createElement("div");
  status.className = "confirmation-submit-status hidden";
  status.setAttribute("aria-live", "polite");
  card.replaceChildren(header, description, facts, impact, safety, actions, status);

  approve.addEventListener("click", () =>
    submitConfirmation(card, confirmation, true, presentation),
  );
  reject.addEventListener("click", () =>
    submitConfirmation(card, confirmation, false, presentation),
  );
}

async function submitConfirmation(card, confirmation, approved, presentation) {
  if (card.classList.contains("is-submitting") || state.confirming > 0) return;
  const buttons = card.querySelectorAll("button");
  const status = card.querySelector(".confirmation-submit-status");
  card.classList.add("is-submitting");
  buttons.forEach((button) => (button.disabled = true));
  status.classList.remove("hidden");
  status.textContent = approved ? "正在安全提交，请勿重复操作…" : "正在返回，不会修改数据…";
  setConfirming(true);
  try {
    const response = await fetchJson("/confirm", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        confirmation_token: confirmation.token,
        approved,
        access_token: state.accessToken,
      }),
    });
    const article = card.closest(".message");
    renderOperationResult(card, response, presentation);
    refreshConfirmedResult(article, confirmation.action, response);
  } catch (error) {
    renderConfirmationFailure(card, error);
  } finally {
    setConfirming(false);
  }
}

function confirmationPresentation(confirmation) {
  const presentations = {
    cancel_order: {
      title: "取消这笔订单？",
      icon: "!",
      badge: "高风险",
      tone: "danger",
      confirmLabel: "确认取消订单",
      impact: "订单将变为已取消，之后不能继续支付；如仍需购买，需要重新下单。",
    },
    update_cart: {
      title: "修改购物车数量？",
      icon: "±",
      badge: "将修改数据",
      tone: "warning",
      confirmLabel: "确认修改数量",
      impact: "购物车中的商品数量和合计金额将随之变化。",
    },
    update_cart_items: {
      title: "批量修改购物车？",
      icon: "±",
      badge: "批量修改",
      tone: "warning",
      confirmLabel: "确认批量修改",
      impact: "多个购物车项的数量和合计金额将同时发生变化。",
    },
    remove_from_cart: {
      title: "移除这件商品？",
      icon: "−",
      badge: "将删除数据",
      tone: "danger",
      confirmLabel: "确认移除",
      impact: "该商品将从购物车移除；需要时可以重新搜索并添加。",
    },
    clear_cart: {
      title: "清空整个购物车？",
      icon: "!",
      badge: "高风险",
      tone: "danger",
      confirmLabel: "确认清空购物车",
      impact: "当前购物车中的所有商品都会被移除，需要时必须重新添加。",
    },
    create_order: {
      title: "创建这笔订单？",
      icon: "+",
      badge: "将创建数据",
      tone: "primary",
      confirmLabel: "确认创建订单",
      impact: "系统将使用演示地址和支付方式创建新订单，创建后仍需完成支付。",
    },
    pay_order: {
      title: "确认支付这笔订单？",
      icon: "¥",
      badge: "高风险",
      tone: "danger",
      confirmLabel: "确认演示支付",
      impact: "订单支付状态将发生变化。本项目使用演示支付，不会发起真实扣款。",
    },
  };
  return (
    presentations[confirmation.action] || {
      title: "确认执行这项操作？",
      icon: "!",
      badge: "将修改数据",
      tone: "warning",
      confirmLabel: "确认执行",
      impact: "这项操作会修改业务数据，请确认目标和内容无误。",
    }
  );
}

function createConfirmationFacts(action, argumentsValue) {
  const facts = document.createElement("dl");
  facts.className = "confirmation-facts";
  const entries = [];
  if (argumentsValue.order_no) entries.push(["订单", String(argumentsValue.order_no)]);
  else if (argumentsValue.order_id) entries.push(["订单", `#${argumentsValue.order_id}`]);
  if (argumentsValue.cart_id) entries.push(["购物车项", `#${argumentsValue.cart_id}`]);
  if (argumentsValue.product_id) entries.push(["商品", `#${argumentsValue.product_id}`]);
  if (argumentsValue.quantity) entries.push(["目标数量", String(argumentsValue.quantity)]);
  if (argumentsValue.final_amount != null) entries.push(["订单金额", formatCurrency(argumentsValue.final_amount)]);
  if (argumentsValue.status != null) entries.push(["当前状态", formatOrderStatus(argumentsValue.status)]);
  if (action === "update_cart_items" && Array.isArray(argumentsValue.items)) {
    entries.push(["影响范围", `${argumentsValue.items.length} 个购物车项`]);
  }
  if (action === "clear_cart") entries.push(["影响范围", "当前购物车全部商品"]);
  if (action === "create_order" && argumentsValue.payment_method) {
    entries.push(["支付方式", String(argumentsValue.payment_method)]);
  }
  if (action === "create_order" && argumentsValue.address_id) {
    entries.push(["演示地址", `#${argumentsValue.address_id}`]);
  }
  entries.forEach(([labelText, valueText]) => appendProductFact(facts, labelText, valueText));
  if (!entries.length) facts.classList.add("hidden");
  return facts;
}

function renderOperationResult(card, response, presentation) {
  const executed = response.status === "executed";
  card.className = `operation-result ${executed ? "success" : "cancelled"}`;
  card.removeAttribute("role");
  card.removeAttribute("aria-modal");
  card.removeAttribute("aria-labelledby");
  const icon = document.createElement("span");
  icon.className = "operation-result-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = executed ? "✓" : "↩";
  const copy = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = executed ? "操作已完成" : "操作已取消";
  const message = document.createElement("p");
  message.textContent = response.message || (executed ? presentation.confirmLabel : "数据没有被修改。");
  copy.append(title, message);
  card.replaceChildren(icon, copy);
}

function renderConfirmationFailure(card, error) {
  card.className = "operation-result failed";
  card.removeAttribute("role");
  card.removeAttribute("aria-modal");
  card.removeAttribute("aria-labelledby");
  const icon = document.createElement("span");
  icon.className = "operation-result-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = "!";
  const copy = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = "操作结果未能确认";
  const message = document.createElement("p");
  message.textContent = error.message;
  const guidance = document.createElement("span");
  guidance.textContent = "为避免重复执行，请重新向助手发起这项操作。";
  copy.append(title, message, guidance);
  card.replaceChildren(icon, copy);
}

function refreshConfirmedResult(article, action, response) {
  if (!article || response.status !== "executed") return;
  if (response.data != null) {
    renderResultData(article, response.data, [{ name: action }]);
    return;
  }
  if (action === "clear_cart") {
    renderResultData(article, [], [{ name: "clear_cart" }]);
  }
}

function renderResultData(article, data, toolCalls = []) {
  if (!article || data == null) return;
  const records = normalizeResultRecords(data);
  const kind = resultDataKind(records, toolCalls);
  const orders = records.filter(isOrderRecord);
  const cartItems = records.filter(isCartRecord);
  const products = records.filter(isProductRecord);

  const list = article.querySelector(".result-list");
  if (!list) return;
  list.classList.remove("hidden");
  list.classList.remove("product-list", "order-list", "cart-list", "empty-result-list");

  if (!records.length && kind) {
    renderEmptyResult(list, kind);
    return;
  }
  if (kind === "cart" && cartItems.length) {
    renderCartResults(list, cartItems);
    return;
  }
  if (kind === "product" && products.length) {
    list.classList.add("product-list");
    const context = productSearchContext(toolCalls);
    list.replaceChildren(...products.map((product) => createProductCard(product, context)));
    return;
  }
  if (kind === "order" && orders.length) {
    list.classList.add("order-list");
    list.replaceChildren(...orders.map(createOrderCard));
    return;
  }
  list.classList.add("hidden");
}

function normalizeResultRecords(data) {
  if (Array.isArray(data)) return data.filter(Boolean);
  if (Array.isArray(data?.content)) return data.content.filter(Boolean);
  return data && typeof data === "object" ? [data] : [];
}

function isOrderRecord(item) {
  return Boolean(item && typeof item === "object" && item.orderNo);
}

function isCartRecord(item) {
  return Boolean(
    item &&
      typeof item === "object" &&
      !item.orderNo &&
      (item.cartId != null ||
        (item.productId != null && item.quantity != null && typeof item.productName === "string")),
  );
}

function isProductRecord(item) {
  return Boolean(
    item &&
      typeof item === "object" &&
      !item.orderNo &&
      !isCartRecord(item) &&
      typeof item.name === "string" &&
      Object.hasOwn(item, "price"),
  );
}

function resultDataKind(records, toolCalls) {
  const calls = Array.isArray(toolCalls) ? toolCalls : [];
  const toolName = [...calls].reverse().find((call) => call?.name)?.name;
  if (["get_cart", "add_to_cart", "update_cart", "remove_from_cart", "clear_cart"].includes(toolName)) {
    return "cart";
  }
  if (["get_my_orders", "get_order_detail", "cancel_order", "create_order", "pay_order"].includes(toolName)) {
    return "order";
  }
  if (["search_products", "get_product_detail"].includes(toolName)) return "product";
  if (records.some(isOrderRecord)) return "order";
  if (records.some(isCartRecord)) return "cart";
  if (records.some(isProductRecord)) return "product";
  return null;
}

function renderEmptyResult(list, kind) {
  const copy = {
    cart: {
      icon: "＋",
      title: "购物车还是空的",
      description: "可以先让 OrderMate 根据预算推荐商品。",
      action: "去找商品",
      prompt: "推荐一些值得购买的商品",
    },
    order: {
      icon: "▤",
      title: "暂时没有订单",
      description: "完成购买后，订单状态会显示在这里。",
      action: "浏览商品",
      prompt: "推荐一些值得购买的商品",
    },
    product: {
      icon: "◇",
      title: "没有找到符合条件的商品",
      description: "试试放宽预算，或者换一个商品关键词。",
      action: "重新描述需求",
      prompt: "帮我推荐其他商品",
    },
  }[kind];
  if (!copy) return;
  list.classList.add("empty-result-list");
  const empty = document.createElement("div");
  empty.className = "result-empty";
  const icon = document.createElement("span");
  icon.className = "result-empty-icon";
  icon.setAttribute("aria-hidden", "true");
  icon.textContent = copy.icon;
  const title = document.createElement("strong");
  title.textContent = copy.title;
  const description = document.createElement("p");
  description.textContent = copy.description;
  const action = document.createElement("button");
  action.type = "button";
  action.dataset.buttonLevel = "secondary";
  action.dataset.prompt = copy.prompt;
  action.textContent = copy.action;
  empty.append(icon, title, description, action);
  list.replaceChildren(empty);
}

function productSearchContext(toolCalls) {
  const calls = Array.isArray(toolCalls) ? toolCalls : [];
  const call = [...calls]
    .reverse()
    .find((item) => item?.name === "search_products" || item?.name === "get_product_detail");
  return call?.arguments && typeof call.arguments === "object" ? call.arguments : {};
}

function createProductCard(product, context = {}) {
  const card = document.createElement("article");
  card.className = "product-card";

  const topline = document.createElement("div");
  topline.className = "product-card-topline";
  const identity = document.createElement("span");
  identity.className = "product-identity";
  identity.textContent = product.id ? `商品 #${product.id}` : "商品";
  const availability = document.createElement("span");
  const hasStock = product.stock != null && product.stock !== "" && Number.isFinite(Number(product.stock));
  const isActive = product.status == null || Number(product.status) === 1;
  const inStock = isActive && hasStock && Number(product.stock) > 0;
  availability.className = `product-availability ${isActive && hasStock ? (inStock ? "available" : "sold-out") : "unknown"}`;
  availability.textContent = !isActive
    ? "已下架"
    : hasStock
      ? inStock
        ? "有货"
        : "暂时缺货"
      : "库存待确认";
  topline.append(identity, availability);

  const heading = document.createElement("h3");
  heading.textContent = product.name || "未命名商品";

  const price = document.createElement("div");
  price.className = "product-price";
  price.textContent = formatCurrency(product.price);

  card.append(topline, heading, price);

  if (product.description) {
    const description = document.createElement("p");
    description.className = "product-description";
    description.textContent = String(product.description);
    card.append(description);
  }

  const facts = document.createElement("dl");
  facts.className = "product-facts";
  if (hasStock) appendProductFact(facts, "库存", `${Number(product.stock)} 件`);
  if (product.categoryId != null) appendProductFact(facts, "分类", `#${product.categoryId}`);
  if (facts.children.length) card.append(facts);

  const reasons = productMatchReasons(product, context);
  if (reasons.length) {
    const match = document.createElement("div");
    match.className = "product-match";
    const label = document.createElement("span");
    label.textContent = "匹配依据";
    const tags = document.createElement("div");
    reasons.forEach((reason) => {
      const tag = document.createElement("span");
      tag.textContent = reason;
      tags.append(tag);
    });
    match.append(label, tags);
    card.append(match);
  }

  const actions = document.createElement("div");
  actions.className = "product-actions";
  const detail = document.createElement("button");
  detail.type = "button";
  detail.className = "product-detail-button";
  detail.dataset.buttonLevel = "secondary";
  detail.textContent = "查看详情";
  const add = document.createElement("button");
  add.type = "button";
  add.className = "product-add-button";
  add.dataset.buttonLevel = "primary";
  configureAuthRequiredButton(add, "加入个人购物车");
  add.textContent = inStock ? "加入购物车" : "暂不可购买";
  if (product.id) {
    detail.dataset.prompt = `查看商品 ${product.id} 的详情`;
    if (inStock) add.dataset.prompt = `将商品 ${product.id} 加入购物车，数量 1`;
  } else {
    detail.disabled = true;
  }
  add.disabled = !product.id || !inStock;
  actions.append(detail, add);
  card.append(actions);
  return card;
}

function appendProductFact(list, labelText, valueText) {
  const item = document.createElement("div");
  const label = document.createElement("dt");
  const value = document.createElement("dd");
  label.textContent = labelText;
  value.textContent = valueText;
  item.append(label, value);
  list.append(item);
}

function productMatchReasons(product, context) {
  const reasons = [];
  const hasPrice = product.price != null && product.price !== "" && Number.isFinite(Number(product.price));
  const price = Number(product.price);
  const stock = Number(product.stock);
  if (context.keyword) reasons.push(`匹配“${context.keyword}”`);
  if (
    hasPrice &&
    context.max_price != null &&
    Number.isFinite(Number(context.max_price)) &&
    price <= Number(context.max_price)
  ) {
    reasons.push(`符合 ${formatCurrency(context.max_price)} 预算`);
  }
  if (
    hasPrice &&
    context.min_price != null &&
    Number.isFinite(Number(context.min_price)) &&
    price >= Number(context.min_price)
  ) {
    reasons.push(`满足 ${formatCurrency(context.min_price)} 起的价格范围`);
  }
  if (Number.isFinite(stock) && stock > 0 && (context.in_stock === true || !reasons.length)) {
    reasons.push("当前有货");
  }
  return reasons.slice(0, 3);
}

function formatCurrency(value) {
  if (value == null || value === "") return "价格待确认";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "价格待确认";
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount);
}

function renderCartResults(list, items) {
  list.classList.add("cart-list");
  const summary = createCartSummary(items);
  const cards = items.map(createCartCard);
  list.replaceChildren(...cards, summary);
}

function createCartCard(item) {
  const card = document.createElement("article");
  card.className = "cart-card";

  const main = document.createElement("div");
  main.className = "cart-card-main";
  const identity = document.createElement("span");
  identity.className = "cart-item-identity";
  identity.textContent = item.productId ? `商品 #${item.productId}` : "购物车商品";
  const heading = document.createElement("h3");
  heading.textContent = item.productName || (item.productId ? `商品 #${item.productId}` : "未命名商品");
  const unitPrice = document.createElement("span");
  unitPrice.className = "cart-unit-price";
  unitPrice.textContent = `${formatCurrency(item.price)} / 件`;
  main.append(identity, heading, unitPrice);

  const quantity = finitePositiveInteger(item.quantity);
  const price = finiteAmount(item.price);
  const metrics = document.createElement("div");
  metrics.className = "cart-card-metrics";
  const quantityBlock = document.createElement("div");
  quantityBlock.innerHTML = `<span>数量</span><strong>${quantity ?? "—"}</strong>`;
  const subtotalBlock = document.createElement("div");
  const subtotal = quantity != null && price != null ? price * quantity : null;
  subtotalBlock.innerHTML = `<span>小计</span><strong>${subtotal == null ? "金额待确认" : formatCurrency(subtotal)}</strong>`;
  metrics.append(quantityBlock, subtotalBlock);

  const actions = document.createElement("div");
  actions.className = "cart-card-actions";
  const detail = document.createElement("button");
  detail.type = "button";
  detail.className = "cart-detail-button";
  detail.dataset.buttonLevel = "secondary";
  detail.textContent = "商品详情";
  if (item.productId) detail.dataset.prompt = `查看商品 ${item.productId} 的详情`;
  else detail.disabled = true;
  const adjust = document.createElement("button");
  adjust.type = "button";
  adjust.className = "cart-adjust-button";
  adjust.dataset.buttonLevel = "secondary";
  configureAuthRequiredButton(adjust, "修改个人购物车");
  adjust.textContent = "调整数量";
  if (item.cartId && quantity != null) {
    adjust.dataset.prompt = `将购物车项 ${item.cartId} 的数量改为 ${quantity + 1}`;
  } else {
    adjust.disabled = true;
  }
  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "cart-remove-button";
  remove.dataset.buttonLevel = "danger";
  configureAuthRequiredButton(remove, "移出个人购物车商品");
  remove.textContent = "移出购物车";
  if (item.cartId) remove.dataset.prompt = `从购物车移除购物车项 ${item.cartId}`;
  else remove.disabled = true;
  actions.append(detail, adjust, remove);

  card.append(main, metrics, actions);
  return card;
}

function createCartSummary(items) {
  const summary = document.createElement("section");
  summary.className = "cart-summary";
  const validQuantities = items.map((item) => finitePositiveInteger(item.quantity));
  const itemCount = validQuantities.reduce((total, value) => total + (value ?? 0), 0);
  const subtotals = items.map((item, index) => {
    const price = finiteAmount(item.price);
    const quantity = validQuantities[index];
    return price != null && quantity != null ? price * quantity : null;
  });
  const completeTotal = subtotals.every((value) => value != null);
  const hasKnownTotal = subtotals.some((value) => value != null);
  const completeQuantity = validQuantities.every((value) => value != null);
  const total = subtotals.reduce((sum, value) => sum + (value ?? 0), 0);

  const copy = document.createElement("div");
  const label = document.createElement("span");
  label.textContent = `${items.length} 种商品 · ${completeQuantity ? `共 ${itemCount} 件` : "部分数量待确认"}`;
  const amount = document.createElement("strong");
  amount.textContent = hasKnownTotal
    ? `${completeTotal ? "合计" : "已知金额"} ${formatCurrency(total)}`
    : "合计金额待确认";
  copy.append(label, amount);

  const action = document.createElement("button");
  action.type = "button";
  action.dataset.buttonLevel = "danger";
  configureAuthRequiredButton(action, "清空个人购物车");
  action.dataset.prompt = "清空我的购物车";
  action.textContent = "清空购物车";
  summary.append(copy, action);
  return summary;
}

function createOrderCard(order) {
  const card = document.createElement("article");
  card.className = "order-card";

  const heading = document.createElement("div");
  heading.className = "order-card-heading";
  const identity = document.createElement("div");
  const label = document.createElement("span");
  label.textContent = "订单编号";
  const number = document.createElement("strong");
  number.textContent = order.orderNo || (order.id ? `订单 #${order.id}` : "订单号待确认");
  identity.append(label, number);
  const status = document.createElement("span");
  status.className = `order-status status-${normalizeOrderStatus(order.status)}`;
  status.textContent = formatOrderStatus(order.status);
  heading.append(identity, status);

  const meta = document.createElement("div");
  meta.className = "order-meta";
  const created = document.createElement("span");
  created.textContent = order.createdAt ? `创建于 ${formatDateTime(order.createdAt)}` : "创建时间待确认";
  const payment = document.createElement("span");
  payment.className = `payment-status payment-${normalizePaymentStatus(order.paymentStatus)}`;
  payment.textContent = formatPaymentStatus(order.paymentStatus);
  meta.append(created, payment);

  const items = Array.isArray(order.items) ? order.items : [];
  const itemList = document.createElement("div");
  itemList.className = "order-item-list";
  if (items.length) {
    items.forEach((item) => itemList.append(createOrderItemRow(item)));
  } else {
    const emptyItems = document.createElement("p");
    emptyItems.className = "order-items-empty";
    emptyItems.textContent = "暂无商品明细";
    itemList.append(emptyItems);
  }

  const amounts = document.createElement("dl");
  amounts.className = "order-amounts";
  if (order.totalAmount != null) appendProductFact(amounts, "商品总额", formatCurrency(order.totalAmount));
  if (order.discountAmount != null && Number(order.discountAmount) !== 0) {
    appendProductFact(amounts, "优惠", `-${formatCurrency(order.discountAmount)}`);
  }
  appendProductFact(amounts, "实付金额", formatCurrency(order.finalAmount ?? order.totalAmount));

  const actions = document.createElement("div");
  actions.className = "order-actions";
  const detail = document.createElement("button");
  detail.type = "button";
  detail.className = "order-detail-button";
  detail.dataset.buttonLevel = "secondary";
  configureAuthRequiredButton(detail, "查看本人订单详情");
  detail.textContent = "查看详情";
  if (order.id) detail.dataset.prompt = `查看订单 ${order.id} 的详情`;
  else detail.disabled = true;
  actions.append(detail);

  if (Number(order.status) === 0 && order.id) {
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "order-cancel-button";
    cancel.dataset.buttonLevel = "danger";
    configureAuthRequiredButton(cancel, "取消本人订单");
    cancel.dataset.prompt = `取消订单 ${order.id}`;
    cancel.textContent = "取消订单";
    actions.append(cancel);
  }
  card.append(heading, meta, itemList, amounts, actions);
  return card;
}

function createOrderItemRow(item) {
  const row = document.createElement("div");
  row.className = "order-item-row";
  const copy = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = item.productName || (item.productId ? `商品 #${item.productId}` : "未命名商品");
  const quantity = document.createElement("span");
  quantity.textContent = `数量 × ${finitePositiveInteger(item.quantity) ?? "—"}`;
  copy.append(name, quantity);
  const subtotal = document.createElement("span");
  const value = item.totalPrice ??
    (finiteAmount(item.unitPrice) != null && finitePositiveInteger(item.quantity) != null
      ? finiteAmount(item.unitPrice) * finitePositiveInteger(item.quantity)
      : null);
  subtotal.textContent = value == null ? "金额待确认" : formatCurrency(value);
  row.append(copy, subtotal);
  return row;
}

function finiteAmount(value) {
  if (value == null || value === "") return null;
  const amount = Number(value);
  return Number.isFinite(amount) && amount >= 0 ? amount : null;
}

function finitePositiveInteger(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isInteger(number) && number > 0 ? number : null;
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间待确认";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function normalizeOrderStatus(status) {
  const value = Number(status);
  return Number.isInteger(value) && value >= 0 && value <= 4 ? value : "unknown";
}

function normalizePaymentStatus(status) {
  const value = Number(status);
  return value === 0 || value === 1 ? value : "unknown";
}

async function fetchJson(url, options = {}) {
  const { handleAuthFailure = true, ...fetchOptions } = options;
  const response = await fetch(url, {
    ...fetchOptions,
    headers: {
      "Content-Type": "application/json",
      ...(fetchOptions.headers || {}),
    },
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) {
    if (response.status === 401 && state.accessToken && handleAuthFailure) {
      const expiredAccessToken = state.accessToken;
      clearAuth();
      void rotateSessionContext(expiredAccessToken);
      loginHint.textContent = "登录已失效，请重新登录。";
      loginHint.classList.add("error");
      addSystemMessage("登录状态已失效，切换到匿名会话。");
    }
    const detail =
      payload.detail === "OPENAI_API_KEY is not configured."
        ? "模型 API Key 尚未配置，请先填写环境变量 OPENAI_API_KEY。"
        : payload.detail;
    throw new Error(detail || `请求失败（HTTP ${response.status}）`);
  }
  return payload;
}

function clearAuth() {
  state.accessToken = null;
  state.username = null;
  state.authStatus = "anonymous";
  state.pendingPrompt = null;
  state.pendingLabel = null;
  sessionStorage.removeItem("ordermate_token");
  sessionStorage.removeItem("ordermate_username");
  syncAuthUi();
}

function formatOutcome(outcome) {
  return (
    {
      success: "成功",
      error: "失败",
      confirmation_required: "待确认",
    }[outcome] || outcome
  );
}

function formatOrderStatus(status) {
  return (
    {
      0: "待支付",
      1: "已支付",
      2: "已发货",
      3: "已完成",
      4: "已取消",
    }[status] || "未知状态"
  );
}

function formatPaymentStatus(status) {
  return (
    {
      0: "未支付",
      1: "已支付",
    }[status] || "支付状态未知"
  );
}

function setSending(sending) {
  state.sending = sending;
  sendButton.disabled = sending;
  sendButton.setAttribute("aria-label", sending ? "正在发送消息" : "发送消息");
  sendButton.classList.toggle("is-loading", sending);
  sendButton.querySelector("span:first-child").textContent = sending ? "发送中…" : "发送";
  chatForm.setAttribute("aria-busy", String(sending));
  conversation.setAttribute("aria-busy", String(sending));
  if (sending) announce("消息已发送，OrderMate 正在处理。");
}

function setConfirming(confirming) {
  state.confirming = confirming ? 1 : 0;
  logoutButton.disabled = confirming;
  newChatButton.disabled = confirming;
}

function cancelActiveRequest() {
  const request = state.activeRequest;
  if (!request) return;
  state.activeRequest = null;
  request.controller.abort();
  setSending(false);
}

function resizeComposer() {
  messageInput.style.height = "auto";
  const nextHeight = Math.min(messageInput.scrollHeight, 140);
  messageInput.style.height = `${nextHeight}px`;
  messageInput.style.overflowY =
    messageInput.scrollHeight > 140 ? "auto" : "hidden";
}

function scrollToLatest(force = false) {
  const distanceFromBottom = conversation.scrollHeight - conversation.scrollTop - conversation.clientHeight;
  const shouldScroll = force || distanceFromBottom < 120;
  if (!shouldScroll) return;
  requestAnimationFrame(() => {
    conversation.scrollTop = conversation.scrollHeight;
  });
}
