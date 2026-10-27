import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Send, Paperclip, X, Bot, Image as ImageIcon, BookOpen, ChevronDown, ChevronUp, Download, FileText, FileImage, FileType, ShieldAlert, CheckCircle, XCircle, Loader2, Package, TerminalSquare, Cpu, Puzzle } from 'lucide-react'
import { apiGet, apiPost, apiStream, formatSize } from '../api/client'
import { isImageFile, isPdfFile, isOfficeFile, isTextFile } from '../utils/highlight'
import MarkdownContent from './MarkdownContent'
import ToolCallCard from './ToolCallCard'
import FileViewer from './FileViewer'
import { parseAssistantContent } from '../utils/parseContent'
import { exportMarkdown, exportWord, exportImage } from '../utils/export'

// 思考过程（中间步骤）：流式实时展示，完成后默认折叠
function ThinkingBlock({ thinking, streaming }) {
  const [open, setOpen] = useState(!!streaming)
  // 流式结束时自动折叠
  useEffect(() => {
    if (!streaming && open) setOpen(false)
  }, [streaming])

  if (!thinking || !thinking.trim()) return null
  const lineCount = thinking.split('\n').length

  return (
    <div className="mb-2 max-w-[85%]">
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md t-bg-panel border t-border t-text-muted text-[11px] hover:opacity-80 transition-opacity"
      >
        {streaming ? (
          <Loader2 className="w-3 h-3 animate-spin t-text-accent" />
        ) : (
          <Bot className="w-3 h-3" />
        )}
        {streaming ? '思考中…' : `思考过程 · ${lineCount} 行`}
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <div className="mt-1.5 px-3 py-2.5 rounded-lg t-bg-bubble border t-border text-xs t-text-muted whitespace-pre-wrap break-words leading-relaxed max-h-60 overflow-y-auto">
          {thinking}
          {streaming && <span className="inline-block w-2 h-3.5 bg-current animate-pulse ml-0.5" />}
        </div>
      )}
    </div>
  )
}

// 知识库参考来源（助手消息下方可折叠展示）
function KnowledgeSources({ sources }) {
  const [open, setOpen] = useState(false)
  if (!sources || sources.length === 0) return null
  return (
    <div className="mt-1.5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 px-2 py-1 rounded-md t-bg-accent-soft t-border-accent t-text-accent text-[11px] hover:opacity-80 transition-opacity"
      >
        <BookOpen className="w-3 h-3" />
        参考知识库 · {sources.length} 条
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5 max-w-[70%]">
          {sources.map((s, i) => (
            <div key={i} className="px-2.5 py-1.5 rounded-md t-bg-bubble border t-border text-[11px]">
              <div className="flex items-center justify-between gap-2">
                <span className="t-text-2 font-medium truncate">{s.filename}</span>
                <span className="t-text-fainter shrink-0">相关度 {(s.score || 0).toFixed(2)}</span>
              </div>
              <div className="t-text-faint whitespace-pre-wrap break-words mt-0.5 line-clamp-3">{s.content}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// 是否可在内嵌查看器直接打开（与 FileViewer 支持的渲染类型保持一致）：
// markdown / pdf / 图片 / Office(doc(x)/xls(x)/ppt(x)) / 文本代码
const isOpenableFile = (name) =>
  /\.md|markdown$/i.test(name || '') ||
  isPdfFile(name) || isImageFile(name) || isOfficeFile(name) || isTextFile(name)

// 本轮后台生成的产物文件：文件名点击可在线打开（不可打开的类型改为下载），
// 右侧下载图标始终保留下载功能；与「脚本」Tab 的产物文件同源。
// 点击文件名通过 onOpenFile 交给 ChatPane 根层渲染查看器（与 HITL 弹窗同级）。
function GeneratedFiles({ files, onOpenFile }) {
  if (!files || files.length === 0) return null
  return (
    <div className="mt-1.5 space-y-1.5 max-w-[78%]">
      <p className="text-[11px] t-text-faint flex items-center gap-1">
        <Package className="w-3 h-3" />
        生成的文件（{files.length}）
      </p>
      {files.map((f) => {
        const rawUrl = f.download_url
        const dlUrl = `${rawUrl}${rawUrl.includes('?') ? '&' : '?'}download=1`
        const openable = isOpenableFile(f.name)
        return (
          <div
            key={f.name}
            className="flex items-center gap-2 px-3 py-2 t-bg-panel border t-border rounded-lg t-hover-border-accent transition-colors"
            title={f.summary ? `内容简介：${f.summary}` : f.name}
          >
            {isImageFile(f.name)
              ? <ImageIcon className="w-3.5 h-3.5 t-text-accent shrink-0" />
              : <FileText className="w-3.5 h-3.5 t-text-accent shrink-0" />}
            {openable ? (
              // 可直接打开的文件（Office/PDF/图片/文本等）：点文件名在线预览
              <button
                type="button"
                onClick={() => onOpenFile({ filename: f.name, rawUrl, downloadUrl: dlUrl })}
                className="text-xs t-text-2 truncate flex-1 text-left hover:underline hover:t-text-accent cursor-pointer"
              >
                {f.name}
              </button>
            ) : (
              // 无法在内嵌查看器打开的文件：点文件名直接下载
              <a
                href={dlUrl}
                download={f.name}
                className="text-xs t-text-2 truncate flex-1 text-left hover:underline hover:t-text-accent cursor-pointer"
              >
                {f.name}
              </a>
            )}
            <span className="text-[10px] t-text-faint shrink-0">{formatSize(f.size)}</span>
            <a
              href={dlUrl}
              download={f.name}
              title="下载文件"
              className="t-text-faint hover:t-text-accent shrink-0"
            >
              <Download className="w-3.5 h-3.5" />
            </a>
          </div>
        )
      })}
    </div>
  )
}

function formatTimestamp(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  if (isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

// 字数：去掉空白后的内容长度
const countChars = (content) => (content || '').replace(/\s/g, '').length

// 助手消息内容：解析工具调用/结果，渲染为 WorkBuddy 风格卡片 + Markdown
function AssistantContent({ content, streaming }) {
  const segments = useMemo(() => parseAssistantContent(content), [content])
  // 跟踪已完成的工具调用，用于配对结果
  const callStack = []
  return (
    <div className="space-y-1">
      {segments.map((seg, idx) => {
        if (seg.type === 'text') {
          return <MarkdownContent key={idx} content={seg.content} streaming={streaming} />
        }
        if (seg.type === 'tool_call') {
          callStack.push({ name: seg.name, icon: seg.icon })
          return (
            <ToolCallCard
              key={idx}
              icon={seg.icon}
              name={seg.name}
              status="done"
            />
          )
        }
        if (seg.type === 'tool_result') {
          // 尝试与最近的工具调用配对
          const call = callStack.pop()
          return (
            <ToolCallCard
              key={idx}
              icon={call?.icon || '📋'}
              name={call?.name || '工具结果'}
              status="done"
              result={seg.content}
            />
          )
        }
        return null
      })}
    </div>
  )
}

function MessageBubble({ msg, onOpenFile }) {
  const isUser = msg.role === 'user'
  const isError = msg.role === 'error'
  const images = msg.images || []
  const bubbleRef = useRef(null)
  const [showExportMenu, setShowExportMenu] = useState(false)
  const [exporting, setExporting] = useState(false)
  const exportMenuRef = useRef(null)

  // 点击外部关闭导出菜单
  useEffect(() => {
    if (!showExportMenu) return
    const handleClickOutside = (e) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target)) {
        setShowExportMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [showExportMenu])

  const handleExport = async (type) => {
    setShowExportMenu(false)
    if (exporting) return
    setExporting(true)
    try {
      const single = [msg]
      if (type === 'markdown') {
        exportMarkdown(single)
      } else if (type === 'word') {
        await exportWord(single)
      } else if (type === 'image') {
        await exportImage(bubbleRef.current)
      }
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div ref={bubbleRef} className={`${isUser ? 'max-w-[78%]' : 'w-full'} ${isUser ? 'items-end' : 'items-start'} flex flex-col group`}>
        {images.length > 0 && (
          <div className={`flex flex-wrap gap-2 mb-2 ${isUser ? 'justify-end' : ''}`}>
            {images.map((img, i) => (
              <img
                key={i}
                src={img.data_url || img.url}
                alt={img.name || `图片${i + 1}`}
                className="max-w-[200px] max-h-[200px] rounded-lg border t-border object-cover"
              />
            ))}
          </div>
        )}
        {!isUser && !isError && (
          <ThinkingBlock thinking={msg.thinking} streaming={msg.streaming} />
        )}
        <div
            className={`px-4 py-3 rounded-xl text-sm ${
              isUser
                ? 't-bg-accent text-white rounded-br-none'
                : isError
                  ? 't-bg-danger-soft border t-border-danger t-text-danger rounded-bl-none'
                  : 't-bg-bubble t-text border t-border rounded-bl-none'
            }`}
          >
            {isUser || isError ? (
              <div className="whitespace-pre-wrap break-words leading-relaxed">{msg.content}</div>
            ) : (
              <AssistantContent content={msg.content} streaming={msg.streaming} />
            )}
          </div>
        {!isUser && !isError && (
          <GeneratedFiles files={msg.files} onOpenFile={onOpenFile} />
        )}
        {!isUser && !isError && (
          <KnowledgeSources sources={msg.knowledge_sources} />
        )}
        <div className={`flex items-center gap-2 mt-1 px-1 text-[10px] t-text-faint ${isUser ? 'flex-row-reverse' : ''}`}>
          {isUser || isError ? (
            <>
              <span>{formatTimestamp(msg.timestamp)}</span>
              {msg.seq != null && (
                <span className="t-text-fainter">
                  ({msg.seq}号/{countChars(msg.content)}字)
                </span>
              )}
            </>
          ) : (
            <>
              {msg.seq != null && (
                <span className="t-text-fainter">
                  ({msg.seq}号/{countChars(msg.content)}字)
                </span>
              )}
              {msg.model_name && (
                <span className="t-text-fainter">
                  模型: {msg.model_name}
                  {msg.token_stats && (msg.token_stats.prompt_tokens > 0 || msg.token_stats.completion_tokens > 0) && (
                    <> | 输入 {msg.token_stats.prompt_tokens} → 输出 {msg.token_stats.completion_tokens} tokens{msg.token_stats.tokens_per_second > 0 ? ` (${msg.token_stats.tokens_per_second.toFixed(1)}/s)` : ''}</>
                  )}
                  {' | '}{formatTimestamp(msg.timestamp)}
                </span>
              )}
              {!msg.model_name && <span>{formatTimestamp(msg.timestamp)}</span>}
            </>
          )}
          {/* 单条消息导出按钮 */}
          <div className="relative" ref={exportMenuRef}>
            <button
              onClick={() => setShowExportMenu((v) => !v)}
              disabled={exporting}
              className="p-1 rounded hover:t-bg-accent-soft t-text-faint hover:t-text-accent disabled:opacity-50 transition-colors"
              title="导出此条消息"
            >
              <Download className="w-3 h-3" />
            </button>
            {showExportMenu && (
              <div className={`absolute ${isUser ? 'right-0' : 'left-0'} bottom-full mb-1 w-32 t-bg-panel border t-border rounded-lg shadow-lg py-1 z-50`}>
                <button
                  onClick={() => handleExport('image')}
                  className="w-full px-3 py-1.5 text-left text-xs t-text-2 hover:t-bg-accent-soft flex items-center gap-2"
                >
                  <FileImage className="w-3.5 h-3.5" />
                  导出图片
                </button>
                <button
                  onClick={() => handleExport('markdown')}
                  className="w-full px-3 py-1.5 text-left text-xs t-text-2 hover:t-bg-accent-soft flex items-center gap-2"
                >
                  <FileText className="w-3.5 h-3.5" />
                  导出 MD
                </button>
                <button
                  onClick={() => handleExport('word')}
                  className="w-full px-3 py-1.5 text-left text-xs t-text-2 hover:t-bg-accent-soft flex items-center gap-2"
                >
                  <FileType className="w-3.5 h-3.5" />
                  导出 Word
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// 流式执行中的状态指示器：解析状态文本，显示对应图标 + 动画
function StreamingIndicator({ status }) {
  if (!status) {
    return (
      <div className="typing-indicator">
        <span></span>
        <span></span>
        <span></span>
      </div>
    )
  }
  // 解析工具名
  let icon = '💭'
  let label = status
  if (status.includes('思考')) {
    icon = '💭'
    label = status.replace(/^第\s*\d+\/\d+\s*步/, '').trim()
  } else if (status.includes('搜索') || status.includes('web_search')) {
    icon = '🔍'
    label = status.includes('正在') ? status : `搜索中…`
  } else if (status.includes('脚本') || status.includes('script')) {
    icon = '📝'
  } else if (status.includes('MCP')) {
    icon = '🔌'
  } else if (status.includes('技能') || status.includes('skill')) {
    icon = '🧩'
  } else if (status.includes('工具')) {
    icon = '🔧'
  }
  return (
    <div className="flex items-center gap-2.5">
      <span className="text-base leading-none animate-pulse">{icon}</span>
      <span className="text-sm t-text-muted">{label}</span>
    </div>
  )
}

function ChatPane({
  sessionId,
  messages,
  setMessages,
  onSessionCreated,
  onRefreshSessions,
  pendingFiles,
  onAddFiles,
  onRemoveFile,
  onFilesSent,
}) {
  const [inputValue, setInputValue] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [streamError, setStreamError] = useState('')
  const [pendingImages, setPendingImages] = useState([])
  const [streamStatus, setStreamStatus] = useState('') // 后台运行状态文本（思考中、执行工具…）
  const messagesEndRef = useRef(null)
  const scrollContainerRef = useRef(null)
  const fileInputRef = useRef(null)
  const prevMsgLenRef = useRef(0)
  const prevSessionRef = useRef(sessionId)
  const [showJumpBottom, setShowJumpBottom] = useState(false)
  const userScrolledUpRef = useRef(false) // 用户主动向上滚动后暂停自动跟随
  const isSendingRef = useRef(false) // 发送状态 ref，供 ResizeObserver 读取（避免闭包捕获旧值）
  const pendingRafRef = useRef(null)
  const [pendingConfirm, setPendingConfirm] = useState(null) // {request_id, summary, meta}
  const confirmResolverRef = useRef(null)
  const abortControllerRef = useRef(null) // 用于中断流式请求
  const [viewingFile, setViewingFile] = useState(null) // 对话中产物文件的在线查看器（根层渲染）

  useEffect(() => {
    const loadModels = async () => {
      try {
        const result = await apiGet('/chat/models')
        if (result.success && Array.isArray(result.models)) {
          setModels(result.models.map((m) => (typeof m === 'object' ? m.name : m)))
        }
      } catch (error) {
        console.error('加载模型失败:', error)
      }
    }
    loadModels()
  }, [])

  // 判断滚动容器是否在底部附近（容错小数像素）
  const isAtBottom = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return true
    return Math.ceil(el.scrollTop + el.clientHeight) >= el.scrollHeight - 80
  }, [])

  const syncJumpButton = useCallback(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const canScroll = el.scrollHeight > el.clientHeight + 80
    setShowJumpBottom(canScroll && !isAtBottom())
  }, [isAtBottom])

  // 监听滚动：用户向上滚动时暂停自动跟随，回到底部时恢复
  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const onScroll = () => {
      const atBottom = isAtBottom()
      if (!atBottom) {
        userScrolledUpRef.current = true
      } else {
        userScrolledUpRef.current = false
      }
      setShowJumpBottom(el.scrollHeight > el.clientHeight + 80 && !atBottom)
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    syncJumpButton()
    return () => el.removeEventListener('scroll', onScroll)
  }, [isAtBottom, syncJumpButton])

  // 消息变化：会话切换 / 新增消息 → 强制到底部；流式更新（长度不变）→ 用户未上滚时跟随。
  // 滚动放进 requestAnimationFrame，确保 DOM 已完成布局（规避非 iframe 下不定位底部）。
  useEffect(() => {
    const el = scrollContainerRef.current
    const len = messages.length
    const sessionChanged = sessionId !== prevSessionRef.current
    const lenChanged = len !== prevMsgLenRef.current
    prevSessionRef.current = sessionId
    prevMsgLenRef.current = len
    if (!el) return
    const forceBottom = sessionChanged || lenChanged
    // 新增消息 / 会话切换：重置用户上滚标记，恢复自动跟随
    if (forceBottom) userScrolledUpRef.current = false
    const last = messages[len - 1]
    const isStreaming = !!(last && last.role === 'assistant' && last.streaming)
    const raf = requestAnimationFrame(() => {
      // 会话切换/新增消息强制跟随；流式更新时只要用户没有主动上滚就跟随（解决"有时不自动滚"）
      if (forceBottom || (isStreaming && !userScrolledUpRef.current)) {
        el.scrollTo({ top: el.scrollHeight, behavior: 'auto' })
      }
      syncJumpButton()
    })
    return () => cancelAnimationFrame(raf)
  }, [messages, sessionId, isAtBottom, syncJumpButton])

  // ResizeObserver：流式输出导致容器高度增长时，若用户未在顶部则自动滚动到底部
  // 解决 messages 状态更新频率低于实际内容变化时 scrollHeight 已增长但 scrollTo 未执行的问题
  useEffect(() => {
    const el = scrollContainerRef.current
    if (!el) return
    const observer = new ResizeObserver(() => {
      if (pendingRafRef.current) cancelAnimationFrame(pendingRafRef.current)
      pendingRafRef.current = requestAnimationFrame(() => {
        pendingRafRef.current = null
        if (isSendingRef.current && !userScrolledUpRef.current && isAtBottom()) {
          el.scrollTop = el.scrollHeight
        }
      })
    })
    observer.observe(el)
    return () => {
      observer.disconnect()
      if (pendingRafRef.current) cancelAnimationFrame(pendingRafRef.current)
    }
  }, [isAtBottom])

  const jumpToBottom = () => {
    const el = scrollContainerRef.current
    if (!el) return
    userScrolledUpRef.current = false
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }

  // 中断后补拉：把服务端已挂载的本轮产物文件补到当前最后一条助手消息上
  const refreshLastMessageFiles = async (sid) => {
    if (!sid) return
    try {
      const result = await apiGet(`/chat/session/${sid}`)
      const serverMsgs = result.session?.messages || []
      for (let i = serverMsgs.length - 1; i >= 0; i--) {
        const m = serverMsgs[i]
        if (m.role === 'assistant' && m.files && m.files.length > 0) {
          setMessages((prev) => {
            const arr = [...prev]
            for (let j = arr.length - 1; j >= 0; j--) {
              if (arr[j].role === 'assistant') {
                arr[j] = { ...arr[j], files: m.files }
                break
              }
            }
            return arr
          })
          return
        }
      }
    } catch {
      // 补拉失败不影响主流程
    }
  }

  // 流式更新当前 assistant 消息
  const appendOrUpdateAssistant = (content, done, meta) => {
    setMessages((prev) => {
      const arr = [...prev]
      const last = arr[arr.length - 1]
      if (last && last.role === 'assistant' && last.streaming) {
        arr[arr.length - 1] = { ...last, content, streaming: !done, ...(meta || {}) }
      } else {
        arr.push({ role: 'assistant', content, timestamp: new Date().toISOString(), streaming: !done, ...(meta || {}) })
      }
      return arr
    })
  }

  const finalizeStreaming = () => {
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      if (last && last.role === 'assistant' && last.streaming) {
        return [...prev.slice(0, -1), { ...last, streaming: false }]
      }
      return prev
    })
  }

  // ---- 图片处理 ----
  const fileToDataUrl = (file) =>
    new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (e) => resolve(e.target.result)
      reader.onerror = () => resolve('')
      reader.readAsDataURL(file)
    })

  const addImageFiles = useCallback(async (files) => {
    const list = Array.from(files).filter((f) => f.type.startsWith('image/'))
    if (!list.length) return
    const max = 10 * 1024 * 1024
    const items = []
    for (const f of list) {
      if (f.size > max) {
        setStreamError(`图片「${f.name}」超过 10MB 限制`)
        continue
      }
      const data_url = await fileToDataUrl(f)
      if (data_url) items.push({ data_url, name: f.name })
    }
    if (items.length) setPendingImages((prev) => [...prev, ...items])
  }, [])

  const removeImage = (index) => {
    setPendingImages((prev) => prev.filter((_, i) => i !== index))
  }

  const handlePaste = useCallback(
    (e) => {
      const items = e.clipboardData?.items
      if (!items) return
      const imageFiles = []
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile()
          if (file) imageFiles.push(file)
        }
      }
      if (imageFiles.length) {
        e.preventDefault()
        addImageFiles(imageFiles)
      }
    },
    [addImageFiles]
  )

  const sendMessage = async () => {
    const message = inputValue.trim()
    if ((!message && pendingFiles.length === 0 && pendingImages.length === 0) || isSending) return

    setIsSending(true)
    isSendingRef.current = true
    setStreamError('')
    setStreamStatus('')

    const parts = []
    if (message) parts.push(message)
    if (pendingFiles.length > 0)
      parts.push(`📎 已上传文件: ${pendingFiles.map((f) => f.filename).join(', ')}`)
    if (pendingImages.length > 0) parts.push(`🖼️ 附带 ${pendingImages.length} 张图片`)
    const displayMessage = parts.join('\n\n')

    setMessages((prev) => [
      ...prev,
      {
        role: 'user',
        content: displayMessage,
        images: pendingImages.length > 0 ? pendingImages : undefined,
        timestamp: new Date().toISOString(),
      },
    ])

    let assistantContent = ''
    let thinkingText = ''
    let newSessionId = null
    let hadError = false

    // 创建 AbortController，支持用户点击「停止」中断流式请求
    const controller = new AbortController()
    abortControllerRef.current = controller

    try {
      const response = await apiStream(
        '/chat/stream',
        {
          message: message || '请分析我上传的图片/文件',
          session_id: sessionId || undefined,
          model_name: selectedModel || undefined,
          files:
            pendingFiles.length > 0
              ? pendingFiles.map(({ filename, content }) => ({ filename, content }))
              : undefined,
          images: pendingImages.length > 0 ? pendingImages : undefined,
        },
        controller.signal,
      )

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed.startsWith('data:')) continue
          try {
            const data = JSON.parse(trimmed.substring(5).trim())
            if (data.success === false) {
              hadError = true
              finalizeStreaming()
              setStreamError(data.error || '请求失败')
              continue
            }
            if (data.session_id) newSessionId = data.session_id
            if (data.type === 'status' && data.text != null) {
              // 后台运行状态：思考中、执行工具… → 替换静默的 typing 提示
              setStreamStatus(data.text)
              continue
            }
            if (data.type === 'confirm' && data.request_id) {
              // 中等/高风险工具需要用户确认：弹窗并等待用户选择
              setPendingConfirm({
                request_id: data.request_id,
                summary: data.summary,
                meta: data.meta || {},
              })
              const approved = await new Promise((resolve) => {
                confirmResolverRef.current = resolve
              })
              confirmResolverRef.current = null
              setPendingConfirm(null)
              try {
                await apiPost('/chat/confirm', {
                  request_id: data.request_id,
                  approved,
                })
              } catch (e) {
                console.error('确认回调失败:', e)
              }
              continue
            }
            if (data.type === 'thinking' && data.content) {
              // 中间步骤的思考过程：实时展示在折叠区
              thinkingText += data.content
              appendOrUpdateAssistant(assistantContent, false, { thinking: thinkingText })
              continue
            }
            if (data.type === 'reclassify' && data.to === 'thinking') {
              // 中间步骤修正：把已流式输出的 content 归入 thinking 折叠区
              thinkingText += assistantContent
              assistantContent = ''
              appendOrUpdateAssistant(assistantContent, false, { thinking: thinkingText })
              continue
            }
            if (data.content) {
              // 收到实际内容输出后，状态条不再需要（下一状态事件会重新设置）
              setStreamStatus('')
              assistantContent += data.content
              appendOrUpdateAssistant(assistantContent, false)
            }
            if (data.done) {
              setStreamStatus('')
              const meta = {}
              if (data.model_name) meta.model_name = data.model_name
              if (data.token_stats) meta.token_stats = data.token_stats
              if (data.knowledge_sources && data.knowledge_sources.length > 0) {
                meta.knowledge_sources = data.knowledge_sources
              }
              if (data.files && data.files.length > 0) {
                meta.files = data.files
              }
              if (thinkingText) {
                meta.thinking = thinkingText
              }
              appendOrUpdateAssistant(assistantContent, true, meta)
            }
          } catch (e) {
            // 忽略无法解析的行
          }
        }
      }

      if (assistantContent) {
        finalizeStreaming()
      }
    } catch (error) {
      // 用户主动点击「停止」触发的 abort，不视为错误
      if (error.name === 'AbortError') {
        if (assistantContent) {
          finalizeStreaming()
        }
        // 中断时 done 事件不会到达：从会话详情补拉本轮已产出文件（后端在 finally 中已挂载）
        refreshLastMessageFiles(newSessionId || sessionId)
      } else {
        console.error('发送消息失败:', error)
        finalizeStreaming()
        setStreamError(`发送失败: ${error.message}`)
      }
    } finally {
      setInputValue('')
      setPendingImages([])
      onFilesSent?.()
      setIsSending(false)
      isSendingRef.current = false
      setStreamStatus('')
      abortControllerRef.current = null
      if (newSessionId && newSessionId !== sessionId) {
        onSessionCreated?.(newSessionId)
      } else {
        onRefreshSessions?.()
      }
    }
  }

  // 停止当前流式请求：中断 fetch 流
  const stopMessage = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }

  // 计算每条消息在同角色内的序号
  let userSeq = 0
  let assistantSeq = 0
  const renderedMessages = messages.map((msg) => {
    if (msg.role === 'user') {
      userSeq += 1
      return { ...msg, seq: userSeq }
    }
    if (msg.role === 'assistant') {
      assistantSeq += 1
      return { ...msg, seq: assistantSeq }
    }
    return { ...msg, seq: null }
  })

  const isEmpty = renderedMessages.length === 0

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* 消息区 */}
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full t-text-fainter">
            <div className="w-20 h-20 rounded-full t-bg-panel flex items-center justify-center mb-4 border t-border">
              <Bot className="w-10 h-10 t-text-faint" />
            </div>
            <p className="text-lg font-medium t-text-muted">开始与龙虾Claw对话</p>
            <p className="text-sm">输入消息发送，或在右侧「文件」面板上传附件</p>
          </div>
        ) : (
          renderedMessages.map((msg, index) => <MessageBubble key={index} msg={msg} onOpenFile={setViewingFile} />)
        )}
        {isSending && !renderedMessages.some((m) => m.role === 'assistant' && m.streaming) && (
          <div className="flex justify-start">
            <div className="px-4 py-3 rounded-xl t-bg-bubble border t-border rounded-bl-none flex items-center gap-3 min-w-[200px]">
              <StreamingIndicator status={streamStatus} />
            </div>
          </div>
        )}
        {/* 流式气泡已存在时的后台状态条：脚本执行/依赖安装等长操作期间保持可见 */}
        {isSending && streamStatus && renderedMessages.some((m) => m.role === 'assistant' && m.streaming) && (
          <div className="flex justify-start">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full t-bg-bubble border t-border t-text-muted text-xs shadow-sm">
              <Loader2 className="w-3.5 h-3.5 animate-spin t-text-accent" />
              <span>{streamStatus}</span>
            </div>
          </div>
        )}
        <div className="flex justify-end">
          {showJumpBottom && (
            <button
              onClick={jumpToBottom}
              title="滚动到底部"
              className="sticky bottom-4 w-8 h-8 rounded-full t-bg-panel border t-border shadow-lg flex items-center justify-center t-text-muted hover:t-text-accent transition-colors"
            >
              <ChevronDown className="w-4 h-4" />
            </button>
          )}
        </div>
        <div ref={messagesEndRef} />
      </div>

      {/* 输入区 */}
      <div className="border-t t-border p-4 shrink-0 t-bg-app">
        {streamError && (
          <div className="mb-3 p-2.5 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-xs flex items-start justify-between gap-2">
            <span>{streamError}</span>
            <button onClick={() => setStreamError('')} className="t-hover-text-danger shrink-0">
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {pendingFiles.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {pendingFiles.map((file, index) => (
              <span
                key={index}
                className="inline-flex items-center gap-2 px-3 py-1 t-bg-accent-soft border t-border-accent t-text-accent rounded-full text-xs"
              >
                <Paperclip className="w-3 h-3" />
                {file.filename}
                <button onClick={() => onRemoveFile(index)} className="t-hover-text-danger">
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}

        {pendingImages.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {pendingImages.map((img, index) => (
              <div key={index} className="relative group">
                <img
                  src={img.data_url}
                  alt={img.name}
                  className="w-20 h-20 object-cover rounded-lg border t-border"
                />
                <button
                  onClick={() => removeImage(index)}
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full t-bg-danger text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2.5">
          <div className="flex flex-col gap-1.5">
            <label
              className="p-2 border t-border-strong rounded-lg cursor-pointer t-hover-card transition-colors t-text-muted"
              title="上传文件"
            >
              <Paperclip className="w-4 h-4" />
              <input
                type="file"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) onAddFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </label>
            <label
              className="p-2 border t-border-strong rounded-lg cursor-pointer t-hover-card transition-colors t-text-muted"
              title="上传图片（或直接粘贴）"
            >
              <ImageIcon className="w-4 h-4" />
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) addImageFiles(e.target.files)
                  e.target.value = ''
                }}
              />
            </label>
          </div>

          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onPaste={handlePaste}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                sendMessage()
              }
            }}
            placeholder="输入你的问题或命令...（Enter 发送，Shift+Enter 换行，可粘贴图片）"
            className="flex-1 px-4 py-3 t-bg-input border t-border-strong rounded-xl resize-none min-h-[80px] max-h-[200px] text-sm t-text t-placeholder t-focus transition-all"
          />

          <div className="flex flex-col gap-2">
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="px-2.5 py-2.5 t-bg-input border t-border-strong rounded-xl text-xs t-text-2 t-focus max-w-[140px]"
            >
              <option value="">默认模型</option>
              {models.map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
            <button
              onClick={isSending ? stopMessage : sendMessage}
              title={isSending ? '停止生成' : '发送'}
              className={`p-3 rounded-xl transition-colors flex items-center justify-center ${
                isSending
                  ? 't-bg-danger t-hover-danger text-white'
                  : 't-bg-accent t-hover-accent text-white disabled:opacity-50'
              }`}
            >
              {isSending ? (
                <X className="w-5 h-5" />
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* 对话中产物文件的在线查看器（根层渲染，与 HITL 弹窗同级） */}
      {viewingFile && (
        <FileViewer
          filename={viewingFile.filename}
          rawUrl={viewingFile.rawUrl}
          downloadUrl={viewingFile.downloadUrl}
          onClose={() => setViewingFile(null)}
        />
      )}

      {/* HITL 工具执行确认弹窗 */}
      {pendingConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => confirmResolverRef.current?.(false)}>
          <div
            className="w-[90%] max-w-lg t-bg-panel border t-border rounded-2xl shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 头部：图标 + 工具名 + 风险标签 */}
            <div className="px-5 py-4 border-b t-border flex items-center gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                pendingConfirm.meta?.risk === 'high'
                  ? 't-bg-danger-soft t-text-danger'
                  : 't-bg-accent-soft t-text-accent'
              }`}>
                {pendingConfirm.meta?.tool === 'run_python_script'
                  ? <TerminalSquare className="w-5 h-5" />
                  : pendingConfirm.meta?.tool === 'call_mcp_tool'
                  ? <Cpu className="w-5 h-5" />
                  : <ShieldAlert className="w-5 h-5" />}
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold t-text truncate">
                  {pendingConfirm.meta?.tool || '工具执行'}
                </h3>
                <p className="text-[11px] t-text-faint mt-0.5">
                  需要你的确认后才能继续
                </p>
              </div>
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium shrink-0 ${
                pendingConfirm.meta?.risk === 'high'
                  ? 't-bg-danger-soft t-text-danger'
                  : 't-bg-accent-soft t-text-accent'
              }`}>
                <ShieldAlert className="w-3 h-3" />
                {pendingConfirm.meta?.risk === 'high' ? '高风险' : '中风险'}
              </span>
            </div>

            {/* 参数详情区 */}
            <div className="px-5 py-4 max-h-[50vh] overflow-y-auto">
              <div className="t-bg-card border t-border rounded-xl px-4 py-3 space-y-2">
                {pendingConfirm.summary.split('\n').map((line, i) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span className="t-text-faint shrink-0 mt-0.5">
                      {line.startsWith('任务：') && <Puzzle className="w-3.5 h-3.5" />}
                      {line.startsWith('代码：') && <TerminalSquare className="w-3.5 h-3.5" />}
                      {(line.startsWith('MCP 服务：') || line.startsWith('工具：') || line.startsWith('参数：') || line.startsWith('技能 ID：')) && <Cpu className="w-3.5 h-3.5" />}
                      {!line.startsWith('任务：') && !line.startsWith('代码：') && !line.startsWith('MCP 服务：') && !line.startsWith('工具：') && !line.startsWith('参数：') && !line.startsWith('技能 ID：') && <span className="inline-block w-3.5 h-3.5" />}
                    </span>
                    <span className="t-text-2 break-all whitespace-pre-wrap leading-relaxed">{line}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 底部按钮区 */}
            <div className="px-5 py-3 border-t t-border flex items-center justify-between">
              <span className="text-[11px] t-text-faint">
                {pendingConfirm.meta?.risk === 'high' ? '⚠️ 高风险操作，请仔细确认' : '确认后将自动继续执行'}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => confirmResolverRef.current?.(false)}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  拒绝
                </button>
                <button
                  onClick={() => confirmResolverRef.current?.(true)}
                  className={`inline-flex items-center gap-1.5 px-4 py-2 text-xs rounded-lg text-white transition-colors ${
                    pendingConfirm.meta?.risk === 'high'
                      ? 't-bg-danger hover:opacity-90'
                      : 't-bg-accent t-hover-accent'
                  }`}
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  批准执行
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ChatPane
