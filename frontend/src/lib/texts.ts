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
