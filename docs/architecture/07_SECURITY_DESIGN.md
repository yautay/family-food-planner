# 07 — Projekt bezpieczeństwa

Aplikacja wystawiona do Internetu ⇒ bezpieczeństwo jest wymaganiem
podstawowym, nie dodatkiem. Zasada: nie implementujemy własnej kryptografii;
biblioteki standardowe (argon2-cffi, secrets, hmac).

## 1. Model zagrożeń (realny, domowy)

Aktorzy: (a) internetowy skaner/bot, (b) osoba z publicznym linkiem listy,
(c) błąd członka rodziny. NIE bronimy się przed targeted APT — bronimy się
przed masowym skanowaniem, credential stuffing, wyciekiem danych przez
publiczne linki i błędami aplikacyjnymi (IDOR/XSS/CSRF/upload).

## 2. Uwierzytelnianie (ADR-003)

- Hasła: **argon2id** (argon2-cffi, parametry domyślne biblioteki,
  rehash przy logowaniu gdy parametry wzrosną). Minimalna długość 10.
- Sesje: server-side w PG (`sessions`), id = `secrets.token_urlsafe(32)`;
  cookie: `HttpOnly; Secure; SameSite=Lax; Path=/`; TTL 30 dni przesuwne;
  logout = delete row. Bez JWT (nic tu nie wymaga bezstanowości, a odwołanie
  sesji ma być natychmiastowe).
- Brak samorejestracji; konta tworzy ADMIN. Pierwszy admin: CLI
  `task create-admin` (nigdy seed z hasłem w repo — lekcja netQArnera).
- Rate limit (slowapi): `/auth/login` 5/min/IP + blokada konta po 10 nieudanych
  próbach (komunikat neutralny — identyczny jak przy złym haśle).
  Stan faktyczny (BATCH_02, `app/core/security.py`): blokada jest **stała,
  15-minutowa**, a licznik porażek zeruje się w momencie założenia blokady —
  nie ma backoffu wykładniczego. Wystarcza na model zagrożeń z §1 (≈10 prób
  na 15 min na konto, przy jednoczesnym limicie 5/min/IP).
  **Przegląd BATCH_17 (2026-09-05) — parametry ZOSTAJĄ bez zmian**: argon2id
  z domyślnymi parametrami argon2-cffi (RFC 9106: t=3, m=64 MiB, p=4 — drugi
  zalecany zestaw, `check_needs_rehash` podniesie je przy logowaniu, gdy
  biblioteka je zmieni), TTL sesji 30 dni przesuwne (aplikacja rodzinna na
  własnych urządzeniach; odwołanie sesji jest natychmiastowe przez DELETE
  wiersza, ADR-003), blokada 10 porażek / 15 min. Jedna konsekwencja obrazu
  prod, o której trzeba wiedzieć: **licznik slowapi jest per PROCES**, a
  `UVICORN_WORKERS=2`, więc realny sufit limitów per IP to dwukrotność
  wartości (login 5/min → do 10/min). Blokada konta jest w BAZIE, więc jej to
  nie dotyczy — to ona jest twardą granicą (10 prób / 15 min / konto).
  Współdzielony licznik (Redis) byłby nowym komponentem wbrew ADR-001 —
  świadomie odrzucone przy tej skali.

## 3. CSRF, CORS, nagłówki

- CSRF: double-submit cookie — `csrf_token` (nie-HttpOnly) + wymagany
  nagłówek `X-CSRF-Token` dla POST/PUT/PATCH/DELETE; porównanie
  `hmac.compare_digest`. Publiczne PATCH-e checkboxów (token listy) —
  wyłączone z CSRF (autoryzuje token w URL), ale rate-limited.
  Drugi wyjątek (BATCH_02, `CSRF_EXEMPT_PREFIXES`): **`POST /auth/login`** —
  przed zalogowaniem nie istnieje jeszcze cookie `csrf_token`, z którym można
  by porównać nagłówek. Żądanie chroni rate limit i blokada konta (§2);
  ryzykiem jest wyłącznie „login CSRF" (wmuszenie ofierze cudzej sesji), a bez
  samorejestracji i przy jednym origin jest ono w tym modelu zagrożeń pomijalne.
- CORS: brak (SPA serwowana z tego samego origin). Nie włączamy „na zapas".
- Nagłówki (middleware): `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`,
  CSP (stan po BATCH_17, ustalenie REVIEW R4 pkt 2):
  `default-src 'self'; img-src 'self' data: blob:; style-src 'self'
  'unsafe-inline'; object-src 'none'; base-uri 'none'; form-action 'self';
  frame-ancestors 'none'` (Tailwind inline styles), bez zewnętrznych źródeł.
  `base-uri`, `form-action` i `frame-ancestors` **nie dziedziczą po
  `default-src`** — bez nich wstrzyknięty `<base>` przestawiałby ścieżki
  względne, a przejęty formularz mógłby wysłać dane na obcy host;
  `frame-ancestors 'none'` to nowoczesny odpowiednik `X-Frame-Options: DENY`,
  który zostaje dla starszych klientów. `worker-src` świadomie NIE jest
  wymieniony: dziedziczy `'self'`, a dokładnie tego potrzebuje service worker
  (`/sw.js` + `workbox-*.js` z tego samego originu, ADR-009) — rejestracja SW
  zweryfikowana na buildzie produkcyjnym w B17. HSTS ustawia reverse proxy.
  Wyjątek dla Swagger UI (`/api/docs`, `/api/openapi.json`, CDN) obowiązuje
  **wyłącznie poza prod** — w prod te ścieżki nie istnieją (`docs_url=None`),
  a middleware nie stosuje wyjątku nawet dla ich 404.
- **Cookies z prefiksem `__Host-` w prod** (BATCH_17, ustalenie REVIEW R4
  pkt 6): `__Host-pasnik_session` i `__Host-csrf_token`. Double-submit czyta
  pierwsze cookie o danej nazwie z `document.cookie`, więc subdomena albo
  sąsiad na tej samej domenie rejestrowalnej mógłby przypiąć własną parę
  cookie + nagłówek; prefiks każe przeglądarce odrzucić cookie bez `Secure`,
  z `Domain` albo z `Path` ≠ `/`. `__Host-` WYMAGA `Secure`, więc włącza się
  razem z tą flagą (`APP_ENV=prod`); w dev/test nazwy są gołe (`app/core/
  cookies.py`). **Frontend nie zna nazwy z literału** — `src/api/client.ts`
  sprawdza obie kandydatki (`CSRF_COOKIE_CANDIDATES`), bo testy jadą po HTTP
  i literał `csrf_token` przeszedłby je, a na produkcji cicho wyłączyłby
  mutacje. Zmiana wylogowała istniejące sesje (nowa nazwa cookie).

## 4. Autoryzacja

- Role ADMIN/USER na dependency (`require_admin`).
- Scope PRIVATE/HOUSEHOLD w serwisach przez `ScopedQuery` — zapytanie USERA
  o encję cudzą kończy się 404 (nie 403 — nie potwierdzamy istnienia).
- **ADMIN jest wyjątkiem w ODCZYCIE encji ze scope** (`visible_condition` →
  `true()`): decyzja właściciela **D16, zatwierdzona 2026-08-21**, zgodna
  z macierzą 08_TESTING §4. Uzasadnienie: administrator tej instalacji i tak
  ma dostęp do bazy i do `/admin/*`, więc udawanie, że nie widzi, dawałoby
  pozorne bezpieczeństwo, a utrudniałoby wsparcie użytkowników. Granice tego
  wyjątku:
  - **nie rozciąga się na MUTACJE reguł właścicielskich** — zmiana scope
    i usunięcie encji przechodzą przez `ScopedQuery.assert_can_manage`;
  - **rozciąga się natomiast na EDYCJĘ TREŚCI** (rozszerzenie D16
    zatwierdzone 2026-09-05, wariant „a" z raportu R4): ADMIN może zmieniać
    treść encji ze scope wszystkich rodzin — w praktyce dotyczy to modułu
    shopping (`share_list`, `revoke_share`, `update_item`, `resolve`,
    `finalize`, `accept_to_pantry` wołają `get_or_404` bez następującego
    `assert_can_manage`). Uzasadnienie: administrator i tak ma bazę
    i `/transfer/export?scope=instance`. **Świadomie przyjęte ryzyko**:
    `share_list` generuje PUBLICZNY TOKEN dla cudzej listy, a taki link
    opuszcza instancję i można go najwyżej odwołać. Przy jednym koncie ADMIN
    bezprzedmiotowe; przy drugiej rodzinie albo drugim adminie punkt wraca
    do przeglądu;
  - **nie rozciąga się na zasoby adresowane „moją rodziną"** —
    `/households/my` i profile członków pokazują ADMIN-owi WŁASNĄ rodzinę,
    do cudzych ma `/admin/households/*` (04_API §3 pkt 2a);
  - **nie rozciąga się na WYBÓR CELU ZAPISU** (ustalenie REVIEW R4): jeżeli
    zasób jest adresowany czymś innym niż własne id — jak dzień planu, który
    adresuje DATA — to zapytanie „który wiersz to mój" musi iść po
    `owned_condition`, nie po `visible_condition`. Inaczej `true()` ADMIN-a
    zamienia „mój dzień na 10 września" w „najstarszy czyjkolwiek dzień na
    10 września" i zapis ląduje w cudzej rodzinie. Dla nie-ADMIN-a oba warunki
    są identyczne, więc rozdzielenie niczego nie zmienia poza tym jednym
    przypadkiem. Ta sama reguła stoi po stronie spiżarni od REVIEW R3
    (`select_own_household`, nie widoczność).
  - **nie rozciąga się na dane osobowe w odpowiedziach publicznych**
    (§5) ani na hasła i tokeny (nigdy w logach — §8).
  Konsekwencja dla batchy: każda nowa encja ze `ScopedMixin` dziedziczy to
  zachowanie automatycznie i MA je zaasercjonować w macierzy uprawnień
  (wzorzec: `tests/api/recipes/test_recipes_api.py::test_d16_admin_widzi_cudze_przepisy_na_sciezkach_uzytkownika`).
- Testy anty-IDOR obowiązkowe w każdym batchu z nowym zasobem: user B nie
  odczyta/nie zmieni zasobu usera A (macierz w 08_TESTING §4).

## 5. Publiczne tokeny list (ADR-010)

256-bit `token_urlsafe(32)`; lookup po unique index (stała czasowo równość
nieistotna — token nieodgadywalny); expiry (default 7 dni, konfigurowalne
przy udostępnieniu), revoke, 410 z przyjaznym ekranem; odpowiedź bez PII
(tylko pozycje listy); rate limit 60/min/IP na `/public/*`; tokeny nie
logowane (filtr w logach — ścieżka maskowana do `/public/lists/***`).

**WDROŻONE w BATCH_11** (`app/modules/shopping/{public_router,lists_service}.py`),
**zweryfikowane realnymi requestami w REVIEW R3** (każdy punkt tej sekcji).
Dziewięć szczegółów wykonawczych, które trzeba utrzymać:

1. Router publiczny siedzi dokładnie pod `/api/v1/public/` — tylko ten prefiks
   jest w `CSRF_EXEMPT_PREFIXES` i tylko on jest maskowany przez `mask_path()`.
   Przeniesienie ścieżki wyłączyłoby publiczny PATCH (403) i odsłoniłoby tokeny
   w logach.
2. Token w ścieżce jest ograniczony wzorcem `^[A-Za-z0-9_-]{43}$`, więc skanowanie
   kończy się 422 przed zapytaniem do bazy.
3. 404 (nieznany token) i 410 (wygasły/odwołany) mają IDENTYCZNY komunikat —
   nie potwierdzamy istnienia. Kod `gone` i wyjątek `GoneError` doszły do
   `app/core/errors.py`.
4. Odwołanie NIE zeruje kolumny `public_token` (żeby nowy losowy token nie mógł
   wskrzesić starego linku); ponowne udostępnienie zawsze zapisuje nowy token.
5. Odpowiedź publiczna to jawna biała lista pól, a nie serializacja encji;
   dokładny zbiór kluczy pilnuje test (08_TESTING §2.9).
6. Publiczny klient frontendu (`src/api/publicList.ts`) wysyła żądania
   z `credentials: 'omit'` — otwarcie linku na zalogowanej przeglądarce nie
   wysyła cookie sesji rodziny.
7. Limit jest WSPÓLNY dla całej ścieżki publicznej (`limiter.shared_limit`
   ze scope `public-lists`), a nie liczony per endpoint — inaczej `/public/*`
   miałoby faktycznie 120/min/IP (60 na GET + 60 na PATCH). Kolejny endpoint
   publiczny dołącza do TEGO scope.
8. **Status 404 vs 410 to świadomie przyjęty ślad** (audyt REVIEW R3):
   komunikat jest identyczny, ale KOD odpowiedzi mówi, czy token kiedykolwiek
   istniał (404 = nigdy, 410 = był i przestał działać). Zostaje tak, bo przy
   entropii 256 bitów i limicie 60/min/IP wyrocznia jest bezużyteczna
   (trafienie w istniejący token trzeba najpierw wylosować), a rozróżnienie
   ratuje diagnostykę: „link wygasł" i „zły link" to dla właściciela listy dwa
   różne problemy. Frontend świadomie NIE korzysta z tej różnicy —
   `publicList.ts` mapuje 404 i 410 na jeden ekran, więc osoba z linkiem
   niczego się nie dowiaduje. Zmiana na „410 zawsze" wymaga decyzji, nie
   refaktoru.
9. **Od wdrożenia warstwy są TRZY, nie dwie** (ustalenie D7, 2026-09-05):
   dochodzi access log REVERSE PROXY. Caddy zapisuje pełny URI żądania, więc
   blok z dyrektywą `log` dla `pasnik.*` wpisze
   `/api/v1/public/lists/<pełny-token>` do pliku na hoście — poza aplikacją,
   poza Dockerem i poza wszystkim, co maskujemy dzisiaj. Token w takim logu
   działa: kto go przeczyta, otwiera listę bez logowania. **B18 ma wybrać
   jedno z dwojga i ZWERYFIKOWAĆ na realnym logu, nie na dokumentacji**:
   albo nie włączać `log` dla tego bloku w ogóle (reszta serwisów właściciela
   też go nie ma — wyjątkiem jest `toc`), albo użyć filtra pól Caddy'ego
   (`format filter`) i zamaskować ścieżkę. Sprawdzenie jest banalne: wejść na
   publiczny link i zgrepować plik logu po tokenie.
9a. Maskowanie w aplikacji działa w DWÓCH warstwach, bo obie piszą na stdout
   kontenera, i obejmuje DWIE ścieżki z tokenem: `/api/v1/public/lists/<token>`
   oraz trasę SPA `/l/<token>`, którą od BATCH_17 serwuje backend (ADR-014) —
   bez tego każde otwarcie linku z telefonu wpisywałoby token do logów prod
   (ustalenie `/security-review` B17, testy w `tests/unit/test_logging.py`):
   `mask_path()` w `RequestLoggingMiddleware` (nasz log) oraz
   `MaskPublicTokenFilter` na loggerze `uvicorn.access` (access log Uvicorna
   formatuje ścieżkę sam z `record.args` i o middleware nie wie). Druga warstwa
   doszła w BATCH_11 po ręcznym sprawdzeniu `docker compose logs app` — token
   wychodził tam w całości. Testy: `tests/unit/test_logging.py`.
10. **`checked_at` w publicznym PATCH (BATCH_12) NIE poszerza uprawnień tokenu.**
   Ciało nadal ma `extra="forbid"` i dwa pola: `checked` (co) oraz opcjonalne
   `checked_at` (kiedy zapadła decyzja — potrzebne kolejce offline, ADR-009).
   Osoba z linkiem nie zyskuje przez to nic nowego: mogła już odhaczać. Granica
   nadużycia jest ograniczona z DWÓCH stron — znacznik starszy niż zapisany jest
   ignorowany, a znacznik z przyszłości ponad 5 minut przycinany do czasu
   serwera, więc najgorsze, co da się zrobić, to „przypiąć" własny stan na te
   kilka minut. Wymagana jest strefa czasowa (naiwna data to 422).
11. **Snapshot listy w IndexedDB (BATCH_12)** trzyma WYŁĄCZNIE treść, którą
   serwer i tak pokazuje osobie z linkiem: `label`, ilość, kategoria, `checked`.
   Zero PII (02_DOMAIN §13.5). Token publiczny jest częścią klucza rekordu —
   akceptowalne, bo mieszka na tym samym urządzeniu, na którym jest URL z tym
   tokenem; do konsoli, logów ani raportów błędów nie trafia. Runtime cache
   service workera świadomie POMIJA `/api/v1/auth/*`, żeby odpowiedzi
   z `Set-Cookie` nie lądowały w Cache Storage.

## 6. Uploady

Dotyczy zdjęć (przepisy/produkty) i **paczek kopii danych** (transfer, B14):
- limity: obraz ≤ 10 MB (`IMAGE_MAX_UPLOAD_MB`), **paczka ≤ 100 MB**
  (`TRANSFER_MAX_ZIP_MB`) — obie konfigurowalne per instalacja od B17;
  MIME sniffing po treści (Pillow verify / sygnatura ZIP `PK`), nie po
  rozszerzeniu;
- **dwie połowy jednej ochrony (BATCH_17, ustalenie REVIEW R4 pkt 3)**:
  (a) `BodyLimitMiddleware` (`app/core/body_limit.py`) odcina ciało żądania
  PRZED aplikacją — endpointy uploadu dostają swój limit + 1 MB marginesu
  multiparta, cała reszta API `REQUEST_MAX_BODY_MB` (domyślnie 2 MB); 413
  w kształcie błędu 04_API §1 także dla ciała bez `Content-Length` (licznik
  na `receive()`); (b) rate limit per IP na trzech endpointach uploadu
  (`app/core/ratelimits.py`): zdjęcia 30/min, paczka kopii danych 10/min.
  Model zagrożeń §1 nie broni się przed członkiem rodziny, ale broni
  przed PRZEJĘTĄ sesją — bez limitu częstości jedyny koszt zapełnienia dysku
  Odroida to pętla `curl`;
- zapis pod losową nazwą na bind mount, poza web-rootem; serwowanie przez
  endpoint z autoryzacją (nie StaticFiles bez auth);
- **`/uploads/*` serwuje wyłącznie podkatalogi z ALLOWLISTY**
  (`core/uploads.SERVED_SUBDIRS`: `recipes`, `retail`, `transfer-import`).
  Do BATCH_20 była to lista ZAKAZANYCH i to był błąd konstrukcyjny: endpoint
  sprawdza tylko sesję, więc katalog, o którym kod przestał wiedzieć (bo
  funkcję wycofano), stawał się pobieralny dla każdego zalogowanego razem
  ze wszystkim, co w nim zostało. Katalog paczek (`transfer/`) świadomie nie
  jest serwowany — to KOMPLET danych jednego konta. **Nowy podkatalog uploadów
  = wpis w allowliście w tym samym batchu**;
- obrazy re-enkodowane przez Pillow (strip EXIF, usunięcie payloadów),
  miniatury generowane;
- **archiwum transferu** (BATCH_14, `transfer/importer.py`) przechodzi kontrolę
  w tej kolejności: limit rozmiaru PRZED otwarciem → sygnatura ZIP → lista
  wpisów (dozwolone WYŁĄCZNIE `export.json` i `photos/<nazwa>`; ścieżka
  absolutna, `..`, backslash i litera dysku odrzucają archiwum) → sumaryczny
  rozmiar po dekompresji i liczba wpisów liczone Z NAGŁÓWKÓW (zip-bomba pada
  przed rozpakowaniem czegokolwiek). Zdjęcia z archiwum idą przez ten sam
  `core/uploads.save_image`, co zwykły upload — dostają nowe, losowe nazwy
  i są re-enkodowane. **Plik eksportu nigdy nie niesie `password_hash` ani
  `shopping_lists.public_token`** (04_API, sekcja formatu).

## 7. Sekrety i konfiguracja

Wyłącznie env (pydantic-settings): `DATABASE_URL`, `SECRET_KEY`, limity
`TRANSFER_MAX_ZIP_MB` / `IMAGE_MAX_UPLOAD_MB` / `REQUEST_MAX_BODY_MB` (§6),
`DISK_MIN_FREE_MB`, `SPA_DIST_DIR`, `LOG_LEVEL`, `UVICORN_WORKERS`,
`FORWARDED_ALLOW_IPS` (komplet z opisem: `.env.example`).
`.env` w .gitignore od pierwszego commita; `.env.example` z placeholderami.
W prod: plik env na hoście `chmod 600` lub docker secrets.

**Od BATCH_20 aplikacja nie ma ANI JEDNEGO klucza do usługi zewnętrznej**:
D25 wycofało import jadłospisów razem z jego kluczem API, więc jedynym
sekretem w konfiguracji jest hasło do bazy w `DATABASE_URL`. Nowa integracja
wychodząca na zewnątrz = nowa decyzja właściciela, nie „dopisanie zmiennej".

**`SECRET_KEY` — stan faktyczny (decyzja BATCH_17, dług U13 z R1)**: zmienna
jest WYMAGANA, ale dziś NIEUŻYWANA w kodzie — identyfikatory sesji, tokeny
CSRF i tokeny publiczne pochodzą z `secrets.token_urlsafe(32)`, nie z podpisu
tym kluczem. Zostaje jako ZAREZERWOWANA (wariant „zostawić i dopisać to wprost"
z karty B17): usunięcie łamałoby każdy istniejący `.env`, compose i szablon
`pasnik.env` dla B18 bez zysku funkcjonalnego, a pierwszy podpisywany payload
(np. jednorazowy link resetu hasła) będzie miał klucz od razu. Nie wolno na tej
podstawie zakładać, że cokolwiek jest już nim podpisane.

**Zaufanie do `X-Forwarded-For` za proxy (BATCH_17, follow-up B02)**: obraz
prod uruchamia uvicorna z `--proxy-headers`, a lista zaufanych adresów to
`FORWARDED_ALLOW_IPS` (czyta ją sam uvicorn; domyślnie `127.0.0.1`). Tylko
połączenia z tych adresów mogą podstawić adres klienta — dla pozostałych
nagłówek jest ignorowany, więc klient nie ominie limitu logowania własnym
`X-Forwarded-For`. Podmieniony `scope["client"]` widzą jednocześnie slowapi
(`get_remote_address`) i `sessions.ip` (`accounts/router.py`). B18 wpisuje
adres bramy sieci compose (albo `*`, bo port aplikacji jest opublikowany
WYŁĄCZNIE na loopbacku hosta — wtedy jedynym nadawcą i tak jest Caddy).

Skan repo: `task secrets-scan` (gitleaks w kontenerze). Konfiguracja
`.gitleaks.toml` (od review R2, 2026-08-21) zachowuje WSZYSTKIE domyślne
reguły (`useDefault = true`) i wycisza wyłącznie dwa literały haseł testowych
(`haslo-testowe-2026`, `nowe-haslo-2026`) — wyciszenie jest po WZORCU, nie po
ścieżce, więc każdy inny sekret w tych samych plikach nadal wywala skan.
Bez tego skan zwracał 14 trafień, wszystkie na te dwa literały, i kończył się
kodem 1 na czystym repo, czyli przestawał być użyteczną bramką. Hasła testowe
nie otwierają żadnego środowiska: konta powstają komendą `task create-admin`
(prompt albo `PASNIK_ADMIN_*`), a w repozytorium nie ma działającego hasła (§2).

## 8. Logowanie i błędy

structlog: request id, user id (nie email), ścieżka, status, czas. NIGDY:
hasła, tokeny (sesyjne/publiczne/API), pełne payloady z danymi. Wyjątki:
stacktrace do logów, użytkownik dostaje generyczny komunikat + id błędu.
Audit log (02 §12) osobno od logów technicznych.

Stan po BATCH_17: w `APP_ENV=prod|test` **cały stdout kontenera jest
JSON-em** — także rekordy stdlib (`uvicorn`, `uvicorn.access`, biblioteki)
przechodzą przez `structlog.stdlib.ProcessorFormatter` z tym samym rendererem,
a maskowanie publicznego tokenu (`MaskPublicTokenFilter`) działa PRZED
renderowaniem. Poziom z `LOG_LEVEL` (aplikacja i uvicorn — `docker/
entrypoint.sh`). Silnik bazy ma `hide_parameters=True` (ustalenie REVIEW R4
pkt 7): komunikat `DBAPIError` nie niesie sekcji `[parameters: ...]`, więc
nieobsłużony błąd na INSERCIE do `sessions` nie wypisze tokenu sesji razem
z tracebackiem. Zweryfikowane grepem po realnym logu obrazu prod w B17
(login, publiczny link, upload): zero tokenów, zero haseł.

## 9. Zależności i baza

- `uv lock` + `npm lockfile`; podbicia zależności przy Review batchach
  (`pip-audit` / `npm audit` jako krok Review).
- PG: osobny user aplikacyjny bez SUPERUSER; port nie wystawiony poza
  sieć docker compose; hasło z env.

## 10. Checklisty bezpieczeństwa w procesie

Każdy batch ma sekcję Security (co dotyka i jak chroni). Review batche
uruchamiają `/security-review` (skill Claude Code) na całości zmian od
poprzedniego review. BATCH_17 (hardening) = pełny przegląd przed wdrożeniem.
