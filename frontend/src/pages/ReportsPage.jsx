import { useAudit } from '../context/AuditContext'
import { useSession } from '../context/SessionContext'
import { Download, FileText } from 'lucide-react'

export default function ReportsPage() {
  const { materiality, riskClassification, samplingResults, aiInsights, uploadedFile, selectedCategory } = useAudit()
  const { secureFetch, sessionId } = useSession()

  const runDownload = async () => {
    if (!uploadedFile) return alert('Please upload a ledger file first.')
    const targetCount = samplingResults?.total_selected || 100
    const fd = new FormData()
    fd.append('session_id', sessionId)
    fd.append('file', uploadedFile)
    fd.append('category', selectedCategory)
    fd.append('target_count', targetCount)
    fd.append('sampling_basis', samplingResults?.coverageBasis || 'count')
    fd.append('tod_pct', riskClassification.isLargeAudit ? 70 : 100)
    fd.append('audit_type', riskClassification.isLargeAudit ? 'large' : 'small')

    try {
      const res = await secureFetch('/api/download', { method: 'POST', body: fd })
      if (!res.ok) {
        const errorData = await res.json()
        throw new Error(errorData.error || `Server responded with ${res.status}`)
      }
      const blob = await res.blob()
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

  return (
    <section className="content-section">
      <div className="section-header mb-16">
        <h2>Audit Working Papers</h2>
      </div>

      {/* AI Executive Summary */}
      <div className="glass-card mb-16">
        <h3 style={{ fontSize: 15 }}>🤖 AI Executive Summary</h3>
        <div className="text-secondary mt-8" style={{ fontSize: 13 }}>
          {aiInsights.focus ? (
            <>
              <div style={{ marginBottom: 8 }}><strong>{aiInsights.focus}</strong></div>
              <div>{aiInsights.summary}</div>
            </>
          ) : 'Complete an audit sampling session to see results here.'}
        </div>
      </div>

      {/* Materiality Summary */}
      <div className="glass-card mb-16">
        <h3 style={{ fontSize: 15 }}>📐 Materiality Thresholds</h3>
        <div className="mt-8" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
          <div className="result-card">
            <div className="result-value">{materiality.overall ? `₹ ${materiality.overall.toFixed(2)}` : '—'}</div>
            <div className="result-label">Overall Materiality</div>
          </div>
          <div className="result-card">
            <div className="result-value">{materiality.performance ? `₹ ${materiality.performance.toFixed(2)}` : '—'}</div>
            <div className="result-label">Performance Materiality</div>
          </div>
          <div className="result-card">
            <div className="result-value">{materiality.trivial ? `₹ ${materiality.trivial.toFixed(2)}` : '—'}</div>
            <div className="result-label">Trivial Threshold</div>
          </div>
        </div>
      </div>

      {/* Classification Summary */}
      <div className="glass-card mb-16">
        <h3 style={{ fontSize: 15 }}>🏛️ Audit Classification</h3>
        <div className="mt-8" style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
          <div><span className="text-secondary" style={{ fontSize: 12 }}>Audit Type:</span> <strong style={{ fontSize: 14, color: riskClassification.auditTypeColor }}>{riskClassification.auditType}</strong></div>
          <div><span className="text-secondary" style={{ fontSize: 12 }}>Approach:</span> <span className="text-secondary" style={{ fontSize: 13 }}>{riskClassification.approach}</span></div>
        </div>
      </div>

      {/* Sampling Summary */}
      <div className="glass-card mb-16">
        <h3 style={{ fontSize: 15 }}>📊 Sampling Results</h3>
        <div className="mt-8" style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 10 }}>
          <div className="result-card">
            <div className="result-value">{samplingResults?.stats?.count?.toLocaleString() || '—'}</div>
            <div className="result-label">Total Txns</div>
          </div>
          <div className="result-card">
            <div className="result-value">{samplingResults?.tod_count?.toLocaleString() || '—'}</div>
            <div className="result-label">TOD</div>
          </div>
          <div className="result-card">
            <div className="result-value">{samplingResults?.toc_count?.toLocaleString() || '—'}</div>
            <div className="result-label">TOC</div>
          </div>
          <div className="result-card">
            <div className="result-value">{samplingResults?.total_selected?.toLocaleString() || '—'}</div>
            <div className="result-label">Total Selected</div>
          </div>
          <div className="result-card">
            <div className="result-value">{samplingResults?.coverage || '—'}</div>
            <div className="result-label">Coverage</div>
          </div>
        </div>
      </div>

      {/* Download Actions */}
      <div className="glass-card">
        <h3 style={{ fontSize: 15 }}>📥 Export Working Papers</h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 12 }}>
          <div className="glass-card" style={{ background: 'rgba(255,255,255,0.02)' }}>
            <h4>📥 Sampling Report</h4>
            <p className="text-secondary text-small mt-8">4-sheet workbook: Original Ledger, TOD, TOC, Summary</p>
            <button className="btn-primary mt-16" disabled={!samplingResults} onClick={runDownload}>
              <Download size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} /> Download Excel
            </button>
          </div>
          <div className="glass-card" style={{ background: 'rgba(255,255,255,0.02)' }}>
            <h4>📋 Materiality Working Paper</h4>
            <p className="text-secondary text-small mt-8">Formal documentation of materiality benchmarks.</p>
            <button className="btn-secondary mt-16" onClick={() => setTimeout(() => window.print(), 300)}>
              <FileText size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} /> Export PDF
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}
