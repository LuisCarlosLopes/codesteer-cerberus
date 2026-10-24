# Política de evidência

Pacote aditivo no run existente. Não substitui `summary.md`, `mutations.diff`,
`bug_report.md` nem `escalations.md`.

## Chave quádrupla

Cada tentativa é `run_id × test_id × project × attempt`. Mix de chave, hash
divergente, anexo fora da raiz (inclusive após resolver symlink) ou trace
obrigatório ausente **bloqueia** a decisão que depende do pacote.

## Imutabilidade

Depois de `finalized_at` o pacote não se sobrescreve. Reprodução e
pós-healing ganham identidade nova e `original_failure_ref` apontando ao
original. Run concorrente não apaga a evidência original.

## Comparação

Antes/depois só com vínculo explícito ao mesmo cenário, intent e alvo de
domínio. Resultado de outro build é obsoleto. Classe ≠ `TEST_DRIFT` ou hash
aplicado ≠ validado bloqueia a aplicação do patch.
