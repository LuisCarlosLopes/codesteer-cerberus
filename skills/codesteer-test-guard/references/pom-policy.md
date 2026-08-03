# Page Object Model — convenção

> **A regra que sustenta todo o resto:** o page object expõe **locators e
> ações**. A asserção fica no `.spec.ts`. Sempre.
>
> Verificado por `scripts/assertion_guard.py --check-po tests/`, que falha se
> qualquer `.page.ts` contiver `expect()`.

## Por que a asserção não entra no page object

Duas razões, e a segunda é estrutural.

**1. O que o teste prova deve ser legível no teste.** Comparar `criar-produto.spec.ts` com `editar-produto.spec.ts` só é possível se a prova estiver lá. Se estiver atrás de `await produtosPage.verificarStatus()`, é preciso abrir um segundo arquivo para saber o que foi verificado — e ninguém abre.

**2. O gate ficaria cego.** O `assertion_guard.py` congela as asserções lendo o `.spec.ts`. Com a asserção dentro do PO, o healing poderia afrouxá-la sem passar por barreira nenhuma:

```ts
// spec.ts — o gate vê ZERO asserções aqui
await produtosPage.verificarStatus('Ativo');

// produtos.page.ts — rota livre para enfraquecer o teste
async verificarStatus(esperado: string) {
  await expect(this.status).toBeAttached();   // era toHaveText(esperado)
}
```

A convenção não é preferência estética. É a premissa da qual a garantia depende.

## Estrutura

```
tests/
├── fixtures.ts                  # injeta os page objects nos testes
├── pages/
│   ├── base.page.ts             # opcional, só se houver algo REAL em comum
│   └── produtos.page.ts
└── e2e/
    └── produtos/
        ├── criar-produto.spec.ts
        └── editar-produto.spec.ts
```

Nomenclatura: arquivo `kebab-case.page.ts`, classe `PascalCasePage`. O nome do
spec vem do cenário do `plan.md`, conforme a reference `spec-driven-testing.md`
da skill `playwright-cli`.

## Anatomia de um page object

```ts
// tests/pages/produtos.page.ts
import { type Page, type Locator } from '@playwright/test';

/**
 * Página de listagem e cadastro de produtos.
 * Expõe locators e ações. Nenhuma asserção — a prova mora no spec.
 */
export class ProdutosPage {
  // Locators nomeados pelo papel na interface, não pela aparência.
  readonly novo: Locator;
  readonly nome: Locator;
  readonly salvar: Locator;

  constructor(private readonly page: Page) {
    this.novo   = page.getByTestId('produto-novo');
    this.nome   = page.getByTestId('produto-nome');
    this.salvar = page.getByTestId('produto-salvar');
  }

  async goto(): Promise<void> {
    await this.page.goto('/produtos');
  }

  /** Ação nomeada pela intenção do usuário, não pelos cliques que executa. */
  async criar(nome: string): Promise<void> {
    await this.novo.click();
    await this.nome.fill(nome);
    await this.salvar.click();
  }

  /**
   * Escopo de linha. Devolver o Locator — em vez de asserções prontas —
   * é o que permite ao spec provar o que quiser sobre a linha.
   */
  linhaDe(nome: string): Locator {
    return this.page.getByRole('row').filter({ hasText: nome });
  }

  /** Dado extraído da página, para o spec asserir sobre ele. */
  async totalExibido(): Promise<string> {
    return (await this.page.getByTestId('produto-total').innerText()).trim();
  }
}
```

## Anatomia de um spec

```ts
// tests/e2e/produtos/criar-produto.spec.ts
// spec: .memory-bank/e2e-specs/produtos.plan.md
// intent: produto criado aparece na lista como Ativo
import { test, expect } from '../../fixtures';

test('produto criado aparece na lista como ativo', async ({ produtosPage }) => {
  // 1. Abrir a listagem de produtos
  await produtosPage.goto();

  // 2. Criar um produto com nome rastreável
  const nome = `e2e-${process.env.E2E_RUN_ID}-teclado`;
  await produtosPage.criar(nome);

  // 3. O produto aparece na lista, ativo
  const linha = produtosPage.linhaDe(nome);
  await expect(linha).toBeVisible();
  await expect(linha.getByTestId('produto-status')).toHaveText('Ativo');
});
```

A prova está visível: o produto aparece e está Ativo. O `expect` é do spec, o
locator é do PO, e o escopo de linha foi preservado.

## Fixtures

Injete os page objects em vez de instanciar em cada teste. Isso compõe com o
`fixtures.ts` que a reference `spec-driven-testing.md` já sugere para o seed.

```ts
// tests/fixtures.ts
import { test as base } from '@playwright/test';
import { ProdutosPage } from './pages/produtos.page';

type Paginas = {
  produtosPage: ProdutosPage;
};

export const test = base.extend<Paginas>({
  produtosPage: async ({ page }, use) => {
    await use(new ProdutosPage(page));
  },
});

export { expect } from '@playwright/test';
```

## O que nunca entra num page object

| Proibido | Por quê |
| :--- | :--- |
| `expect()` | Cega o gate e esconde a prova. **Verificado por script** |
| `test()`, `test.describe()` | PO não é arquivo de teste |
| `waitForTimeout`, `networkidle` | Proibidos em qualquer lugar |
| Classe CSS gerada (`.css-1x2y3z`) | Nível D — ver `selector-health.md` |
| Dado de teste literal | Vem do spec, para o teste declarar seus próprios dados |
| Lógica condicional sobre estado da app | Teste com `if` prova coisas diferentes a cada run |
| Um PO "God" com toda a aplicação | Um PO por tela ou componente significativo |

## Métodos: nomeie pela intenção

```ts
// RUIM — descreve a mecânica; se a UI mudar, o nome mente
async clicarBotaoNovoEPreencherNomeESalvar(nome: string)

// BOM — descreve a intenção; sobrevive a refactor de UI
async criar(nome: string)
```

Um método de PO deve continuar fazendo sentido depois que o botão virar um
menu de contexto.

## Herança: só se houver algo real em comum

`base.page.ts` é útil para navegação compartilhada, header, toasts. Não crie
uma base só para ter uma base — herança prematura em PO produz classes com
métodos que metade das páginas não usa. Composição é preferível: um
`ToastComponent` injetado bate um `BasePage` inchado.

## Refatoração pós-geração

O fluxo oficial do `playwright-cli` gera teste plano, com locator inline. A
conversão para POM é um passo à parte, depois da geração e **antes** do
primeiro run:

```
1. Gere com playwright-cli (locators inline no spec)
2. Extraia locators e ações para o .page.ts
3. Deixe todo expect() no spec, e declare o header `// intent:`
4. Crie/atualize fixtures.ts
5. uv run scripts/assertion_guard.py --check-po tests/    ← obrigatório
6. Rode a suíte
```

Não pule o passo 5. É barato, roda em milissegundos e protege a premissa de
todo o resto.

## Efeito no healing

Sob POM, a maior parte das curas de `TEST_DRIFT` acontece no **page object** —
trocar `getByTestId` por `getByRole` num locator afeta todos os specs que o
usam. Isso é bom: uma correção, muitos testes.

O gate continua governando o `.spec.ts`. Como o PO não tem asserções, editá-lo
não pode enfraquecer a prova — desde que `--check-po` continue passando. Por
isso ele é obrigatório também **depois** de qualquer cura que toque um PO.
