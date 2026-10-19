import { Component, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './styles.css'
import App from './App'
import { AuthProvider } from './auth'
import { ConfirmProvider, ToastProvider } from './ui'
import { initTheme } from './layout'
import { ServerError } from './pages/Errors'

initTheme()

class Boundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  render() { return this.state.error ? <ServerError error={this.state.error} /> : this.props.children }
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Boundary>
      <BrowserRouter>
        <ToastProvider><ConfirmProvider><AuthProvider><App /></AuthProvider></ConfirmProvider></ToastProvider>
      </BrowserRouter>
    </Boundary>
  </StrictMode>,
)
