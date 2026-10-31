# ADR-018 — Prywatna lista offline z izolacją lokalnego zakresu

Status: ACCEPTED (2026-10-31, decyzja techniczna UX06)

## Kontekst

Autoryzowany UX06 wymaga restartu prywatnej listy bez sieci oraz izolacji
po wylogowaniu i zmianie konta lub rodziny. Rzeczywisty preflight zbudowanego
PWA ujawnił pusty ekran po cold reload oraz ujawnienie snapshotu A1 kontu B1,
mimo odmowy 404 z backendu. Globalny cache Workbox `pasnik-api` opierał się
wyłącznie na URL, a prywatny klucz IndexedDB miał postać `list:{id}`.

Ta decyzja zastępuje wyłącznie politykę runtime cache API/uploadów z ADR-009
i uzupełnia lokalną izolację jego snapshotów/kolejki. Sesje server-side,
cookie i CSRF z ADR-003, scope serwera z ADR-006, TanStack Query/Pinia
z ADR-007 oraz publiczny token z ADR-010 pozostają źródłami swoich reguł.

## Decyzja

- Service worker przechowuje shell i zasoby z buildu; nie przechowuje
  odpowiedzi API ani chronionych uploadów. Publiczna lista również korzysta
  z własnego istniejącego snapshotu IDB. Odpowiedź 404/410 nie może zostać
  przykryta wcześniejszym udanym cache HTTP.
- Prywatny snapshot i intencje checkboxów należą do losowego lokalnego
  namespace. Marker zawiera wyłącznie wersję, namespace, losową sól oraz
  SHA-256 pseudonimy ostatnio potwierdzonego konta/rodziny i cookie CSRF.
  Nie zapisujemy CurrentUser, surowych identyfikatorów, nazw, emaili, roli,
  cookie ani tokenu sesji. Pseudonim jest lokalnym identyfikatorem zakresu,
  nie dowodem uwierzytelnienia i nie deklarujemy, że jest anonimowy.
- Zgodne potwierdzenie `/auth/me` zachowuje namespace i oczekujące intencje
  po restarcie. Zmiana potwierdzonego konta/rodziny, wylogowanie, odmowa sesji
  lub zmiana cookie zamyka poprzedni zakres. Operacje asynchroniczne muszą
  sprawdzić aktualność zakresu również po oczekiwaniu na I/O.
- Po błędzie transportu `/auth/me` dopuszczamy wyłącznie nazwaną trasę
  prywatnej listy z markerem związanym z nadal obecnym cookie. `user=null`
  i `isAuthenticated=false`; nie odtwarzamy konta ani uprawnień z dysku.
  Pozostałe widoki nadal wymagają zwykłego guarda. Odpowiedź 4xx/5xx nie jest
  błędem transportu pozwalającym wejść offline.
- Prywatne intencje są wysyłane dopiero po rzeczywistym potwierdzeniu sesji
  online i tylko dla jej aktualnego namespace. Publiczna strona nie pyta
  o `/auth/me` w celu odtworzenia lub wysłania publicznej kolejki.
- Zmiana zakresu zamyka aktywny chroniony widok i jego obserwatory, a także
  czyści cache Query. Samo `QueryClient.clear()` nie jest bramką renderowania.
- Każda chroniona generacja widoku ma własny QueryClient z tymi samymi
  ustawieniami zapytań i mutacji. Późne callbacki poprzedniego komponentu,
  w tym rollback, nie zapisują do klienta nowego konta. Odpowiedzi HTTP oraz
  callbacki ustawiające CurrentUser lub rozpoczynające pobranie eksportu
  sprawdzają ticket generacji i zgodność cookie również po odczycie body.
  Opóźnione 401 nie wylogowuje nowej sesji. Generacja jest wyłącznie lokalnym
  licznikiem w pamięci, bez nowego tokenu ani mechanizmu autoryzacji.
- Przerwanie prywatnego PATCH przez zmianę generacji nie jest terminalną
  odmową serwera: kolejka i snapshot pozostają, licznik prób się nie zwiększa,
  a następna wysyłka ponownie potwierdza `/auth/me`. Reguły rzeczywistych
  odmów 4xx, limitów 429, backoffu, atomowego ack i LWW pozostają zachowane.
- Legacy prywatne wpisy bez namespace pozostają niewysyłane w IDB. Nie można
  przypisać ich nowemu kontu na podstawie samego numeru listy. Nie kasujemy
  arbitralnych starych intencji ani nie oznaczamy ich jako zsynchronizowanych.
- Awaria lokalnego storage wyłącza bezpieczne prywatne offline. Nie może
  unieważniać poprawnej sesji online ani udawać trwałego zapisu checkboxa.

## Przejście ze starego service workera

Nowy kanoniczny worker `sw-private-v1.js` ma znaną politykę bez cache API.
Build zachowuje identyczny alias `/sw.js`, aby dotychczasowe rejestracje
mogły zaktualizować swój precache i otworzyć nowy bootstrap. Jeżeli nowy
bootstrap nadal ma stary controller, przed uruchomieniem routera/API czeka
na przejęcie kontroli przez kanoniczny worker, następnie usuwa legacy
`pasnik-api` i `pasnik-uploads`. Błąd aktualizacji daje jawny stan wymagający
sieci, bez renderowania prywatnych danych. Znany bezpieczny controller
pozwala wystartować offline bez pobierania nowego workera.

## Granice i weryfikacja

Offline nie można poznać odwołania sesji lub zmiany rodziny na serwerze.
Lokalny odczyt dotyczy ostatnio potwierdzonego zakresu tego urządzenia;
powrót sieci wymaga ponownej weryfikacji przed wysłaniem prywatnych zmian.
Nie powstaje offline planu, przepisów, profili ani administracji. Publiczny
token nadal jest jedynym upoważnieniem publicznego klienta bez cookie/CSRF.

Wymagane dowody: cold private i public na rzeczywistym buildzie, A→logout→B
z odmową backendu i obserwacją braku choćby chwilowego ujawnienia, zmiana
rodziny/karty, zaległa kolejka po restarcie, odmowy/awarie storage, LWW oraz
upgrade ze starego workera. Faktyczne wyniki i otwarte ustalenia są w
`docs/implementation-plan/ux-redesign/PROGRESS.md`; ten ADR nie zastępuje
odbioru kodu, security review ani testów runtime.
