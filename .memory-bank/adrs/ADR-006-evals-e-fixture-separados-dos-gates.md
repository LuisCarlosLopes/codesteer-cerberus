# ADR-006: Fixture e corpus de avaliação separados dos gates determinísticos

**Status:** Aceito
**Data:** 2026-10-24
**Feature de origem:** otimizar-governanca-e2e-ia
**Autores:** codesteer.architect skill

---

## Contexto

A CI do plugin (job `self-tests` em `.github/workflows/ci.yml`) roda só `python3 scripts/{guard,assertion_guard,spec_lint}.py --self-test` — 57 casos determinísticos, sem browser e sem modelo. Isso garante o contrato dos gates; não mede se o *agente* encobre falha, classifica `TEST_DRIFT` indevido ou promove um defeito conhecido a verde.

O TSD (RF18, RF19, CA10, L05, FE10) pede corpus local inicial 24+8, três tentativas ao trocar modelo/skill, rótulo com fonte e justificativa, e métricas com denominador. Ensaios com modelo são manuais ou agendados — nenhum custo de API no fluxo comum. Não há SDK de provedor no núcleo. O resultado esperado vem da fixture/requisito, nunca do agente julgado. Held-out não treina o julgamento.

`npm test` hoje é placeholder (`echo "Error: no test specified"`). `playwright.config.ts` aponta alvo remoto. A fixture desta feature é o único lugar onde defeitos injetáveis são permitidos (FE07).

## Decisão

Decidimos três capacidades distintas, que não se substituem:

1. **Gates determinísticos** — `--self-test` atuais (57) + regressões dos falsos `APROVA`, propriedades do gate e fail-closed de schema. Rodam em **todo PR** na CI do plugin, sem browser e sem modelo.
2. **Fixture local de integração** — aplicação mínima com defeitos conhecidos e comportamento correto. Usada para: healing que continua detectando a falha-alvo; smoke 5xx → `CRITICAL_PATH_DOWN`; cleanup idempotente; exemplo de CI parametrizado; perfis nativos (`retain-on-failure` com zero retries, `forbidOnly`, orçamento, `--grep @smoke`). Alvo remoto de produto **não** é default implícito.
3. **Corpus de avaliação do agente** — 24 cenários de desenvolvimento + 8 held-out; até 3 tentativas; versões de modelo/skill/CLI/Playwright/config registradas; `RegistroDeAvaliacao` com `expected_label` externo, `actions[]`, `evidence_refs[]`, `covered_failure_still_detected` / `known_defect_still_red`. Publicação e consulta são operação do pós-processador (ADR-003). Ensaios **não** entram no job `self-tests` do fluxo comum.

A IA não substitui o gate. Revisão humana cobre ambiguidade. `UNCLASSIFIED` pode ser o rótulo correto. Não armazenar raciocínio privado: registrar ferramentas, ações, evidências e decisão declarada.

## Alternativas Consideradas

| Alternativa | Por que foi descartada |
|---|---|
| A. Apenas os 57 self-tests como medida de qualidade da feature | Determinístico e barato, mas cego a decisão do agente, falha encoberta e healing que “passa” o defeito da fixture (RF18). |
| B. SDK de provedor no núcleo e eval em todo PR | Introduz custo de API, credencial e não-determinismo no fluxo comum (NFR 9.1, RF20). Não é certificação estatística (FE10). |
| C. Gates em todo PR + fixture local na CI do plugin + corpus/ensaios fora do fluxo comum | Adotada: mede regra, integração e comportamento do agente em camadas; o núcleo permanece sem provedor. |

## Consequências

**Positivas:**
- ✅ Piso dos 57 casos permanece bloqueante da CI do plugin (CA14, L06).
- ✅ Falha encoberta no held-out bloqueia promoção da skill sem o agente ser juiz de si mesmo (CA10).
- ✅ Documentação e comando real de instalação deixam de depender de `npm test` placeholder e de `baseURL` remoto implícito.

**Trade-offs aceitos:**
- ⚠️ Corpus 24+8 é baseline publicada inicial, não certificação (Q4, FE10). Ampliar amostra é evolução posterior.
- ⚠️ Ensaios com modelo exigem operação manual/agendada e versões registradas; não há semáforo contínuo de “o agente está bom”.

## Guardrails derivados desta decisão

- **[GA-V01]:** Job de PR do plugin continua executando os 57 `--self-test` sem browser e sem modelo. Novas regressões de gate são adicionais, não substitutas.
- **[GA-V02]:** Nenhum SDK de provedor, chave de API ou custo de modelo no núcleo dos gates ou do pós-processador.
- **[GA-V03]:** `expected_label` e a fonte do rótulo são externos ao agente avaliado. Held-out não entra no conjunto de desenvolvimento nem ajusta o julgamento.
- **[GA-V04]:** Healing não pode tornar verde um defeito conhecido da fixture (`known_defect_still_red` / `covered_failure_still_detected`).
- **[GA-V05]:** Denominador zero nas métricas de RF19 é N/A, nunca 100%. Inventário ou seleção vazios continuam falha de validação, não sucesso.
- **[GA-V06]:** Fixture e exemplo de CI não usam aplicação remota real de produto como default. Defeitos injetáveis existem só na fixture deste plugin.

## Status de vigência

- **Aceito** — em vigor desde 2026-10-24, aplica-se a todas as features a partir de `otimizar-governanca-e2e-ia`
- Para superseder: crie ADR-NNN com `Supersede: ADR-006` e atualize este status para `Supersedido por ADR-NNN`
