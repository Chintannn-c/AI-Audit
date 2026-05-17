import { useState, useEffect, useRef } from 'react'

const STEPS = [
  'Reading ledger file...',
  'Analyzing transactions...',
  'Calculating sample size...',
  'Selecting TOD samples...',
  'Selecting TOC samples...'
]

export default function ProcessingOverlay({ visible }) {
  const [currentStep, setCurrentStep] = useState(0)
  const intervalRef = useRef(null)

  useEffect(() => {
    if (visible) {
      setCurrentStep(0)
      intervalRef.current = setInterval(() => {
        setCurrentStep(prev => {
          if (prev >= STEPS.length) {
            clearInterval(intervalRef.current)
            return prev
          }
          return prev + 1
        })
      }, 800)
    } else {
      clearInterval(intervalRef.current)
    }
    return () => clearInterval(intervalRef.current)
  }, [visible])

  if (!visible) return null

  return (
    <div className="processing-overlay">
      <div className="processing-spinner" />
      <h2 style={{ marginBottom: 8 }}>AI Engine Processing...</h2>
      <p className="text-secondary">Please wait while we analyze your ledger</p>
      <ul className="processing-steps">
        {STEPS.map((step, i) => {
          let cls = ''
          let icon = '○'
          if (i < currentStep) { cls = 'done'; icon = '✓' }
          else if (i === currentStep) { cls = 'active'; icon = '◉' }
          return (
            <li key={i} className={cls}>
              <span className="step-icon">{icon}</span> {step}
            </li>
          )
        })}
      </ul>
    </div>
  )
}
