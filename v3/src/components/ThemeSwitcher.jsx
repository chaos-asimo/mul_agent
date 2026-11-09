import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Moon, Droplets, Sun, Monitor, Check, Palette } from 'lucide-react'
import { useThemeStore, THEMES } from '../stores/themeStore'

const ICONS = { dark: Moon, deepblue: Droplets, light: Sun, auto: Monitor }

// 顶栏主题切换：下拉显式选择（暗色/深蓝/亮色/跟随系统），带色块与选中态
// 使用 Portal + fixed 定位渲染到 body，避免被顶栏 overflow-x-auto 容器裁剪
function ThemeSwitcher() {
  const theme = useThemeStore((s) => s.theme)
  const setTheme = useThemeStore((s) => s.setTheme)
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState({ top: 0, right: 0 })
  const btnRef = useRef(null)
  const menuRef = useRef(null)

  const updateCoords = () => {
    const el = btnRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    setCoords({
      top: rect.bottom + 8,
      right: window.innerWidth - rect.right,
    })
  }

  useEffect(() => {
    const onDown = (e) => {
      if (
        btnRef.current && !btnRef.current.contains(e.target) &&
        menuRef.current && !menuRef.current.contains(e.target)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  // 滚动/尺寸变化时重新定位或关闭（fixed 定位下滚动会错位）
  useEffect(() => {
    if (!open) return
    const onScrollOrResize = () => setOpen(false)
    window.addEventListener('scroll', onScrollOrResize, true)
    window.addEventListener('resize', onScrollOrResize)
    return () => {
      window.removeEventListener('scroll', onScrollOrResize, true)
      window.removeEventListener('resize', onScrollOrResize)
    }
  }, [open])

  const Current = ICONS[theme] || Moon

  const toggle = () => {
    if (!open) updateCoords()
    setOpen((o) => !o)
  }

  return (
    <div className="relative" ref={btnRef}>
      <button
        onClick={toggle}
        title="主题"
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors"
      >
        <Current className="w-3.5 h-3.5" />
        <Palette className="w-3.5 h-3.5" />
      </button>

      {open &&
        createPortal(
          <div
            ref={menuRef}
            className="fixed w-40 rounded-xl border t-border t-bg-panel shadow-2xl py-1 z-[9999]"
            style={{ top: coords.top, right: coords.right }}
          >
            {THEMES.map(({ key, label, color }) => {
              const Icon = ICONS[key]
              const active = theme === key
              return (
                <button
                  key={key}
                  onClick={() => {
                    setTheme(key)
                    setOpen(false)
                  }}
                  className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs transition-colors t-hover-bg ${
                    active ? 't-text-accent' : 't-text-2'
                  }`}
                >
                  <span
                    className="w-3 h-3 rounded-full border t-border-strong shrink-0"
                    style={{ background: color }}
                  />
                  <Icon className="w-3.5 h-3.5 shrink-0" />
                  <span>{label}</span>
                  {active && <Check className="w-3.5 h-3.5 ml-auto" />}
                </button>
              )
            })}
          </div>,
          document.body
        )}
    </div>
  )
}

export default ThemeSwitcher
