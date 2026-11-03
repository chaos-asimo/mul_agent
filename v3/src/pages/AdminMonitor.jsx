import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowLeft, Pause, Play, RefreshCw, Cpu, MemoryStick, HardDrive,
  Users, MessageSquare, Zap, Activity, Database, Server, Clock,
  TrendingUp, Timer, Bot, ArrowUpRight, ArrowDownRight,
  Radio, ShieldCheck, Braces, Gauge as GaugeIcon,
} from 'lucide-react'
import { apiGet } from '../api/client'
import ThemeSwitcher from '../components/ThemeSwitcher'

const TONE = {
  accent: 'var(--accent-text)',
  info: 'var(--info)',
  ok: 'var(--ok)',
  warn: 'var(--warn)',
  danger: 'var(--danger)',
}

function usageTone(pct) {
  const value = Number(pct) || 0
  if (value >= 80) return 'danger'
  if (value >= 50) return 'warn'
  return 'ok'
}

function fmtInt(value) {
  return value == null ? '—' : Number(value).toLocaleString('zh-CN')
}

function fmtTokens(value) {
  if (value == null) return '—'
  const number = Number(value)
  if (number >= 1e8) return `${(number / 1e8).toFixed(2)} 亿`
  if (number >= 1e4) return `${(number / 1e4).toFixed(1)} 万`
  return fmtInt(number)
}

function fmtTime(date) {
  return date ? date.toLocaleTimeString('zh-CN', { hour12: false }) : '—'
}

function usePolling(fn, ms, enabled) {
  useEffect(() => {
    if (!enabled) return
    let alive = true
    const tick = () => { if (alive) fn() }
    tick()
    const id = setInterval(tick, ms)
    return () => { alive = false; clearInterval(id) }
  }, [fn, ms, enabled])
}

function StatTile({ label, value, sub, icon: Icon, tone = 'accent' }) {
  return (
    <div className={`monitor-stat monitor-stat-${tone}`}>
      <div className="monitor-stat-icon"><Icon size={17} strokeWidth={1.7} /></div>
      <div className="min-w-0">
        <div className="text-[11px] tracking-[0.12em] t-text-faint uppercase">{label}</div>
        <div className="flex items-baseline gap-2 min-w-0">
          <span className="monitor-stat-value num-mono">{value}</span>
          <span className="text-[11px] t-text-faint truncate">{sub}</span>
        </div>
      </div>
    </div>
  )
}

function Panel({ title, eyebrow, icon: Icon, action, children, className = '' }) {
  return (
    <section className={`monitor-panel ${className}`}>
      <div className="monitor-panel-head">
        <div className="flex items-center gap-2 min-w-0">
          <span className="monitor-panel-icon"><Icon size={14} strokeWidth={1.8} /></span>
          <div className="min-w-0">
            {eyebrow && <div className="monitor-eyebrow">{eyebrow}</div>}
            <h2 className="text-[12px] font-semibold t-text tracking-wide truncate">{title}</h2>
          </div>
        </div>
        {action}
      </div>
      <div className="monitor-panel-body">{children}</div>
    </section>
  )
}

function ResourceGauge({ value, label, detail, icon: Icon }) {
  const number = Math.max(0, Math.min(100, Number(value) || 0))
  const color = TONE[usageTone(number)]
  return (
    <div className="monitor-resource">
      <div className="monitor-ring" style={{ '--gauge-value': `${number * 3.6}deg`, '--gauge-color': color }}>
        <div className="monitor-ring-inner">
          <Icon size={13} style={{ color }} />
          <span className="num-mono text-[18px] font-semibold leading-none" style={{ color }}>{number.toFixed(0)}<small className="text-[9px]">%</small></span>
        </div>
      </div>
      <div className="w-full min-w-0 px-0.5">
        <div className="text-[11px] font-medium t-text-2">{label}</div>
        <div className="text-[9px] t-text-faint mt-1 whitespace-nowrap overflow-hidden text-ellipsis" title={detail}>{detail}</div>
      </div>
    </div>
  )
}

function ServiceRow({ name, ok, detail }) {
  return (
    <div className="monitor-service-row">
      <span className="pulse-dot shrink-0" style={{ background: ok ? TONE.ok : TONE.danger, animationPlayState: ok ? 'running' : 'paused' }} />
      <span className="text-[10px] t-text-2 shrink-0">{name}</span>
      <span className={`text-[9px] num-mono truncate text-right ${ok ? 't-text-faint' : 't-text-danger'}`}>{detail}</span>
    </div>
  )
}

function TrendChart({ data }) {
  const points = Array.from({ length: 7 }, (_, index) => data[index] || { date: '', calls: 0, tokens: 0 })
  const max = Math.max(1, ...points.map((item) => item.calls || 0))
  return (
    <div className="monitor-chart">
      <div className="monitor-chart-grid"><i /><i /><i /><i /></div>
      <div className="monitor-bars">
        {points.map((item, index) => (
          <div className="monitor-bar-column" key={item.date || index}>
            <span className="monitor-bar-value num-mono">{item.calls ? fmtInt(item.calls) : ''}</span>
            <div className="monitor-bar-track">
              <div className="monitor-bar" style={{ height: `${Math.max(item.calls ? 7 : 1, ((item.calls || 0) / max) * 100)}%` }}>
                <span />
              </div>
            </div>
            <span className="monitor-bar-label num-mono">{item.date ? item.date.slice(5).replace('-', '/') : '—'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function RankList({ items, unit = '', limit = 4, tone = 'accent' }) {
  const rows = items.slice(0, limit)
  if (!rows.length) return <div className="monitor-empty">暂无数据</div>
  const max = Math.max(1, ...rows.map((item) => item.value || 0))
  return (
    <div className="monitor-rank-list">
      {rows.map((item, index) => (
        <div className="monitor-rank" key={`${item.name}-${index}`}>
          <span className={`monitor-rank-index ${index === 0 ? 'is-first' : ''}`}>{String(index + 1).padStart(2, '0')}</span>
          <div className="min-w-0 flex-1">
            <div className="flex justify-between items-center gap-2 mb-1">
              <span className="text-[10px] t-text-2 truncate" title={item.name}>{item.name}</span>
              <span className="text-[10px] num-mono t-text-muted shrink-0">{item.display ?? fmtInt(item.value)}{unit}</span>
            </div>
            <div className="monitor-rank-track">
              <div className={`monitor-rank-fill is-${tone}`} style={{ width: `${Math.max(2, ((item.value || 0) / max) * 100)}%` }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function statusClass(code) {
  const value = Number(code) || 0
  if (value >= 500) return 't-text-danger'
  if (value >= 400) return 't-text-warn'
  return 't-text-ok'
}

function RequestLog({ rows }) {
  if (!rows?.length) return <div className="monitor-empty">暂无请求记录</div>
  return (
    <div className="monitor-request-list">
      {rows.slice(0, 7).map((row, index) => (
        <div className="monitor-request" key={`${row.time}-${index}`}>
          <span className="t-text-fainter w-[43px] shrink-0">{row.time}</span>
          <span className={`w-[24px] shrink-0 ${statusClass(row.status)}`}>{row.status}</span>
          <span className="flex-1 truncate t-text-muted" title={row.path}>{row.path}</span>
          <span className="t-text-faint w-[38px] text-right shrink-0">{row.ms}ms</span>
        </div>
      ))}
    </div>
  )
}

function AdminMonitor() {
  const [monitor, setMonitor] = useState(null)
  const [ranking, setRanking] = useState([])
  const [speed, setSpeed] = useState(null)
  const [error, setError] = useState('')
  const [paused, setPaused] = useState(false)
  const [pageVisible, setPageVisible] = useState(() => typeof document === 'undefined' || !document.hidden)
  const [updatedAt, setUpdatedAt] = useState(null)

  useEffect(() => {
    const onVisibility = () => setPageVisible(!document.hidden)
    document.addEventListener('visibilitychange', onVisibility)
    return () => document.removeEventListener('visibilitychange', onVisibility)
  }, [])

  const loadMonitor = useCallback(async () => {
    try {
      const response = await apiGet('/admin/monitor')
      setMonitor(response.data || null)
      setUpdatedAt(new Date())
      setError('')
    } catch (e) {
      setError(e.message || '监控数据加载失败')
    }
  }, [])

  const loadRanking = useCallback(async () => {
    try {
      const response = await apiGet('/admin/usage-ranking')
      setRanking(response.ranking || [])
    } catch (e) { /* 保留上一轮数据，下个周期自动重试 */ }
  }, [])

  const loadSpeed = useCallback(async () => {
    try {
      const response = await apiGet('/admin/model-speed')
      setSpeed(response.data || response)
    } catch (e) { /* 保留上一轮数据，下个周期自动重试 */ }
  }, [])

  const refresh = useCallback(() => {
    loadMonitor()
    loadRanking()
    loadSpeed()
  }, [loadMonitor, loadRanking, loadSpeed])

  const enabled = pageVisible && !paused
  usePolling(loadMonitor, 2000, enabled)
  usePolling(loadRanking, 30000, enabled)
  usePolling(loadSpeed, 60000, enabled)

  const hw = monitor?.hardware || {}
  const svc = monitor?.services || {}
  const loop = monitor?.loop || {}
  const counts = monitor?.counts || {}
  const db = monitor?.db || {}
  const traffic = monitor?.traffic || {}
  const models = monitor?.models || {}
  const daily = models.daily_stats || []
  const today = daily.at(-1) || { calls: 0, tokens: 0 }
  const crons = traffic.cron_24h || {}
  const errorRate = traffic.api_today_total ? (traffic.api_today_errors / traffic.api_today_total) * 100 : 0
  const healthy = [svc.database?.ok, svc.vector_index?.ok, svc.cron?.ok, svc.knowledge?.ok].every(Boolean) && !loop.blocked
  const speedMap = new Map((speed?.ranking || []).map((item) => [item.model_name, item.avg_ttft]))
  const modelRanking = (models.top_models || []).map((item) => ({
    name: item.model,
    value: item.calls,
    display: speedMap.has(item.model) ? `${fmtInt(item.calls)} 次 · ${speedMap.get(item.model).toFixed(2)}s` : `${fmtInt(item.calls)} 次`,
  }))
  const tokenRanking = (ranking || []).map((item) => ({
    name: item.display_name || item.username || `#${item.user_id}`,
    value: item.total_tokens || 0,
    display: fmtTokens(item.total_tokens || 0),
  }))

  return (
    <div className="monitor-page t-bg-app t-text">
      <header className="monitor-header">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/admin/users" className="monitor-icon-button" title="返回用户管理"><ArrowLeft size={17} /></Link>
          <div className="monitor-brand-mark"><Activity size={19} /></div>
          <div className="min-w-0">
            <div className="flex items-center gap-2.5">
              <h1 className="text-[15px] font-semibold tracking-[0.14em]">运行监控</h1>
              <span className="monitor-version">LIVE OPS</span>
            </div>
            <p className="text-[9px] t-text-faint tracking-[0.1em] mt-0.5 truncate">LOBSTERCLAW · SYSTEM OBSERVABILITY</p>
          </div>
        </div>
        <div className="monitor-header-center">
          <span className="pulse-dot" style={{ background: paused || !pageVisible ? 'var(--text-faint)' : healthy ? TONE.ok : TONE.warn }} />
          <span className="text-[10px] t-text-muted">{paused ? '监控已暂停' : healthy ? '全部系统运行正常' : '部分服务需要关注'}</span>
          <span className="w-px h-3 t-bg-card" />
          <span className="text-[9px] num-mono t-text-faint">{fmtTime(updatedAt)}</span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <ThemeSwitcher />
          <button onClick={() => setPaused((value) => !value)} className="monitor-control" title={paused ? '恢复实时刷新' : '暂停实时刷新'}>
            {paused ? <Play size={13} /> : <Pause size={13} />}<span>{paused ? '恢复' : '暂停'}</span>
          </button>
          <button onClick={refresh} className="monitor-control is-primary" title="立即刷新全部数据"><RefreshCw size={13} /><span>刷新</span></button>
        </div>
      </header>

      <main className="monitor-grid-bg monitor-main">
        <div className="monitor-orb monitor-orb-one" /><div className="monitor-orb monitor-orb-two" />
        {error && <div className="monitor-error">{error}</div>}
        {!monitor ? (
          <div className="monitor-loading"><Radio size={25} /><span>正在建立实时监控链路</span><i /></div>
        ) : (
          <div className="monitor-dashboard">
            <div className="monitor-stats">
              <StatTile label="今日模型调用" value={fmtInt(today.calls)} sub={`7 日 ${fmtInt(models.total_calls)} 次`} icon={Zap} tone="accent" />
              <StatTile label="今日 Token 消耗" value={fmtTokens(today.tokens)} sub={`7 日 ${fmtTokens(models.total_tokens)}`} icon={Braces} tone="info" />
              <StatTile label="今日活跃会话" value={fmtInt(counts.active_sessions_today)} sub={`累计 ${fmtInt(counts.total_sessions)}`} icon={MessageSquare} tone="ok" />
              <StatTile label="平台用户" value={fmtInt(counts.users)} sub="已注册账号" icon={Users} tone="accent" />
            </div>

            <div className="monitor-workspace">
              <Panel title="计算资源与服务" eyebrow="INFRASTRUCTURE" icon={Server} className="monitor-infrastructure"
                action={<span className="monitor-live-label"><i />2s 实时</span>}>
                <div className="monitor-resource-grid">
                  <ResourceGauge value={hw.cpu_percent} label="处理器" detail={`${hw.cpu_count || 0} 逻辑核心`} icon={Cpu} />
                  <ResourceGauge value={hw.mem_percent} label="内存" detail={`${((hw.mem_used_mb || 0) / 1024).toFixed(1)} / ${((hw.mem_total_mb || 0) / 1024).toFixed(0)} GB`} icon={MemoryStick} />
                  <ResourceGauge value={hw.disk_percent} label="磁盘" detail={`${hw.disk_used_gb || 0} / ${hw.disk_total_gb || 0} GB`} icon={HardDrive} />
                </div>
                <div className="monitor-network">
                  <div><ArrowUpRight size={12} /><span>上行</span><b className="num-mono">{(hw.net_sent_mb ?? 0).toFixed(2)} <small>MB/s</small></b></div>
                  <div><ArrowDownRight size={12} /><span>下行</span><b className="num-mono">{(hw.net_recv_mb ?? 0).toFixed(2)} <small>MB/s</small></b></div>
                </div>
                <div className="monitor-section-label"><span>服务矩阵</span><span>{healthy ? 'ALL SYSTEMS NOMINAL' : 'CHECK REQUIRED'}</span></div>
                <div className="monitor-services">
                  <ServiceRow name="数据库" ok={!!svc.database?.ok} detail={svc.database?.journal_mode || '未知'} />
                  <ServiceRow name="向量索引" ok={!!svc.vector_index?.ok} detail={svc.vector_index?.ok ? `${fmtInt(svc.vector_index.indexed)} 条` : '不可用'} />
                  <ServiceRow name="定时任务" ok={!!svc.cron?.ok} detail={`${svc.cron?.running ? '运行中' : '已停止'} · ${fmtInt(crons.runs)} 次 / 24h`} />
                  <ServiceRow name="知识库模型" ok={!!svc.knowledge?.ok} detail={svc.knowledge?.ok ? '已就绪' : '未加载'} />
                </div>
                <div className="monitor-runtime">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1.5 text-[10px] t-text-muted"><Timer size={12} />事件循环</span>
                    <span className={`text-[10px] num-mono ${loop.blocked ? 't-text-danger' : 't-text-ok'}`}>{(loop.latency_ms ?? 0).toFixed(1)} ms</span>
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-2">
                    <span className="text-[9px] t-text-faint">运行 {fmtInt(loop.uptime_min)} min</span>
                    <span className={`monitor-health-pill ${loop.blocked ? 'is-bad' : ''}`}><ShieldCheck size={10} />{loop.blocked ? '存在阻塞' : '响应正常'}</span>
                  </div>
                </div>
                <div className="monitor-db-line">
                  <Database size={12} /><span>主库 <b className="num-mono">{fmtInt(db.db_mb)} MB</b></span><i />
                  <span>WAL <b className="num-mono">{fmtInt(db.wal_mb)} MB</b></span>
                </div>
              </Panel>

              <Panel title="模型调用态势" eyebrow="7 DAY ACTIVITY" icon={TrendingUp} className="monitor-trend"
                action={<div className="monitor-chart-legend"><span><i />调用次数</span><b className="num-mono">{fmtInt(models.total_calls)}</b></div>}>
                <TrendChart data={daily.slice(-7)} />
              </Panel>

              <Panel title="接口健康与实时请求" eyebrow="API TELEMETRY" icon={GaugeIcon} className="monitor-api"
                action={<span className={`monitor-health-pill ${errorRate >= 1 ? 'is-bad' : ''}`}>{errorRate >= 1 ? 'ATTENTION' : 'HEALTHY'}</span>}>
                <div className="monitor-api-stats">
                  <div><span>今日请求</span><b className="num-mono t-text">{fmtInt(traffic.api_today_total)}</b></div>
                  <div><span>5xx 错误</span><b className={`num-mono ${traffic.api_today_errors ? 't-text-danger' : 't-text-ok'}`}>{fmtInt(traffic.api_today_errors)}</b></div>
                  <div><span>平均延迟</span><b className="num-mono t-text-info">{fmtInt(traffic.api_avg_ms)}<small>ms</small></b></div>
                </div>
                <div className="monitor-error-rate">
                  <div><span>接口错误率</span><b className="num-mono">{errorRate.toFixed(2)}%</b></div>
                  <div className="monitor-error-track"><i style={{ width: `${Math.min(100, Math.max(1, errorRate * 5))}%`, background: errorRate >= 1 ? TONE.danger : TONE.ok }} /></div>
                </div>
                <div className="monitor-section-label"><span>实时请求流</span><span className="flex items-center gap-1"><Clock size={9} />LATEST</span></div>
                <RequestLog rows={traffic.recent_api} />
                <div className="monitor-task-summary">
                  <span><Activity size={10} className="inline mr-1 t-text-accent" />24h 任务</span>
                  <b className="num-mono t-text-ok">{fmtInt(crons.ok)}</b><span className="t-text-faint">成功</span>
                  <b className={`num-mono ${crons.failed ? 't-text-danger' : 't-text-ok'}`}>{fmtInt(crons.failed)}</b><span className="t-text-faint">失败</span>
                  <span className="ml-auto num-mono t-text-faint">{crons.avg_duration ?? 0}s</span>
                </div>
              </Panel>

              <Panel title="模型调用 Top" eyebrow="MODEL PERFORMANCE" icon={Bot} className="monitor-models"
                action={<span className="text-[9px] t-text-faint">次数 · 首字耗时</span>}>
                <RankList items={modelRanking} limit={4} />
              </Panel>

              <Panel title="用户 Token 消耗" eyebrow="CONSUMPTION RANK" icon={Users} className="monitor-users"
                action={<span className="text-[9px] t-text-faint">TOP 4</span>}>
                <RankList items={tokenRanking} limit={4} tone="info" />
              </Panel>
            </div>

            <footer className="monitor-footer">
              <span><i className={enabled ? 'is-online' : ''} />{enabled ? '数据链路已连接' : '数据链路已挂起'}</span>
              <span className="hidden sm:inline">消息 {fmtInt(db.table_rows?.mu_chat_messages)} · 接口日志 {fmtInt(db.table_rows?.mu_api_access_logs)} · 任务记录 {fmtInt(db.table_rows?.mu_cron_runs)}</span>
              <span className="ml-auto num-mono">UTC+8 · {fmtTime(updatedAt)}</span>
            </footer>
          </div>
        )}
      </main>
    </div>
  )
}

export default AdminMonitor
