import { useState, useEffect } from 'react'
import { useSession } from '../context/SessionContext'
import { Key, ShieldAlert, CheckCircle, RefreshCw, AlertTriangle, Clock, Server, Activity, ShieldCheck } from 'lucide-react'

export default function ApiStatusPage() {
  const { secureFetch } = useSession()
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const [resetSeconds, setResetSeconds] = useState(0)

  const fetchStatus = async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await secureFetch('/api/key-status')
      if (resp.ok) {
        const data = await resp.json()
        setStatus(data)
        if (data?.openrouter?.next_reset_seconds) {
          setResetSeconds(data.openrouter.next_reset_seconds)
        }
      } else {
        const text = await resp.text()
        setError(`Failed to retrieve status: ${text || resp.statusText}`)
      }
    } catch (e) {
      setError(`Network error: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
  }, [])

  // Reset Countdown Timer
  useEffect(() => {
    if (resetSeconds <= 0) return
    const timer = setInterval(() => {
      setResetSeconds(prev => (prev > 0 ? prev - 1 : 0))
    }, 1000)
    return () => clearInterval(timer)
  }, [resetSeconds])

  const formatCountdown = (totalSecs) => {
    if (totalSecs <= 0) return 'Resetting now...'
    const h = Math.floor(totalSecs / 3600)
    const m = Math.floor((totalSecs % 3600) / 60)
    const s = totalSecs % 60
    return `${h}h ${m}m ${s}s`
  }

  return (
    <section className="content-section">
      <div className="section-header mb-20" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Activity size={24} style={{ color: 'var(--accent-primary)', filter: 'drop-shadow(0 0 8px var(--accent-primary))' }} />
            AI Service Diagnostics
          </h1>
          <p className="text-secondary">Real-time upstream rate limits, remaining API credits, and key sanity status.</p>
        </div>
        <button
          className={`btn-secondary ${loading ? 'loading' : ''}`}
          onClick={fetchStatus}
          disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 18px', borderRadius: 10 }}
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Diagnosing...' : 'Refresh Status'}
        </button>
      </div>

      {error && (
        <div className="glass-card mb-20" style={{ borderLeft: '4px solid var(--danger)', background: 'rgba(239, 68, 68, 0.05)', padding: 18 }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <ShieldAlert size={20} style={{ color: 'var(--danger)' }} />
            <h4 style={{ color: 'var(--danger)', margin: 0 }}>System Diagnostic Failure</h4>
          </div>
          <p style={{ marginTop: 8, fontSize: 13, color: 'var(--text-secondary)' }}>{error}</p>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        {/* OpenRouter Diagnostic Panel */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--glass-border)', paddingBottom: 12 }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 16, fontWeight: 600 }}>
              <Server size={18} style={{ color: 'var(--accent-primary)' }} />
              OpenRouter Upstream (Global)
            </h3>
            {status?.openrouter?.configured ? (
              <span className="badge" style={{
                background: status.openrouter.status.includes('Healthy') ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                color: status.openrouter.status.includes('Healthy') ? '#10b981' : 'var(--danger)',
                border: status.openrouter.status.includes('Healthy') ? '1px solid rgba(16,185,129,0.2)' : '1px solid rgba(239,68,68,0.2)',
                fontSize: 11, padding: '4px 10px', borderRadius: 20, display: 'flex', alignItems: 'center', gap: 4
              }}>
                {status.openrouter.status.includes('Healthy') ? <CheckCircle size={10} /> : <AlertTriangle size={10} />}
                {status.openrouter.status}
              </span>
            ) : (
              <span className="badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)', fontSize: 11 }}>
                Not Configured
              </span>
            )}
          </div>

          {status?.openrouter?.configured ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Credit Status Box */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div style={{ padding: 14, background: 'rgba(99,102,241,0.05)', borderRadius: 12, border: '1px solid var(--glass-border)' }}>
                  <span className="text-muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1 }}>Remaining Key Credit</span>
                  <h2 style={{ fontSize: 24, color: 'var(--accent-primary)', marginTop: 4 }}>
                    {status.openrouter.limit_remaining !== null ? `$${parseFloat(status.openrouter.limit_remaining).toFixed(4)}` : 'Unlimited'}
                  </h2>
                </div>

                <div style={{ padding: 14, background: 'rgba(255,255,255,0.02)', borderRadius: 12, border: '1px solid var(--glass-border)' }}>
                  <span className="text-muted" style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1 }}>All-Time usage</span>
                  <h2 style={{ fontSize: 24, marginTop: 4 }}>
                    ${parseFloat(status.openrouter.usage).toFixed(4)}
                  </h2>
                </div>
              </div>

              {/* Reset Countdowns */}
              <div style={{ padding: 14, background: 'rgba(255, 255, 255, 0.02)', borderRadius: 12, border: '1px solid var(--glass-border)', display: 'flex', alignItems: 'center', gap: 12 }}>
                <Clock size={16} style={{ color: 'var(--accent-primary)' }} />
                <div>
                  <span className="text-muted" style={{ display: 'block', fontSize: 10, textTransform: 'uppercase', letterSpacing: 1 }}>Standard Daily Limit Reset</span>
                  <strong style={{ fontSize: 14, color: 'var(--text-primary)' }}>{formatCountdown(resetSeconds)}</strong>
                  <span style={{ fontSize: 10, color: 'var(--text-secondary)', marginLeft: 8 }}>(At {status.openrouter.next_reset_time})</span>
                </div>
              </div>

              {/* Usage Progress Bar */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 6 }}>
                  <span className="text-secondary">Daily Usage (Today UTC)</span>
                  <span style={{ fontWeight: 600 }}>${parseFloat(status.openrouter.usage_daily).toFixed(4)}</span>
                </div>
                <div style={{ height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: status.openrouter.is_free_tier ? `${Math.min((status.openrouter.usage_daily / 0.5) * 100, 100)}%` : '10%',
                    background: 'var(--accent-primary)',
                    borderRadius: 3,
                    boxShadow: '0 0 8px var(--accent-primary)'
                  }} />
                </div>
                <span className="text-muted" style={{ display: 'block', fontSize: 10, marginTop: 6 }}>
                  {status.openrouter.is_free_tier 
                    ? "Currently on Free Tier (Limits: 20 req/min, 50 req/day unless upgraded)"
                    : "Upgraded Premium Account (Standard model caps expanded)"
                  }
                </span>
              </div>
            </div>
          ) : (
            <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
              <p className="text-muted" style={{ fontSize: 13 }}>Configure `OPENROUTER_API_KEY` in your `.env` file to view credits & usage details.</p>
            </div>
          )}
        </div>

        {/* Gemini Multi-Key Diagnostic Panel */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--glass-border)', paddingBottom: 12 }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 16, fontWeight: 600 }}>
              <Key size={18} style={{ color: 'var(--accent-primary)' }} />
              Gemini AI Key Ring (Failovers)
            </h3>
            <span className="badge" style={{ background: 'rgba(99,102,241,0.1)', color: 'var(--accent-primary)', border: '1px solid rgba(99,102,241,0.2)', fontSize: 11, padding: '4px 10px', borderRadius: 20 }}>
              3 Keys Configured
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {status?.gemini_keys?.map((k, index) => {
              const isHealthy = k.status === 'Healthy & Active';
              const isRateLimited = k.status.includes('Rate Limited');
              const isInvalid = k.status.includes('Invalid');
              
              let statusBg = 'rgba(255,255,255,0.02)';
              let dotColor = 'var(--text-secondary)';
              if (isHealthy) { dotColor = '#10b981'; statusBg = 'rgba(16,185,129,0.03)'; }
              else if (isRateLimited) { dotColor = '#f59e0b'; statusBg = 'rgba(245,158,11,0.03)'; }
              else if (isInvalid) { dotColor = '#ef4444'; statusBg = 'rgba(239,68,68,0.03)'; }

              return (
                <div
                  key={index}
                  style={{
                    padding: '12px 16px',
                    background: statusBg,
                    border: '1px solid var(--glass-border)',
                    borderRadius: 10,
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    transition: 'all 0.3s ease'
                  }}
                >
                  <div>
                    <span style={{ display: 'block', fontSize: 12, fontWeight: 600 }}>Gemini Failover Key #{k.key_index}</span>
                    <code style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{k.masked_key}</code>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span
                      style={{
                        height: 8,
                        width: 8,
                        borderRadius: '50%',
                        background: dotColor,
                        boxShadow: `0 0 8px ${dotColor}`
                      }}
                    />
                    <span style={{ fontSize: 12, fontWeight: 600, color: dotColor }}>{k.status}</span>
                  </div>
                </div>
              );
            })}

            {!status?.gemini_keys?.length && (
              <div style={{ height: 180, display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center' }}>
                <p className="text-muted" style={{ fontSize: 13 }}>No Gemini keys active in backend. Please set `GEMINI_API_KEY` in environment config.</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Ensemble Model Bindings */}
      <div className="glass-card mt-24">
        <h3 style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 15, fontWeight: 600, borderBottom: '1px solid var(--glass-border)', paddingBottom: 10, marginBottom: 14 }}>
          <ShieldCheck size={16} style={{ color: 'var(--accent-primary)' }} />
          Ensemble Model Orchestration Bindings
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 16 }}>
          <div style={{ padding: 12, background: 'rgba(255,255,255,0.01)', border: '1px solid var(--glass-border)', borderRadius: 10 }}>
            <span style={{ display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--accent-primary)', marginBottom: 6 }}>Forensic Sampling</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 12 }}>• Meta Llama 3.3 70B</span>
              <span style={{ fontSize: 12 }}>• OpenAI GPT-120B Free</span>
              <span style={{ fontSize: 12 }}>• Google Gemini 2.0 Flash</span>
            </div>
          </div>

          <div style={{ padding: 12, background: 'rgba(255,255,255,0.01)', border: '1px solid var(--glass-border)', borderRadius: 10 }}>
            <span style={{ display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--accent-primary)', marginBottom: 6 }}>Forensic Vouching (OCR)</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 12 }}>• OpenAI GPT-120B Free</span>
              <span style={{ fontSize: 12 }}>• Qwen 3 Coder Free</span>
              <span style={{ fontSize: 12 }}>• Gemini 2.0 Flash</span>
            </div>
          </div>

          <div style={{ padding: 12, background: 'rgba(255,255,255,0.01)', border: '1px solid var(--glass-border)', borderRadius: 10 }}>
            <span style={{ display: 'block', fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, color: 'var(--accent-primary)', marginBottom: 6 }}>Fast Ledger Scanning</span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 12 }}>• Meta Llama 3.3 70B</span>
              <span style={{ fontSize: 12 }}>• Qwen 3 Coder Free</span>
              <span style={{ fontSize: 12 }}>• Google Gemma 2 9B</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
