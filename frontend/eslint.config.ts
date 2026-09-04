import js from '@eslint/js'
import { defineConfigWithVueTs, vueTsConfigs } from '@vue/eslint-config-typescript'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import pluginVue from 'eslint-plugin-vue'

export default defineConfigWithVueTs(
  {
    name: 'pasnik/files',
    files: ['**/*.{ts,mts,tsx,vue}'],
  },
  {
    name: 'pasnik/ignores',
    ignores: [
      'dist/**',
      'dev-dist/**',
      'coverage/**',
      'playwright-report/**',
      'test-results/**',
      // Plik generowany z OpenAPI (task fe-types) — nie formatujemy, nie lintujemy.
      'src/api/generated.ts',
    ],
  },
  js.configs.recommended,
  pluginVue.configs['flat/recommended'],
  vueTsConfigs.recommended,
  {
    name: 'pasnik/rules',
    rules: {
      // ADR-007 / skill pasnik-frontend: brak `any` bez uzasadnienia w komentarzu.
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
      // Nazwy komponentów: shadcn-vue generuje jednowyrazowe (Button, Card…).
      'vue/multi-word-component-names': 'off',
    },
  },
  {
    // Kod generowany przez shadcn-vue: modyfikujemy go przez tokens, nie przez
    // przepisywanie propsów (ADR-007) — reguły stylistyczne tu nie pomagają.
    name: 'pasnik/shadcn-generated',
    files: ['src/components/ui/**/*.vue'],
    rules: {
      'vue/require-default-prop': 'off',
    },
  },
  skipFormatting,
)
