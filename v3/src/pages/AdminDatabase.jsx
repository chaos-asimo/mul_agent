import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft, Database, Play, RefreshCw, Table2, ChevronDown, ChevronRight, ShieldAlert, Download,
} from 'lucide-react'
import { apiGet, apiPost } from '../api/client'
import ThemeSwitcher from '../components/ThemeSwitcher'

const inputCls = 'px-3 py-1.5 text-xs rounded-lg border t-border t-bg-panel t-text focus:outline-none focus:border-accent'
const READONLY_RE = /^\s*(?:(?:--[^\n]*\n)|(?:\/\*[\s\S]*?\*\/\s*))*(select|with|pragma|explain)\b/i

function fmtSize(n) {
  if (n == null) return '-'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function Cell({ value }) {
  if (value === null || value === undefined) return <span className="t-text-fainter italic">NULL</span>
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
  const cut = text.length > 160
  return (
    <span title={cut ? text : undefined} className="whitespace-pre-wrap break-all">
      {cut ? text.slice(0, 160) + '…' : text}
    </span>
  )
}

function AdminDatabase() {
  const [dbs, setDbs] = useState([])
  const [activeDb, setActiveDb] = useState('')
  const [tables, setTables] = useState([])
  const [expanded, setExpanded] = useState({})
  const [sql, setSql] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loadingDbs, setLoadingDbs] = useState(true)
  const [loadingSchema, setLoadingSchema] = useState(false)
  const [executing, setExecuting] = useState(false)
  const [maxRows, setMaxRows] = useState(200)
  const [allowWrite, setAllowWrite] = useState(false)

  const loadDbs = useCallback(async () => {
    setLoadingDbs(true)
    setError('')
    try {
      const res = await apiGet('/admin/db/list')
      if (res.success === false) {
        setError(res.error || '加载数据库列表失败')
        return
      }
      const list = res.dbs || []
      setDbs(list)
      setActiveDb((prev) => prev || (list[0] && list[0].id) || '')
    } catch (e) {
      setError(e.message || '加载数据库列表失败')
    } finally {
      setLoadingDbs(false)
    }
  }, [])

  useEffect(() => { loadDbs() }, [loadDbs])

  const loadSchema = useCallback(async (dbId) => {
    if (!dbId) return
    setLoadingSchema(true)
    try {
      const res = await apiGet(`/admin/db/schema?db=${encodeURIComponent(dbId)}`)
      if (res.success === false) {
        setError(res.error || '读取表结构失败')
        setTables([])
      } else {
        setTables(res.tables || [])
      }
    } catch (e) {
      setError(e.message || '读取表结构失败')
    } finally {
      setLoadingSchema(false)
    }
  }, [])

  useEffect(() => {
    setTables([])
    setExpanded({})
    setResult(null)
    loadSchema(activeDb)
  }, [activeDb, loadSchema])

  const execute = useCallback(async (statement) => {
    const sqlText = (statement !== undefined ? statement : sql).trim()
    if (!sqlText || !activeDb) return
    const readonly = READONLY_RE.test(sqlText)
    if (!readonly && !allowWrite) {
      setError('该语句属于写操作，请先勾选「允许写操作」')
      return
    }
    if (!readonly && !window.confirm('即将对数据库执行写操作，可能影响线上数据。确认继续？')) return
    setExecuting(true)
    setError('')
    try {
      const res = await apiPost('/admin/db/query', {
        db: activeDb, sql: sqlText, max_rows: maxRows, allow_write: allowWrite,
      })
      if (res.success === false) {
        setError(res.error || '执行失败')
        setResult(null)
      } else {
        setResult(res)
        if (!res.readonly) loadSchema(activeDb) // 写操作后刷新结构与行数
      }
    } catch (e) {
      setError(e.message || '执行失败')
      setResult(null)
    } finally {
      setExecuting(false)
    }
  }, [sql, activeDb, maxRows, allowWrite, loadSchema])

  const previewTable = (name) => {
    const statement = `SELECT * FROM "${name.replace(/"/g, '""')}" LIMIT ${maxRows};`
    setSql(statement)
    execute(statement)
  }

  // 把当前结果集导出为 CSV 文件（UTF-8 BOM，Excel 可直接打开中文）
  const exportCsv = () => {
    if (!result || !result.columns || result.columns.length === 0) return
    const esc = (v) => {
      if (v === null || v === undefined) return ''
      const s = typeof v === 'object' ? JSON.stringify(v) : String(v)
      return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s
    }
    const lines = [result.columns.map(esc).join(',')]
    result.rows.forEach((row) => lines.push(row.map(esc).join(',')))
    const csv = '\ufeff' + lines.join('\r\n')
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const dbName = (activeDb.split('/').pop() || 'query').replace(/\.(db|sqlite3?)$/i, '')
    const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '')
    const a = document.createElement('a')
    a.href = url
    a.download = `${dbName}_${stamp}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    if (result.truncated) {
      setError(`注意：导出的是当前返回的 ${result.row_count} 行（结果已截断），如需更多请调大「最多 N 行」或分页查询`)
    }
  }

  return (
    <div className="min-h-screen t-bg-app t-text">
      <header className="flex items-center justify-between px-4 py-3 border-b t-border t-bg-panel">
        <div className="flex items-center gap-3">
          <Link to="/admin/users" className="p-2 rounded-lg t-hover-card" title="返回用户管理">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-base font-semibold inline-flex items-center gap-2">
              <Database className="w-4 h-4" /> SQLite 数据库查看器
            </h1>
            <p className="text-[11px] t-text-faint">
              浏览项目内全部 SQLite 数据库，支持自定义 SQL；默认只读，写操作需显式开启。仅管理员可见
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeSwitcher />
          <button
            onClick={() => { loadDbs(); loadSchema(activeDb) }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingDbs ? 'animate-spin' : ''}`} /> 刷新
          </button>
        </div>
      </header>

      <div className="p-4 grid gap-4 lg:grid-cols-[280px_1fr]">
        {/* 左：数据库与表 */}
        <div className="space-y-3">
          <div className="t-bg-panel border t-border rounded-lg overflow-hidden">
            <div className="px-3 py-2 border-b t-border text-xs font-medium t-text-2">数据库（{dbs.length}）</div>
            <div className="max-h-56 overflow-auto">
              {dbs.map((d) => (
                <button
                  key={d.id}
                  onClick={() => setActiveDb(d.id)}
                  className={`w-full text-left px-3 py-2 border-b t-border last:border-b-0 t-hover-card ${activeDb === d.id ? 't-bg-accent-soft' : ''}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-medium truncate">{d.name}</span>
                    {d.is_main && <span className="text-[10px] px-1 rounded t-bg-accent text-white shrink-0">主库</span>}
                  </div>
                  <div className="text-[10px] t-text-faint truncate">{d.path}</div>
                  <div className="text-[10px] t-text-faint">{fmtSize(d.size)} · {d.table_count ?? '-'} 张表</div>
                </button>
              ))}
              {!loadingDbs && dbs.length === 0 && <p className="p-3 text-xs t-text-faint">未发现数据库文件</p>}
            </div>
          </div>

          <div className="t-bg-panel border t-border rounded-lg overflow-hidden">
            <div className="px-3 py-2 border-b t-border text-xs font-medium t-text-2 inline-flex items-center gap-1.5">
              <Table2 className="w-3.5 h-3.5" /> 表 / 视图（{tables.length}）
            </div>
            <div className="max-h-[420px] overflow-auto">
              {loadingSchema && <p className="p-3 text-xs t-text-faint">读取中...</p>}
              {tables.map((t) => (
                <div key={t.name} className="border-b t-border last:border-b-0">
                  <div className="flex items-center">
                    <button
                      onClick={() => setExpanded((p) => ({ ...p, [t.name]: !p[t.name] }))}
                      className="p-2 t-text-fainter t-hover-text"
                      title="展开列定义"
                    >
                      {expanded[t.name] ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                    </button>
                    <button onClick={() => previewTable(t.name)} className="flex-1 text-left py-1.5 pr-2 t-hover-text" title="查询该表前 N 行">
                      <div className="text-xs truncate">{t.name}</div>
                      <div className="text-[10px] t-text-faint">{t.type === 'view' ? '视图' : '表'} · {t.row_count ?? '-'} 行</div>
                    </button>
                  </div>
                  {expanded[t.name] && (
                    <div className="px-3 pb-2 pl-8 space-y-0.5">
                      {t.columns.map((c) => (
                        <div key={c.name} className="text-[10px] font-mono t-text-muted">
                          {c.name} <span className="t-text-faint">{c.type}</span>
                          {c.pk ? <span className="t-text-accent"> PK</span> : null}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 右：SQL 与结果 */}
        <div className="space-y-3 min-w-0">
          <div className="t-bg-panel border t-border rounded-lg p-3 space-y-2">
            <textarea
              value={sql}
              onChange={(e) => setSql(e.target.value)}
              onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); execute() } }}
              placeholder={'输入单条 SQL，Ctrl+Enter 执行\n例如：SELECT id, username, role FROM users LIMIT 20;'}
              spellCheck={false}
              className="w-full min-h-[120px] px-3 py-2 text-xs font-mono rounded-lg border t-border t-bg-app t-text focus:outline-none focus:border-accent"
            />
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => execute()}
                disabled={executing || !activeDb || !sql.trim()}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50"
              >
                <Play className="w-3.5 h-3.5" /> {executing ? '执行中...' : '执行 (Ctrl+Enter)'}
              </button>
              <select value={maxRows} onChange={(e) => setMaxRows(Number(e.target.value))} className={inputCls} title="最大返回行数">
                {[50, 200, 500, 1000].map((n) => <option key={n} value={n}>最多 {n} 行</option>)}
              </select>
              <label className="inline-flex items-center gap-1.5 text-xs t-text-muted cursor-pointer" title="开启后允许 INSERT/UPDATE/DELETE/DDL">
                <input type="checkbox" checked={allowWrite} onChange={(e) => setAllowWrite(e.target.checked)} />
                允许写操作
              </label>
              <span className="inline-flex items-center gap-1 text-[10px] t-text-faint">
                <ShieldAlert className="w-3 h-3" /> 禁止 ATTACH，单语句，15s 超时
              </span>
            </div>
          </div>

          {error && (
            <div className="p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-xs whitespace-pre-wrap">{error}</div>
          )}

          {result && (
            <div className="t-bg-panel border t-border rounded-lg overflow-hidden">
              <div className="px-3 py-2 border-b t-border text-[11px] t-text-faint flex flex-wrap items-center gap-x-4 gap-y-1">
                <span>{result.readonly ? '只读查询' : '写操作已提交'}</span>
                <span>耗时 {result.elapsed_ms} ms</span>
                {result.affected !== null && result.affected !== undefined && <span>影响行数 {result.affected}</span>}
                {result.columns.length > 0 && <span>返回 {result.row_count} 行{result.truncated ? `（已截断至 ${maxRows} 行）` : ''}</span>}
                {result.columns.length > 0 && (
                  <button
                    onClick={exportCsv}
                    className="ml-auto inline-flex items-center gap-1 px-2 py-1 rounded border t-border-strong t-text-2 t-hover-card"
                    title={result.truncated ? `导出当前 ${result.row_count} 行（结果已截断）` : '导出全部结果为 CSV'}
                  >
                    <Download className="w-3 h-3" /> 导出 CSV
                  </button>
                )}
              </div>
              {result.columns.length > 0 ? (
                <div className="overflow-auto max-h-[520px]">
                  <table className="w-full text-[11px] font-mono">
                    <thead className="sticky top-0 t-bg-app">
                      <tr>
                        <th className="px-2 py-1.5 text-left t-text-faint font-normal border-b t-border">#</th>
                        {result.columns.map((c, i) => (
                          <th key={i} className="px-2 py-1.5 text-left font-medium border-b t-border whitespace-nowrap">{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, ri) => (
                        <tr key={ri} className="t-hover-card align-top">
                          <td className="px-2 py-1 t-text-fainter border-b t-border">{ri + 1}</td>
                          {row.map((v, ci) => (
                            <td key={ci} className="px-2 py-1 border-b t-border max-w-[280px]"><Cell value={v} /></td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="p-3 text-xs t-text-faint">语句已执行，无结果集。</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default AdminDatabase
