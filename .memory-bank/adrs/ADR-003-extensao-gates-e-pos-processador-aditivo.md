# ADR-003: Extensão dos três gates e pós-processador aditivo

**Status:** Aceito
**Data:** 2026-10-24
**Feature de origem:** otimizar-governanca-e2e-ia
**Autores:** codesteer.architect skill

---

## Contexto

As operações públicas atuais são três CLIs, todas com `--self-test` na CI:

| Gate | Funções-âncora | Exit | Papel |
|---|---|---|---|
| `guard.py` | `avaliar`, `classificar_host`, `validar_truth_arquivo` | 0/1/3 | Autoriza alvo, modo, escopo |
| `assertion_guard.py` | `gate`, `decompor`, `check_po`, `extrair_intent` | 0/1/2/3 | Congela a prova do healing |
| `spec_lint.py` | `lint`, `analisar_spec`, `analisar_po`, `orcamento_smoke` | 0/1/3 | Invariantes estáticas da suíte |

O TSD acrescenta seis operações observáveis (superfície de projeto, política estrita, proveniência/pós-processamento, triagem estruturada, completude de CI, avaliação do agente). Se cada uma virar um executor ou um quarto “gate de run”, o Cerberus deixa a fronteira de ADR-001. Se todas incharem os três scripts sem critério, o contrato legado fica opaco e o `--self-test` de 57 casos mistura-se com I/O de reporters.

A tecnologia de AST (Tree-sitter já usado em `assertion_guard.py` / `spec_lint.py` versus Compiler API) **não** é decisão desta ADR — o TSD a deixa para implementação, com FE08 proibindo outro compilador como requisito desta entrega. O que é estrutural é *onde* a operação vive e se ela executa o produto.

## Decisão

Decidimos particionar as operações novas em duas classes:

**Extensões opt-in dos três gates existentes** (mesmo processo, mesma CLI, flags/modos novos, códigos de saída inalterados):

- `guard.avaliar` + validação de `PoliticaDeProjeto` no perfil estrito.
- `assertion_guard.gate` endurecido (prova por teste, não listas globais; wrappers/literais/alvo; `detail.alvo_dominio` em exit 2) e `comparar_superficie` contra `ManifestoDeBaseline`.
- `spec_lint.lint` fail-closed (parse, raiz, inventário, asserção por caso, `@smoke` por caso com herança de `describe`) e recusa de mutação de domínio identificada em smoke.

**Pós-processador aditivo local** (não é gate de autorização nem runner):

- Lê inventário esperado *já protegido*, reporters nativos do Playwright e anexos sob a raiz autorizada.
- Emite `PacoteDeEvidencia`, `MapaDeCobertura` (`coverage-map.json` + `coverage.md`) no run existente `.e2e-engine/runs/<runId>/`.
- Expõe validação de triagem estruturada, verificação de completude do exemplo de CI e publicação de `RegistroDeAvaliacao`.
- Não abre browser, não lança subprocesso, não redefine o esperado, não aplica patch.

Humanos continuam lendo `summary.md`, `mutations.diff`, `bug_report.md`, `escalations.md`. JSON de agente/CI não depende de parse desses Markdown.

## Alternativas Consideradas

| Alternativa | Por que foi descartada |
|---|---|
| A. Um comando monólito que autoriza, roda a suíte, cura e publica | Vira runner (ADR-001 / FE08); mistura I/O de browser com política; quebra o piso dos 57 self-tests como contrato isolado. |
| B. Seis CLIs novas independentes dos gates | Duplica invocação e códigos; o consumidor deixa de ter um único `guard` / `assertion_guard` / `spec_lint`; aumenta superfície sem ganho de fronteira. |
| C. Estender os três gates + um pós-processador aditivo que só lê artefatos | Adotada: CLI e exit codes atuais permanecem; evidência/cobertura/CI são composição sobre o run nativo, não um quarto executor. |

## Consequências

**Positivas:**
- ✅ Os 57 casos de `--self-test` continuam o piso da job `self-tests` em `.github/workflows/ci.yml`; regressões novas são adicionais, não substitutas.
- ✅ Pós-processamento é idempotente após `finalized_at`: revalidar não muta o pacote (TSD 5.3).
- ✅ Planner escolhe nomes de flags (Q1) sem reusar código de saída; o contrato observável já está no TSD.

**Trade-offs aceitos:**
- ⚠️ Análise interprocedural profunda (rebind de `expect`, imports dinâmicos) continua fail-closed: forma não suportada não recebe `APROVA`. Não há promessa de equivalência semântica geral de TypeScript (FE10).
- ⚠️ O pós-processador depende de reporters nativos bem configurados no host (`playwright.config.ts` hoje tem `trace: on-first-retry` com `retries: 0` — o perfil diagnóstico desta feature precisa de `retain-on-failure` mesmo com zero retries).

## Guardrails derivados desta decisão

- **[GA-G01]:** Não criar quarto gate que execute teste ou aplique healing. Operações de evidência/cobertura/CI são pós-processamento ou validação sobre artefatos já produzidos.
- **[GA-G02]:** CLI, campos JSON atuais e significados de exit 0/1/2/3 dos três gates permanecem. Expansões são aditivas e opt-in. Falso `APROVA` que passa a `REJEITA` é correção desejada, não regressão de contrato.
- **[GA-G03]:** Forma desconhecida, parse inválido, dependência não resolvida ou baseline insuficiente → `REJEITA` / falha fechada. Nunca `APROVA` silencioso.
- **[GA-G04]:** Comparação de asserções é por teste (`test_id` estável), não por listas globais ordenadas de matchers. `decompor` hoje zip-global é o déficit que a extensão fecha.
- **[GA-G05]:** Tecnologia de parser permanece decisão de implementação *dentro* do processo Python dos gates existentes. Não introduzir ponte Node/Compiler API como requisito desta entrega.
- **[GA-G06]:** Relatórios humanos em `.e2e-engine/runs/<runId>/reports/` e `.spec.md` / `.plan.md` em `.memory-bank/e2e-specs/` permanecem; manifests novos usam `schema_version: 1` e falham fechado se a versão for desconhecida.

## Status de vigência

- **Aceito** — em vigor desde 2026-10-24, aplica-se a todas as features a partir de `otimizar-governanca-e2e-ia`
- Para superseder: crie ADR-NNN com `Supersede: ADR-003` e atualize este status para `Supersedido por ADR-NNN`
