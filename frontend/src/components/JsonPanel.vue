<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  value: unknown
  label?: string
}>()

const formatted = computed(() => JSON.stringify(props.value, null, 2))
</script>

<template>
  <section class="json-panel">
    <div v-if="label" class="panel-label">{{ label }}</div>
    <pre>{{ formatted }}</pre>
  </section>
</template>
