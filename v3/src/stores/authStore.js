import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { apiGet, apiPost } from '../api/client'

export const useAuthStore = create(
  persist(
    (set, get) => ({
      user: null,
      loading: true,

      login: async (username, password) => {
        try {
          const result = await apiPost('/login', { username, password })
          if (result.status === 'success' && result.user) {
            set({ user: result.user, loading: false })
            return { success: true }
          }
          return { success: false, message: result.message || '登录失败' }
        } catch (error) {
          return { success: false, message: error.message || '登录失败' }
        }
      },

      logout: async () => {
        try {
          await apiPost('/logout')
        } catch (error) {
          console.error('退出登录失败:', error)
        } finally {
          set({ user: null })
        }
      },

      clearUser: () => set({ user: null }),

      checkAuth: async () => {
        try {
          const result = await apiGet('/me')
          set({ user: result.user || null, loading: false })
        } catch (error) {
          set({ user: null, loading: false })
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
