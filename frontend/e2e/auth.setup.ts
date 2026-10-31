import { expect, test as setup } from '@playwright/test'

import { AUTH_STATE_FILE } from './auth-state.js'
import { purgeE2eLeftovers } from './cleanup.js'
import { reserveLoginAttempt } from './login-budget.js'
import { fillSecretPassword } from './secret-password.js'

// Evaluate arguments and login bodies are sensitive even without Fill titles.
setup.use({ trace: 'off' })

/**
 * Logowanie RAZ na cały przebieg E2E — projekt `setup` z `playwright.config.ts`.
 *
 * Powód jest twardy, nie estetyczny: `/auth/login` ma limit **5 żądań na minutę
 * na IP** (`LOGIN_RATE_LIMIT` w `accounts/router.py`, 07_SECURITY §2), a suita
 * logowała się osiem razy na sześciu workerach. Po piątym logowaniu leciało 429
 * i specy padały LOSOWO — za każdym przebiegiem inne, zawsze na
 * `toHaveURL(/plan-dnia/)`. Wygląda to jak flake, a jest zderzeniem testów
 * z realnym zabezpieczeniem aplikacji.
 *
 * Tu logujemy się jeden raz, zapisujemy ciasteczka sesji do pliku, a pozostałe
 * specy startują już zalogowane (`storageState` w konfiguracji). Limit zostaje
 * nietknięty — testujemy tę samą konfigurację, co produkcja.
 *
 * Specy, które testują SAMO logowanie (render formularza, przekierowanie bez
 * sesji, błędne hasło, pełny cykl login→wylogowanie), jawnie zerują
 * `storageState` i wykonują własne logowania — patrz `smoke.spec.ts`.
 */
const email = process.env.E2E_ADMIN_EMAIL ?? ''
const password = process.env.E2E_ADMIN_PASSWORD ?? ''

setup('logowanie raz na przebieg (zapis storageState)', async ({ page, baseURL }, testInfo) => {
  if (!email || !password) {
    throw new Error(
      'Brak E2E_ADMIN_EMAIL / E2E_ADMIN_PASSWORD w .env. Utwórz konto komendą ' +
        '`task create-admin` i wpisz te same dane do .env (patrz .env.example).',
    )
  }

  await page.goto('/login')
  await page.getByTestId('login-email').fill(email)
  await fillSecretPassword(page.getByTestId('login-password'), password)
  await reserveLoginAttempt(baseURL, testInfo)
  await page.getByTestId('login-submit').click()

  // Czekamy na skutek logowania, nie na samo kliknięcie — inaczej zapisalibyśmy
  // stan przed ustawieniem ciasteczka sesji i wszystkie specy byłyby wylogowane.
  await expect(page).toHaveURL(/\/plan-dnia/)
  await expect(page.getByTestId('plan-dnia-page')).toBeVisible()

  await page.context().storageState({ path: AUTH_STATE_FILE })

  // Ten projekt jest zależnością wszystkich pozostałych, więc jest JEDYNYM
  // miejscem, w którym można bezpiecznie skasować wszystkie dane podpisane
  // „E2E" — żaden spec jeszcze nie działa. Bez tego przebieg dziedziczy śmieci
  // z poprzednich konwencji nazw i pada na ukrytej opcji „+ Dodaj"
  // (szukajka trigramowa znajduje stary przepis) — ustalenie R2, dług U15.
  // `baseURL` jedzie jako argument, bo purge kasuje szeroko i ma bramkę na
  // localhost — patrz `purgeE2eLeftovers`.
  await purgeE2eLeftovers(page.request, baseURL)
})
