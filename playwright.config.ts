import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config();

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:4173';

/**
 * Configuração Playwright do plugin — fixture local, sem alvo remoto implícito.
 * testDir (A1a): skills/codesteer-cerberus/evals
 */
export default defineConfig({
  testDir: 'skills/codesteer-cerberus/evals',

  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,

  reporter: [
    ['list'],
    ['html', { open: 'never', outputFolder: 'playwright-report' }],
  ],

  use: {
    baseURL,
    actionTimeout: 10_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    locale: 'pt-BR',
    timezoneId: 'America/Sao_Paulo',
  },

  webServer: {
    command: 'python3 skills/codesteer-cerberus/evals/server.py',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 15_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      testMatch: /.*\.spec\.ts/,
    },
  ],
});
