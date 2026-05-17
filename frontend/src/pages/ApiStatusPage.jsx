import { useState, useEffect, useCallback, memo } from 'react'
import { useSession } from '../context/SessionContext'
import { Copy, Check, ChevronDown, ChevronUp, AlertCircle, RefreshCw } from 'lucide-react'

// Dynamic format helper for reset countdowns
const formatCountdown = (totalSecs) => {
  if (totalSecs === undefined || totalSecs === null || totalSecs <= 0) {
    return 'resets soon'
  }
  const d = Math.floor(totalSecs / 86400)
  const h = Math.floor((totalSecs % 86400) / 3600)
  const m = Math.floor((totalSecs % 3600) / 60)
  const s = totalSecs % 60

  if (d > 0) return `Resets in ${d}d ${h}h`
  if (h > 0) return `Resets in ${h}h ${m}m`
  if (m > 0) return `Resets in ${m}m ${s}s`
  return `Resets in ${s}s`
}

// Status definitions and styling
const STATUS_CONFIGS = {
  'Live': { color: '#10b981', label: 'Live' },
  'Slow': { color: '#f59e0b', label: 'Slow' },
  'Error': { color: '#ef4444', label: 'Error' },
  'Rate Limited': { color: '#f97316', label: 'Rate Limited' },
  'Disabled': { color: '#6b7280', label: 'Disabled' }
}

const getStatusConfig = (statusStr) => {
  if (!statusStr) return STATUS_CONFIGS.Disabled
  const norm = statusStr.trim()
  if (norm.startsWith('Error') || norm.toLowerCase().includes('fail') || norm.toLowerCase().includes('offline')) {
    return STATUS_CONFIGS.Error
  }
  return STATUS_CONFIGS[norm] || STATUS_CONFIGS.Error
}

// Memoized individual model row component for premium performance
const ModelRow = memo(({ model, onCopy, copiedId, isMobile }) => {
  const [expanded, setExpanded] = useState(false)
  const hasDiagnosticWarning = model.status !== 'Live'
  
  // Real limit percentages
  const usedPercent = model.daily_limit > 0 ? (model.used_today / model.daily_limit) * 100 : 0
  const remaining = Math.max(0, model.daily_limit - model.used_today)
  const isExhausted = remaining === 0

  // Progress bar color rules (0-70% Cyan, 70-90% Yellow, 90-100% Red)
  let barColor = '#06b6d4' // Cyan
  if (usedPercent >= 90) barColor = '#ef4444' // Red
  else if (usedPercent >= 70) barColor = '#eab308' // Yellow

  const statusCfg = getStatusConfig(model.status)

  // Map to clean model names if they contain OR prefixes
  const cleanModelName = model.model
    .replace('meta-llama/', '')
    .replace('mistralai/', '')
    .replace('qwen/', '')
    .replace('deepseek/', '')
    .replace('google/', '')
    .replace(':free', '')
    .replace('-instruct', '')
    .replace('-coder', '')

  const handleCopyClick = (e) => {
    e.stopPropagation()
    onCopy(model.id, model.api_key_name)
  }

  return (
    <div 
      className="model-infra-row"
      style={{
        borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
        padding: isMobile ? '16px 8px' : '20px 24px',
        transition: 'background 0.2s ease',
        background: 'rgba(255, 255, 255, 0.01)',
        position: 'relative'
      }}
    >
      <div 
        style={{
          display: 'grid',
          gridTemplateColumns: isMobile ? '1fr' : '1.2fr 1fr 1fr',
          gap: isMobile ? 12 : 24,
          alignItems: 'center'
        }}
      >
        {/* LEFT COLUMN: API Name, Provider, Key Alias */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 14, fontWeight: 600, color: '#f8fafc', letterSpacing: '-0.3px' }}>
              {cleanModelName}
            </span>
            {isExhausted && (
              <span style={{ fontSize: 9, padding: '2px 6px', background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', borderRadius: 4, fontWeight: 700 }}>
                EXHAUSTED
              </span>
            )}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 11, color: '#94a3b8' }}>
              {model.provider}
            </span>
          </div>
        </div>

        {/* CENTER COLUMN: Remaining requests, total requests, progress bar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span style={{ fontSize: 12, color: '#94a3b8' }}>
              <strong>{remaining.toLocaleString()}</strong> / {model.daily_limit.toLocaleString()} left
            </span>
            <span style={{ fontSize: 11, color: '#475569' }}>
              {usedPercent.toFixed(0)}% used
            </span>
          </div>
          
          {/* Minimal Solid Progress Bar */}
          <div 
            style={{
              width: '100%',
              height: 5,
              background: 'rgba(255, 255, 255, 0.06)',
              borderRadius: 3,
              overflow: 'hidden'
            }}
          >
            <div 
              style={{
                width: `${Math.min(100, usedPercent)}%`,
                height: '100%',
                background: barColor,
                borderRadius: 3,
                transition: 'width 0.4s cubic-bezier(0.4, 0, 0.2, 1)'
              }}
            />
          </div>
        </div>

        {/* RIGHT COLUMN: Reset timer, Live status dot, Latency */}
        <div 
          style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center',
            minWidth: 0
          }}
        >
          {/* Reset countdown */}
          <span style={{ fontSize: 12, color: '#64748b' }}>
            {formatCountdown(model.reset_seconds)}
          </span>

          {/* Status Indicator & Latency */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            {model.latency_ms !== null && model.latency_ms !== undefined && (
              <span style={{ fontSize: 11, color: '#475569', fontFamily: 'monospace' }}>
                {model.latency_ms}ms
              </span>
            )}
            
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span 
                style={{
                  height: 6,
                  width: 6,
                  borderRadius: '50%',
                  background: statusCfg.color,
                  boxShadow: `0 0 6px ${statusCfg.color}`,
                  animation: model.status === 'Live' ? 'glowPulse 2s infinite' : 'none'
                }}
              />
              <span style={{ fontSize: 12, fontWeight: 600, color: statusCfg.color }}>
                {statusCfg.label}
              </span>
            </div>

            {/* Expandable diagnostic info if error exists */}
            {hasDiagnosticWarning && (
              <button 
                onClick={() => setExpanded(!expanded)}
                style={{
                  background: 'none',
                  border: 'none',
                  padding: 4,
                  color: '#475569',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center'
                }}
              >
                {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Expanded diagnostic tray */}
      {hasDiagnosticWarning && expanded && (
        <div 
          style={{
            marginTop: 12,
            padding: 10,
            background: model.status === 'Rate Limited' ? 'rgba(245, 158, 11, 0.05)' : 'rgba(239, 68, 68, 0.05)',
            border: model.status === 'Rate Limited' ? '1px solid rgba(245, 158, 11, 0.1)' : '1px solid rgba(239, 68, 68, 0.1)',
            borderRadius: 6,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8
          }}
        >
          <AlertCircle size={14} style={{ color: model.status === 'Rate Limited' ? '#f59e0b' : '#ef4444', marginTop: 2, flexShrink: 0 }} />
          <div style={{ fontSize: 11, color: model.status === 'Rate Limited' ? '#fbbf24' : '#f87171', fontFamily: 'monospace', wordBreak: 'break-all' }}>
            {model.status === 'Rate Limited' 
              ? 'Diagnostic warning: Request limit reached. The self-healing router has automatically quarantined this node to prevent query latency.'
              : 'Diagnostic warning: Endpoint currently unreachable. The self-healing router has automatically isolated this node to prevent downstream query latency.'
            }
          </div>
        </div>
      )}
    </div>
  )
})

ModelRow.displayName = 'ModelRow'

export default function ApiStatusPage() {
  const { secureFetch } = useSession()
  const [loading, setLoading] = useState(false)
  const [models, setModels] = useState([])
  const [error, setError] = useState(null)
  const [copiedId, setCopiedId] = useState(null)
  const [isMobile, setIsMobile] = useState(false)

  // Polling fetcher
  const fetchStatus = useCallback(async (showIndicator = false) => {
    if (showIndicator) setLoading(true)
    setError(null)
    try {
      const resp = await secureFetch('/api/key-status')
      if (resp.ok) {
        const data = await resp.json()
        if (data && Array.isArray(data.models)) {
          setModels(data.models)
        }
      } else {
        const text = await resp.text()
        setError(`Failed to retrieve key statuses: ${text || resp.statusText}`)
      }
    } catch (e) {
      setError(`Network diagnostic error: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }, [secureFetch])

  // Initial and Polling effect (Exactly 10 seconds)
  useEffect(() => {
    fetchStatus(true)
    const pollInterval = setInterval(() => fetchStatus(false), 10000)
    return () => clearInterval(pollInterval)
  }, [fetchStatus])

  // Real-time second countdown update tick (Performance optimized)
  useEffect(() => {
    const timer = setInterval(() => {
      setModels(prev =>
        prev.map(m => ({
          ...m,
          reset_seconds: m.reset_seconds && m.reset_seconds > 0 ? m.reset_seconds - 1 : 0
        }))
      )
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  // Responsiveness listener
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 768)
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Clipboard copy handler
  const handleCopy = useCallback((id, text) => {
    if (!text) return
    navigator.clipboard.writeText(text).then(() => {
      setCopiedId(id)
      setTimeout(() => setCopiedId(null), 2000)
    })
  }, [])

  return (
    <section 
      className="content-section" 
      style={{ 
        minHeight: '100vh', 
        display: 'flex', 
        justifyContent: 'center', 
        alignItems: 'flex-start',
        padding: isMobile ? '24px 12px' : '40px 24px',
        background: '#060816'
      }}
    >
      <div 
        style={{ 
          width: '100%', 
          maxWidth: 960,
          display: 'flex',
          flexDirection: 'column',
          gap: 20
        }}
      >
        {/* HEADER SECTION */}
        <div 
          style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'flex-end',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
            paddingBottom: 20
          }}
        >
          <div>
            <h1 
              style={{ 
                fontSize: 22, 
                fontWeight: 700, 
                color: '#f8fafc',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                letterSpacing: '-0.4px',
                margin: 0
              }}
            >
              API Usage Limits
              {/* Dynamic live pulse dot */}
              <span 
                style={{
                  height: 6,
                  width: 6,
                  borderRadius: '50%',
                  background: '#10b981',
                  boxShadow: '0 0 6px #10b981',
                  animation: 'glowPulse 2s infinite'
                }}
              />
            </h1>
            <p className="text-secondary" style={{ fontSize: 13, marginTop: 4, margin: 0 }}>
              Monitor live API quota consumption and refresh cycles.
            </p>
          </div>

          <button 
            className="btn-secondary"
            onClick={() => fetchStatus(true)}
            disabled={loading}
            style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: 8, 
              padding: '6px 12px', 
              borderRadius: 6,
              fontSize: 12
            }}
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            Sync Status
          </button>
        </div>

        {/* Global error banner */}
        {error && (
          <div 
            style={{
              padding: '12px 16px',
              background: 'rgba(239, 68, 68, 0.06)',
              border: '1px solid rgba(239, 68, 68, 0.15)',
              borderRadius: 8,
              fontSize: 12,
              color: '#ef4444',
              display: 'flex',
              alignItems: 'center',
              gap: 8
            }}
          >
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        )}

        {/* INFRASTRUCTURE MONITORING ROWS CONTAINER */}
        <div 
          style={{
            background: 'rgba(10, 11, 23, 0.35)',
            border: '1px solid rgba(255, 255, 255, 0.06)',
            borderRadius: 12,
            overflow: 'hidden'
          }}
        >
          {models.length > 0 ? (
            models.map(m => (
              <ModelRow 
                key={m.id}
                model={m}
                onCopy={handleCopy}
                copiedId={copiedId}
                isMobile={isMobile}
              />
            ))
          ) : (
            <div 
              style={{ 
                padding: '48px 0', 
                textAlign: 'center', 
                color: '#64748b', 
                fontSize: 13 
              }}
            >
              {loading ? 'Initializing telemetry handshake...' : 'No active model connections mapped.'}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
