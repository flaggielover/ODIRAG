<script setup lang="ts">
import { AlertCircle, Bot, KeyRound, LoaderCircle, ShieldCheck, UserRound } from '@lucide/vue'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/client'
import { api } from '@/api/resources'
import type { HealthResponse } from '@/api/types'
import { auth } from '@/auth/state'
import StatusBadge from '@/components/StatusBadge.vue'

const username = ref('')
const password = ref('')
const error = ref<string | null>(null)
const health = ref<HealthResponse | null>(null)
const router = useRouter()
const route = useRoute()

onMounted(async () => {
  health.value = await api.health().catch(() => null)
})

async function submit(): Promise<void> {
  if (!username.value.trim() || !password.value) return
  error.value = null
  try {
    await auth.login(username.value.trim(), password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (caught) {
    error.value = caught instanceof ApiError ? caught.message : '登录未完成，请重试'
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-panel" aria-labelledby="login-title">
      <header class="login-brand">
        <div class="brand-mark"><Bot :size="22" aria-hidden="true" /></div>
        <div>
          <strong>ODIRAG</strong>
          <span>官方数据智能检索</span>
        </div>
      </header>

      <div class="login-heading">
        <ShieldCheck :size="24" aria-hidden="true" />
        <div>
          <h1 id="login-title">管理员登录</h1>
          <StatusBadge :status="health?.status ?? 'unavailable'" />
        </div>
      </div>

      <form class="login-form" @submit.prevent="submit">
        <div class="form-field">
          <label for="username">用户名</label>
          <div class="input-with-icon">
            <UserRound :size="17" aria-hidden="true" />
            <input
              id="username"
              v-model="username"
              class="input"
              name="username"
              autocomplete="username"
              required
              autofocus
            />
          </div>
        </div>
        <div class="form-field">
          <label for="password">密码</label>
          <div class="input-with-icon">
            <KeyRound :size="17" aria-hidden="true" />
            <input
              id="password"
              v-model="password"
              class="input"
              name="password"
              type="password"
              autocomplete="current-password"
              required
            />
          </div>
        </div>

        <div v-if="error" class="notice notice-error" role="alert">
          <AlertCircle :size="17" aria-hidden="true" />
          <span>{{ error }}</span>
        </div>

        <button class="button login-submit" type="submit" :disabled="auth.state.pending">
          <LoaderCircle v-if="auth.state.pending" class="spin" :size="17" aria-hidden="true" />
          <ShieldCheck v-else :size="17" aria-hidden="true" />
          {{ auth.state.pending ? '正在验证' : '登录' }}
        </button>
      </form>
    </section>
  </main>
</template>
