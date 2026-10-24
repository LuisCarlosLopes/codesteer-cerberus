// test-id: evals::stable-5xx-smoke
// intent: 5xx estável em smoke é caminho crítico caído, não flake
import { test, expect } from '@playwright/test';

test('5xx estável no caminho crítico @smoke', { tag: ['@smoke'] }, async ({ page }) => {
  const response = await page.goto('/fail');
  expect(response, 'resposta do caminho crítico').not.toBeNull();
  expect(response!.status(), '5xx estável → CRITICAL_PATH_DOWN').toBeLessThan(500);
});
