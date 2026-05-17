import { createContext, useContext, useState, useCallback } from 'react'

const AuditContext = createContext(null)

export function AuditProvider({ children }) {
  const [maxUnlockedStage, setMaxUnlockedStage] = useState(1)
  const [materiality, setMateriality] = useState({ overall: 0, performance: 0, trivial: 0 })
  const [riskClassification, setRiskClassification] = useState({
    auditType: '—',
    isLargeAudit: true,
    approach: '—',
    auditTypeColor: '#fff'
  })
  const [samplingResults, setSamplingResults] = useState(null)
  const [uploadedFile, setUploadedFile] = useState(null)
  const [selectedCategory, setSelectedCategory] = useState('Sales')
  const [selectedBasis, setSelectedBasis] = useState('count')
  const [selectedExactPct, setSelectedExactPct] = useState(0.05)
  const [aiInsights, setAiInsights] = useState({ focus: '', summary: '' })
  const [dashboard, setDashboard] = useState(null)

  const unlockStage = useCallback((stage) => {
    setMaxUnlockedStage(prev => Math.max(prev, stage))
  }, [])

  return (
    <AuditContext.Provider value={{
      maxUnlockedStage, unlockStage,
      materiality, setMateriality,
      riskClassification, setRiskClassification,
      samplingResults, setSamplingResults,
      uploadedFile, setUploadedFile,
      selectedCategory, setSelectedCategory,
      selectedBasis, setSelectedBasis,
      selectedExactPct, setSelectedExactPct,
      aiInsights, setAiInsights,
      dashboard, setDashboard
    }}>
      {children}
    </AuditContext.Provider>
  )
}

export function useAudit() {
  const ctx = useContext(AuditContext)
  if (!ctx) throw new Error('useAudit must be used within AuditProvider')
  return ctx
}
