<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed } from 'vue'

const props = defineProps<{
  content: string
}>()

const html = computed(() =>
  DOMPurify.sanitize(marked.parse(props.content, { async: false }), {
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'button'],
    FORBID_ATTR: ['style', 'srcset'],
  }),
)

function handleClick(event: MouseEvent): void {
  const target = event.target
  if (!(target instanceof Element)) return
  const anchor = target.closest('a')
  if (!(anchor instanceof HTMLAnchorElement)) return
  const destination = new URL(anchor.href, window.location.href)
  if (destination.origin !== window.location.origin) {
    event.preventDefault()
    window.open(destination.href, '_blank', 'noopener,noreferrer')
  }
}
</script>

<template>
  <div class="markdown-content" @click="handleClick" v-html="html" />
</template>
