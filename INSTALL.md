# Instalação — codesteer-test-guard

Camada de governança sobre a skill oficial `playwright-cli`. Funciona em
Claude Code CLI e Cursor.

## O que é, e o que não é

Esta skill **não executa Playwright**. Ela governa quem executa.

| Camada | Quem | O quê |
| :--- | :--- | :--- |
| Mecânica | skill oficial **`playwright-cli`** | Navegar, snapshot, gerar locator, gerar teste, rodar, tracing, storage state |
| **Política** | **esta skill** | O que pode ser testado, contra qual ambiente, e o que o healing não pode tocar |

As seis restrições que ela acrescenta:

| # | Restrição | Como é enforçada |
| :---: | :--- | :--- |
| 1 | Host desconhecido não sofre mutação; produção exige flag + allowlist + confirmação | `guard.py`, **exit code** |
| 2 | Modo declarado; `PRODUCT_BUG` inalcançável em `regression` | `SKILL.md` + subagent |
| 3 | Seletor nível D bloqueia a geração | `selector-health.md` + subagent; seletor frágil no código: `spec_lint.py`, **exit code** |
| 4 | Testes seguem POM; `expect()` nunca dentro de um page object | `assertion_guard.py --check-po`, **exit code** |
| 5 | Dado criado tem prefixo e teardown | `SKILL.md`; prefixo ausente vira aviso em `spec_lint.py` |
| 6 | Healing não altera asserção, matcher, `// intent:`, nem introduz `skip`/`fixme` | `assertion_guard.py`, **exit code** |

**A #6 é a razão de a skill existir.** O fluxo oficial
(`spec-driven-testing.md` §3.3) autoriza editar asserção durante o healing, e
§3.5 permite `test.fixme()`. São bons freios, mas todos por instrução ao
agente. Aqui viram exit code.

## Pré-requisito: a skill oficial

```bash
npm install -g @playwright/cli@latest
npx --no-install playwright-cli --version
```

Sem ela, esta skill não tem o que governar.

## Dois repositórios, papéis diferentes

| Onde | O quê | Contém a fixture? |
| :--- | :--- | :---: |
| **Repo da skill** (esta pasta) | Fonte da skill. Onde ela é editada e verificada | Sim |
| **Repos de produto** da squad | Consomem a skill para testar suas aplicações | Não |

`fixtures/app-under-test/` é o **instrumento de medição da skill**, não parte
dela. Quem usa a skill num projeto real nunca precisa da fixture. Quem *mexe*
na skill precisa dela sempre — é o que responde "quebrei alguma coisa?" depois
de editar o `SKILL.md`.

Por isso o `cp` abaixo copia três pastas e deixa `fixtures/` para trás.

## Passo 1 — copie para o repositório de produto

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
uv run scripts/assertion_guard.py --self-test   # 19 casos
uv run scripts/spec_lint.py --self-test         # 10 casos
uv run scripts/guard.py --self-test             # 10 casos
```

Os três devem sair com código 0.

Sem `uv`? `guard.py` não tem dependências e roda com `python3` direto. O gate e
o lint precisam de duas:

```bash
pip install tree-sitter tree-sitter-typescript
python3 scripts/assertion_guard.py --self-test
python3 scripts/spec_lint.py --self-test
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
  que pode afirmar `PRODUCT_BUG`, e só com citação literal da fonte de verdade.

## Estrutura

```
skills/codesteer-test-guard/
├── SKILL.md                      ← as 6 restrições e o fluxo de 11 passos
├── references/
│   ├── healing-policy.md         ← o gate, e o que revoga do oficial
│   ├── pom-policy.md             ← convenção POM; expect fica no spec
│   ├── auth-playbook.md          ← autenticar uma vez (storageState)
│   ├── triage-guide.md           ← árvore de classificação de falha
│   ├── selector-health.md        ← níveis A–D, bloqueio no D
│   └── selector-policy.md        ← esvaziado: virou selector-health.md
└── scripts/
    ├── guard.py                  ← ambiente e modo (sem dependências)
    ├── assertion_guard.py        ← o gate + --check-po (tree-sitter)
    └── spec_lint.py              ← varredura estática da suíte gerada

fixtures/app-under-test/          ← app de verificação, zero dependências
├── server.js                     ← CRUDL com 4 variantes de defeito plantado
├── criterios-aceite.md           ← a FONTE DE VERDADE do modo spec-driven
└── roteiro-verificacao.md        ← V1–V5 e a rubrica

.claude/agents/{e2e-discovery,e2e-triage}.md    ← Claude Code
.cursor/agents/{e2e-discovery,e2e-triage}.md    ← Cursor (corpo idêntico)
```

`selector-policy.md` é um stub de propósito: aponta para onde a informação foi,
para que ninguém reintroduza a duplicata depois.

Os dois subagents são **read-only**. `e2e-triage` sem permissão de escrita é
defesa em profundidade: quem classifica não deve poder editar o teste que julga.

## Personalização

| Quero mudar | Edite |
| :--- | :--- |
| Teto de timeout do healing | `MAX_TIMEOUT_MS` em `assertion_guard.py` |
| Padrões de host de dev/staging | `PADROES_AMBIENTE` em `guard.py` |
| Orçamento do loop | seção correspondente do `SKILL.md` |
| Critério dos níveis A–D | `references/selector-health.md` |
| Convenção de POM, nomes, pastas | `references/pom-policy.md` |
| Quais arquivos contam como page object | `PADROES_PO` em `assertion_guard.py` e `spec_lint.py` |
| Regras do lint da suíte | `REGRAS_TEXTO` / `RE_SELETOR_FRAGIL` em `spec_lint.py` |

Ao mexer no gate, **adicione o caso a `CASOS` no self-test antes de mudar a
lógica.** É a única parte do sistema onde um erro passa despercebido e
contamina tudo depois — foi exatamente assim que dois bugs apareceram durante
a construção.

## Verificação de ponta a ponta

Os self-tests cobrem os scripts. Eles **não** cobrem o julgamento do agente
seguindo o `SKILL.md` — e é ali que mora o risco real.

```bash
node fixtures/app-under-test/server.js       # variante clean
# depois: bug-validation, drift-selectors, selectors-d
```

Siga `fixtures/app-under-test/roteiro-verificacao.md`. São cinco cenários; o
**V3 é bloqueante**: em `bug-validation` os seletores estão intactos e a
aplicação é que está errada. Se o agente classificar aquilo como `TEST_DRIFT` e
tentar consertar o teste, o sistema falhou no que importa — e o gate deve ter
rejeitado o patch.

Rode a verificação uma vez antes de entregar à squad, e de novo sempre que
mexer no `SKILL.md`.

## Se um dia o oficial cobrir isto

Se `playwright-cli` passar a enforçar a fronteira do healing, esta skill perde
a razão de existir e deve ser aposentada. É o resultado desejável. Até lá, a
lacuna do §3.3 é real e não tem enforcement.
