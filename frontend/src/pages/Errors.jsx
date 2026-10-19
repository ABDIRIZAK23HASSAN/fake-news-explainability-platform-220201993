// Plain <a>: the error boundary renders OUTSIDE the router, so <Link> would crash it.
const Page = ({ code, title, children }) => (
  <div className="auth-wrap"><div className="panel auth-card" style={{ textAlign: 'center' }}>
    <div className="muted">{code}</div><h1>{title}</h1><p className="muted">{children}</p>
    <a className="btn" href="/">Back to the start page</a>
  </div></div>
)
export const NotFound = () => <Page code="Error 404" title="This page does not exist">The address may be mistyped, or the page was moved.</Page>
export const Forbidden = () => <Page code="Error 403" title="Administrators only">Your account does not have access to this area.</Page>
export const ServerError = ({ error }) => (
  <Page code="Error 500" title="Something went wrong">The application hit an unexpected error{error?.message ? ` (${error.message})` : ''}. Reload the page; if it keeps happening, tell the administrator.</Page>
)
