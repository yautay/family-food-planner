# UX00 — mapa funkcji i kontrakty do integracji przez O

Data audytu: 2026-10-29. Baza sprawdzona przez `git rev-parse HEAD`: `511a249aa570ad45f6d2569b5c07abdf94975948`.

To pomocniczy audyt kontraktów fali 0. Właścicielem UX00 pozostaje O. Dokument nie oznacza UX00 ani innej karty jako ukończonej. Dowody poniżej pochodzą z odczytu kodu i dokumentów, bez uruchomienia aplikacji, DB, seedów i E2E. Opisy „projektowane” są rekomendowanym kontraktem do zamrożenia przez O przed UX03; nie są opisem wdrożonego API.

Przeczytane źródła: `CLAUDE.md`, historyczny `implementation_prompt.md`, manifest `03_AI_SKILLS.md`, rejestry decyzji i postępu, README/DESIGN_SPEC/ORCHESTRATION programu, UX00, UX03, UX04, UX05, UX07, UX10 i UX12, architektura 02/04/05/06/08, ADR-006 z aneksem i ADR-008. Ścieżki w tabelach są względem korzenia repo; wymienione symbole pozwalają znaleźć konkretny kontrakt bez polegania na numerze linii.

## 1. Mapa zachowania istniejącego do nowych miejsc

W kolumnie „Istnieje” podano dowód z kodu. Kolumna „Nowe miejsce” jest planem UI, nie dowodem implementacji. Usunięcie widocznej pozycji z głównego menu nie usuwa funkcji ani adresu.

| Funkcja | Istnieje: ekran i konkretne źródło | Nowe miejsce / właściciel |
|---|---|---|
| Dzień, poprzedni/następny, dziś, odczyt pustej daty | `frontend/src/pages/plan-dnia/PlanDniaPage.vue` (`currentDate`, `goTo`, `emptyDay`); `api/planning.ts::fetchPlanDays/fetchPlanDay`; `backend/app/modules/planning/service.py::get_day` | Plan → Dzień, pasek dat; UX03. Pusty dzień dopiero po udanym odczycie |
| Dowolna nazwa posiłku, edycja nazwy/celu kcal, usunięcie i duplikat | `PlanDniaPage.vue::saveMeal/removeMeal/duplicateMeal`; `components/domain/MealCard.vue`; `planning/schemas.py::MealCreateRequest/MealUpdateRequest`; `planning/service.py::create_meal/update_meal/delete_meal` | Wiersz posiłku i menu rzadkich działań; UX03. Bez zamkniętej listy typów „śniadanie/obiad/kolacja” |
| Przepis w posiłku i mnożnik | `PlanDniaPage.vue::saveItem/changeServings`; `api/planning.ts::addItem/updateItem`; `planning/schemas.py::ItemCreateRequest` | Dodaj danie i wspólny panel; UX03. Zaplanuj z katalogu/szczegółu UX04, kontekst tygodnia UX07 |
| Produkt luzem w posiłku | `PlanDniaPage.vue::itemForm.mode/saveItem`; `ProductPicker.vue`, `AmountInput.vue`; `planning/service.py::_normalize_product_amount`; `catalog/units.py` | Nadal dostępne Dodaj produkt/menu posiłku; UX03. Nowy panel przepisu nie zastępuje tej ścieżki |
| Rozkład porcji na profile, wyczyszczenie rozkładu | `ServingsSplitDrawer.vue::reset/entries/total`; `PlanDniaPage.vue::saveSplit/clearSplit`; `planning/service.py::_replace_split/_assert_existing_split_matches` | Sekcja porcji panelu oraz edycja istniejącej pozycji; UX03. Historyczny podział zachowany |
| Dopasowanie porcji do celu posiłku | `PlanDniaPage.vue::askFit/applyFit`; `api/planning.ts::fitItemToTarget`; `planning/service.py::fit_to_target` | Menu dania → propozycja → jawne Zastosuj; UX03. POST propozycji nic nie zapisuje |
| Kopia dnia/posiłku, dopisywanie | `PlanDniaPage.vue::copyDay/duplicateMeal`; `planning/schemas.py::PlanCopyRequest`; `planning/service.py::copy/copy_block` | Dzień i Uzupełnij plan; UX03/UX07. Nowe ID, istniejące posiłki zostają |
| Tytuł i widoczność dnia przez API | `api/planning.ts::upsertPlanDay`; `planning/schemas.py::PlanDayUpsertRequest`; `planning/service.py::upsert_day` | Zachować kontrakt API i metadane dnia; UX03/UX07. Obecny PlanDniaPage wyświetla tytuł, ale nie ma formularza PUT; nie oznaczać tego jako utraconego przycisku |
| Tydzień, zakres, miniatury, przejście do dnia | `pages/tydzien/PlanTygodniaPage.vue::weekStart/weekDates/days` | Plan → Tydzień, agenda lub siatka według dostępnej szerokości; UX07 |
| Przeniesienie posiłku (DnD i przycisk) | `PlanTygodniaPage.vue::moveMealMutation/startMoveByButton/onDrop`: najpierw copy, potem delete | Zachować alternatywę przyciskową; UX07. Obecna operacja nie jest atomowa; błąd drugiego żądania może zostawić duplikat |
| Powielenie bloku, szablony dnia/tygodnia, cykle | `components/domain/planning/{BlockCopyDialog,TemplateSaveDialog,TemplateApplyDialog,CycleEditorDialog}.vue`; `api/templates.ts`; `backend/app/modules/planning/templates_service.py` | Uzupełnij plan z podglądem zakresu/ostrzeżeń; UX07. Semantyka backendu bez zmian |
| Historia ponownego użycia | `PlanTygodniaPage.vue::historyQuery/historyRange`; `planning/ReuseHistoryDialog.vue` | Uzupełnij plan → użyj wcześniejszego dnia; UX07. To historia dni planu, nie ogólny dziennik operacji |
| Katalog, wyszukiwanie, tagi AND, private/household/global, paginacja | `pages/przepisy/PrzepisyPage.vue::filters`; `api/pagination.ts::usePaginatedList/PAGE_SIZE` (50); `api/recipes.ts::fetchRecipes`; `recipes/service.py::list_recipes` | Przepisy, filtry w URL i powrót do wyników; UX04. „Do 30 minut” projektowane przez istniejące `prep_time_max=30` |
| Szczegół, skalowanie składników i wartości, oceny 1–5 | `PrzepisSzczegolPage.vue::servings/rate`; `api/recipes.ts::fetchRecipe/rateRecipe`; `recipes/schemas.py::RatingRequest` i `recipes/models.py::RecipeRating` | Przepisy → szczegół z równoczesnymi składnikami/przygotowaniem i Zaplanuj; UX04 |
| Tagi, w tym systemowy „ulubione” | `PrzepisEdytorPage.vue`, `lib/schemas/recipe.ts`; `api/recipes.ts::fetchTags/createTag`; `recipes/models.py::Tag`; `lib/texts.ts::recipes.favoriteTag` | Tagi nadal edytowane w uprawnionym edytorze; UX04/UX08. Serce nie jest osobistą zakładką i nie edytuje globalnego przepisu USER-owi |
| Edytor przepisu, składniki z produktem tworzonym w kontekście, zdjęcie | `PrzepisEdytorPage.vue`; `ProductPicker.vue/ProductCreateDrawer.vue`; `api/recipes.ts::createRecipe/updateRecipe/uploadRecipePhoto/deleteRecipePhoto`; `backend/app/core/uploads.py` | Sekcje edytora + ochrona niezapisanych zmian; UX08. Zdjęcie rzeczywiste lub ilustracja zastępcza w UX04 |
| Kopia przepisu, archiwizacja, usunięcie, zakres i role | `PrzepisSzczegolPage.vue::canEdit/canManage/canCopy`; `api/recipes.ts::copyRecipe/archiveRecipe/deleteRecipe`; `recipes/service.py`; `backend/app/core/scope.py` | Menu szczegółu i edytor; UX04/UX08. Globalny czytelny i planowalny dla zalogowanych, treść/zdjęcie/scope/delete/archive tylko ADMIN |
| Zapisane listy po odświeżeniu | `api/shoppingLists.ts::fetchShoppingLists`, `queryKeys.shopping.listsIndexFiltered`; obecne `ZakupyPage.vue::createdLists` to lokalny ref po finalizacji | Zakupy → trwały indeks list; UX05. Podłączenie już istniejącego API jest zmianą UI, nie nową domeną |
| Generator, tury, jawna spiżarnia, podgląd, rozstrzyganie braków i wariantów | `ZakupyPage.vue`, `ZakupyPreview.vue`, `RoundConfigSection.vue`; `stores/shoppingDraft.ts`; `api/shopping.ts`; `shopping/service.py/engine.py` | Zakupy → zakres → podgląd → utworzenie, konfiguracja niżej; UX05. `use_pantry=false` bez domyślnego odjęcia |
| Odhaczanie, mam w domu, resztka, sklep i kolejność serwera | `ListaZakupowPage.vue::toggle/changeStore`; `ShoppingItemRow.vue`, `StorePicker.vue`; `shopping/lists_service.py/sorting.py` | Lista w sklepie; UX06. Ilości i długie nazwy czytelne, kolejność nie przeliczana w kliencie |
| Publiczny link, QR/systemowe udostępnianie, odwołanie i druk | `ShareListDialog.vue`; `ListaZakupowPage.vue::printList`; `PublicznaListaPage.vue`; `api/publicList.ts`; `assets/print.css`; `shopping/public_router.py` | Akcje listy, `/l/:token` poza rodzinną nawigacją; UX06. Publiczne tylko odczyt i checkboxy |
| Zakupy offline, odzyskanie po reload, LWW | `stores/offlineQueue.ts`; `lib/offline/{db,hydrate,clock,sync}.ts`; `OfflineBanner.vue`; `main.ts`; `shopping/lists_service.py::_apply_item_changes` | Lista prywatna i publiczna; UX06. Zmiana sklepu i przyjęcie do spiżarni nadal wymagają sieci |
| Przyjęcie odhaczonych zakupów, usunięcie listy | `ListaZakupowPage.vue::accept/remove`; `api/shoppingLists.ts`; `shopping/lists_service.py::accept_to_pantry`; `pantry/service.py::receive_purchase` | Jawne akcje z potwierdzeniem; UX06. Stempel `received_at` per pozycja i jedna transakcja; bez automatycznego przyjęcia |
| Spiżarnia: CRUD partii, ilości, daty, search/kategoria/sortowanie, siatka/lista | `pages/spizarnia/SpizarniaPage.vue`; `PantryItemRow.vue/PantryItemCard.vue`; `stores/pantryView.ts`; `api/pantry.ts`; `pantry/service.py` | Spiżarnia, produkty do szybkiego zużycia i paginacja 100; UX09. Jeden stan rodziny; członek może usuwać (D17) |
| Produkty, jednostki domowe, miara/waga sztuki, wartości/weryfikacja/archiwum/usunięcie | `pages/produkty/{ProduktyPage,ProduktFormPage}.vue`; `api/catalog.ts`; `catalog/service.py/units.py`; `ProductCreateDrawer.vue` | Biblioteka pomocnicza z przepisów i ustawień; UX09. Zachować D13/D15, 409 `used_in`, konwersje i stronę 50 |
| Produkty sklepowe, opakowania, marka, zdjęcia i sklep | `RetailProductsSection.vue/RetailProductCreateDrawer.vue`; `api/retail.ts`; `catalog/retail_service.py` | Produkt → warianty sklepowe; UX09. Generator może nadal tworzyć wariant w kontekście |
| Sklepy i kolejność kategorii (DnD + strzałki) | `SklepySection.vue/StoreCategoryOrderEditor.vue/StorePicker.vue`; `api/stores.ts`; `catalog/stores_service.py` | Dom i ustawienia → Zakupy; UX10. Profile sklepu mają jednego właściciela UX10 |
| Profile gotujących/jedzących, aktywność, mnożnik i kcal_goal; osobno konta dostępu | `UstawieniaPage.vue::profiles/members/toggleActive`; `api/households.ts`; `households/schemas.py::MemberProfileRead`; admin users/households | Dom i ustawienia → Rodzina; UX10. Nie wiązać profilu z kontem po imieniu |
| Cele historyczne i progi konta | `UstawieniaPage.vue::saveGoal/saveThresholds`; `api/goals.ts`, `api/auth.ts`; `nutrition/service.py` | Dom i ustawienia → Moje cele; UX10. Zachować dane i `valid_from` |
| Statystyki: do 92 dni, luki, cele schodkowe, średnie, niepełne dane | `StatystykiPage.vue`; `components/charts/{BarChart,TrendLine}.vue`; `api/stats.ts`; `planning/stats_service.py/schemas.py` | Plan → Podsumowanie; UX10. Dane opisują plan, nie faktyczne spożycie osoby |
| Kopia rodziny, dry-run, kolizje, ostrzeżenia/scalenia, import ZIP/JSON | `UstawieniaPage.vue::exportData`; `TransferImportDialog.vue`; `api/transfer.ts`; `transfer/{service,serializer,importer}.py` | Dom i ustawienia → Dane; UX10. Własne private + rodzinne household, bez private innych członków (D26) |
| ADMIN: konta, role/reset/aktywność, rodziny/przypisanie, weryfikacja, kopia instancji | `pages/admin/{AdminUsersPage,AdminHouseholdsPage,AdminWeryfikacjaPage,AdminDanePage}.vue`; `api/adminUsers.ts/adminHouseholds.ts`; `router.ts::authGuard` | Administracja tylko ADMIN, spójny wygląd; UX10. Bez nowych uprawnień i bez zmiany znaczenia eksportu instancji |
| Logowanie, sesja, wylogowanie, powrót po login | `LoginPage.vue`, `stores/auth.ts`, `api/auth.ts`, `layouts/AppShell.vue`, `router.ts::authGuard` | Logowanie i przycisk konta, UX02/UX10. Sesje i CSRF zachowane |
| Dziennik audytu API (bez istniejącego ekranu) | `backend/app/modules/audit/{router,service}.py`; brak trasy `/admin/audit` w `router.ts` | Zachować API; nie dodawać fikcyjnego ekranu historii w ramach tej mapy |

## 2. Kontrakty istniejące i ograniczenia

- `frontend/src/router.ts` zawiera stabilne nazwy i adresy: `plan-dnia`, `tydzien`, `statystyki`, `przepisy` i szczegół/edytor, `zakupy` i `zakupy-lista`, `spizarnia`, `produkty` i formularz, `ustawienia`, cztery trasy admina, `login`, `publiczna-lista`. UX02 grupuje Plan/Przepisy/Zakupy/Spiżarnia, z Dniem/Tygodniem/Podsumowaniem pod Planem. Zachować URL i powroty. Detale/edytory dziedziczą aktywną sekcję. Publiczne `/l/:token` omija `auth.ensureLoaded()` i `AppShell`.
- Serwer = TanStack Query, klucze w `frontend/src/api/queryKeys.ts`. Pinia przechowuje UI/kolejkę, nie kopię dnia, przepisu ani podglądu. Paginacja `usePaginatedList` trzyma offset w `pageParam`, nie w kluczu. Błąd kolejnej strony nie usuwa już pobranych pozycji.
- `frontend/src/api/planning.ts` obecnie zwraca `DayRead` z mutacji posiłku/pozycji; copy zwraca `DaysResponse`, fit zwraca `FitToTargetResponse`. `ItemUpdateRequest` NIE ma `recipe_id`. `create_meal` i `add_item` osobno commitują; ich sekwencja nie gwarantuje rollbacku pustego posiłku.
- `planning/schemas.py`: nazwa posiłku 1–100 znaków po trim; `servings` >0 i <=9999.99 (2 miejsca), multiplier profilu >0 i <=99.99 (2 miejsca), max 20 wpisów podziału; produkt luzem quantity >0 i <=99999.999 (3 miejsca), ilość wymaga jednostki. XOR przepis/produkt. Suma podziału dokładnie równa servings; duplikaty profili i profile spoza rodziny dnia odrzuca serwis. Brak podziału `[]` jest legalny.
- PATCH `servings_split` pominięte zachowuje podział, `[]` go usuwa. Zmiana samego servings z istniejącym podziałem musi nadal zgadzać się z jego sumą. Obecny `ServingsSplitDrawer::reset` uzupełnia brakujące osoby wartościami domyślnymi nawet przy częściowym podziale — UX03 ma nie włączać samoczynnie osób, które świadomie pominięto.
- `planning/service.py::_resolve_day`: odczyt preferuje własny dzień przed widocznym rodzinnym, dalej najstarsze ID. Zapis adresowany datą używa `select_owned`; nie może wybrać ADMIN-owi cudzego dnia tylko dlatego, że ADMIN go widzi. Jawne meal/item ID korzystają z widoczności całego łańcucha. D16 dopuszcza edycję treści przez ADMIN-a po jawnym ID; nie zawężać jej przy okazji redesignu.
- `planning/service.py::_build_days` sumuje wszystkie pozycje dnia i dobiera cele konta z `goals_of(user.id)`; nie liczy żywienia profilu. Sam split nie jest wynikiem per osoba. `DayRead.goal_progress` nie uprawnia do „Bilans Oli” ani porównania rodzinnej sumy z jej celem. UI: „Cały plan”, dane kompletne/niepełne; indywidualną ocenę ukryć, gdy podstawa porównania nie jest jednoznaczna. Cel konkretnego posiłku nadal ma istniejące znaczenie.
- Globalny jest wyłącznie RecipeScope; pozostałe encje mają private/household. Planowanie reużywa `_assert_recipe_available` (`allow_global=True`). UI nie może wymagać edytowalności przepisu do jego zaplanowania.
- `ShoppingListStatus` w `shopping/schemas.py` ma active/expired; `shopping/models.py` nie ma `completed_at`. Wygaśnięcie/publiczny link i licznik checkboxów nie oznaczają trwałego zakończenia. Brak ręcznych pozycji listy (D18). PDF importer runtime został usunięty (D25); narzędzie pdf-extract nie jest ekranem aplikacji.

## 3. Projektowany wspólny panel przepisu — kontrakt dla UX03/UX04/UX07

### Kontekst nawigacji ustalony w UX02

`lib/navigation.ts`: `PlanNavigationContext {selectedDate, from, to}`,
`validNavigationDate`, `navigationRange`, `planNavigationContext` oraz
`planNavigationTarget`. Query `selectedDate/from/to` niesie lokalne dni ISO;
from/to są włącznie i tworzą poprawną parę do 92 dni. Parametr date dnia
jest nadrzędny; weekStart wyznacza tydzień i dopuszczalny selectedDate.
Strzałki zachowują offset dnia, bieżący tydzień jawnie wybiera dziś.
Podsumowanie odczytuje/synchronizuje poprawny zakres URL, nie nadpisując
niepełnego szkicu. UX05 przejmuje ten sam query przez `navigationRange`;
link Zakupy z planu niczego nie zapisuje. Po odbiorze UX02 zmiany helperów
wymagają uzgodnienia z O, aby obie równoległe karty miały tę samą podstawę.

### Panel przepisu

Komponent wdrożony w UX03: `frontend/src/components/domain/planning/RecipePlanningPanel.vue`. Istniejący `PlanningDialog.vue` pozostaje wspólną oprawą operacji tygodnia do czasu uzgodnienia z UX07. Panel przepisu korzysta bezpośrednio z ActionPanel; nie jest zmianą samej oprawy tygodnia.

Wejście wdrożone w UX03 (kontrakt dla UX04/UX07):

| Pole | Typ/znaczenie |
|---|---|
| `open` | boolean; otwarcie kontrolowane przez konsumenta |
| `recipe` | `RecipeSummary` lub null (alias z wygenerowanego API); null pozwala wybrać przepis z dnia/tygodnia |
| `date` | lokalna data ISO `YYYY-MM-DD`; jawnie pokazana w panelu, bez UTC przesuwającego dzień |
| `meal` | `PlanMeal` lub null; istniejący posiłek z załadowanego dnia podanej daty |
| `replaceItem` | `PlanItem` lub null; tylko pozycja przepisu należąca do wskazanego posiłku |

Dane domenowe korzystają z aliasów `api/planning.ts` i `api/recipes.ts`, bez ręcznych interfejsów odpowiedzi HTTP. Podpisy zdarzeń komponentu to kontrakt UI: `close()` oraz `saved({ day: PlanDay, mealId: number, itemId: number, mode: 'add' | 'replace' })`. `saved` jest emitowane po potwierdzonej odpowiedzi serwera, z rzeczywistymi ID, nigdy ze szkicu formularza.

- W trybie dodawania data i posiłek mogą być wybrane w panelu; istniejący kontekst wstępnie je ustawia. Zmiana daty resetuje wybrany meal/item i pobiera właściwy dzień. W zamianie data/posiłek/pozycja są stałe, zmienia się przepis. Niespójne propsy nie mogą wysłać zapisu do innej daty.
- Dwa tryby porcji: sama liczba z pustym podziałem albo rodzinny podział. Dla nowej pozycji domyślne mnożniki są jawną propozycją; wybór rodzinnego trybu wymaga widocznej decyzji. Dla istniejącej pozycji start z zapisanych wartości, bez dopisywania nieobecnych profili. Historyczny/inaktywny wpis jest widoczny i nie znika przy otwarciu.
- W trybie rodzinnym 0/puste/wyłączona osoba nie trafia do payloadu; pozostałe wartości dodatnie, 2 miejsca i maksima jak API. `sumDecimals` daje servings; nie ma drugiego pola wymagającego ręcznego dopasowania sumy. Wszystkie osoby wyłączone blokują rodzinny zapis. Bez profili nadal można podać samą liczbę porcji. Błąd pobrania profili jest błędem, nie potwierdzonym brakiem osób.
- Brakujące wartości odżywcze są opisane przez `complete/missing`; formularz nie wylicza ich na JS. Polskie przecinki normalizuje `lib/decimal.ts`; liczby API jako stringi.
- Stan formularza jest lokalny; serwerowy dzień/profile/przepis w Query. Po sukcesie unieważnić `queryKeys.planDays.all` i `queryKeys.stats.all`; nie unieważniać przepisów, spiżarni ani istniejącego snapshotu generacji zakupów bez przyczyny. Konsument dostaje zapisany dzień. UX04 oferuje/przeprowadza przejście do `plan-dnia` z `day.day`; UX07 pozostaje w widocznym tygodniu i odświeża zakres.
- Zablokować ponowny submit podczas pending. Walidacja/API 4xx zachowuje szkic i pokazuje błąd przy polu lub role=alert. Po utracie odpowiedzi POST stan jest „Nie udało się potwierdzić zapisu”: odczyt dnia, pokazanie rzeczywistego wyniku; bez automatycznego drugiego POST i bez obietnicy exactly-once. Zbieżne wiersze nie są dowodem, który request je utworzył; przy niepewności użytkownik dostaje jawny stan i link do planu.
- Desktop drawer, telefon dostępny dialog z przewijalnym środkiem i osiągalną stopką. Jeśli modal: prawdziwe role=dialog/aria-modal, etykieta, początkowy fokus, Tab/Shift+Tab w panelu, Escape/zamknij, powrót do wywołującego, zablokowana interakcja tła. Samo `aria-modal` na istniejącym `role=group` nie wystarcza. Zagnieżdżony picker/create-in-context nie gubi szkicu ani fokusu.

## 4. Rozszerzenia domenowego API wdrożone w UX03

Poniższy kontrakt zaproponowano w historycznym audycie UX00, następnie zamrożono i wdrożono w UX03. Nie wymagał nowej tabeli ani migracji; istniejące modele przechowują wszystkie dane.

### Dodanie przepisu do nowego albo istniejącego posiłku

`POST /api/v1/plan/days/{date}/recipe-items`, 201:

```json
{
  "meal_id": 123,
  "recipe_id": 456,
  "servings": "3.30",
  "servings_split": [
    {"member_profile_id": 11, "multiplier": "1.10"},
    {"member_profile_id": 12, "multiplier": "1.10"},
    {"member_profile_id": 13, "multiplier": "1.10"}
  ]
}
```

Wariant nowego posiłku: zamiast `meal_id` pole `new_meal_name` (np. „Późny obiad po spacerze”). Dokładnie jeden z `meal_id`/`new_meal_name`, nazwa według MealName. `recipe_id` wymagane; servings domyślnie „1”, servings_split domyślnie `[]`, zgodnie z obecnym ItemCreate. Nowy posiłek ma cel null i pozycję na końcu; jego dalsza edycja celu pozostaje istniejącą akcją. Ten wąski endpoint nie tworzy produktu luzem ani nie ustawia nowego scope.

Odpowiedź projektowana: `{ "day": DayRead, "meal_id": int, "item_id": int }`. Identyfikatory muszą należeć do zwróconego dnia. Nowy envelope pozwala wskazać faktyczną pozycję bez porównywania dwóch list przy współbieżności; istniejące endpointy pozostają kompatybilne. Typ nowej odpowiedzi wygenerować przez `task fe-types`, bez ręcznego TS.

Serwis wykonuje jedną transakcję: rozstrzygnięcie/autoryzacja dnia albo istniejącego meal ID → zgodność daty → widoczność przepisu → limity posiłków/walidacja splitu → utworzenie brakującego dnia/posiłku i pozycji → jeden commit → serializacja faktycznego zmienionego dnia. Nie woła publicznej metody, która commituje w środku. Każda odmowa pozostawia stan sprzed operacji, łącznie z brakiem pustego dnia/posiłku. Sam odczyt pustej daty nie tworzy wiersza.

Statusy: anonim 401, brak/niepoprawny CSRF 403, niewidoczny meal 404, widoczny meal z innej daty 422 (bez zapisu), niedostępny przepis/profil, niespójna suma lub niepoprawny XOR 422 jak obecne reguły. Rozstrzygnięcie daty bez ID zachowuje granicę `select_owned` dla ADMIN-a; jawny meal ID zachowuje dopuszczalną edycję treści D16. Nie wprowadzać automatycznego dostępu do prywatnych danych rodziny.

### Atomowa zamiana przepisu

Addytywne `recipe_id: int >=1` w `PATCH /api/v1/plan/items/{item_id}`. Pominięte pole = dotychczasowa edycja; null nie jest konwersją ani usunięciem przepisu. Podanie recipe_id dla produktu luzem = 422. Dostęp/widoczność nowego przepisu jak przy dodawaniu. Bez DELETE+POST.

Przy samym recipe_id pozostają: item.id, meal ID, pozycja, servings i cały zapisany split. Serwer przelicza nutrition z nowego przepisu. Jeśli panel zmienia też porcje, przesyła zgodne servings/split w tym samym PATCH. Błąd walidacji/uprawnień pozostawia poprzedni przepis i podział. Odpowiedź pozostaje DayRead; panel zna item ID i potwierdza jego obecność oraz docelowy recipe ID w odpowiedzi.

UX00 wykrył, że `add_item/update_item` potwierdzały zapis przez resolver daty. UX03 serializuje faktycznie zmieniony day ID i obejmuje regresją jawny cudzy dzień ADMIN-a oraz jego własny dzień o tej samej dacie. Reguły widoczności i D16 pozostają bez zmian.

Testy UX03 obejmują pełną macierz ról/scope, globalny przepis, profil obcej rodziny, złą datę meal ID, brak CSRF, XOR, granice liczb, istniejący split, rollback nowego dnia/posiłku i zachowane ID zamiany. Źródła: `test_recipe_scheduling_api.py`, `test_recipe_scheduling.py`, `test_recipe_scheduling_schemas.py` oraz dotychczasowe testy planowania. Vitest panelu i `ux-planning.spec.ts` obejmują błędy, cache i utratę odpowiedzi po rzeczywistym zapisie; `recipe-global.spec.ts` sprawdza planowanie globalnego przepisu przez USER-a. Faktyczne wyniki i zakres odbioru pozostają w PROGRESS, bez przypisywania tych testów historycznemu audytowi UX00.

## 5. Reguły braku danych i odstępstwa od makiety

| Stan | Oczekiwane zachowanie nowego UI |
|---|---|
| Pierwsze ładowanie | Loading/skeleton; bez fałszywego „brak planu” i bez aktywnych akcji zależnych od nieznanych danych |
| Udany brak planu | Dla pojedynczego GET `DayRead.id=null`; dla zakresu brak dnia w items. Pokazać pusty dzień i działające Dodaj; nie zastępować błędu zerami |
| Pusta lista / brak wyników filtra | Rozróżnić pierwszy przepis/produkt/listę od wyzerowanych wyników wyszukiwania |
| Błąd bez cache | Jawny błąd z ponowieniem odczytu; nie renderować go jako pustego planu/katalogu |
| Błąd refetch z cache | Zachować dane, opisać nieudane odświeżenie; nie usuwać wyników i szkicu |
| Błąd kolejnej strony | Zachować pobrane wyniki i ich kolejność; ponów przy Pokaż więcej |
| Brak zdjęcia / błędny obraz | Ilustracja zastępcza; bez pozorowania fotografii i bez rozbicia wysokości karty |
| Brak/niepełny podział lub brak profili | Nie dzielić wartości po równo i nie zgadywać konta; zachować porcje i jawnie opisać stan |
| Niepełna nutrition | Pokazać flagę i missing, bez udawania pełnego bilansu |

Makieta jest referencją wyglądu, wariant „Przed” rekonstrukcją. Nie kopiować jej dat, imion, kalorii ani komunikatów sukcesu. Zmiana historycznego braku filtrów czasu w 06_UIUX §4.2 jest jawnie projektowana w UX04: tylko „Do 30 minut” przez istniejące API; nowe filtry trudności/oceny nie wchodzą do karty.

Odroczone UX12: bilans osoby, zakończenie/archiwum zakupów, osobiste ulubione, trwałe szkice, dopasowanie przepisów do spiżarni i tryb gotowania. UX08 chroni wyjście z niezapisanego formularza, ale nie obiecuje trwałego szkicu. UX09 nie udaje filtra „masz wszystkie składniki”. Druk istnieje jako `window.print`; osobny eksport listy do PDF nie jest nową funkcją tego programu.

## 6. Konkretny scenariusz danych UX00 — wyłącznie specyfikacja

Nie wykonano żadnego zapisu do DB. O przygotowuje poniższy zestaw dopiero po identyfikacji bezpiecznego, odrębnego środowiska. To plan danych do fixture/API setup, nie instrukcja czyszczenia obecnej bazy użytkownika. Nie używać produkcji ani danych osobowych. Powtarzalność: identyfikować dane po prefiksie `UX00 kontrakty v1`, zachowywać zwrócone ID w lokalnym manifeście przebiegu; ponowny setup reużywa własne dane albo tworzy nowy prefiks, bez globalnego purge.

| Zestaw | Konkretne dane i powód |
|---|---|
| Rodzina A | „UX00 kontrakty v1 — Dom A”; dwa konta USER A1/A2 i osobny ADMIN do prób roli; trzy profile „Łucja”, „Michał”, „Żaneta”, default_multiplier `1.10` każdy. Konta i profile to osobne encje; profil nie wymaga konta |
| Granice dostępu | Osobna rodzina B z USER B1/profilem „Błażej”; prywatny przepis A2 niewidoczny dla A1; household A widoczny A1/A2; globalny G1 utworzony przez ADMIN widoczny także B1. Osobny USER bez rodziny/profili do samej liczby porcji |
| Produkty | P1 masa: „UX00 kontrakty v1 — Płatki owsiane pełnoziarniste z otrębami i pestkami dyni”, pełna nutrition, przelicznik łyżka `10` g; P2 objętość (ml); P3 sztuki z piece_weight_g; P4 z brakującą nutrition. Wszystkie ilości/nutrition jako stringi/Decimal; użyć dozwolonych kategorii |
| Przepisy | R1 household ze zdjęciem testowym bez danych prywatnych, R2 private bez zdjęcia, G1 global bez zdjęcia; R3 nazwa: „UX00 kontrakty v1 — Pełnoziarnista zapiekanka z pieczoną papryką, cukinią i serem” (test co najmniej 80 znaków, w granicy API). R4 składnik P4 do flagi missing; R5 z prep_time_min=30, R6=31 i R7=null do filtra UX04. Systemowy ulubione + własny tag; ocena 1 i 5 różnych kont |
| Pusty dzień | `2031-01-05`: żadnego PUT ani posiłku; GET zwraca id=null. Nie tworzyć „pustego” dnia z tytułem, bo to inny przypadek |
| Dzień bez podziału | `2031-01-06`, dowolny posiłek „Późny obiad po spacerze”, cel `600`; R1 servings `3.30`, split `[]`; P1 luzem quantity `1.5`, unit „łyżka”, servings `1`. Pokazuje porcje bez przypisania osób i konwersję produktu |
| Dzień z częściowym podziałem | `2031-01-07`, R2 servings `2.20`, tylko Łucja/Michał po `1.10`; Żaneta nie je. To częściowe pokrycie osób, ale pełna zgodność sumy. Payload o servings 3.30 i split 2.20 to osobny oczekiwany błąd 422, nie legalny stan |
| Pełny i historyczny podział | `2031-01-08`, G1 servings `3.30`, wszystkie trzy profile po `1.10`; po zapisaniu można dezaktywować jeden profil, aby sprawdzić odczyt historyczny. UI 0 dla tej osoby przy nowym zapisie ma pominąć ją i dać sumę `2.20` |
| Granica dat / kopie / szablony | Tydzień `2030-12-30`–`2031-01-05`, dzień z istniejącym posiłkiem jako cel kopiowania. Szablon dnia i tygodnia, cykl A→B, jeden szablon z archiwalnym przepisem do ostrzeżenia; puste źródło osobno |
| Paginacja | 55 przepisów o wspólnym prefiksie (w tym R1–R7/G1) oraz 55 produktów; nazwy numerowane `001`–`055`, tak by końcowe 5 nie trafiło na stronę 50. Dla spiżarni 105 partii rozłożonych na kilka produktów; nie mylić stron katalogu 50 i spiżarni 100 |
| Sklep / opakowania | Dwa sklepy z odwróconą kolejnością dwóch kategorii; wariant P1 w opakowaniu `500` g i `1000` g; pozycja bez retail oraz already_have. Sprawdzić kolejność serwera i widoczną resztkę |
| Zakupy | Własna generacja z dni 06–08 stycznia, raz `use_pantry=false`, osobna z jawnym true; jedna oraz wiele tur. Zapisana lista aktywna i wygasła, jedna pozycja received_at, jedna odhaczona nieprzyjęta, jedna nieodhaczona. Bez stanu completed i bez ręcznych pozycji |
| Offline | Lista prywatna i osobny token publiczny: pobrać online, odłączyć sieć, odhaczyć, odświeżyć stronę, przywrócić sieć; porównać końcowy stan serwera. Osobno 404/410 i starszy checked_at. Nie zapisywać tokenów w śledzonym dokumencie ani zrzucie |
| Braki i błędy | Deterministyczne przerwanie GET bez cache, refetch z cache i doładowania drugiej strony; timeout odpowiedzi POST po rzeczywistym zapisie; błędny obraz przez stub/fixture. Nie psuć danych użytkownika, by uzyskać błąd |

Powyższe daty leżą w oknie 2030+, które istniejący setup E2E potrafi czyścić. Dlatego zestaw nie może współdzielić DB z równoległą suitą; O rezerwuje środowisko albo używa izolowanej bazy. Sam `task db-seed-demo` nie spełnia scenariusza: `backend/scripts/seed_demo.py` ma 15 produktów, 5 przepisów, tydzień od `2026-08-24` i pierwszego ADMIN-a, nie tworzy rodziny z trzema profilami ani wielostronicowego katalogu.

Implementacja fixture może reużyć `backend/tests/factories.py::{create_household,create_member_profile,create_recipe,create_plan_day,create_plan_meal,create_plan_item,create_item_split,create_shopping_list}` w izolowanych testach; ręczny scenariusz UI przygotowywać przez istniejące API z autoryzowanymi kontami, nie SQL. Obecne `frontend/e2e/cleanup.ts` ma szerokie sprzątanie okna lat 2030+; nie uruchamiać go na cudzych danych w imię przygotowania UX00.

Plan dowodów wizualnych dla O: Dzień 06/07/08 + pusta data, katalog z długą nazwą/zdjęciem/brakiem, R1/R2/G1, tydzień przełomu roku, indeks zakupów i lista prywatna/publiczna. Każdy krytyczny ekran na telefonie i desktopie; matryca docelowa 360/390/768/1024/1440 px, kontrola 320 px i powiększenia. W tym audycie nie wykonano zrzutów działającego UI.

## 7. Przekazanie, własność i ograniczenia

Jedyny zmieniany plik tej roli: `docs/implementation-plan/ux-redesign/CONTRACTS.md`. UX00.2/UX00.5 otrzymują mapę i propozycję kontraktu, UX00.3 specyfikację danych; ich wdrożenie/odbiór pozostają u O. UX00.1 i UX00.4 (środowisko, bramki, zrzuty) nie były zadaniem tego audytora.

UX03 rezerwuje panel, dzień/MealCard/ServingsSplitDrawer, API planning, schematy/router/service planning, OpenAPI i generated.ts oraz wymagane klucze/teksty. UX04/UX07 konsumują uzgodniony panel, bez własnego POST/PATCH do tej samej intencji. UX05 nie zmienia planning/OpenAPI. Pliki wspólne i dokumentacja architektury wyłącznie według rezerwacji O; ten audyt nie edytuje PROGRESS, decyzji ani kart.

Sprawdzenia wykonane: odczyt plików, wyszukiwanie `rg`, `git status --short` (czysto przed zmianą), `git rev-parse HEAD` (baza zgodna). Odczyt git wymagał eskalacji przez granicę sandboxa worktree; konfiguracji git nie zmieniano. Przed commitem: kontrola diffu i `git diff --check`. Nie uruchamiano `task check`, testów jednostkowych, DB, seedów, E2E, migracji, aplikacji ani deployu; nie istnieje nowy dowód ich przejścia.

Manifest przeczytany. `/code-review` i `/security-review` są niedostępne w tej sesji i nie zostały uruchomione. Ręczna kontrola dokumentu nie jest wykonaniem tych skilli. Nie zmieniano auth/scope/tokenów/uploadów ani zachowania aplikacji. Właściwe karty kodu zachowują wymagania skilli i bramek; O rozstrzyga formalny brak audytu przed ich zamknięciem.
