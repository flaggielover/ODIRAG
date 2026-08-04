<script setup lang="ts">
import { X } from '@lucide/vue'

defineProps<{
  open: boolean
  title: string
  width?: 'small' | 'medium' | 'large'
}>()

defineEmits<{
  close: []
}>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" role="presentation" @mousedown.self="$emit('close')">
      <section
        class="modal-dialog"
        :class="`modal-${width ?? 'medium'}`"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
      >
        <header class="modal-header">
          <h2>{{ title }}</h2>
          <button class="icon-button" type="button" title="关闭" aria-label="关闭" @click="$emit('close')">
            <X :size="18" aria-hidden="true" />
          </button>
        </header>
        <div class="modal-body"><slot /></div>
        <footer v-if="$slots.footer" class="modal-footer"><slot name="footer" /></footer>
      </section>
    </div>
  </Teleport>
</template>
