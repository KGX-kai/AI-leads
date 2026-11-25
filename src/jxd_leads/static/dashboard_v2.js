(() => {
  "use strict";

  const root = document.querySelector("#dashboardRoot");
  let boot = {};
  try {
    boot = JSON.parse(root?.dataset.boot || "{}");
  } catch (_error) {
    boot = {};
  }

  const $ = (selector, scope = document) => scope.querySelector(selector);
  const $$ = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));
  const shell = $("#appShell");
  const sidebar = $("#sidebar");
  const scrim = $(".drawer-scrim");
  const menuButton = $("[data-open-drawer]");
  const collapseButton = $("[data-collapse-sidebar]");
  const breadcrumb = $("#breadcrumbCurrent");
  const toast = $("#toast");
  const overlay = $('[data-overlay="commandPalette"]');
  const commandInput = $("#commandInput");
  const commandResults = $("#commandResults");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const viewTitles = {
    overview: "总览",
    leads: "线索池",
    projects: "客户项目",
    opportunities: "采购机会",
    schedule: "跟进日程",
    analytics: "渠道分析",
    reports: "质量摘要",
    settings: "设置入口",
    detail: "候选摘要",
  };

  let currentView = "overview";
  let toastTimer = 0;
  let commandItems = [];
  let commandActive = -1;
  let chartRange = "6m";
  let overlayTrigger = null;

  function showToast(message) {
    if (!toast) return;
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2400);
  }

  function setActiveNavigation(name) {
    $$("[data-view-target]").forEach((item) => {
      if (item.closest("#commandResults")) return;
      const active = item.dataset.viewTarget === name;
      item.classList.toggle("is-active", active);
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
  }

  function switchView(name, options = {}) {
    const target = $(`.view[data-view="${name}"]`);
    if (!target) return;
    currentView = name;
    $$(".view").forEach((view) => {
      const active = view === target;
      view.hidden = !active;
      view.classList.toggle("is-active", active);
    });
    setActiveNavigation(name);
    if (breadcrumb) breadcrumb.textContent = viewTitles[name] || "工作台";
    document.title = `京小电 · 获客工作台｜${viewTitles[name] || "工作台"}`;
    closeDrawer({ restoreFocus: false });
    if (options.history !== false) {
      const nextUrl = name === "overview"
        ? window.location.pathname + window.location.search
        : `#${name}`;
      window.history.replaceState(null, "", nextUrl);
    }
    if (name === "overview") {
      window.requestAnimationFrame(renderOverviewChart);
    }
    if (options.scroll !== false) {
      window.scrollTo({ top: 0, behavior: !reduceMotion && options.changed ? "smooth" : "auto" });
    }
  }

  function openDrawer() {
    if (!sidebar || !scrim || window.innerWidth > 1024) return;
    sidebar.classList.add("is-open");
    scrim.classList.add("is-open");
    document.body.classList.add("drawer-open");
    menuButton?.setAttribute("aria-expanded", "true");
    $("[data-close-drawer]", sidebar)?.focus();
  }

  function closeDrawer(options = {}) {
    if (!sidebar || !scrim) return;
    const wasOpen = sidebar.classList.contains("is-open");
    sidebar.classList.remove("is-open");
    scrim.classList.remove("is-open");
    document.body.classList.remove("drawer-open");
    menuButton?.setAttribute("aria-expanded", "false");
    if (wasOpen && options.restoreFocus !== false) menuButton?.focus();
  }

  function setSidebarCollapsed(collapsed) {
    shell?.classList.toggle("is-collapsed", collapsed);
    collapseButton?.setAttribute("aria-pressed", String(collapsed));
    collapseButton?.setAttribute("aria-label", collapsed ? "展开侧栏" : "收起侧栏");
    try {
      localStorage.setItem("jxd-dashboard-sidebar", collapsed ? "collapsed" : "expanded");
    } catch (_error) {
      // A file-based standalone preview may not expose localStorage.
    }
    window.requestAnimationFrame(renderOverviewChart);
  }

  function openCommand(trigger) {
    if (!overlay || !commandInput) return;
    overlayTrigger = trigger || document.activeElement;
    overlay.hidden = false;
    overlay.classList.add("is-open");
    overlay.setAttribute("aria-hidden", "false");
    document.body.classList.add("overlay-open");
    commandInput.value = "";
    renderCommands("");
    window.setTimeout(() => commandInput.focus(), reduceMotion ? 0 : 30);
  }

  function closeCommand(options = {}) {
    if (!overlay) return;
    overlay.hidden = true;
    overlay.classList.remove("is-open");
    overlay.setAttribute("aria-hidden", "true");
    document.body.classList.remove("overlay-open");
    if (options.restoreFocus !== false && overlayTrigger instanceof HTMLElement) overlayTrigger.focus();
    overlayTrigger = null;
  }

  function commandPool() {
    return [
      ...(boot.leads || []).map((item) => ({
        label: item.name,
        sub: `${item.org} · ${item.stage}`,
        href: item.href,
        type: "候选",
      })),
      ...(boot.projects || []).map((item) => ({
        label: item.name,
        sub: `${item.client} · ${item.stage}`,
        href: item.href,
        type: "项目",
      })),
      ...(boot.opportunities || []).map((item) => ({
        label: item.name,
        sub: `${item.place} · ${item.stage}`,
        href: item.href,
        type: "机会",
      })),
    ];
  }

  function renderCommands(query) {
    if (!commandResults) return;
    const needle = String(query || "").trim().toLocaleLowerCase("zh-CN");
    commandItems = commandPool()
      .filter((item) => !needle || `${item.label} ${item.sub} ${item.type}`.toLocaleLowerCase("zh-CN").includes(needle))
      .slice(0, 30);
    commandActive = commandItems.length ? 0 : -1;
    commandResults.replaceChildren();

    if (!commandItems.length) {
      const empty = document.createElement("div");
      empty.className = "command-empty";
      empty.textContent = needle ? "没有匹配记录" : "当前页暂无可搜索记录";
      commandResults.append(empty);
      return;
    }

    commandItems.forEach((item, index) => {
      const button = document.createElement("a");
      button.className = "command-item";
      button.href = item.href;
      button.dataset.commandIndex = String(index);
      button.setAttribute("role", "option");
      button.setAttribute("aria-selected", String(index === 0));
      if (index === 0) button.classList.add("is-active");

      const copy = document.createElement("span");
      copy.className = "command-copy";
      const title = document.createElement("strong");
      title.textContent = item.label;
      const detail = document.createElement("small");
      detail.textContent = item.sub;
      copy.append(title, detail);

      const type = document.createElement("span");
      type.className = "command-type";
      type.textContent = item.type;
      button.append(copy, type);
      commandResults.append(button);
    });
  }

  function markCommand(index) {
    if (!commandItems.length) return;
    commandActive = Math.max(0, Math.min(commandItems.length - 1, index));
    $$(".command-item", commandResults).forEach((item, itemIndex) => {
      const active = itemIndex === commandActive;
      item.classList.toggle("is-active", active);
      item.setAttribute("aria-selected", String(active));
      if (active) item.scrollIntoView({ block: "nearest" });
    });
  }

  function makeSvg(tag, attributes = {}, text = "") {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
    if (text) node.textContent = text;
    return node;
  }

  function maxValue(values) {
    const maximum = Math.max(0, ...values);
    if (!maximum) return 1;
    const magnitude = 10 ** Math.max(0, Math.floor(Math.log10(maximum)) - 1);
    return Math.ceil(maximum / magnitude) * magnitude;
  }

  function renderOverviewChart() {
    const svg = $("#overviewChart");
    const note = $("#overviewChartNote");
    if (!svg) return;
    const data = boot.overview?.trend?.[chartRange] || { labels: [], values: [] };
    const labels = Array.isArray(data.labels) ? data.labels : [];
    const values = Array.isArray(data.values) ? data.values.map((value) => Number(value) || 0) : [];
    svg.replaceChildren();

    if (!labels.length || !values.length) {
      svg.setAttribute("viewBox", "0 0 720 250");
      svg.setAttribute("aria-label", "暂无新增线索序列");
      svg.append(makeSvg("text", { x: 360, y: 125, "text-anchor": "middle", class: "chart-empty-text" }, "暂无新增线索序列"));
      if (note) note.textContent = "暂无新增线索序列";
      return;
    }

    const width = Math.max(300, Math.round(svg.parentElement?.getBoundingClientRect().width || 720));
    const height = window.innerWidth < 640 ? 220 : 260;
    const margin = { top: 18, right: 22, bottom: 34, left: 42 };
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    const baseline = margin.top + innerHeight;
    const ceiling = maxValue(values);
    const band = values.length > 1 ? innerWidth / (values.length - 1) : innerWidth;
    const points = values.map((value, index) => ({
      x: values.length > 1 ? margin.left + band * index : margin.left + innerWidth / 2,
      y: margin.top + innerHeight * (1 - value / ceiling),
      value,
    }));

    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", String(width));
    svg.setAttribute("height", String(height));
    svg.setAttribute("aria-label", `新增线索趋势，共 ${values.reduce((sum, value) => sum + value, 0)} 条`);
    svg.append(
      makeSvg("title", {}, "新增线索趋势"),
      makeSvg("desc", {}, labels.map((label, index) => `${label} ${values[index]} 条`).join("，"))
    );

    for (let tick = 0; tick <= 4; tick += 1) {
      const ratio = tick / 4;
      const y = margin.top + innerHeight * (1 - ratio);
      svg.append(makeSvg("line", { class: "chart-grid", x1: margin.left, x2: width - margin.right, y1: y, y2: y }));
      svg.append(makeSvg("text", { class: "chart-axis-text", x: margin.left - 8, y: y + 4, "text-anchor": "end" }, Math.round(ceiling * ratio)));
    }

    const line = points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`).join(" ");
    const area = `${line} L ${points.at(-1).x.toFixed(2)} ${baseline.toFixed(2)} L ${points[0].x.toFixed(2)} ${baseline.toFixed(2)} Z`;
    svg.append(makeSvg("path", { class: "chart-area", d: area, fill: "rgba(255,215,0,0.10)" }));
    svg.append(makeSvg("path", { class: "chart-series", d: line, stroke: "#FFD700", fill: "none" }));

    points.forEach((point, index) => {
      svg.append(makeSvg("circle", {
        class: index === points.length - 1 ? "chart-point is-last" : "chart-point",
        cx: point.x,
        cy: point.y,
        r: index === points.length - 1 ? 4 : 2.5,
        stroke: "#FFD700",
        fill: index === points.length - 1 ? "#FFD700" : "#2D2D2D",
      }));
      const labelStep = width < 480 ? 2 : 1;
      if (index % labelStep === 0 || index === labels.length - 1) {
        svg.append(makeSvg("text", {
          class: "chart-axis-text",
          x: point.x,
          y: height - 9,
          "text-anchor": "middle",
        }, labels[index]));
      }
    });

    if (note) {
      const total = values.reduce((sum, value) => sum + value, 0);
      note.textContent = `${chartRange === "6m" ? "近 6 个月" : "近 8 周"}新增 ${total} 条；按服务端北京时间统计。`;
    }
  }

  function trapOverlayFocus(event) {
    if (!overlay || overlay.hidden || event.key !== "Tab") return;
    const panel = $(".overlay-panel", overlay);
    const items = $$('a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])', panel)
      .filter((item) => item.offsetParent !== null);
    if (!items.length) return;
    const first = items[0];
    const last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  document.addEventListener("click", (event) => {
    const viewButton = event.target.closest("[data-view-target]");
    if (viewButton) {
      event.preventDefault();
      switchView(viewButton.dataset.viewTarget, { changed: currentView !== viewButton.dataset.viewTarget });
      return;
    }

    const closeButton = event.target.closest("[data-overlay-close]");
    if (closeButton) {
      event.preventDefault();
      closeCommand();
      return;
    }

    if (event.target.closest("[data-open-drawer]")) {
      event.preventDefault();
      openDrawer();
      return;
    }

    if (event.target.closest("[data-close-drawer]")) {
      event.preventDefault();
      closeDrawer();
      return;
    }

    if (event.target.closest("[data-collapse-sidebar]")) {
      event.preventDefault();
      setSidebarCollapsed(!shell?.classList.contains("is-collapsed"));
      return;
    }

    if (event.target.closest("#searchTrigger")) {
      event.preventDefault();
      openCommand(event.target.closest("#searchTrigger"));
    }
  });

  document.addEventListener("change", (event) => {
    if (event.target.matches("[data-overview-range]")) {
      chartRange = event.target.dataset.overviewRange === "8w" ? "8w" : "6m";
      $$("[data-overview-range]").forEach((button) => {
        const active = button.dataset.overviewRange === chartRange;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", String(active));
      });
      renderOverviewChart();
    }
  });

  $$("[data-overview-range]").forEach((button) => {
    button.addEventListener("click", () => {
      chartRange = button.dataset.overviewRange === "8w" ? "8w" : "6m";
      $$("[data-overview-range]").forEach((item) => {
        const active = item === button;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
      });
      renderOverviewChart();
    });
  });

  commandInput?.addEventListener("input", () => renderCommands(commandInput.value));
  commandInput?.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      markCommand(commandActive + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      markCommand(commandActive - 1);
    } else if (event.key === "Enter" && commandActive >= 0) {
      event.preventDefault();
      const selected = commandItems[commandActive];
      if (selected?.href) window.location.assign(selected.href);
    }
  });

  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLocaleLowerCase("en-US") === "k") {
      event.preventDefault();
      openCommand(document.activeElement);
      return;
    }
    if (overlay && !overlay.hidden && event.key === "Escape") {
      event.preventDefault();
      closeCommand();
      return;
    }
    if (event.key === "Escape" && sidebar?.classList.contains("is-open")) {
      event.preventDefault();
      closeDrawer();
      return;
    }
    trapOverlayFocus(event);
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 1024) closeDrawer({ restoreFocus: false });
    window.clearTimeout(window.__jxdDashboardResize);
    window.__jxdDashboardResize = window.setTimeout(renderOverviewChart, 120);
  });

  if (shell && window.innerWidth > 1024) {
    let stored = null;
    try {
      stored = localStorage.getItem("jxd-dashboard-sidebar");
    } catch (_error) {
      stored = null;
    }
    const collapsed = stored === "collapsed" || (!stored && window.innerWidth < 1240);
    shell.classList.toggle("is-collapsed", collapsed);
    collapseButton?.setAttribute("aria-pressed", String(collapsed));
  }

  const requestedHash = window.location.hash.slice(1);
  const initial = requestedHash && $(`.view[data-view="${requestedHash}"]`)
    ? requestedHash
    : shell?.dataset.defaultView || "overview";
  switchView(initial, { history: false, scroll: false });
  document.body.classList.add("is-ready");
})();
