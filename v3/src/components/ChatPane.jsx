import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Send, Paperclip, X, Check, Bot, Image as ImageIcon, BookOpen, ChevronDown, ChevronUp, Download, FileText, FileImage, FileType, ShieldAlert, CheckCircle, XCircle, Loader2, Package, TerminalSquare, Cpu, Puzzle, Wrench } from 'lucide-react'
import { apiGet, apiPost, apiStream, formatSize } from '../api/client'
import { isImageFile, isPdfFile, isOfficeFile, isTextFile } from '../utils/highlight'
import MarkdownContent from './MarkdownContent'
import ToolCallCard from './ToolCallCard'
import FileViewer from './FileViewer'
import { parseAssistantContent } from '../utils/parseContent'
import { exportMarkdown, exportWord, exportImage } from '../utils/export'

// 思考 + 执行过程合并为一个状态条：流式期间只显示一行当前阶段（不再堆叠多个进度框），
// 点击可展开查看思考内容与每一步执行明细；结束后自动折叠。
function ActivityBlock({ thinking, events, streaming, elapsed, liveStatus, onOpenFile }) {
  const [open, setOpen] = useState(false)
  const [codeOpen, setCodeOpen] = useState(false)
  useEffect(() => {
    if (!streaming) setOpen(false)
  }, [streaming])

  const hasThinking = !!(thinking && thinking.trim())
  const evs = events || []
  const stepCount = evs.filter((e) => e.stage !== 'install_log').length
  if (!streaming && !hasThinking && stepCount === 0) return null

  // 当前活跃阶段：取最近一条未完成的过程事件
  const running = [...evs].reverse().find(
    (e) => e.stage === 'generating' || e.stage === 'executing' || e.stage === 'fixing'
      || (e.stage === 'install' && e.success === undefined)
  )
  const RUNNING_TEXT = {
    generating: '正在编写脚本…',
    executing: '正在沙箱中执行…',
    fixing: '出错，正在修复脚本…',
    install: '正在安装依赖…',
  }
  let status = ''
  if (streaming) {
    if (running) status = running.text || RUNNING_TEXT[running.stage] || '处理中…'
    else if (liveStatus) status = liveStatus
    else if (hasThinking) status = '思考中…'
    else status = '正在生成回答…'
  }

  const header = streaming
    ? `${status}${elapsed > 0 ? ` · ${elapsed}s` : ''}`
    : `思考与执行过程${stepCount > 0 ? ` · ${stepCount} 步` : ''}`
  const expandable = hasThinking || stepCount > 0

  return (
    <div className="mb-2 max-w-[92%]">
      <button
        onClick={() => expandable && setOpen((v) => !v)}
        className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full t-bg-panel border t-border text-[11px] t-text-muted transition-opacity ${expandable ? 'hover:opacity-80' : 'cursor-default'}`}
      >
        {streaming ? (
          <Loader2 className="w-3 h-3 animate-spin t-text-accent shrink-0" />
        ) : (
          <TerminalSquare className="w-3 h-3 shrink-0" />
        )}
        <span className="truncate">{header}</span>
        {expandable && (open ? <ChevronUp className="w-3 h-3 shrink-0" /> : <ChevronDown className="w-3 h-3 shrink-0" />)}
      </button>
      {open && (
        <div className="mt-1.5 px-3 py-2.5 rounded-lg t-bg-bubble border t-border text-xs space-y-2 max-h-96 overflow-y-auto">
          {hasThinking && (
            <div className="t-text-muted whitespace-pre-wrap break-words leading-relaxed">
              {thinking}
              {streaming && <span className="inline-block w-2 h-3.5 bg-current animate-pulse ml-0.5" />}
            </div>
          )}
          {evs.map((ev, i) => {
            if (ev.stage === 'generating') {
              return (
                <div key={i} className="flex items-center gap-1.5 t-text-muted">
                  <Loader2 className="w-3 h-3 animate-spin t-text-accent shrink-0" />
                  <span>{ev.text || '正在让模型编写脚本…'}</span>
                </div>
              )
            }
            if (ev.stage === 'script') {
              return (
                <div key={i}>
                  <button
                    onClick={() => setCodeOpen((v) => !v)}
                    className="flex items-center gap-1.5 t-text-2 hover:opacity-80 transition-opacity"
                  >
                    <FileText className="w-3 h-3 t-text-accent shrink-0" />
                    <span className="font-medium">脚本《{ev.name}》已生成</span>
                    {ev.desc && <span className="t-text-faint">— {ev.desc}</span>}
                    {codeOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                  </button>
                  {codeOpen && (
                    <pre className="mt-1.5 p-2 rounded-md t-bg-panel border t-border t-text-muted text-[11px] leading-relaxed overflow-x-auto whitespace-pre-wrap break-words max-h-60 overflow-y-auto">
                      {ev.code}
                      {ev.truncated && '\n…（代码过长已截断展示，完整代码见产物文件）'}
                    </pre>
                  )}
                </div>
              )
            }
            if (ev.stage === 'executing') {
              return (
                <div key={i} className="flex items-center gap-1.5 t-text-muted">
                  <Loader2 className="w-3 h-3 animate-spin t-text-accent shrink-0" />
                  <span>{ev.text || '正在沙箱中执行…'}</span>
                </div>
              )
            }
            if (ev.stage === 'install') {
              const done = ev.success !== undefined
              return (
                <div key={i} className="flex items-center gap-1.5 t-text-muted">
                  {done ? (
                    ev.success ? <CheckCircle className="w-3 h-3 shrink-0" /> : <XCircle className="w-3 h-3 shrink-0 t-text-danger" />
                  ) : (
                    <Package className="w-3 h-3 shrink-0 t-text-accent animate-pulse" />
                  )}
                  <span>{ev.text || '正在安装第三方库…'}</span>
                </div>
              )
            }
            if (ev.stage === 'install_log') {
              return (
                <div key={i} className="font-mono text-[11px] t-text-faint break-all leading-relaxed">
                  {ev.line}
                </div>
              )
            }
            if (ev.stage === 'fixing') {
              return (
                <div key={i}>
                  <div className="flex items-center gap-1.5 t-text-warn">
                    <Wrench className="w-3 h-3 shrink-0" />
                    <span>{ev.text || '执行出错，正在让模型修复脚本…'}</span>
                  </div>
                  {ev.error && (
                    <pre className="mt-1 p-2 rounded-md t-bg-danger-soft border t-border-danger t-text-danger text-[11px] leading-relaxed whitespace-pre-wrap break-words max-h-24 overflow-y-auto">
                      {ev.error}
                    </pre>
                  )}
                </div>
              )
            }
            if (ev.stage === 'output') {
              const ok = ev.stage_success !== false
              return (
                <div key={i}>
                  <div className={`flex items-center gap-1.5 ${ok ? 't-text-2' : 't-text-danger'}`}>
                    {ok ? <CheckCircle className="w-3 h-3 shrink-0" /> : <XCircle className="w-3 h-3 shrink-0" />}
                    <span className="font-medium">{ok ? '执行完成' : '执行失败'}</span>
                  </div>
                  {ev.output && (
                    <pre className="mt-1 p-2 rounded-md t-bg-panel border t-border t-text-muted text-[11px] leading-relaxed overflow-x-auto whitespace-pre-wrap break-words max-h-48 overflow-y-auto">
                      {ev.output}
                    </pre>
                  )}
                  {ev.error && (
                    <pre className="mt-1 p-2 rounded-md t-bg-danger-soft border t-border-danger t-text-danger text-[11px] leading-relaxed whitespace-pre-wrap break-words max-h-32 overflow-y-auto">
                      {ev.error}
                    </pre>
                  )}
                  {ev.files && ev.files.length > 0 && (
                    <div className="mt-1">
                      <GeneratedFiles files={ev.files} onOpenFile={onOpenFile} />
                    </div>
                  )}
                </div>
              )
            }
            if (ev.stage === 'error') {
              return (
                <div key={i} className="flex items-center gap-1.5 t-text-danger">
                  <XCircle className="w-3 h-3 shrink-0" />
                  <span>{ev.text}</span>
                </div>
              )
            }
            return null
          })}
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

// 服务器部署后，历史消息/脚本输出里可能残留 http://localhost:8888 的本机地址；
// 去掉 scheme+host 后按当前站点 origin 解析，避免用户点到无法访问的 localhost 链接
const LOCAL_URL_RE = /https?:\/\/(?:localhost|127\.0\.0\.1)(?::8888)?/gi
function normalizeLocalUrls(src) {
  return String(src || '').replace(LOCAL_URL_RE, '')
}

// 助手消息内容：解析工具调用/结果，渲染为 WorkBuddy 风格卡片 + Markdown
function AssistantContent({ content, streaming }) {
  const segments = useMemo(
    () => parseAssistantContent(normalizeLocalUrls(content)),
    [content],
  )
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

function MessageBubble({ msg, onOpenFile, elapsedSec, liveStatus }) {
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
          <ActivityBlock
            thinking={msg.thinking}
            events={msg.procEvents}
            streaming={msg.streaming}
            elapsed={msg.streaming ? elapsedSec : 0}
            liveStatus={msg.streaming ? liveStatus : ''}
            onOpenFile={onOpenFile}
          />
        )}
        {/* 流式期间还没有任何正文时，不渲染空白气泡，避免出现“空框”等待 */}
        {!(msg.streaming && !(msg.content || '').trim()) && (
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
        )}
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

// 流式执行中的状态指示器：解析状态文本，显示对应图标 + 动画 + 已耗时
function StreamingIndicator({ status, elapsed }) {
  const elapsedLabel = elapsed > 0 ? ` · ${elapsed}s` : ''
  if (!status) {
    return (
      <div className="flex items-center gap-2.5">
        <div className="typing-indicator">
          <span></span>
          <span></span>
          <span></span>
        </div>
        {elapsed >= 3 && <span className="text-xs t-text-faint">正在连接模型{elapsedLabel}</span>}
      </div>
    )
  }
  // 解析工具名
  let icon = '💭'
  let label = status
  let stepBadge = null
  if (status.includes('思考')) {
    icon = '💭'
    // 提取"第 N/M 步"作为分步徽章单独展示，突出分步思考过程
    const stepMatch = status.match(/^第\s*(\d+\/\d+)\s*步/)
    if (stepMatch) stepBadge = `第 ${stepMatch[1]} 步`
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
      {stepBadge && (
        <span className="px-1.5 py-0.5 rounded t-bg-accent-soft border t-border-accent t-text-accent text-[10px] font-medium">
          {stepBadge}
        </span>
      )}
      <span className="text-sm t-text-muted">{label}</span>
      {elapsed > 0 && <span className="text-[11px] t-text-faint tabular-nums">{elapsed}s</span>}
    </div>
  )
}

function ChatPane({
  sessionId,
  messages,
  setMessages,
  onSessionCreated,
  onRefreshSessions,
  onStreamsChange,
  pendingFiles,
  onAddFiles,
  onRemoveFile,
  onFilesSent,
}) {
  const [inputValue, setInputValue] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const [streamError, setStreamError] = useState('')
  const [pendingImages, setPendingImages] = useState([])
  const [streamStatus, setStreamStatus] = useState('') // 后台运行状态文本（思考中、执行工具…）
  const [sendStartTs, setSendStartTs] = useState(0) // 本轮发送起始时间，用于显示"已思考 Ns"
  const [elapsedSec, setElapsedSec] = useState(0)
  const messagesEndRef = useRef(null)
  const scrollContainerRef = useRef(null)
  const fileInputRef = useRef(null)
  const textareaRef = useRef(null)
  const prevMsgLenRef = useRef(0)
  const prevSessionRef = useRef(sessionId)
  const [showJumpBottom, setShowJumpBottom] = useState(false)
  const userScrolledUpRef = useRef(false) // 用户主动向上滚动后暂停自动跟随
  const isSendingRef = useRef(false) // 发送状态 ref，供 ResizeObserver 读取（避免闭包捕获旧值）
  const pendingRafRef = useRef(null)
  const [pendingConfirm, setPendingConfirm] = useState(null) // {request_id, summary, meta}
  const confirmResolverRef = useRef(null) // 当前视图所显示确认弹窗的 resolver（镜像自对应 entry）
  const sessionIdRef = useRef(sessionId) // 当前正在浏览的会话
  // 每个会话各自独立的流式任务：sid -> entry。切换会话只切换镜像显示，
  // 各会话的后台流式互不影响，可并发执行、随时切回继续查看。
  const streamsRef = useRef({})
  const pendingEntryRef = useRef(null) // 从未命名新会话发起、尚未分配到 session_id 的 entry
  useEffect(() => {
    sessionIdRef.current = sessionId
  }, [sessionId])

  // 当前视图对应的流式任务（若有）
  const entryForView = useCallback(() => {
    const sid = sessionIdRef.current
    if (sid) return streamsRef.current[sid] || null
    return pendingEntryRef.current
  }, [])

  // 通知父组件：正在执行任务的会话集合（会话列表据此显示执行态标识）
  const streamsNotifyRef = useRef(onStreamsChange)
  useEffect(() => { streamsNotifyRef.current = onStreamsChange }, [onStreamsChange])
  const notifyStreams = useCallback(() => {
    const cb = streamsNotifyRef.current
    if (!cb) return
    // 会话 id 为字符串（如 mu_s_667_...），原样上报，勿做数字转换
    const sids = Object.keys(streamsRef.current).filter((k) => k !== '__pending__')
    cb(sids)
  }, [])

  // 把消息更新写入指定会话：正在浏览该会话才上屏；否则只记录在 entry 上，切回时再合并
  const writeMessages = useCallback(
    (sid, updater) => {
      const viewing = sessionIdRef.current
      const isViewed = viewing ? viewing === sid : pendingEntryRef.current?.sid === sid
      if (isViewed) setMessages((prev) => updater(prev))
    },
    [setMessages]
  )

  // 更新 entry 并把最新内容写入其所属会话的消息列表
  const applyToEntry = useCallback(
    (entry, content, done, extraMeta) => {
      entry.content = content
      entry.done = done
      if (extraMeta) entry.meta = { ...(entry.meta || {}), ...extraMeta }
      writeMessages(entry.sid, (prev) => {
        const arr = [...prev]
        const last = arr[arr.length - 1]
        if (last && last.role === 'assistant' && last.streaming) {
          arr[arr.length - 1] = { ...last, content, streaming: !done, ...(entry.meta || {}) }
        } else {
          arr.push({ role: 'assistant', content, timestamp: new Date().toISOString(), streaming: !done, ...(entry.meta || {}) })
        }
        return arr
      })
    },
    [writeMessages]
  )

  const finalizeEntry = useCallback(
    (entry) => {
      entry.done = true
      writeMessages(entry.sid, (prev) => {
        const last = prev[prev.length - 1]
        if (last && last.role === 'assistant' && last.streaming) {
          return [...prev.slice(0, -1), { ...last, streaming: false }]
        }
        return prev
      })
    },
    [writeMessages]
  )

  // 若该 entry 正被浏览，把它的指示器状态（状态条/计时/确认弹窗）镜像到渲染态
  const syncEntryUi = useCallback(
    (entry) => {
      if (entryForView() !== entry) return
      setIsSending(!entry.done)
      isSendingRef.current = !entry.done
      setStreamStatus(entry.status || '')
      setStreamError(entry.error || '')
      setSendStartTs(entry.startTs || 0)
      setPendingConfirm(entry.confirm || null)
      confirmResolverRef.current = entry.confirmResolve || null
    },
    [entryForView]
  )
  const [viewingFile, setViewingFile] = useState(null) // 对话中产物文件的在线查看器（根层渲染）

  // 输入框自适应高度：随内容增长，最多 200px（Trae 式单行起、无滚动条突兀感）
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`
  }, [inputValue])

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

  // 发送期间的已耗时秒数：让用户直观感知后台正在处理（思考/工具执行）
  useEffect(() => {
    if (!isSending) return
    const t = setInterval(() => {
      setElapsedSec(Math.max(0, Math.floor((Date.now() - sendStartTs) / 1000)))
    }, 1000)
    return () => clearInterval(t)
  }, [isSending, sendStartTs])

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
    // 仅当正浏览的正是该会话时才补挂；切到别的会话或未命名新会话页一律不挂
    const viewing = sessionIdRef.current || pendingEntryRef.current?.sid || null
    if (sid !== viewing) return
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

  // 会话切换：恢复该会话自己的流式任务显示（指示器 + 在途气泡）。各会话独立执行互不干扰；
  // 依赖 messages.length——历史加载完成后会再次执行，把在途气泡合并回视图。
  useEffect(() => {
    if (sessionId && pendingEntryRef.current && pendingEntryRef.current.sid !== sessionId) {
      pendingEntryRef.current = null
    }
    const entry = entryForView()
    if (entry && !entry.done) {
      syncEntryUi(entry)
      if (entry.content || entry.meta) {
        // 幂等合并：视图中尚无在途气泡时把 entry 的最新内容补回来
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last && last.role === 'assistant' && last.streaming) return prev
          return [
            ...prev,
            { role: 'assistant', content: entry.content || '', timestamp: new Date().toISOString(), streaming: true, ...(entry.meta || {}) },
          ]
        })
      }
    } else if (!entry) {
      setIsSending(false)
      isSendingRef.current = false
      setStreamStatus('')
      setStreamError('')
      setSendStartTs(0)
      setElapsedSec(0)
      setPendingConfirm(null)
      confirmResolverRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, messages.length])

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
    const curEntry = entryForView()
    if ((!message && pendingFiles.length === 0 && pendingImages.length === 0) || (curEntry && !curEntry.done)) return

    // 本会话的独立流式任务：切换会话/其他会话发送互不影响
    const entry = {
      sid: sessionId || '__pending__',
      controller: new AbortController(),
      startTs: Date.now(),
      status: '',
      error: '',
      confirm: null,
      confirmResolve: null,
      done: false,
      content: '',
      thinking: '',
      procEvents: [],
      meta: null,
      newSessionId: null,
    }
    streamsRef.current[entry.sid] = entry
    if (!sessionId) pendingEntryRef.current = entry
    notifyStreams()

    setIsSending(true)
    isSendingRef.current = true
    setStreamError('')
    setStreamStatus('')
    setSendStartTs(entry.startTs)
    setElapsedSec(0)

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
        entry.controller.signal,
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
              entry.error = data.error || '请求失败'
              finalizeEntry(entry)
              syncEntryUi(entry)
              continue
            }
            if (data.session_id) {
              entry.newSessionId = data.session_id
              if (entry.sid === '__pending__') {
                delete streamsRef.current['__pending__']
                entry.sid = data.session_id
                streamsRef.current[entry.sid] = entry
                notifyStreams()
              }
              // 首个事件即刷新会话列表：新会话的行立即出现在侧栏，
              // 执行期间就能看到标题旁的"执行中"标识（此前要等到任务结束才刷新）
              if (!entry.listRefreshed) {
                entry.listRefreshed = true
                onRefreshSessions?.()
              }
            }
            if (data.type === 'status' && data.text != null) {
              // 后台运行状态：思考中、执行工具… → 替换静默的 typing 提示
              entry.status = data.text
              syncEntryUi(entry)
              continue
            }
            if (data.type === 'confirm' && data.request_id) {
              // 中等/高风险工具需要用户确认：弹窗并等待用户选择
              entry.confirm = {
                request_id: data.request_id,
                summary: data.summary,
                meta: data.meta || {},
              }
              syncEntryUi(entry)
              const approved = await new Promise((resolve) => {
                entry.confirmResolve = resolve
                syncEntryUi(entry)
              })
              entry.confirmResolve = null
              entry.confirm = null
              syncEntryUi(entry)
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
              // 中间步骤的思考过程：实时展示在折叠区（思考区已接管"思考中"提示，状态条让位）
              entry.status = ''
              entry.thinking += data.content
              applyToEntry(entry, entry.content, false, { thinking: entry.thinking })
              syncEntryUi(entry)
              continue
            }
            if (data.type === 'tool_progress') {
              // 执行过程事件（脚本编写/沙箱执行/输出），实时上屏
              entry.procEvents = [
                ...entry.procEvents,
                {
                  stage: data.stage || '',
                  text: data.text || '',
                  name: data.name || '',
                  desc: data.desc || '',
                  code: data.code || '',
                  truncated: !!data.truncated,
                  output: data.output || '',
                  error: data.error || '',
                  files: Array.isArray(data.files) ? data.files : [],
                  stage_success: data.stage_success,
                },
              ]
              applyToEntry(entry, entry.content, false, {
                thinking: entry.thinking,
                procEvents: entry.procEvents,
              })
              continue
            }

            if (data.type === 'reclassify' && data.to === 'thinking') {
              // 中间步骤修正：把已流式输出的 content 归入 thinking 折叠区
              entry.thinking += entry.content
              entry.content = ''
              applyToEntry(entry, '', false, { thinking: entry.thinking })
              continue
            }
            if (data.content) {
              // 收到实际内容输出后，状态条不再需要（下一状态事件会重新设置）
              entry.status = ''
              entry.content += data.content
              applyToEntry(entry, entry.content, false)
              syncEntryUi(entry)
            }
            if (data.done) {
              entry.status = ''
              const meta = {}
              if (data.model_name) meta.model_name = data.model_name
              if (data.token_stats) meta.token_stats = data.token_stats
              if (data.knowledge_sources && data.knowledge_sources.length > 0) {
                meta.knowledge_sources = data.knowledge_sources
              }
              if (data.files && data.files.length > 0) {
                meta.files = data.files
              }
              if (entry.thinking) {
                meta.thinking = entry.thinking
              }
              applyToEntry(entry, entry.content, true, meta)
            }
          } catch (e) {
            // 忽略无法解析的行
          }
        }
      }

      if (entry.content) {
        finalizeEntry(entry)
      }
    } catch (error) {
      // 用户主动点击「停止」触发的 abort，不视为错误
      if (error.name === 'AbortError') {
        if (entry.content) {
          finalizeEntry(entry)
        }
        // 中断时 done 事件不会到达：从会话详情补拉本轮已产出文件（后端在 finally 中已挂载）
        refreshLastMessageFiles(entry.newSessionId || entry.sid)
      } else {
        console.error('发送消息失败:', error)
        finalizeEntry(entry)
        entry.error = `发送失败: ${error.message}`
        syncEntryUi(entry)
      }
    } finally {
      entry.done = true
      // 仅当本 entry 属于当前视图时才复位指示器，避免并发任务互相清状态
      const wasViewed = sessionIdRef.current
        ? sessionIdRef.current === entry.sid
        : pendingEntryRef.current === entry
      delete streamsRef.current[entry.sid]
      notifyStreams()
      if (wasViewed) {
        setInputValue('')
        setPendingImages([])
        onFilesSent?.()
        setIsSending(false)
        isSendingRef.current = false
        setStreamStatus('')
        confirmResolverRef.current = null
      }
      if (entry.newSessionId && entry.newSessionId !== sessionId) {
        onSessionCreated?.(entry.newSessionId)
      } else {
        onRefreshSessions?.()
      }
    }
  }

  // 停止当前会话的流式请求：仅中断当前视图所对应任务的 fetch 流
  const stopMessage = () => {
    entryForView()?.controller.abort()
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
          renderedMessages.map((msg, index) => <MessageBubble key={index} msg={msg} onOpenFile={setViewingFile} elapsedSec={elapsedSec} liveStatus={streamStatus} />)
        )}
        {isSending && !renderedMessages.some((m) => m.role === 'assistant' && m.streaming) && (
          <div className="flex justify-start">
            <div className="px-4 py-3 rounded-xl t-bg-bubble border t-border rounded-bl-none flex items-center gap-3 min-w-[200px]">
              <StreamingIndicator status={streamStatus} elapsed={elapsedSec} />
            </div>
          </div>
        )}
        {/* 后台状态已并入每条助手消息的状态条，这里不再重复展示，避免多个进度框堆叠 */}
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

        {/* Trae 手机版风格：整体一张圆角卡片，输入在上、操作栏在下 */}
        <div className="t-composer relative border t-border-strong t-bg-input rounded-2xl shadow-sm transition-all">
          <textarea
            ref={textareaRef}
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onPaste={handlePaste}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                sendMessage()
              }
            }}
            rows={1}
            placeholder="发消息…（Shift+Enter 换行，可粘贴图片）"
            className="w-full bg-transparent border-0 outline-none resize-none px-4 pt-3 pb-1.5 text-sm t-text t-placeholder leading-relaxed min-h-[52px] max-h-[200px]"
          />

          <div className="flex items-center justify-between gap-2 px-2 pb-2">
            <div className="flex items-center gap-1 min-w-0">
              <label
                className="w-8 h-8 rounded-full flex items-center justify-center cursor-pointer t-hover-card transition-colors t-text-muted shrink-0"
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
                className="w-8 h-8 rounded-full flex items-center justify-center cursor-pointer t-hover-card transition-colors t-text-muted shrink-0"
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
              <div className="ml-0.5 relative shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    setModelMenuOpen((v) => !v)
                    textareaRef.current?.blur()
                  }}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-full bg-transparent text-[11px] t-text-2 t-hover-card transition-colors max-w-[132px]"
                  title="选择模型"
                >
                  <span className="truncate">{selectedModel || '默认模型'}</span>
                  <ChevronDown className={`w-3 h-3 shrink-0 transition-transform ${modelMenuOpen ? 'rotate-180' : ''}`} />
                </button>

                {modelMenuOpen && (
                  <>
                    {/* 点击遮罩关闭：解决手机端原生 select 弹层不稳定的问题 */}
                    <div className="fixed inset-0 z-20" onClick={() => setModelMenuOpen(false)} />
                    <div className="absolute bottom-full left-0 mb-2 z-30 w-52 max-w-[72vw] max-h-72 overflow-y-auto rounded-xl border t-border-strong t-bg-card shadow-xl py-1">
                      {[{ value: '', label: '默认模型' }, ...models.map((m) => ({ value: m, label: m }))].map((opt) => (
                        <button
                          key={opt.value || '__default'}
                          type="button"
                          onClick={() => {
                            setSelectedModel(opt.value)
                            setModelMenuOpen(false)
                          }}
                          className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-xs text-left t-text-2 t-hover-bg transition-colors"
                        >
                          <span className="truncate">{opt.label}</span>
                          {selectedModel === opt.value && <Check className="w-3.5 h-3.5 shrink-0 t-text-accent" />}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            </div>

            <button
              onClick={isSending ? stopMessage : sendMessage}
              title={isSending ? '停止生成' : '发送'}
              className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 transition-all ${
                isSending
                  ? 't-bg-danger t-hover-danger text-white'
                  : 't-bg-accent t-hover-accent text-white disabled:opacity-40 disabled:cursor-not-allowed'
              }`}
              disabled={!isSending && !inputValue.trim()}
            >
              {isSending ? (
                <X className="w-4 h-4" />
              ) : (
                <Send className="w-4 h-4" />
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
