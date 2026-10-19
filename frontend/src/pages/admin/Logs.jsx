import { useState } from 'react'
import { api } from '../../api'
import { usePage } from '../../layout'
import { Alert, Empty, fmtDate, Loading, Pagination, useDebounced, useFetch } from '../../ui'

const tone = { Error: 'fake', Unauthorized: 'fake', Login: 'neutral', Prediction: 'real', Training: 'warn', Import: 'warn' }

export default function Logs() {
  usePage([{ label: 'Administration', to: '/admin' }, { label: 'Logs and activity' }])
  const [type, setType] = useState(''); const [q, setQ] = useState(''); const [page, setPage] = useState(1); const dq = useDebounced(q)
  const { data, error, loading } = useFetch(() => api.get('/api/admin/logs', { event_type: type, search: dq, page, page_size: 25 }), [type, dq, page])
  const act = useFetch(() => api.get('/api/admin/activity'))
  return (
    <div className="stack">
      <h1>Logs and user activity</h1>
      <div className="panel"><h2>System logs</h2>
        <div className="row" style={{ marginBottom: '1rem' }}>
          <div className="grow" style={{ minWidth: 220 }}><input type="search" placeholder="Search log descriptions" aria-label="Search logs" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></div>
          <select aria-label="Filter by event type" style={{ width: 'auto' }} value={type} onChange={(e) => { setType(e.target.value); setPage(1) }}><option value="">All events</option>{(data?.event_types || []).sort().map((t) => <option key={t}>{t}</option>)}</select></div>
        {error && <Alert>{error}</Alert>}
        {loading && !data ? <Loading /> : data && !data.items.length ? <Empty title="No log entries match" /> : data && (<>
          <div className="table-wrap"><table><thead><tr><th>Time</th><th>Event</th><th>User</th><th>Description</th><th>IP address</th></tr></thead>
            <tbody>{data.items.map((l) => <tr key={l.log_id}><td className="nowrap">{fmtDate(l.date)}</td><td><span className={`badge ${tone[l.event_type] || 'neutral'}`}>{l.event_type}</span></td><td>{l.user || '-'}</td><td style={{ maxWidth: 480 }}>{l.description}</td><td className="small">{l.ip_address || '-'}</td></tr>)}</tbody></table></div>
          <div className="row between"><span className="muted small">{data.total.toLocaleString()} entries</span><Pagination page={data.page} pages={data.pages} onPage={setPage} /></div></>)}
      </div>
      <div className="panel"><h2>User activity</h2>
        {act.loading ? <Loading /> : <div className="table-wrap"><table><thead><tr><th>User</th><th>Role</th><th>Status</th><th>Last login</th><th>Predictions</th><th>Last prediction</th></tr></thead>
          <tbody>{act.data.items.map((u) => <tr key={u.user_id}><td>{u.email}</td><td>{u.role}</td><td><span className={`badge ${u.is_active ? 'real' : 'fake'}`}>{u.is_active ? 'Active' : 'Deactivated'}</span></td><td className="nowrap">{fmtDate(u.last_login)}</td><td>{u.predictions}</td><td className="nowrap">{fmtDate(u.last_prediction)}</td></tr>)}</tbody></table></div>}
      </div>
    </div>
  )
}
