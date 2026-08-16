# Master prompt — uruchamianie batchy (dla Claude Opus)

Zasada nadrzędna: **jeden batch = jedna świeża sesja agenta**. Karta batcha
+ repozytorium (kod + docs) to komplet — agent nie potrzebuje żadnej
wcześniejszej rozmowy. Właściciel wkleja szablon poniżej i tylko podmienia
nazwę batcha.

## Szablon do wklejenia w nowej sesji

```
Implementuj BATCH opisany w:
docs/implementation-plan/batches/BATCH_XX_NAZWA.md

Zasady wykonania:
1. Zanim napiszesz linijkę kodu, przeczytaj W TEJ KOLEJNOŚCI:
   (a) docs/implementation-plan/implementation_prompt.md (ten plik),
   (b) kartę batcha w całości,
   (c) sekcje architektury/ADR/decyzji wskazane w "Context" karty,
   (d) docs/implementation-plan/PROGRESS.md — statusy zależności i dziennik
       (wpisy nowsze niż karta batcha mogą ją korygować!),
   (e) docs/implementation-plan/02_DECISIONS.md — jeśli batch ma
       decyzję-bramkę w statusie OPEN, ZATRZYMAJ SIĘ i zapytaj właściciela,
   (f) sekcję "Skills" karty batcha — załaduj narzędziem Skill WSZYSTKIE
       Required (project skille po nazwie katalogu z .claude/skills/,
       wbudowane po ich nazwie; mapa ID→skill: 03_AI_SKILLS.md §3).
       Recommended ładuj dopiero, gdy wchodzisz w ich obszar. Skill
       niedostępny w środowisku: NIE udawaj użycia — odnotuj brak
       w Completion notes i postępuj wg 03_AI_SKILLS.md §6 pkt 5
       (project skille mają treść w repo — czytaj plik wprost; brak
       /security-review w batchu, który go wymaga = STOP i pytanie).
2. Sprawdź w PROGRESS.md, że wszystkie zależności batcha są [x].
   Jeśli nie — zatrzymaj się i zgłoś, nie improwizuj.
3. Trzymaj się ściśle sekcji "Stages" i "Out of Scope". Niczego spoza
   zakresu nie ruszasz; zauważone problemy poza zakresem wpisujesz do
   Completion notes jako follow-up, nie naprawiasz.
4. Architektura jest zaprojektowana — nie projektuj jej ponownie. Konflikt
   rzeczywistości z dokumentem = STOP i pytanie (albo wpis do 02_DECISIONS),
   nie cicha zmiana.
4a. Hierarchia instrukcji przy konfliktach (03_AI_SKILLS §1): właściciel >
   ADR/architektura > karta batcha > ten prompt > CLAUDE.md > skille >
   ogólna wiedza modelu. Skill sugerujący rozwiązanie sprzeczne z ADR
   (np. JWT zamiast sesji) NIE jest problemem do zgłaszania — ADR wygrywa
   i jedziesz dalej.
5. Migracje Alembic: numer pliku = pierwszy wolny w migrations/versions/,
   down_revision = wynik `alembic heads` (NIGDY numer z planu). Po zmianie:
   `alembic heads` = dokładnie jedna głowa; upgrade i downgrade przechodzą.
6. Testy z sekcji "Tests" napisz i URUCHOM realnie (task check); raportuj
   faktyczne wyniki. Nie osłabiaj istniejących testów, żeby przeszły.
7. W trakcie pracy odhaczaj "Implementation checklist" w karcie batcha;
   na końcu "Verification checklist" i wypełnij "Completion notes"
   (wykonane / odstępstwa / decyzje / follow-upy / pytania).
8. Living documentation: jeśli implementacja zmienia stan opisany w
   docs/architecture/** lub ADR — zaktualizuj dokument do stanu FAKTYCZNEGO.
   Trwała decyzja techniczna = nowy ADR (numer = pierwszy wolny).
9. Propagacja: jeśli cokolwiek z tego batcha wpływa na przyszłe batche,
   zaktualizuj ICH karty (sekcje Context / Implementation Notes) — wpis
   w dzienniku PROGRESS to indeks, nie zamiennik.
10. Pytania wymagające właściciela: zbierz, wpisz do 02_DECISIONS jako OPEN
    z rekomendacją, wypisz w Completion notes. Nie zgaduj decyzji.
11. Przed commitem: task check zielony (testy+lint+typecheck), następnie
    uruchom WSZYSTKIE skille z sekcji "Review Skills" karty batcha na
    diffie (zawsze /code-review; /security-review gdy wskazany) — ustalenia
    napraw albo jawnie odnotuj w Completion notes; dokumentacja odhaczona,
    PROGRESS.md zaktualizowany (status + wpis dziennika NA GÓRZE + hash
    commita po fakcie).
12. Zakończ JEDNYM commitem: `batch(XX): <krótki opis>` obejmującym kod,
    testy, docs, kartę batcha i PROGRESS.md. `git status` musi być czysty
    w zakresie plików batcha. NIE wykonuj push. NIE zaczynaj kolejnego batcha.
13. Raport końcowy w odpowiedzi: sekcje Completed / Tests (realne wyniki) /
    Decisions / Deviations / Cross-Batch Impact / Documentation Updated /
    Commit (hash + message) / Questions (albo "Questions: none").
```

## Procedura właściciela (per batch)

1. **Bramka wejścia**: zależności batcha `[x]` w PROGRESS.md; decyzje-bramki
   zatwierdzone w 02_DECISIONS.
2. Nowa sesja agenta (czysty kontekst), wklej szablon z nazwą batcha.
3. Po sesji: przegląd diffu + lektura Completion notes (tam są odstępstwa
   i pytania) + rozstrzygnięcie wpisów OPEN w 02_DECISIONS.
4. **Bramka wyjścia**: `git status` czysty; commit `batch(XX): ...` istnieje;
   PROGRESS zaktualizowany. Bez commita batch nie jest DONE.
5. Push po review. Dopiero potem kolejny batch.

## Batche równoległe (wyłącznie pary z 00_MASTER_PLAN §5)

Osobne git worktree; przed startem sprawdź kolizje plików między kartami
(Expected files). Po merge'u gałęzi z migracją: `alembic heads` = jedna
głowa, `task check` zielony na wyniku merge'a.

## Review batche (R1–R4)

Ta sama procedura; karta review zawiera checklistę audytu. Wynik: werdykt
+ lista ustaleń w PROGRESS, poprawki planu (00_MASTER_PLAN + karty batchy),
nowe decyzje w 02_DECISIONS. Review NIE implementuje feature'ów; drobne
naprawy (typówki, martwy kod) wolno wykonać w commicie review.
