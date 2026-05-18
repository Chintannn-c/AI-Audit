import { useState, useRef, useEffect } from 'react'
import { useSession } from '../context/SessionContext'
import { useAudit } from '../context/AuditContext'
import FileDropZone from '../components/FileDropZone'
import { Chart as ChartJS, registerables } from 'chart.js'
import { Bar } from 'react-chartjs-2'

ChartJS.register(...registerables)

export default function SamplingPage({ setProcessing }) {
  const { secureFetch, sessionId } = useSession()
  const { riskClassification, uploadedFile, setUploadedFile, selectedCategory, setSelectedCategory, selectedBasis, setSelectedBasis, setSamplingResults, setAiInsights, setDashboard, unlockStage } = useAudit()
  const isLargeAudit = riskClassification.isLargeAudit

  const [fileName, setFileName] = useState('')
  const [showStep2, setShowStep2] = useState(false)
  const [targetCount, setTargetCount] = useState(100)
  const [todPct, setTodPct] = useState(70)
  const [localTodPct, setLocalTodPct] = useState(70)
  const [showResults, setShowResults] = useState(false)
  const [results, setResults] = useState(null)
  const [chartData, setChartData] = useState(null)
  const [preview, setPreview] = useState(null)
  const [dashboardData, setDashboardData] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)

  useEffect(() => {
    setLocalTodPct(todPct)
  }, [todPct])

  const todCount = Math.ceil(targetCount * todPct / 100)
  const tocCount = isLargeAudit ? targetCount - todCount : 0
  const splitDisplay = isLargeAudit ? `${todCount} TOD / ${tocCount} TOC` : `${targetCount} TOD / 0 TOC`

  const handleFileSelect = (file) => {
    setUploadedFile(file)
    setFileName(file.name)
    setShowStep2(true)
  }

  const runAnalysis = async () => {
    if (!uploadedFile) return alert('Please upload a ledger file first.')
    const fd = new FormData()
    fd.append('session_id', sessionId)
    fd.append('file', uploadedFile)
    fd.append('category', selectedCategory)
    fd.append('target_count', targetCount)
    fd.append('sampling_basis', selectedBasis)
    fd.append('tod_pct', isLargeAudit ? todPct : 100)
    fd.append('audit_type', isLargeAudit ? 'large' : 'small')

    setAnalyzing(true)
    setProcessing(true)
    try {
      const res = await secureFetch('/api/analyze', { method: 'POST', body: fd })
      const data = await res.json()
      if (data.error) throw new Error(data.error)

      // Compute coverage
      let coverage = '0.0'
      const basis = data.sampling_basis || 'count'
      if (basis === 'value') {
        const totalVal = data.stats.total_value || 1
        const selectedVal = (data.tod_value || 0) + (data.toc_value || 0)
        coverage = ((selectedVal / totalVal) * 100).toFixed(1)
      } else {
        coverage = data.stats.count > 0 ? ((data.total_selected / data.stats.count) * 100).toFixed(1) : '0.0'
      }

      const r = { ...data, coverage, coverageBasis: basis }
      setResults(r)
      setSamplingResults(r)

      // AI Insights
      const focus = typeof data.ai_insights?.focus === 'object' ? JSON.stringify(data.ai_insights.focus) : (data.ai_insights?.focus || 'AI Analysis')
      const summary = typeof data.ai_insights?.summary === 'object' ? JSON.stringify(data.ai_insights.summary) : (data.ai_insights?.summary || 'Analysis complete. Please review transactions manually.')
      setAiInsights({ focus, summary })

      // Chart data
      setChartData({
        labels: ['Minimum', 'Average', 'Maximum'],
        datasets: [{
          label: 'Transaction Value (₹)',
          data: [data.stats.minimum, data.stats.average, data.stats.maximum],
          backgroundColor: ['rgba(16,185,129,0.5)', 'rgba(99,102,241,0.5)', 'rgba(239,68,68,0.5)'],
          borderColor: ['#10b981', '#6366f1', '#ef4444'],
          borderWidth: 2,
          borderRadius: 8
        }]
      })

      // Preview
      setPreview(data.top_10 || [])

      // Dashboard
      if (data.dashboard) {
        setDashboardData(data.dashboard)
        setDashboard(data.dashboard)
      }

      setShowResults(true)
      unlockStage(4)
    } catch (err) {
      console.error(err)
      alert('Analysis Error: ' + err.message)
    } finally {
      setAnalyzing(false)
      setProcessing(false)
    }
  }

  const runDownload = async () => {
    if (!uploadedFile) return alert('Please upload a ledger file first.')
    const fd = new FormData()
    fd.append('session_id', sessionId)
    fd.append('file', uploadedFile)
    fd.append('category', selectedCategory)
    fd.append('target_count', targetCount)
    fd.append('sampling_basis', selectedBasis)
    fd.append('tod_pct', isLargeAudit ? todPct : 100)
    fd.append('audit_type', isLargeAudit ? 'large' : 'small')

    try {
      const res = await secureFetch('/api/download', { method: 'POST', body: fd })
      if (!res.ok) {
        const errorData = await res.json()
        throw new Error(errorData.error || `Server responded with ${res.status}`)
      }
      const blob = await res.blob()
      if (blob.size < 100) throw new Error('Generated report is empty.')
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `StatAudit_Working_Papers_${selectedCategory}_${targetCount}.xlsx`.replace(/\s+/g, '_')
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Download Failed:', err)
      alert('Download Error: ' + err.message)
    }
  }

  const chartOptions = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
      x: { grid: { display: false }, ticks: { color: '#94a3b8' } }
    }
  }

  return (
    <section className="content-section">
      <div className="section-header">
        <h2>AI Audit Sampling Engine</h2>
        <p>Upload ledger, configure sampling, and download enterprise audit working papers.</p>
      </div>

      {/* Step 1 */}
      <div className="glass-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ fontSize: 15 }}>☁ Step 1 — Select Area & Upload Ledger</h3>
          <div className="badge badge-low">STEP 1 OF 2</div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 16 }}>
          {['Sales', 'Expenses', 'Purchases'].map(cat => (
            <button key={cat} className={`toggle-option ${selectedCategory === cat ? 'active' : ''}`} onClick={() => setSelectedCategory(cat)}>
              {cat === 'Sales' ? '📊' : cat === 'Expenses' ? '💰' : '🛒'} {cat}
            </button>
          ))}
        </div>
        <FileDropZone onFileSelect={handleFileSelect} accept=".xlsx,.xls,.csv" label="Drag & Drop Ledger File" sublabel="or click to browse — supports .xlsx, .xls, .csv" fileName={fileName} />
      </div>

      {/* Step 2 */}
      {showStep2 && (
        <div className="glass-card mt-24">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <h3 style={{ fontSize: 15 }}>⚙ Step 2 — Configure Sampling</h3>
            <div className="badge badge-low">STEP 2 OF 2</div>
          </div>
          <div className="config-panel">
            <div>
              <label className="form-label">Total Number of Samples</label>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <input type="number" className="glass-input" value={targetCount} min={1} onChange={(e) => setTargetCount(parseInt(e.target.value) || 0)} style={{ flex: 1 }} />
                <span className="text-muted">samples</span>
              </div>
            </div>

            {isLargeAudit && (
              <div>
                <label className="form-label">TOD / TOC Split Ratio</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <input 
                    type="range" 
                    className="range-slider" 
                    min={50} 
                    max={90} 
                    value={localTodPct} 
                    onChange={(e) => setLocalTodPct(parseInt(e.target.value))}
                    onMouseUp={() => setTodPct(localTodPct)}
                    onTouchEnd={() => setTodPct(localTodPct)}
                    style={{ flex: 1 }} 
                  />
                  <span style={{ fontWeight: 700, color: 'var(--accent-primary)', minWidth: 140, textAlign: 'center' }}>
                    {isLargeAudit ? `${Math.ceil(targetCount * localTodPct / 100)} TOD / ${targetCount - Math.ceil(targetCount * localTodPct / 100)} TOC` : `${targetCount} TOD / 0 TOC`}
                  </span>
                </div>
              </div>
            )}

            <div className="full-width">
              <label className="form-label">Sampling Basis</label>
              <div className="toggle-group">
                <button className={`toggle-option ${selectedBasis === 'count' ? 'active' : ''}`} onClick={() => setSelectedBasis('count')}>📋 By Number of Transactions</button>
                <button className={`toggle-option ${selectedBasis === 'value' ? 'active' : ''}`} onClick={() => setSelectedBasis('value')}>💵 By Total Transaction Value</button>
              </div>
            </div>

            <div className="full-width" style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 10 }}>
              <button className="btn-primary" style={{ padding: '12px 32px', fontSize: 14 }} onClick={runAnalysis} disabled={analyzing}>
                {analyzing ? '⏳ Analyzing...' : '⚙ Analyze & Generate Samples'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {showResults && results && (
        <div className="mt-24">
          <div className="glass-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h3>📊 Sampling Results</h3>
              <div style={{ display: 'flex', gap: 12 }}>
                <button className="btn-secondary" onClick={() => { setShowResults(false); setShowStep2(true) }}>🔄 Regenerate</button>
                <button className="btn-primary" onClick={runDownload}>📥 Download Working Papers</button>
              </div>
            </div>

            <div className="results-grid">
              {[
                { label: 'Total Transactions', value: results.stats?.count?.toLocaleString() || '0' },
                { label: 'TOD Samples', value: results.tod_count?.toLocaleString() || '0' },
                { label: 'TOC Samples', value: results.toc_count?.toLocaleString() || '0' },
                { label: 'Total Selected', value: results.total_selected?.toLocaleString() || '0' },
                { label: results.coverageBasis === 'value' ? 'Value Coverage' : 'Transaction Coverage', value: `${results.coverage}%` }
              ].map((item, i) => (
                <div key={i} className="result-card">
                  <div className="result-value">{item.value}</div>
                  <div className="result-label">{item.label}</div>
                </div>
              ))}
            </div>

            {/* Vendor Repetition Audit Intelligence Card */}
            {results.repetition_info && (
              <div className="mt-16" style={{
                background: 'rgba(99, 102, 241, 0.04)',
                border: '1px solid rgba(99, 102, 241, 0.15)',
                padding: '18px 22px',
                borderRadius: '16px',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '24px'
              }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-primary)', fontWeight: 'bold', fontSize: '14px' }}>
                    <span>🔍</span>
                    <span>Vendor Repetition Analysis</span>
                  </div>
                  <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1', lineHeight: '1.5' }}>
                    Statutory audit intelligence verifies the concentration of selected samples across different vendors. 
                    No individual vendor exceeds your absolute repeat limit.
                  </p>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '8px' }}>
                    <div style={{ background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.15)', padding: '10px 14px', borderRadius: '12px' }}>
                      <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#34d399' }}>
                        {results.repetition_info.unique_vendors_count}
                      </div>
                      <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>Unique Vendors</div>
                    </div>
                    <div style={{ background: 'rgba(245, 158, 11, 0.08)', border: '1px solid rgba(245, 158, 11, 0.15)', padding: '10px 14px', borderRadius: '12px' }}>
                      <div style={{ fontSize: '18px', fontWeight: 'bold', color: '#fbbf24' }}>
                        {results.repetition_info.repeated_vendors_count}
                      </div>
                      <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>Repeated Vendors</div>
                    </div>
                  </div>
                </div>

                <div style={{ borderLeft: '1px solid rgba(255, 255, 255, 0.08)', paddingLeft: '24px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#94a3b8', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Repeated Vendors Breakdown
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '120px', overflowY: 'auto', paddingRight: '8px' }}>
                    {results.repetition_info.repeated_vendors_details && results.repetition_info.repeated_vendors_details.length > 0 ? (
                      results.repetition_info.repeated_vendors_details.map((detail, idx) => (
                        <div key={idx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255, 255, 255, 0.02)', padding: '6px 12px', borderRadius: '8px', border: '1px solid rgba(255, 255, 255, 0.04)' }}>
                          <span style={{ fontSize: '12px', color: '#e2e8f0', fontWeight: 500 }}>{detail.vendor}</span>
                          <span className="badge badge-medium" style={{ fontSize: '10px', padding: '2px 8px' }}>
                            {detail.count} times
                          </span>
                        </div>
                      ))
                    ) : (
                      <div style={{ fontSize: '12px', color: '#64748b', fontStyle: 'italic', display: 'flex', alignItems: 'center', height: '100%', minHeight: '80px' }}>
                        ✅ Absolute strict non-repetition: All selected vendors are 100% unique!
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {results.deficit_info && (
              <div className="mt-16" style={{
                background: 'rgba(239, 68, 68, 0.08)',
                border: '1px solid rgba(239, 68, 68, 0.25)',
                padding: '16px 20px',
                borderRadius: '16px',
                display: 'flex',
                flexDirection: 'column',
                gap: '8px'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#f87171', fontWeight: 'bold', fontSize: '14px' }}>
                  <span>⚠️</span>
                  <span>Sampling Capping Notice: Deficit in Selected Samples</span>
                </div>
                <p style={{ margin: 0, fontSize: '13px', color: '#cbd5e1', lineHeight: '1.6' }}>
                  {results.deficit_info.explanation}
                </p>
                <div style={{ display: 'flex', gap: '24px', fontSize: '12px', color: '#94a3b8', borderTop: '1px solid rgba(255, 255, 255, 0.08)', paddingTop: '8px', marginTop: '4px' }}>
                  <span><strong>Requested Size:</strong> {results.deficit_info.requested}</span>
                  <span><strong>Actual Selected:</strong> {results.deficit_info.selected}</span>
                  <span><strong>Shortfall:</strong> {results.deficit_info.deficit} samples</span>
                </div>
              </div>
            )}


            <div className="mt-16" style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: 16, alignItems: 'center' }}>
              <div style={{ background: 'rgba(99,102,241,0.05)', padding: 20, borderRadius: 16, borderLeft: '4px solid var(--accent-primary)', height: '100%', display: 'flex', alignItems: 'center' }}>
                <p className="text-secondary" style={{ margin: 0, fontSize: 13, lineHeight: 1.6 }}>
                  <strong>{typeof results.ai_insights?.focus === 'object' ? JSON.stringify(results.ai_insights.focus) : (results.ai_insights?.focus || 'AI Analysis')}</strong><br />
                  {typeof results.ai_insights?.summary === 'object' ? JSON.stringify(results.ai_insights.summary) : (results.ai_insights?.summary || 'Analysis complete. Please review transactions manually.')}
                </p>
              </div>
              <div style={{ height: 140, width: '100%', position: 'relative' }}>
                {chartData && <Bar key={selectedCategory} data={chartData} options={chartOptions} />}
              </div>
            </div>

            {/* Preview Table */}
            {preview && preview.length > 0 && (
              <div className="mt-32">
                <h4 style={{ marginBottom: 16 }}>Top Transactions (Highest Value)</h4>
                <div className="table-container">
                  <table className="premium-table">
                    <thead>
                      <tr>
                        {Object.keys(preview[0]).filter(k => !k.startsWith('_Risk_') || k === '_Risk_Category').map(k => (
                          <th key={k}>{k.replace(/^_/, '').replace(/_/g, ' ')}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.map((row, i) => (
                        <tr key={i}>
                          {Object.keys(row).filter(k => !k.startsWith('_Risk_') || k === '_Risk_Category').map(k => (
                            <td key={k}>
                              {k === '_Risk_Category'
                                ? <span className={`badge badge-${(row[k] || 'Low').toLowerCase()}`}>{row[k] || 'LOW'}</span>
                                : (row[k] !== null ? row[k] : '—')
                              }
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>

          {/* Forensic Dashboard */}
          {dashboardData && <ForensicDashboard data={dashboardData} />}
        </div>
      )}
    </section>
  )
}

function ForensicDashboard({ data }) {
  const rc = data.risk_concentration || {}
  const gini = data.vendor_gini || 0
  const rd = data.risk_distribution || {}
  const flags = data.forensic_flags || {}
  const topVendors = data.top_vendors || []
  const trends = data.monthly_trends || []

  const concentrationPct = ((rc.top_5pct_share || 0) * 100).toFixed(1)
  const giniLabel = gini > 0.6 ? 'High Concentration' : (gini > 0.4 ? 'Moderate' : 'Diversified')
  const giniColor = gini > 0.6 ? '#ef4444' : (gini > 0.4 ? '#f59e0b' : '#10b981')

  const flagEntries = Object.entries(flags).sort((a, b) => b[1] - a[1]).slice(0, 8)
  const spikeMonths = trends.filter(t => t.is_spike)

  // Trend chart data
  const trendChartData = trends.length > 0 ? {
    labels: trends.map(t => t.month),
    datasets: [
      {
        label: 'Txn Value (₹)', data: trends.map(t => t.value),
        backgroundColor: trends.map(t => t.is_spike ? 'rgba(239,68,68,0.6)' : 'rgba(99,102,241,0.4)'),
        borderColor: trends.map(t => t.is_spike ? '#ef4444' : '#6366f1'),
        borderWidth: 2, borderRadius: 6, yAxisID: 'y'
      },
      {
        type: 'line', label: 'Txn Count', data: trends.map(t => t.count),
        borderColor: '#10b981', backgroundColor: 'rgba(16,185,129,0.1)',
        borderWidth: 2, pointRadius: 3, pointBackgroundColor: '#10b981',
        fill: true, tension: 0.4, yAxisID: 'y1'
      }
    ]
  } : null

  const trendOptions = {
    responsive: true, maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { display: true, labels: { color: '#94a3b8', font: { size: 10 } } } },
    scales: {
      y: { type: 'linear', position: 'left', grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8', font: { size: 9 } } },
      y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, ticks: { color: '#10b981', font: { size: 9 } } },
      x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 9 }, maxRotation: 45 } }
    }
  }

  return (
    <div className="glass-card mt-24">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h3 style={{ fontSize: 16 }}>🔬 Forensic Intelligence Dashboard</h3>
        <div className="badge badge-low" style={{ fontSize: 10 }}>AI POWERED</div>
      </div>

      {/* KPI Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 20 }}>
        <div className="result-card">
          <div className="result-value" style={{ color: giniColor }}>{gini.toFixed(2)}</div>
          <div className="result-label">Vendor Gini <span style={{ fontSize: 9, opacity: 0.6 }}>({giniLabel})</span></div>
        </div>
        <div className="result-card">
          <div className="result-value" style={{ color: '#f59e0b' }}>{concentrationPct}%</div>
          <div className="result-label">Top 5% Value Share</div>
        </div>
        <div className="result-card">
          <div className="result-value" style={{ color: '#ef4444' }}>{rd.high || 0}</div>
          <div className="result-label">High Risk Txns</div>
        </div>
        <div className="result-card">
          <div className="result-value" style={{ color: '#10b981' }}>{rd.low || 0}</div>
          <div className="result-label">Low Risk Txns</div>
        </div>
      </div>

      {/* Forensic Flags */}
      <div style={{ marginBottom: 20 }}>
        <h4 style={{ fontSize: 13, marginBottom: 10, color: 'var(--text-secondary)' }}>Forensic Risk Flags</h4>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {flagEntries.length > 0 ? flagEntries.map(([name, count]) => {
            const color = name.includes('Split') || name.includes('Round') ? '#ef4444' : name.includes('High') || name.includes('Above') ? '#f59e0b' : '#6366f1'
            return (
              <span key={name} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, padding: '4px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600, background: `${color}18`, color, border: `1px solid ${color}30` }}>
                {name} <span style={{ opacity: 0.7 }}>({count})</span>
              </span>
            )
          }) : <span className="text-muted" style={{ fontSize: 12 }}>No anomalies detected</span>}
        </div>
      </div>

      {/* Two Column: Vendors + Trend */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.5fr', gap: 16 }}>
        <div style={{ padding: 14, background: 'rgba(255,255,255,0.02)', borderRadius: 12, border: '1px solid var(--glass-border)' }}>
          <h4 style={{ fontSize: 13, marginBottom: 10 }}>Top Vendors by Value</h4>
          {topVendors.length > 0 ? topVendors.map((v, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '6px 0', borderBottom: i < topVendors.length - 1 ? '1px solid rgba(255,255,255,0.06)' : 'none' }}>
              <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{v.name}</span>
              <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--accent-primary)' }}>₹{Number(v.value).toLocaleString()}</span>
            </div>
          )) : <span className="text-muted" style={{ fontSize: 12 }}>No vendor data</span>}
        </div>
        <div style={{ padding: 14, background: 'rgba(255,255,255,0.02)', borderRadius: 12, border: '1px solid var(--glass-border)' }}>
          <h4 style={{ fontSize: 13, marginBottom: 10 }}>Monthly Transaction Trends</h4>
          <div style={{ height: 160, position: 'relative' }}>
            {trendChartData && <Bar key={trendChartData.labels.join(',')} data={trendChartData} options={trendOptions} />}
          </div>
          {spikeMonths.length > 0 && (
            <div style={{ marginTop: 8, padding: '8px 12px', borderRadius: 8, background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)', fontSize: 11, color: '#ef4444' }}>
              ⚠️ Anomalous spikes detected in: {spikeMonths.map(s => <strong key={s.month}>{s.month} (z={s.z_score})</strong>).reduce((a, b) => [a, ', ', b])}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
