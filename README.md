# CodeSteer Test Guard

Camada de **governança** para testes E2E construídos com **[Playwright](https://playwright.dev)**.

Ela decide o que pode ser testado, contra qual ambiente, e impede que o
*healing* automático de um teste enfraqueça o que ele prova. A mecânica de
browser — navegar, tirar snapshot, gerar locator, gerar teste, rodar, tracing,
storage state — fica por conta do Playwright em si e da skill oficial
[`playwright-cli`](https://github.com/microsoft/playwright-cli) (Microsoft).

**Esta skill não executa Playwright. Ela governa quem executa.**

| Camada | Quem | O quê |
| :--- | :--- | :--- |
| Mecânica | **Playwright** + skill oficial **`playwright-cli`** | Navegar, snapshot, gerar locator, gerar teste, rodar (`npx playwright test`), tracing, storage state |
| **Política** | **este plugin** | Ambiente, modo, seletores A–D, POM, dados com teardown, gate de healing |

Os testes gerados são **Playwright Test** puro (`@playwright/test`, ver
[`package.json`](package.json) e [`playwright.config.ts`](playwright.config.ts))
— nada de framework proprietário. O que este projeto adiciona é a política em
cima: o fluxo oficial (`plan → generate → heal`) é bom, mas autoriza editar
asserção e usar `test.fixme()` no healing — freios que hoje só existem como
instrução ao agente. Aqui viram **exit code**: se o gate rejeita, o patch não
entra.

---

## Como funciona

### As seis restrições

| # | Restrição | Enforcement |
| :---: | :--- | :--- |
| 1 | Host desconhecido não sofre mutação; produção exige allowlist + confirmação | `scripts/guard.py` (exit code) |
| 2 | Modo declarado; `PRODUCT_BUG` inalcançável em `regression` | `SKILL.md` + agents |
| 3 | Seletor nível D bloqueia a geração | `references/selector-health.md` + agent `e2e-discovery` |
| 4 | Testes em Page Object Model; `expect()` nunca dentro do page object | `assertion_guard.py --check-po` + `spec_lint.py` |
| 5 | Dado criado tem prefixo `e2e-<runId>-` e teardown | `SKILL.md`; aviso A1 no `spec_lint.py` |
| 6 | Healing não altera asserção, matcher, `// intent:`, nem introduz `skip`/`fixme` | `assertion_guard.py` (exit code) |

A **#6** é a razão de a skill existir. Sem ela, o loop de cura automática pode
"passar" o teste Playwright removendo o que ele prova.

### Modos

| Modo | Quando | Consequência |
| :--- | :--- | :--- |
| `regression` | Sem requisito escrito | Congela o comportamento atual do produto. Falha futura = *mudou*, não *está errado*. `PRODUCT_BUG` inalcançável |
| `spec-driven` | Com requisito, ticket ou `.spec.md` **approved** | Único modo que pode afirmar defeito — e só com citação literal da fonte |

Spec gerada só pela UI nasce como **draft**. O `guard.py` rejeita draft (`E008`)
até haver aprovação humana. Playbook:
[`references/spec-generation.md`](skills/codesteer-test-guard/references/spec-generation.md).

### Fluxo (resumo)

```
0. GUARD       scripts/guard.py          → ambiente + modo + truth
1. MODO        declare regression|spec-driven
2. DISCOVERY   agent e2e-discovery       → rotas, auth, saúde A–D
3. SPEC/PLAN   (spec-driven: draft → HITL → approved → plan)
4. GENERATE    playwright-cli + refactor POM + // intent:
5. LINT        assertion_guard --check-po + spec_lint
6. RUN         npx playwright test
7. TRIAGE      agent e2e-triage          → classificação (read-only)
8. HEAL        patch → assertion_guard antes/depois → só então aplica
```

Detalhe operacional completo: [`skills/codesteer-test-guard/SKILL.md`](skills/codesteer-test-guard/SKILL.md).

### Agents (read-only)

| Agent | Papel |
| :--- | :--- |
| `e2e-discovery` | Mapeia a URL (rotas, CRUDL, auth, nível A–D de seletor) sem encher o contexto com snapshot bruto do Playwright |
| `e2e-triage` | Classifica falha de teste (`INFRA_FLAKE`, `TEST_DRIFT`, `BEHAVIOR_CHANGED`, `PRODUCT_BUG`, `UNCLASSIFIED`). **Não edita** o teste que julga |

Ambos são read-only de propósito: quem descobre ou classifica não pode editar
o teste, o que remove o incentivo de forçar uma classificação mais confortável.

### O que o lint / gate rejeitam

`spec_lint.py` (varredura da suíte gerada):

| Código | Problema |
| :---: | :--- |
| E1–E2 | `waitForTimeout`, `networkidle` |
| E3 | Seletor frágil (classe gerada, `nth-child`, …) |
| E4 | Falta `// intent:` |
| E5–E6 | `.only()` / `.skip()` / `.fixme()` |
| E7–E8 | Spec sem asserção; `expect()` dentro de page object |
| A1 | Dado em `.fill()` sem prefixo `e2e-` (aviso) |

`assertion_guard.py` (gate de healing): compara a versão antes/depois de um
patch e rejeita remoção ou afrouxamento de asserção, mudança do header
`// intent:`, introdução de `skip`/`fixme`, ou timeout acima do teto.
Exit 2 (`APROVA_COM_PROVA`) = o locator dentro de `expect()` mudou — só aplica
com prova, no snapshot, de que resolve para o **mesmo** elemento.

---

## Uso

```
crie testes e2e para https://app-staging.empresa.com/produtos
```

Só a fonte de verdade (para no HITL, sem gerar teste ainda):

```
gere a spec / critérios de aceite para https://app-staging.empresa.com/cadastro
```

Exemplo de `.spec.md`:
[`examples/cadastro.spec.md`](skills/codesteer-test-guard/examples/cadastro.spec.md).

Artefatos típicos no repositório de produto:

```
.memory-bank/e2e-specs/<feature>.spec.md    # critérios (draft → approved)
.memory-bank/e2e-specs/<feature>.plan.md    # plano operacional
tests/…                                     # .spec.ts (Playwright) + page objects
```

---

## Pré-requisitos

Playwright é a base de tudo. Este repositório já traz `@playwright/test` como
dependência (ver [`package.json`](package.json)):

```bash
npm install
npx playwright install   # baixa os browsers
```

E a skill oficial que executa a mecânica de navegação/geração:

```bash
npm install -g @playwright/cli@latest
npx --no-install playwright-cli --version
```

Sem o Playwright e sem a skill oficial, este plugin não tem o que governar.

Gates com análise AST (`assertion_guard.py`, `spec_lint.py`) precisam de:

```bash
pip install tree-sitter tree-sitter-typescript
# ou: uv run … (se usar uv no projeto)
```

`guard.py` roda com `python3` puro, sem dependências.

---

## Instalação por cliente

Você **não precisa** copiar pastas para o repositório de produto. Instale o
plugin a partir deste repositório git ou de uma pasta local.

### Claude Code

```
/plugin marketplace add LuisCarlosLopes/codesteer-test-guard
/plugin install codesteer-test-guard
```

Pasta local: `/plugin marketplace add /caminho/para/codesteer-test-guard` e
depois `/plugin install`. Teste: `claude --plugin-dir /caminho/para/codesteer-test-guard`.

### GitHub Copilot CLI

```bash
copilot plugin install LuisCarlosLopes/codesteer-test-guard
# ou: copilot plugin install /caminho/para/codesteer-test-guard
```

Remover: `copilot plugin uninstall codesteer-test-guard`.

**Copilot Cloud Agent:** habilite em `.github/copilot/settings.json`
(`enabledPlugins`) no repositório de produto.

### Cursor (Desktop)

Instale pelo Marketplace / Team Marketplace a partir deste repositório, ou
aponte o plugin local (`.cursor-plugin/plugin.json` + `skills/` + `agents/`).

Neste repo, symlinks em `.cursor/skills` e `.cursor/agents` apontam para a
fonte canônica (DX local).

### Cursor Cloud

Cloud Agents não leem `~/.cursor`. Escolha uma:

1. Plugin no Team Marketplace marcado como **Required**, ou
2. Commit de `skills/codesteer-test-guard/` e `agents/e2e-*.md` no repositório de produto

Detalhes em [`AGENTS.md`](AGENTS.md).

### GitKraken Pro (Agent Mode)

Não há formato de plugin próprio. No Agent Mode, escolha Claude Code, Copilot
CLI ou Cursor e instale o plugin correspondente **antes** de iniciar a sessão.

### Kiro (Power)

Importe este repositório como Custom Power ([`POWER.md`](POWER.md)). Siga o
onboarding (Playwright, `python3`/`uv`, `playwright-cli`, self-tests).

---

## Estrutura do repositório

```
skills/codesteer-test-guard/
├── SKILL.md                 # as 6 restrições e o fluxo completo
├── examples/                # ex.: cadastro.spec.md
├── references/
│   ├── spec-generation.md   # draft → HITL → approved → plan
│   ├── healing-policy.md    # o que o gate aprova / rejeita
│   ├── pom-policy.md        # POM; expect fica no .spec.ts
│   ├── selector-health.md   # níveis A–D de seletor
│   ├── triage-guide.md      # árvore de classificação de falha
│   └── auth-playbook.md     # storageState / login único por run
└── scripts/
    ├── guard.py             # ambiente, modo, E008 (draft)
    ├── assertion_guard.py   # gate de healing + --check-po
    └── spec_lint.py         # varredura estática da suíte

agents/                      # e2e-*.md canônicos; *.agent.md = symlink (Copilot)
.claude-plugin/               # marketplace Claude Code
.cursor-plugin/               # plugin Cursor
plugin.json                  # plugin Copilot CLI
playwright.config.ts         # config Playwright Test deste repositório
package.json                 # @playwright/test como devDependency
```

`playwright-cli` sob `.claude/skills/` neste repo é só DX local — **não** vai
no manifest do plugin.

---

## Ajustar a skill (personalização)

A fonte canônica é **`skills/codesteer-test-guard/`**. Edite ali; os hosts
consomem via plugin/symlinks. Depois de mudar política ou gate, rode os
self-tests (abaixo) e, se possível, o roteiro de verificação ponta a ponta
descrito no `SKILL.md`.

| Quero mudar | Onde |
| :--- | :--- |
| Texto das 6 restrições / orçamento do loop / passos do fluxo | [`SKILL.md`](skills/codesteer-test-guard/SKILL.md) |
| Teto de timeout no healing | `MAX_TIMEOUT_MS` em `scripts/assertion_guard.py` |
| Hosts de local / staging / prod (regex) | `PADROES_AMBIENTE` em `scripts/guard.py` |
| Critério dos níveis A–D e bloqueio no D | [`references/selector-health.md`](skills/codesteer-test-guard/references/selector-health.md) |
| Pastas/nomes de page object; `expect` só no spec | [`references/pom-policy.md`](skills/codesteer-test-guard/references/pom-policy.md) + `PADROES_PO` nos scripts |
| Regras do lint (waitForTimeout, seletores frágeis, …) | `REGRAS_TEXTO` / `RE_SELETOR_FRAGIL` em `scripts/spec_lint.py` |
| O que o healing pode ou não tocar | [`references/healing-policy.md`](skills/codesteer-test-guard/references/healing-policy.md) |
| Fluxo draft → approved | [`references/spec-generation.md`](skills/codesteer-test-guard/references/spec-generation.md) |
| Comportamento de discovery / triage | [`agents/e2e-discovery.md`](agents/e2e-discovery.md), [`agents/e2e-triage.md`](agents/e2e-triage.md) |
| Config Playwright deste repositório | [`playwright.config.ts`](playwright.config.ts) |

**Ao mexer no gate (`assertion_guard.py`):** adicione o caso em `CASOS` no
self-test **antes** de mudar a lógica. É a única peça em que um erro passa
despercebido e contamina o healing depois.

**Agents Copilot:** `*.agent.md` são **symlinks** para os `.md` canônicos —
edite só o `.md`; o Copilot resolve o sufixo que exige sem duplicar conteúdo.

Versionamento: ao publicar comportamento novo, bump `version` em
`.claude-plugin/plugin.json`, `.cursor-plugin/plugin.json` e `plugin.json`
(mesmo número).

---

## Self-tests dos gates

```bash
cd skills/codesteer-test-guard
python3 scripts/guard.py --self-test
pip install tree-sitter tree-sitter-typescript   # uma vez
python3 scripts/assertion_guard.py --self-test
python3 scripts/spec_lint.py --self-test
```

Com `uv`:

```bash
uv run scripts/assertion_guard.py --self-test
uv run scripts/spec_lint.py --self-test
```

Os três devem sair com código 0. Se o gate falhar, **não use healing** — a
barreira está quebrada.

CI: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda esses
self-tests em todo push/PR.

---

## Se o oficial cobrir isto

Se `playwright-cli` passar a enforçar a fronteira do healing (asserção /
`fixme`), esta skill perde a razão de existir e deve ser aposentada. Até lá, a
lacuna é real e não tem enforcement no fluxo oficial do Playwright.

---

## Licença

MIT — veja [LICENSE](LICENSE).
