/**
 * Kolejka odhaczeń offline (Pinia = stan UI, ADR-007; kontrakt: ADR-009).
 *
 * Dlaczego to jest Pinia, a nie TanStack Query: kolejka NIE JEST stanem serwera.
 * To lokalna lista intencji użytkownika, których serwer jeszcze nie widział —
 * ma własny cykl życia (przeżywa reload dzięki IndexedDB) i własne zdarzenia
 * (`online`, powrót do karty). Kopiowanie tu odpowiedzi API byłoby złamaniem
 * ADR-007; store trzyma wyłącznie to, czego serwer nie zna.
 *
 * Cztery zasady, z których wynika reszta pliku:
 *
 * 1. **IndexedDB jest źródłem prawdy, `pending` tylko jego odbiciem dla UI.**
 *    Licznik w bannerze musi przeżyć zamknięcie karty, a ref w pamięci nie
 *    przeżywa nawet odświeżenia.
 * 2. **Flush jest SEKWENCYJNY i zatrzymuje się na pierwszym `retry`.** Limit
 *    60/min/IP jest wspólny dla całej ścieżki publicznej (ustalenie R3), więc
 *    równoległy wystrzał kolejki po odzyskaniu sieci sam by w niego wpadł.
 *    Zatrzymanie zachowuje też KOLEJNOŚĆ wysyłki.
 * 3. **410 nie jest błędem do ponowienia, tylko końcem tej listy.** Kolejka dla
 *    tego adresata idzie do kosza, a strona pokazuje ekran „wygasła" (AC 6).
 *    Bez tego mielibyśmy pętlę retry na martwym tokenie.
 * 4. **Znacznik `checked_at` powstaje w momencie KLIKNIĘCIA**, a nie wysyłki,
 *    i w zegarze serwera (`clock.ts`) — na tym stoi LWW.
 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { nowWithSkew } from '@/lib/offline/clock'
import {
  clearQueueFor,
  bumpAttempts,
  deleteQueued,
  deleteQueuedIfUnchanged,
  deleteSnapshot,
  enqueueCheck,
  OfflineStorageError,
  isQueueTargetCurrent,
  queueKey,
  readQueue,
  rejectQueuedIfUnchanged,
  targetKey,
  type QueuedCheck,
  type QueueTarget,
} from '@/lib/offline/db'
import { sendQueued } from '@/lib/offline/sync'
import {
  isPrivateOfflineScopeConfirmed,
  subscribePrivateOfflineScope,
} from '@/lib/offline/privateSession'
import { useAuthStore } from './auth'
import { ApiError } from '@/api/client'

/** Odstęp przed automatycznym ponowieniem po 429/5xx (backoff, ustalenie R3 pkt 2). */
const RETRY_DELAY_MS = 15_000

type SyncListener = () => void

export const useOfflineQueueStore = defineStore('offlineQueue', () => {
  /** Odbicie kolejki z IndexedDB — wyłącznie do licznika i testów. */
  const pending = ref<QueuedCheck[]>([])
  /** `navigator.onLine` bywa optymistyczny (Wi-Fi bez internetu) — patrz `markOffline`. */
  const online = ref(typeof navigator === 'undefined' ? true : navigator.onLine)
  const flushing = ref(false)
  /** Adresaci, dla których serwer powiedział 404/410 — ekran „lista wygasła". */
  const gone = ref<string[]>([])
  // Odmowa pozostaje widoczna także po sukcesie INNEJ pozycji tej listy.
  // Nie przechowujemy tu danych serwera, tylko wynik lokalnej intencji.
  const failures = ref<Record<string, true>>({})
  const storageFailed = ref(false)
  // Numery są lokalnymi wersjami uzgodnienia, nie danymi serwera. Samo
  // opróżnienie kolejki (200 może przegrać LWW) nie potwierdza checkboxów.
  const reconciliation = ref<Record<string, number>>({})
  const reconciled = ref<Record<string, number>>({})

  const listeners = new Map<string, Set<SyncListener>>()
  let started = false
  let retryTimer: ReturnType<typeof setTimeout> | undefined
  let flushRequested = false

  const pendingCount = computed(() => pending.value.length)
  const isOffline = computed(() => !online.value)

  function pendingFor(target: QueueTarget | null): number {
    if (target === null || !isQueueTargetCurrent(target)) return 0
    const prefix = `${targetKey(target)}#`
    return pending.value.filter((entry) => entry.key.startsWith(prefix)).length
  }

  function isGone(target: QueueTarget | null): boolean {
    if (target === null || !isQueueTargetCurrent(target)) return false
    return gone.value.includes(targetKey(target))
  }

  function reconciliationVersion(target: QueueTarget | null): number {
    if (target === null || !isQueueTargetCurrent(target)) return 0
    return reconciliation.value[targetKey(target)] ?? 0
  }

  function needsReconciliation(target: QueueTarget | null): boolean {
    if (target === null || !isQueueTargetCurrent(target)) return false
    return reconciliationVersion(target) !== (reconciled.value[targetKey(target)] ?? 0)
  }

  function requireReconciliation(target: QueueTarget): void {
    const key = targetKey(target)
    reconciliation.value = { ...reconciliation.value, [key]: reconciliationVersion(target) + 1 }
  }

  /** Wołane przez widok dopiero po ZASTOSOWANYM, udanym GET tej wersji. */
  function confirmReconciled(target: QueueTarget, version: number): void {
    if (
      isQueueTargetCurrent(target) &&
      version === reconciliationVersion(target) &&
      pendingFor(target) === 0
    ) {
      reconciled.value = { ...reconciled.value, [targetKey(target)]: version }
    }
  }

  function errorFor(target: QueueTarget | null): string | null {
    if (target === null || !isQueueTargetCurrent(target)) return null
    if (storageFailed.value) return new OfflineStorageError().message
    const prefix = `${targetKey(target)}#`
    return Object.keys(failures.value).some((key) => key.startsWith(prefix))
      ? 'Nie udało się zapisać części odhaczeń. Sprawdź listę i ponów te zmiany.'
      : null
  }

  function clearFailure(key: string): void {
    const next = { ...failures.value }
    delete next[key]
    failures.value = next
  }

  async function refresh(): Promise<void> {
    try {
      pending.value = (await readQueue()).filter((entry) => isQueueTargetCurrent(entry.target))
      storageFailed.value = false
    } catch {
      // Awaria odczytu nie jest pustą kolejką. Zachowujemy znane intencje
      // i jawny błąd, więc pending=0 nie może udawać potwierdzonego zapisu.
      storageFailed.value = true
    }
  }

  /**
   * Zapisz odhaczenie do wysłania później.
   *
   * `checkedAt` liczymy TERAZ, nie przy wysyłce: to moment decyzji użytkownika,
   * a nie moment, w którym telefon złapał zasięg. Cała wartość LWW z ADR-009
   * siedzi w tej różnicy.
   */
  async function enqueue(
    target: QueueTarget,
    itemId: number,
    checked: boolean,
    snapshot?: unknown,
  ): Promise<void> {
    await enqueueCheck(target, itemId, checked, nowWithSkew(), snapshot)
    await refresh()
    if (online.value && retryTimer === undefined) {
      // Powrót online mógł już odczytać migawkę sprzed tego zapisu IndexedDB.
      // Zapamiętaj pobudkę także wtedy, gdy poprzedni flush jeszcze trwa.
      flushRequested = true
      void flush()
    }
  }

  /**
   * Usuń wpis dla pozycji, którą właśnie udało się zapisać online.
   *
   * Bez tego stary wpis z kolejki poszedłby na serwer po odzyskaniu sieci
   * i (jako starszy) zostałby odrzucony przez LWW — działałoby, ale byłoby to
   * żądanie zużywające limit 60/min bez żadnego powodu.
   */
  async function forget(target: QueueTarget, itemId: number): Promise<void> {
    if (!isQueueTargetCurrent(target)) return
    await deleteQueued(queueKey(target, itemId))
    clearFailure(queueKey(target, itemId))
    await refresh()
  }

  /** Zarejestruj reakcję na udaną synchronizację tej listy (zwykle `invalidateQueries`). */
  function subscribeToSync(target: QueueTarget, listener: SyncListener): () => void {
    const key = targetKey(target)
    const set = listeners.get(key) ?? new Set<SyncListener>()
    set.add(listener)
    listeners.set(key, set)
    return () => {
      set.delete(listener)
      if (set.size === 0) {
        listeners.delete(key)
      }
    }
  }

  function notify(key: string): void {
    for (const listener of listeners.get(key) ?? []) {
      listener()
    }
  }

  async function markGone(target: QueueTarget): Promise<void> {
    if (!isQueueTargetCurrent(target)) return
    const key = targetKey(target)
    if (gone.value.includes(key)) return
    gone.value = [...new Set([...gone.value, key])]
    await clearQueueFor(target)
    await deleteSnapshot(key)
    await refresh()
    if (isQueueTargetCurrent(target)) notify(key)
  }

  function scheduleRetry(): void {
    if (retryTimer !== undefined || typeof setTimeout === 'undefined') {
      return
    }
    retryTimer = setTimeout(() => {
      retryTimer = undefined
      void flush()
    }, RETRY_DELAY_MS)
  }

  function privateReplayAllowed(): boolean {
    return typeof window === 'undefined' || !window.location.pathname.startsWith('/l/')
  }

  /**
   * Wyślij kolejkę po kolei. Zwraca liczbę wpisów, które trafiły na serwer.
   *
   * Zatrzymanie na pierwszym `retry` jest celowe: kolejne wpisy i tak trafiłyby
   * w ten sam brak sieci albo ten sam rate limit, a przy okazji straciłyby
   * kolejność.
   */
  async function flush(): Promise<number> {
    if (flushing.value) {
      return 0
    }
    flushRequested = false
    flushing.value = true
    let sent = 0
    const touched = new Set<string>()
    // Adresaci, którzy w TYM przebiegu okazali się martwi (410). Iterujemy po
    // migawce kolejki, więc bez tego zbioru kolejne wpisy tej samej listy
    // poleciałyby na serwer mimo `clearQueueFor` — czyli dokładnie ta pętla
    // żądań na wygasłym tokenie, której zabrania AC 6.
    const dead = new Set<string>()
    let validatedScope: string | null = null
    try {
      for (const entry of await readQueue()) {
        if (!isQueueTargetCurrent(entry.target)) continue
        if (entry.target.kind === 'list') {
          // Publiczny link nie uruchamia /auth/me przez cudze zaległe wpisy.
          if (!privateReplayAllowed()) continue
          if (validatedScope !== entry.target.scope) {
            const auth = useAuthStore()
            try {
              await auth.ensureLoaded(true)
            } catch (error) {
              if (error instanceof ApiError && error.status === 0) online.value = false
              scheduleRetry()
              break
            }
            if (
              !isQueueTargetCurrent(entry.target) ||
              !isPrivateOfflineScopeConfirmed(entry.target.scope)
            ) {
              if (auth.offlineSession) {
                online.value = false
                scheduleRetry()
                break
              }
              continue
            }
            validatedScope = entry.target.scope
          }
          if (
            !privateReplayAllowed() ||
            !isQueueTargetCurrent(entry.target) ||
            !isPrivateOfflineScopeConfirmed(entry.target.scope)
          )
            continue
        }
        if (dead.has(targetKey(entry.target))) {
          continue
        }
        const outcome = await sendQueued(entry)
        if (outcome === 'session-changed') {
          // Ten sam namespace może dostać nową generację (np. zmianę roli).
          // Stara odpowiedź nie jest odmową ani potwierdzeniem intencji.
          // Następny przebieg ponownie wykona rzeczywiste /me przed PATCH.
          scheduleRetry()
          break
        }
        if (
          !isQueueTargetCurrent(entry.target) ||
          (entry.target.kind === 'list' && !isPrivateOfflineScopeConfirmed(entry.target.scope))
        )
          continue
        if (outcome === 'offline') {
          // Żądanie nie doszło do serwera. Banner ma pokazać PRAWDĘ, a nie
          // deklarację `navigator.onLine` (sklepowe Wi-Fi bywa „online" i nie
          // przepuszcza ruchu). Licznika prób NIE ruszamy: brak sieci to nie
          // odmowa serwera, a kwadrans bez zasięgu nie może kasować zakupów.
          online.value = false
          scheduleRetry()
          break
        }
        if (outcome === 'retry') {
          // Serwer ODPOWIEDZIAŁ (429 albo 5xx) — jesteśmy online, tylko musimy
          // odczekać. Tu licznik prób ma sens: chroni przed wpisem, którego
          // serwer nie chce przyjąć nigdy, a który blokowałby całą kolejkę.
          await bumpAttempts(entry)
          scheduleRetry()
          break
        }
        const key = targetKey(entry.target)
        if (outcome === 'dropped') {
          // Stara odmowa nie jest błędem NOWEJ intencji pod tym samym kluczem.
          // Snapshot i wpis znikają atomowo dopiero po porównaniu wersji IDB.
          if (await rejectQueuedIfUnchanged(entry)) {
            requireReconciliation(entry.target)
            failures.value = { ...failures.value, [entry.key]: true }
            touched.add(key)
          }
          continue
        }
        if (outcome === 'sent') {
          // Powrót do karty może wysłać kolejkę bez zdarzenia `online`.
          // Dopiero udany PATCH bieżącej sesji/scope potwierdza transport;
          // samo /me nie wystarcza, bo późniejszy PATCH mógł stracić sieć.
          online.value = true
          requireReconciliation(entry.target)
        }
        await deleteQueuedIfUnchanged(entry)
        if (outcome === 'gone') {
          dead.add(key)
          await clearQueueFor(entry.target)
          await deleteSnapshot(key)
          if (!gone.value.includes(key)) {
            gone.value = [...gone.value, key]
          }
          notify(key)
          continue
        }
        if (outcome === 'sent') {
          clearFailure(entry.key)
          sent += 1
          touched.add(key)
        }
      }
    } catch {
      storageFailed.value = true
    } finally {
      await refresh()
      flushing.value = false
      if (flushRequested && online.value && retryTimer === undefined) {
        void flush()
      }
    }
    for (const key of touched) {
      notify(key)
    }
    return sent
  }

  /** Sieć wróciła: przeglądarka mówi „online", więc próbujemy jeszcze raz. */
  function markOnline(): void {
    online.value = true
    void flush()
  }

  function markOffline(): void {
    online.value = false
  }

  /**
   * Podłącz nasłuch zdarzeń przeglądarki. Wołane RAZ, z `main.ts`.
   *
   * `visibilitychange` zamiast Background Sync API: ADR-009 mówi wprost, że
   * flush przy powrocie do aplikacji wystarcza, a Background Sync nie działa
   * na iOS i wymagałby osobnej ścieżki kodu w service workerze.
   */
  function start(): void {
    if (started || typeof window === 'undefined') {
      return
    }
    started = true
    subscribePrivateOfflineScope(() => {
      pending.value = pending.value.filter((entry) => isQueueTargetCurrent(entry.target))
      void refresh()
    })
    window.addEventListener('online', markOnline)
    window.addEventListener('offline', markOffline)
    window.addEventListener('focus', () => void flush())
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') {
        void flush()
      }
    })
    void refresh().then(() => {
      if (online.value) {
        void flush()
      }
    })
  }

  return {
    pending,
    pendingCount,
    online,
    isOffline,
    flushing,
    gone,
    pendingFor,
    isGone,
    markGone,
    errorFor,
    reconciliationVersion,
    needsReconciliation,
    confirmReconciled,
    refresh,
    enqueue,
    forget,
    subscribeToSync,
    flush,
    markOnline,
    markOffline,
    start,
  }
})
