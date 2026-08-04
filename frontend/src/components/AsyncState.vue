<script setup lang="ts">
import { AlertTriangle, Inbox, LoaderCircle, RefreshCw } from '@lucide/vue'

defineProps<{
  loading?: boolean
  error?: string | null
  empty?: boolean
  emptyText?: string
}>()

defineEmits<{
  retry: []
}>()
</script>

<template>
  <div v-if="loading" class="state-panel" role="status" aria-live="polite">
    <LoaderCircle class="spin" :size="22" aria-hidden="true" />
    <span>正在加载</span>
  </div>
  <div v-else-if="error" class="state-panel state-panel-error" role="alert">
    <AlertTriangle :size="22" aria-hidden="true" />
    <span>{{ error }}</span>
    <button class="icon-button" type="button" title="重试" aria-label="重试" @click="$emit('retry')">
      <RefreshCw :size="17" aria-hidden="true" />
    </button>
  </div>
  <div v-else-if="empty" class="state-panel" role="status">
    <Inbox :size="22" aria-hidden="true" />
    <span>{{ emptyText ?? '暂无数据' }}</span>
  </div>
  <slot v-else />
</template>
