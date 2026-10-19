import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../../api'
import { useAuth } from '../../auth'
import { Alert, Button, Field } from '../../ui'

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const pwError = (p) => (p.length < 8 ? 'Password is too short (minimum 8 characters)'
  : !/\d/.test(p) || !/[A-Za-z]/.test(p) ? 'Password must contain both letters and numbers' : '')

function Card({ title, subtitle, children, footer }) {
  return (
    <div className="auth-wrap"><div className="panel auth-card">
      <h1>{title}</h1>{subtitle && <p className="muted">{subtitle}</p>}
      {children}<div className="small muted" style={{ marginTop: '1rem' }}>{footer}</div>
    </div></div>
  )
}

export function Login() {
  const { login, sessionMsg } = useAuth()
  const nav = useNavigate()
  const [f, setF] = useState({ email: '', password: '' })
  const [err, setErr] = useState({}); const [msg, setMsg] = useState(''); const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault(); setMsg('')
    const v = {}
    if (!EMAIL_RE.test(f.email)) v.email = 'Invalid email format'
    if (!f.password) v.password = 'Enter your password'
    setErr(v); if (Object.keys(v).length) return
    setBusy(true)
    try { const u = await login(f.email.trim(), f.password); nav(u.role === 'Administrator' ? '/admin' : '/dashboard') }
    catch (ex) { setMsg(ex.message) } finally { setBusy(false) }
  }
  return (
    <Card title="Log in" subtitle="Check whether a news article is likely fake or real, and see why."
      footer={<>New here? <Link to="/register">Create an account</Link></>}>
      <Alert kind="warn">{sessionMsg}</Alert><Alert>{msg}</Alert>
      <form onSubmit={submit} noValidate>
        <Field label="Email" type="email" autoComplete="username" value={f.email} onChange={set('email')} error={err.email} />
        <Field label="Password" type="password" autoComplete="current-password" value={f.password} onChange={set('password')} error={err.password} />
        <div className="row between"><Button type="submit" loading={busy}>Log in</Button><Link to="/forgot-password" className="small">Forgot your password?</Link></div>
      </form>
    </Card>
  )
}

export function Register() {
  const { register } = useAuth(); const nav = useNavigate()
  const [f, setF] = useState({ first_name: '', last_name: '', email: '', password: '', confirm: '' })
  const [err, setErr] = useState({}); const [msg, setMsg] = useState(''); const [busy, setBusy] = useState(false)
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value })
  const submit = async (e) => {
    e.preventDefault(); setMsg('')
    const v = {}
    if (!f.first_name.trim()) v.first_name = 'Enter your first name'
    if (!f.last_name.trim()) v.last_name = 'Enter your last name'
    if (!EMAIL_RE.test(f.email)) v.email = 'Invalid email format'
    const pe = pwError(f.password); if (pe) v.password = pe
    if (f.password !== f.confirm) v.confirm = 'Passwords do not match'
    setErr(v); if (Object.keys(v).length) return
    setBusy(true)
    try { await register({ first_name: f.first_name.trim(), last_name: f.last_name.trim(), email: f.email.trim(), password: f.password }); nav('/dashboard') }
    catch (ex) { setMsg(ex.message) } finally { setBusy(false) }
  }
  return (
    <Card title="Create an account" footer={<>Already registered? <Link to="/login">Log in</Link></>}>
      <Alert>{msg}</Alert>
      <form onSubmit={submit} noValidate>
        <div className="grid g2">
          <Field label="First name" value={f.first_name} onChange={set('first_name')} error={err.first_name} autoComplete="given-name" />
          <Field label="Last name" value={f.last_name} onChange={set('last_name')} error={err.last_name} autoComplete="family-name" />
        </div>
        <Field label="Email" type="email" value={f.email} onChange={set('email')} error={err.email} autoComplete="email" />
        <Field label="Password" type="password" value={f.password} onChange={set('password')} error={err.password} hint="At least 8 characters, with letters and numbers" autoComplete="new-password" />
        <Field label="Confirm password" type="password" value={f.confirm} onChange={set('confirm')} error={err.confirm} autoComplete="new-password" />
        <Button type="submit" loading={busy}>Create account</Button>
      </form>
    </Card>
  )
}

export function ForgotPassword() {
  const [email, setEmail] = useState(''); const [err, setErr] = useState(''); const [res, setRes] = useState(null); const [busy, setBusy] = useState(false)
  const submit = async (e) => {
    e.preventDefault(); setErr('')
    if (!EMAIL_RE.test(email)) return setErr('Invalid email format')
    setBusy(true)
    try { setRes(await api.post('/api/auth/forgot-password', { email: email.trim() })) } catch (ex) { setErr(ex.message) } finally { setBusy(false) }
  }
  return (
    <Card title="Reset your password" subtitle="Enter your account email and we will send a reset link." footer={<Link to="/login">Back to log in</Link>}>
      {res ? <>
        <Alert kind="ok">{res.message}</Alert>
        {res.dev_reset_token && <p className="small">Demo mode: <Link to={`/reset-password?token=${res.dev_reset_token}`}>open the reset page</Link></p>}
      </> : <form onSubmit={submit} noValidate>
        <Field label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} error={err} />
        <Button type="submit" loading={busy}>Send reset link</Button>
      </form>}
    </Card>
  )
}

export function ResetPassword() {
  const [q] = useSearchParams(); const nav = useNavigate()
  const [pw, setPw] = useState(''); const [pw2, setPw2] = useState(''); const [err, setErr] = useState({}); const [msg, setMsg] = useState(''); const [done, setDone] = useState(false); const [busy, setBusy] = useState(false)
  const token = q.get('token') || ''
  const submit = async (e) => {
    e.preventDefault(); setMsg('')
    const v = {}; const pe = pwError(pw); if (pe) v.pw = pe; if (pw !== pw2) v.pw2 = 'Passwords do not match'
    setErr(v); if (Object.keys(v).length) return
    setBusy(true)
    try { await api.post('/api/auth/reset-password', { token, new_password: pw }); setDone(true); setTimeout(() => nav('/login'), 1800) }
    catch (ex) { setMsg(ex.message) } finally { setBusy(false) }
  }
  return (
    <Card title="Choose a new password" footer={<Link to="/login">Back to log in</Link>}>
      {!token && <Alert>This link is missing its reset token. Request a new link.</Alert>}
      {done ? <Alert kind="ok">Password has been reset. Redirecting to log in...</Alert> : <form onSubmit={submit} noValidate>
        <Alert>{msg}</Alert>
        <Field label="New password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} error={err.pw} autoComplete="new-password" />
        <Field label="Confirm new password" type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} error={err.pw2} autoComplete="new-password" />
        <Button type="submit" loading={busy} disabled={!token}>Reset password</Button>
      </form>}
    </Card>
  )
}
