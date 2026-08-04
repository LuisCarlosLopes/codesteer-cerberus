# Geração de Spec — critérios de aceite

> **Passos 4b e 4c do fluxo.** O orquestrador redige e aprova a spec — **não**
> delegue a subagent. O valor não é o Markdown; é o encadeamento
> draft → HITL → `approved` → `--truth` → `plan.md` → testes.
>
> Spec gerada só pela UI é **rascunho observado**, não fonte de verdade.
> Sem aprovação humana explícita, `PRODUCT_BUG` permanece inalcançável.

## Quando disparar

| Situação | Ação |
| :--- | :--- |
| Modo `spec-driven` e ainda não existe `.spec.md` aprovado | Execute 4b → HITL → 4c |
| Usuário pediu “gerar spec / critérios de aceite” (com ou sem testes) | Execute 4b → HITL; se pediu só o doc, **pare após 4c** |
| Já existe `.spec.md` com `status: approved` | Pule 4b/4c; use como `--truth` |
| Modo `regression` e usuário não pediu spec | Pule; vá ao PLAN |
| Modo `smoke` | Não se aplica — smoke não afirma requisito. Ver `smoke-policy.md` |

## Entradas

1. Relatório do `e2e-discovery` (rotas, campos, CRUDL, sinais de sucesso)
2. Material do usuário, se houver: lista de valores, ticket, critérios já escritos
3. Decisão do `guard.py` (`scope`, ambiente)

Sem material do usuário → `source: observed`. Com material → `source: mixed`
ou `user-provided`. Em todos os casos o rascunho nasce com `status: draft`.

## Artefato

Grave em `.memory-bank/e2e-specs/<feature>.spec.md`.

### Front matter mínimo

```yaml
---
id: e2e-spec-<feature>
status: draft          # draft | approved
source: observed       # observed | user-provided | mixed
feature: cadastro
url: https://app.exemplo.com/cadastro
approved_by: null
approved_at: null
---
```

### Corpo fixo (seções obrigatórias)

1. **Contexto** — tela/rota, pré-condições (auth, escopo CRUDL/RL)
2. **Regras** — numeradas e citáveis (`R1`, `R2`…)
3. **Cenários de aceite** — cada um com id (`CA-01`, `CA-02`…)
4. **Dados** — tabelas de valores (lista parametrizada mora aqui)
5. **Sinais observáveis** — o que prova sucesso/erro na UI
6. **Fora de escopo**
7. **Proveniência** — o que veio do discovery vs o que o usuário colou

Se `source: observed`, inclua na Proveniência:

> Até aprovação humana, falha futura indica que algo **mudou**, não que algo
> está **errado**. Este documento ainda não autoriza `PRODUCT_BUG`.

### Template completo

```markdown
---
id: e2e-spec-cadastro
status: draft
source: mixed
feature: cadastro
url: https://app-stg.exemplo.com/cadastro
approved_by: null
approved_at: null
---

# Spec — Cadastro de Cliente

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

### Inválidos

| id | nome | documento | esperado |
| :--- | :--- | :--- | :--- |
| I1 | (vazio) | 11144477735 | erro de obrigatoriedade (R1) |

## Sinais observáveis

- Sucesso: toast/mensagem de confirmação; linha na lista com nome e status Ativo
- Erro: mensagem de validação visível; lista sem o registro tentado

## Fora de escopo

- Importação em lote, API direta, perfis sem permissão de cadastro

## Proveniência

- Campos e sinais de sucesso: relatório e2e-discovery
- Tabela de documentos: fornecida pelo usuário
```

## Regras de redação

- Toda regra e cenário tem id estável (`R1`, `CA-01`) — a citação de
  `PRODUCT_BUG` e o header `// truth:` dependem disso.
- Não afirme defeito no draft. Descreva o comportamento desejado.
- Prefira tabelas a prosa para listas de valores.
- Não copie seletores frágeis para a spec; a spec fala de intenção e sinais,
  não de `css-1x2y3z`.
- Prefixo de dados E2E (`e2e-<runId>-`) é preocupação do generate, não da spec
  de produto — na tabela use valores de negócio; o teste aplica o prefixo.

## HITL (bloqueante) — passo 4c

Após gravar o rascunho:

1. Mostre o caminho do `.spec.md` e um resumo das regras/cenários
2. Pergunte: **aprovar como está** / **editar** / **descartar e cair em `regression`**
3. **Aguarde resposta.** Não prossiga sem ela.
4. Se aprovado: atualize front matter:

```yaml
status: approved
approved_by: <identificador do usuário ou "user">
approved_at: <ISO-8601 UTC>
```

5. Só então rode:

```bash
uv run scripts/guard.py --url <URL> --mode spec-driven \
  --truth .memory-bank/e2e-specs/<feature>.spec.md
```

Exit != 0 (inclui `E008` se ainda estiver `draft`) → **PARE.**

Se o usuário recusar aprovação mas quiser testes: modo `regression`, sem este
arquivo como `--truth`; o `plan.md` continua válido.

Se o usuário pediu **só** a spec: pare após 4c. Não gere PLAN/GENERATE.

### Checklist HITL

- [ ] Arquivo em `.memory-bank/e2e-specs/<feature>.spec.md`
- [ ] Front matter com `status`, `source`, `feature`, `url`
- [ ] Regras `R*` e cenários `CA-*` citáveis
- [ ] Seção Dados preenchida quando há lista de valores
- [ ] Usuário respondeu aprovar / editar / descartar
- [ ] Se aprovado: `status: approved` + `approved_by` + `approved_at`
- [ ] `guard.py --mode spec-driven --truth <arquivo>` exit 0 antes do PLAN

## Derivação PLAN ← SPEC

Com `.spec.md` aprovado, o passo PLAN gera
`.memory-bank/e2e-specs/<feature>.plan.md`:

- Um bloco de cenário por `CA-xx`
- Dados: referencie a seção do spec (`Dados → Válidos`); não duplique a tabela
  a menos que o plan precise de um recorte
- Escopo/mutations herdados do guard
- Citação explícita em cada cenário: `Fonte: <feature>.spec.md#CA-01`

Em `regression` sem spec aprovada, o plan continua podendo descrever o
comportamento observado — sem campo `Fonte:` de critérios.

## Headers nos testes gerados

```ts
// truth: .memory-bank/e2e-specs/cadastro.spec.md#CA-01
// spec:  .memory-bank/e2e-specs/cadastro.plan.md
// intent: cliente da tabela Válidos aparece na lista como Ativo
```

Em `regression` sem truth, omita `// truth:`.

## Dados parametrizados no generate

A partir da seção **Dados** do spec:

- Use `test.each` (ou loop equivalente) — uma linha = um caso
- Prefixe valores criados com `e2e-<runId>-` (restrição 5 da skill)
- Teardown por prefixo em `afterEach` e varredura final
