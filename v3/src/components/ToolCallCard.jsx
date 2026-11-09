import { useState } from 'react'
import { ChevronDown, ChevronUp, CheckCircle, Loader2 } from 'lucide-react'
import MarkdownContent from './MarkdownContent'

// 单个工具调用卡片：WorkBuddy 风格
// props: { icon, name, status: 'running'|'done'|'error', result }
export default function ToolCallCard({ icon, name, status = 'done', result }) {
  const [expanded, setExpanded] = useState(false)
  const hasResult = result && result.trim().length > 0

  return (
    <div className="my-1.5 rounded-xl border t-border overflow-hidden t-bg-bubble">
      {/* 卡片头部：图标 + 工具名 + 状态 */}
      <button
        onClick={() => hasResult && setExpanded((v) => !v)}
        className={`w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors ${
          hasResult ? 'hover:t-bg-accent-soft/40 cursor-pointer' : 'cursor-default'
        }`}
      >
        <span className="text-base leading-none">{icon}</span>
        <span className="text-sm font-medium t-text flex-1 truncate">{name}</span>
        {status === 'running' ? (
          <span className="inline-flex items-center gap-1.5 text-xs t-text-accent">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            执行中
          </span>
        ) : status === 'error' ? (
          <span className="inline-flex items-center gap-1.5 text-xs t-text-danger">
            <span>✕</span>
            失败
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 text-xs t-text-success">
            <CheckCircle className="w-3.5 h-3.5" />
            完成
          </span>
        )}
        {hasResult && (
          <span className="t-text-fainter">
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </span>
        )}
      </button>

      {/* 可折叠的结果内容：按 Markdown 渲染（表格/代码块/列表），限制高度可滚动 */}
      {hasResult && expanded && (
        <div className="px-3 pb-3 border-t t-border">
          <div className="mt-2 p-2.5 rounded-lg t-bg-input text-xs t-text-2 max-h-[400px] overflow-y-auto">
            <MarkdownContent content={result} />
          </div>
        </div>
      )}
    </div>
  )
}
