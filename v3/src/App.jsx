import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import { useThemeStore } from './stores/themeStore'
import Login from './pages/Login'
import Workbench from './pages/Workbench'
import AdminUsers from './pages/AdminUsers'
import AdminKnowledge from './pages/AdminKnowledge'
import AdminModelSpeed from './pages/AdminModelSpeed'

// direct 登录后处于“待二次验证”状态时：弹出本系统域的 2FA 窗口，验证通过后再放行
function TwoFactorGate() {
  const user = useAuthStore((s) => s.user)
  const checkAuth = useAuthStore((s) => s.checkAuth)

  useEffect(() => {
    if (!user) return
    const origin = window.location.origin
    const url = `${origin}/static/totp-login.html?username=${encodeURIComponent(user.username)}`
    const win = window.open(url, 'lobster_mu_2fa', 'width=440,height=600')
    if (!win) {
      // 弹窗被拦截：给出提示与手动打开链接
      return
    }
    const onMessage = (event) => {
      if (event.origin !== origin) return
      const data = event.data || {}
      if (data.source !== 'lobster_mu_2fa') return
      if (data.type === '2fa_success') {
        window.removeEventListener('message', onMessage)
        checkAuth() // 会话已解锁，重新拉取登录态
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [user, checkAuth])

  return (
    <div className="flex flex-col items-center justify-center min-h-screen t-bg-app t-text gap-4 p-6">
      <div className="text-lg font-semibold">请完成二次验证</div>
      <p className="t-text-muted text-sm text-center max-w-md">
        已为你弹出微软 Authenticator 验证窗口，请在该窗口输入 6 位动态码。
        若未弹出，请
        <a
          className="t-text-accent underline ml-1"
          href={`${window.location.origin}/static/totp-login.html?username=${encodeURIComponent(user?.username || '')}`}
          target="_blank"
          rel="noreferrer"
        >
          点此手动打开
        </a>
        。
      </p>
    </div>
  )
}

function MuProtectedRoute({ children, adminOnly = false }) {
  const { user, loading, needs2fa } = useAuthStore()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen t-bg-app t-text-muted loading-pulse">
        加载中...
      </div>
    )
  }

  if (needs2fa) {
    return <TwoFactorGate />
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (adminOnly && user.role !== 'admin') {
    return <Navigate to="/" replace />
  }

  return children
}

function App() {
  const checkAuth = useAuthStore((s) => s.checkAuth)
  const initTheme = useThemeStore((s) => s.initTheme)

  useEffect(() => {
    initTheme()
    checkAuth()
  }, [checkAuth, initTheme])

  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <MuProtectedRoute>
            <Workbench />
          </MuProtectedRoute>
        }
      />
      <Route
        path="/admin/users"
        element={
          <MuProtectedRoute adminOnly>
            <AdminUsers />
          </MuProtectedRoute>
        }
      />
      <Route
        path="/admin/knowledge"
        element={
          <MuProtectedRoute adminOnly>
            <AdminKnowledge />
          </MuProtectedRoute>
        }
      />
      <Route
        path="/admin/model-speed"
        element={
          <MuProtectedRoute adminOnly>
            <AdminModelSpeed />
          </MuProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
