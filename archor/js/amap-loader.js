/**
 * 统一加载高德 JS API 2.0（依赖 amap-config.js 中的 window.AMAP_CONFIG）
 */
(function (global) {
  var PLACEHOLDER = "请填写";

  function getConfig() {
    return global.AMAP_CONFIG || {};
  }

  function isConfigured() {
    var c = getConfig();
    return Boolean(c.key && String(c.key).indexOf(PLACEHOLDER) < 0);
  }

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-amap-loader="1"]');
      if (existing) {
        if (global.AMap) resolve();
        else {
          existing.addEventListener("load", function () {
            resolve();
          });
          existing.addEventListener("error", reject);
        }
        return;
      }
      var s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.setAttribute("data-amap-loader", "1");
      s.onload = function () {
        resolve();
      };
      s.onerror = function () {
        reject(new Error("高德地图脚本加载失败"));
      };
      document.head.appendChild(s);
    });
  }

  /**
   * @param {string[]} [plugins] 如 ['AMap.AutoComplete','AMap.Geocoder']
   * @returns {Promise<void>}
   */
  function loadAmap(plugins) {
    plugins = plugins || [];
    if (!isConfigured()) {
      return Promise.reject(new Error("AMAP_NOT_CONFIGURED"));
    }
    var c = getConfig();
    if (c.securityJsCode && String(c.securityJsCode).indexOf(PLACEHOLDER) < 0) {
      global._AMapSecurityConfig = { securityJsCode: c.securityJsCode };
    }
    var url =
      "https://webapi.amap.com/maps?v=2.0&key=" + encodeURIComponent(c.key);
    return loadScript(url).then(function () {
      if (!global.AMap) {
        return Promise.reject(new Error("AMap 未定义"));
      }
      if (!plugins.length) return;
      return new Promise(function (resolve, reject) {
        try {
          global.AMap.plugin(plugins, resolve);
        } catch (e) {
          reject(e);
        }
      });
    });
  }

  global.AmapApp = {
    getConfig: getConfig,
    isConfigured: isConfigured,
    loadAmap: loadAmap,
  };
})(window);
