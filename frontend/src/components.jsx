import { useEffect, useState } from 'react'
import { Chart as ChartJS, ArcElement, BarController, BarElement, CategoryScale, DoughnutController, Filler, Legend, LineController, LineElement, LinearScale, PointElement, Tooltip } from 'chart.js'
import { Chart } from 'react-chartjs-2'
import { pct } from './ui'

ChartJS.register(BarController, LineController, DoughnutController, ArcElement, BarElement, CategoryScale, Filler, Legend, LineElement, LinearScale, PointElement, Tooltip)

/* ---- direction helper: a weight is relative to the PREDICTED class (+ = supports it) ---- */
export const towards = (predicted, weight) => ((predicted === 'Fake') === (weight > 0) ? 'fake' : 'real')
export const signed = (w) => `${w > 0 ? '+' : ''}${w.toFixed(2)}`

/* ---- the article with influential words marked inside the original text ---- */
export function Evidence({ segments, predicted }) {
  const max = Math.max(0.0001, ...segments.map((s) => Math.abs(s.weight || 0)))
  return (
    <>
      <div className="legend" style={{ marginBottom: '.8rem' }}>
        <span><span className="swatch f" />Pushes towards fake</span>
        <span><span className="swatch r" />Pushes towards real</span>
        <span>Darker = stronger influence. Hover a marked word for its weight.</span>
      </div>
      <div className="article" lang="en">
        {segments.map((s, i) => s.weight == null ? s.text : (
          <mark key={i} className={`ev toward-${towards(predicted, s.weight)}`} style={{ '--a': Math.min(1, Math.abs(s.weight) / max) }}
            title={`${s.text}: ${signed(s.weight)} (${s.weight > 0 ? 'supports' : 'opposes'} the "${predicted}" prediction)`}>{s.text}</mark>
        ))}
      </div>
    </>
  )
}

/* ---- horizontal bars for word contributions ---- */
export function WordBars({ items, predicted, limit = 10 }) {
  const rows = items.slice(0, limit)
  if (!rows.length) return <p className="muted small">No words in this group.</p>
  const max = Math.max(...rows.map((r) => Math.abs(r.weight)))
  return (
    <div className="bars">
      {rows.map((r) => (
        <div className="bar" key={r.word}>
          <span title={r.word} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{r.word}</span>
          <span className="track"><span className={`fill toward-${towards(predicted, r.weight)}`} style={{ left: 0, width: `${(Math.abs(r.weight) / max) * 100}%` }} /></span>
          <span className="w">{signed(r.weight)}</span>
        </div>
      ))}
    </div>
  )
}

export function ProbabilityMeter({ fake, real }) {
  return (
    <div>
      <div className="meter" role="img" aria-label={`Fake ${pct(fake)}, real ${pct(real)}`}><div className="f" style={{ width: `${fake * 100}%` }} /><div className="r" style={{ width: `${real * 100}%` }} /></div>
      <div className="row between small muted"><span>Fake {pct(fake)}</span><span>Real {pct(real)}</span></div>
    </div>
  )
}

/* ---- chart.js wrapper that follows the light/dark theme ---- */
function useThemeColors() {
  const read = () => {
    const s = getComputedStyle(document.documentElement)
    const g = (n) => s.getPropertyValue(n).trim()
    return { ink: g('--ink'), soft: g('--ink-soft'), line: g('--line'), fake: g('--fake'), real: g('--real'), navy: g('--navy') }
  }
  const [c, setC] = useState(read)
  useEffect(() => {
    const mo = new MutationObserver(() => setC(read()))
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return c
}

export function ChartBox({ type = 'bar', data, options = {}, height = 280, empty = 'No data yet.' }) {
  const c = useThemeColors()
  const has = data?.datasets?.some((d) => d.data?.length)
  if (!has) return <p className="muted small" style={{ padding: '1rem 0' }}>{empty}</p>
  const scaled = type !== 'doughnut' && type !== 'pie'
  const merged = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { labels: { color: c.ink } }, ...(options.plugins || {}) },
    ...(scaled ? { scales: { x: { ticks: { color: c.soft }, grid: { color: c.line } }, y: { ticks: { color: c.soft }, grid: { color: c.line }, beginAtZero: true }, ...(options.scales || {}) } } : {}),
    ...Object.fromEntries(Object.entries(options).filter(([k]) => !['plugins', 'scales'].includes(k))),
  }
  return <div className="chart-box" style={{ height }}><Chart type={type} data={data} options={merged} /></div>
}
export { useThemeColors }
