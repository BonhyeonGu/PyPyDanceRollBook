// main.js

import {
    onThemeChange
} from "/static/js/theme.js";


let excludedUserIds = new Set();

export async function initMain() {
    excludedUserIds = new Set();
    const app = document.getElementById("app");
    if (!app) return;

    // 🔸 콘텐츠는 처음에 비가시 상태로 삽입됨
    app.innerHTML = `
    <div id="main-content" class="opacity-0 translate-y-2 transition-all duration-500">
      <div class="flex justify-between items-center mb-4">
        <h1 class="text-xl font-bold">출석 랭킹</h1>
        <button id="rankingModeBtn" class="text-sm px-3 py-1 rounded bg-gray-300 dark:bg-gray-600 hover:bg-gray-400 dark:hover:bg-gray-500 transition">
          🗓️ 주간 랭킹
        </button>
      </div>
      <div id="ranking-list" class="space-y-4 mt-8"></div>

      <div class="mt-16">
        <div class="flex justify-between items-center mb-4">
          <h2 class="text-xl font-bold">히든 스타</h2>
          <button id="refreshThanksBtn" class="text-sm px-3 py-1 rounded bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition">
            🔄
          </button>
        </div>
        <div id="thanks-list" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
      </div>

      <div class="mt-16">
        <h2 class="text-xl font-bold mb-4">최근 인기곡 (7 days)</h2>
        <div id="popular-music" class="grid grid-cols-2 md:grid-cols-5 gap-4"></div>
      </div>

      <div class="mt-16">
        <h2 class="text-xl font-bold mb-2">유저 검색</h2>
        <div class="flex space-x-2">
          <input id="searchInput" type="text" placeholder="닉네임 입력..." class="flex-1 border px-4 py-2 rounded bg-white dark:bg-gray-800 text-gray-800 dark:text-white border-gray-300 dark:border-gray-600 transition-colors duration-300" />
          <button id="searchBtn" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded transition">검색</button>
        </div>
        <div id="searchResult" class="mt-4 mb-4"></div>
      </div>

      <div class="mt-16">
        <h2 class="text-xl font-semibold mb-4">날짜별 참여자 및 재생 음악 보기</h2>
        <input type="date" id="calendar" class="border px-4 py-2 rounded mb-4 bg-white dark:bg-gray-800 text-gray-800 dark:text-white border-gray-300 dark:border-gray-600 transition-colors duration-300">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6" id="day-results">
          <div>
            <h3 class="text-lg font-bold mb-2">참여자</h3>
            <div id="participant-list" class="space-y-2"></div>
          </div>
          <div>
            <h3 class="text-lg font-bold mb-2">음악</h3>
            <div id="music-list" class="space-y-2"></div>
          </div>
        </div>
      </div>
    </div>
  `;

    const searchBtn = document.getElementById("searchBtn");
    const searchInput = document.getElementById("searchInput");
    if (searchBtn && searchInput) {
        searchBtn.addEventListener("click", searchUser);
        searchInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") searchUser();
        });
    }

    try {
        setupRankingModeButton(); // 버튼 먼저 설정

        // 🔹 주간 랭킹 유저를 불러오고 ID 목록 추출
        const rankingUsers = await renderRankingList("weekly");
        const excludedIds = rankingUsers.map(u => u.user_id);
        excludedUserIds = new Set(excludedIds);

        // 🔹 히든 스타 초기 로딩 시, 제외된 ID 기반
        await loadInitialThanksUsers(excludedIds, "weekly");

        setupRefreshThanksButton();
        await renderPopularMusic();

        const calendarInput = document.getElementById("calendar");
        if (calendarInput) {
            const yesterday = new Date();
            yesterday.setDate(yesterday.getDate() - 1);
            const yyyy = yesterday.getFullYear();
            const mm = String(yesterday.getMonth() + 1).padStart(2, '0');
            const dd = String(yesterday.getDate()).padStart(2, '0');
            calendarInput.value = `${yyyy}-${mm}-${dd}`;

            // 🔹 어제 날짜에 해당하는 데이터 자동 로딩
            const fakeChangeEvent = { target: calendarInput };
            setupCalendarEvent(); // 먼저 이벤트 바인딩
            calendarInput.dispatchEvent(new Event('change')); // change 이벤트 트리거
        }

        const content = document.getElementById("main-content");
        if (content) {
            content.classList.remove("opacity-0", "translate-y-2");
            content.classList.add("opacity-100", "translate-y-0");
        }
    } catch (err) {
        console.error("초기화 실패:", err);
    }
}


const PROFILE_BASE = "/static/profiles";

let currentChart = null;

onThemeChange((isDark) => {
    if (currentChart && currentChart.canvas) {
        const canvas = currentChart.canvas;
        const labels = currentChart.data.labels;
        const data = currentChart.data.datasets[0].data;
        drawChart(canvas, labels, data, isDark);
    }
});

function bindUserBoxEvents() {
    document.querySelectorAll(".user-box").forEach(box => {
        // 먼저 기존 이벤트 완전히 제거
        const cloned = box.cloneNode(true);
        box.replaceWith(cloned);
    });

    document.querySelectorAll(".user-box").forEach(box => {
        box.addEventListener("click", () => {
            const nickname = box.dataset.nickname;
            const input = document.getElementById("searchInput");

            input.value = nickname;
            searchUser();

            const targetY = input.getBoundingClientRect().top + window.scrollY - 100;
            smoothScrollTo(targetY);
        });
    });
}


function showToast(message) {
    const toast = document.getElementById("copyToast");
    if (!toast) return;

    // 텍스트 지정
    toast.textContent = message;

    // 기존 class 제거
    toast.classList.remove("opacity-0", "pointer-events-none");

    // 스타일 설정 강제 초기화
    toast.style.transition = "opacity 0.3s ease";
    toast.style.opacity = "1";
    toast.style.pointerEvents = "auto";

    // 기존 timeout 제거를 위한 보조: 여러 호출 대비
    clearTimeout(toast._hideTimer);

    // 일정 시간 후 숨김 처리
    toast._hideTimer = setTimeout(() => {
        toast.classList.add("opacity-0", "pointer-events-none");
        toast.style.opacity = "0";
        toast.style.pointerEvents = "none";
    }, 1500);
}


//=================================================================================================================================

async function renderRankingList(mode = "total") {
    const container = document.getElementById("ranking-list");

    // 🔸 현재 높이 기억
    const originalHeight = container.offsetHeight;
    container.style.minHeight = originalHeight + "px";

    container.style.transition = "opacity 0.3s ease";
    container.style.opacity = "0";
    await new Promise(resolve => setTimeout(resolve, 300));

    container.innerHTML = "";
    container.style.opacity = "1";

    try {
        const res = await fetch(`/api/ranking-users?mode=${mode}`);
        const users = await res.json();

        // 🔸 순위 값 직접 부여
        users.forEach((u, i) => u.rank = i + 1);
        // ✅ 유저 없을 경우 안내 메시지 표시
        if (users.length === 0) {
            container.innerHTML = `
                <div class="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
                    현재 기간에 기록된 출석 정보가 없습니다.
                </div>
            `;
            setTimeout(() => {
                container.style.minHeight = "";
            }, 300);
            return [];
        }

        // 🔸 출석 텍스트 라벨
        const attendanceLabel =
            mode === "weekly" ? "주간 출석" :
            mode === "monthly" ? "월간 출석" :
            "누적 출석";

        users.forEach(user => {
            const userBox = document.createElement("div");
            userBox.className = `
                user-box bg-white dark:bg-gray-800 rounded-xl shadow p-4 flex items-center space-x-6
                hover:shadow-lg transition-colors duration-300
            `;
            userBox.dataset.nickname = user.nickname;
            userBox.dataset.userId = user.user_id;  // ✅ 히든 스타 제외 처리를 위한 ID 속성 추가

            const maxAchievements = 3;
            const shown = user.achievements.slice(0, maxAchievements);
            const restCount = user.achievements.length - maxAchievements;

            const achievementsHtml = shown.map(ach => `
                <div class="relative group">
                    <img src="/static/achievements/a_${ach.name}.png"
                        alt="${ach.name} 아이콘"
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
                            ${ach.description.split(",").map((part, i) => `
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

            userBox.innerHTML = `
                <div class="text-2xl font-bold w-8 text-gray-500 dark:text-gray-300 text-center">#${user.rank}</div>

                <img src="${user.img}" alt="${user.nickname} 프로필"
                    class="w-16 h-16 rounded-full object-cover border border-gray-300 dark:border-gray-600 shadow-sm">

                <div class="flex-1">
                    <div class="text-lg font-semibold text-gray-800 dark:text-white">${user.nickname}</div>
                    <div class="text-gray-500 dark:text-gray-300 text-sm">${user.comment || '한줄 소개 없음'}</div>
                </div>

                <div class="flex space-x-2">
                    ${achievementsHtml}
                    ${showMoreHtml}
                </div>

                <div class="text-right text-sm text-gray-600 dark:text-gray-300 whitespace-nowrap">
                    <div>${attendanceLabel}: <span class="font-medium text-gray-800 dark:text-white">${user.total_count}</span>회</div>
                    <div class="text-xs">마지막 접속: ${user.last_attended}</div>
                </div>
            `;

            container.appendChild(userBox);
        });

        bindUserBoxEvents();
        setTimeout(() => {
            container.style.minHeight = "";
        }, 300);

        return users;
    } catch (err) {
        container.innerHTML = `<div class="text-red-500">랭킹 정보를 불러오지 못했습니다.</div>`;
        console.error("랭킹 로드 오류:", err);
    }
}





let rankingMode = "weekly";
const rankingModes = ["weekly", "monthly", "total"];
const rankingModeLabels = {
    weekly: "🗓️ 주간 랭킹",
    monthly: "📅 월간 랭킹",
    total: "🏆 누적 랭킹"
};

function setupRankingModeButton() {
    const btn = document.getElementById("rankingModeBtn");
    if (!btn) return;

    btn.addEventListener("click", async () => {
        const content = document.getElementById("main-content");

        // 🔸 전환 애니메이션 시작
        if (content) {
            content.classList.add("opacity-0", "translate-y-2");
            await new Promise(resolve => setTimeout(resolve, 300));
        }

        const nextIndex = (rankingModes.indexOf(rankingMode) + 1) % rankingModes.length;
        rankingMode = rankingModes[nextIndex];
        btn.textContent = rankingModeLabels[rankingMode];

        // ✅ 리셋
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = "🔄";
        }

        excludedUserIds = new Set();
        const rankingUsers = await renderRankingList(rankingMode);
        const excludedIds = rankingUsers.map(u => u.user_id);
        excludedUserIds = new Set(excludedIds);

        await loadInitialThanksUsers(excludedIds, rankingMode);

        // 🔸 전환 애니메이션 종료
        if (content) {
            content.classList.remove("opacity-0", "translate-y-2");
            content.classList.add("opacity-100", "translate-y-0");
        }
    });
}




//=================================================================================================================================

let refreshBtn = null;


function renderThanksUsers(users) {
    const container = document.getElementById("thanks-list");
    container.innerHTML = "";

    users.forEach(user => {
        const box = document.createElement("div");
        box.className = `
      user-box bg-white dark:bg-gray-800 rounded-xl shadow p-4 flex items-center justify-between space-x-4
      hover:shadow-lg transition-colors duration-300
    `.trim();
        box.dataset.nickname = user.nickname;
        box.dataset.userId = user.user_id;

        const maxAchievements = 2;
        const shown = user.achievements.slice(0, maxAchievements);
        const restCount = user.achievements.length - maxAchievements;

        const achievementsHtml = shown.map(ach => `
      <div class="relative group">
        <img src="/static/achievements/a_${ach.name}.png" alt="${ach.name} 아이콘"
          class="w-8 h-8 rounded object-cover border border-gray-300 dark:border-gray-600 cursor-pointer">
        <div class="absolute left-1/2 -translate-x-1/2 bottom-full mb-2
                    bg-blue-100 dark:bg-blue-950 text-gray-800 dark:text-white text-xs px-4 py-3 rounded-xl
                    border border-blue-300 dark:border-blue-700 shadow-lg
                    opacity-0 group-hover:opacity-100 transition-opacity duration-200
                    pointer-events-none z-50 text-center min-w-[20rem] max-w-[26rem] whitespace-normal">
          <div class="font-bold text-blue-900 dark:text-blue-300 text-xs">${ach.name} (${ach.achieved_at})</div>
          <div class="mt-2 flex flex-col gap-1">
            ${ach.description.split(",").map((part, idx) => `
              <div class="text-[11px] leading-snug ${idx > 0 ? 'italic' : ''} text-blue-${idx === 0 ? '400' : '500'} dark:text-blue-${idx === 0 ? '400' : '500'}">
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

        box.innerHTML = `
      <img src="${user.img}" alt="${user.nickname} 프로필"
          class="w-16 h-16 rounded-full object-cover border border-gray-300 dark:border-gray-600 shadow-sm">

      <div class="flex-1">
          <div class="text-lg font-semibold text-gray-800 dark:text-white">${user.nickname}</div>
          <div class="text-gray-500 dark:text-gray-300 text-sm">${user.comment || '한줄 소개 없음'}</div>
          <div class="text-sm text-gray-600 dark:text-gray-300 mt-1">누적 출석: ${user.total_count}회</div>
          <div class="text-xs text-gray-600 dark:text-gray-300">마지막 접속: ${user.last_attended}</div>
      </div>

      <div class="flex flex-wrap gap-2 ml-4">
        ${achievementsHtml}
        ${showMoreHtml}
      </div>
    `;

        // ✅ 애니메이션 효과 직접 스타일로 적용
        box.style.opacity = "0";
        box.style.transform = "translateY(0.5rem)";
        box.style.transition = "opacity 0.4s ease, transform 0.4s ease";

        container.appendChild(box);
        void box.offsetWidth; // 강제 리플로우
        box.style.opacity = "1";
        box.style.transform = "translateY(0)";
    });
    setTimeout(() => {
        bindUserBoxEvents();
    }, 400); // transition과 동일 시간

}


async function loadInitialThanksUsers(initialUsers, mode = "weekly") {
    initialUsers.forEach(u => excludedUserIds.add(u.user_id));
    await loadRandomUsers(Array.from(excludedUserIds), mode);
}

async function loadRandomUsers(excludedIdList, mode = "weekly") {
    const container = document.getElementById("thanks-list");

    // 🔸 현재 화면에 표시된 유저 ID도 제외해야 함
    const displayedIds = Array.from(container.querySelectorAll(".user-box[data-user-id]"))
        .map(box => parseInt(box.dataset.userId));

    // 🔸 모든 제외 ID 합치고 중복 제거
    const allExcluded = Array.from(new Set([...excludedIdList, ...displayedIds]));

    const params = allExcluded.map(id => `excluded_ids=${encodeURIComponent(id)}`).join("&");
    const res = await fetch(`/api/random-users?mode=${mode}&${params}`);
    const users = await res.json();

    if (users.length === 0 && refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.textContent = "😴 더 없음";
        return;
    }

    users.forEach(u => excludedUserIds.add(u.user_id)); // 다시 중복 방지용 set에 반영
    renderThanksUsers(users);
}


function setupRefreshThanksButton() {
    const button = document.getElementById("refreshThanksBtn");
    if (!button) {
        console.warn("히든 스타 새로고침 버튼을 찾을 수 없습니다.");
        return;
    }
    refreshBtn = button;

    button.addEventListener("click", async () => {
        // 이미 표시된 유저 id를 모두 제외 ID Set에 추가
        const ids = Array.from(document.querySelectorAll(".user-box[data-user-id]"))
            .map(box => parseInt(box.dataset.userId));
        ids.forEach(id => excludedUserIds.add(id));

        await loadRandomUsers(Array.from(excludedUserIds));
    });
}

//=================================================================================================================================



//인기노래
async function renderPopularMusic() {
    const res = await fetch("/api/popular-music");
    const data = await res.json();
    const box = document.getElementById("popular-music");
    box.innerHTML = "";

    data.forEach((m, i) => {
        const wrapper = document.createElement("div");
        wrapper.className = "relative group";

        const card = document.createElement("div");
        card.className = `
          bg-white dark:bg-gray-800 text-gray-800 dark:text-white
          p-3 rounded shadow text-center text-sm truncate
          hover:shadow-lg cursor-pointer transition-colors duration-300
        `.trim();
        card.innerHTML = `
          <div class="font-semibold truncate">${m.title}</div>
          <div class="text-xs text-gray-500 dark:text-gray-300 mt-1">${m.count}회 재생</div>
        `;

        const tooltip = document.createElement("div");
        tooltip.className = `
          absolute left-1/2 -translate-x-1/2 bottom-full mb-2
          bg-gray-600 text-white text-sm px-4 py-2 rounded
          opacity-0 group-hover:opacity-100 transition-opacity duration-200
          pointer-events-none z-50 w-[320px] text-center
        `.trim();
        tooltip.textContent = m.title;

        // 클릭 시 클립보드 복사 + 토스트
        card.addEventListener("click", () => {
            navigator.clipboard.writeText(m.title).then(() => {
                showToast("제목이 복사되었습니다.");
            });
        });

        wrapper.appendChild(card);
        wrapper.appendChild(tooltip);
        box.appendChild(wrapper);
    });
}

//날짜 검색
function setupCalendarEvent() {
    const calendar = document.getElementById("calendar");
    if (!calendar) {
        console.warn("calendar 요소를 찾을 수 없습니다.");
        return;
    }

    calendar.addEventListener("change", async (e) => {
        const date = e.target.value;
        if (!date) return;

        const participantRes = await fetch(`/api/date/participants?date=${date}`);
        const musicRes = await fetch(`/api/date/music?date=${date}`);
        const participants = await participantRes.json();
        const musics = await musicRes.json();

        const pList = document.getElementById("participant-list");
        const mList = document.getElementById("music-list");
        pList.innerHTML = "";
        mList.innerHTML = "";

        if (participants.length === 0) {
            pList.innerHTML = "<div class='text-sm text-gray-500 dark:text-gray-400'>참여자가 없습니다.</div>";
        } else {
            participants.forEach((p) => {
                const el = document.createElement("div");
                el.className = `
          user-box bg-white dark:bg-gray-800 text-gray-800 dark:text-white
          rounded-xl shadow flex items-stretch gap-4
          transition-all duration-300 min-h-[110px] pl-0 pr-4
        `.trim();

                el.dataset.nickname = p.nickname;

                el.innerHTML = `
          <div class="h-[110px] w-[64px] overflow-hidden shrink-0 rounded-l-xl">
            <img src="${p.img}" alt="${p.nickname} 프로필"
                class="w-[84px] h-full object-cover object-[40%] border border-gray-300 dark:border-gray-600"
                onerror="this.src='${PROFILE_BASE}/default.png'">
          </div>

          <div class="flex-1 flex flex-col justify-center">
            <div class="font-semibold">${p.nickname}</div>
            <div class="text-sm text-gray-500 dark:text-gray-300">${p.comment || '한줄 소개 없음'}</div>
          </div>

          <div class="text-sm text-gray-700 dark:text-gray-300 text-right whitespace-nowrap self-center">
            누적 ${p.total_count}회<br>
            체류 ${p.duration}분
          </div>
        `;

                // 👇 애니메이션 적용
                el.style.opacity = "0";
                el.style.transform = "translateY(0.5rem)";
                el.style.transition = "opacity 0.4s ease, transform 0.4s ease";

                pList.appendChild(el);
                void el.offsetWidth; // 강제 리플로우
                el.style.opacity = "1";
                el.style.transform = "translateY(0)";
            });

            setTimeout(() => {
                bindUserBoxEvents();
            }, 400); // transition과 동일 시간
        }

        if (musics.length === 0) {
            mList.innerHTML = "<div class='text-sm text-gray-500 dark:text-gray-400'>재생된 음악이 없습니다.</div>";
        } else {
            musics.forEach(m => {
                const el = document.createElement("div");
                el.className = `
          bg-white dark:bg-gray-800 text-gray-800 dark:text-white
          rounded-xl shadow p-3 transition-all duration-300 min-h-[110px]
          relative group
        `.trim();

                el.innerHTML = `
          <div class="text-sm text-gray-500 dark:text-gray-300">${m.played_at}</div>
          <div class="font-semibold text-sm mt-1">${m.title}</div>
          <div class="text-sm text-gray-600 dark:text-gray-400">by ${m.user}</div>
          <div class="absolute top-2 right-2 flex gap-5">
            <button class="text-xs text-blue-500 hover:underline copy-title">이름 복사</button>
            <button class="text-xs text-blue-500 hover:underline copy-url">URL 복사</button>
          </div>
        `;

                el.querySelector(".copy-title").addEventListener("click", (e) => {
                    e.stopPropagation();
                    navigator.clipboard.writeText(m.title).then(() => showToast("제목이 복사되었습니다."));
                });

                el.querySelector(".copy-url").addEventListener("click", (e) => {
                    e.stopPropagation();
                    navigator.clipboard.writeText(m.url).then(() => showToast("URL이 복사되었습니다."));
                });

                // 👇 애니메이션 적용
                el.style.opacity = "0";
                el.style.transform = "translateY(0.5rem)";
                el.style.transition = "opacity 0.4s ease, transform 0.4s ease";

                mList.appendChild(el);
                void el.offsetWidth; // 강제 리플로우
                el.style.opacity = "1";
                el.style.transform = "translateY(0)";
            });
        }
    });
}



//=================================================================================================================================


function drawChart(canvas, labels, data, isDark) {
    const lineColor = isDark ? 'rgba(96,165,250,1)' : 'rgba(54,162,235,1)';
    const pointBg = isDark ? 'rgba(147,197,253,1)' : 'rgba(54,162,235,0.6)';
    const gridColor = isDark ? '#444' : '#ccc';
    const fontColor = isDark ? '#ddd' : '#333';

    if (currentChart) {
        currentChart.destroy();
    }

    currentChart = new Chart(canvas.getContext("2d"), {
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
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 80, // ✅ 최대값 고정
                    ticks: {
                        font: {
                            size: 10
                        },
                        color: fontColor
                    },
                    grid: {
                        color: gridColor
                    },
                    title: {
                        display: false
                    }
                },
                x: {
                    ticks: {
                        font: {
                            size: 10
                        },
                        color: fontColor
                    },
                    grid: {
                        color: gridColor
                    },
                    title: {
                        display: false
                    }
                }
            }
        }
    });
}


async function searchUser() {
    const name = document.getElementById("searchInput").value.trim();
    const resultBox = document.getElementById("searchResult");
    resultBox.innerHTML = "";

    if (!name) return;

    try {
        const res = await fetch(`/api/user-details?nickname=${encodeURIComponent(name)}`);
        if (!res.ok) throw new Error("유저를 찾을 수 없습니다");
        const p = await res.json();

        const card = document.createElement("div");
        card.className = "bg-white dark:bg-gray-800 text-gray-800 dark:text-white rounded-xl shadow p-6 transition-colors duration-300";

        const achLeft = document.createElement("div");
        achLeft.className = "flex flex-wrap justify-end gap-2 w-32";

        const achRight = document.createElement("div");
        achRight.className = "flex flex-wrap justify-start gap-2 w-32";

        const achs = p.achievements || [];
        const half = Math.ceil(achs.length / 2);

        achs.forEach((ach, i) => {
            const achDiv = document.createElement("div");
            achDiv.className = "relative group";

            const descLines = (ach.description || "").split(",").map(part => part.trim());
            const descHtml = descLines.map((line, i) =>
                `<div class="text-[13px] leading-snug ${i === 0 ? "text-blue-800 dark:text-blue-400" : "italic text-blue-800 dark:text-blue-500"}">${line}</div>`
            ).join("");

            achDiv.innerHTML = `
            <img src="/static/achievements/a_${ach.name}.png"
                alt="${ach.name} 아이콘"
                class="w-20 h-20 rounded object-cover border border-gray-300 dark:border-gray-600 cursor-pointer">
            <div class="absolute left-1/2 -translate-x-1/2 bottom-full mb-3
                        bg-blue-100 dark:bg-blue-950 text-gray-800 dark:text-white text-sm px-5 py-4 rounded-xl
                        border border-blue-300 dark:border-blue-700 shadow-lg
                        opacity-0 group-hover:opacity-100 transition-opacity duration-200
                        pointer-events-none z-50 text-center min-w-[22rem] max-w-[28rem] whitespace-normal">
              <div class="font-bold text-base text-blue-900 dark:text-blue-300">${ach.name} (${ach.achieved_at})</div>
              <div class="mt-2 flex flex-col gap-1">
                ${descHtml}
              </div>
            </div>
          `;

            if (i < half) {
                achLeft.appendChild(achDiv);
            } else {
                achRight.appendChild(achDiv);
            }
        });

        const infoDiv = document.createElement("div");
        infoDiv.className = "flex flex-col items-center text-center sm:px-4";

        const totalSec = p.play_duration_sec || 0;
        const hours = Math.floor(totalSec / 3600);
        const minutes = Math.floor((totalSec % 3600) / 60);
        const formattedPlayTime = `${hours}시간 ${minutes}분`;

        infoDiv.innerHTML = `
          <img src="${p.img}" onerror="this.src='/static/profiles/default.png'" 
              alt="${p.nickname} 프로필"
              class="w-52 h-52 rounded-full object-cover border-4 border-gray-300 dark:border-gray-600 mb-4" />
          <h3 class="text-2xl font-bold mb-2">${p.nickname}</h3>
          <p class="text-gray-500 italic mb-2">${p.comment || "한줄 소개 없음"}</p>
          <div class="flex justify-between flex-wrap gap-6 text-gray-800 dark:text-gray-200 text-base sm:text-lg w-full px-6 max-w-2xl translate-x-8">
            <div class="flex flex-col gap-1 text-left min-w-[12rem] sm:min-w-[14rem]">
              <p><strong>누적 출석:</strong> ${p.total_count}회</p>
              <p><strong>총 플레이:</strong> ${formattedPlayTime}</p>
            </div>
            <div class="flex flex-col gap-1 text-left min-w-[12rem] sm:min-w-[14rem]">
              <p><strong>최근 접속:</strong> ${p.last_attended || "기록 없음"}</p>
              <p><strong>곡 선택:</strong> ${p.song_play_count}회</p>
            </div>
          </div>
        `;

        const layout = document.createElement("div");
        layout.className = "flex flex-col items-center sm:flex-row sm:items-start sm:justify-center gap-4";
        layout.appendChild(achLeft);
        layout.appendChild(infoDiv);
        layout.appendChild(achRight);

        card.appendChild(layout);

        // ✅ 그래프 추가
        if (p.recent_30days && p.recent_30days.length) {
            const chartWrapper = document.createElement("div");
            chartWrapper.className = "mt-6 w-full max-w-3xl mx-auto";

            const canvas = document.createElement("canvas");
            canvas.id = "durationChart";
            canvas.className = "w-full";
            canvas.height = 60; // 실제 픽셀 높이

            chartWrapper.appendChild(canvas);
            card.appendChild(chartWrapper);

            const labels = p.recent_30days.map(item => {
                const [, month, day] = item.date.split("-");
                return `${month}-${day}`;
            });

            const data = p.recent_30days.map(item => (item.duration_sec / 60).toFixed(1));

            // ✅ 현재 테마 확인
            const isDark = document.documentElement.classList.contains("dark");
            drawChart(canvas, labels, data, isDark);

        }

        // ✅ 애니메이션 초기 클래스 삽입
        card.style.opacity = "0";
        card.style.transform = "translateY(0.5rem)";
        card.style.transition = "opacity 0.4s ease, transform 0.4s ease";
        resultBox.appendChild(card);

        // 강제 리플로우
        card.getBoundingClientRect(); // 또는 void card.offsetWidth;

        // 애니메이션 적용
        card.style.opacity = "1";
        card.style.transform = "translateY(0)";

    } catch (err) {
        resultBox.innerHTML = `<div class="text-sm text-red-500">[오류] ${err.message}</div>`;
    }
}


function smoothScrollTo(targetY, duration = 400) {
    const startY = window.scrollY;
    const startTime = performance.now();

    function step(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const ease = 0.5 * (1 - Math.cos(Math.PI * progress)); // easeInOut
        window.scrollTo(0, startY + (targetY - startY) * ease);

        if (progress < 1) requestAnimationFrame(step);
    }

    requestAnimationFrame(step);
}