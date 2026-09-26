import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Shell, Lock, User, ShieldCheck, KeyRound, ArrowLeft } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import ThemeSwitcher from '../components/ThemeSwitcher'

function Login() {
  const { login, login2fa, user, loading } = useAuthStore()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 两步登录：TOTP 验证码步骤
  const [step, setStep] = useState('password')
  const [pendingUsername, setPendingUsername] = useState('')
  const [totp, setTotp] = useState('')

  // 已登录用户直接进入工作台
  useEffect(() => {
    if (!loading && user) {
      navigate('/', { replace: true })
    }
  }, [user, loading, navigate])

  // 阻止浏览器自动填充残留的上次凭据
  useEffect(() => {
    setUsername('')
    setPassword('')
    setTotp('')
  }, [])

  const handleSubmitPassword = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)

    const result = await login(username, password)

    if (result.success) {
      navigate('/', { replace: true })
    } else if (result.needs2fa) {
      setPendingUsername(result.username)
      setStep('totp')
    } else {
      setError(result.message || '登录失败')
    }

    setSubmitting(false)
  }

  const handleSubmitTotp = async (e) => {
    e.preventDefault()
    setError('')
    setSubmitting(true)

    const result = await login2fa(pendingUsername, totp)

    if (result.success) {
      navigate('/', { replace: true })
    } else {
      setError(result.message || '验证码错误')
    }

    setSubmitting(false)
  }

  const handleBackToPassword = () => {
    setStep('password')
    setTotp('')
    setPendingUsername('')
    setError('')
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
          <h1 className="text-2xl font-bold t-text">个人助理多用户版</h1>
          <p className="t-text-faint mt-2">Multi-User Lobster Claw · v3</p>
        </div>

        {/* 登录表单 */}
        <div className="t-bg-panel border t-border rounded-2xl shadow-xl p-8 backdrop-blur">
          {step === 'password' ? (
            <>
              <h2 className="text-lg font-semibold t-text-2 mb-6 text-center">欢迎登录</h2>

              {error && (
                <div className="mb-4 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmitPassword} className="space-y-4">
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
                      autoComplete="off"
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
                      autoComplete="new-password"
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
            </>
          ) : (
            <>
              <div className="flex items-center justify-center mb-6">
                <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl t-bg-accent-soft mb-3">
                  <ShieldCheck className="w-7 h-7 t-text-accent" />
                </div>
              </div>
              <h2 className="text-lg font-semibold t-text-2 mb-2 text-center">两步验证</h2>
              <p className="text-sm t-text-faint text-center mb-6">
                请输入 <span className="t-text-accent font-medium">{pendingUsername}</span> 的 Authenticator 验证码
              </p>

              {error && (
                <div className="mb-4 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">
                  {error}
                </div>
              )}

              <form onSubmit={handleSubmitTotp} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium t-text-2 mb-2">6 位验证码</label>
                  <div className="relative">
                    <KeyRound className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 t-text-faint" />
                    <input
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      maxLength={6}
                      value={totp}
                      onChange={(e) => setTotp(e.target.value.replace(/\D/g, ''))}
                      className="w-full pl-10 pr-4 py-3 t-bg-input border t-border-strong rounded-lg t-text t-placeholder t-focus transition-all tracking-[0.4em] text-center text-lg font-mono"
                      placeholder="000000"
                      autoComplete="one-time-code"
                      disabled={submitting}
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={submitting || totp.length !== 6}
                  className="w-full py-3 t-bg-accent t-hover-accent text-white font-medium rounded-lg t-focus transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {submitting ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
                      验证中...
                    </span>
                  ) : (
                    '验证并登录'
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleBackToPassword}
                  disabled={submitting}
                  className="w-full py-2 text-sm t-text-faint t-hover-text flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                >
                  <ArrowLeft className="w-4 h-4" />
                  返回重新输入密码
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default Login
