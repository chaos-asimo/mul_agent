import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// 主题选项：dark 暗色 / deepblue 深蓝 / light 亮色 / auto 跟随系统
export const THEMES = [
  { key: 'dark', label: '暗色', color: '#64748b' },
  { key: 'deepblue', label: '深蓝', color: '#3b82f6' },
  { key: 'light', label: '亮色', color: '#f8fafc' },
  { key: 'auto', label: '跟随系统', color: 'linear-gradient(135deg,#f8fafc 50%,#0f172a 50%)' },
]

export function systemPrefersDark() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

// auto 解析为实际的 dark/light（deepblue 仅显式选择）
export function resolveTheme(theme) {
  if (theme === 'auto') return systemPrefersDark() ? 'dark' : 'light'
  return theme
}

function applyThemeClass(theme) {
  const resolved = resolveTheme(theme)
  const root = document.documentElement
  root.classList.remove('theme-dark', 'theme-deepblue', 'theme-light')
  root.classList.add(`theme-${resolved}`)
  return resolved
}

export const useThemeStore = create(
  persist(
    (set, get) => ({
      theme: 'dark',
      resolvedTheme: 'dark',

      setTheme: (theme) => {
        if (!THEMES.some((t) => t.key === theme)) return
        const resolved = applyThemeClass(theme)
        set({ theme, resolvedTheme: resolved })
      },

      // 应用启动时调用：恢复 class 并监听系统主题变化（auto 模式下实时跟随）
      initTheme: () => {
        const resolved = applyThemeClass(get().theme)
        set({ resolvedTheme: resolved })
        const mq = window.matchMedia('(prefers-color-scheme: dark)')
        mq.addEventListener?.('change', (e) => {
          if (get().theme === 'auto') {
            const r = e.matches ? 'dark' : 'light'
            document.documentElement.classList.remove('theme-dark', 'theme-light')
            document.documentElement.classList.add(`theme-${r}`)
            set({ resolvedTheme: r })
          }
        })
      },
    }),
    {
      name: 'v3_theme',
      partialize: (state) => ({ theme: state.theme }),
    },
  ),
)
