const conversation = document.querySelector("#conversation");
const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message-input");
const sendButton = document.querySelector("#send-button");
const loginForm = document.querySelector("#login-form");
const loginButton = document.querySelector("#login-button");
const fillDemoButton = document.querySelector("#fill-demo-button");
const loginHint = document.querySelector("#login-hint");
const signedIn = document.querySelector("#signed-in");
const signedInName = document.querySelector("#signed-in-name");
const logoutButton = document.querySelector("#logout-button");
const clearButton = document.querySelector("#clear-button");
const agentStatus = document.querySelector("#agent-status");
const modelStatus = document.querySelector("#model-status");

const state = {
  sessionId: sessionStorage.getItem("ordermate_session") || crypto.randomUUID(),
  accessToken: sessionStorage.getItem("ordermate_token"),
  username: sessionStorage.getItem("ordermate_username"),
  sending: false,
};

sessionStorage.setItem("ordermate_session", state.sessionId);
syncAuthUi();
checkHealth();
resizeComposer();

document.addEventListener("click", (event) => {
  const promptButton = event.target.closest("[data-prompt]");
  if (!promptButton) return;
  messageInput.value = promptButton.dataset.prompt;
  resizeComposer();
  messageInput.focus();
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

  try {
    const response = await fetchChatStream(
      {
        message,
        session_id: state.sessionId,
        access_token: state.accessToken,
      },
      (event) => updateStreamingStatus(pendingMessage, event),
    );
    fillAssistantMessage(pendingMessage, response);
  } catch (error) {
    fillAssistantMessage(pendingMessage, {
      answer: error.message,
      tool_calls: [],
    });
  } finally {
    setSending(false);
    messageInput.focus();
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
  loginButton.disabled = true;
  loginButton.textContent = "正在登录…";
  loginHint.classList.remove("error");

  const form = new FormData(loginForm);
  const username = String(form.get("username") || "");
  const password = String(form.get("password") || "");

  try {
    const response = await fetchJson("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    state.accessToken = response.access_token;
    state.username = username;
    sessionStorage.setItem("ordermate_token", state.accessToken);
    sessionStorage.setItem("ordermate_username", username);
    loginForm.reset();
    loginHint.textContent = "登录成功，购物车和订单工具已经解锁。";
    syncAuthUi();
    addSystemMessage(`已切换到「${username}」的个人会话上下文，订单和购物车工具已解锁。`);
  } catch (error) {
    loginHint.textContent = error.message;
    loginHint.classList.add("error");
  } finally {
    loginButton.disabled = false;
    loginButton.textContent = "登录以使用订单工具";
  }
});

fillDemoButton.addEventListener("click", () => {
  loginForm.elements.username.value = "testuser";
  loginForm.elements.password.value = "password";
  loginForm.elements.username.focus();
  loginHint.textContent = "演示账号已填入，点击上方按钮登录。";
  loginHint.classList.remove("error");
});

logoutButton.addEventListener("click", () => {
  clearAuth();
  loginHint.textContent = "已退出。商品搜索仍可匿名使用。";
  addSystemMessage("已退出登录，切换到匿名会话。历史上下文已清除，商品搜索仍可匿名使用。");
});

clearButton.addEventListener("click", async () => {
  const previousSessionId = state.sessionId;
  conversation.querySelectorAll(".message").forEach((message, index) => {
    if (index > 0) message.remove();
  });
  state.sessionId = crypto.randomUUID();
  sessionStorage.setItem("ordermate_session", state.sessionId);

  try {
    await fetchJson("/conversation/clear", {
      method: "POST",
      body: JSON.stringify({
        session_id: previousSessionId,
        access_token: state.accessToken,
      }),
    });
    addSystemMessage("会话已清空，历史上下文已重置。");
  } catch (error) {
    console.warn("服务端会话记忆清理失败：", error);
  }
});

async function checkHealth() {
  try {
    const health = await fetchJson("/health");
    agentStatus.classList.add("online");
    agentStatus.querySelector("span").textContent = "在线";
    modelStatus.textContent =
      health.agent_mode === "demo"
        ? "本地演示"
        : health.model_configured
          ? "真实模型"
          : "待配置";
  } catch {
    agentStatus.classList.add("offline");
    agentStatus.querySelector("span").textContent = "离线";
    modelStatus.textContent = "不可用";
  }
}

function syncAuthUi() {
  const loggedIn = Boolean(state.accessToken);
  loginForm.classList.toggle("hidden", loggedIn);
  signedIn.classList.toggle("hidden", !loggedIn);
  if (loggedIn) signedInName.textContent = state.username || "已登录";
}

function addUserMessage(text) {
  const fragment = document
    .querySelector("#user-message-template")
    .content.cloneNode(true);
  fragment.querySelector(".message-bubble p").textContent = text;
  conversation.append(fragment);
  scrollToLatest();
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
  article.querySelector(".message-bubble p").innerHTML =
    '<span class="typing-dots"><i></i><i></i><i></i></span>';
  conversation.append(fragment);
  scrollToLatest();
  return article;
}

function fillAssistantMessage(article, response) {
  article.querySelector(".message-bubble p").textContent =
    response.answer || "暂时没有回复。";

  if (response.reference) {
    const refBar = article.querySelector(".reference-bar");
    if (refBar) {
      refBar.classList.remove("hidden");
      const typeLabel =
        response.reference.type === "order" ? "订单" : "商品";
      refBar.textContent = `已从上下文解析为${typeLabel} #${response.reference.value}`;
    }
  }

  if (response.tool_calls?.length) {
    const trace = article.querySelector(".tool-trace");
    trace.classList.remove("hidden");
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = `工具调用轨迹 · ${response.tool_calls.length} 步`;
    details.append(summary);
    const list = document.createElement("div");
    list.className = "tool-list";
    response.tool_calls.forEach((call) => {
      const chip = document.createElement("span");
      chip.className = `tool-chip ${call.outcome === "error" ? "error" : ""}`;
      chip.textContent = `${call.name} · ${formatOutcome(call.outcome)}`;
      chip.title = JSON.stringify(call.arguments);
      list.append(chip);
    });
    details.append(list);
    trace.replaceChildren(details);
  }

  renderResultData(article, response.data);

  if (response.confirmation) {
    renderConfirmation(article, response.confirmation);
  }
  scrollToLatest();
}

function updateStreamingStatus(article, event) {
  if (event.type === "started" || event.type === "progress") {
    article.querySelector(".message-bubble p").textContent = event.data.message;
  }
  if (event.type === "reference") {
    article.querySelector(".message-bubble p").textContent =
      `已从上下文解析为${event.data.type === "order" ? "订单" : "商品"}：${event.data.value}`;
  }
  if (event.type === "tool") {
    article.querySelector(".message-bubble p").textContent = `正在执行工具：${event.data.name}`;
  }
  if (event.type === "confirmation_required") {
    article.querySelector(".message-bubble p").textContent = "操作需要你的确认。";
  }
}

async function fetchChatStream(payload, onEvent) {
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
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
    const frames = buffer.split("\n\n");
    buffer = frames.pop();
    for (const frame of frames) {
      const event = frame.match(/^event: (.+)$/m)?.[1];
      const data = frame.match(/^data: (.+)$/m)?.[1];
      if (!event || !data) continue;
      const parsed = JSON.parse(data);
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
  card.classList.remove("hidden");

  const title = document.createElement("strong");
  title.textContent = "需要你的明确确认";
  const description = document.createElement("span");
  description.textContent = confirmation.description;
  const actions = document.createElement("div");
  actions.className = "confirmation-actions";
  const approve = document.createElement("button");
  approve.className = "confirm-button";
  approve.type = "button";
  approve.textContent = "确认执行";
  const reject = document.createElement("button");
  reject.className = "reject-button";
  reject.type = "button";
  reject.textContent = "暂不执行";
  actions.append(approve, reject);
  card.replaceChildren(title, description, actions);

  approve.addEventListener("click", () =>
    submitConfirmation(card, confirmation.token, true),
  );
  reject.addEventListener("click", () =>
    submitConfirmation(card, confirmation.token, false),
  );
}

async function submitConfirmation(card, token, approved) {
  const buttons = card.querySelectorAll("button");
  buttons.forEach((button) => (button.disabled = true));
  try {
    const response = await fetchJson("/confirm", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.sessionId,
        confirmation_token: token,
        approved,
        access_token: state.accessToken,
      }),
    });
    card.classList.remove("confirmation-card");
    card.classList.add("tool-trace");
    card.replaceChildren(document.createTextNode(response.message));
    renderResultData(card.closest(".message"), response.data);
  } catch (error) {
    const errorLine = document.createElement("span");
    errorLine.textContent = error.message;
    card.append(errorLine);
    buttons.forEach((button) => (button.disabled = false));
  }
}

function renderResultData(article, data) {
  if (!article || !data) return;
  const orders = (Array.isArray(data) ? data : [data]).filter(
    (item) => item && typeof item === "object" && item.orderNo,
  );
  if (!orders.length) return;

  const list = article.querySelector(".result-list");
  if (!list) return;
  list.classList.remove("hidden");
  list.replaceChildren(...orders.map(createOrderCard));
}

function createOrderCard(order) {
  const card = document.createElement("article");
  card.className = "order-card";

  const heading = document.createElement("div");
  heading.className = "order-card-heading";
  const number = document.createElement("strong");
  number.textContent = order.orderNo;
  const status = document.createElement("span");
  status.className = `order-status status-${order.status}`;
  status.textContent = formatOrderStatus(order.status);
  heading.append(number, status);

  const amount = document.createElement("div");
  amount.className = "order-amount";
  amount.textContent = `实付 ¥${order.finalAmount ?? order.totalAmount ?? "—"}`;

  const products = document.createElement("p");
  const items = Array.isArray(order.items) ? order.items : [];
  products.textContent = items.length
    ? items
        .map((item) => `${item.productName || `商品 #${item.productId}`} × ${item.quantity}`)
        .join("、")
    : "暂无商品明细";

  card.append(heading, amount, products);
  if (order.status === 0) {
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "order-cancel-button";
    cancel.dataset.prompt = `取消订单 ${order.id}`;
    cancel.textContent = "申请取消";
    card.append(cancel);
  }
  return card;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    payload = {};
  }
  if (!response.ok) {
    if (response.status === 401 && state.accessToken) {
      clearAuth();
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

function setSending(sending) {
  state.sending = sending;
  sendButton.disabled = sending;
}

function resizeComposer() {
  messageInput.style.height = "auto";
  const nextHeight = Math.min(messageInput.scrollHeight, 140);
  messageInput.style.height = `${nextHeight}px`;
  messageInput.style.overflowY =
    messageInput.scrollHeight > 140 ? "auto" : "hidden";
}

function scrollToLatest() {
  requestAnimationFrame(() => {
    conversation.scrollTop = conversation.scrollHeight;
  });
}
