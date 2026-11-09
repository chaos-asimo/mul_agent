import { useState, useRef, useEffect } from 'react'
import { Send, Paperclip, Trash2, Plus, X, ChevronRight } from 'lucide-react'

function LobsterClaw() {
  const [tabs, setTabs] = useState([{ id: 1, name: '新会话', sessionId: null }])
  const [currentTab, setCurrentTab] = useState(0)
  const [messages, setMessages] = useState({ 1: [] })
  const [inputValue, setInputValue] = useState('')
  const [uploadedFiles, setUploadedFiles] = useState({})
  const [isSending, setIsSending] = useState(false)
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')
  const messagesEndRef = useRef(null)

  useEffect(() => {
    loadModels()
  }, [])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const loadModels = async () => {
    try {
      const response = await fetch('/api/lobster-claw/chat/models')
      const result = await response.json()
      if (result.success) {
        // 后端可能返回对象数组或字符串数组
        if (Array.isArray(result.models)) {
          setModels(result.models.map(m => typeof m === 'object' ? m.name : m))
        }
      }
    } catch (error) {
      console.error('加载模型失败:', error)
    }
  }

  const addNewTab = () => {
    const newId = Date.now()
    setTabs([...tabs, { id: newId, name: '新会话', sessionId: null }])
    setMessages({ ...messages, [newId]: [] })
    setUploadedFiles({ ...uploadedFiles, [newId]: [] })
    setCurrentTab(tabs.length)
  }

  const closeTab = (index) => {
    if (tabs.length === 1) return
    const newTabs = tabs.filter((_, i) => i !== index)
    const newMessages = {}
    const newUploadedFiles = {}
    newTabs.forEach((tab, i) => {
      newMessages[tab.id] = messages[tab.id] || []
      newUploadedFiles[tab.id] = uploadedFiles[tab.id] || []
    })
    setTabs(newTabs)
    setMessages(newMessages)
    setUploadedFiles(newUploadedFiles)
    setCurrentTab(Math.min(index, newTabs.length - 1))
  }

  const readFileContent = async (file) => {
    const ext = file.name.split('.').pop().toLowerCase()
    
    if (['txt', 'md', 'json', 'py', 'js', 'html', 'css', 'xml', 'csv'].includes(ext)) {
      return new Promise((resolve) => {
        const reader = new FileReader()
        reader.onload = (e) => resolve(e.target.result)
        reader.onerror = () => resolve('')
        reader.readAsText(file, 'utf-8')
      })
    }

    if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) {
      try {
        const formData = new FormData()
        formData.append('file', file)
        const response = await fetch('/api/lobster-claw/upload/text', {
          method: 'POST',
          body: formData,
        })
        const result = await response.json()
        return result.success && result.content ? result.content : ''
      } catch (error) {
        console.error('上传文件解析失败:', error)
        return ''
      }
    }

    return ''
  }

  const handleFileUpload = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    const tabId = tabs[currentTab].id
    const currentFiles = uploadedFiles[tabId] || []

    for (const file of files) {
      if (file.size > 10 * 1024 * 1024) {
        alert(`${file.name} 文件过大，请上传小于10MB的文件`)
        continue
      }

      const content = await readFileContent(file)
      currentFiles.push({
        filename: file.name,
        content: content,
        size: file.size,
      })
    }

    setUploadedFiles({ ...uploadedFiles, [tabId]: currentFiles })
    e.target.value = ''
  }

  const removeFile = (index) => {
    const tabId = tabs[currentTab].id
    const currentFiles = uploadedFiles[tabId] || []
    currentFiles.splice(index, 1)
    setUploadedFiles({ ...uploadedFiles, [tabId]: currentFiles })
  }

  const sendMessage = async () => {
    const message = inputValue.trim()
    const tabId = tabs[currentTab].id
    const currentTabData = tabs[currentTab]
    const currentFiles = uploadedFiles[tabId] || []

    if (!message && currentFiles.length === 0) return

    setIsSending(true)

    const displayMessage = currentFiles.length > 0
      ? `${message}\n\n📎 已上传文件: ${currentFiles.map(f => f.filename).join(', ')}`
      : message

    setMessages({
      ...messages,
      [tabId]: [...(messages[tabId] || []), {
        role: 'user',
        content: displayMessage,
        timestamp: new Date().toISOString(),
      }],
    })

    try {
      const response = await fetch('/api/lobster-claw/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message || '请分析我上传的文件',
          session_id: currentTabData.sessionId,
          model_name: selectedModel || undefined,
          files: currentFiles.length > 0 ? currentFiles : undefined,
        }),
      })

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let assistantContent = ''
      let sessionId = null

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6))
              if (data.success) {
                if (data.session_id) sessionId = data.session_id
                if (data.content) {
                  assistantContent += data.content
                  setMessages(prev => ({
                    ...prev,
                    [tabId]: [...(prev[tabId] || []).filter(m => m.role !== 'assistant' || !m.isStreaming), {
                      role: 'assistant',
                      content: assistantContent,
                      timestamp: new Date().toISOString(),
                      isStreaming: !data.done,
                    }],
                  }))
                }
                if (data.done) {
                  setMessages(prev => ({
                    ...prev,
                    [tabId]: [...(prev[tabId] || []).filter(m => m.role !== 'assistant' || !m.isStreaming), {
                      role: 'assistant',
                      content: assistantContent,
                      timestamp: new Date().toISOString(),
                    }],
                  }))
                  if (sessionId && !currentTabData.sessionId) {
                    setTabs(prev => prev.map((t, i) => i === currentTab ? { ...t, sessionId } : t))
                  }
                }
              }
            } catch (e) {
              console.error('解析SSE数据失败:', e)
            }
          }
        }
      }
    } catch (error) {
      console.error('发送消息失败:', error)
      setMessages(prev => ({
        ...prev,
        [tabId]: [...(prev[tabId] || []), {
          role: 'system',
          content: `<span style="color: #ef4444;">发送失败: ${error.message}</span>`,
          timestamp: new Date().toISOString(),
        }],
      }))
    } finally {
      setInputValue('')
      setUploadedFiles({ ...uploadedFiles, [tabId]: [] })
      setIsSending(false)
    }
  }

  const clearMessages = () => {
    const tabId = tabs[currentTab].id
    setMessages({ ...messages, [tabId]: [] })
  }

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return ''
    const date = new Date(timestamp)
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  const currentTabId = tabs[currentTab]?.id
  const currentMessages = messages[currentTabId] || []

  return (
    <div className="h-full flex flex-col bg-white rounded-xl shadow-lg overflow-hidden">
      {/* Tabs */}
      <div className="flex border-b border-gray-200 bg-gray-50">
        {tabs.map((tab, index) => (
          <div
            key={tab.id}
            className={`flex items-center gap-2 px-4 py-3 cursor-pointer transition-colors ${
              index === currentTab
                ? 'bg-white border-b-2 border-blue-600 text-blue-600'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
            }`}
          >
            <ChevronRight className="w-4 h-4" />
            <span className="font-medium">{tab.name}</span>
            {tabs.length > 1 && (
              <button
                onClick={(e) => { e.stopPropagation(); closeTab(index) }}
                className="p-1 hover:text-red-500"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        ))}
        <button
          onClick={addNewTab}
          className="flex items-center gap-2 px-4 py-3 text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
        >
          <Plus className="w-4 h-4" />
          新会话
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto p-6 space-y-4">
        {currentMessages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="w-20 h-20 rounded-full bg-gray-100 flex items-center justify-center mb-4">
              <Send className="w-10 h-10" />
            </div>
            <p className="text-lg font-medium">开始聊天</p>
            <p className="text-sm">发送消息或上传文件开始对话</p>
          </div>
        ) : (
          currentMessages.map((msg, index) => (
            <div
              key={index}
              className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
            >
              <div
                className={`flex-1 max-w-[70%] ${
                  msg.role === 'user' ? 'text-right' : ''
                }`}
              >
                <div
                  className={`inline-block px-4 py-3 rounded-xl ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white rounded-br-none'
                      : 'bg-gray-100 text-gray-800 rounded-bl-none'
                  }`}
                >
                  <div
                    className={`markdown-content ${msg.role === 'user' ? 'text-white' : ''}`}
                    dangerouslySetInnerHTML={{ __html: msg.content }}
                  />
                  <div className={`text-xs mt-2 ${msg.role === 'user' ? 'text-blue-200' : 'text-gray-400'}`}>
                    {formatTimestamp(msg.timestamp)}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
        {isSending && (
          <div className="flex gap-4">
            <div className="flex-1 max-w-[70%]">
              <div className="inline-block px-4 py-3 rounded-xl bg-gray-100 rounded-bl-none">
                <div className="typing-indicator">
                  <span></span><span></span><span></span>
                </div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 p-4">
        {uploadedFiles[currentTabId]?.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {uploadedFiles[currentTabId].map((file, index) => (
              <span
                key={index}
                className="inline-flex items-center gap-2 px-3 py-1 bg-blue-50 text-blue-600 rounded-full text-sm"
              >
                <Paperclip className="w-4 h-4" />
                {file.filename}
                <button onClick={() => removeFile(index)} className="hover:text-red-500">
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}
          </div>
        )}
        
        <div className="flex items-end gap-3">
          <div className="flex-1 flex flex-col min-w-0">
            <textarea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  sendMessage()
                }
              }}
              placeholder="输入你的问题或命令..."
              className="w-full px-4 py-3 border border-gray-200 rounded-xl resize-none min-h-[80px] max-h-[200px] focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
            />
          </div>
          
          <div className="flex flex-col gap-2">
            <label className="p-3 border border-gray-200 rounded-xl cursor-pointer hover:bg-gray-50 transition-colors">
              <Paperclip className="w-5 h-5 text-gray-500" />
              <input type="file" multiple className="hidden" onChange={handleFileUpload} />
            </label>
            <button
              onClick={sendMessage}
              disabled={isSending}
              className="p-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>

          <div className="flex flex-col gap-2">
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="px-3 py-3 border border-gray-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
            >
              <option value="">默认模型</option>
              {models.map((model) => (
                <option key={model} value={model}>{model}</option>
              ))}
            </select>
            <button
              onClick={clearMessages}
              className="p-3 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors"
            >
              <Trash2 className="w-5 h-5 text-gray-500" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default LobsterClaw
