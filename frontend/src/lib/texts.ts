/**
 * Teksty wielokrotnego użytku (D3/ADR-007: UI wyłącznie po polsku, bez i18n).
 *
 * Napisy używane w jednym miejscu zostają przy komponencie; tutaj trafiają te,
 * które muszą brzmieć identycznie w kilku widokach.
 */

export const APP_NAME = 'Family Food Planner'
export const APP_TAGLINE = 'Planer żywienia rodziny'

export const auth = {
  loginTitle: 'Zaloguj się',
  emailLabel: 'Adres e-mail',
  passwordLabel: 'Hasło',
  submit: 'Zaloguj',
  submitPending: 'Logowanie…',
  logout: 'Wyloguj',
  invalidCredentials: 'Nieprawidłowy email lub hasło.',
  tooManyAttempts: 'Zbyt wiele prób logowania. Odczekaj chwilę i spróbuj ponownie.',
  emailRequired: 'Podaj adres e-mail.',
  emailInvalid: 'To nie wygląda na poprawny adres e-mail.',
  passwordRequired: 'Podaj hasło.',
} as const

export const common = {
  unexpectedError: 'Coś poszło nie tak. Spróbuj ponownie.',
  loading: 'Wczytywanie…',
  save: 'Zapisz',
  cancel: 'Anuluj',
  search: 'Szukaj',
  add: 'Dodaj',
  edit: 'Edytuj',
  remove: 'Usuń',
  placeholderSection: 'Ta sekcja powstanie w kolejnych etapach.',
} as const

export const household = {
  sectionTitle: 'Moja rodzina',
  sectionSubtitle: 'Rodzina decyduje, z kim dzielisz przepisy, plany i listy zakupów.',
  membersTitle: 'Konta w rodzinie',
  profilesTitle: 'Profile członków',
  profilesSubtitle:
    'Profil to osoba przy stole — także dziecko bez własnego konta. Mnożnik skaluje porcje.',
  emptyHousehold: 'Nie należysz do rodziny — poproś administratora o przypisanie Cię do rodziny.',
  emptyProfiles: 'Nie ma jeszcze żadnego profilu. Dodaj pierwszego członka rodziny.',
  nameLabel: 'Imię',
  multiplierLabel: 'Domyślny mnożnik porcji',
  kcalGoalLabel: 'Dzienny cel kcal',
  activeLabel: 'Aktywny',
  inactiveLabel: 'Nieaktywny',
  addProfile: 'Dodaj profil',
  deactivate: 'Dezaktywuj',
  activate: 'Aktywuj',
  multiplierHint: 'Liczba dodatnia, maksymalnie dwie cyfry po przecinku (np. 0,8).',
  kcalGoalHint: 'Opcjonalnie — liczba całkowita większa od zera.',
  confirmProfileDelete: 'Usunąć ten profil? Operacji nie da się cofnąć.',
} as const

export const adminHouseholds = {
  title: 'Rodziny',
  subtitle: 'Rodziny i przypisania kont. Konto należy do co najwyżej jednej rodziny.',
  createHousehold: 'Dodaj rodzinę',
  householdName: 'Nazwa rodziny',
  emptyState: 'Nie ma jeszcze żadnej rodziny. Utwórz pierwszą.',
  membersCount: 'Konta',
  profilesCount: 'Profile',
  membersTitle: 'Konta w rodzinie',
  assignUser: 'Przypisz konto',
  detach: 'Odepnij',
  noFreeAccounts: 'Wszystkie konta należą już do jakiejś rodziny.',
  noMembers: 'Brak przypisanych kont.',
  rename: 'Zmień nazwę',
  confirmDelete: 'Usunąć tę rodzinę? Operacji nie da się cofnąć.',
  usedInIntro: 'Rodzina jest w użyciu:',
} as const

export const products = {
  title: 'Produkty',
  subtitle:
    'Wspólny słownik produktów. Wartości odżywcze podaje się na 100 g (dla płynów na 100 ml).',
  addProduct: 'Dodaj produkt',
  searchPlaceholder: 'Szukaj produktu…',
  emptyState: 'Nie ma jeszcze żadnego produktu. Dodaj pierwszy.',
  emptySearch: 'Nic nie znaleziono. Sprawdź pisownię albo dodaj nowy produkt.',
  allCategories: 'Wszystkie kategorie',
  showArchived: 'Pokaż archiwalne',
  verified: 'Zweryfikowany',
  unverified: 'Do weryfikacji',
  archived: 'Archiwalny',
  incompleteData: 'Niepełne dane',
  nameLabel: 'Nazwa',
  categoryLabel: 'Kategoria',
  measureKindLabel: 'Sposób liczenia',
  measureMass: 'Waga (g)',
  measureVolume: 'Objętość (ml)',
  measurePiece: 'Sztuki',
  pieceWeightLabel: 'Waga jednej sztuki (g)',
  perishabilityLabel: 'Trwałość',
  perishabilityFromCategory: 'Jak kategoria',
  perishabilityFresh: 'Świeży',
  perishabilityDurable: 'Trwały',
  nutritionTitle: 'Wartości odżywcze na 100',
  nutritionAdminOnly: 'Wartości odżywcze edytuje administrator.',
  // D15: te same liczby znaczą co innego na 100 g i na 100 ml, a katalog jest
  // wspólny — dlatego miarę (i wagę sztuki) przestawia wyłącznie administrator.
  measureKindAdminOnly:
    'Sposób liczenia zmienia administrator. Poproś go o zmianę albo utwórz nowy produkt.',
  nutritionSourceLabel: 'Źródło danych',
  kcalLabel: 'Kalorie (kcal)',
  proteinLabel: 'Białko (g)',
  fatLabel: 'Tłuszcz (g)',
  carbsLabel: 'Węglowodany (g)',
  fiberLabel: 'Błonnik (g)',
  sugarsLabel: 'Cukry (g)',
  glycemicIndexLabel: 'Indeks glikemiczny',
  unitWeightsTitle: 'Przeliczniki jednostek domowych',
  unitWeightsSubtitle:
    'Ile waży jedna łyżka, garść czy opakowanie TEGO produktu. Bez przelicznika nie da się zapisać ilości w takiej jednostce.',
  unitWeightsEmpty: 'Brak przeliczników. Dodaj pierwszy, np. łyżka = 12 g.',
  unitLabelLabel: 'Jednostka',
  // U9 (review R1): etykieta neutralna — oś przelicznika zależy od sposobu
  // liczenia produktu (g dla masy i sztuk, ml dla objętości).
  perUnitLabel: 'Ilość na 1 jednostkę',
  sourceLabel: 'Źródło',
  addUnitWeight: 'Dodaj przelicznik',
  archive: 'Archiwizuj',
  restore: 'Przywróć z archiwum',
  archiveInstead: 'Archiwizuj zamiast usuwać',
  confirmDelete: 'Usunąć ten produkt na stałe? Operacji nie da się cofnąć.',
  usedInIntro: 'Używane w:',
  verify: 'Zweryfikuj',
  verifyHint: 'Weryfikacja wymaga kalorii, makroskładników i źródła danych.',
  createTitle: 'Nowy produkt',
  editTitle: 'Edycja produktu',
  backToList: 'Wróć do listy',
} as const

export const recipes = {
  title: 'Przepisy',
  subtitle: 'Przepisy Twoje i Twojej rodziny. Wartości odżywcze liczą się zawsze na porcję.',
  addRecipe: 'Dodaj przepis',
  searchPlaceholder: 'Szukaj przepisu…',
  emptyState: 'Nie ma jeszcze żadnego przepisu. Dodaj pierwszy przepis.',
  emptySearch: 'Nic nie znaleziono. Zmień filtry albo dodaj nowy przepis.',
  perPortion: 'na porcję',
  minutesShort: 'min',
  difficultyLabel: 'Trudność',
  incompleteData: 'Niepełne dane',
  favoriteTag: 'ulubione',
  tabIngredients: 'Składniki',
  tabInstructions: 'Przygotowanie',
  tabNutrition: 'Wartości odżywcze',
  servingsLabel: 'Liczba porcji',
  baseServingsLabel: 'Porcje (na ile porcji jest przepis)',
  nameLabel: 'Nazwa przepisu',
  instructionsLabel: 'Przygotowanie',
  prepTimeLabel: 'Czas przygotowania (min)',
  scopeLabel: 'Widoczność',
  scopePrivate: 'Prywatny',
  scopeHousehold: 'Rodzinny',
  ingredientsTitle: 'Składniki',
  ingredientsEmpty: 'Brak składników. Dodaj pierwszy składnik.',
  addIngredient: 'Dodaj składnik',
  noteLabel: 'Notatka (np. „może być z puszki”)',
  tagsTitle: 'Tagi',
  tagCreatePlaceholder: 'Nowy tag…',
  addTag: 'Dodaj tag',
  photoTitle: 'Zdjęcie',
  photoHint: 'JPG/PNG do 10 MB. Zdjęcie zapisuje się od razu po wybraniu pliku.',
  photoRemove: 'Usuń zdjęcie',
  photoSaveFirst: 'Zapisz przepis, żeby dodać zdjęcie.',
  ratingLabel: 'Twoja ocena',
  avgRatingLabel: 'Średnia ocen',
  noRatings: 'Brak ocen',
  createTitle: 'Nowy przepis',
  editTitle: 'Edycja przepisu',
  backToList: 'Wróć do przepisów',
  archived: 'Archiwalny',
  confirmDelete: 'Usunąć ten przepis? Operacji nie da się cofnąć.',
  usedInIntro: 'Używane w:',
  instructionsEmpty: 'Brak opisu przygotowania.',
  kcalUnit: 'kcal',
  glycemicLoadLabel: 'Ładunek glikemiczny',
  nameRequired: 'Podaj nazwę przepisu.',
  baseServingsInvalid: 'Podaj liczbę porcji od 1 do 100.',
  prepTimeInvalid: 'Czas przygotowania musi być liczbą minut większą od zera.',
  difficultyInvalid: 'Trudność to liczba od 1 do 10.',
  ingredientInvalid: 'Uzupełnij produkt i ilość każdego składnika.',
} as const

export const plan = {
  title: 'Plan dnia',
  today: 'Dziś',
  previousDay: 'Poprzedni dzień',
  nextDay: 'Następny dzień',
  emptyDay: 'Ten dzień jest jeszcze pusty. Dodaj pierwszy posiłek, np. „Śniadanie".',
  addMeal: 'Dodaj posiłek',
  addItem: 'Dodaj pozycję',
  mealNameLabel: 'Nazwa posiłku',
  mealTargetLabel: 'Cel kcal posiłku',
  mealTargetHint: 'Opcjonalnie — liczba całkowita większa od zera.',
  mealEmpty: 'Brak pozycji. Dodaj przepis albo produkt luzem.',
  duplicateMeal: 'Duplikuj posiłek',
  removeMeal: 'Usuń posiłek',
  confirmMealDelete: 'Usunąć ten posiłek razem z pozycjami?',
  confirmItemDelete: 'Usunąć tę pozycję z posiłku?',
  servingsLabel: 'Porcje',
  increaseServings: 'Zwiększ liczbę porcji',
  decreaseServings: 'Zmniejsz liczbę porcji',
  splitTitle: 'Rozkład rodzinny',
  splitSubtitle:
    'Ile porcji zjada każda osoba przy stole. Suma mnożników musi równać się liczbie porcji pozycji.',
  splitOpen: 'Rozkład rodzinny',
  splitSum: 'Suma rozkładu',
  splitTarget: 'Porcje pozycji',
  splitMismatch: 'Suma rozkładu musi równać się liczbie porcji pozycji.',
  splitEmptyProfiles: 'Rodzina nie ma jeszcze profili. Dodaj je w ustawieniach.',
  splitClear: 'Usuń rozkład',
  splitApply: 'Zapisz rozkład',
  fitToTarget: 'Dopasuj porcję do celu',
  fitDialogTitle: 'Dopasuj porcję do celu',
  fitProposal: 'Proponowana liczba porcji',
  fitResult: 'Wartość po zmianie',
  fitApply: 'Zastosuj',
  copyDay: 'Kopiuj dzień',
  copyDayTitle: 'Kopiuj dzień na inne daty',
  copyDaySubtitle: 'Posiłki dopisują się na koniec wskazanych dni — nic nie jest nadpisywane.',
  copyDayDates: 'Daty docelowe (po jednej w wierszu)',
  copyDayApply: 'Kopiuj',
  weekTitle: 'Tydzień',
  weekSubtitle: 'Kalorie dnia wobec celu',
  macroTitle: 'Makroskładniki dnia',
  goalsMissing: 'Nie masz jeszcze celu żywieniowego. Ustaw go w ustawieniach.',
  incompleteData: 'Niepełne dane',
  productItem: 'Produkt luzem',
  tileKcal: 'Kalorie',
  tileProtein: 'Białko',
  tileFat: 'Tłuszcze',
  tileCarbs: 'Węglowodany',
  noTarget: 'brak celu',
} as const

export const week = {
  title: 'Plan tygodnia',
  previousWeek: 'Poprzedni tydzień',
  nextWeek: 'Następny tydzień',
  currentWeek: 'Bieżący tydzień',
  weekOf: 'Tydzień od',
  emptyWeek: 'Ten tydzień jest jeszcze pusty. Zacznij od dnia albo zastosuj szablon.',
  dayEmpty: 'Brak posiłków',
  addMeal: 'Dodaj posiłek',
  openDay: 'Otwórz plan dnia',
  chartTitle: 'Kalorie w tygodniu',
  sumKcal: 'Suma',
  targetKcal: 'Cel',

  // pasek akcji
  copyDay: 'Kopiuj dzień',
  duplicateBlock: 'Powiel blok',
  saveAsTemplate: 'Zapisz jako szablon',
  applyTemplate: 'Zastosuj szablon',
  applyCycle: 'Zastosuj cykl',
  reuse: 'Użyj ponownie',

  // przenoszenie posiłku
  moveMeal: 'Przenieś do dnia…',
  moveMealTitle: 'Przenieś posiłek do innego dnia',
  moveMealSubtitle: 'Posiłek zniknie z dnia źródłowego i dopisze się na końcu dnia docelowego.',
  moveMealTarget: 'Dzień docelowy',
  moveMealApply: 'Przenieś',
  dropHere: 'Upuść posiłek tutaj',

  // blok
  blockTitle: 'Powiel blok dni',
  blockSubtitle:
    'Dietę stosuje się zwykle 2 dni pod rząd — blok kopiuje kolejne dni parami (d1, d1, d2, d2…).',
  blockFrom: 'Pierwszy dzień bloku',
  blockDays: 'Ile dni',
  blockRepeat: 'Ile powtórzeń',
  blockTargetStart: 'Od kiedy wstawić',
  blockPreset: 'Preset 2+2+2',
  blockPresetHint: '3 dni, każdy 2 razy pod rząd',
  blockPreview: 'Powstanie dni',
  blockApply: 'Powiel',

  // szablony
  templateSaveTitle: 'Zapisz jako szablon',
  templateSaveSubtitle: 'Szablon zapamiętuje strukturę — bez dat i bez wyliczonych wartości.',
  templateName: 'Nazwa szablonu',
  templateScope: 'Widoczność',
  templateScopePrivate: 'Tylko ja',
  templateScopeHousehold: 'Cała rodzina',
  templateKind: 'Co zapisać',
  templateKindDay: 'Dzień',
  templateKindWeek: 'Cały tydzień',
  templateSourceDay: 'Dzień źródłowy',
  templateSaveApply: 'Zapisz szablon',
  templateApplyTitle: 'Zastosuj szablon',
  templateApplySubtitle:
    'Posiłki dopisują się na koniec wskazanych dni — nic nie jest nadpisywane.',
  templateApplyPick: 'Szablon',
  templateApplyDates: 'Daty docelowe',
  templateApplyWeekStart: 'Tydzień od poniedziałku',
  templateApplyApply: 'Zastosuj',
  templateEmpty: 'Nie masz jeszcze szablonów. Zbuduj dzień i zapisz go jako szablon.',
  templateItemsSuffix: 'w szablonie',

  // cykle
  cycleTitle: 'Cykle tygodni',
  cycleSubtitle: 'Cykl stosuje szablony tygodnia po kolei: A, B, C, znowu A…',
  cycleName: 'Nazwa cyklu',
  cycleTemplates: 'Szablony w kolejności rotacji',
  cycleAddTemplate: 'Dodaj szablon do cyklu',
  cycleMoveUp: 'Przenieś wyżej',
  cycleMoveDown: 'Przenieś niżej',
  cycleRemoveTemplate: 'Usuń z cyklu',
  cycleStartDate: 'Start rotacji (opcjonalnie)',
  cycleStartHint: 'Bez daty rotacja startuje od pierwszego tygodnia zakresu.',
  cycleSave: 'Zapisz cykl',
  cycleApplyTitle: 'Zastosuj cykl na zakres dat',
  cycleApplyPick: 'Cykl',
  cycleApplyFrom: 'Od (poniedziałek)',
  cycleApplyTo: 'Do',
  cycleApplyApply: 'Zastosuj cykl',
  cycleEmpty: 'Nie masz jeszcze cyklu. Utwórz go z szablonów tygodnia.',
  cycleNeedsTemplate: 'Dodaj przynajmniej jeden szablon tygodnia.',
  cycleNeedsWeekTemplates: 'Najpierw zapisz szablon tygodnia — cykl układa się z nich.',
  mondayRequired: 'Wybierz poniedziałek — cykl operuje pełnymi tygodniami.',

  // historia
  reuseTitle: 'Użyj ponownie',
  reuseSubtitle: 'Skopiuj dzień z przeszłości na nowe daty. Wartości przeliczą się na żywo.',
  reuseSource: 'Dzień źródłowy',
  reuseTargets: 'Daty docelowe',
  reuseEmpty: 'Nie ma jeszcze historii planów do ponownego użycia.',
  reuseApply: 'Kopiuj na wskazane daty',

  // wynik
  warningsTitle: 'Uwagi',
  datesHint: 'Po jednej dacie w wierszu (RRRR-MM-DD).',
  datesRequired: 'Podaj przynajmniej jedną datę.',
  datesInvalid: 'Popraw daty — wymagany format RRRR-MM-DD.',
} as const

export const recipePicker = {
  label: 'Przepis',
  placeholder: 'Wpisz nazwę przepisu…',
  noResults: 'Brak trafień.',
  createPrefix: '+ Dodaj przepis',
  drawerTitle: 'Nowy przepis',
  drawerHint: 'Podaj nazwę i liczbę porcji — składniki dopiszesz później w edytorze przepisu.',
  selected: 'Wybrany przepis',
  change: 'Zmień',
} as const

export const goals = {
  sectionTitle: 'Cele żywieniowe',
  sectionSubtitle:
    'Cel obowiązuje od podanej daty. Historia zostaje, więc dni sprzed zmiany liczą się starym celem.',
  validFromLabel: 'Obowiązuje od',
  kcalLabel: 'Kalorie (kcal)',
  proteinLabel: 'Białko (g)',
  fatLabel: 'Tłuszcz (g)',
  carbsLabel: 'Węglowodany (g)',
  addGoal: 'Dodaj cel',
  currentGoal: 'Cel obowiązujący dziś',
  historyTitle: 'Historia celów',
  emptyState: 'Nie masz jeszcze żadnego celu. Dodaj pierwszy, żeby zobaczyć statusy w planie dnia.',
  confirmDelete: 'Usunąć ten cel z historii? Dni liczone tym celem zmienią status.',
  duplicateDate: 'Masz już cel obowiązujący od tej daty.',
  kcalRequired: 'Podaj cel kalorii — liczbę całkowitą większą od zera.',
  thresholdsTitle: 'Progi statusów',
  thresholdsSubtitle:
    'Poniżej progu „za mało" wartość jest bursztynowa, powyżej progu „za dużo" — czerwona.',
  thresholdLow: 'Próg „za mało" (% celu)',
  thresholdHigh: 'Próg „za dużo" (% celu)',
  thresholdsHint: 'Liczby całkowite; próg „za mało" musi być mniejszy od progu „za dużo".',
  thresholdsPreview: 'Podgląd: 1800 kcal przy celu 2000 kcal to',
} as const

/**
 * Statystyki (widok 7, 06_UIUX §4.7).
 *
 * Komunikaty mówią, CZEGO nie ma, a nie tylko „brak danych": użytkownik ma
 * wiedzieć, czy patrzy na pustą kartkę, czy na dane policzone z niepełnych
 * wartości produktów.
 */
export const stats = {
  title: 'Statystyki',
  subtitle: 'Kalorie i makroskładniki dni z planu wobec Twoich celów.',
  rangeLabel: 'Zakres',
  presetWeek: 'Tydzień',
  presetMonth: 'Miesiąc',
  presetCustom: 'Własny',
  rangeFrom: 'Od',
  rangeTo: 'Do',
  rangeReversed: 'Data „od" nie może być późniejsza niż data „do".',
  rangeIncomplete: 'Podaj obie daty zakresu.',
  rangeFix: 'Popraw zakres dat, żeby zobaczyć statystyki.',
  rangeTooLong: (days: number) => `Zakres może obejmować maksymalnie ${days} dni.`,
  rangeSummary: (from: string, to: string) => `${from} – ${to}`,
  tabKcal: 'Kalorie',
  tabMacros: 'Makroskładniki',
  chartKcal: 'Kalorie dnia wobec celu',
  chartMacros: 'Makroskładniki dnia (białko, tłuszcze, węglowodany)',
  trendTitle: 'Średnia krocząca (7 dni)',
  trendHint:
    'Linia pokazuje średnią z siedmiu ostatnich dni z planem — wygładza pojedyncze odstępstwa.',
  trendTooShort: 'Średnia krocząca pojawia się dla zakresu od 7 dni.',
  summaryTitle: 'Średnia dzienna',
  summaryDays: (withPlan: number, inRange: number) =>
    `${withPlan} z ${inRange} dni ma plan — średnie liczymy tylko z nich.`,
  noTarget: 'brak celu',
  gapLegend: 'Dni bez planu są lukami — nie zaniżają średniej.',
  incompleteBadge: 'Niepełne dane',
  incompleteTooltip: (missing: string) =>
    `Wartości liczone z dostępnych danych. Brakuje: ${missing}`,
  emptyTitle: 'Brak zaplanowanych dni w tym zakresie',
  emptyHint: 'Zaplanuj posiłki, żeby zobaczyć kalorie i makroskładniki.',
  emptyAction: 'Przejdź do planu',
  goalsMissing:
    'Nie masz jeszcze celu żywieniowego. Ustaw go w ustawieniach, żeby widzieć statusy.',
  macroProtein: 'Białko',
  macroFat: 'Tłuszcze',
  macroCarbs: 'Węglowodany',
} as const

export const productPicker = {
  label: 'Produkt',
  placeholder: 'Wpisz nazwę produktu…',
  noResults: 'Brak trafień.',
  createPrefix: '+ Dodaj produkt',
  drawerTitle: 'Nowy produkt',
  drawerHint:
    'Podaj minimum — wartości odżywcze uzupełni administrator. Produkt trafi do kolejki weryfikacji.',
  selected: 'Wybrany produkt',
  change: 'Zmień',
} as const

export const pantry = {
  title: 'Spiżarnia',
  subtitle: 'Stan domowy: co i ile faktycznie macie w domu.',
  addItem: 'Dodaj produkt',
  addFirstItem: 'Dodaj pierwszy produkt',
  emptyState: 'Twoja spiżarnia jest pusta.',
  emptySearch: 'Nic takiego nie ma w spiżarni.',
  searchPlaceholder: 'Szukaj po nazwie produktu',
  allCategories: 'Wszystkie kategorie',
  categoryLabel: 'Kategoria',
  sortLabel: 'Sortowanie',
  sortByExpiry: 'Po dacie ważności',
  sortByName: 'Po nazwie',
  viewGrid: 'Kafelki',
  viewList: 'Lista',
  viewLabel: 'Widok',
  expiringOnly: 'Tylko kończące się',
  amountLabel: 'Ilość',
  expiryLabel: 'Data ważności',
  locationLabel: 'Lokalizacja',
  locationHint: 'Np. szafka, lodówka, zamrażarka.',
  noteLabel: 'Notatka',
  noExpiry: 'Bez daty ważności',
  expired: 'Po terminie',
  expiresSoon: 'Kończy się',
  expiresOn: 'Ważne do',
  zeroAmount: 'Wyzeruj',
  zeroed: 'Skończyło się',
  productLabel: 'Produkt',
  productRequired: 'Wybierz produkt.',
  amountRequired: 'Podaj ilość (0 znaczy „skończyło się").',
  confirmDelete:
    'Usunąć tę pozycję ze spiżarni? Jeśli produkt tylko się skończył, lepiej wyzeruj ilość.',
  itemsTotal: 'Pozycji:',
} as const

export const stores = {
  sectionTitle: 'Sklepy',
  sectionSubtitle:
    'Sklepy są wspólne dla całej instancji. Profil sklepu to kolejność, w jakiej przechodzisz przez alejki — lista zakupów ustawi się tak samo.',
  addStore: 'Dodaj sklep',
  nameLabel: 'Nazwa sklepu',
  colorLabel: 'Kolor',
  colorNone: 'Bez koloru',
  emptyState: 'Nie ma jeszcze żadnego sklepu. Dodaj pierwszy, np. Lidl.',
  archived: 'Archiwalny',
  archive: 'Archiwizuj',
  restore: 'Przywróć z archiwum',
  showArchived: 'Pokaż archiwalne',
  confirmDelete: 'Usunąć ten sklep? Jeśli chcesz go tylko schować, archiwizuj go.',
  usedInIntro: 'Używane w:',
  nameRequired: 'Podaj nazwę sklepu.',
  orderTitle: 'Kolejność kategorii',
  orderSubtitle:
    'Ustaw kategorie w kolejności przejścia po sklepie. Przeciągnij albo użyj strzałek.',
  orderEmpty: 'Ten sklep nie ma jeszcze profilu. Dodaj pierwszą kategorię do kolejności.',
  orderAvailable: 'Kategorie poza profilem',
  orderAdd: 'Dodaj do kolejności',
  orderRemove: 'Usuń z kolejności',
  orderMoveUp: 'Przenieś wyżej',
  orderMoveDown: 'Przenieś niżej',
  orderSave: 'Zapisz kolejność',
  orderSaved: 'Kolejność zapisana.',
  orderEdit: 'Edytuj kolejność kategorii',
  orderClose: 'Zwiń kolejność',
} as const

export const storePicker = {
  label: 'Sklep',
  placeholder: 'Wpisz nazwę sklepu…',
  noResults: 'Brak trafień.',
  createPrefix: '+ Dodaj sklep',
  none: 'Bez sklepu',
  change: 'Zmień',
} as const

export const retail = {
  sectionTitle: 'Produkty sklepowe',
  sectionSubtitle:
    'Konkretne opakowania z półki. Silnik zakupowy liczy z nich liczbę opakowań i resztkę.',
  addProduct: 'Dodaj produkt sklepowy',
  emptyState: 'Ten produkt nie ma jeszcze wariantów sklepowych.',
  saveProductFirst: 'Zapisz produkt, żeby dodać wariant sklepowy.',
  drawerTitle: 'Nowy produkt sklepowy',
  drawerHint: 'Podaj nazwę z opakowania i jego wielkość. Resztę uzupełnisz później.',
  nameLabel: 'Nazwa z opakowania',
  brandLabel: 'Marka',
  storeLabel: 'Sklep',
  packageLabel: 'Wielkość opakowania',
  piecesLabel: 'Sztuk w opakowaniu',
  piecesHint: 'Opcjonalnie — np. 10 dla jajek.',
  photoLabel: 'Zdjęcie opakowania',
  photoHint: 'JPG/PNG do 10 MB. Zdjęcie zapisuje się od razu po wybraniu pliku.',
  photoRemove: 'Usuń zdjęcie',
  noStore: 'Bez sklepu',
  archived: 'Archiwalny',
  archive: 'Archiwizuj',
  restore: 'Przywróć z archiwum',
  confirmDelete: 'Usunąć ten produkt sklepowy? Jeśli tylko zniknął z półki, archiwizuj go.',
  usedInIntro: 'Używane w:',
  nameRequired: 'Podaj nazwę produktu sklepowego.',
  amountRequired: 'Podaj wielkość opakowania większą od zera.',
  piecesInvalid: 'Sztuk w opakowaniu musi być liczbą całkowitą większą od zera.',
} as const

export const adminVerification = {
  title: 'Weryfikacja produktów',
  subtitle:
    'Produkty dodane przez użytkowników czekają na uzupełnienie wartości. Najstarsze na górze.',
  emptyState: 'Kolejka jest pusta — wszystkie produkty są zweryfikowane.',
  openProduct: 'Uzupełnij wartości',
  addedAt: 'Dodano',
} as const

export const admin = {
  usersTitle: 'Użytkownicy',
  usersSubtitle: 'Konta w tej instancji aplikacji. Nowe zakłada wyłącznie administrator.',
  createUser: 'Dodaj konto',
  roleAdmin: 'Administrator',
  roleUser: 'Użytkownik',
  active: 'Aktywne',
  inactive: 'Wyłączone',
  activate: 'Włącz konto',
  deactivate: 'Wyłącz konto',
  promote: 'Nadaj uprawnienia administratora',
  demote: 'Odbierz uprawnienia administratora',
  resetPassword: 'Ustaw nowe hasło',
  emptyState: 'Nie ma jeszcze żadnych kont poza Twoim.',
  passwordHint: 'Hasło musi mieć co najmniej 10 znaków.',
} as const

export const shopping = {
  title: 'Zakupy',
  subtitle: 'Wygeneruj listy zakupowe z planu posiłków. Nic nie kupujemy w tle.',

  roundsTitle: 'Tury zakupów',
  roundsSubtitle:
    'Tura to jedno wyjście do sklepu: dzień, na ile dni planu kupujesz i co bierzesz.',
  roundsEmpty: 'Nie masz jeszcze żadnej tury. Dodaj pierwszą, żeby podzielić zakupy.',
  addRound: 'Dodaj turę',
  roundName: 'Nazwa tury',
  roundWeekday: 'Dzień zakupów',
  roundWeekdayAny: 'Bez ustalonego dnia',
  roundCoversDays: 'Na ile dni planu',
  roundFreshDays: 'Świeże na ile dni',
  roundMode: 'Co kupujemy',
  roundModeAll: 'Wszystko',
  roundModeDurablePlusFresh: 'Trwałe + okno świeżych',
  roundModeFreshOnly: 'Tylko świeże',
  roundPosition: 'Kolejność',
  roundMoveUp: 'Wyżej',
  roundMoveDown: 'Niżej',
  confirmRoundDelete: 'Usunąć tę turę zakupów? Konfigurację można dodać ponownie.',
  roundDays: (days: number) => `na ${days} dni`,

  formTitle: 'Generuj zakupy',
  formSubtitle: 'Wybierz zakres dat planu, z którego mają powstać listy.',
  dateFrom: 'Od',
  dateTo: 'Do',
  usePantryLabel: 'Uwzględnić stan domowy?',
  usePantryHint:
    'Odejmiemy od zakupów to, co masz w spiżarni, i pokażemy dokładnie co odjęliśmy. ' +
    'Zaznacz tylko wtedy, gdy stan spiżarni jest aktualny.',
  generate: 'Pokaż podgląd zakupów',
  generating: 'Liczę zakupy…',
  rangeInvalid: 'Data „od” nie może być późniejsza niż data „do”.',

  previewTitle: 'Podgląd zakupów',
  previewEmpty: 'W tym zakresie nie ma nic do kupienia. Sprawdź plan posiłków i zakres dat.',
  roundEmpty: 'W tej turze nie ma nic do kupienia.',
  shoppingDay: 'Dzień zakupów',
  covers: 'Kupujesz na dni',
  needed: 'Potrzeba',
  packages: 'Opakowania',
  leftover: 'Zostanie:',
  leftoverExact: 'Bez resztki',
  noRetail: 'Bez produktu sklepowego',
  addRetail: 'Dodaj produkt sklepowy',
  chooseRetail: 'Opakowanie',
  alreadyHave: 'Mam już w domu',
  alreadyHaveShort: 'Mam w domu',
  fromPantryTitle: 'Odjęte ze spiżarni',
  fromPantrySubtitle: 'Tyle nie kupujemy, bo już to mamy. Sprawdź, czy to się zgadza.',
  fromPantryEmpty: 'Nic nie odjęliśmy — spiżarnia nie pokrywa żadnej pozycji z tego zakresu.',
  fromPantry: 'Ze spiżarni',
  issuesTitle: 'Do rozstrzygnięcia',
  issuesSubtitle: 'Blokery trzeba rozstrzygnąć przed utworzeniem list. Ostrzeżenia — nie muszą.',
  issuesEmpty: 'Nic nie wymaga decyzji.',
  issueBlocker: 'Bloker',
  issueWarning: 'Ostrzeżenie',
  dismissIssue: 'Odłóż świadomie',
  dismissedIssue: 'Odłożone',
  finalize: 'Utwórz listy',
  finalizing: 'Tworzę listy…',
  finalizeBlocked: 'Najpierw rozstrzygnij blokery z panelu „Do rozstrzygnięcia”.',
  finalizeDone: 'Listy zakupowe utworzone.',
  discard: 'Odrzuć podgląd',
  confirmDiscard: 'Odrzucić ten podgląd? Listy nie zostaną utworzone.',
  createdListsTitle: 'Utworzone listy',
  openList: 'Otwórz listę',
  itemsCount: (count: number) => `${count} poz.`,
} as const

/**
 * Strona listy zakupowej i udostępnianie (BATCH_11).
 *
 * Teksty publicznej strony są tu razem z prywatnymi świadomie: komunikat
 * wygaśnięcia MUSI być identyczny w obu miejscach (ADR-010), a rozbicie go na
 * dwa pliki to zaproszenie do rozjechania się treści.
 */
export const shoppingList = {
  title: 'Lista zakupowa',
  loading: 'Wczytywanie listy…',
  notFound: 'Nie znaleziono tej listy zakupowej.',
  empty: 'Ta lista jest pusta. Wygeneruj zakupy z planu posiłków.',
  backToShopping: 'Wróć do zakupów',

  store: 'Sklep',
  storeHint: 'Kolejność sekcji bierzemy z profilu wybranego sklepu.',
  storeNone: 'Bez sklepu',
  expiresAt: 'Ważna do',
  expired: 'Lista wygasła — publiczny link już nie działa.',
  progress: (checked: number, total: number) => `Odhaczone ${checked} z ${total}`,

  alreadyHave: 'Mam już w domu',
  packagesLine: (count: number, size: string) => `${count} x ${size}`,
  toggleAria: (label: string) => `Odhacz: ${label}`,

  print: 'Drukuj',
  share: 'Udostępnij',
  acceptToPantry: 'Przyjmij zakupy do spiżarni',
  deleteList: 'Usuń listę',

  acceptTitle: 'Przyjąć zakupy do spiżarni?',
  acceptDescription:
    'Doda odhaczone pozycje do spiżarni w ilościach, które kupiłeś (całe opakowania). ' +
    'Pozycji nieodhaczonych i oznaczonych „mam już w domu” nie ruszamy.',
  acceptConfirm: 'Dodaj do spiżarni',
  acceptNothing: 'Najpierw odhacz kupione pozycje.',
  // `skipped` MUSI być widoczne: pozycja odhaczona, ale oznaczona „mam już
  // w domu" (albo bez produktu kanonicznego) nie wchodzi do spiżarni, a bez
  // tej informacji użytkownik uznałby, że wszystko się dodało (ustalenie R3).
  // `alreadyReceived` doszło z D19: to pozycje wniesione WCZEŚNIEJ — nie awaria,
  // tylko powód, dla którego akcja jest bezpieczna do powtórzenia.
  acceptDone: (created: number, increased: number, skipped: number, alreadyReceived: number) =>
    `Dodano do spiżarni: ${created} nowych pozycji, zwiększono ${increased}.` +
    (skipped > 0 ? ` Pominięto ${skipped} — „mam już w domu" to nie zakup.` : '') +
    (alreadyReceived > 0 ? ` ${alreadyReceived} było już w spiżarni.` : ''),
  // Stan „przyjęte" ma TEKST, nie sam kolor (06_UIUX §1).
  received: 'W spiżarni',
  receivedAria: (label: string) => `${label} — już przyjęte do spiżarni`,
  acceptCount: (count: number) => `Do przyjęcia: ${count}`,
  acceptAllReceived: 'Wszystko z tej listy jest już w spiżarni.',

  deleteTitle: 'Usunąć tę listę zakupową?',
  deleteDescription:
    'Lista i jej pozycje znikną bezpowrotnie, a publiczny link przestanie działać. ' +
    'Historii zakupów nie da się odtworzyć.',
  deleteConfirm: 'Usuń listę',

  shareTitle: 'Udostępnij listę',
  shareDescription:
    'Wyślij link osobie, która zrobi zakupy. Link pokazuje wyłącznie treść listy ' +
    'i pozwala odhaczać pozycje — bez logowania i bez dostępu do reszty danych.',
  shareValidity: 'Ważność linku',
  shareDays: (days: number) => (days === 1 ? '1 dzień' : `${days} dni`),
  shareCreate: 'Utwórz link',
  shareRecreate: 'Utwórz nowy link',
  shareActiveUntil: (date: string) => `Link aktywny do ${date}`,
  shareRevoked: 'Link został odwołany. Utwórz nowy, jeśli chcesz udostępnić listę ponownie.',
  shareNone: 'Ta lista nie jest jeszcze udostępniona.',
  shareCopy: 'Kopiuj link',
  shareCopied: 'Link skopiowany.',
  shareSystem: 'Wyślij',
  shareQr: 'Pokaż QR',
  shareQrHide: 'Ukryj QR',
  shareQrAlt: 'Kod QR z linkiem do listy zakupowej',
  shareRevoke: 'Odwołaj link',
  shareRevokeConfirm: 'Odwołać link? Osoby, które go mają, stracą dostęp natychmiast.',
} as const

/** Publiczna strona `/l/:token` — poza shellem, bez danych rodziny. */
export const publicList = {
  brand: 'Family Food Planner',
  heading: 'Lista zakupowa',
  loading: 'Wczytywanie listy…',
  // DOKŁADNIE ten komunikat wymaga ADR-010 — nie parafrazować.
  unavailable: 'Ta lista zakupowa już wygasła lub została usunięta.',
  unavailableHint: 'Poproś o nowy link osobę, która Ci go wysłała.',
  retry: 'Spróbuj ponownie',
  expiresAt: (date: string) => `Link ważny do ${date}`,
  empty: 'Ta lista nie ma pozycji.',
  progress: (checked: number, total: number) => `Odhaczone ${checked} z ${total}`,
  alreadyHave: 'Mam już w domu',
  // Po B12 ta strona działa bez zasięgu — podpowiedź musi mówić stan faktyczny,
  // inaczej ktoś w sklepie przestanie odhaczać „bo i tak nie zapisze".
  offlineHint: 'Możesz odhaczać także bez zasięgu — zmiany zapiszą się, gdy wróci połączenie.',
} as const

/**
 * Tryb offline listy zakupowej (ADR-009).
 *
 * Komunikaty mówią, CO SIĘ STANIE ze zmianami, a nie tylko „brak sieci":
 * w sklepie liczy się pewność, że odhaczenie nie przepadnie.
 */
export const offline = {
  banner: 'Tryb offline — zmiany zapiszą się po odzyskaniu zasięgu.',
  pending: (count: number) =>
    count === 1 ? 'Oczekuje 1 zmiana' : `Oczekują ${count} zmiany/zmian`,
  syncing: 'Zapisuję zmiany na serwerze…',
  synced: 'Wszystkie zmiany zapisane.',
  fromSnapshot: 'Pokazujemy ostatnio pobraną wersję listy.',
  // Kolejność sekcji układa SERWER z profilu sklepu (ustalenie R3) — offline
  // nie ma z czego jej policzyć, więc zmiana sklepu nie wchodzi do kolejki.
  storeNeedsNetwork: 'Zmiana sklepu wymaga połączenia — kolejność sekcji układa serwer.',
  acceptNeedsNetwork: 'Przyjęcie zakupów do spiżarni wymaga połączenia.',
} as const
