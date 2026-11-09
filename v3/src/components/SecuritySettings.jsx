import { useState, useEffect } from 'react'
import { X, ShieldCheck, KeyRound, Lock, QrCode, CheckCircle2 } from 'lucide-react'
import { apiGet, apiPost } from '../api/client'

/**
 * 微软 Authenticator（TOTP）两步认证 安全设置弹窗
 * 未启用：生成 QR → 输入 6 位码确认 → 启用
 * 已启用：输入密码解绑
 */
function SecuritySettings({ onClose }) {
  const [enabled, setEnabled] = useState(null) // null=加载中
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  // 绑定流程
  const [binding, setBinding] = useState(false)
  const [qr, setQr] = useState('')
  const [secret, setSecret] = useState('')
  const [bindCode, setBindCode] = useState('')
  const [submitting, setSubmitting] = useState(false)

  // 解绑流程
  const [password, setPassword] = useState('')

  useEffect(() => {
    apiGet('/totp/status')
      .then((res) => setEnabled(!!res.enabled))
      .catch((e) => setError(e.message || '加载状态失败'))
      .finally(() => setLoading(false))
  }, [])

  const handleSetup = async () => {
    setError('')
    setNotice('')
    setSubmitting(true)
    try {
      const res = await apiPost('/totp/setup', {})
      setQr(res.qr || '')
      setSecret(res.secret || '')
      setBinding(true)
    } catch (e) {
      setError(e.message || '生成失败')
    } finally {
      setSubmitting(false)
    }
  }

  const handleConfirm = async () => {
    setError('')
    setSubmitting(true)
    try {
      const res = await apiPost('/totp/confirm', { totp: bindCode.trim() })
      setEnabled(true)
      setBinding(false)
      setBindCode('')
      setQr('')
      setSecret('')
      setNotice(res.message || '已启用微软 Authenticator')
    } catch (e) {
      setError(e.message || '验证码错误')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDisable = async () => {
    setError('')
    if (!password) return
    setSubmitting(true)
    try {
      const res = await apiPost('/totp/disable', { password })
      setEnabled(false)
      setPassword('')
      setNotice(res.message || '已关闭微软 Authenticator')
    } catch (e) {
      setError(e.message || '密码错误')
    } finally {
      setSubmitting(false)
    }
  }

  const cancelBinding = () => {
    setBinding(false)
    setBindCode('')
    setQr('')
    setSecret('')
    setError('')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative t-bg-panel border t-border rounded-2xl shadow-xl w-full max-w-md">
        {/* 头部 */}
        <div className="flex items-center justify-between p-5 border-b t-border">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-lg t-bg-accent-soft flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 t-text-accent" />
            </div>
            <div>
              <h2 className="text-sm font-semibold t-text">安全设置</h2>
              <p className="text-[11px] t-text-faint">微软 Authenticator 两步认证</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg t-text-faint t-hover-text t-hover-bg transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5">
          {loading ? (
            <p className="text-sm t-text-faint text-center py-8 loading-pulse">加载中...</p>
          ) : (
            <>
              {error && (
                <div className="mb-4 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">
                  {error}
                </div>
              )}
              {notice && (
                <div className="mb-4 p-3 t-bg-accent-soft border t-border-accent rounded-lg t-text-accent text-sm flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  {notice}
                </div>
              )}

              {/* 未启用 */}
              {!enabled && !binding && (
                <div className="space-y-4">
                  <div className="p-4 t-bg-input border t-border-strong rounded-lg">
                    <p className="text-sm t-text-2 leading-relaxed">
                      启用后，每次登录需要在密码之后额外输入 Authenticator 应用的 6 位验证码，提升账号安全性。
                    </p>
                  </div>
                  <div className="text-xs t-text-faint space-y-1.5">
                    <p>操作步骤：</p>
                    <ol className="list-decimal list-inside space-y-1">
                      <li>打开 微软 Authenticator（或其他 TOTP 应用）</li>
                      <li>扫码或手动输入密钥添加账号</li>
                      <li>输入应用生成的 6 位验证码完成绑定</li>
                    </ol>
                  </div>
                  <button
                    onClick={handleSetup}
                    disabled={submitting}
                    className="w-full py-3 t-bg-accent t-hover-accent text-white font-medium rounded-lg t-focus transition-all disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2"
                  >
                    <QrCode className="w-4 h-4" />
                    开始绑定
                  </button>
                </div>
              )}

              {/* 绑定中：QR + 验证码 */}
              {!enabled && binding && (
                <div className="space-y-4">
                  {qr && (
                    <div className="flex justify-center">
                      <img
                        src={qr}
                        alt="TOTP 二维码"
                        className="w-52 h-52 rounded-lg border t-border-strong p-2"
                      />
                    </div>
                  )}
                  {secret && (
                    <div className="p-3 t-bg-input border t-border-strong rounded-lg">
                      <p className="text-xs t-text-faint mb-1">无法扫码？手动输入密钥：</p>
                      <p className="text-sm font-mono t-text break-all leading-relaxed">{secret}</p>
                    </div>
                  )}
                  <div>
                    <label className="block text-sm font-medium t-text-2 mb-2">6 位验证码</label>
                    <div className="relative">
                      <KeyRound className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 t-text-faint" />
                      <input
                        type="text"
                        inputMode="numeric"
                        pattern="[0-9]*"
                        maxLength={6}
                        value={bindCode}
                        onChange={(e) => setBindCode(e.target.value.replace(/\D/g, ''))}
                        className="w-full pl-10 pr-4 py-3 t-bg-input border t-border-strong rounded-lg t-text t-placeholder t-focus transition-all tracking-[0.4em] text-center text-lg font-mono"
                        placeholder="000000"
                        autoComplete="one-time-code"
                        disabled={submitting}
                      />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={cancelBinding}
                      disabled={submitting}
                      className="flex-1 py-2.5 text-sm rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors disabled:opacity-50"
                    >
                      取消
                    </button>
                    <button
                      onClick={handleConfirm}
                      disabled={submitting || bindCode.length !== 6}
                      className="flex-1 py-2.5 t-bg-accent t-hover-accent text-white text-sm font-medium rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {submitting ? '验证中...' : '确认绑定'}
                    </button>
                  </div>
                </div>
              )}

              {/* 已启用 */}
              {enabled && (
                <div className="space-y-4">
                  <div className="p-4 t-bg-accent-soft border t-border-accent rounded-lg flex items-center gap-3">
                    <CheckCircle2 className="w-5 h-5 t-text-accent shrink-0" />
                    <div>
                      <p className="text-sm font-medium t-text-accent">已启用两步认证</p>
                      <p className="text-xs t-text-faint mt-0.5">登录时需要输入 Authenticator 验证码</p>
                    </div>
                  </div>

                  <div className="border-t t-border pt-4">
                    <p className="text-sm font-medium t-text-2 mb-1.5">解绑两步认证</p>
                    <p className="text-xs t-text-faint mb-3">
                      解绑后登录将不再需要验证码。请输入密码确认。
                    </p>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 t-text-faint" />
                      <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="w-full pl-10 pr-4 py-3 t-bg-input border t-border-strong rounded-lg t-text t-placeholder t-focus transition-all"
                        placeholder="请输入密码"
                        autoComplete="current-password"
                        disabled={submitting}
                      />
                    </div>
                    <button
                      onClick={handleDisable}
                      disabled={submitting || !password}
                      className="mt-3 w-full py-3 t-bg-danger-soft border t-border-danger t-text-danger font-medium rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {submitting ? '处理中...' : '解绑两步认证'}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default SecuritySettings
