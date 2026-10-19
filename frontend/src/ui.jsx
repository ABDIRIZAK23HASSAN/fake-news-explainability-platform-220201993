import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

/* ---------- basic controls ---------- */
export function Spinner() { return <span className="spinner" role="status" aria-label="Loading" /> }

export function Button({ variant = 'primary', loading, small, children, ...rest }) {
  return (
    <button className={`btn ${variant === 'primary' ? '' : variant} ${small ? 'sm' : ''}`} disabled={loading || rest.disabled} {...rest}>
      {loading && <Spinner />}{children}
    </button>
  )
}

export function Field({ label, error, hint, id, children, ...input }) {
  const fid = id || `f-${label?.toLowerCase().replace(/\W+/g, '-')}`
  return (
    <div className="field">
      {label && <label htmlFor={fid}>{label}</label>}
      {children || <input id={fid} aria-invalid={!!error} aria-describedby={error ? `${fid}-e` : undefined} {...input} />}
      {hint && !error && <span className="hint">{hint}</span>}
      {error && <span className="err" id={`${fid}-e`}>{error}</span>}
    </div>
  )
}

export const Alert = ({ kind = 'error', children }) => children ? <div className={`alert ${kind}`} role={kind === 'error' ? 'alert' : 'status'}>{children}</div> : null
export const Loading = ({ text = 'Loading...' }) => <div className="loading-block"><Spinner /><span>{text}</span></div>
export const Empty = ({ title, children }) => <div className="empty"><h3>{title}</h3>{children}</div>

export function LabelBadge({ label }) {
  return <span className={`badge ${label === 'Fake' ? 'fake' : 'real'}`}>{label === 'Fake' ? 'Fake news' : 'Real news'}</span>
}

export const StatCard = ({ value, label, tone }) => <div className={`stat ${tone || ''}`}><div className="v">{value}</div><div className="l">{label}</div></div>

export function Breadcrumbs({ items }) {
  return (
    <nav className="crumbs" aria-label="Breadcrumb">
      {items.map((it, i) => (
        <span key={i}>{i > 0 && <span aria-hidden="true"> / </span>}
          {it.to && i < items.length - 1 ? <Link to={it.to}>{it.label}</Link> : <span aria-current={i === items.length - 1 ? 'page' : undefined}>{it.label}</span>}
        </span>
      ))}
    </nav>
  )
}

export function Pagination({ page, pages, onPage }) {
  if (!pages || pages <= 1) return null
  return (
    <div className="pager">
      <Button variant="secondary" small disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
      <span className="muted small">Page {page} of {pages}</span>
      <Button variant="secondary" small disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
    </div>
  )
}

/* ---------- toasts ---------- */
const ToastCtx = createContext(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((message, kind = 'info') => {
    const id = Math.random().toString(36).slice(2)
    setItems((s) => [...s, { id, message, kind }])
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), kind === 'error' ? 7000 : 4000)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">{items.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.message}</div>)}</div>
    </ToastCtx.Provider>
  )
}

/* ---------- modal + promise-based confirmation dialog ---------- */
export function Modal({ title, onClose, children, wide }) {
  const ref = useRef(null)
  useEffect(() => {
    const prev = document.activeElement
    ref.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.() }
  }, [onClose])
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <h2>{title}</h2>{children}
      </div>
    </div>
  )
}

const ConfirmCtx = createContext(async () => false)
export const useConfirm = () => useContext(ConfirmCtx)
export function ConfirmProvider({ children }) {
  const [state, setState] = useState(null)
  const confirm = useCallback((opts) => new Promise((resolve) => setState({ ...opts, resolve })), [])
  const close = (v) => { state.resolve(v); setState(null) }
  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      {state && (
        <Modal title={state.title || 'Are you sure?'} onClose={() => close(false)}>
          <p>{state.message}</p>
          <div className="row" style={{ justifyContent: 'flex-end' }}>
            <Button variant="secondary" onClick={() => close(false)}>Cancel</Button>
            <Button variant={state.danger === false ? 'primary' : 'danger'} onClick={() => close(true)}>{state.confirmLabel || 'Confirm'}</Button>
          </div>
        </Modal>
      )}
    </ConfirmCtx.Provider>
  )
}

/* ---------- data loading hook ---------- */
export function useFetch(fn, deps = []) {
  const [state, setState] = useState({ data: null, error: '', loading: true })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    let alive = true
    setState((s) => ({ ...s, loading: true, error: '' }))
    fn().then((data) => alive && setState({ data, error: '', loading: false }))
      .catch((e) => alive && setState({ data: null, error: e.message, loading: false }))
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])
  return { ...state, reload: () => setTick((t) => t + 1) }
}

export const pct = (v, d = 1) => (v === null || v === undefined ? '-' : `${(v * 100).toFixed(d)}%`)
export const fmtDate = (s) => (s ? new Date(s).toLocaleString() : '-')
export function useDebounced(value, ms = 350) {
  const [v, setV] = useState(value)
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t) }, [value, ms])
  return v
}
