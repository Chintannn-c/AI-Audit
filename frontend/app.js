
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
let lastVouchFile = null;
let isLargeAudit = true; // Default to true so TOC generates by default
let selectedExactPct = 0.05; // Default for 'Medium' risk
let selectedCategory = 'Sales';
let selectedBasis = 'count';

// â”€â”€ Initialization â”€â”€
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

    // Mobile init: Collapse sidebar by default
    if (window.innerWidth <= 768) {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) sidebar.classList.add('collapsed');
        
        // Also ensure the toggle button is in the right state
        const toggleBtn = document.getElementById('sidebarToggle');
        if (toggleBtn) {
            toggleBtn.classList.remove('active');
            toggleBtn.innerHTML = '<i data-lucide="menu"></i>';
            lucide.createIcons();
        }
    }

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

// â”€â”€ Navigation Controller â”€â”€
function navigateTo(sectionId) {
    const sections = document.querySelectorAll('.content-section');
    sections.forEach(s => s.classList.add('hidden'));

    const target = document.getElementById(sectionId);
    if (target) {
        target.classList.remove('hidden');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    // Toggle Sidebar & Toggle Button
    const sidebar = document.querySelector('.sidebar');
    const main = document.querySelector('.main-wrapper');
    const toggleBtn = document.getElementById('sidebarToggle');
    const topBar = document.getElementById('topProgressBar');

    if (sectionId === 'landing-page') {
        if (sidebar) sidebar.classList.add('hidden');
        if (main) main.classList.add('expanded');
        if (toggleBtn) toggleBtn.classList.add('hidden');
        if (topBar) topBar.classList.add('hidden');
    } else {
        if (sidebar) {
            sidebar.classList.remove('hidden');
            // If not collapsed, keep main margin
            if (!sidebar.classList.contains('collapsed')) {
                main.classList.remove('expanded');
                if (toggleBtn) {
                    toggleBtn.classList.add('active');
                    toggleBtn.innerHTML = '<i data-lucide="chevron-left"></i>';
                }
            } else {
                main.classList.add('expanded');
                if (toggleBtn) {
                    toggleBtn.classList.remove('active');
                    toggleBtn.innerHTML = '<i data-lucide="menu"></i>';
                }
            }
            if (window.lucide) lucide.createIcons();
        }
        if (toggleBtn) toggleBtn.classList.remove('hidden');
        if (topBar) topBar.classList.remove('hidden');
    }

    // Auto-close sidebar on mobile after navigation
    if (window.innerWidth <= 768) {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar && !sidebar.classList.contains('collapsed')) {
            toggleSidebar();
        }
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

function toggleSidebar() {
    console.log("Toggling sidebar...");
    const sidebar = document.querySelector('.sidebar');
    const main = document.querySelector('.main-wrapper');
    const toggleBtn = document.getElementById('sidebarToggle');
    
    if (!sidebar || !main || !toggleBtn) return;
    
    const isNowCollapsed = sidebar.classList.toggle('collapsed');
    
    // On desktop, we want to expand/collapse the main margin
    // On mobile, the main wrapper should stay full width (expanded)
    if (window.innerWidth > 768) {
        main.classList.toggle('expanded', isNowCollapsed);
    } else {
        main.classList.add('expanded');
    }
    
    toggleBtn.classList.toggle('active', !isNowCollapsed);
    
    // Update icon
    toggleBtn.innerHTML = isNowCollapsed ? '<i data-lucide="menu"></i>' : '<i data-lucide="chevron-left"></i>';
    
    // Refresh icons
    if (window.lucide) lucide.createIcons();
}

// â”€â”€ Section 1: Materiality Logic â”€â”€
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

        document.getElementById('resOverall').textContent = `â‚¹ ${overall.toFixed(2)}`;
        document.getElementById('resPerf').textContent = `â‚¹ ${performance.toFixed(2)}`;
        document.getElementById('resTrivial').textContent = `â‚¹ ${trivial.toFixed(2)}`;

        // Sync to Reports section
        const rptO = document.getElementById('rptOverall');
        const rptP = document.getElementById('rptPerf');
        const rptT = document.getElementById('rptTrivial');
        if (rptO) rptO.textContent = `â‚¹ ${overall.toFixed(2)} `;
        if (rptP) rptP.textContent = `â‚¹ ${performance.toFixed(2)}`;
        if (rptT) rptT.textContent = `â‚¹ ${trivial.toFixed(2)}`;

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

// â”€â”€ Section 2: Classification Logic â”€â”€
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

// â”€â”€ Section 3: Sampling Logic â”€â”€
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
    lastVouchFile = file;
    const status = document.getElementById('vouchStatus');
    const results = document.getElementById('vouchResults');
    const statusTitle = document.getElementById('vouchStatusTitle');
    const statusText = document.getElementById('vouchStatusText');
    const flagsText = document.getElementById('vouchFlagsText');
    
    status.classList.remove('hidden');
    results.classList.add('hidden');

    // Animate Agents
    const a1 = document.getElementById('agent1Status');
    const a2 = document.getElementById('agent2Status');
    const d1 = document.getElementById('agent1Dot');
    const d2 = document.getElementById('agent2Dot');

    // Reset styles
    a1.style.opacity = '0.4'; d1.className = 'status-dot';
    a2.style.opacity = '0.4'; d2.className = 'status-dot';
    document.getElementById('vouchTableBody').innerHTML = '';
    flagsText.textContent = "Agent 1 is starting deep OCR extraction...";

    // Agent 1 Active
    a1.style.opacity = '1'; d1.className = 'status-dot active';
    statusTitle.textContent = "Extracting Document...";
    statusText.textContent = "Agent 1 is performing deep OCR & layout analysis";
    
    await new Promise(r => setTimeout(r, 1200));
    
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('file', file);
    
    try {
        const res = await fetch('/api/vouch', { method: 'POST', body: fd });
        const data = await res.json();
        
        if (!res.ok || !data.data) {
            throw new Error(data.error || data.detail || 'Extraction failed.');
        }

        const modelName = data.model_used || "AI Ensemble";
        
        // Agent 1 Done, Agent 2 Active
        d1.className = 'status-dot done';
        a2.style.opacity = '1'; d2.className = 'status-dot active';
        statusTitle.textContent = "Verifying Ledger...";
        statusText.textContent = "Agent 2 is cross-referencing extracted data with ERP records";
        flagsText.innerHTML = `Agent 1 successfully extracted data via <strong>${modelName}</strong>. Agent 2 is now validating...`;

        await new Promise(r => setTimeout(r, 1500));

        d2.className = 'status-dot done';
        status.classList.add('hidden');
        results.classList.remove('hidden');

        const body = document.getElementById('vouchTableBody');
        body.innerHTML = data.data.map(row => `
            <tr>
                <td style="color:var(--text-secondary); font-size:12px;">${row.field}</td>
                <td style="font-weight:700; color:${row.field === 'Match Status' ? 'var(--success)' : 'white'}">${row.value}</td>
            </tr>
        `).join('');

        const matchStatusField = data.data.find(r => r.field === 'Match Status');
        const matchStatusText = matchStatusField ? matchStatusField.value : "Verified";

        document.getElementById('vouchFlagsTitle').textContent = "✅ Forensic Verification Complete";
        flagsText.innerHTML = `Audit Verdict: <strong style="color:var(--success);">${matchStatusText}</strong>. All data points persisted to reconciliation history.`;
        
        // Update History Table
        updateVouchHistory();

    } catch (err) {
        console.error(err);
        status.classList.add('hidden');
        alert('Vouching Error: ' + err.message);
    }
}

function regenerateVouch() {
    if (lastVouchFile) {
        runVouch(lastVouchFile);
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

async function runVouchingDownload() {
    try {
        const res = await fetch(`/api/download/vouching?session_id=${sessionId}`);
        if (!res.ok) {
            const errData = await res.json();
            throw new Error(errData.error || 'Failed to download report');
        }
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `Vouching_Reconciliation_Report.xlsx`;
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
        const coverage = data.stats.count > 0
            ? ((data.total_selected / data.stats.count) * 100).toFixed(1)
            : '0.0';
        document.getElementById('resCoverage').textContent = `${coverage}%`;

        // Sync to Reports section
        const rptIds = { rptTotalTxns: data.stats.count, rptTodCount: data.tod_count, rptTocCount: data.toc_count, rptTotalSel: data.total_selected };
        for (const [id, val] of Object.entries(rptIds)) {
            const el = document.getElementById(id);
            if (el) el.textContent = val.toLocaleString();
        }
        const rptCov = document.getElementById('rptCoverage');
        if (rptCov) rptCov.textContent = `${coverage}%`;

        // Render AI Insights (null-safe)
        const insightFocus = (data.ai_insights && data.ai_insights.focus) ? data.ai_insights.focus : 'AI Analysis';
        const insightSummary = (data.ai_insights && data.ai_insights.summary) ? data.ai_insights.summary : 'Analysis complete. Please review transactions manually.';
        document.getElementById('aiInsightText').innerHTML = `
            <strong>${insightFocus}</strong><br>
            ${insightSummary}
        `;
        
        // Populate Reports Section AI Output
        const aiOutput = document.getElementById('aiOutput');
        if (aiOutput) {
            aiOutput.innerHTML = `
                <div style="margin-bottom:8px;"><strong>${insightFocus}</strong></div>
                <div>${insightSummary}</div>
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

        // Render Forensic Dashboard
        if (data.dashboard) {
            renderDashboard(data.dashboard);
        }

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
        return `<td>${r[k] !== null ? r[k] : 'â€”'}</td>`;
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
                label: 'Transaction Value (â‚¹)',
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

// â”€â”€ Processing Overlay Animation â”€â”€
let stepInterval = null;

function showProcessingSteps() {
    const overlay = document.getElementById('processingOverlay');
    overlay.classList.remove('hidden');

    const steps = document.querySelectorAll('#processingSteps li');
    steps.forEach(li => {
        li.classList.remove('active', 'done');
        li.querySelector('.step-icon').textContent = 'â—‹';
    });

    let current = 0;
    clearInterval(stepInterval);
    stepInterval = setInterval(() => {
        if (current > 0 && current <= steps.length) {
            steps[current - 1].classList.remove('active');
            steps[current - 1].classList.add('done');
            steps[current - 1].querySelector('.step-icon').textContent = 'âœ“';
        }
        if (current < steps.length) {
            steps[current].classList.add('active');
            steps[current].querySelector('.step-icon').textContent = 'â—';
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

// â”€â”€ Forensic Dashboard Renderer â”€â”€
let trendChart = null;

function renderDashboard(db) {
    let container = document.getElementById('forensicDashboard');
    if (!container) {
        // Create dashboard container after sampling results
        const parent = document.getElementById('samplingResults');
        if (!parent) return;
        container = document.createElement('div');
        container.id = 'forensicDashboard';
        container.className = 'mt-24';
        parent.parentElement.insertBefore(container, parent.nextSibling);
    }

    const rc = db.risk_concentration || {};
    const gini = db.vendor_gini || 0;
    const rd = db.risk_distribution || {};
    const flags = db.forensic_flags || {};
    const topVendors = db.top_vendors || [];
    const trends = db.monthly_trends || [];

    const concentrationPct = ((rc.top_5pct_share || 0) * 100).toFixed(1);
    const giniLabel = gini > 0.6 ? 'High Concentration' : (gini > 0.4 ? 'Moderate' : 'Diversified');
    const giniColor = gini > 0.6 ? '#ef4444' : (gini > 0.4 ? '#f59e0b' : '#10b981');

    // Forensic flag pills
    const flagPills = Object.entries(flags)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([name, count]) => {
            const color = name.includes('Split') || name.includes('Round') ? '#ef4444'
                : name.includes('High') || name.includes('Above') ? '#f59e0b' : '#6366f1';
            return `<span style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;border-radius:20px;font-size:11px;font-weight:600;background:${color}18;color:${color};border:1px solid ${color}30;">${name} <span style="opacity:0.7;">(${count})</span></span>`;
        }).join('');

    // Top vendors list
    const vendorRows = topVendors.map((v, i) =>
        `<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;${i < topVendors.length - 1 ? 'border-bottom:1px solid rgba(255,255,255,0.06);' : ''}">
            <span style="font-size:12px;color:var(--text-primary);">${v.name}</span>
            <span style="font-size:12px;font-weight:700;color:var(--accent-primary);">â‚¹${Number(v.value).toLocaleString()}</span>
        </div>`
    ).join('');

    // Spike months
    const spikeMonths = trends.filter(t => t.is_spike);
    const spikeWarning = spikeMonths.length > 0
        ? `<div style="margin-top:8px;padding:8px 12px;border-radius:8px;background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);font-size:11px;color:#ef4444;">
            âš ï¸ Anomalous spikes detected in: ${spikeMonths.map(s => `<strong>${s.month}</strong> (z=${s.z_score})`).join(', ')}
           </div>`
        : '';

    container.innerHTML = `
        <div class="glass-card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                <h3 style="font-size:16px;">ðŸ”¬ Forensic Intelligence Dashboard</h3>
                <div class="badge badge-low" style="font-size:10px;">AI POWERED</div>
            </div>

            <!-- KPI Row -->
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">
                <div class="result-card">
                    <div class="result-value" style="color:${giniColor};">${gini.toFixed(2)}</div>
                    <div class="result-label">Vendor Gini <span style="font-size:9px;opacity:0.6;">(${giniLabel})</span></div>
                </div>
                <div class="result-card">
                    <div class="result-value" style="color:#f59e0b;">${concentrationPct}%</div>
                    <div class="result-label">Top 5% Value Share</div>
                </div>
                <div class="result-card">
                    <div class="result-value" style="color:#ef4444;">${rd.high || 0}</div>
                    <div class="result-label">High Risk Txns</div>
                </div>
                <div class="result-card">
                    <div class="result-value" style="color:#10b981;">${rd.low || 0}</div>
                    <div class="result-label">Low Risk Txns</div>
                </div>
            </div>

            <!-- Forensic Flags -->
            <div style="margin-bottom:20px;">
                <h4 style="font-size:13px;margin-bottom:10px;color:var(--text-secondary);">Forensic Risk Flags</h4>
                <div style="display:flex;flex-wrap:wrap;gap:6px;">
                    ${flagPills || '<span class="text-muted" style="font-size:12px;">No anomalies detected</span>'}
                </div>
            </div>

            <!-- Two Column: Vendors + Trend -->
            <div style="display:grid;grid-template-columns:1fr 1.5fr;gap:16px;">
                <div style="padding:14px;background:rgba(255,255,255,0.02);border-radius:12px;border:1px solid var(--glass-border);">
                    <h4 style="font-size:13px;margin-bottom:10px;">Top Vendors by Value</h4>
                    ${vendorRows || '<span class="text-muted" style="font-size:12px;">No vendor data</span>'}
                </div>
                <div style="padding:14px;background:rgba(255,255,255,0.02);border-radius:12px;border:1px solid var(--glass-border);">
                    <h4 style="font-size:13px;margin-bottom:10px;">Monthly Transaction Trends</h4>
                    <div style="height:160px;position:relative;">
                        <canvas id="trendChartCanvas"></canvas>
                    </div>
                    ${spikeWarning}
                </div>
            </div>
        </div>
    `;

    // Draw trend chart
    if (trends.length > 0) {
        renderTrendChart(trends);
    }
}

function renderTrendChart(trends) {
    const ctx = document.getElementById('trendChartCanvas')?.getContext('2d');
    if (!ctx) return;
    if (trendChart) trendChart.destroy();

    const labels = trends.map(t => t.month);
    const values = trends.map(t => t.value);
    const counts = trends.map(t => t.count);
    const bgColors = trends.map(t =>
        t.is_spike ? 'rgba(239,68,68,0.6)' : 'rgba(99,102,241,0.4)'
    );
    const borderColors = trends.map(t =>
        t.is_spike ? '#ef4444' : '#6366f1'
    );

    trendChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Txn Value (â‚¹)',
                    data: values,
                    backgroundColor: bgColors,
                    borderColor: borderColors,
                    borderWidth: 2,
                    borderRadius: 6,
                    yAxisID: 'y'
                },
                {
                    label: 'Txn Count',
                    data: counts,
                    type: 'line',
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16,185,129,0.1)',
                    borderWidth: 2,
                    pointRadius: 3,
                    pointBackgroundColor: '#10b981',
                    fill: true,
                    tension: 0.4,
                    yAxisID: 'y1'
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: true, labels: { color: '#94a3b8', font: { size: 10 } } }
            },
            scales: {
                y: {
                    type: 'linear', position: 'left',
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#94a3b8', font: { size: 9 } }
                },
                y1: {
                    type: 'linear', position: 'right',
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#10b981', font: { size: 9 } }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#94a3b8', font: { size: 9 }, maxRotation: 45 }
                }
            }
        }
    });
}

async function updateVouchHistory() {
    const section = document.getElementById('vouchHistorySection');
    const body = document.getElementById('vouchHistoryBody');
    const count = document.getElementById('vouchCount');
    
    if (!section || !body || !sessionId) return;
    
    try {
        const res = await fetch(`/api/vouch/history?session_id=${sessionId}`);
        const data = await res.json();
        
        if (data.data && data.data.length > 0) {
            section.classList.remove('hidden');
            count.textContent = `${data.data.length} Invoices Processed`;
            
            body.innerHTML = data.data.map(res => {
                const fields = {};
                if (res.extracted_data) {
                    res.extracted_data.forEach(item => fields[item.field] = item.value);
                }
                
                // Flexible mapping for different AI models
                const invNo = fields['Invoice Number'] || fields['Invoice No'] || fields['Invoice #'] || 'N/A';
                const date = fields['Date'] || fields['Invoice Date'] || 'N/A';
                const total = fields['Grand Total'] || fields['Total Amount'] || fields['Amount'] || '0.00';
                const vendor = fields['Vendor Name'] || fields['Vendor'] || 'Extracted';

                return `
                    <tr>
                        <td style="padding:16px 24px; font-weight:600;">${invNo}</td>
                        <td style="padding:16px 24px; color:var(--text-secondary);">${date}</td>
                        <td style="padding:16px 24px;">${vendor}</td>
                        <td style="padding:16px 24px; font-weight:800; color:var(--accent-primary);">${total}</td>
                        <td style="padding:16px 24px;">
                            <span class="badge badge-low">Verified</span>
                        </td>
                        <td style="padding:16px 24px; text-align:right;">
                            <button class="btn-secondary" style="padding:4px 8px; font-size:10px;">Details</button>
                        </td>
                    </tr>
                `;
            }).join('');
        }
    } catch (err) {
        console.error('History Error:', err);
    }
}


