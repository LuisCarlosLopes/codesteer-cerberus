# Guia de Padrões CRUDL e Escopo por Linha (Row-Scoping)

Este documento descreve os padrões obrigatórios de código TypeScript para geração de testes CRUDL no Playwright pelo `codesteer-test-guard`.

---

## 1. Princípio da Idempotência e Teardown

Testes E2E devem ser capazes de rodar múltiplas vezes no mesmo ambiente sem falhar por duplicidade ou poluir o banco de dados.

* **Dados Únicos:** Sempre concatenar timestamp no valor dos campos criados:
  ```typescript
  const itemUnico = `Item_E2E_${Date.now()}`;
  ```
* **Teardown no Próprio Teste:** O ciclo de exclusão (Delete) é obrigatório como última etapa e deve remover o dado criado no próprio teste.
* **Isolamento entre Testes:** Cada teste `test()` deve ser autossuficiente. Não dependa de dados criados em outro teste do mesmo `describe`.

---

## 2. Hierarquia de Locators Semânticos

Use locators nesta ordem de preferência. Seletores CSS/XPath puros são último recurso:

| Prioridade | Locator | Quando Usar | Exemplo |
| :---: | :--- | :--- | :--- |
| 1 | `getByRole()` | Sempre que o elemento tiver uma role ARIA reconhecível. | `page.getByRole('button', { name: /salvar/i })` |
| 2 | `getByLabel()` | Campos de formulário com `<label>` associado. | `page.getByLabel('Nome do Produto')` |
| 3 | `getByPlaceholder()` | Campos sem label mas com placeholder text. | `page.getByPlaceholder('O que precisa ser feito?')` |
| 4 | `getByText()` | Textos visíveis sem role ou label. | `page.getByText('Nenhum resultado encontrado')` |
| 5 | `getByTestId()` | Quando `data-testid` existir no elemento. | `page.getByTestId('todo-title')` |
| 6 | `locator()` | Último recurso com CSS. | `page.locator('.todo-list li.editing .edit')` |

---

## 3. Padrão de Escopo por Linha (Row-Scoping Pattern)

Em páginas com tabelas ou listagens contendo múltiplos botões "Editar" ou "Excluir", o Playwright lançará um erro de seletor estrito (strict mode violation) se o botão for buscado de forma global.

### ❌ Incorreto (Causa erro de ambiguidade):
```typescript
// Falha se houver mais de um botão 'Editar' na tela
await page.getByRole('button', { name: 'Editar' }).click();
```

### ✅ Correto (Escopado por Linha):
```typescript
// Localiza a linha específica da tabela pelo texto do item criado
const linhaDoItem = page.locator('tr', { hasText: itemUnico });

// Interage com o botão 'Editar' contido estritamente dentro daquela linha
await linhaDoItem.getByRole('button', { name: /editar/i }).click();
```

### ✅ Alternativa para listas (`<ul>/<li>`):
```typescript
// Para listagens que usam <li> em vez de <tr>
const itemDaLista = page.locator('li', { hasText: itemUnico });
await itemDaLista.hover();
await itemDaLista.getByRole('button', { name: /delete/i }).click();
```

---

## 4. Tratamento de Diálogos de Confirmação Nativos

Quando a ação de exclusão aciona um alerta ou diálogo nativo do navegador (`window.confirm` / `window.alert`), registre o listener **ANTES** de clicar no botão que o dispara:

```typescript
// IMPORTANTE: Registrar o listener ANTES da ação que dispara o diálogo
page.on('dialog', dialog => dialog.accept());

// Só depois clicar no botão de exclusão
const linhaParaDeletar = page.locator('tr', { hasText: itemEditado });
await linhaParaDeletar.getByRole('button', { name: /excluir|deletar/i }).click();

// Validar que o elemento foi removido do DOM
await expect(page.getByText(itemEditado)).not.toBeVisible();
```

> **Nota:** Se a aplicação usar modais customizados (não nativos), trate-os como elementos normais da página: aguarde a visibilidade, clique no botão de confirmação e aguarde o fechamento.

---

## 5. Esperas Assíncronas Resilientes (evitando flaky tests)

### ❌ PROIBIDO — Espera estática:
```typescript
// NUNCA usar waitForTimeout em testes de produção
await page.waitForTimeout(3000);
```

### ✅ Correto — Espera por resposta HTTP:
```typescript
// Aguardar a resposta HTTP 200 da API antes de verificar a UI
await Promise.all([
  page.waitForResponse(resp => resp.url().includes('/api/produtos') && resp.status() === 200),
  page.getByRole('button', { name: /salvar/i }).click(),
]);
```

### ✅ Correto — Espera por estado do DOM:
```typescript
// Aguardar spinner/loader desaparecer antes de interagir
await page.locator('.spinner, .loading').waitFor({ state: 'detached' });

// Aguardar um elemento aparecer na tela
await expect(page.getByText(itemUnico)).toBeVisible({ timeout: 10000 });
```

### ✅ Correto — Espera por navegação:
```typescript
// Aguardar a navegação completar após clique em link
await Promise.all([
  page.waitForURL(/.*\/dashboard/),
  page.getByRole('link', { name: /dashboard/i }).click(),
]);
```

---

## 6. Padrão Completo de Teste CRUDL (Template de Referência)

```typescript
import { test, expect } from '@playwright/test';

test.describe('CRUDL - [Nome da Entidade]', () => {
  const itemUnico = `Item_E2E_${Date.now()}`;

  test('Deve executar o ciclo completo de Criar, Listar, Editar e Deletar', async ({ page }) => {
    // 1. Acessar a URL alvo
    await page.goto('/entidade');
    await expect(page).toHaveURL(/.*entidade/);

    // 2. CREATE - Preencher formulário e salvar
    await page.getByRole('button', { name: /novo|adicionar|criar/i }).click();
    await page.getByLabel(/nome/i).fill(itemUnico);
    await page.getByRole('button', { name: /salvar|cadastrar/i }).click();

    // 3. READ - Validar exibição na tabela/listagem
    await expect(page.getByText(itemUnico)).toBeVisible();

    // 4. UPDATE - Editar com escopo de linha
    const linhaCriada = page.locator('tr', { hasText: itemUnico });
    await linhaCriada.getByRole('button', { name: /editar/i }).click();
    await page.getByLabel(/nome/i).fill(`${itemUnico}_Editado`);
    await page.getByRole('button', { name: /salvar|atualizar/i }).click();
    await expect(page.getByText(`${itemUnico}_Editado`)).toBeVisible();

    // 5. DELETE & TEARDOWN - Excluir e confirmar remoção
    page.on('dialog', dialog => dialog.accept());
    const linhaEditada = page.locator('tr', { hasText: `${itemUnico}_Editado` });
    await linhaEditada.getByRole('button', { name: /excluir|deletar/i }).click();
    await expect(page.getByText(`${itemUnico}_Editado`)).not.toBeVisible();
  });
});
```
