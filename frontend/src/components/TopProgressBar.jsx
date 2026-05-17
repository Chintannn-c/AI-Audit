export default function TopProgressBar({ currentIndex, total }) {
  const pct = currentIndex >= 0 ? ((currentIndex + 1) / total) * 100 : 0
  return <div className="top-progress-bar" style={{ width: `${pct}%` }} />
}
