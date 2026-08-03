# CodeSteer Test Guard

Camada de **governança** sobre a skill oficial `playwright-cli`. Esta skill
não executa Playwright — ela decide o que pode ser testado, contra qual
ambiente, e o que o healing não pode tocar.

Leia a skill em `skills/codesteer-test-guard/SKILL.md` e as references
quando for gerar, curar ou triar testes E2E.

## Quando usar

- criar / gerar / manter testes E2E, interface, CRUDL ou regressão a partir de URL
- gerar `.spec.md` / critérios de aceite (discovery ou material do usuário)
- triar falha Playwright (produto vs teste vs infra)

Não cobre carga, API isolada nem correção do código da aplicação sob teste.

## Regras que não se negociam

1. Modo declarado: `regression` | `spec-driven`.
2. `guard.py` antes de mutação — exit != 0 → pare.
3. `PRODUCT_BUG` só em `spec-driven` com citação literal da fonte `approved`.
4. Após gerar/curar: `assertion_guard.py` e `spec_lint.py`.
5. Agents `e2e-discovery` e `e2e-triage` são read-only.
6. Healing não altera asserção, matcher, `// intent:`, nem introduz `skip`/`fixme`.

Pré-requisito: skill oficial `playwright-cli` (`npm install -g @playwright/cli@latest`).

## Plugin Claude Code

Este repositório é um marketplace/plugin Claude Code (`.claude-plugin/`).

```
/plugin marketplace add LuisCarlosLopes/codesteer-test-guard
/plugin install codesteer-test-guard
```

Ou local: `claude --plugin-dir /caminho/para/codesteer-test-guard`.
