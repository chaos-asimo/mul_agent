import { useState, useEffect, useCallback, Fragment } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Route, Search, ChevronDown, ChevronRight } from 'lucide-react'
import { apiGet } from '../api/client'
import ThemeSwitcher from '../components/ThemeSwitcher'

const ROLE_LABEL = {
  user: '用户',
  assistant: '模型',
  tool: '工具',
}

function fmtTime(v) {
  if (!v) return ''
  // 兼容秒级时间戳与字符串两种存储
  const n = Number(v)
  if (!Number.isNaN(n) && n > 1000000) {
    const d = new Date(n * 1000)
    return d.toLocaleString('zh-CN', { hour12: false })
  }
  return String(v)
}

function AdminTraces() {
  const [traces, setTraces] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sessionId, setSessionId] = useState('')
  const [limit, setLimit] = useState(100)
  const [expanded, setExpanded] = useState({})

  const load = useCallback(async (sid = sessionId, lim = limit) => {
    setLoading(true)
    setError('')
    try {
      const qs = new URLSearchParams()
      if (sid.trim()) qs.set('session_id', sid.trim())
      qs.set('limit', String(lim))
      const result = await apiGet(`/admin/agent-traces?${qs.toString()}`)
      if (result.success === false) {
        setError(result.error || '查询失败')
        setTraces([])
      } else {
        setTraces(result.traces || [])
      }
    } catch (e) {
      setError(e.message || '查询失败')
      setTraces([])
    } finally {
      setLoading(false)
    }
  }, [sessionId, limit])

  useEffect(() => { load() }, [load])

  const toggle = (id) => setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))

  return (
    <div className="min-h-screen t-bg-app t-text">
      <header className="flex items-center justify-between px-4 py-3 border-b t-border t-bg-panel">
        <div className="flex items-center gap-3">
          <Link to="/admin/users" className="p-2 rounded-lg t-hover-card" title="返回用户管理">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-base font-semibold">Agent 执行轨迹</h1>
            <p className="text-[11px] t-text-faint">
              记录 ReAct 每一步的模型输出与工具调用（表 mu_agent_traces），仅管理员可见
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeSwitcher />
          <button
            onClick={() => load()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto p-4">
        {error && (
          <div className="mb-3 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">
            {error}
          </div>
        )}

        {/* 查询条件 */}
        <div className="flex flex-wrap items-center gap-2 mb-3">
          <div className="flex items-center gap-2 flex-1 min-w-[240px]">
            <input
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') load() }}
              placeholder="按会话 ID 过滤（留空查看全部）"
              className="flex-1 px-3 py-1.5 text-xs rounded-lg border t-border t-bg-panel t-text"
            />
            <select
              value={limit}
              onChange={(e) => { const v = Number(e.target.value); setLimit(v); load(sessionId, v) }}
              className="px-2 py-1.5 text-xs rounded-lg border t-border t-bg-panel t-text"
            >
              {[50, 100, 200, 500].map((n) => (
                <option key={n} value={n}>最近 {n} 条</option>
              ))}
            </select>
          </div>
          <button
            onClick={() => load()}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50"
          >
            <Search className="w-3.5 h-3.5" />
            查询
          </button>
        </div>

        {/* 轨迹表 */}
        <div className="border t-border rounded-xl overflow-hidden">
          <table className="w-full text-xs table-fixed">
            <thead>
              <tr className="t-bg-panel t-text-muted">
                <th className="text-left px-2 py-2 font-medium w-32">时间</th>
                <th className="text-left px-2 py-2 font-medium w-16">用户</th>
                <th className="text-left px-2 py-2 font-medium w-24">会话</th>
                <th className="text-left px-2 py-2 font-medium w-14">步</th>
                <th className="text-left px-2 py-2 font-medium w-20">角色</th>
                <th className="text-left px-2 py-2 font-medium w-32">工具</th>
                <th className="text-left px-2 py-2 font-medium w-16">状态</th>
                <th className="text-left px-2 py-2 font-medium">内容</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {traces.map((t) => {
                const content = t.content || ''
                const open = !!expanded[t.id]
                const long = content.length > 160
                return (
                  <Fragment key={t.id}>
                    <tr className="align-top">
                      <td className="px-2 py-2 t-text-muted whitespace-nowrap">{fmtTime(t.created_at)}</td>
                      <td className="px-2 py-2 t-text-muted">{t.user_id}</td>
                      <td className="px-2 py-2 t-text-muted break-all" title={t.session_id}>
                        {(t.session_id || '').slice(0, 8)}
                      </td>
                      <td className="px-2 py-2 t-text-muted">{t.step}</td>
                      <td className="px-2 py-2">
                        <span className={`px-1.5 py-0.5 rounded ${
                          t.role === 'tool' ? 't-bg-accent text-white'
                            : t.role === 'assistant' ? 't-border-strong border' : 't-text-muted'
                        }`}>
                          {ROLE_LABEL[t.role] || t.role}
                        </span>
                      </td>
                      <td className="px-2 py-2 t-text-2 break-all">{t.tool_name || '-'}</td>
                      <td className="px-2 py-2">
                        {t.status === 'fail'
                          ? <span className="t-text-danger">失败</span>
                          : <span className="t-text-muted">{t.status || '-'}</span>}
                      </td>
                      <td className="px-2 py-2 t-text-2">
                        <div className="whitespace-pre-wrap break-words">
                          {open || !long ? content : content.slice(0, 160) + '…'}
                        </div>
                        {t.arguments && (
                          <div className="mt-1 t-text-faint break-all">
                            参数：{open ? t.arguments : String(t.arguments).slice(0, 120)}
                          </div>
                        )}
                        {long && (
                          <button
                            onClick={() => toggle(t.id)}
                            className="inline-flex items-center gap-1 mt-1 t-text-accent"
                          >
                            {open ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                            {open ? '收起' : '展开'}
                          </button>
                        )}
                      </td>
                    </tr>
                  </Fragment>
                )
              })}
              {traces.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-3 py-8 text-center t-text-faint">
                    {loading ? '加载中...' : '暂无轨迹记录（需开启 ReAct 编排并产生工具调用）'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center gap-2 mt-2 text-[11px] t-text-faint">
          <Route className="w-3.5 h-3.5" />
          共 {traces.length} 条，按时间倒序
        </div>
      </div>
    </div>
  )
}

export default AdminTraces
