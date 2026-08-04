# Triagem de Falhas

Classificar errado é pior que não classificar. Um `TEST_DRIFT` atribuído a um
bug real faz você **consertar o teste até ele parar de denunciar o defeito** —
o pior resultado possível deste sistema.

> **Relação com o fluxo oficial.** A skill `playwright-cli`
> (`spec-driven-testing.md` §3.2) já ensina a diagnosticar: rodar em
> `--debug=cli`, dar attach, inspecionar. Use aquilo para **coletar**. Este
> documento define como **classificar** o que foi coletado — que é o que o
> oficial não formaliza. O §3.4 do oficial, que manda parar e perguntar quando
> não se sabe se é regressão ou spec desatualizada, é o mesmo espírito da
> classe `UNCLASSIFIED` aqui.

## Entradas obrigatórias

Não classifique sem ter as seis. Colete com a skill oficial:

| # | Entrada | Como obter |
| :---: | :--- | :--- |
| 1 | `intent` do caso | O que o teste queria provar (do plan/spec) |
| 2 | `truthRef` | Fonte de verdade externa — só existe em `spec-driven` |
| 3 | Erro do Playwright | Saída do run: mensagem, stack, locator que falhou |
| 4 | Estado da página | `playwright-cli snapshot` no ponto da falha |
| 5 | Console e rede | `playwright-cli console`, `playwright-cli requests` |
| 6 | Histórico do run | Esta falha já apareceu? é intermitente? |

Faltando alguma, obtenha antes. Se o trace estiver desligado no
`playwright.config.ts`, você não tem base para triagem — resolva isso primeiro.

**Antes de tudo:** se o primeiro teste redirecionou para `/login`, a sessão
expirou. Regrave o estado (`playwright-cli state-save`) e rode de novo. Triar
uma cascata de falhas com causa única gera diagnóstico errado em série.

## Árvore de decisão

Percorra na ordem. A primeira condição que casar define a classe.

**Modo `smoke` tem árvore própria** — pule para a seção seguinte. Ela existe
porque aqui a indisponibilidade reproduzível é o **achado**, não o ruído.

```
1. Houve erro 5xx, falha de conexão, DNS ou timeout de ambiente?
   └─ SIM → INFRA_FLAKE
            Retry com backoff. Três falhas idênticas → reclassifique,
            não é intermitência, é determinístico.

2. O elemento existe na página, e só o locator não o encontrou?
   Evidência exigida: o screenshot mostra o elemento, OU o DOM do trace
   contém um nó semanticamente equivalente sob outro seletor.
   └─ SIM → TEST_DRIFT
            Elegível a self-healing. Vá ao gate.

3. O modo é `regression`?
   └─ SIM → BEHAVIOR_CHANGED
            Você não tem fonte de verdade. Reporte a diferença entre o que foi
            capturado e o que aconteceu. NÃO julgue se é defeito.
            Pare aqui — PRODUCT_BUG é inalcançável em regression.

4. Modo `spec-driven`: o comportamento observado contradiz a fonte de verdade?
   ├─ SIM, e você consegue citar o trecho literal → PRODUCT_BUG
   ├─ SIM, mas não consegue citar trecho nenhum   → UNCLASSIFIED
   ├─ A fonte de verdade é omissa sobre este ponto → UNCLASSIFIED
   └─ Sua confiança está abaixo de 0.8             → UNCLASSIFIED
```

## Árvore de smoke

Ver `references/smoke-policy.md`. Em `smoke` não há fonte de verdade:
`PRODUCT_BUG` é inalcançável, como em `regression`.

```
S1. Erro 5xx, DNS, conexão recusada ou timeout de ambiente?
    ├─ 1ª ocorrência        → INFRA_FLAKE. Retry ÚNICO, não três.
    └─ reproduziu idêntico  → CRITICAL_PATH_DOWN
                              Não é intermitência. É o que o smoke procura.

S2. O elemento existe na página, sob outro seletor?
    Evidência exigida: a mesma do passo 2 da árvore principal — o snapshot
    mostra o nó equivalente. Em smoke a barra é mais alta: o alvo era um sinal
    estável, então drift aqui é exceção.
    └─ SIM → TEST_DRIFT. Vá ao gate.
             2ª cura no mesmo caso → pare; a âncora está funda demais.

S3. A aplicação respondeu, mas o sinal de domínio não apareceu
    (heading, saldo, primeira linha da lista)?
    └─ SIM → CRITICAL_PATH_DOWN
             Responder e não entregar é queda igual — só mais silenciosa.

S4. Nada acima → UNCLASSIFIED. Escale.
```

`CRITICAL_PATH_DOWN` não autoriza tocar no teste. Autoriza avisar, rápido:
reporte, e recomende rollback ou escalada conforme a janela do deploy.

## As classes

| Classe | Significado | Pode editar o teste? |
| :--- | :--- | :---: |
| `INFRA_FLAKE` | Ambiente instável, não o produto nem o teste | Não (só retry) |
| `TEST_DRIFT` | O teste endereça mal; a intenção continua válida | **Sim, sob gate** |
| `BEHAVIOR_CHANGED` | O comportamento mudou; sem fonte de verdade, não se sabe se é defeito | Não |
| `PRODUCT_BUG` | O produto contraria o requisito, com citação | Não |
| `CRITICAL_PATH_DOWN` | **Só em `smoke`.** Caminho crítico indisponível de forma reproduzível | Não — reporte imediatamente |
| `UNCLASSIFIED` | Não há base para decidir | Não |

## `PRODUCT_BUG` exige citação literal

Sem trecho citável da fonte de verdade, a classificação é `UNCLASSIFIED`. Sempre.

Esta regra existe porque um classificador sem restrição inventa defeitos
plausíveis. Se você está prestes a escrever "o sistema deveria validar o campo"
sem conseguir apontar onde isso está escrito, você está inferindo o requisito —
e inferir o requisito a partir do comportamento é a circularidade que o modo
`spec-driven` existe para evitar.

Formato no `bug_report.md`:

```markdown
## BUG-001 — Cadastro aceita nome vazio

**Fonte de verdade:** docs/criterios-aceite.md, linha 42
> "O campo Nome é obrigatório e o formulário não pode ser submetido sem ele."

**Observado:** o formulário foi submetido com Nome vazio e retornou 201.
**Evidência:** traces/cadastro-nome-vazio.zip, screenshot em 00:04.
**Reprodução:** tests/e2e/cadastro.spec.ts:31
```

## `UNCLASSIFIED` é resposta correta

Não é falha sua. É o comportamento certo quando não há base para decidir.

Uma engine que sempre classifica é uma engine que às vezes mente. Escalar ao
humano com o contexto organizado vale mais do que um palpite com aparência de
veredito.

## Erros comuns

| Erro | Por que acontece | Correção |
| :--- | :--- | :--- |
| Chamar bug real de `TEST_DRIFT` | O elemento "sumiu" — mas sumiu porque o produto quebrou | Só use `TEST_DRIFT` se houver evidência positiva do elemento no DOM |
| `PRODUCT_BUG` em modo `regression` | Impossível por construção | Volte ao passo 3 |
| `INFRA_FLAKE` para toda falha intermitente | Intermitência também vem de race condition no produto | Três falhas idênticas = determinístico, reclassifique |
| `INFRA_FLAKE` para 5xx reproduzível em `smoke` | O reflexo de tratar erro de rede como ambiente | Em smoke, 5xx que repete é `CRITICAL_PATH_DOWN` — é o achado, não o ruído |
| Inferir requisito do comportamento | Ausência de fonte de verdade explícita | `UNCLASSIFIED` e pergunte ao usuário |
