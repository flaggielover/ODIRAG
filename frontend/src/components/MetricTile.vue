<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
  label: string
  value: string | number
  detail?: string
  icon?: Component
  tone?: 'default' | 'positive' | 'warning' | 'danger'
}>()
</script>

<template>
  <article class="metric-tile" :class="`metric-${tone ?? 'default'}`">
    <div class="metric-label">
      <component :is="icon" v-if="icon" :size="17" aria-hidden="true" />
      <span>{{ label }}</span>
    </div>
    <strong>{{ value }}</strong>
    <span v-if="detail" class="metric-detail">{{ detail }}</span>
  </article>
</template>
