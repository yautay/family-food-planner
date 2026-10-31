import type { Locator } from '@playwright/test'

/**
 * `fill` exposes passwords in report titles; evaluate arguments avoid that.
 * Callers must also disable trace, which records arguments and login bodies.
 */
export async function fillSecretPassword(locator: Locator, value: string): Promise<void> {
  try {
    await locator.waitFor({ state: 'visible' })
    const filled = await locator.evaluate((element, password) => {
      try {
        const window = element.ownerDocument.defaultView
        if (
          !window ||
          !(element instanceof window.HTMLInputElement) ||
          element.type !== 'password' ||
          element.disabled ||
          element.readOnly
        ) {
          return false
        }
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype,
          'value',
        )?.set
        if (!setter) return false
        setter.call(element, password)
        element.dispatchEvent(new window.Event('input', { bubbles: true }))
        return true
      } catch {
        return false
      }
    }, value)
    if (!filled) throw new Error('Nie udało się uzupełnić pola hasła.')
  } catch {
    // Oryginalny błąd ani cause nie mogą przenieść hasła do raportu.
    throw new Error('Nie udało się uzupełnić pola hasła.')
  }
}
