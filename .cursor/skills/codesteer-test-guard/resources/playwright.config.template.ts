import { defineConfig, devices } from '@playwright/test';

/**
 * Template padronizado do codesteer-test-guard.
 * Utilizado para bootstrap automático em novos projetos (State 1: Init).
 *
 * Quando o agente detectar que o repositório não possui playwright.config.ts,
 * deve copiar este template e ajustar o baseURL se fornecido pelo usuário.
 */
export default defineConfig({
  testDir: './tests/e2e',

  fullyParallel: false,
  retries: 0,
  workers: 1,

  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],

  use: {
    /* Descomentar e ajustar quando o usuário fornecer uma baseURL: */
    // baseURL: 'https://app.exemplo.com',

    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
