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
  placeholderSection: 'Ta sekcja powstanie w kolejnych etapach.',
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
