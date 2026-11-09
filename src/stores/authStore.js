import { create } from 'zustand'

export const useAuthStore = create((set) => ({
  user: null,
  loading: true,
  
  login: async (username, password) => {
    try {
      const response = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const result = await response.json()
      
      if (result.status === 'success') {
        set({ user: { username }, loading: false })
        return { success: true }
      } else {
        return { success: false, message: result.message }
      }
    } catch (error) {
      return { success: false, message: error.message }
    }
  },
  
  logout: async () => {
    try {
      await fetch('/api/logout', {
        method: 'POST',
      })
    } catch (error) {
      console.error('Logout error:', error)
    } finally {
      set({ user: null })
    }
  },
  
  checkAuth: async () => {
    set({ loading: true })
    try {
      const response = await fetch('/api/status')
      const result = await response.json()
      if (response.ok) {
        set({ user: { username: 'shineyue' }, loading: false })
      } else {
        set({ user: null, loading: false })
      }
    } catch (error) {
      set({ user: null, loading: false })
    }
  },
}))
