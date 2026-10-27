import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Settings, Bot, Plus, Trash2, Save } from 'lucide-react'
import { apiGet, apiPut, apiDelete } from '../api/client'
import ThemeSwitcher from '../components/ThemeSwitcher'

// 常用开关的友好呈现（不在此列表的配置项仍会在下方全量表格中列出）
const KNOWN = [
  {
    key: 'agent_react_enabled',
    label: '启用 ReAct 编排',
    type: 'bool',
    desc: '开启后走 function calling 工具调用链路，并触发 HITL 人工确认；关闭时回落到原有标记解析路径',
  },
  {
    key: 'agent_dual_track',
    label: '双轨路由',
    type: 'bool',
    desc: '仅在适配器支持 tools 且无附件时启用新链路，否则自动回落',
  },
  {
    key: 'agent_max_steps',
    label: '最大循环步数',
    type: 'number',
    desc: '单次请求内 ReAct 循环上限，达到后强制输出当前结果',
  },
]

function toBool(v) {
  if (typeof v === 'boolean') return v
  if (typeof v === 'string') return v.toLowerCase() === 'true'
  return false
}

function toDisplay(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function AdminConfig() {
  const [config, setConfig] = useState({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [savingKey, setSavingKey] = useState('')
  const [filter, setFilter] = useState('')
  const [draft, setDraft] = useState({})
  const [newKey, setNewKey] = useState('')
  const [newValue, setNewValue] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await apiGet('/admin/config')
      setConfig(result || {})
      setDraft({})
    } catch (e) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const flash = (msg) => {
    setNotice(msg)
    setTimeout(() => setNotice(''), 2500)
  }

  const save = async (key, value) => {
    setSavingKey(key)
    setError('')
    try {
      await apiPut(`/admin/config/${encodeURIComponent(key)}`, { value })
      setConfig((prev) => ({ ...prev, [key]: value }))
      setDraft((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
      flash(`已保存：${key}`)
    } catch (e) {
      setError(e.message || '保存失败')
    } finally {
      setSavingKey('')
    }
  }

  const remove = async (key) => {
    setSavingKey(key)
    setError('')
    try {
      await apiDelete(`/admin/config/${encodeURIComponent(key)}`)
      setConfig((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
      flash(`已删除：${key}`)
    } catch (e) {
      setError(e.message || '删除失败')
    } finally {
      setSavingKey('')
    }
  }

  const handleAdd = async () => {
    const k = newKey.trim()
    if (!k) return
    await save(k, newValue)
    setNewKey('')
    setNewValue('')
  }

  const keys = Object.keys(config).sort()
  const visibleKeys = filter.trim()
    ? keys.filter((k) => k.toLowerCase().includes(filter.trim().toLowerCase()))
    : keys

  return (
    <div className="min-h-screen t-bg-app t-text">
      <header className="flex items-center justify-between px-4 py-3 border-b t-border t-bg-panel">
        <div className="flex items-center gap-3">
          <Link to="/admin/users" className="p-2 rounded-lg t-hover-card" title="返回用户管理">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-base font-semibold">系统配置</h1>
            <p className="text-[11px] t-text-faint">
              直接读写 mu_config 表，保存后立即生效，无需重启服务
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeSwitcher />
          <button
            onClick={load}
            disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </header>

      <div className="max-w-4xl mx-auto p-4">
        {error && (
          <div className="mb-3 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">
            {error}
          </div>
        )}
        {notice && (
          <div className="mb-3 p-3 rounded-lg text-sm border t-border t-bg-panel t-text-2">{notice}</div>
        )}

        {/* Agent 编排开关 */}
        <section className="mb-6">
          <div className="flex items-center gap-2 mb-2">
            <Bot className="w-4 h-4 t-text-accent" />
            <h2 className="text-sm font-semibold">Agent 编排引擎</h2>
          </div>
          <div className="border t-border rounded-xl divide-y divide-[var(--border)]">
            {KNOWN.map((item) => {
              const raw = config[item.key]
              const defined = Object.prototype.hasOwnProperty.call(config, item.key)
              const current = item.type === 'bool' ? toBool(raw) : raw
              const pending = draft[item.key]
              const value = pending === undefined ? current : pending

              return (
                <div key={item.key} className="flex items-start justify-between gap-4 p-4">
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{item.label}</div>
                    <div className="text-[11px] t-text-faint mt-0.5">{item.desc}</div>
                    <code className="text-[11px] t-text-faint">{item.key}</code>
                    {!defined && <span className="ml-2 text-[11px] t-text-faint">（未设置，使用默认值）</span>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {item.type === 'bool' ? (
                      <button
                        onClick={() => save(item.key, !toBool(raw))}
                        disabled={savingKey === item.key}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-50 ${
                          value ? 't-bg-accent' : 'bg-gray-400'
                        }`}
                        title={value ? '点击关闭' : '点击开启'}
                      >
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                          value ? 'translate-x-6' : 'translate-x-1'
                        }`} />
                      </button>
                    ) : (
                      <>
                        <input
                          type="number"
                          value={toDisplay(value)}
                          onChange={(e) => setDraft((p) => ({ ...p, [item.key]: e.target.value }))}
                          className="w-20 px-2 py-1.5 text-xs rounded-lg border t-border t-bg-panel t-text"
                        />
                        <button
                          onClick={() => save(item.key, Number(draft[item.key] ?? value))}
                          disabled={savingKey === item.key || pending === undefined}
                          className="px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50"
                        >
                          保存
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        {/* 全量配置项 */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Settings className="w-4 h-4 t-text-accent" />
              <h2 className="text-sm font-semibold">全部配置项（{keys.length}）</h2>
            </div>
            <input
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="按 key 过滤"
              className="px-3 py-1.5 text-xs rounded-lg border t-border t-bg-panel t-text w-48"
            />
          </div>

          <div className="border t-border rounded-xl overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="t-bg-panel t-text-muted">
                  <th className="text-left px-3 py-2 font-medium w-1/3">键</th>
                  <th className="text-left px-3 py-2 font-medium">值</th>
                  <th className="text-right px-3 py-2 font-medium w-28">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {visibleKeys.map((key) => {
                  const pending = draft[key]
                  const value = pending === undefined ? toDisplay(config[key]) : pending
                  return (
                    <tr key={key}>
                      <td className="px-3 py-2 t-text-2 break-all">{key}</td>
                      <td className="px-3 py-2">
                        <input
                          value={value}
                          onChange={(e) => setDraft((p) => ({ ...p, [key]: e.target.value }))}
                          className="w-full px-2 py-1 rounded border t-border t-bg-panel t-text"
                        />
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        <button
                          onClick={() => save(key, draft[key])}
                          disabled={pending === undefined || savingKey === key}
                          title="保存"
                          className="inline-flex items-center gap-1 px-2 py-1 rounded t-hover-card disabled:opacity-30"
                        >
                          <Save className="w-3.5 h-3.5" />
                          保存
                        </button>
                        <button
                          onClick={() => remove(key)}
                          disabled={savingKey === key}
                          title="删除"
                          className="inline-flex items-center gap-1 px-2 py-1 rounded t-text-danger t-hover-card ml-1 disabled:opacity-30"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          删除
                        </button>
                      </td>
                    </tr>
                  )
                })}
                {visibleKeys.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-3 py-6 text-center t-text-faint">
                      {loading ? '加载中...' : '暂无配置项'}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {/* 新增配置 */}
          <div className="flex items-center gap-2 mt-3">
            <input
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="新配置 key"
              className="px-3 py-1.5 text-xs rounded-lg border t-border t-bg-panel t-text w-56"
            />
            <input
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder="值"
              className="px-3 py-1.5 text-xs rounded-lg border t-border t-bg-panel t-text flex-1"
            />
            <button
              onClick={handleAdd}
              disabled={!newKey.trim() || savingKey === newKey.trim()}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50"
            >
              <Plus className="w-3.5 h-3.5" />
              新增
            </button>
          </div>
        </section>
      </div>
    </div>
  )
}

export default AdminConfig
