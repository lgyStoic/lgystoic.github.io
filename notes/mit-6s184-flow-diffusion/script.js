const root = document.documentElement;
const searchInput = document.querySelector("#conceptSearch");
const sections = [...document.querySelectorAll("main .section, main .hero")];
const emptyState = document.querySelector("#emptyState");
const progressBar = document.querySelector("#progressBar");
const navLinks = [...document.querySelectorAll(".side-nav a")];
const themeToggle = document.querySelector("#themeToggle");

const savedTheme = localStorage.getItem("mit-6s184-theme");
if (savedTheme === "dark") {
  root.classList.add("dark");
}

themeToggle.addEventListener("click", () => {
  root.classList.toggle("dark");
  localStorage.setItem("mit-6s184-theme", root.classList.contains("dark") ? "dark" : "light");
});

function normalize(value) {
  return value.toLowerCase().trim();
}

function applySearch() {
  const query = normalize(searchInput.value);
  let visibleCount = 0;

  sections.forEach((section) => {
    section.classList.remove("highlight");
    if (!query) {
      section.classList.remove("is-hidden");
      visibleCount += 1;
      return;
    }

    const haystack = normalize(`${section.textContent} ${section.dataset.keywords || ""}`);
    const matched = haystack.includes(query);
    section.classList.toggle("is-hidden", !matched);
    section.classList.toggle("highlight", matched);
    if (matched) visibleCount += 1;
  });

  emptyState.hidden = visibleCount !== 0 || !query;
}

function updateProgress() {
  const doc = document.documentElement;
  const max = doc.scrollHeight - window.innerHeight;
  const ratio = max > 0 ? window.scrollY / max : 0;
  progressBar.style.width = `${Math.max(0, Math.min(1, ratio)) * 100}%`;
}

function updateActiveNav() {
  const candidates = sections
    .filter((section) => section.id)
    .map((section) => ({
      id: section.id,
      top: Math.abs(section.getBoundingClientRect().top - 110),
    }))
    .sort((a, b) => a.top - b.top);

  const activeId = candidates[0]?.id;
  navLinks.forEach((link) => {
    link.classList.toggle("active", link.getAttribute("href") === `#${activeId}`);
  });
}

searchInput.addEventListener("input", applySearch);
window.addEventListener("scroll", () => {
  updateProgress();
  updateActiveNav();
}, { passive: true });
window.addEventListener("resize", updateProgress);

updateProgress();
updateActiveNav();
