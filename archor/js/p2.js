(function () {
  var S = window.ArchorSession;
  var STORAGE_SESSION = S.STORAGE_SESSION;
  var STORAGE_MESSAGES = S.STORAGE_MESSAGES;
  var STORAGE_MODE = S.STORAGE_MODE;
  var STORAGE_PROMPT = "archorPrompt";
  var API_BASE = S.API_BASE;

  var thread = document.getElementById("chat-thread");
  var form = document.getElementById("chat-form");
  var input = document.getElementById("chat-input");
  var btnSend = document.getElementById("btn-send");
  var stateLabel = document.getElementById("state-label");
  var slotProgress = document.getElementById("slot-progress");
  var convergenceActions = document.getElementById("convergence-actions");
  var btnGenerate = document.getElementById("btn-generate");
  var footer = document.querySelector(".p2-footer");

  var session = null;
  var messages = [];
  var busy = false;
  var bootstrapped = false;

  var STATE_LABELS = {
    INIT: "聊聊行程",
    SLOT_FILLING: "聊聊行程",
    CONVERGENCE: "可以进入下一步",
  };

  var SUPPORTED_CITIES = ["北京", "南京", "重庆", "新疆"];
  var MODE_ANCHOR = {
    ROUTE: "玩",
    EVENT: "玩",
    FOOD: "吃",
    FILL: "住",
    RISK: "玩",
  };
  var PROFILE_TAGS = [
    "大学生/年轻毕业生",
    "追星族/赛事爱好者",
    "年轻情侣/朋友",
    "长途长假游客",
    "单身独居青年",
    "上班族",
    "商务出差",
    "亲子游出行",
    "带长辈出行",
  ];

  function hasProfileTag(tags) {
    if (!tags || !tags.length) return false;
    return tags.some(function (t) {
      return PROFILE_TAGS.indexOf(t) >= 0;
    });
  }

  function inferSlotProgress(slots, mode) {
    mode = mode || sessionStorage.getItem(STORAGE_MODE) || null;
    var destOk =
      slots &&
      slots.destination &&
      SUPPORTED_CITIES.indexOf(slots.destination) >= 0;
    var daysOk = slots && slots.days > 0;
    var anchorOk =
      slots &&
      (slots.anchor === "吃" ||
        slots.anchor === "住" ||
        slots.anchor === "玩" ||
        (mode && MODE_ANCHOR[mode]));
    var tagsOk = slots && hasProfileTag(slots.tags);
    var transportOk =
      slots &&
      slots.transport_preferences &&
      slots.transport_preferences.length > 0;
    return {
      destination: !!destOk,
      days: !!daysOk,
      anchor: !!anchorOk,
      tags: !!tagsOk,
      transport: !!transportOk,
    };
  }

  function updateSlotProgress(slots, meta) {
    if (!slotProgress || !slots) return;
    var progress =
      (meta && meta.slot_progress) || inferSlotProgress(slots);
    slotProgress.querySelectorAll(".p2-chip").forEach(function (chip) {
      var key = chip.getAttribute("data-slot");
      chip.classList.toggle("is-done", !!(progress && progress[key]));
    });
  }

  function loadJson(key, fallback) {
    try {
      var raw = sessionStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (err) {
      return fallback;
    }
  }

  function saveJson(key, value) {
    try {
      sessionStorage.setItem(key, JSON.stringify(value));
    } catch (err) {}
  }

  function saveSession() {
    saveJson(STORAGE_SESSION, session);
  }

  function saveMessages() {
    saveJson(STORAGE_MESSAGES, messages);
  }

  function syncSendState() {
    btnSend.disabled = busy || !input.value.trim();
  }

  function autoResize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
  }

  function scrollToBottom() {
    thread.scrollTop = thread.scrollHeight;
  }

  function escapeHtml(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderMessages() {
    thread.innerHTML = messages
      .map(function (msg) {
        var roleClass = msg.role === "user" ? "msg--user" : "msg--assistant";
        var avatar = msg.role === "user" ? "你" : "A";
        return (
          '<article class="msg ' +
          roleClass +
          '">' +
          '<div class="msg__avatar" aria-hidden="true">' +
          avatar +
          "</div>" +
          '<div class="msg__body">' +
          '<div class="msg__bubble">' +
          escapeHtml(msg.text) +
          "</div>" +
          "</div>" +
          "</article>"
        );
      })
      .join("");
    scrollToBottom();
  }

  function appendMessage(role, text) {
    messages.push({ role: role, text: text });
    saveMessages();
    renderMessages();
  }

  function showTyping() {
    var el = document.createElement("article");
    el.className = "msg msg--assistant msg--typing";
    el.id = "typing-indicator";
    el.innerHTML =
      '<div class="msg__avatar" aria-hidden="true">A</div>' +
      '<div class="msg__body"><div class="msg__bubble">' +
      '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>' +
      "</div></div>";
    thread.appendChild(el);
    scrollToBottom();
  }

  function hideTyping() {
    var el = document.getElementById("typing-indicator");
    if (el) el.remove();
  }

  function updateUiState(currentState, meta, slots) {
    stateLabel.textContent = STATE_LABELS[currentState] || "对话中";
    if (slots) {
      updateSlotProgress(slots, meta || {});
    }

    var isConverged = currentState === "CONVERGENCE";

    convergenceActions.hidden = !isConverged;
    footer.classList.toggle("is-converged", isConverged);
    input.placeholder = isConverged
      ? "还可以说「太累了」「换个玩法」…"
      : "问问 Anchor";
    input.disabled = false;
    input.readOnly = false;
  }

  function postChat(message) {
    return fetch(API_BASE + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: message,
        session: session,
        mode: sessionStorage.getItem(STORAGE_MODE),
      }),
    }).then(function (res) {
      if (!res.ok) {
        return res.text().then(function (text) {
          var detail = "对话请求失败";
          try {
            var data = JSON.parse(text);
            if (typeof data.detail === "string") detail = data.detail;
          } catch (parseErr) {}
          throw new Error(detail);
        });
      }
      return res.json();
    }).catch(function (err) {
      if (err instanceof TypeError) {
        throw new Error("network");
      }
      throw err;
    });
  }

  function sendMessage(text, options) {
    options = options || {};
    if (busy) return Promise.resolve();
    if (!text || !text.trim()) return Promise.resolve();

    busy = true;
    syncSendState();

    if (!options.skipUserBubble) {
      appendMessage("user", text.trim());
    }

    showTyping();

    return postChat(text.trim())
      .then(function (data) {
        hideTyping();
        session = data.session;
        saveSession();
        appendMessage("assistant", data.reply);
        updateUiState(session.current_state, data.meta, session.slots);
      })
      .catch(function (err) {
        hideTyping();
        var hint =
          err && err.message === "network"
            ? "无法连接 Anchor 后端。请确认已在 8000 端口启动服务，并访问 http://localhost:8000/archor/"
            : "抱歉，服务暂时不可用，请稍后重试。";
        appendMessage("assistant", hint);
      })
      .finally(function () {
        busy = false;
        syncSendState();
      });
  }

  function bootstrap() {
    if (bootstrapped) return;
    bootstrapped = true;

    session = loadJson(STORAGE_SESSION, null);
    messages = loadJson(STORAGE_MESSAGES, []);

    if (messages.length) {
      renderMessages();
      if (session) {
        var state = session.current_state;
        if (state === "RISK_CLARIFY") {
          state = "CONVERGENCE";
          session.current_state = state;
          saveSession();
        }
        updateUiState(state, {}, session);
      }
      return;
    }

    appendMessage(
      "assistant",
      "你好，我是 Anchor，你的智能旅行规划搭档。说说这次想去哪儿、怎么玩，我来帮你量化排行程。"
    );

    var seed = sessionStorage.getItem(STORAGE_PROMPT);
    if (seed && seed.trim()) {
      sendMessage(seed.trim(), { skipUserBubble: false });
    }
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    autoResize();
    syncSendState();
    sendMessage(text);
  });

  input.addEventListener("input", function () {
    autoResize();
    syncSendState();
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!btnSend.disabled) form.requestSubmit();
    }
  });

  btnGenerate.addEventListener("click", function () {
    if (!session || session.current_state !== "CONVERGENCE") return;
    session.p1_mode = sessionStorage.getItem(STORAGE_MODE) || session.p1_mode || "ROUTE";
    S.saveSession(session);
    S.clearPlanCache();
    window.location.href = "p3.html";
  });

  bootstrap();
  syncSendState();
})();
