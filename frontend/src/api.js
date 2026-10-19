// Thin fetch wrapper: JWT header, uniform errors, blob downloads.
const TOKEN_KEY = 'fn_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (t) => (t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY))

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status }
}

let onUnauthorized = () => {}
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn }

async function request(path, { method = 'GET', body, form, params, raw } = {}) {
  const url = new URL(path, window.location.origin)
  if (params) Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && url.searchParams.set(k, v))
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let payload
  if (form) payload = form
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body) }
  let res
  try {
    res = await fetch(url, { method, headers, body: payload })
  } catch {
    throw new ApiError('Server connection error. Check your connection and that the backend is running.', 0)
  }
  if (res.status === 401 && token && !path.startsWith('/api/auth/login')) onUnauthorized()
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try { const j = await res.json(); if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not JSON */ }
    throw new ApiError(msg, res.status)
  }
  return raw ? res : res.json()
}

export const api = {
  get: (p, params) => request(p, { params }),
  post: (p, body, params) => request(p, { method: 'POST', body, params }),
  put: (p, body) => request(p, { method: 'PUT', body }),
  del: (p, body) => request(p, { method: 'DELETE', body }),
  upload: (p, file, params) => { const f = new FormData(); f.append('file', file); return request(p, { method: 'POST', form: f, params }) },
}

// Authenticated download (exports) - an <a href> cannot send the Authorization header.
export async function download(path, params, fallbackName = 'download') {
  const res = await request(path, { params, raw: true })
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const name = /filename="?([^";]+)"?/.exec(cd)?.[1] || fallbackName
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
