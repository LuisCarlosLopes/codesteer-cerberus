# ADR-004: Superfície de projeto contra baseline protegida pelo host

**Status:** Aceito
**Data:** 2026-10-24
**Feature de origem:** otimizar-governanca-e2e-ia
**Autores:** codesteer.architect skill

---

## Contexto

`assertion_guard.gate(antes, depois)` compara dois arquivos. `--check-po` recusa `expect()` em `*.page.ts` / `*.po.ts`, mas não vê redefinição de locator em helper, fixture, mock, `playwright.config.ts` ou seleção (`grep`, projetos, exclusões). A prova de locator hoje exige o “mesmo elemento” no DOM — um re-render recria o nó.

O TSD (RF05, RF15, CA05, A07) exige superfície completa e inventário esperado **antes** do run, extraídos de revisão aprovada fora do controle do patch. Hash escrito pelo healer não demonstra aprovação. Import dinâmico, não resolvido ou fora da raiz autorizada impede aprovação automática.

## Decisão

Decidimos manter a CLI de dois arquivos e acrescentar modo de projeto opt-in em `assertion_guard`:

1. O host/CI extrai um `ManifestoDeBaseline` (`schema_version: 1`, `origin_revision`, `content_hashes`, `authorized_root`, `tests[]` com asserções por `test_id`, `truth_source`, `policy_profile`, `extracted_at`) de uma revisão **já aprovada**.
2. `comparar_superficie` confronta a superfície candidata (specs, page objects, helpers, fixtures, configuração, arquivos novos e removidos) com esse manifesto.
3. Candidato, healer e reporter **não** aprovam nem reduzem a baseline, a seleção, o projeto, o filtro ou o inventário esperado.
4. Locator em PO/helper que altere alvo de asserção recebe no mínimo exit 2 e análise de impacto nos specs dependentes. A prova deixa de ser “mesmo nó DOM” e passa a ser **mesmo alvo de domínio** (`detail.alvo_dominio`: entidade, papel/nome ou testid, cardinalidade, escopo) — ver composição em ADR-005.
5. Mudança de fixture, mock, config, identidade de `expect` ou seleção sem revisão → `REJEITA`. Dependência não resolvida → `REJEITA`.

Import estático local no subconjunto documentado é resolvido; o restante é conservador.

## Alternativas Consideradas

| Alternativa | Por que foi descartada |
|---|---|
| A. Continuar só a comparação isolada de dois `.spec.ts` | Interface atual simples, mas cega a locator indireto, helper novo e config — exatamente os buracos de CA05. |
| B. Diff textual do repositório inteiro como “superfície” | Inclui ruído (docs, lockfile) e não identifica asserção, `test_id` nem fonte de verdade; não substitui manifesto de prova. |
| C. Manifesto de baseline extraído pelo host + comparação opt-in da superfície relevante | Adotada: aditiva à CLI atual; a autoridade da baseline é o host, não o patch. |

## Consequências

**Positivas:**
- ✅ Healing de um spec não consegue esconder enfraquecimento em PO/helper/config.
- ✅ Inventário esperado (RF15) nasce da mesma origem protegida que a baseline — o reporter não redefine o esperado.
- ✅ `--check-po` permanece a checagem focada durante o loop; o modo de projeto é o gate de superfície.

**Trade-offs aceitos:**
- ⚠️ Resolução de imports é um subconjunto explícito; casos interprocedurais sobem para revisão humana (fail-closed, ADR-003).
- ⚠️ Extração da baseline é um ato do host/CI. Em disco local sem proteção, o manifesto declara confiança limitada (ADR-002 / Q5).

## Guardrails derivados desta decisão

- **[GA-S01]:** Baseline e inventário esperado são extraídos *antes* do run, de origem protegida pelo host. O patch candidato não é dono da baseline e não a reescreve.
- **[GA-S02]:** Sem manifesto suficiente, com hash da baseline sob controle do candidato, ou com dependência não resolvida → `REJEITA`. Nunca `APROVA` silencioso.
- **[GA-S03]:** Healing não altera asserção, matcher, valor esperado, `// intent:`, plano, mapa, seleção nem inventário; não introduz `skip`/`fixme`/`only`.
- **[GA-S04]:** Alteração de locator em PO/helper implica no mínimo exit 2 (`APROVA_COM_PROVA`) e impacto nos specs que dependem desse locator. Ausência de `expect` no PO não autoriza mudar locator/helper.
- **[GA-S05]:** Configuração Playwright, mocks, fixtures e identidade do símbolo `expect` são superfície protegida. Mudança exige revisão fora do healing.

## Status de vigência

- **Aceito** — em vigor desde 2026-10-24, aplica-se a todas as features a partir de `otimizar-governanca-e2e-ia`
- Para superseder: crie ADR-NNN com `Supersede: ADR-004` e atualize este status para `Supersedido por ADR-NNN`
