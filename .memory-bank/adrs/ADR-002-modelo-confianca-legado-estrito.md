# ADR-002: Modelo de confiança dual — legado default e perfil estrito opt-in

**Status:** Aceito
**Data:** 2026-10-24
**Feature de origem:** otimizar-governanca-e2e-ia
**Autores:** codesteer.architect skill

---

## Contexto

`guard.avaliar` classifica o host por heurística de nome (`PADROES_AMBIENTE` em `guard.py`): `local` / `dev` / `staging` / `unknown` / `production`. Produção só existe com `--allow-production` e allowlist (`E002`/`E003`/`E007`). Em `smoke`, host `unknown` sai `approved: true`, `exit_code: 0`, `scope: RL` e `hitl` preenchido — o consumidor que olha só o código de saída segue.

O TSD (RF06, CA07, Q2, Q5) fecha o buraco sem quebrar invocações atuais: perfil estrito é operação nova; invocação sem opção nova permanece legado, **exceto** os falsos `APROVA` do healing, que passam a `REJEITA` (isso é correção de prova, não mudança de confiança de host).

Hash, `approved_by` e confiança autodeclarada não provam ação humana se o host não proteger a origem. Agentes desta sessão têm `Bash`. Conclusão estrita de CI exige origem protegida; no disco local a confiança é limitada e deve ser declarada.

## Decisão

Decidimos operar dois perfis no mesmo `Decisao` e na mesma CLI de `guard.py`:

- **`policy_profile` ausente ou `legacy` (default):** heurística atual de `classificar_host`; `exit 0` + `hitl` pendente continua possível em smoke/`unknown`; documentação declara que isso **não** é autorização estrita.
- **`strict` (opt-in):** `guard.avaliar` passa a validar `PoliticaDeProjeto` (`schema_version: 1`, origens exatas por ambiente, caminhos, modo, escopo, orçamento, `approval_refs`, `content_hash`) contra esquema HTTP(S), host, IP, porta e registro de aprovação. HITL pendente, alvo ≠ política, hash divergente ou origem incompleta → `approved: false`, exit 1. Sem curinga amplo por default.

O campo JSON `policy_profile` é aditivo. Códigos de saída 0/1/3 e os campos atuais de `Decisao` não mudam de significado. Projeto novo é orientado ao estrito na documentação; a adoção continua explícita.

## Alternativas Consideradas

| Alternativa | Por que foi descartada |
|---|---|
| A. Quebrar o legado e tornar o estrito o único caminho | Consumidores atuais de `exit 0` + `hitl` em smoke/`unknown` quebram sem flag (RF02). O TSD congela a invocação sem opção nova. |
| B. Manter só o legado e documentar a limitação | Fecha a documentação, não o buraco: CI que olha só exit code segue autorizando alvo não confirmado (RF06, CA07). |
| C. Dois perfis no mesmo `guard.avaliar` — legado default, estrito opt-in | Adotada: preserva CLI/JSON; conclusão estrita fica disponível quando o host protege política e registro; Q5 permanece honesto no disco local. |

## Consequências

**Positivas:**
- ✅ Self-tests atuais de `guard.py --self-test` continuam válidos no caminho legado.
- ✅ Smoke de produção só se anuncia seguro quando há conta de leitura no servidor **e** origem verificável no perfil estrito (RF08, A04, A05).
- ✅ Política, baseline e inventário esperado passam a ter o mesmo modelo de confiança: protegidos pelo host, não pelo candidato.

**Trade-offs aceitos:**
- ⚠️ Dois significados de `exit 0` coexistirão até o consumidor optar pelo estrito; a documentação e o campo `policy_profile` são o discriminador, não um código de saída novo.
- ⚠️ Perfil estrito em máquina de desenvolvedor com shell aberto declara confiança limitada — não se anuncia como aprovação independente (Q5).

## Guardrails derivados desta decisão

- **[GA-T01]:** Invocação de `guard.py` sem a operação/flag nova = legado. Não reatribuir o significado de exit 0/1/3.
- **[GA-T02]:** No perfil estrito, `hitl` não vazio implica `approved: false` e exit 1. Nunca `approved: true` com HITL pendente.
- **[GA-T03]:** `PoliticaDeProjeto` sem curinga amplo, com origens exatas e `content_hash` vinculado ao registro. Política inválida, incompleta ou com hash divergente bloqueia.
- **[GA-T04]:** Hash escrito pelo mesmo agente, `approved_by` e confiança autodeclarada **não** demonstram aprovação humana. Conclusão estrita de CI exige origem protegida pelo host.
- **[GA-T05]:** Página, console, ticket ou relatório não autorizam mudar modo, política, fonte, seleção ou testes (A06).

## Status de vigência

- **Aceito** — em vigor desde 2026-10-24, aplica-se a todas as features a partir de `otimizar-governanca-e2e-ia`
- Para superseder: crie ADR-NNN com `Supersede: ADR-002` e atualize este status para `Supersedido por ADR-NNN`
