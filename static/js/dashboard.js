/* =============================================
   Event Analytics Dashboard — Client-side JS
   Chart rendering (Plotly.js), AJAX interactions,
   event selection, pin/unpin, tab switching
   ============================================= */

const COLORS = {
    bg:      '#0f172a',
    card:    '#1e293b',
    surface: '#334155',
    accent:  '#6366f1',
    accent2: '#818cf8',
    green:   '#10b981',
    amber:   '#f59e0b',
    red:     '#ef4444',
    sky:     '#38bdf8',
    text:    '#e2e8f0',
    text2:   '#94a3b8',
    muted:   '#64748b',
    border:  '#334155',
};

const CHART_KEYS = ['daily', 'gender', 'occupation', 'country', 'state', 'city', 'citystat'];

const PLOTLY_LAYOUT = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor:  'rgba(0,0,0,0)',
    font: { family: 'Inter, -apple-system, sans-serif', size: 13, color: '#ffffff' },
    margin: { l: 50, r: 30, t: 30, b: 50 },
    xaxis: {
        gridcolor: 'rgba(148,163,184,0.08)',
        zerolinecolor: 'rgba(148,163,184,0.1)',
        title_font: { size: 12, color: '#ffffff' },
        tickfont:   { size: 11, color: '#ffffff' },
    },
    yaxis: {
        gridcolor: 'rgba(148,163,184,0.08)',
        zerolinecolor: 'rgba(148,163,184,0.1)',
        title_font: { size: 12, color: '#ffffff' },
        tickfont:   { size: 11, color: '#ffffff' },
    },
    hoverlabel: { bgcolor: COLORS.card, font: { color: '#ffffff' }, bordercolor: COLORS.border },
};

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };

// ── State ──
let currentEvent = '';
let lastAnalyticsData = null;
const chartViews = {};

// ── Number formatting ──
function fmt(n) {
    return n != null ? n.toLocaleString() : '0';
}

function isMobile() {
    return window.matchMedia('(max-width: 768px)').matches;
}

function getDefaultView(chartKey) {
    const stored = sessionStorage.getItem('chartView_' + chartKey);
    if (stored === 'chart' || stored === 'table') return stored;
    return isMobile() ? 'table' : 'chart';
}

function getChartView(chartKey) {
    return chartViews[chartKey] || getDefaultView(chartKey);
}

function getChartEl(chartKey) {
    return document.getElementById('chart-' + chartKey);
}

function getTableEl(chartKey) {
    return document.getElementById('table-' + chartKey);
}

function getEmptyEl(chartKey) {
    const map = {
        daily: 'daily-empty',
        gender: 'gender-empty',
        occupation: 'occupation-empty',
        country: 'country-empty',
        state: 'state-empty',
        city: 'city-empty',
        citystat: 'citystat-empty',
    };
    return document.getElementById(map[chartKey]);
}

function barChartHeight(rowCount, desktopDefault) {
    if (!isMobile()) return desktopDefault || 380;
    return Math.min(380, Math.max(200, rowCount * 40 + 80));
}

function barLeftMargin(labels) {
    const longest = labels.reduce((m, l) => Math.max(m, String(l).length), 0);
    return Math.min(200, Math.max(isMobile() ? 80 : 120, longest * 7));
}

// ── Deep-merge helper for Plotly layouts ──
function mergeLayout(overrides) {
    const base = JSON.parse(JSON.stringify(PLOTLY_LAYOUT));
    for (const [k, v] of Object.entries(overrides || {})) {
        if (k in base && typeof base[k] === 'object' && typeof v === 'object' && !Array.isArray(v)) {
            Object.assign(base[k], v);
        } else {
            base[k] = v;
        }
    }
    return base;
}

// ── View toggle ──
function setChartView(chartKey, view, persist) {
    chartViews[chartKey] = view;
    if (persist !== false) {
        sessionStorage.setItem('chartView_' + chartKey, view);
    }

    const chartEl = getChartEl(chartKey);
    const tableEl = getTableEl(chartKey);
    const toggle = document.querySelector(`.view-toggle[data-chart="${chartKey}"]`);

    if (toggle) {
        toggle.querySelectorAll('.view-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.view === view);
        });
    }

    if (chartEl) chartEl.classList.toggle('hidden', view !== 'chart');
    if (tableEl) tableEl.classList.toggle('hidden', view !== 'table');

    if (view === 'chart' && chartEl && chartEl.querySelector('.plotly')) {
        Plotly.Plots.resize(chartEl);
    }
}

function initViewToggles() {
    document.querySelectorAll('.view-toggle').forEach(toggle => {
        const chartKey = toggle.dataset.chart;
        if (!chartKey) return;

        toggle.querySelectorAll('.view-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                setChartView(chartKey, btn.dataset.view);
            });
        });
    });
    applyAllChartViews();
}

function applyAllChartViews() {
    CHART_KEYS.forEach(key => {
        if (document.querySelector(`.view-toggle[data-chart="${key}"]`)) {
            setChartView(key, getChartView(key), false);
        }
    });
}

// ── Table renderers ──
function renderDistributionTable(tableId, data) {
    const el = document.getElementById(tableId);
    if (!el) return;

    if (!data || data.length === 0) {
        el.innerHTML = '';
        return;
    }

    const total = data.reduce((s, d) => s + d.value, 0);
    const rows = data
        .slice()
        .sort((a, b) => b.value - a.value)
        .map(d => {
            const pct = total ? ((d.value / total) * 100).toFixed(1) : '0.0';
            const label = escapeHtml(d.label);
            return `<tr>
                <td class="label-cell" title="${label}">${label}</td>
                <td class="num">${fmt(d.value)}</td>
                <td class="num">${pct}%</td>
            </tr>`;
        })
        .join('');

    el.innerHTML = `
        <div class="data-table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Label</th>
                        <th class="num">Count</th>
                        <th class="num">Share</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
}

function renderDailyTable(tableId, daily) {
    const el = document.getElementById(tableId);
    if (!el) return;

    if (!daily || !daily.dates || daily.dates.length === 0) {
        el.innerHTML = '';
        return;
    }

    const rows = daily.dates.map((date, i) => {
        const count = daily.counts[i] ?? 0;
        const cum = daily.cumulative[i] ?? 0;
        return `<tr>
            <td class="label-cell" title="${escapeHtml(date)}">${escapeHtml(date)}</td>
            <td class="num">${fmt(count)}</td>
            <td class="num">${fmt(cum)}</td>
        </tr>`;
    }).join('');

    el.innerHTML = `
        <div class="data-table-wrap">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th class="num">Daily</th>
                        <th class="num">Cumulative</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>`;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ── Event selection ──
async function selectEvent(name) {
    if (currentEvent === name) return;
    currentEvent = name;

    document.querySelectorAll('.event-btn').forEach(btn => {
        const ev = btn.dataset.event;
        if (ev === name) {
            btn.className = 'event-btn flex-1 text-left text-[0.8rem] font-medium px-3 py-2 rounded-lg transition-all duration-150 bg-indigo-500/15 text-indigo-300 border border-indigo-500/25';
        } else {
            btn.className = 'event-btn flex-1 text-left text-[0.8rem] font-medium px-3 py-2 rounded-lg transition-all duration-150 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60';
        }
    });

    await fetch(BASE + '/api/select', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: name }),
    });

    await loadEventData(name);
}

async function loadEventData(eventName) {
    const content   = document.getElementById('dashboard-content');
    const noData    = document.getElementById('empty-no-data');
    const noSel     = document.getElementById('empty-no-selection');
    const loading   = document.getElementById('loading-state');

    noData.classList.add('hidden');
    noSel.classList.add('hidden');
    content.classList.add('hidden');
    loading.classList.remove('hidden');

    try {
        const res = await fetch(BASE + `/api/data?event=${encodeURIComponent(eventName)}`);
        if (!res.ok) throw new Error('Failed to load data');
        const data = await res.json();

        loading.classList.add('hidden');
        content.classList.remove('hidden');

        lastAnalyticsData = data;
        renderAll(data);
    } catch (err) {
        loading.classList.add('hidden');
        noSel.classList.remove('hidden');
        console.error('Load error:', err);
    }
}

// ── Pin / Unpin ──
async function pinEvent(name) {
    await fetch(BASE + '/api/pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: name, action: 'pin' }),
    });
    location.reload();
}

async function unpinEvent(name) {
    await fetch(BASE + '/api/pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: name, action: 'unpin' }),
    });
    location.reload();
}

// ── Tab switching ──
function switchTab(tab) {
    const tabs = ['demographics', 'geography', 'citystat'];
    tabs.forEach(t => {
        const btn   = document.getElementById('tab-' + t);
        const panel = document.getElementById('panel-' + t);
        if (t === tab) {
            btn.classList.add('tab-active');
            panel.classList.remove('hidden');
        } else {
            btn.classList.remove('tab-active');
            panel.classList.add('hidden');
        }
    });
    resizeAllCharts();
}

// ── Credentials toggle ──
function toggleCredentials() {
    const panel = document.getElementById('credentials-panel');
    const chev  = document.getElementById('creds-chevron');
    panel.classList.toggle('hidden');
    chev.classList.toggle('rotate-180');
}

// ── Resize handling ──
let resizeTimer;
function resizeAllCharts() {
    CHART_KEYS.forEach(key => {
        const el = getChartEl(key);
        if (el && el.querySelector('.plotly') && getChartView(key) === 'chart') {
            Plotly.Plots.resize(el);
        }
    });
}

function debouncedResize() {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        if (lastAnalyticsData) {
            renderAll(lastAnalyticsData);
        } else {
            resizeAllCharts();
        }
    }, 150);
}

window.addEventListener('resize', debouncedResize);

document.addEventListener('DOMContentLoaded', () => {
    initViewToggles();
});

// ══════════════════════════════════════════════
//  Render pipeline
// ══════════════════════════════════════════════

function renderAll(data) {
    renderEventHeader(data);
    renderKPIs(data.kpis);
    renderProgress(data.kpis.registrations, data.reg_target);
    renderCredentials(data.config);
    renderDailyChart(data.daily);
    renderPieChart('gender', data.gender, ['#818cf8','#f472b6','#34d399','#fbbf24','#fb923c']);
    renderPieChart('occupation', data.occupation, ['#38bdf8','#a78bfa','#fb923c','#4ade80','#f87171','#facc15']);
    renderBarChart('country', data.country, [[0,'#1e3a5f'],[1,'#818cf8']], 380);
    renderBarChart('state', data.state, [[0,'#134e4a'],[1,'#34d399']], 380);
    renderBarChart('city', data.city, [[0,'#312e81'],[1,'#a78bfa']], 420);
    renderBarChart('citystat', data.city_stat, [[0,'#1e3a5f'],[1,'#38bdf8']], 420);
    toggleCityStatTab(data.city_stat);
    applyAllChartViews();
}

function toggleCityStatTab(cityStatData) {
    const tab = document.getElementById('tab-citystat');
    if (!cityStatData || cityStatData.length === 0) {
        tab.classList.add('hidden');
    } else {
        tab.classList.remove('hidden');
    }
}

function renderEventHeader(data) {
    document.getElementById('event-title').textContent = data.event_name;
    const link = document.getElementById('dashboard-link');
    if (data.config && data.config.dashboard_link) {
        link.href = data.config.dashboard_link;
        link.classList.remove('hidden');
    } else {
        link.classList.add('hidden');
    }
}

function renderKPIs(kpis) {
    document.getElementById('kpi-registrations').textContent = fmt(kpis.registrations);
    document.getElementById('kpi-submissions').textContent   = fmt(kpis.submissions);
    document.getElementById('kpi-teams').textContent         = fmt(kpis.teams);
    document.getElementById('kpi-visits').textContent        = fmt(kpis.page_visits);
}

function renderProgress(current, target) {
    const section = document.getElementById('progress-section');
    if (!target) {
        section.classList.add('hidden');
        return;
    }
    section.classList.remove('hidden');
    const pct = Math.min((current / target) * 100, 100);
    document.getElementById('progress-stats').textContent = `${fmt(current)} / ${fmt(target)} (${pct.toFixed(1)}%)`;
    const fill = document.getElementById('progress-fill');
    fill.style.width = pct.toFixed(1) + '%';
    if (pct >= 100) {
        fill.className = 'h-full rounded-full transition-all duration-700 ease-out bg-gradient-to-r from-emerald-600 to-emerald-400';
    } else {
        fill.className = 'h-full rounded-full transition-all duration-700 ease-out bg-gradient-to-r from-indigo-600 to-indigo-400';
    }
}

function renderCredentials(config) {
    const section = document.getElementById('credentials-section');
    if (!config || (!config.admin_username && !config.admin_password)) {
        section.classList.add('hidden');
        return;
    }
    section.classList.remove('hidden');
    document.getElementById('cred-username').textContent = config.admin_username || '—';
    document.getElementById('cred-password').textContent = config.admin_password || '—';
}

function showChartSection(chartKey, hasData) {
    const chartEl = getChartEl(chartKey);
    const tableEl = getTableEl(chartKey);
    const emptyEl = getEmptyEl(chartKey);
    const toggle = document.querySelector(`.view-toggle[data-chart="${chartKey}"]`);

    if (!hasData) {
        if (chartEl) { chartEl.innerHTML = ''; chartEl.style.display = 'none'; }
        if (tableEl) { tableEl.innerHTML = ''; tableEl.classList.add('hidden'); }
        if (emptyEl) emptyEl.classList.remove('hidden');
        if (toggle) toggle.classList.add('hidden');
        return;
    }

    if (emptyEl) emptyEl.classList.add('hidden');
    if (toggle) toggle.classList.remove('hidden');
    if (chartEl) chartEl.style.display = '';
}

// ── Daily Registration Chart ──
function renderDailyChart(daily) {
    const el    = getChartEl('daily');
    const cap   = document.getElementById('daily-caption');

    renderDailyTable('table-daily', daily);

    if (!daily || !daily.dates || daily.dates.length === 0) {
        showChartSection('daily', false);
        cap.classList.add('hidden');
        return;
    }

    showChartSection('daily', true);

    const height = isMobile() ? 280 : 400;
    el.style.height = height + 'px';

    const traces = [
        {
            x: daily.dates,
            y: daily.counts,
            type: 'bar',
            marker: { color: daily.bar_colors, line: { width: 0 } },
            name: 'Daily',
            opacity: 0.75,
            hovertemplate: '<b>%{x}</b><br>Daily: %{y:,}<extra></extra>',
        },
        {
            x: daily.dates,
            y: daily.cumulative,
            type: 'scatter',
            mode: 'lines+markers',
            line: { color: COLORS.accent2, width: 2.5 },
            marker: { size: 4, color: COLORS.accent2 },
            name: 'Cumulative',
            yaxis: 'y2',
            hovertemplate: '<b>%{x}</b><br>Cumulative: %{y:,}<extra></extra>',
        },
    ];

    const layout = mergeLayout({
        height,
        hovermode: 'x unified',
        showlegend: true,
        bargap: 0.15,
        legend: {
            orientation: isMobile() ? 'h' : 'h',
            yanchor: 'bottom',
            y: isMobile() ? -0.2 : 1.02,
            xanchor: 'right',
            x: 1,
            font: { size: 11, color: '#ffffff' },
            bgcolor: 'rgba(0,0,0,0)',
        },
        margin: isMobile() ? { l: 40, r: 40, t: 30, b: 60 } : { l: 50, r: 30, t: 30, b: 50 },
        xaxis: { title: { text: 'Date' } },
        yaxis: { title: { text: 'Daily' } },
        yaxis2: {
            title: { text: 'Cumulative' },
            overlaying: 'y', side: 'right', showgrid: false,
            title_font: { size: 12, color: '#ffffff' },
            tickfont:   { size: 11, color: '#ffffff' },
        },
        shapes: [],
        annotations: [],
    });

    if (daily.average_daily) {
        layout.shapes.push({
            type: 'line', xref: 'paper', x0: 0, x1: 1,
            yref: 'y', y0: daily.average_daily, y1: daily.average_daily,
            line: { dash: 'dash', color: COLORS.amber, width: 1.5 },
        });
        if (!isMobile()) {
            layout.annotations.push({
                xref: 'paper', x: 0, yref: 'y', y: daily.average_daily,
                text: `Avg: ${fmt(daily.average_daily)}`,
                showarrow: false, font: { size: 10, color: COLORS.amber },
                bgcolor: 'rgba(15,23,42,0.85)', bordercolor: COLORS.amber,
                borderpad: 3, xanchor: 'left', yanchor: 'top',
            });
        }
    }

    if (daily.req_avg != null) {
        layout.shapes.push({
            type: 'line', xref: 'paper', x0: 0, x1: 1,
            yref: 'y', y0: daily.req_avg, y1: daily.req_avg,
            line: { dash: 'dot', color: COLORS.green, width: 1.5 },
        });
        if (!isMobile()) {
            layout.annotations.push({
                xref: 'paper', x: 0, yref: 'y', y: daily.req_avg,
                text: daily.req_avg_label || `Req: ${fmt(daily.req_avg)}`,
                showarrow: false, font: { size: 10, color: COLORS.green },
                bgcolor: 'rgba(15,23,42,0.85)', bordercolor: COLORS.green,
                borderpad: 3, xanchor: 'left', yanchor: 'bottom',
            });
        }
    }

    if (daily.reg_target) {
        layout.shapes.push({
            type: 'line', xref: 'paper', x0: 0, x1: 1,
            yref: 'y2', y0: daily.reg_target, y1: daily.reg_target,
            line: { dash: 'dash', color: 'rgba(148,163,184,0.3)', width: 1 },
        });
        if (!isMobile()) {
            layout.annotations.push({
                xref: 'paper', x: 1, yref: 'y2', y: daily.reg_target,
                text: `Target: ${fmt(daily.reg_target)}`,
                showarrow: false, font: { size: 10, color: COLORS.muted },
                bgcolor: 'rgba(15,23,42,0.85)',
                borderpad: 3, xanchor: 'right', yanchor: 'bottom',
            });
        }
    }

    Plotly.newPlot(el, traces, layout, PLOTLY_CONFIG);
    cap.classList.add('hidden');
}

// ── Pie / Donut Chart ──
function renderPieChart(chartKey, data, colorSeq) {
    const el = getChartEl(chartKey);

    renderDistributionTable('table-' + chartKey, data);

    if (!data || data.length === 0) {
        showChartSection(chartKey, false);
        return;
    }

    showChartSection(chartKey, true);

    const height = isMobile() ? 260 : 320;
    el.style.height = height + 'px';

    const trace = {
        values: data.map(d => d.value),
        labels: data.map(d => d.label),
        type: 'pie',
        hole: 0.5,
        marker: { colors: colorSeq },
        textfont: { color: '#fff' },
        hovertemplate: '<b>%{label}</b><br>%{value:,} (%{percent})<extra></extra>',
    };

    const layout = mergeLayout({
        height,
        showlegend: true,
        legend: isMobile()
            ? { orientation: 'h', yanchor: 'top', y: -0.15, xanchor: 'center', x: 0.5, font: { size: 10, color: '#ffffff' } }
            : { font: { size: 11, color: '#ffffff' } },
        margin: isMobile() ? { l: 10, r: 10, t: 10, b: 40 } : { l: 20, r: 20, t: 20, b: 20 },
    });

    Plotly.newPlot(el, [trace], layout, PLOTLY_CONFIG);
}

// ── Horizontal Bar Chart ──
function renderBarChart(chartKey, data, colorscale, desktopHeight) {
    const el = getChartEl(chartKey);

    renderDistributionTable('table-' + chartKey, data);

    if (!data || data.length === 0) {
        showChartSection(chartKey, false);
        return;
    }

    showChartSection(chartKey, true);

    const labels = data.map(d => d.label);
    const values = data.map(d => d.value);
    const height = barChartHeight(labels.length, desktopHeight);
    const leftMargin = barLeftMargin(labels);

    el.style.height = height + 'px';

    const trace = {
        x: values,
        y: labels,
        type: 'bar',
        orientation: 'h',
        marker: {
            color: values,
            colorscale: colorscale,
            line: { width: 0 },
            cornerradius: 3,
        },
        hovertemplate: '<b>%{y}</b><br>%{x:,}<extra></extra>',
    };

    const layout = mergeLayout({
        height,
        showlegend: false,
        yaxis: { autorange: 'reversed', tickfont: { size: isMobile() ? 10 : 11 } },
        margin: { l: leftMargin, r: 20, t: 20, b: 40 },
    });

    Plotly.newPlot(el, [trace], layout, PLOTLY_CONFIG);
}
