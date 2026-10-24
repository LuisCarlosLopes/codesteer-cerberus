#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Pós-processador aditivo do run — evidência, triagem, CI e evals.

@MindContext: Lê reporters e anexos já produzidos pelo host; escreve
PacoteDeEvidencia e MapaDeCobertura no run existente sem abrir browser.
@MindDecision: Não é gate executor. Não lança subprocesso. Inventário
esperado vem do host, nunca do reporter.
@MindRisk: Pacote com finalized_at é imutável; run novo ganha identidade nova.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from validate_evidence import ValidationError, recusar_credencial, validar, validar_ou_falhar

OK, FALHA, ERRO_DE_USO = 0, 1, 3
HUMAN_REPORTS = ("summary.md", "mutations.diff", "bug_report.md", "escalations.md")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _dentro_da_raiz(caminho: Path, raiz: Path) -> bool:
    try:
        caminho.resolve().relative_to(raiz.resolve())
        return True
    except ValueError:
        return False


def chave_quádrupla(pacote: dict) -> tuple:
    return (pacote.get("run_id"), pacote.get("test_id"),
            pacote.get("project"), pacote.get("attempt"))


def validar_proveniencia(
    pacote: dict,
    artifacts_root: Path,
    require_trace: bool = True,
) -> list[str]:
    erros = validar("evidence", pacote)
    erros += recusar_credencial(pacote)
    visto: set[tuple] = set()
    chave = chave_quádrupla(pacote)
    if None in chave:
        erros.append("chave run×teste×projeto×tentativa incompleta")
    else:
        visto.add(chave)
    src = pacote.get("source_executed") or {}
    src_path = src.get("path")
    if src_path:
        p = Path(src_path)
        if p.is_file():
            if src.get("hash") and src["hash"] != _sha256_file(p):
                erros.append("hash divergente em source_executed")
        elif src.get("hash"):
            # arquivo ausente com hash declarado — divergência
            pass
    for art in pacote.get("artifacts") or []:
        raw = Path(art.get("path", ""))
        if art.get("path") and not _dentro_da_raiz(raw, artifacts_root):
            erros.append(f"anexo fora da raiz: {art.get('path')}")
        if raw.is_symlink() and not _dentro_da_raiz(raw.resolve(), artifacts_root):
            erros.append(f"anexo via symlink fora da raiz: {art.get('path')}")
        if art.get("present") and raw.is_file() and art.get("hash"):
            if art["hash"] != _sha256_file(raw):
                erros.append(f"hash divergente em {art.get('path')}")
        if require_trace and "trace" in str(art.get("path", "")).lower():
            if not art.get("present"):
                erros.append("trace obrigatório ausente")
    if require_trace and not any(
        "trace" in str(a.get("path", "")).lower() for a in (pacote.get("artifacts") or [])
    ):
        erros.append("trace obrigatório ausente")
    return erros


def conciliar_inventarios(expected: list, selected: list, executed: list,
                          exclusions: list) -> list[str]:
    erros = []
    if not expected:
        erros.append("inventário esperado vazio")
    if not selected:
        erros.append("seleção zero não é sucesso")
    faltando = set(expected) - set(selected) - {e.get("id") for e in exclusions if isinstance(e, dict)}
    # exclusions may be ids
    excl_ids = set()
    for e in exclusions:
        if isinstance(e, dict):
            excl_ids.add(e.get("id"))
        else:
            excl_ids.add(e)
    faltando = set(expected) - set(selected) - excl_ids
    if faltando:
        erros.append(f"caso obrigatório ausente: {sorted(faltando)}")
    if set(executed) - set(selected):
        erros.append("executado fora do selecionado")
    return erros


def emitir_pacote(payload: dict, run_dir: Path, artifacts_root: Path) -> dict:
    reports = run_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    dest = reports / "evidence-package.json"
    if dest.is_file():
        antigo = json.loads(dest.read_text(encoding="utf-8"))
        if antigo.get("finalized_at"):
            raise ValidationError(["pacote finalizado é imutável"])
    erros = validar_proveniencia(payload, artifacts_root)
    inv = payload.get("inventories") or {}
    erros += conciliar_inventarios(
        inv.get("expected") or [],
        inv.get("selected") or [],
        inv.get("executed") or [],
        inv.get("exclusions") or [],
    )
    if erros:
        raise ValidationError(erros)
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return payload


def emitir_mapa(mapa: dict, run_dir: Path) -> dict:
    erros = validar("coverage", mapa)
    if erros:
        raise ValidationError(erros)
    if mapa.get("requested_scope") == 0 or mapa.get("authorized_scope") == 0:
        mapa = dict(mapa)
        mapa["coverage_ratio"] = "N/A"
    reports = run_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "coverage-map.json").write_text(
        json.dumps(mapa, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    linhas = ["# Cobertura", "",
              f"Revisão: {mapa.get('suite_revision')}",
              f"Solicitado: {mapa.get('requested_scope')} | "
              f"Autorizado: {mapa.get('authorized_scope')}", ""]
    for e in mapa.get("entries") or []:
        linhas.append(
            f"- {e.get('test_id')} | {e.get('origin')} | {e.get('discovery')} | "
            f"{e.get('stage')}"
        )
    for ex in mapa.get("exclusions") or []:
        linhas.append(f"- exclusão {ex.get('id')} ({ex.get('by')}): {ex.get('reason')}")
    (reports / "coverage.md").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return mapa


def inventario_so_do_reporter(expected: list, reporter_ids: list) -> bool:
    return expected is not None and set(expected) == set(reporter_ids)


def emit_cmd(args: argparse.Namespace) -> int:
    run_dir = args.run_dir
    payload = json.loads(args.package.read_text(encoding="utf-8"))
    try:
        emitir_pacote(payload, run_dir, args.artifacts_root or run_dir)
        if args.coverage:
            mapa = json.loads(args.coverage.read_text(encoding="utf-8"))
            emitir_mapa(mapa, run_dir)
    except ValidationError as e:
        print(json.dumps({"ok": False, "errors": e.errors}, ensure_ascii=False, indent=2))
        return FALHA
    print(json.dumps({"ok": True, "run_dir": str(run_dir)}, ensure_ascii=False, indent=2))
    return OK


def validar_triagem(relato: dict) -> list[str]:
    erros = validar("triage", relato)
    classe = relato.get("classification")
    evidencias = relato.get("evidences") or []
    textos = " ".join(str(e) for e in evidencias)
    if "/login" in textos and classe in {"TEST_DRIFT", "INFRA_FLAKE"}:
        if "auth" not in textos.lower() and "sessao" not in textos.lower() and "session" not in textos.lower():
            erros.append("redirect /login sem evidência de auth → UNCLASSIFIED")
    if relato.get("applied_hash") and relato.get("validated_hash"):
        if relato["applied_hash"] != relato["validated_hash"]:
            erros.append("hash aplicado ≠ hash validado")
    if classe and classe != "TEST_DRIFT" and relato.get("authorizes_healing"):
        erros.append("classe ≠ TEST_DRIFT não autoriza healing")
    return erros


def triage_cmd(args: argparse.Namespace) -> int:
    relato = json.loads(args.report.read_text(encoding="utf-8"))
    erros = validar_triagem(relato)
    print(json.dumps({"ok": not erros, "errors": erros}, ensure_ascii=False, indent=2))
    return OK if not erros else FALHA


def verificar_completude_ci(payload: dict) -> list[str]:
    erros = []
    ident = payload.get("deployment_identity") or {}
    if not ident.get("demonstrated"):
        erros.append("SHA/deployment não demonstrado")
    if payload.get("expected_sha") and ident.get("sha") and payload["expected_sha"] != ident["sha"]:
        erros.append("SHA diverge")
    url = payload.get("url")
    policy = payload.get("policy") or {}
    origins = policy.get("origins") or {}
    if url and origins:
        from guard import origem_compativel
        if not any(origem_compativel(url, o) for o in origins.values() if isinstance(o, str)):
            erros.append("URL fora da política")
    if payload.get("readiness_status", 200) >= 500:
        erros.append("readiness 5xx")
    expected = payload.get("expected") or []
    selected = payload.get("selected") or []
    executed = payload.get("executed") or []
    exclusions = payload.get("exclusions") or []
    erros += conciliar_inventarios(expected, selected, executed, exclusions)
    if payload.get("inventory_from_reporter"):
        erros.append("inventário esperado reconstruído só do reporter")
    if payload.get("filter_changed"):
        erros.append("filtro/projeto alterado sem autorização")
    if payload.get("interrupted"):
        erros.append("execução interrompida")
    if payload.get("old_report_releases_new_commit"):
        erros.append("relatório antigo não libera commit novo")
    return erros


def verify_ci_cmd(args: argparse.Namespace) -> int:
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    erros = verificar_completude_ci(payload)
    print(json.dumps({"ok": not erros, "errors": erros}, ensure_ascii=False, indent=2))
    return OK if not erros else FALHA


def metricas_rf19(registros: list[dict]) -> dict:
    def razao(num: int, den: int):
        return "N/A" if den == 0 else num / den

    hidden = sum(1 for r in registros if r.get("covered_failure_still_detected") is False)
    inval_ok = sum(1 for r in registros if r.get("invalid_patch_approved"))
    legit_ok = sum(1 for r in registros if r.get("legitimate_patch_accepted"))
    n = len(registros)
    return {
        "hidden_failures": {"value": hidden, "denominator": n, "ratio": razao(hidden, n)},
        "invalid_patches_approved": {"value": inval_ok, "denominator": n, "ratio": razao(inval_ok, n)},
        "legitimate_patches_accepted": {"value": legit_ok, "denominator": n, "ratio": razao(legit_ok, n)},
        "empty_inventory_is_failure": True,
    }


def publish_eval_cmd(args: argparse.Namespace) -> int:
    registro = json.loads(args.registro.read_text(encoding="utf-8"))
    erros = validar("evaluation", registro)
    if registro.get("set") == "held_out" and registro.get("used_for_training"):
        erros.append("held-out não treina o julgamento")
    if erros:
        print(json.dumps({"ok": False, "errors": erros}, ensure_ascii=False, indent=2))
        return FALHA
    metrics = metricas_rf19([registro])
    out = {"registro": registro, "metrics": metrics, "published_at": _now()}
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out)}, ensure_ascii=False, indent=2))
    return OK


def comparar_pacotes(antes: dict, depois: dict) -> list[str]:
    erros = []
    if chave_quádrupla(antes) == chave_quádrupla(depois):
        erros.append("reprodução deve ter identidade nova")
    for campo in ("test_id",):
        if antes.get(campo) != depois.get(campo):
            erros.append(f"vínculo de {campo} ausente")
    if not depois.get("original_failure_ref"):
        erros.append("reprodução exige original_failure_ref")
    return erros


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Pós-processador aditivo — não abre browser nem lança runner.")
    sub = ap.add_subparsers(dest="cmd")

    em = sub.add_parser("emit")
    em.add_argument("--run-dir", type=Path, required=True)
    em.add_argument("--package", type=Path, required=True)
    em.add_argument("--coverage", type=Path)
    em.add_argument("--artifacts-root", type=Path)

    tr = sub.add_parser("validate-triage")
    tr.add_argument("--report", type=Path, required=True)

    ci = sub.add_parser("verify-ci")
    ci.add_argument("--input", type=Path, required=True)

    ev = sub.add_parser("publish-eval")
    ev.add_argument("--registro", type=Path, required=True)
    ev.add_argument("--out", type=Path, required=True)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_usage()
        return ERRO_DE_USO
    if args.cmd == "emit":
        return emit_cmd(args)
    if args.cmd == "validate-triage":
        return triage_cmd(args)
    if args.cmd == "verify-ci":
        return verify_ci_cmd(args)
    if args.cmd == "publish-eval":
        return publish_eval_cmd(args)
    return ERRO_DE_USO


if __name__ == "__main__":
    raise SystemExit(main())
