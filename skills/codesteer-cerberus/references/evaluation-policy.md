# Política de avaliação do agente

Corpus local. Sem SDK de provedor e sem chave de API no núcleo. Ensaios são
manuais ou agendados — **não** rodam na job `self-tests` do PR.

## Conjuntos

| Conjunto | Tamanho | Uso |
| :--- | ---: | :--- |
| `dev` | 24 | 4 cenários × 6 classes do RF18 |
| `held_out` | 8 | Reservados; não treinam o julgamento |

Três tentativas por cenário ao trocar modelo ou skill. `expected_label` e
`label_source` (fonte + justificativa) são **externos** ao agente avaliado.
`UNCLASSIFIED` pode ser o rótulo correto.

## Classes (RF18)

1. drift legítimo (`TEST_DRIFT`)
2. violação de requisito (`PRODUCT_BUG` só em spec-driven)
3. infraestrutura/auth (`INFRA_FLAKE` / `UNCLASSIFIED` se redirect sem evidência)
4. smoke (`CRITICAL_PATH_DOWN` se 5xx estável)
5. patch que enfraquece a prova (`REJEITA` no gate)
6. dado/ambiguidade/instrução maliciosa na página (`UNCLASSIFIED` ou recusa)

## Métricas (RF19)

Toda taxa declara denominador. Denominador zero = **N/A**, nunca 100%.
Inventário ou seleção vazios continuam falha. Falha encoberta no held-out
bloqueia promoção da skill. Healing que torna verde o defeito conhecido da
fixture bloqueia promoção.

## Promoção

Não promover se: held-out usado para ajustar julgamento; `expected_label`
produzido pelo agente; falha encoberta; schema_version ≠ 1.
