import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, RefreshCw, Zap, Gauge, Trophy } from 'lucide-react'
import { apiGet } from '../api/client'
import ThemeSwitcher from '../components/ThemeSwitcher'

function AdminModelSpeed() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [applying, setApplying] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const result = await apiGet('/admin/model-speed')
      setData(result.data || result)
    } catch (e) {
      setError(e.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleApply = async () => {
    setApplying(true)
    setError('')
    try {
      const result = await apiGet('/admin/model-speed?apply=1')
      setData(result.data || result)
    } catch (e) {
      setError(e.message || '切换失败')
    } finally {
      setApplying(false)
    }
  }

  const ranking = data?.ranking || []
  const currentDefault = data?.current_default

  return (
    <div className="min-h-screen t-bg-app t-text">
      <header className="flex items-center justify-between px-4 py-3 border-b t-border t-bg-panel">
        <div className="flex items-center gap-3">
          <Link to="/admin/users" className="p-2 rounded-lg t-hover-card" title="返回用户管理">
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-base font-semibold">模型速度排名</h1>
            <p className="text-[11px] t-text-faint">按首字输出耗时（TTFT）升序，自动选最快为默认模型</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeSwitcher />
          <button onClick={load} disabled={loading} className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card disabled:opacity-50">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
          <button onClick={handleApply} disabled={applying || ranking.length === 0}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg t-bg-accent text-white t-hover-accent disabled:opacity-50"
            title="立即将默认模型切换为当前最快">
            <Zap className="w-3.5 h-3.5" />
            {applying ? '切换中...' : '立即切换到最快'}
          </button>
        </div>
      </header>

      <div className="max-w-3xl mx-auto p-4">
        {error && <div className="mb-3 p-3 t-bg-danger-soft border t-border-danger rounded-lg t-text-danger text-sm">{error}</div>}

        {/* 当前默认模型 */}
        <div className="flex items-center gap-3 p-4 t-bg-panel border t-border rounded-xl mb-4">
          <div className="w-10 h-10 rounded-lg t-bg-accent text-white flex items-center justify-center">
            <Trophy className="w-5 h-5" />
          </div>
          <div>
            <div className="text-xs t-text-muted">当前默认模型</div>
            <div className="text-lg font-semibold">{currentDefault || '—'}</div>
          </div>
          <div className="ml-auto text-[11px] t-text-faint text-right leading-relaxed">
            后台每小时自动重算并切换<br />启动 5 分钟后首次执行
          </div>
        </div>

        {data?.switched_to && (
          <div className="mb-3 p-3 t-bg-accent-soft border t-border-accent rounded-lg text-sm flex items-center gap-2">
            <Zap className="w-4 h-4 t-text-accent" />
            已将默认模型切换为：<span className="font-semibold">{data.switched_to}</span>
          </div>
        )}

        {/* 排名表 */}
        {loading ? (
          <p className="text-sm t-text-faint text-center py-10">加载中...</p>
        ) : ranking.length === 0 ? (
          <div className="text-center t-text-fainter py-16">
            <Gauge className="w-10 h-10 mx-auto mb-3 opacity-40" />
            <p className="text-sm">暂无速度数据</p>
            <p className="text-xs mt-1">先用各模型发起一些对话，积累首字耗时（TTFT）数据后再查看</p>
          </div>
        ) : (
          <div className="t-bg-panel border t-border rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="t-bg-input text-xs t-text-muted">
                <tr>
                  <th className="text-left px-4 py-2.5 font-medium">排名</th>
                  <th className="text-left px-4 py-2.5 font-medium">模型</th>
                  <th className="text-right px-4 py-2.5 font-medium">平均首字耗时</th>
                  <th className="text-right px-4 py-2.5 font-medium">样本数</th>
                  <th className="text-right px-4 py-2.5 font-medium">最近一次</th>
                </tr>
              </thead>
              <tbody>
                {ranking.map((r, i) => (
                  <tr key={r.model_name} className={`border-t t-border ${r.model_name === currentDefault ? 't-bg-accent-soft' : ''}`}>
                    <td className="px-4 py-2.5">
                      {i === 0 ? <Trophy className="w-4 h-4 t-text-accent" /> : <span className="t-text-muted">{i + 1}</span>}
                    </td>
                    <td className="px-4 py-2.5 font-medium">
                      {r.model_name}
                      {r.model_name === currentDefault && <span className="ml-2 text-[10px] px-1.5 py-0.5 rounded t-bg-accent text-white">默认</span>}
                    </td>
                    <td className="px-4 py-2.5 text-right tabular-nums">{r.avg_ttft.toFixed(3)}s</td>
                    <td className="px-4 py-2.5 text-right tabular-nums t-text-muted">{r.sample_count}</td>
                    <td className="px-4 py-2.5 text-right tabular-nums t-text-muted">{r.last_ttft.toFixed(3)}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

export default AdminModelSpeed
