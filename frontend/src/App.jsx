import { Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth'
import { Shell } from './layout'
import { Loading } from './ui'
import { Forbidden, NotFound } from './pages/Errors'
import { ForgotPassword, Login, Register, ResetPassword } from './pages/auth/AuthPages'
import Dashboard from './pages/user/Dashboard'
import Analyze from './pages/user/Analyze'
import { ResultLayout, ResultOverview, ResultExplain, ResultSimilar, ResultKeywords } from './pages/user/Result'
import ArticleView from './pages/user/ArticleView'
import History from './pages/user/History'
import Profile from './pages/user/Profile'
import AdminDashboard from './pages/admin/AdminDashboard'
import AdminUsers from './pages/admin/Users'
import AdminDatasets from './pages/admin/Datasets'
import AdminNews from './pages/admin/News'
import AdminModels from './pages/admin/Models'
import AdminAnalytics from './pages/admin/Analytics'
import AdminExplain from './pages/admin/Explainability'
import AdminSettings from './pages/admin/Settings'
import AdminLogs from './pages/admin/Logs'

const home = (u) => (u.role === 'Administrator' ? '/admin' : '/dashboard')

// The two interfaces are separate: each guard sends the wrong role to its own area.
function Guard({ role }) {
  const { user, loading } = useAuth()
  if (loading) return <Loading text="Checking your session..." />
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== role) return role === 'Administrator' ? <Forbidden /> : <Navigate to={home(user)} replace />
  return <Shell admin={role === 'Administrator'} />
}

function Public() {
  const { user, loading } = useAuth()
  if (loading) return <Loading />
  return user ? <Navigate to={home(user)} replace /> : <Outlet />
}

function Root() {
  const { user, loading } = useAuth()
  if (loading) return <Loading />
  return <Navigate to={user ? home(user) : '/login'} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Root />} />
      <Route element={<Public />}>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="/forgot-password" element={<ForgotPassword />} />
        <Route path="/reset-password" element={<ResetPassword />} />
      </Route>

      <Route element={<Guard role="User" />}>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/analyze" element={<Analyze />} />
        <Route path="/results/:id" element={<ResultLayout />}>
          <Route index element={<ResultOverview />} />
          <Route path="explain" element={<ResultExplain />} />
          <Route path="similar" element={<ResultSimilar />} />
          <Route path="keywords" element={<ResultKeywords />} />
        </Route>
        <Route path="/articles/:newsId" element={<ArticleView />} />
        <Route path="/history" element={<History />} />
        <Route path="/profile" element={<Profile />} />
      </Route>

      <Route element={<Guard role="Administrator" />}>
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/admin/users" element={<AdminUsers />} />
        <Route path="/admin/datasets" element={<AdminDatasets />} />
        <Route path="/admin/news" element={<AdminNews />} />
        <Route path="/admin/models" element={<AdminModels />} />
        <Route path="/admin/analytics" element={<AdminAnalytics />} />
        <Route path="/admin/explainability" element={<AdminExplain />} />
        <Route path="/admin/settings" element={<AdminSettings />} />
        <Route path="/admin/logs" element={<AdminLogs />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
