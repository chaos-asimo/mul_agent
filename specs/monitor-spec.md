# v3 运行监控页 — 技术规格书

> 管理员实时监控系统运行状态。一个页面掌握硬件资源、服务健康、模型调用、接口流量、定时任务。科技感 UI，数据实时刷新。

## 1. 概述

在 v3 工作台新增管理员页面 `/admin/monitor`，聚合展示系统运行全貌：

- **KPI 概览**：今日模型调用、Token 消耗、活跃会话、用户数、CPU/内存/磁盘占用
- **资源监控**：CPU、内存、磁盘半圆仪表盘（gauges），网络流量
- **服务健康**：数据库、向量索引、定时任务调度、知识库模型存活状态
- **接口流量**：今日 API 请求数、错误率、平均延迟、最近请求日志
- **模型调用**：7 日调用趋势柱状图、模型 Top 排名、用户 Token 消耗排名
- **数据库**：文件大小、核心表行数、WAL 状态

**设计风格**：暗色主题下近黑背景 `#020617` + 靛蓝 `#4f46e5` 主调 + 青色 `#7dd3fc` 辅助 + 绿色 `#6ee7b7` 健康态，半透明面板 `#0f172a`，卡片带微光晕。

## 2. 后端 API

### 2.1 新增 `GET /api/lobster-mu/admin/monitor`（聚合端点，require_admin）

一次返回全部监控数据。在 `web/routes/lobster_mu.py` 的 `/admin/config` 路由之前新增。

```python
import psutil, os, time, asyncio
from datetime import datetime

# 模块级 psutil priming（CPU% 需要两次调用才有差值）
psutil.cpu_percent(None)
_net_prev = psutil.net_io_counters()
_net_prev_ts = time.time()

# 事件循环看门狗
_loop_probe = {"latency_ms": 0.0, "started": time.time(), "_task": None}

async def _loop_watchdog():
    while True:
        t0 = time.perf_counter()
        await asyncio.sleep(1)
        drift = (time.perf_counter() - t0) - 1.0
        _loop_probe["latency_ms"] = max(0.0, drift * 1000)
```

端点返回 JSON 结构：

```json
{
  "success": true,
  "data": {
    "ts": 1701331200,
    "hardware": {
      "cpu_percent": 34.2,
      "cpu_count": 16,
      "mem_percent": 61.0,
      "mem_total_mb": 16384,
      "mem_used_mb": 9984,
      "disk_percent": 48.0,
      "disk_total_gb": 477,
      "disk_used_gb": 229,
      "net_sent_mb": 1.2,
      "net_recv_mb": 8.5
    },
    "services": {
      "database":   {"ok": true, "journal_mode": "wal"},
      "vector_index": {"ok": true, "indexed": 1234, "expected": 1300},
      "cron":       {"ok": true, "running": true, "enabled_tasks": 5},
      "knowledge":  {"ok": true}
    },
    "loop": {"latency_ms": 0.4, "blocked": false, "uptime_min": 1440},
    "counts": {
      "users": 42,
      "active_sessions_today": 128,
      "total_sessions": 1560
    },
    "db": {
      "db_mb": 234,
      "wal_mb": 4,
      "table_rows": {
        "mu_chat_messages": 90000,
        "mu_api_access_logs": 210000,
        "mu_cron_runs": 5000
      }
    },
    "traffic": {
      "api_today_total": 5000,
      "api_today_errors": 12,
      "api_avg_ms": 88,
      "cron_24h_runs": 34,
      "cron_24h_ok": 32,
      "cron_24h_failed": 2,
      "recent_api": [
        {"method": "GET", "path": "/chat/stream", "status": 200, "ms": 95, "user": "alice", "time": "14:23:01"}
      ]
    },
    "models": {
      "total_calls": 1523,
      "total_tokens": 4567890,
      "avg_duration_s": 2.3,
      "success_rate": 0.98,
      "daily_stats": [
        {"date": "2026-10-24", "calls": 120, "tokens": 456000, "avg_ms": 2100}
      ],
      "top_models": [
        {"model": "gpt-4o", "calls": 500, "tokens": 1800000}
      ]
    }
  }
}
```

**实现要点**：
- `psutil.cpu_percent(None)` 取快照值（模块级已 prime）
- 内存/磁盘用 `psutil.virtual_memory()` / `psutil.disk_usage('/')`
- 网络用 `psutil.net_io_counters()` 减去模块级 `_net_prev` 算速率
- 服务检测 try/except 包裹：`db.check_wal()`、`vector_index.available()`、cron 调度器 `.running` 属性、知识库模型就绪状态
- 事件循环：首次调用时懒启动 `_loop_watchdog` task
- DB 文件大小：`os.path.getsize(DB_PATH)` + `DB_PATH + "-wal"`
- 表行数：`SELECT COUNT(*)` 三个核心表
- 接口流量：`mu_api_access_logs` 今日统计 + `mu_cron_runs` 24h 统计 + 最近 8 条
- 模型统计：从 `mu_chat_messages` 按 `token_stats` JSON 聚合（与 `/admin/usage-ranking` 同源），7 日趋势按 `created_at` 分组
- 全部用单个 `db.get_conn()` + try/finally close

### 2.2 不新增其他端点

前端直接调用现有端点：
- `GET /admin/usage-ranking` → 用户 Token 消耗排名
- `GET /admin/model-speed` → 模型 TTFT 排名

## 3. 前端页面

### 3.1 文件

**新建** `v3/src/pages/AdminMonitor.jsx` — 单文件包含所有子组件和 polling hook。

**修改**：
- `v3/src/App.jsx` — 导入 AdminMonitor，添加 `<Route path="/admin/monitor" .../>`
- `v3/src/pages/AdminUsers.jsx` — 在管理按钮组添加 `<Link to="/admin/monitor">` 入口（Monitor 图标）
- `v3/src/index.css` — 追加 gauge/glow/pulse 样式块

### 3.2 页面布局

全屏 `min-h-screen t-bg-app t-text`，sticky header + 12 列网格内容区。

```
┌─ HEADER (sticky) ──────────────────────────────────────────────┐
│ ← 运行监控 [● 实时 | 更新于 14:23:01] | ⏸暂停 | ThemeSwitcher │
└────────────────────────────────────────────────────────────────┘

Row A — KPI 指标带（6 个 StatTile，md:grid-cols-6）
  今日调用 | 今日Token | 活跃会话 | 用户数 | CPU% | 内存%

Row B — 资源 + 服务（grid-cols-12）
  [ CPU Gauge 4 ] [ 内存 Gauge 4 ] [ 磁盘 Gauge 4 ]
  [ 服务健康 8 ] [ 事件循环 4 ]

Row C — 趋势 + 流量（grid-cols-12）
  [ 7日调用趋势 8 ] [ 接口健康 4 ]

Row D — 模型 + 用户 + 任务（grid-cols-12）
  [ 模型Top 4 ] [ Token Top 4 ] [ 定时任务 4 ]
  [ 数据库 6 ] [ 最近API请求 6 ]
```

移动端全部折叠为单列 `grid-cols-1 md:grid-cols-12`。

### 3.3 子组件（均定义在 AdminMonitor.jsx 内部）

```jsx
// KPI 数字卡片
function StatTile({ label, value, icon, tone, sub })
  // tone: 'ok' | 'warn' | 'danger' | 'info' | 'accent'
  // 大数字 num-mono，小标签，左侧彩色光晕

// 半圆仪表盘
function Gauge({ value, size, label, sub })
  // 120px conic-gradient 半圆
  // 颜色: <50% ok绿, 50-80% warn黄, >80% danger红
  // 中心大数字 + 底部标签

// 服务状态指示
function ServiceDot({ name, ok, detail })
  // 圆点: ok=绿脉冲, fail=红静态
  // 名称 + 详情文字

// 7 日趋势柱状图
function TrendBars({ data })
  // 7 根垂直柱，高度 = value/max * 100%
  // 渐变填充 linear-gradient(180deg, var(--info), var(--accent))
  // 顶部数值，底部日期

// Top N 列表
function MiniList({ title, icon, items, tone })
  // 每行: 名称 + 进度条 + 数值
  // 进度条宽度 = value/max * 100%

// 最近 API 请求
function RecentApiLog({ rows })
  // 表格: 时间 | 方法 | 路径 | 状态 | 延迟
  // 状态码着色: 2xx绿, 4xx黄, 5xx红
```

### 3.4 数据流与轮询

三组独立 state，各自 polling，互不阻塞：

```js
// 1. 硬件 + 服务 + 流量 + 模型统计 → /admin/monitor，2s 轮询
const [monitor, setMonitor] = useState(null)

// 2. 用户排名 → /admin/usage-ranking，30s 轮询
const [ranking, setRanking] = useState(null)

// 3. 模型速度 → /admin/model-speed，60s 轮询
const [speed, setSpeed] = useState(null)
```

**usePolling hook**（本地定义）：
```js
function usePolling(fn, ms, enabled) {
  useEffect(() => {
    if (!enabled) return
    let alive = true
    const run = async () => {
      try { const r = await fn(); if (alive) r }
      catch { /* 静默，下一轮重试 */ }
    }
    run()
    const id = setInterval(run, ms)
    return () => { alive = false; clearInterval(id) }
  }, [ms, enabled])
}
```

- **暂停/恢复**：header 按钮 toggle `enabled`
- **visibilitychange**：tab 隐藏时停止轮询，显示时恢复
- **错误处理**：各 section 独立 try/catch，失败时显示 `t-bg-danger-soft` 提示条

### 3.5 CSS 新增（追加到 index.css 末尾）

```css
/* ============ 监控页专用 ============ */

/* 等宽数字（tick 时不抖动） */
.num-mono { font-variant-numeric: tabular-nums; }

/* 发光效果 */
.glow-accent { box-shadow: 0 0 18px -4px var(--accent); }
.glow-ok { box-shadow: 0 0 12px -2px var(--ok); }
.glow-danger { box-shadow: 0 0 12px -2px var(--danger); }

/* 实时脉冲圆点 */
@keyframes monitor-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.5); }
}
.pulse-dot {
  width: 8px; height: 8px; border-radius: 50%;
  animation: monitor-pulse 2s ease-in-out infinite;
}

/* 半圆仪表盘 */
.gauge-track {
  width: 120px; height: 60px;
  border-radius: 120px 120px 0 0;
  overflow: hidden;
  position: relative;
  background: var(--bg-card);
}
.gauge-fill {
  position: absolute; bottom: 0; left: 0; right: 0;
  transition: height 0.7s ease-out;
}
.gauge-value {
  position: absolute; bottom: 4px; left: 50%;
  transform: translateX(-50%);
  font-size: 1.25rem; font-weight: 700;
}

/* 趋势柱 */
.trend-bar {
  border-radius: 4px 4px 0 0;
  background: linear-gradient(180deg, var(--info), var(--accent));
  transition: height 0.5s ease-out;
  min-height: 2px;
}

/* 进度条 */
.progress-track {
  height: 6px; border-radius: 3px;
  background: var(--bg-card); overflow: hidden;
}
.progress-fill {
  height: 100%; border-radius: 3px;
  transition: width 0.5s ease-out;
}

/* 页面网格背景（命令中心感） */
.monitor-grid-bg {
  background-image:
    radial-gradient(circle at 50% 0%, rgba(79,70,229,0.08) 0%, transparent 50%),
    repeating-linear-gradient(0deg, transparent, transparent 59px, rgba(148,163,184,0.03) 60px),
    repeating-linear-gradient(90deg, transparent, transparent 59px, rgba(148,163,184,0.03) 60px);
}
```

### 3.6 Header 入口

在 `AdminUsers.jsx` 的管理按钮组（约第 669 行 `执行轨迹` 之后）添加：

```jsx
<Link to="/admin/monitor" className={btnGhost}>
  <Gauge className="w-3.5 h-3.5" />
  运行监控
</Link>
```

`App.jsx` 添加路由：
```jsx
import AdminMonitor from './pages/AdminMonitor'
// ...
<Route path="/admin/monitor" element={
  <MuProtectedRoute adminOnly><AdminMonitor /></MuProtectedRoute>
} />
```

## 4. 实时刷新策略

| 数据 | 端点 | 间隔 | 说明 |
|------|------|------|------|
| CPU/内存/磁盘/网络/服务/事件循环/DB/流量/模型统计 | `/admin/monitor` | **2s** | 核心实时数据 |
| 用户 Token 排名 | `/admin/usage-ranking` | **30s** | 全表扫描，较重 |
| 模型 TTFT | `/admin/model-speed` | **60s** | 全表扫描，最重 |

- 首次挂载立即请求全部三组
- tab 隐藏时暂停轮询（`visibilitychange`）
- 暂停按钮可手动停止
- 2s 间隔驱动"实时"观感：CPU/内存 gauge 缓动、网络流量递增、最近请求追加

## 5. 验证清单

- [ ] `psutil` 已安装且 `/admin/monitor` 返回正确硬件数据
- [ ] 服务健康检测：DB/向量索引/cron/知识库各自 try/except 不崩溃
- [ ] 事件循环看门狗：正常时 latency < 50ms，不报 blocked
- [ ] 前端 2s 轮询：CPU gauge 平滑过渡，最近请求实时追加
- [ ] 暂停/恢复：toggle 按钮停止/重启轮询
- [ ] tab 隐藏时停止轮询
- [ ] 暗色/深蓝/亮色三主题下 UI 正常
- [ ] 移动端单列折叠
- [ ] `npm run build:v3` 成功
- [ ] 打包 `package-deploy.py` 成功
