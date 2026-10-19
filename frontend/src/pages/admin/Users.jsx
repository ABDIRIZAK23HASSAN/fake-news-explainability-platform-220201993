import { useState } from 'react'
import { api } from '../../api'
import { useAuth } from '../../auth'
import { usePage } from '../../layout'
import { Alert, Button, Empty, Field, fmtDate, Loading, Modal, Pagination, useConfirm, useDebounced, useFetch, useToast } from '../../ui'

function UserForm({ initial, onClose, onSaved }) {
  const isNew = !initial
  const [f, setF] = useState(initial ? { first_name: initial.first_name, last_name: initial.last_name, email: initial.email, role: initial.role } : { first_name: '', last_name: '', email: '', password: '', role: 'User' })
  const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const save = async () => {
    setBusy(true); setErr('')
    try { isNew ? await api.post('/api/admin/users', f) : await api.put(`/api/admin/users/${initial.id}`, f); onSaved() } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  return (
    <Modal title={isNew ? 'Add user' : 'Edit user'} onClose={onClose}>
      <Alert>{err}</Alert>
      <div className="grid g2"><Field label="First name" value={f.first_name} onChange={set('first_name')} /><Field label="Last name" value={f.last_name} onChange={set('last_name')} /></div>
      <Field label="Email" type="email" value={f.email} onChange={set('email')} />
      {isNew && <Field label="Initial password" type="password" value={f.password} onChange={set('password')} hint="At least 8 characters, with letters and numbers" />}
      <Field label="Role" id="u-role"><select id="u-role" value={f.role} onChange={set('role')}><option>User</option><option>Administrator</option></select></Field>
      <div className="row" style={{ justifyContent: 'flex-end' }}><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy}>{isNew ? 'Add user' : 'Save changes'}</Button></div>
    </Modal>
  )
}

function ResetModal({ user, onClose }) {
  const toast = useToast(); const [pw, setPw] = useState(''); const [err, setErr] = useState('')
  const go = async () => { try { await api.post(`/api/admin/users/${user.id}/reset-password`, { new_password: pw }); toast('Password reset', 'ok'); onClose() } catch (e) { setErr(e.message) } }
  return <Modal title={`Reset password for ${user.email}`} onClose={onClose}><Alert>{err}</Alert>
    <Field label="New password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} hint="Tell the user this password; they can change it from their profile." />
    <div className="row" style={{ justifyContent: 'flex-end' }}><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={go}>Reset password</Button></div></Modal>
}

export default function Users() {
  usePage([{ label: 'Administration', to: '/admin' }, { label: 'Users' }])
  const { user: me } = useAuth(); const toast = useToast(); const confirm = useConfirm()
  const [q, setQ] = useState(''); const [role, setRole] = useState(''); const [active, setActive] = useState(''); const [page, setPage] = useState(1); const [modal, setModal] = useState(null)
  const dq = useDebounced(q)
  const { data, error, loading, reload } = useFetch(() => api.get('/api/admin/users', { search: dq, role, is_active: active, page, page_size: 10 }), [dq, role, active, page])
  const act = async (fn, ok) => { try { await fn(); toast(ok, 'ok'); reload() } catch (e) { toast(e.message, 'error') } }
  return (
    <div className="stack">
      <div className="row between"><h1>Users</h1><Button onClick={() => setModal({ type: 'form' })}>Add user</Button></div>
      <div className="panel">
        <div className="row" style={{ marginBottom: '1rem' }}>
          <div className="grow" style={{ minWidth: 220 }}><input type="search" placeholder="Search by name or email" aria-label="Search users" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></div>
          <select aria-label="Filter by role" style={{ width: 'auto' }} value={role} onChange={(e) => { setRole(e.target.value); setPage(1) }}><option value="">All roles</option><option>User</option><option>Administrator</option></select>
          <select aria-label="Filter by status" style={{ width: 'auto' }} value={active} onChange={(e) => { setActive(e.target.value); setPage(1) }}><option value="">Any status</option><option value="true">Active</option><option value="false">Deactivated</option></select>
        </div>
        {error && <Alert>{error}</Alert>}
        {loading && !data ? <Loading /> : data && !data.items.length ? <Empty title="No users match your filters" /> : data && (<>
          <div className="table-wrap"><table>
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Predictions</th><th>Last login</th><th /></tr></thead>
            <tbody>{data.items.map((u) => (
              <tr key={u.id}><td>{u.first_name} {u.last_name}</td><td>{u.email}</td>
                <td><span className={`badge ${u.role === 'Administrator' ? 'warn' : 'neutral'}`}>{u.role}</span></td>
                <td><span className={`badge ${u.is_active ? 'real' : 'fake'}`}>{u.is_active ? 'Active' : 'Deactivated'}</span></td>
                <td>{u.predictions}</td><td className="nowrap">{fmtDate(u.last_login)}</td>
                <td className="nowrap">
                  <Button variant="ghost" small onClick={() => setModal({ type: 'form', user: u })}>Edit</Button>
                  <Button variant="ghost" small onClick={() => setModal({ type: 'reset', user: u })}>Reset password</Button>
                  {u.is_active ? <Button variant="ghost" small disabled={u.id === me.id} onClick={() => act(() => api.post(`/api/admin/users/${u.id}/deactivate`), 'User deactivated')}>Deactivate</Button>
                    : <Button variant="ghost" small onClick={() => act(() => api.post(`/api/admin/users/${u.id}/activate`), 'User activated')}>Activate</Button>}
                  <Button variant="ghost" small disabled={u.id === me.id} onClick={async () => { if (await confirm({ title: 'Delete user', message: `Delete ${u.email} and all of their prediction history? This cannot be undone.`, confirmLabel: 'Delete user' })) act(() => api.del(`/api/admin/users/${u.id}`), 'User deleted') }}>Delete</Button></td></tr>))}</tbody></table></div>
          <div className="row between"><span className="muted small">{data.total} users</span><Pagination page={data.page} pages={data.pages} onPage={setPage} /></div></>)}
      </div>
      {modal?.type === 'form' && <UserForm initial={modal.user} onClose={() => setModal(null)} onSaved={() => { setModal(null); toast('User saved', 'ok'); reload() }} />}
      {modal?.type === 'reset' && <ResetModal user={modal.user} onClose={() => setModal(null)} />}
    </div>
  )
}
