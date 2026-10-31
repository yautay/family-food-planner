# 05 — Architektura frontendu

Vue 3 (Composition API, `<script setup lang="ts">`), TypeScript strict,
Vite, Tailwind CSS 4, shadcn-vue, Pinia, TanStack Query, vue-router.
Bez Nuxta, bez i18n (UI wyłącznie PL).

### Wspólne komponenty UX01

`PageHeader` przyjmuje `title`, opcjonalne `description`, `eyebrow`,
`titleTestid` i `decoration` (`plate/herbs/wheat/pot/false`); slot `actions`
zawiera istniejące Button/RouterLink, domyślny slot dodatkowy kontekst.
`RecipeImage` przyjmuje `src`, `alt`, `tone` i `loading`, reaguje na błąd
obrazu i zmianę URL. `EmptyState`, `ErrorState`, `LoadingState`,
`FeedbackMessage`, `ActionArea`, `SummaryPanel` standaryzują hierarchię
treści bez posiadania danych serwera.

`ActionPanel` to modal Reka Dialog, kontrolowany przez `open`. Props:
`title`, `description`, `submitLabel`, `submitDisabled`, `pending`, `error`,
`validationMessage`, `warnings`, `testid`; zdarzenia `submit` i `close`.
Sloty: domyślny scoped slot z `formId`, `context`, `footer-extra`.
Treść jest rodzeństwem formularza akcji: natywne kontrolki wiążą `:form="formId"`,
co zachowuje Enter i natywną walidację bez zagnieżdżania formularzy pickerów.
`AmountInput` ma opcjonalny prop `form`, przekazywany do input i select.
Formularze create-in-context pozostają samodzielne i nie wysyłają panelu.
Reka zapewnia trap fokusu
i modalność; komponent przywraca fokus wywołującemu, blokuje podwójny submit
i zamknięcie w pending, obsługuje natywną walidację oraz fokus błędu serwera.
Formularz i mutacja należą do konsumenta. Przewijalny środek i osobna stopka
utrzymują akcje dostępne na telefonie. `PlanningDialog` pozostaje adapterem
starych propsów/zdarzeń/testid, mapując `subtitle` na `description`; przekazuje
również `validationMessage` i scoped slot `formId`. Walidacja na żywo nie
jest błędem API i nie przejmuje fokusu podczas pisania. Pięciu konsumentów
tygodnia wiąże pola przez `formId` i korzysta z rzeczywistego modala. Kontrakty panelu
planowania przepisu UX03 pozostają w `ux-redesign/CONTRACTS.md`.

UX03: `components/domain/planning/RecipePlanningPanel.vue` ma props
`open`, `recipe: RecipeSummary | null`, `date` oraz opcjonalne `meal`
i `replaceItem`; emituje `close` i
`saved({ day, mealId, itemId, mode: 'add' | 'replace' })` po potwierdzonej
odpowiedzi. Konsumenci UX04/07 używają tego panelu, bez drugiej implementacji
POST/PATCH. Panel unieważnia `planDays.all` i `stats.all`; wynik zawiera
rzeczywiste ID. Przy utracie odpowiedzi blokuje kolejny zapis, odczytuje
stan serwera i pozwala sprawdzić dzień bez uznawania podobnej pozycji za
pewne potwierdzenie własnej mutacji.

`planning/portions.ts` buduje podział ze stringów Decimal i zachowuje wpisy
historyczne. Nowy rodzinny tryb jest jawnym wyborem; wyłączone/zerowe osoby
nie trafiają do payloadu. Sama zamiana przepisu nie zmienia istniejącego
podziału ani nie dopisuje nieobecnych profili. `ServingsSplitDrawer` emituje
`retry` do rodzica, który odświeża profile i przekazuje `isFetching` jako
pending. RecipePicker rozróżnia błąd GET od braku wyników; tworzenie dotyczy
wyłącznie aktualnej, poprawnie odczytanej frazy po debounce.

## 1. Podział odpowiedzialności stanu (ADR-007)

- **TanStack Query** = cały stan serwera (fetch, cache, invalidation,
  optimistic updates). Klucze zapytań centralnie w `src/api/queryKeys.ts`.
- **Pinia** = wyłącznie stan UI/klienta: sesja użytkownika (`authStore`),
  stan szkicu generacji zakupów (`shoppingDraft` — zakres dat, odpowiedź na
  pytanie o spiżarnię, otwarte sekcje; od B10), kolejka offline checkboxów
  (`offlineQueue` — od B12; źródłem prawdy jest IndexedDB, store trzyma jej
  odbicie dla licznika w bannerze), preferencje widoku (`pantryView`). Store NIE trzyma kopii danych serwera —
  podgląd zakupów liczy silnik na serwerze, więc jest stanem serwera i mieszka
  w TanStack Query.
- Mutacje przez composables `useXxxMutation` z jawnym `invalidateQueries`.

## 2. Warstwa API

UX00 (2026-10-30): Vite proxy'uje w dev zarówno `/api`, jak i `/uploads`
do tego samego backendu. Bez drugiej ścieżki fallback SPA zwracał HTML
zamiast zdjęcia. Zdjęcia nadal serwuje uwierzytelniony endpoint backendu;
proxy nie dodaje publicznego serwowania plików ani nowego API.

`src/api/client.ts` — fetch wrapper: credentials include, nagłówek CSRF
z cookie, mapowanie kształtu błędu (04_API §1) na `ApiError`, toast dla
błędów nieobsłużonych lokalnie. Typy: generowane z OpenAPI
(`task fe-types` → `src/api/generated.ts`) — ręcznych interfejsów dla
odpowiedzi API nie piszemy.

## 3. Routing i strony (zgodnie z wizualizacją UI)

```
/                     → redirect /plan-dnia
/plan-dnia/:date?     PlanDniaPage        (widok 1 wizualizacji)
/tydzien/:weekStart?  PlanTygodniaPage    (widok 4)
/przepisy, /przepisy/nowy, /przepisy/:id, /przepisy/:id/edytuj   (widoki 2–3)
/produkty, /produkty/nowy, /produkty/:id/edytuj   (widok 8)
/spizarnia            SpizarniaPage       (widok 6)
/zakupy               ZakupyPage — katalog zapisanych list + generator + preview
/zakupy/listy/:id     ListaZakupowPage    (widok 5; wariant print) — DOSTARCZONE
                        w B11: sekcje per kategoria wg profilu sklepu, checkboxy
                        48 px z optimistic update, udostępnianie, druk
/statystyki           StatystykiPage      (widok 7) — DOSTARCZONE w B13:
                        zakres tydzień/miesiąc/własny (max 92 dni), zakładki
                        Kalorie/Makroskładniki, luki dni bez planu, średnia
                        dzienna vs średnia celów ze statusem
/ustawienia           UstawieniaPage      (cele, profile rodziny, sklepy, konto)
/admin/uzytkownicy · /admin/rodziny · /admin/weryfikacja · /admin/dane
                      (AdminDanePage: kopia CAŁEJ instancji, B14);
                      sekcja „Kopia danych rodziny" mieszka w /ustawienia
                      (B20 — jedyna droga importu i eksportu dla użytkownika).
                      **Ekranu `/admin/audit` NIE MA** — `GET /api/v1/audit`
                      istnieje i jest ADMIN-only, ale B03 miał ten widok jako
                      opcjonalny („jeśli tanio") i nie powstał. Dziennik czyta
                      się dziś przez API albo bazę (ustalenie REVIEW R4)
/login
/l/:token             PublicznaListaPage  — POZA shellem aplikacji, bez auth
```

Guard: brak sesji → `/login` (poza `/l/:token`). Layout: `AppShell`
(sidebar desktop / bottom-nav mobile — patrz 06_UIUX).

UX05: `ShoppingListsCatalog` pobiera rzeczywisty indeks przez
`usePaginatedList` i `queryKeys.shopping.listsIndexFiltered({ limit: 50 })`.
Offset jest wyłącznie pageParam. Katalog nie filtruje wygaśniętych list;
pierwszy wiersz ma neutralną etykietę „Ostatnia lista”. Nazwa, sklep, daty
i licznik odhaczonych pochodzą z API. `listsIndex` jest wspólnym prefiksem
invalidacji dla finalizacji oraz zmian konkretnej listy w UX06.

Pager udostępnia addytywne `nextPageFailed`, `refreshFailed`,
`isRefreshing` i `refresh()`. Pierwszy błąd, błąd kolejnej strony i błąd
odświeżenia danych z cache mają odrębne komunikaty; dotychczasowa semantyka
`loadMoreFailed` pozostaje dla starszych konsumentów. Finalizacja zachowuje
odpowiedź w TanStack Mutation, pokazuje wszystkie rzeczywiste ID list
i unieważnia indeks. Pinia nie przechowuje kopii zapisanych list.
Generator przyjmuje poprawny zakres query przez `navigationRange` także
bez remountu. Zgoda `usePantry` dotyczy jednej generacji i po jej sukcesie
wraca do false; konfiguracja tur jest rozwijanym poziomem szczegółów.

UX02 zachowuje wszystkie powyższe adresy i nazwy tras. `lib/navigation.ts`
jest jednym rejestrem sekcji Plan / Przepisy / Zakupy / Spiżarnia oraz
pomocniczej biblioteki i konta. `routes` wpisu wiąże szczegóły/edytory
z aktywną sekcją. Administracja pozostaje tylko dla ADMIN-a; zmiana menu
nie zmienia `authGuard` ani serwerowych uprawnień. `PlanNavigation`
(`context`, `activeView`) pokazuje Dzień / Tydzień / Podsumowanie i link
Zakupy z planu. `AccountNavigation` przyjmuje `displayName`, `householdName`,
`isAdmin`, `pending`, `mobile` i emituje `logout`; Reka obsługuje menu
zarówno przy koncie w sidebarze, jak i w nagłówku telefonu.

Kontrakt UI dla UX03/04/05/07/10:

- `PlanNavigationContext { selectedDate, from, to }`: lokalne dni ISO,
  zakres włącznie, do 92 dni. `validNavigationDate` odrzuca także tablice
  i nieistniejące dni. `navigationRange` wymaga poprawnej pary.
- `planNavigationContext(route, today?)` odczytuje kontekst;
  `planNavigationTarget(name, context)` buduje link i query
  `selectedDate/from/to`. Parametr dnia jest nadrzędny. Parametr tygodnia
  określa jego granice; selectedDate musi w nich pozostać. Bez wyboru:
  dziś, jeżeli należy do tygodnia, w przeciwnym razie poniedziałek.
- Strzałki tygodnia zachowują offset wybranego dnia. Przycisk bieżącego
  tygodnia jawnie wybiera dziś. Podsumowanie rzeczywiście czyta parę
  from/to; poprawne własne zmiany zapisuje przez replace, niepełny szkic
  zostaje lokalny. Presety używają aktualnej daty odniesienia także bez reloadu.
- Zakupy otrzymują from/to/selectedDate w query. Odczyt przez generator
  należy do UX05; sama nawigacja nie generuje listy ani nie zapisuje danych.
- Przepisy również otrzymują from/to/selectedDate. UX04 zachowuje ten kontekst
  między katalogiem a szczegółem i przekazuje datę do RecipePlanningPanel.
  Filtry katalogu są w URL (`q`, powtarzane `tag`, `scope`, `prep_time_max=30`);
  serwer filtruje przed paginacją. `catalogNavigation.ts` buduje powrót do
  katalogu, a istniejący cache Query zachowuje pobrane strony. Nie utrwalamy
  odpowiedzi serwera w Pinia ani osobnym magazynie katalogu.

AppShell przechowuje wyłącznie kalendarzowy kontekst UI, nie dane planu.
Zmiana path kieruje fokus do `main#main-content`, query zachowuje fokus
i scroll. Wstecz odtwarza zapisaną pozycję. Skiplink prowadzi do tego samego
main. Menu konta oddaje fokus triggerowi po Escape, a po zaakceptowanej
nawigacji pozostawia go treści; anulowany guard nie gubi otwartego menu.

Stan faktyczny po BATCH_11 — trzy rzeczy, które wiążą kolejne trasy publiczne:

- `meta.public` znaczy „ekran LOGOWANIA": trasa działa bez sesji, ale zalogowany
  jest z niej odsyłany na plan dnia. Dla `/l/:token` to byłoby błędem (właściciel
  listy ma prawo otworzyć własny link), więc doszła osobna flaga
  **`meta.anonymous`** — dostępne dla każdego, bez przekierowania. Guard sprawdza
  ją PRZED `auth.ensureLoaded()`, więc publiczna strona nie strzela do `/auth/me`.
- `/l/:token` jest importowane leniwie i renderuje WŁASNY, minimalny layout —
  `AppShell` ciągnąłby stan sesji i menu, których ta strona nie ma prawa pokazać.
- Wywołania `/api/v1/public/*` idą osobnym, lekkim klientem
  (`src/api/publicList.ts`) z `credentials: 'omit'` i bez nagłówka CSRF —
  `client.ts` NIE dostał trybu warunkowego, bo jeden `if` w warstwie HTTP całej
  aplikacji łatwo pomylić, a pomyłka oznaczałaby wysyłanie cudzej sesji.

~~Stan faktyczny po REVIEW R4 — żaden ekran listy nie ma paginacji.~~
**NIEAKTUALNE — dług zamknięty w BATCH_19.** Akapit opisywał wyłącznie ten
dług (każdy ekran wysyłał `offset: 0` ze stałym limitem, a `/produkty` pisało
„Produktów: 185" i renderowało 50), więc razem z naprawą traci przedmiot.

Stan faktyczny po BATCH_19 — **paginacja to jeden wzorzec dla wszystkich
ekranów listowych**, opisany w 06_UIUX §3.6:

- `src/api/pagination.ts` — `usePaginatedList` na `useInfiniteQuery`; zwraca
  `items`/`total`/`loaded`/`hasMore`/`isPending`/`isLoadingMore`/`loadMore`.
  **`offset` NIE wchodzi do klucza zapytań** — niesie go `pageParam`, więc
  klucz listy jest ten sam co przed batchem i `invalidateQueries` po mutacji
  nadal trafia w całą listę (klucz per strona rozbiłby cache na wpisy, z których
  inwalidacja odświeżałaby jeden). Dlatego `offset` w interfejsach filtrów
  w `queryKeys.ts` jest OPCJONALNY: podają go tylko pickery, które pobierają
  jedną krótką stronę i paginacji nie mają.
- `src/components/domain/LoadMoreButton.vue` — przycisk „Pokaż więcej (N)",
  ≥44 px, spinner na sobie zamiast skeletonu listy; `failed` dokłada przy nim
  komunikat ponowienia.
- **Rozdzielenie stanów błędu jest częścią kontraktu**: `isError` zapala się
  WYŁĄCZNIE, gdy padła pierwsza strona (nie ma czego pokazać), a nieudane
  doładowanie to `loadMoreFailed` — lista zostaje na ekranie. Wystawienie
  ekranowi surowego `isError` całego `useInfiniteQuery` kasowało 50 poprawnych
  wierszy po jednym nieudanym kliknięciu.
- Pozycje są ODSIEWANE po `id` (`TItem extends { id: number }`): paginacja po
  `offset` może oddać ten sam wiersz na dwóch stronach, gdy zbiór zmieni się
  między pobraniami, a dwa węzły z tym samym `:key` psują patchowanie listy.
- Ekrany i rozmiary stron: `/produkty` 50, `/przepisy` 50, `/spizarnia` **100**
  (inwentarz przeglądany „ile mam czego", nie przeszukiwany katalog — mniejsza
  strona dołożyłaby kliknięć), `/admin/weryfikacja` 50, `/admin/uzytkownicy` 50,
  `/admin/rodziny` 50.
- Każdy z tych ekranów pokazuje licznik `listCount(loaded, total)` („50 z 185"),
  nie samo `total`.
- **`/admin/weryfikacja` sortuje na SERWERZE** (`GET /products?sort=created_at`,
  04_API §1). Sortowanie po stronie klienta układało po wieku pięćdziesiątkę,
  którą serwer wybrał alfabetycznie, więc produkt spoza pierwszych 50 nazw był
  z tego ekranu nieosiągalny — a to jest ekran, na którym uzupełnia się wartości
  odżywcze produktów wniesionych hurtem. Zmierzone na 68 pozycjach w kolejce:
  stara ścieżka nie pokazywała na pierwszej stronie ANI najstarszego realnego
  produktu, ANI ostatniego z wniesionej partii.
- Świadomie POZA zakresem: wirtualizacja list i nieskończone przewijanie
  sterowane scrollem; select przypisania konta na `/admin/rodziny` bierze jedną
  stronę z sufitem 200 (to kontrolka formularza, nie ekran listy — przy większej
  instancji potrzebuje szukajki, nie doładowywania).

## 4. Komponenty

- `src/components/ui/*` — wygenerowane shadcn-vue (button, card, dialog,
  drawer, input, select, tabs, badge, checkbox, tooltip, sheet, command…).
  Modyfikacje tylko przez tailwind theme tokens, nie fork logiki.
- `src/components/domain/*` — domenowe, m.in.:
  - `ProductPicker` — command palette z wyszukiwaniem; brak wyniku ⇒
    pozycja `+ Dodaj produkt "cebula"` otwierająca `ProductCreateDrawer`
    (create-in-context; po zapisie auto-wybór i powrót do edycji) — wzorzec
    obowiązkowy wszędzie, gdzie wybiera się produkt/przepis/tag/sklep.
    Stan faktyczny (BATCH_04, `components/domain/ProductPicker.vue`):
    props `modelValue: Product | ProductDetail | null`, `label?`, `limit?`
    (domyślnie 8), `disabled?`, `debounceMs?` (250; testy podają 0);
    emits `update:modelValue` i `selected(product)`. Obsługa klawiatury
    (↑/↓/Enter/Escape) i `data-testid` (`picker-input`, `picker-option-{id}`,
    `picker-create`, `picker-selected`) są częścią kontraktu — konsumenci
    (B05/B06/B08/B09) opierają na nich E2E.
  - `StorePicker` (BATCH_09, `components/domain/StorePicker.vue`) — ten sam
    wzorzec dla sklepów, z prefiksem testid `store-picker-`. Dwie świadome
    różnice wobec `ProductPicker`: lista sklepów przychodzi w CAŁOŚCI jednym
    zapytaniem i filtruje się po stronie klienta (słownik ma kilka pozycji,
    więc debounce byłby opóźnieniem bez powodu), a wśród opcji jest jawna
    pozycja „Bez sklepu" (`store-picker-none`) — wariant retail bez sklepu to
    dozwolony stan (03_DATABASE §3). Props `modelValue: Store | null`,
    `label?`, `disabled?`; emits `update:modelValue` i `selected(store)`.
  - `RetailProductCreateDrawer` (BATCH_09) — KONTRAKT dla B10/B11: props
    `{ open: boolean, canonicalProductId: number, prefillName?: string }`,
    emits `created(retailProduct)` i `close()`. Poza id produktu nie wymaga
    niczego: sposób liczenia dociąga z `/products/{id}`, a z niego wynika
    ZAWĘŻONA jednostka opakowania (g / ml / szt.).
  - `StoreCategoryOrderEditor` (BATCH_09) — kolejność kategorii w sklepie:
    natywne HTML5 DnD **plus obowiązkowe strzałki** góra/dół (06_UIUX §2).
    Komponent trzyma szkic i oddaje wynik zdarzeniem `save(categoryIds)` —
    zapis (PUT całej kolejności) należy do rodzica. Biblioteki DnD świadomie
    NIE MA: lista jest jednokolumnowa i krótka, więc trzy handlery zdarzeń
    kosztują mniej niż zależność do utrzymania.
  - `NutritionBar` / `NutritionRing` — wskaźniki wartość/cel/status.
  - `MacroSummary`, `MealCard`, `RecipeCard`, `ShoppingItemRow`
    (duży checkbox ≥44px), `LeftoverBadge` („Zostanie: 150 g").
  - `AmountInput` — ilość + jednostka, walidacja dziesiętna z przecinkiem.
- Wykresy: `src/components/charts/*` — własne SVG (ADR-013): `BarChart`
  (słupki dni), `NutritionBar`, `DonutChart` (makro), `TrendLine` (statystyki).
  Stan faktyczny po BATCH_13 — dwa kontrakty, na których stoi widok statystyk:
  - `BarChart` przyjmuje cel dwojako: `target` na CAŁYM wykresie (jedna pozioma
    linia) albo `target` na POJEDYNCZYM słupku, co przełącza wykres na linię
    SCHODKOWĄ (cele są historyczne, więc zmiana celu w środku zakresu musi być
    widoczna jako zmiana poziomu). Dzień bez planu podaje się jako
    `empty: true` — komponent rysuje wtedy przerywany obrys i nie wlicza dnia do
    skali, bo luka to nie zero. Slot `overlay` udostępnia geometrię wykresu
    (`width`, `height`, `scaleMax`) nakładkom.
  - `TrendLine` ma dwa tryby: samodzielny (`<svg>` z własną skalą) i nakładkę
    (`frame` z geometrią rodzica ⇒ `<g>` bez własnego `<svg>`), używaną w slocie
    `overlay`. Wspólna skala jest tu warunkiem sensu: dwie skale dałyby wykres,
    który da się porównać tylko na oko. Punkt `null` PRZERYWA linię.

## 5. Formularze i walidacja

vee-validate + zod: schematy w `src/lib/schemas/*` odzwierciedlają reguły
backendu (min/max, wymagalność); komunikaty PL. Walidacja frontowa to UX —
prawdą jest walidacja serwera (422 mapowane na pola formularza).

## 6. PWA i offline (ADR-009)

Stan faktyczny po BATCH_12.

**PWA** (`vite.config.ts`, `index.html`):

- manifest PL: `name` i `short_name` „Paśnik" (nazwa mieści się na ekranie
  domowym, więc skrótu nie ma), `lang: pl`,
  `display: standalone`, `theme_color` #E07A2F, `background_color` #FAF6EF,
  ikony PNG 192/512 w wariantach `any` i `maskable` (`public/icons/`).
  Splash na Androidzie składa przeglądarka z ikony 512 + `background_color`;
  iOS nie czyta manifestu w tym zakresie, więc `apple-touch-icon` i metatagi
  `apple-mobile-web-app-*` siedzą w `index.html`.
- Workbox `generateSW`: precache shella (`**/*.{js,css,html,svg,png,woff2}`),
  `navigateFallback: index.html` z wykluczeniem `/api/` i `/uploads/`
  (te obsługuje backend, ADR-014). Runtime: `NetworkFirst` dla `/api/*`
  z `networkTimeoutSeconds: 3` (bez tego offline UX to 30 s spinnera) oraz
  `CacheFirst` dla `/uploads/*`. **`/api/v1/auth/*` jest wykluczone** —
  odpowiedzi z `Set-Cookie` nie wchodzą do cache (07_SECURITY).
- `registerType: 'autoUpdate'`, ale podmiana NIE jest cicha:
  `src/lib/offline/registerSW.ts` pyta „Dostępna jest nowa wersja aplikacji.
  Odświeżyć teraz?", żeby przeładowanie nie trafiło w środek odhaczania listy.
  W dev SW jest wyłączony (`devOptions.enabled: false`) — precache w trakcie
  pracy zatruwa cache; testuje się go na buildzie produkcyjnym.

**Offline listy zakupowej** (`src/lib/offline/*`, `src/stores/offlineQueue.ts`):

- **Wszystko, co idzie do IndexedDB, przechodzi przez `plain()`** (`db.ts`):
  structured clone rzuca `DataCloneError` na proxy Vue, a dokładnie takie
  obiekty przychodzą z cache'u TanStack Query. Bez tej konwersji zapis padał
  po cichu (błąd łykany przez `withDb`), UI wyglądał poprawnie, bo optimistic
  update żyje w pamięci, a kolejka i snapshot zostawały puste.
- `db.ts` — IndexedDB (`idb`) z dwoma magazynami: `list-snapshots`
  (klucz `list:{id}` albo `public:{token}`) i `mutation-queue` (klucz
  `{target}#{itemId}`, czyli deduplikacja per pozycja za darmo — podwójne
  odhaczenie tej samej rzeczy daje JEDEN PATCH z ostatnim stanem). Brak
  IndexedDB (tryb prywatny, zablokowany storage) degraduje się do zachowania
  sprzed B12, a nie do białego ekranu.
- `hydrate.ts` — snapshot wchodzi do CACHE'U TanStack Query (`updatedAt: 1`,
  więc jest od razu nieświeży i nie blokuje refetchu przez `staleTime`), a nie
  do osobnego ref-a strony. Dzięki temu render, optimistic update i rollback
  działają offline tym samym kodem, co online.
- `clock.ts` — przesunięcie zegara liczone z nagłówka `Date` KAŻDEJ odpowiedzi
  (oba klienty HTTP). `checked_at` w kolejce jest w czasie SERWERA, bo LWW ma
  rozstrzygać, kto odhaczył później, a nie czyj telefon się spieszy.
- `offlineQueue.ts` (Pinia — stan UI, ADR-007) — enqueue w momencie
  KLIKNIĘCIA, flush po `online`, `focus` i `visibilitychange`. Flush jest
  SEKWENCYJNY: limit 60/min/IP jest wspólny dla całej ścieżki publicznej
  (ustalenie R3), więc równoległy wystrzał kolejki sam by w niego wpadł.
- **`networkMode: 'always'` w `main.ts` jest WARUNKIEM działania kolejki**, nie
  optymalizacją. Domyślny tryb `'online'` PAUZUJE mutację przy
  `navigator.onLine === false`: `onMutate` się wykonuje (optimistic update
  wygląda poprawnie), ale `mutationFn` nie jest wołane aż do powrotu sieci —
  więc kolejka nigdy nie zobaczyłaby odhaczenia. Pauza TanStack żyje w pamięci
  karty i nie przeżywa reloadu; nasza kolejka przeżywa (ADR-009). Wyłapało to
  dopiero E2E z `context.setOffline(true)`.
- `sync.ts` — klasyfikacja wyniku: `sent` (200, także gdy LWW odrzucił starszy
  znacznik), `retry` (brak sieci, 429, 5xx — wpis zostaje, backoff 15 s),
  `gone` (404/410 — kolejka tej listy i jej snapshot idą do kosza, strona
  pokazuje ekran „wygasła", bez pętli retry) i `dropped` (4xx trwałe albo
  wyczerpane 8 prób, żeby jeden wpis nie zablokował kolejki na zawsze).
- `OfflineBanner.vue` w UI obu stron listy: komunikat trybu offline + licznik
  oczekujących zmian; niewidoczny, gdy nie ma o czym mówić.
- Czego kolejka NIE obsługuje i dlaczego: **zmiany sklepu** (kolejność sekcji
  składa serwer z profilu `store_category_order`, którego przeglądarka nie zna
  — ustalenie R3) i **przyjęcia zakupów do spiżarni** (jego wartością jest
  policzalna odpowiedź serwera, a bez niej użytkownik nie wie, co weszło).
  Obie akcje są offline wyłączone z podpowiedzią, dlaczego.
- Publiczna strona `/l/:token` ma DOKŁADNIE ten sam mechanizm, ale własny
  klient HTTP (`api/publicList.ts`, bez cookies i CSRF) i własny kształt
  snapshotu (`PublicListRead` nie ma sekcji ani `received_at`).
- Backend: PATCH pozycji (prywatny i publiczny) przyjmuje opcjonalne
  `checked_at`; last-write-wins per pozycja, znacznik z przyszłości ponad
  5 minut przycinany do czasu serwera, powtórka tego samego żądania nie
  przesuwa znacznika (idempotencja, na której stoi ponawianie z kolejki).
- Offline dla innych widoków (plan, przepisy) jest poza zakresem —
  osobna decyzja po R4.

## 7. Konwencje jakości

- `vue-tsc --noEmit` i eslint (flat config, vue+ts) zielone = warunek DoD
  każdego batcha; vitest dla logiki composables/komponentów krytycznych.
- Dostępność: każdy interaktywny element ma etykietę (aria-label gdy brak
  tekstu); focus states Tailwind ring; kontrast wg 06_UIUX tokens.
- Formatowanie ilości: helper `formatAmount` (g→kg powyżej 1000, przecinek
  dziesiętny PL) — jedyne miejsce formatowania ilości w aplikacji.
