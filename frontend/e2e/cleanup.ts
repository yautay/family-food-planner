import type { APIRequestContext } from '@playwright/test'

/**
 * Sprzątanie po specach E2E — izolacja danych między przebiegami (08_TESTING §5).
 *
 * Problem, który to rozwiązuje (ustalenie R2, dług U15): specy pracują na
 * JEDNEJ bazie deweloperskiej i na jednym koncie, a asercje typu „dzień jest
 * pusty" albo „szukajka nie znajduje przepisu, więc pokazuje «+ Dodaj»" są
 * prawdziwe tylko na czystym stanie. Kolejny przebieg padał na danych
 * poprzedniego:
 *
 * - `plan-empty` nie był już pusty (posiłki z poprzedniego przebiegu),
 * - `week-day-…` zawierał „Obiad E2E" zamiast „Brak posiłków",
 * - wyszukiwarka TRIGRAMOWA znajdowała „Zupa E2E <stary stamp>" przy szukaniu
 *   „Zupa E2E <nowy stamp>", więc `canCreate` w `RecipePicker` było `false`
 *   i inline create stawał się nieosiągalny.
 *
 * Łatanie asercji leczyłoby objawy. Sprzątamy więc PRZEZ API (te same
 * endpointy, których używa aplikacja), w `afterAll`, który wykonuje się także
 * po nieudanym teście — inaczej pierwszy fail zatruwałby wszystkie kolejne
 * przebiegi.
 *
 * Uwaga na kolejność: `week_cycles` blokuje usunięcie szablonu tygodnia (409
 * `used_in`), a pozycje planu blokują usunięcie przepisu i produktu (FK
 * RESTRICT, ADR-012). Dlatego `cleanupE2eData` idzie od najbardziej zależnych
 * encji do najmniej: cykle → szablony → posiłki planu → przepisy → spiżarnia →
 * **produkty sklepowe → sklepy** → produkty kanoniczne. Dwa ostatnie ogniwa
 * doszły w B09: wariant retail trzyma produkt kanoniczny (FK RESTRICT), a sklep
 * jest trzymany przez wariant (409 `used_in`), więc odwrotna kolejność zostawia
 * śmieci i blokuje kolejny przebieg.
 */
const API = '/api/v1'
const CSRF_COOKIE = 'csrf_token'
const CSRF_HEADER = 'X-CSRF-Token'

/** Górny limit list — sprzątanie ma być tanie, nie kompletne dla całej bazy. */
const PAGE = 200

interface NamedRow {
  id: number
  name: string
}

/**
 * Nagłówek CSRF przepisany z cookie zapisanego przez `auth.setup.ts`.
 *
 * Backend wymaga double-submit dla każdej mutacji (07_SECURITY §3), więc bez
 * tego nagłówka sprzątanie dostawałoby 403 i cicho nic nie robiło.
 */
async function csrfHeaders(request: APIRequestContext): Promise<Record<string, string>> {
  const state = await request.storageState()
  const token = state.cookies.find((cookie) => cookie.name === CSRF_COOKIE)?.value
  if (!token) {
    throw new Error(
      `Brak cookie ${CSRF_COOKIE} w stanie sesji — sprzątanie E2E wymaga zalogowanego kontekstu.`,
    )
  }
  return { [CSRF_HEADER]: token }
}

/**
 * Usuwa zasób, tolerując 404 i 409.
 *
 * Sprzątanie NIE MOŻE wysadzić przebiegu: encja może już nie istnieć (test ją
 * usunął), a 409 znaczy „coś jeszcze ją trzyma" — wtedy raportujemy do konsoli
 * i idziemy dalej, bo alternatywą jest czerwony przebieg z powodu porządków.
 */
async function tryDelete(
  request: APIRequestContext,
  url: string,
  headers: Record<string, string>,
): Promise<void> {
  const response = await request.delete(url, { headers })
  if (!response.ok() && response.status() !== 404) {
    console.warn(`[e2e cleanup] DELETE ${url} → ${response.status()} ${await response.text()}`)
  }
}

async function listNamed(
  request: APIRequestContext,
  url: string,
  matches: (name: string) => boolean,
): Promise<NamedRow[]> {
  const response = await request.get(url)
  if (!response.ok()) {
    console.warn(`[e2e cleanup] GET ${url} → ${response.status()}`)
    return []
  }
  const body = (await response.json()) as { items?: NamedRow[] }
  return (body.items ?? []).filter((item) => typeof item.name === 'string' && matches(item.name))
}

/** Dopasowanie po prefiksie nazwy — domyślny tryb sprzątania per spec. */
function byPrefix(prefix: string): (name: string) => boolean {
  return (name) => name.startsWith(prefix)
}

/**
 * Znacznik czasu `Date.now()` w nazwie — 13 cyfr pod rząd.
 *
 * KAŻDA encja tworzona przez specy jest podpisana `Date.now()`, żeby nazwa
 * była unikalna w skali przebiegu. To najpewniejszy ślad danych testowych,
 * pewniejszy niż samo „E2E": stare specy nazywały szablony i cykle
 * „Szablon dnia 1787303350577" — bez słowa „E2E", więc filtr po samym „E2E"
 * ich nie widział, a one blokowały usunięcie przepisu (409 `used_in`).
 * Człowiek nie wpisuje trzynastocyfrowej liczby w nazwę przepisu.
 */
const STAMPED = /\d{13}/

/** Dopasowanie „cokolwiek podpisane E2E" — używane WYŁĄCZNIE w `setup` (bez równoległości). */
function anyE2e(name: string): boolean {
  return name.includes('E2E') || STAMPED.test(name)
}

/** Kasuje posiłki (a kaskadą pozycje i rozkłady) we wskazanych datach. */
export async function clearPlanDays(
  request: APIRequestContext,
  dates: readonly string[],
): Promise<void> {
  if (dates.length === 0) {
    return
  }
  const headers = await csrfHeaders(request)
  const sorted = [...dates].sort()
  const response = await request.get(
    `${API}/plan/days?from=${sorted[0]}&to=${sorted[sorted.length - 1]}`,
  )
  if (!response.ok()) {
    console.warn(`[e2e cleanup] GET /plan/days → ${response.status()}`)
    return
  }
  const body = (await response.json()) as { items: { day: string; meals: { id: number }[] }[] }
  for (const day of body.items) {
    if (!dates.includes(day.day)) {
      continue
    }
    for (const meal of day.meals) {
      await tryDelete(request, `${API}/plan/meals/${meal.id}`, headers)
    }
  }
}

/** Kasuje cykle, szablony tygodnia i szablony dnia o nazwie z danym prefiksem. */
export async function clearTemplatesAndCycles(
  request: APIRequestContext,
  prefix: string,
): Promise<void> {
  const headers = await csrfHeaders(request)
  await deleteTemplatesAndCycles(request, headers, byPrefix(prefix))
}

async function deleteTemplatesAndCycles(
  request: APIRequestContext,
  headers: Record<string, string>,
  matches: (name: string) => boolean,
): Promise<void> {
  for (const cycle of await listNamed(request, `${API}/cycles`, matches)) {
    await tryDelete(request, `${API}/cycles/${cycle.id}`, headers)
  }
  for (const template of await listNamed(request, `${API}/templates/weeks`, matches)) {
    await tryDelete(request, `${API}/templates/weeks/${template.id}`, headers)
  }
  for (const template of await listNamed(request, `${API}/templates/days`, matches)) {
    await tryDelete(request, `${API}/templates/days/${template.id}`, headers)
  }
}

/**
 * Kasuje pozycje spiżarni wskazujące produkty o nazwie z danym prefiksem.
 *
 * MUSI iść przed `clearProducts`: `pantry_items.product_id` ma FK RESTRICT
 * (ADR-012), więc pozostawiona pozycja blokuje usunięcie produktu 409-ką
 * i cały ślad po specu zostaje w bazie.
 */
export async function clearPantry(request: APIRequestContext, prefix: string): Promise<void> {
  const headers = await csrfHeaders(request)
  await deletePantryItems(request, headers, byPrefix(prefix))
}

async function deletePantryItems(
  request: APIRequestContext,
  headers: Record<string, string>,
  matches: (name: string) => boolean,
): Promise<void> {
  const response = await request.get(`${API}/pantry?limit=${PAGE}&offset=0`)
  if (!response.ok()) {
    console.warn(`[e2e cleanup] GET /pantry → ${response.status()}`)
    return
  }
  // Pozycja spiżarni nie ma własnej nazwy — identyfikuje ją nazwa produktu.
  const body = (await response.json()) as { items?: { id: number; product_name: string | null }[] }
  for (const row of body.items ?? []) {
    if (row.product_name !== null && matches(row.product_name)) {
      await tryDelete(request, `${API}/pantry/${row.id}`, headers)
    }
  }
}

/**
 * Kasuje przepisy o nazwie z danym prefiksem.
 *
 * To jest sedno naprawy inline create: dopóki w bazie leży „Zupa E2E 123",
 * szukajka trigramowa znajduje ją dla frazy „Zupa E2E 456" i opcja „+ Dodaj"
 * się nie pokazuje.
 */
export async function clearRecipes(request: APIRequestContext, prefix: string): Promise<void> {
  const headers = await csrfHeaders(request)
  // Bez `?q=` z rozmysłem: szukajka jest TRIGRAMOWA, więc dopasowanie prefiksu
  // zależy od progu podobieństwa, a sprzątanie musi być deterministyczne.
  // Filtrujemy po prefiksie w JS na pełnej (krótkiej) liście bazy dev.
  await deleteRecipes(request, headers, byPrefix(prefix))
}

async function deleteRecipes(
  request: APIRequestContext,
  headers: Record<string, string>,
  matches: (name: string) => boolean,
): Promise<void> {
  const rows = await listNamed(
    request,
    `${API}/recipes?limit=${PAGE}&offset=0&include_archived=true`,
    matches,
  )
  for (const recipe of rows) {
    await tryDelete(request, `${API}/recipes/${recipe.id}`, headers)
  }
}

/**
 * Kasuje produkty sklepowe o nazwie z danym prefiksem.
 *
 * MUSI iść przed `clearProducts` i `clearStores`: `retail_products` trzyma
 * produkt kanoniczny FK RESTRICT, a sklep — blokadą 409 z listą użyć (B09).
 */
export async function clearRetailProducts(
  request: APIRequestContext,
  prefix: string,
): Promise<void> {
  const headers = await csrfHeaders(request)
  await deleteRetailProducts(request, headers, byPrefix(prefix))
}

async function deleteRetailProducts(
  request: APIRequestContext,
  headers: Record<string, string>,
  matches: (name: string) => boolean,
): Promise<void> {
  const rows = await listNamed(
    request,
    `${API}/retail-products?limit=${PAGE}&offset=0&include_archived=true`,
    matches,
  )
  for (const retail of rows) {
    await tryDelete(request, `${API}/retail-products/${retail.id}`, headers)
  }
}

/** Kasuje sklepy o nazwie z danym prefiksem (po wariantach retail!). */
export async function clearStores(request: APIRequestContext, prefix: string): Promise<void> {
  const headers = await csrfHeaders(request)
  await deleteStores(request, headers, byPrefix(prefix))
}

async function deleteStores(
  request: APIRequestContext,
  headers: Record<string, string>,
  matches: (name: string) => boolean,
): Promise<void> {
  const rows = await listNamed(request, `${API}/stores?include_archived=true`, matches)
  for (const store of rows) {
    await tryDelete(request, `${API}/stores/${store.id}`, headers)
  }
}

/**
 * Kasuje listy zakupowe z OKNA DAT E2E (lata 2030+).
 *
 * Listy nie mają prefiksu nazwy — finalizacja nadaje im nazwę z zakresu dat
 * („Zakupy 07.03-13.03.2033"), więc identyfikuje je ROK. To ta sama konwencja,
 * co przy planie: daty testowe leżą w latach 2030+, a „dziś" zostaje dla
 * ręcznego klikania (08_TESTING §3.1 pkt 4).
 *
 * MUSI iść przed `clearRetailProducts` i `clearProducts`: pozycje listy trzymają
 * produkt kanoniczny i wariant sklepowy FK RESTRICT (ADR-012), więc dopóki
 * lista istnieje, produktu nie da się usunąć. Do BATCH_11 endpointu usuwania
 * list nie było i to właśnie dlatego specy zakupowe pracują na produktach seedu.
 */
export async function clearShoppingLists(request: APIRequestContext): Promise<void> {
  const headers = await csrfHeaders(request)
  await deleteShoppingLists(request, headers)
}

/** Nazwa listy z finalizacji: „Zakupy DD.MM-DD.MM.RRRR". */
const LIST_NAME_PATTERN = /^Zakupy \d{2}\.\d{2}-\d{2}\.\d{2}\.(\d{4})$/

/**
 * Czy lista pochodzi z okna dat zarezerwowanego dla E2E (lata 2030+).
 *
 * Rok czytamy z NAZWY, bo listy nie mają prefiksu — finalizacja nadaje nazwę
 * z zakresu dat. To ta sama konwencja co przy planie (08_TESTING §3.1 pkt 4),
 * więc lista ręcznie wygenerowana z dzisiejszego planu nigdy tu nie wpadnie.
 */
function isE2eListName(name: string): boolean {
  const match = LIST_NAME_PATTERN.exec(name)
  const year = match === null ? null : Number(match[1])
  return year !== null && E2E_YEARS.some((allowed) => allowed === year)
}

async function deleteShoppingLists(
  request: APIRequestContext,
  headers: Record<string, string>,
): Promise<void> {
  const rows = await listNamed(
    request,
    `${API}/shopping/lists?limit=${PAGE}&offset=0`,
    isE2eListName,
  )
  for (const list of rows) {
    await tryDelete(request, `${API}/shopping/lists/${list.id}`, headers)
  }
}

/** Kasuje produkty kanoniczne o nazwie z danym prefiksem (konto E2E jest ADMIN-em). */
export async function clearProducts(request: APIRequestContext, prefix: string): Promise<void> {
  const headers = await csrfHeaders(request)
  await deleteProducts(request, headers, byPrefix(prefix))
}

async function deleteProducts(
  request: APIRequestContext,
  headers: Record<string, string>,
  matches: (name: string) => boolean,
): Promise<void> {
  const rows = await listNamed(
    request,
    `${API}/products?limit=${PAGE}&offset=0&include_archived=true`,
    matches,
  )
  for (const product of rows) {
    await tryDelete(request, `${API}/products/${product.id}`, headers)
  }
}

/**
 * Pełne sprzątanie po specu — kolejność wymuszona blokadami usuwania.
 *
 * `namePrefix` to wspólny prefiks nazw, którymi spec podpisuje swoje encje
 * (np. `E2E smoke`), a `dates` to daty planu, których dotknął.
 */
export async function cleanupE2eData(
  request: APIRequestContext,
  { namePrefix, dates = [] }: { namePrefix: string; dates?: readonly string[] },
): Promise<void> {
  await clearTemplatesAndCycles(request, namePrefix)
  await clearPlanDays(request, dates)
  await clearRecipes(request, namePrefix)
  await clearPantry(request, namePrefix)
  await clearShoppingLists(request)
  await clearRetailProducts(request, namePrefix)
  await clearStores(request, namePrefix)
  await clearProducts(request, namePrefix)
}

/**
 * Okno dat ZAREZERWOWANE dla E2E.
 *
 * Konwencja: żaden spec nie planuje w bieżącym roku — daty testowe leżą
 * w latach 2030+ („dziś" zostaje dla ręcznego klikania). Dzięki temu `setup`
 * może wyczyścić CAŁE to okno bez pytania każdego specu o jego daty i bez
 * ryzyka usunięcia planu, który ktoś wpisał ręcznie.
 *
 * Okno przechodzimy ROK PO ROKU, bo `GET /plan/days` przyjmuje maksymalnie
 * 366 dni na żądanie (`MAX_RANGE_DAYS` w `planning/service.py`) — szerszy
 * zakres kończy się 422 i sprzątanie po cichu nic nie robi.
 */
export const E2E_YEARS = [2030, 2031, 2032, 2033, 2034, 2035] as const

/**
 * Jednorazowe czyszczenie WSZYSTKICH śmieci E2E — wołane z projektu `setup`.
 *
 * Po co osobna funkcja obok `cleanupE2eData`: sprzątanie per spec zna tylko
 * SWÓJ prefiks, więc nie ruszy danych z czasów innej konwencji nazw ani danych
 * po specu, który zmienił nazwę. Baza dev żyje długo, a jedna zapomniana
 * „Zupa E2E 1737…" wystarcza, żeby szukajka trigramowa ukryła opcję
 * „+ Dodaj" i inline create stał się nieosiągalny.
 *
 * Dopasowanie po fragmencie „E2E" jest tu bezpieczne WYŁĄCZNIE dlatego, że
 * projekt `setup` jest zależnością pozostałych projektów: w chwili tego
 * wywołania żaden spec jeszcze nie działa, więc nie ma czyich danych zabrać.
 * W `afterAll` specu byłoby to wyścigiem — dlatego tam obowiązuje prefiks.
 *
 * **Bramka `baseURL` jest obowiązkowa.** Ta funkcja kasuje szeroko: wszystkie
 * posiłki planu z okna 2030+ NIEZALEŻNIE od nazwy oraz przepisy, warianty sklepowe,
 * sklepy i produkty kanoniczne, których nazwa nosi ślad testu, a konto E2E jest ADMIN-em, więc
 * `DELETE /products/{id}` mu przechodzi. Wskazanie `E2E_BASE_URL` na
 * współdzieloną instancję skasowałoby czyjeś dane bez pytania, dlatego
 * purge działa TYLKO przeciw localhostowi (ustalenie `/security-review` w R2).
 */
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])

export async function purgeE2eLeftovers(
  request: APIRequestContext,
  baseURL: string | undefined,
): Promise<void> {
  const host = baseURL === undefined ? '' : new URL(baseURL).hostname
  if (!LOCAL_HOSTS.has(host)) {
    throw new Error(
      `Odmawiam masowego sprzątania danych na „${baseURL ?? '(brak baseURL)'}". ` +
        'purgeE2eLeftovers kasuje plan z lat 2030+ oraz przepisy i produkty ' +
        'oznaczone jako testowe — wolno mu to robić wyłącznie na localhoście. ' +
        'Uruchom E2E przeciw lokalnemu stackowi (`task dev`) albo sprzątnij ' +
        'dane ręcznie.',
    )
  }

  const headers = await csrfHeaders(request)

  // Kolejność jak w `cleanupE2eData`: najpierw to, co blokuje usuwanie.
  await deleteTemplatesAndCycles(request, headers, anyE2e)

  for (const year of E2E_YEARS) {
    const response = await request.get(`${API}/plan/days?from=${year}-01-01&to=${year}-12-31`)
    if (!response.ok()) {
      console.warn(`[e2e cleanup] GET /plan/days ${year} → ${response.status()}`)
      continue
    }
    const body = (await response.json()) as { items: { meals: { id: number }[] }[] }
    for (const day of body.items) {
      for (const meal of day.meals) {
        await tryDelete(request, `${API}/plan/meals/${meal.id}`, headers)
      }
    }
  }

  await deleteRecipes(request, headers, anyE2e)
  await deletePantryItems(request, headers, anyE2e)
  await deleteShoppingLists(request, headers)
  await deleteRetailProducts(request, headers, anyE2e)
  await deleteStores(request, headers, anyE2e)
  await deleteProducts(request, headers, anyE2e)
}
