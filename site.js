/* 站点交互：深浅色切换 + 归档页搜索/标签筛选。
   列表本身由 tools/build.py 预渲染成静态 HTML，这里不负责渲染内容，
   所以禁用 JS 时页面依然完整可读。 */

(function theme() {
  const root = document.documentElement;
  const button = document.querySelector("[data-theme-toggle]");
  const icon = document.querySelector("[data-theme-icon]");
  if (!button) return;

  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");

  const current = () => root.dataset.theme || (prefersDark.matches ? "dark" : "light");

  function paint() {
    const mode = current();
    if (icon) icon.textContent = mode === "dark" ? "☀" : "☾";
    button.setAttribute("aria-label", mode === "dark" ? "切换到浅色" : "切换到深色");
  }

  button.addEventListener("click", () => {
    const next = current() === "dark" ? "light" : "dark";
    root.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch (e) {}
    paint();
  });

  prefersDark.addEventListener("change", () => {
    if (!root.dataset.theme) paint();
  });

  paint();
})();

(function archive() {
  const container = document.querySelector("[data-archive]");
  if (!container) return;

  const input = document.querySelector("[data-search-input]");
  const chips = [...document.querySelectorAll(".tag-chip[data-tag]")];
  const counter = document.querySelector("[data-result-count]");
  const empty = document.querySelector("[data-empty]");
  const items = [...container.querySelectorAll("li[data-search]")];
  const groups = [...container.querySelectorAll(".year-group")];

  let query = "";
  let tag = new URLSearchParams(location.search).get("tag") || "";

  function matches(item) {
    const tags = (item.dataset.tags || "").split("|");
    if (tag && !tags.includes(tag)) return false;
    if (query && !(item.dataset.search || "").includes(query)) return false;
    return true;
  }

  function apply() {
    let visible = 0;
    items.forEach((item) => {
      const ok = matches(item);
      item.hidden = !ok;
      if (ok) visible += 1;
    });

    groups.forEach((group) => {
      group.hidden = ![...group.querySelectorAll("li[data-search]")].some((li) => !li.hidden);
    });

    chips.forEach((chip) => {
      const active = chip.dataset.tag === tag;
      chip.setAttribute("aria-pressed", String(active));
      // 选中的标签如果折在 <details> 里，展开它，否则筛选结果看起来像凭空发生。
      if (active && tag) {
        const box = chip.closest("details");
        if (box) box.open = true;
      }
    });
    if (counter) counter.textContent = `${visible} 篇${tag ? ` · #${tag}` : ""}`;
    if (empty) empty.hidden = visible !== 0;
  }

  if (input) {
    input.addEventListener("input", () => {
      query = input.value.trim().toLowerCase();
      apply();
    });
  }

  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      tag = chip.dataset.tag === tag ? "" : chip.dataset.tag;
      const url = tag ? `?tag=${encodeURIComponent(tag)}` : location.pathname;
      history.replaceState(null, "", url);
      apply();
    });
  });

  // 按 / 聚焦搜索框，和大多数文档站一致。
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && input && document.activeElement !== input) {
      event.preventDefault();
      input.focus();
    }
  });

  apply();
})();
