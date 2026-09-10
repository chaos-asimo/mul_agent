import { useState, useRef, useEffect } from 'react'
import { Moon, Droplets, Sun, Monitor, Check, Palette } from 'lucide-react'
import { useThemeStore, THEMES } from '../stores/themeStore'

const ICONS = { dark: Moon, deepblue: Droplets, light: Sun, auto: Monitor }

// 顶栏主题切换：下拉显式选择（暗色/深蓝/亮色/跟随系统），带色块与选中态
function ThemeSwitcher() {
  const theme = useThemeStore((s) => s.theme)
  const setTheme = useThemeStore((s) => s.setTheme)
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [])

  const Current = ICONS[theme] || Moon

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="主题"
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border t-border-strong t-text-2 t-hover-card transition-colors"
      >
        <Current className="w-3.5 h-3.5" />
        <Palette className="w-3.5 h-3.5" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-40 rounded-xl border t-border t-bg-panel shadow-2xl py-1 z-50">
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
        </div>
      )}
    </div>
  )
}

export default ThemeSwitcher
