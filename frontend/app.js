
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
let isLargeAudit = true; 
let isSubstantiveForced = false; 
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

    // Retrieve or create Session ID
    sessionId = getOrCreateSessionId();
    console.log('Session:', sessionId);

    // Mobile init
    if (window.innerWidth <= 768) {
        const sidebar = document.querySelector('.sidebar');
        if (sidebar) sidebar.classList.add('collapsed');
    }

    // Bind Global Export PDF
    const exportPdfBtn = document.getElementById('exportPdfBtn');
    if (exportPdfBtn) {
        exportPdfBtn.addEventListener('click', () => {
            window.print();
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

    // Sidebar & Main Visibility
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
        if (sidebar) sidebar.classList.remove('hidden');
        if (toggleBtn) toggleBtn.classList.remove('hidden');
        if (topBar) topBar.classList.remove('hidden');
    }

    // Update Tab Active State
    const tabMap = {
        'planning-section': 'tab-planning',
        'analysis-section': 'tab-analysis',
        'sampling-section': 'tab-sampling'
    };
    
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    const activeTabId = tabMap[sectionId];
    if (activeTabId) {
        document.getElementById(activeTabId)?.classList.add('active');
    }

    // Update Sidebar Active Link
    document.querySelectorAll('.nav-link').forEach(link => {
        link.classList.remove('active');
        if (link.dataset.target === sectionId) link.classList.add('active');
    });

    // Progress Bar
    const stages = ['planning-section', 'analysis-section', 'sampling-section', 'vouching-section'];
    const currentIdx = stages.indexOf(sectionId);
    if (topBar && currentIdx !== -1) {
        const pct = ((currentIdx + 1) / stages.length) * 100;
        topBar.style.width = pct + '%';
    }
}

function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const main = document.querySelector('.main-wrapper');
    const toggleBtn = document.getElementById('sidebarToggle');
    if (!sidebar || !main || !toggleBtn) return;
    
    const isNowCollapsed = sidebar.classList.toggle('collapsed');
    if (window.innerWidth > 768) main.classList.toggle('expanded', isNowCollapsed);
    
    toggleBtn.innerHTML = isNowCollapsed ? '<i data-lucide="menu"></i>' : '<i data-lucide="chevron-left"></i>';
    if (window.lucide) lucide.createIcons();
}

// ── Section 1: Materiality Logic ──
function initMaterialityLogic() {
    const calcBtn = document.getElementById('calcMaterialityBtn');
    if (!calcBtn) return;

    // Range Sliders Label Sync
    const overallSlider = document.getElementById('overallPct');
    const perfSlider = document.getElementById('perfPct');
    const trivialSlider = document.getElementById('trivialPct');
    const benchmarkSelect = document.getElementById('materialityBenchmark');
    const rommSelect = document.getElementById('rommLevel');

    const updateLabels = () => {
        document.getElementById('labelOverallPct').textContent = overallSlider.value + '%';
        document.getElementById('labelPerfPct').textContent = perfSlider.value + '%';
        document.getElementById('labelTrivialPct').textContent = trivialSlider.value + '%';
    };

    overallSlider.addEventListener('input', updateLabels);
    perfSlider.addEventListener('input', updateLabels);
    trivialSlider.addEventListener('input', updateLabels);

    // Auto-adjust Overall % based on Benchmark/Risk
    const autoAdjustOverall = () => {
        const bench = benchmarkSelect.value;
        const risk = rommSelect.value;
        let base = 5.0; // Default NPBT Medium

        if (bench === 'NPBT') {
            base = risk === 'High' ? 5.0 : (risk === 'Low' ? 10.0 : 7.5);
        } else if (bench === 'REVENUE') {
            base = risk === 'High' ? 0.5 : (risk === 'Low' ? 1.0 : 0.75);
        } else if (bench === 'ASSETS') {
            base = risk === 'High' ? 1.0 : (risk === 'Low' ? 2.0 : 1.5);
        }
        
        overallSlider.value = base;
        updateLabels();
    };

    benchmarkSelect.addEventListener('change', autoAdjustOverall);
    rommSelect.addEventListener('change', autoAdjustOverall);

    calcBtn.addEventListener('click', async () => {
        const val = parseFloat(document.getElementById('materialityValue').value);
        if (isNaN(val)) return alert("Please enter a benchmark value.");

        const fd = new FormData();
        fd.append('session_id', sessionId);
        fd.append('value', val);
        fd.append('benchmark', benchmarkSelect.value);
        fd.append('romm', rommSelect.value);
        fd.append('perf_pct', perfSlider.value);
        fd.append('trivial_pct', trivialSlider.value);
        fd.append('overall_pct', overallSlider.value);

        try {
            const res = await fetch('/api/materiality', { method: 'POST', body: fd });
            const data = await res.json();
            
            document.getElementById('resOverall').textContent = `₹ ${data.overall_materiality.toLocaleString(undefined, {minimumFractionDigits:2})}`;
            document.getElementById('resPerf').textContent = `₹ ${data.performance_materiality.toLocaleString(undefined, {minimumFractionDigits:2})}`;
            document.getElementById('resTrivial').textContent = `₹ ${data.trivial_threshold.toLocaleString(undefined, {minimumFractionDigits:2})}`;
            
            // Sync Reports
            document.getElementById('rptOverall').textContent = `₹ ${data.overall_materiality.toLocaleString()}`;
            document.getElementById('rptPerf').textContent = `₹ ${data.performance_materiality.toLocaleString()}`;
            document.getElementById('rptTrivial').textContent = `₹ ${data.trivial_threshold.toLocaleString()}`;

            document.getElementById('materialityResults').classList.remove('hidden');
            
            // Auto-advance
            setTimeout(() => navigateTo('analysis-section'), 800);
        } catch (e) {
            console.error(e);
            alert("Calculation failed.");
        }
    });
}

// ── Section 2: Classification Logic ──
function initClassificationLogic() {
    const assessBtn = document.getElementById('assessRiskBtn');
    if (!assessBtn) return;

    document.querySelectorAll('.option-card input').forEach(input => {
        input.addEventListener('change', () => {
            input.closest('.option-card').classList.toggle('active', input.checked);
            updateLiveClassification();
        });
    });

    assessBtn.addEventListener('click', async () => {
        updateLiveClassification();
        const fd = new FormData();
        fd.append('session_id', sessionId);
        fd.append('turnover_250', document.getElementById('checkTurnover').checked);
        fd.append('ifc', document.getElementById('checkIFC').checked);
        fd.append('governance', document.getElementById('checkGov').checked);
        fd.append('misstatements', document.getElementById('checkMis').checked);

        try {
            await fetch('/api/risk-assessment', { method: 'POST', body: fd });
            document.getElementById('riskResults').classList.remove('hidden');
            setTimeout(() => navigateTo('sampling-section'), 800);
        } catch (e) { console.error(e); }
    });
}

function updateLiveClassification() {
    const isPie = document.getElementById('checkTurnover').checked;
    const isIfc = document.getElementById('checkIFC').checked;
    const isWeakControls = document.getElementById('checkGov').checked;
    const isHistory = document.getElementById('checkMis').checked;

    const isLarge = isPie || isIfc || isWeakControls || isHistory;
    isSubstantiveForced = isWeakControls; // Weak controls force 100% TOD

    const resType = document.getElementById('resAuditType');
    const resClass = document.getElementById('resClassification');

    if (isLarge) {
        resType.textContent = 'LARGE AUDIT';
        resType.style.color = '#2563EB';
        resClass.textContent = isSubstantiveForced 
            ? 'Forced Substantive Approach (100% TOD) due to Control Risk.' 
            : 'Combined approach (TOD + TOC) applicable for this engagement.';
        isLargeAudit = true;
    } else {
        resType.textContent = 'SMALL AUDIT';
        resType.style.color = '#10b981';
        resClass.textContent = 'Substantive approach (TOD only) sufficient for this engagement.';
        isLargeAudit = false;
    }

    // Toggle TOD/TOC Sliders
    const splitConfig = document.getElementById('splitConfigRow');
    const forcedMsg = document.getElementById('forcedSubstantiveMsg');
    const todSlider = document.getElementById('todPctSlider');

    if (!isLargeAudit || isSubstantiveForced) {
        if (todSlider) {
            todSlider.value = 100;
            todSlider.disabled = true;
        }
        if (forcedMsg) forcedMsg.classList.toggle('hidden', !isSubstantiveForced);
    } else {
        if (todSlider) {
            todSlider.disabled = false;
            if (todSlider.value == 100) todSlider.value = 70;
        }
        if (forcedMsg) forcedMsg.classList.add('hidden');
    }

    updateSamplingSplitDisplay();
}

// ── Section 3: Sampling Logic ──
function initSamplingLogic() {
    const zone = document.getElementById('uploadZone');
    const input = document.getElementById('fileUpload');
    if (zone && input) {
        zone.addEventListener('click', () => input.click());
        input.addEventListener('change', e => {
            if (e.target.files[0]) {
                uploadedFile = e.target.files[0];
                document.getElementById('fileNameDisplay').textContent = `Uploaded: ${uploadedFile.name}`;
                document.getElementById('samplingStep2').style.display = 'block';
            }
        });
    }

    document.getElementById('analyzeBtn')?.addEventListener('click', runAnalysis);
    document.getElementById('downloadBtn')?.addEventListener('click', runDownload);
    document.getElementById('downloadBtn2')?.addEventListener('click', runDownload);

    document.getElementById('sampleCountInput')?.addEventListener('input', updateSamplingSplitDisplay);
    document.getElementById('todPctSlider')?.addEventListener('input', updateSamplingSplitDisplay);
    document.getElementById('auditCategory')?.addEventListener('change', (e) => selectedCategory = e.target.value);
}

function updateSamplingSplitDisplay() {
    const total = parseInt(document.getElementById('sampleCountInput')?.value) || 0;
    const todSlider = document.getElementById('todPctSlider');
    const display = document.getElementById('todPctDisplay');
    
    if (!display) return;
    
    if (!isLargeAudit || isSubstantiveForced) {
        display.textContent = `${total} TOD / 0 TOC`;
        return;
    }
    
    const todPct = parseInt(todSlider?.value || 70);
    const todCount = Math.ceil(total * todPct / 100);
    const tocCount = total - todCount;
    display.textContent = `${todCount} TOD / ${tocCount} TOC`;
}

function selectBasis(btn) {
    document.querySelectorAll('[data-basis]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    selectedBasis = btn.dataset.basis;
}

async function runAnalysis() {
    if (!uploadedFile) return alert("Please upload a ledger file first.");
    const total = document.getElementById('sampleCountInput').value;
    const todPct = isLargeAudit && !isSubstantiveForced ? document.getElementById('todPctSlider').value : 100;

    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('file', uploadedFile);
    fd.append('category', selectedCategory);
    fd.append('target_count', total);
    fd.append('sampling_basis', selectedBasis);
    fd.append('tod_pct', todPct);
    fd.append('audit_type', isLargeAudit ? 'large' : 'small');

    const btn = document.getElementById('analyzeBtn');
    btn.disabled = true;
    btn.textContent = "Analyzing...";

    try {
        const res = await fetch('/api/analyze', { method: 'POST', body: fd });
        const data = await res.json();
        
        document.getElementById('resTotalTxns').textContent = data.stats.count.toLocaleString();
        document.getElementById('resTodCount').textContent = data.tod_count;
        document.getElementById('resTocCount').textContent = data.toc_count;
        document.getElementById('resTotalSelected').textContent = data.total_selected;
        document.getElementById('resCoverage').textContent = ((data.total_selected / data.stats.count) * 100).toFixed(1) + '%';
        
        document.getElementById('aiInsightText').textContent = data.ai_insights?.summary || "Analysis complete.";
        renderChart(data.stats);
        renderPreview(data.top_10);

        document.getElementById('samplingResults').classList.remove('hidden');
        document.getElementById('downloadBtn2').disabled = false;
    } catch (e) {
        console.error(e);
        alert("Analysis failed.");
    } finally {
        btn.disabled = false;
        btn.textContent = "Analyze & Generate Samples";
    }
}

async function runDownload() {
    const total = document.getElementById('sampleCountInput').value;
    const todPct = isLargeAudit && !isSubstantiveForced ? document.getElementById('todPctSlider').value : 100;

    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('file', uploadedFile);
    fd.append('category', selectedCategory);
    fd.append('target_count', total);
    fd.append('sampling_basis', selectedBasis);
    fd.append('tod_pct', todPct);
    fd.append('audit_type', isLargeAudit ? 'large' : 'small');

    const res = await fetch('/api/download', { method: 'POST', body: fd });
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `StatAudit_Working_Papers_${selectedCategory}.xlsx`;
    a.click();
}

function renderChart(stats) {
    const ctx = document.getElementById('samplingChart').getContext('2d');
    if (auditChart) auditChart.destroy();
    auditChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Sampled', 'Remaining'],
            datasets: [{
                data: [1, 9],
                backgroundColor: ['#6366f1', 'rgba(255,255,255,0.05)'],
                borderWidth: 0
            }]
        },
        options: { cutout: '80%', plugins: { legend: { display: false } } }
    });
}

function renderPreview(data) {
    if (!data || data.length === 0) return;
    const head = document.getElementById('previewHead');
    const body = document.getElementById('previewBody');
    const cols = Object.keys(data[0]);
    head.innerHTML = `<tr>${cols.map(c => `<th>${c}</th>`).join('')}</tr>`;
    body.innerHTML = data.map(row => `<tr>${cols.map(c => `<td>${row[c]}</td>`).join('')}</tr>`).join('');
}

// ── Vouching Logic ──
function initVouchingLogic() {
    document.getElementById('vouchUploadZone')?.addEventListener('click', () => document.getElementById('vouchFileInput').click());
    document.getElementById('vouchFileInput')?.addEventListener('change', e => {
        if (e.target.files[0]) runVouch(e.target.files[0]);
    });
}

async function runVouch(file) {
    lastVouchFile = file;
    const fd = new FormData();
    fd.append('session_id', sessionId);
    fd.append('file', file);
    
    document.getElementById('vouchStatus').classList.remove('hidden');
    
    try {
        const res = await fetch('/api/vouch', { method: 'POST', body: fd });
        const data = await res.json();
        
        const body = document.getElementById('vouchTableBody');
        body.innerHTML = data.data.map(row => `
            <tr>
                <td>${row.field}</td>
                <td style="font-weight:700;">${row.value}</td>
            </tr>
        `).join('');
        document.getElementById('vouchResults').classList.remove('hidden');
        updateVouchHistory();
    } catch (e) { alert("Vouching failed."); }
    finally { document.getElementById('vouchStatus').classList.add('hidden'); }
}

async function updateVouchHistory() {
    const res = await fetch(`/api/vouch/history?session_id=${sessionId}`);
    const data = await res.json();
    const body = document.getElementById('vouchHistoryBody');
    body.innerHTML = data.data.map(item => `
        <tr>
            <td style="padding:16px 24px;">${item.extracted_data.find(d => d.field === 'Invoice No')?.value || 'N/A'}</td>
            <td>${item.extracted_data.find(d => d.field === 'Date')?.value || 'N/A'}</td>
            <td>${item.extracted_data.find(d => d.field === 'Vendor Name')?.value || 'N/A'}</td>
            <td>${item.extracted_data.find(d => d.field === 'Gross Amount')?.value || 'N/A'}</td>
            <td><span class="badge badge-low">${item.extracted_data.find(d => d.field === 'Match Status')?.value || 'Verified'}</span></td>
            <td style="text-align:right; padding-right:24px;"><button class="btn-secondary" style="padding:4px 8px; font-size:10px;">View</button></td>
        </tr>
    `).join('');
}

function showProcessingSteps() {
    // Legacy logic if needed
}
