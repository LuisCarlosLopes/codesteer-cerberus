import { defineConfig, devices } from '@playwright/test';

/**
 * Configuração Playwright — bootstrap do codesteer-test-guard (State 1: Init).
 * baseURL apontando para a URL alvo fornecida pelo usuário.
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
    baseURL: 'https://codesteer.vercel.app',

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
