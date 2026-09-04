import DefaultTheme from 'vitepress/theme'
import MermaidZoomLayout from './MermaidZoomLayout.vue'
import './style.css'

export default {
  extends: DefaultTheme,
  Layout: MermaidZoomLayout,
}
