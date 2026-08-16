import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Łączenie klas Tailwind z rozwiązywaniem konfliktów — wymagane przez shadcn-vue. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}
