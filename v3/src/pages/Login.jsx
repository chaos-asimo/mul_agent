import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shell, Lock, User } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import ThemeSwitcher from '../components/ThemeSwitcher'

function Login() {
  const { login, user, loading } = useAuthStore()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 已登录用户直接进入工作台
  useEffect(() => {
    if (!loading && user) {
      navigate('/', { replace: true })
    }
  }, [user, loading, navigate])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)

    const result = await login(username, password)

    if (result.success) {
      navigate('/', { replace: true })
    } else {
      setError(result.message || '登录失败')
    }

    setSubmitting(false)
  }

  return (
    <div className="min-h-screen t-bg-login flex items-center justify-center p-4 relative">
      <div className="absolute top-4 right-4">
        <ThemeSwitcher />
      </div>
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl t-bg-accent mb-4 shadow-lg shadow-black/30">
            <Shell className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold t-text">龙虾Claw 多用户版</h1>
          <p className="t-text-faint mt-2">Multi-User Lobster Claw · v3</p>
        </div>

        {/* 登录表单 */}
        <div className="t-bg-panel border t-border rounded-2xl shadow-xl p-8 backdrop-blur">
          <h2 className="text-lg font-semibold t-text-2 mb-6 text-center">欢迎登录</h2>

          {error && (
            <div className="mb-4 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium t-text-2 mb-2">用户名</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 t-text-faint" />
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 t-bg-input border t-border-strong rounded-lg t-text t-placeholder t-focus transition-all"
                  placeholder="请输入用户名"
                  disabled={submitting}
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium t-text-2 mb-2">密码</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 t-text-faint" />
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-10 pr-4 py-3 t-bg-input border t-border-strong rounded-lg t-text t-placeholder t-focus transition-all"
                  placeholder="请输入密码"
                  disabled={submitting}
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={submitting || !username || !password}
              className="w-full py-3 t-bg-accent t-hover-accent text-white font-medium rounded-lg t-focus transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                  登录中...
                </span>
              ) : (
                '登录'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}

export default Login
