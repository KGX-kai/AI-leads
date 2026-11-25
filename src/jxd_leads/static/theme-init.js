(() => {
  "use strict";

  let theme = "dark";
  try {
    const stored = localStorage.getItem("jxd-theme");
    if (stored === "light" || stored === "dark") theme = stored;
  } catch (error) {}
  document.documentElement.dataset.theme = theme;
})();
