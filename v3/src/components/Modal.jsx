import { X } from 'lucide-react'

/**
 * 通用模态窗：wide 加宽、max 接近全屏。用于放大查看执行结果等。
 */
export default function Modal({ title, onClose, children, wide = false, max = false }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70" onClick={onClose}>
      <div
        className={`t-bg-panel border t-border-strong rounded-2xl shadow-2xl flex flex-col ${
          max
            ? 'w-[96vw] h-[94vh]'
            : wide
              ? 'w-full max-w-3xl max-h-[85vh]'
              : 'w-full max-w-xl max-h-[85vh]'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-5 py-3.5 border-b t-border shrink-0">
          <h3 className="text-sm font-semibold t-text">{title}</h3>
          <button onClick={onClose} className="t-text-faint t-hover-text">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className={`p-5 ${max ? 'flex-1 overflow-hidden flex flex-col' : 'overflow-y-auto'}`}>{children}</div>
      </div>
    </div>
  )
}
