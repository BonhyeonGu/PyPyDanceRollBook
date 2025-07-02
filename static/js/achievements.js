export async function renderAchievementsPage() {
  const app = document.getElementById("app");
  if (!app) return;

  app.innerHTML = `
    <h1 class="text-2xl font-bold mb-6">전체 도전과제</h1>
    <div id="achievements-container" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6">
      <div class="col-span-full text-center text-gray-500">불러오는 중...</div>
    </div>
  `;

  try {
    const res = await fetch("/api/achievements");
    const achievements = await res.json();

    const container = document.getElementById("achievements-container");
    container.innerHTML = "";

    achievements.forEach(ach => {
      const item = document.createElement("div");
      item.className = "bg-white dark:bg-gray-800 p-4 rounded-xl shadow flex flex-col items-center text-center";
      item.innerHTML = `
        <img src="/static/achievements/a_${ach.name}.png" alt="${ach.name}" class="w-20 h-20 mb-2">
        <div class="text-lg font-semibold">${ach.name}</div>
        <div class="text-sm text-gray-600 dark:text-gray-300 mt-1">${ach.description}</div>
      `;
      container.appendChild(item);
    });

  } catch (err) {
    document.getElementById("achievements-container").innerHTML =
      `<div class="text-red-500">도전과제를 불러오지 못했습니다.</div>`;
  }

  // ✅ 애니메이션 복귀
  requestAnimationFrame(() => {
    app.classList.remove("translate-x-4", "opacity-0");
    app.classList.add("translate-x-0", "opacity-100");
  });
}
