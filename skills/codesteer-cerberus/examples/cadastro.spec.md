---
id: e2e-spec-cadastro
status: approved
source: mixed
feature: cadastro
url: https://app-stg.exemplo.com/cadastro
approved_by: user
approved_at: 2026-08-03T00:00:00Z
---

# Spec — Cadastro de Cliente (exemplo)

Exemplo mínimo do contrato `.spec.md` do Cerberus. Em uso real, grave em
`.memory-bank/e2e-specs/cadastro.spec.md` e só passe a `--truth` com
`status: approved`.

## Contexto

- Rota: `/cadastro`
- Auth: storageState (usuário autenticado)
- Escopo guard: CRUDL

## Regras

- **R1** — Nome e documento são obrigatórios.
- **R2** — Documento deve ser único; duplicata exibe erro e não cria registro.
- **R3** — Cadastro válido aparece na listagem com status Ativo.

## Cenários de aceite

### CA-01 — Cadastro válido (tabela de dados)

Dado o formulário de cadastro aberto
Quando preencho uma linha da tabela **Dados → Válidos** e salvo
Então o registro aparece na lista com status Ativo (R3)

### CA-02 — Campo obrigatório ausente

Dado o formulário aberto
Quando salvo sem nome
Então vejo mensagem de obrigatoriedade e nenhum registro é criado (R1)

## Dados

### Válidos

| id | nome | documento | email |
| :--- | :--- | :--- | :--- |
| D1 | Ana Silva | 11144477735 | ana@example.com |
| D2 | Bruno Costa | 39053344705 | bruno@example.com |
| D3 | Carla Mendes | 52998224725 | carla@example.com |

### Inválidos

| id | nome | documento | esperado |
| :--- | :--- | :--- | :--- |
| I1 | (vazio) | 11144477735 | erro de obrigatoriedade (R1) |

## Sinais observáveis

- Sucesso: mensagem de confirmação; linha na lista com nome e status Ativo
- Erro: mensagem de validação visível; lista sem o registro tentado

## Fora de escopo

- Importação em lote, API direta, perfis sem permissão de cadastro

## Proveniência

- Campos e sinais: discovery (exemplo)
- Tabela de documentos: fornecida pelo usuário (exemplo)
