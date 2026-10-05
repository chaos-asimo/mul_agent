import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Shell, Shield, ShieldCheck, Plus, Trash2, MessageSquare,
  FolderOpen, FileCode, Brain, Clock, BookOpen, Wrench, Bot, Wand2,
  PanelRightClose, PanelRightOpen, PanelLeftClose, PanelLeftOpen, Lightbulb, Send, X,
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { apiGet, apiPost, apiDelete, readFileContent } from '../api/client'
import ChatPane from '../components/ChatPane'
import FilesTab from '../components/FilesTab'
import ScriptsTab from '../components/ScriptsTab'
import MemoryTab from '../components/MemoryTab'
import CronTab from '../components/CronTab'
import KnowledgeTab from '../components/KnowledgeTab'
import McpTab from '../components/McpTab'
import SkillsTab from '../components/SkillsTab'
import AgentTab from '../components/AgentTab'
import ThemeSwitcher from '../components/ThemeSwitcher'
import SecuritySettings from '../components/SecuritySettings'

const TABS = [
  { key: 'files', label: '文件', icon: FolderOpen },
  { key: 'scripts', label: '脚本', icon: FileCode },
  { key: 'agents', label: 'Agent', icon: Bot },
  { key: 'memory', label: '记忆', icon: Brain },
  { key: 'cron', label: 'Cron', icon: Clock },
  { key: 'knowledge', label: '知识库', icon: BookOpen },
  { key: 'mcp', label: 'MCP', icon: Wrench },
  { key: 'skills', label: '技能', icon: Wand2 },
]

function formatSessionTime(ts) {
  if (!ts) return ''
  const date = new Date(ts)
  if (isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function Workbench() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  // 会话
  const [sessions, setSessions] = useState([])
  const [currentSessionId, setCurrentSessionId] = useState(null)
  const [loadingSessions, setLoadingSessions] = useState(true)

  // 消息
  const [messages, setMessages] = useState([])

  // 待发送文件（文件 Tab 与聊天输入框共用）
  const [pendingFiles, setPendingFiles] = useState([])

  // 功能 Tab
  const [activeTab, setActiveTab] = useState('files')
  // 登录后右侧功能栏默认收起（用户可手动展开）
  const [rightCollapsed, setRightCollapsed] = useState(true)
  const [leftCollapsed, setLeftCollapsed] = useState(() => typeof window !== 'undefined' && window.innerWidth < 768)

  // 安全设置弹窗
  const [showSecurity, setShowSecurity] = useState(false)

  // 建议弹窗
  const [showSuggestion, setShowSuggestion] = useState(false)
  const [suggestionText, setSuggestionText] = useState('')
  const [mySuggestions, setMySuggestions] = useState([])
  const [sending, setSending] = useState(false)

  const loadSessions = useCallback(async () => {
    try {
      const result = await apiGet('/chat/sessions')
      setSessions(result.sessions || [])
    } catch (e) {
      console.error('加载会话列表失败:', e)
    } finally {
      setLoadingSessions(false)
    }
  }, [])

  useEffect(() => {
    loadSessions()
  }, [loadSessions])

  const startNewSession = () => {
    setCurrentSessionId(null)
    setMessages([])
  }

  const selectSession = async (sessionId) => {
    if (sessionId === currentSessionId) return
    setCurrentSessionId(sessionId)
    setMessages([])
    try {
      const result = await apiGet(`/chat/session/${sessionId}`)
      if (result.success && result.session) {
        setMessages(result.session.messages || [])
      }
    } catch (e) {
      console.error('加载会话消息失败:', e)
    }
  }

  const deleteSession = async (sessionId) => {
    try {
      await apiDelete(`/chat/session/${sessionId}`)
      if (sessionId === currentSessionId) {
        setCurrentSessionId(null)
        setMessages([])
      }
      loadSessions()
    } catch (e) {
      console.error('删除会话失败:', e)
    }
  }

  const handleSessionCreated = (sessionId) => {
    setCurrentSessionId(sessionId)
    loadSessions()
  }

  // 文件：文本类直接读取，二进制走 /upload/text，单文件 10MB 上限
  const addPendingFiles = async (fileList) => {
    for (const file of fileList) {
      if (file.size > 10 * 1024 * 1024) {
        alert(`${file.name} 文件过大，请上传小于10MB的文件`)
        continue
      }
      const content = await readFileContent(file)
      setPendingFiles((prev) => [...prev, { filename: file.name, content, size: file.size }])
    }
  }

  const removePendingFile = (index) => {
    setPendingFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const loadMySuggestions = useCallback(async () => {
    try {
      const result = await apiGet('/suggestions')
      setMySuggestions(result.suggestions || [])
    } catch (e) {
      console.error('加载建议列表失败:', e)
    }
  }, [])

  const openSuggestion = () => {
    setShowSuggestion(true)
    loadMySuggestions()
  }

  const handleSubmitSuggestion = async (e) => {
    e.preventDefault()
    const content = suggestionText.trim()
    if (!content || sending) return
    setSending(true)
    try {
      await apiPost('/suggestions', { content })
      setSuggestionText('')
      loadMySuggestions()
    } catch (err) {
      alert('提交建议失败：' + (err?.message || '未知错误'))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="h-screen flex flex-col t-bg-app t-text">
      {/* 顶栏 */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b t-border t-bg-panel shrink-0">
        <div className="flex items-center gap-2.5">
          <button
            onClick={handleLogout}
            className="w-8 h-8 rounded-lg t-bg-accent flex items-center justify-center cursor-default"
          >
            <Shell className="w-5 h-5 text-white" />
          </button>
          <div>
            <h1 className="text-sm font-semibold leading-tight">个人助理多用户版</h1>
            <p className="text-[10px] t-text-faint leading-tight hidden sm:block">v3 · Multi-User Workbench</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5 text-sm overflow-x-auto flex-nowrap max-w-[60%]">
          <ThemeSwitcher />
          <span className="t-text-muted">{user?.display_name || user?.username}</span>
          <span
            className={`text-xs px-2 py-0.5 rounded-full border ${
              user?.role === 'admin' ? 't-badge-accent' : 't-badge-neutral'
            }`}
          >
            {user?.role === 'admin' ? '管理员' : '用户'}
          </span>
          {user?.role === 'admin' && (
            <Link
              to="/admin/users"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors"
            >
              <Shield className="w-3.5 h-3.5" />
              用户管理
            </Link>
          )}
          <button
            onClick={() => setShowSecurity(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors"
            title="安全设置（两步认证）"
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            安全
          </button>
          <button
            onClick={user?.role === 'admin' ? () => navigate('/admin/users') : openSuggestion}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors"
            title={user?.role === 'admin' ? '查看并回复用户建议' : '给管理员提建议'}
          >
            <Lightbulb className="w-3.5 h-3.5" />
            建议
          </button>
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        {/* 左栏：会话列表 */}
        <aside className={`${leftCollapsed ? 'w-0 border-r-0' : 'w-60 sm:w-64 lg:w-72 border-r'} shrink-0 flex flex-col t-bg-app overflow-hidden transition-all duration-200`}>
          {!leftCollapsed && (
          <div className="p-3 flex items-center gap-2 border-b t-border">
            <button
              onClick={startNewSession}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs rounded-lg t-bg-accent t-hover-accent text-white transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              新建会话
            </button>
            <button
              onClick={() => setLeftCollapsed(true)}
              title="隐藏会话列表"
              className="p-2 rounded-lg border t-border-strong t-text-muted t-hover-card t-hover-text-accent transition-colors"
            >
              <PanelLeftClose className="w-4 h-4" />
            </button>
          </div>
          )}
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {loadingSessions ? (
              <p className="text-xs t-text-faint text-center py-6 loading-pulse">加载中...</p>
            ) : sessions.length === 0 ? (
              <div className="text-center t-text-fainter py-10">
                <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-xs">暂无历史会话</p>
              </div>
            ) : (
              sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => selectSession(s.id)}
                  className={`group px-3 py-2.5 rounded-lg cursor-pointer transition-colors border ${
                    s.id === currentSessionId
                      ? 't-bg-accent-soft t-border-accent'
                      : 't-border t-hover-bg'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate flex-1">{s.title || '新会话'}</span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteSession(s.id)
                      }}
                      className="opacity-0 group-hover:opacity-100 t-text-faint t-hover-text-danger transition-all"
                      title="删除会话"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <p className="text-xs t-text-faint truncate mt-1">
                    {s.preview || `${s.message_count || 0} 条消息`}
                  </p>
                  <p className="text-[10px] t-text-fainter mt-0.5">{formatSessionTime(s.last_used)}</p>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* 中栏：聊天流 */}
        <main className="flex-1 min-w-0 flex flex-col relative">
          {leftCollapsed && (
            <button
              onClick={() => setLeftCollapsed(false)}
              title="展开会话列表"
              className="absolute left-2 top-2 z-10 p-1.5 rounded-lg border t-border-strong t-text-muted t-hover-card t-hover-text-accent transition-colors"
            >
              <PanelLeftOpen className="w-4 h-4" />
            </button>
          )}
          {rightCollapsed && (
            <button
              onClick={() => setRightCollapsed(false)}
              title="展开侧栏"
              className="absolute right-2 top-2 z-10 p-1.5 rounded-lg border t-border-strong t-text-muted t-hover-card t-hover-text-accent transition-colors"
            >
              <PanelRightOpen className="w-4 h-4" />
            </button>
          )}
          <ChatPane
            sessionId={currentSessionId}
            messages={messages}
            setMessages={setMessages}
            onSessionCreated={handleSessionCreated}
            onRefreshSessions={loadSessions}
            pendingFiles={pendingFiles}
            onAddFiles={addPendingFiles}
            onRemoveFile={removePendingFile}
            onFilesSent={() => setPendingFiles([])}
          />
        </main>

        {/* 右栏：功能 Tab */}
        <aside className={`${rightCollapsed ? 'w-0 border-l-0' : 'w-72 sm:w-80 lg:w-96 border-l'} shrink-0 flex flex-col t-bg-app overflow-hidden transition-all duration-200`}>
          {!rightCollapsed && (
            <>
          <div className="flex items-stretch border-b t-border shrink-0">
            <div className="flex-1 flex">
              {TABS.map(({ key, label, icon: Icon }) => (
                <button
                  key={key}
                  onClick={() => setActiveTab(key)}
                  className={`flex-1 flex flex-col items-center gap-1 py-2.5 text-[11px] transition-colors border-b-2 border-transparent ${
                    activeTab === key
                      ? 't-text-accent t-border-accent'
                      : 't-text-faint t-hover-text'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {label}
                </button>
              ))}
            </div>
            <button
              onClick={() => setRightCollapsed(true)}
              title="折叠侧栏"
              className="px-2 t-text-faint t-hover-text t-hover-bg transition-colors"
            >
              <PanelRightClose className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            {activeTab === 'files' && (
              <FilesTab
                pendingFiles={pendingFiles}
                onAddFiles={addPendingFiles}
                onRemoveFile={removePendingFile}
              />
            )}
            {activeTab === 'scripts' && <ScriptsTab />}
            {activeTab === 'agents' && <AgentTab />}
            {activeTab === 'memory' && <MemoryTab />}
            {activeTab === 'cron' && <CronTab />}
            {activeTab === 'knowledge' && <KnowledgeTab />}
            {activeTab === 'mcp' && <McpTab />}
            {activeTab === 'skills' && <SkillsTab />}
          </div>
            </>
          )}
        </aside>
      </div>

      {showSecurity && <SecuritySettings onClose={() => setShowSecurity(false)} />}

      {/* 建议弹窗（非管理员提交 + 查看自己的建议） */}
      {showSuggestion && user?.role !== 'admin' && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/70">
          <div className="w-full max-w-2xl max-h-[85vh] flex flex-col rounded-xl border t-border-strong t-bg-panel shadow-2xl">
            <div className="flex items-center justify-between px-4 py-3 border-b t-border shrink-0">
              <h2 className="text-sm font-semibold flex items-center gap-2">
                <Lightbulb className="w-4 h-4 t-text-accent" />
                我的建议
              </h2>
              <button
                onClick={() => setShowSuggestion(false)}
                className="p-1.5 rounded-lg t-text-faint t-hover-bg t-hover-text transition-colors"
                title="关闭"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* 提交框 */}
            <form onSubmit={handleSubmitSuggestion} className="px-4 py-3 border-b t-border shrink-0">
              <textarea
                value={suggestionText}
                onChange={(e) => setSuggestionText(e.target.value)}
                placeholder="给管理员提一条建议（功能改进、使用问题等），最多 2000 字..."
                rows={3}
                className="w-full resize-none rounded-lg border t-border-strong t-bg-app t-text px-3 py-2 text-xs outline-none focus:border-accent"
              />
              <div className="flex justify-end mt-2">
                <button
                  type="submit"
                  disabled={!suggestionText.trim() || sending}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs rounded-lg t-bg-accent t-hover-accent text-white transition-colors disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  {sending ? '提交中...' : '提交建议'}
                </button>
              </div>
            </form>

            {/* 自己的建议列表 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {mySuggestions.length === 0 ? (
                <div className="text-center t-text-fainter py-10">
                  <Lightbulb className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p className="text-xs">暂无建议，提交后会显示在这里</p>
                </div>
              ) : (
                mySuggestions.map((s) => (
                  <div
                    key={s.id}
                    className={`rounded-lg border p-3 ${
                      s.status === 'replied' ? 't-border-accent' : 't-border'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full border t-border-strong t-text-muted">
                        {s.created_at?.slice(0, 19).replace('T', ' ') || ''}
                      </span>
                      <span
                        className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                          s.status === 'replied' ? 't-badge-accent' : 't-badge-neutral'
                        }`}
                      >
                        {s.status === 'replied' ? '已回复' : '待处理'}
                      </span>
                    </div>
                    <p className="text-xs whitespace-pre-wrap break-words t-text">{s.content}</p>
                    {s.status === 'replied' && s.reply && (
                      <div className="mt-2 rounded-lg border t-border-accent/40 p-2.5">
                        <p className="text-[10px] font-semibold t-text-accent mb-1">管理员回复</p>
                        <p className="text-xs whitespace-pre-wrap break-words t-text-2">{s.reply}</p>
                        {s.replied_at && (
                          <p className="text-[10px] t-text-faint mt-1.5">{s.replied_at?.slice(0, 19).replace('T', ' ')}</p>
                        )}
                      </div>
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

export default Workbench
