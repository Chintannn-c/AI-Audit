import { useState } from 'react'
import { useSession } from '../context/SessionContext'
import { useAudit } from '../context/AuditContext'
import { BarChart3, ShieldCheck, Users, AlertCircle } from 'lucide-react'

const CHECKS = [
  { id: 'turnover_250', icon: BarChart3, category: 'Turnover', title: 'a) Above ₹250 Crore?', desc: 'Statutory threshold for audit' },
  { id: 'ifc', icon: ShieldCheck, category: 'Compliance', title: 'b) IFC Applicable?', desc: 'Internal Financial Controls' },
  { id: 'governance', icon: Users, category: 'Governance', title: 'c) Weak Structures?', desc: 'Control environment risk' },
  { id: 'misstatements', icon: AlertCircle, category: 'History', title: 'd) Prior Misstatements?', desc: 'Known historical audit errors' }
]

export default function RiskPage({ navigateTo }) {
  const { secureFetch, sessionId } = useSession()
  const { setRiskClassification, unlockStage } = useAudit()
  const [checks, setChecks] = useState({ turnover_250: false, ifc: false, governance: false, misstatements: false })
  const [showResults, setShowResults] = useState(false)

  const toggleCheck = (id) => {
    setChecks(prev => ({ ...prev, [id]: !prev[id] }))
  }

  const isLarge = Object.values(checks).some(v => v)

  const handleAssess = async () => {
    const auditType = isLarge ? 'LARGE AUDIT' : 'SMALL AUDIT'
    const color = isLarge ? '#2563EB' : '#10b981'
    const approach = isLarge
      ? 'Combined approach (TOD + TOC) required for this engagement.'
      : 'Substantive approach (TOD only) sufficient for this engagement.'

    setRiskClassification({ auditType, isLargeAudit: isLarge, approach, auditTypeColor: color })
    setShowResults(true)

    // Sync with backend
    const fd = new FormData()
    fd.append('session_id', sessionId)
    fd.append('turnover_250', checks.turnover_250)
    fd.append('ifc', checks.ifc)
    fd.append('governance', checks.governance)
    fd.append('misstatements', checks.misstatements)
    try {
      await secureFetch('/api/risk-assessment', { method: 'POST', body: fd })
    } catch (e) { console.error('Risk Sync Failed', e) }

    unlockStage(3)
  }

  return (
    <section className="content-section">
      <div className="section-header mb-24">
        <h2>Audit Classification</h2>
        <p>AI will determine the audit type based on statutory and risk thresholds.</p>
      </div>

      <div className="glass-card" style={{ maxWidth: 680, margin: '0 auto' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {CHECKS.map(item => (
            <label key={item.id} className={`option-card ${checks[item.id] ? 'active' : ''}`}>
              <input type="checkbox" checked={checks[item.id]} onChange={() => toggleCheck(item.id)} style={{ display: 'none' }} />
              <div className="custom-checkbox" />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--accent-primary)', marginBottom: 4 }}>
                  <item.icon size={16} />
                  <span style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: 1 }}>{item.category}</span>
                </div>
                <h4 style={{ fontSize: 14 }}>{item.title}</h4>
                <p style={{ fontSize: 11 }}>{item.desc}</p>
              </div>
            </label>
          ))}
        </div>

        <button className="btn-primary w-full mt-16" onClick={handleAssess}>Classify Audit</button>

        {showResults && (
          <div className="mt-16" style={{ padding: 16, borderRadius: 12, border: '1px solid var(--glass-border)' }}>
            <div style={{ textAlign: 'center' }}>
              <h2 style={{ fontSize: 28, marginBottom: 8, color: isLarge ? '#2563EB' : '#10b981' }}>
                {isLarge ? 'LARGE AUDIT' : 'SMALL AUDIT'}
              </h2>
              <p className="text-secondary" style={{ fontSize: 14 }}>
                {isLarge
                  ? 'Combined approach (TOD + TOC) required for this engagement.'
                  : 'Substantive approach (TOD only) sufficient for this engagement.'}
              </p>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginTop: 16 }}>
              <div className="glass-card" style={{ padding: 12, textAlign: 'center' }}>
                <h4 style={{ color: 'var(--accent-primary)' }}>Test of Details</h4>
                <p className="text-muted" style={{ fontSize: 12 }}>Substantive testing</p>
                <div className="badge badge-low mt-8">APPLICABLE</div>
              </div>
              <div className="glass-card" style={{ padding: 12, textAlign: 'center' }}>
                <h4 style={{ fontSize: 15 }}>Test of Controls (TOC)</h4>
                <p className="text-muted" style={{ fontSize: 11, margin: '6px 0' }}>Selection: <strong>Random Basis</strong></p>
                <div className={`badge ${isLarge ? 'badge-low' : 'badge-medium'} mt-8`}>
                  {isLarge ? 'APPLICABLE' : 'NOT APPLICABLE'}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
