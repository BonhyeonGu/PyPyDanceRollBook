export async function renderAchievementsPage() {
  const app = document.getElementById("app");
  if (!app) return;

  app.innerHTML = `
    <div id="achievements-content" class="opacity-0 translate-y-2 transition-all duration-500">
      <h1 class="text-2xl font-bold mb-6">전체 도전과제</h1>
      <div id="achievements-container" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-6">
        <div class="col-span-full text-center text-gray-500">불러오는 중...</div>
      </div>
    </div>
  `;

  try {
    const res = await fetch("/api/achievements");
    const achievements = await res.json();

    const container = document.getElementById("achievements-container");
    container.innerHTML = "";

    achievements.forEach(ach => {
      const descLines = (ach.description || "").split(",").map(line => line.trim());

      const descHtml = descLines.map((line, i) => `
        <div class="${i === 0 ? "text-[15px] font-medium text-gray-800 dark:text-gray-100" : "text-[14px] italic text-gray-600 dark:text-gray-300"}">
          ${line}
        </div>
      `).join("");

      const item = document.createElement("div");
      item.className = "bg-white dark:bg-gray-800 p-4 rounded-xl shadow flex flex-col items-center text-center";

      item.innerHTML = `
        <img src="/static/achievements/a_${ach.name}.png"
            alt="${ach.name}"
            class="w-20 h-20 mb-2 rounded border-2 border-gray-400 dark:border-gray-200">

        <div class="text-[18px] font-semibold mt-1 text-gray-900 dark:text-white">${ach.name}</div>

        <div class="flex flex-col justify-between flex-grow w-full h-full mt-2">
          <div class="flex flex-col gap-[2px] text-[14px] text-gray-700 dark:text-gray-300">
            ${descHtml}
          </div>

          <div class="text-[14px] text-blue-600 dark:text-blue-400 mt-4">
            ${ach.achieved_count}명 달성 (${ach.percentage}%)
          </div>
        </div>
      `;


      container.appendChild(item);
    });



    // ✅ 애니메이션 적용 (나중에 등장)
    requestAnimationFrame(() => {
      document.getElementById("achievements-content")?.classList.replace("opacity-0", "opacity-100");
      document.getElementById("achievements-content")?.classList.replace("translate-y-2", "translate-y-0");
    });

  } catch (err) {
    document.getElementById("achievements-container").innerHTML =
      `<div class="text-red-500">도전과제를 불러오지 못했습니다.</div>`;
  }
}
