import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Trash2, Clock, RefreshCw, PlayCircle, History, Loader2, X, Power,
} from 'lucide-react'
import { apiGet, apiPost, apiDelete } from '../api/client'

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

function CronTab() {
  const [tasks, setTasks] = useState([])
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [viewRunsTask, setViewRunsTask] = useState(null) // {task, runs}
  const [message, setMessage] = useState('')
  const [form, setForm] = useState({
    name: '',
    task_type: 'ai',
    content: '',
    schedule: '',
    run_at: '',
    enabled: true,
    timeout: 300,
  })

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

  // 本 Tab 激活期间每 5 秒轮询运行记录，切走即停（组件卸载时清理）
  useEffect(() => {
    loadTasks()
    loadRecentRuns()
    const timer = setInterval(loadRecentRuns, 5000)
    return () => clearInterval(timer)
  }, [loadTasks, loadRecentRuns])

  const handleCreate = async (e) => {
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
      if (form.schedule.trim()) body.schedule = form.schedule.trim()
      if (form.run_at) body.run_at = form.run_at
      const result = await apiPost('/cron/add', body)
      if (result.success) {
        setShowCreate(false)
        setForm({ name: '', task_type: 'ai', content: '', schedule: '', run_at: '', enabled: true, timeout: 300 })
        loadTasks()
      } else {
        setMessage(result.error || '创建失败')
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
          <button onClick={() => setShowCreate(!showCreate)} className={btnPrimary}>
            <Plus className="w-3 h-3" />
            新建
          </button>
        </div>
      </div>

      {message && <p className="text-xs t-text-warn break-all">{message}</p>}

      {/* 新建表单 */}
      {showCreate && (
        <form onSubmit={handleCreate} className="p-3 t-bg-panel border t-border rounded-xl space-y-2.5">
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
          <div className="grid grid-cols-2 gap-2">
            <input
              className={inputCls}
              value={form.schedule}
              onChange={(e) => setForm({ ...form, schedule: e.target.value })}
              placeholder="Cron 表达式，如 */5 * * * *"
            />
            <input
              type="datetime-local"
              className={inputCls}
              value={form.run_at}
              onChange={(e) => setForm({ ...form, run_at: e.target.value })}
              title="单次执行时间"
            />
          </div>
          <label className="flex items-center gap-2 text-xs t-text-muted">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
              className="accent-indigo-500"
            />
            创建后立即启用
          </label>
          <p className="text-[10px] t-text-fainter">Cron 表达式与单次执行时间至少填一项</p>
          <div className="flex gap-2">
            <button type="submit" className="px-3 py-1.5 text-xs rounded-lg t-bg-accent t-hover-accent text-white">
              创建
            </button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
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

      {/* 单任务运行记录弹窗 */}
      {viewRunsTask && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/70"
          onClick={() => setViewRunsTask(null)}
        >
          <div
            className="t-bg-panel border t-border-strong rounded-2xl shadow-2xl w-full max-w-xl max-h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-3.5 border-b t-border">
              <h3 className="text-sm font-semibold t-text flex items-center gap-2">
                <History className="w-4 h-4 t-text-accent" />
                运行记录：{viewRunsTask.task.name}
              </h3>
              <button onClick={() => setViewRunsTask(null)} className="t-text-faint t-hover-text">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 overflow-y-auto space-y-2">
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
                    {(r.error || r.output) && (
                      <pre className="mt-1.5 max-h-32 overflow-y-auto text-[10px] t-text-muted whitespace-pre-wrap break-all">
                        {r.error ? `❌ ${r.error}` : r.output}
                      </pre>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CronTab
