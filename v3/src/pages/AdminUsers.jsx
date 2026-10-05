import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, Shield, ShieldOff, Smartphone, KeyRound, RefreshCw, Ban, CheckCircle, XCircle, MessageSquare, ChevronRight, ArrowLeft as ArrowLeftIcon, Maximize2, Minimize2, ClipboardList, Search, ArrowLeftRight, Lightbulb, Send, X, BookOpen, Zap, BarChart3, Database } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { apiGet, apiPost, apiPut, apiDelete } from '../api/client'
import ThemeSwitcher from '../components/ThemeSwitcher'
import MarkdownContent from '../components/MarkdownContent'

function AdminUsers() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState({ role: 'user', display_name: '', new_password: '' })
  const [createForm, setCreateForm] = useState({ username: '', password: '', role: 'user', display_name: '' })

  const loadUsers = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await apiGet('/admin/users')
      setUsers(result.users || [])
    } catch (e) {
      setError(e.message || '加载用户失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadUsers()
  }, [loadUsers])

  // 用户列表搜索 + 前端分页
  const [searchText, setSearchText] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)

  const filteredUsers = (() => {
    const kw = searchText.trim().toLowerCase()
    if (!kw) return users
    return users.filter(
      (u) =>
        (u.username || '').toLowerCase().includes(kw) ||
        (u.display_name || '').toLowerCase().includes(kw)
    )
  })()

  useEffect(() => {
    // 搜索/每页条数变化时回到第一页
    setPage(1)
  }, [searchText, pageSize])

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / pageSize))
  const safePage = Math.min(page, totalPages)
  const pagedUsers = filteredUsers.slice((safePage - 1) * pageSize, safePage * pageSize)

  const handleCreate = async (e) => {
    e.preventDefault()
    setError('')
    try {
      const result = await apiPost('/admin/users', createForm)
      if (result.status === 'success') {
        setShowCreate(false)
        setCreateForm({ username: '', password: '', role: 'user', display_name: '' })
        loadUsers()
      } else {
        setError(result.message || result.detail || '创建失败')
      }
    } catch (e2) {
      setError(e2.message || '创建失败')
    }
  }

  const startEdit = (u) => {
    setEditingId(u.id)
    setEditForm({ role: u.role, display_name: u.display_name || '', new_password: '' })
  }

  const handleUpdate = async (userId) => {
    setError('')
    try {
      const payload = { role: editForm.role, display_name: editForm.display_name }
      if (editForm.new_password) payload.new_password = editForm.new_password
      const result = await apiPut(`/admin/users/${userId}`, payload)
      if (result.status === 'success') {
        setEditingId(null)
        loadUsers()
      } else {
        setError(result.detail || result.message || '更新失败')
      }
    } catch (e2) {
      setError(e2.message || '更新失败')
    }
  }

  const handleToggleDisabled = async (u) => {
    setError('')
    try {
      const result = await apiPut(`/admin/users/${u.id}`, { disabled: !u.disabled })
      if (result.status === 'success') {
        loadUsers()
      } else {
        setError(result.detail || result.message || '操作失败')
      }
    } catch (e2) {
      setError(e2.message || '操作失败')
    }
  }

  const handleDelete = async (u) => {
    if (!window.confirm(`确定删除用户 "${u.username}" 吗？其所有数据将被清除。`)) return
    setError('')
    try {
      const result = await apiDelete(`/admin/users/${u.id}`)
      if (result.status === 'success') {
        loadUsers()
      } else {
        setError(result.detail || result.message || '删除失败')
      }
    } catch (e2) {
      setError(e2.message || '删除失败')
    }
  }

  const handleDisableTotp = async (u) => {
    if (!window.confirm(`确定解绑用户 "${u.display_name || u.username}" 的微软 Authenticator 两步认证吗？解绑后该用户登录将不再需要二次验证。`)) return
    setError('')
    try {
      const result = await apiPost(`/admin/users/${u.id}/totp/disable`, {})
      if (result.status === 'success') {
        loadUsers()
      } else {
        setError(result.detail || result.message || '解绑失败')
      }
    } catch (e2) {
      setError(e2.message || '解绑失败')
    }
  }

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  // 查看用户聊天
  const [chatUser, setChatUser] = useState(null)       // { id, username }
  const [chatSessions, setChatSessions] = useState([])
  const [chatLoading, setChatLoading] = useState(false)
  const [chatError, setChatError] = useState('')
  const [viewSession, setViewSession] = useState(null)  // { id, messages }
  const [msgsLoading, setMsgsLoading] = useState(false)
  const [chatMaximized, setChatMaximized] = useState(false)

  const handleViewChat = async (u) => {
    setChatUser({ id: u.id, username: u.username, display_name: u.display_name })
    setChatMaximized(true)
    setChatSessions([])
    setChatError('')
    setViewSession(null)
    setChatLoading(true)
    try {
      const res = await apiGet(`/admin/users/${u.id}/sessions`)
      if (res.success) {
        setChatSessions(res.sessions || [])
      } else {
        setChatError(res.error || '加载失败')
      }
    } catch (e) {
      setChatError(e.message)
    } finally {
      setChatLoading(false)
    }
  }

  const handleViewSessionMsgs = async (sessionId) => {
    setViewSession(null)
    setMsgsLoading(true)
    try {
      const res = await apiGet(`/admin/users/${chatUser.id}/sessions/${sessionId}/messages`)
      if (res.success) {
        setViewSession({ id: sessionId, messages: res.session.messages || [] })
      } else {
        setChatError(res.error || '加载失败')
      }
    } catch (e) {
      setChatError(e.message)
    } finally {
      setMsgsLoading(false)
    }
  }

  const closeChatModal = () => {
    setChatUser(null)
    setChatSessions([])
    setViewSession(null)
    setChatError('')
    setChatMaximized(false)
  }

  // 日志管理
  const [showLogs, setShowLogs] = useState(false)
  const [logFilter, setLogFilter] = useState({ username: '', operation: '' })
  const [logs, setLogs] = useState([])
  const [logTotal, setLogTotal] = useState(0)
  const [logsLoading, setLogsLoading] = useState(false)
  const [logError, setLogError] = useState('')
  const [logPage, setLogPage] = useState(1)
  const [logMaximized, setLogMaximized] = useState(false)
  const LOG_PAGE_SIZE = 20

  const loadLogs = useCallback(async (page = 1) => {
    setLogsLoading(true)
    setLogError('')
    try {
      const params = new URLSearchParams()
      if (logFilter.username) {
        const u = users.find((x) => x.username === logFilter.username)
        if (u) params.set('user_id', u.id)
      }
      if (logFilter.operation) params.set('operation', logFilter.operation)
      params.set('limit', LOG_PAGE_SIZE)
      params.set('offset', (page - 1) * LOG_PAGE_SIZE)
      const res = await apiGet(`/admin/logs?${params.toString()}`)
      if (res.success) {
        setLogs(res.logs || [])
        setLogTotal(res.total || 0)
        setLogPage(page)
      } else {
        setLogError(res.error || '加载日志失败')
      }
    } catch (e) {
      setLogError(e.message)
    } finally {
      setLogsLoading(false)
    }
  }, [logFilter, users])

  useEffect(() => {
    if (showLogs) loadLogs(1)
  }, [showLogs, loadLogs])

  const closeLogsModal = () => {
    setShowLogs(false)
    setLogFilter({ username: '', operation: '' })
    setLogPage(1)
    setLogMaximized(false)
  }

  const handleDeleteLog = async (log) => {
    if (!window.confirm(`确定删除日志 #${log.id}（${log.display_name || log.username} · ${log.operation}）吗？`)) return
    try {
      await apiDelete(`/admin/logs/${log.id}`)
      loadLogs()
    } catch (e) {
      setLogError(e.message)
    }
  }

  const handleClearLogs = async () => {
    const scope = logFilter.username ? `用户 ${logFilter.username} 的` : '全部'
    if (!window.confirm(`确定清空${scope}日志吗？此操作不可恢复。`)) return
    try {
      const params = new URLSearchParams()
      if (logFilter.username) {
        const u = users.find((x) => x.username === logFilter.username)
        if (u) params.set('user_id', u.id)
      }
      await apiDelete(`/admin/logs?${params.toString()}`)
      loadLogs()
    } catch (e) {
      setLogError(e.message)
    }
  }

  // 操作类型显示名
  const OP_LABELS = {
    login: '登录',
    login_failed: '登录失败',
    logout: '退出登录',
    chat: '聊天',
    tool: '工具调用',
    'admin:delete_log': '管理员·删除日志',
    'admin:clear_logs': '管理员·清空日志',
  }
  const opLabel = (op) => OP_LABELS[op] || op

  // 接口访问日志
  const [showApiLogs, setShowApiLogs] = useState(false)
  const [apiLogs, setApiLogs] = useState([])
  const [apiLogTotal, setApiLogTotal] = useState(0)
  const [apiLogsLoading, setApiLogsLoading] = useState(false)
  const [apiLogError, setApiLogError] = useState('')
  const [apiLogPage, setApiLogPage] = useState(1)
  const [apiLogMaximized, setApiLogMaximized] = useState(false)
  const [apiLogFilter, setApiLogFilter] = useState({ username: '', path: '', status: '' })
  const API_LOG_PAGE_SIZE = 20

  const loadApiLogs = useCallback(async (page = 1) => {
    setApiLogsLoading(true)
    setApiLogError('')
    try {
      const params = new URLSearchParams()
      if (apiLogFilter.username) {
        const u = users.find((x) => x.username === apiLogFilter.username)
        if (u) params.set('user_id', u.id)
      }
      if (apiLogFilter.path) params.set('path', apiLogFilter.path)
      if (apiLogFilter.status) params.set('status', apiLogFilter.status)
      params.set('limit', API_LOG_PAGE_SIZE)
      params.set('offset', (page - 1) * API_LOG_PAGE_SIZE)
      const res = await apiGet(`/admin/api-access-logs?${params.toString()}`)
      if (res.success) {
        setApiLogs(res.logs || [])
        setApiLogTotal(res.total || 0)
        setApiLogPage(page)
      } else {
        setApiLogError(res.error || '加载接口日志失败')
      }
    } catch (e) {
      setApiLogError(e.message)
    } finally {
      setApiLogsLoading(false)
    }
  }, [apiLogFilter, users])

  useEffect(() => {
    if (showApiLogs) loadApiLogs(1)
  }, [showApiLogs, loadApiLogs])

  const closeApiLogsModal = () => {
    setShowApiLogs(false)
    setApiLogFilter({ username: '', path: '', status: '' })
    setApiLogPage(1)
    setApiLogMaximized(false)
  }

  // 用户大模型使用排行
  const [showRanking, setShowRanking] = useState(false)
  const [ranking, setRanking] = useState([])
  const [rankingLoading, setRankingLoading] = useState(false)
  const [rankingError, setRankingError] = useState('')
  const [rankingMaximized, setRankingMaximized] = useState(false)

  const loadRanking = useCallback(async () => {
    setRankingLoading(true)
    setRankingError('')
    try {
      const res = await apiGet('/admin/usage-ranking')
      if (res.success) {
        setRanking(res.ranking || [])
      } else {
        setRankingError(res.error || '加载排行失败')
      }
    } catch (e) {
      setRankingError(e.message || '加载排行失败')
    } finally {
      setRankingLoading(false)
    }
  }, [])

  useEffect(() => {
    if (showRanking) loadRanking()
  }, [showRanking, loadRanking])

  const closeRankingModal = () => {
    setShowRanking(false)
    setRankingMaximized(false)
  }

  const fmtTok = (n) => {
    if (!n) return '0'
    if (n >= 10000) return (n / 10000).toFixed(1) + '万'
    return n.toLocaleString()
  }

  // 数据库维护（VACUUM 等）
  const [maintaining, setMaintaining] = useState(false)
  const handleDbMaintenance = async () => {
    if (!window.confirm('执行数据库维护（回收空间/优化查询）？可能耗时数秒，期间短暂阻塞写入。')) return
    setMaintaining(true)
    try {
      const res = await apiPost('/admin/db-maintenance')
      if (res.success) {
        const freed = ((res.info?.freed_bytes || 0) / 1048576).toFixed(2)
        alert(`维护完成，释放 ${freed} MB 空间。`)
        loadUsers()
      } else {
        alert(res.error || '维护失败')
      }
    } catch (e) {
      alert('维护失败：' + (e.message || ''))
    } finally {
      setMaintaining(false)
    }
  }

  const handleDeleteApiLog = async (log) => {
    if (!window.confirm(`确定删除接口日志 #${log.id}（${log.display_name || log.username} · ${log.method} ${log.path}）吗？`)) return
    try {
      await apiDelete(`/admin/api-access-logs/${log.id}`)
      loadApiLogs(apiLogPage)
    } catch (e) {
      setApiLogError(e.message)
    }
  }

  const handleClearApiLogs = async () => {
    const scope = apiLogFilter.username ? `用户 ${apiLogFilter.username} 的` : '全部'
    if (!window.confirm(`确定清空${scope}接口访问日志吗？此操作不可恢复。`)) return
    try {
      const params = new URLSearchParams()
      if (apiLogFilter.username) {
        const u = users.find((x) => x.username === apiLogFilter.username)
        if (u) params.set('user_id', u.id)
      }
      await apiDelete(`/admin/api-access-logs?${params.toString()}`)
      loadApiLogs(1)
    } catch (e) {
      setApiLogError(e.message)
    }
  }

  // 用户建议管理
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [suggestions, setSuggestions] = useState([])
  const [suggestionTotal, setSuggestionTotal] = useState(0)
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)
  const [suggestionError, setSuggestionError] = useState('')
  const [suggestionPage, setSuggestionPage] = useState(1)
  const [suggestionMaximized, setSuggestionMaximized] = useState(false)
  const [suggestionStatusFilter, setSuggestionStatusFilter] = useState('')
  const [replyingId, setReplyingId] = useState(null)
  const [replyText, setReplyText] = useState('')
  const [replying, setReplying] = useState(false)
  const SUGGESTION_PAGE_SIZE = 20

  const loadSuggestions = useCallback(async (page = 1) => {
    setSuggestionsLoading(true)
    setSuggestionError('')
    try {
      const params = new URLSearchParams()
      if (suggestionStatusFilter) params.set('status', suggestionStatusFilter)
      params.set('limit', SUGGESTION_PAGE_SIZE)
      params.set('offset', (page - 1) * SUGGESTION_PAGE_SIZE)
      const res = await apiGet(`/admin/suggestions?${params.toString()}`)
      if (res.success) {
        setSuggestions(res.suggestions || [])
        setSuggestionTotal(res.total || 0)
        setSuggestionPage(page)
      } else {
        setSuggestionError(res.error || '加载建议失败')
      }
    } catch (e) {
      setSuggestionError(e.message)
    } finally {
      setSuggestionsLoading(false)
    }
  }, [suggestionStatusFilter])

  useEffect(() => {
    if (showSuggestions) loadSuggestions(1)
  }, [showSuggestions, loadSuggestions])

  const closeSuggestionsModal = () => {
    setShowSuggestions(false)
    setSuggestionStatusFilter('')
    setSuggestionPage(1)
    setSuggestionMaximized(false)
    setReplyingId(null)
    setReplyText('')
  }

  const openReply = (sug) => {
    setReplyingId(sug.id)
    setReplyText(sug.reply || '')
  }

  const handleReplySuggestion = async (sug) => {
    const reply = replyText.trim()
    if (!reply || replying) return
    setReplying(true)
    try {
      await apiPut(`/admin/suggestions/${sug.id}/reply`, { reply })
      setReplyingId(null)
      setReplyText('')
      loadSuggestions(suggestionPage)
    } catch (e) {
      setSuggestionError(e.message)
    } finally {
      setReplying(false)
    }
  }

  const handleDeleteSuggestion = async (sug) => {
    if (!window.confirm(`确定删除建议 #${sug.id}（来自 ${sug.display_name || sug.username || '未知用户'}）吗？`)) return
    try {
      await apiDelete(`/admin/suggestions/${sug.id}`)
      loadSuggestions(suggestionPage)
    } catch (e) {
      setSuggestionError(e.message)
    }
  }

  const handleClearSuggestions = async () => {
    const scope = suggestionStatusFilter ? `「${suggestionStatusFilter === 'replied' ? '已回复' : '待处理'}」状态的` : '全部'
    if (!window.confirm(`确定清空${scope}用户建议吗？此操作不可恢复。`)) return
    try {
      const params = new URLSearchParams()
      if (suggestionStatusFilter) params.set('status', suggestionStatusFilter)
      await apiDelete(`/admin/suggestions?${params.toString()}`)
      loadSuggestions(1)
    } catch (e) {
      setSuggestionError(e.message)
    }
  }

  const inputCls =
    'px-3 py-2 t-bg-input border t-border-strong rounded-lg text-sm t-text t-placeholder t-focus'
  const btnGhost =
    'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors'
  const btnDanger =
    'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-danger t-text-danger t-bg-danger-soft transition-colors'

  return (
    <div className="min-h-screen t-bg-app t-text">
      {/* 顶栏 */}
      <header className="border-b t-border t-bg-panel">
        <div className="w-full px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              to="/"
              className="inline-flex items-center gap-1 text-sm t-text-muted t-hover-text"
            >
              <ArrowLeft className="w-4 h-4" />
              返回工作台
            </Link>
            <span className="t-text-fainter">|</span>
            <h1 className="text-base font-semibold flex items-center gap-2">
              <Shield className="w-5 h-5 t-text-accent" />
              用户管理
            </h1>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="t-text-muted">
              {user?.display_name || user?.username}
              <span className="ml-2 text-xs px-2 py-0.5 rounded-full t-badge-accent">
                管理员
              </span>
            </span>
            <ThemeSwitcher />
            <button
              onClick={handleLogout}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card"
            >
              <KeyRound className="w-3.5 h-3.5" />
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="w-full px-4 py-6">
        {error && (
          <div className="mb-4 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">
            {error}
          </div>
        )}

        <div className="flex items-center justify-between mb-4 gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <p className="text-sm t-text-muted">
              共 {filteredUsers.length} 个用户{searchText.trim() ? `（已筛选）` : ''}
            </p>
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 t-text-faint" />
              <input
                className={inputCls + ' pl-8 w-48'}
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                placeholder="搜索用户名 / 显示名"
              />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={loadUsers} className={btnGhost} disabled={loading}>
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              刷新
            </button>
            <button onClick={handleDbMaintenance} disabled={maintaining} className={btnGhost} title="VACUUM 回收空间、优化查询（变慢时执行）">
              <Database className={`w-3.5 h-3.5 ${maintaining ? 'animate-spin' : ''}`} />
              {maintaining ? '维护中' : '数据库维护'}
            </button>
            <button onClick={() => { setLogPage(1); setLogMaximized(true); setShowLogs(true) }} className={btnGhost}>
              <ClipboardList className="w-3.5 h-3.5" />
              日志管理
            </button>
            <button onClick={() => { setApiLogPage(1); setApiLogMaximized(true); setShowApiLogs(true) }} className={btnGhost}>
              <ArrowLeftRight className="w-3.5 h-3.5" />
              接口日志
            </button>
            <button onClick={() => { setSuggestionPage(1); setSuggestionStatusFilter(''); setSuggestionMaximized(true); setShowSuggestions(true) }} className={btnGhost}>
              <Lightbulb className="w-3.5 h-3.5" />
              建议管理
            </button>
            <Link to="/admin/knowledge" className={btnGhost}>
              <BookOpen className="w-3.5 h-3.5" />
              知识库共享
            </Link>
            <Link to="/admin/model-speed" className={btnGhost}>
              <Zap className="w-3.5 h-3.5" />
              模型速度
            </Link>
            <button onClick={() => { setRankingMaximized(true); setShowRanking(true) }} className={btnGhost}>
              <BarChart3 className="w-3.5 h-3.5" />
              用户排行
            </button>
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg t-bg-accent t-hover-accent text-white"
            >
              <Plus className="w-3.5 h-3.5" />
              新建用户
            </button>
          </div>
        </div>

        {showCreate && (
          <form
            onSubmit={handleCreate}
            className="mb-4 p-4 t-bg-panel border t-border rounded-xl grid grid-cols-1 md:grid-cols-5 gap-3 items-end"
          >
            <div>
              <label className="block text-xs t-text-muted mb-1">用户名 *</label>
              <input
                className={inputCls + ' w-full'}
                value={createForm.username}
                onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })}
                placeholder="登录名"
                required
              />
            </div>
            <div>
              <label className="block text-xs t-text-muted mb-1">密码 *</label>
              <input
                type="password"
                className={inputCls + ' w-full'}
                value={createForm.password}
                onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
                placeholder="初始密码"
                required
              />
            </div>
            <div>
              <label className="block text-xs t-text-muted mb-1">角色</label>
              <select
                className={inputCls + ' w-full'}
                value={createForm.role}
                onChange={(e) => setCreateForm({ ...createForm, role: e.target.value })}
              >
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
            </div>
            <div>
              <label className="block text-xs t-text-muted mb-1">显示名</label>
              <input
                className={inputCls + ' w-full'}
                value={createForm.display_name}
                onChange={(e) => setCreateForm({ ...createForm, display_name: e.target.value })}
                placeholder="昵称（可选）"
              />
            </div>
            <div className="flex gap-2">
              <button type="submit" className="px-3 py-2 text-xs rounded-lg t-bg-accent t-hover-accent text-white">
                创建
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="px-3 py-2 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card"
              >
                取消
              </button>
            </div>
          </form>
        )}

        <div className="t-bg-panel border t-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs t-text-faint border-b t-border">
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">用户名</th>
                <th className="px-4 py-3">显示名 / 角色</th>
                <th className="px-4 py-3">状态</th>
                <th className="px-4 py-3">两步认证</th>
                <th className="px-4 py-3">最后登录</th>
                <th className="px-4 py-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="7" className="px-4 py-10 text-center t-text-faint loading-pulse">
                    加载中...
                  </td>
                </tr>
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan="7" className="px-4 py-10 text-center t-text-faint">
                    {searchText.trim() ? '未找到匹配的用户' : '暂无用户'}
                  </td>
                </tr>
              ) : (
                pagedUsers.map((u) => (
                  <tr key={u.id} className="border-b t-border t-hover-bg">
                    <td className="px-4 py-3 t-text-faint">{u.id}</td>
                    <td className="px-4 py-3 font-medium">{u.username}</td>
                    <td className="px-4 py-3">
                      {editingId === u.id ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <input
                            className={inputCls + ' w-28'}
                            value={editForm.display_name}
                            onChange={(e) => setEditForm({ ...editForm, display_name: e.target.value })}
                            placeholder="显示名"
                          />
                          <select
                            className={inputCls}
                            value={editForm.role}
                            onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}
                          >
                            <option value="user">user</option>
                            <option value="admin">admin</option>
                          </select>
                          <input
                            type="password"
                            className={inputCls + ' w-32'}
                            value={editForm.new_password}
                            onChange={(e) => setEditForm({ ...editForm, new_password: e.target.value })}
                            placeholder="新密码（可选）"
                          />
                          <button
                            onClick={() => handleUpdate(u.id)}
                            className="px-3 py-1.5 text-xs rounded-lg t-bg-accent t-hover-accent text-white"
                          >
                            保存
                          </button>
                          <button onClick={() => setEditingId(null)} className={btnGhost}>
                            取消
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <span>{u.display_name || '-'}</span>
                          <span
                            className={`text-xs px-2 py-0.5 rounded-full border ${
                              u.role === 'admin' ? 't-badge-accent' : 't-badge-neutral'
                            }`}
                          >
                            {u.role}
                          </span>
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {u.disabled ? (
                        <span className="inline-flex items-center gap-1 text-xs t-text-danger">
                          <Ban className="w-3.5 h-3.5" />
                          已禁用
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs t-text-ok">
                          <CheckCircle className="w-3.5 h-3.5" />
                          正常
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {u.totp_enabled ? (
                        <span className="inline-flex items-center gap-1 text-xs t-text-ok">
                          <Smartphone className="w-3.5 h-3.5" />
                          已启用
                        </span>
                      ) : (
                        <span className="text-xs t-text-faint">未启用</span>
                      )}
                    </td>
                    <td className="px-4 py-3 t-text-faint text-xs">{u.last_login_at || '从未登录'}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {editingId !== u.id && (
                          <>
                            <button onClick={() => startEdit(u)} className={btnGhost}>
                              <KeyRound className="w-3.5 h-3.5" />
                              编辑
                            </button>
                            <button onClick={() => handleViewChat(u)} className={btnGhost}>
                              <MessageSquare className="w-3.5 h-3.5" />
                              聊天
                            </button>
                            <button onClick={() => handleToggleDisabled(u)} className={btnGhost}>
                              {u.disabled ? (
                                <>
                                  <CheckCircle className="w-3.5 h-3.5" />
                                  启用
                                </>
                              ) : (
                                <>
                                  <XCircle className="w-3.5 h-3.5" />
                                  禁用
                                </>
                              )}
                            </button>
                            {u.totp_enabled && (
                              <button onClick={() => handleDisableTotp(u)} className={btnGhost} title="解绑微软 Authenticator 两步认证">
                                <ShieldOff className="w-3.5 h-3.5" />
                                解绑认证
                              </button>
                            )}
                            {u.id !== user?.id && (
                              <button onClick={() => handleDelete(u)} className={btnDanger}>
                                <Trash2 className="w-3.5 h-3.5" />
                                删除
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          {filteredUsers.length > 0 && (
            <div className="flex items-center justify-between flex-wrap gap-2 px-4 py-3 border-t t-border text-xs t-text-muted">
              <div className="flex items-center gap-2">
                <span>
                  第 {safePage} / {totalPages} 页 · 共 {filteredUsers.length} 条
                </span>
                <select
                  className={inputCls + ' w-auto py-1'}
                  value={pageSize}
                  onChange={(e) => setPageSize(Number(e.target.value))}
                >
                  <option value={10}>10 条/页</option>
                  <option value={20}>20 条/页</option>
                  <option value={50}>50 条/页</option>
                </select>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage(1)}
                  disabled={safePage === 1}
                  className={btnGhost + ' px-2 py-1 disabled:opacity-40 disabled:cursor-not-allowed'}
                >
                  首页
                </button>
                <button
                  onClick={() => setPage(safePage - 1)}
                  disabled={safePage === 1}
                  className={btnGhost + ' px-2 py-1 disabled:opacity-40 disabled:cursor-not-allowed'}
                >
                  上一页
                </button>
                <span className="px-2">
                  {safePage}
                </span>
                <button
                  onClick={() => setPage(safePage + 1)}
                  disabled={safePage === totalPages}
                  className={btnGhost + ' px-2 py-1 disabled:opacity-40 disabled:cursor-not-allowed'}
                >
                  下一页
                </button>
                <button
                  onClick={() => setPage(totalPages)}
                  disabled={safePage === totalPages}
                  className={btnGhost + ' px-2 py-1 disabled:opacity-40 disabled:cursor-not-allowed'}
                >
                  末页
                </button>
              </div>
            </div>
          )}
        </div>
      </main>

      {/* 用户大模型使用排行 Modal */}
      {showRanking && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/70"
          onClick={closeRankingModal}
        >
          <div
            className={`t-bg-panel border t-border-strong rounded-2xl shadow-2xl flex flex-col transition-all duration-200 ${
              rankingMaximized ? 'w-full max-w-none h-full max-h-none' : 'w-full max-w-4xl max-h-[85vh]'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-3.5 border-b t-border shrink-0">
              <h3 className="text-sm font-semibold t-text flex items-center gap-2">
                <BarChart3 className="w-4 h-4 t-text-accent" />
                用户大模型使用排行（按调用次数降序）
              </h3>
              <div className="flex items-center gap-2">
                <button onClick={loadRanking} className="t-text-faint t-hover-text transition-colors" title="刷新">
                  <RefreshCw className={`w-4 h-4 ${rankingLoading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={() => setRankingMaximized(!rankingMaximized)}
                  title={rankingMaximized ? '还原' : '最大化'}
                  className="t-text-faint t-hover-text transition-colors"
                >
                  {rankingMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                <button onClick={closeRankingModal} className="t-text-faint t-hover-text transition-colors">
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {rankingError && <p className="text-xs t-text-danger mb-3">{rankingError}</p>}
              {rankingLoading ? (
                <p className="text-xs t-text-faint text-center py-8 loading-pulse">加载中...</p>
              ) : ranking.length === 0 ? (
                <p className="text-xs t-text-fainter text-center py-8">暂无模型调用记录</p>
              ) : (
                <table className="w-full text-xs">
                  <thead className="sticky top-0 t-bg-panel">
                    <tr className="text-left t-text-faint border-b t-border">
                      <th className="px-2 py-2">#</th>
                      <th className="px-2 py-2">用户</th>
                      <th className="px-2 py-2 text-right">调用次数</th>
                      <th className="px-2 py-2 text-right">输入 tokens</th>
                      <th className="px-2 py-2 text-right">输出 tokens</th>
                      <th className="px-2 py-2 text-right">总 tokens</th>
                      <th className="px-2 py-2">各模型调用明细（次数 / 总 tokens）</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ranking.map((u, i) => (
                      <tr key={u.user_id} className="border-b t-border t-hover-bg align-top">
                        <td className="px-2 py-2 t-text-faint">{i + 1}</td>
                        <td className="px-2 py-2 whitespace-nowrap font-medium">
                          {u.display_name || u.username}
                          <span className="ml-1 t-text-faint font-normal">（{u.username}）</span>
                        </td>
                        <td className="px-2 py-2 text-right font-semibold t-text-accent">{u.total_calls}</td>
                        <td className="px-2 py-2 text-right t-text-2">{fmtTok(u.prompt_tokens)}</td>
                        <td className="px-2 py-2 text-right t-text-2">{fmtTok(u.completion_tokens)}</td>
                        <td className="px-2 py-2 text-right t-text-2">{fmtTok(u.total_tokens)}</td>
                        <td className="px-2 py-2">
                          <div className="flex flex-wrap gap-1.5">
                            {(u.models || []).map((m) => (
                              <span
                                key={m.model_name}
                                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border t-border-strong t-bg-input t-text-2 whitespace-nowrap"
                                title={`${m.model_name}：调用 ${m.calls} 次，输入 ${fmtTok(m.prompt_tokens)} / 输出 ${fmtTok(m.completion_tokens)} / 总 ${fmtTok(m.total_tokens)} tokens`}
                              >
                                <span className="t-text-muted">{m.model_name}</span>
                                <span className="t-text-accent font-medium">{m.calls}</span>
                                <span className="t-text-faint">{fmtTok(m.total_tokens)}</span>
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 查看用户聊天 Modal */}
      {chatUser && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/70"
          onClick={closeChatModal}
        >
          <div
            className={`t-bg-panel border t-border-strong rounded-2xl shadow-2xl flex flex-col transition-all duration-200 ${
              chatMaximized ? 'w-full max-w-none h-full max-h-none' : 'w-full max-w-2xl max-h-[85vh]'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b t-border shrink-0">
              <h3 className="text-sm font-semibold t-text flex items-center gap-2">
                <MessageSquare className="w-4 h-4 t-text-accent" />
                {viewSession ? (
                  <button onClick={() => setViewSession(null)} className="inline-flex items-center gap-1.5 t-hover-text-accent">
                    <ArrowLeftIcon className="w-3.5 h-3.5" />
                    返回会话列表
                  </button>
                ) : (
                  `${chatUser.display_name || chatUser.username} 的聊天记录`
                )}
              </h3>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setChatMaximized(!chatMaximized)}
                  title={chatMaximized ? '还原' : '最大化'}
                  className="t-text-faint t-hover-text transition-colors"
                >
                  {chatMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                <button onClick={closeChatModal} className="t-text-faint t-hover-text transition-colors">
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-4">
              {chatError && (
                <p className="text-xs t-text-danger mb-3">{chatError}</p>
              )}

              {/* 会话列表 */}
              {!viewSession && (
                <>
                  {chatLoading ? (
                    <p className="text-xs t-text-faint text-center py-8 loading-pulse">加载中...</p>
                  ) : chatSessions.length === 0 ? (
                    <p className="text-xs t-text-fainter text-center py-8">该用户暂无聊天会话</p>
                  ) : (
                    <div className="space-y-1.5">
                      {chatSessions.map((s) => (
                        <div
                          key={s.id}
                          onClick={() => handleViewSessionMsgs(s.id)}
                          className="px-3 py-2.5 t-bg-input border t-border rounded-lg cursor-pointer t-hover-border-accent t-hover-card transition-colors group"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium t-text-2 truncate flex-1">{s.title || '新会话'}</span>
                            <ChevronRight className="w-4 h-4 t-text-faint group-hover:t-text-accent transition-colors shrink-0" />
                          </div>
                          <div className="flex items-center gap-3 mt-1 text-[10px] t-text-faint">
                            <span>{s.message_count || 0} 条消息</span>
                            {s.preview && <span className="truncate flex-1">{s.preview}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}

              {/* 消息列表 */}
              {viewSession && (
                <>
                  {msgsLoading ? (
                    <p className="text-xs t-text-faint text-center py-8 loading-pulse">加载中...</p>
                  ) : viewSession.messages.length === 0 ? (
                    <p className="text-xs t-text-fainter text-center py-8">该会话暂无消息</p>
                  ) : (
                    <div className="space-y-3">
                      {viewSession.messages.map((msg, i) => (
                        <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                          <div
                            className={`max-w-[85%] px-3 py-2 rounded-lg text-sm ${
                              msg.role === 'user'
                                ? 't-bg-accent text-white'
                                : 't-bg-bubble border t-border t-text-2'
                            }`}
                          >
            <p className="text-[10px] t-text-faint mb-1">
              {msg.role === 'user' ? '用户' : 'AI'} · {msg.timestamp || ''}
            </p>
                            {msg.role === 'assistant'
                              ? <MarkdownContent content={msg.content} />
                              : <div className="whitespace-pre-wrap break-words">{msg.content}</div>
                            }
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 日志管理 Modal */}
      {showLogs && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/70"
          onClick={closeLogsModal}
        >
          <div
            className={`t-bg-panel border t-border-strong rounded-2xl shadow-2xl flex flex-col transition-all duration-200 ${
              logMaximized ? 'w-full max-w-none h-full max-h-none' : 'w-full max-w-4xl max-h-[85vh]'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b t-border shrink-0">
              <h3 className="text-sm font-semibold t-text flex items-center gap-2">
                <ClipboardList className="w-4 h-4 t-text-accent" />
                操作日志（共 {logTotal} 条）
              </h3>
              <div className="flex items-center gap-2">
                <button onClick={() => loadLogs(logPage)} className="t-text-faint t-hover-text transition-colors" title="刷新">
                  <RefreshCw className={`w-4 h-4 ${logsLoading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={() => setLogMaximized(!logMaximized)}
                  title={logMaximized ? '还原' : '最大化'}
                  className="t-text-faint t-hover-text transition-colors"
                >
                  {logMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                <button onClick={closeLogsModal} className="t-text-faint t-hover-text transition-colors">
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* 筛选栏 */}
            <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-b t-border shrink-0">
              <div className="relative">
                <Search className="w-3.5 h-3.5 t-text-faint absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  className="px-3 py-1.5 pl-8 text-xs t-bg-input border t-border-strong rounded-lg t-text w-44"
                  placeholder="按用户名筛选"
                  value={logFilter.username}
                  onChange={(e) => setLogFilter({ ...logFilter, username: e.target.value })}
                  list="log-usernames"
                />
                <datalist id="log-usernames">
                  {users.map((u) => (
                    <option key={u.id} value={u.username} label={u.display_name || u.username} />
                  ))}
                </datalist>
              </div>
              <select
                className="px-3 py-1.5 text-xs t-bg-input border t-border-strong rounded-lg t-text"
                value={logFilter.operation}
                onChange={(e) => setLogFilter({ ...logFilter, operation: e.target.value })}
              >
                <option value="">全部操作</option>
                <option value="login">登录</option>
                <option value="login_failed">登录失败</option>
                <option value="logout">退出登录</option>
                <option value="chat">聊天</option>
                <option value="tool">工具调用</option>
              </select>
              {(logFilter.username || logFilter.operation) && (
                <button onClick={() => setLogFilter({ username: '', operation: '' })} className={btnGhost}>
                  清除筛选
                </button>
              )}
              <button
                onClick={handleClearLogs}
                className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-danger t-text-danger t-bg-danger-soft transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                清空
              </button>
            </div>

            {/* 日志列表 */}
            <div className="flex-1 overflow-y-auto p-4">
              {logError && <p className="text-xs t-text-danger mb-3">{logError}</p>}
              {logsLoading ? (
                <p className="text-xs t-text-faint text-center py-8 loading-pulse">加载中...</p>
              ) : logs.length === 0 ? (
                <p className="text-xs t-text-fainter text-center py-8">暂无日志</p>
              ) : (
                <table className="w-full text-xs">
                  <thead className="sticky top-0 t-bg-panel">
                    <tr className="text-left t-text-faint border-b t-border">
                      <th className="px-2 py-2">时间</th>
                      <th className="px-2 py-2">用户</th>
                      <th className="px-2 py-2">操作</th>
                      <th className="px-2 py-2">详情</th>
                      <th className="px-2 py-2">IP</th>
                      <th className="px-2 py-2">状态</th>
                      <th className="px-2 py-2 text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {logs.map((log) => (
                      <tr key={log.id} className="border-b t-border t-hover-bg align-top">
                        <td className="px-2 py-2 t-text-faint whitespace-nowrap">
                          {log.created_at?.replace('T', ' ').slice(0, 19)}
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap font-medium">{log.display_name || log.username}</td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <span className={log.operation === 'login_failed' ? 't-text-danger' : 't-text-2'}>
                            {opLabel(log.operation)}
                          </span>
                        </td>
                        <td className="px-2 py-2 t-text-faint max-w-[220px]">
                          <div className="truncate" title={log.detail}>{log.detail || '-'}</div>
                        </td>
                        <td className="px-2 py-2 t-text-faint whitespace-nowrap">{log.ip || '-'}</td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          {log.success ? (
                            <span className="text-ok">成功</span>
                          ) : (
                            <span className="t-text-danger">失败</span>
                          )}
                        </td>
                        <td className="px-2 py-2 text-right whitespace-nowrap">
                          <button onClick={() => handleDeleteLog(log)} className="t-text-faint t-hover-text-danger transition-colors" title="删除">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* 分页控制 */}
            {logTotal > LOG_PAGE_SIZE && (
              <div className="flex items-center justify-between px-5 py-3 border-t t-border shrink-0">
                <span className="text-xs t-text-faint">
                  第 {logPage} / {Math.ceil(logTotal / LOG_PAGE_SIZE)} 页
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => loadLogs(logPage - 1)}
                    disabled={logPage <= 1 || logsLoading}
                    className={`${btnGhost} disabled:opacity-40 disabled:cursor-not-allowed`}
                  >
                    上一页
                  </button>
                  <button
                    onClick={() => loadLogs(logPage + 1)}
                    disabled={logPage >= Math.ceil(logTotal / LOG_PAGE_SIZE) || logsLoading}
                    className={`${btnGhost} disabled:opacity-40 disabled:cursor-not-allowed`}
                  >
                    下一页
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 接口访问日志 Modal */}
      {showApiLogs && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/70"
          onClick={closeApiLogsModal}
        >
          <div
            className={`t-bg-panel border t-border-strong rounded-2xl shadow-2xl flex flex-col transition-all duration-200 ${
              apiLogMaximized ? 'w-full max-w-none h-full max-h-none' : 'w-full max-w-4xl max-h-[85vh]'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b t-border shrink-0">
              <h3 className="text-sm font-semibold t-text flex items-center gap-2">
                <ArrowLeftRight className="w-4 h-4 t-text-accent" />
                接口访问日志（共 {apiLogTotal} 条）
              </h3>
              <div className="flex items-center gap-2">
                <button onClick={() => loadApiLogs(apiLogPage)} className="t-text-faint t-hover-text transition-colors" title="刷新">
                  <RefreshCw className={`w-4 h-4 ${apiLogsLoading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={() => setApiLogMaximized(!apiLogMaximized)}
                  title={apiLogMaximized ? '还原' : '最大化'}
                  className="t-text-faint t-hover-text transition-colors"
                >
                  {apiLogMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                <button onClick={closeApiLogsModal} className="t-text-faint t-hover-text transition-colors">
                  <XCircle className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* 筛选栏 */}
            <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-b t-border shrink-0">
              <div className="relative">
                <Search className="w-3.5 h-3.5 t-text-faint absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  className="px-3 py-1.5 pl-8 text-xs t-bg-input border t-border-strong rounded-lg t-text w-36"
                  placeholder="按用户名筛选"
                  value={apiLogFilter.username}
                  onChange={(e) => setApiLogFilter({ ...apiLogFilter, username: e.target.value })}
                  list="api-log-usernames"
                />
                <datalist id="api-log-usernames">
                  {users.map((u) => (<option key={u.id} value={u.username} label={u.display_name || u.username} />))}
                </datalist>
              </div>
              <input
                className="px-3 py-1.5 text-xs t-bg-input border t-border-strong rounded-lg t-text w-40"
                placeholder="按路径筛选（如 /chat）"
                value={apiLogFilter.path}
                onChange={(e) => setApiLogFilter({ ...apiLogFilter, path: e.target.value })}
              />
              <select
                className="px-3 py-1.5 text-xs t-bg-input border t-border-strong rounded-lg t-text"
                value={apiLogFilter.status}
                onChange={(e) => setApiLogFilter({ ...apiLogFilter, status: e.target.value })}
              >
                <option value="">全部状态</option>
                <option value="200">200</option>
                <option value="401">401</option>
                <option value="403">403</option>
                <option value="404">404</option>
                <option value="429">429</option>
                <option value="500">500</option>
              </select>
              {(apiLogFilter.username || apiLogFilter.path || apiLogFilter.status) && (
                <button onClick={() => setApiLogFilter({ username: '', path: '', status: '' })} className={btnGhost}>
                  清除筛选
                </button>
              )}
              <button
                onClick={handleClearApiLogs}
                className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-danger t-text-danger t-bg-danger-soft transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                清空
              </button>
            </div>

            {/* 日志列表 */}
            <div className="flex-1 overflow-y-auto p-4">
              {apiLogError && <p className="text-xs t-text-danger mb-3">{apiLogError}</p>}
              {apiLogsLoading ? (
                <p className="text-xs t-text-faint text-center py-8 loading-pulse">加载中...</p>
              ) : apiLogs.length === 0 ? (
                <p className="text-xs t-text-fainter text-center py-8">暂无接口访问日志</p>
              ) : (
                <table className="w-full text-xs">
                  <thead className="sticky top-0 t-bg-panel">
                    <tr className="text-left t-text-faint border-b t-border">
                      <th className="px-2 py-2">时间</th>
                      <th className="px-2 py-2">方法</th>
                      <th className="px-2 py-2">路径</th>
                      <th className="px-2 py-2">状态</th>
                      <th className="px-2 py-2">耗时</th>
                      <th className="px-2 py-2">用户</th>
                      <th className="px-2 py-2">IP</th>
                      <th className="px-2 py-2">认证</th>
                      <th className="px-2 py-2 text-right">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {apiLogs.map((log) => (
                      <tr key={log.id} className="border-b t-border t-hover-bg align-top">
                        <td className="px-2 py-2 t-text-faint whitespace-nowrap">
                          {log.created_at?.replace('T', ' ').slice(0, 19)}
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap font-medium">{log.method}</td>
                        <td className="px-2 py-2 max-w-[200px]">
                          <div className="truncate" title={log.path}>{log.path}</div>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <span className={log.status >= 400 ? 't-text-danger' : 't-text-ok'}>{log.status}</span>
                        </td>
                        <td className="px-2 py-2 t-text-faint whitespace-nowrap">{log.duration_ms}ms</td>
                        <td className="px-2 py-2 whitespace-nowrap font-medium">{log.display_name || log.username || '-'}</td>
                        <td className="px-2 py-2 t-text-faint whitespace-nowrap">{log.ip || '-'}</td>
                        <td className="px-2 py-2 t-text-faint whitespace-nowrap">{log.auth_type}</td>
                        <td className="px-2 py-2 text-right whitespace-nowrap">
                          <button onClick={() => handleDeleteApiLog(log)} className="t-text-faint t-hover-text-danger transition-colors" title="删除">
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* 分页控制 */}
            {apiLogTotal > API_LOG_PAGE_SIZE && (
              <div className="flex items-center justify-between px-5 py-3 border-t t-border shrink-0">
                <span className="text-xs t-text-faint">
                  第 {apiLogPage} / {Math.ceil(apiLogTotal / API_LOG_PAGE_SIZE)} 页
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => loadApiLogs(apiLogPage - 1)}
                    disabled={apiLogPage <= 1 || apiLogsLoading}
                    className={`${btnGhost} disabled:opacity-40 disabled:cursor-not-allowed`}
                  >
                    上一页
                  </button>
                  <button
                    onClick={() => loadApiLogs(apiLogPage + 1)}
                    disabled={apiLogPage >= Math.ceil(apiLogTotal / API_LOG_PAGE_SIZE) || apiLogsLoading}
                    className={`${btnGhost} disabled:opacity-40 disabled:cursor-not-allowed`}
                  >
                    下一页
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 用户建议管理 Modal */}
      {showSuggestions && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-black/70"
          onClick={closeSuggestionsModal}
        >
          <div
            className={`t-bg-panel border t-border-strong rounded-2xl shadow-2xl flex flex-col transition-all duration-200 ${
              suggestionMaximized ? 'w-full max-w-none h-full max-h-none' : 'w-full max-w-4xl max-h-[85vh]'
            }`}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-3.5 border-b t-border shrink-0">
              <h3 className="text-sm font-semibold t-text flex items-center gap-2">
                <Lightbulb className="w-4 h-4 t-text-accent" />
                用户建议（共 {suggestionTotal} 条）
              </h3>
              <div className="flex items-center gap-2">
                <button onClick={() => loadSuggestions(suggestionPage)} className="t-text-faint t-hover-text transition-colors" title="刷新">
                  <RefreshCw className={`w-4 h-4 ${suggestionsLoading ? 'animate-spin' : ''}`} />
                </button>
                <button
                  onClick={() => setSuggestionMaximized(!suggestionMaximized)}
                  title={suggestionMaximized ? '还原' : '最大化'}
                  className="t-text-faint t-hover-text transition-colors"
                >
                  {suggestionMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                </button>
                <button onClick={closeSuggestionsModal} className="t-text-faint t-hover-text transition-colors">
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* 筛选栏 */}
            <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-b t-border shrink-0">
              <select
                className="px-3 py-1.5 text-xs t-bg-input border t-border-strong rounded-lg t-text"
                value={suggestionStatusFilter}
                onChange={(e) => setSuggestionStatusFilter(e.target.value)}
              >
                <option value="">全部状态</option>
                <option value="pending">待处理</option>
                <option value="replied">已回复</option>
              </select>
              {suggestionStatusFilter && (
                <button onClick={() => setSuggestionStatusFilter('')} className={btnGhost}>
                  清除筛选
                </button>
              )}
              <button
                onClick={handleClearSuggestions}
                className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-danger t-text-danger t-bg-danger-soft transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                清空
              </button>
            </div>

            {/* 建议列表 */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {suggestionError && <p className="text-xs t-text-danger">{suggestionError}</p>}
              {suggestionsLoading ? (
                <p className="text-xs t-text-faint text-center py-8 loading-pulse">加载中...</p>
              ) : suggestions.length === 0 ? (
                <div className="text-center t-text-fainter py-10">
                  <Lightbulb className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p className="text-xs">暂无用户建议</p>
                </div>
              ) : (
                suggestions.map((s) => (
                  <div key={s.id} className="rounded-xl border t-border p-3.5">
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-semibold t-text">{s.display_name || s.username || `用户#${s.user_id}`}</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full border t-border-strong t-text-muted">
                          {s.created_at?.replace('T', ' ').slice(0, 19) || ''}
                        </span>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                            s.status === 'replied' ? 't-badge-accent' : 't-badge-neutral'
                          }`}
                        >
                          {s.status === 'replied' ? '已回复' : '待处理'}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          onClick={() => openReply(s)}
                          className="inline-flex items-center gap-1 px-2 py-1 text-[11px] rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors"
                        >
                          <MessageSquare className="w-3 h-3" />
                          {s.status === 'replied' ? '修改回复' : '回复'}
                        </button>
                        <button
                          onClick={() => handleDeleteSuggestion(s)}
                          className="t-text-faint t-hover-text-danger transition-colors"
                          title="删除"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    <p className="text-xs whitespace-pre-wrap break-words t-text-2">{s.content}</p>

                    {/* 已有回复 */}
                    {s.status === 'replied' && s.reply && (
                      <div className="mt-2.5 rounded-lg border t-border-accent/40 p-2.5">
                        <p className="text-[10px] font-semibold t-text-accent mb-1">管理员回复</p>
                        <p className="text-xs whitespace-pre-wrap break-words t-text-2">{s.reply}</p>
                        {s.replied_at && (
                          <p className="text-[10px] t-text-faint mt-1.5">{s.replied_at?.replace('T', ' ').slice(0, 19)}</p>
                        )}
                      </div>
                    )}

                    {/* 回复编辑框 */}
                    {replyingId === s.id && (
                      <div className="mt-2.5">
                        <textarea
                          value={replyText}
                          onChange={(e) => setReplyText(e.target.value)}
                          placeholder="输入回复内容..."
                          rows={2}
                          className="w-full resize-none rounded-lg border t-border-strong t-bg-input t-text px-3 py-2 text-xs outline-none focus:border-accent"
                        />
                        <div className="flex justify-end gap-2 mt-2">
                          <button
                            onClick={() => { setReplyingId(null); setReplyText('') }}
                            className="px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors"
                          >
                            取消
                          </button>
                          <button
                            onClick={() => handleReplySuggestion(s)}
                            disabled={!replyText.trim() || replying}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg t-bg-accent t-hover-accent text-white transition-colors disabled:opacity-50"
                          >
                            <Send className="w-3 h-3" />
                            {replying ? '回复中...' : '发送回复'}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            {/* 分页控制 */}
            {suggestionTotal > SUGGESTION_PAGE_SIZE && (
              <div className="flex items-center justify-between px-5 py-3 border-t t-border shrink-0">
                <span className="text-xs t-text-faint">
                  第 {suggestionPage} / {Math.ceil(suggestionTotal / SUGGESTION_PAGE_SIZE)} 页
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => loadSuggestions(suggestionPage - 1)}
                    disabled={suggestionPage <= 1 || suggestionsLoading}
                    className={`${btnGhost} disabled:opacity-40 disabled:cursor-not-allowed`}
                  >
                    上一页
                  </button>
                  <button
                    onClick={() => loadSuggestions(suggestionPage + 1)}
                    disabled={suggestionPage >= Math.ceil(suggestionTotal / SUGGESTION_PAGE_SIZE) || suggestionsLoading}
                    className={`${btnGhost} disabled:opacity-40 disabled:cursor-not-allowed`}
                  >
                    下一页
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default AdminUsers
