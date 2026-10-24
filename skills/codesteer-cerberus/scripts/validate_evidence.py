#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Validação fail-closed dos schemas v1 de evidência, mapa e política.

@MindContext: Contrato determinístico que P2 consome — baseline, evidência,
cobertura, política, triagem e avaliação — sem I/O de browser ou modelo.
@MindSpec: schema_version deve ser 1; campo obrigatório ausente ou credencial
no payload → falha fechada, nunca “aprovado com aviso”.
@MindRisk: Este módulo não emite pacote nem lança runner; só valida.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

OK, FALHA, ERRO_DE_USO = 0, 1, 3

SCHEMA_KINDS = (
    "baseline", "evidence", "coverage", "policy", "triage", "evaluation",
)

RE_SENSITIVE_KEY = re.compile(
    r"(?i)(password|secret|token|api[_-]?key|authorization|credential|"
    r"private[_-]?key)$"
)
RE_SECRET_VALUE = re.compile(
    r"(?i)^(sk-|ghp_|github_pat_|Bearer\s+\S{8,}|-----BEGIN )"
)
RE_ISO = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _as_int_version(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _exigir(obj: dict, *campos: str) -> list[str]:
    return [f"campo obrigatório ausente: {c}" for c in campos if c not in obj]


def _tipo(obj: Any, esperado: type, nome: str) -> list[str]:
    if not isinstance(obj, esperado):
        return [f"{nome} deve ser {esperado.__name__}"]
    return []


def recusar_credencial(obj: Any, caminho: str = "$") -> list[str]:
    erros: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{caminho}.{k}"
            if RE_SENSITIVE_KEY.search(str(k)):
                if isinstance(v, str) and v and not v.startswith("process.env."):
                    erros.append(f"credencial em {here}")
            erros.extend(recusar_credencial(v, here))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            erros.extend(recusar_credencial(item, f"{caminho}[{i}]"))
    elif isinstance(obj, str) and RE_SECRET_VALUE.search(obj.strip()):
        erros.append(f"credencial em {caminho}")
    return erros


def _versao(obj: dict) -> list[str]:
    if "schema_version" not in obj:
        return ["campo obrigatório ausente: schema_version"]
    ver = _as_int_version(obj["schema_version"])
    if ver != 1:
        return [f"schema_version desconhecida: {obj['schema_version']!r}"]
    return []


def _iso(valor: Any, nome: str) -> list[str]:
    if not isinstance(valor, str) or not RE_ISO.match(valor):
        return [f"{nome} deve ser DateTime ISO-8601"]
    try:
        datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        return [f"{nome} não é DateTime válido"]
    return []


def validar_baseline(obj: dict) -> list[str]:
    erros = _versao(obj)
    erros += _exigir(
        obj, "origin_revision", "content_hashes", "authorized_root",
        "tests", "truth_source", "policy_profile", "extracted_at",
    )
    if erros:
        return erros
    erros += _tipo(obj["origin_revision"], str, "origin_revision")
    erros += _tipo(obj["content_hashes"], dict, "content_hashes")
    erros += _tipo(obj["authorized_root"], str, "authorized_root")
    erros += _tipo(obj["tests"], list, "tests")
    erros += _tipo(obj["policy_profile"], str, "policy_profile")
    erros += _iso(obj["extracted_at"], "extracted_at")
    ts = obj["truth_source"]
    if ts != "observed":
        if not isinstance(ts, dict):
            erros.append("truth_source deve ser objeto ou 'observed'")
        else:
            erros += _exigir(ts, "path", "hash", "status")
    for i, teste in enumerate(obj.get("tests") or []):
        if not isinstance(teste, dict):
            erros.append(f"tests[{i}] inválido")
            continue
        erros += _exigir(teste, "test_id", "assertions")
        for j, ass in enumerate(teste.get("assertions") or []):
            if not isinstance(ass, dict):
                erros.append(f"tests[{i}].assertions[{j}] inválido")
                continue
            erros += _exigir(ass, "target", "matcher", "arguments", "context")
    return erros


def validar_evidence(obj: dict) -> list[str]:
    erros = _versao(obj)
    erros += _exigir(
        obj, "run_id", "test_id", "project", "attempt", "mode", "policy",
        "suite_revision", "target", "inventories", "source_executed",
        "artifacts", "finalized_at",
    )
    if "schema_version" in obj and _as_int_version(obj["schema_version"]) != 1:
        return erros
    for campo in ("run_id", "test_id", "project", "mode", "policy",
                  "suite_revision", "target"):
        if campo in obj:
            erros += _tipo(obj[campo], str, campo)
    if "attempt" in obj and (
        not isinstance(obj["attempt"], int) or isinstance(obj["attempt"], bool)
        or obj["attempt"] < 1
    ):
        erros.append("attempt deve ser inteiro >= 1")
    if "inventories" in obj:
        inv = obj["inventories"]
        erros += _tipo(inv, dict, "inventories")
        if isinstance(inv, dict):
            for chave in ("expected", "selected", "executed", "exclusions"):
                if chave not in inv:
                    erros.append(f"inventories.{chave} ausente")
                elif not isinstance(inv[chave], list):
                    erros.append(f"inventories.{chave} deve ser lista")
    if "source_executed" in obj:
        src = obj["source_executed"]
        if not isinstance(src, dict):
            erros.append("source_executed deve ser objeto")
        else:
            erros += _exigir(src, "path", "hash")
    if "artifacts" in obj:
        if not isinstance(obj["artifacts"], list):
            erros.append("artifacts deve ser lista")
        else:
            for i, art in enumerate(obj["artifacts"]):
                if not isinstance(art, dict):
                    erros.append(f"artifacts[{i}] inválido")
                    continue
                erros += _exigir(art, "path", "hash", "present")
    if "finalized_at" in obj:
        erros += _iso(obj["finalized_at"], "finalized_at")
    if "target" in obj and isinstance(obj["target"], str):
        parsed = urlparse(obj["target"])
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            erros.append("target deve ser URL http(s) com host")
        if parsed.hostname and "vercel.app" in parsed.hostname:
            erros.append("alvo remoto de produto não é permitido no manifesto")
    return erros


def validar_coverage(obj: dict) -> list[str]:
    erros = _versao(obj)
    erros += _exigir(
        obj, "suite_revision", "requested_scope", "authorized_scope", "entries",
    )
    if "entries" in obj and not isinstance(obj["entries"], list):
        erros.append("entries deve ser lista")
    ids: set[str] = set()
    for i, entry in enumerate(obj.get("entries") or []):
        if not isinstance(entry, dict):
            erros.append(f"entries[{i}] inválido")
            continue
        erros += _exigir(
            entry, "origin", "discovery", "stage", "feature", "scenario", "test_id",
        )
        if entry.get("origin") not in {"approved", "observed"}:
            erros.append(f"entries[{i}].origin inválida")
        if entry.get("discovery") not in {"explored", "partial", "blocked"}:
            erros.append(f"entries[{i}].discovery inválida")
        if entry.get("stage") not in {"proposed", "generated", "executed"}:
            erros.append(f"entries[{i}].stage inválido")
        tid = entry.get("test_id")
        if isinstance(tid, str):
            if tid in ids:
                erros.append(f"test_id duplicado: {tid}")
            ids.add(tid)
    if "exclusions" in obj and not isinstance(obj["exclusions"], list):
        erros.append("exclusions deve ser lista")
    for i, ex in enumerate(obj.get("exclusions") or []):
        if not isinstance(ex, dict):
            erros.append(f"exclusions[{i}] inválida")
            continue
        erros += _exigir(ex, "id", "reason", "by")
        if ex.get("by") not in {"guard", "policy"}:
            erros.append(f"exclusions[{i}].by inválido")
    return erros


def validar_policy(obj: dict) -> list[str]:
    erros = _versao(obj)
    erros += _exigir(
        obj, "origins", "allowed_paths", "mode", "scope", "budget",
        "approval_refs", "content_hash",
    )
    origins = obj.get("origins")
    if isinstance(origins, dict):
        for amb, origem in origins.items():
            if not isinstance(origem, str) or any(ch in origem for ch in "*?"):
                erros.append(f"origins.{amb} não pode usar curinga amplo")
            if isinstance(origem, str) and "vercel.app" in origem:
                erros.append("alvo remoto de produto não é permitido na política")
    elif "origins" in obj:
        erros.append("origins deve ser mapa")
    if "allowed_paths" in obj and not isinstance(obj["allowed_paths"], list):
        erros.append("allowed_paths deve ser lista")
    if obj.get("mode") not in {None, "regression", "spec-driven", "smoke"}:
        if "mode" in obj:
            erros.append("mode inválido")
    if obj.get("scope") not in {None, "CRUDL", "RL"}:
        if "scope" in obj:
            erros.append("scope inválido")
    if "budget" in obj and not isinstance(obj["budget"], dict):
        erros.append("budget deve ser objeto")
    if "approval_refs" in obj and not isinstance(obj["approval_refs"], list):
        erros.append("approval_refs deve ser lista")
    if "content_hash" in obj and not isinstance(obj["content_hash"], str):
        erros.append("content_hash deve ser string")
    return erros


def validar_triage(obj: dict) -> list[str]:
    erros = _versao(obj)
    erros += _exigir(
        obj, "classification", "mode", "test_id", "intent", "evidences",
        "evidence_package_ref",
    )
    classes = {
        "INFRA_FLAKE", "TEST_DRIFT", "BEHAVIOR_CHANGED",
        "PRODUCT_BUG", "CRITICAL_PATH_DOWN", "UNCLASSIFIED",
    }
    if obj.get("classification") not in {None, *classes}:
        if "classification" in obj:
            erros.append("classification inválida")
    mode = obj.get("mode")
    classe = obj.get("classification")
    if classe == "PRODUCT_BUG" and mode in {"regression", "smoke"}:
        erros.append("PRODUCT_BUG é inalcançável em regression/smoke")
    if classe == "PRODUCT_BUG":
        erros += _exigir(obj, "truth_ref", "citation", "source_hash")
        if not obj.get("contradiction"):
            erros.append("PRODUCT_BUG exige evidência de contradição")
    if obj.get("confidence_authorizes"):
        erros.append("confiança autodeclarada não autoriza")
    return erros


def validar_evaluation(obj: dict) -> list[str]:
    erros = _versao(obj)
    erros += _exigir(
        obj, "scenario_id", "set", "expected_label", "label_source", "attempts",
    )
    if obj.get("set") not in {None, "dev", "held_out"}:
        if "set" in obj:
            erros.append("set deve ser dev ou held_out")
    if not obj.get("label_source"):
        if "label_source" in obj:
            erros.append("label_source (fonte e justificativa) é obrigatório")
    if obj.get("expected_label_from_agent"):
        erros.append("expected_label não pode vir do agente avaliado")
    if "attempts" in obj:
        if not isinstance(obj["attempts"], list):
            erros.append("attempts deve ser lista")
        elif len(obj["attempts"]) > 3:
            erros.append("attempts excede 3")
    return erros


VALIDADORES = {
    "baseline": validar_baseline,
    "evidence": validar_evidence,
    "coverage": validar_coverage,
    "policy": validar_policy,
    "triage": validar_triage,
    "evaluation": validar_evaluation,
}


def validar(kind: str, obj: Any) -> list[str]:
    if kind not in VALIDADORES:
        return [f"schema desconhecido: {kind}"]
    if not isinstance(obj, dict):
        return ["payload deve ser objeto JSON"]
    erros = VALIDADORES[kind](obj)
    erros += recusar_credencial(obj)
    return erros


def validar_ou_falhar(kind: str, obj: Any) -> dict:
    erros = validar(kind, obj)
    if erros:
        raise ValidationError(erros)
    return obj


def carregar(caminho: Path) -> Any:
    return json.loads(caminho.read_text(encoding="utf-8"))


def self_test() -> int:
    falhas = 0
    casos = [
        ("baseline sem versão", "baseline", {"origin_revision": "a"}, False),
        ("evidence versão 2", "evidence", {"schema_version": 2}, False),
        ("policy com senha", "policy", {
            "schema_version": 1, "origins": {"local": "http://127.0.0.1:4173"},
            "allowed_paths": ["evals"], "mode": "smoke", "scope": "RL",
            "budget": {}, "approval_refs": ["r1"], "content_hash": "abc",
            "password": "hunter2",
        }, False),
        ("coverage incompleta", "coverage", {"schema_version": 1}, False),
    ]
    print(f"validate_evidence — self-test ({len(casos)} casos)\n")
    for nome, kind, payload, deve_passar in casos:
        erros = validar(kind, payload)
        ok = (not erros) == deve_passar
        falhas += not ok
        print(f"  {'PASS' if ok else 'FALHA':5}  {nome}")
    print()
    if falhas:
        print(f"{falhas} caso(s) divergente(s).")
        return FALHA
    print("Todos os casos conforme. Validador operacional.")
    return OK


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Valida schemas v1 de evidência/cobertura/política.")
    ap.add_argument("--schema", choices=SCHEMA_KINDS)
    ap.add_argument("arquivo", nargs="?", type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.schema or not args.arquivo:
        ap.print_usage()
        return ERRO_DE_USO
    if not args.arquivo.is_file():
        print(f"arquivo não encontrado: {args.arquivo}", file=sys.stderr)
        return ERRO_DE_USO
    try:
        payload = carregar(args.arquivo)
    except json.JSONDecodeError as e:
        print(json.dumps({"ok": False, "errors": [f"JSON inválido: {e}"]},
                         ensure_ascii=False, indent=2))
        return FALHA
    erros = validar(args.schema, payload)
    print(json.dumps({"ok": not erros, "errors": erros},
                     ensure_ascii=False, indent=2))
    return OK if not erros else FALHA


if __name__ == "__main__":
    raise SystemExit(main())
