/**
 * 高德地图密钥（复制本文件为 amap-config.js 后填写）
 *
 * 申请：https://console.amap.com/dev/key/app
 * - 创建应用 → 添加 Key → 服务平台选「Web端(JS API)」
 * - 若开启「安全密钥」，把 securityJsCode 填到下面（与 Key 配对）
 * - 在 Key 设置里配置「域名白名单」：本地开发可加 localhost、127.0.0.1
 */
window.AMAP_CONFIG = {
  key: "请填写 Web端(JS API) Key",
  webServiceKey: "请填写 Web服务 Key（可选，供后端 REST 用）",
  securityJsCode: "请填写你的安全密钥（未开启安全校验可留空字符串）",
};
