---
name: codesteer-test-guard
description: Engine autônoma e portátil para geração, execução e estabilização de testes E2E com Playwright baseada em Graph Engineer (DAG de estados) e Loop Engineer (Self-Healing com triagem de falhas estilo TestSprite). Use quando o usuário fornecer uma URL e desejar gerar testes E2E (Smoke, CRUDL / Auto-Discovery ou Cenário Específico).
---

# codesteer-test-guard

Engine autônoma de automação de testes E2E com Playwright. A engine opera em uma máquina de estados agêntica **Graph Engineer** (DAG de 6 Estados) e possui um **Loop Engineer** para autocorreção e triagem de falhas (Product Bug, Test Drift ou Infra Flake).

---

## 🚀 Como Invocar esta Skill

O usuário fornece a **URL Alvo** e um **Contexto Opcional**:
* `URL`: Exemplo `https://demo.playwright.dev/todomvc` ou `https://app.exemplo.com/produtos`
* `Contexto`:
  * **Smoke Test:** Checar renderização, HTTP 200, ausência de console errors.
  * **CRUDL / Auto-Discovery:** Mapeamento automático de Criar, Listar, Editar e Deletar.
  * **Cenário Customizado:** Passo a passo funcional fornecido pelo usuário.
* `baseURL` (opcional): Quando fornecida, será configurada em `playwright.config.ts` para que os testes usem caminhos relativos.
* `Credenciais` (opcional): Usuário e senha de teste, ou caminho para `auth.json` (`storageState`) para URLs protegidas por autenticação.

---

## 🏛️ Máquina de Estados da DAG (Graph Engineer)

Você deve seguir rigorosamente a sequência de estados abaixo. **Não pule estados.** Se um estado não tiver trabalho significativo (ex: repositório já possui Playwright), registre isso e avance.

```
[State 1: Init] ──> [State 2: Discovery] ──> [State 3: Design] ──> [State 4: CodeGen] ──> [State 5: LoopFix] ──> [State 6: Report]
```

### State 1: Environment Readiness & Bootstrap (`init`)

**Objetivo:** Garantir que o repositório possui infraestrutura mínima para rodar testes Playwright em TypeScript.

1. **Verificação do Repositório:** Checar se `package.json` e `playwright.config.ts` existem no projeto.
2. **Zero-Setup Bootstrap:** Se for um repositório novo ou vazio, executar autonomamente:
   ```bash
   npm init -y
   npm install -D @playwright/test typescript @types/node
   npx playwright install chromium
   ```
3. **Verificação de Browsers Instalados:** Checar se o Chromium do Playwright está disponível. Se não, executar `npx playwright install chromium`.
4. **Template de Configuração:** Garantir que `playwright.config.ts` existe. Usar o template em `resources/playwright.config.template.ts` como base. Se o usuário forneceu `baseURL`, configurá-la no `use.baseURL`.
5. **Criação da Estrutura de Diretórios:** Garantir que `tests/e2e/` existe.
6. **Segurança:** Garantir que `.gitignore` contém entradas para `auth.json`, `*.auth-state.json`, `test-results/`, `playwright-report/` e `node_modules/`.

**Critério de Saída:** `npx playwright --version` retorna sem erro e a estrutura `tests/e2e/` existe.

---

### State 2: Live Discovery & Surface Scan (`discovery`)

**Objetivo:** Explorar a URL alvo ao vivo via `playwright-cli` para mapear a UI real sem premissas cegas.

1. **Inspeção ao Vivo:**
   ```bash
   playwright-cli open <URL_ALVO>
   playwright-cli snapshot
   ```
2. **Detecção de Auth/Login:**
   * Após navegar para a URL alvo, verificar se houve redirecionamento para uma tela de login (detectar campos de email/senha, botões de "Login"/"Sign In").
   * **Se auth for necessária e credenciais foram fornecidas:** Realizar o login via CLI e salvar o estado autenticado:
     ```bash
     playwright-cli fill <campo_email> "usuario@teste.com"
     playwright-cli fill <campo_senha> "senhadeteste"
     playwright-cli click <botao_login>
     playwright-cli state-save auth.json
     ```
   * **Se auth for necessária mas credenciais NÃO foram fornecidas:** Interromper a execução e solicitar credenciais ao usuário. Não prosseguir sem autenticação.
   * **Se `auth.json` já existir:** Carregar com `playwright-cli state-load auth.json` antes de navegar.
3. **Mapeamento de Interativos:**
   * Usar `playwright-cli snapshot` para capturar o DOM tree completo.
   * Registrar cada elemento interativo encontrado: `<input>`, `<button>`, `<select>`, `<textarea>`, `<form>`.
   * Identificar estruturas tabulares: `<table>`, `<tr>`, `div[role="grid"]`, `ul > li`.
   * Mapear botões de ação por linha (Editar, Excluir, Visualizar).
   * Registrar labels, placeholders e roles acessíveis que o Playwright pode usar como locators.
4. **Mapeamento de Console Errors:**
   ```bash
   playwright-cli console
   ```
   Registrar qualquer erro de console encontrado na página carregada (útil para Smoke Test).
5. **Encerramento da Sessão de Discovery:**
   ```bash
   playwright-cli close
   ```

**Critério de Saída:** Uma lista documentada de elementos interativos, suas referências, e a confirmação de que a URL está acessível (com ou sem auth).

---

### State 3: Requirement-Driven Scenario Design (`design`)

**Objetivo:** Formular os cenários de teste baseando-se no objetivo funcional do usuário (não em bugs existentes no código).

#### Modo Smoke Test:
1. Navegação com HTTP 200 (sem redirecionamento inesperado).
2. Títulos e cabeçalhos primários visíveis.
3. Ausência de exceções não tratadas no console do navegador.
4. Elementos interativos primários renderizados e visíveis.

#### Modo CRUDL / Auto-Discovery:
1. **Create:** Formulário preenchido com dado dinâmico temporal (`Produto_${Date.now()}`). Submissão via botão e confirmação de sucesso (toast, redirecionamento ou novo item na lista).
2. **Read/List:** Validação de exibição do registro recém-criado na listagem/tabela.
3. **Update:** Edição do registro usando **escopo por linha** (`locator('tr', { hasText })`). Alteração de campo e verificação da atualização.
4. **Delete & Teardown:** Exclusão com confirmação de diálogo modal nativo (`page.on('dialog')`). Validação de remoção do DOM. **O Delete é obrigatório como teardown para garantir idempotência.**

#### Modo Cenário Customizado:
Traduzir os passos textuais fornecidos pelo usuário em ações Playwright e asserções funcionais sequenciais.

**Critério de Saída:** Lista de cenários com objetivo, ações sequenciais e asserções esperadas.

---

### State 4: Test Code Generation com Page Object Model (`codegen`)

**Objetivo:** Gerar Page Objects e arquivos `.spec.ts` seguindo a arquitetura **Page Object Model (POM)** obrigatória.

#### Arquitetura de Diretórios (POM):
```
tests/e2e/
├── pages/                           # Page Objects (locators + ações de negócio)
│   ├── base.page.ts                 # Classe base abstrata (navigate, waitForLoading, acceptDialog)
│   ├── login.page.ts                # Page Object de login (quando auth for necessária)
│   └── [entidade].page.ts           # Uma Page Object por tela mapeada
└── specs/                           # Ou na raiz de e2e/ — Suítes de teste (.spec.ts)
    └── [entidade].spec.ts           # Testes que consomem Page Objects
```

> **Referência completa:** Ler [page-object-patterns.md](references/page-object-patterns.md) para templates detalhados de `BasePage`, `LoginPage` e Page Objects CRUDL.

#### Regras de Geração de Page Objects:

1. **Todo locator deve viver na Page Object**, nunca diretamente no `.spec.ts`.
2. **Métodos representam ações de negócio:** `createProduct(name)`, `deleteProduct(name)`, não `fillInputAndClickButton()`.
3. **Toda Page Object herda de `BasePage`** (`base.page.ts`), que fornece `navigate()`, `verifyPageLoaded()`, `waitForLoadingToFinish()` e `acceptNextDialog()`.
4. **Locators declarados como `private readonly`** no topo da classe.
5. **Row-Scoping fica na Page Object** via métodos helper como `row(text)`, `editButtonInRow(text)`.
6. **Regex case-insensitive (`/texto/i`)** nos locators de botão e label.
7. **Um arquivo `.page.ts` por tela/entidade.**

#### Padrões de Código (dentro das Page Objects):

1. **Hierarquia de Locators Semânticos (usar nesta ordem de preferência):**
   * `page.getByRole()` → `page.getByLabel()` → `page.getByPlaceholder()` → `page.getByText()` → `page.getByTestId()` → `page.locator()` (último recurso).

2. **Dados Dinâmicos Temporais nos testes:**
   ```typescript
   const itemUnico = `Item_E2E_${Date.now()}`;
   ```

3. **Esperas Assíncronas Explícitas — PROIBIDO usar `waitForTimeout()`.** Usar `waitForResponse()`, `waitFor({ state })` ou `waitForURL()`.

4. **Tratamento de Diálogos Nativos** encapsulado no método `acceptNextDialog()` da `BasePage`.

5. **Configuração de storageState para Auth (quando `auth.json` existir):**
   ```typescript
   test.use({ storageState: 'auth.json' });
   ```

6. **Comentários explicativos em Português.**

**Critério de Saída:** Page Object(s) criadas em `tests/e2e/pages/` + arquivo `.spec.ts` que importa e consome as Page Objects. O teste deve ser compilável e ler como especificação de negócio.

---

### State 5: Self-Healing Loop & Triagem de Falhas (`loop-fix`)

**Objetivo:** Executar os testes gerados e, em caso de falha, classificar o erro e aplicar a remediação adequada.

**Regra: Máximo de 3 iterações do loop.** Se após 3 tentativas o teste não passar, encerrar e reportar.

#### Execução:
```bash
npx playwright test --reporter=list
```

#### Se o teste PASSAR: Avançar para State 6.

#### Se o teste FALHAR: Aplicar a Matriz de Triagem:

| Categoria | Como Identificar | Ação |
| :--- | :--- | :--- |
| 🐛 **Product Bug** | Status HTTP 4xx/5xx na rede; exceção `uncaught` no console; asserção de valor de negócio falha (ex: item salvo não aparece na lista mesmo após espera adequada). | **PARAR o loop.** Não alterar o teste. Gerar `bug_report.md` com passos de reprodução, evidência de rede/console e causa raiz provável. Avançar para State 6 com status `product_bug_found`. |
| 🔧 **Test Drift** | `TimeoutError` esperando locator; `strict mode violation` (múltiplos elementos); elemento com texto/role diferente do esperado. | **Aplicar Self-Healing:** 1) Abrir `playwright-cli open <URL>`, 2) Executar `playwright-cli snapshot`, 3) Identificar o novo seletor/ref correto, 4) Atualizar o `.spec.ts` com o locator correto, 5) Fechar CLI e re-executar o teste. |
| 🌐 **Infra Flake** | `Navigation timeout` esporádico; `net::ERR_CONNECTION_REFUSED`; `browser disconnected`. Tipicamente aparece na 1ª execução e desaparece na 2ª. | **Retry simples.** Re-executar sem alterar código. Se falhar 2x consecutivas com o mesmo erro de infra, reportar como `environment_blocked`. |

#### Procedimento detalhado de Self-Healing:
1. Ler a mensagem de erro do Playwright (linha, tipo de erro, locator que falhou).
2. Identificar **qual Page Object** contém o locator que falhou (ex: `todo.page.ts`).
3. Abrir sessão de discovery pontual:
   ```bash
   playwright-cli open <URL_ALVO>
   playwright-cli snapshot
   ```
4. Comparar o locator que falhou com os elementos reais no snapshot.
5. Atualizar o locator **na Page Object** (`.page.ts`), nunca no `.spec.ts`.
6. Fechar a sessão:
   ```bash
   playwright-cli close
   ```
7. Re-executar o teste.

**Critério de Saída:** Teste verde OU relatório de falha classificada (Product Bug / Environment Blocked / Max Retries Exceeded).

---

### State 6: Result Reporting (`report`)

**Objetivo:** Gerar a síntese final e disponibilizar evidências.

1. **Gerar o relatório HTML do Playwright:**
   ```bash
   npx playwright show-report --host 0.0.0.0
   ```
   O relatório fica disponível em `playwright-report/index.html`.

2. **Síntese Markdown (resumo textual):**
   * URL testada
   * Modo de teste executado (Smoke / CRUDL / Customizado)
   * Quantidade de cenários / asserções
   * Resultado: PASSOU / FALHOU (com classificação)
   * Se Product Bug: incluir referência ao `bug_report.md` gerado
   * Tempo total de execução

3. **Artefatos Gerados:**
   * `tests/e2e/pages/*.page.ts` — Page Objects com locators centralizados
   * `tests/e2e/*.spec.ts` — Suítes de teste que consomem Page Objects
   * `playwright-report/` — Relatório HTML interativo
   * `bug_report.md` — Apenas se Product Bug foi encontrado

**Critério de Saída:** Relatório entregue ao usuário com síntese e evidências.

---

## 📚 Referências de Apoio

Leia estes documentos quando precisar de contexto adicional durante a execução:

* [page-object-patterns.md](references/page-object-patterns.md): **Arquitetura POM obrigatória** — templates de `BasePage`, `LoginPage`, Page Objects CRUDL e regras de geração.
* [crudl-patterns.md](references/crudl-patterns.md): Padrões de código para cenários CRUDL, Row-Scoping, tratamento de diálogos e esperas assíncronas resilientes.
* [failure-triage-guide.md](references/failure-triage-guide.md): Guia detalhado de triagem de erros, critérios de classificação e template completo de `bug_report.md`.

---

## ⚠️ Guardrails

* **Não coloque locators diretamente no `.spec.ts`.** Todo locator deve viver na Page Object correspondente.
* **Não use `waitForTimeout()`.** Sempre espere por estados explícitos do DOM ou respostas de rede.
* **Não use seletores CSS/XPath frágeis** (`.class-name`, `#id-genérico`) como primeira opção. Prefira sempre locators semânticos.
* **Não mascare bugs da aplicação** corrigindo o teste para passar quando o comportamento está errado. Classifique como Product Bug.
* **Self-Healing corrige a Page Object, não o teste.** Quando a UI mudar, edite o locator na `.page.ts`, não no `.spec.ts`.
* **Não persista credenciais em repositórios públicos.** Garanta que `auth.json` e `*.auth-state.json` estejam no `.gitignore`.
* **Não infle a suíte com cenários de baixo valor.** Priorize fluxos críticos e de alto risco.
* **Não execute mais de 3 iterações do Loop Engineer** sem parar e reportar a falha.
