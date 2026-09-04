<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vitepress'
import DefaultTheme from 'vitepress/theme'

const route = useRoute()
const enlargedSvg = ref('')
let diagramObserver: MutationObserver | undefined
let decorationFrame: number | undefined
let previousBodyOverflow = ''

function decorateDiagrams() {
  document.querySelectorAll<SVGSVGElement>('.vp-doc .mermaid svg').forEach((svg) => {
    svg.classList.add('mermaid-zoom-trigger')
    svg.setAttribute('tabindex', '0')
    svg.setAttribute('aria-label', '点击放大图表')
  })
}

function scheduleDecoration() {
  if (decorationFrame !== undefined) return

  decorationFrame = window.requestAnimationFrame(() => {
    decorationFrame = undefined
    decorateDiagrams()
  })
}

function openDiagram(svg: SVGSVGElement) {
  enlargedSvg.value = svg.outerHTML
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  void nextTick(() => document.querySelector<HTMLButtonElement>('.mermaid-zoom-close')?.focus())
}

function closeDiagram() {
  if (!enlargedSvg.value) return
  enlargedSvg.value = ''
  document.body.style.overflow = previousBodyOverflow
}

function findDiagramTarget(target: EventTarget | null) {
  return target instanceof Element
    ? target.closest<SVGSVGElement>('.vp-doc .mermaid svg')
    : null
}

function handleDocumentClick(event: MouseEvent) {
  const target = event.target
  if (target instanceof Element && target.closest('a')) return

  const svg = findDiagramTarget(target)
  if (svg) openDiagram(svg)
}

function handleDocumentKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    closeDiagram()
    return
  }

  if (event.key !== 'Enter' && event.key !== ' ') return
  const svg = findDiagramTarget(event.target)
  if (!svg) return

  event.preventDefault()
  openDiagram(svg)
}

watch(() => route.path, closeDiagram)

onMounted(() => {
  decorateDiagrams()
  diagramObserver = new MutationObserver(scheduleDecoration)
  diagramObserver.observe(document.body, { childList: true, subtree: true })
  document.addEventListener('click', handleDocumentClick)
  document.addEventListener('keydown', handleDocumentKeydown)
})

onUnmounted(() => {
  diagramObserver?.disconnect()
  if (decorationFrame !== undefined) window.cancelAnimationFrame(decorationFrame)
  document.removeEventListener('click', handleDocumentClick)
  document.removeEventListener('keydown', handleDocumentKeydown)
  closeDiagram()
})
</script>

<template>
  <DefaultTheme.Layout />
  <Teleport to="body">
    <div
      v-if="enlargedSvg"
      class="mermaid-zoom-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Mermaid 图表放大预览"
      @click.self="closeDiagram"
    >
      <button class="mermaid-zoom-close" type="button" aria-label="关闭图表预览" @click="closeDiagram">
        ×
      </button>
      <div class="mermaid-zoom-content" v-html="enlargedSvg" />
    </div>
  </Teleport>
</template>
