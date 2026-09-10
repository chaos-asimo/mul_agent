import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Trash2, Bot, RefreshCw, Edit3, Brain, X, ChevronDown, ChevronRight, Target,
} from 'lucide-react'
import { apiGet, apiPost, apiPut, apiDelete } from '../api/client'

const EMPTY_FORM = { name: '', personality: '', model_name: '', avatar: '🤖', tone: '', capabilities: [] }
const EMPTY_PLAN_INPUT = { title: '', steps: '' }

const CAPABILITY_OPTIONS = [
  { key: 'web_search', label: '联网搜索', icon: '🔍', hint: '可自行搜索互联网获取最新信息' },
  { key: 'mcp', label: 'MCP 外部工具', icon: '🔧', hint: '可调用你已启用的 MCP 工具' },
]

function AgentTab() {
  const [agents, setAgents] = useState([])
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [message, setMessage] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [memoryOpenId, setMemoryOpenId] = useState(null)
  const [memories, setMemories] = useState({}) // { [agentId]: [...] }
  const [memoryInput, setMemoryInput] = useState('')
  const [planOpenId, setPlanOpenId] = useState(null)
  const [plans, setPlans] = useState({}) // { [agentId]: [...] }
  const [planInput, setPlanInput] = useState(EMPTY_PLAN_INPUT)

  const loadAgents = useCallback(async () => {
    try {
      const result = await apiGet('/agent/list')
      if (result.success) setAgents(result.agents || [])
    } catch (e) {
      console.error('加载 Agent 失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadModels = useCallback(async () => {
    try {
      const result = await apiGet('/chat/models')
      if (result.success) setModels(result.models || [])
    } catch (e) {
      console.error('加载模型列表失败:', e)
    }
  }, [])

  useEffect(() => {
    loadAgents()
    loadModels()
  }, [loadAgents, loadModels])

  const resetForm = () => {
    setForm(EMPTY_FORM)
    setEditingId(null)
    setShowForm(false)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setMessage('')
    if (!form.name.trim()) {
      setMessage('请填写 Agent 名称')
      return
    }
    try {
      const body = {
        name: form.name.trim(),
        personality: form.personality.trim(),
        model_name: form.model_name || null,
        avatar: form.avatar.trim() || '🤖',
        tone: form.tone.trim(),
        capabilities: form.capabilities,
      }
      const result = editingId
        ? await apiPut(`/agent/${editingId}`, body)
        : await apiPost('/agent/create', body)
      if (result.success) {
        resetForm()
        loadAgents()
      } else {
        setMessage(result.error || result.detail || '保存失败')
      }
    } catch (e2) {
      setMessage(e2.message)
    }
  }

  const handleEdit = (agent) => {
    setMessage('')
    setEditingId(agent.id)
    setForm({
      name: agent.name || '',
      personality: agent.role_description || '',
      model_name: agent.model_name || '',
      avatar: agent.avatar || '🤖',
      tone: agent.tone || '',
      capabilities: agent.capabilities || [],
    })
    setShowForm(true)
  }

  const handleDelete = async (agent) => {
    if (!window.confirm(`确定删除 Agent「${agent.name}」吗？其记忆将一并删除。`)) return
    try {
      await apiDelete(`/agent/${agent.id}`)
      if (memoryOpenId === agent.id) setMemoryOpenId(null)
      loadAgents()
    } catch (e) {
      setMessage(e.message)
    }
  }

  const toggleMemory = async (agent) => {
    setMessage('')
    if (memoryOpenId === agent.id) {
      setMemoryOpenId(null)
      return
    }
    setMemoryOpenId(agent.id)
    if (!memories[agent.id]) {
      try {
        const result = await apiGet(`/agent/${agent.id}/memory`)
        if (result.success) {
          setMemories((prev) => ({ ...prev, [agent.id]: result.memory || [] }))
        }
      } catch (e) {
        setMessage(e.message)
      }
    }
  }

  const handleAddMemory = async (agent) => {
    const content = memoryInput.trim()
    if (!content) return
    try {
      const result = await apiPost(`/agent/${agent.id}/add_memory`, { content })
      if (result.success) {
        setMemoryInput('')
        setMemories((prev) => ({
          ...prev,
          [agent.id]: [{ id: result.id, content, created_at: new Date().toISOString() }, ...(prev[agent.id] || [])],
        }))
      } else {
        setMessage(result.error || '添加记忆失败')
      }
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleDeleteMemory = async (agent, mem) => {
    try {
      const result = await apiDelete(`/agent/${agent.id}/memory/${mem.id}`)
      if (result.success !== false) {
        setMemories((prev) => ({
          ...prev,
          [agent.id]: (prev[agent.id] || []).filter((m) => m.id !== mem.id),
        }))
      }
    } catch (e) {
      setMessage(e.message)
    }
  }

  const togglePlan = async (agent) => {
    setMessage('')
    if (planOpenId === agent.id) {
      setPlanOpenId(null)
      return
    }
    setPlanOpenId(agent.id)
    setPlanInput(EMPTY_PLAN_INPUT)
    try {
      const result = await apiGet(`/agent/${agent.id}/plans`)
      if (result.success) {
        setPlans((prev) => ({ ...prev, [agent.id]: result.plans || [] }))
      }
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleCreatePlan = async (agent) => {
    const title = planInput.title.trim()
    if (!title) {
      setMessage('请填写计划标题')
      return
    }
    const steps = planInput.steps.split(/[\n,，;；]/).map((s) => s.trim()).filter(Boolean)
    try {
      const result = await apiPost(`/agent/${agent.id}/plans`, { title, steps })
      if (result.success) {
        setPlans((prev) => ({ ...prev, [agent.id]: [result.plan, ...(prev[agent.id] || [])] }))
        setPlanInput(EMPTY_PLAN_INPUT)
      } else {
        setMessage(result.error || '创建计划失败')
      }
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleToggleStep = async (agent, plan, idx) => {
    try {
      const result = await apiPut(`/agent/${agent.id}/plans/${plan.id}/toggle`, {
        step_index: idx,
        done: !plan.steps[idx].done,
      })
      if (result.success) {
        setPlans((prev) => ({
          ...prev,
          [agent.id]: (prev[agent.id] || []).map((p) => (p.id === plan.id ? result.plan : p)),
        }))
      } else {
        setMessage(result.error || '更新失败')
      }
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleDeletePlan = async (agent, plan) => {
    try {
      const result = await apiDelete(`/agent/${agent.id}/plans/${plan.id}`)
      if (result.success !== false) {
        setPlans((prev) => ({
          ...prev,
          [agent.id]: (prev[agent.id] || []).filter((p) => p.id !== plan.id),
        }))
      }
    } catch (e) {
      setMessage(e.message)
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
          <Bot className="w-4 h-4 t-text-accent" />
          Agent 编排
        </h3>
        <div className="flex items-center gap-1.5">
          <button onClick={loadAgents} className={btnGhost} title="刷新">
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => {
              setMessage('')
              if (showForm) resetForm()
              else {
                setEditingId(null)
                setForm(EMPTY_FORM)
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

      <p className="text-[10px] t-text-fainter leading-relaxed">
        创建专属 Agent 后，AI 对话中可自动将子任务分派给它们协作完成。每个 Agent 拥有独立人设、绑定模型和记忆。
      </p>

      {message && <p className="text-xs t-text-warn break-all">{message}</p>}

      {/* 新建/编辑表单 */}
      {showForm && (
        <form onSubmit={handleSubmit} className="p-3 t-bg-panel border t-border rounded-xl space-y-2.5">
          <div className="flex gap-2">
            <input
              className="w-14 px-2 py-2 text-center t-bg-input border t-border-strong rounded-lg text-base shrink-0"
              value={form.avatar}
              onChange={(e) => setForm({ ...form, avatar: e.target.value })}
              placeholder="🤖"
              title="头像（emoji）"
            />
            <input
              className={inputCls}
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="名称 *（如：文案专家、代码审查员）"
              required
            />
          </div>
          <textarea
            className={inputCls + ' resize-none h-20'}
            value={form.personality}
            onChange={(e) => setForm({ ...form, personality: e.target.value })}
            placeholder="人设/职责描述（如：你是一位资深文案策划，擅长撰写简洁有力的营销文案）"
          />
          <input
            className={inputCls}
            value={form.tone}
            onChange={(e) => setForm({ ...form, tone: e.target.value })}
            placeholder="语气风格（如：幽默轻松 / 严谨专业 / 简洁直接），可选"
          />
          <div>
            <p className="text-[10px] t-text-faint mb-1">工具能力（该 Agent 被分派任务时可自行使用）：</p>
            <div className="space-y-1">
              {CAPABILITY_OPTIONS.map((opt) => {
                const checked = form.capabilities.includes(opt.key)
                return (
                  <label
                    key={opt.key}
                    className="flex items-center gap-2 px-2 py-1.5 rounded-lg border t-border t-bg-input cursor-pointer t-hover-card"
                    title={opt.hint}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {
                        setForm({
                          ...form,
                          capabilities: checked
                            ? form.capabilities.filter((c) => c !== opt.key)
                            : [...form.capabilities, opt.key],
                        })
                      }}
                      className="accent-current"
                    />
                    <span className="text-xs t-text-2">{opt.icon} {opt.label}</span>
                    <span className="text-[10px] t-text-fainter ml-auto">{opt.hint}</span>
                  </label>
                )
              })}
            </div>
          </div>
          <select
            value={form.model_name}
            onChange={(e) => setForm({ ...form, model_name: e.target.value })}
            className={inputCls}
          >
            <option value="">使用默认模型</option>
            {models.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name}（{m.provider}）
              </option>
            ))}
          </select>
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

      {/* Agent 列表 */}
      {agents.length === 0 && !loading ? (
        <div className="text-center py-8">
          <Bot className="w-8 h-8 t-text-fainter mx-auto mb-2" />
          <p className="text-xs t-text-fainter">暂无 Agent，创建一个用于任务分派</p>
        </div>
      ) : (
        <div className="space-y-2">
          {agents.map((agent) => (
            <div key={agent.id} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium t-text-2 truncate flex-1 flex items-center gap-1.5" title={agent.name}>
                  <span className="text-base shrink-0">{agent.avatar || '🤖'}</span>
                  <span className="truncate">{agent.name}</span>
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded-full border t-badge-accent shrink-0">
                  {agent.model_name || '默认模型'}
                </span>
              </div>
              {agent.role_description && (
                <p className="text-[10px] t-text-fainter mt-1 break-all line-clamp-2">
                  {agent.role_description}
                </p>
              )}
              {agent.tone && (
                <p className="text-[10px] t-text-faint mt-0.5">语气：{agent.tone}</p>
              )}
              {(agent.capabilities || []).length > 0 && (
                <div className="flex flex-wrap gap-1 mt-1">
                  {(agent.capabilities || []).map((c) => {
                    const opt = CAPABILITY_OPTIONS.find((o) => o.key === c)
                    if (!opt) return null
                    return (
                      <span
                        key={c}
                        className="text-[10px] px-1.5 py-0.5 rounded-full border t-border t-text-muted"
                        title={opt.hint}
                      >
                        {opt.icon} {opt.label}
                      </span>
                    )
                  })}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                <button onClick={() => toggleMemory(agent)} className={btnGhost}>
                  {memoryOpenId === agent.id ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  <Brain className="w-3 h-3" />
                  记忆
                </button>
                <button onClick={() => togglePlan(agent)} className={btnGhost}>
                  {planOpenId === agent.id ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                  <Target className="w-3 h-3" />
                  计划
                </button>
                <button onClick={() => handleEdit(agent)} className={btnGhost}>
                  <Edit3 className="w-3 h-3" />
                  编辑
                </button>
                <button onClick={() => handleDelete(agent)} className={btnDanger}>
                  <Trash2 className="w-3 h-3" />
                  删除
                </button>
              </div>

              {/* 记忆区 */}
              {memoryOpenId === agent.id && (
                <div className="mt-2 p-2 rounded-lg border t-border t-bg-input space-y-1.5">
                  <div className="flex gap-1.5">
                    <input
                      className="flex-1 min-w-0 px-2 py-1 t-bg-panel border t-border-strong rounded-lg text-[11px] t-text t-placeholder"
                      value={memoryInput}
                      onChange={(e) => setMemoryInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          handleAddMemory(agent)
                        }
                      }}
                      placeholder="添加记忆内容，回车确认"
                    />
                    <button onClick={() => handleAddMemory(agent)} className={btnPrimary}>
                      <Plus className="w-3 h-3" />
                    </button>
                  </div>
                  {(memories[agent.id] || []).length === 0 ? (
                    <p className="text-[10px] t-text-fainter text-center py-1">暂无记忆</p>
                  ) : (
                    <div className="space-y-1 max-h-40 overflow-y-auto">
                      {(memories[agent.id] || []).map((mem) => (
                        <div key={mem.id} className="flex items-start gap-1.5 group">
                          <p className="text-[10px] t-text-muted flex-1 min-w-0 break-all">
                            {mem.source === 'auto' && (
                              <span className="t-text-accent mr-1" title="子Agent自动沉淀">⚡</span>
                            )}
                            {mem.content}
                          </p>
                          <button
                            onClick={() => handleDeleteMemory(agent, mem)}
                            className="t-text-faint t-hover-text-danger opacity-0 group-hover:opacity-100 transition-all shrink-0"
                            title="删除记忆"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* 计划区 */}
              {planOpenId === agent.id && (
                <div className="mt-2 p-2 rounded-lg border t-border t-bg-input space-y-1.5">
                  <div className="flex gap-1.5">
                    <input
                      className="flex-1 min-w-0 px-2 py-1 t-bg-panel border t-border-strong rounded-lg text-[11px] t-text t-placeholder"
                      value={planInput.title}
                      onChange={(e) => setPlanInput({ ...planInput, title: e.target.value })}
                      placeholder="计划目标（如：完成品牌口号设计）"
                    />
                  </div>
                  <div className="flex gap-1.5">
                    <input
                      className="flex-1 min-w-0 px-2 py-1 t-bg-panel border t-border-strong rounded-lg text-[11px] t-text t-placeholder"
                      value={planInput.steps}
                      onChange={(e) => setPlanInput({ ...planInput, steps: e.target.value })}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault()
                          handleCreatePlan(agent)
                        }
                      }}
                      placeholder="步骤，用逗号分隔（如：写初稿，润色，交付）"
                    />
                    <button onClick={() => handleCreatePlan(agent)} className={btnPrimary}>
                      <Plus className="w-3 h-3" />
                    </button>
                  </div>
                  {(plans[agent.id] || []).length === 0 ? (
                    <p className="text-[10px] t-text-fainter text-center py-1">
                      暂无计划；Agent 执行任务时会自动参考并推进这里的计划
                    </p>
                  ) : (
                    <div className="space-y-1.5 max-h-48 overflow-y-auto">
                      {(plans[agent.id] || []).map((plan) => (
                        <div key={plan.id} className="p-1.5 rounded-lg border t-border t-bg-panel">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`text-[10px] font-medium flex-1 min-w-0 break-all ${plan.status === 'done' ? 't-text-faint line-through' : 't-text-2'}`}
                            >
                              {plan.status === 'done' ? '✅ ' : '🎯 '}
                              {plan.title}
                            </span>
                            <button
                              onClick={() => handleDeletePlan(agent, plan)}
                              className="t-text-faint t-hover-text-danger shrink-0"
                              title="删除计划"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          </div>
                          <div className="mt-1 space-y-0.5">
                            {(plan.steps || []).map((s, idx) => (
                              <button
                                key={idx}
                                onClick={() => handleToggleStep(agent, plan, idx)}
                                className="flex items-center gap-1.5 w-full text-left group"
                              >
                                <span className={`shrink-0 ${s.done ? 't-text-accent' : 't-text-faint'}`}>
                                  {s.done ? '☑' : '☐'}
                                </span>
                                <span
                                  className={`text-[10px] break-all ${s.done ? 't-text-faint line-through' : 't-text-muted'}`}
                                >
                                  {s.text}
                                </span>
                              </button>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default AgentTab
