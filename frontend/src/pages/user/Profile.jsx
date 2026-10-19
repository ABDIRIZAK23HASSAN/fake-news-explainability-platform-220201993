import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { useAuth } from '../../auth'
import { usePage } from '../../layout'
import { Alert, Button, Field, Modal, useToast } from '../../ui'

const pwError = (p) => (p.length < 8 ? 'Password is too short (minimum 8 characters)' : !/\d/.test(p) || !/[A-Za-z]/.test(p) ? 'Password must contain both letters and numbers' : '')

export default function Profile() {
  usePage([{ label: 'Dashboard', to: '/dashboard' }, { label: 'My profile' }])
  const { user, setUser, logout } = useAuth(); const toast = useToast(); const nav = useNavigate()
  const [f, setF] = useState({ first_name: user.first_name, last_name: user.last_name, email: user.email })
  const [pw, setPw] = useState({ current: '', next: '', again: '' }); const [pwErr, setPwErr] = useState({})
  const [prefs, setPrefs] = useState(null); const [msg, setMsg] = useState(''); const [del, setDel] = useState(false); const [delPw, setDelPw] = useState('')
  const fileRef = useRef(null)
  useEffect(() => { api.get('/api/users/settings').then(setPrefs).catch(() => {}) }, [])
  const wrap = (fn, ok) => async (e) => { e?.preventDefault(); setMsg(''); try { await fn(); ok && toast(ok, 'ok') } catch (ex) { setMsg(ex.message) } }

  return (
    <div className="stack" style={{ maxWidth: 820 }}>
      <h1>My profile</h1><Alert>{msg}</Alert>
      <form className="panel" onSubmit={wrap(async () => setUser(await api.put('/api/users/profile', f)), 'Profile updated')}>
        <h2>Personal information</h2>
        <div className="row" style={{ marginBottom: '1rem' }}>
          {user.profile_image ? <img className="avatar" style={{ width: 64, height: 64 }} src={user.profile_image} alt="Your profile" /> : <span className="avatar" style={{ width: 64, height: 64, fontSize: '1.3rem' }}>{user.first_name[0]}{user.last_name[0]}</span>}
          <input ref={fileRef} type="file" accept="image/png,image/jpeg" hidden onChange={wrap(async () => setUser(await api.upload('/api/users/profile-image', fileRef.current.files[0])), 'Profile picture updated')} />
          <Button type="button" variant="secondary" small onClick={() => fileRef.current.click()}>Upload picture</Button><span className="hint">PNG or JPEG, up to 2 MB</span>
        </div>
        <div className="grid g2"><Field label="First name" value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} /><Field label="Last name" value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} /></div>
        <Field label="Email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <Button type="submit">Save changes</Button>
      </form>

      <form className="panel" onSubmit={wrap(async () => {
        const v = {}; const e = pwError(pw.next); if (e) v.next = e; if (pw.next !== pw.again) v.again = 'Passwords do not match'
        setPwErr(v); if (Object.keys(v).length) return
        await api.put('/api/users/password', { current_password: pw.current, new_password: pw.next }); setPw({ current: '', next: '', again: '' })
      }, 'Password changed')}>
        <h2>Change password</h2>
        <Field label="Current password" type="password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} autoComplete="current-password" />
        <Field label="New password" type="password" value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} error={pwErr.next} autoComplete="new-password" />
        <Field label="Confirm new password" type="password" value={pw.again} onChange={(e) => setPw({ ...pw, again: e.target.value })} error={pwErr.again} autoComplete="new-password" />
        <Button type="submit">Change password</Button>
      </form>

      {prefs && <form className="panel" onSubmit={wrap(async () => setPrefs(await api.put('/api/users/settings', prefs)), 'Preferences saved')}>
        <h2>Preferences</h2>
        <div className="grid g2">
          <Field label="Theme" id="pref-theme"><select id="pref-theme" value={prefs.theme} onChange={(e) => { setPrefs({ ...prefs, theme: e.target.value }); document.documentElement.dataset.theme = e.target.value.toLowerCase(); localStorage.setItem('fn_theme', e.target.value.toLowerCase()) }}><option>Light</option><option>Dark</option></select></Field>
          <Field label="Interface language" id="pref-lang"><select id="pref-lang" value={prefs.language} onChange={(e) => setPrefs({ ...prefs, language: e.target.value })}><option value="en">English</option><option value="tr">Turkish</option><option value="ar">Arabic</option></select></Field>
          <Field label="Default export format (used in your history)" id="pref-exp"><select id="pref-exp" value={prefs.default_export_format} onChange={(e) => setPrefs({ ...prefs, default_export_format: e.target.value })}><option>PDF</option><option>CSV</option></select></Field>
          <Field label="Email notifications" id="pref-mail"><label className="row"><input id="pref-mail" type="checkbox" checked={prefs.email_notification} onChange={(e) => setPrefs({ ...prefs, email_notification: e.target.checked })} /> Send me updates by email</label></Field>
        </div>
        <p className="hint">Language and notification choices are saved, but the interface is currently English only and no emails are sent yet.</p>
        <Button type="submit">Save preferences</Button>
      </form>}

      <div className="panel"><h2>Delete account</h2><p className="muted">This permanently removes your account and your prediction history.</p>
        <Button variant="danger" onClick={() => setDel(true)}>Delete my account</Button></div>
      {del && <Modal title="Delete your account?" onClose={() => setDel(false)}>
        <p>Enter your password to confirm. This cannot be undone.</p>
        <Field label="Password" type="password" value={delPw} onChange={(e) => setDelPw(e.target.value)} autoComplete="current-password" />
        <div className="row" style={{ justifyContent: 'flex-end' }}><Button variant="secondary" onClick={() => setDel(false)}>Cancel</Button>
          <Button variant="danger" onClick={wrap(async () => { await api.del('/api/users/profile', { password: delPw }); await logout(); nav('/login') })}>Delete account</Button></div></Modal>}
    </div>
  )
}
