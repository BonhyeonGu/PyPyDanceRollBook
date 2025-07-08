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

export async function renderAnalysisPage() {
    const app = document.getElementById("app");
    if (!app) return;

    app.innerHTML = `
        <h1 class="text-2xl font-bold mb-6">분석</h1>
        <div class="text-sm text-gray-600 dark:text-gray-300 mb-8">
            최근 30일 동안의 데이터를 분석합니다.
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 items-start justify-center">
            <div class="flex flex-col items-center">
                <h2 class="text-lg font-semibold mb-2 text-gray-800 dark:text-white">날짜별 출석 유저 수</h2>
                <canvas id="dailyCountChart" width="400" height="320"></canvas>
            </div>
            <div class="flex flex-col items-center">
                <h2 class="text-lg font-semibold mb-2 text-gray-800 dark:text-white">출석 시간에 따른 평균 인원비율</h2>
                <canvas id="intervalChart" width="400" height="320"></canvas>
            </div>
        </div>
    `;

    let labels1 = [], values1 = [], avg = 0;
    let labels2 = [], values2 = [];

    async function loadAndDrawCharts() {
        const isDark = document.documentElement.classList.contains("dark");

        drawLineChart("dailyCountChart", labels1, values1, isDark, {
            label: "출석자 수",
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
    }

    try {
        const res1 = await fetch("/api/attendance-daily-count");
        const data1 = await res1.json();
        labels1 = data1.map(d => {
            const [, m, d2] = d.date.split("-");
            return `${m}/${d2}`;
        });
        values1 = data1.map(d => d.count);
        avg = values1.reduce((a, b) => a + b, 0) / values1.length;
    } catch (e) {
        console.error("출석일 수 오류:", e);
    }

    try {
        const res2 = await fetch("/api/attendance-interval-summary");
        const data2 = await res2.json();
        labels2 = data2.labels;
        values2 = data2.averages;
    } catch (e) {
        console.error("10분 단위 오류:", e);
    }

    // 초기 그리기
    loadAndDrawCharts();

    // 테마 변경 감지 및 리렌더링
    const observer = new MutationObserver(() => {
        loadAndDrawCharts();
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
}
