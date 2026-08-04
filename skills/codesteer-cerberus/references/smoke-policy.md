# Smoke — o modo que só pergunta se está de pé

> Smoke não prova regra de negócio. Prova que o **caminho crítico responde**.
>
> É o único modo **somente leitura por construção** — e é exatamente isso que
> torna defensável apontá-lo para produção depois de um deploy.

## O que qualifica

| Cabe em smoke | Não cabe |
| :--- | :--- |
| A aplicação sobe e a rota raiz responde autenticada | Validação de campo obrigatório |
| Login com conta de serviço leva ao dashboard | Cálculo de total, regra de desconto |
| Listagem crítica carrega com dado real | Fluxo CRUD completo |
| Rota de saúde do front (sem 5xx, sem tela de erro) | Paginação, ordenação, filtro combinado |
| Um número/estado que prova que o backend respondeu | Qualquer coisa que precise **criar** registro |

Regra de corte: **se você precisou criar, editar ou apagar dado para provar,
não é smoke — é regressão.** Volte ao modo `regression`.

## Guard

```bash
uv run scripts/guard.py --url https://app-stg.empresa.com --mode smoke
```

Produção, pós-deploy:

```bash
uv run scripts/guard.py --url https://app.empresa.com --mode smoke \
  --allow-production --allowlist .e2e-engine/production-allowlist.txt
```

O que o guard garante em `smoke`:

- `mutations_allowed: false` e `scope: "RL"` **em qualquer ambiente** — inclusive
  local. Não é o ambiente que restringe; é o modo.
- `hitl` preenchido em produção, com o texto certo: sem mutação, mas confirme a
  janela de execução e a conta usada.
- **O guard não adivinha produção.** Ele reconhece local, dev e staging por
  padrão de host; qualquer outra coisa é `unknown`, e `production` só existe
  quando você declara `--allow-production`. Em `smoke` esse é o caso comum — é o
  modo feito para rodar pós-deploy — então host `unknown` em smoke gera **HITL,
  não só aviso**: pergunte se o alvo é produção antes de seguir.

  A allowlist não é uma barreira que o guard aplica sozinho a um host
  desconhecido; é o que você ganha ao declarar a intenção. Declare.
- `--truth` é aceito e **ignorado**, com aviso. `PRODUCT_BUG` é inalcançável em
  smoke — não há fonte de verdade citável para "estava no ar".

## Escolha do caminho crítico

Pergunte ao usuário, literalmente:

> Quais fluxos, se quebrarem depois de um deploy, valem um rollback?

Se ele não souber, derive do relatório do `e2e-discovery` (rota inicial, rota
mais profunda alcançável, listagem principal) e **mostre a lista antes de
gerar**. Não é HITL bloqueante como a aprovação de spec — mas escolher o
caminho crítico sozinho e em silêncio é escolher o que o rollback vai proteger.

Entre 3 e 8 casos. Um caso por caminho, não por asserção.

## Orçamento

| Item | Teto | Por quê |
| :--- | :---: | :--- |
| Casos na suíte | 12 | Acima disso o `spec_lint` avisa (A2): deixou de ser smoke |
| Caso individual | 30s | Mesmo teto do healing; smoke lento não gateia deploy |
| Suíte inteira | 5 min | Ninguém segura um deploy esperando |
| Retries | **1** | Ver abaixo |

O retry merece explicação. Em `regression`, 3 retries filtram intermitência.
Em smoke pós-deploy, retry longo atrasa a decisão de rollback **e mascara
indisponibilidade real** — que é justamente o que este modo existe para achar.
Duas falhas idênticas em smoke não são flake: são o caminho crítico caído.

## Anatomia

Local: `tests/smoke/**/*.spec.ts` (ou `*.smoke.spec.ts`). O `spec_lint`
reconhece smoke pelo **caminho ou pela tag** — um arquivo marcado `@smoke` fora
da pasta segue as regras de smoke do mesmo jeito, porque é a tag que decide o
que o CI executa. O caminho serve para pegar o arquivo que está na pasta certa
e esqueceu a tag (`E9`).

Rode o lint a partir da raiz do projeto (`spec_lint.py tests/`): o
reconhecimento por caminho usa o caminho recebido, não o absoluto — de dentro
de `tests/smoke/` o segmento se perde, e sobra só a tag.

```ts
// spec: .memory-bank/e2e-specs/smoke.plan.md
// intent: dashboard responde autenticado depois do deploy
import { test, expect } from '../fixtures';

test('dashboard carrega autenticado', { tag: ['@smoke'] }, async ({ page }) => {
  await page.goto('/dashboard');

  // Sinal de domínio, não "a página existe".
  await expect(page.getByRole('heading', { name: 'Resumo' })).toBeVisible();
  await expect(page.getByTestId('saldo-total')).not.toBeEmpty();
});
```

Obrigatório: header `// intent:` (como em qualquer spec) **e** a tag `@smoke`
no título ou na opção `tag:`. Sem a tag, `--grep @smoke` não executa o arquivo
e ele some do CI sem avisar ninguém — por isso é `E9`, erro, não aviso.

Se a sua suíte separa smoke por *project* (`testMatch`) em vez de `--grep`, a
tag continua exigida. Ela custa nada, documenta a intenção no próprio teste e
mantém o `--grep @smoke` funcionando de qualquer lugar — inclusive de um runner
que não conhece seus projects.

Sem `// truth:` — smoke não tem fonte de verdade.

## A asserção precisa provar algo

```ts
// PROIBIDO (E10) — passa com o produto quebrado
await expect(page.locator('body')).toBeVisible();
await expect(page).toBeTruthy();

// CERTO — só passa se o backend respondeu e a tela renderizou o domínio
await expect(page.getByRole('heading', { name: 'Resumo' })).toBeVisible();
await expect(page).toHaveURL(/\/dashboard/);
await expect(page.getByTestId('linha-pedido').first()).toBeVisible();
```

Um smoke que só checa que a página carregou é um smoke que fica verde durante
a queda. É o modo de falha mais comum deste tipo de suíte, e o mais caro:
ele consome o orçamento de confiança sem entregar sinal.

## Como as seis restrições se aplicam

| # | Em smoke |
| :---: | :--- |
| 1 | Guard obrigatório. `scope` é sempre `RL` — não há decisão a tomar |
| 2 | Modo declarado `smoke`. `PRODUCT_BUG` inalcançável, como em `regression` |
| 3 | Nível A–D vale **para o caminho crítico**, não para o app inteiro. Se o checkout tem `data-testid` e o resto do app é D, gere smoke do checkout e reporte o D do resto |
| 4 | POM **opcional** — a suíte é rasa e curta; reuse page objects se já existirem. O que **não** relaxa: `expect()` fora do page object (E8) e o `// intent:` |
| 5 | Vácua: nada é criado, nada precisa de teardown. Se você escreveu um `afterEach` de limpeza, revise — provavelmente não é smoke |
| 6 | Gate idêntico. Com uma leitura a mais: `TEST_DRIFT` recorrente em smoke é sintoma de âncora funda demais (ver abaixo) |

## Healing em smoke

O gate (`assertion_guard.py`) é o mesmo, sem exceção. O que muda é a leitura do
resultado:

> **Segunda cura no mesmo caso smoke → não cure. Reescreva a âncora.**

Um caso smoke deveria depender de dois ou três elementos muito estáveis. Se ele
deriva com frequência, o alvo está errado: você ancorou num detalhe de layout em
vez de num sinal de domínio. Trocar locator repetidamente mantém o verde e perde
o sentido do teste.

## Triagem em smoke

A árvore de `triage-guide.md` vale, com uma correção na entrada:

```
Erro 5xx, DNS, conexão ou timeout de ambiente em smoke?
├─ 1ª ocorrência        → retry único
└─ reproduziu idêntico  → CRITICAL_PATH_DOWN, não INFRA_FLAKE
```

Chamar de `INFRA_FLAKE` uma indisponibilidade reproduzível é o erro que anula o
modo: smoke existe para detectar exatamente isso. `CRITICAL_PATH_DOWN` não
autoriza editar o teste — autoriza avisar, e rápido.

## Autenticação

Mesmo padrão do `auth-playbook.md`: um setup project, `storageState` salvo,
nenhum teste faz login.

Duas regras extras em smoke, e ambas importam mais em produção:

- **Conta de serviço dedicada, com permissão mínima de leitura.** Nunca a conta
  de um usuário real, nunca uma conta com poder de escrita "só por
  conveniência". O guard bloqueia mutação no código; a conta bloqueia no
  servidor. Duas barreiras, causas independentes.
- **Se o login é o caminho crítico**, um dos casos precisa logar de verdade —
  o `storageState` esconderia justamente a quebra que interessa:

```ts
test.use({ storageState: { cookies: [], origins: [] } });

test('login leva ao dashboard', { tag: ['@smoke'] }, async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('E-mail').fill(process.env.E2E_SMOKE_USER!);
  await page.getByLabel('Senha').fill(process.env.E2E_SMOKE_PASS!);
  await page.getByRole('button', { name: 'Entrar' }).click();
  await expect(page.getByRole('heading', { name: 'Resumo' })).toBeVisible();
});
```

Este caso vai disparar o aviso `A3` (ação aparentemente mutante). É aviso, não
erro: confira que é o caso de login e siga. Credenciais sempre em
`process.env.E2E_*`, nunca no código.

## CI

```bash
npx playwright test --grep @smoke
```

Rode **depois** do deploy, contra o ambiente que acabou de receber o build.
Falhou → rollback ou escalada, nesta ordem.

Nunca use `--grep-invert @smoke` para "destravar" um pipeline vermelho: é o
mesmo que `test.skip()`, só que fora do alcance do lint.

## O que smoke não é

- **Não é regressão rasa.** Regressão congela comportamento; smoke verifica
  disponibilidade. Cobrir menos não transforma um no outro.
- **Não substitui a suíte.** Smoke verde diz "está de pé", não "está correto".
- **Não afirma defeito.** Sem fonte de verdade, `PRODUCT_BUG` continua
  inalcançável — igual a `regression`.
