import { useState } from 'react'
import { useSession } from '../context/SessionContext'
import { useAudit } from '../context/AuditContext'
import { Calculator } from 'lucide-react'

const BENCHMARK_CONFIGS = {
  TURNOVER: {
    label: 'Total Turnover (₹)',
    placeholder: 'e.g. 500',
    rommRanges: {
      low: [1.5, 2.0],
      medium: [1.0, 1.2],
      high: [0.5, 0.8]
    }
  },
  NPBT: {
    label: 'Net Profit Before Tax (₹)',
    placeholder: 'e.g. 50',
    rommRanges: {
      low: [8, 9, 10],
      medium: [5, 6, 7],
      high: [2, 3, 4]
    }
  },
  NPAT: {
    label: 'Net Profit After Tax (₹)',
    placeholder: 'e.g. 40',
    rommRanges: {
      low: [8, 9, 10],
      medium: [5, 6, 7],
      high: [2, 3, 4]
    }
  }
}

export default function MaterialityPage({ navigateTo }) {
  const { secureFetch, sessionId } = useSession()
  const { setMateriality, unlockStage, selectedExactPct, setSelectedExactPct } = useAudit()

  const [benchmark, setBenchmark] = useState('TURNOVER')
  const [turnover, setTurnover] = useState('')
  const [romm, setRomm] = useState('low')
  const [perfPct, setPerfPct] = useState(75)
  const [trivialPct, setTrivialPct] = useState(3)
  const [exactPctOptions, setExactPctOptions] = useState(BENCHMARK_CONFIGS.TURNOVER.rommRanges.low)
  const [showResults, setShowResults] = useState(false)
  const [results, setResults] = useState({ overall: 0, performance: 0, trivial: 0 })

  const selectBenchmark = (bId) => {
    setBenchmark(bId)
    const configs = BENCHMARK_CONFIGS[bId]
    const opts = configs.rommRanges[romm]
    setExactPctOptions(opts)
    setSelectedExactPct(opts[0] / 100)
  }

  const selectRisk = (risk) => {
    setRomm(risk)
    const configs = BENCHMARK_CONFIGS[benchmark]
    const opts = configs.rommRanges[risk]
    setExactPctOptions(opts)
    setSelectedExactPct(opts[0] / 100)
  }

  const handleCalculate = async () => {
    const turnoverVal = parseFloat(turnover)
    if (isNaN(turnoverVal) || !selectedExactPct) {
      alert('Please enter a benchmark value and select an exact ROMM basis.')
      return
    }

    const overall = turnoverVal * selectedExactPct
    const performance = overall * (perfPct / 100)
    const trivial = overall * (trivialPct / 100)

    const r = { overall, performance, trivial }
    setResults(r)
    setMateriality(r)
    setShowResults(true)

    // Sync with backend
    const fd = new FormData()
    fd.append('session_id', sessionId)
    fd.append('value', turnoverVal)
    fd.append('benchmark', benchmark)
    fd.append('romm', romm)
    fd.append('perf_pct', perfPct)
    fd.append('trivial_pct', trivialPct)
    fd.append('overall_pct', selectedExactPct * 100)
    try {
      await secureFetch('/api/materiality', { method: 'POST', body: fd })
    } catch (e) { console.error('Materiality Sync Failed', e) }

    unlockStage(2)
  }

  return (
    <section className="content-section">
      <div className="section-header mb-16">
        <h1 style={{ fontSize: 22 }}>Materiality Planning</h1>
        <p className="text-secondary">Set benchmarks and assess risk to determine audit thresholds.</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        {/* Input Card */}
        <div className="glass-card">
          <h3 style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 8, fontSize: 15 }}>
            <Calculator size={18} style={{ color: 'var(--accent-primary)' }} /> Benchmarking
          </h3>

          <div className="form-group">
            <label className="form-label">Materiality Benchmark</label>
            <div className="toggle-group">
              {[
                { id: 'TURNOVER', label: 'Turnover' },
                { id: 'NPBT', label: 'NPBT (Profit Before Tax)' },
                { id: 'NPAT', label: 'NPAT (Profit After Tax)' }
              ].map(b => (
                <button
                  key={b.id}
                  type="button"
                  className={`toggle-option ${benchmark === b.id ? 'active' : ''}`}
                  onClick={() => selectBenchmark(b.id)}
                >
                  {b.label}
                </button>
              ))}
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">{BENCHMARK_CONFIGS[benchmark].label}</label>
            <input
              type="number"
              className="glass-input"
              placeholder={BENCHMARK_CONFIGS[benchmark].placeholder}
              value={turnover}
              onChange={(e) => setTurnover(e.target.value)}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Audit Risk Level (ROMM)</label>
            <div className="toggle-group">
              {['low', 'medium', 'high'].map(r => (
                <button
                  key={r}
                  type="button"
                  className={`toggle-option ${romm === r ? 'active' : ''}`}
                  onClick={() => selectRisk(r)}
                >
                  {r.charAt(0).toUpperCase() + r.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Exact % Picker */}
          <div style={{ marginTop: -4, marginBottom: 10, padding: 10, background: 'rgba(99,102,241,0.05)', borderRadius: 10, border: '1px dashed var(--accent-primary)' }}>
            <label style={{ display: 'block', fontSize: 10, color: 'var(--accent-primary)', fontWeight: 700, textTransform: 'uppercase', marginBottom: 8 }}>
              Select Exact Basis (%)
            </label>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              {exactPctOptions.map(p => (
                <button
                  key={p}
                  type="button"
                  className={`toggle-option ${selectedExactPct === p / 100 ? 'active' : ''}`}
                  onClick={() => setSelectedExactPct(p / 100)}
                >
                  {p}%
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <div className="form-group">
              <label className="form-label">Perf. Mat (%)</label>
              <input type="number" className="glass-input" value={perfPct} onChange={(e) => setPerfPct(parseFloat(e.target.value) || 0)} />
            </div>
            <div className="form-group">
              <label className="form-label">Trivial (%)</label>
              <input type="number" className="glass-input" value={trivialPct} onChange={(e) => setTrivialPct(parseFloat(e.target.value) || 0)} />
            </div>
          </div>

          <button className="btn-primary w-full mt-8" style={{ padding: 12 }} onClick={handleCalculate}>
            Calculate Thresholds
          </button>
        </div>

        {/* Results Card */}
        <div className="glass-card">
          <h3 style={{ marginBottom: 14, fontSize: 15 }}>Audit Thresholds</h3>
          {showResults ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ padding: 14, background: 'rgba(99,102,241,0.05)', borderRadius: 12, border: '1px solid var(--glass-border)' }}>
                <span className="text-muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1 }}>Overall Materiality</span>
                <h2 style={{ fontSize: 28, color: 'var(--accent-primary)', marginTop: 4 }}>₹ {results.overall.toFixed(2)}</h2>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 10, border: '1px solid var(--glass-border)' }}>
                  <span className="text-muted" style={{ fontSize: 11 }}>Performance</span>
                  <h4 style={{ fontSize: 18, marginTop: 2 }}>₹ {results.performance.toFixed(2)}</h4>
                </div>
                <div style={{ padding: 12, background: 'rgba(255,255,255,0.02)', borderRadius: 10, border: '1px solid var(--glass-border)' }}>
                  <span className="text-muted" style={{ fontSize: 11 }}>Trivial</span>
                  <h4 style={{ fontSize: 18, color: 'var(--danger)', marginTop: 2 }}>₹ {results.trivial.toFixed(2)}</h4>
                </div>
              </div>
              <button className="btn-secondary w-full mt-8" onClick={() => navigateTo('/risk')}>
                Confirm & Proceed to Classification →
              </button>
            </div>
          ) : (
            <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
              <p className="text-muted">Enter turnover to see AI-calculated thresholds</p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
