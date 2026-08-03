---
name: codesteer-cerberus
displayName: CodeSteer Cerberus
description: Camada de governança para testes E2E em Playwright — ambiente, modo, seletores, POM e gate de healing sobre a skill oficial playwright-cli.
keywords:
  - e2e
  - playwright
  - governance
  - healing
  - cerberus
  - POM
author: CodeSteer Squad
---

# CodeSteer Cerberus

Governança E2E sobre `playwright-cli`. Não executa browser — decide o que pode
ser testado e o que o healing não pode tocar.

## Onboarding

Ao ativar este power pela primeira vez:

1. Verifique `python3` (e opcionalmente `uv`): `python3 --version`.
2. Instale a mecânica oficial:

   ```bash
   npm install -g @playwright/cli@latest
   npx --no-install playwright-cli --version
   ```

3. Rode os self-tests dos gates (na raiz deste repositório / plugin):

   ```bash
   python3 skills/codesteer-cerberus/scripts/guard.py --self-test
   pip install tree-sitter tree-sitter-typescript
   python3 skills/codesteer-cerberus/scripts/assertion_guard.py --self-test
   python3 skills/codesteer-cerberus/scripts/spec_lint.py --self-test
   ```

4. Se algum self-test falhar, **não use o passo de healing** até corrigir o gate.

## Quando usar

- Gerar ou manter testes E2E / CRUDL / regressão a partir de uma URL
- Redigir `.spec.md` / critérios de aceite após discovery
- Triar falha Playwright (produto vs teste vs infra)

## Fluxo

1. Declare `regression` ou `spec-driven`.
2. Rode `guard.py` — exit != 0 → pare.
3. Discovery via agent `e2e-discovery`; triagem via `e2e-triage` (read-only).
4. Após gerar/curar: `assertion_guard.py` e `spec_lint.py`.

## Boas práticas

- Prefira a skill `playwright-cli` para toda ação de browser.
- Em `regression`, nunca afirme `PRODUCT_BUG`.
- Healing nunca altera asserção, matcher, `// intent:`, nem introduz `skip`/`fixme`.
