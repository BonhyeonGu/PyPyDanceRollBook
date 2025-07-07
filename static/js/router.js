window.addEventListener("DOMContentLoaded", handleRouteChange);
window.addEventListener("hashchange", handleRouteChange);

async function handleRouteChange() {
  const hash = location.hash || "#/";
  const app = document.getElementById("app");
  if (!app) return;

  // ✅ 1. 기존 콘텐츠를 천천히 사라지게
  app.classList.remove("opacity-100");
  app.classList.add("opacity-0");
  await new Promise(resolve => setTimeout(resolve, 200)); // fade-out 시간

  try {
    // ✅ 2. 라우트에 따라 동적으로 페이지 렌더링
    switch (hash) {
      case "#/":
      case "#/main": {
        const { initMain } = await import("/static/js/main.js");
        await initMain(); // 내부에서 app.innerHTML 설정
        break;
      }


      case "#/allusers": {
        const { renderAllusersPage } = await import("/static/js/allusers.js");
        await renderAllusersPage(); // 내부에서 app.innerHTML 설정
        break;
      }

      case "#/achievements": {
        const { renderAchievementsPage } = await import("/static/js/achievements.js");
        await renderAchievementsPage(); // 내부에서 app.innerHTML 설정
        break;
      }

      case "#/analysis": {
        const { renderAnalysisPage } = await import("/static/js/analysis.js");
        await renderAnalysisPage(); // 내부에서 app.innerHTML 설정
        break;
      }

      default:
        app.innerHTML = `<div class="text-red-500 text-center mt-12">존재하지 않는 페이지입니다.</div>`;
    }

    // ✅ 3. 새로운 콘텐츠가 준비되었으므로, 부드럽게 등장
    app.classList.remove("opacity-0");
    app.classList.add("opacity-100");

  } catch (e) {
    app.innerHTML = `<div class="text-red-500 text-center mt-12">페이지 로딩 실패: ${e.message}</div>`;
    console.error("라우터 오류:", e);
    app.classList.remove("opacity-0");
    app.classList.add("opacity-100");
  }
}
