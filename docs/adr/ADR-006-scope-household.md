# ADR-006 — Scope PRIVATE/HOUSEHOLD; jeden household na użytkownika

Status: ACCEPTED (2026-08-16)

## Kontekst
Rodzina współdzieli przepisy, plany, szablony, listy i spiżarnię; część
danych bywa prywatna. Aplikacja domowa — bez skomplikowanych ACL.

## Decyzja
- Encje współdzielne mają `scope ∈ {PRIVATE, HOUSEHOLD}` + owner_user_id
  + household_id (wzorzec kolumn 03_DATABASE §4, egzekwowany mixinem
  `ScopedQuery` w jednym miejscu).
- Użytkownik należy do **maksymalnie jednej** rodziny (kolumna na users).
- Spiżarnia zawsze HOUSEHOLD (jeden stan domowy); edycja encji HOUSEHOLD
  przez każdego członka (zaufanie rodzinne + audit); zmiana scope
  i usunięcie — właściciel lub ADMIN.
- Słowniki (produkty kanoniczne, kategorie, tagi, sklepy, retail) —
  globalne per instancja.

## Konsekwencje
+ Autoryzacja to jedno zapytanie i jeden mixin; macierz testowa mała
  (08_TESTING §4).
− Przenosiny użytkownika między rodzinami zostawiają jego encje HOUSEHOLD
  w starej rodzinie (household_id nie podąża) — świadome, admin może
  przepiąć ręcznie; odnotować w dokumentacji admina.
