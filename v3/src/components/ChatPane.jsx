import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Send, Paperclip, X, Bot, Image as ImageIcon } from 'lucide-react'
import { apiGet, apiStream } from '../api/client'
import MarkdownContent from './MarkdownContent'

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

function MessageBubble({ msg }) {
  const isUser = msg.role === 'user'
  const isError = msg.role === 'error'
  const images = msg.images || []

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`max-w-[78%] ${isUser ? 'items-end' : 'items-start'} flex flex-col`}>
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
              <MarkdownContent content={msg.content} />
            )}
          </div>
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
        </div>
      </div>
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
  const messagesEndRef = useRef(null)
  const fileInputRef = useRef(null)

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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

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
    setStreamError('')

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
    let newSessionId = null
    let hadError = false

    try {
      const response = await apiStream('/chat/stream', {
        message: message || '请分析我上传的图片/文件',
        session_id: sessionId || undefined,
        model_name: selectedModel || undefined,
        files:
          pendingFiles.length > 0
            ? pendingFiles.map(({ filename, content }) => ({ filename, content }))
            : undefined,
        images: pendingImages.length > 0 ? pendingImages : undefined,
      })

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
            if (data.content) {
              assistantContent += data.content
              appendOrUpdateAssistant(assistantContent, false)
            }
            if (data.done) {
              const meta = {}
              if (data.model_name) meta.model_name = data.model_name
              if (data.token_stats) meta.token_stats = data.token_stats
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
      console.error('发送消息失败:', error)
      finalizeStreaming()
      setStreamError(`发送失败: ${error.message}`)
    } finally {
      setInputValue('')
      setPendingImages([])
      onFilesSent?.()
      setIsSending(false)
      if (newSessionId && newSessionId !== sessionId) {
        onSessionCreated?.(newSessionId)
      } else {
        onRefreshSessions?.()
      }
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
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
        {isEmpty ? (
          <div className="flex flex-col items-center justify-center h-full t-text-fainter">
            <div className="w-20 h-20 rounded-full t-bg-panel flex items-center justify-center mb-4 border t-border">
              <Bot className="w-10 h-10 t-text-faint" />
            </div>
            <p className="text-lg font-medium t-text-muted">开始与龙虾Claw对话</p>
            <p className="text-sm">输入消息发送，或在右侧「文件」面板上传附件</p>
          </div>
        ) : (
          renderedMessages.map((msg, index) => <MessageBubble key={index} msg={msg} />)
        )}
        {isSending && !renderedMessages.some((m) => m.role === 'assistant' && m.streaming) && (
          <div className="flex justify-start">
            <div className="px-4 py-3 rounded-xl t-bg-bubble border t-border rounded-bl-none">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
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
              onClick={sendMessage}
              disabled={isSending}
              className="p-3 t-bg-accent t-hover-accent text-white rounded-xl transition-colors disabled:opacity-50 flex items-center justify-center"
            >
              {isSending ? (
                <span className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin"></span>
              ) : (
                <Send className="w-5 h-5" />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default ChatPane
