import { createRouter, createWebHistory } from 'vue-router'

import { auth } from '@/auth/state'
import AppShell from '@/layouts/AppShell.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/',
      component: AppShell,
      children: [
        { path: '', component: () => import('@/views/DashboardView.vue'), meta: { title: '仪表盘' } },
        { path: 'sources', component: () => import('@/views/SourcesView.vue'), meta: { title: '来源' } },
        { path: 'source-discovery', component: () => import('@/views/SourceDiscoveryView.vue'), meta: { title: '来源发现' } },
        { path: 'crawl-tasks', component: () => import('@/views/CrawlTasksView.vue'), meta: { title: '抓取任务' } },
        { path: 'crawl-tasks/:id', component: () => import('@/views/CrawlTaskDetailView.vue'), meta: { title: '抓取任务详情' } },
        { path: 'documents', component: () => import('@/views/DocumentsView.vue'), meta: { title: '文档' } },
        { path: 'documents/:id', component: () => import('@/views/DocumentDetailView.vue'), meta: { title: '文档详情' } },
        { path: 'reviews', component: () => import('@/views/ReviewsView.vue'), meta: { title: '人工审核' } },
        { path: 'chat', component: () => import('@/views/ChatView.vue'), meta: { title: '问答与证据' } },
        { path: 'evaluations', component: () => import('@/views/EvaluationsView.vue'), meta: { title: '评估' } },
        { path: 'experiments', component: () => import('@/views/ExperimentsView.vue'), meta: { title: '实验' } },
        { path: 'monitoring', component: () => import('@/views/MonitoringView.vue'), meta: { title: '监控与告警' } },
        { path: 'activity', component: () => import('@/views/ActivityView.vue'), meta: { title: '反馈与日志' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  await auth.bootstrap()
  if (!to.meta.public && !auth.authenticated.value) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.path === '/login' && auth.authenticated.value) return '/'
  return true
})

window.addEventListener('odirag:auth-expired', () => {
  if (router.currentRoute.value.path !== '/login') {
    void router.replace({ path: '/login', query: { redirect: router.currentRoute.value.fullPath } })
  }
})
