# Saúde de Seletores — a porta de qualidade

> **Mecânica de seletor não está aqui.** Para gerar locators, use a skill
> `playwright-cli`: `snapshot` dá refs de acessibilidade e
> `generate-locator e5 --raw` produz o locator Playwright do elemento.
> Este documento define apenas **quando você tem permissão para gerar testes**.

O fluxo oficial gera sobre qualquer seletor disponível. Esta é a restrição que
esta skill acrescenta.

## Classifique antes de gerar

Rode `playwright-cli snapshot` e examine os elementos-chave dos fluxos alvo.

| Nível | Critério | Ação |
| :---: | :--- | :--- |
| **A** | `data-testid` nos elementos-chave | Prossiga |
| **B** | Sem testid, mas roles ARIA e nomes acessíveis consistentes | Prossiga, avise fragilidade moderada |
| **C** | Só texto visível e estrutura de DOM | Prossiga, avise que quebrará a cada mudança de copy |
| **D** | Classes geradas, sem roles, DOM instável | **PARE** |

Para confirmar a presença de testid num elemento do snapshot:

```bash
playwright-cli eval "el => el.getAttribute('data-testid')" e5
```

Se o snapshot já traz `role` e `name` úteis para os elementos que importam,
você está em B ou acima. Se os elementos aparecem sem nome acessível e só são
alcançáveis por seletor estrutural, você está em D.

## Nível D bloqueia

Não gere testes. Escreva `selector-recommendations.md` e entregue ao usuário:

```markdown
# Seletores necessários antes da automação

A aplicação não expõe ganchos estáveis. Testes gerados agora quebrariam a cada
build, pois as classes CSS são geradas automaticamente.

| Tela | Elemento | Sugestão | Por quê |
| :--- | :--- | :--- | :--- |
| /produtos | Botão "Novo" | `data-testid="produto-novo"` | Classe `css-1x2y3z` muda a cada build |
| /produtos | Linha da tabela | `data-testid="produto-linha"` | Sem `role="row"`, não há como ancorar escopo |
| /produtos | Campo Nome | `data-testid="produto-nome"` | Label não associado ao input |

Com esses atributos a suíte sobe ao nível A e a automação passa a ser viável.
```

Isso não é recusa de trabalho. É o único resultado honesto: gerar a suíte
custaria mais do que entregaria.

## Duas regras que sobrevivem à geração

O `playwright-cli` escolhe bem o locator na maior parte dos casos. Estas duas
situações ele não resolve sozinho — confira no código gerado.

### Classe CSS gerada é proibida

```ts
// PROIBIDO — muda a cada build
page.locator('.css-1x2y3z > div:nth-child(2)');
// PROIBIDO — quebra com qualquer refactor de layout
page.locator('div > table > tbody > tr:nth-child(3) > td:nth-child(2)');
```

Se o `generate-locator` devolveu algo assim, você está em nível D. Volte.

### Escopo de linha em listas

Locator global em lista acerta por acaso com um item e falha — ou age no item
errado — com vários.

```ts
// ERRADO — com dois produtos, clica no primeiro botão da página
await page.getByTestId('produto-editar').click();

// CERTO — ancora na linha do produto alvo
const linha = page.getByRole('row').filter({ hasText: 'e2e-run1-teclado' });
await linha.getByTestId('produto-editar').click();
await expect(linha.getByTestId('produto-status')).toHaveText('Ativo');
```

Vale também para asserções: a expectativa dentro do escopo da linha. Fora dele
você prova apenas que "existe algum elemento na página com esse texto", quase
sempre mais fraco que a intenção do teste.

## Checklist antes de rodar a suíte gerada

- [ ] Nenhuma classe CSS gerada
- [ ] Nenhum `waitForTimeout`, nenhum `networkidle`
- [ ] Todo locator em lista ancorado na linha
- [ ] Toda asserção em lista dentro do escopo da linha
- [ ] Testes independentes, sem ordem implícita
- [ ] Dados criados com prefixo `e2e-<runId>-` e teardown correspondente
