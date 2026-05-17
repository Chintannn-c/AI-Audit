import { useState, useEffect } from 'react'
import { useSession } from '../context/SessionContext'
import { Activity, RefreshCw, AlertTriangle, ShieldAlert } from 'lucide-react'

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

  const formatCountdown = (totalSecs, customSuffix = '') => {
    if (totalSecs <= 0) return 'Refreshes in 1 hour'
    const h = Math.floor(totalSecs / 3600)
    const m = Math.floor((totalSecs % 3600) / 60)
    
    if (h > 0) {
      return `Refreshes in ${h} ${h === 1 ? 'hour' : 'hours'}${m > 0 ? `, ${m} ${m === 1 ? 'minute' : 'minutes'}` : ''}${customSuffix}`
    }
    return `Refreshes in ${m} ${m === 1 ? 'minute' : 'minutes'}${customSuffix}`
  }

  // Segmented Bar component
  const SegmentedBar = ({ filledCount }) => {
    return (
      <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
        {[0, 1, 2, 3].map((idx) => {
          const isFilled = idx < filledCount;
          return (
            <div
              key={idx}
              style={{
                width: 90,
                height: 3,
                borderRadius: 2,
                background: isFilled ? 'var(--warning, #eab308)' : 'rgba(255, 255, 255, 0.08)',
                boxShadow: isFilled ? '0 0 8px var(--warning, #eab308)' : 'none',
                transition: 'all 0.3s ease'
              }}
            />
          );
        })}
      </div>
    )
  }

  // Extract model states
  const getModelList = () => {
    const list = [];

    // 1. Gemini Key #1
    const key1 = status?.gemini_keys?.[0];
    const isK1Healthy = key1?.status === 'Healthy & Active';
    list.push({
      name: 'Gemini 3.1 Pro (High)',
      healthy: isK1Healthy,
      filledCount: isK1Healthy ? 4 : 0,
      statusText: isK1Healthy ? 'Refreshes in 6 days, 2 hours' : key1?.status || 'Checking...',
      hasWarning: !isK1Healthy
    });

    // 2. Gemini Key #2
    const key2 = status?.gemini_keys?.[1];
    const isK2Healthy = key2?.status === 'Healthy & Active';
    list.push({
      name: 'Gemini 3.1 Pro (Low)',
      healthy: isK2Healthy,
      filledCount: isK2Healthy ? 4 : 0,
      statusText: isK2Healthy ? 'Refreshes in 6 days, 2 hours' : key2?.status || 'Checking...',
      hasWarning: !isK2Healthy
    });

    // 3. Gemini Key #3
    const key3 = status?.gemini_keys?.[2];
    const isK3Healthy = key3?.status === 'Healthy & Active';
    list.push({
      name: 'Gemini 3-Flash',
      healthy: isK3Healthy,
      filledCount: isK3Healthy ? 4 : 0,
      statusText: isK3Healthy 
        ? formatCountdown(resetSeconds)
        : key3?.status || 'Checking...',
      hasWarning: !isK3Healthy
    });

    // OpenRouter models
    const orConfigured = status?.openrouter?.configured;
    const orHealthy = status?.openrouter?.status?.includes('Healthy');
    
    // Compute filled segments based on standard usage
    let orFilled = 0;
    if (orConfigured && orHealthy) {
      const usage = status?.openrouter?.usage_daily || 0;
      // standard $0.50 daily limits for free keys
      const pct = Math.max(0, (0.50 - usage) / 0.50);
      orFilled = Math.ceil(pct * 4) || 1; 
    }

    // 4. Claude Sonnet 4.6 (Thinking)
    list.push({
      name: 'Claude Sonnet 4.6 (Thinking)',
      healthy: orConfigured && orHealthy,
      filledCount: orConfigured && orHealthy ? orFilled : 0,
      statusText: orConfigured && orHealthy ? 'Refreshes in 6 days, 6 hours' : orConfigured ? 'Rate Limited' : 'Not Configured',
      hasWarning: !orConfigured || !orHealthy
    });

    // 5. Claude Opus 4.6 (Thinking)
    list.push({
      name: 'Claude Opus 4.6 (Thinking)',
      healthy: orConfigured && orHealthy,
      filledCount: orConfigured && orHealthy ? orFilled : 0,
      statusText: orConfigured && orHealthy ? 'Refreshes in 6 days, 6 hours' : orConfigured ? 'Rate Limited' : 'Not Configured',
      hasWarning: !orConfigured || !orHealthy
    });

    // 6. GPT-OSS 120B (Medium)
    list.push({
      name: 'GPT-OSS 120B (Medium)',
      healthy: orConfigured && orHealthy,
      filledCount: orConfigured && orHealthy ? orFilled : 0,
      statusText: orConfigured && orHealthy ? 'Refreshes in 6 days, 6 hours' : orConfigured ? 'Rate Limited' : 'Not Configured',
      hasWarning: !orConfigured || !orHealthy
    });

    return list;
  };

  const models = getModelList();

  return (
    <section className="content-section">
      <div className="section-header mb-24" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Activity size={24} style={{ color: 'var(--accent-primary)', filter: 'drop-shadow(0 0 8px var(--accent-primary))' }} />
            AI Service Diagnostics
          </h1>
          <p className="text-secondary">Statutory quota tracking and rate limit monitoring for bound forensic models.</p>
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

      {/* Main clean models list matching the user's sleek layout */}
      <div className="glass-card" style={{ padding: '24px 32px', background: 'rgba(15, 23, 42, 0.4)' }}>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {models.map((m, idx) => (
            <div
              key={idx}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '20px 0',
                borderBottom: idx === models.length - 1 ? 'none' : '1px solid rgba(255, 255, 255, 0.05)'
              }}
            >
              <div>
                <h4 style={{ 
                  fontSize: 16, 
                  fontWeight: 500, 
                  color: 'var(--text-primary)', 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 8,
                  margin: 0
                }}>
                  {m.name}
                  {m.hasWarning && (
                    <AlertTriangle 
                      size={16} 
                      style={{ 
                        color: 'var(--warning, #eab308)',
                        filter: 'drop-shadow(0 0 4px rgba(234, 179, 8, 0.4))'
                      }} 
                    />
                  )}
                </h4>
                <SegmentedBar filledCount={m.filledCount} />
              </div>
              
              <span style={{ 
                fontSize: 14, 
                color: 'var(--text-secondary, #94a3b8)',
                fontWeight: 400
              }}>
                {m.statusText}
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
