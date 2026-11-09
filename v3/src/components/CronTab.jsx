import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Trash2, Clock, RefreshCw, PlayCircle, History, Loader2, X, Power, Pencil,
} from 'lucide-react'
import { apiGet, apiPost, apiPut, apiDelete } from '../api/client'
import Modal from './Modal'
import MarkdownContent from './MarkdownContent'

function formatRunTime(ts) {
  if (!ts) return '-'
  const date = new Date(ts)
  if (isNaN(date.getTime())) return ts
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

const STATUS_STYLES = {
  success: 't-badge-ok',
  failed: 't-badge-danger',
  timeout: 't-badge-warn',
  running: 't-badge-info',
}

function statusStyle(status) {
  return STATUS_STYLES[status] || 't-badge-neutral'
}

// ====== 简易调度模式（参考 v1 设计）：频率下拉 → 自动生成 cron ======
const FREQ_OPTIONS = [
  { value: 'every_minute', label: '每分钟' },
  { value: 'every_n_minute', label: '每 N 分钟' },
  { value: 'every_hour', label: '每小时' },
  { value: 'every_n_hour', label: '每 N 小时' },
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每周' },
  { value: 'monthly', label: '每月' },
]

function buildCronFromSimple(simple) {
  const { freq, interval, time, weekday, day } = simple
  const [hStr, mStr] = (time || '09:00').split(':')
  const hour = parseInt(hStr) || 0
  const minute = parseInt(mStr) || 0
  const n = Math.max(1, parseInt(interval) || 5)
  const d = Math.max(1, Math.min(31, parseInt(day) || 1))
  switch (freq) {
    case 'every_minute':   return '* * * * *'
    case 'every_n_minute': return `*/${n} * * * *`
    case 'every_hour':     return '0 * * * *'
    case 'every_n_hour':   return `0 */${n} * * *`
    case 'daily':          return `${minute} ${hour} * * *`
    case 'weekly':         return `${minute} ${hour} * * ${weekday}`
    case 'monthly':        return `${minute} ${hour} ${d} * *`
    default:               return '* * * * *'
  }
}

function parseCronToSimple(expr) {
  const raw = (expr || '').trim()
  if (!raw) return null
  const parts = raw.split(/\s+/)
  if (parts.length !== 5) return null
  const [m, h, dom, mo, dow] = parts
  let matched = null
  if (m === '*' && h === '*' && dom === '*' && mo === '*' && dow === '*') {
    matched = { freq: 'every_minute' }
  } else if (/^\*\/\d+$/.test(m) && h === '*' && dom === '*' && mo === '*' && dow === '*') {
    matched = { freq: 'every_n_minute', interval: parseInt(m.slice(2)) }
  } else if (m === '0' && h === '*' && dom === '*' && mo === '*' && dow === '*') {
    matched = { freq: 'every_hour' }
  } else if (m === '0' && /^\*\/\d+$/.test(h) && dom === '*' && mo === '*' && dow === '*') {
    matched = { freq: 'every_n_hour', interval: parseInt(h.slice(2)) }
  } else if (/^\d+$/.test(m) && /^\d+$/.test(h) && dom === '*' && mo === '*' && dow === '*') {
    matched = { freq: 'daily', minute: parseInt(m), hour: parseInt(h) }
  } else if (/^\d+$/.test(m) && /^\d+$/.test(h) && dom === '*' && mo === '*' && /^\d+$/.test(dow)) {
    matched = { freq: 'weekly', minute: parseInt(m), hour: parseInt(h), weekday: dow }
  } else if (/^\d+$/.test(m) && /^\d+$/.test(h) && /^\d+$/.test(dom) && mo === '*' && dow === '*') {
    matched = { freq: 'monthly', minute: parseInt(m), hour: parseInt(h), day: parseInt(dom) }
  }
  if (!matched) return null
  const pad = (n) => String(n).padStart(2, '0')
  return {
    freq: matched.freq,
    interval: matched.interval ?? 5,
    time: ('minute' in matched && 'hour' in matched) ? `${pad(matched.hour)}:${pad(matched.minute)}` : '09:00',
    weekday: matched.weekday ?? '1',
    day: matched.day ?? 1,
  }
}

const DEFAULT_FORM = {
  name: '',
  task_type: 'ai',
  content: '',
  schedule: '',
  run_at: '',
  enabled: true,
  timeout: 300,
}
const DEFAULT_SIMPLE = {
  freq: 'every_n_minute',
  interval: 5,
  time: '09:00',
  weekday: '1',
  day: 1,
}

function CronTab() {
  const [tasks, setTasks] = useState([])
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null) // null=新建，否则编辑
  const [cronMode, setCronMode] = useState('simple') // simple | advanced | once
  const [viewRunsTask, setViewRunsTask] = useState(null)
  const [message, setMessage] = useState('')
  const [form, setForm] = useState(DEFAULT_FORM)
  const [simple, setSimple] = useState(DEFAULT_SIMPLE)

  const loadTasks = useCallback(async () => {
    try {
      const result = await apiGet('/cron/list')
      if (result.success) setTasks(result.tasks || [])
    } catch (e) {
      console.error('加载任务失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadRecentRuns = useCallback(async () => {
    try {
      const result = await apiGet('/cron/runs/recent?limit=20')
      if (result.success) setRuns(result.runs || [])
    } catch (e) {
      console.error('加载运行记录失败:', e)
    }
  }, [])

  useEffect(() => {
    loadTasks()
    loadRecentRuns()
    const timer = setInterval(loadRecentRuns, 5000)
    return () => clearInterval(timer)
  }, [loadTasks, loadRecentRuns])

  // 简易模式参数变化时自动同步 cron 表达式
  useEffect(() => {
    if (cronMode === 'simple') {
      setForm((f) => ({ ...f, schedule: buildCronFromSimple(simple) }))
    }
  }, [simple, cronMode])

  const resetForm = () => {
    setForm(DEFAULT_FORM)
    setSimple(DEFAULT_SIMPLE)
    setCronMode('simple')
    setEditingId(null)
  }

  const openCreate = () => {
    resetForm()
    setShowForm(true)
  }

  const openEdit = (task) => {
    setForm({
      name: task.name,
      task_type: task.task_type,
      content: task.content,
      schedule: task.schedule || '',
      run_at: task.run_at || '',
      enabled: !!task.enabled,
      timeout: task.timeout,
    })
    if (task.run_at) {
      setCronMode('once')
    } else {
      const parsed = parseCronToSimple(task.schedule)
      if (parsed) {
        setSimple(parsed)
        setCronMode('simple')
      } else {
        setCronMode('advanced')
      }
    }
    setEditingId(task.id)
    setShowForm(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setMessage('')
    try {
      const body = {
        name: form.name,
        task_type: form.task_type,
        content: form.content,
        enabled: form.enabled,
        timeout: Number(form.timeout) || 300,
      }
      if (cronMode === 'once') {
        if (!form.run_at) { setMessage('请选择单次执行时间'); return }
        body.run_at = form.run_at
      } else {
        const expr = cronMode === 'simple' ? buildCronFromSimple(simple) : form.schedule.trim()
        if (!expr) { setMessage('请填写 Cron 表达式或切换到单次执行'); return }
        body.schedule = expr
      }

      const result = editingId
        ? await apiPut(`/cron/${editingId}`, body)
        : await apiPost('/cron/add', body)

      if (result.success) {
        setShowForm(false)
        resetForm()
        loadTasks()
      } else {
        setMessage(result.error || (editingId ? '更新失败' : '创建失败'))
      }
    } catch (e2) {
      setMessage(e2.message)
    }
  }

  const handleToggle = async (task) => {
    setMessage('')
    try {
      const result = await apiPost(`/cron/toggle/${task.id}`)
      if (result.success) loadTasks()
      else setMessage(result.error || '操作失败')
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleRunNow = async (task) => {
    setMessage('')
    try {
      const result = await apiPost(`/cron/${task.id}/run-now`)
      if (result.success) {
        setMessage(`任务 "${task.name}" 已触发执行`)
        loadRecentRuns()
      } else {
        setMessage(result.error || '触发失败')
      }
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleDelete = async (task) => {
    if (!window.confirm(`确定删除任务 "${task.name}" 吗？`)) return
    try {
      await apiDelete(`/cron/${task.id}`)
      loadTasks()
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleViewRuns = async (task) => {
    setMessage('')
    try {
      const result = await apiGet(`/cron/${task.id}/runs?limit=50`)
      if (result.success) {
        setViewRunsTask({ task, runs: result.runs || [] })
      } else {
        setMessage(result.error || '加载运行记录失败')
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
  const modeBtn = (key) =>
    `px-2.5 py-1 text-[11px] rounded-lg border transition-colors ${
      cronMode === key
        ? 't-bg-accent text-white border-transparent'
        : 't-border-strong t-text-muted t-hover-card'
    }`

  const showN = simple.freq === 'every_n_minute' || simple.freq === 'every_n_hour'
  const showTime = simple.freq === 'daily' || simple.freq === 'weekly' || simple.freq === 'monthly'
  const showWeekday = simple.freq === 'weekly'
  const showDay = simple.freq === 'monthly'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold t-text-2 flex items-center gap-1.5">
          <Clock className="w-4 h-4 t-text-accent" />
          定时任务
        </h3>
        <div className="flex items-center gap-1.5">
          <button onClick={loadTasks} className={btnGhost} title="刷新">
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={openCreate} className={btnPrimary}>
            <Plus className="w-3 h-3" />
            新建
          </button>
        </div>
      </div>

      {message && <p className="text-xs t-text-warn break-all">{message}</p>}

      {/* 新建/编辑表单 */}
      {showForm && (
        <form onSubmit={handleSubmit} className="p-3 t-bg-panel border t-border rounded-xl space-y-2.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium t-text-2">
              {editingId ? '编辑定时任务' : '新建定时任务'}
            </span>
            <button type="button" onClick={() => setShowForm(false)} className="t-text-faint t-hover-text">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
          <input
            className={inputCls}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="任务名称 *"
            required
          />
          <div className="flex gap-2">
            <select
              value={form.task_type}
              onChange={(e) => setForm({ ...form, task_type: e.target.value })}
              className="flex-1 px-2 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text-2 outline-none"
            >
              <option value="ai">AI 任务（LLM 执行）</option>
              <option value="command">命令（白名单）</option>
            </select>
            <input
              type="number"
              className="w-24 px-2 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text outline-none"
              value={form.timeout}
              onChange={(e) => setForm({ ...form, timeout: e.target.value })}
              title="超时（秒）"
              placeholder="超时秒"
            />
          </div>
          <textarea
            className={inputCls + ' resize-none h-16'}
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            placeholder={form.task_type === 'ai' ? '描述 AI 要完成的任务 *' : '要执行的命令 *'}
            required
          />

          {/* 调度模式切换 */}
          <div className="flex items-center gap-1.5">
            <button type="button" className={modeBtn('simple')} onClick={() => setCronMode('simple')}>简易</button>
            <button type="button" className={modeBtn('advanced')} onClick={() => setCronMode('advanced')}>高级</button>
            <button type="button" className={modeBtn('once')} onClick={() => setCronMode('once')}>单次</button>
          </div>

          {cronMode === 'simple' && (
            <div className="space-y-2">
              <div className="flex gap-2">
                <select
                  value={simple.freq}
                  onChange={(e) => setSimple({ ...simple, freq: e.target.value })}
                  className="flex-1 px-2 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text-2 outline-none"
                >
                  {FREQ_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                {showN && (
                  <input
                    type="number"
                    min={1}
                    className="w-20 px-2 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text outline-none"
                    value={simple.interval}
                    onChange={(e) => setSimple({ ...simple, interval: e.target.value })}
                    title="间隔 N"
                  />
                )}
              </div>
              {showTime && (
                <input
                  type="time"
                  className={inputCls}
                  value={simple.time}
                  onChange={(e) => setSimple({ ...simple, time: e.target.value })}
                />
              )}
              {showWeekday && (
                <select
                  value={simple.weekday}
                  onChange={(e) => setSimple({ ...simple, weekday: e.target.value })}
                  className={inputCls}
                >
                  <option value="0">周日</option>
                  <option value="1">周一</option>
                  <option value="2">周二</option>
                  <option value="3">周三</option>
                  <option value="4">周四</option>
                  <option value="5">周五</option>
                  <option value="6">周六</option>
                </select>
              )}
              {showDay && (
                <input
                  type="number"
                  min={1}
                  max={31}
                  className={inputCls}
                  value={simple.day}
                  onChange={(e) => setSimple({ ...simple, day: e.target.value })}
                  title="每月第几天"
                  placeholder="日（1-31）"
                />
              )}
              <p className="text-[10px] t-text-fainter">
                生成的 Cron 表达式：<code className="t-text-accent">{buildCronFromSimple(simple)}</code>
              </p>
            </div>
          )}

          {cronMode === 'advanced' && (
            <input
              className={inputCls}
              value={form.schedule}
              onChange={(e) => setForm({ ...form, schedule: e.target.value })}
              placeholder="Cron 表达式，如 */5 * * * *"
            />
          )}

          {cronMode === 'once' && (
            <input
              type="datetime-local"
              className={inputCls}
              value={form.run_at}
              onChange={(e) => setForm({ ...form, run_at: e.target.value })}
              title="单次执行时间"
            />
          )}

          <label className="flex items-center gap-2 text-xs t-text-muted">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              className="accent-indigo-500"
            />
            保存后启用
          </label>
          <p className="text-[10px] t-text-fainter">简易/高级为周期调度，单次为一次性执行</p>
          <div className="flex gap-2">
            <button type="submit" className="px-3 py-1.5 text-xs rounded-lg t-bg-accent t-hover-accent text-white">
              {editingId ? '保存' : '创建'}
            </button>
            <button
              type="button"
              onClick={() => { setShowForm(false); resetForm() }}
              className="px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card"
            >
              取消
            </button>
          </div>
        </form>
      )}

      {/* 任务列表 */}
      {tasks.length === 0 && !loading ? (
        <p className="text-xs t-text-fainter text-center py-6">暂无定时任务</p>
      ) : (
        <div className="space-y-2">
          {tasks.map((t) => (
            <div key={t.id} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium t-text-2 truncate flex-1" title={t.name}>
                  {t.name}
                </span>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                      t.task_type === 'command' ? 't-badge-warn' : 't-badge-accent'
                    }`}
                  >
                    {t.task_type === 'command' ? '命令' : 'AI'}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                      t.enabled ? 't-badge-ok' : 't-badge-neutral'
                    }`}
                  >
                    {t.enabled ? '启用' : '禁用'}
                  </span>
                </div>
              </div>
              <p className="text-[10px] t-text-faint mt-1 break-all line-clamp-2" title={t.content}>
                {t.content}
              </p>
              <p className="text-[10px] t-text-fainter mt-1">
                {t.schedule ? `调度: ${t.schedule}` : `单次: ${t.run_at || '-'}`}
                {t.enabled && t.next_run_at ? ` · 下次: ${formatRunTime(t.next_run_at)}` : ''}
              </p>
              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                <button onClick={() => openEdit(t)} className={btnGhost}>
                  <Pencil className="w-3 h-3" />
                  编辑
                </button>
                <button onClick={() => handleToggle(t)} className={btnGhost}>
                  <Power className="w-3 h-3" />
                  {t.enabled ? '禁用' : '启用'}
                </button>
                <button onClick={() => handleRunNow(t)} disabled={!t.enabled} className={btnPrimary}>
                  <PlayCircle className="w-3 h-3" />
                  立即运行
                </button>
                <button onClick={() => handleViewRuns(t)} className={btnGhost}>
                  <History className="w-3 h-3" />
                  记录
                </button>
                <button onClick={() => handleDelete(t)} className={btnDanger}>
                  <Trash2 className="w-3 h-3" />
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 最近运行记录（5 秒轮询刷新） */}
      <div>
        <p className="text-xs t-text-faint mb-2">最近运行记录（自动刷新）</p>
        {runs.length === 0 ? (
          <p className="text-[10px] t-text-fainter text-center py-3">暂无运行记录</p>
        ) : (
          <div className="space-y-1.5">
            {runs.map((r) => (
              <div key={r.id} className="px-3 py-2 t-bg-panel border t-border rounded-lg">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs t-text-2 truncate flex-1" title={r.task_name}>
                    {r.task_name}
                  </span>
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded-full border shrink-0 ${statusStyle(r.status)}`}
                  >
                    {r.status === 'success' ? '成功' : r.status === 'failed' ? '失败' : r.status}
                  </span>
                </div>
                <p className="text-[10px] t-text-fainter mt-1">
                  {formatRunTime(r.started_at)}
                  {r.duration ? ` · 耗时 ${Number(r.duration).toFixed(1)}s` : ''}
                </p>
                {(r.error || r.output) && (
                  <p className="text-[10px] t-text-faint mt-1 line-clamp-2" title={r.error || r.output}>
                    {r.error ? `❌ ${r.error}` : r.output}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 单任务运行记录弹窗（默认最大化 + Markdown 渲染） */}
      {viewRunsTask && (
        <Modal
          title={`运行记录：${viewRunsTask.task.name}`}
          onClose={() => setViewRunsTask(null)}
          max
        >
          <div className="flex-1 overflow-y-auto space-y-2">
            {viewRunsTask.runs.length === 0 ? (
              <p className="text-xs t-text-fainter text-center py-6">该任务还没有运行记录</p>
            ) : (
              viewRunsTask.runs.map((r) => (
                <div key={r.id} className="px-3 py-2.5 t-bg-input border t-border rounded-lg">
                  <div className="flex items-center justify-between gap-2">
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded-full border shrink-0 ${statusStyle(r.status)}`}
                    >
                      {r.status === 'success' ? '成功' : r.status === 'failed' ? '失败' : r.status}
                    </span>
                    <span className="text-[10px] t-text-faint">
                      {formatRunTime(r.started_at)}
                      {r.duration ? ` · ${Number(r.duration).toFixed(1)}s` : ''}
                    </span>
                  </div>
                  {r.error ? (
                    <pre className="mt-1.5 text-[11px] t-text-danger whitespace-pre-wrap break-all">
                      {r.error}
                    </pre>
                  ) : r.output ? (
                    <div className="mt-1.5 text-[11px] t-text-muted prose-sm max-w-none">
                      <MarkdownContent content={r.output} />
                    </div>
                  ) : null}
                </div>
              ))
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}

export default CronTab
