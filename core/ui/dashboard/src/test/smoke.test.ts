import { describe, it, expect } from 'vitest'
import { useVectorStore } from '../store/vectorStore'

describe('vectorStore — smoke', () => {
  it('initialises with sane defaults', () => {
    const s = useVectorStore.getState()
    expect(s.bootDone).toBe(false)
    expect(s.processing).toBe(false)
    expect(s.voiceState).toBe('idle')
    expect(['ORB_MODE', 'DASHBOARD_MODE', 'FORTRESS_MODE']).toContain(s.mode)
    expect(Array.isArray(s.contentWindows)).toBe(true)
  })

  it('voiceState transitions cover the FSM events', () => {
    const { setVoiceState } = useVectorStore.getState()
    setVoiceState('listening')
    expect(useVectorStore.getState().voiceState).toBe('listening')
    setVoiceState('processing')
    expect(useVectorStore.getState().voiceState).toBe('processing')
    setVoiceState('speaking')
    expect(useVectorStore.getState().voiceState).toBe('speaking')
    setVoiceState('idle')
    expect(useVectorStore.getState().voiceState).toBe('idle')
  })

  it('addContentWindow / removeContentWindow round-trips', () => {
    const s = useVectorStore.getState()
    s.clearContentWindows()
    s.addContentWindow({ id: 'w1', type: 'map', title: 'London' })
    expect(useVectorStore.getState().contentWindows.find((w) => w.id === 'w1')).toBeDefined()
    s.removeContentWindow('w1')
    expect(useVectorStore.getState().contentWindows.find((w) => w.id === 'w1')).toBeUndefined()
  })
})
