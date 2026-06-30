(function () {
  var S = window.ArchorSession;
  var STORAGE_SESSION = S.STORAGE_SESSION;
  var STORAGE_PLAN = S.STORAGE_PLAN;
  var STORAGE_PLAN_KEY = S.STORAGE_PLAN_KEY;
  var API_BASE = S.API_BASE;

  var stage = document.getElementById("flipbook-stage");
  var book = document.getElementById("flipbook");
  var errBox = document.getElementById("p3-error");
  var indicator = document.getElementById("page-indicator");
  var genProgress = document.getElementById("gen-progress");
  var genStatus = document.getElementById("gen-status");
  var genEta = document.getElementById("gen-eta");
  var genBar = document.getElementById("gen-bar");
  var genSteps = document.getElementById("gen-steps");
  var exportRoot = document.getElementById("export-root");
  var exportToast = document.getElementById("export-toast");

  var plan = null;
  var spreadIndex = 0;
  var spreads = [];
  var progressTimer = null;
  var amapLoadPromise = null;
  var activeMap = null;
  var exportLibPromise = null;
  var exportToastTimer = null;

  var EXPORT_WIDTH = 860;
  var EXPORT_PDF_HEIGHT = 520;
  var HTML2CANVAS_SRC =
    "https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js";
  var JSPDF_SRC =
    "https://cdn.jsdelivr.net/npm/jspdf@2.5.2/dist/jspdf.umd.min.js";

  var PACE_TITLE = {
    normal: "顺路",
    relaxed: "松弛感轻调",
    compact: "紧凑高能",
  };

  var CITY_GRADIENT = {
    北京: "linear-gradient(135deg, #c4a882 0%, #8b7355 100%)",
    南京: "linear-gradient(135deg, #9eb4c8 0%, #5a7a96 100%)",
    重庆: "linear-gradient(135deg, #8fa8b8 0%, #4a6678 100%)",
    新疆: "linear-gradient(135deg, #d4b896 0%, #a08060 100%)",
  };

  var PROGRESS_STEPS = [
    { id: "anchor", label: "锁定第一锚点" },
    { id: "follow", label: "写入跟随推荐" },
    { id: "fill", label: "锚点周边 1.5km 高分填充" },
    { id: "route", label: "编排动线与交通" },
    { id: "diag", label: "AI 行程诊断" },
    { id: "render", label: "合成路书" },
  ];

  function loadJson(key) {
    try {
      var raw = sessionStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  var planCacheKey = S.planCacheKey;

  function saveSession(session) {
    S.saveSession(session);
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function companionCapsule(tags) {
    var joined = (tags || []).join(" ");
    if (/情侣|朋友/.test(joined)) return "双人出行";
    if (/亲子|带娃/.test(joined)) return "家庭出行";
    if (/长辈|爸妈/.test(joined)) return "陪长辈出行";
    if (/独自|单身/.test(joined)) return "独自出行";
    return "结伴出行";
  }

  function buildShellFromSession(session) {
    var slots = session.slots || {};
    var tags = slots.tags || [];
    var profile = tags[0] || "旅行者";
    var days = slots.days || 3;
    var dest = slots.destination || "重庆";
    var pace = session.pace_modifier || "normal";
    var fatigue = ((session.conflict_detail || {}).fatigue_score) || 28;
    var title = dest + days + "日游";
    var coverTags = tags.slice(0, 2);
    coverTags.push(companionCapsule(tags));

    return {
      shell: true,
      cover: {
        title: title,
        hero_gradient: CITY_GRADIENT[dest] || CITY_GRADIENT["重庆"],
        hero_image: null,
        destination: dest,
        days: days,
        tags: coverTags.filter(Boolean).slice(0, 3),
        total_fatigue_score: fatigue,
        total_commute_km: null,
      },
      days: Array.from({ length: days }, function (_, i) {
        return { day_index: i + 1, timeline: [], route: [], pros: [], cons: [], ready: false };
      }),
      back: {
        pdf_label: "下载 PDF 路书",
        share_label: "生成长图分享",
      },
      eta_seconds: Math.max(2, Math.min(6, 1 + days)),
    };
  }

  function renderSkeletonTimeline() {
    return (
      '<ul class="timeline timeline--skeleton">' +
      [1, 2, 3, 4, 5]
        .map(function () {
          return (
            '<li class="timeline__item">' +
            '<div class="skeleton skeleton--line short"></div>' +
            '<div class="skeleton skeleton--line long"></div>' +
            '<div class="skeleton skeleton--line mid"></div>' +
            "</li>"
          );
        })
        .join("") +
      "</ul>"
    );
  }

  function renderSkeletonDiagnosis() {
    return (
      '<div class="diagnosis diagnosis--skeleton">' +
      '<div class="skeleton skeleton--diag"></div>' +
      '<div class="skeleton skeleton--diag"></div>' +
      "</div>"
    );
  }

  function buildRouteSvg(route) {
    if (!route || route.length < 1) {
      return '<div class="skeleton skeleton--map map-panel__skeleton"></div>';
    }
    var lngs = route.map(function (p) {
      return p.lng;
    });
    var lats = route.map(function (p) {
      return p.lat;
    });
    var minLng = Math.min.apply(null, lngs) - 0.008;
    var maxLng = Math.max.apply(null, lngs) + 0.008;
    var minLat = Math.min.apply(null, lats) - 0.008;
    var maxLat = Math.max.apply(null, lats) + 0.008;

    function proj(lng, lat) {
      return {
        x: ((lng - minLng) / (maxLng - minLng || 1)) * 360 + 20,
        y: 200 - ((lat - minLat) / (maxLat - minLat || 1)) * 170,
      };
    }

    var points = route
      .map(function (p) {
        var c = proj(p.lng, p.lat);
        return c.x + "," + c.y;
      })
      .join(" ");

    var dots = route
      .map(function (p) {
        var c = proj(p.lng, p.lat);
        var fill = p.type === "吃" ? "#b45a28" : p.type === "住" ? "#4a6fa5" : "#014421";
        return (
          '<circle cx="' +
          c.x +
          '" cy="' +
          c.y +
          '" r="5" fill="' +
          fill +
          '" stroke="#fff" stroke-width="1.5"/>'
        );
      })
      .join("");

    return (
      '<svg viewBox="0 0 400 220" preserveAspectRatio="xMidYMid slice">' +
      '<rect fill="#e8e4dc" width="400" height="220"/>' +
      '<polyline points="' +
      points +
      '" fill="none" stroke="#014421" stroke-width="2.5" stroke-dasharray="6 4"/>' +
      dots +
      "</svg>"
    );
  }

  function buildRouteMapPanel(dayIndex, shellMode, ready, route, exportMode) {
    if (exportMode && route && route.length) {
      return (
        '<div class="map-panel">' +
        '<span class="map-panel__label">路线地图 · Day ' +
        dayIndex +
        " 动线</span>" +
        buildRouteSvg(route) +
        "</div>"
      );
    }
    if (shellMode || !ready) {
      return (
        '<div class="map-panel map-panel--loading">' +
        '<span class="map-panel__label">路线地图</span>' +
        '<div class="skeleton skeleton--map"></div></div>'
      );
    }
    return (
      '<div class="map-panel">' +
      '<span class="map-panel__label">高德地图 · Day ' +
      dayIndex +
      " 动线</span>" +
      '<div class="amap-host" id="amap-day-' +
      dayIndex +
      '" role="application" aria-label="Day ' +
      dayIndex +
      ' 路线地图"></div>' +
      '<div class="map-panel__svg-fallback" id="map-svg-day-' +
      dayIndex +
      '" hidden></div></div>'
    );
  }

  function destroyActiveMap() {
    if (activeMap) {
      try {
        activeMap.destroy();
      } catch (e) {}
      activeMap = null;
    }
  }

  function ensureAmapLoaded() {
    if (typeof AMap !== "undefined") return Promise.resolve();
    if (!window.AmapApp || !window.AmapApp.isConfigured()) {
      return Promise.reject(new Error("AMAP_NOT_CONFIGURED"));
    }
    if (!amapLoadPromise) {
      amapLoadPromise = window.AmapApp.loadAmap([]);
    }
    return amapLoadPromise;
  }

  function showSvgFallback(dayIndex, route) {
    var host = document.getElementById("amap-day-" + dayIndex);
    var fallback = document.getElementById("map-svg-day-" + dayIndex);
    if (host) host.hidden = true;
    if (fallback) {
      fallback.hidden = false;
      fallback.innerHTML = buildRouteSvg(route);
    }
  }

  function markerLabelHtml(index, type) {
    var color = type === "吃" ? "#b45a28" : type === "住" ? "#4a6fa5" : "#014421";
    return (
      '<span class="amap-marker-label" style="border-color:' +
      color +
      ";color:" +
      color +
      '">' +
      (index + 1) +
      "</span>"
    );
  }

  function mountDayMap(dayIndex, route) {
    var spreadId = "day-" + dayIndex;
    var containerId = "amap-day-" + dayIndex;
    if (!route || !route.length || !document.getElementById(containerId)) return;

    destroyActiveMap();

    ensureAmapLoaded()
      .then(function () {
        var current = spreads[spreadIndex];
        if (!current || current.id !== spreadId) return;
        if (!document.getElementById(containerId)) return;

        activeMap = new AMap.Map(containerId, {
          zoom: 13,
          viewMode: "2D",
        });

        var markers = [];
        var path = [];
        route.forEach(function (point, i) {
          if (point.lng == null || point.lat == null) return;
          var pos = [point.lng, point.lat];
          path.push(pos);
          markers.push(
            new AMap.Marker({
              position: pos,
              map: activeMap,
              label: {
                content: markerLabelHtml(i, point.type),
                direction: "right",
                offset: new AMap.Pixel(6, -6),
              },
            })
          );
        });

        var overlays = markers.slice();
        if (path.length >= 2) {
          overlays.push(
            new AMap.Polyline({
              path: path,
              strokeColor: "#014421",
              strokeWeight: 4,
              strokeOpacity: 0.82,
              strokeStyle: "dashed",
              map: activeMap,
            })
          );
        }

        if (overlays.length) {
          activeMap.setFitView(overlays, false, [28, 28, 28, 28]);
        }
      })
      .catch(function () {
        var current = spreads[spreadIndex];
        if (!current || current.id !== spreadId) return;
        showSvgFallback(dayIndex, route);
      });
  }

  function renderDiagnosis(pros, cons) {
    var html = "";
    (pros || []).slice(0, 1).forEach(function (p) {
      html +=
        '<div class="diagnosis__block diagnosis__block--pro">' +
        escapeHtml(p.standard_text || p) +
        "</div>";
    });
    (cons || []).slice(0, 1).forEach(function (c) {
      html +=
        '<div class="diagnosis__block diagnosis__block--con">' +
        escapeHtml(c.standard_text || c) +
        (c.preset_tip ? " " + escapeHtml(c.preset_tip) : "") +
        "</div>";
    });
    return (
      html ||
      '<div class="diagnosis__block diagnosis__block--pro">动线已按锚点收束，今日节奏可控。</div>'
    );
  }

  function renderTimeline(items) {
    return (items || [])
      .map(function (node) {
        return (
          '<li class="timeline__item">' +
          '<span class="timeline__dot"></span>' +
          '<span class="timeline__time">' +
          escapeHtml(node.time) +
          '</span><span class="timeline__type">' +
          escapeHtml(node.type) +
          "</span>" +
          '<p class="timeline__name">' +
          escapeHtml(node.name) +
          "</p>" +
          '<p class="timeline__detail">' +
          escapeHtml(node.detail) +
          "</p></li>"
        );
      })
      .join("");
  }

  function coverHeroStyle(cover) {
    if (cover.hero_image) {
      return (
        "background-image:url(" +
        encodeURI(cover.hero_image) +
        ");background-size:cover;background-position:center;"
      );
    }
    if (cover.hero_gradient) {
      return "background:" + cover.hero_gradient;
    }
    return "background:linear-gradient(135deg, #8fa8b8, #4a6678)";
  }

  function renderCover(cover, pendingKm) {
    var kmVal = pendingKm
      ? '<span class="metric__value is-pending">计算中</span>'
      : '<span class="metric__value">' +
        (cover.total_commute_km != null ? cover.total_commute_km : "—") +
        '<span class="metric__unit"> km</span></span>';

    return (
      '<div class="spread spread--cover">' +
      '<div class="page cover">' +
      '<div class="cover__hero" style="' +
      coverHeroStyle(cover) +
      '"></div>' +
      '<div class="cover__panel">' +
      '<div class="cover__eyebrow">Anchor 定制路书 · 扉页</div>' +
      '<h1 class="cover__title">' +
      escapeHtml(cover.title) +
      "</h1>" +
      '<div class="cover__metrics">' +
      '<div class="metric"><span class="metric__label">总劳累度评分</span>' +
      '<span class="metric__value">' +
      cover.total_fatigue_score +
      '<span class="metric__unit"> 分</span></span></div>' +
      '<div class="metric"><span class="metric__label">总通勤公里数</span>' +
      kmVal +
      "</div></div></div></div></div>"
    );
  }

  function syncFlipControls(index) {
    if (indicator && spreads[index]) {
      indicator.textContent = spreads[index].label + " · " + (index + 1) + "/" + spreads.length;
    }
  }

  function dismissProgress() {
    if (!genProgress) return;
    genProgress.classList.add("is-done");
    window.setTimeout(function () {
      genProgress.hidden = true;
    }, 400);
  }

  function buildSpreads(data, shellMode, exportMode) {
    exportMode = !!exportMode;
    var list = [];
    var cover = data.cover;
    var pendingKm = shellMode || cover.total_commute_km == null;

    list.push({ id: "cover", label: "封面", html: renderCover(cover, pendingKm) });

    (data.days || []).forEach(function (day) {
      var left = shellMode || !day.ready
        ? renderSkeletonTimeline()
        : '<ul class="timeline">' + renderTimeline(day.timeline) + "</ul>";
      var mapBlock = buildRouteMapPanel(
        day.day_index,
        shellMode,
        day.ready,
        day.route || [],
        exportMode
      );
      var diagBlock = shellMode || !day.ready
        ? renderSkeletonDiagnosis()
        : '<div class="diagnosis"><h3 class="diagnosis__title">AI 行程诊断</h3>' +
          renderDiagnosis(day.pros, day.cons) +
          "</div>";

      list.push({
        id: "day-" + day.day_index,
        label: "Day " + day.day_index,
        mapDayIndex: day.day_index,
        mapReady: !shellMode && !!day.ready,
        route: day.route || [],
        html:
          '<div class="spread">' +
          '<div class="page page--left"><div class="page__inner">' +
          '<div class="day-head">' +
          '<div class="day-head__label">Day ' +
          day.day_index +
          " · 深度解构</div>" +
          '<h2 class="day-head__title">动线与能耗</h2></div>' +
          left +
          "</div></div>" +
          '<div class="page page--right"><div class="page__inner">' +
          mapBlock +
          diagBlock +
          "</div></div></div>",
      });
    });

    var backActions = exportMode
      ? '<p class="back-cover__export-note">Anchor 定制路书 · 保存后可分享给同行伙伴</p>'
      : '<div class="back-cover__actions">' +
        '<button type="button" class="btn-roadbook btn-roadbook--primary" id="btn-pdf">' +
        escapeHtml(data.back.pdf_label) +
        "</button>" +
        '<button type="button" class="btn-roadbook btn-roadbook--ghost" id="btn-share">' +
        escapeHtml(data.back.share_label) +
        "</button></div>";

    list.push({
      id: "back",
      label: "封底",
      html:
        '<div class="spread spread--back">' +
        '<div class="page back-cover">' +
        '<h2 class="back-cover__title">路书已就绪</h2>' +
        '<p class="back-cover__sub">保存这份行程，随时分享给同行伙伴</p>' +
        backActions +
        "</div></div>",
    });

    return list;
  }

  function showExportToast(message, isError) {
    if (!exportToast) return;
    exportToast.textContent = message;
    exportToast.classList.toggle("export-toast--error", !!isError);
    exportToast.hidden = false;
    if (exportToastTimer) clearTimeout(exportToastTimer);
    exportToastTimer = window.setTimeout(function () {
      exportToast.hidden = true;
    }, isError ? 4200 : 2600);
  }

  function loadScriptOnce(src, globalCheck) {
    if (globalCheck()) return Promise.resolve();
    var existing = document.querySelector('script[data-export-lib="' + src + '"]');
    if (existing) {
      return new Promise(function (resolve, reject) {
        existing.addEventListener("load", function () {
          resolve();
        });
        existing.addEventListener("error", reject);
      });
    }
    return new Promise(function (resolve, reject) {
      var script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.dataset.exportLib = src;
      script.onload = resolve;
      script.onerror = function () {
        reject(new Error("EXPORT_LIB_LOAD_FAILED"));
      };
      document.head.appendChild(script);
    });
  }

  function ensureExportLibs() {
    if (!exportLibPromise) {
      exportLibPromise = Promise.all([
        loadScriptOnce(HTML2CANVAS_SRC, function () {
          return typeof html2canvas !== "undefined";
        }),
        loadScriptOnce(JSPDF_SRC, function () {
          return typeof window.jspdf !== "undefined";
        }),
      ]);
    }
    return exportLibPromise;
  }

  function exportFilename(ext) {
    var title = (plan && plan.cover && plan.cover.title) || "Anchor路书";
    var safe = title.replace(/[\\/:*?"<>|]/g, "").replace(/\s+/g, "");
    return (safe || "Anchor路书") + "." + ext;
  }

  function planReadyForExport() {
    return !!(plan && !plan.shell && (plan.days || []).some(function (d) {
      return d.ready;
    }));
  }

  function waitForFonts() {
    if (document.fonts && document.fonts.ready) {
      return document.fonts.ready.catch(function () {});
    }
    return Promise.resolve();
  }

  function buildExportSpreads() {
    return buildSpreads(plan, false, true);
  }

  function mountExportSheet(html) {
    if (!exportRoot) throw new Error("EXPORT_ROOT_MISSING");
    var sheet = document.createElement("div");
    sheet.className = "export-sheet";
    sheet.style.width = EXPORT_WIDTH + "px";
    sheet.innerHTML = html;
    exportRoot.innerHTML = "";
    exportRoot.appendChild(sheet);
    return sheet;
  }

  function clearExportRoot() {
    if (exportRoot) exportRoot.innerHTML = "";
  }

  function captureElementCanvas(element) {
    return html2canvas(element, {
      scale: 2,
      useCORS: true,
      allowTaint: true,
      backgroundColor: "#f3ede3",
      logging: false,
      width: EXPORT_WIDTH,
      windowWidth: EXPORT_WIDTH,
      scrollX: 0,
      scrollY: 0,
    });
  }

  function canvasToBlob(canvas, type, quality) {
    return new Promise(function (resolve, reject) {
      if (!canvas.toBlob) {
        reject(new Error("BLOB_UNSUPPORTED"));
        return;
      }
      canvas.toBlob(
        function (blob) {
          if (!blob) reject(new Error("BLOB_EMPTY"));
          else resolve(blob);
        },
        type,
        quality
      );
    });
  }

  function triggerDownload(blob, filename) {
    var url = URL.createObjectURL(blob);
    var link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.rel = "noopener";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1200);
  }

  function setExportButtonBusy(btn, busy, busyText) {
    if (!btn) return;
    if (!btn.dataset.defaultLabel) {
      btn.dataset.defaultLabel = btn.textContent;
    }
    btn.disabled = busy || !planReadyForExport();
    btn.classList.toggle("is-busy", busy);
    btn.textContent = busy ? busyText : btn.dataset.defaultLabel;
  }

  async function captureSpreadCanvas(spread) {
    var sheet = mountExportSheet(spread.html);
    await waitForFonts();
    await new Promise(function (resolve) {
      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(resolve);
      });
    });
    return captureElementCanvas(sheet);
  }

  async function downloadPdfRoadbook(btn) {
    if (!planReadyForExport()) {
      showExportToast("路书还在生成中，请稍候再下载", true);
      return;
    }
    setExportButtonBusy(btn, true, "正在生成 PDF…");
    showExportToast("正在排版 PDF，请稍候…");
    try {
      await ensureExportLibs();
      var exportSpreads = buildExportSpreads();
      var jsPDF = window.jspdf.jsPDF;
      var pdf = new jsPDF({
        orientation: "landscape",
        unit: "px",
        format: [EXPORT_WIDTH, EXPORT_PDF_HEIGHT],
        compress: true,
      });

      for (var i = 0; i < exportSpreads.length; i++) {
        if (i > 0) pdf.addPage([EXPORT_WIDTH, EXPORT_PDF_HEIGHT], "landscape");
        var canvas = await captureSpreadCanvas(exportSpreads[i]);
        var imgData = canvas.toDataURL("image/jpeg", 0.92);
        pdf.addImage(imgData, "JPEG", 0, 0, EXPORT_WIDTH, EXPORT_PDF_HEIGHT, undefined, "FAST");
      }

      pdf.save(exportFilename("pdf"));
      showExportToast("PDF 已下载");
    } catch (err) {
      showExportToast("PDF 生成失败，请检查网络后重试", true);
    } finally {
      clearExportRoot();
      setExportButtonBusy(btn, false);
    }
  }

  async function downloadLongImageShare(btn) {
    if (!planReadyForExport()) {
      showExportToast("路书还在生成中，请稍候再分享", true);
      return;
    }
    setExportButtonBusy(btn, true, "正在生成长图…");
    showExportToast("正在拼接全行程长图…");
    try {
      await ensureExportLibs();
      var exportSpreads = buildExportSpreads();
      if (!exportRoot) throw new Error("EXPORT_ROOT_MISSING");

      var stack = document.createElement("div");
      stack.className = "export-long-stack";
      stack.style.width = EXPORT_WIDTH + "px";
      exportSpreads.forEach(function (spread) {
        var sheet = document.createElement("div");
        sheet.className = "export-sheet export-sheet--stacked";
        sheet.style.width = EXPORT_WIDTH + "px";
        sheet.innerHTML = spread.html;
        stack.appendChild(sheet);
      });
      exportRoot.innerHTML = "";
      exportRoot.appendChild(stack);

      await waitForFonts();
      await new Promise(function (resolve) {
        window.requestAnimationFrame(function () {
          window.requestAnimationFrame(resolve);
        });
      });

      var canvas = await html2canvas(stack, {
        scale: 2,
        useCORS: true,
        allowTaint: true,
        backgroundColor: "#ebe4d8",
        logging: false,
        width: EXPORT_WIDTH,
        windowWidth: EXPORT_WIDTH,
        height: stack.scrollHeight,
        windowHeight: stack.scrollHeight,
        scrollX: 0,
        scrollY: 0,
      });

      var blob = await canvasToBlob(canvas, "image/png");
      var filename = exportFilename("png");
      var file = new File([blob], filename, { type: "image/png" });

      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        await navigator.share({
          title: (plan && plan.cover && plan.cover.title) || "路书长图",
          text: "我的 Anchor 定制路书",
          files: [file],
        });
        showExportToast("长图已唤起系统分享");
      } else {
        triggerDownload(blob, filename);
        showExportToast("长图已保存到本机");
      }
    } catch (err) {
      if (err && err.name === "AbortError") {
        showExportToast("已取消分享");
      } else {
        showExportToast("长图生成失败，请检查网络后重试", true);
      }
    } finally {
      clearExportRoot();
      setExportButtonBusy(btn, false);
    }
  }

  function bindBackCoverActions() {
    var pdfBtn = document.getElementById("btn-pdf");
    var shareBtn = document.getElementById("btn-share");
    var ready = planReadyForExport();

    if (pdfBtn) {
      pdfBtn.disabled = !ready;
      pdfBtn.onclick = function () {
        downloadPdfRoadbook(pdfBtn);
      };
    }
    if (shareBtn) {
      shareBtn.disabled = !ready;
      shareBtn.onclick = function () {
        downloadLongImageShare(shareBtn);
      };
    }
  }

  function renderSpread(index) {
    if (!spreads[index]) return;
    destroyActiveMap();
    book.innerHTML = spreads[index].html;
    syncFlipControls(index);

    var spread = spreads[index];
    if (spread.mapReady && spread.route && spread.route.length) {
      window.setTimeout(function () {
        mountDayMap(spread.mapDayIndex, spread.route);
      }, 80);
    }

    if (spread.id === "back") {
      bindBackCoverActions();
    }
  }

  function flipTo(index) {
    if (index < 0 || index >= spreads.length || index === spreadIndex) return;
    book.classList.add("is-turning");
    setTimeout(function () {
      spreadIndex = index;
      renderSpread(spreadIndex);
      book.classList.remove("is-turning");
    }, 280);
  }

  function initProgressSteps() {
    genSteps.innerHTML = PROGRESS_STEPS.map(function (s) {
      return '<li data-step="' + s.id + '">' + s.label + "</li>";
    }).join("");
  }

  function setProgressStep(stepId, state) {
    var el = genSteps.querySelector('[data-step="' + stepId + '"]');
    if (!el) return;
    el.classList.remove("is-active", "is-done");
    if (state) el.classList.add(state);
  }

  function setProgress(pct, statusText, etaSec) {
    genBar.style.width = Math.min(100, Math.max(0, pct)) + "%";
    genBar.parentElement.setAttribute("aria-valuenow", String(Math.round(pct)));
    if (statusText) genStatus.textContent = statusText;
    if (etaSec != null) {
      if (etaSec <= 0) genEta.textContent = "即将完成";
      else genEta.textContent = "预计还需 " + Math.ceil(etaSec) + " 秒";
    }
  }

  function startProgressSimulation(etaSeconds) {
    var start = Date.now();
    var duration = (etaSeconds || 3) * 1000;
    setProgressStep("anchor", "is-done");
    setProgressStep("follow", "is-active");
    setProgress(12, "锁定锚点与跟随项…", etaSeconds);

    if (progressTimer) clearInterval(progressTimer);
    progressTimer = setInterval(function () {
      var elapsed = Date.now() - start;
      var ratio = Math.min(0.85, elapsed / duration);
      var pct = 12 + ratio * 100 * 0.7;
      var remain = Math.max(0, (duration - elapsed) / 1000);
      if (ratio > 0.15) setProgressStep("follow", "is-done");
      if (ratio > 0.3) setProgressStep("fill", "is-active");
      if (ratio > 0.45) {
        setProgressStep("fill", "is-done");
        setProgressStep("route", "is-active");
      }
      if (ratio > 0.6) {
        setProgressStep("route", "is-done");
        setProgressStep("diag", "is-active");
      }
      setProgress(pct, "填充周边 POI、编排动线…", remain);
    }, 120);
  }

  function finishProgress(generationMs, buildSteps) {
    if (progressTimer) {
      clearInterval(progressTimer);
      progressTimer = null;
    }
    (buildSteps || PROGRESS_STEPS).forEach(function (s) {
      setProgressStep(s.id, "is-done");
    });
    setProgress(100, "路书已生成" + (generationMs ? " · " + generationMs + "ms" : ""), 0);
    dismissProgress();
  }

  function bootPlanPipeline(session) {
    var cacheKey = planCacheKey(session);
    var cached = loadJson(STORAGE_PLAN);
    if (
      cached &&
      !cached.shell &&
      sessionStorage.getItem(STORAGE_PLAN_KEY) === cacheKey
    ) {
      boot(cached, false);
      dismissProgress();
      ensureAmapLoaded().catch(function () {});
      return;
    }

    var shell = buildShellFromSession(session);
    boot(shell, true);
    if (genProgress) genProgress.hidden = false;
    startProgressSimulation(shell.eta_seconds);
    ensureAmapLoaded().catch(function () {});

    fetchPlan(session, 12000)
      .then(function (data) {
        try {
          sessionStorage.setItem(STORAGE_PLAN_KEY, cacheKey);
        } catch (e) {}
        hydrateFullPlan(data.plan, data.generation_ms, data.build_steps);
      })
      .catch(function (err) {
        showError(err.message || "路书生成失败");
      });
  }

  var fetchPlan = S.fetchPlan;

  function boot(data, shellMode) {
    plan = data;
    spreads = buildSpreads(plan, shellMode);
    renderSpread(spreadIndex);
    if (genProgress) genProgress.hidden = false;
    if (plan.cover && plan.cover.hero_image) {
      var img = new Image();
      img.onload = function () {
        spreads = buildSpreads(plan, false);
        if (spreadIndex === 0) renderSpread(0);
      };
      img.src = plan.cover.hero_image;
    }
  }

  function hydrateFullPlan(fullPlan, generationMs, buildSteps) {
    plan = fullPlan;
    try {
      sessionStorage.setItem(STORAGE_PLAN, JSON.stringify(fullPlan));
    } catch (e) {}
    spreads = buildSpreads(plan, false);
    renderSpread(spreadIndex);
    finishProgress(generationMs, buildSteps || fullPlan.build_steps);
  }

  function showError(msg) {
    if (progressTimer) clearInterval(progressTimer);
    dismissProgress();
    errBox.hidden = false;
    errBox.innerHTML =
      "<p>" + escapeHtml(msg) + '</p><a href="p2.html">返回对话页</a>';
  }

  function init() {
    try {
      initProgressSteps();
      setProgress(8, "正在读取行程信息…", 3);

      var session = loadJson(STORAGE_SESSION);
      if (!session || !session.slots || !session.slots.destination) {
        showError("尚未收到完整行程信息，请先在对话页完成资料收集。");
        return;
      }
      if (!session.selected_anchor_pois || !session.selected_anchor_pois.length) {
        showError("请先在锚点页（第 3 页）完成选择。");
        errBox.innerHTML += ' <a href="p3.html">前往锚点页</a>';
        return;
      }
      if (!session.selected_follow_pois || !session.selected_follow_pois.length) {
        showError("请先在跟随页（第 4 页）完成选择。");
        errBox.innerHTML += ' <a href="p4.html">前往跟随页</a>';
        return;
      }
      if (!session.transport_confirmed) {
        showError("请先在出行方式页（第 5 页）确认各路段。");
        errBox.innerHTML += ' <a href="p5.html">前往出行方式页</a>';
        return;
      }

      var cacheKey = planCacheKey(session);
      var cached = loadJson(STORAGE_PLAN);
      if (
        cached &&
        !cached.shell &&
        sessionStorage.getItem(STORAGE_PLAN_KEY) === cacheKey
      ) {
        boot(cached, false);
        dismissProgress();
        ensureAmapLoaded().catch(function () {});
        return;
      }

      bootPlanPipeline(session);
    } catch (err) {
      showError("页面初始化失败：" + (err && err.message ? err.message : "未知错误"));
    }
  }

  if (stage) {
    stage.addEventListener("click", function (e) {
      if (e.target.closest("button, a, input, textarea")) return;
      var rect = book.getBoundingClientRect();
      if (!rect.width) return;
      var x = e.clientX - rect.left;
      if (x > rect.width * 0.55) flipTo(spreadIndex + 1);
      else if (x < rect.width * 0.45) flipTo(spreadIndex - 1);
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "ArrowRight") flipTo(spreadIndex + 1);
    if (e.key === "ArrowLeft") flipTo(spreadIndex - 1);
  });

  init();
})();
