import { ref, readonly } from 'vue'
import { getSessionInfo, logout as apiLogout } from '@/api/auth'

// Singleton reactive state
const user = ref(null)
const fullName = ref('')
const isAuthenticated = ref(false)
const loading = ref(true)

export function useAuth() {
  async function checkAuth() {
    loading.value = true
    try {
      const info = await getSessionInfo()
      if (info.user && info.user !== 'Guest') {
        user.value = info.user
        fullName.value = info.full_name || info.user
        isAuthenticated.value = true
      } else {
        isAuthenticated.value = false
      }
    } catch {
      isAuthenticated.value = false
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    await apiLogout()
  }

  return {
    user: readonly(user),
    fullName: readonly(fullName),
    isAuthenticated: readonly(isAuthenticated),
    loading: readonly(loading),
    checkAuth,
    logout
  }
}
