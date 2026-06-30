(function () {
  var CITIES = ["重庆", "北京", "南京", "新疆", "成都", "西安"];

  /** 各目的地建议游玩天数（P1 飞入文案与对话默认参考） */
  var RECOMMENDED_DAYS = {
    北京: 4,
    南京: 3,
    重庆: 3,
    新疆: 7,
    成都: 4,
    西安: 4,
  };

  var ROUTE_TAILS = {
    重庆:
      "听说那里的马路是立体迷宫。我平时最怕走折返跑。请帮我串成一条线，怎么顺路怎么来！",
    北京:
      "听说景点南北跨度大、来回折返。我平时最怕走冤枉路。请帮我串成一条线，怎么顺路怎么来！",
    南京:
      "听说景点东一块西一块。我平时最怕走折返跑。请帮我串成一条线，怎么顺路怎么来！",
    新疆:
      "听说景点之间路途远。我平时最怕把时间耗在路上。请帮我串成一条线，怎么顺路怎么来！",
    成都:
      "听说市区和青城山都江堰不在一块。我平时最怕折返跑。请帮我串成一条线，怎么顺路怎么来！",
    西安:
      "听说兵马俑华山离市区远。我平时最怕把时间耗在路上。请帮我串成一条线，怎么顺路怎么来！",
  };

  var FOOD_SPECIALTIES = {
    南京: "板鸭",
    北京: "烤鸭",
    重庆: "火锅",
    新疆: "烤羊肉串",
    成都: "火锅",
    西安: "羊肉泡馍",
  };

  var FILL_AREAS = {
    南京: "南京新街口",
    北京: "北京王府井",
    重庆: "重庆解放碑",
    新疆: "新疆大巴扎附近",
    成都: "成都春熙路",
    西安: "西安钟楼",
  };

  var EVENT_LINES = {
    北京: function (days) {
      return (
        "我路过北京只有1天空闲（玩透大概要" +
        days +
        "天），帮我安排下怎么玩最省事。"
      );
    },
    南京: function (days) {
      return (
        "我在南京中转有半天时间（正常玩" +
        days +
        "天比较合适），帮我看看附近有什么值得一逛的。"
      );
    },
    重庆: function (days) {
      return (
        "出差到重庆，想抽半天随便走走（完整逛吃建议" +
        days +
        "天），帮我安排个轻松的行程。"
      );
    },
    新疆: function (days) {
      return (
        "在新疆停留2天，之前没来过（想玩透建议" +
        days +
        "天左右），帮我看看怎么玩比较顺路。"
      );
    },
    成都: function (days) {
      return (
        "在成都中转只有半天（完整逛吃建议" +
        days +
        "天），帮我安排个轻松顺路的行程。"
      );
    },
    西安: function (days) {
      return (
        "路过西安只有1天空闲（玩透大概要" +
        days +
        "天），帮我看看怎么玩最省事。"
      );
    },
  };

  var BUDGET_BUDGETS = {
    北京: 3500,
    南京: 3000,
    重庆: 3000,
    新疆: 5000,
    成都: 3200,
    西安: 3200,
  };

  var modeState = {
    ROUTE: { i: -1 },
    FOOD: { i: -1 },
    FILL: { i: -1 },
    EVENT: { i: -1 },
    BUDGET: { i: -1 },
  };

  var capsules = document.querySelectorAll(".capsule");
  var stage = document.querySelector(".scenarios");
  var input = document.getElementById("chat-input");
  var form = document.getElementById("chat-form");
  var btnSend = document.getElementById("btn-send");
  var prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  function syncSendState() {
    btnSend.disabled = !input.value.trim();
  }

  function autoResize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 176) + "px";
  }

  function setActiveCapsule(mode) {
    capsules.forEach(function (cap) {
      cap.classList.toggle("is-active", cap.dataset.mode === mode);
    });
  }

  function recommendedDays(city) {
    return RECOMMENDED_DAYS[city] || 3;
  }

  function nextCity(state) {
    state.i = (state.i + 1) % CITIES.length;
    return CITIES[state.i];
  }

  function buildRoute(state) {
    var city = nextCity(state);
    var days = recommendedDays(city);
    return (
      "我已经订好了去" +
      city +
      "的机票，打算玩" +
      days +
      "天。" +
      ROUTE_TAILS[city]
    );
  }

  function buildFood(state) {
    var city = nextCity(state);
    var days = recommendedDays(city);
    return (
      "我想去" +
      city +
      "玩" +
      days +
      "天，冲着" +
      FOOD_SPECIALTIES[city] +
      "去的，帮我推荐下" +
      city +
      "的酒店和景点。"
    );
  }

  function buildFill(state) {
    var city = nextCity(state);
    var days = recommendedDays(city);
    return (
      "我已经定了酒店在" +
      FILL_AREAS[city] +
      "，打算玩" +
      days +
      "天，帮我推荐下周围的景点。"
    );
  }

  function buildEvent(state) {
    var city = nextCity(state);
    return EVENT_LINES[city](recommendedDays(city));
  }

  function buildBudget(state) {
    var city = nextCity(state);
    var days = recommendedDays(city);
    var budget = BUDGET_BUDGETS[city] || 3000;
    if (city === "新疆") {
      return (
        "我只有 " +
        days +
        " 天假，预算是" +
        budget +
        "元。有没有性价比好的地方推荐？"
      );
    }
    return (
      "我只有 " +
      days +
      " 天假，预算是" +
      budget +
      "元。想问问去" +
      city +
      "，有没有性价比好的安排？"
    );
  }

  var builders = {
    ROUTE: buildRoute,
    FOOD: buildFood,
    FILL: buildFill,
    EVENT: buildEvent,
    BUDGET: buildBudget,
  };

  function flyToInput(fromEl, text, mode) {
    if (prefersReducedMotion) {
      input.value = text;
      autoResize();
      syncSendState();
      setActiveCapsule(mode);
      input.focus();
      return;
    }

    var start = fromEl.getBoundingClientRect();
    var end = input.getBoundingClientRect();
    var ghost = document.createElement("div");
    ghost.className = "fly-ghost";
    ghost.textContent =
      text.length > 42 ? text.slice(0, 42) + "…" : text;
    ghost.style.left = start.left + 12 + "px";
    ghost.style.top = start.top + start.height * 0.35 + "px";
    document.body.appendChild(ghost);

    requestAnimationFrame(function () {
      ghost.style.left = end.left + 16 + "px";
      ghost.style.top = end.top + 10 + "px";
      ghost.classList.add("is-landing");
    });

    ghost.addEventListener("transitionend", function onEnd(e) {
      if (e.propertyName !== "left") return;
      ghost.removeEventListener("transitionend", onEnd);
      ghost.remove();
      input.value = text;
      autoResize();
      syncSendState();
      setActiveCapsule(mode);
      input.focus();
      input.setSelectionRange(text.length, text.length);
    });
  }

  function onCapsuleClick(capsule) {
    // 「暂未上线」的模式（如预算）不响应点击，避免带入不支持的流程
    if (capsule.classList.contains("capsule--soon")) return;
    var mode = capsule.dataset.mode;
    var builder = builders[mode];
    if (!builder) return;

    var text = builder(modeState[mode]);
    flyToInput(capsule, text, mode);
  }

  capsules.forEach(function (cap) {
    cap.addEventListener("click", function () {
      onCapsuleClick(cap);
    });
  });

  input.addEventListener("input", function () {
    autoResize();
    syncSendState();
    if (!input.value.trim()) setActiveCapsule(null);
  });

  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!btnSend.disabled) form.requestSubmit();
    }
  });

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;

    var active = document.querySelector(".capsule.is-active");
    var mode = active ? active.dataset.mode : "FREE";

    try {
      sessionStorage.setItem("archorMode", mode);
      sessionStorage.setItem("archorPrompt", text);
      sessionStorage.removeItem("archorSession");
      sessionStorage.removeItem("archorMessages");
    } catch (err) {}

    window.location.href = "p2.html";
  });

  syncSendState();

  function initBubbleDrift() {
    if (!stage || !capsules.length) return;

    var STARTS = [
      { x: 0.1, y: 0.14 },
      { x: 0.58, y: 0.08 },
      { x: 0.62, y: 0.46 },
      { x: 0.06, y: 0.5 },
      { x: 0.34, y: 0.68 },
    ];

    var bodies = [];
    var hovered = null;
    var running = true;

    function randSpeed() {
      var angle = Math.random() * Math.PI * 2;
      var speed = 0.018 + Math.random() * 0.028;
      return {
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed,
      };
    }

    function measure(body) {
      body.w = body.el.offsetWidth;
      body.h = body.el.offsetHeight;
      body.r = Math.max(body.w, body.h) * 0.48;
    }

    function placeBodies(resetPositions) {
      var sw = stage.clientWidth;
      var sh = stage.clientHeight;

      capsules.forEach(function (el, i) {
        var body = bodies[i];
        if (!body) {
          var vel = randSpeed();
          body = {
            el: el,
            x: 0,
            y: 0,
            w: 0,
            h: 0,
            r: 0,
            vx: vel.vx,
            vy: vel.vy,
          };
          bodies[i] = body;
        }

        measure(body);

        if (resetPositions) {
          var start = STARTS[i] || { x: 0.2, y: 0.2 };
          body.x = start.x * Math.max(0, sw - body.w);
          body.y = start.y * Math.max(0, sh - body.h);
        } else {
          body.x = Math.min(body.x, Math.max(0, sw - body.w));
          body.y = Math.min(body.y, Math.max(0, sh - body.h));
        }

        body.el.style.transform =
          "translate3d(" + body.x + "px," + body.y + "px,0)";
      });
    }

    function clampSpeed(body) {
      var max = 0.06;
      var speed = Math.hypot(body.vx, body.vy);
      if (speed > max) {
        body.vx = (body.vx / speed) * max;
        body.vy = (body.vy / speed) * max;
      }
    }

    function bounceWall(body, sw, sh) {
      if (body.x <= 0) {
        body.x = 0;
        body.vx = Math.abs(body.vx) * 0.92;
      }
      if (body.y <= 0) {
        body.y = 0;
        body.vy = Math.abs(body.vy) * 0.92;
      }
      if (body.x + body.w >= sw) {
        body.x = sw - body.w;
        body.vx = -Math.abs(body.vx) * 0.92;
      }
      if (body.y + body.h >= sh) {
        body.y = sh - body.h;
        body.vy = -Math.abs(body.vy) * 0.92;
      }
    }

    function collide(a, b) {
      var ax = a.x + a.w * 0.5;
      var ay = a.y + a.h * 0.5;
      var bx = b.x + b.w * 0.5;
      var by = b.y + b.h * 0.5;
      var dx = bx - ax;
      var dy = by - ay;
      var dist = Math.hypot(dx, dy) || 0.001;
      var minDist = a.r + b.r;

      if (dist >= minDist) return;

      var nx = dx / dist;
      var ny = dy / dist;
      var overlap = minDist - dist;

      if (a.el === hovered || a.el.classList.contains("is-active")) {
        b.x += nx * overlap;
        b.y += ny * overlap;
        b.vx += nx * 0.01;
        b.vy += ny * 0.01;
        return;
      }
      if (b.el === hovered || b.el.classList.contains("is-active")) {
        a.x -= nx * overlap;
        a.y -= ny * overlap;
        a.vx -= nx * 0.01;
        a.vy -= ny * 0.01;
        return;
      }

      a.x -= nx * overlap * 0.5;
      a.y -= ny * overlap * 0.5;
      b.x += nx * overlap * 0.5;
      b.y += ny * overlap * 0.5;

      var dvx = a.vx - b.vx;
      var dvy = a.vy - b.vy;
      var dot = dvx * nx + dvy * ny;
      if (dot > 0) {
        a.vx -= dot * nx * 0.95;
        a.vy -= dot * ny * 0.95;
        b.vx += dot * nx * 0.95;
        b.vy += dot * ny * 0.95;
      }
    }

    function tick() {
      if (!running) return;

      var sw = stage.clientWidth;
      var sh = stage.clientHeight;

      bodies.forEach(function (body) {
        if (
          body.el === hovered ||
          body.el.classList.contains("is-active")
        ) {
          body.el.style.transform =
            "translate3d(" + body.x + "px," + body.y + "px,0)";
          return;
        }

        body.vx += (Math.random() - 0.5) * 0.0008;
        body.vy += (Math.random() - 0.5) * 0.0008;
        body.x += body.vx;
        body.y += body.vy;

        clampSpeed(body);
        bounceWall(body, sw, sh);
        body.el.style.transform =
          "translate3d(" + body.x + "px," + body.y + "px,0)";
      });

      for (var i = 0; i < bodies.length; i++) {
        for (var j = i + 1; j < bodies.length; j++) {
          collide(bodies[i], bodies[j]);
        }
      }

      requestAnimationFrame(tick);
    }

    capsules.forEach(function (el) {
      el.addEventListener("mouseenter", function () {
        hovered = el;
      });
      el.addEventListener("mouseleave", function () {
        if (hovered === el) hovered = null;
      });
      el.addEventListener("focus", function () {
        hovered = el;
      });
      el.addEventListener("blur", function () {
        if (hovered === el) hovered = null;
      });
    });

    if (prefersReducedMotion) {
      stage.classList.add("is-static");
      placeBodies(true);
      return;
    }

    placeBodies(true);
    window.addEventListener("resize", function () {
      placeBodies(false);
    });
    requestAnimationFrame(tick);
  }

  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(initBubbleDrift);
  } else {
    window.addEventListener("load", initBubbleDrift);
  }
})();
