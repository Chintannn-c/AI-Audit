import { useSession } from '../context/SessionContext'
import { Calculator, ClipboardList, Layers, Search, FileText, Home, RefreshCw, ShieldCheck, Key } from 'lucide-react'
import { useState, useEffect } from 'react'

const NAV_ITEMS = [
  { path: '/', label: 'Home', icon: Home, stage: 0 },
  { path: '/materiality', label: 'Materiality', icon: Calculator, stage: 1 },
  { path: '/risk', label: 'Classification', icon: ClipboardList, stage: 2 },
  { path: '/sampling', label: 'Sampling', icon: Layers, stage: 3 },
  { path: '/vouching', label: 'Vouching', icon: Search, stage: 4 },
  { path: '/reports', label: 'Reports', icon: FileText, stage: 5, section: 'Analysis' },
  { path: '/api-status', label: 'AI Status', icon: Key, stage: 0 }
]

export default function Sidebar({ collapsed, currentPath, navigateTo, maxUnlockedStage }) {
  const { clearSession } = useSession()
  const [theme, setTheme] = useState(() => localStorage.getItem('stataudit_theme') || 'default')

  useEffect(() => {
    if (theme === 'default') {
      document.documentElement.removeAttribute('data-theme')
      localStorage.removeItem('stataudit_theme')
    } else {
      document.documentElement.setAttribute('data-theme', theme)
      localStorage.setItem('stataudit_theme', theme)
    }
  }, [theme])

  return (
    <aside className={`sidebar ${collapsed ? 'collapsed' : ''}`}>
      <div className="sidebar-header">
        <div className="logo">
          <ShieldCheck style={{ color: 'var(--accent-primary)', filter: 'drop-shadow(0 0 8px var(--accent-primary))' }} size={22} />
          <span>StatAudit AI</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="nav-label">Main Menu</div>
        {NAV_ITEMS.map((item) => {
          if (item.section) {
            return (
              <div key={`section-${item.section}`}>
                <div className="nav-label" style={{ marginTop: 20 }}>{item.section}</div>
                <a
                  href="#"
                  className={`nav-link ${currentPath === item.path ? 'active' : ''} ${item.stage > maxUnlockedStage ? 'disabled' : ''}`}
                  onClick={(e) => { e.preventDefault(); navigateTo(item.path) }}
                >
                  <item.icon size={16} /> {item.label}
                </a>
              </div>
            )
          }
          return (
            <a
              key={item.path}
              href="#"
              className={`nav-link ${currentPath === item.path ? 'active' : ''} ${item.stage > maxUnlockedStage ? 'disabled' : ''}`}
              onClick={(e) => { e.preventDefault(); navigateTo(item.path) }}
            >
              <item.icon size={16} /> {item.label}
            </a>
          )
        })}
      </nav>

      <div style={{ padding: 16, marginTop: 'auto', borderTop: '1px solid var(--glass-border)' }}>
        <div className="form-group mb-12">
          <label className="form-label" style={{ fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6, display: 'block' }}>UI Theme</label>
          <select
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
            className="glass-input"
            style={{ padding: '6px 10px', fontSize: 12, background: 'rgba(15,23,42,0.6)', borderRadius: 8, width: '100%' }}
          >
            <option value="default">Midnight Indigo</option>
            <option value="emerald">Emerald Mint</option>
            <option value="sunset">Sunset Crimson</option>
            <option value="cyberpunk">Cyberpunk Neon</option>
            <option value="slate">Classic Slate</option>
          </select>
        </div>
        <button onClick={clearSession} className="btn-secondary w-full" style={{ fontSize: 11, padding: 8 }}>
          <RefreshCw size={12} style={{ display: 'inline', verticalAlign: 'middle', marginRight: 4 }} />
          New Session
        </button>
      </div>
    </aside>
  )
}
