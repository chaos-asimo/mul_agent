import { useState, useRef, useEffect } from 'react'
import { Send, Trash2, Plus, X, ChevronRight } from 'lucide-react'

function AIChat() {
  const [tabs, setTabs] = useState([{ id: 1, name: '新会话', sessionId: null }])
  const [currentTab, setCurrentTab] = useState(0)
  const [messages, setMessages] = useState({ 1: [] })
  const [inputValue, setInputValue] = useState('')
  const [isSending, setIsSending] = useState(false)
  const messagesEndRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const addNewTab = () => {
    const newId = Date.now()
    setTabs([...tabs, { id: newId, name: '新会话', sessionId: null }])
    setMessages({ ...messages, [newId]: [] })
    setCurrentTab(tabs.length)
  }

  const closeTab = (index) => {
    if (tabs.length === 1) return
    const newTabs = tabs.filter((_, i) => i !== index)
    const newMessages = {}
    newTabs.forEach((tab, i) => {
      newMessages[tab.id] = messages[tab.id] || []
    })
    setTabs(newTabs)
    setMessages(newMessages)
    setCurrentTab(Math.min(index, newTabs.length - 1))
  }

  const sendMessage = async () => {
    const message = inputValue.trim()
    const tabId = tabs[currentTab].id
    const currentTabData = tabs[currentTab]

    if (!message) return

    setIsSending(true)

    setMessages({
      ...messages,
      [tabId]: [...(messages[tabId] || []), {
        role: 'user',
        content: message,
        timestamp: new Date().toISOString(),
      }],
    })

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: message,
          session_id: currentTabData.sessionId,
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
            <p className="text-lg font-medium">开始对话</p>
            <p className="text-sm">发送消息开始与AI对话</p>
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
              placeholder="输入你的问题..."
              className="w-full px-4 py-3 border border-gray-200 rounded-xl resize-none min-h-[80px] max-h-[200px] focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
            />
          </div>
          
          <div className="flex flex-col gap-2">
            <button
              onClick={sendMessage}
              disabled={isSending || !inputValue.trim()}
              className="p-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 transition-colors disabled:opacity-50"
            >
              <Send className="w-5 h-5" />
            </button>
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

export default AIChat
