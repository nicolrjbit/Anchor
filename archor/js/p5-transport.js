(function () {
  var S = window.ArchorSession;
  var root = document.getElementById("transport-root");
  var btnNext = document.getElementById("btn-next");
  var footerHint = document.getElementById("footer-hint");
  var pageSub = document.getElementById("page-sub");
  var pageError = document.getElementById("page-error");

  var session = S.syncTransportPreferences(S.ensureP1Mode(S.loadSession() || {}));
  S.saveSession(session);
  var MODES = ["公交", "地铁", "骑行", "步行", "自驾"];
  var legs = [];
  var preferenceLabel = "";
  // 回填上一次逐段选择（从他页返回时不丢）
  var savedModes = session.transport_modes || {};

  function showError(msg, link) {
    pageError.hidden = false;
    pageError.innerHTML = S.escapeHtml(msg) + (link || "");
    btnNext.disabled = true;
  }

  function typeLabel(t) {
    return S.POI_TYPE_LABEL[t] || t || "";
  }

  function renderLegRow(leg) {
    var current = savedModes[leg.leg_id] || leg.selected_mode || leg.recommended_mode;
    var options = MODES.map(function (m) {
      return (
        '<option value="' +
        S.escapeHtml(m) +
        '"' +
        (m === current ? " selected" : "") +
        ">" +
        S.escapeHtml(m) +
        "</option>"
      );
    }).join("");
    var switchCls = leg.cross_switch ? " transport-leg--switch" : "";
    return (
      '<div class="transport-leg' +
      switchCls +
      '" data-leg-id="' +
      S.escapeHtml(leg.leg_id) +
      '">' +
      '<p class="transport-leg__route">Day ' +
      leg.day_index +
      " · " +
      S.escapeHtml(leg.from_name) +
      "（" +
      S.escapeHtml(typeLabel(leg.from_type)) +
      "）→ " +
      S.escapeHtml(leg.to_name) +
      "（" +
      S.escapeHtml(typeLabel(leg.to_type)) +
      "）</p>" +
      '<p class="transport-leg__reason">' +
      S.escapeHtml(leg.reason || "") +
      " · 约 " +
      (leg.tran_minutes || 0) +
      "min</p>" +
      '<div class="transport-leg__pick">' +
      '<span class="transport-leg__pick-label">出行方式</span>' +
      '<select class="transport-mode-select" data-leg-id="' +
      S.escapeHtml(leg.leg_id) +
      '">' +
      options +
      "</select></div></div>"
    );
  }

  function render() {
    if (!legs.length) {
      root.innerHTML =
        '<p class="transport-empty">本次行程各点距离很近，无需额外交通，可直接进入下一步。</p>';
      btnNext.disabled = false;
      footerHint.textContent = "无需交通段";
      return;
    }
    root.innerHTML = legs.map(renderLegRow).join("");
    footerHint.textContent = preferenceLabel
      ? "已按「" + preferenceLabel + "」默认推荐，可逐段调整"
      : "已默认采用推荐，可逐段调整";
    btnNext.disabled = false;
  }

  function collectModes() {
    var modes = {};
    root.querySelectorAll(".transport-mode-select").forEach(function (sel) {
      modes[sel.dataset.legId] = sel.value;
    });
    return modes;
  }

  if (!session.selected_anchor_pois || !session.selected_anchor_pois.length) {
    showError("请先在锚点页（第 3 页）完成选择。", ' <a href="p3.html">前往锚点页</a>');
    return;
  }
  if (!session.selected_follow_pois || !session.selected_follow_pois.length) {
    showError("请先在跟随页（第 4 页）完成选择。", ' <a href="p4.html">前往跟随页</a>');
    return;
  }

  preferenceLabel =
    S.transportPreferenceLabel(S.effectiveTransportPreferences(session)) || "";
  pageSub.textContent = preferenceLabel
    ? "正在按你希望的「" + preferenceLabel + "」计算各路段推荐…"
    : "正在按你的住/玩/吃动线计算各路段…";
  // 拉取一次路书草案，拿到真实路段后逐段给出推荐
  S.fetchPlan(session, 12000)
    .then(function (data) {
      var plan = data.plan || {};
      legs = plan.transport_legs || [];
      preferenceLabel =
        plan.transport_preference_label ||
        S.transportPreferenceLabel(plan.transport_preferences) ||
        preferenceLabel;
      if (legs.length) {
        pageSub.textContent = preferenceLabel
          ? "已按你在对话里说的「" +
            preferenceLabel +
            "」为各路段默认推荐；很近的路会优先步行，你仍可逐段调整。"
          : "下面是按你的动线算出的真实路段，已给出推荐方式。很近的路段会优先步行，跨区/换酒店会优先省力方式。";
      } else {
        pageSub.textContent = "已根据动线编排，本次没有需要长距离移动的路段。";
      }
      render();
    })
    .catch(function (err) {
      showError(err.message || "路段计算失败，请稍后重试");
    });

  btnNext.addEventListener("click", function () {
    session.transport_modes = collectModes();
    session.transport_confirmed = true;
    S.syncTransportPreferences(session);
    S.saveSession(session);
    S.clearPlanCache();
    window.location.href = "p6.html";
  });
})();
