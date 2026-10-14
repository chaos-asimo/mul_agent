import { useState } from 'react'
import { X, Maximize2, Minimize2 } from 'lucide-react'

/**
 * 通用模态窗：wide 加宽、max 接近全屏；标题栏可最大化切换。用于放大查看执行结果等。
 */
export default function Modal({ title, onClose, children, wide = false, max = false, maximizable = true }) {
  const [isMax, setIsMax] = useState(max)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={onClose}>
      <div
        className={`t-bg-panel border t-border-strong rounded-2xl shadow-2xl flex flex-col ${
          isMax
            ? 'w-[98vw] h-[96vh]'
            : wide
              ? 'w-full max-w-3xl max-h-[85vh]'
              : 'w-full max-w-xl max-h-[85vh]'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3.5 border-b t-border shrink-0">
          <h3 className="text-sm font-semibold t-text">{title}</h3>
          <div className="flex items-center gap-1.5">
            {maximizable && (
              <button
                onClick={() => setIsMax((v) => !v)}
                title={isMax ? '还原' : '最大化'}
                className="t-text-faint t-hover-text p-0.5"
              >
                {isMax ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
              </button>
            )}
            <button onClick={onClose} className="t-text-faint t-hover-text">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
        <div className={`p-5 ${isMax ? 'flex-1 overflow-hidden flex flex-col' : 'overflow-y-auto'}`}>{children}</div>
      </div>
    </div>
  )
}
