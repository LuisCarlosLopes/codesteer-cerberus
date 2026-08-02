# Guia de Padrões Page Object Model (POM) para o codesteer-test-guard

Este documento define a arquitetura obrigatória de Page Objects para todos os testes gerados pelo `codesteer-test-guard`.

---

## 1. Por que Page Object Model?

| Problema sem POM | Solução com POM |
| :--- | :--- |
| Locators espalhados em cada `test()` — quando a UI muda, dezenas de testes quebram. | Locators centralizados na Page Object — uma mudança no seletor corrige todos os testes que usam aquele método. |
| Lógica de navegação e preenchimento duplicada entre testes. | Métodos reutilizáveis (`createItem()`, `deleteItem()`) encapsulam a interação. |
| Testes longos e difíceis de ler. | Testes leem como especificação de negócio: `await productsPage.createProduct(nome)`. |
| Self-Healing precisa editar N arquivos de teste. | Self-Healing edita apenas a Page Object afetada. |

---

## 2. Estrutura de Diretórios

```
tests/
├── e2e/
│   ├── pages/                           # Page Objects
│   │   ├── base.page.ts                 # Classe base abstrata com métodos comuns
│   │   ├── login.page.ts                # Page Object de autenticação (quando necessário)
│   │   └── [entidade].page.ts           # Page Object de cada tela mapeada
│   └── [entidade].spec.ts              # Suítes de teste (.spec.ts) que consomem Page Objects
```

---

## 3. Classe Base Abstrata (`base.page.ts`)

Toda Page Object deve estender a `BasePage`, que encapsula padrões comuns:

```typescript
import { type Page, type Locator, expect } from '@playwright/test';

/**
 * Classe base abstrata para todas as Page Objects.
 * Encapsula padrões comuns de navegação, espera e verificação.
 */
export abstract class BasePage {
  constructor(protected readonly page: Page) {}

  /** URL relativa da página (definida por cada subclasse) */
  abstract readonly path: string;

  /** Navegar para a URL desta página */
  async navigate(): Promise<void> {
    await this.page.goto(this.path);
  }

  /** Verificar se a página carregou corretamente */
  async verifyPageLoaded(): Promise<void> {
    await expect(this.page).toHaveURL(new RegExp(`.*${this.path}`));
  }

  /** Aguardar spinner/loader desaparecer antes de interagir */
  async waitForLoadingToFinish(): Promise<void> {
    const spinner = this.page.locator('.spinner, .loading, [data-testid="loading"]');
    if (await spinner.isVisible({ timeout: 1000 }).catch(() => false)) {
      await spinner.waitFor({ state: 'detached', timeout: 15_000 });
    }
  }

  /** Aceitar diálogo nativo de confirmação (registrar ANTES da ação) */
  acceptNextDialog(): void {
    this.page.on('dialog', dialog => dialog.accept());
  }
}
```

---

## 4. Page Object de Login (`login.page.ts`)

Utilizada quando a URL alvo requer autenticação:

```typescript
import { type Page } from '@playwright/test';
import { BasePage } from './base.page';

export class LoginPage extends BasePage {
  readonly path = '/login';

  // Locators centralizados
  private readonly emailInput = this.page.getByLabel(/email|usuário/i);
  private readonly passwordInput = this.page.getByLabel(/senha|password/i);
  private readonly submitButton = this.page.getByRole('button', { name: /entrar|login|sign in/i });

  /** Executar login completo e retornar à página autenticada */
  async login(email: string, password: string): Promise<void> {
    await this.navigate();
    await this.emailInput.fill(email);
    await this.passwordInput.fill(password);
    await this.submitButton.click();
    await this.page.waitForURL(/.*(?!login)/); // Aguardar sair da tela de login
  }
}
```

---

## 5. Page Object de Entidade CRUDL

Template padrão para qualquer tela com operações CRUDL:

```typescript
import { type Page, expect } from '@playwright/test';
import { BasePage } from './base.page';

export class ProductsPage extends BasePage {
  readonly path = '/produtos';

  // --- Locators centralizados ---
  private readonly newButton = this.page.getByRole('button', { name: /novo|adicionar|criar/i });
  private readonly nameInput = this.page.getByLabel(/nome/i);
  private readonly saveButton = this.page.getByRole('button', { name: /salvar|cadastrar/i });
  private readonly updateButton = this.page.getByRole('button', { name: /salvar|atualizar/i });

  // --- Helpers de escopo por linha ---

  /** Localizar a linha da tabela que contém o texto informado */
  private row(text: string) {
    return this.page.locator('tr', { hasText: text });
  }

  /** Botão de editar dentro da linha escopada */
  private editButtonInRow(text: string) {
    return this.row(text).getByRole('button', { name: /editar|edit/i });
  }

  /** Botão de excluir dentro da linha escopada */
  private deleteButtonInRow(text: string) {
    return this.row(text).getByRole('button', { name: /excluir|deletar|delete/i });
  }

  // --- Ações CRUDL ---

  /** CREATE: Preencher formulário e salvar um novo registro */
  async createProduct(name: string): Promise<void> {
    await this.newButton.click();
    await this.nameInput.fill(name);
    await this.saveButton.click();
    await this.waitForLoadingToFinish();
  }

  /** READ: Verificar se o item está visível na listagem */
  async assertProductVisible(name: string): Promise<void> {
    await expect(this.page.getByText(name)).toBeVisible();
  }

  /** READ: Verificar se o item NÃO está visível na listagem */
  async assertProductNotVisible(name: string): Promise<void> {
    await expect(this.page.getByText(name)).not.toBeVisible();
  }

  /** UPDATE: Editar um campo do registro existente */
  async updateProduct(currentName: string, newName: string): Promise<void> {
    await this.editButtonInRow(currentName).click();
    await this.nameInput.fill(newName);
    await this.updateButton.click();
    await this.waitForLoadingToFinish();
  }

  /** DELETE: Excluir o registro com confirmação de diálogo */
  async deleteProduct(name: string): Promise<void> {
    this.acceptNextDialog();
    await this.deleteButtonInRow(name).click();
    await this.waitForLoadingToFinish();
  }
}
```

---

## 6. Teste Usando Page Objects

O teste fica limpo e lê como uma especificação funcional:

```typescript
import { test } from '@playwright/test';
import { ProductsPage } from './pages/products.page';

test.describe('CRUDL - Produtos', () => {
  const itemUnico = `Produto_E2E_${Date.now()}`;

  test('Deve executar o ciclo CRUDL completo', async ({ page }) => {
    const productsPage = new ProductsPage(page);

    // Navegar
    await productsPage.navigate();
    await productsPage.verifyPageLoaded();

    // Create
    await productsPage.createProduct(itemUnico);
    await productsPage.assertProductVisible(itemUnico);

    // Update
    const nomeEditado = `${itemUnico}_Editado`;
    await productsPage.updateProduct(itemUnico, nomeEditado);
    await productsPage.assertProductVisible(nomeEditado);

    // Delete & Teardown
    await productsPage.deleteProduct(nomeEditado);
    await productsPage.assertProductNotVisible(nomeEditado);
  });
});
```

---

## 7. Regras Obrigatórias para Geração de Page Objects

1. **Todo locator deve viver dentro da Page Object**, nunca diretamente no `.spec.ts`.
2. **Métodos devem representar ações de negócio**, não interações técnicas. Use `createProduct()` em vez de `fillNameAndClickSave()`.
3. **A classe base `BasePage` é obrigatória.** Toda Page Object herda dela.
4. **Row-Scoping fica na Page Object.** Os métodos helper `row()`, `editButtonInRow()` e `deleteButtonInRow()` isolam a lógica de escopo por linha.
5. **Locators declarados como propriedades `private readonly`** no topo da classe, nunca inline nos métodos.
6. **Regex case-insensitive (`/texto/i`)** nos locators de botão e label para suportar variações de capitalização entre ambientes/idiomas.
7. **Self-Healing corrige a Page Object, não o teste.** Quando a UI mudar, o agente edita apenas o locator na Page Object correspondente.
8. **Um arquivo por Page Object.** Não agrupar múltiplas páginas em um mesmo arquivo.
