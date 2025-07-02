window.addEventListener("DOMContentLoaded", handleRouteChange);
window.addEventListener("hashchange", handleRouteChange);

async function handleRouteChange() {
  const hash = location.hash || "#/";
  const app = document.getElementById("app");
  if (!app) return;

  // 애니메이션 OUT
  app.classList.remove("opacity-100", "translate-x-0");
  app.classList.add("opacity-0", "translate-x-4");

  await new Promise(resolve => requestAnimationFrame(() => setTimeout(resolve, 150)));

  try {
    switch (hash) {
      case "#/":
      case "#/main": {
        const { initMain } = await import("/static/js/main.js");
        await initMain(); // 내부에서 innerHTML 초기화 및 fade-in 수행
        return;
      }

      case "#/achievements": {
        const { renderAchievementsPage } = await import("/static/js/achievements.js");
        await renderAchievementsPage(); // 내부에서 초기화 및 fade-in 수행
        return;
      }

      default:
        app.innerHTML = `<div class="text-red-500 text-center mt-12">존재하지 않는 페이지입니다.</div>`;
        fadeInApp(app); // fallback 애니메이션
    }

  } catch (e) {
    app.innerHTML = `<div class="text-red-500 text-center mt-12">페이지 로딩 실패: ${e.message}</div>`;
    console.error("라우터 오류:", e);
    fadeInApp(app);
  }
}

function fadeInApp(app) {
  requestAnimationFrame(() => {
    app.classList.remove("translate-x-4", "opacity-0");
    app.classList.add("translate-x-0", "opacity-100");
  });
}
