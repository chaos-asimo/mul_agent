import { useEffect, useRef, useMemo } from 'react'
import { highlightPythonCode } from '../utils/highlight'

/**
 * 带 Python 关键字高亮的代码编辑器：
 * 透明 textarea（上层，接收输入）叠加在高亮 <pre>（下层，显示着色）之上，
 * 滚动位置保持同步。移植自 v1 的脚本编辑器能力。
 */
export default function CodeEditor({ value, onChange, placeholder, minHeight = '18rem', style }) {
  const taRef = useRef(null)
  const preRef = useRef(null)

  const highlighted = useMemo(() => highlightPythonCode(value || ''), [value])

  // 高亮层跟随 textarea 滚动
  const syncScroll = () => {
    if (taRef.current && preRef.current) {
      preRef.current.scrollTop = taRef.current.scrollTop
      preRef.current.scrollLeft = taRef.current.scrollLeft
    }
  }

  useEffect(() => {
    syncScroll()
  }, [value])

  return (
    <div className="code-editor-wrap" style={{ minHeight, ...style }}>
      <pre ref={preRef} className="code-highlight-layer python-highlight" aria-hidden="true">
        <code dangerouslySetInnerHTML={{ __html: highlighted || ' ' }} />
      </pre>
      <textarea
        ref={taRef}
        value={value}
        spellCheck={false}
        placeholder={placeholder}
        onChange={(e) => onChange && onChange(e.target.value)}
        onScroll={syncScroll}
        style={{ minHeight, height: '100%' }}
      />
    </div>
  )
}
