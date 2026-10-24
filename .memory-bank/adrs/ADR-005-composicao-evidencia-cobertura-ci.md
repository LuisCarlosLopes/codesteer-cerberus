# ADR-005: Composição de evidência, cobertura e exemplo de CI

**Status:** Aceito
**Data:** 2026-10-24
**Feature de origem:** otimizar-governanca-e2e-ia
**Autores:** codesteer.architect skill

---

## Contexto

O run atual grava Markdown em `.e2e-engine/runs/<runId>/reports/` (`summary.md`, `mutations.diff`, `bug_report.md`, `escalations.md`). Não há manifesto por tentativa, nem mapa que distinga origem `approved`/`observed`, nem conciliação esperado/selecionado/executado. `playwright.config.ts` do repo aponta `baseURL` remoto fixo, `retries: 0` e `trace: on-first-retry` — sem retry não há trace.

O TSD (RF11–RF17, CA11–CA13, CA16) pede pacote identificável por `run_id` × `test_id` × `project` × `attempt`, mapa versionado e exemplo de CI parametrizado. Dashboard, túneis, comentário de PR e histórico agregado estão fora (FE04, FE06). Contar arquivos verdes não revela critério sem teste nem resultado de outro build.

`e2e-triage` hoje devolve Markdown; `PRODUCT_BUG` e `TEST_DRIFT` precisam de `evidence_package_ref` ao pacote da tentativa falha. A prova de locator deixa o “mesmo nó DOM” e passa a **mesmo alvo de domínio**, o que só é auditável se o pacote existir.

## Decisão

Decidimos compor três artefatos locais no **mesmo run**, emitidos pelo pós-processador de ADR-003, sem serviço novo:

1. **`PacoteDeEvidencia`** (`schema_version: 1`) — um por teste × projeto × tentativa. Fonte executada, erro e anexos (`path` + `hash` + `present`) pertencem a essa chave. Ausência se declara, nunca se fabrica. Perfil diagnóstico exige trace da falha. Pacote finalizado é imutável no limite do host; reprodução e pós-healing geram registro **novo** com `original_failure_ref`. Run concorrente não sobrescreve o original (nova identidade).
2. **`MapaDeCobertura`** (`coverage-map.json` + tabela derivada `coverage.md`) — liga critério (0..1), funcionalidade, cenário, `test_id` e referências de execução. Distingue `origin` (`approved`|`observed`), `discovery` (`explored`|`partial`|`blocked` + motivo), `stage` (`proposed`|`generated`|`executed`) e resultado por ambiente/revisão/run/tentativa. Dado de outro build é obsoleto. ID duplicado ou referência inexistente invalida o mapa. Relação lógica entre cenários **não** sequencia execução.
3. **Inventários** `expected` / `selected` / `executed` / `exclusions` — o esperado vem do plano/manifesto protegido **antes** do run (ADR-004). Reporter não redefine o esperado. Zero seleção, caso obrigatório ausente, execução incompleta ou resultado obsoleto não são sucesso.

**Comparação entre execuções** só com referências explícitas a pacotes válidos do mesmo cenário, `// intent:` e alvo de domínio; diferenças de build/política/estado são declaradas.

**Exemplo de CI consumidor** é um workflow parametrizado (URL, SHA esperado, identidade de deployment de origem confiável do CI *do produto*): `guard.avaliar` → readiness HTTP (não prova identidade) → runner nativo na seleção autorizada → pós-processador. A CI deste plugin valida o exemplo na **fixture local**; não instala integração em repositório externo, não comenta PR, não altera branch protection e não implanta produto.

**Alvo de domínio** (exit 2): entidade + papel/nome ou testid + cardinalidade + escopo, com evidências do pacote da tentativa. Sem baseline suficiente, não há `APROVA` automático. Papel+nome e testid são contratos estáveis equivalentes (RF09); nível D continua bloqueando geração.

**Smoke em camadas** permanece no lint/política (`spec_lint.analisar_spec` / `orcamento_smoke`), não num interceptor: mutação de domínio identificada bloqueia; ação não classificada fica pendente de revisão; login excepcional e filtro de busca só sob contrato. Sem interceptação obrigatória (FE08).

## Alternativas Consideradas

| Alternativa | Por que foi descartada |
|---|---|
| A. Contar testes verdes / arquivos e reusar só `summary.md` | Não mostra critério sem teste, discovery bloqueado, exclusão por guard nem resultado de outro SHA (RF13, RF19). |
| B. Reporter plugin que redefine o esperado a partir do que chegou ao JUnit | Viola RF15/V13: o reporter passa a ser fonte do inventário; healer pode reduzir seleção e ainda “passar”. |
| C. Dashboard, grafo editável ou serviço remoto de evidência | FE04/FE06/FE01; acrescenta produto sem resolver integridade do gate. |
| D. Pacote + mapa + inventários no run existente, consumidos por exemplo de CI parametrizado | Adotada: aditivo aos Markdown atuais; composição local; identidade de build é do host. |

## Consequências

**Positivas:**
- ✅ Triagem e healing passam a citar a mesma chave `run/teste/projeto/tentativa`.
- ✅ Cobertura deixa de ser “ficou verde” e passa a ser inventário com procedência e denominador (RF19).
- ✅ O exemplo de CI demonstra o contrato sem acoplar este repositório a um alvo remoto fixo (`baseURL` atual de `playwright.config.ts` deixa de ser default implícito — RF17).

**Trade-offs aceitos:**
- ⚠️ Vínculo semântico critério↔teste além das referências continua revisão humana quando a referência existe mas o sentido diverge (Q3). O mapa não se autoaprova.
- ⚠️ Sem SHA/deployment demonstrável, `deployment_identity.demonstrated` é `false` e a conclusão *estrita* de CI bloqueia, ainda que a URL responda (CA26).
- ⚠️ Prova de alvo de domínio não é equivalência matemática de nós DOM (FE10).

## Guardrails derivados desta decisão

- **[GA-E01]:** Manifestos novos são aditivos no run `.e2e-engine/runs/<runId>/`. Não substituir `summary.md` / `mutations.diff` / `bug_report.md` / `escalations.md`.
- **[GA-E02]:** Toda decisão que depende de evidência (exit 2, `TEST_DRIFT`, `PRODUCT_BUG`, conclusão estrita de CI) exige pacote da mesma chave; mix de run/teste/projeto/tentativa, hash divergente, anexo fora da raiz ou trace obrigatório ausente bloqueia.
- **[GA-E03]:** Pacote finalizado não se sobrescreve. Reprodução e pós-healing = registro novo com `original_failure_ref`. Resultado pós-healing não se apresenta como sucesso original.
- **[GA-E04]:** Inventário esperado é anterior ao run e independente do reporter. Healing e candidato não reduzem seleção, projeto, filtro ou exclusões.
- **[GA-E05]:** Origem `observed` nunca é promovida a `approved` por geração, rename ou mapa. `draft` não vira fonte por mover arquivo.
- **[GA-E06]:** O exemplo de CI não publica comentário, não altera proteção de branch, não implanta produto e não contém segredo. Readiness HTTP não comprova identidade do build.
- **[GA-E07]:** Caminho de anexo, inclusive após resolver symlink, permanece na raiz autorizada de artefatos. Credencial em argumento, manifesto, mapa, relatório, exemplo ou corpus → rejeição.
- **[GA-E08]:** Não acrescentar interceptor de rede, dashboard ou túnel para cumprir evidência, cobertura ou smoke.

## Status de vigência

- **Aceito** — em vigor desde 2026-10-24, aplica-se a todas as features a partir de `otimizar-governanca-e2e-ia`
- Para superseder: crie ADR-NNN com `Supersede: ADR-005` e atualize este status para `Supersedido por ADR-NNN`
