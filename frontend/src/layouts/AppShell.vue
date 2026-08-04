<script setup lang="ts">
import {
  Activity,
  BellRing,
  BookOpenText,
  Bot,
  ChevronLeft,
  ClipboardCheck,
  DatabaseZap,
  FileSearch,
  FlaskConical,
  Gauge,
  LogOut,
  Menu,
  MessageSquareText,
  RadioTower,
  SearchCheck,
  ServerCog,
  X,
} from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'

import { api } from '@/api/resources'
import type { HealthResponse } from '@/api/types'
import { auth } from '@/auth/state'
import StatusBadge from '@/components/StatusBadge.vue'

const route = useRoute()
const router = useRouter()
const mobileOpen = ref(false)
const collapsed = ref(false)
const health = ref<HealthResponse | null>(null)

const groups = [
  {
    label: '概览',
    items: [{ to: '/', label: '仪表盘', icon: Gauge }],
  },
  {
    label: '内容管理',
    items: [
      { to: '/sources', label: '来源', icon: RadioTower },
      { to: '/source-discovery', label: '来源发现', icon: SearchCheck },
      { to: '/crawl-tasks', label: '抓取任务', icon: DatabaseZap },
      { to: '/documents', label: '文档', icon: BookOpenText },
      { to: '/reviews', label: '人工审核', icon: ClipboardCheck },
    ],
  },
  {
    label: '智能检索',
    items: [{ to: '/chat', label: '问答与证据', icon: MessageSquareText }],
  },
  {
    label: '质量工程',
    items: [
      { to: '/evaluations', label: '评估', icon: FileSearch },
      { to: '/experiments', label: '实验', icon: FlaskConical },
    ],
  },
  {
    label: '系统运维',
    items: [
      { to: '/monitoring', label: '监控与告警', icon: ServerCog },
      { to: '/activity', label: '反馈与日志', icon: Activity },
    ],
  },
]

const currentLabel = computed(() => String(route.meta.title ?? 'ODIRAG'))

let healthTimer: number | undefined

onMounted(async () => {
  health.value = await api.health().catch(() => null)
  healthTimer = window.setInterval(async () => {
    health.value = await api.health().catch(() => null)
  }, 60_000)
})

onUnmounted(() => {
  if (healthTimer !== undefined) window.clearInterval(healthTimer)
})

async function signOut(): Promise<void> {
  await auth.logout()
  await router.replace('/login')
}
</script>

<template>
  <div class="app-shell" :class="{ 'nav-collapsed': collapsed, 'mobile-nav-open': mobileOpen }">
    <aside class="sidebar">
      <div class="brand-row">
        <div class="brand-mark" aria-hidden="true"><Bot :size="21" /></div>
        <div class="brand-copy">
          <strong>ODIRAG</strong>
          <span>管理控制台</span>
        </div>
        <button
          class="icon-button sidebar-close"
          type="button"
          title="关闭导航"
          aria-label="关闭导航"
          @click="mobileOpen = false"
        >
          <X :size="19" aria-hidden="true" />
        </button>
      </div>

      <nav aria-label="主导航">
        <section v-for="group in groups" :key="group.label" class="nav-group">
          <h2>{{ group.label }}</h2>
          <RouterLink
            v-for="item in group.items"
            :key="item.to"
            :to="item.to"
            :title="collapsed ? item.label : undefined"
            @click="mobileOpen = false"
          >
            <component :is="item.icon" :size="18" aria-hidden="true" />
            <span>{{ item.label }}</span>
          </RouterLink>
        </section>
      </nav>

      <div class="sidebar-footer">
        <div class="sidebar-health">
          <BellRing :size="17" aria-hidden="true" />
          <StatusBadge :status="health?.status ?? 'unavailable'" />
        </div>
        <button class="nav-action" type="button" @click="signOut">
          <LogOut :size="18" aria-hidden="true" />
          <span>退出登录</span>
        </button>
      </div>
    </aside>

    <button class="nav-scrim" type="button" aria-label="关闭导航" @click="mobileOpen = false" />

    <div class="workspace">
      <header class="topbar">
        <div class="topbar-leading">
          <button
            class="icon-button mobile-menu"
            type="button"
            title="打开导航"
            aria-label="打开导航"
            @click="mobileOpen = true"
          >
            <Menu :size="20" aria-hidden="true" />
          </button>
          <button
            class="icon-button collapse-button"
            type="button"
            :title="collapsed ? '展开导航' : '收起导航'"
            :aria-label="collapsed ? '展开导航' : '收起导航'"
            @click="collapsed = !collapsed"
          >
            <ChevronLeft :size="18" :class="{ rotate: collapsed }" aria-hidden="true" />
          </button>
          <span class="topbar-title">{{ currentLabel }}</span>
        </div>
        <div class="user-chip">
          <span class="user-avatar">{{ auth.state.user?.username.slice(0, 1).toUpperCase() }}</span>
          <span>{{ auth.state.user?.username }}</span>
        </div>
      </header>

      <main class="page-content">
        <RouterView />
      </main>
    </div>
  </div>
</template>
