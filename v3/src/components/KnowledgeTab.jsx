import { useState, useEffect, useCallback } from 'react'
import { UploadCloud, Trash2, Search, RefreshCw, BookOpen, ArrowLeft, Database } from 'lucide-react'
import { apiGet, apiPost, apiDelete, apiUpload, formatSize } from '../api/client'

function KnowledgeTab() {
  const [docs, setDocs] = useState([])
  const [stats, setStats] = useState({ documents: 0, chunks: 0 })
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState('')
  const [searchMode, setSearchMode] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [searching, setSearching] = useState(false)

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [listRes, statsRes] = await Promise.all([apiGet('/knowledge/list'), apiGet('/knowledge/stats')])
      if (listRes.success) setDocs(listRes.data || [])
      if (statsRes.success) setStats(statsRes.data || { documents: 0, chunks: 0 })
    } catch (e) {
      console.error('加载知识库失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!searchMode) loadData()
  }, [loadData, searchMode])

  const handleUpload = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    setUploading(true)
    setUploadMsg('')
    try {
      const formData = new FormData()
      for (const file of files) formData.append('files', file)
      const result = await apiUpload('/knowledge/upload', formData)
      const ok = (result.results || []).filter((r) => r.success)
      const fail = (result.results || []).filter((r) => !r.success)
      setUploadMsg(
        `成功入库 ${ok.length} 个文档${ok.length ? '（共 ' + ok.reduce((s, r) => s + (r.chunk_count || 0), 0) + ' 个分块）' : ''}` +
          (fail.length ? `，失败 ${fail.length} 个：${fail.map((f) => `${f.filename}(${f.error || '未知错误'})`).join('、')}` : ''),
      )
      loadData()
    } catch (e2) {
      setUploadMsg(`上传失败: ${e2.message}`)
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handleDelete = async (docId) => {
    if (!window.confirm('确定删除该文档及其全部分块吗？')) return
    try {
      const result = await apiDelete(`/knowledge/${docId}`)
      if (result.success) {
        setDocs((prev) => prev.filter((d) => d.id !== docId))
        loadData()
      } else {
        alert(result.error || '删除失败')
      }
    } catch (e) {
      alert(e.message)
    }
  }

  const handleSearch = async (e) => {
    e.preventDefault()
    const q = query.trim()
    if (!q) return
    setSearching(true)
    setSearchMode(true)
    try {
      const result = await apiPost('/knowledge/search', { query: q, top_k: 8 })
      if (result.success) {
        setResults(result.data || [])
      } else {
        setResults([])
        setUploadMsg(result.error || '检索失败')
      }
    } catch (e2) {
      setUploadMsg(e2.message)
    } finally {
      setSearching(false)
    }
  }

  const inputCls =
    'w-full px-3 py-2 t-bg-input border t-border-strong rounded-lg text-xs t-text t-placeholder t-focus'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold t-text-2 flex items-center gap-1.5">
          <BookOpen className="w-4 h-4 t-text-accent" />
          知识库 RAG
        </h3>
        <span className="text-xs t-text-faint flex items-center gap-1">
          <Database className="w-3 h-3" />
          文档 {stats.documents} · 分块 {stats.chunks}
        </span>
      </div>

      {/* 上传 */}
      <label className="flex flex-col items-center justify-center gap-1.5 py-5 border-2 border-dashed t-border-strong rounded-xl cursor-pointer t-hover-border-accent t-hover-bg transition-colors t-text-faint t-hover-text-accent">
        <UploadCloud className={`w-7 h-7 ${uploading ? 'animate-bounce' : ''}`} />
        <span className="text-xs">{uploading ? '上传解析中...' : '上传文档到知识库'}</span>
        <input type="file" multiple className="hidden" onChange={handleUpload} disabled={uploading} />
      </label>
      {uploadMsg && <p className="text-xs t-text-info break-all">{uploadMsg}</p>}

      {/* 搜索 */}
      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          className={inputCls}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="语义检索知识库..."
        />
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="px-3 rounded-lg t-bg-card border t-border-strong t-text-2 t-hover-card disabled:opacity-50"
          title="检索"
        >
          <Search className={`w-3.5 h-3.5 ${searching ? 'animate-pulse' : ''}`} />
        </button>
        <button
          type="button"
          onClick={loadData}
          className="px-3 rounded-lg border t-border-strong t-text-muted t-hover-card"
          title="刷新列表"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </form>
      {searchMode && (
        <button
          onClick={() => {
            setSearchMode(false)
            setQuery('')
            setResults([])
          }}
          className="text-xs t-text-accent hover:underline inline-flex items-center gap-1"
        >
          <ArrowLeft className="w-3 h-3" />
          返回文档列表
        </button>
      )}

      {searching && (
        <p className="text-xs t-text-accent animate-pulse">
          正在检索…（本地 embedding 模型首次加载需数分钟，请耐心等待）
        </p>
      )}
      {searchMode ? (
        <div className="space-y-2">
          <p className="text-xs t-text-faint">检索结果（{results.length}）</p>
          {results.length === 0 && !searching ? (
            <p className="text-xs t-text-fainter text-center py-6">没有匹配内容（可能未配置 embedding 模型）</p>
          ) : (
            results.map((r, i) => (
              <div key={i} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg">
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-xs t-text-accent truncate" title={r.filename}>
                    {r.filename}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full t-badge-ok shrink-0">
                    相似度 {typeof r.score === 'number' ? (r.score * 100).toFixed(1) + '%' : r.score}
                  </span>
                </div>
                <p className="text-xs t-text-2 break-words line-clamp-4">{r.content}</p>
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-xs t-text-faint">文档列表（{docs.length}）</p>
          {docs.length === 0 && !loading ? (
            <p className="text-xs t-text-fainter text-center py-6">暂无文档，上传后自动切块入库</p>
          ) : (
            docs.map((d) => (
              <div key={d.id} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg group">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs t-text-2 truncate flex-1" title={d.filename}>
                    {d.filename}
                  </p>
                  <button
                    onClick={() => handleDelete(d.id)}
                    className="t-text-fainter t-hover-text-danger opacity-0 group-hover:opacity-100 transition-all shrink-0"
                    title="删除"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
                <p className="text-[10px] t-text-faint mt-1">
                  {d.chunk_count} 个分块 · {formatSize(d.file_size)} · {d.created_at}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

export default KnowledgeTab
