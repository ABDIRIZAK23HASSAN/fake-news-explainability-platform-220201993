import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, getToken, setToken, setUnauthorizedHandler } from './api'

const Ctx = createContext(null)
export const useAuth = () => useContext(Ctx)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(!!getToken())
  const [sessionMsg, setSessionMsg] = useState('')

  const logoutLocal = useCallback((msg = '') => { setToken(null); setUser(null); setSessionMsg(msg) }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => logoutLocal('Your session has ended. Please log in again.'))
    if (!getToken()) return
    api.get('/api/auth/me').then(setUser).catch(() => setToken(null)).finally(() => setLoading(false))
  }, [logoutLocal])

  const startSession = (res) => { setToken(res.access_token); setUser(res.user); setSessionMsg(''); return res.user }
  const value = {
    user, loading, sessionMsg, setUser,
    login: async (email, password) => startSession(await api.post('/api/auth/login', { email, password })),
    register: async (data) => startSession(await api.post('/api/auth/register', data)),
    logout: async () => { try { await api.post('/api/auth/logout') } catch { /* token may already be invalid */ } logoutLocal() },
  }
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
