# CodeSteer Test Guard

Camada de **governança** sobre a skill oficial `playwright-cli`. Esta skill
não executa Playwright — ela decide o que pode ser testado, contra qual
ambiente, e o que o healing não pode tocar.

## Quando usar

Use a skill `codesteer-test-guard` sempre que o usuário quiser:

- criar, gerar ou manter testes E2E / interface / CRUDL / regressão a partir de uma URL
- gerar spec ou critérios de aceite (`.spec.md`) a partir de discovery ou material do usuário
- triar falha de teste Playwright (bug do produto vs deriva do teste vs infra)

Não use para teste de carga, API isolada ou correção do código da aplicação.

## Fluxo obrigatório

1. Declare o modo: `regression` ou `spec-driven` (pergunte se o usuário não disse).
2. Rode `guard.py` antes de mutar qualquer ambiente. Exit != 0 → pare.
3. Em `spec-driven`, só afirme `PRODUCT_BUG` com citação literal da fonte aprovada.
4. Em `regression`, `PRODUCT_BUG` é inalcançável.
5. Após gerar ou curar: `assertion_guard.py` e `spec_lint.py` — exit != 0 bloqueia.
6. Delegue discovery ao agent `e2e-discovery` e triagem ao `e2e-triage` (read-only).

Nunca contorne os scripts de gate. Nunca enfraqueça asserção, matcher,
`// intent:`, nem introduza `skip`/`fixme` no healing.

Pré-requisito externo: `@playwright/cli` (skill `playwright-cli`).

## Cursor Cloud specific instructions

Cloud Agents não leem `~/.cursor`. Para a skill estar disponível no VM:

1. Instale o plugin via Team Marketplace e marque como Required, **ou**
2. Committe `skills/codesteer-test-guard/` e `agents/e2e-*.md` no repositório de produto.

Garanta `playwright-cli` / `@playwright/cli` no ambiente Cloud (setup do
projeto). Rode os self-tests dos gates se alterar a skill:

```bash
python3 skills/codesteer-test-guard/scripts/guard.py --self-test
```
