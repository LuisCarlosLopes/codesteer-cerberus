# codesteer-test-guard

Camada de governança para testes E2E em Playwright, para Claude Code CLI e Cursor.

**Ela não executa Playwright.** A mecânica — navegar, gerar locator, gerar
teste, rodar, tracing — é da skill oficial `playwright-cli`, da Microsoft.
Esta skill decide **o que pode ser testado, contra qual ambiente, e o que o
conserto automático de um teste não pode tocar.**

## Instalação

```bash
npm install -g @playwright/cli@latest     # a skill oficial, pré-requisito
./install.sh /caminho/do/seu/repositorio
```

Depois, no Claude Code ou Cursor, de dentro do seu repositório:

```
crie testes e2e para https://app-staging.suaempresa.com/produtos
```

Detalhes e instalação manual em [`INSTALL.md`](INSTALL.md).

## O problema que ela resolve

O fluxo oficial de *healing* autoriza, em `spec-driven-testing.md`:

> §3.3 — *"Edit the test file: update the locator, **assertion**, step order, or inputs..."*
> §3.5 — *"mark the test `test.fixme(...)`"*

Um loop que edita o teste quando o teste falha tem um ponto de convergência
óbvio: **a suíte que sempre passa.** Cada asserção afrouxada aumenta a taxa de
aprovação, então o caminho de menor resistência leva a uma suíte verde e
inútil — e um bug encoberto por asserção afrouxada não deixa rastro.

O oficial tem bons freios: *never add sleeps*, *never silently skip*, *stop and
ask the user*. Todos são instrução ao agente. Quando a instrução compete com a
pressão de deixar a suíte verde, a instrução perde às vezes. Uma vez basta.

Aqui os freios são **exit code**.

## As seis restrições

| # | Restrição | Enforcement |
| :---: | :--- | :--- |
| 1 | Host desconhecido não sofre mutação; produção exige flag + allowlist + confirmação | `guard.py` |
| 2 | Modo declarado; `PRODUCT_BUG` inalcançável em `regression` | instrução |
| 3 | Seletor nível D bloqueia a geração; seletor frágil no código é erro | instrução + `spec_lint.py` |
| 4 | POM: `expect()` nunca dentro de um page object | `assertion_guard.py --check-po` |
| 5 | Dado criado tem prefixo e teardown | instrução + aviso no lint |
| 6 | **Healing não altera asserção, matcher nem `// intent:`** | `assertion_guard.py` |

## Duas ideias que sustentam o resto

**Sem fonte de verdade externa, não existe "bug".** No modo `regression` a expectativa é
extraída do próprio produto — afirmar defeito seria circular. Só o modo
`spec-driven`, com requisito escrito, pode classificar `PRODUCT_BUG`, e só
citando o trecho contrariado **literalmente**. Sem citação, a classe é
`UNCLASSIFIED`. Uma engine que sempre classifica é uma engine que às vezes mente.

**O gate separa endereçamento de semântica.** Numa asserção, o *locator* diz
como achar o elemento e o *matcher* diz o que se prova:

```
await expect( page.getByRole('row').filter(...).getByTestId('cel') ).toHaveText('A')
              └──────────────── LOCATOR: mutável ────────────────┘  └─ MATCHER: congelado ─┘
```

O healing pode reescrever o endereço. Não pode tocar o que o teste prova.

## Verificar

```bash
cd skills/codesteer-test-guard
uv run scripts/assertion_guard.py --self-test   # 19 casos
uv run scripts/spec_lint.py --self-test         # 10 casos
uv run scripts/guard.py --self-test             # 10 casos
```

Os self-tests cobrem os scripts. Eles **não** cobrem o julgamento do agente
seguindo o `SKILL.md` — para isso existe a fixture:

```bash
node fixtures/app-under-test/server.js
```

Siga [`fixtures/app-under-test/roteiro-verificacao.md`](fixtures/app-under-test/roteiro-verificacao.md).
São cinco cenários; **V3 é o critério de release**.

## Estrutura

```
skills/codesteer-test-guard/   a skill (SKILL.md, references, scripts)
.claude/agents/                subagents do Claude Code — read-only
.cursor/agents/                idem para Cursor, corpo idêntico
fixtures/app-under-test/       app de verificação — NÃO vai para repo de produto
install.sh                     instala num repositório de produto
```

## Quando aposentar

Se o `playwright-cli` passar a enforçar a fronteira do healing, esta skill
perde a razão de existir. É o resultado desejável.
