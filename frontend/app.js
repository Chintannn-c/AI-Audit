// ════════════════════════════════════════════
// StatAudit Pro — High-Performance AI Engine
// ════════════════════════════════════════════

function generateSessionId() {
    return 'sess_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now();
}

function getOrCreateSessionId() {
    let stored = localStorage.getItem('stataudit_session_id');
    if (stored) return stored;
    const newId = generateSessionId();
    localStorage.setItem('stataudit_session_id', newId);
    return newId;
}

function clearSession() {
    localStorage.removeItem('stataudit_session_id');
    sessionId = getOrCreateSessionId();
    location.reload();
}

let sessionId = '';
let uploadedFile = null;
let isLargeAudit = true; // Default to true so TOC generates by default
let selectedExactPct = 0.05; // Default for 'Medium' risk
let selectedCategory = 'Sales';
let selectedBasis = 'count';

// ── Initialization ──
document.addEventListener('DOMContentLoaded', () => {
    console.log("StatAudit Engine: Initializing...");
    lucide.createIcons();
    initMaterialityLogic();
    initClassificationLogic();
    initSamplingLogic();
    initVouchingLogic();

    // Default Page
    navigateTo('landing-page');

    // Retrieve or create Session ID (persists across refreshes)
    sessionId = getOrCreateSessionId();
    console.log('Session:', sessionId);

    // Bind Global Export PDF
    const exportPdfBtn = document.getElementById('exportPdfBtn');
    if (exportPdfBtn) {
        exportPdfBtn.addEventListener('click', () => {
            navigateTo('reports-section');
            setTimeout(() => window.print(), 300);
        });
    }
});

let auditChart = null;

// ── Navigation Controller ──
function navigateTo(sectionId) {
    const sections = document.querySelectorAll('.content-section');
    sections.forEach(s => s.classList.add('hidden'));

    const target = document.getElementById(sectionId);
    if (target) {
        target.classList.remove('hidden');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // Toggle Sidebar & Progress Bar
    const sidebar = document.querySelector('.sidebar');
    const main = document.querySelector('.main-wrapper');
    const topBar = document.getElementById('topProgressBar');

    if (sectionId === 'landing-page') {
        if (sidebar) sidebar.style.display = 'none';
        if (main) main.style.marginLeft = '0';
        if (topBar) topBar.style.display = 'none';
    } else {
        if (sidebar) sidebar.style.display = 'flex';
        if (main) main.style.marginLeft = '280px';
        if (topBar) topBar.style.display = 'block';
    }

    // Update Sidebar Active State
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
        if (link.dataset.target === sectionId) {
            link.classList.add('active');
        }
    });

    // Update Progress Bar
    const stages = ['materiality-section', 'risk-section', 'sampling-section', 'vouching-section'];
    const currentIdx = stages.indexOf(sectionId);
    if (topBar && currentIdx !== -1) {
        const pct = ((currentIdx + 1) / stages.length) * 100;
        topBar.style.width = pct + '%';
    }
}

// ── Section 1: Materiality Logic ──
function selectRisk(risk, btn) {
    const group = btn.parentElement;
    group.querySelectorAll('.toggle-option').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('rommInput').value = risk;

    const picker = document.getElementById('exactPctPicker');
    const optionsDiv = document.getElementById('exactPctOptions');
    picker.classList.remove('hidden');

    const ranges = {
        low: [8, 9, 10],
        medium: [5, 6, 7],
        high: [2, 3, 4]
    };

    const pcts = ranges[risk];
    optionsDiv.innerHTML = pcts.map(p =>
        `<button type="button" class="toggle-option" onclick="setExactPct(${p}, this)">${p}%</button>`
    ).join('');

    // Auto-select first
    setExactPct(pcts[0], optionsDiv.querySelector('button'));
}

function setExactPct(val, btn) {
    const parent = btn.parentElement;
    parent.querySelectorAll('.toggle-option').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedExactPct = val / 100;
}

function initMaterialityLogic() {
    const calcBtn = document.getElementById('calcMaterialityBtn');
    if (!calcBtn) return;

    calcBtn.addEventListener('click', async () => {
        const turnover = parseFloat(document.getElementById('turnoverInput').value);
        const perfPct = parseFloat(document.getElementById('perfPctInput').value);
        const trivialPct = parseFloat(document.getElementById('trivialPctInput').value);
        const romm = document.getElementById('rommInput').value;

        if (isNaN(turnover) || !selectedExactPct) {
            alert("Please enter turnover and select an exact ROMM basis.");
            return;
        }

        const overall = turnover * selectedExactPct;
        const performance = overall * (perfPct / 100);
        const trivial = overall * (trivialPct / 100);

        document.getElementById('resOverall').textContent = `₹ ${overall.toFixed(2)} Cr`;
        document.getElementById('resPerf').textContent = `₹ ${performance.toFixed(2)} Cr`;
        document.getElementById('resTrivial').textContent = `₹ ${trivial.toFixed(2)} Cr`;

        // Sync to Reports section
        const rptO = document.getElementById('rptOverall');
        const rptP = document.getElementById('rptPerf');
        const rptT = document.getElementById('rptTrivial');
        if (rptO) rptO.textContent = `₹ ${overall.toFixed(2)} Cr`;
        if (rptP) rptP.textContent = `₹ ${performance.toFixed(2)} Cr`;
        if (rptT) rptT.textContent = `₹ ${trivial.toFixed(2)} Cr`;

        document.getElementById('materialityPlaceholder').classList.add('hidden');
        document.getElementById('materialityResults').classList.remove('hidden');

        // Sync with Backend
        const fd = new FormData();
        fd.append('session_id', sessionId);
        fd.append('npbt', turnover); // Using turnover as the basis for NPBT in this simplified logic
        fd.append('romm', romm);
        fd.append('perf_pct', perfPct);
        fd.append('trivial_pct', trivialPct);
        fd.append('overall_pct', selectedExactPct * 100);
        try {
            await fetch('/api/materiality', { method: 'POST', body: fd });
        } catch (e) { console.error("Materiality Sync Failed", e); }
    });
}

// ── Section 2: Classification Logic ──
function initClassificationLogic() {
    const assessBtn = document.getElementById('assessRiskBtn');
    if (!assessBtn) return;

    // Checkbox styling
    document.querySelectorAll('.option-card').forEach(card => {
        const input = card.querySelector('input');
        input.addEventListener('change', () => {
            card.classList.toggle('active', input.checked);
            updateLiveClassification();
        });
    });

    assessBtn.addEventListener('click', async () => {
        updateLiveClassification();
        document.getElementById('riskResults').classList.remove('hidden');

        // Sync with Backend
        const fd = new FormData();
        fd.append('session_id', sessionId);
        fd.append('turnover_250', document.getElementById('checkTurnover').checked);
        fd.append('ifc', document.getElementById('checkIFC').checked);
        fd.append('governance', document.getElementById('checkGov').checked);
        fd.append('misstatements', document.getElementById('checkMis').checked);
        try {
            await fetch('/api/risk-assessment', { method: 'POST', body: fd });
        } catch (e) { console.error("Risk Sync Failed", e); }
    });
}

function updateLiveClassification() {
    const a = document.getElementById('checkTurnover').checked;
    const b = document.getElementById('checkIFC').checked;
    const c = document.getElementById('checkGov').checked;
    const d = document.getElementById('checkMis').checked;

    const isLarge = a || b || c || d;

    const resType = document.getElementById('resAuditType');
    const resClass = document.getElementById('resClassification');

    if (isLarge) {
        resType.textContent = 'LARGE AUDIT';
        resType.style.color = '#2563EB';
        resClass.textContent = 'Combined approach (TOD + TOC) required for this engagement.';
        isLargeAudit = true;
    } else {
        resType.textContent = 'SMALL AUDIT';
        resType.style.color = '#10b981';
        resClass.textContent = 'Substantive approach (TOD only) sufficient for this engagement.';
        isLargeAudit = false;
    }

    // Sync to Reports section
    const rptType = document.getElementById('rptAuditType');
    const rptApproach = document.getElementById('rptApproach');
    if (rptType) { rptType.textContent = resType.textContent; rptType.style.color = resType.style.color; }
    if (rptApproach) rptApproach.textContent = resClass.textContent;

    // Dynamic UI: Hide TOD split slider if TOD only
    const todSliderRow = document.getElementById('todPctSlider')?.parentElement?.parentElement;
    if (todSliderRow) {
        todSliderRow.style.display = isLargeAudit ? 'block' : 'none';
    }

    // Update TOC badge
    const tocBadge = document.getElementById('tocBadge');
    if (tocBadge) {
        tocBadge.textContent = isLargeAudit ? 'APPLICABLE' : 'NOT APPLICABLE';
        tocBadge.className = isLargeAudit ? 'badge badge-low mt-8' : 'badge badge-medium mt-8';
    }
}

// ── Section 3: Sampling Logic ──
function initSamplingLogic() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('fileUpload');
    if (zone && input) {
        zone.addEventListener('click', () => input.click());
        zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.style.borderColor = 'var(--accent-primary)'; });
        zone.addEventListener('dragleave', (e) => { e.preventDefault(); zone.style.borderColor = 'var(--glass-border)'; });
        zone.addEventListener('drop', (e) => {
            e.preventDefault();
            zone.style.borderColor = 'var(--glass-border)';
            if (e.dataTransfer.files[0]) {
                input.files = e.dataTransfer.files;
                uploadedFile = e.dataTransfer.files[0];
                document.getElementById('fileNameDisplay').textContent = `Uploaded: ${uploadedFile.name}`;
                document.getElementById('samplingStep2').style.display = 'block';
            }
        });
        input.addEventListener('change', e => {
            if (e.target.files[0]) {
                uploadedFile = e.target.files[0];
                document.getElementById('fileNameDisplay').textContent = `Uploaded: ${uploadedFile.name}`;
                document.getElementById('samplingStep2').style.display = 'block';
            }
        });
    }

    const analyzeBtn = document.getElementById('analyzeBtn');
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', runAnalysis);
    }

    const downloadBtn = document.getElementById('downloadBtn');
    if (downloadBtn) {
        downloadBtn.addEventListener('click', runDownload);
    }
    
    const downloadBtn2 = document.getElementById('downloadBtn2');
    if (downloadBtn2) {
        downloadBtn2.addEventListener('click', runDownload);
    }

    // Sync sliders
    const samplePctSlider = document.getElementById('samplePctSlider');
    const samplePctInput = document.getElementById('samplePctInput');
    if (samplePctSlider && samplePctInput) {
        samplePctSlider.addEventListener('input', () => {
            samplePctInput.value = samplePctSlider.value;
        });
        samplePctInput.addEventListener('input', () => {
            samplePctSlider.value = samplePctInput.value;
        });
    }

    const todPctSlider = document.getElementById('todPctSlider');
    const todPctDisplay = document.getElementById('todPctDisplay');
    if (todPctSlider && todPctDisplay) {
        todPctSlider.addEventListener('input', () => {
            const tod = todPctSlider.value;
            const toc = 100 - tod;
            todPctDisplay.textContent = `${tod} / ${toc}`;
        });
    }
}

function regenerateSampling() {
    const el = document.getElementById('samplingStep2');
    if (el) {
        el.style.display = 'block';
        el.scrollIntoView({ behavior: 'smooth' });
    }
    const res = document.getElementById('samplingResults');
    if (res) res.classList.add('hidden');
}

function initVouchingLogic() {
    const zone = document.getElementById('vouchUploadZone');
    const input = document.getElementById('vouchFileInput');
    if (zone && input) {
        zone.addEventListener('click', () => input.click());
        input.addEventListener('change', e => {
            if (e.target.files[0]) runVouch(e.target.files[0]);
        });
    }
}

async function runVouch(file) {
    const status = document.getElementById('vouchStatus');
    const results = document.getElementById('vouchResults');
    status.classList.remove('hidden');
    results.classList.add('hidden');

    // Animate Agents
    const a1 = document.getElementById('agent1Status');
    const a2 = document.getElementById('agent2Status');
    const d1 = document.getElementById('agent1Dot');
    const d2 = document.getElementById('agent2Dot');

    // Reset styles
    a1.style.opacity = '0.4'; d1.style.background = 'var(--text-muted)';
    a2.style.opacity = '0.4'; d2.style.background = 'var(--text-muted)';
    document.getElementById('vouchTableBody').innerHTML = '';
    document.getElementById('vouchFlagsTitle').textContent = "⏳ Agent 2 Validation";
    document.getElementById('vouchFlagsText').textContent = "Waiting for results...";

    a1.style.opacity = '1'; d1.style.background = '#fbbf24';
    await new Promise(r => setTimeout(r, 1500));
    d1.style.background = '#10b981';
    
    a2.style.opacity = '1'; d2.style.background = '#fbbf24';
    
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('file', file);
    try {
        const res = await fetch('/api/vouch', { method: 'POST', body: fd });
        const data = await res.json();
        
        d2.style.background = '#10b981';
        status.classList.add('hidden');
        results.classList.remove('hidden');

        const body = document.getElementById('vouchTableBody');
        body.innerHTML = data.data.map(row => `
            <tr>
                <td>${row.field}</td>
                <td style="font-weight:700; color:${row.field === 'Match Status' ? '#10b981' : 'white'}">${row.value}</td>
            </tr>
        `).join('');

        const matchStatusField = data.data.find(r => r.field === 'Match Status');
        const matchStatusText = matchStatusField ? matchStatusField.value : "Data extracted successfully.";

        document.getElementById('vouchFlagsTitle').textContent = "✅ Verification Complete";
        document.getElementById('vouchFlagsText').textContent = `AI Ensemble status: ${matchStatusText}`;

    } catch (err) {
        console.error(err);
        alert('Vouching Error: ' + err.message);
    }
}

async function runDownload() {
    if (!uploadedFile) return alert("Please upload a ledger file first.");

    const samplePct = document.getElementById('samplePctSlider').value;
    const todPct = isLargeAudit ? (document.getElementById('todPctSlider')?.value || 70) : 100;

    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('file', uploadedFile);
    fd.append('category', typeof selectedCategory !== 'undefined' ? selectedCategory : 'Sales');
    fd.append('sample_pct', samplePct);
    fd.append('sampling_basis', typeof selectedBasis !== 'undefined' ? selectedBasis : 'count');
    fd.append('tod_pct', todPct);

    try {
        const res = await fetch('/api/download', { method: 'POST', body: fd });
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Audit_Working_Papers_${selectedCategory}_${samplePct}pct.xlsx`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
    } catch (err) {
        console.error(err);
        alert('Download Error: ' + err.message);
    }
}

async function runAnalysis() {
    if (!uploadedFile) return alert("Please upload a ledger file first.");

    const samplePct = document.getElementById('samplePctSlider')?.value || 10;
    const todPct = isLargeAudit ? (document.getElementById('todPctSlider')?.value || 70) : 100;

    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('file', uploadedFile);
    fd.append('category', typeof selectedCategory !== 'undefined' ? selectedCategory : 'Sales');
    fd.append('sample_pct', samplePct);
    fd.append('sampling_basis', typeof selectedBasis !== 'undefined' ? selectedBasis : 'count');
    fd.append('tod_pct', todPct);
    fd.append('audit_type', isLargeAudit ? 'large' : 'small');

    const analyzeBtn = document.getElementById('analyzeBtn');
    const originalText = analyzeBtn ? analyzeBtn.innerHTML : '';
    if (analyzeBtn) {
        analyzeBtn.innerHTML = '<div class="processing-spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;margin-right:8px;vertical-align:middle;"></div> Analyzing...';
        analyzeBtn.disabled = true;
    }

    showProcessingSteps();

    try {
        const res = await fetch('/api/analyze', { method: 'POST', body: fd });
        const data = await res.json();
        if (data.error) throw new Error(data.error);

        // Update Results UI
        document.getElementById('resTotalTxns').textContent = data.stats.count.toLocaleString();
        document.getElementById('resTodCount').textContent = data.tod_count.toLocaleString();
        document.getElementById('resTocCount').textContent = data.toc_count.toLocaleString();
        document.getElementById('resTotalSelected').textContent = data.total_selected.toLocaleString();
        const coverage = ((data.total_selected / data.stats.count) * 100).toFixed(1);
        document.getElementById('resCoverage').textContent = `${coverage}%`;

        // Sync to Reports section
        const rptIds = { rptTotalTxns: data.stats.count, rptTodCount: data.tod_count, rptTocCount: data.toc_count, rptTotalSel: data.total_selected };
        for (const [id, val] of Object.entries(rptIds)) {
            const el = document.getElementById(id);
            if (el) el.textContent = val.toLocaleString();
        }
        const rptCov = document.getElementById('rptCoverage');
        if (rptCov) rptCov.textContent = `${coverage}%`;

        // Render AI Insights
        document.getElementById('aiInsightText').innerHTML = `
            <strong>${data.ai_insights.focus}</strong><br>
            ${data.ai_insights.summary}
        `;
        
        // Populate Reports Section AI Output
        const aiOutput = document.getElementById('aiOutput');
        if (aiOutput) {
            aiOutput.innerHTML = `
                <div style="margin-bottom:8px;"><strong>${data.ai_insights.focus}</strong></div>
                <div>${data.ai_insights.summary}</div>
            `;
        }
        
        const dl2 = document.getElementById('downloadBtn2');
        if (dl2) dl2.disabled = false;

        // Render Table Preview
        renderPreview(data.top_10);

        // Show Results before drawing chart (Chart.js needs visible dimensions)
        document.getElementById('samplingResults').classList.remove('hidden');
        document.getElementById('samplingResults').scrollIntoView({ behavior: 'smooth' });

        // Update Chart
        updateChart(data.stats);

    } catch (err) {
        console.error(err);
        alert('Analysis Error: ' + err.message);
    } finally {
        hideProcessing();
        if (analyzeBtn) {
            analyzeBtn.innerHTML = originalText;
            analyzeBtn.disabled = false;
        }
    }
}

function renderPreview(records) {
    if (!records || !records.length) return;
    const head = document.getElementById('previewHead');
    const body = document.getElementById('previewBody');
    if (!head || !body) return;

    const allKeys = Object.keys(records[0]);
    const displayKeys = allKeys.filter(k => !k.startsWith('_Risk_') || k === '_Risk_Category');

    head.innerHTML = `<tr>${displayKeys.map(k => `<th>${k.replace(/^_/, '').replace(/_/g, ' ')}</th>`).join('')}</tr>`;
    body.innerHTML = records.map(r => `<tr>${displayKeys.map(k => {
        if (k === '_Risk_Category') {
            const cat = (r[k] || 'Low').toLowerCase();
            return `<td><span class="badge badge-${cat}">${r[k] || 'LOW'}</span></td>`;
        }
        return `<td>${r[k] !== null ? r[k] : '—'}</td>`;
    }).join('')}</tr>`).join('');
}

function updateChart(stats) {
    const ctx = document.getElementById('samplingChart')?.getContext('2d');
    if (!ctx) return;

    if (auditChart) {
        auditChart.destroy();
    }

    auditChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Minimum', 'Average', 'Maximum'],
            datasets: [{
                label: 'Transaction Value (₹)',
                data: [stats.minimum, stats.average, stats.maximum],
                backgroundColor: ['rgba(16,185,129,0.5)', 'rgba(99,102,241,0.5)', 'rgba(239,68,68,0.5)'],
                borderColor: ['#10b981', '#6366f1', '#ef4444'],
                borderWidth: 2, borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
                x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
            }
        }
    });
}

// ── Processing Overlay Animation ──
let stepInterval = null;

function showProcessingSteps() {
    const overlay = document.getElementById('processingOverlay');
    overlay.classList.remove('hidden');

    const steps = document.querySelectorAll('#processingSteps li');
    steps.forEach(li => {
        li.classList.remove('active', 'done');
        li.querySelector('.step-icon').textContent = '○';
    });

    let current = 0;
    clearInterval(stepInterval);
    stepInterval = setInterval(() => {
        if (current > 0 && current <= steps.length) {
            steps[current - 1].classList.remove('active');
            steps[current - 1].classList.add('done');
            steps[current - 1].querySelector('.step-icon').textContent = '✓';
        }
        if (current < steps.length) {
            steps[current].classList.add('active');
            steps[current].querySelector('.step-icon').textContent = '●';
        }
        current++;
        if (current > steps.length + 1) clearInterval(stepInterval);
    }, 800);
}

function hideProcessing() {
    clearInterval(stepInterval);
    document.getElementById('processingOverlay').classList.add('hidden');
}
function selectCategory(btn) {
    const parent = btn.parentElement;
    parent.querySelectorAll('.toggle-option').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedCategory = btn.dataset.category;
}

function selectBasis(btn) {
    const parent = btn.parentElement;
    parent.querySelectorAll('.toggle-option').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedBasis = btn.dataset.basis;
}

