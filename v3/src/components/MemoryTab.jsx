import { useState, useEffect, useCallback } from 'react'
import { Plus, Trash2, Search, RefreshCw, BrainCircuit, ArrowLeft } from 'lucide-react'
import { apiGet, apiPost, apiDelete } from '../api/client'

const TYPE_LABELS = {
  short_term: '短期',
  long_term: '长期',
}

function MemoryTab() {
  const [typeFilter, setTypeFilter] = useState('')
  const [memories, setMemories] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchMode, setSearchMode] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [addType, setAddType] = useState('short_term')
  const [addContent, setAddContent] = useState('')
  const [message, setMessage] = useState('')

  const loadMemories = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '100' })
      if (typeFilter) params.set('type', typeFilter)
      const result = await apiGet(`/memory/list?${params.toString()}`)
      setMemories(result.memories || [])
    } catch (e) {
      console.error('加载记忆失败:', e)
    } finally {
      setLoading(false)
    }
  }, [typeFilter])

  useEffect(() => {
    if (!searchMode) loadMemories()
  }, [loadMemories, searchMode])

  const handleAdd = async (e) => {
    e.preventDefault()
    const content = addContent.trim()
    if (!content) return
    setMessage('')
    try {
      const result = await apiPost('/memory/add', { type: addType, content })
      if (result.success) {
        setAddContent('')
        loadMemories()
      } else {
        setMessage(result.error || '添加失败')
      }
    } catch (e2) {
      setMessage(e2.message)
    }
  }

  const handleSearch = async (e) => {
    e.preventDefault()
    const q = query.trim()
    if (!q) return
    setSearchMode(true)
    setLoading(true)
    try {
      const body = { query: q }
      if (typeFilter) body.type = typeFilter
      const result = await apiPost('/memory/search', body)
      setResults(result.results || [])
    } catch (e2) {
      console.error('搜索失败:', e2)
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (id) => {
    try {
      await apiDelete(`/memory/${id}`)
      setMemories((prev) => prev.filter((m) => m.id !== id))
      setResults((prev) => prev.filter((m) => m.id !== id))
    } catch (e) {
      console.error('删除失败:', e)
    }
  }

  const handleClear = async () => {
    const scope = typeFilter ? `所有「${TYPE_LABELS[typeFilter]}」记忆` : '所有记忆'
    if (!window.confirm(`确定清空${scope}吗？该操作不可恢复。`)) return
    try {
      const result = await apiDelete(`/memory/clear${typeFilter ? `?type=${typeFilter}` : ''}`)
      setMessage(`已清空 ${result.deleted || 0} 条记忆`)
      loadMemories()
    } catch (e) {
      console.error('清空失败:', e)
    }
  }

  const list = searchMode ? results : memories
  const inputCls =
    'w-full px-3 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text t-placeholder t-focus'
  const btnGhost =
    'p-1.5 rounded-lg border t-border-strong t-text-muted t-hover-card transition-colors'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold t-text-2 flex items-center gap-1.5">
          <BrainCircuit className="w-4 h-4 t-text-accent" />
          记忆管理
        </h3>
        <div className="flex items-center gap-1.5">
          <select
            value={typeFilter}
            onChange={(e) => {
              setTypeFilter(e.target.value)
              setSearchMode(false)
            }}
            className="px-2 py-1.5 t-bg-input border t-border-strong rounded-lg text-xs t-text-2 outline-none"
          >
            <option value="">全部类型</option>
            <option value="short_term">短期记忆</option>
            <option value="long_term">长期记忆</option>
          </select>
          <button onClick={loadMemories} className={btnGhost} title="刷新">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {message && <p className="text-xs t-text-accent">{message}</p>}

      {/* 搜索 */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          className={inputCls}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索记忆内容/关键词..."
        />
        <button
          type="submit"
          className="px-3 rounded-lg t-bg-card border t-border-strong t-text-2 t-hover-bg"
          title="搜索"
        >
          <Search className="w-3.5 h-3.5" />
        </button>
      </form>
      {searchMode && (
        <button
          onClick={() => {
            setSearchMode(false)
            setQuery('')
          }}
          className="text-xs t-text-accent hover:underline inline-flex items-center gap-1"
        >
          <ArrowLeft className="w-3 h-3" />
          返回全部列表
        </button>
      )}

      {/* 添加 */}
      <form onSubmit={handleAdd} className="p-3 t-bg-panel border t-border rounded-xl space-y-2">
        <div className="flex items-center gap-2">
          <select
            value={addType}
            onChange={(e) => setAddType(e.target.value)}
            className="px-2 py-1.5 t-bg-input border t-border-strong rounded-lg text-xs t-text-2 outline-none"
          >
            <option value="short_term">短期记忆</option>
            <option value="long_term">长期记忆</option>
          </select>
          <span className="text-xs t-text-fainter">手动添加记忆</span>
        </div>
        <textarea
          className={inputCls + ' resize-none h-16'}
          value={addContent}
          onChange={(e) => setAddContent(e.target.value)}
          placeholder="输入要记住的内容..."
        />
        <button
          type="submit"
          disabled={!addContent.trim()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg t-bg-accent t-hover-accent text-white disabled:opacity-50"
        >
          <Plus className="w-3.5 h-3.5" />
          添加
        </button>
      </form>

      {/* 列表 */}
      <div className="flex items-center justify-between">
        <p className="text-xs t-text-faint">
          {searchMode ? `搜索结果（${list.length}）` : `共 ${list.length} 条`}
        </p>
        <button
          onClick={handleClear}
          className="text-xs t-text-danger opacity-80 t-hover-text-danger inline-flex items-center gap-1"
        >
          <Trash2 className="w-3 h-3" />
          清空{typeFilter ? '当前类型' : '全部'}
        </button>
      </div>

      {list.length === 0 && !loading ? (
        <p className="text-xs t-text-fainter text-center py-6">
          {searchMode ? '没有匹配的记忆' : '暂无记忆'}
        </p>
      ) : (
        <div className="space-y-2">
          {list.map((m) => (
            <div key={m.id} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg group">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span
                    className={`text-[10px] px-1.5 py-0.5 rounded-full border ${
                      m.type === 'long_term' ? 't-badge-accent' : 't-badge-info'
                    }`}
                  >
                    {TYPE_LABELS[m.type] || m.type}
                  </span>
                  {searchMode && typeof m.score === 'number' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full border t-badge-ok">
                      相关度 {m.score}
                    </span>
                  )}
                  <span className="text-[10px] t-text-fainter">权重 {m.weight ?? 1}</span>
                </div>
                <button
                  onClick={() => handleDelete(m.id)}
                  className="t-text-fainter t-hover-text-danger opacity-0 group-hover:opacity-100 transition-all shrink-0"
                  title="删除"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <p className="text-xs t-text-2 mt-1.5 break-words">{m.content}</p>
              <p className="text-[10px] t-text-fainter mt-1">{m.timestamp}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default MemoryTab
