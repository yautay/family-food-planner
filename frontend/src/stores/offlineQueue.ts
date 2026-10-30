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
  queueKey,
  readQueue,
  targetKey,
  type QueuedCheck,
  type QueueTarget,
} from '@/lib/offline/db'
import { sendQueued } from '@/lib/offline/sync'

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

  const listeners = new Map<string, Set<SyncListener>>()
  let started = false
  let retryTimer: ReturnType<typeof setTimeout> | undefined
  let flushRequested = false

  const pendingCount = computed(() => pending.value.length)
  const isOffline = computed(() => !online.value)

  function pendingFor(target: QueueTarget): number {
    const prefix = `${targetKey(target)}#`
    return pending.value.filter((entry) => entry.key.startsWith(prefix)).length
  }

  function isGone(target: QueueTarget): boolean {
    return gone.value.includes(targetKey(target))
  }

  async function refresh(): Promise<void> {
    pending.value = await readQueue()
  }

  /**
   * Zapisz odhaczenie do wysłania później.
   *
   * `checkedAt` liczymy TERAZ, nie przy wysyłce: to moment decyzji użytkownika,
   * a nie moment, w którym telefon złapał zasięg. Cała wartość LWW z ADR-009
   * siedzi w tej różnicy.
   */
  async function enqueue(target: QueueTarget, itemId: number, checked: boolean): Promise<void> {
    await enqueueCheck(target, itemId, checked, nowWithSkew())
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
    await deleteQueued(queueKey(target, itemId))
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

  function scheduleRetry(): void {
    if (retryTimer !== undefined || typeof setTimeout === 'undefined') {
      return
    }
    retryTimer = setTimeout(() => {
      retryTimer = undefined
      void flush()
    }, RETRY_DELAY_MS)
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
    try {
      for (const entry of await readQueue()) {
        if (dead.has(targetKey(entry.target))) {
          continue
        }
        const outcome = await sendQueued(entry)
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
        await deleteQueuedIfUnchanged(entry)
        const key = targetKey(entry.target)
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
          sent += 1
          touched.add(key)
        }
      }
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
