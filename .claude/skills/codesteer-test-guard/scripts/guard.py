#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
guard.py — State 0. Portão de entrada da engine.

Responde a duas perguntas antes de qualquer navegação ou geração de teste:

    1. A combinação modo + oráculo é coerente?
    2. É seguro criar, alterar e apagar dados neste host?

100% determinístico. Sem rede, sem modelo, sem dependências externas.
Se este script não aprovar, o agente PARA e reporta ao usuário.

USO
---
    uv run guard.py --url https://app.exemplo.com --mode regression
    uv run guard.py --url ... --mode spec-driven --oracle docs/criterios.md
    uv run guard.py --url ... --mode regression --allow-production \\
                    --allowlist .e2e-engine/production-allowlist.txt
    uv run guard.py --self-test

SAÍDA
-----
JSON em stdout com a classificação de ambiente e a decisão.

EXIT CODES
----------
    0  APROVADO           pode prosseguir com o escopo indicado em `scope`
    1  BLOQUEADO          erro de configuração ou de segurança (ver `errors`)
    3  ERRO_DE_USO
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from urllib.parse import urlparse

APROVADO, BLOQUEADO, ERRO_DE_USO = 0, 1, 3

MODOS = ("regression", "spec-driven")

# Ordem importa: o primeiro padrão que casar define a classificação.
PADROES_AMBIENTE: list[tuple[str, str]] = [
    (r"^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])$", "local"),
    (r"\.(local|test|localhost)$", "local"),
    (r"(^|[.\-])(dev|develop|development)([.\-]|$)", "dev"),
    (r"(^|[.\-])(staging|stg|hml|homolog|homologacao|qa|uat|sandbox)([.\-]|$)", "staging"),
]

ERROS = {
    "E001": "modo spec-driven exige --oracle <caminho|texto>. "
            "Use --mode regression se o objetivo é criar rede de regressão.",
    "E002": "host classificado como produção e --allow-production não foi informado.",
    "E003": "host de produção fora da allowlist.",
    "E004": "modo inválido.",
    "E005": "URL inválida ou sem host.",
    "E006": "arquivo de oráculo informado não existe.",
    "E007": "--allow-production exige --allowlist apontando para um arquivo existente.",
}


@dataclass
class Decisao:
    approved: bool
    exit_code: int
    mode: str
    target_url: str
    host: str
    environment: str
    mutations_allowed: bool
    scope: str                       # "CRUDL" | "RL" (somente leitura)
    oracle: str | None = None
    errors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    hitl: list[str] = field(default_factory=list)

    def emit(self) -> int:
        print(json.dumps(asdict(self), ensure_ascii=False, indent=2))
        return self.exit_code


def erro(codigo: str, extra: str = "") -> dict:
    return {"code": codigo, "message": ERROS[codigo] + (f" {extra}" if extra else "")}


def classificar_host(host: str) -> str:
    h = host.lower().split(":")[0]
    for padrao, rotulo in PADROES_AMBIENTE:
        if re.search(padrao, h):
            return rotulo
    return "unknown"


def ler_allowlist(caminho: Path | None) -> set[str]:
    if not caminho or not caminho.is_file():
        return set()
    entradas = set()
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.split("#", 1)[0].strip().lower()
        if linha:
            entradas.add(linha)
    return entradas


def avaliar(
    url: str,
    mode: str,
    oracle: str | None = None,
    allow_production: bool = False,
    allowlist_path: Path | None = None,
) -> Decisao:
    erros: list[dict] = []
    avisos: list[str] = []
    hitl: list[str] = []

    if mode not in MODOS:
        erros.append(erro("E004", f"recebido: {mode!r}; válidos: {', '.join(MODOS)}"))

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        erros.append(erro("E005", f"recebido: {url!r}"))

    # --- oráculo -----------------------------------------------------------
    if mode == "spec-driven":
        if not oracle:
            erros.append(erro("E001"))
        else:
            p = Path(oracle)
            # oráculo pode ser caminho de arquivo OU texto livre
            parece_caminho = p.suffix != "" or "/" in oracle
            if parece_caminho and not p.is_file():
                erros.append(erro("E006", f"caminho: {oracle}"))
    elif oracle:
        avisos.append(
            "--oracle informado em modo regression será ignorado. "
            "PRODUCT_BUG é inalcançável neste modo."
        )

    # --- ambiente ----------------------------------------------------------
    ambiente = classificar_host(host) if host else "unknown"
    permitidos = ler_allowlist(allowlist_path)

    if allow_production:
        # Ao declarar --allow-production o usuário assume intenção de atingir
        # produção. Classificamos como tal mesmo sem allowlist: na dúvida,
        # a classificação mais restritiva.
        ambiente = "production"
        if not allowlist_path or not allowlist_path.is_file():
            erros.append(erro("E007", f"caminho: {allowlist_path}"))
        elif host in permitidos:
            ambiente = "production"
            hitl.append(
                f"CONFIRME COM O USUÁRIO antes de prosseguir: testes destrutivos "
                f"serão executados contra PRODUÇÃO ({host})."
            )
        else:
            ambiente = "production"
            erros.append(erro("E003", f"host: {host}"))
    elif ambiente == "unknown" and host:
        avisos.append(
            f"host {host!r} não reconhecido como local/dev/staging. "
            "Mutações bloqueadas; suíte limitada a List e Read."
        )

    mutations = ambiente in ("local", "dev", "staging") or (
        ambiente == "production" and allow_production and host in permitidos
    )

    if ambiente == "production" and not allow_production:
        erros.append(erro("E002", f"host: {host}"))

    aprovado = not erros
    return Decisao(
        approved=aprovado,
        exit_code=APROVADO if aprovado else BLOQUEADO,
        mode=mode,
        target_url=url,
        host=host,
        environment=ambiente,
        mutations_allowed=bool(mutations),
        scope="CRUDL" if mutations else "RL",
        oracle=oracle if mode == "spec-driven" else None,
        errors=erros,
        warnings=avisos,
        hitl=hitl,
    )


# ---------------------------------------------------------------- self-test

CASOS = [
    ("local + regression",
     dict(url="http://localhost:3000", mode="regression"), True, "local", True),
    ("staging + regression",
     dict(url="https://app-stg.empresa.com", mode="regression"), True, "staging", True),
    ("dev + regression",
     dict(url="https://dev.empresa.com/produtos", mode="regression"), True, "dev", True),
    ("homolog + regression",
     dict(url="https://homolog.empresa.com", mode="regression"), True, "staging", True),
    ("host desconhecido → somente leitura",
     dict(url="https://app.cliente.com", mode="regression"), True, "unknown", False),
    ("spec-driven sem oráculo → E001",
     dict(url="http://localhost:3000", mode="spec-driven"), False, "local", True),
    ("spec-driven com oráculo em texto",
     dict(url="http://localhost:3000", mode="spec-driven",
          oracle="o campo nome é obrigatório"), True, "local", True),
    ("modo inválido → E004",
     dict(url="http://localhost:3000", mode="smoke"), False, "local", True),
    ("URL sem host → E005",
     dict(url="nao-e-url", mode="regression"), False, "unknown", False),
    ("produção sem allowlist → E007",
     dict(url="https://app.empresa.com", mode="regression",
          allow_production=True), False, "production", False),
]


def self_test() -> int:
    falhas = 0
    print(f"guard — self-test ({len(CASOS)} casos)\n")
    for nome, kwargs, esperado_ok, esperado_env, esperado_mut in CASOS:
        d = avaliar(**kwargs)
        ok = (d.approved == esperado_ok
              and d.environment == esperado_env
              and d.mutations_allowed == esperado_mut)
        falhas += not ok
        codigos = ",".join(e["code"] for e in d.errors) or "-"
        print(f"  {'PASS' if ok else 'FALHA':5}  {nome:38} "
              f"env={d.environment:11} mut={str(d.mutations_allowed):5} "
              f"scope={d.scope:5} erros={codigos}")
    print()
    if falhas:
        print(f"{falhas} caso(s) divergente(s).")
        return BLOQUEADO
    print("Todos os casos conforme. Guard operacional.")
    return APROVADO


def main() -> int:
    ap = argparse.ArgumentParser(
        description="State 0 — valida modo, oráculo e segurança de ambiente.")
    ap.add_argument("--url")
    ap.add_argument("--mode", choices=MODOS + ("smoke",),
                    help="regression | spec-driven")
    ap.add_argument("--oracle", help="caminho de arquivo ou texto do requisito")
    ap.add_argument("--allow-production", action="store_true")
    ap.add_argument("--allowlist", type=Path,
                    help="arquivo com hosts de produção permitidos, um por linha")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if not args.url or not args.mode:
        ap.print_usage()
        print("\n--url e --mode são obrigatórios, ou use --self-test.", file=sys.stderr)
        return ERRO_DE_USO

    return avaliar(
        url=args.url,
        mode=args.mode,
        oracle=args.oracle,
        allow_production=args.allow_production,
        allowlist_path=args.allowlist,
    ).emit()


if __name__ == "__main__":
    raise SystemExit(main())
