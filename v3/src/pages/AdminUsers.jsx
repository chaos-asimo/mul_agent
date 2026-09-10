import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Plus, Trash2, Shield, ShieldOff, KeyRound, RefreshCw, Ban, CheckCircle, XCircle, MessageSquare, ChevronRight, ArrowLeft as ArrowLeftIcon, Maximize2, Minimize2 } from 'lucide-react'
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
    setChatUser({ id: u.id, username: u.username })
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
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
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
              {user?.username}
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

      <main className="max-w-6xl mx-auto px-4 py-6">
        {error && (
          <div className="mb-4 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">
            {error}
          </div>
        )}

        <div className="flex items-center justify-between mb-4">
          <p className="text-sm t-text-muted">共 {users.length} 个用户</p>
          <div className="flex items-center gap-2">
            <button onClick={loadUsers} className={btnGhost} disabled={loading}>
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              刷新
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
                <th className="px-4 py-3">最后登录</th>
                <th className="px-4 py-3 text-right">操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan="6" className="px-4 py-10 text-center t-text-faint loading-pulse">
                    加载中...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-4 py-10 text-center t-text-faint">
                    暂无用户
                  </td>
                </tr>
              ) : (
                users.map((u) => (
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
        </div>
      </main>

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
                  `${chatUser.username} 的聊天记录`
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
    </div>
  )
}

export default AdminUsers
