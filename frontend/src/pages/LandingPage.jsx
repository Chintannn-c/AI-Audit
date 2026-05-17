export default function LandingPage({ navigateTo }) {
  return (
    <section className="content-section" style={{ justifyContent: 'center', alignItems: 'center', padding: 0 }}>
      <div className="hero-section" style={{ maxWidth: 900 }}>
        <h1 className="hero-title" style={{ fontSize: 56, lineHeight: 1.1, marginBottom: 16 }}>
          AI-Powered Statutory<br />Audit Sampling
        </h1>
        <p className="hero-subtitle" style={{ fontSize: 16, maxWidth: 650, margin: '0 auto 28px auto', opacity: 0.8 }}>
          Intelligent sample selection for Test of Details & Test of Controls. Dual-mode sampling, 10 risk indicators, zero-overlap guarantee.
        </p>
        <div style={{ display: 'flex', justifyContent: 'center', width: '100%' }}>
          <div className="glass-card" style={{ textAlign: 'left', borderLeft: '4px solid var(--accent-primary)', padding: 24, maxWidth: 460, width: '100%' }}>
            <h3 style={{ marginBottom: 8, fontSize: 17 }}>Materiality & Planning</h3>
            <p style={{ color: 'var(--text-secondary)', fontSize: 13, marginBottom: 20 }}>
              Calculate statutory materiality thresholds and perform audit classification.
            </p>
            <button className="btn-primary w-full" onClick={() => navigateTo('/materiality')}>Start Audit</button>
          </div>
        </div>
      </div>
    </section>
  )
}
