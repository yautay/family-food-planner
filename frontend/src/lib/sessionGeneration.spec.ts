import { describe, expect, it, vi } from 'vitest'

import {
  advanceSessionGeneration,
  captureSessionGeneration,
  isSessionGenerationCurrent,
  subscribeSessionGeneration,
} from './sessionGeneration'

describe('generacja odpowiedzi sesji', () => {
  it('unieważnia poprzedni ticket i synchronicznie powiadamia poddrzewo tylko do unsubscribe', () => {
    const before = captureSessionGeneration()
    const listener = vi.fn()
    const unsubscribe = subscribeSessionGeneration(listener)
    advanceSessionGeneration()
    expect(isSessionGenerationCurrent(before)).toBe(false)
    expect(isSessionGenerationCurrent(captureSessionGeneration())).toBe(true)
    expect(listener).toHaveBeenCalledOnce()
    unsubscribe()
    advanceSessionGeneration()
    expect(listener).toHaveBeenCalledOnce()
  })
})
