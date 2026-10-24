# Roteiro de ensaio (manual ou agendado)

Não execute na job `self-tests` do PR. Sem SDK de provedor.

1. Confira `corpus/catalog.json` (24 `dev` + 8 `held_out`).
2. Para cada cenário, até 3 tentativas. Grave versões (modelo, skill, CLI, Playwright).
3. Compare `produced_label` com `expected_label` **externo**.
4. Publique com `run_report.py publish-eval --registro <arquivo> --out <saída>`.
5. Se held-out revelar falha encoberta, não promova a skill.
6. Healing da fixture não pode tornar verde `evals/known-defect.spec.ts`.
