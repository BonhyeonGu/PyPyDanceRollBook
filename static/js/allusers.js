function drawChart(canvas, labels, data, isDark) {
    const lineColor = isDark ? 'rgba(96,165,250,1)' : 'rgba(54,162,235,1)';
    const pointBg = isDark ? 'rgba(147,197,253,1)' : 'rgba(54,162,235,0.6)';
    const gridColor = isDark ? '#444' : '#ccc';
    const fontColor = isDark ? '#ddd' : '#333';

    if (canvas && canvas.getContext) {
        const ctx = canvas.getContext("2d");
        if (ctx) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [{
                        label: '',
                        data: data,
                        fill: false,
                        borderColor: lineColor,
                        backgroundColor: pointBg,
                        tension: 0.3,
                        pointRadius: 2,
                        pointHoverRadius: 4
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 80,
                            ticks: { font: { size: 10 }, color: fontColor },
                            grid: { color: gridColor },
                            title: { display: false }
                        },
                        x: {
                            ticks: { font: { size: 10 }, color: fontColor },
                            grid: { color: gridColor },
                            title: { display: false }
                        }
                    }
                }
            });
        }
    }
}

let hoverCard = null;
document.addEventListener("mousemove", (e) => {
    if (hoverCard) {
        const offset = 16;
        const cardHeight = hoverCard.offsetHeight || 200;  // 카드 높이 (기본값 200)
        const windowHeight = window.innerHeight;

        let top;
        if (e.clientY + offset + cardHeight > windowHeight) {
            // 화면 아래에 닿을 경우: 위에 표시
            top = e.clientY - offset - cardHeight;
        } else {
            // 기본: 커서 아래에 표시
            top = e.clientY + offset;
        }

        hoverCard.style.left = `${e.clientX + offset}px`;
        hoverCard.style.top = `${top}px`;
    }
});

export async function renderAllusersPage() {
    const app = document.getElementById("app");
    if (!app) return;
    app.innerHTML = `
        <h1 class="text-2xl font-bold mb-4 text-center">모든 유저 목록</h1>

        <div class="px-4 md:px-8">
            <!-- ✅ 유저 카드 영역 먼저 -->
            <div id="user-list"
                class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-20 relative mb-20">
            </div>

            <!-- ✅ 그 아래 배너 이미지 -->
            <div class="w-full">
                <!--<a href="https://vrcimg.hatsune.app" target="_blank" rel="noopener noreferrer">-->
                    <img src="https://vrcimg.hatsune.app/jd.png"
                        alt="유저 배너"
                        class="w-full rounded-xl shadow-lg object-cover transition duration-300
                                hover:brightness-110 hover:shadow-[0_0_15px_rgba(59,130,246,0.6)]">
                    </div>
                <!--</a>-->
        </div>

        <div id="hover-card"
            class="fixed z-50 hidden pointer-events-none bg-transparent"
            style="left: 0; top: 0;">
        </div>
    `;


    const res = await fetch("/api/all-users");
    const users = await res.json();
    const list = document.getElementById("user-list");
    hoverCard = document.getElementById("hover-card");

    users.forEach(user => {
        const el = document.createElement("div");
        el.className = `user-box bg-white dark:bg-gray-800 text-gray-900 dark:text-white \
          rounded-xl shadow p-4 text-center cursor-pointer transition hover:scale-105`;
        el.innerHTML = `
            <div class="aspect-square w-full relative rounded-xl overflow-hidden border border-gray-300 dark:border-gray-600">
                <img src="${user.img}" alt="${user.nickname}" 
                    class="absolute inset-0 w-full h-full object-cover">
            </div>
            <div class="font-semibold mt-2 truncate">${user.nickname}</div>
            `;

        el.addEventListener("mouseenter", async (e) => {
            try {
                const res = await fetch(`/api/user-details?nickname=${encodeURIComponent(user.nickname)}`);
                const p = await res.json();

                const maxAchievements = 5;
                const shown = p.achievements.slice(0, maxAchievements);
                const restCount = p.achievements.length - maxAchievements;

                const achHtml = shown.map(ach => `
                    <div class="relative group">
                        <img src="/static/achievements/a_${ach.name}.png" alt="${ach.name} 아이콘"
                             class="w-8 h-8 rounded object-cover border border-gray-300 dark:border-gray-600 cursor-pointer">
                        <div class="absolute left-1/2 -translate-x-1/2 bottom-full mb-2
                                    bg-blue-100 dark:bg-blue-950 text-gray-800 dark:text-white text-xs px-4 py-3 rounded-xl
                                    border border-blue-300 dark:border-blue-700 shadow-lg
                                    opacity-0 group-hover:opacity-100 transition-opacity duration-200
                                    pointer-events-none z-50 text-center min-w-[20rem] max-w-[26rem] whitespace-normal">
                            <div class="font-bold text-blue-900 dark:text-blue-300 text-xs">
                                ${ach.name} (${ach.achieved_at})
                            </div>
                            <div class="mt-2 flex flex-col gap-1">
                                ${ach.description.split(",,,").map((part, i) => `
                                    <div class="text-[11px] leading-snug ${i > 0 ? 'italic' : ''} text-blue-${i > 0 ? '500' : '400'} dark:text-blue-${i > 0 ? '500' : '400'}">
                                        ${part.trim()}
                                    </div>
                                `).join("")}
                            </div>
                        </div>
                    </div>
                `).join("");

                const showMoreHtml = restCount > 0 ? `
                    <div class="w-8 h-8 flex items-center justify-center bg-gray-200 dark:bg-gray-700 rounded text-sm text-gray-600 dark:text-gray-300">
                        +${restCount}
                    </div>
                ` : "";

                const totalSec = p.play_duration_sec || 0;
                const hours = Math.floor(totalSec / 3600);
                const minutes = Math.floor((totalSec % 3600) / 60);
                const playTime = `${hours}시간 ${minutes}분`;

                const safe = (val, fallback = "없음") => val ?? fallback;

                hoverCard.innerHTML = `
                <div class="bg-blue-100 dark:bg-blue-950 text-sm text-gray-800 dark:text-white 
                            border border-blue-300 dark:border-blue-700 
                            rounded-xl shadow-xl w-80 overflow-hidden">
                    
                    <!-- ✅ 이미지가 카드 상단에 딱 붙도록 -->
                    <div class="w-full h-24">
                        <img src="${safe(user.img, '/static/profiles/default.png')}" alt="${safe(user.nickname)} 프로필"
                            class="w-full h-full object-cover object-[center_60%]">
                    </div>

                    <!-- ✅ 본문 padding은 여기서 시작 -->
                    <div class="p-4">
                        <div class="text-lg font-semibold text-gray-800 dark:text-white">${safe(user.nickname)}</div>
                        <div class="text-gray-600 dark:text-gray-300 text-sm">${safe(user.comment)}</div>
                        
                        <div class="flex space-x-2 mt-2">
                            ${achHtml}
                            ${showMoreHtml}
                        </div>

                        <div class="text-right text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap mt-2">
                            <div>누적 출석: <span class="font-medium text-gray-800 dark:text-white">${safe(user.total_count)}회</span></div>
                            <div>총 플레이: <span class="font-medium text-gray-800 dark:text-white">${safe(playTime)}</span></div>
                            <div class="text-xs">마지막 접속: ${safe(user.last_attended)}</div>
                        </div>

                        <canvas id="hoverChart" width="280" height="60" class="mt-4"></canvas>
                    </div>
                </div>
                `;


                hoverCard.style.display = "block";
                hoverCard.classList.remove("hidden");

                const labels = p.recent_30days.map(item => {
                    const [, month, day] = item.date.split("-");
                    return `${month}-${day}`;
                });

                const data = p.recent_30days.map(item => (item.duration_sec / 60).toFixed(1));

                const isDark = document.documentElement.classList.contains("dark");
                const canvas = document.getElementById("hoverChart");
                if (canvas) {
                    requestAnimationFrame(() => drawChart(canvas, labels, data, isDark));
                }
            } catch (e) {
                hoverCard.classList.add("hidden");
            }
        });

        el.addEventListener("mousemove", (e) => {
            const offset = 16;
            hoverCard.style.left = `${e.clientX + offset}px`;
            hoverCard.style.top = `${e.clientY + offset}px`;
        });

        el.addEventListener("mouseleave", () => {
            hoverCard.classList.add("hidden");
            hoverCard.innerHTML = "";
        });

        list.appendChild(el);
    });
}