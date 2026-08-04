---
name: codesteer-cerberus
description: Camada de governança para testes E2E em Playwright — decide o que pode ser testado, contra qual ambiente, e impede que o conserto automático de um teste enfraqueça o que ele prova. Use SEMPRE que o usuário quiser criar, gerar ou manter testes end-to-end, testes de interface, suíte de regressão ou testes CRUDL de uma URL; SEMPRE que quiser suíte de smoke, smoke test, verificação pós-deploy ou health check de caminho crítico (inclusive contra produção); SEMPRE que quiser gerar spec, critérios de aceite ou fonte de verdade E2E (`.spec.md`) a partir de discovery ou material do usuário; e SEMPRE que um teste Playwright estiver falhando e for preciso decidir se é bug do produto, deriva do teste ou instabilidade de ambiente. Opera sobre a skill oficial playwright-cli, que executa a mecânica de navegação, geração e execução. Não cobre teste de carga, teste de API isolado nem correção do código da aplicação.
---

# codesteer-cerberus

Esta skill **não executa Playwright**. Ela governa quem executa.

## Divisão de responsabilidade

| Camada | Quem | O quê |
| :--- | :--- | :--- |
| Mecânica | skill **`playwright-cli`** (oficial Microsoft) | Navegar, snapshot, gerar locator, gerar teste, rodar, tracing, storage state |
| **Política** | **esta skill** | O que pode ser testado, contra qual ambiente, e o que o healing não pode tocar |

Use a skill `playwright-cli` para toda ação de browser e geração de código. Ela
tem `snapshot` com refs de acessibilidade, `generate-locator`, `state-save`,
`console`, `requests`, `tracing-*` e a reference `spec-driven-testing.md` com o
fluxo plan → generate → heal. **Não reimplemente nada disso aqui.**

O que esta skill acrescenta são seis restrições que o fluxo oficial não impõe.

---

## As seis restrições

### 1. Ambiente é verificado antes de qualquer coisa

O fluxo oficial roda contra qualquer URL. Este não.

```bash
uv run scripts/guard.py --url <URL> --mode <regression|spec-driven|smoke> [--truth <ref>]
```

- **exit 0** → prossiga. Leia `scope`: `CRUDL` libera criar/editar/apagar;
  `RL` restringe a listar e ler. Em `smoke` o `scope` é sempre `RL`, em
  qualquer ambiente — não é o host que restringe, é o modo.
- **exit != 0** → **PARE.** Mostre `errors` e peça correção. Não contorne.
- `hitl` não vazio → pergunte ao usuário e **aguarde resposta**.

Sem `uv`, use `python3 scripts/guard.py` — não tem dependências.

### 2. O modo é declarado, e determina o que você pode afirmar

Pergunte se o usuário não disse. Não escolha sozinho.

| Modo | Quando | Consequência |
| :--- | :--- | :--- |
| `regression` | Sem requisito escrito | Congela o comportamento atual. **`PRODUCT_BUG` é inalcançável** |
| `spec-driven` | Com requisito, critério de aceite ou ticket | Único modo que pode afirmar defeito, e só com citação literal |
| `smoke` | Verificação pós-deploy do caminho crítico | Somente leitura por construção (`scope: RL` sempre). **`PRODUCT_BUG` é inalcançável** |

Declare ao usuário, em `regression`:

> Os testes vão codificar o comportamento atual. Uma falha futura indica que
> algo **mudou**, não que algo está **errado**. Não é possível afirmar "isto é
> um bug" quando a expectativa foi extraída do próprio produto.

Declare ao usuário, em `smoke`:

> A suíte prova que o caminho crítico **está de pé**, não que ele está correto.
> Nada será criado, editado ou apagado — nem em staging. Se o fluxo só é
> verificável criando registro, ele não cabe aqui; é caso de `regression`.

`smoke` é o modo que se pode apontar para produção com menos cerimônia: não há
mutação para autorizar. Mas **o guard não infere produção** — sem
`--allow-production`, um host de produção é classificado como `unknown`. Por
isso, em `smoke`, host `unknown` gera `hitl`: pergunte se o alvo é produção
antes de seguir, e declare a intenção se for. Ver
`references/smoke-policy.md`: escolha do caminho crítico, orçamento, tag
`@smoke` e o que a asserção precisa provar.

Em `spec-driven`, `--truth` deve ser:

- um `.memory-bank/e2e-specs/<feature>.spec.md` com **`status: approved`**, ou
- um doc externo já aprovado pelo usuário (ticket, `criterios-aceite.md` legado)

Spec gerada só pela UI nasce como **draft**. O `guard.py` rejeita draft com
`E008` — aprove no passo 4c antes de seguir. Ver
`references/spec-generation.md`.

O `plan.md` do fluxo oficial serve como plano operacional em ambos os modos;
grave-o em `.memory-bank/e2e-specs/<feature>.plan.md`. Em `spec-driven`, cada
cenário do plan deve citar a fonte (`Fonte: <feature>.spec.md#CA-01`) — não
apenas o que você observou navegando.

### 3. Seletor ruim bloqueia a geração

**Delegue esta etapa ao subagent `e2e-discovery`.** Ele roda o
`playwright-cli`, examina o snapshot e devolve rotas, autenticação e o nível
A–D em ~150 linhas — em vez de encher seu contexto com snapshot bruto. Se o
subagent não estiver instalado, faça você mesmo seguindo
`references/selector-health.md`.

Classifique de A a D **antes** de gerar qualquer teste. Em `smoke`, o nível vale
para o **caminho crítico**, não para o app inteiro: se o checkout tem ganchos
estáveis e o resto é D, gere o smoke do checkout e reporte o D do resto.

> **Nível D — classes geradas (`css-1x2y3z`), sem roles, DOM instável: PARE.**
> Não gere testes. Entregue `selector-recommendations.md` com os `data-testid`
> necessários.

O fluxo oficial gera sobre qualquer seletor. Suíte sobre nível D é dívida com
aparência de cobertura.

### 4. Os testes seguem POM, e a asserção fica no spec

O fluxo oficial gera teste plano, com locator inline. **Refatore para Page
Object Model antes do primeiro run.** Ver `references/pom-policy.md`.

A regra que sustenta o resto: **o page object expõe locators e ações; o
`expect()` fica no `.spec.ts`.** Se a asserção migrar para o PO, o gate da
restrição 6 fica cego — ele lê o spec.

Obrigatório após gerar, e após qualquer cura que toque um page object:

```bash
uv run scripts/assertion_guard.py --check-po tests/   # foco: expect em PO
uv run scripts/spec_lint.py tests/                    # varredura completa
```

Exit 1 → corrija antes de rodar a suíte. O `--check-po` é a checagem focada
usada durante o healing; o `spec_lint` é a varredura ampla do passo 7.

**Todo `.spec.ts` gerado declara o header `// intent:`**, ao lado dos `// spec:`
e `// seed:` do fluxo oficial. Em `spec-driven`, declare também `// truth:`
apontando para o critério citável:

```ts
// truth: .memory-bank/e2e-specs/produtos.spec.md#CA-01
// spec: .memory-bank/e2e-specs/produtos.plan.md
// intent: produto criado aparece na lista como Ativo
```

Em `regression` sem fonte aprovada, omita `// truth:`.

Uma frase no `// intent:`: o que este teste prova. É o valor que o gate congela
na restrição 6 — sem ele, o healing não tem referência e é bloqueado.

**Em `smoke`, POM é opcional** — a suíte é rasa e curta, e exigir page object
para 5 casos é cerimônia sem retorno; reuse os POs que já existirem. O que não
relaxa: `expect()` continua fora do page object (E8), o `// intent:` continua
obrigatório, e cada arquivo carrega a tag `@smoke` (E9). Sem `// truth:`.

### 5. Todo dado criado é rastreável e removido

Prefixe todo registro com `e2e-<runId>-`. Teardown em `afterEach` **e**
varredura final por prefixo. Se `scope` for `RL`, gere só List e Read, e marque
Create/Update/Delete como `SKIPPED_BY_GUARD` no relatório — visivelmente.

Em `smoke` esta restrição é vácua: nada é criado. Se você escreveu um teardown,
revise o caso — provavelmente ele não é smoke.

### 6. O healing passa pelo gate — sempre

**Esta é a restrição que justifica a skill existir.**

O fluxo oficial (`spec-driven-testing.md` §3.3) autoriza editar a asserção
durante o healing, e §3.5 permite `test.fixme()`. Ambos ficam **revogados** aqui.

Ver `references/healing-policy.md`. Procedimento:

```bash
cp tests/<x>.spec.ts /tmp/antes.ts
# escreva a versão corrigida em /tmp/depois.ts
uv run scripts/assertion_guard.py /tmp/antes.ts /tmp/depois.ts
```

O gate lê o `// intent:` **dos dois arquivos**. Você não o informa — e portanto
não pode reescrevê-lo para caber num teste mais fraco. Alterar ou remover o
header é rejeitado.

| Exit | Decisão | Ação |
| :---: | :--- | :--- |
| 0 | APROVA | Aplique. Registre o diff |
| 2 | APROVA_COM_PROVA | Locator dentro de `expect()` mudou. Confirme no snapshot que resolve para o **mesmo elemento**. Sem prova, trate como rejeitado |
| 1 | REJEITA | **Descarte o patch.** Não reformule para passar. 2ª rejeição → escale |

**Nunca edite um `.spec.ts` sem passar pelo gate.** Se você se pegar querendo
remover asserção, afrouxar matcher ou adicionar `.skip`, a resposta certa não é
um patch — é reportar a falha.

### O que o `spec_lint` pega

| Código | Erro |
| :---: | :--- |
| E1 | `waitForTimeout` |
| E2 | `networkidle` |
| E3 | Seletor frágil: classe gerada, `nth-child`, cadeia estrutural |
| E4 | Falta o header `// intent:` |
| E5 | `.only()` — silencia o resto da suíte sem avisar |
| E6 | `.skip()` / `.fixme()` |
| E7 | Spec sem nenhuma asserção — passa sempre |
| E8 | `expect()` dentro de page object |
| E9 | Teste smoke sem a tag `@smoke` — `--grep @smoke` não o executa |
| E10 | Asserção tautológica (`expect(page).toBeTruthy()`, `body` visível) |

E três avisos heurísticos, que não falham o build — confira e decida:

| Código | Aviso |
| :---: | :--- |
| A1 | Dado literal em `.fill()` sem o prefixo `e2e-`; pode escapar do teardown |
| A2 | Suíte smoke acima de 12 casos — deixou de ser smoke |
| A3 | Ação aparentemente mutante em teste smoke (smoke é `RL`) |

---

## Fluxo

```
0. GUARD          scripts/guard.py                    ← esta skill
1. MODO           pergunte; declare a consequência    ← esta skill
2. DISCOVERY      → subagent e2e-discovery            ← delegado
3. SELETORES      nível A–D vem do subagent; D bloqueia
4. AUTH           setup project + storageState        ← esta skill
4b. SPEC_DRAFT    .memory-bank/e2e-specs/*.spec.md    ← orquestrador (sem subagent)
4c. SPEC_APPROVE  HITL; status: approved; re-guarde   ← orquestrador (sem subagent)
                  se o usuário pediu só a spec → PARE aqui
5. PLAN           deriva do .spec.md aprovado (ou observação em regression)
                  → .memory-bank/e2e-specs/*.plan.md  ← oficial + esta skill
6. GENERATE       playwright-cli: gere os .spec.ts    ← oficial
                  + prefixo de dados e teardown       ← esta skill
7. POM            refatore; --check-po + spec_lint     ← esta skill
8. RUN            npx playwright test                 ← oficial
9. TRIAGEM        → subagent e2e-triage               ← delegado
10. HEAL          só se TEST_DRIFT, e só sob o gate   ← esta skill governa
                  tocou um PO? rode --check-po de novo
11. REPORT        summary, mutations.diff, bug_report ← esta skill
```

### Smoke (fluxo curto)

Mesmo fluxo, quatro atalhos — detalhe em `references/smoke-policy.md`:

| Passo | Em `smoke` |
| :--- | :--- |
| 4b / 4c | **Pulados.** Não há spec a aprovar; smoke não afirma requisito |
| 5 PLAN | Vira a lista de caminhos críticos. Pergunte ao usuário quais fluxos, quebrados, valem rollback — e mostre a lista antes de gerar |
| 7 POM | Opcional. `spec_lint` continua obrigatório (E9 e E10 são dele) |
| 8 RUN | `npx playwright test --grep @smoke` |
| 9 TRIAGEM | Árvore de smoke: 5xx reproduzível é `CRITICAL_PATH_DOWN`, não flake |

### Spec de critérios (passos 4b e 4c)

**Não delegue.** O orquestrador redige o rascunho e conduz o HITL, seguindo
`references/spec-generation.md`. Volume baixo (relatório de discovery + material
do usuário) — não justifica subagent.

1. Grave `.memory-bank/e2e-specs/<feature>.spec.md` com `status: draft`
2. Mostre o caminho e o resumo; pergunte aprovar / editar / descartar
3. **Aguarde resposta**
4. Se aprovado: `status: approved` + `approved_by` + `approved_at`
5. Rode `guard.py --mode spec-driven --truth <arquivo>` — `E008` se ainda draft
6. Se o usuário pediu **só** critérios de aceite: **PARE** após 4c

Em `regression` sem pedido de spec, pule 4b/4c e vá ao PLAN. Em `smoke`, 4b/4c
não se aplicam.

### Autenticação (passo 4)

**Nenhum teste faz login.** Autentique uma vez por run com um *setup project*,
salve o `storageState` em disco, e todo teste nasce autenticado. Ver
`references/auth-playbook.md` para o padrão completo e os perfis múltiplos.

```ts
// playwright.config.ts
projects: [
  { name: 'setup', testMatch: /.*\.setup\.ts/ },
  { name: 'chromium',
    use: { storageState: '.e2e-engine/auth/user.json' },
    dependencies: ['setup'] },
]
```

O `auth.setup.ts` **deve asserir que o login funcionou** antes de salvar o
estado. Sem isso você grava um estado deslogado e a suíte inteira falha com
causa invisível.

Antes de gravar qualquer coisa: `.env` e `.e2e-engine/auth/` no `.gitignore`.
Um `storageState` commitado é um token vazado.

**MFA ou SSO interativo → escalada bloqueante.** Peça ao usuário que logue uma
vez e salve o estado com `playwright-cli state-save`. Não automatize leitura de
código de MFA.

## Os dois subagents

Passos 2 e 9 são delegados por um motivo só: **contenção de contexto.**
Snapshot de página e saída de trace são volumosos; o orquestrador precisa da
conclusão, não do material bruto. Passos **4b/4c (spec) não entram nesta
lista** — ficam no orquestrador.

| Subagent | Passo | Devolve | Permissão |
| :--- | :---: | :--- | :--- |
| `e2e-discovery` | 2 | Rotas, autenticação, nível A–D | read-only |
| `e2e-triage` | 9 | Uma `Classification` com evidência | read-only |

Ambos são **read-only de propósito**. `e2e-triage` sem permissão de escrita é
defesa em profundidade: quem classifica não pode editar o teste que julga, o
que remove o incentivo a chamar `TEST_DRIFT` o que é defeito do produto.

Se os subagents não estiverem instalados, execute os passos 2 e 9 você mesmo
seguindo as references. O resultado é o mesmo; só custa mais contexto.

### Triagem (passo 9)

**Delegue ao subagent `e2e-triage`.** Siga `references/triage-guide.md` —
a árvore é fixa.

| Classe | Ação |
| :--- | :--- |
| `INFRA_FLAKE` | Retry com backoff, máx. 3 — em `smoke`, retry único |
| `TEST_DRIFT` | Único caso que autoriza editar o teste → passo 10 |
| `BEHAVIOR_CHANGED` | **Não conserte.** Reporte |
| `PRODUCT_BUG` | **Não conserte.** Gere `bug_report.md` com citação literal |
| `CRITICAL_PATH_DOWN` | Só em `smoke`. **Não conserte.** Reporte já; recomende rollback ou escalada |
| `UNCLASSIFIED` | **Não conserte.** Escale |

### Orçamento

Pare e vá ao relatório ao atingir: 8 iterações no run, 3 curas no mesmo teste,
20 minutos, ou timeout individual acima de 30s. Encerre com `BUDGET_EXCEEDED`.
**Nunca desabilite testes para terminar verde.**

Em `smoke` o orçamento é outro, porque a suíte gateia deploy: **máx. 12 casos,
30s por caso, 5 minutos de suíte, 1 retry.** Segunda cura no mesmo caso smoke →
pare de curar e reescreva a âncora; o alvo está fundo demais.

### Relatório (passo 11)

Em `.e2e-engine/runs/<runId>/reports/`: `summary.md`, `mutations.diff` (todo
patch aprovado, legível), `bug_report.md` (só `spec-driven`, só com citação),
`escalations.md`.

No chat, seja breve: quantos testes, quantos verdes, o que exige atenção.

---

## Segredos

Delegue a mecânica de sessão ao `playwright-cli` (`state-save`, `state-load`,
reference `storage-state.md`). As regras de política:

- Credenciais nunca em código gerado, log, trace, relatório ou estado.
  Sempre `process.env.E2E_*`.
- `.env` e `.e2e-engine/auth/` no `.gitignore` antes de gravar qualquer coisa.
- **MFA e SSO interativo: pare.** Peça ao usuário que logue uma vez e salve o
  estado com `playwright-cli state-save auth.json`. Não automatize leitura de
  código de MFA — é um controle de segurança que existe de propósito.
- Trace captura requisições completas. Ao anexar trace a um relatório que sai
  da máquina do usuário, avise que pode conter segredos de sessão.

---

## Escalar ao usuário

| Situação | Bloqueia? |
| :--- | :---: |
| Seletores nível D | Sim |
| MFA ou SSO interativo | Sim |
| Produção sem allowlist | Sim |
| Gate rejeitou o mesmo patch 2× | Sim |
| `CRITICAL_PATH_DOWN` em smoke | Sim — reporte antes de qualquer outra coisa |
| Orçamento esgotado com testes vermelhos | Não, mas relate |
| `UNCLASSIFIED` | Não, mas relate |
| Resíduo de dados após teardown | Não, mas relate com a lista |

---

## Verificar a instalação

```bash
uv run scripts/assertion_guard.py --self-test   # 19 casos
uv run scripts/spec_lint.py --self-test         # 17 casos (inclui smoke)
uv run scripts/guard.py --self-test             # 21 casos (inclui E008 e smoke)
uv run scripts/assertion_guard.py --check-po tests/   # invariante do POM
npx --no-install playwright-cli --version       # skill oficial disponível?
ls .claude/agents/e2e-*.md                      # subagents instalados?
```

Os três self-tests devem sair com código 0. **Se o gate falhar em qualquer caso,
não execute o passo 10** — a barreira está quebrada.

Se `playwright-cli` não estiver instalado: `npm install -g @playwright/cli@latest`.

## Referências

- `references/spec-generation.md` — critérios `.spec.md`, HITL e derivação do plan
- `references/smoke-policy.md` — caminho crítico, orçamento, tag `@smoke`, produção
- `references/healing-policy.md` — o gate, e o que ele revoga do fluxo oficial
- `references/triage-guide.md` — árvore de classificação de falha
- `references/auth-playbook.md` — autenticar uma vez; armadilhas de sessão
- `references/pom-policy.md` — estrutura, fixtures, e por que o expect fica no spec
- `references/selector-health.md` — níveis A–D e o bloqueio no D
- Mecânica de Playwright → skill **`playwright-cli`** e suas references
