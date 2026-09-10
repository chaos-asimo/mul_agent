import { useState, useEffect, useCallback, useRef } from 'react'
import {
  Plus, Trash2, Pencil, Play, CheckCircle, XCircle, RefreshCw, FileCode,
  Download, Package, Loader2, X,
} from 'lucide-react'
import { apiGet, apiPost, apiPut, apiDelete, formatSize } from '../api/client'

function Modal({ title, onClose, children, wide = false }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/70" onClick={onClose}>
      <div
        className={`t-bg-panel border t-border-strong rounded-2xl shadow-2xl w-full ${
          wide ? 'max-w-3xl' : 'max-w-xl'
        } max-h-[85vh] flex flex-col`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3.5 border-b t-border">
          <h3 className="text-sm font-semibold t-text">{title}</h3>
          <button onClick={onClose} className="t-text-faint t-hover-text">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5 overflow-y-auto">{children}</div>
      </div>
    </div>
  )
}

function ScriptsTab() {
  const [scripts, setScripts] = useState([])
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')

  // 编辑器
  const [editor, setEditor] = useState(null) // {id?, name, description, code}
  const [saving, setSaving] = useState(false)
  const [missingDeps, setMissingDeps] = useState(null)
  const [checkingDeps, setCheckingDeps] = useState(false)

  // 执行结果
  const [execResult, setExecResult] = useState(null)
  const [executing, setExecuting] = useState(null) // script_id

  // 依赖安装（异步 + 轮询）
  const [packageInput, setPackageInput] = useState('')
  const [installStatus, setInstallStatus] = useState(null)
  const [installing, setInstalling] = useState(false)
  const pollRef = useRef(null)

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const startPolling = useCallback(() => {
    if (pollRef.current) return
    pollRef.current = setInterval(async () => {
      try {
        const st = await apiGet('/script/installation-status')
        setInstallStatus(st)
        if (!st.in_progress) {
          stopPolling()
          setInstalling(false)
        }
      } catch (e) {
        console.error('查询安装状态失败:', e)
      }
    }, 5000)
  }, [])

  // Tab 卸载即停止轮询
  useEffect(() => () => stopPolling(), [])

  const loadScripts = useCallback(async () => {
    setLoading(true)
    try {
      const result = await apiGet('/script/list')
      if (result.success) setScripts(result.scripts || [])
    } catch (e) {
      console.error('加载脚本失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadFiles = useCallback(async () => {
    try {
      const result = await apiGet('/script/files/list')
      if (result.success) setFiles(result.files || [])
    } catch (e) {
      console.error('加载产物文件失败:', e)
    }
  }, [])

  // 挂载时恢复安装状态（若后台仍在安装则继续轮询）
  useEffect(() => {
    loadScripts()
    loadFiles()
    apiGet('/script/installation-status')
      .then((st) => {
        setInstallStatus(st)
        if (st.in_progress) {
          setInstalling(true)
          startPolling()
        }
      })
      .catch(() => {})
  }, [loadScripts, loadFiles, startPolling])

  const openCreate = () => {
    setMissingDeps(null)
    setEditor({ id: null, name: '', description: '', code: '' })
  }

  const openEdit = async (s) => {
    setMissingDeps(null)
    try {
      const result = await apiGet(`/script/${s.id}`)
      if (result.success) {
        const sc = result.script
        setEditor({ id: sc.id, name: sc.name, description: sc.description || '', code: sc.code })
      } else {
        setMessage(result.error || '加载脚本失败')
      }
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleSave = async () => {
    if (!editor) return
    setSaving(true)
    setMessage('')
    try {
      if (editor.id) {
        const result = await apiPut(`/script/${editor.id}`, {
          name: editor.name || undefined,
          description: editor.description,
          code: editor.code,
        })
        if (!result.success) setMessage(result.message || result.error || '更新失败')
      } else {
        const result = await apiPost('/script/create', {
          name: editor.name || undefined,
          description: editor.description,
          code: editor.code,
        })
        if (result.success) {
          if (result.syntax && !result.syntax.success) {
            setMessage(`脚本已创建，但存在语法错误：${result.syntax.error}`)
          }
        } else {
          setMessage(result.error || '创建失败')
        }
      }
      setEditor(null)
      loadScripts()
    } catch (e) {
      setMessage(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleCheckDeps = async () => {
    if (!editor?.code) return
    setCheckingDeps(true)
    try {
      const result = await apiPost('/script/check-dependencies', { code: editor.code })
      setMissingDeps(result.missing || [])
    } catch (e) {
      setMessage(e.message)
    } finally {
      setCheckingDeps(false)
    }
  }

  const handleApprove = async (s) => {
    try {
      const result = await apiPost(`/script/${s.id}/approve`)
      if (!result.success) setMessage(result.message || '操作失败')
      loadScripts()
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleRevoke = async (s) => {
    try {
      const result = await apiPost(`/script/${s.id}/revoke`)
      if (!result.success) setMessage(result.message || '操作失败')
      loadScripts()
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleDelete = async (s) => {
    if (!window.confirm(`确定删除脚本 "${s.name}" 吗？`)) return
    try {
      await apiDelete(`/script/${s.id}`)
      loadScripts()
    } catch (e) {
      setMessage(e.message)
    }
  }

  const handleExecute = async (s) => {
    setExecuting(s.id)
    setMessage('')
    try {
      const result = await apiPost('/script/execute', { script_id: s.id, timeout: 120 })
      setExecResult({ name: s.name, ...result })
      loadFiles()
      if (!result.success && result.error) setMessage(result.error)
    } catch (e) {
      setMessage(e.message)
    } finally {
      setExecuting(null)
    }
  }

  const handleInstall = async () => {
    const pkg = packageInput.trim()
    if (!pkg) return
    setMessage('')
    try {
      const result = await apiPost('/script/install-dependency-async', { package: pkg })
      if (result.success === false) {
        setMessage(result.error || '启动安装失败')
        return
      }
      setPackageInput('')
      setInstalling(true)
      setInstallStatus({ in_progress: true, package: pkg, progress: 0, output: '', success: false })
      startPolling()
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
          <FileCode className="w-4 h-4 t-text-accent" />
          脚本管理
        </h3>
        <div className="flex items-center gap-1.5">
          <button onClick={loadScripts} className={btnGhost} title="刷新">
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={openCreate} className={btnPrimary}>
            <Plus className="w-3 h-3" />
            新建
          </button>
        </div>
      </div>

      {message && <p className="text-xs t-text-warn break-all">{message}</p>}

      {/* 依赖安装 */}
      <div className="p-3 t-bg-panel border t-border rounded-xl space-y-2">
        <p className="text-xs t-text-muted flex items-center gap-1.5">
          <Package className="w-3.5 h-3.5 t-text-accent" />
          Python 依赖安装（后台异步）
        </p>
        <div className="flex gap-2">
          <input
            className={inputCls}
            value={packageInput}
            onChange={(e) => setPackageInput(e.target.value)}
            placeholder="包名，如 requests"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                handleInstall()
              }
            }}
          />
          <button
            onClick={handleInstall}
            disabled={!packageInput.trim() || installing}
            className="px-3 rounded-lg t-bg-accent t-hover-accent text-white text-xs disabled:opacity-50 whitespace-nowrap"
          >
            安装
          </button>
        </div>
        {installStatus && (installStatus.in_progress || installStatus.output) && (
          <div className="text-xs space-y-1">
            <p className={installStatus.in_progress ? 't-text-warn' : installStatus.success ? 't-text-ok' : 't-text-danger'}>
              {installStatus.in_progress
                ? `正在安装 ${installStatus.package}...（每 5 秒自动刷新）`
                : installStatus.success
                  ? `${installStatus.package} 安装成功`
                  : `${installStatus.package} 安装失败`}
            </p>
            {installStatus.output && (
              <pre className="max-h-28 overflow-y-auto t-bg-input rounded-lg p-2 text-[10px] t-text-faint whitespace-pre-wrap break-all">
                {installStatus.output}
              </pre>
            )}
          </div>
        )}
      </div>

      {/* 脚本列表 */}
      {scripts.length === 0 && !loading ? (
        <p className="text-xs t-text-fainter text-center py-6">暂无脚本，点击「新建」创建</p>
      ) : (
        <div className="space-y-2">
          {scripts.map((s) => (
            <div key={s.id} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium t-text-2 truncate flex-1" title={s.name}>
                  {s.name}
                </span>
                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded-full border shrink-0 ${
                    s.is_approved ? 't-badge-ok' : 't-badge-neutral'
                  }`}
                >
                  {s.is_approved ? '已批准' : '未批准'}
                </span>
              </div>
              {s.description && (
                <p className="text-[10px] t-text-faint mt-1 truncate" title={s.description}>
                  {s.description}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-1.5 mt-2">
                <button onClick={() => handleExecute(s)} disabled={executing === s.id} className={btnPrimary}>
                  {executing === s.id ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <Play className="w-3 h-3" />
                  )}
                  执行
                </button>
                <button onClick={() => openEdit(s)} className={btnGhost}>
                  <Pencil className="w-3 h-3" />
                  编辑
                </button>
                {s.is_approved ? (
                  <button onClick={() => handleRevoke(s)} className={btnGhost}>
                    <XCircle className="w-3 h-3" />
                    撤销
                  </button>
                ) : (
                  <button onClick={() => handleApprove(s)} className={btnGhost}>
                    <CheckCircle className="w-3 h-3" />
                    批准
                  </button>
                )}
                <button onClick={() => handleDelete(s)} className={btnDanger}>
                  <Trash2 className="w-3 h-3" />
                  删除
                </button>
              </div>
              <p className="text-[10px] t-text-fainter mt-1.5">{s.created_at}</p>
            </div>
          ))}
        </div>
      )}

      {/* 产物文件 */}
      <div>
        <p className="text-xs t-text-faint mb-2">生成的产物文件（{files.length}）</p>
        {files.length === 0 ? (
          <p className="text-[10px] t-text-fainter text-center py-3">执行脚本后生成的文件将显示在这里</p>
        ) : (
          <div className="space-y-1.5">
            {files.map((f) => (
              <a
                key={f.name}
                href={f.download_url}
                className="flex items-center gap-2 px-3 py-2 t-bg-panel border t-border rounded-lg t-hover-border-accent transition-colors"
              >
                <Download className="w-3.5 h-3.5 t-text-accent shrink-0" />
                <span className="text-xs t-text-2 truncate flex-1" title={f.name}>
                  {f.name}
                </span>
                <span className="text-[10px] t-text-faint shrink-0">{formatSize(f.size)}</span>
              </a>
            ))}
          </div>
        )}
      </div>

      {/* 编辑器弹窗 */}
      {editor && (
        <Modal title={editor.id ? '编辑脚本' : '新建脚本'} onClose={() => setEditor(null)} wide>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <input
                className={inputCls}
                value={editor.name}
                onChange={(e) => setEditor({ ...editor, name: e.target.value })}
                placeholder="脚本名称（留空自动生成）"
              />
              <input
                className={inputCls}
                value={editor.description}
                onChange={(e) => setEditor({ ...editor, description: e.target.value })}
                placeholder="脚本描述"
              />
            </div>
            <textarea
              className={inputCls + ' font-mono resize-y h-72 leading-relaxed'}
              value={editor.code}
              onChange={(e) => setEditor({ ...editor, code: e.target.value })}
              placeholder="在此粘贴或编写 Python 脚本代码..."
            />
            <div className="flex items-center justify-between">
              <button
                onClick={handleCheckDeps}
                disabled={checkingDeps || !editor.code}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card disabled:opacity-50"
              >
                {checkingDeps ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Package className="w-3.5 h-3.5" />}
                依赖检测
              </button>
              <div className="flex gap-2">
                <button
                  onClick={() => setEditor(null)}
                  className="px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card"
                >
                  取消
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving || !editor.code}
                  className="px-3 py-1.5 text-xs rounded-lg t-bg-accent t-hover-accent text-white disabled:opacity-50"
                >
                  {saving ? '保存中...' : '保存'}
                </button>
              </div>
            </div>
            {missingDeps && (
              <div className="p-3 t-bg-input border t-border rounded-lg text-xs">
                {missingDeps.length === 0 ? (
                  <p className="t-text-ok">✅ 未检测到缺失依赖</p>
                ) : (
                  <div className="space-y-1.5">
                    <p className="t-text-warn">缺失依赖：{missingDeps.join('、')}</p>
                    <div className="flex flex-wrap gap-2">
                      {missingDeps.map((dep) => (
                        <button
                          key={dep}
                          onClick={async () => {
                            try {
                              await apiPost('/script/install-dependency-async', { package: dep })
                              setEditor(null)
                              setInstalling(true)
                              setInstallStatus({ in_progress: true, package: dep, progress: 0, output: '', success: false })
                              startPolling()
                            } catch (e) {
                              setMessage(e.message)
                            }
                          }}
                          className="px-2 py-1 rounded-lg t-bg-accent t-hover-accent text-white"
                        >
                          安装 {dep}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* 执行结果弹窗 */}
      {execResult && (
        <Modal title={`执行结果：${execResult.name}`} onClose={() => setExecResult(null)} wide>
          <div className="space-y-3">
            <p className={`text-xs ${execResult.success ? 't-text-ok' : 't-text-danger'}`}>
              {execResult.success ? '✅ 执行成功' : `❌ ${execResult.error || '执行失败'}`}
            </p>
            <pre className="max-h-72 overflow-y-auto t-bg-input rounded-lg p-3 text-xs t-text-2 whitespace-pre-wrap break-all leading-relaxed">
              {execResult.result || '（无输出）'}
            </pre>
            {execResult.generated_files?.length > 0 && (
              <div>
                <p className="text-xs t-text-muted mb-1.5">生成的文件</p>
                <div className="space-y-1.5">
                  {execResult.generated_files.map((f) => (
                    <a
                      key={f.name}
                      href={f.download_url}
                      className="flex items-center gap-2 px-3 py-2 t-bg-input border t-border rounded-lg t-hover-border-accent"
                    >
                      <Download className="w-3.5 h-3.5 t-text-accent shrink-0" />
                      <span className="text-xs t-text-2 truncate flex-1">{f.name}</span>
                      <span className="text-[10px] t-text-faint">{formatSize(f.size)}</span>
                    </a>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  )
}

export default ScriptsTab
