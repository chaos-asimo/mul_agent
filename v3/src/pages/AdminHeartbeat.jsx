import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Heart, CheckCircle, AlertCircle, Play, Pause, Save, Activity } from 'lucide-react'
import { apiGet, apiPut } from '../api/client'
import ThemeSwitcher from '../components/ThemeSwitcher'

function AdminHeartbeat() {
  const [config, setConfig] = useState({
    backend_heartbeat_enabled: false,
    backend_heartbeat_url: '',
    backend_heartbeat_interval: 60,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState(null)   // { ok, latency, msg }
  const [error, setError] = useState('')
  const [savedMsg, setSavedMsg] = useState('')

  const load = useCallback(async () => {
    setLoading(true); setError(''); setSavedMsg('')
    try {
      const raw = await apiGet('/admin/config')
      const cfg = raw.data || raw || {}
      setConfig({
        backend_heartbeat_enabled: String(cfg.backend_heartbeat_enabled ?? 'false').toLowerCase() === 'true',
        backend_heartbeat_url: String(cfg.backend_heartbeat_url ?? ''),
        backend_heartbeat_interval: Number(cfg.backend_heartbeat_interval ?? 60),
      })
    } catch (e) {
      setError(e.message || '加载配置失败')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const save = async () => {
    setSaving(true); setError(''); setSavedMsg('')
    try {
      // 三个配置项分别 PUT
      const ops = [
        apiPut('/admin/config/backend_heartbeat_enabled', { value: String(config.backend_heartbeat_enabled) }),
        apiPut('/admin/config/backend_heartbeat_url', { value: config.backend_heartbeat_url }),
        apiPut('/admin/config/backend_heartbeat_interval', { value: String(Math.max(10, Number(config.backend_heartbeat_interval) || 60)) }),
      ]
      await Promise.all(ops)
      setSavedMsg('已保存，重启服务后生效')
    } catch (e) {
      setError(e.message || '保存失败')
    } finally { setSaving(false) }
  }

  const test = async () => {
    if (!config.backend_heartbeat_url) { setError('请先填写心跳 URL'); return }
    setTesting(true); setError(''); setTestResult(null)
    try {
      const t0 = performance.now()
      // 用后端的 /health 端点做真实验证
      const resp = await fetch(config.backend_heartbeat_url, { method: 'GET', headers: { 'User-Agent': 'mul-agent-heartbeat-test/1.0' } })
      const t1 = performance.now()
      const body = await resp.text()
      let ok = false
      try { ok = !!JSON.parse(body)?.ok } catch {}
      setTestResult({ ok, latency: Math.round(t1 - t0), status: resp.status })
    } catch (e) {
      setTestResult({ ok: false, latency: null, error: e.message })
    } finally { setTesting(false) }
  }

  const toggleEnabled = () => setConfig(c => ({ ...c, backend_heartbeat_enabled: !c.backend_heartbeat_enabled }))
  const setUrl = (v) => setConfig(c => ({ ...c, backend_heartbeat_url: v }))
  const setInterval = (v) => setConfig(c => ({ ...c, backend_heartbeat_interval: Math.max(10, Number(v) || 60) }))

  return (
    <div className="min-h-screen t-bg-app t-text">
      <header className="flex items-center justify-between px-4 py-3 border-b t-border t-bg-panel">
        <div className="flex items-center gap-3">
          <Link to="/admin/users" className="p-2 rounded-lg t-hover-card" title="返回用户管理">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-base font-semibold flex items-center gap-2">
              反代链路心跳
              <Heart className="w-4 h-4 t-text-danger" />
            </h1>
            <p className="text-[11px] t-text-faint">
              周期性从后端发起请求到反代公网地址，让 keepalive 连接池持续活跃，消灭「空闲后首请求卡 30s」僵尸连接
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeSwitcher />
          <button onClick={load} disabled={loading} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card disabled:opacity-50">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button onClick={save} disabled={saving} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50">
            <Save className="w-3.5 h-3.5" />
            {saving ? '保存中...' : '保存并生效'}
          </button>
        </div>
      </header>

      <div className="max-w-2xl mx-auto p-4">
        {error && <div className="mb-3 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm flex items-center gap-2"><AlertCircle className="w-4 h-4" />{error}</div>}
        {savedMsg && <div className="mb-3 p-3 t-bg-accent-soft border t-border-accent rounded-lg text-sm flex items-center gap-2"><CheckCircle className="w-4 h-4 t-text-accent" />{savedMsg}</div>}

        {/* 开关 */}
        <div className="flex items-center justify-between p-4 t-bg-panel border t-border rounded-xl mb-4">
          <div className="flex items-center gap-3">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${config.backend_heartbeat_enabled ? 't-bg-accent text-white' : 't-bg-input t-text-muted'}`}>
              {config.backend_heartbeat_enabled ? <Activity className="w-5 h-5" /> : <Pause className="w-5 h-5" />}
            </div>
            <div>
              <div className="text-sm font-medium">心跳状态</div>
              <div className="text-[11px] t-text-faint">
                {config.backend_heartbeat_enabled ? '已开启：保持反代→后端连接活跃' : '未开启：反代空闲后可能丢状态'}
              </div>
            </div>
          </div>
          <button onClick={toggleEnabled}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${config.backend_heartbeat_enabled ? 't-bg-accent' : 'bg-gray-400'}`}>
            <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${config.backend_heartbeat_enabled ? 'translate-x-6' : 'translate-x-1'}`} />
          </button>
        </div>

        {/* URL */}
        <div className="p-4 t-bg-panel border t-border rounded-xl mb-4">
          <label className="block text-xs font-medium t-text-muted mb-2">心跳 URL（必填）</label>
          <input type="text" value={config.backend_heartbeat_url} onChange={e => setUrl(e.target.value)}
            placeholder="https://claw.jbysoft.com/api/lobster-mu/health"
            className="w-full px-3 py-2 text-sm border t-border-strong rounded-lg t-bg-input t-text outline-none focus:ring-2 focus:ring-blue-400" />
          <p className="text-[11px] t-text-faint mt-2 leading-relaxed">
            必须是<strong>经过反代的公网地址</strong>。后端每次向这个 URL 发 GET 请求，反代→后端的 keepalive 连接池因此持续有流量，中间设备不会丢弃状态。
            <br />端点写 <code className="t-bg-input px-1 rounded">/api/lobster-mu/health</code>（零开销，no-auth）。
          </p>
        </div>

        {/* 间隔 + 测试 */}
        <div className="p-4 t-bg-panel border t-border rounded-xl mb-4">
          <label className="block text-xs font-medium t-text-muted mb-2">发送间隔（秒，最小 10）</label>
          <input type="number" min={10} max={3600} value={config.backend_heartbeat_interval}
            onChange={e => setInterval(e.target.value)}
            className="w-28 px-3 py-2 text-sm border t-border-strong rounded-lg t-bg-input t-text outline-none focus:ring-2 focus:ring-blue-400" />
          <p className="text-[11px] t-text-faint mt-2">默认 60 秒。设为 <strong>小于中间设备空闲超时</strong>（通常 60~300s）即可保活。</p>

          <div className="mt-4 pt-4 border-t t-border flex items-center gap-3">
            <button onClick={test} disabled={testing || !config.backend_heartbeat_url}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card disabled:opacity-50">
              <Play className="w-3.5 h-3.5" />
              {testing ? '测试中...' : '立即测试'}
            </button>
            {testResult && (
              testResult.ok
                ? <span className="text-xs flex items-center gap-1.5 t-text-accent">
                    <CheckCircle className="w-3.5 h-3.5" /> 可达 · {testResult.status} · {testResult.latency}ms
                  </span>
                : <span className="text-xs flex items-center gap-1.5 t-text-danger">
                    <AlertCircle className="w-3.5 h-3.5" /> 失败 · {testResult.error || `HTTP ${testResult.status}`}
                  </span>
            )}
          </div>
        </div>

        {/* 工作原理 */}
        <details className="p-4 t-bg-panel border t-border rounded-xl mb-4 text-[12px] leading-relaxed">
          <summary className="cursor-pointer font-medium">工作原理（为何能消灭 30s 卡顿）</summary>
          <div className="mt-3 t-text-faint space-y-1.5">
            <p><strong>根因回顾</strong>：反代服务器与云中间设备（安全组/NAT/CDN）之间，空闲 TCP 连接状态会被静默丢弃（不发 FIN/RST）。浏览器回来复用这个"僵尸连接"→黑洞丢包 → TCP 指数退避重传 ≈ <strong>30 秒</strong>才新建连接成功。</p>
            <p><strong>心跳为什么管用</strong>：后端每 60s 一次主动发 GET → 反代用 keepalive 连接池转发 → <strong>反代→后端 的 TCP 链路永远不"空闲"</strong>，中间设备不会丢状态。浏览器回来时反代用同一条活跃连接响应，秒出。</p>
            <p><strong>为什么从后端发起</strong>：反代→后端 的连接池由 Nginx upstream keepalive 管理，浏览器→反代的连接用完就关。让前者保活，中间层状态一直是活的。</p>
            <p><strong>与 Nginx keepalive_timeout 的关系</strong>：两者互补。Nginx 的 keepalive_timeout 管的是浏览器→反代这一段，心跳管的是反代→后端这一段。中间设备如果在 Nginx 关之前就丢状态，心跳兜底。</p>
          </div>
        </details>
      </div>
    </div>
  )
}

export default AdminHeartbeat
