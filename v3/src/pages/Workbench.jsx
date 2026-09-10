import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Shell, LogOut, Shield, Plus, Trash2, MessageSquare,
  FolderOpen, FileCode, Brain, Clock, BookOpen, Wrench, Bot,
  PanelRightClose, PanelRightOpen,
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { apiGet, apiDelete, readFileContent } from '../api/client'
import ChatPane from '../components/ChatPane'
import FilesTab from '../components/FilesTab'
import ScriptsTab from '../components/ScriptsTab'
import MemoryTab from '../components/MemoryTab'
import CronTab from '../components/CronTab'
import KnowledgeTab from '../components/KnowledgeTab'
import McpTab from '../components/McpTab'
import AgentTab from '../components/AgentTab'
import ThemeSwitcher from '../components/ThemeSwitcher'

const TABS = [
  { key: 'files', label: '文件', icon: FolderOpen },
  { key: 'scripts', label: '脚本', icon: FileCode },
  { key: 'agents', label: 'Agent', icon: Bot },
  { key: 'memory', label: '记忆', icon: Brain },
  { key: 'cron', label: 'Cron', icon: Clock },
  { key: 'knowledge', label: '知识库', icon: BookOpen },
  { key: 'mcp', label: 'MCP', icon: Wrench },
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
  const [rightCollapsed, setRightCollapsed] = useState(false)

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

  return (
    <div className="h-screen flex flex-col t-bg-app t-text">
      {/* 顶栏 */}
      <header className="flex items-center justify-between px-4 py-2.5 border-b t-border t-bg-panel shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg t-bg-accent flex items-center justify-center">
            <Shell className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-sm font-semibold leading-tight">龙虾Claw 多用户版</h1>
            <p className="text-[10px] t-text-faint leading-tight">v3 · Multi-User Workbench</p>
          </div>
        </div>
        <div className="flex items-center gap-2.5 text-sm">
          <ThemeSwitcher />
          <span className="t-text-muted">{user?.username}</span>
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
            onClick={handleLogout}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors"
          >
            <LogOut className="w-3.5 h-3.5" />
            退出
          </button>
        </div>
      </header>

      <div className="flex-1 flex min-h-0">
        {/* 左栏：会话列表 */}
        <aside className="w-64 shrink-0 border-r t-border flex flex-col t-bg-app">
          <div className="p-3 flex items-center gap-2 border-b t-border">
            <button
              onClick={startNewSession}
              className="flex-1 inline-flex items-center justify-center gap-1.5 px-3 py-2 text-xs rounded-lg t-bg-accent t-hover-accent text-white transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              新建会话
            </button>

          </div>
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
        <aside className={`${rightCollapsed ? 'w-0 border-l-0' : 'w-80 border-l'} shrink-0 flex flex-col t-bg-app overflow-hidden transition-all duration-200`}>
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
          </div>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}

export default Workbench
