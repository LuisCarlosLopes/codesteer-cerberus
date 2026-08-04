# CodeSteer Cerberus

Camada de **governança** sobre a skill oficial `playwright-cli`. Esta skill
não executa Playwright — ela decide o que pode ser testado, contra qual
ambiente, e o que o healing não pode tocar.

Leia a skill em `skills/codesteer-cerberus/SKILL.md` e as references
quando for gerar, curar ou triar testes E2E.

## Quando usar

- criar / gerar / manter testes E2E, interface, CRUDL ou regressão a partir de URL
- suíte de **smoke** / verificação pós-deploy do caminho crítico (inclusive produção)
- gerar `.spec.md` / critérios de aceite (discovery ou material do usuário)
- triar falha Playwright (produto vs teste vs infra)

Não cobre carga, API isolada nem correção do código da aplicação sob teste.

## Regras que não se negociam

1. Modo declarado: `regression` | `spec-driven` | `smoke`.
2. `guard.py` antes de mutação — exit != 0 → pare.
3. `PRODUCT_BUG` só em `spec-driven` com citação literal da fonte `approved`.
4. Após gerar/curar: `assertion_guard.py` e `spec_lint.py`.
5. Agents `e2e-discovery` e `e2e-triage` são read-only.
6. Healing não altera asserção, matcher, `// intent:`, nem introduz `skip`/`fixme`.
7. `smoke` é somente leitura por construção (`scope: RL` em qualquer ambiente),
   carrega a tag `@smoke`, e 5xx reproduzível nele é `CRITICAL_PATH_DOWN`, não
   flake. Ver `references/smoke-policy.md`.

Pré-requisito: skill oficial `playwright-cli` (`npm install -g @playwright/cli@latest`).

## Plugin Claude Code

Este repositório é um marketplace/plugin Claude Code (`.claude-plugin/`).

```
/plugin marketplace add LuisCarlosLopes/codesteer-cerberus
/plugin install codesteer-cerberus
```

Ou local: `claude --plugin-dir /caminho/para/codesteer-cerberus`.
