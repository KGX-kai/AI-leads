(() => {
  "use strict";

  const STORAGE_KEY = "jxd-theme";
  const root = document.documentElement;
  const meta = document.querySelector('meta[name="theme-color"]');

  const ICONS = {
    light:
      '<circle cx="12" cy="12" r="4.2"></circle>' +
      '<path d="M12 2.8v2.2M12 19v2.2M2.8 12h2.2M19 12h2.2M5.5 5.5l1.6 1.6M16.9 16.9l1.6 1.6M18.5 5.5l-1.6 1.6M7.1 16.9l-1.6 1.6"></path>',
    dark:
      '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.8 6.8 0 0 0 10.5 10.5Z"></path>',
  };

  function currentTheme() {
    return root.dataset.theme === "light" ? "light" : "dark";
  }

  function paint(theme) {
    root.dataset.theme = theme;
    if (meta) meta.setAttribute("content", theme === "light" ? "#F4F1EC" : "#1A1A1A");
    const button = document.querySelector("[data-theme-toggle]");
    if (!button) return;
    const next = theme === "light" ? "深色" : "浅色";
    button.setAttribute("aria-label", "切换到" + next + "主题");
    button.setAttribute("title", "切换到" + next + "主题");
    button.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
    const icon = button.querySelector("svg");
    if (icon) icon.innerHTML = ICONS[theme === "light" ? "dark" : "light"];
  }

  function apply(theme, persist) {
    paint(theme);
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, theme);
      } catch (error) {}
    }
    window.dispatchEvent(new CustomEvent("jxd:themechange", { detail: { theme } }));
  }

  function mount() {
    const right = document.querySelector(".topbar-right");
    if (!right || right.querySelector("[data-theme-toggle]")) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "icon-button theme-toggle";
    button.setAttribute("data-theme-toggle", "");
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"></svg>';
    const anchor =
      right.querySelector('a[href="/notifications"]') ||
      right.querySelector(".icon-button.has-dot");
    right.insertBefore(button, anchor || null);
    button.addEventListener("click", () => {
      apply(currentTheme() === "light" ? "dark" : "light", true);
    });
    paint(currentTheme());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount, { once: true });
  } else {
    mount();
  }

  window.addEventListener("storage", (event) => {
    if (event.key === STORAGE_KEY && (event.newValue === "light" || event.newValue === "dark")) {
      apply(event.newValue, false);
    }
  });
})();
