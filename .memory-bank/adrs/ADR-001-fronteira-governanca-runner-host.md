# ADR-001: Fronteira permanente governança ↔ runner ↔ host

**Status:** Aceito
**Data:** 2026-10-24
**Feature de origem:** otimizar-governanca-e2e-ia
**Autores:** codesteer.architect skill

---

## Contexto

O plugin Cerberus já declara, em `skills/codesteer-cerberus/SKILL.md`, que **não executa Playwright**. Os gates `guard.py`, `assertion_guard.py` e `spec_lint.py` são scripts Python determinísticos, sem rede e sem modelo. A mecânica de browser, geração, run e tracing mora na skill oficial `playwright-cli` e no runner `@playwright/test`. A CI do plugin (`.github/workflows/ci.yml`) só invoca `--self-test` dos três gates.

O TSD v1.2 (RF01, RF16, FE08) exige manter essa fronteira enquanto acrescenta proveniência, cobertura e exemplo de CI. Sem decisão explícita, a tentação é fazer o Cerberus lançar o browser, orquestrar o run ou instalar um serviço de healing — e com isso perder a propriedade que justifica o plugin: política auditável, independente do executor.

A confiança de baseline, política e identidade de deployment **não cabe no gate**: `e2e-discovery` e `e2e-triage` expõem `Bash`; um hash escrito na mesma sessão não prova origem humana. Quem protege origem é o host/CI.

## Decisão

Decidimos manter três camadas distintas e não atravessáveis:

1. **Host / CI** — protege política, baseline, inventário esperado, SHA e identidade de deployment; aplica o candidato já validado; lança o runner; retém artefatos.
2. **Cerberus (governança)** — autoriza (`guard.avaliar`), valida prova (`assertion_guard.gate`, `assertion_guard.check_po`, `spec_lint.lint`), classifica e registra. Não abre browser, não lança subprocesso de teste, não aplica recuperação em runtime.
3. **Runner externo** — `playwright-cli` e `@playwright/test` executam, geram locators e emitem reporters nativos.

Setas de Cerberus para Playwright são **autorizações consumidas pelo host/orquestrador**, não chamadas feitas pelos scripts de governança.

## Alternativas Consideradas

| Alternativa | Por que foi descartada |
|---|---|
| A. Cerberus como orquestrador/runner (lança `npx playwright test`, healing em runtime, interceptor obrigatório) | Viola RF01/FE08; acopla política ao executor; cria runner concorrente; recuperação oculta escapa de `assertion_guard.gate`. |
| B. Serviço remoto de healing/evidência (estilo TestSprite ou equivalente) | FE01; introduz autenticação, rede e dependência operacional fora do escopo; a pesquisa de 2026-10-24 é evidência datada, não contrato. |
| C. Três camadas distintas (host protege, Cerberus governa, Playwright executa) | Adotada: reusa os gates e a CI atuais; escala evidência/cobertura como artefato local; confiança estrita só existe quando o host protege a origem (Q5). |

## Consequências

**Positivas:**
- ✅ Gates continuam testáveis sem browser (piso dos 57 `--self-test` em `ci.yml`).
- ✅ Healing permanece um patch inspecionável que passa por `assertion_guard.gate` antes de o host aplicar.
- ✅ Consumidor de produto liga deployment à origem confiável do *seu* CI; o plugin só oferece exemplo parametrizado.

**Trade-offs aceitos:**
- ⚠️ Imutabilidade do pacote finalizado e “aprovação humana” valem no limite da proteção do host — o contrato declara o nível, não promete sandbox físico (FE10, NFR 9.2).
- ⚠️ Agentes `e2e-discovery` / `e2e-triage` permanecem read-only por declaração de ferramentas; isolamento real é do host, não da skill.

## Guardrails derivados desta decisão

- **[GA-B01]:** Nenhum script de governança desta feature abre browser, chama modelo ou lança o runner Playwright.
- **[GA-B02]:** Não criar runner concorrente, skill paralela a `playwright-cli`, interceptor de rede obrigatório nem núcleo baseado em outro compilador como requisito desta entrega.
- **[GA-B03]:** Aplicação do candidato e reexecução são atos do host/orquestrador; o conteúdo aplicado deve corresponder ao hash validado por `assertion_guard.gate` (ou pela comparação de superfície). Sem recuperação distinta do arquivo aprovado.
- **[GA-B04]:** Declaração de ferramentas nos agents não substitui sandbox; o ARD e a documentação distinguem política, bloqueio estático, permissão do servidor e limitação do host.

## Status de vigência

- **Aceito** — em vigor desde 2026-10-24, aplica-se a todas as features a partir de `otimizar-governanca-e2e-ia`
- Para superseder: crie ADR-NNN com `Supersede: ADR-001` e atualize este status para `Supersedido por ADR-NNN`
