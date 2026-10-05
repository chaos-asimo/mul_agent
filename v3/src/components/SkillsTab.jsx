import { useState, useEffect, useCallback } from 'react'
import { Wand2, Plus, Trash2, Pencil, Play, Power, X, RefreshCw, Globe } from 'lucide-react'
import { apiGet, apiPost, apiPut, apiDelete } from '../api/client'
import { useAuthStore } from '../stores/authStore'

const EXECUTORS = [
  { value: 'llm', label: 'LLM 提示模板' },
  { value: 'script', label: 'Python 脚本' },
  { value: 'search', label: '联网搜索' },
  { value: 'api', label: 'HTTP API' },
]

function emptyForm() {
  return {
    name: '',
    description: '',
    executor: 'llm',
    prompt_template: '',
    script: '',
    api_endpoint: '',
    parameters: '',
    enabled: true,
  }
}

// 根据技能声明的参数，生成默认 JSON 模板（用于「测试执行」输入框预填）
function defaultParamsFor(skill) {
  const params = (skill && skill.config && skill.config.parameters) || []
  if (!Array.isArray(params) || params.length === 0) return '{}'
  const obj = {}
  params.forEach((p) => {
    if (p && p.name) obj[p.name] = (p.description && String(p.description).trim()) || ''
  })
  return JSON.stringify(obj, null, 2)
}

function SkillsTab() {
  const { user } = useAuthStore()
  const isAdmin = user?.role === 'admin'

  const [skills, setSkills] = useState([])
  const [loading, setLoading] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editingIsPublic, setEditingIsPublic] = useState(false)
  const [form, setForm] = useState(emptyForm())
  const [msg, setMsg] = useState('')

  // 手动执行
  const [execId, setExecId] = useState(null)
  const [execParams, setExecParams] = useState('{}')
  const [execResult, setExecResult] = useState('')
  const [executing, setExecuting] = useState(false)

  // 管理员：公共技能管理
  const [adminMode, setAdminMode] = useState(false)

  // 路由基址：公共技能必须走 admin 路由（用户路由不认 admin 身份，会被 _can_write 拒绝）
  const apiBase = (s) => (adminMode || (s && s.is_public && isAdmin) ? '/admin/skill' : '/skill')
  // 非管理员视角下，公共技能只读（可执行，不可改/删/启停）
  const readonlyForMe = (s) => !!s.is_public && !isAdmin

  const loadSkills = useCallback(async () => {
    setLoading(true)
    try {
      const path = adminMode ? '/admin/skill/list' : '/skill/list'
      const res = await apiGet(path)
      if (res.success) setSkills(res.skills || [])
    } catch (e) {
      console.error('加载技能失败:', e)
    } finally {
      setLoading(false)
    }
  }, [adminMode])

  useEffect(() => {
    loadSkills()
  }, [loadSkills])

  const openNew = () => {
    setEditingId(null)
    setEditingIsPublic(false)
    setForm(emptyForm())
    setShowForm(true)
    setMsg('')
  }

  const openEdit = (s) => {
    setEditingId(s.skill_id)
    setEditingIsPublic(!!s.is_public)
    const cfg = s.config || {}
    setForm({
      name: s.name || cfg.name || '',
      description: s.description || cfg.description || '',
      executor: s.executor || cfg.executor || 'llm',
      prompt_template: cfg.prompt_template || '',
      script: cfg.script || '',
      api_endpoint: cfg.api_endpoint || '',
      parameters: JSON.stringify(cfg.parameters || [], null, 2),
      enabled: !!s.enabled,
    })
    setShowForm(true)
    setMsg('')
  }

  const buildPayload = () => {
    let parameters = []
    try {
      parameters = form.parameters ? JSON.parse(form.parameters) : []
    } catch (e) {
      setMsg('parameters 不是合法 JSON 数组')
      return null
    }
    return {
      name: form.name,
      description: form.description,
      executor: form.executor,
      prompt_template: form.prompt_template,
      script: form.script,
      api_endpoint: form.api_endpoint,
      parameters,
      enabled: form.enabled,
    }
  }

  const handleSave = async () => {
    const payload = buildPayload()
    if (!payload) return
    if (!payload.name.trim()) {
      setMsg('请填写技能名称')
      return
    }
    try {
      const base = adminMode || editingIsPublic ? '/admin/skill' : '/skill'
      const res = editingId
        ? await apiPut(`${base}/${editingId}`, payload)
        : await apiPost(base, payload)
      if (res.success) {
        setShowForm(false)
        setMsg('')
        loadSkills()
      } else {
        setMsg(res.error || '保存失败')
      }
    } catch (e) {
      setMsg('保存失败: ' + e.message)
    }
  }

  const handleDelete = async (s) => {
    if (!window.confirm('确定删除该技能吗？')) return
    try {
      const res = await apiDelete(`${apiBase(s)}/${s.skill_id}`)
      if (res.success) loadSkills()
      else alert(res.error || '删除失败')
    } catch (e) {
      alert(e.message)
    }
  }

  const toggleEnabled = async (s) => {
    try {
      const action = s.enabled ? 'disable' : 'enable'
      const res = await apiPost(`${apiBase(s)}/${s.skill_id}/${action}`, {})
      if (res.success) loadSkills()
      else alert(res.error || '操作失败')
    } catch (e) {
      alert(e.message)
    }
  }

  const runExecute = async () => {
    if (!execId) return
    let params = {}
    try {
      params = execParams.trim() ? JSON.parse(execParams) : {}
    } catch (e) {
      setExecResult('参数不是合法 JSON: ' + e.message)
      return
    }
    setExecuting(true)
    setExecResult('')
    try {
      const res = await apiPost(`/skill/${execId}/execute`, { params })
      if (res.success) {
        setExecResult(typeof res.result === 'string' ? res.result : JSON.stringify(res.result, null, 2))
      } else {
        setExecResult('执行失败: ' + (res.error || '未知错误'))
      }
    } catch (e) {
      setExecResult('执行失败: ' + e.message)
    } finally {
      setExecuting(false)
    }
  }

  const inputCls = 'w-full px-3 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text t-placeholder t-focus'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold t-text-2 flex items-center gap-1.5">
          <Wand2 className="w-4 h-4 t-text-accent" />
          {adminMode ? '公共技能管理' : '我的技能'}
        </h3>
        <div className="flex items-center gap-1.5">
          {isAdmin && (
            <button
              onClick={() => { setAdminMode(!adminMode); setShowForm(false); setExecId(null) }}
              className={`inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border transition-colors ${
                adminMode ? 't-bg-accent text-white border-transparent' : 't-border-strong t-text-2 t-hover-card'
              }`}
              title="切换公共技能管理"
            >
              <Globe className="w-3 h-3" />
              公共
            </button>
          )}
          <button onClick={openNew} className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg t-bg-accent text-white t-hover-accent">
            <Plus className="w-3 h-3" /> 新建
          </button>
          <button onClick={loadSkills} className="p-1 rounded-lg border t-border-strong t-text-muted t-hover-card" title="刷新">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {msg && <p className="text-xs t-text-info break-all">{msg}</p>}

      {/* 表单 */}
      {showForm && (
        <div className="space-y-2 p-3 t-bg-panel border t-border rounded-lg">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium t-text-2">{editingId ? '编辑技能' : '新建技能'}</span>
            <button onClick={() => setShowForm(false)} className="t-text-fainter t-hover-text"><X className="w-3.5 h-3.5" /></button>
          </div>
          <input className={inputCls} placeholder="技能名称" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <input className={inputCls} placeholder="描述（何时使用该技能）" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <select className={inputCls} value={form.executor} onChange={(e) => setForm({ ...form, executor: e.target.value })}>
            {EXECUTORS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          {form.executor === 'llm' && (
            <textarea className={inputCls + ' min-h-[72px] font-mono'} placeholder="提示模板，可用 {占位符}，如：请总结：{content}" value={form.prompt_template} onChange={(e) => setForm({ ...form, prompt_template: e.target.value })} />
          )}
          {form.executor === 'script' && (
            <textarea className={inputCls + ' min-h-[90px] font-mono'} placeholder="Python 脚本代码（在沙箱中执行）" value={form.script} onChange={(e) => setForm({ ...form, script: e.target.value })} />
          )}
          {form.executor === 'api' && (
            <input className={inputCls} placeholder="API endpoint URL" value={form.api_endpoint} onChange={(e) => setForm({ ...form, api_endpoint: e.target.value })} />
          )}
          <textarea className={inputCls + ' min-h-[56px] font-mono'} placeholder='参数定义 JSON 数组，如 [{"name":"content","required":true}]' value={form.parameters} onChange={(e) => setForm({ ...form, parameters: e.target.value })} />
          <div className="flex items-center gap-2">
            <button onClick={handleSave} className="px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent">保存</button>
            <button onClick={() => setShowForm(false)} className="px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-muted t-hover-card">取消</button>
          </div>
        </div>
      )}

      {/* 手动执行面板 */}
      {execId && (
        <div className="space-y-2 p-3 t-bg-panel border t-border-accent/40 rounded-lg">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium t-text-accent">测试执行: {skills.find((s) => s.skill_id === execId)?.name || execId}</span>
            <button onClick={() => { setExecId(null); setExecResult('') }} className="t-text-fainter t-hover-text"><X className="w-3.5 h-3.5" /></button>
          </div>
          <textarea className={inputCls + ' min-h-[56px] font-mono'} placeholder='参数 JSON，如 {"content":"你好"}' value={execParams} onChange={(e) => setExecParams(e.target.value)} />
          <button onClick={runExecute} disabled={executing} className="inline-flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50">
            <Play className="w-3 h-3" /> {executing ? '执行中...' : '执行'}
          </button>
          {execResult && <pre className="text-[11px] t-text-2 whitespace-pre-wrap break-words max-h-48 overflow-auto p-2 t-bg-app border t-border rounded-lg">{execResult}</pre>}
        </div>
      )}

      {/* 列表 */}
      <div className="space-y-2">
        <p className="text-xs t-text-faint">技能列表（{skills.length}）{!adminMode && ' · 含公共技能'}</p>
        {loading ? (
          <p className="text-xs t-text-faint text-center py-6 loading-pulse">加载中...</p>
        ) : skills.length === 0 ? (
          <p className="text-xs t-text-fainter text-center py-6">暂无技能，点击「新建」创建</p>
        ) : (
          skills.map((s) => (
            <div key={s.skill_id} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg group">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs t-text-2 truncate flex-1" title={s.description}>
                  {s.is_public && <span className="text-[9px] px-1 py-0.5 rounded t-badge-accent mr-1">公共</span>}
                  {s.name}
                  {!s.enabled && <span className="text-[9px] t-text-faint ml-1">（已禁用）</span>}
                </p>
                <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-all">
                  <button onClick={() => toggleEnabled(s)} disabled={readonlyForMe(s)} className="t-text-fainter t-hover-text-accent disabled:opacity-30 disabled:cursor-not-allowed" title={readonlyForMe(s) ? '公共技能只读' : s.enabled ? '禁用' : '启用'}>
                    <Power className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => { setExecId(s.skill_id); setExecResult(''); setExecParams(defaultParamsFor(s)) }} className="t-text-fainter t-hover-text-accent" title="测试执行">
                    <Play className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => openEdit(s)} disabled={readonlyForMe(s)} className="t-text-fainter t-hover-text-accent disabled:opacity-30 disabled:cursor-not-allowed" title={readonlyForMe(s) ? '公共技能只读' : '编辑'}>
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => handleDelete(s)} disabled={readonlyForMe(s)} className="t-text-fainter t-hover-text-danger disabled:opacity-30 disabled:cursor-not-allowed" title={readonlyForMe(s) ? '公共技能只读' : '删除'}>
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <p className="text-[10px] t-text-faint mt-1 truncate">{s.description || '无描述'} · {s.executor}</p>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default SkillsTab
