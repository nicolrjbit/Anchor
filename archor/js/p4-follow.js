(function () {
  var S = window.ArchorSession;
  var root = document.getElementById("follow-root");
  var btnNext = document.getElementById("btn-next");
  var footerHint = document.getElementById("footer-hint");
  var pageSub = document.getElementById("page-sub");
  var pageError = document.getElementById("page-error");

  var session = S.ensureP1Mode(S.loadSession() || {});
  var selectedByAnchor = {};

  // 回填上一次的跟随选择（从他页返回时不丢）
  (session.selected_follow_pois || []).forEach(function (pick) {
    if (pick && pick.anchor_poi_id) {
      selectedByAnchor[pick.anchor_poi_id] = pick;
    }
  });

  function showError(msg) {
    pageError.hidden = false;
    pageError.textContent = msg;
  }

  function syncFooter(groups) {
    var done = groups.every(function (g) {
      return selectedByAnchor[g.anchor_poi_id];
    });
    footerHint.textContent = done
      ? "已选齐 " + groups.length + " 组跟随"
      : "每个锚点请选 1 项";
    btnNext.disabled = !done;
  }

  function renderGroups(data) {
    var groups = data.groups || [];
    pageSub.textContent =
      "当前模式「" +
      (data.travel_mode_name || "") +
      "」，为你推荐顺路的" +
      (data.follow_label || "") +
      "。口语说就是：离锚点不太绕、综合分更高。";

    root.innerHTML = groups
      .map(function (group) {
        var cards = (group.picks || [])
          .map(function (pick) {
            var sel = selectedByAnchor[group.anchor_poi_id];
            var selected = sel && sel.poi_id === pick.poi_id;
            return S.renderPoiCard(pick, { multi: false, selected: selected });
          })
          .join("");
        return (
          '<section class="follow-group" data-anchor-id="' +
          S.escapeHtml(group.anchor_poi_id) +
          '">' +
          '<h2 class="follow-group__title">围绕「' +
          S.escapeHtml(group.anchor_name) +
          "」的" +
          S.escapeHtml(group.follow_label) +
          "推荐</h2>" +
          '<div class="poi-grid">' +
          cards +
          "</div></section>"
        );
      })
      .join("");

    root.onclick = function (e) {
      var card = e.target.closest(".poi-card");
      if (!card) return;
      var section = card.closest(".follow-group");
      if (!section) return;
      var anchorId = section.dataset.anchorId;
      var group = groups.find(function (g) {
        return g.anchor_poi_id === anchorId;
      });
      if (!group) return;
      var pick = (group.picks || []).find(function (p) {
        return String(p.rank) === String(card.dataset.rank);
      });
      if (!pick) return;
      // 记录所属锚点，便于回填与排期
      pick = Object.assign({}, pick, { anchor_poi_id: anchorId });
      selectedByAnchor[anchorId] = pick;
      renderGroups(data);
      syncFooter(groups);
    };

    syncFooter(groups);
  }

  if (!session.selected_anchor_pois || !session.selected_anchor_pois.length) {
    showError("请先在锚点页完成选择。");
    btnNext.disabled = true;
  } else {
    S.postJson("/api/wizard/follow", session)
      .then(renderGroups)
      .catch(function (err) {
        showError(err.message || "跟随推荐加载失败");
      });
  }

  btnNext.addEventListener("click", function () {
    var list = Object.keys(selectedByAnchor).map(function (k) {
      return selectedByAnchor[k];
    });
    session.selected_follow_pois = list;
    // 跟随变化会影响动线/酒店 → 失效旧路书与已确认的交通
    session.transport_modes = {};
    session.transport_confirmed = false;
    S.saveSession(session);
    S.clearPlanCache();
    window.location.href = "p5.html";
  });
})();
