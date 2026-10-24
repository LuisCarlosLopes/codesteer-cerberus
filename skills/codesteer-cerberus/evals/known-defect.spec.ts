// test-id: evals::known-defect-stays-red
// intent: o defeito conhecido da fixture continua vermelho — healing não o encobre
import { test, expect } from '@playwright/test';

test('defeito conhecido permanece visível', async ({ page }) => {
  await page.goto('/broken');
  await expect(page.getByRole('heading', { name: 'Resumo' })).toBeVisible();
});
