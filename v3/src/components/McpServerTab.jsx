import { useState, useEffect, useCallback } from 'react'
import {
  Server, Plus, Trash2, Pencil, Play, Power, RefreshCw, X, Copy, Check,
  KeyRound, BookOpen, Wrench, AlertTriangle, Loader2,
} from 'lucide-react'
import { apiGet, apiPost, apiPut, apiDelete } from '../api/client'
import { useAuthStore } from '../stores/authStore'
import Modal from './Modal'

const METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']
const PARAMS_SCHEMA_PLACEHOLDER = '[{"name":"q","type":"string","description":"搜索词","required":true}]'

function emptyToolForm() {
  return {
    name: '',
    description: '',
    method: 'GET',
    url: '',
    headers: [], // [{k, v}]
    queryParams: [], // [{k, v}]
    bodyTemplate: '',
    paramsSchema: '',
    timeout: 30,
    isPublic: false,
  }
}

function kvRowsToObj(rows) {
  const obj = {}
  rows.forEach(({ k, v }) => {
    const key = (k || '').trim()
    if (key) obj[key] = v
  })
  return obj
}

function objToKvRows(obj) {
  if (!obj || typeof obj !== 'object') return []
  return Object.entries(obj).map(([k, v]) => ({ k, v: String(v) }))
}

function fmtTime(ts) {
  if (!ts) return '—'
  return String(ts).slice(0, 19).replace('T', ' ')
}

// 复制按钮（带短暂 ✓ 反馈）
function CopyButton({ text, label = '复制' }) {
  const [copied, setCopied] = useState(false)
  const doCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch (e) {
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button
      onClick={doCopy}
      className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border t-border-strong t-text-muted t-hover-card t-hover-text transition-colors"
    >
      {copied ? <Check className="w-3 h-3 t-text-ok" /> : <Copy className="w-3 h-3" />}
      {copied ? '已复制' : label}
    </button>
  )
}

// key-value 行编辑器（可加行删行）
function KvEditor({ rows, onChange, keyPlaceholder = 'Key', valuePlaceholder = 'Value' }) {
  const update = (idx, field, val) => {
    const next = rows.map((r, i) => (i === idx ? { ...r, [field]: val } : r))
    onChange(next)
  }
  const remove = (idx) => onChange(rows.filter((_, i) => i !== idx))
  const add = () => onChange([...rows, { k: '', v: '' }])
  return (
    <div className="space-y-1.5">
      {rows.map((r, i) => (
        <div key={i} className="flex items-center gap-1.5">
          <input
            className="flex-1 min-w-0 px-2 py-1.5 t-bg-input border t-border-strong rounded-lg text-xs t-text t-placeholder t-focus font-mono"
            placeholder={keyPlaceholder}
            value={r.k}
            onChange={(e) => update(i, 'k', e.target.value)}
          />
          <input
            className="flex-1 min-w-0 px-2 py-1.5 t-bg-input border t-border-strong rounded-lg text-xs t-text t-placeholder t-focus font-mono"
            placeholder={valuePlaceholder}
            value={r.v}
            onChange={(e) => update(i, 'v', e.target.value)}
          />
          <button type="button" onClick={() => remove(i)} className="t-text-fainter t-hover-text-danger shrink-0" title="删除该行">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={add}
        className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border t-border-strong t-text-muted t-hover-card t-hover-text transition-colors"
      >
        <Plus className="w-3 h-3" /> 添加一行
      </button>
    </div>
  )
}

function McpServerTab() {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin'
  const defaultSection = isAdmin ? 'tools' : 'guide'
  const [section, setSection] = useState(defaultSection) // tools | tokens | guide

  const sections = [
    ...(isAdmin ? [
      { k: 'tools', label: '工具管理', icon: Wrench },
      { k: 'tokens', label: '令牌管理', icon: KeyRound },
    ] : []),
    { k: 'guide', label: '接入指南', icon: BookOpen },
  ]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold t-text-2 flex items-center gap-1.5">
          <Server className="w-4 h-4 t-text-accent" />
          MCP 服务
        </h3>
      </div>

      {/* 内部分段（工具/令牌仅管理员可见） */}
      <div className="flex items-center gap-1">
        {sections.map((t) => (
          <button
            key={t.k}
            onClick={() => setSection(t.k)}
            className={`inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border transition-colors ${
              section === t.k ? 't-bg-accent text-white border-transparent' : 't-border-strong t-text-2 t-hover-card'
            }`}
          >
            <t.icon className="w-3 h-3" /> {t.label}
          </button>
        ))}
      </div>

      {section === 'tools' && isAdmin && <ToolsSection />}
      {section === 'tokens' && isAdmin && <TokensSection />}
      {section === 'guide' && <GuideSection />}
      {!isAdmin && section !== 'guide' && (
        <p className="text-xs t-text-faint text-center py-6">仅管理员可管理工具与令牌</p>
      )}
    </div>
  )
}

// ==================== 工具管理 ====================
function ToolsSection() {
  const [tools, setTools] = useState([])
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')

  // 新建/编辑弹窗
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(emptyToolForm())
  const [formMsg, setFormMsg] = useState('')
  const [saving, setSaving] = useState(false)

  // 测试弹窗
  const [testTool, setTestTool] = useState(null)
  const [testArgs, setTestArgs] = useState('{}')
  const [testResult, setTestResult] = useState('')
  const [testing, setTesting] = useState(false)

  const inputCls = 'w-full px-3 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text t-placeholder t-focus'

  const loadTools = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiGet('/mcp-server/tools')
      if (res.success) setTools(res.tools || [])
    } catch (e) {
      console.error('加载 MCP 服务工具失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTools()
  }, [loadTools])

  const openNew = () => {
    setEditingId(null)
    setForm(emptyToolForm())
    setFormMsg('')
    setShowForm(true)
  }

  const openEdit = (t) => {
    setEditingId(t.id)
    setForm({
      name: t.name || '',
      description: t.description || '',
      method: (t.method || 'GET').toUpperCase(),
      url: t.url || '',
      headers: objToKvRows(t.headers),
      queryParams: objToKvRows(t.query_params),
      bodyTemplate: t.body_template || '',
      paramsSchema: t.params_schema ? JSON.stringify(t.params_schema, null, 2) : '',
      timeout: t.timeout ?? 30,
      isPublic: !!t.is_public,
    })
    setFormMsg('')
    setShowForm(true)
  }

  const buildPayload = () => {
    let paramsSchema = []
    if (form.paramsSchema.trim()) {
      try {
        paramsSchema = JSON.parse(form.paramsSchema)
        if (!Array.isArray(paramsSchema)) throw new Error('params_schema 必须是 JSON 数组')
      } catch (e) {
        setFormMsg('参数定义不是合法 JSON 数组: ' + e.message)
        return null
      }
    }
    return {
      name: form.name.trim(),
      description: form.description,
      method: form.method,
      url: form.url.trim(),
      headers: kvRowsToObj(form.headers),
      query_params: kvRowsToObj(form.queryParams),
      body_template: form.bodyTemplate,
      params_schema: paramsSchema,
      timeout: Number(form.timeout) || 30,
      is_public: form.isPublic,
    }
  }

  const handleSave = async () => {
    const payload = buildPayload()
    if (!payload) return
    if (!payload.name) { setFormMsg('请填写工具名称'); return }
    if (!payload.url) { setFormMsg('请填写 URL'); return }
    setSaving(true)
    try {
      const res = editingId
        ? await apiPut(`/mcp-server/tools/${editingId}`, payload)
        : await apiPost('/mcp-server/tools', payload)
      if (res.success) {
        setShowForm(false)
        loadTools()
      } else {
        setFormMsg(res.error || '保存失败')
      }
    } catch (e) {
      setFormMsg('保存失败: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (t) => {
    if (!window.confirm(`确定删除工具「${t.name}」吗？`)) return
    try {
      const res = await apiDelete(`/mcp-server/tools/${t.id}`)
      if (res.success) loadTools()
      else alert(res.error || '删除失败')
    } catch (e) {
      alert(e.message)
    }
  }

  const handleToggle = async (t) => {
    try {
      const res = await apiPost(`/mcp-server/tools/${t.id}/toggle`, { enabled: !t.enabled })
      if (res.success) loadTools()
      else alert(res.error || '操作失败')
    } catch (e) {
      alert(e.message)
    }
  }

  const openTest = (t) => {
    setTestTool(t)
    // 根据参数定义预填默认 arguments
    const schema = Array.isArray(t.params_schema) ? t.params_schema : []
    const obj = {}
    schema.forEach((p) => { if (p && p.name) obj[p.name] = '' })
    setTestArgs(JSON.stringify(obj, null, 2))
    setTestResult('')
  }

  const runTest = async () => {
    if (!testTool) return
    let args = {}
    try {
      args = testArgs.trim() ? JSON.parse(testArgs) : {}
    } catch (e) {
      setTestResult('arguments 不是合法 JSON: ' + e.message)
      return
    }
    setTesting(true)
    setTestResult('')
    try {
      const res = await apiPost(`/mcp-server/tools/${testTool.id}/test`, { arguments: args })
      setTestResult(res.success ? (res.result || '（无返回）') : '调用失败: ' + (res.error || '未知错误'))
    } catch (e) {
      setTestResult('调用失败: ' + e.message)
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs t-text-faint">对外暴露的 HTTP 工具（{tools.length}）</p>
        <div className="flex items-center gap-1.5">
          <button onClick={openNew} className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg t-bg-accent text-white t-hover-accent">
            <Plus className="w-3 h-3" /> 新建
          </button>
          <button onClick={loadTools} className="p-1 rounded-lg border t-border-strong t-text-muted t-hover-card" title="刷新">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {msg && <p className="text-xs t-text-info break-all">{msg}</p>}

      {loading ? (
        <p className="text-xs t-text-faint text-center py-6 loading-pulse">加载中...</p>
      ) : tools.length === 0 ? (
        <p className="text-xs t-text-fainter text-center py-6">暂无工具，点击「新建」创建</p>
      ) : (
        <div className="space-y-2">
          {tools.map((t) => (
            <div key={t.id} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg group">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs t-text-2 truncate flex-1" title={t.description}>
                  <span className="text-[9px] px-1 py-0.5 rounded t-badge-accent mr-1.5 font-mono">{(t.method || 'GET').toUpperCase()}</span>
                  <span className="truncate">{t.name}</span>
                  {t.is_public && <span className="text-[9px] px-1 py-0.5 rounded t-badge-neutral mr-1.5">公共</span>}
                  {!t.enabled && <span className="text-[9px] t-text-faint ml-1">（已禁用）</span>}
                </p>
                <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-all">
                  <button onClick={() => handleToggle(t)} className="t-text-fainter t-hover-text-accent" title={t.enabled ? '禁用' : '启用'}>
                    <Power className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => openTest(t)} className="t-text-fainter t-hover-text-accent" title="测试调用">
                    <Play className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => openEdit(t)} className="t-text-fainter t-hover-text-accent" title="编辑">
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => handleDelete(t)} className="t-text-fainter t-hover-text-danger" title="删除">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <p className="text-[10px] t-text-faint mt-1 break-all font-mono">{t.url}</p>
              {t.description && <p className="text-[10px] t-text-fainter mt-0.5 truncate">{t.description}</p>}
            </div>
          ))}
        </div>
      )}

      {/* 新建/编辑弹窗 */}
      {showForm && (
        <Modal title={editingId ? '编辑工具' : '新建工具'} wide onClose={() => setShowForm(false)}>
          <div className="space-y-2.5">
            <input className={inputCls} placeholder="工具名称（如 web_search）" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className={inputCls} placeholder="描述（何时调用该工具）" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            <div className="flex gap-2">
              <select className="w-28 px-2 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text-2 outline-none shrink-0" value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>
                {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
              </select>
              <input className={inputCls} placeholder="URL，可用 {参数名} 占位，如 https://api.example.com/search" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
            </div>
            <div>
              <p className="text-[11px] t-text-muted mb-1">请求头 Headers</p>
              <KvEditor rows={form.headers} onChange={(rows) => setForm({ ...form, headers: rows })} keyPlaceholder="Header 名" valuePlaceholder="Header 值" />
            </div>
            <div>
              <p className="text-[11px] t-text-muted mb-1">查询参数 Query Params</p>
              <KvEditor rows={form.queryParams} onChange={(rows) => setForm({ ...form, queryParams: rows })} keyPlaceholder="参数名" valuePlaceholder="参数值（可用 {占位符}）" />
            </div>
            <div>
              <p className="text-[11px] t-text-muted mb-1">请求体模板 Body Template（POST/PUT/PATCH 使用，可用 {'{占位符}'}）</p>
              <textarea className={inputCls + ' min-h-[72px] font-mono'} placeholder='{"query": "{q}", "count": 10}' value={form.bodyTemplate} onChange={(e) => setForm({ ...form, bodyTemplate: e.target.value })} />
            </div>
            <div>
              <p className="text-[11px] t-text-muted mb-1">参数定义 params_schema（JSON 数组）</p>
              <textarea className={inputCls + ' min-h-[72px] font-mono'} placeholder={PARAMS_SCHEMA_PLACEHOLDER} value={form.paramsSchema} onChange={(e) => setForm({ ...form, paramsSchema: e.target.value })} />
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] t-text-muted shrink-0">超时（秒）</span>
              <input type="number" min="1" max="300" className="w-24 px-2 py-1.5 t-bg-input border t-border-strong rounded-lg text-xs t-text t-focus" value={form.timeout} onChange={(e) => setForm({ ...form, timeout: e.target.value })} />
            </div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={form.isPublic}
                onChange={(e) => setForm({ ...form, isPublic: e.target.checked })}
                className="w-3.5 h-3.5 accent-current t-text-accent"
              />
              <span className="text-[11px] t-text-muted">设为公共（所有用户可通过 MCP 服务端调用此工具）</span>
            </label>
            {formMsg && <p className="text-xs t-text-warn break-all">{formMsg}</p>}
            <div className="flex items-center gap-2 pt-1">
              <button onClick={handleSave} disabled={saving} className="px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50">
                {saving ? '保存中...' : '保存'}
              </button>
              <button onClick={() => setShowForm(false)} className="px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-muted t-hover-card">取消</button>
            </div>
          </div>
        </Modal>
      )}

      {/* 测试调用弹窗 */}
      {testTool && (
        <Modal title={`测试工具: ${testTool.name}`} wide onClose={() => setTestTool(null)}>
          <div className="space-y-2.5">
            <p className="text-[11px] t-text-muted">输入 arguments（JSON 对象），将按参数定义发起真实 HTTP 调用</p>
            <textarea
              className={inputCls + ' min-h-[90px] font-mono'}
              placeholder='{"q": "搜索词"}'
              value={testArgs}
              onChange={(e) => setTestArgs(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <button onClick={runTest} disabled={testing} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50">
                {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                {testing ? '调用中...' : '执行调用'}
              </button>
              <button onClick={() => setTestTool(null)} className="px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-muted t-hover-card">关闭</button>
            </div>
            {testResult && (
              <pre className="max-h-72 overflow-auto p-3 t-bg-app border t-border rounded-lg text-[11px] t-text-2 whitespace-pre-wrap break-all font-mono">{testResult}</pre>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}

// ==================== 令牌管理 ====================
function TokensSection() {
  const [tokens, setTokens] = useState([])
  const [loading, setLoading] = useState(false)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [plaintext, setPlaintext] = useState('') // 一次性明文
  const [msg, setMsg] = useState('')

  const loadTokens = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiGet('/mcp-server/tokens')
      if (res.success) setTokens(res.tokens || [])
    } catch (e) {
      console.error('加载令牌失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadTokens()
  }, [loadTokens])

  const handleCreate = async () => {
    const name = newName.trim()
    if (!name) { setMsg('请填写令牌名称'); return }
    setCreating(true)
    setMsg('')
    try {
      const res = await apiPost('/mcp-server/tokens', { name })
      if (res.success && res.plaintext) {
        setPlaintext(res.plaintext)
        setNewName('')
        loadTokens()
      } else {
        setMsg(res.error || '创建失败')
      }
    } catch (e) {
      setMsg('创建失败: ' + e.message)
    } finally {
      setCreating(false)
    }
  }

  const handleRevoke = async (t) => {
    if (!window.confirm(`确定吊销令牌「${t.name}」吗？吊销后使用该令牌的客户端将立即无法访问。`)) return
    try {
      const res = await apiDelete(`/mcp-server/tokens/${t.id}`)
      if (res.success) loadTokens()
      else alert(res.error || '吊销失败')
    } catch (e) {
      alert(e.message)
    }
  }

  const inputCls = 'w-full px-3 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text t-placeholder t-focus'

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1.5">
        <input
          className={inputCls}
          placeholder="令牌名称（如：我的 Claude Desktop）"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleCreate() }}
        />
        <button
          onClick={handleCreate}
          disabled={creating}
          className="inline-flex items-center gap-1 px-2.5 py-2 text-[11px] rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50 shrink-0"
        >
          {creating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
          生成
        </button>
        <button onClick={loadTokens} className="p-1 rounded-lg border t-border-strong t-text-muted t-hover-card shrink-0" title="刷新">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {msg && <p className="text-xs t-text-warn break-all">{msg}</p>}

      {loading ? (
        <p className="text-xs t-text-faint text-center py-6 loading-pulse">加载中...</p>
      ) : tokens.length === 0 ? (
        <p className="text-xs t-text-fainter text-center py-6">暂无令牌，输入名称生成一个</p>
      ) : (
        <div className="space-y-2">
          {tokens.map((t) => (
            <div key={t.id} className={`px-3 py-2.5 t-bg-panel border t-border rounded-lg ${t.revoked ? 'opacity-50' : ''}`}>
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs t-text-2 truncate flex-1">
                  <span className="truncate">{t.name}</span>
                  <span className="text-[10px] t-text-faint font-mono ml-1.5">{t.prefix}…</span>
                  {t.revoked && <span className="text-[9px] t-badge-neutral px-1 py-0.5 rounded ml-1.5">已吊销</span>}
                </p>
                {!t.revoked && (
                  <button onClick={() => handleRevoke(t)} className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border t-border-danger t-text-danger t-bg-danger-soft transition-colors shrink-0" title="吊销该令牌">
                    <Trash2 className="w-3 h-3" /> 吊销
                  </button>
                )}
              </div>
              <p className="text-[10px] t-text-fainter mt-1">
                最近使用：{fmtTime(t.last_used_at)} · 创建：{fmtTime(t.created_at)}
                {t.expires_at ? ` · 过期：${fmtTime(t.expires_at)}` : ''}
              </p>
            </div>
          ))}
        </div>
      )}

      {/* 一次性明文展示弹窗 */}
      {plaintext && (
        <Modal title="令牌已生成" onClose={() => setPlaintext('')} maximizable={false}>
          <div className="space-y-3">
            <div className="p-2.5 t-bg-warn-soft border t-border-warn rounded-lg t-text-warn text-[11px] flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>令牌明文仅显示一次，请立即复制并妥善保存。关闭本窗口后将无法再次查看。</span>
            </div>
            <pre className="p-3 t-bg-app border t-border rounded-lg text-xs t-text-2 font-mono break-all whitespace-pre-wrap select-all">{plaintext}</pre>
            <div className="flex items-center gap-2">
              <CopyButton text={plaintext} label="复制令牌" />
              <button onClick={() => setPlaintext('')} className="px-3 py-1 text-[11px] rounded-lg border t-border-strong t-text-muted t-hover-card">我已保存，关闭</button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}

// ==================== 接入指南 ====================
function GuideSection() {
  const [info, setInfo] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await apiGet('/mcp-server/endpoint-info')
      if (res.success) setInfo(res)
    } catch (e) {
      console.error('加载接入信息失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return <p className="text-xs t-text-faint text-center py-6 loading-pulse">加载中...</p>
  }

  if (!info || info.available === false) {
    return (
      <div className="p-2.5 t-bg-warn-soft border t-border-warn rounded-lg t-text-warn text-[11px] flex items-start gap-2">
        <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
        <span>MCP 服务当前不可用，请联系管理员检查服务端配置。</span>
      </div>
    )
  }

  const configText = typeof info.client_config_example === 'string'
    ? info.client_config_example
    : JSON.stringify(info.client_config_example || {}, null, 2)

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <p className="text-[11px] t-text-muted">接入地址（Endpoint）</p>
        <div className="flex items-center gap-1.5">
          <code className="flex-1 min-w-0 px-2.5 py-2 t-bg-input border t-border-strong rounded-lg text-[11px] t-text-2 font-mono break-all">{info.endpoint}</code>
          <CopyButton text={info.endpoint} />
        </div>
      </div>

      <div className="space-y-1.5">
        <p className="text-[11px] t-text-muted">传输方式（Transport）</p>
        <span className="inline-block text-[10px] px-1.5 py-0.5 rounded-full border t-badge-accent font-mono">{info.transport || 'streamable-http'}</span>
      </div>

      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <p className="text-[11px] t-text-muted">客户端配置示例</p>
          <CopyButton text={configText} label="复制配置" />
        </div>
        <pre className="max-h-72 overflow-auto p-3 t-bg-app border t-border rounded-lg text-[11px] t-text-2 font-mono whitespace-pre-wrap break-all">{configText}</pre>
      </div>

      <p className="text-[10px] t-text-fainter leading-relaxed">
        将上方配置粘贴到 Claude Desktop / Cursor 的 MCP 配置文件中，并将
        <code className="mx-1 px-1 t-bg-panel rounded">{'<在此粘贴你的令牌>'}</code>
        替换为「令牌管理」中生成的令牌，保存后重启客户端即可使用这里配置的工具。
      </p>
    </div>
  )
}

export default McpServerTab
