import { useEffect, useRef, useState } from 'react'
import { Loader2, FileWarning } from 'lucide-react'

/**
 * 浏览器原生渲染 Office 文件（动态 import，按需加载，不拖慢首屏）：
 * - docx → docx-preview
 * - xlsx/xls → SheetJS（xlsx）渲染为表格，多 sheet 可切换
 * - pptx → pptx-preview
 * 旧版二进制 .doc/.ppt 浏览器无法解析，交由上层回退到文本展示。
 */
export default function OfficePreview({ filename, getBuffer }) {
  const hostRef = useRef(null)
  const [status, setStatus] = useState('loading') // loading | ok | error
  const [errMsg, setErrMsg] = useState('')

  useEffect(() => {
    let alive = true
    const ext = String(filename).split('.').pop().toLowerCase()

    async function run() {
      try {
        const buffer = await getBuffer()
        if (!alive || !buffer) return
        const host = hostRef.current
        if (!host) return

        if (ext === 'docx') {
          const mod = await import('docx-preview')
          const renderAsync = mod.renderAsync || mod.default?.renderAsync
          host.innerHTML = ''
          await renderAsync(buffer, host, host, {
            inWrapper: true,
            ignoreWidth: false,
            ignoreHeight: false,
            breakPages: false,
          })
        } else if (ext === 'xlsx' || ext === 'xls') {
          const mod = await import('xlsx')
          const XLSX = mod.default || mod
          const wb = XLSX.read(buffer, { type: 'array' })
          host.innerHTML = ''
          renderWorkbook(wb, XLSX, host)
        } else if (ext === 'pptx') {
          const { init } = await import('pptx-preview')
          host.innerHTML = ''
          // 按容器实际尺寸渲染幻灯片（保持 16:9，充分利用最大化后的弹窗）
          const rect = host.getBoundingClientRect()
          let w = Math.max(320, Math.floor(rect.width) - 24)
          let h = Math.floor(w * 9 / 16)
          const maxH = Math.max(240, Math.floor(rect.height) - 16)
          if (h > maxH) { h = maxH; w = Math.floor(h * 16 / 9) }
          const viewer = init(host, { width: w, height: h })
          await viewer.preview(buffer)
        }
        if (alive) setStatus('ok')
      } catch (e) {
        if (alive) {
          setStatus('error')
          setErrMsg(e?.message || '渲染失败')
        }
      }
    }
    run()
    return () => { alive = false }
  }, [filename])

  // 容器必须始终挂载（run() 在 loading 阶段就要拿到 ref），加载/出错用覆盖层提示
  return (
    <div className="relative flex-1 min-h-0">
      <div ref={hostRef} className="office-preview-host overflow-auto h-full"
        style={{ visibility: status === 'ok' ? 'visible' : 'hidden' }} />
      {status === 'loading' && (
        <div className="absolute inset-0 flex items-center justify-center text-xs t-text-faint gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> 正在渲染文档...
        </div>
      )}
      {status === 'error' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-xs t-text-faint gap-2">
          <FileWarning className="w-6 h-6" /> 渲染失败：{errMsg}
        </div>
      )}
    </div>
  )
}

function renderWorkbook(wb, XLSX, host) {
  const names = wb.SheetNames
  if (!names.length) {
    host.innerHTML = '<p class="t-text-faint text-xs">（空工作簿）</p>'
    return
  }
  // 单 sheet 直接渲染；多 sheet 加简易切换
  if (names.length === 1) {
    host.innerHTML = sheetHtml(wb, XLSX, names[0])
    return
  }
  const bar = document.createElement('div')
  bar.className = 'flex items-center gap-1 mb-2 flex-wrap'
  const body = document.createElement('div')
  const show = (name) => {
    body.innerHTML = sheetHtml(wb, XLSX, name)
    Array.from(bar.children).forEach((b) => {
      b.className = b.dataset.name === name
        ? 'text-[11px] px-2 py-1 rounded t-bg-accent text-white'
        : 'text-[11px] px-2 py-1 rounded border t-border-strong t-text-2 t-hover-card cursor-pointer'
    })
  }
  names.forEach((name, i) => {
    const btn = document.createElement('button')
    btn.textContent = name
    btn.dataset.name = name
    btn.onclick = () => show(name)
    bar.appendChild(btn)
    if (i === 0) show(name)
  })
  host.appendChild(bar)
  host.appendChild(body)
}

function sheetHtml(wb, XLSX, name) {
  const sheet = wb.Sheets[name]
  const html = XLSX.utils.sheet_to_html(sheet, { editable: false })
  return `<div class="office-xlsx">${html}</div>`
}
