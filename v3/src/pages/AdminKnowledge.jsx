import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft, RefreshCw, KeyRound, BookOpen, Users, FileText,
  Database, Layers, Share2, ChevronDown, ChevronRight
} from 'lucide-react'
import { useAuthStore } from '../stores/authStore'
import { apiGet } from '../api/client'
import ThemeSwitcher from '../components/ThemeSwitcher'

function fmtBytes(n) {
  if (!n) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++ }
  return n.toFixed(i === 0 ? 0 : 1) + ' ' + units[i]
}

function StatCard({ icon, label, value, accent }) {
  return (
    <div className="flex items-center gap-3 p-3 t-bg-panel border t-border rounded-xl">
      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${accent ? 't-bg-accent text-white' : 't-bg-input t-text-2'}`}>
        {icon}
      </div>
      <div>
        <div className="text-lg font-semibold leading-tight">{value}</div>
        <div className="text-xs t-text-muted">{label}</div>
      </div>
    </div>
  )
}

function AdminKnowledge() {
  const { user, logout } = useAuthStore()
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState({})

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await apiGet('/admin/knowledge')
      setData(result.data || result)
    } catch (e) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const toggle = (uid) => setExpanded((p) => ({ ...p, [uid]: !p[uid] }))

  const btnGhost =
    'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors'

  const summary = data?.summary
  const users = data?.users || []

  return (
    <div className="min-h-screen t-bg-app t-text">
      {/* 顶栏 */}
      <header className="border-b t-border t-bg-panel">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link to="/" className="inline-flex items-center gap-1 text-sm t-text-muted t-hover-text">
              <ArrowLeft className="w-4 h-4" />
              返回工作台
            </Link>
            <span className="t-text-fainter">|</span>
            <h1 className="text-base font-semibold flex items-center gap-2">
              <BookOpen className="w-5 h-5 t-text-accent" />
              知识库共享情况
            </h1>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <span className="t-text-muted">
              {user?.display_name || user?.username}
              <span className="ml-2 text-xs px-2 py-0.5 rounded-full t-badge-accent">管理员</span>
            </span>
            <ThemeSwitcher />
            <button onClick={logout} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card">
              <KeyRound className="w-3.5 h-3.5" />
              退出
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6">
        {error && (
          <div className="mb-4 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">{error}</div>
        )}

        {/* 操作行 */}
        <div className="flex items-center justify-between mb-4">
          <p className="text-sm t-text-muted">
            {summary ? `${summary.users_with_docs} 个用户共上传 ${summary.total_documents} 篇文档，去重后存储 ${summary.total_unique_contents} 份内容` : '加载中...'}
          </p>
          <button onClick={load} className={btnGhost} disabled={loading}>
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>

        {loading && !data ? (
          <div className="p-10 text-center t-text-faint loading-pulse">加载中...</div>
        ) : (
          <>
            {/* 统计卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mb-6">
              <StatCard icon={<Users className="w-4 h-4" />} label="有文档用户" value={summary?.users_with_docs ?? 0} />
              <StatCard icon={<FileText className="w-4 h-4" />} label="文档总数" value={summary?.total_documents ?? 0} />
              <StatCard icon={<Database className="w-4 h-4" />} label="去重后内容" value={summary?.total_unique_contents ?? 0} accent />
              <StatCard icon={<Layers className="w-4 h-4" />} label="共享池向量" value={summary?.total_shared_vectors ?? 0} />
              <StatCard icon={<Share2 className="w-4 h-4" />} label="共享文档份数" value={users.reduce((s, u) => s + (u.shared_docs || 0), 0)} />
              <StatCard
                icon={<Share2 className="w-4 h-4" />}
                label="节省存储"
                value={summary ? summary.total_documents - summary.total_unique_contents : 0}
                accent
              />
            </div>

            {/* 用户知识库表格 */}
            <div className="t-bg-panel border t-border rounded-xl overflow-hidden mb-6">
              <div className="px-4 py-3 border-b t-border text-sm font-semibold">各用户知识库明细</div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs t-text-faint border-b t-border">
                    <th className="px-4 py-3 w-10"></th>
                    <th className="px-4 py-3">用户</th>
                    <th className="px-4 py-3 text-right">文档数</th>
                    <th className="px-4 py-3 text-right">分块数</th>
                    <th className="px-4 py-3 text-right">共享文档</th>
                  </tr>
                </thead>
                <tbody>
                  {users.length === 0 ? (
                    <tr><td colSpan="5" className="px-4 py-10 text-center t-text-faint">暂无知识库数据</td></tr>
                  ) : (
                    users.map((u) => (
                      <UserRow
                        key={u.user_id}
                        u={u}
                        expanded={!!expanded[u.user_id]}
                        onToggle={() => toggle(u.user_id)}
                      />
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* 共享内容列表 */}
            <div className="t-bg-panel border t-border rounded-xl overflow-hidden">
              <div className="px-4 py-3 border-b t-border text-sm font-semibold flex items-center gap-2">
                <Share2 className="w-4 h-4 t-text-accent" />
                被多用户共享的文档（{summary?.shared_content_list?.length || 0}）
              </div>
              {(summary?.shared_content_list?.length || 0) === 0 ? (
                <div className="px-4 py-8 text-center t-text-faint text-sm">暂无共享文档（所有文档内容均独立）</div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs t-text-faint border-b t-border">
                      <th className="px-4 py-3">文件名</th>
                      <th className="px-4 py-3 text-right">引用用户数</th>
                      <th className="px-4 py-3 text-right">分块数</th>
                      <th className="px-4 py-3">内容哈希</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.shared_content_list.map((c) => (
                      <tr key={c.content_hash} className="border-b t-border t-hover-bg">
                        <td className="px-4 py-3 font-medium flex items-center gap-2">
                          <FileText className="w-3.5 h-3.5 t-text-2" />
                          {c.filename}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full t-badge-accent text-xs">
                            <Users className="w-3 h-3" />{c.ref_count}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-right t-text-2">{c.chunk_count}</td>
                        <td className="px-4 py-3 font-mono text-xs t-text-faint">{c.content_hash.slice(0, 16)}...</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  )
}

function UserRow({ u, expanded, onToggle }) {
  return (
    <>
      <tr className="border-b t-border t-hover-bg cursor-pointer" onClick={onToggle}>
        <td className="px-4 py-3 t-text-muted">
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </td>
        <td className="px-4 py-3 font-medium">
          <div className="flex flex-col">
            <span className="flex items-center gap-2">
              {u.display_name || u.username}
              {u.shared_docs > 0 && (
                <span className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full t-badge-accent">
                  <Share2 className="w-3 h-3" />{u.shared_docs} 共享
                </span>
              )}
            </span>
            {u.display_name && u.display_name !== u.username && (
              <span className="text-xs t-text-faint font-normal">@{u.username}</span>
            )}
          </div>
        </td>
        <td className="px-4 py-3 text-right">{u.documents}</td>
        <td className="px-4 py-3 text-right t-text-2">{u.total_chunks}</td>
        <td className="px-4 py-3 text-right">
          {u.shared_docs > 0 ? <span className="t-text-accent font-medium">{u.shared_docs}</span> : <span className="t-text-faint">0</span>}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b t-border">
          <td colSpan="5" className="px-4 py-3 t-bg-input/40">
            {u.docs.length === 0 ? (
              <div className="text-xs t-text-faint">无文档</div>
            ) : (
              <div className="space-y-1.5">
                {u.docs.map((d) => (
                  <div key={d.id} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileText className="w-3.5 h-3.5 t-text-2 shrink-0" />
                      <span className="truncate font-medium">{d.filename}</span>
                      <span className="t-text-faint shrink-0">{fmtBytes(d.file_size)}</span>
                      {d.shared && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full t-badge-accent shrink-0">
                          <Users className="w-3 h-3" />{d.shared_by} 人共享
                        </span>
                      )}
                    </div>
                    <span className="t-text-faint font-mono shrink-0">{d.chunk_count} 块 · {d.content_hash.slice(0, 12)}…</span>
                  </div>
                ))}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export default AdminKnowledge
