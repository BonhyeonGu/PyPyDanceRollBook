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
    <div class="flex justify-between items-start mb-4">
        <h1 class="text-xl font-bold">출석 랭킹</h1>

        <div class="flex flex-col items-end space-y-1">
        <button id="rankingModeBtn" class="text-sm px-3 py-1 rounded bg-gray-300 dark:bg-gray-600 hover:bg-gray-400 dark:hover:bg-gray-500 transition">
            🗓️ 주간 랭킹
        </button>
        <div class="flex items-center gap-2" id="rankingOffsetControls">
            <button id="rankingPrevBtn" class="text-xs px-2 py-1 rounded bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition">⬅ 이전</button>
            <span id="rankingOffsetLabel" class="text-xs text-gray-600 dark:text-gray-300">이번 주</span>
            <button id="rankingNextBtn" class="text-xs px-2 py-1 rounded bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 transition">다음 ➡</button>
        </div>
        </div>
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
        <h2 class="text-xl font-bold mb-4">최근 인기곡 (30 days)</h2>
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
            <h3 class="text-lg font-bold mb-2">참여자 <span id="participant-count" class="text-gray-500 dark:text-gray-400">(0)</span></h3>
            <div id="participant-list" class="space-y-2"></div>
        </div>
        <div>
            <h3 class="text-lg font-bold mb-2">음악 <span id="music-count" class="text-gray-500 dark:text-gray-400">(0)</span></h3>
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
            const fakeChangeEvent = {
                target: calendarInput
            };
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

async function renderRankingList(mode = "total", offset = 0) {
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
        const res = await fetch(`/api/ranking-users?mode=${mode}&offset=${offset}`);
        const data = await res.json();
        const { users, start_date, end_date } = data;

        // ✅ 이 줄을 추가
        updateRankingOffsetLabel(start_date, end_date);



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
            userBox.dataset.userId = user.user_id; // ✅ 히든 스타 제외 처리를 위한 ID 속성 추가

            const maxAchievements = 3;
            const shown = user.achievements.slice(0, maxAchievements);
            const restCount = user.achievements.length - maxAchievements;

            const achievementsHtml = shown.map(ach => `
                <div class="relative group">
                    <img src="/static/achievements/a_${ach.name}.png"
                        alt="${ach.name} 아이콘"
                        class="w-8 h-8 rounded object-cover border border-gray-300 dark:border-gray-600 cursor-default">
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
let rankingOffset = 0;
const rankingModes = ["weekly", "monthly", "total"];
const rankingModeLabels = {
    weekly: "🗓️ 주간 랭킹",
    monthly: "📅 월간 랭킹",
    total: "🏆 누적 랭킹"
};

function updateRankingOffsetLabel(startDate, endDate) {
    const label = document.getElementById("rankingOffsetLabel");
    const controls = document.getElementById("rankingOffsetControls");

    if (!label || !controls) return;

    let offsetText = "";

    if (rankingMode === "weekly") {
        offsetText = rankingOffset === 0 ? "이번 주" : `${rankingOffset}주 전`;
        controls.style.visibility = "visible";
        controls.style.pointerEvents = "auto";
    } else if (rankingMode === "monthly") {
        offsetText = rankingOffset === 0 ? "이번 달" : `${rankingOffset}달 전`;
        controls.style.visibility = "visible";
        controls.style.pointerEvents = "auto";
    } else {
        offsetText = "전체 랭킹";
        controls.style.visibility = "hidden";      // 🔸 공간은 유지
        controls.style.pointerEvents = "none";     // 🔸 클릭 안됨
    }

    if (rankingMode === "weekly" || rankingMode === "monthly") {
        label.textContent = `${startDate} ~ ${endDate} (${offsetText})`;
    } else {
        label.textContent = offsetText;
    }
}


function setupRankingModeButton() {
    const modeBtn = document.getElementById("rankingModeBtn");

    if (!modeBtn) return;

    modeBtn.addEventListener("click", async () => {
        const currentIndex = rankingModes.indexOf(rankingMode);
        const nextIndex = (currentIndex + 1) % rankingModes.length;
        rankingMode = rankingModes[nextIndex];
        rankingOffset = 0;

        modeBtn.textContent = rankingModeLabels[rankingMode];

        const rankingUsers = await renderRankingList(rankingMode, rankingOffset);
        excludedUserIds = new Set(rankingUsers.map(u => u.user_id));
        await loadInitialThanksUsers([...excludedUserIds], rankingMode);
    });

    const prevBtn = document.getElementById("rankingPrevBtn");
    const nextBtn = document.getElementById("rankingNextBtn");

    if (prevBtn && nextBtn) {
        prevBtn.addEventListener("click", async () => {
            rankingOffset += 1;
            const rankingUsers = await renderRankingList(rankingMode, rankingOffset);
            excludedUserIds = new Set(rankingUsers.map(u => u.user_id));
            await loadInitialThanksUsers([...excludedUserIds], rankingMode);
        });

        nextBtn.addEventListener("click", async () => {
            if (rankingOffset > 0) {
                rankingOffset -= 1;
                const rankingUsers = await renderRankingList(rankingMode, rankingOffset);
                excludedUserIds = new Set(rankingUsers.map(u => u.user_id));
                await loadInitialThanksUsers([...excludedUserIds], rankingMode);
            }
        });
    }
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
            <img src="/static/achievements/a_${ach.name}.png" alt="${ach.name} 아이콘"
                class="w-8 h-8 rounded object-cover border border-gray-300 dark:border-gray-600" />
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

        // 애니메이션 효과 직접 스타일로 적용
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

const INSTANCE_USER = "Nine_Bones";

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
        const pCount = document.getElementById("participant-count");
        const mCount = document.getElementById("music-count");
        pList.innerHTML = "";
        mList.innerHTML = "";

        // ✅ HOST(방장) 제외 로직
        let renderParticipants = participants;
        let countLabel = `(${participants.length})`;

        if (
            Array.isArray(participants) &&
            participants.length > 0 &&
            typeof INSTANCE_USER === "string" &&
            participants[0]?.nickname === INSTANCE_USER
        ) {
            // 리스트에서는 첫 번째(방장) 유저 제외
            renderParticipants = participants.slice(1);

            // 카운트 변경
            countLabel = `(${participants.length - 1} + 1)`;
        }

        if (pCount) pCount.textContent = countLabel;
        if (mCount) mCount.textContent = `(${musics.length})`;

        if (renderParticipants.length === 0) {
            pList.innerHTML = "<div class='text-sm text-gray-500 dark:text-gray-400'>참여자가 없습니다.</div>";
        } else {
            renderParticipants.forEach((p) => {
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

            // 애니메이션
            el.style.opacity = "0";
            el.style.transform = "translateY(0.5rem)";
            el.style.transition = "opacity 0.4s ease, transform 0.4s ease";

            pList.appendChild(el);
            void el.offsetWidth;
            el.style.opacity = "1";
            el.style.transform = "translateY(0)";
            });

            setTimeout(() => {
            bindUserBoxEvents();
            }, 400);
        }

        // (음악 렌더링 로직은 기존 그대로)
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

            el.style.opacity = "0";
            el.style.transform = "translateY(0.5rem)";
            el.style.transition = "opacity 0.4s ease, transform 0.4s ease";

            mList.appendChild(el);
            void el.offsetWidth;
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



// 레이아웃/스크롤/도전과제 그리드/툴팁 CSS 주입 (최초 1회)
(function injectOnce() {
  if (document.getElementById("fixed-grid-and-scroll-style")) return;
  const s = document.createElement("style");
  s.id = "fixed-grid-and-scroll-style";
  s.textContent = `
  /* 고정 3-컬럼 레이아웃 */
  @media (min-width: 1024px) { .grid-3-fixed-lg { grid-template-columns: 20rem 1fr 22rem; } }

  /* 스크롤바 테마 + 레이아웃 쉬프트 방지 */
  .themed-scroll { scrollbar-width: thin; scrollbar-color: #9ca3af #e5e7eb; scrollbar-gutter: stable both-edges; }
  html.dark .themed-scroll { scrollbar-color: #6b7280 #1f2937; }
  .themed-scroll::-webkit-scrollbar { width: 8px; height: 8px; }
  .themed-scroll::-webkit-scrollbar-track { background: #e5e7eb; }
  .themed-scroll::-webkit-scrollbar-thumb { background: #9ca3af; border-radius: 9999px; }
  html.dark .themed-scroll::-webkit-scrollbar-track { background: #1f2937; }
  html.dark .themed-scroll::-webkit-scrollbar-thumb { background: #6b7280; }

  /* 도전과제 그리드: 좌우 여백(2px), md부터 3열 */
  .ach-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); column-gap: 1px; row-gap: 16px; place-items: center; }
  @media (min-width: 768px) { .ach-grid { grid-template-columns: repeat(3, minmax(0,1fr)); } }
  @media (min-width: 1024px) { .ach-grid { grid-template-columns: repeat(3, minmax(0,1fr)); } }

  /* 바디 포털 툴팁 */
  .ach-tooltip {
    position: fixed; z-index: 9999; pointer-events: none;
    background: #dbeafe; color: #111827; border: 1px solid #93c5fd;
    padding: 10px 14px; border-radius: 0.75rem; box-shadow: 0 10px 25px rgba(0,0,0,.2);
    max-width: 26rem; min-width: 18rem; white-space: normal; opacity: 0; transform: translateY(4px);
    transition: opacity .12s ease, transform .12s ease;
  }
  html.dark .ach-tooltip {
    background: #0B1C3A; color: white; border-color: #1e3a8a;
  }
  .ach-tooltip.show { opacity: 1; transform: translateY(0); }
  .ach-tooltip .title { font-weight: 700; font-size: 15px; margin-bottom: .35rem; }
  .ach-tooltip .line { font-size: 13px; line-height: 1.2; }
  .ach-tooltip .line.first { color: #1e40af; }
  html.dark .ach-tooltip .line.first { color: #93c5fd; }
  `;
  document.head.appendChild(s);
})();

// 포털 툴팁 유틸
function attachPortalTooltip(targetEl, title, descLines) {
  let tip = null;

  const buildHTML = () => {
    const lines = (descLines || []).map((t, i) =>
      `<div class="line ${i===0 ? 'first':''}">${t}</div>`).join("");
    return `<div class="title">${title}</div><div>${lines}</div>`;
  };

  const placeTip = (ev) => {
    if (!tip) return;
    const rect = targetEl.getBoundingClientRect();
    const vw = window.innerWidth, vh = window.innerHeight;

    // 기본: 아이콘 중심 상단에 8px 위로
    const tipRect = tip.getBoundingClientRect();
    let left = rect.left + rect.width/2 - tipRect.width/2;
    let top  = rect.top - tipRect.height - 8;

    // 화면 밖이면 보정
    const margin = 8;
    if (left < margin) left = margin;
    if (left + tipRect.width > vw - margin) left = vw - margin - tipRect.width;

    // 위쪽이 부족하면 아래로 띄우기
    if (top < margin) top = rect.bottom + 8;

    tip.style.left = `${Math.round(left)}px`;
    tip.style.top  = `${Math.round(top)}px`;
  };

  const onEnter = (ev) => {
    tip = document.createElement("div");
    tip.className = "ach-tooltip";
    tip.innerHTML = buildHTML();
    document.body.appendChild(tip);
    // 최초 배치 후 표시
    requestAnimationFrame(() => {
      placeTip(ev);
      tip.classList.add("show");
    });
    window.addEventListener("scroll", placeTip, true);
    window.addEventListener("resize", placeTip, true);
    targetEl.addEventListener("mousemove", placeTip, { passive: true });
  };

  const onLeave = () => {
    if (tip) {
      tip.remove();
      tip = null;
    }
    window.removeEventListener("scroll", placeTip, true);
    window.removeEventListener("resize", placeTip, true);
    targetEl.removeEventListener("mousemove", placeTip);
  };

  targetEl.addEventListener("mouseenter", onEnter);
  targetEl.addEventListener("mouseleave", onLeave);
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

    // 카드 컨테이너 (좌 이미지 풀블리드)
    const card = document.createElement("div");
    card.className = [
      "bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100",
      "rounded-2xl shadow overflow-hidden",
      "grid gap-0 grid-cols-1",
      "lg:grid-cols-3",
      "grid-3-fixed-lg"
    ].join(" ");

    // 좌: 프로필 (박스 높이 다소 낮춤)
    const leftCol = document.createElement("aside");
    leftCol.className = "flex flex-col";
    const avatarFrame = document.createElement("div");
    avatarFrame.className = "w-full h-56 sm:h-72 lg:h-[24rem] xl:h-[28rem] bg-gray-200 dark:bg-gray-700 overflow-hidden";
    const avatar = document.createElement("img");
    avatar.src = p.img || "/static/profiles/default.png";
    avatar.onerror = function(){ this.src = "/static/profiles/default.png"; };
    avatar.alt = `${p.nickname} 프로필`;
    avatar.className = "w-full h-full object-cover object-[50%_center] block";
    avatarFrame.appendChild(avatar);
    leftCol.appendChild(avatarFrame);

    // 중: 이름/소개/6 정보/차트
    const centerCol = document.createElement("section");
    centerCol.className = "flex flex-col gap-4 min-w-0 p-3 sm:p-4 lg:p-6";

    const header = document.createElement("div");
    header.innerHTML = `
      <h3 class="text-2xl sm:text-3xl font-extrabold tracking-tight">${p.nickname}</h3>
      <p class="text-gray-500 dark:text-gray-400 italic mt-1">${p.comment || "한줄 소개 없음"}</p>
    `;
    centerCol.appendChild(header);

    const totalSec = p.play_duration_sec || 0;
    const hours = Math.floor(totalSec / 3600);
    const minutes = Math.floor((totalSec % 3600) / 60);
    const formattedPlayTime = `${hours}시간 ${minutes}분`;
    const monthlyTopN = p.topn_monthly_count_excl_current ?? 0;
    const weeklyTopN  = p.topn_weekly_count_excl_current ?? 0;

    // ✅ 월간 랭킹 ↔ 최근 접속 자리 교체 (월간랭킹을 3번째, 최근접속을 5번째로)
    const infoGrid = document.createElement("div");
    infoGrid.className = "grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3";
    infoGrid.innerHTML = `
      <div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900/40">
        <div class="text-sm text-gray-500 dark:text-gray-400">누적 출석</div>
        <div class="text-lg sm:text-xl font-semibold mt-1">${p.total_count}회</div>
      </div>
      <div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900/40">
        <div class="text-sm text-gray-500 dark:text-gray-400">총 플레이</div>
        <div class="text-lg sm:text-xl font-semibold mt-1">${formattedPlayTime}</div>
      </div>
      <!-- ③ 월간 랭킹 -->
      <div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900/40">
        <div class="text-sm text-gray-500 dark:text-gray-400">월간 랭킹(Top5)</div>
        <div class="text-lg sm:text-xl font-semibold mt-1">${monthlyTopN}회</div>
      </div>
      <div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900/40">
        <div class="text-sm text-gray-500 dark:text-gray-400">곡 선택</div>
        <div class="text-lg sm:text-xl font-semibold mt-1">${p.song_play_count || 0}회</div>
      </div>
      <!-- ⑤ 최근 접속 -->
      <div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900/40">
        <div class="text-sm text-gray-500 dark:text-gray-400">최근 접속</div>
        <div class="text-sm sm:text-xl font-semibold mt-1">${p.last_attended || "기록 없음"}</div>
      </div>
      <div class="p-3 rounded-xl bg-gray-50 dark:bg-gray-900/40">
        <div class="text-sm text-gray-500 dark:text-gray-400">주간 랭킹(Top5)</div>
        <div class="text-lg sm:text-xl font-semibold mt-1">${weeklyTopN}회</div>
      </div>
    `;
    centerCol.appendChild(infoGrid);

    if (p.recent_30days && p.recent_30days.length) {
      const chartWrapper = document.createElement("div");
      chartWrapper.className = "mt-1.5 w-full";
      const canvas = document.createElement("canvas");
      canvas.id = "durationChart";
      canvas.className = "w-full";
      canvas.height = 52;
      chartWrapper.appendChild(canvas);
      centerCol.appendChild(chartWrapper);

      const labels = p.recent_30days.map(it => { const [, m, d] = it.date.split("-"); return `${m}-${d}`; });
      const data = p.recent_30days.map(it => (it.duration_sec / 60).toFixed(1));
      const isDark = document.documentElement.classList.contains("dark");
      drawChart(canvas, labels, data, isDark);
    }

    // 우: 도전과제 (더 촘촘/작은 아이콘/3열, 포털 툴팁)
    const rightCol = document.createElement("aside");
    rightCol.className = "flex flex-col gap-2 min-w-0 p-3 sm:p-4 lg:p-6 lg:max-h-[28rem] overflow-auto themed-scroll";

    const achs = p.achievements || [];
    if (achs.length) {
      const achHeader = document.createElement("h4");
      achHeader.className = "text-base sm:text-lg font-semibold";
      achHeader.textContent = "도전과제";
      rightCol.appendChild(achHeader);

      const achGrid = document.createElement("div");
      achGrid.className = "ach-grid"; // ← 주입한 CSS 사용 (3열, 가로 2px)

      achs.forEach(ach => {
        const achDiv = document.createElement("div");
        achDiv.className = "relative";

        // 설명 라인
        const descLines = (ach.description || "").split(",,,").map(s => s.trim()).filter(Boolean);

        // 아이콘 (64px)
        const img = document.createElement("img");
        img.src = `/static/achievements/a_${ach.name}.png`;
        img.alt = `${ach.name} 아이콘`;
        img.className = "w-16 h-16 rounded object-cover border border-gray-300 dark:border-gray-600 cursor-default";

        // 포털 툴팁 부착 (카드/검색영역 경계 밖으로도 보임)
        const title = `${ach.name} (${ach.achieved_at})`;
        attachPortalTooltip(img, title, descLines);

        achDiv.appendChild(img);
        achGrid.appendChild(achDiv);
      });

      rightCol.appendChild(achGrid);
    } else {
      const noAch = document.createElement("div");
      noAch.className = "text-sm text-gray-500 dark:text-gray-400";
      noAch.textContent = "도전과제가 없습니다.";
      rightCol.appendChild(noAch);
    }

    // 조립
    card.appendChild(leftCol);
    card.appendChild(centerCol);
    card.appendChild(rightCol);

    // 페이드인
    card.style.opacity = "0";
    card.style.transform = "translateY(0.5rem)";
    card.style.transition = "opacity 0.4s ease, transform 0.4s ease";
    resultBox.appendChild(card);
    card.getBoundingClientRect();
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