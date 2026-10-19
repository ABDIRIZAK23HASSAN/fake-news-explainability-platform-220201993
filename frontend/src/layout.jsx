import { createContext, useContext, useEffect, useState } from 'react'
import { NavLink, Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from './auth'
import { api } from './api'
import { Breadcrumbs, Button } from './ui'

/* ---------- theme (light / dark) ---------- */
export function initTheme() {
  const saved = localStorage.getItem('fn_theme')
  const theme = saved || (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
  document.documentElement.dataset.theme = theme
  if (!saved) {      // no personal choice yet: use the default the administrator configured
    fetch('/api/settings/public').then((r) => r.json()).then((j) => {
      if (!localStorage.getItem('fn_theme') && ['light', 'dark'].includes(j.default_theme)) document.documentElement.dataset.theme = j.default_theme
    }).catch(() => {})
  }
}
function useTheme() {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme || 'light')
  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    document.documentElement.dataset.theme = next
    localStorage.setItem('fn_theme', next); setTheme(next)
    api.put('/api/users/settings', { theme: next === 'dark' ? 'Dark' : 'Light' }).catch(() => {})
  }
  return [theme, toggle]
}

/* ---------- breadcrumb context: each page declares its trail ---------- */
const CrumbCtx = createContext(() => {})
export function usePage(crumbs) {
  const set = useContext(CrumbCtx)
  const key = JSON.stringify(crumbs)
  useEffect(() => { set(crumbs); document.title = `${crumbs.at(-1).label} - Fake News Explainability`; /* eslint-disable-next-line */ }, [key])
}

const USER_NAV = [
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/analyze', label: 'Analyze news' },
  { to: '/history', label: 'Prediction history' },
  { to: '/profile', label: 'My profile' },
]
const ADMIN_NAV = [
  { to: '/admin', label: 'Dashboard', end: true },
  { group: 'Data' },
  { to: '/admin/datasets', label: 'Datasets' },
  { to: '/admin/news', label: 'News articles' },
  { group: 'Machine learning' },
  { to: '/admin/models', label: 'Models' },
  { to: '/admin/analytics', label: 'Analytics' },
  { to: '/admin/explainability', label: 'Explainability' },
  { group: 'System' },
  { to: '/admin/users', label: 'Users' },
  { to: '/admin/settings', label: 'Settings' },
  { to: '/admin/logs', label: 'Logs and activity' },
]

export function Shell({ admin }) {
  const { user, logout } = useAuth()
  const [crumbs, setCrumbs] = useState([{ label: 'Home' }])
  const [open, setOpen] = useState(false)
  const [theme, toggleTheme] = useTheme()
  const nav = useNavigate()
  const loc = useLocation()
  useEffect(() => setOpen(false), [loc.pathname])
  const items = admin ? ADMIN_NAV : USER_NAV
  const initials = `${user.first_name[0] || ''}${user.last_name[0] || ''}`.toUpperCase()

  return (
    <CrumbCtx.Provider value={setCrumbs}>
      <div className={`shell ${admin ? 'admin' : ''}`}>
        <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Main navigation">
          <div className="brand">Fake News Explainability<small>{admin ? 'Administration' : 'Decision-support for news readers'}</small></div>
          <nav className="nav">
            {items.map((it, i) => it.group
              ? <div className="group" key={i}>{it.group}</div>
              : <NavLink key={it.to} to={it.to} end={it.end}>{it.label}</NavLink>)}
          </nav>
        </aside>
        <div className="main">
          <header className="topbar">
            <button className="btn secondary sm menu-btn" onClick={() => setOpen((o) => !o)} aria-label="Toggle menu" aria-expanded={open}>Menu</button>
            <Breadcrumbs items={crumbs} />
            <div className="grow" />
            <Button variant="ghost" small onClick={toggleTheme}>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</Button>
            {user.profile_image ? <img className="avatar who" src={user.profile_image} alt="" /> : <span className="avatar who" aria-hidden="true">{initials}</span>}
            <span className="small nowrap who">{user.first_name}</span>
            <Button variant="secondary" small onClick={async () => { await logout(); nav('/login') }}>Log out</Button>
          </header>
          <main className="content"><Outlet /></main>
        </div>
      </div>
    </CrumbCtx.Provider>
  )
}
