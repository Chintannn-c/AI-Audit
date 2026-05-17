import { Routes, Route, useLocation, useNavigate } from 'react-router-dom'
import { useAudit } from './context/AuditContext'
import { useSession } from './context/SessionContext'
import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import TopProgressBar from './components/TopProgressBar'
import TabNavigation from './components/TabNavigation'
import ProcessingOverlay from './components/ProcessingOverlay'
import LandingPage from './pages/LandingPage'
import MaterialityPage from './pages/MaterialityPage'
import RiskPage from './pages/RiskPage'
import SamplingPage from './pages/SamplingPage'
import VouchingPage from './pages/VouchingPage'
import ReportsPage from './pages/ReportsPage'

const STAGE_MAP = {
  '/': 0,
  '/materiality': 1,
  '/risk': 2,
  '/sampling': 3,
  '/vouching': 4,
  '/reports': 5
}

const STAGE_NAMES = {
  1: '1. Planning & Materiality',
  2: '2. Risk Classification',
  3: '3. Sampling Generation',
  4: '4. Forensic Vouching',
  5: '5. Reports Summary'
}

const AUDIT_SECTIONS = ['/materiality', '/risk', '/sampling', '/vouching']

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const { maxUnlockedStage } = useAudit()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true)
  const [processing, setProcessing] = useState(false)

  const currentPath = location.pathname
  const isLanding = currentPath === '/'
  const showTabs = AUDIT_SECTIONS.includes(currentPath)
  const currentStageIndex = AUDIT_SECTIONS.indexOf(currentPath)

  // Gate navigation
  const navigateTo = (path) => {
    const targetStage = STAGE_MAP[path] || 0
    if (targetStage > maxUnlockedStage) {
      alert(`Access Locked: Please complete the "${STAGE_NAMES[maxUnlockedStage]}" step first to proceed.`)
      return
    }
    navigate(path)
    window.scrollTo({ top: 0, behavior: 'smooth' })

    // Auto-close sidebar on mobile
    if (window.innerWidth <= 768) {
      setSidebarCollapsed(true)
    }
  }

  return (
    <>
      {!isLanding && (
        <TopProgressBar currentIndex={currentStageIndex} total={AUDIT_SECTIONS.length} />
      )}

      {!isLanding && (
        <button
          className={`sidebar-toggle ${!sidebarCollapsed ? 'active' : ''}`}
          onClick={() => setSidebarCollapsed(prev => !prev)}
        >
          {sidebarCollapsed ? '☰' : '◁'}
        </button>
      )}

      <div className="app-container">
        {!isLanding && (
          <Sidebar
            collapsed={sidebarCollapsed}
            currentPath={currentPath}
            navigateTo={navigateTo}
            maxUnlockedStage={maxUnlockedStage}
          />
        )}

        <main className={`main-wrapper ${isLanding || sidebarCollapsed ? 'expanded' : ''}`}>
          <div className="content-area">
            {showTabs && (
              <TabNavigation
                currentPath={currentPath}
                navigateTo={navigateTo}
                maxUnlockedStage={maxUnlockedStage}
              />
            )}

            <Routes>
              <Route path="/" element={<LandingPage navigateTo={navigateTo} />} />
              <Route path="/materiality" element={<MaterialityPage navigateTo={navigateTo} />} />
              <Route path="/risk" element={<RiskPage navigateTo={navigateTo} />} />
              <Route path="/sampling" element={<SamplingPage setProcessing={setProcessing} />} />
              <Route path="/vouching" element={<VouchingPage />} />
              <Route path="/reports" element={<ReportsPage />} />
            </Routes>
          </div>
        </main>

        <ProcessingOverlay visible={processing} />
      </div>
    </>
  )
}
