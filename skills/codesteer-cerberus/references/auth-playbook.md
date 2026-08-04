# Autenticação — autentique uma vez

> **Regra:** nenhum teste faz login. A autenticação acontece **uma vez** por
> run, o estado do navegador vai para disco, e todo teste nasce logado.
>
> Login por teste é lento, frágil, polui o log de auditoria da aplicação e
> transforma qualquer instabilidade da tela de login em falha de toda a suíte.

A mecânica de sessão (`state-save`, `state-load`, cookies, storage) está na
skill oficial `playwright-cli`, reference `storage-state.md`. Este documento
define **onde a autenticação entra no fluxo** e as regras que não são mecânica.

## O padrão: setup project

Use um *setup project* com `dependencies`. É melhor que o `globalSetup` antigo
porque roda como teste — gera trace, aparece no relatório, aceita retry, e
principalmente **permite asserir que o login funcionou** antes de salvar.

```ts
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  use: { trace: 'on' },
  projects: [
    // 1. Roda primeiro, uma vez.
    { name: 'setup', testMatch: /.*\.setup\.ts/ },

    // 2. Todo teste daqui nasce autenticado.
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.e2e-engine/auth/user.json',
      },
      dependencies: ['setup'],
    },
  ],
});
```

```ts
// tests/auth.setup.ts
import { test as setup, expect } from '@playwright/test';

const ARQUIVO = '.e2e-engine/auth/user.json';

setup('autentica', async ({ page }) => {
  await page.goto('/login');

  // Credenciais SEMPRE do ambiente. Nunca literais, nunca no estado do run.
  await page.getByLabel('E-mail').fill(process.env.E2E_USER!);
  await page.getByLabel('Senha').fill(process.env.E2E_PASSWORD!);
  await page.getByRole('button', { name: 'Entrar' }).click();

  // Confirme o login ANTES de salvar. Sem esta asserção você grava um estado
  // deslogado e a suíte inteira falha com causa invisível.
  await expect(page.getByTestId('menu-usuario')).toBeVisible();

  await page.context().storageState({ path: ARQUIVO });
});
```

Os specs não sabem que login existe:

```ts
test('produto criado aparece na lista', async ({ produtosPage }) => {
  await produtosPage.goto();   // já autenticado
  // ...
});
```

> **Nota sobre o `--check-po`:** `auth.setup.ts` contém `expect()` e isso está
> correto — não é page object. O check varre apenas `*.page.ts` e `*.po.ts`.

## Múltiplos perfis

Um setup e um project por papel:

```ts
projects: [
  { name: 'setup-admin',   testMatch: /admin\.setup\.ts/ },
  { name: 'setup-usuario', testMatch: /usuario\.setup\.ts/ },
  {
    name: 'admin',
    use: { storageState: '.e2e-engine/auth/admin.json' },
    dependencies: ['setup-admin'],
    testMatch: /.*\.admin\.spec\.ts/,
  },
  {
    name: 'usuario',
    use: { storageState: '.e2e-engine/auth/usuario.json' },
    dependencies: ['setup-usuario'],
    testMatch: /.*\.usuario\.spec\.ts/,
  },
]
```

## Regras de política

1. **Credenciais nunca** em código gerado, log, trace, relatório ou estado do
   run. Sempre `process.env.E2E_*`. Se a variável não estiver definida, **pare
   e peça ao usuário** — não invente credencial, não use valor de exemplo, não
   tente descobrir usuário válido.
2. `.env` e `.e2e-engine/auth/` no `.gitignore` **antes** de gravar qualquer
   coisa. Um `storageState` commitado é um token vazado.
3. **MFA e SSO interativo: pare e escale.** Não automatize leitura de código de
   MFA por e-mail ou SMS — é um controle de segurança que existe de propósito,
   e contorná-lo é frágil e indevido. Entregue ao usuário:

   ```
   A aplicação exige MFA/SSO interativo, que eu não devo contornar.
   Rode uma vez, faça o login manualmente na janela que abrir, e feche:

       playwright-cli open --persistent <URL>
       # após logar:
       playwright-cli state-save .e2e-engine/auth/user.json

   Depois me avise que eu retomo daqui.
   ```
4. Trace captura requisições completas, incluindo headers de sessão. Antes de
   anexar um trace a um relatório que sai da máquina do usuário, **avise que
   pode conter segredos**.
5. Em `smoke` — sobretudo contra produção — use **conta de serviço dedicada,
   com permissão mínima de leitura**. O guard bloqueia mutação no código; a
   conta bloqueia no servidor. Duas barreiras com causas independentes. Se o
   próprio login é o caminho crítico, um caso smoke precisa logar de verdade;
   ver `smoke-policy.md`.

## Três armadilhas

### `sessionStorage` não vai no storageState

O `storageState` captura cookies e `localStorage`. Se a aplicação guarda o
token em `sessionStorage`, ele **não é restaurado** e todo teste começa
deslogado — apesar do arquivo de estado existir e parecer correto.

Verifique antes de assumir que está resolvido:

```bash
playwright-cli sessionstorage-list
```

Se o token estiver lá, será preciso reinjetá-lo por `addInitScript` no setup,
ou usar perfil persistente.

### Sessão que expira no meio do run

Se o TTL do servidor for menor que a duração da suíte, os testes do fim quebram
sem motivo aparente. Sintomas: as primeiras specs passam, as últimas falham com
redirect. Peça ao usuário um perfil de teste com sessão longa, ou refaça o
setup periodicamente.

### A que mais causa diagnóstico errado

**Sessão vencida se manifesta como cascata de falhas em testes não
relacionados.** Sem saber disso, a triagem classifica dez `TEST_DRIFT` e o
healing sai "consertando" locators que não têm defeito nenhum — gastando
orçamento e sujando o histórico do repositório.

Por isso, antes de qualquer classificação:

> Se o teste redirecionou para `/login`, **a causa é sessão, não o teste.**
> Regrave o estado e rode de novo. Só então classifique o que sobrar.

Está no `triage-guide.md` como primeira verificação, e é a regra mais barata de
todo o sistema.

## Diagnóstico rápido

| Sintoma | Causa provável | Ação |
| :--- | :--- | :--- |
| Todos os testes redirecionam para `/login` | Estado não gravado, ou gravado deslogado | Confira a asserção do `auth.setup.ts` |
| Estado existe mas não autentica | Token em `sessionStorage` | `playwright-cli sessionstorage-list` |
| Primeiros testes passam, últimos falham | TTL da sessão menor que o run | Perfil de teste com sessão longa |
| Login manual funciona, script falha | Label não associado ao input | Suba para `getByRole` ou peça `data-testid` |
| Passa local, falha em CI | Variável de ambiente ausente no CI | Reporte; não é falha de teste |
