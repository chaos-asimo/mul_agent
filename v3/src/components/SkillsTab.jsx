import { useState, useEffect, useCallback } from 'react'
import { Wand2, Plus, Trash2, Pencil, Play, Power, X, RefreshCw, Globe, Upload, Package, Link2, Maximize2 } from 'lucide-react'
import { apiGet, apiPost, apiPut, apiDelete, apiUpload } from '../api/client'
import { useAuthStore } from '../stores/authStore'
import MarkdownContent from './MarkdownContent'
import Modal from './Modal'

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
  const [resultMax, setResultMax] = useState(false)
  const [executing, setExecuting] = useState(false)

  // 管理员：公共技能管理
  const [adminMode, setAdminMode] = useState(false)

  // 导入标准 SKILL.md 技能包
  const [showImport, setShowImport] = useState(false)
  const [importMode, setImportMode] = useState('paste') // paste | upload | url
  const [importContent, setImportContent] = useState('')
  const [importUrl, setImportUrl] = useState('')
  const [importFile, setImportFile] = useState(null)
  const [importPreview, setImportPreview] = useState(null)
  const [importParsed, setImportParsed] = useState(null)
  const [importPublic, setImportPublic] = useState(false)
  const [importBusy, setImportBusy] = useState(false)
  const [importMsg, setImportMsg] = useState('')

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

  // 管理员：切换技能是否公共
  const togglePublic = async (s) => {
    try {
      const res = await apiPost(`/admin/skill/${s.skill_id}/public`, { is_public: !s.is_public })
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
        // 字符串直接作为 markdown 渲染；对象/数组包装为 json 代码块，走与聊天一致的渲染管线
        const raw = res.result
        setExecResult(typeof raw === 'string' ? raw : '```json\n' + JSON.stringify(raw, null, 2) + '\n```')
      } else {
        setExecResult('> **执行失败**\n\n' + (res.error || '未知错误'))
      }
    } catch (e) {
      setExecResult('> **执行失败**\n\n' + e.message)
    } finally {
      setExecuting(false)
    }
  }

  const inputCls = 'w-full px-3 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text t-placeholder t-focus'

  // ===== 导入标准技能包 =====
  const openImport = () => {
    setShowImport(true); setImportMode('paste'); setImportContent(''); setImportUrl('')
    setImportFile(null); setImportPreview(null); setImportParsed(null)
    setImportPublic(false); setImportMsg('')
  }
  const closeImport = () => { setShowImport(false); setImportBusy(false); setImportMsg('') }

  const callImport = async (confirm) => {
    setImportBusy(true); setImportMsg('')
    try {
      let res
      if (importMode === 'paste') {
        if (!importContent.trim()) { setImportMsg('请粘贴 SKILL.md 内容'); setImportBusy(false); return }
        res = await apiPost('/skill/import', { content: importContent, is_public: importPublic, confirm })
      } else if (importMode === 'url') {
        if (!importUrl.trim()) { setImportMsg('请填写 URL'); setImportBusy(false); return }
        res = await apiPost('/skill/import/url', { url: importUrl, is_public: importPublic, confirm })
      } else {
        if (!importFile) { setImportMsg('请选择 .md 或 .zip 文件'); setImportBusy(false); return }
        const fd = new FormData()
        fd.append('file', importFile)
        fd.append('is_public', String(importPublic))
        fd.append('confirm', String(confirm))
        res = await apiUpload('/skill/import/upload', fd)
      }
      if (!res.success) { setImportMsg(res.error || '操作失败'); return }
      if (!confirm) {
        setImportPreview(res.preview); setImportParsed(res.parsed || null)
      } else {
        setImportMsg('导入成功：' + (res.preview?.name || res.skill?.name || ''))
        setImportPreview(null); setImportParsed(null)
        setImportContent(''); setImportUrl(''); setImportFile(null)
        loadSkills()
      }
    } catch (e) {
      setImportMsg('操作失败: ' + e.message)
    } finally {
      setImportBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold t-text-2 flex items-center gap-1.5">
          <Wand2 className="w-4 h-4 t-text-accent" />
          {adminMode ? '全部技能管理' : '我的技能'}
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
          <button onClick={openImport} className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border t-border-strong t-text-2 t-hover-card" title="导入标准 SKILL.md 技能包">
            <Upload className="w-3 h-3" /> 导入
          </button>
          <button onClick={loadSkills} className="p-1 rounded-lg border t-border-strong t-text-muted t-hover-card" title="刷新">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {msg && <p className="text-xs t-text-info break-all">{msg}</p>}

      {/* 导入标准技能包弹窗 */}
      {showImport && (
        <div className="space-y-2 p-3 t-bg-panel border t-border-accent/40 rounded-lg">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium t-text-accent flex items-center gap-1">
              <Package className="w-3.5 h-3.5" /> 导入标准 SKILL.md 技能包
            </span>
            <button onClick={closeImport} className="t-text-fainter t-hover-text"><X className="w-3.5 h-3.5" /></button>
          </div>
          <div className="flex items-center gap-1">
            {[
              { k: 'paste', label: '粘贴内容', icon: Package },
              { k: 'upload', label: '上传文件', icon: Upload },
              { k: 'url', label: 'URL 拉取', icon: Link2 },
            ].map((t) => (
              <button key={t.k} onClick={() => { setImportMode(t.k); setImportPreview(null); setImportMsg('') }}
                className={`inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border transition-colors ${
                  importMode === t.k ? 't-bg-accent text-white border-transparent' : 't-border-strong t-text-2 t-hover-card'
                }`}>
                <t.icon className="w-3 h-3" /> {t.label}
              </button>
            ))}
          </div>

          {importMode === 'paste' && (
            <textarea className={inputCls + ' min-h-[140px] font-mono'} placeholder={'粘贴 SKILL.md 全文，例如：\n---\nname: 我的技能\ndescription: 技能说明\n---\n# 正文指令\n...'}
              value={importContent} onChange={(e) => setImportContent(e.target.value)} />
          )}
          {importMode === 'upload' && (
            <input type="file" accept=".md,.markdown,.zip" onChange={(e) => setImportFile(e.target.files?.[0] || null)}
              className="text-[11px] t-text-2 file:mr-2 file:px-2 file:py-1 file:rounded file:border-0 file:text-[11px] file:t-bg-accent file:text-white" />
          )}
          {importMode === 'url' && (
            <input className={inputCls} placeholder="https://.../SKILL.md 或 .zip（仅 http/https）"
              value={importUrl} onChange={(e) => setImportUrl(e.target.value)} />
          )}

          {isAdmin && (
            <label className="flex items-center gap-1.5 text-[11px] t-text-2">
              <input type="checkbox" checked={importPublic} onChange={(e) => setImportPublic(e.target.checked)} />
              导入为公共技能（所有用户可用）
            </label>
          )}

          <div className="flex items-center gap-2">
            <button onClick={() => callImport(false)} disabled={importBusy}
              className="px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card disabled:opacity-50">
              解析预览
            </button>
            <button onClick={() => callImport(true)} disabled={importBusy}
              className="px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50">
              {importBusy ? '处理中...' : '确认导入'}
            </button>
          </div>

          {importMsg && <p className="text-xs t-text-info break-all">{importMsg}</p>}

          {importPreview && (
            <div className="space-y-1 p-2 t-bg-app border t-border rounded-lg text-[11px] t-text-2">
              <p><b>名称：</b>{importPreview.name}</p>
              <p><b>描述：</b>{importPreview.description || '（无）'}</p>
              <p><b>脚本：</b>{importPreview.scripts?.length ? importPreview.scripts.join(', ') : '（无）'}</p>
              <p><b>引用：</b>{importPreview.references?.length ? importPreview.references.join(', ') : '（无）'}</p>
              <p className="t-text-faint">正文摘要：{(importPreview.body_preview || '').slice(0, 160)}{(importPreview.body_preview || '').length > 160 ? '…' : ''}</p>
              <p className="t-text-accent">确认无误后点「确认导入」</p>
            </div>
          )}
        </div>
      )}

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
          {execResult && (
            <div className="text-sm t-bg-card border t-border rounded-lg overflow-hidden">
              <div className="flex items-center justify-between px-3 py-1.5 border-b t-border t-bg-app/60">
                <span className="text-[11px] t-text-faint">执行结果</span>
                <button onClick={() => setResultMax(true)} title="放大查看" className="t-text-fainter t-hover-text-accent inline-flex items-center gap-1 text-[11px]">
                  <Maximize2 className="w-3 h-3" /> 放大
                </button>
              </div>
              <div className="max-h-72 overflow-auto p-3">
                <MarkdownContent content={execResult} />
              </div>
            </div>
          )}
        </div>
      )}

      {/* 执行结果放大窗口 */}
      {resultMax && execResult && (
        <Modal title="执行结果" max onClose={() => setResultMax(false)}>
          <div className="flex-1 overflow-auto">
            <MarkdownContent content={execResult} />
          </div>
        </Modal>
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
                <p className="text-xs t-text-2 truncate flex-1 flex items-center" title={s.description}>
                  {adminMode && (
                    <button
                      onClick={() => togglePublic(s)}
                      className={`shrink-0 mr-1.5 inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded border transition-colors ${
                        s.is_public ? 't-badge-accent' : 't-border-strong t-text-faint hover:t-text-2'
                      }`}
                      title={s.is_public ? '点击设为私有' : '点击设为公共'}
                    >
                      <Globe className="w-2.5 h-2.5" />
                      {s.is_public ? '公共' : '私有'}
                    </button>
                  )}
                  {s.is_public && !adminMode && <span className="text-[9px] px-1 py-0.5 rounded t-badge-accent mr-1">公共</span>}
                  {s.config?.source === 'skillmd' && <span className="text-[9px] px-1 py-0.5 rounded border t-border-strong t-text-faint mr-1" title="导入的标准 SKILL.md 技能包">标准包</span>}
                  <span className="truncate">{s.name}</span>
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
