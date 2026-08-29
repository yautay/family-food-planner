/**
 * Zapis bloba na dysk użytkownika — jedno miejsce dla całej aplikacji.
 *
 * Wydzielone z komponentu, bo dotyka `document` i `URL.createObjectURL`: dzięki
 * temu strona daje się testować w vitest bez udawania DOM-u, a zwolnienie
 * obiektu URL (wyciek pamięci, gdy się o nim zapomni) jest tu, a nie w każdym
 * miejscu, które coś pobiera.
 */

export function saveBlob(blob: Blob, filename: string): void {
  if (typeof document === 'undefined') {
    return
  }
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.append(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
