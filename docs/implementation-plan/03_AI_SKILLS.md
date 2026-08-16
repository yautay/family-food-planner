# 03 — AI skills i narzędzia jakości sesji implementacyjnych

Stan faktyczny (sprawdzony 2026-08-16): katalog skilli/pluginów organizacji
NIE zawiera gotowych paczek dla FastAPI/SQLAlchemy/Vue/Tailwind/
shadcn-vue/Playwright/Docker/PWA (wyszukiwania zwróciły pusto). Wniosek:
jakości między sesjami nie zapewni instalacja skilli z półki — zapewni ją
**własny project skill + CLAUDE.md + karty batchy**, dokładnie jak
w netQArnerze (skill `netqarner-framework`).

## Obowiązkowe (powstają w tym repo)

| Element | Kiedy powstaje | Jaki problem ogranicza |
|---|---|---|
| `CLAUDE.md` (root) | B01 | kontrakt repo dla każdej sesji: komendy task, zakazy (float w ilościach, kopiowanie stanu serwera do Pinia, endpoint bez testu scope), wskaźnik na master prompt |
| Project skill `.claude/skills/ffp-framework` | B01, rozbudowa w R1–R4 | skondensowany kontrakt kodowania: wzorzec modułu (router→service→models), ScopedQuery, konwencje Decimal/NUMERIC, wzorce frontendu (Query/Pinia, create-in-context), jak uruchamiać testy — ładowany przed pracą w `backend/**` lub `frontend/**` |
| `implementation_prompt.md` | już jest | procedura sesji batcha (odpowiednik netQArnerowego) |

## Wbudowane w Claude Code — używać w procesie

| Skill/narzędzie | Status | Kiedy | Co ogranicza |
|---|---|---|---|
| `/code-review` | dostępny | koniec każdego batcha (przed commitem) + Review batche na całości od poprzedniego review | bugi poprawności, nadmiarowa złożoność |
| `/security-review` | dostępny | Review R1–R4 + B17 obowiązkowo | podatności w zmianach (auth, tokeny, upload) |
| `anthropic-skills:pdf` | dostępny | sesje B15/B16 przy pracy z PDF-ami | poprawne użycie pdfplumber/pypdf |
| `skill-creator` | dostępny | B01 przy tworzeniu project skilla | poprawna struktura i triggering skilla |
| `anthropic-skills:xlsx` | dostępny | opcjonalnie: analizy danych referencyjnych | — |

## Świadomie NIE używane

- `nuxt-ui` skill — inny stack komponentów (my: shadcn-vue, bez Nuxta).
- `dataviz` — wykresy robimy własnymi prymitywami SVG (ADR-013);
  wytyczne kolorów mamy w 06_UIUX.
- Instalacja pluginów „na zapas" — katalog pusty dla naszego stacka,
  a nieużywany skill to szum kontekstu.

## Zasada

Rekomendację skilla wolno dodać do tej listy tylko z uzasadnieniem
„jaki problem jakościowy ogranicza" i miejscem w procesie (kiedy ładowany).
Review batche weryfikują, czy project skill nadąża za rzeczywistością repo.
