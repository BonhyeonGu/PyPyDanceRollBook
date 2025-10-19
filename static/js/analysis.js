let chartInstances = {};

function drawLineChart(canvasId, labels, data, isDark, options = {}) {
    const lineColor = isDark ? 'rgba(96,165,250,1)' : 'rgba(54,162,235,1)';
    const pointBg = isDark ? 'rgba(147,197,253,1)' : 'rgba(54,162,235,0.6)';
    const gridColor = isDark ? '#444' : '#ccc';
    const fontColor = isDark ? '#ddd' : '#333';

    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
    }

    const chart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: options.label || '',
                data,
                fill: options.fill ?? false,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 5,
                borderColor: options.lineColor || lineColor,
                backgroundColor: options.pointBg || pointBg
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: options.showLegend ?? false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            return `${ctx.dataset.label || ''}: ${ctx.parsed.y}`;
                        }
                    }
                },
                // 안전장치: 전역 플러그인이 있어도 비활성화
                avatarPlugin: false,
                ...(options.plugins || {})
            },
            scales: {
                x: {
                    ticks: { font: { size: 10 }, color: fontColor },
                    grid: { color: gridColor }
                },
                y: {
                    beginAtZero: true,
                    ticks: { font: { size: 10 }, color: fontColor },
                    grid: { color: gridColor }
                }
            },
            elements: {
                point: {
                    radius: function(context) {
                        const index = context.dataIndex;
                        const value = context.dataset.data[index];
                        const min = Math.min(...context.dataset.data);
                        const max = Math.max(...context.dataset.data);
                        return (value === min || value === max) ? 6 : 3;
                    }
                }
            },
            animation: {
                onComplete: function({ chart }) {
                    const ctx = chart.ctx;
                    const dataset = chart.data.datasets[0];
                    const meta = chart.getDatasetMeta(0);
                    const font = Chart.defaults.font;
                    ctx.save();
                    ctx.font = `${font.size}px ${font.family}`;
                    ctx.fillStyle = fontColor;

                    const data = dataset.data;
                    const min = Math.min(...data);
                    const max = Math.max(...data);
                    const minIndex = data.indexOf(min);
                    const maxIndex = data.indexOf(max);

                    [minIndex, maxIndex].forEach(i => {
                        const point = meta.data[i];
                        const value = data[i];
                        if (point) {
                            ctx.fillText(`${value}`, point.x + 4, point.y - 6);
                        }
                    });

                    ctx.restore();
                }
            }
        }
    });

    chartInstances[canvasId] = chart;
}

function drawBarChart(canvasId, labels, data, isDark) {
    const barColor = isDark ? 'rgba(96,165,250,0.8)' : 'rgba(54,162,235,0.8)';
    const borderColor = isDark ? 'rgba(96,165,250,1)' : 'rgba(54,162,235,1)';
    const gridColor = isDark ? '#444' : '#ccc';
    const fontColor = isDark ? '#ddd' : '#333';

    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext("2d");

    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
    }

    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: "평균 출석 횟수",
                data: data,
                backgroundColor: barColor,
                borderColor: borderColor,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { labels: { color: fontColor } },
                tooltip: {
                    callbacks: { label: context => `${context.parsed.y} 회` }
                },
                // 안전장치: 전역 플러그인이 있어도 비활성화
                avatarPlugin: false
            },
            scales: {
                x: { ticks: { color: fontColor }, grid: { color: gridColor } },
                y: { beginAtZero: true, ticks: { color: fontColor }, grid: { color: gridColor } }
            }
        }
    });

    chartInstances[canvasId] = chart;
}

function drawHorizontalBarChartWithAvatars(canvasId, items, isDark, options = {}) {
    // items: [{ nickname, value, img }]
    const barColor = isDark ? 'rgba(147,197,253,0.9)' : 'rgba(54,162,235,0.9)';
    const borderColor = isDark ? 'rgba(96,165,250,1)' : 'rgba(54,162,235,1)';
    const gridColor = isDark ? '#444' : '#ccc';
    const fontColor = isDark ? '#ddd' : '#333';

    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    // 부모 박스 크기에 맞춰 캔버스 크기 강제 (무한 확장 방지 + 반응형 높이 지원)
    const parent = canvas.parentElement;
    const parentWidth = parent ? parent.clientWidth : undefined;
    const parentHeight = parent ? parent.clientHeight : 360;
    if (parentWidth) canvas.width = parentWidth;
    canvas.height = parentHeight;

    const ctx = canvas.getContext("2d");

    if (chartInstances[canvasId]) {
        chartInstances[canvasId].destroy();
    }

    // 데이터 정리: 숫자만, 내림차순
    const sorted = (items || [])
        .filter(it => typeof it.value === 'number' && !Number.isNaN(it.value))
        .sort((a, b) => b.value - a.value);

    if (sorted.length === 0) {
        // 데이터 없음: 그냥 반환
        return;
    }

    const topN = options.topN && options.topN > 0 ? options.topN : null;
    const top = topN ? sorted.slice(0, topN) : sorted;

    const labels = top.map(it => it.nickname || '');
    const data = top.map(it => it.value);

    // 아바타 이미지 미리 로드
    top.forEach(it => {
        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.src = it.img || options.defaultAvatar || '';
        it._imgObj = img;
    });

    // 이름-프사 간 간격과 프사 크기
    const size = options.avatarSize || 28;
    const gap = (options.avatarLabelGap ?? 12);

    // 로컬 플러그인: y축 라벨 왼쪽에 아바타 그리기 (라벨과 겹침 방지)
    const avatarPlugin = {
        id: 'avatarPlugin',
        afterDraw(chart) {
            if (chart.canvas.id !== canvasId) return;
            const scaleY = chart.scales.y;
            if (!scaleY) return;

            const c = chart.ctx;
            // 라벨 영역의 왼쪽 기준으로 프사를 더 왼쪽에 배치
            const xLeft = scaleY.left - size - gap;

            c.save();
            for (let i = 0; i < top.length; i++) {
                const yPos = scaleY.getPixelForTick(i);
                const img = top[i]._imgObj;
                if (img && img.complete && img.naturalWidth > 0) {
                    c.drawImage(img, xLeft, yPos - size / 2, size, size);
                } else {
                    // fallback: 원형 + 이니셜
                    c.beginPath();
                    c.arc(xLeft + size / 2, yPos, size / 2, 0, Math.PI * 2);
                    c.fillStyle = isDark ? '#555' : '#ddd';
                    c.fill();
                    const name = labels[i];
                    const initial = (name && name.trim()[0]) || '?';
                    c.fillStyle = isDark ? '#eee' : '#333';
                    c.font = `bold ${Math.floor(size * 0.5)}px system-ui, -apple-system, Segoe UI, Roboto`;
                    c.textAlign = 'center';
                    c.textBaseline = 'middle';
                    c.fillText(initial, xLeft + size / 2, yPos);
                }
            }
            c.restore();
        }
    };

    const chart = new Chart(ctx, {
        type: 'bar',
        plugins: [avatarPlugin], // 이 차트에서만 아바타 플러그인 사용
        data: {
            labels,
            datasets: [{
                label: options.label || '그룹 상관계수(r)',
                data,
                backgroundColor: barColor,
                borderColor: borderColor,
                borderWidth: 1
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                // 아바타 크기 + 라벨과의 간격 + 여유만큼 왼쪽 패딩 확보
                padding: {
                    left: size + gap + 8,
                    top: options.topPadding || 0
                }
            },
            plugins: {
                legend: { display: options.showLegend ?? false },
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const v = typeof ctx.parsed.x === 'number' ? ctx.parsed.x : ctx.parsed.y;
                            return `${ctx.dataset.label || ''}: ${typeof v === 'number' ? v.toFixed(3) : v}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    ticks: { color: fontColor },
                    grid: { color: gridColor, borderColor: gridColor }
                },
                y: {
                    ticks: { color: fontColor, font: { size: 11 } },
                    grid: { color: gridColor, borderColor: gridColor }
                }
            }
        }
    });

    // 이미지가 늦게 로드되어도 다시 그리기
    top.forEach(it => {
        if (it._imgObj) {
            it._imgObj.onload = () => chart.draw();
        }
    });

    chartInstances[canvasId] = chart;
}


function drawLoveGraph(elements, isDark) {
    const container = document.getElementById('loveGraph');
    if (!container) return;

    container.innerHTML = ''; // 기존 그래프 제거

    cytoscape({
        container: container,
        elements: elements,
        layout: { name: 'cose', padding: 20 },
        style: [
            {
                selector: 'node',
                style: {
                    'label': 'data(label)',
                    'background-image': 'data(img)',
                    'background-fit': 'cover',
                    'background-color': '#999',
                    'color': isDark ? '#fff' : '#111',
                    'text-valign': 'bottom',
                    'text-halign': 'center',
                    'font-size': 7,
                    'text-margin-y': 2,
                    'width': 50,
                    'height': 50
                }
            },
            {
                selector: 'edge',
                style: {
                    'width': 1,
                    'line-color': isDark ? '#aaa' : '#ccc',
                    'curve-style': 'bezier',
                    'label': 'data(label)',
                    'font-size': 8,
                    'text-background-color': isDark ? '#333' : '#eee',
                    'text-background-opacity': 1,
                    'text-background-padding': 2,
                    'text-margin-y': -4,
                    'color': isDark ? '#fff' : '#000',
                    'text-rotation': 'autorotate'
                }
            },
            {
                selector: 'edge.highlight',
                style: {
                    'width': 3,
                    'line-color': isDark ? '#f87171' : '#dc2626',
                    'label': 'data(label)',
                    'font-size': 8,
                    'text-background-color': isDark ? '#333' : '#eee',
                    'text-background-opacity': 1,
                    'text-background-padding': 2,
                    'text-margin-y': -4,
                    'color': isDark ? '#fff' : '#000',
                    'text-rotation': 'autorotate'
                }
            }
        ]
    });
}

export async function renderAnalysisPage() {
    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
        <h1 class="text-2xl font-bold mb-6">분석</h1>
        <div class="text-sm text-gray-600 dark:text-gray-300 mb-8">
            최근 90일 동안의 데이터를 분석합니다.
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 items-start justify-center">
            <div class="flex flex-col items-center col-span-1 md:col-span-2">
                <h2 class="text-lg font-semibold mb-2 text-gray-800 dark:text-white">참여자 친밀도 추정</h2>
                <div id="loveGraph" class="w-full h-[500px] bg-white dark:bg-zinc-900 rounded-xl shadow-inner border border-gray-300 dark:border-zinc-700"></div>
            </div>

            <div class="flex flex-col items-center">
                <h2 class="text-lg font-semibold mb-2 text-gray-800 dark:text-white">날짜별 출석 인원수</h2>
                <canvas id="dailyCountChart" width="400" height="320"></canvas>
            </div>

            <div class="flex flex-col items-center">
                <h2 class="text-lg font-semibold mb-2 text-gray-800 dark:text-white">요일별 평균 출석 인원수</h2>
                <canvas id="weekdayChart" width="400" height="320"></canvas>
            </div>

            <div class="flex flex-col items-center">
                <h2 class="text-lg font-semibold mb-2 text-gray-800 dark:text-white">평균 입장 시간 비율</h2>
                <canvas id="intervalChart" width="400" height="320"></canvas>
            </div>

            <!-- 상관계수 Top 가로 막대 (두 컬럼 폭 사용) -->
            <div class="flex flex-col items-center col-span-1 md:col-start-2">
                <h2 class="text-lg font-semibold mb-0 text-gray-800 dark:text-white" style="margin-bottom:18px;">
                    유저별 출석 인원수 영향력
                </h2>
                <div class="w-full bg-white dark:bg-zinc-900 rounded-xl shadow-inner border border-gray-300 dark:border-zinc-700 p-4"
                    style="height:clamp(360px, 60vh, 640px); overflow:hidden;">
                    <canvas id="corrChart"></canvas>
                </div>
            </div>
        </div>
    `;

    let labels1 = [], values1 = [], avg = 0;
    let labels2 = [], values2 = [];
    let labels3 = [], values3 = [];
    let loveElements = [];
    let corrItems = [];

    async function loadAndDrawCharts() {
        const isDark = document.documentElement.classList.contains("dark");

        drawLineChart("dailyCountChart", labels1, values1, isDark, {
            label: "출석자 수 (명)",
            plugins: {
                annotation: {
                    annotations: {
                        avgLine: {
                            type: 'line',
                            yMin: avg,
                            yMax: avg,
                            borderColor: 'orange',
                            borderWidth: 1.5,
                            borderDash: [4, 4],
                            label: {
                                content: `평균 ${avg.toFixed(1)}명`,
                                enabled: true,
                                backgroundColor: 'orange',
                                color: '#fff',
                                font: { size: 10 },
                                position: 'end'
                            }
                        }
                    }
                }
            }
        });

        drawLineChart("intervalChart", labels2, values2, isDark, {
            label: "출석 비율 (%)",
            fill: true,
            lineColor: isDark ? 'rgba(34,197,94,1)' : 'rgba(16,185,129,1)',
            pointBg: isDark ? 'rgba(34,197,94,0.2)' : 'rgba(16,185,129,0.2)',
            showLegend: false
        });

        drawBarChart("weekdayChart", labels3, values3, isDark);

        drawLoveGraph(loveElements, isDark);

        // 상관계수 가로 막대 + 아바타
        drawHorizontalBarChartWithAvatars("corrChart", corrItems, isDark, {
            label: "그룹 상관계수(r)",
            avatarSize: 28,
            topN: 20,
            defaultAvatar: "/static/img/default_profile.png"
        });
    }

    try {
        const res1 = await fetch("/api/attendance-daily-count");
        const data1 = await res1.json();
        labels1 = data1.map(d => {
            const [, m, d2] = d.date.split("-");
            return `${m}/${d2}`;
        });
        values1 = data1.map(d => d.count);
        avg = values1.length ? values1.reduce((a, b) => a + b, 0) / values1.length : 0;
    } catch (e) {
        console.error("출석일 수 오류:", e);
    }

    try {
        const res2 = await fetch("/api/attendance-interval-summary");
        const data2 = await res2.json();
        labels2 = data2.labels || [];
        values2 = data2.averages || [];
    } catch (e) {
        console.error("10분 단위 오류:", e);
    }

    try {
        const res3 = await fetch("/api/weekday-attendance-summary");
        const data3 = await res3.json();
        labels3 = data3.labels || [];
        values3 = data3.averages || [];
    } catch (e) {
        console.error("요일별 출석 오류:", e);
    }

    try {
        const res = await fetch("/api/love-graph");
        const data = await res.json();
        loveElements = [
            ...data.nodes.map(n => ({
                data: { id: n.id, label: n.nickname, img: n.img }
            })),
            ...data.links.map(e => ({
                data: {
                    id: `${e.source}__${e.target}`,
                    source: e.source,
                    target: e.target,
                    weight: e.weight,
                    label: `${e.weight.toFixed(2)}`
                },
                classes: e.highlight ? 'highlight' : ''
            }))
        ];
    } catch (e) {
        console.error("친밀도 그래프 오류:", e);
    }

    try {
        // 백엔드에서 Top-N + img를 내려줌
        const res4 = await fetch("/api/attendance_correlation");
        const corr = await res4.json();
        corrItems = (corr || []).map(row => ({
            user_id: String(row.user_id),
            nickname: row.nickname,
            value: row.corr_with_group_excl_self,
            img: row.img // 서버에서 내려주는 URL
        }));
    } catch (e) {
        console.error("상관계수 불러오기 오류:", e);
    }

    // 초기 그리기
    loadAndDrawCharts();

    // 테마 변경 감지 및 리렌더링 (디바운스)
    let _rerenderTimer = null;
    const observer = new MutationObserver(() => {
        clearTimeout(_rerenderTimer);
        _rerenderTimer = setTimeout(loadAndDrawCharts, 150);
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
}
