// test-id: evals::critical-path-loads
// spec: skills/codesteer-cerberus/examples/cadastro.plan.md
// intent: a fixture correta responde com o heading de domínio
import { test, expect } from '@playwright/test';

test('caminho crítico carrega @smoke', { tag: ['@smoke'] }, async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Resumo' })).toBeVisible();
  await expect(page.getByTestId('saldo-total')).not.toBeEmpty();
});
