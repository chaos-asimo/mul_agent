import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Trash2, Plug, RefreshCw, Loader2, X, Power, Wrench, Edit3, Zap, AlertTriangle,
} from 'lucide-react'
import { apiGet, apiPost, apiPut, apiDelete } from '../api/client'

const TRANSPORT_LABELS = {
  stdio: 'stdio',
  sse: 'SSE',
  http: 'HTTP',
  'streamable-http': 'HTTP',
}

function parseLines(text, mapper) {
  return text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map(mapper)
}

function McpTab() {
  const [servers, setServers] = useState([])
  const [loading, setLoading] = useState(true)
  const [mcpAvailable, setMcpAvailable] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [message, setMessage] = useState('')
  const [testStates, setTestStates] = useState({}) // { [id]: {loading, result} }
  const [form, setForm] = useState({
    name: '',
    transport: 'stdio',
    command: '',
    argsText: '',
    envText: '',
    url: '',
    enabled: true,
  })

  const loadServers = useCallback(async () => {
    try {
      const result = await apiGet('/mcp/servers')
      if (result.success) {
        setServers(result.servers || [])
        setMcpAvailable(result.mcp_available !== false)
      }
    } catch (e) {
      console.error('加载 MCP server 失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadServers()
  }, [loadServers])

  const resetForm = () => {
    setForm({ name: '', transport: 'stdio', command: '', argsText: '', envText: '', url: '', enabled: true })
    setEditingId(null)
    setShowForm(false)
  }

  const buildBody = () => {
    const body = {
      name: form.name.trim(),
      transport: form.transport,
      enabled: form.enabled,
    }
    if (form.transport === 'stdio') {
      body.command = form.command.trim()
      body.args = parseLines(form.argsText, (l) => l)
      body.env = {}
      parseLines(form.envText, (l) => {
        const idx = l.indexOf('=')
        if (idx > 0) body.env[l.slice(0, idx).trim()] = l.slice(idx + 1).trim()
        return null
      })
    } else {
      body.url = form.url.trim()
    }
    return body
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setMessage('')
    if (!form.name.trim()) {
      setMessage('请填写名称')
      return
    }
    if (form.transport === 'stdio' && !form.command.trim()) {
      setMessage('stdio 类型必须填写启动命令')
      return
    }
    if (form.transport !== 'stdio' && !form.url.trim()) {
      setMessage('SSE/HTTP 类型必须填写 URL')
      return
    }
    try {
      const body = buildBody()
      const result = editingId
        ? await apiPut(`/mcp/servers/${editingId}`, body)
        : await apiPost('/mcp/servers', body)
      if (result.success) {
        resetForm()
        loadServers()
      } else {
        setMessage(result.error || result.detail || '保存失败')
      }
    } catch (e2) {
      setMessage(e2.message)
    }
  }

  const handleEdit = (srv) => {
    setMessage('')
    setEditingId(srv.id)
    setForm({
      name: srv.name || '',
      transport: srv.transport || 'stdio',
      command: srv.command || '',
      argsText: Array.isArray(srv.args) ? srv.args.join('\n') : '',
      // 编辑时 env 为脱敏 {KEY: '***'}，预填为 KEY=***（保持不变）
      envText: srv.env && typeof srv.env === 'object'
        ? Object.entries(srv.env).map(([k]) => `${k}=***`).join('\n')
        : '',
      url: srv.url || '',
      enabled: !!srv.enabled,
    })
    setShowForm(true)
  }

  const handleToggle = async (srv) => {
    setMessage('')
    try {
      const result = await apiPost(`/mcp/servers/${srv.id}/toggle`)
      if (result.success) loadServers()
      else setMessage(result.error || '操作失败')
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleDelete = async (srv) => {
    if (!window.confirm(`确定删除 MCP server「${srv.name}」吗？`)) return
    try {
      await apiDelete(`/mcp/servers/${srv.id}`)
      setTestStates((prev) => {
        const next = { ...prev }
        delete next[srv.id]
        return next
      })
      loadServers()
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleTest = async (srv) => {
    setMessage('')
    setTestStates((prev) => ({ ...prev, [srv.id]: { loading: true, result: null } }))
    try {
      const result = await apiPost(`/mcp/servers/${srv.id}/test`)
      setTestStates((prev) => ({ ...prev, [srv.id]: { loading: false, result } }))
      loadServers()
    } catch (e) {
      setTestStates((prev) => ({
        ...prev,
        [srv.id]: { loading: false, result: { success: false, error: e.message } },
      }))
    }
  }

  const inputCls =
    'w-full px-3 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text t-placeholder t-focus'
  const btnGhost =
    'inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border t-border-strong t-text-muted t-hover-card t-hover-text transition-colors'
  const btnDanger =
    'inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border t-border-danger t-text-danger t-bg-danger-soft transition-colors'
  const btnPrimary =
    'inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg t-bg-accent t-hover-accent text-white disabled:opacity-50'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold t-text-2 flex items-center gap-1.5">
          <Plug className="w-4 h-4 t-text-accent" />
          MCP 工具
        </h3>
        <div className="flex items-center gap-1.5">
          <button onClick={loadServers} className={btnGhost} title="刷新">
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => {
              setMessage('')
              if (showForm) resetForm()
              else {
                setEditingId(null)
                setForm({ name: '', transport: 'stdio', command: '', argsText: '', envText: '', url: '', enabled: true })
                setShowForm(true)
              }
            }}
            className={btnPrimary}
          >
            <Plus className="w-3 h-3" />
            新建
          </button>
        </div>
      </div>

      {!mcpAvailable && (
        <div className="p-2.5 t-bg-warn-soft border t-border-warn rounded-lg t-text-warn text-[11px] flex items-start gap-2">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>
            MCP 依赖未安装，外部工具功能不可用。请在服务器环境执行
            <code className="mx-1 px-1 t-bg-panel rounded">pip install mcp</code>
            后重启服务。
          </span>
        </div>
      )}

      {message && <p className="text-xs t-text-warn break-all">{message}</p>}

      {/* 新建/编辑表单 */}
      {showForm && (
        <form onSubmit={handleSubmit} className="p-3 t-bg-panel border t-border rounded-xl space-y-2.5">
          <div className="flex gap-2">
            <input
              className={inputCls}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="名称 *（如：文件系统、网页抓取）"
              required
            />
            <select
              value={form.transport}
              onChange={(e) => setForm({ ...form, transport: e.target.value })}
              className="w-28 px-2 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text-2 outline-none shrink-0"
            >
              <option value="stdio">stdio</option>
              <option value="sse">SSE</option>
              <option value="http">HTTP</option>
            </select>
          </div>

          {form.transport === 'stdio' ? (
            <>
              <input
                className={inputCls}
                value={form.command}
                onChange={(e) => setForm({ ...form, command: e.target.value })}
                placeholder="启动命令 *（如：npx、uvx、python）"
              />
              <textarea
                className={inputCls + ' resize-none h-14'}
                value={form.argsText}
                onChange={(e) => setForm({ ...form, argsText: e.target.value })}
                placeholder={'参数，每行一个，如：\n-y\n@modelcontextprotocol/server-filesystem\nC:\\data'}
              />
              <textarea
                className={inputCls + ' resize-none h-14'}
                value={form.envText}
                onChange={(e) => setForm({ ...form, envText: e.target.value })}
                placeholder={'环境变量，每行一个 KEY=VALUE（可留空）\n编辑时 *** 表示保持原值不变'}
              />
            </>
          ) : (
            <input
              className={inputCls}
              value={form.url}
              onChange={(e) => setForm({ ...form, url: e.target.value })}
              placeholder="服务 URL *（如：http://localhost:8000/sse）"
            />
          )}

          <label className="flex items-center gap-2 text-xs t-text-muted">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              className="accent-indigo-500"
            />
            保存后启用（启用后 AI 对话中可调用其工具）
          </label>
          <div className="flex gap-2">
            <button type="submit" className="px-3 py-1.5 text-xs rounded-lg t-bg-accent t-hover-accent text-white">
              {editingId ? '保存' : '创建'}
            </button>
            <button
              type="button"
              onClick={resetForm}
              className="px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card"
            >
              取消
            </button>
          </div>
        </form>
      )}

      {/* server 列表 */}
      {servers.length === 0 && !loading ? (
        <div className="text-center py-8">
          <Wrench className="w-8 h-8 t-text-fainter mx-auto mb-2" />
          <p className="text-xs t-text-fainter">暂无 MCP server，添加一个以接入外部工具</p>
          <p className="text-[10px] t-text-fainter mt-1">
            支持 stdio 本地进程（npx / uvx）与 SSE / HTTP 远程服务
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {servers.map((srv) => {
            const ts = testStates[srv.id]
            return (
              <div key={srv.id} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium t-text-2 truncate flex-1" title={srv.name}>
                    {srv.name}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full border t-badge-accent">
                      {TRANSPORT_LABELS[srv.transport] || srv.transport}
                    </span>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                        srv.enabled ? 't-badge-ok' : 't-badge-neutral'
                      }`}
                    >
                      {srv.enabled ? '启用' : '禁用'}
                    </span>
                  </div>
                </div>
                <p className="text-[10px] t-text-fainter mt-1 break-all">
                  {srv.transport === 'stdio'
                    ? `${srv.command} ${(srv.args || []).join(' ')}`
                    : srv.url}
                </p>
                <p className="text-[10px] t-text-fainter mt-0.5">
                  {srv.tool_count_cached != null ? `已发现 ${srv.tool_count_cached} 个工具` : '尚未连接测试'}
                </p>

                <div className="flex flex-wrap items-center gap-1.5 mt-2">
                  <button onClick={() => handleToggle(srv)} className={btnGhost}>
                    <Power className="w-3 h-3" />
                    {srv.enabled ? '禁用' : '启用'}
                  </button>
                  <button onClick={() => handleTest(srv)} disabled={ts?.loading} className={btnPrimary}>
                    {ts?.loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Zap className="w-3 h-3" />}
                    测试连接
                  </button>
                  <button onClick={() => handleEdit(srv)} className={btnGhost}>
                    <Edit3 className="w-3 h-3" />
                    编辑
                  </button>
                  <button onClick={() => handleDelete(srv)} className={btnDanger}>
                    <Trash2 className="w-3 h-3" />
                    删除
                  </button>
                </div>

                {/* 测试结果 */}
                {ts?.result && (
                  <div className="mt-2 p-2 rounded-lg border t-border t-bg-input">
                    {ts.result.success ? (
                      <>
                        <p className="text-[11px] t-text-ok font-medium">
                          ✅ 连接成功，发现 {ts.result.tool_count ?? ts.result.tools?.length ?? 0} 个工具
                        </p>
                        <div className="mt-1.5 space-y-1 max-h-40 overflow-y-auto">
                          {(ts.result.tools || []).map((tool) => (
                            <div key={tool.name} className="text-[10px] t-text-muted">
                              <span className="font-medium t-text-accent">{tool.name}</span>
                              {tool.description ? (
                                <span className="t-text-faint"> — {tool.description.slice(0, 100)}</span>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      </>
                    ) : (
                      <p className="text-[11px] t-text-danger break-all">❌ {ts.result.error || '连接失败'}</p>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default McpTab
