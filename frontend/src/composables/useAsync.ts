import { ref } from 'vue'

import { ApiError } from '@/api/client'

export function useAsyncTask() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function run<T>(operation: () => Promise<T>): Promise<T | null> {
    loading.value = true
    error.value = null
    try {
      return await operation()
    } catch (caught) {
      error.value = caught instanceof ApiError ? caught.message : '操作未完成，请稍后重试'
      return null
    } finally {
      loading.value = false
    }
  }

  return { loading, error, run }
}
