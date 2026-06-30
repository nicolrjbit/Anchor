(function (global) {
  var STORAGE_SESSION = "archorSession";
  var STORAGE_PLAN = "archorPlan";
  var STORAGE_PLAN_KEY = "archorPlanKey";
  var STORAGE_MODE = "archorMode";
  var STORAGE_MESSAGES = "archorMessages";
  var STORAGE_SCHEMA = "archorSchema";

  // 路书 JSON / 流程结构变更时递增（需与后端 PLAN_CONTENT_VERSION 对齐）
  var PLAN_CONTENT_VERSION = "wizard-v5";
  // 前端 session/缓存结构版本：不一致时自动清空旧 session，免去手动清缓存
  var SCHEMA_VERSION = "flow-3";

  var API_BASE = (function () {
    var protocol = window.location.protocol;
    var hostname = window.location.hostname;
    var port = window.location.port;
    if (protocol === "file:") return "http://127.0.0.1:8000";
    if (port === "8000") return "";
    if (!hostname || hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]") {
      return "http://127.0.0.1:8000";
    }
    return "";
  })();

  var POI_TYPE_LABEL = { 玩: "景点", 住: "酒店", 吃: "餐厅" };

  // schema 版本不一致 → 清掉所有旧的会话/计划/消息，避免跨版本脏数据
  function resetStaleSession() {
    try {
      if (sessionStorage.getItem(STORAGE_SCHEMA) === SCHEMA_VERSION) return;
      [STORAGE_SESSION, STORAGE_PLAN, STORAGE_PLAN_KEY, STORAGE_MESSAGES].forEach(function (k) {
        sessionStorage.removeItem(k);
      });
      sessionStorage.setItem(STORAGE_SCHEMA, SCHEMA_VERSION);
    } catch (e) {}
  }

  function loadSession() {
    try {
      var raw = sessionStorage.getItem(STORAGE_SESSION);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function saveSession(session) {
    try {
      sessionStorage.setItem(STORAGE_SESSION, JSON.stringify(session));
    } catch (e) {}
  }

  function clearPlanCache() {
    try {
      sessionStorage.removeItem(STORAGE_PLAN);
      sessionStorage.removeItem(STORAGE_PLAN_KEY);
    } catch (e) {}
  }

  function ensureP1Mode(session) {
    if (!session.p1_mode) {
      session.p1_mode = sessionStorage.getItem(STORAGE_MODE) || "ROUTE";
    }
    return session;
  }

  function selectedPoiCacheSig(session) {
    var list = session.selected_anchor_pois || [];
    if (!list.length && session.selected_anchor_poi) list = [session.selected_anchor_poi];
    return list
      .map(function (p) {
        return p.poi_id || p.name || "";
      })
      .filter(Boolean)
      .sort()
      .join(",");
  }

  function effectiveTransportPreferences(session) {
    if (!session) return [];
    if (session.transport_preferences && session.transport_preferences.length) {
      return session.transport_preferences;
    }
    var slots = session.slots || {};
    return slots.transport_preferences || [];
  }

  function transportPreferenceLabel(prefs) {
    if (!prefs || !prefs.length) return "";
    if (prefs.length === 1 && prefs[0] === "自驾") return "自驾/租车";
    if (prefs.indexOf("地铁") >= 0 && prefs.indexOf("步行") >= 0) return "地铁加步行";
    return prefs.join("、");
  }

  function syncTransportPreferences(session) {
    var prefs = effectiveTransportPreferences(session);
    if (prefs.length) {
      session.transport_preferences = prefs;
      var slots = session.slots || {};
      if (!slots.transport_preferences || !slots.transport_preferences.length) {
        slots.transport_preferences = prefs;
        session.slots = slots;
      }
    }
    return session;
  }

  function planCacheKey(session) {
    if (!session || !session.slots) return "";
    var s = session.slots || {};
    var modes = session.transport_modes || {};
    var modeSig = Object.keys(modes)
      .sort()
      .map(function (k) {
        return k + ":" + modes[k];
      })
      .join(",");
    var follow = (session.selected_follow_pois || [])
      .map(function (p) {
        return p.poi_id || "";
      })
      .filter(Boolean)
      .sort()
      .join(",");
    return [
      PLAN_CONTENT_VERSION,
      session.travel_mode || session.p1_mode || "",
      s.destination || "",
      s.days || "",
      s.anchor || "",
      (s.tags || []).join(","),
      session.pace_modifier || "normal",
      ((session.conflict_detail || {}).fatigue_score || ""),
      selectedPoiCacheSig(session),
      follow,
      (effectiveTransportPreferences(session) || []).join(","),
      modeSig,
    ].join("|");
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function pickSketchUrl(pick) {
    return (
      pick.sketch_image ||
      (pick.extra && pick.extra.sketch_image) ||
      "/archor/images/sketches/" + (pick.poi_id || "") + ".svg"
    );
  }

  function renderPoiCard(pick, options) {
    options = options || {};
    var multi = !!options.multi;
    var selected = !!options.selected;
    var sketch = pickSketchUrl(pick);
    var intro = pick.intro || pick.reason || "";
    return (
      '<button type="button" class="poi-card' +
      (selected ? " poi-card--selected" : "") +
      '" data-rank="' +
      pick.rank +
      '" data-poi-id="' +
      escapeHtml(pick.poi_id || "") +
      '">' +
      (multi ? '<span class="poi-card__check">' + (selected ? "✓" : "") + "</span>" : "") +
      '<div class="poi-card__thumb"><img src="' +
      escapeHtml(sketch) +
      '" alt="" loading="lazy"/></div>' +
      '<div class="poi-card__body">' +
      '<span class="poi-card__rank">推荐 ' +
      pick.rank +
      "</span>" +
      '<h3 class="poi-card__name">' +
      escapeHtml(pick.name) +
      "</h3>" +
      '<p class="poi-card__meta">评分 ' +
      (pick.rating != null ? Number(pick.rating).toFixed(1) : "—") +
      (pick.visit_time ? " · " + escapeHtml(pick.visit_time) : "") +
      "</p>" +
      '<p class="poi-card__intro">' +
      escapeHtml(intro) +
      "</p></div></button>"
    );
  }

  function postJson(path, session) {
    return fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: session }),
    }).then(function (res) {
      if (!res.ok) {
        return res.json().then(function (d) {
          throw new Error(d.detail || "请求失败");
        });
      }
      return res.json();
    });
  }

  // 拉取路书：带超时与友好错误，供出行方式页 / 路书页共用
  function fetchPlan(session, timeoutMs) {
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, timeoutMs || 12000);

    return fetch(API_BASE + "/api/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session: session }),
      signal: controller.signal,
    })
      .then(function (res) {
        clearTimeout(timer);
        if (!res.ok) {
          return res.json().then(function (d) {
            throw new Error(d.detail || "路书生成失败");
          });
        }
        return res.json();
      })
      .catch(function (err) {
        clearTimeout(timer);
        if (err.name === "AbortError") {
          throw new Error("生成超时，请确认后端已在 8000 端口运行后重试");
        }
        if (err instanceof TypeError) {
          throw new Error("无法连接后端，请确认服务已在 8000 端口启动");
        }
        throw err;
      });
  }

  global.ArchorSession = {
    STORAGE_SESSION: STORAGE_SESSION,
    STORAGE_PLAN: STORAGE_PLAN,
    STORAGE_PLAN_KEY: STORAGE_PLAN_KEY,
    STORAGE_MODE: STORAGE_MODE,
    STORAGE_MESSAGES: STORAGE_MESSAGES,
    PLAN_CONTENT_VERSION: PLAN_CONTENT_VERSION,
    SCHEMA_VERSION: SCHEMA_VERSION,
    API_BASE: API_BASE,
    POI_TYPE_LABEL: POI_TYPE_LABEL,
    resetStaleSession: resetStaleSession,
    loadSession: loadSession,
    saveSession: saveSession,
    clearPlanCache: clearPlanCache,
    ensureP1Mode: ensureP1Mode,
    effectiveTransportPreferences: effectiveTransportPreferences,
    transportPreferenceLabel: transportPreferenceLabel,
    syncTransportPreferences: syncTransportPreferences,
    planCacheKey: planCacheKey,
    selectedPoiCacheSig: selectedPoiCacheSig,
    escapeHtml: escapeHtml,
    pickSketchUrl: pickSketchUrl,
    renderPoiCard: renderPoiCard,
    postJson: postJson,
    fetchPlan: fetchPlan,
  };

  // 加载即校验：跨版本时自动清旧 session（schema 一致则无副作用）
  resetStaleSession();
})(window);
