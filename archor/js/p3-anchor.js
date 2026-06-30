(function () {
  var S = window.ArchorSession;
  var grid = document.getElementById("poi-grid");
  var btnNext = document.getElementById("btn-next");
  var footerHint = document.getElementById("footer-hint");
  var pageSub = document.getElementById("page-sub");
  var pageTitle = document.getElementById("page-title");
  var pageError = document.getElementById("page-error");

  var session = S.ensureP1Mode(S.loadSession() || {});
  var picks = session.anchor_recommendations || [];
  var anchor = (session.slots && session.slots.anchor) || "玩";
  var multi = anchor === "玩";
  var selectedRanks = {};

  // 回填上一次的锚点选择（从他页返回时不丢）
  (function backfill() {
    var prev = session.selected_anchor_pois || [];
    if (!prev.length && session.selected_anchor_poi) prev = [session.selected_anchor_poi];
    var prevIds = {};
    prev.forEach(function (p) {
      if (p && p.poi_id) prevIds[p.poi_id] = true;
    });
    picks.forEach(function (p) {
      if (prevIds[p.poi_id]) selectedRanks[p.rank] = true;
    });
  })();

  function showError(msg) {
    pageError.hidden = false;
    pageError.textContent = msg;
  }

  if (!session.slots || !session.slots.destination) {
    showError("请先在对话页完成资料收集。");
    btnNext.disabled = true;
  } else if (!picks.length) {
    showError("暂无锚点推荐，请返回对话页重新收束。");
    btnNext.disabled = true;
  } else {
    var typeLabel = S.POI_TYPE_LABEL[anchor] || anchor;
    pageTitle.textContent = "选择第一锚点 · " + typeLabel;
    pageSub.textContent = multi
      ? "以下均为必去项，会全部写进路书。可多选景点，至少选 1 个。"
      : "选定后将作为全程第一锚点，后续跟随与填充都围绕它展开。";

    function render() {
      grid.innerHTML = picks
        .map(function (pick) {
          return S.renderPoiCard(pick, { multi: multi, selected: !!selectedRanks[pick.rank] });
        })
        .join("");
    }

    function syncFooter() {
      var count = Object.keys(selectedRanks).length;
      footerHint.textContent = multi
        ? "已选 " + count + " 个" + typeLabel
        : count ? "已选定" : "请选择 1 项";
      btnNext.disabled = count < 1;
    }

    grid.addEventListener("click", function (e) {
      var card = e.target.closest(".poi-card");
      if (!card) return;
      var rank = Number(card.dataset.rank);
      if (multi) {
        if (selectedRanks[rank]) delete selectedRanks[rank];
        else selectedRanks[rank] = true;
      } else {
        selectedRanks = {};
        selectedRanks[rank] = true;
      }
      render();
      syncFooter();
    });

    render();
    syncFooter();
  }

  btnNext.addEventListener("click", function () {
    var chosen = picks.filter(function (p) {
      return selectedRanks[p.rank];
    });
    if (!chosen.length) return;
    session.travel_mode = session.travel_mode || ({
      ROUTE: "play_drive",
      FOOD: "food_drive",
      FILL: "stay_drive",
      EVENT: "route_light",
      BUDGET: "budget_drive",
    }[session.p1_mode] || "play_drive");
    session.selected_anchor_pois = chosen;
    session.selected_anchor_poi = chosen[0];
    // 锚点变化会让跟随/动线/交通全部失效，清空下游选择
    session.selected_follow_pois = [];
    session.transport_modes = {};
    session.transport_confirmed = false;
    S.saveSession(session);
    S.clearPlanCache();
    window.location.href = "p4.html";
  });
})();
