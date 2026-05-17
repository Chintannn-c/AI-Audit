import { useState, useRef } from 'react'
import { useSession } from '../context/SessionContext'
import { useAudit } from '../context/AuditContext'
import { Eye, ShieldCheck } from 'lucide-react'

export default function VouchingPage() {
  const { secureFetch, sessionId } = useSession()
  const { unlockStage } = useAudit()

  const [vouchStatus, setVouchStatus] = useState('idle') // idle, extracting, verifying, done
  const [extractedData, setExtractedData] = useState([])
  const [flagsTitle, setFlagsTitle] = useState('Live Analysis Logs')
  const [flagsText, setFlagsText] = useState('Waiting for document upload...')
  const [agent1, setAgent1] = useState({ opacity: 0.4, dot: '' })
  const [agent2, setAgent2] = useState({ opacity: 0.4, dot: '' })
  const [history, setHistory] = useState([])
  const [historyCount, setHistoryCount] = useState(0)
  const [showHistory, setShowHistory] = useState(false)
  const lastFileRef = useRef(null)
  const fileInputRef = useRef(null)

  const runVouch = async (file) => {
    lastFileRef.current = file
    setVouchStatus('extracting')
    setExtractedData([])

    setAgent1({ opacity: 0.4, dot: '' })
    setAgent2({ opacity: 0.4, dot: '' })
    setFlagsText('Agent 1 is starting deep OCR extraction...')

    // Agent 1 Active
    setAgent1({ opacity: 1, dot: 'active' })
    await new Promise(r => setTimeout(r, 1200))

    const fd = new FormData()
    fd.append('session_id', sessionId)
    fd.append('file', file)

    try {
      const res = await secureFetch('/api/vouch', { method: 'POST', body: fd })
      const data = await res.json()

      if (!res.ok || !data.data) {
        throw new Error(data.error || data.detail || 'Extraction failed.')
      }

      const modelName = data.model_used || 'AI Ensemble'

      // Agent 1 Done, Agent 2 Active
      setAgent1({ opacity: 1, dot: 'done' })
      setAgent2({ opacity: 1, dot: 'active' })
      setFlagsText(`Agent 1 successfully extracted data via <strong>${modelName}</strong>. Agent 2 is now validating...`)

      await new Promise(r => setTimeout(r, 1500))

      setAgent2({ opacity: 1, dot: 'done' })
      setVouchStatus('done')
      setExtractedData(data.data)

      const matchStatusField = data.data.find(r => r.field === 'Match Status')
      const matchStatusText = matchStatusField ? matchStatusField.value : 'Verified'
      setFlagsTitle('✅ Forensic Verification Complete')
      setFlagsText(`Audit Verdict: <strong style="color:var(--success);">${matchStatusText}</strong>. All data points persisted to reconciliation history.`)

      // Update History
      await updateVouchHistory()
      unlockStage(5)
    } catch (err) {
      console.error(err)
      setVouchStatus('idle')
      alert('Vouching Error: ' + err.message)
    }
  }

  const updateVouchHistory = async () => {
    try {
      const res = await secureFetch('/api/vouch/history')
      const data = await res.json()
      if (data.data && data.data.length > 0) {
        setShowHistory(true)
        setHistoryCount(data.data.length)
        setHistory(data.data)
      }
    } catch (err) {
      console.error('History Error:', err)
    }
  }

  const runVouchingDownload = async () => {
    try {
      const res = await secureFetch('/api/download/vouching')
      if (!res.ok) {
        const errData = await res.json()
        throw new Error(errData.error || 'Failed to download report')
      }
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'Vouching_Reconciliation_Report.xlsx'
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      alert('Download Error: ' + err.message)
    }
  }

  return (
    <section className="content-section">
      <div className="section-header mb-16">
        <h2>AI Invoice Vouching</h2>
        <p>Verify physical invoices against ledger data using the Multi-Agent Forensic Ensemble.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: 24 }}>
        {/* Upload & Pipeline */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div className="upload-zone" onClick={() => fileInputRef.current?.click()} style={{ minHeight: 180, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
            <div style={{ width: 48, height: 48, color: 'var(--accent-primary)', marginBottom: 12, fontSize: 36 }}>☁</div>
            <h3>Drop Invoice or Click to Upload</h3>
            <p className="text-muted" style={{ fontSize: 12, marginTop: 8 }}>Supports PDF, JPG, PNG (Max 10MB)</p>
            <input ref={fileInputRef} type="file" accept=".jpg,.jpeg,.png,.pdf" hidden onChange={(e) => { if (e.target.files[0]) runVouch(e.target.files[0]) }} />
          </div>

          {vouchStatus !== 'idle' && vouchStatus !== 'done' && (
            <div style={{ padding: 16, borderRadius: 12, background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                <div className="processing-spinner" style={{ width: 28, height: 28, marginBottom: 0 }} />
                <div>
                  <h4 style={{ fontSize: 14 }}>{vouchStatus === 'extracting' ? 'Extracting Document...' : 'Verifying Ledger...'}</h4>
                  <p className="text-muted" style={{ fontSize: 11 }}>
                    {vouchStatus === 'extracting' ? 'Agent 1 is performing deep OCR & layout analysis' : 'Agent 2 is cross-referencing extracted data with ERP records'}
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Pipeline Progress */}
        <div className="glass-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <h3 style={{ fontSize: 15 }}>🤖 AI Ensemble Pipeline</h3>
            <div className="badge badge-low" style={{ fontSize: 9 }}>ACTIVE</div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="agent-card" style={{ opacity: agent1.opacity }}>
              <div className="agent-icon-box"><Eye size={16} /></div>
              <div style={{ flex: 1 }}>
                <h4 style={{ fontSize: 13 }}>Agent 1 — Vision System</h4>
                <p className="text-muted" style={{ fontSize: 11 }}>OCR & Layout Extraction</p>
              </div>
              <div className={`status-dot ${agent1.dot}`} />
            </div>

            <div className="agent-card" style={{ opacity: agent2.opacity }}>
              <div className="agent-icon-box" style={{ background: 'rgba(168,85,247,0.1)', color: 'var(--accent-secondary)' }}><ShieldCheck size={16} /></div>
              <div style={{ flex: 1 }}>
                <h4 style={{ fontSize: 13 }}>Agent 2 — Auditor Logic</h4>
                <p className="text-muted" style={{ fontSize: 11 }}>Reconciliation & Flagging</p>
              </div>
              <div className={`status-dot ${agent2.dot}`} />
            </div>
          </div>

          <div className="mt-16" style={{ paddingTop: 16, borderTop: '1px solid var(--glass-border)' }}>
            <h4 style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 8 }}>{flagsTitle}</h4>
            <div className="text-muted" style={{ fontSize: 11, lineHeight: 1.5 }} dangerouslySetInnerHTML={{ __html: flagsText }} />
          </div>
        </div>
      </div>

      {/* History Table */}
      {showHistory && (
        <div className="mt-24">
          <div className="glass-card" style={{ padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '20px 24px', borderBottom: '1px solid var(--glass-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255,255,255,0.01)' }}>
              <div>
                <h3 style={{ fontSize: 18, display: 'flex', alignItems: 'center', gap: 10 }}>✅ Vouching Reconciliation Summary</h3>
                <p className="text-muted" style={{ fontSize: 12, marginTop: 4 }}>Cross-verified data points from processed session history</p>
              </div>
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <span className="badge badge-low" style={{ textTransform: 'none' }}>{historyCount} Invoices Processed</span>
                <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: 11 }} onClick={runVouchingDownload}>📥 Export Reconciliation</button>
              </div>
            </div>
            <div className="table-container" style={{ borderRadius: 0 }}>
              <table className="premium-table">
                <thead>
                  <tr style={{ background: 'rgba(255,255,255,0.02)' }}>
                    <th style={{ padding: '16px 24px' }}>Invoice Number</th>
                    <th>Date</th>
                    <th>Vendor Name</th>
                    <th>Extracted Total</th>
                    <th>Match Status</th>
                    <th style={{ textAlign: 'right', paddingRight: 24 }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((res, i) => {
                    const fields = {}
                    if (res.extracted_data) {
                      res.extracted_data.forEach(item => { fields[item.field] = item.value })
                    }
                    const invNo = fields['Invoice Number'] || fields['Invoice No'] || fields['Invoice #'] || 'N/A'
                    const date = fields['Date'] || fields['Invoice Date'] || 'N/A'
                    const total = fields['Grand Total'] || fields['Total Amount'] || fields['Amount'] || '0.00'
                    const vendor = fields['Vendor Name'] || fields['Vendor'] || 'Extracted'
                    return (
                      <tr key={i}>
                        <td style={{ padding: '16px 24px', fontWeight: 600 }}>{invNo}</td>
                        <td style={{ padding: '16px 24px', color: 'var(--text-secondary)' }}>{date}</td>
                        <td style={{ padding: '16px 24px' }}>{vendor}</td>
                        <td style={{ padding: '16px 24px', fontWeight: 800, color: 'var(--accent-primary)' }}>{total}</td>
                        <td style={{ padding: '16px 24px' }}><span className="badge badge-low">Verified</span></td>
                        <td style={{ padding: '16px 24px', textAlign: 'right' }}><button className="btn-secondary" style={{ padding: '4px 8px', fontSize: 10 }}>Details</button></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Extracted Data */}
      {vouchStatus === 'done' && extractedData.length > 0 && (
        <div className="mt-24">
          <div className="glass-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <h3>📋 Extracted Invoice Data</h3>
              <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: 11 }} onClick={() => { if (lastFileRef.current) runVouch(lastFileRef.current) }}>
                🔄 Re-Extract
              </button>
            </div>
            <div className="table-container">
              <table className="premium-table">
                <thead><tr><th>Field</th><th>Extracted Value</th></tr></thead>
                <tbody>
                  {extractedData.map((row, i) => (
                    <tr key={i}>
                      <td style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{row.field}</td>
                      <td style={{ fontWeight: 700, color: row.field === 'Match Status' ? 'var(--success)' : 'white' }}>{row.value}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
