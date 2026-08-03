# Política de Self-Healing

> **Este documento revoga duas permissões do fluxo oficial.** A skill
> `playwright-cli`, em `spec-driven-testing.md`, autoriza no healing:
>
> - §3.3 — *"Edit the test file: update the locator, **assertion**, step order,
>   or inputs..."*
> - §3.5 — *"mark the test `test.fixme(...)`"*
>
> Ambas ficam **proibidas** aqui. O restante do fluxo oficial de heal
> (§3.1 diagnosticar, §3.2 attach e inspecionar, §3.4 reconciliar com a spec)
> continua valendo integralmente — e §3.4, que manda parar e perguntar quando
> não se sabe se é regressão ou spec desatualizada, é exatamente o espírito
> certo. Só falta o enforcement.

## Por que revogar

Um loop que edita o teste quando o teste falha tem um ponto de convergência
óbvio: **a suíte que sempre passa.** Cada correção que afrouxa uma asserção
aumenta a taxa de aprovação, então um otimizador ingênuo caminha direto para
uma suíte verde e inútil.

O fluxo oficial tem bons freios — "never add sleeps", "never silently skip",
"stop and ask the user" — mas todos são instrução ao agente. Quando a instrução
compete com a pressão de deixar a suíte verde, a instrução perde às vezes. Uma
vez basta: um bug encoberto por asserção afrouxada não deixa rastro.

Por isso o gate é `scripts/assertion_guard.py` — determinístico, com exit code.
Não é conselho.

## A decomposição

```
await expect( page.getByRole('row').filter({ hasText: 'A' }).getByTestId('cel') ).toHaveText('A')
              └──────────────────── LOCATOR ────────────────────┘  └────── MATCHER ──────┘
                     endereçamento — como achar o elemento          semântica — o que se prova
```

| Parte | Regime |
| :--- | :--- |
| Matcher: nome, argumentos, `not.` | **Congelado.** Alterou → rejeita |
| Contagem de asserções | **Congelada.** Alterou → rejeita |
| Header `// intent:` | **Congelado.** Alterado ou removido → rejeita |
| Locator dentro de `expect()` | Mutável **sob prova de mesmo elemento** |
| Locator fora de `expect()` (ações) | Livre |
| `timeout` | Livre até o teto de 30s |

`timeout` é a única opção do matcher que não conta como semântica. Opções que
mudam o significado — `ignoreCase`, `useInnerText` — permanecem congeladas.

## Prova de mesmo elemento

Mudar o locator dentro de uma asserção abriria a porta para apontá-la a um
elemento diferente que a satisfaça trivialmente:

```ts
// ANTES — prova que o total é 10
await expect(page.getByTestId('total')).toHaveText('10');
// DEPOIS — matcher idêntico, mas agora prova outra coisa
await expect(page.getByTestId('rodape-exemplo')).toHaveText('10');
```

Por isso o gate devolve **exit 2** nesse caso, não exit 0. Antes de aplicar,
confirme com `playwright-cli snapshot` que o locator novo resolve para o **mesmo
nó** que o antigo. Sem essa confirmação, trate como rejeitado.

## Tabela de permissões

| Permitido | Proibido |
| :--- | :--- |
| Trocar estratégia de locator | Alterar ou remover `expect()` |
| Adicionar espera web-first | Alterar ou remover o `// intent:` |
| Corrigir escopo de linha (sob prova) | Remover steps |
| Ajustar timeout até 30s | `.skip()`, `.fixme()`, `.only()` |
| Corrigir setup e teardown | Afrouxar matcher (`toBeVisible` → `toBeAttached`) |
| Estabilizar dados de fixture | Trocar valor esperado |

Nunca `waitForTimeout`, nunca `networkidle` — nisto o oficial e esta política
concordam.

## Uso

```bash
uv run scripts/assertion_guard.py <antes.ts> <depois.ts>
```

O `// intent:` é lido **dos arquivos**, nunca recebido por argumento. Um guarda
cujo valor de referência é fornecido por quem está sendo guardado não guarda
nada — o agente poderia passar a mesma string duas vezes e o teste passaria
vazio. Para suítes legadas sem o header, `--sem-intent` desativa a exigência
(mas se o header existir nos dois arquivos, ele ainda é comparado).

| Exit | Decisão | Ação |
| :---: | :--- | :--- |
| 0 | APROVA | Aplique e registre o diff |
| 2 | APROVA_COM_PROVA | Verifique no snapshot; sem prova, trate como 1 |
| 1 | REJEITA | Descarte o patch |
| 3 | ERRO_DE_USO | Argumentos inválidos |

Falha de parsing resulta em rejeição. **Um gate que não consegue analisar não
pode aprovar.**

## Depois de uma rejeição

Não reformule o patch para passar pelo gate. A rejeição é informação: ela diz
que a correção que você imaginou altera o que o teste prova — ou seja, o
problema provavelmente não está no teste.

```
1ª rejeição  → reconsidere a classificação. Provavelmente não é TEST_DRIFT.
2ª rejeição  → pare. Escale ao usuário com o veredito do gate anexado.
```

Tentar caminhos alternativos até o gate ceder é exatamente o comportamento que
o gate existe para bloquear.

## E quando o teste está certo e o produto errado?

O oficial resolve com `test.fixme()` após confirmação do usuário. Aqui não:
`fixme` é rejeitado pelo gate, porque um teste marcado assim some do radar e
volta a ser ruído em vez de sinal.

Faça em vez disso:

1. Classifique como `PRODUCT_BUG` — com citação literal da fonte de verdade.
2. Gere `bug_report.md`.
3. **Deixe o teste vermelho.** Ele é a evidência viva do defeito.
4. Registre em `escalations.md` que a suíte tem N vermelhos conhecidos e por quê.

Um vermelho conhecido e documentado é honesto. Um `fixme` é dívida silenciosa.

## Auditoria

Toda mutação aprovada vai para `mutations.diff` como diff unificado legível,
com a justificativa. O usuário sempre vê o que foi alterado e por quê.

**Self-healing invisível é inaceitável.** Um teste que mudou sozinho sem
registro é pior que um teste vermelho: o vermelho ao menos é honesto.
