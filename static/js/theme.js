// static/js/theme.js
let onThemeChangeCallbacks = [];

export function initTheme() {
  const themeIcon = document.getElementById("themeIcon");
  const themeText = document.getElementById("themeText");
  const toggleBtn = document.getElementById("themeToggle");

  const savedTheme = localStorage.getItem("theme");
  const isDarkInitial = savedTheme === "dark" || (!savedTheme && window.matchMedia("(prefers-color-scheme: dark)").matches);
  if (isDarkInitial) document.documentElement.classList.add("dark");

  applyThemeUI(document.documentElement.classList.contains("dark"));

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const isDark = document.documentElement.classList.toggle("dark");
      localStorage.setItem("theme", isDark ? "dark" : "light");
      applyThemeUI(isDark);
      onThemeChangeCallbacks.forEach(cb => cb(isDark)); // 🔥 외부에 알림
    });
  }
}

export function onThemeChange(callback) {
  onThemeChangeCallbacks.push(callback);
}

function applyThemeUI(isDark) {
  const icon = document.getElementById("themeIcon");
  const text = document.getElementById("themeText");
  if (!icon || !text) return;

  icon.textContent = isDark ? "☀️" : "🌙";
  text.textContent = isDark ? "라이트모드 전환" : "다크모드 전환";

  icon.classList.remove("invisible", "opacity-0");
  text.classList.remove("invisible", "opacity-0");
}
