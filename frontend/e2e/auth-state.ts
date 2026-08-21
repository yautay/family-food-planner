import path from 'node:path'
import { fileURLToPath } from 'node:url'

/**
 * Ścieżka pliku ze stanem sesji E2E (ciasteczka po jednorazowym logowaniu).
 *
 * Osobny moduł, bo korzystają z niej trzy strony: `playwright.config.ts`
 * (ustawia `storageState` projektu), `auth.setup.ts` (zapisuje) i `.gitignore`
 * (plik NIE trafia do repo — zawiera token sesji, 07_SECURITY §7).
 *
 * `fileURLToPath(import.meta.url)`, a nie `__dirname`: pakiet jest ESM-em, więc
 * `__dirname` nie istnieje i Playwright wysypuje się już na ładowaniu configu.
 */
const HERE = path.dirname(fileURLToPath(import.meta.url))

export const AUTH_STATE_FILE = path.join(HERE, '.auth', 'admin.json')

/**
 * Pusty stan dla specy, które testują SAMO logowanie i muszą startować bez sesji.
 *
 * Bez `as const` z rozmysłem: Playwright oczekuje MUTOWALNEGO `StorageState`,
 * a `as const` czyni tablice `readonly` i `test.use()` odrzuca taki typ.
 */
export const EMPTY_STATE: { cookies: []; origins: [] } = { cookies: [], origins: [] }
