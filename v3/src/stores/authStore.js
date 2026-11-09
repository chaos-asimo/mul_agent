import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiGet, apiPost } from '../api/client'

export const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      loading: true,
      needs2fa: false,

      login: async (username, password) => {
        try {
          const result = await apiPost('/login', { username, password })
          if (result.status === 'success' && result.user) {
            set({ user: result.user, loading: false, needs2fa: false })
            return { success: true }
          }
          // TOTP 已启用：进入二次验证
          if (result.status === 'needs_2fa') {
            return { success: false, needs2fa: true, username: result.username }
          }
          return { success: false, message: result.message || '登录失败' }
        } catch (error) {
          return { success: false, message: error.message || '登录失败' }
        }
      },

      login2fa: async (username, totp) => {
        try {
          const result = await apiPost('/login/2fa', { username, totp })
          if (result.status === 'success' && result.user) {
            set({ user: result.user, loading: false, needs2fa: false })
            return { success: true }
          }
          return { success: false, message: result.message || '二次验证失败' }
        } catch (error) {
          return { success: false, message: error.message || '二次验证失败' }
        }
      },

      logout: async () => {
        try {
          await apiPost('/logout')
        } catch (error) {
          console.error('退出登录失败:', error)
        } finally {
          set({ user: null, needs2fa: false })
        }
      },

      clearUser: () => set({ user: null, needs2fa: false }),

      checkAuth: async () => {
        try {
          const result = await apiGet('/me')
          set({
            user: result.user || null,
            needs2fa: !!result.needs_2fa,
            loading: false,
          })
        } catch (error) {
          set({ user: null, needs2fa: false, loading: false })
        }
      },

      isLoggedIn: () => !!get().user,
    }),
    {
      name: 'v3_auth',
      partialize: (state) => ({ user: state.user }),
    },
  ),
)
