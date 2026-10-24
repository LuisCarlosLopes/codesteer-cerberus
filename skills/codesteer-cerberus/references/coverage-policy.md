# Política de cobertura

O mapa (`coverage-map.json` + `coverage.md`) é inventário, não certificado.

## Origem

- `approved` — critério com fonte aprovada
- `observed` — comportamento visto na UI; **não vira approved** por rename,
  mapa ou geração

## Discovery

`explored` | `partial` | `blocked` (+ motivo). Discovery é somente leitura e
compacto (L04). Lacuna sem seletor inventado; nível D bloqueia.

## Estágio

`proposed` → `generated` → `executed`. Gerado ≠ verificado. Resultado de
outro build é histórico.

## Denominadores

`requested_scope` e `authorized_scope` são o denominador. Zero = **N/A**,
nunca 100%. Inventário ou seleção vazios continuam falha. Exclusões por
guard/policy permanecem visíveis no solicitado.
