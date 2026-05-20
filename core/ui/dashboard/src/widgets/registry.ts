import type { ComponentType } from 'react'

export interface WidgetSpec {
  id: string
  title: string
  type: 'text' | 'camera' | 'map' | 'chart'
  voiceOpen: string[]
  voiceClose: string[]
  defaultPos: { x: number; y: number }
  defaultSize: { w: number; h: number }
  component: ComponentType<{ onClose?: () => void }>
}

// No custom widgets in the new JARVIS design — map/camera handled by ContentWindow directly
export const WIDGETS: Record<string, WidgetSpec> = {}

export function getWidget(id: string): WidgetSpec | null {
  return WIDGETS[id] ?? null
}

export function widgetIds(): string[] {
  return Object.keys(WIDGETS)
}

export function matchUtterance(text: string): { action: 'widget_open' | 'widget_close'; id: string } | null {
  const t = text.toLowerCase()
  for (const w of Object.values(WIDGETS)) {
    for (const phrase of w.voiceOpen) {
      if (t.includes(phrase)) return { action: 'widget_open', id: w.id }
    }
    for (const phrase of w.voiceClose) {
      if (t.includes(phrase)) return { action: 'widget_close', id: w.id }
    }
  }
  return null
}
