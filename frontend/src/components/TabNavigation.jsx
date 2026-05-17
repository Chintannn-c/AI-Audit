import { Calculator, ShieldCheck, Layers, Search } from 'lucide-react'

const TABS = [
  { path: '/materiality', label: '1. Planning', icon: Calculator, stage: 1 },
  { path: '/risk', label: '2. Risk', icon: ShieldCheck, stage: 2 },
  { path: '/sampling', label: '3. Sampling', icon: Layers, stage: 3 },
  { path: '/vouching', label: '4. Vouching', icon: Search, stage: 4 }
]

export default function TabNavigation({ currentPath, navigateTo, maxUnlockedStage }) {
  return (
    <div className="tab-container mb-24">
      {TABS.map(tab => (
        <button
          key={tab.path}
          className={`tab-btn ${currentPath === tab.path ? 'active' : ''} ${tab.stage > maxUnlockedStage ? 'disabled' : ''}`}
          onClick={() => navigateTo(tab.path)}
        >
          <tab.icon size={14} /> {tab.label}
        </button>
      ))}
    </div>
  )
}
