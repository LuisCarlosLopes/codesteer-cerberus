---
name: codesteer-test-guard
description: Camada de governança para testes E2E em Playwright — decide o que pode ser testado, contra qual ambiente, e impede que o conserto automático de um teste enfraqueça o que ele prova. Use SEMPRE que o usuário quiser criar, gerar ou manter testes end-to-end, testes de interface, suíte de regressão ou testes CRUDL de uma URL; e SEMPRE que um teste Playwright estiver falhando e for preciso decidir se é bug do produto, deriva do teste ou instabilidade de ambiente. Opera sobre a skill oficial playwright-cli, que executa a mecânica de navegação, geração e execução. Não cobre teste de carga, teste de API isolado nem correção do código da aplicação.
---

# codesteer-test-guard

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
uv run scripts/guard.py --url <URL> --mode <regression|spec-driven> [--truth <ref>]
```

- **exit 0** → prossiga. Leia `scope`: `CRUDL` libera criar/editar/apagar;
  `RL` restringe a listar e ler.
- **exit != 0** → **PARE.** Mostre `errors` e peça correção. Não contorne.
- `hitl` não vazio → pergunte ao usuário e **aguarde resposta**.

Sem `uv`, use `python3 scripts/guard.py` — não tem dependências.

### 2. O modo é declarado, e determina o que você pode afirmar

Pergunte se o usuário não disse. Não escolha sozinho.

| Modo | Quando | Consequência |
| :--- | :--- | :--- |
| `regression` | Sem requisito escrito | Congela o comportamento atual. **`PRODUCT_BUG` é inalcançável** |
| `spec-driven` | Com requisito, critério de aceite ou ticket | Único modo que pode afirmar defeito, e só com citação literal |

Declare ao usuário, em `regression`:

> Os testes vão codificar o comportamento atual. Uma falha futura indica que
> algo **mudou**, não que algo está **errado**. Não é possível afirmar "isto é
> um bug" quando a expectativa foi extraída do próprio produto.

O `plan.md` do fluxo oficial serve como spec em ambos os modos; grave-o em
`.memory-bank/e2e-specs/<feature>.plan.md`. Em `spec-driven`, cada cenário deve
apontar para a fonte externa — requisito, ticket, contrato — não apenas para o
que você observou navegando.

### 3. Seletor ruim bloqueia a geração

**Delegue esta etapa ao subagent `e2e-discovery`.** Ele roda o
`playwright-cli`, examina o snapshot e devolve rotas, autenticação e o nível
A–D em ~150 linhas — em vez de encher seu contexto com snapshot bruto. Se o
subagent não estiver instalado, faça você mesmo seguindo
`references/selector-health.md`.

Classifique de A a D **antes** de gerar qualquer teste.

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
e `// seed:` do fluxo oficial:

```ts
// spec: .memory-bank/e2e-specs/produtos.plan.md
// intent: produto criado aparece na lista como Ativo
```

Uma frase: o que este teste prova. É o valor que o gate congela na restrição 6 —
sem ele, o healing não tem referência e é bloqueado.

### 5. Todo dado criado é rastreável e removido

Prefixe todo registro com `e2e-<runId>-`. Teardown em `afterEach` **e**
varredura final por prefixo. Se `scope` for `RL`, gere só List e Read, e marque
Create/Update/Delete como `SKIPPED_BY_GUARD` no relatório — visivelmente.

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

Mais um aviso heurístico (A1): dado literal em `.fill()` sem o prefixo `e2e-`,
que pode escapar do teardown. Aviso não falha o build — confira e decida.

---

## Fluxo

```
0. GUARD          scripts/guard.py                    ← esta skill
1. MODO           pergunte; declare a consequência    ← esta skill
2. DISCOVERY      → subagent e2e-discovery            ← delegado
3. SELETORES      nível A–D vem do subagent; D bloqueia
4. AUTH           setup project + storageState        ← esta skill
5. PLAN           playwright-cli: .memory-bank/e2e-specs/*.plan.md ← oficial
6. GENERATE       playwright-cli: gere os .spec.ts    ← oficial
                  + prefixo de dados e teardown       ← esta skill
7. POM            refatore; --check-po + spec_lint     ← esta skill
8. RUN            npx playwright test                 ← oficial
9. TRIAGEM        → subagent e2e-triage               ← delegado
10. HEAL          só se TEST_DRIFT, e só sob o gate   ← esta skill governa
                  tocou um PO? rode --check-po de novo
11. REPORT        summary, mutations.diff, bug_report ← esta skill
```

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
conclusão, não do material bruto.

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
| `INFRA_FLAKE` | Retry com backoff, máx. 3 |
| `TEST_DRIFT` | Único caso que autoriza editar o teste → passo 10 |
| `BEHAVIOR_CHANGED` | **Não conserte.** Reporte |
| `PRODUCT_BUG` | **Não conserte.** Gere `bug_report.md` com citação literal |
| `UNCLASSIFIED` | **Não conserte.** Escale |

### Orçamento

Pare e vá ao relatório ao atingir: 8 iterações no run, 3 curas no mesmo teste,
20 minutos, ou timeout individual acima de 30s. Encerre com `BUDGET_EXCEEDED`.
**Nunca desabilite testes para terminar verde.**

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
| Orçamento esgotado com testes vermelhos | Não, mas relate |
| `UNCLASSIFIED` | Não, mas relate |
| Resíduo de dados após teardown | Não, mas relate com a lista |

---

## Verificar a instalação

```bash
uv run scripts/assertion_guard.py --self-test   # 19 casos
uv run scripts/spec_lint.py --self-test         # 10 casos
uv run scripts/guard.py --self-test             # 10 casos
uv run scripts/assertion_guard.py --check-po tests/   # invariante do POM
npx --no-install playwright-cli --version       # skill oficial disponível?
ls .claude/agents/e2e-*.md                      # subagents instalados?
```

Os três self-tests devem sair com código 0. **Se o gate falhar em qualquer caso,
não execute o passo 10** — a barreira está quebrada.

Se `playwright-cli` não estiver instalado: `npm install -g @playwright/cli@latest`.

## Referências

- `references/healing-policy.md` — o gate, e o que ele revoga do fluxo oficial
- `references/triage-guide.md` — árvore de classificação de falha
- `references/auth-playbook.md` — autenticar uma vez; armadilhas de sessão
- `references/pom-policy.md` — estrutura, fixtures, e por que o expect fica no spec
- `references/selector-health.md` — níveis A–D e o bloqueio no D
- Mecânica de Playwright → skill **`playwright-cli`** e suas references
