/** Epoka lokalnych odpowiedzi; nie jest tokenem ani uwierzytelnieniem. */
let generation = 0
const listeners = new Set<() => void>()

export function captureSessionGeneration(): number {
  return generation
}

export function isSessionGenerationCurrent(ticket: number): boolean {
  return ticket === generation
}

export function advanceSessionGeneration(): void {
  generation += 1
  for (const listener of listeners) listener()
}

export function subscribeSessionGeneration(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

export class StaleSessionResponseError extends Error {
  constructor() {
    super('Sesja zmieniła się w trakcie żądania.')
    this.name = 'StaleSessionResponseError'
  }
}
