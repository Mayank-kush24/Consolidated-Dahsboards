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

const PLOTLY_LAYOUT = {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor:  'rgba(0,0,0,0)',
    font: { family: 'Inter, -apple-system, sans-serif', size: 13, color: COLORS.text },
    margin: { l: 50, r: 30, t: 30, b: 50 },
    xaxis: {
        gridcolor: 'rgba(148,163,184,0.08)',
        zerolinecolor: 'rgba(148,163,184,0.1)',
        title_font: { size: 12, color: COLORS.text2 },
        tickfont:   { size: 11, color: COLORS.muted },
    },
    yaxis: {
        gridcolor: 'rgba(148,163,184,0.08)',
        zerolinecolor: 'rgba(148,163,184,0.1)',
        title_font: { size: 12, color: COLORS.text2 },
        tickfont:   { size: 11, color: COLORS.muted },
    },
    hoverlabel: { bgcolor: COLORS.card, font_color: COLORS.text, bordercolor: COLORS.border },
};

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };

// ── State ──
let currentEvent = '';

// ── Number formatting ──
function fmt(n) {
    return n != null ? n.toLocaleString() : '0';
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

// ── Event selection ──
async function selectEvent(name) {
    if (currentEvent === name) return;
    currentEvent = name;

    // Update sidebar active states
    document.querySelectorAll('.event-btn').forEach(btn => {
        const ev = btn.dataset.event;
        if (ev === name) {
            btn.className = 'event-btn flex-1 text-left text-[0.8rem] font-medium px-3 py-2 rounded-lg transition-all duration-150 bg-indigo-500/15 text-indigo-300 border border-indigo-500/25';
        } else {
            btn.className = 'event-btn flex-1 text-left text-[0.8rem] font-medium px-3 py-2 rounded-lg transition-all duration-150 text-slate-400 hover:text-slate-200 hover:bg-slate-800/60';
        }
    });

    await fetch('/api/select', {
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
        const res = await fetch(`/api/data?event=${encodeURIComponent(eventName)}`);
        if (!res.ok) throw new Error('Failed to load data');
        const data = await res.json();

        loading.classList.add('hidden');
        content.classList.remove('hidden');

        renderAll(data);
    } catch (err) {
        loading.classList.add('hidden');
        noSel.classList.remove('hidden');
        console.error('Load error:', err);
    }
}

// ── Pin / Unpin ──
async function pinEvent(name) {
    await fetch('/api/pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: name, action: 'pin' }),
    });
    location.reload();
}

async function unpinEvent(name) {
    await fetch('/api/pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event: name, action: 'unpin' }),
    });
    location.reload();
}

// ── Tab switching ──
function switchTab(tab) {
    const tabs = ['demographics', 'geography'];
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
}

// ── Credentials toggle ──
function toggleCredentials() {
    const panel = document.getElementById('credentials-panel');
    const chev  = document.getElementById('creds-chevron');
    panel.classList.toggle('hidden');
    chev.classList.toggle('rotate-180');
}

// ══════════════════════════════════════════════
//  Render pipeline
// ══════════════════════════════════════════════

function renderAll(data) {
    renderEventHeader(data);
    renderKPIs(data.kpis);
    renderProgress(data.kpis.registrations, data.reg_target);
    renderCredentials(data.config);
    renderDailyChart(data.daily);
    renderPieChart('chart-gender',     'gender-empty',     data.gender,     ['#818cf8','#f472b6','#34d399','#fbbf24','#fb923c']);
    renderPieChart('chart-occupation', 'occupation-empty', data.occupation, ['#38bdf8','#a78bfa','#fb923c','#4ade80','#f87171','#facc15']);
    renderBarChart('chart-country', 'country-empty', data.country, [[0,'#1e3a5f'],[1,'#818cf8']]);
    renderBarChart('chart-state',   'state-empty',   data.state,   [[0,'#134e4a'],[1,'#34d399']]);
    renderBarChart('chart-city',    'city-empty',    data.city,    [[0,'#312e81'],[1,'#a78bfa']], 420);
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

// ── Daily Registration Chart ──
function renderDailyChart(daily) {
    const el    = document.getElementById('chart-daily');
    const empty = document.getElementById('daily-empty');
    const cap   = document.getElementById('daily-caption');

    if (!daily || !daily.dates || daily.dates.length === 0) {
        el.innerHTML = '';
        el.style.display = 'none';
        empty.classList.remove('hidden');
        cap.classList.add('hidden');
        return;
    }

    el.style.display = '';
    empty.classList.add('hidden');

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
        height: 400,
        hovermode: 'x unified',
        showlegend: true,
        bargap: 0.15,
        legend: {
            orientation: 'h', yanchor: 'bottom', y: 1.02, xanchor: 'right', x: 1,
            font: { size: 11, color: COLORS.text2 }, bgcolor: 'rgba(0,0,0,0)',
        },
        xaxis: { title: { text: 'Date' } },
        yaxis: { title: { text: 'Daily' } },
        yaxis2: {
            title: { text: 'Cumulative' },
            overlaying: 'y', side: 'right', showgrid: false,
            title_font: { size: 12, color: COLORS.accent2 },
            tickfont:   { size: 11, color: COLORS.accent2 },
        },
        shapes: [],
        annotations: [],
    });

    // Average daily line
    if (daily.average_daily) {
        layout.shapes.push({
            type: 'line', xref: 'paper', x0: 0, x1: 1,
            yref: 'y', y0: daily.average_daily, y1: daily.average_daily,
            line: { dash: 'dash', color: COLORS.amber, width: 1.5 },
        });
        layout.annotations.push({
            xref: 'paper', x: 0, yref: 'y', y: daily.average_daily,
            text: `Avg: ${fmt(daily.average_daily)}`,
            showarrow: false, font: { size: 10, color: COLORS.amber },
            bgcolor: 'rgba(15,23,42,0.85)', bordercolor: COLORS.amber,
            borderpad: 3, xanchor: 'left', yanchor: 'top',
        });
    }

    // Required average line
    if (daily.req_avg != null) {
        layout.shapes.push({
            type: 'line', xref: 'paper', x0: 0, x1: 1,
            yref: 'y', y0: daily.req_avg, y1: daily.req_avg,
            line: { dash: 'dot', color: COLORS.green, width: 1.5 },
        });
        layout.annotations.push({
            xref: 'paper', x: 0, yref: 'y', y: daily.req_avg,
            text: daily.req_avg_label || `Req: ${fmt(daily.req_avg)}`,
            showarrow: false, font: { size: 10, color: COLORS.green },
            bgcolor: 'rgba(15,23,42,0.85)', bordercolor: COLORS.green,
            borderpad: 3, xanchor: 'left', yanchor: 'bottom',
        });
    }

    // Target line on y2
    if (daily.reg_target) {
        layout.shapes.push({
            type: 'line', xref: 'paper', x0: 0, x1: 1,
            yref: 'y2', y0: daily.reg_target, y1: daily.reg_target,
            line: { dash: 'dash', color: 'rgba(148,163,184,0.3)', width: 1 },
        });
        layout.annotations.push({
            xref: 'paper', x: 1, yref: 'y2', y: daily.reg_target,
            text: `Target: ${fmt(daily.reg_target)}`,
            showarrow: false, font: { size: 10, color: COLORS.muted },
            bgcolor: 'rgba(15,23,42,0.85)',
            borderpad: 3, xanchor: 'right', yanchor: 'bottom',
        });
    }

    Plotly.newPlot(el, traces, layout, PLOTLY_CONFIG);

    cap.classList.add('hidden');
}

// ── Pie / Donut Chart ──
function renderPieChart(containerId, emptyId, data, colorSeq) {
    const el    = document.getElementById(containerId);
    const empty = document.getElementById(emptyId);

    if (!data || data.length === 0) {
        el.innerHTML = '';
        el.style.display = 'none';
        empty.classList.remove('hidden');
        return;
    }

    el.style.display = '';
    empty.classList.add('hidden');

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
        height: 320,
        showlegend: true,
        legend: { font: { size: 11, color: COLORS.text2 } },
        margin: { l: 20, r: 20, t: 20, b: 20 },
    });

    Plotly.newPlot(el, [trace], layout, PLOTLY_CONFIG);
}

// ── Horizontal Bar Chart ──
function renderBarChart(containerId, emptyId, data, colorscale, height) {
    const el    = document.getElementById(containerId);
    const empty = document.getElementById(emptyId);

    if (!data || data.length === 0) {
        el.innerHTML = '';
        el.style.display = 'none';
        empty.classList.remove('hidden');
        return;
    }

    el.style.display = '';
    empty.classList.add('hidden');

    const labels = data.map(d => d.label);
    const values = data.map(d => d.value);

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
        height: height || 380,
        showlegend: false,
        yaxis: { autorange: 'reversed' },
        margin: { l: 120, r: 30, t: 20, b: 40 },
    });

    Plotly.newPlot(el, [trace], layout, PLOTLY_CONFIG);
}
