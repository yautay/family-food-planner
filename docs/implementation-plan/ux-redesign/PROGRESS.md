# Postęp przebudowy UX

Stan na 2026-10-29: przygotowano plan. Nie uruchomiono implementacji, agentów wykonawczych ani testów aplikacji w ramach tego programu. Akceptacja wyglądu nie jest oznaczeniem batchy jako wykonane.

Tylko orkiestrator aktualizuje ten rejestr. Reguły stanów i dowodów: [ORCHESTRATION.md](ORCHESTRATION.md).

| Batch | Stan | Właściciel | Baza/worktree | Dowód i commit integracji |
|---|---|---|---|---|
| UX00 | PLANOWANY | — | — | — |
| UX01 | PLANOWANY | — | — | — |
| UX02 | PLANOWANY | — | — | — |
| UX03 | PLANOWANY | — | — | — |
| UX04 | PLANOWANY | — | — | — |
| UX05 | PLANOWANY | — | — | — |
| UX06 | PLANOWANY | — | — | — |
| UX07 | PLANOWANY | — | — | — |
| UX08 | PLANOWANY | — | — | — |
| UX09 | PLANOWANY | — | — | — |
| UX10 | PLANOWANY | — | — | — |
| UX11 | PLANOWANY | — | — | — |
| UX12 | POZA_ZAKRESEM | — | — | nowe zlecenie |

## Rezerwacje

Brak. Przy starcie zapisz rezerwacje wspólnych plików, środowiska E2E i bazy: zasób, agent, batch, czas zajęcia, warunek zwolnienia. Nie zapisuj haseł ani zawartości `.env`.

## Decyzje i ograniczenia

- Wygląd: zaakceptowany kierunek „domowa książka kucharska”.
- Na dziś: wyłącznie planowanie; START_PROMPT nie został wykonany.
- Wykonawca UX00 weryfikuje skille review dostępne w docelowej sesji Sol oraz zgodność proponowanej orkiestracji z procedurą repo.
- Bilans osoby, trwałe zakończenie zakupów, osobiste ulubione, trwałe szkice i dopasowanie spiżarni: UX12. Brak tych funkcji nie może być maskowany tekstami z makiety.

## Dziennik

2026-10-29 — przygotowano 12 kart podstawowego programu UX00–UX11, kartę rozszerzeń UX12, specyfikację wyglądu, zasady orkiestracji i prompt. Kod aplikacji niezmieniony. Wyniki testów z wcześniejszych historycznych batchy nie są wynikami tego programu.

## Szablon wpisu po przekazaniu

```text
Data / batch / zadania:
Stan i właściciel:
Baza, worktree, commit/diff:
Spełnione kryteria:
Komendy, wyniki i niewykonane sprawdzenia:
Review i zrzuty ekranów:
Zmiany kontraktów oraz dokumentacji:
Blokery / następne zadanie / zwolnione rezerwacje:
```
