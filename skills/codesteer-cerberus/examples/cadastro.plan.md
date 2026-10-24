# Plan — Cadastro de Cliente

Fonte de verdade: `examples/cadastro.spec.md` (aprovada). Sem schema
versionado novo — campos operacionais no Markdown existente.

## Cenário CA-01 — Cadastro válido

- **intent:** cliente da tabela Válidos aparece na lista como Ativo
- **precondições:** usuário autenticado; formulário `/cadastro` aberto; escopo CRUDL
- **ações:** preencher nome e documento da linha D1; salvar
- **asserções:** linha na lista com nome e status Ativo
- **prioridade:** P0
- **dados:** Dados → Válidos / D1 (prefixo `e2e-<runId>-`)
- **efeitos de domínio:** cria um registro Ativo rastreável pelo run
- **Fonte:** cadastro.spec.md#CA-01

## Cenário CA-02 — Campo obrigatório ausente

- **intent:** salvar sem nome não cria registro e mostra obrigatoriedade
- **precondições:** formulário aberto
- **ações:** limpar nome; salvar
- **asserções:** mensagem de obrigatoriedade visível; lista sem o registro
- **prioridade:** P0
- **dados:** Dados → Inválidos / I1
- **efeitos de domínio:** nenhum registro persistido
- **Fonte:** cadastro.spec.md#CA-02
