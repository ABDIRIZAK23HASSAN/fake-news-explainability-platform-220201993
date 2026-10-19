import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, download } from '../../api'
import { usePage } from '../../layout'
import { Alert, Button, Empty, fmtDate, LabelBadge, Loading, Pagination, pct, useConfirm, useDebounced, useFetch, useToast } from '../../ui'

export default function History() {
  usePage([{ label: 'Dashboard', to: '/dashboard' }, { label: 'Prediction history' }])
  const nav = useNavigate(); const toast = useToast(); const confirm = useConfirm()
  const [q, setQ] = useState(''); const [result, setResult] = useState(''); const [sort, setSort] = useState('date'); const [order, setOrder] = useState('desc'); const [page, setPage] = useState(1)
  const [sel, setSel] = useState(new Set())
  const [fmt, setFmt] = useState('pdf')
  useEffect(() => { api.get('/api/users/settings').then((x) => setFmt(x.default_export_format.toLowerCase())).catch(() => {}) }, [])
  const dq = useDebounced(q)
  const { data, error, loading, reload } = useFetch(() => api.get('/api/predictions/history', { search: dq, result, sort, order, page, page_size: 10 }), [dq, result, sort, order, page])

  const head = (key, label) => <th className="sortable" onClick={() => { if (sort === key) setOrder(order === 'asc' ? 'desc' : 'asc'); else { setSort(key); setOrder('desc') } setPage(1) }}
    aria-sort={sort === key ? (order === 'asc' ? 'ascending' : 'descending') : 'none'}>{label}{sort === key ? (order === 'asc' ? ' (asc)' : ' (desc)') : ''}</th>
  const toggle = (id) => { const s = new Set(sel); s.has(id) ? s.delete(id) : s.add(id); setSel(s) }
  const run = async (fn, ok) => { try { await fn(); if (ok) toast(ok, 'ok') } catch (e) { toast(e.message, 'error') } }
  const del = async (ids) => {
    if (!(await confirm({ title: 'Delete from history', message: `Delete ${ids.length} prediction${ids.length > 1 ? 's' : ''}? This cannot be undone.`, confirmLabel: 'Delete' }))) return
    await run(async () => { await api.post('/api/predictions/delete', { ids }); setSel(new Set()); reload() }, 'Deleted')
  }

  return (
    <div className="stack">
      <div className="row between"><h1>Prediction history</h1>
        <div className="row">
          <Button variant="secondary" small onClick={() => run(() => download('/api/predictions/export', sel.size ? { ids: [...sel].join(',') } : {}), 'Export ready')}>{sel.size ? `Export ${sel.size} selected (CSV)` : 'Export all (CSV)'}</Button>
          {sel.size > 0 && <Button variant="danger" small onClick={() => del([...sel])}>Delete {sel.size} selected</Button>}</div></div>
      <div className="panel">
        <div className="row" style={{ marginBottom: '1rem' }}>
          <div className="grow" style={{ minWidth: 220 }}><input type="search" placeholder="Search titles, text and keywords" aria-label="Search history" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></div>
          <select aria-label="Filter by result" style={{ width: 'auto' }} value={result} onChange={(e) => { setResult(e.target.value); setPage(1) }}>
            <option value="">All results</option><option value="Fake">Fake only</option><option value="Real">Real only</option></select>
        </div>
        {error && <Alert>{error}</Alert>}
        {loading && !data ? <Loading /> : data && !data.items.length ? (
          <Empty title={dq || result ? 'No analyses match your filters' : 'No analyses yet'}>{!dq && !result && <Link className="btn" to="/analyze">Analyze an article</Link>}</Empty>
        ) : data && (<>
          <div className="table-wrap"><table>
            <thead><tr><th style={{ width: 30 }} /><th>Article</th>{head('result', 'Result')}{head('confidence', 'Confidence')}{head('date', 'Date')}{head('processing_time', 'Time')}<th>Model</th><th /></tr></thead>
            <tbody>{data.items.map((p) => (
              <tr key={p.prediction_id}>
                <td><input type="checkbox" aria-label={`Select prediction ${p.prediction_id}`} checked={sel.has(p.prediction_id)} onChange={() => toggle(p.prediction_id)} /></td>
                <td><Link to={`/results/${p.prediction_id}`}>{p.title || `${p.snippet.slice(0, 80)}...`}</Link></td>
                <td><LabelBadge label={p.result} /></td><td>{pct(p.confidence)}</td><td className="nowrap">{fmtDate(p.date)}</td><td>{p.processing_time.toFixed(2)}s</td>
                <td className="small muted" style={{ maxWidth: 160 }}>{p.model || 'deleted'}</td>
                <td className="nowrap">
                  <Button variant="ghost" small onClick={() => nav(`/results/${p.prediction_id}`)}>Open</Button>
                  <Button variant="ghost" small onClick={() => run(() => download(`/api/predictions/${p.prediction_id}/export`, { format: fmt }))}>{fmt.toUpperCase()}</Button>
                  <Button variant="ghost" small onClick={() => del([p.prediction_id])}>Delete</Button></td>
              </tr>))}</tbody></table></div>
          <div className="row between"><span className="muted small">{data.total} result{data.total === 1 ? '' : 's'}</span><Pagination page={data.page} pages={data.pages} onPage={setPage} /></div>
        </>)}
      </div>
    </div>
  )
}
