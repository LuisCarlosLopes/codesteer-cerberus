# Instalação — codesteer-test-guard

Camada de governança sobre a skill oficial `playwright-cli`. Funciona em
Claude Code CLI e Cursor.

## O que é, e o que não é

Esta skill **não executa Playwright**. Ela governa quem executa.

| Camada | Quem | O quê |
| :--- | :--- | :--- |
| Mecânica | skill oficial **`playwright-cli`** | Navegar, snapshot, gerar locator, gerar teste, rodar, tracing, storage state |
| **Política** | **esta skill** | O que pode ser testado, contra qual ambiente, e o que o healing não pode tocar |

As cinco restrições que ela acrescenta:

| # | Restrição | Como é enforçada |
| :---: | :--- | :--- |
| 1 | Host desconhecido não sofre mutação; produção exige flag + allowlist + confirmação | `guard.py`, **exit code** |
| 2 | Modo declarado; `PRODUCT_BUG` inalcançável em `regression` | `SKILL.md` + subagent |
| 3 | Seletor nível D bloqueia a geração | `selector-health.md` + subagent |
| 4 | Dado criado tem prefixo e teardown | `SKILL.md` |
| 5 | Healing não altera asserção, matcher, `intent`, nem introduz `skip`/`fixme` | `assertion_guard.py`, **exit code** |

**A #5 é a razão de a skill existir.** O fluxo oficial
(`spec-driven-testing.md` §3.3) autoriza editar asserção durante o healing, e
§3.5 permite `test.fixme()`. São bons freios, mas todos por instrução ao
agente. Aqui viram exit code.

## Pré-requisito: a skill oficial

```bash
npm install -g @playwright/cli@latest
npx --no-install playwright-cli --version
```

Sem ela, esta skill não tem o que governar.

## Passo 1 — copie para o seu repositório

```bash
cp -r skills .claude .cursor /caminho/do/seu/repo/
```

## Passo 2 — ligue os caminhos de descoberta

Cada ferramenta procura skills num diretório diferente. Uma fonte, três links:

```bash
cd /caminho/do/seu/repo
mkdir -p .claude/skills .cursor/skills .agents/skills

ln -s ../../skills/codesteer-test-guard .claude/skills/codesteer-test-guard
ln -s ../../skills/codesteer-test-guard .cursor/skills/codesteer-test-guard
ln -s ../../skills/codesteer-test-guard .agents/skills/codesteer-test-guard   # Codex CLI
```

| Ferramenta | Procura em |
| :--- | :--- |
| Claude Code | `.claude/skills/` |
| Cursor | `.cursor/skills/` |
| Codex CLI | `.agents/skills/` |

**Windows:** symlink exige `git config core.symlinks true` e Developer Mode.
Se a squad tiver Windows, troque os links por cópia com um passo de sincronização.

## Passo 3 — verifique

```bash
cd skills/codesteer-test-guard
uv run scripts/assertion_guard.py --self-test   # 13 casos
uv run scripts/guard.py --self-test             # 10 casos
```

Ambos devem sair com código 0.

Sem `uv`? `guard.py` não tem dependências e roda com `python3` direto. O gate
precisa de duas:

```bash
pip install tree-sitter tree-sitter-typescript
python3 scripts/assertion_guard.py --self-test
```

> Se o gate falhar em qualquer caso, **não use o passo de healing**. A barreira
> está quebrada e o loop pode adulterar asserções.

## Passo 4 — use

```
crie testes e2e para https://app-staging.empresa.com/produtos
```

A skill dispara pela descrição, roda o `guard.py`, pergunta o modo e delega a
mecânica ao `playwright-cli`.

- **`regression`** — sem requisito escrito. Congela o comportamento atual.
  Detecta *mudança*, não *defeito*.
- **`spec-driven`** — com requisito, critério de aceite ou ticket. Único modo
  que pode afirmar `PRODUCT_BUG`, e só com citação literal do oráculo.

## Estrutura

```
skills/codesteer-test-guard/
├── SKILL.md                      ← as 5 restrições e o fluxo
├── references/
│   ├── healing-policy.md         ← o gate, e o que revoga do oficial
│   ├── triage-guide.md           ← árvore de classificação de falha
│   ├── selector-health.md        ← níveis A–D, bloqueio no D
│   ├── auth-playbook.md          ← esvaziado: delega ao oficial
│   └── selector-policy.md        ← esvaziado: virou selector-health.md
└── scripts/
    ├── guard.py                  ← ambiente e modo (sem dependências)
    └── assertion_guard.py        ← o gate (tree-sitter)

.claude/agents/{e2e-discovery,e2e-triage}.md    ← Claude Code
.cursor/agents/{e2e-discovery,e2e-triage}.md    ← Cursor (corpo idêntico)
```

Os dois `references` esvaziados são stubs de propósito: apontam para onde a
informação foi, para que ninguém reintroduza a duplicata depois.

Os dois subagents são **read-only**. `e2e-triage` sem permissão de escrita é
defesa em profundidade: quem classifica não deve poder editar o teste que julga.

## Personalização

| Quero mudar | Edite |
| :--- | :--- |
| Teto de timeout do healing | `MAX_TIMEOUT_MS` em `assertion_guard.py` |
| Padrões de host de dev/staging | `PADROES_AMBIENTE` em `guard.py` |
| Orçamento do loop | seção correspondente do `SKILL.md` |
| Critério dos níveis A–D | `references/selector-health.md` |

Ao mexer no gate, **adicione o caso a `CASOS` no self-test antes de mudar a
lógica.** É a única parte do sistema onde um erro passa despercebido e
contamina tudo depois — foi exatamente assim que dois bugs apareceram durante
a construção.

## Se um dia o oficial cobrir isto

Se `playwright-cli` passar a enforçar a fronteira do healing, esta skill perde
a razão de existir e deve ser aposentada. É o resultado desejável. Até lá, a
lacuna do §3.3 é real e não tem enforcement.
