import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useAuthStore } from './stores/authStore'
import { useThemeStore } from './stores/themeStore'
import Login from './pages/Login'
import Workbench from './pages/Workbench'
import AdminUsers from './pages/AdminUsers'

function MuProtectedRoute({ children, adminOnly = false }) {
  const { user, loading } = useAuthStore()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen t-bg-app t-text-muted loading-pulse">
        加载中...
      </div>
    )
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
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
