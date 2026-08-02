# Guia de Triagem de Falhas & Geração de Bug Report

Inspirado no modelo de diagnóstico do **TestSprite**, quando um teste falha durante a execução da engine, o **Loop Engineer** deve classificar o erro antes de tomar qualquer ação de autocorreção.

**Regra fundamental: Nunca mascare um bug da aplicação corrigindo o teste para que ele passe.**

---

## 1. Fluxo de Decisão do Loop Engineer

```
Teste falhou
    │
    ├── A mensagem de erro contém HTTP 4xx/5xx ou uncaught exception?
    │       SIM ──> PRODUCT BUG
    │       NÃO ──┐
    │              │
    │   ├── A mensagem contém "Navigation timeout" ou "net::ERR_"?
    │   │       SIM ──> Re-executou e passou?
    │   │                   SIM ──> INFRA FLAKE (resolvido)
    │   │                   NÃO ──> ENVIRONMENT BLOCKED
    │   │       NÃO ──┐
    │   │              │
    │   │   ├── A mensagem contém "TimeoutError" de locator ou "strict mode violation"?
    │   │   │       SIM ──> TEST DRIFT (aplicar Self-Healing)
    │   │   │       NÃO ──┐
    │   │   │              │
    │   │   │   └── Asserção de valor falha (ex: texto esperado não encontrado)?
    │   │   │           ├── O valor existe na UI mas com texto diferente? ──> TEST DRIFT
    │   │   │           └── O valor não existe na UI de forma alguma?    ──> PRODUCT BUG
```

---

## 2. Categorias de Falha — Detalhamento

### 🐛 Product Bug (Falha da Aplicação)

**Definição:** A aplicação web real apresentou um defeito funcional, erro de servidor ou comportamento que diverge do requisito do usuário.

**Sintomas Comuns:**
* Resposta HTTP 500, 502, 503 ou 404 inesperado na rede.
* Exceção `uncaught` no console do navegador (ex: `TypeError: Cannot read properties of undefined`).
* Asserção de valor de negócio falha: item criado não aparece na lista mesmo após espera adequada.
* Formulário submetido com sucesso (sem erro HTTP) mas dado não foi persistido.
* Redirecionamento inesperado para página de erro.

**Ação Autônoma:**
1. **PARAR o loop de autocorreção.** Não alterar o código do teste.
2. Coletar evidências: mensagem de erro, stack trace do console, status HTTP das requisições.
3. Gerar `bug_report.md` no diretório raiz do projeto.
4. Avançar para State 6 (Report) com status `product_bug_found`.

---

### 🔧 Test Drift (Fragilidade de UI / Seletor Desatualizado)

**Definição:** A interface do usuário mudou (novo texto de botão, classe reestruturada, elemento renomeado), mas a funcionalidade da aplicação continua válida.

**Sintomas Comuns:**
* `TimeoutError: locator.click: Timeout 5000ms exceeded` esperando um locator que não encontra match.
* `strict mode violation`: múltiplos elementos correspondem ao locator.
* Texto de botão mudou (ex: "Salvar" virou "Gravar").

**Ação Autônoma:**
1. Abrir sessão de discovery pontual com `playwright-cli open <URL>`.
2. Executar `playwright-cli snapshot` para capturar o DOM atualizado.
3. Comparar o locator que falhou com os elementos reais no snapshot.
4. Atualizar o arquivo `.spec.ts` com o locator correto.
5. Fechar a sessão (`playwright-cli close`).
6. Re-executar o teste.

---

### 🌐 Infra Flake (Instabilidade de Ambiente)

**Definição:** Instabilidade temporária de rede, browser lag, servidor lento no carregamento.

**Sintomas Comuns:**
* `Navigation timeout of 30000ms exceeded` esporádico (aparece uma vez e não se repete).
* `net::ERR_CONNECTION_REFUSED` ou `net::ERR_NAME_NOT_RESOLVED`.
* `browser has been closed` ou `browser disconnected`.

**Ação Autônoma:**
1. Re-executar o teste **sem alterar o código**.
2. Se falhar 2 vezes consecutivas com o **mesmo** erro de infraestrutura, classificar como `environment_blocked` e parar.

---

## 3. Estrutura do Relatório `bug_report.md`

Caso a falha seja identificada como **Product Bug**, crie o arquivo `bug_report.md` no diretório raiz do projeto com o seguinte formato:

```markdown
# 🐛 Bug Report: Falha Funcional Detectada pelo codesteer-test-guard

**URL Alvo:** [URL_ALVO]
**Cenário:** [NOME_DO_CENÁRIO — ex: CRUDL Delete]
**Modo de Teste:** [Smoke / CRUDL / Cenário Customizado]
**Data:** [DATA_ATUAL ISO 8601]

## Descrição do Defeito
[Descrição objetiva do que aconteceu vs. o que era esperado.]

## Passos para Reproduzir
1. Acessar `[URL_ALVO]`.
2. [AÇÃO 1 — ex: Clicar em "Novo Produto"].
3. [AÇÃO 2 — ex: Preencher nome com "Item_E2E_1754137200"].
4. [AÇÃO 3 — ex: Clicar em "Salvar"].
5. Observar a falha: [DESCRIÇÃO DA FALHA OBSERVADA].

## Evidência Empírica
- **Erro HTTP:** `[METHOD] [URL_DA_REQUISIÇÃO] [STATUS_CODE] ([STATUS_TEXT])`
- **Erro de Console:** `[MENSAGEM_DE_ERRO_DO_CONSOLE]`
- **Linha do Teste Afetada:** `tests/e2e/[NOME_DO_TESTE].spec.ts:[LINHA]`
- **Asserção que Falhou:** `[expect(X).toBeVisible() — X não foi encontrado]`

## Causa Raiz Provável
[Hipótese técnica fundamentada nas evidências coletadas. Ex: "A rota POST /api/produtos retorna 500, indicando possível erro no handler de criação do backend."]

## Recomendação de Correção
[Sugestão acionável para o desenvolvedor. Ex: "Verificar o handler da rota POST /api/produtos no backend e validar o schema do body recebido."]

## Classificação
- **Severidade:** [Critical / High / Medium / Low]
- **Componente Afetado:** [Frontend / Backend API / Banco de Dados / Autenticação]
```

---

## 4. Contadores e Limites do Loop Engineer

| Parâmetro | Valor | Justificativa |
| :--- | :---: | :--- |
| Máximo de iterações do loop | **3** | Evitar degradação de contexto e loops infinitos. |
| Máximo de retries para Infra Flake | **2** | Se falhar 2x consecutivas com mesmo erro de infra, é bloqueio de ambiente. |
| Máximo de Self-Healing por teste | **2** | Se 2 correções de locator não resolverem, a divergência é estrutural e exige revisão humana. |
